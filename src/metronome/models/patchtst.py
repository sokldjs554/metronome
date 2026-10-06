"""PatchTST (Nie et al., ICLR 2023), supervised variant, written from the paper.

Design points reproduced from the paper / reference code (github.com/yuqinie98/PatchTST):
  * instance normalization (RevIN without affine) before patching, denormalized after the head
  * patching with end-replication padding: patch_num = (L - P) // S + 2
  * channel independence: each channel is a separate sequence through a shared encoder
  * encoder = pre-activation-free Transformer blocks with BatchNorm (not LayerNorm) and GELU
  * flatten head: concat all patch embeddings -> Linear -> H

Deviation, stated so the reproduction numbers are interpreted correctly: attention is
torch.nn.MultiheadAttention without the reference code's residual-attention (Realformer) score
carry-over between layers.
"""

from __future__ import annotations

import math

import torch
from torch import Tensor, nn


class RevIN(nn.Module):
    def __init__(self, eps: float = 1e-5) -> None:
        super().__init__()
        self.eps = eps

    def normalize(self, x: Tensor) -> tuple[Tensor, Tensor, Tensor]:  # (B, L, C)
        mean = x.mean(dim=1, keepdim=True).detach()
        std = torch.sqrt(x.var(dim=1, keepdim=True, unbiased=False) + self.eps).detach()
        return (x - mean) / std, mean, std

    @staticmethod
    def denormalize(y: Tensor, mean: Tensor, std: Tensor) -> Tensor:
        return y * std + mean


class _BatchNormSeq(nn.Module):
    """BatchNorm1d over d_model for a (N, T, d_model) tensor."""

    def __init__(self, d_model: int) -> None:
        super().__init__()
        self.bn = nn.BatchNorm1d(d_model)

    def forward(self, x: Tensor) -> Tensor:
        return self.bn(x.transpose(1, 2)).transpose(1, 2)


class _EncoderLayer(nn.Module):
    def __init__(self, d_model: int, n_heads: int, d_ff: int, dropout: float, attn_dropout: float) -> None:
        super().__init__()
        self.attn = nn.MultiheadAttention(d_model, n_heads, dropout=attn_dropout, batch_first=True)
        self.drop_attn = nn.Dropout(dropout)
        self.norm_attn = _BatchNormSeq(d_model)
        self.ff = nn.Sequential(
            nn.Linear(d_model, d_ff), nn.GELU(), nn.Dropout(dropout), nn.Linear(d_ff, d_model)
        )
        self.drop_ff = nn.Dropout(dropout)
        self.norm_ff = _BatchNormSeq(d_model)

    def forward(self, x: Tensor) -> Tensor:
        a, _ = self.attn(x, x, x, need_weights=False)
        x = self.norm_attn(x + self.drop_attn(a))
        f = self.ff(x)
        return self.norm_ff(x + self.drop_ff(f))


class PatchTST(nn.Module):
    def __init__(
        self,
        lookback: int,
        horizon: int,
        channels: int,
        patch_len: int = 16,
        stride: int = 8,
        d_model: int = 16,
        n_heads: int = 4,
        n_layers: int = 3,
        d_ff: int = 128,
        dropout: float = 0.3,
        attn_dropout: float = 0.0,
        fc_dropout: float = 0.3,
        head_dropout: float = 0.0,
        revin: bool = True,
    ) -> None:
        super().__init__()
        if patch_len > lookback:
            raise ValueError("patch_len must not exceed lookback")
        self.lookback, self.horizon, self.channels = lookback, horizon, channels
        self.patch_len, self.stride = patch_len, stride
        self.revin = RevIN() if revin else None
        self.patch_num = (lookback - patch_len) // stride + 2  # +1 for the end-replicated patch
        self.pad = nn.ReplicationPad1d((0, stride))
        # Gather indices instead of Tensor.unfold: identical result, and exportable to ONNX with a
        # dynamic batch axis (unfold needs a static input size in the TorchScript exporter).
        patch_idx = torch.arange(patch_len)[None, :] + stride * torch.arange(self.patch_num)[:, None]
        self.register_buffer("patch_idx", patch_idx, persistent=False)
        self.embed = nn.Linear(patch_len, d_model)
        self.pos = nn.Parameter(torch.empty(self.patch_num, d_model).uniform_(-0.02, 0.02))
        self.drop = nn.Dropout(dropout)
        self.layers = nn.ModuleList(
            [_EncoderLayer(d_model, n_heads, d_ff, dropout, attn_dropout) for _ in range(n_layers)]
        )
        self.head = nn.Sequential(
            nn.Flatten(start_dim=-2),
            nn.Dropout(fc_dropout),
            nn.Linear(d_model * self.patch_num, horizon),
            nn.Dropout(head_dropout),
        )

    def forward(self, x: Tensor) -> Tensor:  # (B, L, C) -> (B, H, C)
        b, _, c = x.shape
        if self.revin is not None:
            x, mean, std = self.revin.normalize(x)
        z = x.transpose(1, 2)  # (B, C, L)
        z = self.pad(z)
        z = z[:, :, self.patch_idx]  # (B, C, N, P)
        z = z.reshape(b * c, self.patch_num, self.patch_len)
        z = self.drop(self.embed(z) + self.pos)
        for layer in self.layers:
            z = layer(z)
        y = self.head(z)  # (B*C, H)
        y = y.reshape(b, c, self.horizon).transpose(1, 2)
        if self.revin is not None:
            y = self.revin.denormalize(y, mean, std)
        return y

    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters())


def positional_sanity(patch_num: int, d_model: int) -> float:
    """Expected RMS of the uniform(-0.02, 0.02) positional init (used by a test)."""
    return 0.02 / math.sqrt(3)
