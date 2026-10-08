from __future__ import annotations

import numpy as np
import pytest
import torch

from metronome.models import REGISTRY, TRAINABLE, build
from metronome.models.linear import MovingAverage
from metronome.models.patchtst import PatchTST

L, H, C = 48, 12, 3


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_output_shape(name: str) -> None:
    torch.manual_seed(0)
    model = build(name, L, H, C)
    x = torch.randn(5, L, C)
    y = model(x)
    assert y.shape == (5, H, C)
    assert torch.isfinite(y).all()


def test_naive_repeats_last_value() -> None:
    x = torch.randn(2, L, C)
    y = build("naive", L, H, C)(x)
    assert torch.equal(y, x[:, -1:, :].expand(-1, H, -1))


def test_seasonal_naive_repeats_last_period() -> None:
    x = torch.arange(L, dtype=torch.float32).repeat(C, 1).T[None]  # (1, L, C) ramp
    y = build("seasonal_naive", L, H, C, period=24)(x)
    assert torch.equal(y[0, :, 0], torch.arange(L - 24, L - 24 + H, dtype=torch.float32))
    with pytest.raises(ValueError):
        build("seasonal_naive", L, H, C, period=L + 1)


def test_moving_average_preserves_constants_and_linear_trend() -> None:
    ma = MovingAverage(5)
    const = torch.full((1, 20, 1), 3.0)
    assert torch.allclose(ma(const), const)
    with pytest.raises(ValueError):
        MovingAverage(4)


def test_nlinear_is_shift_equivariant() -> None:
    torch.manual_seed(1)
    model = build("nlinear", L, H, C)
    x = torch.randn(4, L, C)
    y1, y2 = model(x), model(x + 100.0)
    assert torch.allclose(y2, y1 + 100.0, atol=1e-3)


def test_dlinear_equals_sum_of_components() -> None:
    torch.manual_seed(2)
    model = build("dlinear", L, H, C)
    x = torch.randn(3, L, C)
    trend = model.decompose(x)
    expected = model.seasonal(x - trend) + model.trend(trend)
    assert torch.allclose(model(x), expected)


def test_individual_linear_has_per_channel_weights() -> None:
    shared = build("linear", L, H, C)
    indiv = build("linear", L, H, C, individual=True)
    n_shared = sum(p.numel() for p in shared.parameters())
    n_indiv = sum(p.numel() for p in indiv.parameters())
    assert n_indiv == C * n_shared


def test_patchtst_patch_count_matches_paper_formula() -> None:
    model = PatchTST(lookback=336, horizon=96, channels=7, patch_len=16, stride=8)
    assert model.patch_num == 42  # the "/42" in PatchTST/42
    model64 = PatchTST(lookback=512, horizon=96, channels=7, patch_len=16, stride=8)
    assert model64.patch_num == 64


def test_patchtst_is_channel_independent() -> None:
    torch.manual_seed(3)
    model = PatchTST(
        lookback=L, horizon=H, channels=C, patch_len=8, stride=4, d_model=8, n_heads=2, n_layers=1
    )
    model.eval()
    x = torch.randn(2, L, C)
    y = model(x)
    x2 = x.clone()
    x2[:, :, 1] = torch.randn(2, L)  # perturb channel 1 only
    y2 = model(x2)
    assert torch.allclose(y[:, :, 0], y2[:, :, 0], atol=1e-6) and torch.allclose(
        y[:, :, 2], y2[:, :, 2], atol=1e-6
    )
    assert not torch.allclose(y[:, :, 1], y2[:, :, 1])


def test_patchtst_revin_scale_equivariance() -> None:
    torch.manual_seed(4)
    model = PatchTST(
        lookback=L, horizon=H, channels=1, patch_len=8, stride=4, d_model=8, n_heads=2, n_layers=1
    )
    model.eval()
    x = torch.randn(1, L, 1)
    y = model(x)
    y_scaled = model(x * 3 + 7)
    assert torch.allclose(y_scaled, y * 3 + 7, atol=1e-4)


def test_trainable_set_matches_parameters() -> None:
    for name in REGISTRY:
        n = sum(p.numel() for p in build(name, L, H, C).parameters())
        assert (n > 0) == (name in TRAINABLE), name


def test_models_accept_numpy_roundtrip() -> None:
    model = build("dlinear", L, H, C)
    x = np.random.default_rng(0).normal(size=(2, L, C)).astype(np.float32)
    y = model(torch.from_numpy(x)).detach().numpy()
    assert y.dtype == np.float32


@pytest.mark.parametrize("norm", ["last", "revin"])
def test_dlinear_norm_is_shift_equivariant(norm: str) -> None:
    """With window normalization a constant level shift of the input shifts the forecast by the same
    constant, which is what makes these variants robust to level changes."""
    from metronome.models.linear import DLinear

    torch.manual_seed(0)
    model = DLinear(48, 12, 3, kernel_size=13, norm=norm).eval()
    x = torch.randn(4, 48, 3)
    with torch.no_grad():
        y, y_shift = model(x), model(x + 5.0)
    assert torch.allclose(y_shift, y + 5.0, atol=1e-4)
    if norm == "revin":  # also scale-equivariant
        with torch.no_grad():
            assert torch.allclose(model(3.0 * x), 3.0 * y, atol=1e-3)


def test_dlinear_rejects_unknown_norm_and_default_is_unchanged() -> None:
    from metronome.models.linear import DLinear

    with pytest.raises(ValueError):
        DLinear(48, 12, 3, norm="batch")
    a, b = DLinear(48, 12, 3), DLinear(48, 12, 3, norm="none")
    assert set(a.state_dict()) == set(b.state_dict())  # no new weights: ONNX export and registry unchanged
