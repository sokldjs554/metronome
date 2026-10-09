"""When is a forecast's ground truth all in? Shared by the offline simulation and the live gate.

A forecast whose origin (first target row) is row o covers rows o .. o + horizon - 1, so with the
rows before `cutoff` known it is resolved iff o + horizon <= cutoff. Decisions are made on whole
blocks of `per_day` origins (stream days offline, blocks counted back from the cutoff online).
"""

from __future__ import annotations

import numpy as np


def resolve_lag_days(horizon: int, per_day: int) -> int:
    """Days between a decision at 00:00 of day D and the latest day whose every forecast is resolved.

    The last origin of day d is row (d+1)*per_day - 1 and its last target is `horizon` - 1 rows
    later; it is resolved at D 00:00 when that row is before row D*per_day, i.e. when
    d <= D - 1 - ceil((horizon - 1) / per_day). Hourly data with H=96: 5 (days D-5 and earlier).
    """
    return 1 + -(-(horizon - 1) // per_day)


def evaluation_origins(
    cutoff_row: int, *, lookback: int, horizon: int, per_day: int, window_days: int
) -> tuple[np.ndarray, int]:
    """Origins of the gate's evaluation sample at a decision with rows before `cutoff_row` known.

    The sample is the last `window_days` blocks of `per_day` origins before the cutoff, keeping
    only the blocks whose every forecast is resolved there: rows [cutoff - window*per_day,
    cutoff - lag_blocks*per_day) with lag_blocks = ceil((horizon-1)/per_day). Returns the origin
    rows and the number of complete blocks; both are empty/0 unless the whole window is available
    (enough history for the first origin's lookback), so a short sample is never scored.
    At a day boundary the blocks are the stream days the offline cache uses.
    """
    lag_blocks = resolve_lag_days(horizon, per_day) - 1
    start = cutoff_row - window_days * per_day
    end = cutoff_row - lag_blocks * per_day
    if start < lookback or end <= start:
        return np.arange(0), 0
    return np.arange(start, end), window_days - lag_blocks
