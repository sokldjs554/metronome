"""Raw file -> validated, regularly spaced Parquet with a sidecar manifest.

Each prepared dataset records the raw SHA-256 it came from, the transformation applied, and the
validation report. Downstream stages read only the Parquet + manifest, never the raw file.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import itertools
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from metronome.data.fetch import fetch, sha256_of
from metronome.data.schema import TIMESTAMP, ValidationReport, parse_duration, validate_frame
from metronome.data.sources import PREPARED, SOURCES, PreparedSpec, Source


def load_raw(source: Source, path: Path) -> pl.DataFrame:
    """Parse a raw file into (timestamp, ch_0..ch_n) with float64 channels."""
    if source.format == "ett_csv":
        df = pl.read_csv(path, try_parse_dates=False)
        df = df.rename({"date": TIMESTAMP}).with_columns(
            pl.col(TIMESTAMP).str.strptime(pl.Datetime("ns"), "%Y-%m-%d %H:%M:%S")
        )
    elif source.format == "darts_weather_csv":
        df = pl.read_csv(path, try_parse_dates=False)
        df = df.rename({"Date Time": TIMESTAMP}).with_columns(
            pl.col(TIMESTAMP).str.strptime(pl.Datetime("ns"), "%d.%m.%Y %H:%M:%S")
        )
    elif source.format == "darts_wide_csv":
        df = pl.read_csv(path, try_parse_dates=False)
        df = df.rename({"Date": TIMESTAMP}).with_columns(
            pl.col(TIMESTAMP).str.strptime(pl.Datetime("ns"), "%Y-%m-%d %H:%M:%S")
        )
    elif source.format == "laiguokun_txt_gz":
        with gzip.open(path, "rb") as fh:
            raw = fh.read()
        values = pl.read_csv(io.BytesIO(raw), has_header=False)
        assert source.start is not None and source.freq is not None
        start = datetime.fromisoformat(source.start)
        step = parse_duration(source.freq)
        stamps = [start + i * step for i in range(values.height)]
        df = pl.DataFrame({TIMESTAMP: stamps}).with_columns(pl.col(TIMESTAMP).cast(pl.Datetime("ns")))
        df = pl.concat([df, values], how="horizontal")
    else:
        raise ValueError(f"{source.format} is not a time-series source")
    channels = [c for c in df.columns if c != TIMESTAMP]
    return df.with_columns([pl.col(c).cast(pl.Float64) for c in channels]).sort(TIMESTAMP)


def resample_mean(df: pl.DataFrame, every: str) -> pl.DataFrame:
    """Average every channel into regular bins of `every` (bin label = floor of the timestamp)."""
    channels = [c for c in df.columns if c != TIMESTAMP]
    return (
        df.with_columns(pl.col(TIMESTAMP).dt.truncate(every))
        .group_by(TIMESTAMP, maintain_order=True)
        .agg([pl.col(c).mean() for c in channels])
        .sort(TIMESTAMP)
    )


def fill_gaps(df: pl.DataFrame, freq: str, max_gap: int) -> tuple[pl.DataFrame, int]:
    """Insert missing timestamps on the regular grid and linearly interpolate runs of at most
    `max_gap` consecutive missing rows. Longer runs are left as NaN (and fail validation).

    Returns the completed frame and the number of rows that were filled.
    """
    if max_gap <= 0 or df.height < 2:
        return df, 0
    channels = [c for c in df.columns if c != TIMESTAMP]
    grid = pl.datetime_range(df[TIMESTAMP][0], df[TIMESTAMP][-1], interval=freq, eager=True, time_unit="ns")
    full = pl.DataFrame({TIMESTAMP: grid}).join(df, on=TIMESTAMP, how="left").sort(TIMESTAMP)
    missing = full[channels[0]].is_null().to_numpy()
    if not missing.any():
        return full, 0
    # Runs of missing rows longer than max_gap stay NaN so validation reports them.
    allowed = np.ones(full.height, dtype=bool)
    edges = np.flatnonzero(np.r_[True, missing[1:] != missing[:-1], True])
    for start, end in itertools.pairwise(edges):
        if missing[start] and (end - start) > max_gap:
            allowed[start:end] = False
    filled = full.with_columns([pl.col(c).interpolate() for c in channels])
    if not allowed.all():
        filled = filled.with_columns(pl.Series("_keep", allowed))
        filled = filled.with_columns(
            [pl.when(pl.col("_keep")).then(pl.col(c)).otherwise(None).alias(c) for c in channels]
        ).drop("_keep")
    return filled, int((missing & allowed).sum())


def select_channels(df: pl.DataFrame, channels: tuple[int, ...] | None) -> pl.DataFrame:
    if channels is None:
        return df
    names = [c for c in df.columns if c != TIMESTAMP]
    picked = [names[i] for i in channels]
    return df.select([TIMESTAMP, *picked])


def content_hash(df: pl.DataFrame) -> str:
    """Content hash of a prepared frame (timestamps + values), independent of file encoding."""
    h = hashlib.sha256()
    h.update(df[TIMESTAMP].to_numpy().astype("datetime64[ns]").tobytes())
    h.update(np.ascontiguousarray(df.drop(TIMESTAMP).to_numpy().astype(np.float64)).tobytes())
    return h.hexdigest()


def prepare_frame(
    df: pl.DataFrame,
    spec: PreparedSpec,
    processed_dir: Path,
    *,
    source_info: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Apply the spec's transformations to an already-loaded raw frame, validate, and persist."""
    if spec.resample:
        df = resample_mean(df, spec.resample)
    df, filled_rows = fill_gaps(df, spec.freq, spec.max_gap_fill)
    df = select_channels(df, spec.channels)
    report: ValidationReport = validate_frame(df, spec.freq)
    processed_dir.mkdir(parents=True, exist_ok=True)
    out = processed_dir / f"{spec.name}.parquet"
    df.write_parquet(out, compression="zstd")
    manifest = {
        "name": spec.name,
        "spec": asdict(spec),
        "source": source_info or {},
        "content_sha256": content_hash(df),
        "parquet_sha256": sha256_of(out),
        "filled_rows": filled_rows,
        "validation": report.to_dict(),
    }
    (processed_dir / f"{spec.name}.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return out, manifest


def prepare(
    name: str,
    raw_dir: Path,
    processed_dir: Path,
    *,
    local_dir: Path | None = None,
    spec: PreparedSpec | None = None,
) -> tuple[Path, dict[str, Any]]:
    spec = spec or PREPARED[name]
    source = SOURCES[spec.source]
    raw_path = fetch(spec.source, raw_dir, local_dir)
    df = load_raw(source, raw_path)
    info = {"key": source.key, "url": source.url, "sha256": source.sha256, "file_sha256": sha256_of(raw_path)}
    return prepare_frame(df, spec, processed_dir, source_info=info)


def load_prepared(name: str, processed_dir: Path) -> tuple[np.ndarray, np.ndarray, list[str], dict[str, Any]]:
    """Return (timestamps[datetime64[ns]], values[float32, T x C], channel names, manifest)."""
    manifest = json.loads((processed_dir / f"{name}.json").read_text())
    df = pl.read_parquet(processed_dir / f"{name}.parquet")
    channels = [c for c in df.columns if c != TIMESTAMP]
    ts = df[TIMESTAMP].to_numpy().astype("datetime64[ns]")
    values = df.select(channels).to_numpy().astype(np.float32)
    return ts, values, channels, manifest
