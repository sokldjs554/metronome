"""Promotion gate for the live service: candidate and champion scored on the same resolved windows.

The offline gate (cadence/simulate.gate_decide) compares a candidate refit on day D with the
incumbent on the days of the candidate's validation span whose every forecast is resolved at
D 00:00. This module is the same decision for the registry: at the candidate's training cutoff
(rows before it known) both ONNX models forecast from the same raw histories on the last
`window_days` blocks of origins before the cutoff, restricted to the blocks whose every target has
arrived (eval/resolve.evaluation_origins), and both are scored on the deployment's fixed scale.
The candidate goes live only when its MAE is strictly lower; a short or non-finite sample and a
tie keep the champion. Integrity (hashes, reference I/O, parity) is a separate check that runs
before this one and again at activation.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from metronome.eval.resolve import evaluation_origins
from metronome.serving.engine import OnnxEngine
from metronome.serving.registry import Registry

WINDOW_DAYS = 14  # the worker's validation span (val_days), like the offline cache's


@dataclass
class GateRecord:
    candidate: str
    champion: str | None
    decision: str  # promote | reject | hold | initial
    reason: str  # better | worse | tie | insufficient_sample | nonfinite | no_champion
    decided_at: str  # wall clock, UTC
    cutoff_row: int  # rows before it were known at the decision (the candidate's training cutoff)
    cutoff_time: str | None
    window_days: int
    n_days: int  # complete resolved blocks in the sample
    n_origins: int
    origin_rows: list[int]  # [first, last] origin rows of the sample
    origin_times: list[str | None]  # their timestamps
    candidate_mae: float | None
    champion_mae: float | None
    scale: str = "fixed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def model_errors(
    registry: Registry,
    version: str,
    values: np.ndarray,
    origins: np.ndarray,
    horizon: int,
    fixed_std: np.ndarray,
    threads: int = 1,
) -> np.ndarray:
    """|forecast - actual| / fixed_std of `version` on every origin: (N, H, C), exactly as served."""
    manifest = registry.manifest(version)
    mean = np.asarray(manifest["scaler"]["mean"], dtype=np.float32)
    std = np.asarray(manifest["scaler"]["std"], dtype=np.float32)
    lookback = int(manifest["lookback"])
    engine = OnnxEngine(registry.model_path(version), threads=threads)
    x = np.stack([(values[o - lookback : o] - mean) / std for o in origins]).astype(np.float32)
    pred = engine.predict(x) * std + mean
    truth = np.stack([values[o : o + horizon] for o in origins]).astype(np.float32)
    errors: np.ndarray = np.abs(pred - truth) / fixed_std
    return errors


def evaluate(
    registry: Registry,
    values: np.ndarray,
    timestamps: np.ndarray | None,
    *,
    candidate: str,
    champion: str | None,
    cutoff_row: int,
    per_day: int,
    window_days: int = WINDOW_DAYS,
    threads: int = 1,
) -> GateRecord:
    dep = registry.deployment()
    fixed_std = np.asarray(dep.fixed_scaler["std"], dtype=np.float32)
    cutoff_row = int(min(max(cutoff_row, 0), len(values)))
    origins, n_days = evaluation_origins(
        cutoff_row, lookback=dep.lookback, horizon=dep.horizon, per_day=per_day, window_days=window_days
    )

    def stamp(row: int) -> str | None:
        return str(timestamps[row]) if timestamps is not None and 0 <= row < len(timestamps) else None

    base: dict[str, Any] = {
        "candidate": candidate,
        "champion": champion,
        "decided_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cutoff_row": cutoff_row,
        "cutoff_time": stamp(cutoff_row - 1),
        "window_days": window_days,
        "n_days": n_days,
        "n_origins": len(origins),
        "origin_rows": [int(origins[0]), int(origins[-1])] if len(origins) else [],
        "origin_times": [stamp(int(origins[0])), stamp(int(origins[-1]))] if len(origins) else [],
        "candidate_mae": None,
        "champion_mae": None,
    }
    if champion is None:
        return GateRecord(decision="initial", reason="no_champion", **base)
    if len(origins) == 0:
        return GateRecord(decision="hold", reason="insufficient_sample", **base)
    cand = float(model_errors(registry, candidate, values, origins, dep.horizon, fixed_std, threads).mean())
    champ = float(model_errors(registry, champion, values, origins, dep.horizon, fixed_std, threads).mean())
    base.update(candidate_mae=cand, champion_mae=champ)
    if not (np.isfinite(cand) and np.isfinite(champ)):
        return GateRecord(decision="hold", reason="nonfinite", **base)
    if cand < champ:
        return GateRecord(decision="promote", reason="better", **base)
    if cand == champ:
        return GateRecord(decision="hold", reason="tie", **base)
    return GateRecord(decision="reject", reason="worse", **base)
