"""Parameter-free baselines. Any trained model has to beat these on the same split."""

from __future__ import annotations

import torch
from torch import Tensor, nn


class Naive(nn.Module):
    """Repeat the last observed value for every horizon step."""

    def __init__(self, lookback: int, horizon: int, channels: int) -> None:
        super().__init__()
        self.lookback, self.horizon, self.channels = lookback, horizon, channels

    def forward(self, x: Tensor) -> Tensor:
        return x[:, -1:, :].expand(-1, self.horizon, -1)


class SeasonalNaive(nn.Module):
    """Repeat the last full season (default: 24 steps)."""

    def __init__(self, lookback: int, horizon: int, channels: int, period: int = 24) -> None:
        super().__init__()
        if period > lookback:
            raise ValueError("period must not exceed lookback")
        self.lookback, self.horizon, self.channels, self.period = lookback, horizon, channels, period

    def forward(self, x: Tensor) -> Tensor:
        season = x[:, -self.period :, :]
        reps = -(-self.horizon // self.period)
        return torch.cat([season] * reps, dim=1)[:, : self.horizon, :]
