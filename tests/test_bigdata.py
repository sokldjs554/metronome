from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from metronome.bigdata import engines


def _tiny_m4(tmp_path: Path) -> list[Path]:
    """Two wide files in the M4 layout: header V1..Vn, one series per row, ragged tails empty."""
    files = []
    for part, rows in (("Hourly", [("H1", [1, 2, 3]), ("H2", [4, 5])]), ("Daily", [("D1", [7, 8, 9, 10])])):
        width = max(len(v) for _, v in rows)
        lines = [",".join(f'"V{i + 1}"' for i in range(width + 1))]
        for sid, values in rows:
            cells = [f'"{sid}"'] + [str(v) for v in values] + [""] * (width - len(values))
            lines.append(",".join(cells))
        p = tmp_path / f"M4-{part}-train.csv"
        p.write_text("\n".join(lines) + "\n")
        files.append(p)
    return files


def test_freq_name_from_filename() -> None:
    assert engines.freq_name(Path("/x/M4-Monthly-train.csv")) == "Monthly"


def test_polars_and_pandas_agree_on_tiny_m4(tmp_path: Path) -> None:
    files = _tiny_m4(tmp_path)
    p_cells, p_series, p_sum = engines.run_polars_m4(files, tmp_path / "polars")
    d_cells, d_series, d_sum = engines.run_pandas_m4(files, tmp_path / "pandas")
    assert (p_cells, p_series) == (9, 3) == (d_cells, d_series)
    assert p_sum == pytest.approx(d_sum)
    assert (tmp_path / "polars" / "frequency=Hourly").exists() and (
        tmp_path / "polars" / "frequency=Daily"
    ).exists()


@pytest.mark.skipif(shutil.which("java") is None, reason="PySpark needs a JVM")
def test_spark_agrees_on_tiny_m4(tmp_path: Path) -> None:
    pytest.importorskip("pyspark")
    files = _tiny_m4(tmp_path)
    p = engines.run_polars_m4(files, tmp_path / "polars")
    s = engines.run_spark_m4(files, tmp_path / "spark", master="local[1]")
    assert s[:2] == p[:2] and s[2] == pytest.approx(p[2])


def test_agrees_uses_the_p12_rule() -> None:
    ref = (100, 10, 1_000_000.0)
    assert engines.agrees((100, 10, 1_000_000.5), ref)
    assert not engines.agrees((100, 10, 1_000_002.0), ref)
    assert not engines.agrees((101, 10, 1_000_000.0), ref)
    assert not engines.agrees((100, 9, 1_000_000.0), ref)


def test_alive_workers_drops_dead_ones() -> None:
    from metronome.bigdata import cluster

    state = {
        "workers": [
            {"id": "w1", "host": "spark-worker-1", "cores": 2, "memory": 3072, "state": "ALIVE"},
            {"id": "w0", "host": "spark-worker-1", "cores": 2, "memory": 3072, "state": "DEAD"},
            {"id": "w2", "host": "spark-worker-2", "cores": 2, "memory": 3072, "state": "ALIVE"},
        ]
    }
    assert [w["id"] for w in cluster.alive_workers(state)] == ["w1", "w2"]
    assert cluster.alive_workers({}) == []


def test_distribution_rule_needs_every_worker_above_the_share() -> None:
    from metronome.bigdata import cluster

    def ex(host: str, tasks: int) -> dict[str, object]:
        return {"id": host, "host": host, "completed_tasks": tasks}

    hosts = ["spark-worker-1", "spark-worker-2"]
    even = [ex("spark-worker-1", 30), ex("spark-worker-2", 26)]
    assert cluster.task_share_by_host(even)["spark-worker-1"] == pytest.approx(30 / 56)
    assert cluster.distributed(even, hosts, 0.25)
    lopsided = [ex("spark-worker-1", 50), ex("spark-worker-2", 6)]
    assert not cluster.distributed(lopsided, hosts, 0.25)
    # a worker whose executor never registered counts as zero
    assert not cluster.distributed([ex("spark-worker-1", 56)], hosts, 0.25)
    assert not cluster.distributed([], hosts, 0.25)


def test_cluster_conf_splits_input_and_waits_for_all_executors() -> None:
    from metronome.bigdata import cluster

    conf = cluster.cluster_conf(n_workers=2, executor_cores=2, executor_memory="2g", partition_mib=8)
    assert conf["spark.sql.files.maxPartitionBytes"] == str(8 * 1024 * 1024)
    assert conf["spark.cores.max"] == "4"
    assert conf["spark.scheduler.minRegisteredResourcesRatio"] == "1.0"
    assert conf["spark.ui.enabled"] == "true"
