"""Forecasters. Every model maps (B, L, C) -> (B, H, C) on the standardized scale."""

from __future__ import annotations

from typing import Any

from torch import nn

from metronome.models.linear import DLinear, Linear, NLinear
from metronome.models.naive import Naive, SeasonalNaive
from metronome.models.patchtst import PatchTST

REGISTRY: dict[str, type[nn.Module]] = {
    "naive": Naive,
    "seasonal_naive": SeasonalNaive,
    "linear": Linear,
    "nlinear": NLinear,
    "dlinear": DLinear,
    "patchtst": PatchTST,
}

TRAINABLE = {"linear", "nlinear", "dlinear", "patchtst"}


def build(name: str, lookback: int, horizon: int, channels: int, **kwargs: Any) -> nn.Module:
    cls = REGISTRY[name]
    return cls(lookback=lookback, horizon=horizon, channels=channels, **kwargs)


__all__ = [
    "REGISTRY",
    "TRAINABLE",
    "DLinear",
    "Linear",
    "NLinear",
    "Naive",
    "PatchTST",
    "SeasonalNaive",
    "build",
]
