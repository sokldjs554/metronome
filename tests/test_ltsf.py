from __future__ import annotations

import json
from pathlib import Path

from metronome.eval.ltsf import LTSFConfig, run_ltsf
from metronome.train.trainer import TrainConfig


def test_run_ltsf_other_split_writes_report(processed: tuple[str, Path], tmp_path: Path) -> None:
    name, processed_dir = processed
    cfg = LTSFConfig(
        dataset=name,
        kind="other",
        model="linear",
        lookback=48,
        horizon=12,
        seed=1,
        train=TrainConfig(max_epochs=2, batch_size=32, threads=1),
    )
    report = run_ltsf(cfg, processed_dir, tmp_path / "out")
    assert (tmp_path / "out" / f"{cfg.name}.json").exists() and (tmp_path / "out" / f"{cfg.name}.pt").exists()
    assert report["metrics"]["mse"] > 0 and report["fit"]["epochs"] == 2
    n = report["n_windows"]
    assert n["train"] > n["val"] and n["test"] > 0
    loaded = json.loads((tmp_path / "out" / f"{cfg.name}.json").read_text())
    assert loaded["state_sha256"] == report["state_sha256"]


def test_run_ltsf_naive_needs_no_training(processed: tuple[str, Path], tmp_path: Path) -> None:
    name, processed_dir = processed
    cfg = LTSFConfig(dataset=name, kind="other", model="seasonal_naive", lookback=48, horizon=12)
    report = run_ltsf(cfg, processed_dir, tmp_path / "out")
    assert report["fit"] is None and report["n_parameters"] == 0
