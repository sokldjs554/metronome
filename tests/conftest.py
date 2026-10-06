from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from metronome.data.pipeline import prepare_frame
from metronome.data.schema import TIMESTAMP
from metronome.data.sources import PreparedSpec


def synthetic_frame(
    n_rows: int = 24 * 70,
    n_channels: int = 3,
    freq_minutes: int = 60,
    seed: int = 0,
    start: datetime = datetime(2021, 1, 1),
    drift_at: int | None = None,
) -> pl.DataFrame:
    """Daily + weekly sinusoids with noise; optional level shift at row `drift_at`."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_rows)
    stamps = [start + timedelta(minutes=freq_minutes * i) for i in range(n_rows)]
    cols = {TIMESTAMP: stamps}
    for c in range(n_channels):
        daily = np.sin(2 * np.pi * t / 24 + c)
        weekly = 0.5 * np.sin(2 * np.pi * t / (24 * 7) + 2 * c)
        series = 10 * (c + 1) + 3 * daily + weekly + rng.normal(0, 0.3, n_rows)
        if drift_at is not None:
            series[drift_at:] += 5.0
        cols[f"ch{c}"] = series
    return pl.DataFrame(cols).with_columns(pl.col(TIMESTAMP).cast(pl.Datetime("ns")))


@pytest.fixture
def frame() -> pl.DataFrame:
    return synthetic_frame()


@pytest.fixture
def processed(tmp_path: Path) -> tuple[str, Path]:
    """A prepared synthetic dataset on disk: 70 days hourly, 3 channels, stream = last 20 days."""
    spec = PreparedSpec(name="synth", source="synthetic", freq="1h", stream_days=20)
    prepare_frame(synthetic_frame(), spec, tmp_path / "processed", source_info={"key": "synthetic"})
    return "synth", tmp_path / "processed"
