from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from metronome.cadence.cache import CacheConfig, build_cache, build_warm_chain, load_stream, train_day
from metronome.cadence.simulate import (
    Cache,
    evaluate_schedule,
    run_policies,
    schedule_periodic,
    schedule_triggered,
    simulate_cache,
)
from metronome.data.sources import PREPARED, PreparedSpec
from metronome.train.trainer import TrainConfig

SMALL = TrainConfig(lr=0.01, batch_size=32, max_epochs=2, patience=2, threads=1)


@pytest.fixture
def small_cfg(processed: tuple[str, Path], monkeypatch: pytest.MonkeyPatch) -> tuple[CacheConfig, Path, Path]:
    name, processed_dir = processed
    monkeypatch.setitem(
        PREPARED, name, PreparedSpec(name=name, source="synthetic", freq="1h", stream_days=20)
    )
    cfg = CacheConfig(dataset=name, seed=0, lookback=48, horizon=12, val_days=3, stream_days=20, train=SMALL)
    return cfg, processed_dir, processed_dir.parent / "cache"


def test_load_stream_origins_and_days(small_cfg: tuple[CacheConfig, Path, Path]) -> None:
    cfg, processed_dir, _ = small_cfg
    data = load_stream(cfg.dataset, processed_dir, cfg.lookback, cfg.horizon, 20)
    assert data.n_days == 20
    assert data.stream_origins[0] == data.split.stream_start
    assert data.stream_origins[-1] + cfg.horizon == len(data.values)
    assert data.origin_day[0] == 0 and data.origin_day[-1] == 19
    assert np.all(np.diff(data.origin_day) >= 0)


def test_train_day_uses_only_past_rows(small_cfg: tuple[CacheConfig, Path, Path]) -> None:
    cfg, processed_dir, _ = small_cfg
    data = load_stream(cfg.dataset, processed_dir, cfg.lookback, cfg.horizon, 20)
    _, _, info = train_day(data, 5, cfg)
    assert info["train_rows"][1] <= int(data.split.day_starts[5]) - cfg.val_days * 24
    assert info["val_mae_fixed"] > 0 and info["fit"]["epochs"] == 2


def test_cache_build_and_policies_end_to_end(small_cfg: tuple[CacheConfig, Path, Path]) -> None:
    cfg, processed_dir, cache_dir = small_cfg
    out = build_cache(cfg, processed_dir, cache_dir, workers=2, progress=False)
    assert out.exists()
    cache = Cache.load(cache_dir, cfg.name)
    assert cache.n_days == 20 and cache.n_channels == 3
    # model m is only evaluated from day m on
    assert np.isnan(cache.abs_sum[5, 4]).all() and np.isfinite(cache.abs_sum[5, 5]).all()
    assert cache.count[0] == 24 and cache.count[-1] == 24 - 12 + 1  # last day: 13 origins have full targets

    results = run_policies(cache, periodic=(1, 7), triggered=("ratio-0.2", "ph-0.1", "adwin-0.01"))
    never, daily = results["never"], results["periodic-1"]
    assert never.n_refits == 0 and never.train_seconds == 0 and all(a == 0 for a in never.active)
    # a model refit on day r serves from day r + 1 (protocol P7)
    assert daily.n_refits == 19 and daily.active[1] == 0 and daily.active[2] == 1 and daily.active[-1] == 18
    assert np.isfinite(never.mae) and np.isfinite(daily.mae)
    assert never.daily_mae[0] == pytest.approx(daily.daily_mae[0])  # same model on day 0
    for res in results.values():
        assert 0 <= res.n_refits <= 19
        assert all(0 <= r < 20 for r in res.refit_days)

    summary = simulate_cache(cache_dir, cfg.name)
    assert set(summary.policies) >= {"never", "periodic-1", "ratio-0.2"}
    comp = next(c for c in summary.comparisons if c["policy"] == "periodic-1" and c["reference"] == "never")
    assert comp["lo"] <= comp["diff"] <= comp["hi"]


def test_schedules_are_consistent() -> None:
    assert schedule_periodic(10, 3) == [3, 6, 9] and schedule_periodic(10, 0) == []


def test_triggered_schedule_refits_after_injected_drift(small_cfg: tuple[CacheConfig, Path, Path]) -> None:
    cfg, _, _ = small_cfg
    n, c = 30, 1
    abs_sum = np.full((n, n, c), np.nan)
    for m in range(n):
        for d in range(m, n):
            abs_sum[m, d] = 0.1 * 24 * cfg.horizon if (d < 15 or m >= 15) else 0.4 * 24 * cfg.horizon
    cache = Cache(
        name="fake",
        abs_sum=abs_sum,
        sq_sum=abs_sum**2,
        count=np.full(n, 24),
        train_seconds=np.ones(n),
        val_mae_fixed=np.full(n, 0.1),
        horizon=cfg.horizon,
        config={"seed": 0},
    )
    refits = schedule_triggered(cache, "ratio-0.2")
    assert refits and 15 + 4 <= refits[0] <= 15 + 4 + 7
    res = evaluate_schedule(cache, "ratio-0.2", refits)
    never = evaluate_schedule(cache, "never", [])
    assert res.mae < never.mae and res.n_refits == len(refits)


def test_warm_chain_runs(small_cfg: tuple[CacheConfig, Path, Path]) -> None:
    cfg, processed_dir, cache_dir = small_cfg
    out = build_warm_chain(cfg, processed_dir, cache_dir, epochs=1, lr=1e-3)
    z = np.load(out)
    assert z["abs_next"].shape == (20, 3) and np.isfinite(z["abs_next"]).all()
    assert z["train_seconds"][1:].min() > 0
