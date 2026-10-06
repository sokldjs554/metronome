"""Residual monitor: pairs forecasts with the actual values that arrive later and runs detectors.

Time here is *event time* (the timestamps on the data), never wall-clock, so a replayed year and a
live stream behave identically. A forecast is "resolved" once every one of its horizon steps has
an observed value; only resolved forecasts contribute to the daily statistic the detectors see.
"""

from __future__ import annotations

import threading
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any

import numpy as np

from metronome.drift.detectors import Detector, make_detector

NS_PER_HOUR = 3_600_000_000_000


@dataclass
class PendingForecast:
    origin: np.datetime64
    version: str
    forecast: np.ndarray  # (H, C) raw units
    observed: np.ndarray  # (H, C) raw units, NaN until observed


@dataclass
class DaySummary:
    day: str
    n_forecasts: int
    mae: float
    versions: list[str]


class ResidualMonitor:
    def __init__(
        self,
        horizon: int,
        step_ns: int,
        fixed_mean: np.ndarray,
        fixed_std: np.ndarray,
        detector_specs: tuple[str, ...] = ("ratio-0.2", "ph-0.1", "adwin-0.01"),
        max_pending: int = 20_000,
        history_days: int = 400,
    ) -> None:
        self.horizon = horizon
        self.step_ns = step_ns
        self.fixed_mean = np.asarray(fixed_mean, dtype=np.float32)
        self.fixed_std = np.asarray(fixed_std, dtype=np.float32)
        self.pending: OrderedDict[np.datetime64, PendingForecast] = OrderedDict()
        self.max_pending = max_pending
        self.detectors: list[Detector] = [make_detector(s) for s in detector_specs]
        self.days: deque[DaySummary] = deque(maxlen=history_days)
        self.current_day: str | None = None
        self._day_abs: float = 0.0
        self._day_n: int = 0
        self._day_versions: set[str] = set()
        self.baseline: float | None = None
        self.active_version: str | None = None
        self.skipped_days = 0  # days whose forecasts came (partly) from a previous version
        self.resolved_total = 0
        self.alarms: list[dict[str, Any]] = []
        self.last_alarm_day: str | None = None
        self._lock = threading.Lock()

    # ---- recording ----------------------------------------------------------------------------
    def record_forecast(self, origin: np.datetime64, version: str, forecast: np.ndarray) -> None:
        with self._lock:
            if origin in self.pending:
                return
            self.pending[origin] = PendingForecast(
                origin=origin,
                version=version,
                forecast=np.asarray(forecast, dtype=np.float32),
                observed=np.full(forecast.shape, np.nan, dtype=np.float32),
            )
            while len(self.pending) > self.max_pending:
                self.pending.popitem(last=False)

    def observe(self, timestamp: np.datetime64, values: np.ndarray) -> dict[str, Any]:
        """Deliver the actual value at `timestamp`; resolve any forecast whose horizon is complete."""
        values = np.asarray(values, dtype=np.float32)
        resolved: list[PendingForecast] = []
        matched = 0
        with self._lock:
            ts = np.datetime64(timestamp, "ns")
            for origin, pf in list(self.pending.items()):
                offset = (ts - origin).astype("timedelta64[ns]").astype(np.int64)
                if offset <= 0 or offset % self.step_ns:
                    continue
                step = int(offset // self.step_ns)
                if 1 <= step <= self.horizon:
                    pf.observed[step - 1] = values
                    matched += 1
                    if not np.isnan(pf.observed).any():
                        resolved.append(pf)
                        del self.pending[origin]
            alarms = [self._resolve(pf) for pf in resolved]
        return {"matched": matched, "resolved": len(resolved), "alarms": [a for a in alarms if a]}

    # ---- daily statistic ----------------------------------------------------------------------
    def _resolve(self, pf: PendingForecast) -> dict[str, Any] | None:
        err = (pf.forecast - pf.observed) / self.fixed_std  # fixed evaluation scale
        mae = float(np.mean(np.abs(err)))
        day = str(pf.origin.astype("datetime64[D]"))
        alarm = None
        if self.current_day is not None and day != self.current_day:
            alarm = self._close_day()
        self.current_day = day
        self._day_abs += mae
        self._day_n += 1
        self._day_versions.add(pf.version)
        self.resolved_total += 1
        return alarm

    def _close_day(self) -> dict[str, Any] | None:
        if self.current_day is None or self._day_n == 0:
            return None
        day_mae = self._day_abs / self._day_n
        summary = DaySummary(self.current_day, self._day_n, day_mae, sorted(self._day_versions))
        self.days.append(summary)
        self._day_abs, self._day_n, self._day_versions = 0.0, 0, set()
        if self.active_version is not None and summary.versions != [self.active_version]:
            # Forecasts made by an older version resolve for up to one horizon after a swap; judging
            # the new model by them would re-trigger a retrain on stale evidence.
            self.skipped_days += 1
            return None
        fired = [d.name for d in self.detectors if d.update(day_mae)]
        if fired:
            alarm = {"day": summary.day, "mae": day_mae, "detectors": fired, "baseline": self.baseline}
            self.alarms.append(alarm)
            self.last_alarm_day = summary.day
            return alarm
        return None

    def set_baseline(self, baseline: float | None, version: str | None = None) -> None:
        """Reset detectors around a newly activated model whose validation MAE is `baseline`."""
        with self._lock:
            self.baseline = baseline
            self.active_version = version
            for d in self.detectors:
                d.reset(baseline=baseline)

    # ---- state --------------------------------------------------------------------------------
    def state(self) -> dict[str, Any]:
        with self._lock:
            recent = list(self.days)[-7:]
            rolling = float(np.mean([d.mae for d in recent])) if recent else None
            return {
                "baseline_val_mae": self.baseline,
                "judged_version": self.active_version,
                "skipped_days": self.skipped_days,
                "rolling_7d_mae": rolling,
                "resolved_forecasts": self.resolved_total,
                "pending_forecasts": len(self.pending),
                "days_closed": len(self.days),
                "current_day": self.current_day,
                "detectors": [d.state() for d in self.detectors],
                "alarms": self.alarms[-20:],
                "last_alarm_day": self.last_alarm_day,
                "daily": [
                    {"day": d.day, "mae": d.mae, "n": d.n_forecasts, "versions": d.versions}
                    for d in self.days
                ],
            }
