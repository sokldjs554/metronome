from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from metronome.report.build import build_all, judge_hypotheses, summarize_cadence, summarize_ltsf
from metronome.report.svg import Point, Series, line_chart, pareto_chart

ROOT = Path(__file__).resolve().parents[1]


def _fake_cadence(
    path: Path, cache: str, seed: int, never: float, daily: float, trig: float, n_trig: int
) -> None:
    days = 30
    pol = {
        "never": {
            "policy": "never",
            "mae": never,
            "mse": never**2,
            "n_refits": 0,
            "train_seconds": 0.0,
            "refit_days": [],
            "daily_mae": [never] * days,
        },
        "periodic-1": {
            "policy": "periodic-1",
            "mae": daily,
            "mse": daily**2,
            "n_refits": days - 1,
            "train_seconds": 100.0,
            "refit_days": list(range(1, days)),
            "daily_mae": [daily] * days,
        },
        "periodic-7": {
            "policy": "periodic-7",
            "mae": (never + daily) / 2,
            "mse": 0.1,
            "n_refits": 4,
            "train_seconds": 14.0,
            "refit_days": [7, 14, 21, 28],
            "daily_mae": [(never + daily) / 2] * days,
        },
        "ratio-0.2": {
            "policy": "ratio-0.2",
            "mae": trig,
            "mse": trig**2,
            "n_refits": n_trig,
            "train_seconds": 3.0 * n_trig,
            "refit_days": list(range(n_trig)),
            "daily_mae": [trig] * days,
        },
        "warm-1": {
            "policy": "warm-1",
            "mae": daily * 1.005,
            "mse": 0.1,
            "n_refits": days - 1,
            "train_seconds": 20.0,
            "refit_days": list(range(1, days)),
            "daily_mae": [daily] * days,
        },
    }
    comps = [
        {
            "policy": "periodic-1",
            "reference": "never",
            "diff": daily - never,
            "lo": daily - never - 0.01,
            "hi": daily - never + 0.01,
        },
        {
            "policy": "ratio-0.2",
            "reference": "never",
            "diff": trig - never,
            "lo": trig - never - 0.01,
            "hi": trig - never + 0.01,
        },
        {"policy": "ratio-0.2", "reference": "periodic-1", "diff": trig - daily, "lo": -0.02, "hi": 0.02},
    ]
    path.write_text(json.dumps({"cache": cache, "seed": seed, "policies": pol, "comparisons": comps}))


def test_summarize_cadence_and_hypotheses(tmp_path: Path) -> None:
    cad = tmp_path / "artifacts" / "cadence"
    cad.mkdir(parents=True)
    for seed in (0, 1):
        _fake_cadence(
            cad / f"etth1_dlinear_s{seed}.json", f"etth1_dlinear_s{seed}", seed, 0.50, 0.40, 0.42, 20
        )
        _fake_cadence(
            cad / f"etth1_dlinear_s{seed}_sliding.json",
            f"etth1_dlinear_s{seed}_sliding",
            seed,
            0.52,
            0.42,
            0.44,
            20,
        )
    summary = summarize_cadence(cad)
    e = summary["datasets"]["etth1"]["expanding"]["policies"]
    assert e["never"]["mae_mean"] == pytest.approx(0.50) and e["periodic-1"]["n_refits_mean"] == 29
    assert e["ratio-0.2"]["gain_fraction_of_daily"] == pytest.approx(0.8)
    assert e["periodic-1"]["ci_vs_never"]["all_seeds_hi_below_zero"]
    h = judge_hypotheses(summary)
    assert h["H1"]["pass"] and h["H2"]["pass"] and h["H2"]["rows"]["etth1"]["policy"] == "ratio-0.2"
    assert h["H3"]["rows"]["etth1"]["pass"] and h["H4"]["rows"]["etth1"]["pass"]


