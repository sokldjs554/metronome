"""Frequency strings ("1h", "10m", "1d") without any heavy dependency, so the serving image can use them."""

from __future__ import annotations

from datetime import timedelta


class FrequencyError(ValueError):
    pass


def parse_duration(freq: str) -> timedelta:
    """Parse a polars-style duration ("1h", "10m", "15m", "1d", "30s") into a timedelta."""
    units = {"m": "minutes", "h": "hours", "d": "days", "s": "seconds"}
    num = "".join(ch for ch in freq if ch.isdigit())
    unit = freq[len(num) :]
    if not num or unit not in units:
        raise FrequencyError(f"unsupported frequency {freq!r}")
    return timedelta(**{units[unit]: int(num)})
