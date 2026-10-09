"""Simulate retraining policies on a refit cache and summarize them with bootstrap intervals.

Policy names:
  never, periodic-<k>, ratio-<tau>, ph-<lambda>, adwin-<delta>, warm-1
  <any>+gate   — same schedule, but a refit only goes live if the candidate beats the incumbent
                 on the same evaluation sample: the days of the candidate's validation span whose
                 every forecast is resolved at the decision time, both measured by the cache on
                 the fixed scale. Added after the first ETTh1 results (post-hoc, see protocol
                 change log); the pre-registered grid is the un-gated one.

Time, for a refit decided on stream day D (protocol P6/P7): the candidate trains at D 00:00 on the
rows before it; the decision uses only rows before D 00:00; the new model serves from D+1 00:00.
A forecast whose origin (first target row) is on day d is resolved once its last target row has
arrived, which for the last origin of the day is day d + ceil((H-1)/per_day) at the earliest, so
the latest day whose every forecast is resolved at D 00:00 is D - resolve_lag_days(H, per_day).
Detectors and the gate read nothing later than that.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from metronome.drift.detectors import make_detector
from metronome.eval.bootstrap import paired_block_bootstrap
from metronome.eval.resolve import resolve_lag_days

__all__ = [
    "Cache",
    "GateDecision",
    "gate_decide",
    "resolve_lag_days",
    "resolved_days",
    "run_policies",
    "simulate_cache",
]


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
    epochs: np.ndarray | None = None  # (M,) epochs actually trained per cold refit
    per_day: int = 24  # origins per stream day (the data period)
    backward_days: int = 0  # days before its own day each model was also evaluated on (0: old cache)

    @property
    def n_days(self) -> int:
        return int(self.abs_sum.shape[1])

    @property
    def n_channels(self) -> int:
        return int(self.abs_sum.shape[2])

    @property
    def resolve_lag_days(self) -> int:
        return resolve_lag_days(self.horizon, self.per_day)

    def denominators(self) -> np.ndarray:
        return self.count * self.horizon * self.n_channels

    def daily_mae(self, model_day: int, eval_day: int) -> float:
        n = self.count[eval_day] * self.horizon * self.n_channels
        return float(self.abs_sum[model_day, eval_day].sum() / n) if n else float("nan")

    def mae_over_days(self, model_day: int, days: np.ndarray) -> float:
        den = self.denominators()[days].sum()
        return float(self.abs_sum[model_day, days].sum() / den) if den else float("nan")

    @classmethod
    def load(cls, cache_dir: Path, name: str) -> Cache:
        z = np.load(cache_dir / f"{name}.npz")
        meta = json.loads((cache_dir / f"{name}.json").read_text())
        day_starts = z["day_starts"] if "day_starts" in z.files else None
        per_day = int(day_starts[1] - day_starts[0]) if day_starts is not None and len(day_starts) > 1 else 24
        return cls(
            name=name,
            abs_sum=z["abs_sum"],
            sq_sum=z["sq_sum"],
            count=z["count"],
            train_seconds=z["train_seconds"],
            val_mae_fixed=z["val_mae_fixed"],
            horizon=int(meta["config"]["horizon"]),
            config=meta["config"],
            epochs=z["epochs"].astype(np.float64) if "epochs" in z.files else None,
            per_day=per_day,
            backward_days=int(meta.get("backward_days", 0)),
        )


@dataclass
class PolicyResult:
    policy: str
    mae: float
    mse: float
    n_refits: int  # models that went live
    n_trained: int  # models that were trained (>= n_refits when gated)
    train_seconds: float
    refit_days: list[int]
    rejected_days: list[int]
    active: list[int]
    daily_mae: list[float]
    train_epochs: float = (
        0.0  # epochs summed over trained models; unlike seconds, independent of machine load
    )
    rejections: dict[str, int] = field(default_factory=dict)  # gate: why candidates did not go live

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


def resolved_days(cache: Cache, decision_day: int, window: int) -> np.ndarray:
    """Stream days in [decision_day - window, decision_day) whose every forecast is resolved at
    decision_day 00:00: the evaluation sample of a gate decision on that day."""
    first = max(0, decision_day - window)
    last = decision_day - cache.resolve_lag_days
    return np.arange(first, last + 1) if last >= first else np.arange(0)


@dataclass
class GateDecision:
    candidate_day: int
    incumbent_day: int
    days: list[int]  # the evaluation sample: complete stream days, every forecast resolved
    candidate_mae: float
    incumbent_mae: float
    accept: bool
    reason: str  # better | worse | tie | insufficient_sample | nonfinite | no_backward_window


def gate_decide(cache: Cache, candidate_day: int, incumbent_day: int) -> GateDecision:
    """Champion/challenger check with both models measured on the same days by the same cache.

    The sample is the candidate's validation span (`cache.backward_days` days before its refit
    day, held out from its weight fitting but used for its early stopping, so the comparison
    favours the candidate slightly) restricted to the days whose every forecast is resolved at
    the decision time. Both MAEs are the cache's per-day sums over those days on the fixed scale.
    The candidate goes live only when its MAE is strictly lower; a short or non-finite sample
    and a tie keep the incumbent.
    """
    window = cache.backward_days
    nan = float("nan")
    if window <= 0:
        return GateDecision(candidate_day, incumbent_day, [], nan, nan, False, "no_backward_window")
    days = resolved_days(cache, candidate_day, window)
    needed = window - cache.resolve_lag_days + 1  # the full resolved window, nothing clipped
    if needed < 1 or len(days) < needed:
        return GateDecision(
            candidate_day, incumbent_day, days.tolist(), nan, nan, False, "insufficient_sample"
        )
    candidate = cache.mae_over_days(candidate_day, days)
    incumbent = cache.mae_over_days(incumbent_day, days)
    if not (np.isfinite(candidate) and np.isfinite(incumbent)):
        return GateDecision(
            candidate_day, incumbent_day, days.tolist(), candidate, incumbent, False, "nonfinite"
        )
    if candidate < incumbent:
        reason, accept = "better", True
    elif candidate == incumbent:
        reason, accept = "tie", False
    else:
        reason, accept = "worse", False
    return GateDecision(candidate_day, incumbent_day, days.tolist(), candidate, incumbent, accept, reason)


def gate_accepts(cache: Cache, candidate_day: int, incumbent_day: int) -> bool:
    return gate_decide(cache, candidate_day, incumbent_day).accept


def gate_schedule(cache: Cache, refit_days: list[int]) -> tuple[list[int], list[int], dict[str, int]]:
    """Apply the gate to a fixed schedule: (days that went live, days trained but kept out, why)."""
    accepted: list[int] = []
    rejected: list[int] = []
    reasons: dict[str, int] = {}
    incumbent = 0
    for r in sorted(refit_days):
        decision = gate_decide(cache, r, incumbent)
        if decision.accept:
            accepted.append(r)
            incumbent = r
        else:
            rejected.append(r)
            reasons[decision.reason] = reasons.get(decision.reason, 0) + 1
    return accepted, rejected, reasons


def schedule_triggered(
    cache: Cache, spec: str, *, gate: bool = False
) -> tuple[list[int], list[int], dict[str, int]]:
    """Replay the stream day by day and ask the detector whether to refit.

    The statistic fed to the detector on day D is the daily MAE, of the model that was active then,
    of the latest day whose every forecast is resolved at D 00:00 (D - resolve_lag_days). After a
    refit on day D the detector is reset with the new model's validation MAE as baseline; the new
    model serves from D + 1. With `gate`, a candidate that is kept out leaves the incumbent (and
    its baseline) in place and only restarts the detector.
    """
    n_days = cache.n_days
    lag = cache.resolve_lag_days
    detector = make_detector(spec, baseline=float(cache.val_mae_fixed[0]))
    refits: list[int] = []
    rejected: list[int] = []
    reasons: dict[str, int] = {}
    active_model = 0
    for day in range(n_days):
        lag_day = day - lag
        if lag_day < 0:
            continue
        stat = cache.daily_mae(_model_on_day(refits, lag_day), lag_day)
        if not np.isfinite(stat):
            continue
        if detector.update(stat) and day + 1 < n_days:
            if gate:
                decision = gate_decide(cache, day, active_model)
                if not decision.accept:
                    rejected.append(day)
                    reasons[decision.reason] = reasons.get(decision.reason, 0) + 1
                    detector.reset(baseline=float(cache.val_mae_fixed[active_model]))
                    continue
            refits.append(day)
            active_model = day
            detector.reset(baseline=float(cache.val_mae_fixed[day]))
    return refits, rejected, reasons


def _model_on_day(refits: list[int], day: int) -> int:
    model = 0
    for r in refits:
        if r + 1 <= day:
            model = r
    return model


def evaluate_schedule(
    cache: Cache,
    policy: str,
    refit_days: list[int],
    rejected_days: list[int] | None = None,
    rejections: dict[str, int] | None = None,
) -> PolicyResult:
    n_days = cache.n_days
    rejected_days = rejected_days or []
    active = _activate(n_days, refit_days)
    idx = np.arange(n_days)
    abs_days = cache.abs_sum[active, idx].sum(axis=1)  # (D,)
    sq_days = cache.sq_sum[active, idx].sum(axis=1)
    denom = cache.denominators()
    total = denom.sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        daily = np.where(denom > 0, abs_days / denom, np.nan)
    trained = sorted(set(refit_days) | set(rejected_days))
    return PolicyResult(
        policy=policy,
        mae=float(np.nansum(abs_days) / total),
        mse=float(np.nansum(sq_days) / total),
        n_refits=len(refit_days),
        n_trained=len(trained),
        train_seconds=float(np.nansum(cache.train_seconds[trained])) if trained else 0.0,
        refit_days=list(refit_days),
        rejected_days=list(rejected_days),
        active=active.tolist(),
        daily_mae=daily.tolist(),
        train_epochs=float(np.nansum(cache.epochs[trained]))
        if (cache.epochs is not None and trained)
        else 0.0,
        rejections=dict(rejections or {}),
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
    *,
    gated: bool | None = None,
) -> dict[str, PolicyResult]:
    """Every policy of the grid; `+gate` variants only when the cache carries the backward window
    the gate needs (None = decide from the cache)."""
    if gated is None:
        gated = cache.backward_days > 0
    results: dict[str, PolicyResult] = {"never": evaluate_schedule(cache, "never", [])}
    for k in periodic:
        name = f"periodic-{k}"
        plain = schedule_periodic(cache.n_days, k)
        results[name] = evaluate_schedule(cache, name, plain)
        if gated:
            acc, rej, why = gate_schedule(cache, plain)
            results[f"{name}+gate"] = evaluate_schedule(cache, f"{name}+gate", acc, rej, why)
    for spec in triggered:
        refits, _, _ = schedule_triggered(cache, spec)
        results[spec] = evaluate_schedule(cache, spec, refits)
        if gated:
            acc, rej, why = schedule_triggered(cache, spec, gate=True)
            results[f"{spec}+gate"] = evaluate_schedule(cache, f"{spec}+gate", acc, rej, why)
    return results


def evaluate_warm_chain(cache: Cache, cache_dir: Path) -> PolicyResult | None:
    path = cache_dir / f"{cache.name}_warm.npz"
    if not path.exists():
        return None
    z = np.load(path)
    abs_next, sq_next, count, seconds = z["abs_next"], z["sq_next"], z["count"], z["train_seconds"]
    meta_path = cache_dir / f"{cache.name}_warm.json"
    warm_epochs = int(json.loads(meta_path.read_text()).get("epochs", 0)) if meta_path.exists() else 0
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
        n_trained=n - 1,
        train_seconds=float(np.nansum(seconds[1:])),
        refit_days=list(range(1, n)),
        rejected_days=[],
        active=list(range(n)),
        daily_mae=daily.tolist(),
        train_epochs=float(warm_epochs * (n - 1)),
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
