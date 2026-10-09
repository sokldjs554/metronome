"""Retraining worker: the only serving-side process that imports PyTorch.

Polls the registry for retrain jobs written by the API, trains a replacement on the stream up to
the job's cutoff, exports it to ONNX with a reference pair, registers it, and asks the API to
*promote* it: the API checks integrity (hashes, reference I/O, parity) and then the performance
gate (candidate vs champion on the same resolved windows, serving/gate.py), so a bad export or a
worse model never reaches the service and the previous model keeps serving. Without an API the
worker runs the same gate itself before writing ACTIVE.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from metronome.serving.registry import Registry
from metronome.serving.replay import load_stream

LOGGER = logging.getLogger("metronome.worker")


@dataclass
class WorkerConfig:
    registry_root: Path
    stream_path: Path
    api_url: str | None = None  # when None, run the gate here and write ACTIVE directly
    api_key: str | None = None
    model: str = "dlinear"
    max_epochs: int = 10
    val_days: int = 14
    seed: int = 0
    threads: int = 1
    poll_seconds: float = 2.0
    activate: bool = True  # False: register only; the caller asks the API's gate later


def train_replacement(
    values: np.ndarray,
    cutoff_row: int,
    lookback: int,
    horizon: int,
    *,
    model_name: str = "dlinear",
    max_epochs: int = 10,
    val_days: int = 14,
    seed: int = 0,
    threads: int = 1,
    fixed: dict[str, list[float]] | None = None,
) -> tuple[Any, dict[str, list[float]], dict[str, Any]]:
    """Cold-train on values[:cutoff_row] with the same recipe as the offline refit cache."""
    import torch

    from metronome.data.windows import Scaler, make_windows
    from metronome.models import build
    from metronome.train.trainer import TrainConfig, fit, predict, seed_everything, state_hash

    torch.set_num_threads(threads)
    hist = values[:cutoff_row]
    val_rows = val_days * 24
    train_end = len(hist) - val_rows
    if train_end < lookback + horizon + 1:
        raise ValueError("not enough history to retrain")
    scaler = Scaler.fit(hist[:train_end])
    z = scaler.transform(hist)
    x_tr, y_tr = make_windows(z[:train_end], lookback, horizon)
    x_va, y_va = make_windows(z[train_end - lookback :], lookback, horizon)
    seed_everything(seed)
    model = build(model_name, lookback, horizon, hist.shape[1])
    cfg = TrainConfig(lr=0.005, batch_size=32, max_epochs=max_epochs, patience=3, threads=threads)
    result = fit(model, x_tr, y_tr, x_va, y_va, cfg, seed=seed)
    pred = scaler.inverse(predict(model, x_va))
    truth = scaler.inverse(np.ascontiguousarray(y_va))
    if fixed is not None:
        fstd = np.asarray(fixed["std"], dtype=np.float32)
        val_mae_fixed = float(np.mean(np.abs(pred - truth) / fstd))
    else:
        val_mae_fixed = float(np.mean(np.abs(pred - truth) / scaler.std))
    metrics = {
        "val_mae_fixed": val_mae_fixed,
        "val_mse_standardized": result.best_val,
        "epochs": result.epochs,
        "train_seconds": result.seconds,
        "n_train_windows": len(x_tr),
        "state_sha256": state_hash(model),
    }
    return model, scaler.to_dict(), metrics


def export_and_register(
    registry: Registry,
    model: Any,
    scaler: dict[str, list[float]],
    metrics: dict[str, Any],
    provenance: dict[str, Any],
    values: np.ndarray,
    cutoff_row: int,
    work_dir: Path,
) -> str:
    from metronome.export.onnx_export import check_parity, export_onnx, torch_predict, write_reference

    dep = registry.deployment()
    work_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = export_onnx(model, dep.lookback, len(dep.channels), work_dir / "model.onnx")
    # reference pair: two real windows from the training span, standardized exactly as serving does
    mean = np.asarray(scaler["mean"], dtype=np.float32)
    std = np.asarray(scaler["std"], dtype=np.float32)
    idx = [max(dep.lookback, cutoff_row // 2), cutoff_row - dep.lookback]
    x = np.stack([(values[i - dep.lookback : i] - mean) / std for i in idx]).astype(np.float32)
    y = torch_predict(model, x)
    parity = check_parity(model, onnx_path, x)
    if not parity.ok:
        raise RuntimeError(f"ONNX parity failed: {parity}")
    ref = write_reference(onnx_path, x, y)
    metrics = {**metrics, "export_parity_max_abs_diff": parity.max_abs_diff}
    return registry.register(onnx_path, ref, scaler=scaler, metrics=metrics, provenance=provenance)


def process_job(cfg: WorkerConfig, job_path: Path) -> dict[str, Any]:
    registry = Registry(cfg.registry_root)
    job = json.loads(job_path.read_text())
    dep = registry.deployment()
    ts, values = load_stream(cfg.stream_path)
    cutoff = int(job.get("cutoff_row") or len(values))
    # A job may ask for a specific family / budget (the dashboard's candidate training); the
    # worker's own config is the default. Activation can be left to a gate (API or Airflow).
    from metronome.models import TRAINABLE  # torch import stays out of the serving image

    model_name = str(job.get("model") or cfg.model)
    if model_name not in TRAINABLE:
        raise ValueError(f"unknown model family {model_name!r}; choose one of {sorted(TRAINABLE)}")
    max_epochs = max(1, min(int(job.get("max_epochs") or cfg.max_epochs), 50))
    activate = cfg.activate and bool(job.get("activate", True))
    registry.update_job(job_path, status="training", started_at=time.time(), model=model_name)
    t0 = time.perf_counter()
    model, scaler, metrics = train_replacement(
        values,
        cutoff,
        dep.lookback,
        dep.horizon,
        model_name=model_name,
        max_epochs=max_epochs,
        val_days=cfg.val_days,
        seed=cfg.seed,
        threads=cfg.threads,
        fixed=dep.fixed_scaler,
    )
    provenance = {
        "job_id": job["job_id"],
        "trigger": job.get("trigger"),
        "cutoff_row": cutoff,
        "cutoff_time": str(ts[cutoff - 1]),
        "train_rows": [0, cutoff],
        "model": model_name,
        "max_epochs": max_epochs,
        "seed": cfg.seed,
        "stream_file": str(cfg.stream_path),
    }
    version = export_and_register(
        registry,
        model,
        scaler,
        metrics,
        provenance,
        values,
        cutoff,
        cfg.registry_root / "work" / job["job_id"],
    )
    activation: dict[str, Any]
    if not activate:
        activation = {"skipped": True, "reason": "activation left to the caller"}
    elif cfg.api_url:
        # The gate answers 200 (promoted) or 409 (kept: worse, tie or too little evidence); both
        # are normal outcomes of a job. 422 means the export failed integrity and stays out.
        headers = {"X-API-Key": cfg.api_key} if cfg.api_key else {}
        resp = httpx.post(
            f"{cfg.api_url}/v1/candidates/promote",
            json={"version": version, "reason": "worker"},
            headers=headers,
            timeout=120,
        )
        if resp.status_code not in (200, 409):
            resp.raise_for_status()
        activation = resp.json()
    else:
        activation = promote_locally(registry, version, values, ts, cutoff, via="worker")
    registry.update_job(
        job_path,
        status="done",
        version=version,
        finished_at=time.time(),
        seconds=time.perf_counter() - t0,
        activation=activation,
    )
    LOGGER.info("job %s -> %s (%.1fs)", job["job_id"], version, time.perf_counter() - t0)
    return {"job": job["job_id"], "version": version, "metrics": metrics, "activation": activation}


def promote_locally(
    registry: Registry, version: str, values: np.ndarray, ts: np.ndarray, cutoff: int, *, via: str
) -> dict[str, Any]:
    """The API's promotion in a process without an API: integrity, then the gate, then ACTIVE."""
    from metronome.data.freq import parse_duration
    from metronome.serving import gate

    dep = registry.deployment()
    per_day = round(86400.0 / parse_duration(dep.freq).total_seconds())
    registry.verify(version)
    record = gate.evaluate(
        registry,
        values,
        ts,
        candidate=version,
        champion=registry.active(),
        cutoff_row=cutoff,
        per_day=per_day,
    ).to_dict()
    applied = record["decision"] in ("promote", "initial")
    out: dict[str, Any] = {**record, "via": via, "forced": False, "applied": applied, "activation": None}
    if applied:
        out["activation"] = {
            **registry.activate(version),
            "reason": "gate" if record["decision"] == "promote" else "initial",
        }
    registry.record_gate(version, out)
    return out


def run_worker(cfg: WorkerConfig, *, once: bool = False, max_jobs: int | None = None) -> list[dict[str, Any]]:
    registry = Registry(cfg.registry_root)
    done: list[dict[str, Any]] = []
    while True:
        jobs = registry.pending_jobs()
        for job_path in jobs:
            try:
                done.append(process_job(cfg, job_path))
            except Exception as exc:  # keep serving; record the failure on the job
                LOGGER.exception("job %s failed", job_path.stem)
                registry.update_job(job_path, status="failed", error=str(exc))
            if max_jobs is not None and len(done) >= max_jobs:
                return done
        if once:
            return done
        time.sleep(cfg.poll_seconds)
