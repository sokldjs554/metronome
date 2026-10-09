"""Weekly retraining with a promotion gate, as an Airflow DAG.

The offline experiment (docs/results.md) compares a weekly retrain that only promotes the
candidate when it beats the champion (periodic-7+gate) with the un-gated schedules. This DAG runs
that policy against the live service:

    champion_state -> train_candidate -> gate -> promoted | keep

* champion_state reads the serving API: which version is active and where the replayed stream is.
* train_candidate writes a retrain job into the shared registry and runs the worker once with
  activation turned off, so the candidate is exported, parity-checked and registered but not serving.
* gate asks the API to promote the candidate (POST /v1/candidates/promote). The API re-verifies
  hashes and reference I/O, then scores candidate and champion on the same resolved windows
  before the candidate's training cutoff (serving/gate.py) and swaps only a strictly better one.
  The DAG names the champion it saw, so a decision is never applied against a different live model.
* promoted checks the service really serves the candidate; keep logs why it stayed registered only.

Configuration (Airflow Variables or environment, in that order): METRONOME_API_URL, METRONOME_REGISTRY,
METRONOME_API_KEY, METRONOME_MAX_EPOCHS. The worker needs PyTorch, so run Airflow where
`metronome[train,export]` is installed. CI runs the whole DAG with `airflow dags test`.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from airflow.decorators import dag, task

LOGGER = logging.getLogger("airflow.task")
DAG_ID = "metronome_weekly_retrain"


def setting(name: str, default: str) -> str:
    """An Airflow Variable if set, else the environment, else the default."""
    try:
        from airflow.models import Variable

        value = Variable.get(name, default_var=None)
        if value:
            return str(value)
    except Exception:  # no metadata DB yet (e.g. DAG parsing in isolation)
        pass
    return os.environ.get(name, default)


def api_headers() -> dict[str, str]:
    key = setting("METRONOME_API_KEY", "")
    return {"X-API-Key": key} if key else {}


@dag(
    dag_id=DAG_ID,
    description="Weekly retrain with a promotion gate (periodic-7+gate from docs/results.md)",
    schedule="0 3 * * 1",  # Monday 03:00
    start_date=datetime(2026, 10, 6),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 0, "execution_timeout": timedelta(hours=2)},
    tags=["metronome", "retrain"],
)
def metronome_weekly_retrain() -> None:
    @task
    def champion_state() -> dict[str, Any]:
        import httpx

        base = setting("METRONOME_API_URL", "http://127.0.0.1:8000").rstrip("/")
        ready = httpx.get(f"{base}/ready", timeout=30).json()
        if not ready.get("ready"):
            raise RuntimeError(f"service not ready: {ready}")
        monitor = httpx.get(f"{base}/v1/monitor", timeout=30).json()
        replay = httpx.get(f"{base}/v1/replay", timeout=30).json()
        state = {
            "api_url": base,
            "champion": ready["model"],
            "rolling_7d_mae": monitor.get("rolling_7d_mae"),
            "baseline_val_mae": monitor.get("baseline_val_mae"),
            "resolved_forecasts": monitor.get("resolved_forecasts", 0),
            # In a replayed stream the cutoff is the replay cursor; in production it is None (all data).
            "cutoff_row": replay.get("cursor") if replay.get("active") else None,
            "pending_jobs": monitor.get("pending_jobs", []),
        }
        LOGGER.info(
            "champion %s rolling_7d_mae=%s baseline_val_mae=%s cutoff=%s",
            state["champion"],
            state["rolling_7d_mae"],
            state["baseline_val_mae"],
            state["cutoff_row"],
        )
        return state

    @task
    def train_candidate(state: dict[str, Any]) -> dict[str, Any]:
        from metronome.serving.registry import Registry
        from metronome.serving.worker import WorkerConfig, run_worker

        root = Path(setting("METRONOME_REGISTRY", "registry/etth1"))
        registry = Registry(root)
        if state["pending_jobs"]:
            raise RuntimeError(f"retrain jobs already pending: {state['pending_jobs']}")
        job = registry.request_retrain(
            {
                "trigger": "airflow-weekly",
                "cutoff_row": state["cutoff_row"],
                "active_version": state["champion"],
            }
        )
        cfg = WorkerConfig(
            registry_root=root,
            stream_path=root / "stream.npz",
            api_url=None,
            activate=False,
            max_epochs=int(setting("METRONOME_MAX_EPOCHS", "10")),
            threads=int(setting("METRONOME_WORKER_THREADS", "1")),
        )
        done = run_worker(cfg, once=True, max_jobs=1)
        if not done or done[0]["job"] != job.stem:
            raise RuntimeError(f"worker did not process {job.stem}: {done}")
        result = {
            "version": done[0]["version"],
            "val_mae_fixed": done[0]["metrics"]["val_mae_fixed"],
            "job": job.stem,
        }
        LOGGER.info(
            "candidate %s val_mae_fixed=%.4f (not activated)", result["version"], result["val_mae_fixed"]
        )
        return result

    @task.branch
    def gate(state: dict[str, Any], candidate: dict[str, Any]) -> str:
        import httpx

        resp = httpx.post(
            f"{state['api_url']}/v1/candidates/promote",
            json={"version": candidate["version"], "reason": "airflow-weekly", "champion": state["champion"]},
            headers=api_headers(),
            timeout=300,
        )
        if resp.status_code not in (200, 409):
            resp.raise_for_status()
        decision = resp.json()
        if "decision" not in decision:  # 409 without a record: champion changed or already active
            raise RuntimeError(f"promotion refused: {decision}")
        LOGGER.info("gate: %s", json.dumps(decision))
        Path(setting("METRONOME_GATE_LOG", "/tmp/metronome-gate.json")).write_text(
            json.dumps(decision, indent=2)
        )
        return "promoted" if decision["applied"] else "keep"

    @task
    def promoted(state: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        import httpx

        ready = httpx.get(f"{state['api_url']}/ready", timeout=30).json()
        if ready.get("model") != candidate["version"]:
            raise RuntimeError(f"promotion did not take: {ready}")
        LOGGER.info("promoted %s -> %s", state["champion"], candidate["version"])
        return ready

    @task
    def keep(state: dict[str, Any], candidate: dict[str, Any]) -> None:
        LOGGER.info(
            "kept %s; candidate %s stays registered but inactive", state["champion"], candidate["version"]
        )

    s = champion_state()
    c = train_candidate(s)
    g = gate(s, c)
    g >> [promoted(s, c), keep(s, c)]


metronome_weekly_retrain()
