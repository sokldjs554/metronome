"""Error metrics on (N, H, C) forecasts, plus per-day aggregation used by the refit cache."""

from __future__ import annotations

import numpy as np


def mae(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.mean(np.abs(pred - target)))


def mse(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.mean((pred - target) ** 2))


def per_channel(pred: np.ndarray, target: np.ndarray) -> dict[str, list[float]]:
    err = pred - target
    return {"mae": np.abs(err).mean(axis=(0, 1)).tolist(), "mse": (err**2).mean(axis=(0, 1)).tolist()}


def per_horizon(pred: np.ndarray, target: np.ndarray) -> dict[str, list[float]]:
    err = pred - target
    return {"mae": np.abs(err).mean(axis=(0, 2)).tolist(), "mse": (err**2).mean(axis=(0, 2)).tolist()}


def daily_error_sums(
    pred: np.ndarray, target: np.ndarray, origin_day: np.ndarray, n_days: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Aggregate |err| and err² by the day of the forecast origin.

    Returns (abs_sum[D, C], sq_sum[D, C], count[D]) where count is the number of origins in the
    day; dividing by count * H gives the per-channel daily MAE/MSE.
    """
    err = pred - target  # (N, H, C)
    abs_sum = np.zeros((n_days, err.shape[2]), dtype=np.float64)
    sq_sum = np.zeros_like(abs_sum)
    count = np.zeros(n_days, dtype=np.int64)
    np.add.at(abs_sum, origin_day, np.abs(err).sum(axis=1))
    np.add.at(sq_sum, origin_day, (err**2).sum(axis=1))
    np.add.at(count, origin_day, 1)
    return abs_sum, sq_sum, count
