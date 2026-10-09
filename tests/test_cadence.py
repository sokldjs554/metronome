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
    # model m is evaluated on its val_days before it (its validation span) and every day from m on
    assert cache.backward_days == cfg.val_days == 3 and cache.per_day == 24
    assert np.isnan(cache.abs_sum[5, 1]).all() and np.isfinite(cache.abs_sum[5, 2:]).all()
    assert np.isnan(cache.abs_sum[1, :0]).all() and np.isfinite(cache.abs_sum[1, 0:]).all()
    assert cache.count[0] == 24 and cache.count[-1] == 24 - 12 + 1  # last day: 13 origins have full targets

    results = run_policies(cache, periodic=(1, 7), triggered=("ratio-0.2", "ph-0.1", "adwin-0.01"))
    assert "periodic-7+gate" in results  # the cache carries the backward window the gate needs
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
    refits, rejected, reasons = schedule_triggered(cache, "ratio-0.2")
    assert rejected == [] and reasons == {}
    # day 15's errors are visible only once every forecast of that day is resolved: lag days later
    assert cache.resolve_lag_days == 2  # H=12 on 24 origins a day
    assert refits and 15 + cache.resolve_lag_days <= refits[0] <= 15 + cache.resolve_lag_days + 7
    res = evaluate_schedule(cache, "ratio-0.2", refits)
    never = evaluate_schedule(cache, "never", [])
    assert res.mae < never.mae and res.n_refits == len(refits)


def test_warm_chain_runs(small_cfg: tuple[CacheConfig, Path, Path]) -> None:
    cfg, processed_dir, cache_dir = small_cfg
    out = build_warm_chain(cfg, processed_dir, cache_dir, epochs=1, lr=1e-3)
    z = np.load(out)
    assert z["abs_next"].shape == (20, 3) and np.isfinite(z["abs_next"]).all()
    assert z["train_seconds"][1:].min() > 0


def _fake_cache(n: int, horizon: int, level: callable, backward_days: int = 14, per_day: int = 24) -> Cache:
    """Per-(model, day) error sums with model m's error level on day d = level(m, d); model m is
    evaluated on days [m - backward_days, n) like a real cache."""
    abs_sum = np.full((n, n, 1), np.nan)
    for m in range(n):
        for d in range(max(0, m - backward_days), n):
            abs_sum[m, d] = level(m, d) * per_day * horizon
    return Cache(
        name="fake",
        abs_sum=abs_sum,
        sq_sum=abs_sum**2,
        count=np.full(n, per_day),
        train_seconds=np.ones(n),
        val_mae_fixed=np.array([level(m, m) for m in range(n)]),
        horizon=horizon,
        config={"seed": 0},
        per_day=per_day,
        backward_days=backward_days,
    )


def test_resolve_lag_days_from_horizon_and_period() -> None:
    from metronome.cadence.simulate import resolve_lag_days

    # the last origin of day d (hour 23) with H=96 has its last target at day d+4 22:00, so at
    # D 00:00 only days <= D-5 are complete; H=12 -> D-2; H=1 -> D-1; 10-min data, H=96 -> D-2
    assert resolve_lag_days(96, 24) == 5
    assert resolve_lag_days(12, 24) == 2
    assert resolve_lag_days(1, 24) == 1
    assert resolve_lag_days(96, 144) == 2


def test_gate_compares_both_models_on_the_same_resolved_days() -> None:
    """Days whose forecasts are not resolved at the decision time never reach the gate: changing
    them changes neither the two MAEs nor the decision. Both MAEs come from the same days."""
    from metronome.cadence.simulate import gate_decide, resolved_days

    def level(m: int, d: int) -> float:
        return 0.10 if m == 0 else 0.09

    cache = _fake_cache(60, horizon=96, level=level)
    decision = gate_decide(cache, candidate_day=40, incumbent_day=0)
    assert cache.resolve_lag_days == 5
    assert decision.days == list(range(26, 36)) == resolved_days(cache, 40, 14).tolist()
    assert decision.accept and decision.reason == "better"
    assert decision.candidate_mae == pytest.approx(0.09) and decision.incumbent_mae == pytest.approx(0.10)

    # targets after the decision time (days 36..39 are not complete at day 40 00:00) change
    tampered = _fake_cache(60, horizon=96, level=lambda m, d: 5.0 if 36 <= d < 40 and m == 0 else level(m, d))
    tampered.abs_sum[40, 36:40] = 1e-9  # and the candidate looks perfect there
    after = gate_decide(tampered, candidate_day=40, incumbent_day=0)
    assert (after.candidate_mae, after.incumbent_mae, after.accept, after.days) == (
        decision.candidate_mae,
        decision.incumbent_mae,
        decision.accept,
        decision.days,
    )


