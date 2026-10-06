"""Simulate retraining policies on a refit cache and summarize them with bootstrap intervals."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from metronome.drift.detectors import make_detector
from metronome.eval.bootstrap import paired_block_bootstrap

RESOLVE_LAG_DAYS = 4  # a 96-step hourly forecast made on day D is fully resolved by the end of day D+3


@dataclass
class Cache:
    name: str
    abs_sum: np.ndarray  # (M, D, C) errors of model trained on day m, evaluated on day d
    sq_sum: np.ndarray
    count: np.ndarray  # (D,) number of origins per evaluation day
    train_seconds: np.ndarray  # (M,)
    val_mae_fixed: np.ndarray  # (M,)
    horizon: int
    config: dict[str, Any]

    @property
    def n_days(self) -> int:
        return int(self.abs_sum.shape[1])

    @property
    def n_channels(self) -> int:
        return int(self.abs_sum.shape[2])

    def daily_mae(self, model_day: int, eval_day: int) -> float:
        n = self.count[eval_day] * self.horizon * self.n_channels
        return float(self.abs_sum[model_day, eval_day].sum() / n) if n else float("nan")

    @classmethod
    def load(cls, cache_dir: Path, name: str) -> Cache:
        z = np.load(cache_dir / f"{name}.npz")
        meta = json.loads((cache_dir / f"{name}.json").read_text())
        return cls(
            name=name,
            abs_sum=z["abs_sum"],
            sq_sum=z["sq_sum"],
            count=z["count"],
            train_seconds=z["train_seconds"],
            val_mae_fixed=z["val_mae_fixed"],
            horizon=int(meta["config"]["horizon"]),
            config=meta["config"],
        )


@dataclass
class PolicyResult:
    policy: str
    mae: float
    mse: float
    n_refits: int
    train_seconds: float
    refit_days: list[int]
    active: list[int]
    daily_mae: list[float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def schedule_periodic(n_days: int, k: int) -> list[int]:
    return list(range(k, n_days, k)) if k > 0 else []


def _activate(n_days: int, refit_days: list[int]) -> np.ndarray:
    """Model trained on refit day r serves from day r+1 (protocol P7)."""
    active = np.zeros(n_days, dtype=np.int64)
    for r in sorted(refit_days):
        if r + 1 < n_days:
            active[r + 1 :] = r
    return active


def schedule_triggered(cache: Cache, spec: str) -> list[int]:
    """Replay the stream day by day and ask the detector whether to refit.

    The statistic fed to the detector on day D is the resolved daily MAE of the model that was
    active on day D - RESOLVE_LAG_DAYS. After a refit on day D the detector is reset with the new
    model's validation MAE as baseline; the new model serves from D + 1.
    """
    n_days = cache.n_days
    detector = make_detector(spec, baseline=float(cache.val_mae_fixed[0]))
    refits: list[int] = []
    active_model = 0
    active_from = 0
    for day in range(n_days):
        lag_day = day - RESOLVE_LAG_DAYS
        if lag_day < 0:
            continue
        model_on_lag_day = active_model if lag_day >= active_from else _previous_model(refits, lag_day)
        stat = cache.daily_mae(model_on_lag_day, lag_day)
        if not np.isfinite(stat):
            continue
        if detector.update(stat) and day + 1 < n_days:
            refits.append(day)
            active_model, active_from = day, day + 1
            detector.reset(baseline=float(cache.val_mae_fixed[day]))
    return refits


def _previous_model(refits: list[int], day: int) -> int:
    model = 0
    for r in refits:
        if r + 1 <= day:
            model = r
    return model


def evaluate_schedule(cache: Cache, policy: str, refit_days: list[int]) -> PolicyResult:
    n_days = cache.n_days
    active = _activate(n_days, refit_days)
    idx = np.arange(n_days)
    abs_days = cache.abs_sum[active, idx].sum(axis=1)  # (D,)
    sq_days = cache.sq_sum[active, idx].sum(axis=1)
    denom = cache.count * cache.horizon * cache.n_channels
    total = denom.sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        daily = np.where(denom > 0, abs_days / denom, np.nan)
    return PolicyResult(
        policy=policy,
        mae=float(np.nansum(abs_days) / total),
        mse=float(np.nansum(sq_days) / total),
        n_refits=len(refit_days),
        train_seconds=float(np.nansum(cache.train_seconds[refit_days])) if refit_days else 0.0,
        refit_days=list(refit_days),
        active=active.tolist(),
        daily_mae=daily.tolist(),
    )


DEFAULT_PERIODIC = (1, 3, 7, 14, 30, 60, 90)
DEFAULT_TRIGGERED = (
    "ratio-0.1",
    "ratio-0.2",
    "ratio-0.3",
    "ratio-0.5",
    "ph-0.05",
    "ph-0.1",
    "ph-0.2",
    "ph-0.4",
    "adwin-0.3",
    "adwin-0.1",
    "adwin-0.01",
    "adwin-0.001",
)


def run_policies(
    cache: Cache,
    periodic: tuple[int, ...] = DEFAULT_PERIODIC,
    triggered: tuple[str, ...] = DEFAULT_TRIGGERED,
) -> dict[str, PolicyResult]:
    results: dict[str, PolicyResult] = {"never": evaluate_schedule(cache, "never", [])}
    for k in periodic:
        results[f"periodic-{k}"] = evaluate_schedule(
            cache, f"periodic-{k}", schedule_periodic(cache.n_days, k)
        )
    for spec in triggered:
        results[spec] = evaluate_schedule(cache, spec, schedule_triggered(cache, spec))
    return results


def evaluate_warm_chain(cache: Cache, cache_dir: Path) -> PolicyResult | None:
    path = cache_dir / f"{cache.name}_warm.npz"
    if not path.exists():
        return None
    z = np.load(path)
    abs_next, sq_next, count, seconds = z["abs_next"], z["sq_next"], z["count"], z["train_seconds"]
    denom = count * cache.horizon * cache.n_channels
    total = denom.sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        daily = np.where(denom > 0, np.nansum(abs_next, axis=1) / denom, np.nan)
    n = cache.n_days
    return PolicyResult(
        policy="warm-1",
        mae=float(np.nansum(abs_next) / total),
        mse=float(np.nansum(sq_next) / total),
        n_refits=n - 1,
        train_seconds=float(np.nansum(seconds[1:])),
        refit_days=list(range(1, n)),
        active=list(range(n)),
        daily_mae=daily.tolist(),
    )


@dataclass
class Comparison:
    policy: str
    reference: str
    diff: float  # mean(policy) - mean(reference); negative = policy better
    lo: float
    hi: float


def compare(cache: Cache, a: PolicyResult, b: PolicyResult, seed: int = 0) -> Comparison:
    w = cache.count.astype(np.float64)
    ad, bd = np.nan_to_num(np.array(a.daily_mae)), np.nan_to_num(np.array(b.daily_mae))
    iv = paired_block_bootstrap(ad, bd, w, block=7, n_boot=1000, seed=seed)
    return Comparison(a.policy, b.policy, iv.mean, iv.lo, iv.hi)


@dataclass
class SeedSummary:
    cache: str
    seed: int
    policies: dict[str, dict[str, Any]] = field(default_factory=dict)
    comparisons: list[dict[str, Any]] = field(default_factory=list)


def simulate_cache(cache_dir: Path, name: str, seed_for_bootstrap: int = 0) -> SeedSummary:
    cache = Cache.load(cache_dir, name)
    results = run_policies(cache)
    warm = evaluate_warm_chain(cache, cache_dir)
    if warm is not None:
        results["warm-1"] = warm
    summary = SeedSummary(cache=name, seed=int(cache.config["seed"]))
    for policy, res in results.items():
        d = res.to_dict()
        d.pop("active")
        summary.policies[policy] = d
    for policy, res in results.items():
        if policy == "never":
            continue
        summary.comparisons.append(asdict(compare(cache, res, results["never"], seed_for_bootstrap)))
        if policy != "periodic-1":
            summary.comparisons.append(asdict(compare(cache, res, results["periodic-1"], seed_for_bootstrap)))
    return summary
