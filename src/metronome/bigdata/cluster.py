"""The P12 Spark job on a standalone cluster (protocol P16).

One master and N workers run in separate containers (docker-compose.spark.yml); this module is the
driver. The transformation is `engines.spark_melt`, unchanged; what changes is the master URL and the
input split size. With Spark's default 128 MiB splits each M4 file is a single task, so a cluster
would sit idle. Input CSV and output Parquet live on a volume every container mounts at the same
path, standing in for HDFS or object storage.

The run passes only if (1) the cluster result agrees with Polars on the same files (the P12 rule) and
(2) every worker's executors completed at least `min_share` of the tasks.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import time
import urllib.request
from pathlib import Path
from typing import Any

import polars as pl

from metronome.bigdata.engines import (
    LOCAL_SPARK_CONF,
    agrees,
    m4_files,
    run_polars_m4,
    spark_melt,
    spark_session,
)


def _get_json(url: str, timeout: float = 5.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def alive_workers(master_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Workers the master reports as ALIVE, from its `/json/` page."""
    return [
        {"id": w["id"], "host": w["host"], "cores": w["cores"], "memory_mb": w["memory"]}
        for w in master_state.get("workers", [])
        if w.get("state") == "ALIVE"
    ]


def wait_for_workers(master_ui: str, n_workers: int, timeout: float = 180.0) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    workers: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        try:
            workers = alive_workers(_get_json(f"{master_ui.rstrip('/')}/json/"))
        except OSError:
            workers = []
        if len(workers) >= n_workers:
            return workers
        time.sleep(2)
    raise RuntimeError(f"only {len(workers)} of {n_workers} workers registered with {master_ui}")


def executor_stats(spark: Any) -> list[dict[str, Any]]:
    """Per-executor task counts from the driver's REST API (the driver itself is left out)."""
    sc = spark.sparkContext
    rows = _get_json(f"{sc.uiWebUrl}/api/v1/applications/{sc.applicationId}/allexecutors")
    return [
        {
            "id": e["id"],
            "host": e["hostPort"].rsplit(":", 1)[0],
            "cores": e["totalCores"],
            "completed_tasks": e["completedTasks"],
            "failed_tasks": e["failedTasks"],
            "task_seconds": e["totalDuration"] / 1000.0,
        }
        for e in rows
        if e["id"] != "driver"
    ]


def task_share_by_host(executors: list[dict[str, Any]]) -> dict[str, float]:
    total = sum(e["completed_tasks"] for e in executors)
    share: dict[str, float] = {}
    for e in executors:
        share[e["host"]] = share.get(e["host"], 0.0) + (e["completed_tasks"] / total if total else 0.0)
    return share


def distributed(executors: list[dict[str, Any]], worker_hosts: list[str], min_share: float) -> bool:
    """Every worker host ran at least `min_share` of the completed tasks."""
    share = task_share_by_host(executors)
    return all(share.get(h, 0.0) >= min_share for h in worker_hosts)


def cluster_conf(
    *, n_workers: int, executor_cores: int, executor_memory: str, partition_mib: int
) -> dict[str, str]:
    return {
        "spark.driver.host": socket.gethostname(),
        "spark.driver.bindAddress": "0.0.0.0",
        # Same as the single-machine run: the local reference below reuses this driver JVM.
        "spark.driver.memory": LOCAL_SPARK_CONF["spark.driver.memory"],
        "spark.executor.cores": str(executor_cores),
        "spark.executor.memory": executor_memory,
        "spark.cores.max": str(n_workers * executor_cores),
        # Start scheduling only once every executor has registered, so no worker is left out.
        "spark.scheduler.minRegisteredResourcesRatio": "1.0",
        "spark.scheduler.maxRegisteredResourcesWaitingTime": "120s",
        "spark.sql.files.maxPartitionBytes": str(partition_mib << 20),
        "spark.sql.shuffle.partitions": "8",
        "spark.ui.enabled": "true",  # the REST API that reports tasks per executor
    }


def _result(seconds: float, triple: tuple[int, int, float], **extra: Any) -> dict[str, Any]:
    return {"seconds": seconds, "n_cells": triple[0], "n_series": triple[1], "checksum": triple[2], **extra}


def run_cluster_stage(
    raw_dir: Path,
    out_dir: Path,
    *,
    master: str,
    master_ui: str,
    n_workers: int = 2,
    local_dir: Path | None = None,
    executor_cores: int = 2,
    executor_memory: str = "2g",
    partition_mib: int = 8,
    min_share: float = 0.25,
    local_reference: bool = True,
) -> dict[str, Any]:
    files = m4_files(raw_dir, local_dir)
    workers = wait_for_workers(master_ui, n_workers)

    t0 = time.perf_counter()
    ref = run_polars_m4(files, out_dir / "parquet" / "polars")
    polars_seconds = time.perf_counter() - t0

    conf = cluster_conf(
        n_workers=n_workers,
        executor_cores=executor_cores,
        executor_memory=executor_memory,
        partition_mib=partition_mib,
    )
    spark = spark_session(master, conf, app_name="metronome-bigdata-cluster")
    try:
        t0 = time.perf_counter()
        cells, series, checksum, per_file = spark_melt(spark, files, out_dir / "parquet" / "spark-cluster")
        cluster_seconds = time.perf_counter() - t0
        executors = executor_stats(spark)
        spark_version = spark.version
    finally:
        spark.stop()
    cluster = (cells, series, checksum)
    worker_hosts = [w["host"] for w in workers]

    report: dict[str, Any] = {
        "source": {"name": "M4 train (6 frequencies)", "files": [f.name for f in files]},
        "master": master,
        "workers": workers,
        "conf": {k: v for k, v in conf.items() if k not in ("spark.driver.host", "spark.driver.bindAddress")},
        "polars": _result(polars_seconds, ref),
        "cluster": _result(cluster_seconds, cluster, per_file=per_file),
        "executors": executors,
        "task_share_by_host": task_share_by_host(executors),
        "min_share": min_share,
        "agree": agrees(cluster, ref),
        "distributed": distributed(executors, worker_hosts, min_share),
        "host_cpu_count": os.cpu_count(),
        "machine": platform.machine(),
        "versions": {"spark": spark_version, "polars": pl.__version__, "python": platform.python_version()},
    }

    if local_reference:
        # Same container, same split size, no cluster: separates the effect of the split size from
        # the effect of the cluster. Not part of the pass rule.
        local_conf = {**LOCAL_SPARK_CONF, "spark.sql.files.maxPartitionBytes": str(partition_mib << 20)}
        n_local = n_workers * executor_cores
        spark = spark_session(f"local[{n_local}]", local_conf, app_name="metronome-bigdata-local")
        try:
            t0 = time.perf_counter()
            lc, ls, lsum, _ = spark_melt(spark, files, out_dir / "parquet" / "spark-local")
            local_seconds = time.perf_counter() - t0
        finally:
            spark.stop()
        report["local_same_splits"] = _result(local_seconds, (lc, ls, lsum), master=f"local[{n_local}]")
        report["local_same_splits"]["agree"] = agrees((lc, ls, lsum), ref)

    report["passed"] = bool(report["agree"] and report["distributed"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bigdata_cluster.json").write_text(json.dumps(report, indent=2))
    return report
