from __future__ import annotations

import numpy as np
import pytest
import torch

from metronome.data.windows import make_windows
from metronome.models import build
from metronome.train.trainer import TrainConfig, evaluate_loss, fit, predict, seed_everything, state_hash

L, H, C = 48, 12, 2


def _data(seed: int = 0, n: int = 600) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    v = np.stack([np.sin(2 * np.pi * t / 24), np.cos(2 * np.pi * t / 24)], axis=1) + rng.normal(
        0, 0.05, (n, C)
    )
    x, y = make_windows(v.astype(np.float32), L, H)
    cut = int(len(x) * 0.8)
    return x[:cut], y[:cut], x[cut:], y[cut:]


def test_fit_improves_over_init_and_restores_best() -> None:
    xtr, ytr, xva, yva = _data()
    seed_everything(0)
    model = build("dlinear", L, H, C)
    before = evaluate_loss(model, xva, yva, "mse", 256)
    result = fit(model, xtr, ytr, xva, yva, TrainConfig(max_epochs=5, patience=5, batch_size=16), seed=0)
    after = evaluate_loss(model, xva, yva, "mse", 256)
    assert after < before
    assert result.best_val == pytest.approx(after, rel=1e-5)
    assert result.epochs == 5 and result.best_epoch >= 1 and len(result.history) == 5


def test_fit_is_deterministic_for_same_seed() -> None:
    xtr, ytr, xva, yva = _data()
    hashes = []
    for _ in range(2):
        seed_everything(7)
        model = build("dlinear", L, H, C)
        fit(model, xtr, ytr, xva, yva, TrainConfig(max_epochs=2, batch_size=16), seed=7)
        hashes.append(state_hash(model))
    assert hashes[0] == hashes[1]
    seed_everything(8)
    other = build("dlinear", L, H, C)
    fit(other, xtr, ytr, xva, yva, TrainConfig(max_epochs=2, batch_size=16), seed=8)
    assert state_hash(other) != hashes[0]


def test_early_stopping_triggers_and_lr_halves() -> None:
    xtr, ytr, xva, yva = _data()
    seed_everything(0)
    model = build("linear", L, H, C)
    cfg = TrainConfig(max_epochs=30, patience=2, batch_size=16, lr=0.05)
    result = fit(model, xtr, ytr, xva, yva, cfg, seed=0)
    assert result.stopped_early and result.epochs < 30
    lrs = [h["lr"] for h in result.history]
    assert lrs[0] == pytest.approx(0.05) and lrs[1] == pytest.approx(0.025)


def test_onecycle_schedule_runs() -> None:
    xtr, ytr, xva, yva = _data()
    seed_everything(0)
    model = build("linear", L, H, C)
    result = fit(
        model, xtr, ytr, xva, yva, TrainConfig(max_epochs=3, patience=3, lr_schedule="onecycle"), seed=0
    )
    assert result.epochs == 3


def test_predict_matches_forward() -> None:
    xtr, _ytr, _, _ = _data()
    model = build("dlinear", L, H, C)
    out = predict(model, xtr[:10], batch_size=4)
    with torch.inference_mode():
        ref = model(torch.from_numpy(np.ascontiguousarray(xtr[:10]))).numpy()
    np.testing.assert_allclose(out, ref, atol=1e-6)
    assert predict(model, xtr[:0]).shape == (0, H, C)


def test_warm_start_continues_from_given_weights() -> None:
    xtr, ytr, xva, yva = _data()
    seed_everything(0)
    model = build("dlinear", L, H, C)
    fit(model, xtr, ytr, xva, yva, TrainConfig(max_epochs=3, batch_size=16), seed=0)
    warm_hash = state_hash(model)
    warm_val = evaluate_loss(model, xva, yva, "mse", 256)
    fit(model, xtr, ytr, xva, yva, TrainConfig(max_epochs=1, patience=1, lr=1e-4, batch_size=16), seed=1)
    assert state_hash(model) != warm_hash
    assert evaluate_loss(model, xva, yva, "mse", 256) <= warm_val * 1.05
