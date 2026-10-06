"""Paired moving-block bootstrap over days for differences between two policies' errors."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Interval:
    mean: float
    lo: float
    hi: float
    n_boot: int
    block: int


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    return float((values * weights).sum() / weights.sum())


def paired_block_bootstrap(
    a_daily: np.ndarray,
    b_daily: np.ndarray,
    weights: np.ndarray,
    *,
    block: int = 7,
    n_boot: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
) -> Interval:
    """95% interval for mean(a) - mean(b), resampling blocks of consecutive days with replacement.

    `a_daily`/`b_daily` are per-day mean errors of two policies on the same days, `weights` the
    number of forecasts behind each day (so partial days count less). Positive = a worse than b.
    """
    a, b, w = (np.asarray(v, dtype=np.float64) for v in (a_daily, b_daily, weights))
    if not (a.shape == b.shape == w.shape) or a.ndim != 1:
        raise ValueError("inputs must be 1-D arrays of equal length")
    n = len(a)
    diff = a - b
    point = _weighted_mean(diff, w)
    if n < 2:
        return Interval(point, point, point, 0, block)
    block = max(1, min(block, n))
    rng = np.random.default_rng(seed)
    n_blocks = -(-n // block)
    starts_max = n - block + 1
    stats = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, starts_max, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        stats[i] = _weighted_mean(diff[idx], w[idx])
    lo, hi = np.quantile(stats, [alpha / 2, 1 - alpha / 2])
    return Interval(point, float(lo), float(hi), n_boot, block)