def test_gate_holds_without_a_full_sample_on_ties_and_non_finite_values() -> None:
    from metronome.cadence.simulate import gate_decide, gate_schedule

    cache = _fake_cache(40, horizon=96, level=lambda m, d: 0.10)
    assert gate_decide(cache, 13, 0).reason == "insufficient_sample"  # window 14 not yet in the stream
    assert gate_decide(cache, 14, 0).reason == "tie" and not gate_decide(cache, 14, 0).accept
    cache.abs_sum[20, 6:16] = np.nan
    assert gate_decide(cache, 20, 0).reason == "nonfinite"
    old = Cache(**{**cache.__dict__, "backward_days": 0})
    assert gate_decide(old, 20, 0).reason == "no_backward_window"
    accepted, rejected, reasons = gate_schedule(cache, [13, 14, 20])
    assert accepted == [] and rejected == [13, 14, 20]
    assert reasons == {"insufficient_sample": 1, "tie": 1, "nonfinite": 1}


def test_gate_rejects_candidates_that_lose_to_the_incumbent() -> None:
    """Models trained on days 15-19 are bad on their own validation days; the gate keeps model 0
    until a candidate that is better there (day 25) comes along. Refits before the window fits in
    the stream are kept out as well, and every trained model is counted."""
    from metronome.cadence.simulate import gate_schedule, run_policies

    def level(m: int, d: int) -> float:
        if m == 0:
            return 0.10
        return 0.30 if 15 <= m < 20 else (0.08 if m >= 25 else 0.10)

    cache = _fake_cache(40, horizon=12, level=level)
    assert cache.resolve_lag_days == 2
    accepted, rejected, reasons = gate_schedule(cache, [5, 12, 15, 25])
    assert accepted == [25] and rejected == [5, 12, 15]
    assert reasons == {"insufficient_sample": 2, "worse": 1}
    res = run_policies(cache, periodic=(5,), triggered=("ratio-0.2",))
    assert res["periodic-5+gate"].mae <= res["periodic-5"].mae
    assert res["periodic-5+gate"].n_trained == res["periodic-5"].n_refits
    assert (
        res["periodic-5+gate"].n_refits + len(res["periodic-5+gate"].rejected_days)
        == res["periodic-5"].n_refits
    )
    assert sum(res["periodic-5+gate"].rejections.values()) == len(res["periodic-5+gate"].rejected_days)


def test_triggered_schedule_reads_only_resolved_days() -> None:
    """A bad day becomes visible to the detector only once all its forecasts are resolved."""
    cache = _fake_cache(40, horizon=96, level=lambda m, d: 0.10 if d != 20 else 5.0, backward_days=0)
    refits, _, _ = schedule_triggered(cache, "ratio-0.1")
    assert refits[0] == 20 + cache.resolve_lag_days == 25


def test_gate_is_blind_to_actuals_that_arrive_after_the_decision(
    processed: tuple[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two streams, identical up to the decision day's 00:00 and different afterwards, give the
    gate the same evaluation sample, the same two MAEs and the same decision."""
    from tests.conftest import synthetic_frame

    from metronome.cadence.simulate import gate_decide
    from metronome.data.pipeline import prepare_frame

    name, processed_dir = processed
    spec = PreparedSpec(name="synth", source="synthetic", freq="1h", stream_days=20)
    monkeypatch.setitem(PREPARED, name, spec)
    cfg = CacheConfig(dataset=name, seed=0, lookback=48, horizon=12, val_days=3, stream_days=20, train=SMALL)
    data = load_stream(name, processed_dir, cfg.lookback, cfg.horizon, 20)
    decision_day = 10
    cutoff = int(data.split.day_starts[decision_day])  # rows before it are known at the decision

    other_dir = tmp_path / "other"
    other = synthetic_frame(drift_at=cutoff)  # same rows before the cutoff, a level shift after
    prepare_frame(other, spec, other_dir / "processed", source_info={"key": "synthetic-after"})
    data_b = load_stream(name, other_dir / "processed", cfg.lookback, cfg.horizon, 20)
    assert np.array_equal(data.values[:cutoff], data_b.values[:cutoff])
    assert not np.array_equal(data.values[cutoff:], data_b.values[cutoff:])

    days = list(range(decision_day - 5, decision_day + 1))
    build_cache(cfg, processed_dir, tmp_path / "cache_a", workers=2, days=[0, *days], progress=False)
    build_cache(
        cfg, other_dir / "processed", tmp_path / "cache_b", workers=2, days=[0, *days], progress=False
    )
    a = Cache.load(tmp_path / "cache_a", cfg.name)
    b = Cache.load(tmp_path / "cache_b", cfg.name)
    da = gate_decide(a, decision_day, 0)
    db = gate_decide(b, decision_day, 0)
    assert da.days == db.days == [7, 8]  # resolved part of the candidate's 3-day validation span
    assert da.reason not in ("insufficient_sample", "nonfinite", "no_backward_window")
    assert da.candidate_mae == pytest.approx(db.candidate_mae, rel=0, abs=0)
    assert da.incumbent_mae == pytest.approx(db.incumbent_mae, rel=0, abs=0)
    assert da.accept == db.accept
    # the two caches do differ where actuals after the cutoff enter: day 9 (unresolved) and later
    assert not np.allclose(a.abs_sum[0, 9], b.abs_sum[0, 9])
