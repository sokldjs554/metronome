"""Schema and integrity checks a prepared series must pass before training or serving uses it.

The checks are deliberately strict: a time-series pipeline that silently tolerates duplicated or
missing timestamps produces leakage-prone windows, and a NaN that reaches the model becomes a NaN
forecast at the worst possible moment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

import numpy as np
import polars as pl

TIMESTAMP = "timestamp"


class SchemaError(ValueError):
    pass


@dataclass
class ValidationReport:
    n_rows: int
    n_channels: int
    channels: list[str]
    freq: str
    start: str
    end: str
    duplicates: int = 0
    non_monotonic: int = 0
    gaps: int = 0
    nan_cells: int = 0
    non_finite_cells: int = 0
    constant_channels: list[str] = field(default_factory=list)
    ok: bool = True
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_duration(freq: str) -> timedelta:
    """Parse a polars-style duration ("1h", "10m", "15m", "1d") into a timedelta."""
    units = {"m": "minutes", "h": "hours", "d": "days", "s": "seconds"}
    num = "".join(ch for ch in freq if ch.isdigit())
    unit = freq[len(num) :]
    if not num or unit not in units:
        raise SchemaError(f"unsupported frequency {freq!r}")
    return timedelta(**{units[unit]: int(num)})


def validate_frame(df: pl.DataFrame, freq: str, *, strict: bool = True) -> ValidationReport:
    if TIMESTAMP not in df.columns:
        raise SchemaError(f"missing {TIMESTAMP!r} column")
    if df.schema[TIMESTAMP] != pl.Datetime and not isinstance(df.schema[TIMESTAMP], pl.Datetime):
        raise SchemaError(f"{TIMESTAMP!r} must be Datetime, got {df.schema[TIMESTAMP]}")
    channels = [c for c in df.columns if c != TIMESTAMP]
    if not channels:
        raise SchemaError("no value channels")
    for c in channels:
        if not df.schema[c].is_numeric():
            raise SchemaError(f"channel {c!r} is not numeric ({df.schema[c]})")

    ts = df[TIMESTAMP].to_numpy().astype("datetime64[ns]")
    report = ValidationReport(
        n_rows=df.height,
        n_channels=len(channels),
        channels=channels,
        freq=freq,
        start=str(ts[0]) if len(ts) else "",
        end=str(ts[-1]) if len(ts) else "",
    )
    if len(ts) < 2:
        report.problems.append("fewer than 2 rows")
    else:
        diffs = np.diff(ts).astype("timedelta64[ns]").astype(np.int64)
        step = int(parse_duration(freq).total_seconds() * 1e9)
        report.duplicates = int((diffs == 0).sum())
        report.non_monotonic = int((diffs < 0).sum())
        report.gaps = int((diffs > step).sum())
        if (diffs > 0).any() and ((diffs > 0) & (diffs < step)).any():
            report.problems.append("timestamps finer than declared frequency")
    values = df.select(channels).to_numpy().astype(np.float64)
    report.nan_cells = int(np.isnan(values).sum())
    report.non_finite_cells = int((~np.isfinite(values)).sum() - report.nan_cells)
    with np.errstate(invalid="ignore"):
        std = np.nanstd(values, axis=0)
    report.constant_channels = [c for c, s in zip(channels, std, strict=True) if not (s > 0)]

    if report.duplicates:
        report.problems.append(f"{report.duplicates} duplicated timestamps")
    if report.non_monotonic:
        report.problems.append(f"{report.non_monotonic} backwards timestamps")
    if report.gaps:
        report.problems.append(f"{report.gaps} gaps larger than {freq}")
    if report.nan_cells:
        report.problems.append(f"{report.nan_cells} NaN cells")
    if report.non_finite_cells:
        report.problems.append(f"{report.non_finite_cells} non-finite cells")
    report.ok = not report.problems
    if strict and not report.ok:
        raise SchemaError("; ".join(report.problems))
    return report
