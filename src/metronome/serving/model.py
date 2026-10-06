"""A verified registry version loaded for serving: scaler + ONNX engine + manifest."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from metronome.serving.engine import OnnxEngine
from metronome.serving.registry import Registry


class ServingModel:
    def __init__(self, registry: Registry, version: str, threads: int = 1) -> None:
        self.version = version
        self.manifest = registry.manifest(version)
        self.verification = registry.verify(version, threads=threads)
        self.engine = OnnxEngine(registry.model_path(version), threads=threads)
        self.mean = np.asarray(self.manifest["scaler"]["mean"], dtype=np.float32)
        self.std = np.asarray(self.manifest["scaler"]["std"], dtype=np.float32)
        self.lookback = int(self.manifest["lookback"])
        self.horizon = int(self.manifest["horizon"])
        self.channels = list(self.manifest["channels"])
        self.loaded_at = time.time()

    def forecast(self, history: np.ndarray) -> np.ndarray:
        """history (B, L, C) in raw units -> forecast (B, H, C) in raw units."""
        arr = np.asarray(history, dtype=np.float32)
        if arr.ndim == 2:
            arr = arr[None]
        if not np.isfinite(arr).all():
            raise ValueError("history contains non-finite values")
        z = (arr - self.mean) / self.std
        out = self.engine.predict(z)
        return out * self.std + self.mean

    def summary(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.manifest.get("created_at"),
            "metrics": self.manifest.get("metrics", {}),
            "onnx_sha256": self.manifest["onnx_sha256"],
            "parity_max_abs_diff": self.verification["max_abs_diff"],
            "provenance": self.manifest.get("provenance", {}),
        }


@dataclass
class SwapEvent:
    at: float
    from_version: str | None
    to_version: str
    reason: str


@dataclass
class ActiveModel:
    """Holds the live model; `swap` is atomic and never interrupts an in-flight forecast.

    Readers call `get()` and keep the returned object for the duration of one request. Python's
    attribute assignment is atomic, and the old ServingModel stays alive while any request still
    references it, so there is no window in which a forecast fails because a swap happened.
    """

    model: ServingModel | None = None
    events: list[SwapEvent] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get(self) -> ServingModel:
        model = self.model
        if model is None:
            raise RuntimeError("no active model")
        return model

    def swap(self, new: ServingModel, reason: str = "activate") -> SwapEvent:
        with self._lock:
            previous = self.model.version if self.model is not None else None
            self.model = new
            event = SwapEvent(time.time(), previous, new.version, reason)
            self.events.append(event)
            return event
