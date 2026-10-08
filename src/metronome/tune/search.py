"""Pre-registered model improvement search (docs/protocol.md P14).

Validation MSE is the only thing the search sees. The chosen configuration and the paper recipe are then
trained on seeds the search never used and the test split is evaluated once, paired by seed.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from metronome.data.pipeline import load_prepared
from metronome.data.splits import ltsf_borders
from metronome.data.windows import Scaler, make_windows
from metronome.eval.ltsf import dlinear_recipe
from metronome.eval.metrics import mae, mse
from metronome.models import build
from metronome.train.trainer import fit, predict, seed_everything

LOOKBACKS = (96, 192, 336, 512, 720)
KERNELS = (13, 25, 49)
NORMS = ("none", "last", "revin")
BATCHES = (16, 32, 64)
PAPER = {
    "lookback": 336,
    "kernel_size": 25,
    "norm": "none",
    "individual": False,
    "loss": "mse",
    "lr": 0.005,
    "batch_size": 32,
}
SEARCH_SEED = 2021  # training seed during the search (P10's seed)
TEST_SEEDS = (0, 1, 2)  # seeds the search never saw


class Splits:
    """Train/val/test windows per lookback, built once per process (the data never changes)."""

    def __init__(self, dataset: str, kind: str, horizon: int, processed_dir: Path) -> None:
        self.dataset, self.kind, self.horizon = dataset, kind, horizon
        _ts, self.values, self.channels, self.manifest = load_prepared(dataset, processed_dir)
        self._cache: dict[int, tuple[tuple[np.ndarray, np.ndarray], ...]] = {}

    def get(self, lookback: int) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
        if lookback not in self._cache:
            b1, b2 = ltsf_borders(len(self.values), lookback, self.kind)
            scaler = Scaler.fit(self.values[b1[0] : b2[0]])
            z = scaler.transform(self.values)
            self._cache[lookback] = tuple(
                make_windows(z[b1[i] : b2[i]], lookback, self.horizon) for i in range(3)
            )
        return self._cache[lookback]


def train_eval(
    splits: Splits, params: dict[str, Any], seed: int, *, test: bool, threads: int = 1
) -> dict[str, Any]:
    """Train one configuration; return validation metrics, and test metrics only when asked."""
    (x_tr, y_tr), (x_va, y_va), (x_te, y_te) = splits.get(int(params["lookback"]))
    cfg = replace(
        dlinear_recipe(threads),
        lr=float(params["lr"]),
        batch_size=int(params["batch_size"]),
        loss=params["loss"],
    )
    seed_everything(seed)
    model = build(
        "dlinear",
        int(params["lookback"]),
        splits.horizon,
        len(splits.channels),
        kernel_size=int(params["kernel_size"]),
        individual=bool(params["individual"]),
        norm=str(params["norm"]),
    )
    started = time.perf_counter()
    info = fit(model, x_tr, y_tr, x_va, y_va, cfg, seed)
    pred_va = predict(model, x_va, cfg.eval_batch_size)
    out: dict[str, Any] = {
        "params": dict(params),
        "seed": seed,
        "val_mse": mse(pred_va, y_va),
        "val_mae": mae(pred_va, y_va),
        "epochs": info.epochs,
        "best_epoch": info.best_epoch,
        "seconds": time.perf_counter() - started,
    }
    if test:
        pred_te = predict(model, x_te, cfg.eval_batch_size)
        out["test_mse"] = mse(pred_te, y_te)
        out["test_mae"] = mae(pred_te, y_te)
        out["n_test_windows"] = len(x_te)
    return out


def suggest(trial: Any) -> dict[str, Any]:
    return {
        "lookback": trial.suggest_categorical("lookback", list(LOOKBACKS)),
        "kernel_size": trial.suggest_categorical("kernel_size", list(KERNELS)),
        "norm": trial.suggest_categorical("norm", list(NORMS)),
        "individual": trial.suggest_categorical("individual", [False, True]),
        "loss": trial.suggest_categorical("loss", ["mse", "mae"]),
        "lr": trial.suggest_float("lr", 1e-4, 1e-2, log=True),
        "batch_size": trial.suggest_categorical("batch_size", list(BATCHES)),
    }


def run_search(
    dataset: str,
    *,
    kind: str = "etth",
    horizon: int = 96,
    n_trials: int = 40,
    processed_dir: Path = Path("data/processed"),
    out_dir: Path = Path("artifacts/tune"),
    threads: int = 1,
    mlflow_uri: str | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    splits = Splits(dataset, kind, horizon, processed_dir)
    tracker = _Tracker(mlflow_uri, f"metronome-tune-{dataset}")
    trials: list[dict[str, Any]] = []

    def objective(trial: Any) -> float:
        params = suggest(trial)
        res = train_eval(splits, params, SEARCH_SEED, test=False, threads=threads)
        res["trial"] = trial.number
        trials.append(res)
        tracker.log(
            f"trial-{trial.number:03d}", params, {"val_mse": res["val_mse"], "val_mae": res["val_mae"]}
        )
        log(f"[{dataset}] trial {trial.number:02d} val_mse={res['val_mse']:.4f} {params}")
        return float(res["val_mse"])

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=0))
    study.optimize(objective, n_trials=n_trials)
    best = min(trials, key=lambda r: r["val_mse"])
    paper_val = train_eval(splits, PAPER, SEARCH_SEED, test=False, threads=threads)
    tracker.log("paper-recipe", PAPER, {"val_mse": paper_val["val_mse"], "val_mae": paper_val["val_mae"]})

    # The only look at the test split: chosen configuration vs the paper recipe on unseen seeds.
    final = {
        name: [train_eval(splits, params, s, test=True, threads=threads) for s in TEST_SEEDS]
        for name, params in (("selected", best["params"]), ("paper", PAPER))
    }
    report = {
        "dataset": dataset,
        "kind": kind,
        "horizon": horizon,
        "n_trials": n_trials,
        "search_seed": SEARCH_SEED,
        "test_seeds": list(TEST_SEEDS),
        "dataset_content_sha256": splits.manifest["content_sha256"],
        "trials": trials,
        "best_trial": best["trial"],
        "selected_params": best["params"],
        "paper_params": PAPER,
        "val": {"selected": best["val_mse"], "paper": paper_val["val_mse"]},
        "final": final,
        "summary": summarize(final),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{dataset}_h{horizon}.json").write_text(json.dumps(report, indent=1))
    return report


def summarize(final: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    sel, pap = final["selected"], final["paper"]
    by_seed = {
        str(a["seed"]): {
            "selected_mse": a["test_mse"],
            "paper_mse": b["test_mse"],
            "mse_change_pct": (b["test_mse"] - a["test_mse"]) / b["test_mse"] * 100,
            "selected_mae": a["test_mae"],
            "paper_mae": b["test_mae"],
        }
        for a, b in zip(sel, pap, strict=True)
    }
    sel_mse = float(np.mean([r["test_mse"] for r in sel]))
    pap_mse = float(np.mean([r["test_mse"] for r in pap]))
    sel_mae = float(np.mean([r["test_mae"] for r in sel]))
    pap_mae = float(np.mean([r["test_mae"] for r in pap]))
    improvement = (pap_mse - sel_mse) / pap_mse * 100
    return {
        "selected_test_mse_mean": sel_mse,
        "paper_test_mse_mean": pap_mse,
        "selected_test_mae_mean": sel_mae,
        "paper_test_mae_mean": pap_mae,
        "mse_improvement_pct": improvement,
        "mae_improvement_pct": (pap_mae - sel_mae) / pap_mae * 100,
        "n_seeds_better": sum(v["selected_mse"] < v["paper_mse"] for v in by_seed.values()),
        "by_seed": by_seed,
        "h5_row_pass": improvement >= 1.0
        and all(v["selected_mse"] < v["paper_mse"] for v in by_seed.values()),
    }


class _Tracker:
    """MLflow logging when available; a silent no-op otherwise (the JSON report is the record)."""

    def __init__(self, uri: str | None, experiment: str) -> None:
        self.enabled = False
        if uri is None:
            return
        try:
            import mlflow
        except ImportError:
            return
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(experiment)
        self._mlflow, self.enabled = mlflow, True

    def log(self, name: str, params: dict[str, Any], metrics: dict[str, float]) -> None:
        if not self.enabled:
            return
        with self._mlflow.start_run(run_name=name):
            self._mlflow.log_params(params)
            self._mlflow.log_metrics(metrics)
