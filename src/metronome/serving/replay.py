"""Replay a recorded stream through the live service at any speed (demo and integration tests).

The stream file is a NumPy archive written by `metronome export-stream` from the prepared
Parquet: `timestamps` (datetime64[ns]) and `values` (T, C) float32. The replay cursor advances in
event time; every step forecasts from the active model, then delivers the actual values to the
monitor exactly as a production ingest would.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class ReplayState:
    path: Path
    timestamps: np.ndarray
    values: np.ndarray
    cursor: int  # index of the next row to observe
    started_at: int
    steps: int = 0
    retrain_schedule_days: int | None = None  # periodic policy in addition to detectors (None = off)
    last_retrain_day: str | None = None
    wait_for_retrain: bool = (
        True  # pause the stream while a retrain job is pending (offline-protocol semantics)
    )
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def n_rows(self) -> int:
        return len(self.timestamps)

    def position(self) -> dict[str, Any]:
        return {
            "cursor": self.cursor,
            "n_rows": self.n_rows,
            "current_time": str(self.timestamps[min(self.cursor, self.n_rows) - 1]) if self.cursor else None,
            "started_at": self.started_at,
            "steps": self.steps,
            "progress": self.cursor / self.n_rows,
            "retrain_schedule_days": self.retrain_schedule_days,
            "last_retrain_day": self.last_retrain_day,
            "wait_for_retrain": self.wait_for_retrain,
        }


def load_stream(path: Path) -> tuple[np.ndarray, np.ndarray]:
    z = np.load(path)
    ts = z["timestamps"].astype("datetime64[ns]")
    values = z["values"].astype(np.float32)
    if values.ndim != 2 or len(ts) != len(values):
        raise ValueError("stream file must hold timestamps (T,) and values (T, C)")
    return ts, values


def write_stream(path: Path, timestamps: np.ndarray, values: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path, timestamps=timestamps.astype("datetime64[ns]"), values=values.astype(np.float32)
    )
    return path
