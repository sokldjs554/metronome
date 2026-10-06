from __future__ import annotations

import polars as pl
import pytest
from tests.conftest import synthetic_frame

from metronome.data.pipeline import fill_gaps, prepare_frame
from metronome.data.schema import TIMESTAMP, SchemaError
from metronome.data.sources import PreparedSpec


def _drop_rows(df: pl.DataFrame, rows: list[int]) -> pl.DataFrame:
    return df.with_row_index("i").filter(~pl.col("i").is_in(rows)).drop("i")


def test_fill_gaps_interpolates_short_runs_only() -> None:
    df = synthetic_frame(n_rows=48, n_channels=2)
    gapped = _drop_rows(df, [10, 20, 21, 22])  # one 1-row gap and one 3-row gap
    filled, n = fill_gaps(gapped, "1h", max_gap=1)
    assert filled.height == 48 and n == 1
    assert filled["ch0"][10] == pytest.approx((df["ch0"][9] + df["ch0"][11]) / 2)
    assert filled["ch0"][20] is None and filled["ch0"][22] is None
    assert filled["ch0"][23] == pytest.approx(df["ch0"][23])


def test_fill_gaps_noop_when_disabled_or_complete() -> None:
    df = synthetic_frame(n_rows=30, n_channels=1)
    out, n = fill_gaps(df, "1h", max_gap=0)
    assert n == 0 and out.height == 30
    out, n = fill_gaps(_drop_rows(df, [5]), "1h", max_gap=0)
    assert n == 0 and out.height == 29
    out, n = fill_gaps(df, "1h", max_gap=3)
    assert n == 0 and out.height == 30


def test_prepare_frame_records_filled_rows_and_rejects_long_gaps(tmp_path) -> None:
    df = _drop_rows(synthetic_frame(n_rows=24 * 10, n_channels=1), [50])
    spec = PreparedSpec(name="g", source="synthetic", freq="1h", stream_days=2, max_gap_fill=1)
    _, manifest = prepare_frame(df, spec, tmp_path, source_info={})
    assert manifest["filled_rows"] == 1 and manifest["validation"]["ok"]
    strict = PreparedSpec(name="g2", source="synthetic", freq="1h", stream_days=2, max_gap_fill=0)
    with pytest.raises(SchemaError, match="gaps"):
        prepare_frame(df, strict, tmp_path, source_info={})
    long_gap = _drop_rows(synthetic_frame(n_rows=24 * 10, n_channels=1), [50, 51, 52])
    with pytest.raises(SchemaError, match="NaN"):
        prepare_frame(long_gap, spec, tmp_path, source_info={})
    assert TIMESTAMP in df.columns
