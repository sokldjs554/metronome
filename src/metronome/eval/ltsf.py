"""Standard long-term forecasting protocol (LTSF-Linear / PatchTST): one fixed split, one model.

Used for two things: the model leaderboard on each dataset, and the paper-reproduction check
(docs/protocol.md P10). Metrics are on the train-standardized scale exactly as the papers report.
"""

from __future__ import annotations

import json
import platform
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch

from metronome.data.pipeline import load_prepared
from metronome.data.splits import ltsf_borders
from metronome.data.windows import Scaler, make_windows
from metronome.eval.metrics import mae, mse, per_horizon
from metronome.models import TRAINABLE, build
from metronome.train.trainer import TrainConfig, fit, predict, seed_everything, state_hash


@dataclass
class LTSFConfig:
    dataset: str
    kind: str  # "etth" | "ettm" | "other"
    model: str
    lookback: int = 336
    horizon: int = 96
    seed: int = 2021
    train: TrainConfig = field(default_factory=TrainConfig)
    model_kwargs: dict[str, Any] = field(default_factory=dict)
    tag: str = ""

    @property
    def name(self) -> str:
        return self.tag or f"{self.dataset}_{self.model}_{self.lookback}_{self.horizon}_s{self.seed}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["train"] = self.train.to_dict()
        return d


def run_ltsf(
    cfg: LTSFConfig, processed_dir: Path, out_dir: Path, *, save_model: bool = True
) -> dict[str, Any]:
    _ts, values, channels, manifest = load_prepared(cfg.dataset, processed_dir)
    b1, b2 = ltsf_borders(len(values), cfg.lookback, cfg.kind)
    scaler = Scaler.fit(values[b1[0] : b2[0]])
    z = scaler.transform(values)
    splits = [make_windows(z[b1[i] : b2[i]], cfg.lookback, cfg.horizon) for i in range(3)]
    (x_tr, y_tr), (x_va, y_va), (x_te, y_te) = splits

    seed_everything(cfg.seed)
    model = build(cfg.model, cfg.lookback, cfg.horizon, len(channels), **cfg.model_kwargs)
    fit_info: dict[str, Any] | None = None
    if cfg.model in TRAINABLE:
        fit_info = fit(model, x_tr, y_tr, x_va, y_va, cfg.train, cfg.seed).to_dict()
    else:
        torch.set_num_threads(cfg.train.threads)
    started = time.perf_counter()
    pred = predict(model, x_te, cfg.train.eval_batch_size)
    infer_seconds = time.perf_counter() - started
    target = np.ascontiguousarray(y_te)

    report: dict[str, Any] = {
        "config": cfg.to_dict(),
        "dataset_content_sha256": manifest["content_sha256"],
        "channels": channels,
        "borders": {"start": b1, "end": b2},
        "n_windows": {"train": len(x_tr), "val": len(x_va), "test": len(x_te)},
        "metrics": {
            "mse": mse(pred, target),
            "mae": mae(pred, target),
            "per_horizon_mse_at": {
                str(h): per_horizon(pred, target)["mse"][h - 1] for h in (1, 24, 48, 96) if h <= cfg.horizon
            },
        },
        "fit": fit_info,
        "inference_seconds": infer_seconds,
        "n_parameters": sum(p.numel() for p in model.parameters()),
        "state_sha256": state_hash(model),
        "env": {
            "torch": torch.__version__,
            "python": platform.python_version(),
            "threads": cfg.train.threads,
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{cfg.name}.json").write_text(json.dumps(report, indent=2))
    if save_model and cfg.model in TRAINABLE:
        torch.save(
            {
                "state_dict": model.state_dict(),
                "config": cfg.to_dict(),
                "scaler": scaler.to_dict(),
                "channels": channels,
            },
            out_dir / f"{cfg.name}.pt",
        )
    return report


def dlinear_recipe(threads: int = 1) -> TrainConfig:
    """LTSF-Linear reference script settings for the ETT datasets (lr 0.005, halving, patience 3)."""
    return TrainConfig(
        lr=0.005, batch_size=32, max_epochs=20, patience=3, lr_schedule="halving", threads=threads
    )


def patchtst_recipe(threads: int = 1, max_epochs: int = 100) -> TrainConfig:
    """PatchTST/42 ETTh script settings: lr 1e-4 OneCycle (pct_start 0.3), batch 128, patience 20."""
    return TrainConfig(
        lr=1e-4,
        batch_size=128,
        max_epochs=max_epochs,
        patience=20,
        lr_schedule="onecycle",
        pct_start=0.3,
        threads=threads,
    )
