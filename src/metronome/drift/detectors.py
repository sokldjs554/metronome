"""Three ways to decide that a deployed model's error has drifted.

All detectors consume one scalar per day (the resolved daily MAE of the active model) and answer
`update(x) -> bool` ("retrain now?"). They are pure Python so the serving monitor and the offline
simulation share the exact same code path.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol


class Detector(Protocol):
    name: str

    def update(self, x: float) -> bool: ...

    def reset(self, baseline: float | None = None) -> None: ...

    def state(self) -> dict[str, Any]: ...


@dataclass
class RatioRule:
    """Rolling mean of the last `window` values exceeds baseline * (1 + tau).

    The baseline is the model's own validation error measured right after it was trained, so the
    rule reads as "the model is now tau worse than it was when we shipped it".
    """

    tau: float = 0.2
    window: int = 7
    cooldown: int = 7
    baseline: float | None = None
    name: str = field(init=False)
    _buf: deque[float] = field(default_factory=deque, init=False, repr=False)
    _since_reset: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.name = f"ratio-{self.tau:g}"

    def update(self, x: float) -> bool:
        self._buf.append(x)
        if len(self._buf) > self.window:
            self._buf.popleft()
        self._since_reset += 1
        if self.baseline is None or len(self._buf) < self.window or self._since_reset < self.cooldown:
            return False
        return sum(self._buf) / len(self._buf) > self.baseline * (1.0 + self.tau)

    def reset(self, baseline: float | None = None) -> None:
        self.baseline = baseline if baseline is not None else self.baseline
        self._buf.clear()
        self._since_reset = 0

    def state(self) -> dict[str, Any]:
        rolling = sum(self._buf) / len(self._buf) if self._buf else None
        return {
            "name": self.name,
            "baseline": self.baseline,
            "rolling": rolling,
            "threshold": None if self.baseline is None else self.baseline * (1 + self.tau),
            "window_filled": len(self._buf),
        }


@dataclass
class PageHinkley:
    """Page-Hinkley test for an upward shift in the mean (Page 1954; Hinkley 1971).

    m_t accumulates (x - mean_t - delta); an alarm fires when m_t rises more than `lambda_` above
    its running minimum. `delta` is the magnitude of change tolerated per step.
    """

    lambda_: float = 0.1
    delta: float = 0.005
    min_samples: int = 7
    name: str = field(init=False)
    _n: int = field(default=0, init=False, repr=False)
    _mean: float = field(default=0.0, init=False, repr=False)
    _m: float = field(default=0.0, init=False, repr=False)
    _m_min: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.name = f"ph-{self.lambda_:g}"

    def update(self, x: float) -> bool:
        self._n += 1
        self._mean += (x - self._mean) / self._n
        self._m += x - self._mean - self.delta
        self._m_min = min(self._m_min, self._m)
        if self._n < self.min_samples:
            return False
        return (self._m - self._m_min) > self.lambda_

    def reset(self, baseline: float | None = None) -> None:
        self._n, self._mean, self._m, self._m_min = 0, 0.0, 0.0, 0.0

    def state(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "n": self._n,
            "mean": self._mean,
            "statistic": self._m - self._m_min,
            "threshold": self.lambda_,
        }


class _Bucket:
    __slots__ = ("total", "variance")

    def __init__(self, total: float = 0.0, variance: float = 0.0) -> None:
        self.total = total
        self.variance = variance


class ADWIN:
    """ADaptive WINdowing (Bifet & Gavaldà, SDM 2007), the exponential-histogram variant (ADWIN2).

    Keeps a variable-length window of recent values and drops its oldest part whenever two
    sub-windows have means that differ more than the Hoeffding-style bound allows at confidence
    `delta`. `update` returns True when such a cut happened (= a change was detected).
    """

    def __init__(self, delta: float = 0.01, max_buckets: int = 5, min_window: int = 7) -> None:
        self.delta = delta
        self.max_buckets = max_buckets
        self.min_window = min_window
        self.name = f"adwin-{delta:g}"
        self.reset()

    def reset(self, baseline: float | None = None) -> None:
        # rows[i] holds up to max_buckets buckets each summarizing 2**i items
        self.rows: list[list[_Bucket]] = [[]]
        self.width = 0
        self.total = 0.0
        self.variance = 0.0

    def _insert(self, x: float) -> None:
        self.rows[0].append(_Bucket(x, 0.0))
        if self.width > 0:
            mean = self.total / self.width
            self.variance += self.width * (x - mean) ** 2 / (self.width + 1)
        self.width += 1
        self.total += x
        self._compress()

    def _compress(self) -> None:
        for i, row in enumerate(self.rows):
            if len(row) <= self.max_buckets:
                break
            if i + 1 == len(self.rows):
                self.rows.append([])
            a, b = row.pop(0), row.pop(0)
            n = 2**i
            merged = _Bucket(a.total + b.total)
            mean_a, mean_b = a.total / n, b.total / n
            merged.variance = a.variance + b.variance + n * n * (mean_a - mean_b) ** 2 / (2 * n)
            self.rows[i + 1].append(merged)

    def _drop_oldest(self) -> None:
        for i in range(len(self.rows) - 1, -1, -1):
            if self.rows[i]:
                bucket = self.rows[i].pop(0)
                n = 2**i
                mean_bucket = bucket.total / n
                self.width -= n
                self.total -= bucket.total
                if self.width > 0:
                    mean = self.total / self.width
                    self.variance -= bucket.variance + n * self.width * (mean_bucket - mean) ** 2 / (
                        n + self.width
                    )
                    self.variance = max(self.variance, 0.0)
                else:
                    self.variance = 0.0
                return

    def update(self, x: float) -> bool:
        self._insert(x)
        if self.width < self.min_window:
            return False
        changed = False
        reduce = True
        while reduce:
            reduce = False
            n0, s0 = 0, 0.0
            for i in range(len(self.rows) - 1, -1, -1):
                n_bucket = 2**i
                for bucket in list(self.rows[i]):
                    n0 += n_bucket
                    s0 += bucket.total
                    n1 = self.width - n0
                    if n1 <= 0:
                        break
                    s1 = self.total - s0
                    if n0 < 1 or n1 < 1:
                        continue
                    mean0, mean1 = s0 / n0, s1 / n1
                    var = self.variance / self.width if self.width else 0.0
                    m = 1.0 / (1.0 / n0 + 1.0 / n1)
                    delta_prime = self.delta / max(math.log(self.width), 1.0)
                    eps = math.sqrt(2.0 / m * var * math.log(2.0 / delta_prime)) + 2.0 / (3.0 * m) * math.log(
                        2.0 / delta_prime
                    )
                    if abs(mean0 - mean1) > eps and self.width > self.min_window:
                        self._drop_oldest()
                        changed = True
                        reduce = True
                        break
                if reduce:
                    break
        return changed

    def state(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "width": self.width,
            "mean": self.total / self.width if self.width else None,
            "delta": self.delta,
        }


def make_detector(spec: str, baseline: float | None = None) -> Detector:
    """Build a detector from a policy string such as "ratio-0.2", "ph-0.1", "adwin-0.01"."""
    kind, _, value = spec.partition("-")
    if kind == "ratio":
        return RatioRule(tau=float(value), baseline=baseline)
    if kind == "ph":
        return PageHinkley(lambda_=float(value))
    if kind == "adwin":
        return ADWIN(delta=float(value))
    raise ValueError(f"unknown detector {spec!r}")
