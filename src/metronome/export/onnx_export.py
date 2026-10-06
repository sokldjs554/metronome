"""Export a trained forecaster to ONNX and prove the exported graph computes the same function.

Every export writes a reference input/output pair next to the graph. The serving registry replays
that pair with ONNX Runtime before a version may go live (fail-closed parity), so a stale or
mismatched file can never serve a forecast.
"""

from __future__ import annotations

import hashlib
import json
import platform
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import torch
from torch import nn

OPSET = 17
PARITY_TOL = 1e-4


@dataclass
class ParityReport:
    max_abs_diff: float
    tolerance: float
    ok: bool
    output_shape: list[int]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_onnx(model: nn.Module, lookback: int, channels: int, path: Path, opset: int = OPSET) -> Path:
    model.eval()
    path.parent.mkdir(parents=True, exist_ok=True)
    example = torch.zeros(1, lookback, channels, dtype=torch.float32)
    torch.onnx.export(
        model,
        (example,),
        str(path),
        input_names=["history"],
        output_names=["forecast"],
        dynamic_axes={"history": {0: "batch"}, "forecast": {0: "batch"}},
        opset_version=opset,
        dynamo=False,
    )
    return path


def ort_session(path: Path, threads: int = 1) -> ort.InferenceSession:
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


def ort_predict(session: ort.InferenceSession, x: np.ndarray) -> np.ndarray:
    name = session.get_inputs()[0].name
    return session.run(None, {name: np.ascontiguousarray(x, dtype=np.float32)})[0]


@torch.inference_mode()
def torch_predict(model: nn.Module, x: np.ndarray) -> np.ndarray:
    model.eval()
    return model(torch.from_numpy(np.ascontiguousarray(x, dtype=np.float32))).numpy()


def check_parity(model: nn.Module, onnx_path: Path, x: np.ndarray, tol: float = PARITY_TOL) -> ParityReport:
    ref = torch_predict(model, x)
    out = ort_predict(ort_session(onnx_path), x)
    if out.shape != ref.shape:
        return ParityReport(float("inf"), tol, False, list(out.shape))
    diff = float(np.max(np.abs(out - ref))) if out.size else 0.0
    ok = bool(np.isfinite(out).all() and diff <= tol)
    return ParityReport(diff, tol, ok, list(out.shape))


def write_reference(onnx_path: Path, x: np.ndarray, y: np.ndarray) -> Path:
    ref = onnx_path.with_name("reference.npz")
    np.savez(ref, x=np.ascontiguousarray(x, dtype=np.float32), y=np.ascontiguousarray(y, dtype=np.float32))
    return ref


def quantize_dynamic(onnx_path: Path, out_path: Path) -> Path:
    from onnxruntime.quantization import QuantType
    from onnxruntime.quantization import quantize_dynamic as _quantize

    _quantize(str(onnx_path), str(out_path), weight_type=QuantType.QInt8)
    return out_path


def _percentiles(samples: list[float]) -> dict[str, float]:
    arr = np.asarray(samples) * 1000.0
    return {
        "p50_ms": float(np.percentile(arr, 50)),
        "p95_ms": float(np.percentile(arr, 95)),
        "p99_ms": float(np.percentile(arr, 99)),
        "mean_ms": float(arr.mean()),
    }


def benchmark(
    model: nn.Module,
    onnx_fp32: Path,
    onnx_int8: Path | None,
    lookback: int,
    channels: int,
    *,
    batch_sizes: tuple[int, ...] = (1, 16, 64),
    warmup: int = 50,
    repeats: int = 300,
    threads: int = 1,
    seed: int = 0,
) -> dict[str, Any]:
    """Latency of torch eager vs ONNX Runtime (fp32, int8) on identical float32 NumPy inputs.

    Engine order is alternated every round so that neither engine systematically benefits from a
    warmer cache. Numbers are the model call only, excluding HTTP.
    """
    torch.set_num_threads(threads)
    rng = np.random.default_rng(seed)
    engines: dict[str, Any] = {"torch": None, "ort_fp32": ort_session(onnx_fp32, threads)}
    if onnx_int8 is not None:
        engines["ort_int8"] = ort_session(onnx_int8, threads)

    def call(name: str, x: np.ndarray) -> np.ndarray:
        return torch_predict(model, x) if name == "torch" else ort_predict(engines[name], x)

    results: dict[str, Any] = {
        "threads": threads,
        "warmup": warmup,
        "repeats": repeats,
        "opset": OPSET,
        "sizes_bytes": {
            "onnx_fp32": onnx_fp32.stat().st_size,
            "onnx_int8": onnx_int8.stat().st_size if onnx_int8 else None,
        },
        "env": {
            "torch": torch.__version__,
            "onnxruntime": ort.__version__,
            "python": platform.python_version(),
            "machine": platform.machine(),
        },
        "batches": {},
    }
    for bs in batch_sizes:
        x = rng.normal(size=(bs, lookback, channels)).astype(np.float32)
        names = list(engines)
        for name in names:
            for _ in range(warmup):
                call(name, x)
        samples: dict[str, list[float]] = {n: [] for n in names}
        for r in range(repeats):
            order = names if r % 2 == 0 else names[::-1]
            for name in order:
                t0 = time.perf_counter()
                call(name, x)
                samples[name].append(time.perf_counter() - t0)
        ref = call("torch", x)
        per_engine: dict[str, Any] = {}
        for name in names:
            out = call(name, x)
            per_engine[name] = {
                **_percentiles(samples[name]),
                "throughput_rows_per_s": bs / (np.mean(samples[name]) or 1e-12),
                "max_abs_diff_vs_torch": float(np.max(np.abs(out - ref))),
            }
        results["batches"][str(bs)] = per_engine
    return results


def save_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj if not hasattr(obj, "__dataclass_fields__") else asdict(obj), indent=2))
