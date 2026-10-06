"""Pinned public dataset sources and the prepared-dataset specifications used by experiments.

Every raw file is identified by URL + SHA-256. A prepared dataset is a deterministic function of
one raw source (resampling, channel subset) and is what the experiments consume. Keeping both
tables in one module makes "which bytes did this number come from" answerable from code alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RawFormat = Literal["ett_csv", "darts_weather_csv", "darts_wide_csv", "laiguokun_txt_gz", "m4_csv"]


@dataclass(frozen=True)
class Source:
    key: str
    url: str
    sha256: str
    filename: str
    format: RawFormat
    freq: str | None
    description: str
    start: str | None = None  # ISO timestamp for sources without a time column


@dataclass(frozen=True)
class PreparedSpec:
    """How a raw source becomes an experiment dataset."""

    name: str
    source: str
    freq: str  # polars duration string of the prepared series ("1h")
    resample: str | None = None  # e.g. "1h" mean-resample from a finer raw frequency
    channels: tuple[int, ...] | None = None  # subset of raw channel indices (sorted), None = all
    stream_days: int = 365  # evaluation stream = last N days
    max_gap_fill: int = 0  # linearly interpolate runs of at most this many missing rows
    description: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)


_GH = "https://raw.githubusercontent.com"

SOURCES: dict[str, Source] = {
    "etth1": Source(
        key="etth1",
        url=f"{_GH}/zhouhaoyi/ETDataset/main/ETT-small/ETTh1.csv",
        sha256="f18de3ad269cef59bb07b5438d79bb3042d3be49bdeecf01c1cd6d29695ee066",
        filename="ETTh1.csv",
        format="ett_csv",
        freq="1h",
        description="Electricity Transformer Temperature, station 1, hourly, 7 channels (Zhou et al. 2021).",
    ),
    "etth2": Source(
        key="etth2",
        url=f"{_GH}/zhouhaoyi/ETDataset/main/ETT-small/ETTh2.csv",
        sha256="a3dc2c597b9218c7ce1cd55eb77b283fd459a1d09d753063f944967dd6b9218b",
        filename="ETTh2.csv",
        format="ett_csv",
        freq="1h",
        description="Electricity Transformer Temperature, station 2, hourly, 7 channels.",
    ),
    "ettm1": Source(
        key="ettm1",
        url=f"{_GH}/zhouhaoyi/ETDataset/main/ETT-small/ETTm1.csv",
        sha256="6ce1759b1a18e3328421d5d75fadcb316c449fcd7cec32820c8dafda71986c9e",
        filename="ETTm1.csv",
        format="ett_csv",
        freq="15m",
        description="ETT station 1, 15-minute.",
    ),
    "ettm2": Source(
        key="ettm2",
        url=f"{_GH}/zhouhaoyi/ETDataset/main/ETT-small/ETTm2.csv",
        sha256="db973ca252c6410a30d0469b13d696cf919648d0f3fd588c60f03fdbdbadd1fd",
        filename="ETTm2.csv",
        format="ett_csv",
        freq="15m",
        description="ETT station 2, 15-minute.",
    ),
    "weather": Source(
        key="weather",
        url=f"{_GH}/unit8co/darts/master/datasets/weather.csv",
        sha256="e5187654cfcc5b6358bb916170a1f7ce29dffe388b6ad0a003e9ab56693523d0",
        filename="weather.csv",
        format="darts_weather_csv",
        freq="10m",
        description="Max Planck Institute Jena weather station, 2020, 10-minute, 21 variables (darts mirror).",
    ),
    "traffic": Source(
        key="traffic",
        url=f"{_GH}/unit8co/darts/master/datasets/traffic.csv",
        sha256="9fbdd16bc504f396a7fe154f26677f1137681987459092f6d7e141ac4f3b59c0",
        filename="traffic.csv",
        format="darts_wide_csv",
        freq="1h",
        description="California PeMS road occupancy, 862 sensors, hourly, 2015-2016 (darts mirror).",
    ),
    "electricity": Source(
        key="electricity",
        url=f"{_GH}/laiguokun/multivariate-time-series-data/master/electricity/electricity.txt.gz",
        sha256="3c4c069588198c1fcc95cace7bb69c99922129edfd673b7286661dad20badefa",
        filename="electricity.txt.gz",
        format="laiguokun_txt_gz",
        freq="1h",
        start="2012-01-01T00:00:00",
        description="UCI ElectricityLoadDiagrams aggregated to hourly kWh for 321 clients, 2012-2014 (Lai et al. 2018 mirror).",
    ),
}

_M4_SHA = {
    "Hourly-train": "ea59b7783573c49077a835ab6465c7d66f1474783360f310988a9a737fbca62f",
    "Hourly-test": "71a57fccb15e534d973626ada4fb87febf789e9317715b7cc6dd3b5f90db6f42",
    "Daily-train": "78e94591c60c06309f1e544fd7b2ccba28f3616b01913dd336a1d1d98483a1ec",
    "Daily-test": "633b0815626ae266d36872c4d53e95eb93ee8d43e79587fceec519eba3e6b05e",
    "Weekly-train": "d478d3f6ed673e6ed3c2cb0fbed5425f72eedd51318ebebeb0b5ecfcefc37714",
    "Weekly-test": "3b2bc4be8e636e802260dcd843ca3c5da40536a1fbe1ecb3229a97dae4f44688",
    "Monthly-train": "63aaa56198b4a22279a2fec541f56921f3bed6d8e0f84e550206df9276f2e9b9",
    "Monthly-test": "5e3538bf23b4a09f4078180c3e2b34859f0382e1c4f22564affc1797e8f3f48f",
    "Quarterly-train": "4450678cd493aa965c14bde984a5b62a66d8c3b2f7af1e53779bc91ff008ccdc",
    "Quarterly-test": "bf1cab3b969a744c220cdc148e3829803eaa5da2754270fc4f376e775cd7d0ae",
    "Yearly-train": "6aa668d4f04654c0bf5f07b266a51c556f0df2faf4709f852653755396a249e4",
    "Yearly-test": "6dc2dd45b3af320389e2d3735cb4b3cdf320b63cbcda15d1a17193ab99702306",
}
for _part, _sha in _M4_SHA.items():
    _split = "Train" if _part.endswith("train") else "Test"
    SOURCES[f"m4_{_part.lower().replace('-', '_')}"] = Source(
        key=f"m4_{_part.lower().replace('-', '_')}",
        url=f"{_GH}/Mcompetitions/M4-methods/master/Dataset/{_split}/{_part}.csv",
        sha256=_sha,
        filename=f"M4-{_part}.csv",
        format="m4_csv",
        freq=None,
        description=f"M4 competition {_part} (Makridakis et al. 2018), wide CSV, one series per row.",
    )
SOURCES["m4_info"] = Source(
    key="m4_info",
    url=f"{_GH}/Mcompetitions/M4-methods/master/Dataset/M4-info.csv",
    sha256="26a75cc9b9f65e351b39b0bdbb7e3464ac837df0baf541ab55abdd2ba1a14c88",
    filename="M4-info.csv",
    format="m4_csv",
    freq=None,
    description="M4 series metadata (category, frequency, horizon, start date).",
)

# Pre-registered (docs/protocol.md P2). The electricity subset is
# sorted(numpy.random.default_rng(2026).choice(321, 20, replace=False)).
ELECTRICITY20_CHANNELS: tuple[int, ...] = (
    8,
    24,
    31,
    54,
    56,
    95,
    110,
    111,
    114,
    143,
    195,
    199,
    208,
    221,
    227,
    247,
    257,
    259,
    272,
    285,
)

PREPARED: dict[str, PreparedSpec] = {
    "etth1": PreparedSpec(
        name="etth1",
        source="etth1",
        freq="1h",
        stream_days=365,
        description="ETTh1, 7 channels, hourly; stream = last 365 days.",
    ),
    "etth2": PreparedSpec(
        name="etth2",
        source="etth2",
        freq="1h",
        stream_days=365,
        description="ETTh2, 7 channels, hourly; stream = last 365 days.",
    ),
    "weather": PreparedSpec(
        name="weather",
        source="weather",
        freq="1h",
        resample="1h",
        stream_days=180,
        max_gap_fill=1,
        description="Jena 2020 weather, 21 channels, 10-min mean-resampled to hourly; stream = last 180 days.",
        notes=(
            "10-minute readings are averaged into the hour they fall in (floor).",
            "One hour (2020-05-29 10:00) is missing in the source and is linearly interpolated (protocol change log).",
        ),
    ),
    "electricity20": PreparedSpec(
        name="electricity20",
        source="electricity",
        freq="1h",
        channels=ELECTRICITY20_CHANNELS,
        stream_days=365,
        description="20 of 321 electricity clients, hourly; stream = last 365 days.",
        notes=("Channel subset fixed before any experiment ran (protocol P2).",),
    ),
    # Full-width datasets used by the large-data stage and the LTSF leaderboard, not by cadence.
    "electricity": PreparedSpec(
        name="electricity",
        source="electricity",
        freq="1h",
        stream_days=365,
        description="All 321 electricity clients, hourly.",
    ),
    "traffic": PreparedSpec(
        name="traffic",
        source="traffic",
        freq="1h",
        stream_days=365,
        description="862 PeMS sensors, hourly.",
    ),
}
