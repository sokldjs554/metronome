from __future__ import annotations

import numpy as np
import pytest

tf = pytest.importorskip("tensorflow")
torch = pytest.importorskip("torch")


def test_keras_dlinear_matches_pytorch_after_weight_transfer() -> None:
    from metronome.models import build
    from metronome.tfmodels import TFDLinear, load_torch_state, predict_tf

    torch.manual_seed(0)
    for kernel in (1, 13, 25):
        tm = build("dlinear", 48, 12, 3, kernel_size=kernel).eval()
        km = TFDLinear(48, 12, 3, kernel_size=kernel)
        load_torch_state(km, {k: v.detach().numpy() for k, v in tm.state_dict().items()})
        x = np.random.default_rng(kernel).normal(size=(16, 48, 3)).astype(np.float32)
        with torch.no_grad():
            expected = tm(torch.from_numpy(x)).numpy()
        assert np.max(np.abs(predict_tf(km, x) - expected)) < 1e-5


def test_lockstep_training_tracks_pytorch() -> None:
    """Same init, same batch order, same recipe: the two frameworks end at nearly the same model."""
    from metronome.eval.ltsf import dlinear_recipe
    from metronome.models import build
    from metronome.tfmodels import TFDLinear, fit_tf, load_torch_state, predict_tf
    from metronome.train.trainer import fit, predict, seed_everything

    rng = np.random.default_rng(0)
    t = np.arange(900)
    series = np.stack(
        [np.sin(2 * np.pi * t / 24 + c) + 0.1 * rng.normal(size=len(t)) for c in range(2)], axis=1
    )
    windows = np.lib.stride_tricks.sliding_window_view(series, 48 + 12, axis=0).transpose(0, 2, 1)
    x, y = windows[:, :48].astype(np.float32), windows[:, 48:].astype(np.float32)
    x_tr, y_tr, x_va, y_va = x[:600], y[:600], x[600:], y[600:]
    seed_everything(3)
    tm = build("dlinear", 48, 12, 2, kernel_size=13)
    km = TFDLinear(48, 12, 2, kernel_size=13)
    load_torch_state(km, {k: v.detach().numpy() for k, v in tm.state_dict().items()})
    recipe = dlinear_recipe(1)
    recipe.max_epochs = 4
    ft = fit(tm, x_tr, y_tr, x_va, y_va, recipe, 3)
    fk = fit_tf(km, x_tr, y_tr, x_va, y_va, seed=3, max_epochs=4)
    mse_t = float(np.mean((predict(tm, x_va) - y_va) ** 2))
    mse_k = float(np.mean((predict_tf(km, x_va) - y_va) ** 2))
    assert ft.best_epoch == fk["best_epoch"]
    assert abs(mse_k - mse_t) / mse_t < 0.01
