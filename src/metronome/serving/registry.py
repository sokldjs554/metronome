"""File-based model registry with fail-closed verification.

Layout::

    <root>/deployment.json                what is being served (dataset, L, H, channels, fixed scaler)
    <root>/versions/<version>/model.onnx
    <root>/versions/<version>/reference.npz   input/output pair recorded at export time
    <root>/versions/<version>/manifest.json   sha256 of model.onnx, scaler, metrics, provenance
    <root>/ACTIVE                             the active version name (written atomically)

A version can only be activated after `verify()` recomputed the ONNX file hash and replayed the
reference input through ONNX Runtime within tolerance. MLflow mirrors this registry when enabled;
the directory is the source of truth for the running service.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from metronome.serving.engine import OnnxEngine

PARITY_TOL = 1e-4


class RegistryError(RuntimeError):
    pass


class VerificationError(RegistryError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


@dataclass(frozen=True)
class Deployment:
    dataset: str
    lookback: int
    horizon: int
    channels: list[str]
    fixed_scaler: dict[str, list[float]]
    freq: str = "1h"
    stream_start: int | None = None  # row where the held-out evaluation stream begins (replay default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "lookback": self.lookback,
            "horizon": self.horizon,
            "channels": self.channels,
            "fixed_scaler": self.fixed_scaler,
            "freq": self.freq,
            "stream_start": self.stream_start,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Deployment:
        return cls(
            dataset=d["dataset"],
            lookback=int(d["lookback"]),
            horizon=int(d["horizon"]),
            channels=list(d["channels"]),
            fixed_scaler=d["fixed_scaler"],
            freq=d.get("freq", "1h"),
            stream_start=d.get("stream_start"),
        )


class Registry:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.versions_dir = self.root / "versions"

    # ---- deployment ---------------------------------------------------------------------------
    def init(self, deployment: Deployment) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.versions_dir.mkdir(exist_ok=True)
        _atomic_write(self.root / "deployment.json", json.dumps(deployment.to_dict(), indent=2))

    def deployment(self) -> Deployment:
        path = self.root / "deployment.json"
        if not path.exists():
            raise RegistryError(f"{self.root} is not an initialized registry")
        return Deployment.from_dict(json.loads(path.read_text()))

    # ---- versions -----------------------------------------------------------------------------
    def list_versions(self) -> list[str]:
        if not self.versions_dir.exists():
            return []
        return sorted(p.name for p in self.versions_dir.iterdir() if (p / "manifest.json").exists())

    def next_version(self) -> str:
        existing = [int(v[1:]) for v in self.list_versions() if v.startswith("v") and v[1:].isdigit()]
        return f"v{(max(existing) + 1 if existing else 1):04d}"

    def manifest(self, version: str) -> dict[str, Any]:
        path = self.versions_dir / version / "manifest.json"
        if not path.exists():
            raise RegistryError(f"unknown version {version}")
        return json.loads(path.read_text())

    def model_path(self, version: str) -> Path:
        return self.versions_dir / version / "model.onnx"

    def register(
        self,
        onnx_path: Path,
        reference_path: Path,
        *,
        scaler: dict[str, list[float]],
        metrics: dict[str, Any],
        provenance: dict[str, Any],
        version: str | None = None,
    ) -> str:
        """Copy an exported model into the registry under a new version and write its manifest."""
        dep = self.deployment()
        version = version or self.next_version()
        target = self.versions_dir / version
        if target.exists():
            raise RegistryError(f"version {version} already exists")
        tmp = self.versions_dir / f".{version}.partial"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        shutil.copyfile(onnx_path, tmp / "model.onnx")
        shutil.copyfile(reference_path, tmp / "reference.npz")
        manifest = {
            "version": version,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset": dep.dataset,
            "lookback": dep.lookback,
            "horizon": dep.horizon,
            "channels": dep.channels,
            "scaler": scaler,
            "metrics": metrics,
            "provenance": provenance,
            "onnx_sha256": sha256_file(tmp / "model.onnx"),
            "reference_sha256": sha256_file(tmp / "reference.npz"),
            "parity_tolerance": PARITY_TOL,
        }
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2))
        os.replace(tmp, target)
        return version

    def verify(self, version: str, threads: int = 1) -> dict[str, Any]:
        """Recompute hashes and replay the reference pair; raise VerificationError on any mismatch."""
        manifest = self.manifest(version)
        vdir = self.versions_dir / version
        onnx_path, ref_path = vdir / "model.onnx", vdir / "reference.npz"
        if not onnx_path.exists() or not ref_path.exists():
            raise VerificationError(f"{version}: files missing")
        if sha256_file(onnx_path) != manifest["onnx_sha256"]:
            raise VerificationError(f"{version}: model.onnx hash mismatch")
        if sha256_file(ref_path) != manifest["reference_sha256"]:
            raise VerificationError(f"{version}: reference.npz hash mismatch")
        ref = np.load(ref_path)
        engine = OnnxEngine(onnx_path, threads=threads)
        out = engine.predict(ref["x"])
        if out.shape != ref["y"].shape:
            raise VerificationError(f"{version}: output shape {out.shape} != {ref['y'].shape}")
        if not np.isfinite(out).all():
            raise VerificationError(f"{version}: non-finite output")
        diff = float(np.max(np.abs(out - ref["y"])))
        if diff > manifest["parity_tolerance"]:
            raise VerificationError(f"{version}: parity {diff:.2e} exceeds {manifest['parity_tolerance']}")
        dep = self.deployment()
        if out.shape[1] != dep.horizon or out.shape[2] != len(dep.channels):
            raise VerificationError(f"{version}: output does not match deployment horizon/channels")
        return {"version": version, "max_abs_diff": diff, "onnx_sha256": manifest["onnx_sha256"]}

    # ---- activation ---------------------------------------------------------------------------
    def active(self) -> str | None:
        path = self.root / "ACTIVE"
        if not path.exists():
            return None
        value = path.read_text().strip()
        return value or None

    def activate(self, version: str) -> dict[str, Any]:
        report = self.verify(version)
        _atomic_write(self.root / "ACTIVE", version + "\n")
        return report

    # ---- retrain jobs (API -> worker hand-off) ------------------------------------------------
    def request_retrain(self, reason: dict[str, Any]) -> Path:
        jobs = self.root / "jobs"
        jobs.mkdir(exist_ok=True)
        job_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{int(time.time() * 1000) % 1000:03d}"
        path = jobs / f"{job_id}.json"
        _atomic_write(path, json.dumps({"job_id": job_id, "status": "requested", **reason}, indent=2))
        return path

    def _jobs_with_status(self, statuses: set[str]) -> list[Path]:
        jobs = self.root / "jobs"
        if not jobs.exists():
            return []
        out = []
        for p in sorted(jobs.glob("*.json")):
            if json.loads(p.read_text()).get("status") in statuses:
                out.append(p)
        return out

    def pending_jobs(self) -> list[Path]:
        """Jobs a worker has not picked up yet."""
        return self._jobs_with_status({"requested"})

    def open_jobs(self) -> list[Path]:
        """Jobs that are requested or currently training: the service must not stack more on top."""
        return self._jobs_with_status({"requested", "training"})

    def update_job(self, path: Path, **fields: Any) -> None:
        data = json.loads(path.read_text())
        data.update(fields)
        _atomic_write(path, json.dumps(data, indent=2))
