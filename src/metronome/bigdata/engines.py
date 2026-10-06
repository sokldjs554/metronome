"""Wide CSV (one series per row or one series per column) -> long Parquet, three engines.

The job is deliberately mundane — melt, drop missing cells, per-series statistics, partitioned
Parquet, re-read and count — because that is what a data pipeline spends its time on. Each engine
must produce the same cell count and the same per-series aggregates (checked to 1e-6) or the
stage fails. Timings are wall-clock medians over repeated runs.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from metronome.data.fetch import fetch

M4_PARTS = ("Hourly", "Daily", "Weekly", "Monthly", "Quarterly", "Yearly")


@dataclass
class EngineResult:
    engine: str
    source: str
    seconds: list[float]
    median_seconds: float
    n_cells: int
    n_series: int
    parquet_bytes: int
    checksum: float  # sum of per-series means, compared across engines


def _m4_files(raw_dir: Path, local_dir: Path | None) -> list[Path]:
    return [fetch(f"m4_{part.lower()}_train", raw_dir, local_dir) for part in M4_PARTS]


# ---- Polars --------------------------------------------------------------------------------------
def run_polars_m4(files: list[Path], out_dir: Path) -> tuple[int, int, float]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    total_cells, total_series, checksum = 0, 0, 0.0
    for f in files:
        lf = pl.scan_csv(f, infer_schema_length=0)  # every column as string -> cast after melt
        long = (
            lf.unpivot(index=["V1"], variable_name="step", value_name="value")
            .filter(pl.col("value").is_not_null() & (pl.col("value") != ""))
            .with_columns(
                pl.col("value").cast(pl.Float64),
                pl.col("step").str.slice(1).cast(pl.Int32) - 1,
                pl.lit(f.stem.split("-")[0]).alias("frequency"),
            )
            .rename({"V1": "series_id"})
        )
        part_dir = out_dir / f"frequency={f.stem.split('-')[0]}"
        part_dir.mkdir()
        long.sink_parquet(part_dir / "part-0.parquet", compression="zstd")
        stats = (
            pl.scan_parquet(part_dir / "part-0.parquet")
            .group_by("series_id")
            .agg(pl.len().alias("n"), pl.col("value").mean().alias("mean"))
            .collect()
        )
        total_cells += int(stats["n"].sum())
        total_series += stats.height
        checksum += float(stats["mean"].sum())
    return total_cells, total_series, checksum


# ---- pandas --------------------------------------------------------------------------------------
def run_pandas_m4(files: list[Path], out_dir: Path) -> tuple[int, int, float]:
    import pandas as pd

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    total_cells, total_series, checksum = 0, 0, 0.0
    for f in files:
        wide = pd.read_csv(f, dtype=str)
        long = wide.melt(id_vars=["V1"], var_name="step", value_name="value")
        long = long[long["value"].notna() & (long["value"] != "")]
        long["value"] = long["value"].astype("float64")
        long["step"] = long["step"].str[1:].astype("int32") - 1
        long["frequency"] = f.stem.split("-")[0]
        long = long.rename(columns={"V1": "series_id"})
        part_dir = out_dir / f"frequency={f.stem.split('-')[0]}"
        part_dir.mkdir()
        long.to_parquet(part_dir / "part-0.parquet", compression="zstd", index=False)
        stats = (
            pd.read_parquet(part_dir / "part-0.parquet").groupby("series_id")["value"].agg(["count", "mean"])
        )
        total_cells += int(stats["count"].sum())
        total_series += len(stats)
        checksum += float(stats["mean"].sum())
    return total_cells, total_series, checksum


# ---- PySpark -------------------------------------------------------------------------------------
def run_spark_m4(files: list[Path], out_dir: Path, master: str = "local[4]") -> tuple[int, int, float]:
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F

    if out_dir.exists():
        shutil.rmtree(out_dir)
    spark = (
        SparkSession.builder.master(master)
        .appName("metronome-bigdata")
        .config("spark.driver.memory", "4g")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    total_cells, total_series, checksum = 0, 0, 0.0
    try:
        for f in files:
            wide = spark.read.option("header", True).csv(str(f))
            value_cols = [c for c in wide.columns if c != "V1"]
            stack_expr = ", ".join(f"'{c}', `{c}`" for c in value_cols)
            long = (
                wide.select("V1", F.expr(f"stack({len(value_cols)}, {stack_expr}) as (step, value)"))
                .where(F.col("value").isNotNull() & (F.col("value") != ""))
                .select(
                    F.col("V1").alias("series_id"),
                    (F.substring("step", 2, 10).cast("int") - 1).alias("step"),
                    F.col("value").cast("double").alias("value"),
                    F.lit(f.stem.split("-")[0]).alias("frequency"),
                )
            )
            part_dir = out_dir / f"frequency={f.stem.split('-')[0]}"
            long.write.mode("overwrite").option("compression", "zstd").parquet(str(part_dir))
            stats = (
                spark.read.parquet(str(part_dir))
                .groupBy("series_id")
                .agg(F.count("value").alias("n"), F.mean("value").alias("mean"))
            )
            agg = stats.agg(F.sum("n"), F.count("series_id"), F.sum("mean")).collect()[0]
            total_cells += int(agg[0])
            total_series += int(agg[1])
            checksum += float(agg[2])
    finally:
        spark.stop()
    return total_cells, total_series, checksum


def _dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def run_stage(
    raw_dir: Path,
    out_dir: Path,
    *,
    local_dir: Path | None = None,
    engines: tuple[str, ...] = ("polars", "pandas", "spark"),
    repeats: int = 3,
) -> dict[str, Any]:
    files = _m4_files(raw_dir, local_dir)
    source_bytes = sum(f.stat().st_size for f in files)
    runners = {"polars": run_polars_m4, "pandas": run_pandas_m4, "spark": run_spark_m4}
    results: list[EngineResult] = []
    for name in engines:
        runner = runners[name]
        seconds = []
        cells = series = 0
        checksum = 0.0
        target = out_dir / "parquet" / name
        for _ in range(repeats):
            t0 = time.perf_counter()
            cells, series, checksum = runner(files, target)
            seconds.append(time.perf_counter() - t0)
        results.append(
            EngineResult(
                name, "m4", seconds, statistics.median(seconds), cells, series, _dir_bytes(target), checksum
            )
        )
    ref = results[0]
    for r in results[1:]:
        if (
            r.n_cells != ref.n_cells
            or r.n_series != ref.n_series
            or abs(r.checksum - ref.checksum) > 1e-6 * max(1.0, abs(ref.checksum))
        ):
            raise RuntimeError(f"{r.engine} disagrees with {ref.engine}: {asdict(r)} vs {asdict(ref)}")
    report = {
        "source": {
            "name": "M4 train (6 frequencies)",
            "files": [f.name for f in files],
            "bytes": source_bytes,
        },
        "repeats": repeats,
        "cpu_count": os.cpu_count(),
        "machine": platform.machine(),
        "versions": {"polars": pl.__version__, "numpy": np.__version__},
        "engines": [asdict(r) for r in results],
        "agree": True,
    }
    try:
        import pandas

        report["versions"]["pandas"] = pandas.__version__
    except ImportError:
        pass
    if "spark" in engines:
        import pyspark

        report["versions"]["pyspark"] = pyspark.__version__
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bigdata.json").write_text(json.dumps(report, indent=2))
    return report
