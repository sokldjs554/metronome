"""Per-channel scaling and sliding windows without copies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


@dataclass
class Scaler:
    mean: np.ndarray
    std: np.ndarray

    @classmethod
    def fit(cls, values: np.ndarray, eps: float = 1e-8) -> Scaler:
        if values.ndim != 2 or values.shape[0] < 2:
            raise ValueError("scaler needs a (T, C) array with T >= 2")
        mean = values.mean(axis=0, dtype=np.float64)
        std = values.std(axis=0, dtype=np.float64)
        std = np.where(std > eps, std, 1.0)  # a constant channel is left unscaled, not exploded
        return cls(mean.astype(np.float32), std.astype(np.float32))

    def transform(self, values: np.ndarray) -> np.ndarray:
        return np.asarray((values - self.mean) / self.std, dtype=np.float32)

    def inverse(self, values: np.ndarray) -> np.ndarray:
        return np.asarray(values * self.std + self.mean, dtype=np.float32)

    def to_dict(self) -> dict[str, Any]:
        return {"mean": self.mean.tolist(), "std": self.std.tolist()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Scaler:
        return cls(np.asarray(d["mean"], dtype=np.float32), np.asarray(d["std"], dtype=np.float32))


def make_windows(values: np.ndarray, lookback: int, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    """Return views X (N, L, C) and Y (N, H, C) for every origin where both fit.

    Origin i uses values[i : i+L] as input and values[i+L : i+L+H] as target. Both outputs are
    strided views on `values`; copy before mutating.
    """
    if values.ndim != 2:
        raise ValueError("values must be (T, C)")
    total = lookback + horizon
    if values.shape[0] < total:
        raise ValueError(f"need at least {total} rows, got {values.shape[0]}")
    win = sliding_window_view(values, total, axis=0)  # (N, C, total)
    win = np.swapaxes(win, 1, 2)  # (N, total, C)
    return win[:, :lookback, :], win[:, lookback:, :]


def window_count(n_rows: int, lookback: int, horizon: int) -> int:
    return max(0, n_rows - lookback - horizon + 1)