def test_summarize_ltsf_compares_with_paper(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    report = {
        "config": {"dataset": "etth1", "model": "dlinear", "lookback": 336, "horizon": 96, "seed": 2021},
        "metrics": {"mse": 0.380, "mae": 0.400},
        "fit": {"epochs": 5, "seconds": 6.0},
        "n_parameters": 100,
    }
    (runs / "etth1_dlinear_336_96_s2021.json").write_text(json.dumps(report))
    out = summarize_ltsf(runs, ROOT / "artifacts" / "paper_reference.json")
    row = out["runs"]["etth1.dlinear.96"]
    assert row["paper"]["mse"] == 0.375 and row["within_3pct"] and abs(row["mse_rel_diff_pct"] - 1.333) < 0.01


def test_build_all_writes_outputs(tmp_path: Path) -> None:
    (tmp_path / "artifacts" / "cadence").mkdir(parents=True)
    (tmp_path / "artifacts" / "runs").mkdir(parents=True)
    _fake_cadence(
        tmp_path / "artifacts" / "cadence" / "weather_dlinear_s0.json",
        "weather_dlinear_s0",
        0,
        0.3,
        0.25,
        0.26,
        10,
    )
    out = build_all(tmp_path)
    assert (tmp_path / "artifacts" / "cadence_summary.json").exists()
    assert (tmp_path / "src" / "metronome" / "static" / "evidence.json").exists()
    assert any("pareto_weather" in c for c in out["charts"]) and any(
        "daily_weather" in c for c in out["charts"]
    )


def test_svg_charts_render(tmp_path: Path) -> None:
    pts = [
        Point(0, 0.5, "never", "never"),
        Point(52, 0.45, "periodic-7", "periodic", 0.44, 0.46),
        Point(10, 0.47, "ratio-0.2", "ratio"),
    ]
    p = pareto_chart(pts, tmp_path / "p.svg", "t")
    assert p.read_text().startswith("<svg") and "ratio" in p.read_text()
    line = line_chart(
        [Series("a", [0, 1, 2], [0.1, 0.2, 0.15], "#000", marks=[1])], tmp_path / "l.svg", "t", "x", "y"
    )
    assert "<polyline" in line.read_text()


def test_check_numbers_script(tmp_path: Path) -> None:
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "s.json").write_text(
        json.dumps({"a": {"ratio-0.2": {"mae": 0.41234}}, "l": [1, 2.5]})
    )
    good = tmp_path / "good.md"
    good.write_text(
        "MAE <!-- num:artifacts/s.json#a/ratio-0.2/mae:.3f -->0.412<!-- /num --> and <!-- num:artifacts/s.json#l/1 -->2.5<!-- /num -->"
    )
    bad = tmp_path / "bad.md"
    bad.write_text("MAE <!-- num:artifacts/s.json#a/ratio-0.2/mae:.3f -->0.999<!-- /num -->")
    empty = tmp_path / "empty.md"
    empty.write_text("no numbers here")
    script = ROOT / "scripts" / "check_numbers.py"
    ok = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), str(good)], capture_output=True, text=True
    )
    assert ok.returncode == 0, ok.stdout
    fail = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), str(bad)], capture_output=True, text=True
    )
    assert fail.returncode == 1 and "0.999" in fail.stdout
    req = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), "--require-markers", str(empty)],
        capture_output=True,
        text=True,
    )
    assert req.returncode == 1 and "no numeric markers" in req.stdout


def test_mlflow_mirror(tmp_path: Path) -> None:
    pytest.importorskip("mlflow")
    from metronome.tracking.mlflow_log import log_cadence, log_ltsf_runs

    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "etth1_linear_336_96_s2021.json").write_text(
        json.dumps(
            {
                "config": {
                    "dataset": "etth1",
                    "model": "linear",
                    "lookback": 336,
                    "horizon": 96,
                    "seed": 2021,
                    "train": {"lr": 0.005, "batch_size": 32, "max_epochs": 2, "lr_schedule": "halving"},
                },
                "metrics": {"mse": 0.4, "mae": 0.41, "per_horizon_mse_at": {"1": 0.1}},
                "fit": {
                    "epochs": 2,
                    "seconds": 1.0,
                    "best_val": 0.3,
                    "history": [{"epoch": 1, "val": 0.35}, {"epoch": 2, "val": 0.3}],
                },
                "state_sha256": "abc",
                "dataset_content_sha256": "def",
                "n_parameters": 10,
            }
        )
    )
    cad = tmp_path / "cadence"
    cad.mkdir()
    _fake_cadence(cad / "etth1_dlinear_s0.json", "etth1_dlinear_s0", 0, 0.5, 0.4, 0.42, 5)
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    assert len(log_ltsf_runs(runs, uri)) == 1
    assert len(log_cadence(cad, uri)) == 6  # 5 policies + parent
