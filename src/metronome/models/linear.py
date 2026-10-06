"""Linear family from "Are Transformers Effective for Time Series Forecasting?" (Zeng et al., AAAI 2023).

Written from the paper's description and checked against the public reference code
(github.com/cure-lab/LTSF-Linear). Weight initialization is PyTorch's default, as in the
reference models (its 1/L constant init is a commented-out visualization aid there).
"""

from __future__ import annotations

import torch
from torch import Tensor, nn
from torch.nn import functional as F


class MovingAverage(nn.Module):
    """Trend extractor: centered moving average with edge replication."""

    def __init__(self, kernel_size: int) -> None:
        super().__init__()
        if kernel_size < 1 or kernel_size % 2 == 0:
            raise ValueError("kernel_size must be a positive odd integer")
        self.kernel_size = kernel_size

    def forward(self, x: Tensor) -> Tensor:  # (B, L, C) -> (B, L, C)
        pad = (self.kernel_size - 1) // 2
        xt = F.pad(x.transpose(1, 2), (pad, pad), mode="replicate")
        return F.avg_pool1d(xt, kernel_size=self.kernel_size, stride=1).transpose(1, 2)


class Linear(nn.Module):
    """One linear map from the L input steps to the H output steps, shared across channels."""

    def __init__(self, lookback: int, horizon: int, channels: int, individual: bool = False) -> None:
        super().__init__()
        self.lookback, self.horizon, self.channels, self.individual = lookback, horizon, channels, individual
        if individual:
            self.proj = nn.ModuleList([nn.Linear(lookback, horizon) for _ in range(channels)])
        else:
            self.proj = nn.Linear(lookback, horizon)

    def _apply(self, x: Tensor) -> Tensor:  # x (B, C, L) -> (B, C, H)
        if self.individual:
            assert isinstance(self.proj, nn.ModuleList)
            return torch.stack([layer(x[:, i, :]) for i, layer in enumerate(self.proj)], dim=1)
        assert isinstance(self.proj, nn.Linear)
        return self.proj(x)

    def forward(self, x: Tensor) -> Tensor:
        return self._apply(x.transpose(1, 2)).transpose(1, 2)


class NLinear(Linear):
    """Linear on the sequence minus its last value, then add the last value back (handles level shifts)."""

    def forward(self, x: Tensor) -> Tensor:
        last = x[:, -1:, :].detach()
        y = self._apply((x - last).transpose(1, 2)).transpose(1, 2)
        return y + last


class DLinear(nn.Module):
    """Decompose into trend (moving average) and remainder; one linear map per component."""

    def __init__(
        self,
        lookback: int,
        horizon: int,
        channels: int,
        kernel_size: int = 25,
        individual: bool = False,
    ) -> None:
        super().__init__()
        self.lookback, self.horizon, self.channels = lookback, horizon, channels
        self.decompose = MovingAverage(kernel_size)
        self.seasonal = Linear(lookback, horizon, channels, individual)
        self.trend = Linear(lookback, horizon, channels, individual)

    def forward(self, x: Tensor) -> Tensor:
        trend = self.decompose(x)
        seasonal = x - trend
        return self.seasonal(seasonal) + self.trend(trend)
