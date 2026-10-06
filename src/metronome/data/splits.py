"""Chronological splits: the evaluation stream, day boundaries, and the standard LTSF borders."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class StreamSplit:
    """Rows [0, stream_start) are the initial history; rows [stream_start, n) are the stream."""

    n_rows: int
    stream_start: int
    day_starts: np.ndarray  # row index of 00:00 for each stream day (first = stream_start)

    @property
    def n_days(self) -> int:
        return len(self.day_starts)

    def day_slice(self, day: int) -> slice:
        start = int(self.day_starts[day])
        end = int(self.day_starts[day + 1]) if day + 1 < self.n_days else self.n_rows
        return slice(start, end)


def stream_split(timestamps: np.ndarray, stream_days: int) -> StreamSplit:
    """Last `stream_days` calendar days (starting at a 00:00 row) form the stream."""
    ts = timestamps.astype("datetime64[ns]")
    days = ts.astype("datetime64[D]")
    starts = np.flatnonzero(np.r_[True, days[1:] != days[:-1]])  # first row of every calendar day
    if len(starts) <= stream_days:
        raise ValueError(f"series has only {len(starts)} days; cannot hold out {stream_days}")
    stream_day_starts = starts[-stream_days:]
    return StreamSplit(n_rows=len(ts), stream_start=int(stream_day_starts[0]), day_starts=stream_day_starts)


def ltsf_borders(n_rows: int, lookback: int, kind: str) -> tuple[list[int], list[int]]:
    """Train/val/test row borders used by the LTSF-Linear / PatchTST reference code.

    kind="etth": 12/4/4 months of hourly data; kind="ettm": the same months at 15 minutes;
    kind="other": 70/10/20 split. Val/test start `lookback` rows early so the first window of each
    split ends exactly at the split boundary (as in the reference Data_Loader).
    """
    if kind == "etth":
        b1 = [0, 12 * 30 * 24 - lookback, 16 * 30 * 24 - lookback]
        b2 = [12 * 30 * 24, 16 * 30 * 24, 20 * 30 * 24]
    elif kind == "ettm":
        b1 = [0, 12 * 30 * 24 * 4 - lookback, 16 * 30 * 24 * 4 - lookback]
        b2 = [12 * 30 * 24 * 4, 16 * 30 * 24 * 4, 20 * 30 * 24 * 4]
    elif kind == "other":
        n_train = int(n_rows * 0.7)
        n_test = int(n_rows * 0.2)
        n_val = n_rows - n_train - n_test
        b1 = [0, n_train - lookback, n_rows - n_test - lookback]
        b2 = [n_train, n_train + n_val, n_rows]
    else:
        raise ValueError(kind)
    if b2[-1] > n_rows:
        raise ValueError(f"{kind} borders need {b2[-1]} rows, series has {n_rows}")
    return b1, b2
