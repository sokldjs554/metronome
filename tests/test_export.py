from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from metronome.export.onnx_export import (
    benchmark,
    check_parity,
    export_onnx,
    ort_predict,
    ort_session,
    quantize_dynamic,
    torch_predict,
    write_reference,
)
from metronome.models import build

L, H, C = 48, 12, 3


def _model(name: str = "dlinear") -> torch.nn.Module:
    torch.manual_seed(0)
    return build(name, L, H, C).eval()


def test_export_parity_and_dynamic_batch(tmp_path: Path) -> None:
    model = _model()
    path = export_onnx(model, L, C, tmp_path / "m.onnx")
    x = np.random.default_rng(0).normal(size=(5, L, C)).astype(np.float32)
    report = check_parity(model, path, x)
    assert report.ok and report.max_abs_diff < 1e-5 and report.output_shape == [5, H, C]
    sess = ort_session(path)
    assert ort_predict(sess, x[:1]).shape == (1, H, C)  # dynamic batch axis


def test_parity_fails_when_graph_is_wrong(tmp_path: Path) -> None:
    model = _model()
    path = export_onnx(model, L, C, tmp_path / "m.onnx")
    other = _model("nlinear")
    x = np.random.default_rng(1).normal(size=(3, L, C)).astype(np.float32)
    assert not check_parity(other, path, x).ok


def test_patchtst_exports(tmp_path: Path) -> None:
    torch.manual_seed(0)
    model = build("patchtst", L, H, C, patch_len=8, stride=4, d_model=8, n_heads=2, n_layers=1).eval()
    path = export_onnx(model, L, C, tmp_path / "p.onnx")
    x = np.random.default_rng(2).normal(size=(2, L, C)).astype(np.float32)
    assert check_parity(model, path, x).ok


def test_quantize_and_benchmark(tmp_path: Path) -> None:
    model = _model()
    fp32 = export_onnx(model, L, C, tmp_path / "m.onnx")
    int8 = quantize_dynamic(fp32, tmp_path / "m.int8.onnx")
    assert int8.exists()
    x = np.random.default_rng(3).normal(size=(4, L, C)).astype(np.float32)
    q = ort_predict(ort_session(int8), x)
    assert q.shape == (4, H, C) and np.isfinite(q).all()
    report = benchmark(model, fp32, int8, L, C, batch_sizes=(1, 4), warmup=2, repeats=5)
    for bs in ("1", "4"):
        for engine in ("torch", "ort_fp32", "ort_int8"):
            e = report["batches"][bs][engine]
            assert e["p50_ms"] > 0 and e["p95_ms"] >= e["p50_ms"]
        assert report["batches"][bs]["ort_fp32"]["max_abs_diff_vs_torch"] < 1e-4
    assert report["sizes_bytes"]["onnx_int8"] < report["sizes_bytes"]["onnx_fp32"] * 1.5


def test_reference_pair_roundtrip(tmp_path: Path) -> None:
    model = _model()
    path = export_onnx(model, L, C, tmp_path / "m.onnx")
    x = np.random.default_rng(4).normal(size=(2, L, C)).astype(np.float32)
    ref = write_reference(path, x, torch_predict(model, x))
    z = np.load(ref)
    np.testing.assert_allclose(ort_predict(ort_session(path), z["x"]), z["y"], atol=1e-5)
