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
