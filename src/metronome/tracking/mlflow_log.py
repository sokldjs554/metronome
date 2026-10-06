"""Log Metronome artifacts into MLflow: LTSF runs, cadence policy results, and registry versions.

Why a mirror and not the source: the JSON files under `artifacts/` are what tests and the numbers
check read; MLflow gives the same facts a UI, run comparison, and a model registry with stages.
Registry versions are only promoted to the "production" alias when the file registry's
fail-closed verification passes — MLflow records the decision, it does not make it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mlflow
from mlflow import MlflowClient

from metronome.serving.registry import Registry, VerificationError


def _flatten(prefix: str, obj: Any, out: dict[str, float]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(f"{prefix}{k}.", v, out)
    elif isinstance(obj, int | float) and not isinstance(obj, bool):
        out[prefix[:-1]] = float(obj)


def log_ltsf_runs(runs_dir: Path, tracking_uri: str, experiment: str = "metronome/ltsf") -> list[str]:
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    run_ids = []
    for path in sorted(runs_dir.glob("*.json")):
        report = json.loads(path.read_text())
        cfg = report["config"]
        with mlflow.start_run(run_name=path.stem) as run:
            mlflow.log_params(
                {
                    "dataset": cfg["dataset"],
                    "model": cfg["model"],
                    "lookback": cfg["lookback"],
                    "horizon": cfg["horizon"],
                    "seed": cfg["seed"],
                    "lr": cfg["train"]["lr"],
                    "batch_size": cfg["train"]["batch_size"],
                    "max_epochs": cfg["train"]["max_epochs"],
                    "lr_schedule": cfg["train"]["lr_schedule"],
                }
            )
            metrics: dict[str, float] = {}
            _flatten("", report["metrics"], metrics)
            if report.get("fit"):
                metrics["fit.epochs"] = float(report["fit"]["epochs"])
                metrics["fit.seconds"] = float(report["fit"]["seconds"])
                metrics["fit.best_val"] = float(report["fit"]["best_val"])
                for h in report["fit"].get("history", []):
                    mlflow.log_metric("epoch_val_loss", h["val"], step=int(h["epoch"]))
            mlflow.log_metrics({k.replace("@", "_"): v for k, v in metrics.items()})
            mlflow.set_tags(
                {
                    "state_sha256": report["state_sha256"],
                    "dataset_sha256": report["dataset_content_sha256"][:16],
                }
            )
            mlflow.log_artifact(str(path))
            pt = path.with_suffix(".pt")
            if pt.exists():
                mlflow.log_artifact(str(pt))
            run_ids.append(run.info.run_id)
    return run_ids


def log_cadence(cadence_dir: Path, tracking_uri: str, experiment: str = "metronome/cadence") -> list[str]:
    """One MLflow run per (cache, policy): comparable in the UI as a table of MAE vs refits."""
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    run_ids = []
    for path in sorted(cadence_dir.glob("*.json")):
        summary = json.loads(path.read_text())
        cache_name = summary["cache"]
        with mlflow.start_run(run_name=cache_name) as parent:
            mlflow.log_params({"cache": cache_name, "seed": summary["seed"]})
            mlflow.log_artifact(str(path))
            for policy, res in summary["policies"].items():
                with mlflow.start_run(run_name=f"{cache_name}/{policy}", nested=True) as child:
                    mlflow.log_params({"cache": cache_name, "policy": policy, "seed": summary["seed"]})
                    mlflow.log_metrics(
                        {
                            "mae": res["mae"],
                            "mse": res["mse"],
                            "n_refits": res["n_refits"],
                            "train_seconds": res["train_seconds"],
                        }
                    )
                    run_ids.append(child.info.run_id)
            run_ids.append(parent.info.run_id)
    return run_ids


def register_versions(
    registry_root: Path, tracking_uri: str, model_name: str | None = None
) -> list[dict[str, Any]]:
    """Mirror the file registry into the MLflow Model Registry and alias the verified active version."""
    mlflow.set_tracking_uri(tracking_uri)
    registry = Registry(registry_root)
    dep = registry.deployment()
    name = model_name or f"metronome-{dep.dataset}"
    client = MlflowClient()
    mlflow.set_experiment("metronome/registry")
    out = []
    active = registry.active()
    for version in registry.list_versions():
        manifest = registry.manifest(version)
        try:
            check = registry.verify(version)
            verified, reason = True, f"parity {check['max_abs_diff']:.2e}"
        except VerificationError as exc:
            verified, reason = False, str(exc)
        with mlflow.start_run(run_name=f"{name}/{version}") as run:
            mlflow.log_params(
                {
                    "version": version,
                    "trigger": manifest.get("provenance", {}).get("trigger"),
                    "cutoff_time": manifest.get("provenance", {}).get("cutoff_time"),
                    "onnx_sha256": manifest["onnx_sha256"],
                }
            )
            metrics: dict[str, float] = {}
            _flatten("", manifest.get("metrics", {}), metrics)
            mlflow.log_metrics(metrics)
            mlflow.set_tags(
                {
                    "verified": str(verified),
                    "verification": reason,
                    "file_registry_active": str(version == active),
                }
            )
            mlflow.log_artifacts(str(registry.versions_dir / version))
            mv = mlflow.register_model(f"runs:/{run.info.run_id}", name)
            if verified and version == active:
                client.set_registered_model_alias(name, "production", mv.version)
            client.set_model_version_tag(name, mv.version, "file_version", version)
            client.set_model_version_tag(name, mv.version, "verified", str(verified))
            out.append(
                {
                    "version": version,
                    "mlflow_version": mv.version,
                    "verified": verified,
                    "active": version == active,
                }
            )
    return out
