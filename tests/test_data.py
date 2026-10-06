from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from tests.conftest import synthetic_frame

from metronome.data import fetch as fetch_mod
from metronome.data.pipeline import load_prepared, prepare_frame, resample_mean, select_channels
from metronome.data.schema import TIMESTAMP, SchemaError, parse_duration, validate_frame
from metronome.data.sources import ELECTRICITY20_CHANNELS, PREPARED, SOURCES, PreparedSpec, Source
from metronome.data.splits import ltsf_borders, stream_split
from metronome.data.windows import Scaler, make_windows, window_count


def test_validate_ok(frame: pl.DataFrame) -> None:
    report = validate_frame(frame, "1h")
    assert report.ok and report.n_rows == frame.height and report.n_channels == 3
    assert report.gaps == 0 and report.duplicates == 0 and report.nan_cells == 0


def test_validate_rejects_duplicates(frame: pl.DataFrame) -> None:
    dup = pl.concat([frame, frame.tail(1)]).sort(TIMESTAMP)
    with pytest.raises(SchemaError, match="duplicated"):
        validate_frame(dup, "1h")


def test_validate_rejects_gaps(frame: pl.DataFrame) -> None:
    gapped = pl.concat([frame.head(100), frame.tail(frame.height - 103)])
    with pytest.raises(SchemaError, match="gaps"):
        validate_frame(gapped, "1h")
    report = validate_frame(gapped, "1h", strict=False)
    assert report.gaps == 1 and not report.ok


def test_validate_rejects_nan(frame: pl.DataFrame) -> None:
    bad = frame.with_columns(
        pl.when(pl.arange(0, frame.height) == 5).then(None).otherwise(pl.col("ch0")).alias("ch0")
    )
    with pytest.raises(SchemaError, match="NaN"):
        validate_frame(bad, "1h")


def test_validate_rejects_backwards_time(frame: pl.DataFrame) -> None:
    rows = frame.to_dicts()
    rows[10], rows[11] = rows[11], rows[10]
    bad = pl.DataFrame(rows).with_columns(pl.col(TIMESTAMP).cast(pl.Datetime("ns")))
    with pytest.raises(SchemaError):
        validate_frame(bad, "1h")


def test_validate_flags_constant_channel(frame: pl.DataFrame) -> None:
    const = frame.with_columns(pl.lit(1.0).alias("ch1"))
    report = validate_frame(const, "1h")
    assert report.constant_channels == ["ch1"]


def test_parse_duration() -> None:
    assert parse_duration("10m").total_seconds() == 600
    assert parse_duration("1h").total_seconds() == 3600
    with pytest.raises(SchemaError):
        parse_duration("1x")


def test_resample_mean_bins_by_floor() -> None:
    df = synthetic_frame(n_rows=12 * 6, n_channels=1, freq_minutes=10)
    hourly = resample_mean(df, "1h")
    assert hourly.height == 12
    first = df.head(6)["ch0"].mean()
    assert hourly["ch0"][0] == pytest.approx(first)
    assert hourly[TIMESTAMP][0] == datetime(2021, 1, 1, 0, 0)


def test_select_channels_by_index(frame: pl.DataFrame) -> None:
    out = select_channels(frame, (2, 0))
    assert out.columns == [TIMESTAMP, "ch2", "ch0"]


def test_make_windows_views(frame: pl.DataFrame) -> None:
    values = frame.drop(TIMESTAMP).to_numpy().astype(np.float32)
    x, y = make_windows(values, 48, 12)
    assert x.shape == (window_count(len(values), 48, 12), 48, 3) and y.shape[1:] == (12, 3)
    np.testing.assert_array_equal(x[5], values[5:53])
    np.testing.assert_array_equal(y[5], values[53:65])
    with pytest.raises(ValueError):
        make_windows(values[:10], 48, 12)


def test_scaler_roundtrip_and_constant_channel() -> None:
    v = np.random.default_rng(0).normal(size=(100, 2)).astype(np.float32)
    v[:, 1] = 7.0
    s = Scaler.fit(v)
    z = s.transform(v)
    assert abs(z[:, 0].mean()) < 1e-5 and abs(z[:, 0].std() - 1) < 1e-4
    assert np.allclose(z[:, 1], 0.0) and s.std[1] == 1.0
    np.testing.assert_allclose(s.inverse(z), v, atol=1e-5)
    assert Scaler.from_dict(s.to_dict()).mean.tolist() == s.mean.tolist()


def test_stream_split_days(frame: pl.DataFrame) -> None:
    ts = frame[TIMESTAMP].to_numpy()
    split = stream_split(ts, 20)
    assert split.n_days == 20 and split.stream_start == frame.height - 20 * 24
    assert split.day_slice(0) == slice(split.stream_start, split.stream_start + 24)
    assert split.day_slice(19).stop == frame.height
    with pytest.raises(ValueError):
        stream_split(ts, 70)


def test_ltsf_borders_etth() -> None:
    b1, b2 = ltsf_borders(17420, 336, "etth")
    assert b1 == [0, 8640 - 336, 11520 - 336] and b2 == [8640, 11520, 14400]
    with pytest.raises(ValueError):
        ltsf_borders(1000, 336, "etth")
    b1, b2 = ltsf_borders(1000, 10, "other")
    assert b2[-1] == 1000 and b1[1] == 700 - 10


def test_prepare_frame_writes_manifest(tmp_path: Path, frame: pl.DataFrame) -> None:
    spec = PreparedSpec(name="t", source="synthetic", freq="1h", channels=(1,), stream_days=5)
    out, manifest = prepare_frame(frame, spec, tmp_path, source_info={"key": "synthetic"})
    assert out.exists() and manifest["validation"]["ok"] and manifest["validation"]["channels"] == ["ch1"]
    _ts, values, channels, loaded = load_prepared("t", tmp_path)
    assert (
        values.shape == (frame.height, 1)
        and channels == ["ch1"]
        and loaded["content_sha256"] == manifest["content_sha256"]
    )


def test_fetch_verifies_checksum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"a,b\n1,2\n"
    local = tmp_path / "local"
    local.mkdir()
    (local / "tiny.csv").write_bytes(payload)
    good = Source(
        "tiny",
        "https://example.invalid/tiny.csv",
        hashlib.sha256(payload).hexdigest(),
        "tiny.csv",
        "ett_csv",
        "1h",
        "",
    )
    monkeypatch.setitem(SOURCES, "tiny", good)
    path = fetch_mod.fetch("tiny", tmp_path / "raw", local)
    assert path.read_bytes() == payload
    bad = Source("tiny", good.url, "0" * 64, "tiny.csv", "ett_csv", "1h", "")
    monkeypatch.setitem(SOURCES, "tiny", bad)
    with pytest.raises(fetch_mod.ChecksumMismatch):
        fetch_mod.fetch("tiny", tmp_path / "raw2", local)
    assert not (tmp_path / "raw2" / "tiny.csv").exists()


def test_sources_are_pinned() -> None:
    for key, src in SOURCES.items():
        assert len(src.sha256) == 64 and src.url.startswith("https://"), key
    assert tuple(sorted(np.random.default_rng(2026).choice(321, 20, replace=False))) == ELECTRICITY20_CHANNELS
    assert PREPARED["electricity20"].channels == ELECTRICITY20_CHANNELS
