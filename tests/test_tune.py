from __future__ import annotations

import json
from pathlib import Path

import pytest

optuna = pytest.importorskip("optuna")


def test_search_selects_on_validation_and_looks_at_test_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end on a small synthetic series: trials record validation metrics only, the selected
    configuration is the lowest validation MSE, and only the final paired comparison carries test metrics."""
    from tests.conftest import synthetic_frame

    import metronome.tune.search as search
    from metronome.data.pipeline import prepare_frame
    from metronome.data.sources import PreparedSpec

    spec = PreparedSpec(name="synth", source="synthetic", freq="1h", stream_days=20)
    prepare_frame(synthetic_frame(n_rows=24 * 60), spec, tmp_path / "processed", source_info={})
    monkeypatch.setattr(search, "LOOKBACKS", (24, 48))
    monkeypatch.setattr(search, "PAPER", {**search.PAPER, "lookback": 48})
    monkeypatch.setattr(search, "TEST_SEEDS", (0, 1))
    report = search.run_search(
        "synth",
        kind="other",
        horizon=12,
        n_trials=3,
        processed_dir=tmp_path / "processed",
        out_dir=tmp_path / "tune",
        log=lambda _msg: None,
    )
    assert len(report["trials"]) == 3
    assert all("test_mse" not in t for t in report["trials"])  # the search never sees the test split
    best = min(report["trials"], key=lambda t: t["val_mse"])
    assert report["selected_params"] == best["params"]
    assert [r["seed"] for r in report["final"]["selected"]] == [0, 1]
    assert all("test_mse" in r for runs in report["final"].values() for r in runs)
    s = report["summary"]
    assert set(s["by_seed"]) == {"0", "1"} and 0 <= s["n_seeds_better"] <= 2
    saved = json.loads((tmp_path / "tune" / "synth_h12.json").read_text())
    assert saved["summary"]["mse_improvement_pct"] == pytest.approx(s["mse_improvement_pct"])
