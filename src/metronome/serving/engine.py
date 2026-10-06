"""ONNX Runtime inference engine (the only engine the serving image ships)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort


class OnnxEngine:
    def __init__(self, path: Path, threads: int = 1) -> None:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        self.lookback = int(shape[1])
        self.channels = int(shape[2])
        self.path = Path(path)

    def predict(self, x: np.ndarray) -> np.ndarray:
        arr = np.ascontiguousarray(x, dtype=np.float32)
        if arr.ndim != 3 or arr.shape[1] != self.lookback or arr.shape[2] != self.channels:
            raise ValueError(f"expected (batch, {self.lookback}, {self.channels}), got {arr.shape}")
        out: np.ndarray = self.session.run(None, {self.input_name: arr})[0]
        return out
