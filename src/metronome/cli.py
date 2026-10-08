"""`metronome` command line: every experiment and service stage is a subcommand."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="Data-driven retraining cadence for deployed forecasters.", no_args_is_help=True)

RAW = Path("data/raw")
PROCESSED = Path("data/processed")
CACHE = Path("artifacts/cache")
RUNS = Path("artifacts/runs")


# ---- data ----------------------------------------------------------------------------------------
@app.command()
def prepare(
    datasets: Annotated[list[str], typer.Argument(help="prepared dataset names (see sources.PREPARED)")],
    raw_dir: Path = RAW,
    processed_dir: Path = PROCESSED,
    local_dir: Annotated[
        Path | None, typer.Option(help="copy raw files from here instead of downloading")
    ] = None,
) -> None:
    """Fetch (checksum-verified), validate and write Parquet + manifest for each dataset."""
    from metronome.data.pipeline import prepare as _prepare

    for name in datasets:
        _out, manifest = _prepare(name, raw_dir, processed_dir, local_dir=local_dir)
        v = manifest["validation"]
        typer.echo(
            f"{name}: rows={v['n_rows']} channels={v['n_channels']} filled={manifest['filled_rows']} ok={v['ok']}"
        )


# ---- experiments ---------------------------------------------------------------------------------
@app.command()
def cache(
    dataset: str,
    seed: int = 0,
    model: str = "dlinear",
    window: str = "expanding",
    workers: int = 4,
    max_epochs: int = 10,
    limit_days: Annotated[
        int | None, typer.Option(help="build only the first N stream days (CI smoke)")
    ] = None,
    processed_dir: Path = PROCESSED,
    cache_dir: Path = CACHE,
) -> None:
    """Build the daily cold-refit cache for one dataset and seed (protocol P6)."""
    from metronome.cadence.cache import CacheConfig, build_cache
    from metronome.train.trainer import TrainConfig

    cfg = CacheConfig(
        dataset=dataset,
        seed=seed,
        model=model,
        window=window,
        train=TrainConfig(lr=0.005, batch_size=32, max_epochs=max_epochs, patience=3, threads=1),
    )
    days = list(range(limit_days)) if limit_days else None
    typer.echo(f"wrote {build_cache(cfg, processed_dir, cache_dir, workers=workers, days=days)}")


@app.command()
def warm(
    dataset: str,
    seed: int = 0,
    epochs: int = 2,
    lr: float = 1e-3,
    threads: int = 1,
    processed_dir: Path = PROCESSED,
    cache_dir: Path = CACHE,
) -> None:
    """Sequential warm-start daily refits (protocol P6 variant)."""
    from metronome.cadence.cache import CacheConfig, build_warm_chain
    from metronome.train.trainer import TrainConfig

    cfg = CacheConfig(
        dataset=dataset,
        seed=seed,
        train=TrainConfig(lr=0.005, batch_size=32, max_epochs=10, patience=3, threads=threads),
    )
    typer.echo(f"wrote {build_warm_chain(cfg, processed_dir, cache_dir, epochs=epochs, lr=lr)}")


@app.command()
def simulate(
    names: Annotated[list[str], typer.Argument(help="cache names, e.g. etth1_dlinear_s0")],
    cache_dir: Path = CACHE,
    out_dir: Path = Path("artifacts/cadence"),
) -> None:
    """Evaluate every retraining policy on the given caches (protocol P7-P8)."""
    from dataclasses import asdict

    from metronome.cadence.simulate import simulate_cache

    out_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        summary = simulate_cache(cache_dir, name)
        (out_dir / f"{name}.json").write_text(json.dumps(asdict(summary), indent=1))
        never = summary.policies["never"]["mae"]
        daily = summary.policies["periodic-1"]["mae"]
        typer.echo(f"{name}: never={never:.4f} periodic-1={daily:.4f} ({(never - daily) / never:+.2%})")


@app.command()
def ltsf(
    dataset: str,
    model: str = "dlinear",
    kind: str = "etth",
    lookback: int = 336,
    horizon: int = 96,
    seed: int = 2021,
    threads: int = 1,
    max_epochs: int | None = None,
    processed_dir: Path = PROCESSED,
    out_dir: Path = RUNS,
) -> None:
    """Train/evaluate one model under the standard LTSF split (protocol P10)."""
    from metronome.eval.ltsf import LTSFConfig, dlinear_recipe, patchtst_recipe, run_ltsf

    recipe = patchtst_recipe(threads) if model == "patchtst" else dlinear_recipe(threads)
    if max_epochs is not None:
        recipe.max_epochs = max_epochs
    cfg = LTSFConfig(
        dataset=dataset, kind=kind, model=model, lookback=lookback, horizon=horizon, seed=seed, train=recipe
    )
    report = run_ltsf(cfg, processed_dir, out_dir)
    m = report["metrics"]
    fit = report["fit"] or {}
    typer.echo(
        f"{cfg.name}: mse={m['mse']:.4f} mae={m['mae']:.4f} epochs={fit.get('epochs')} {fit.get('seconds', 0):.0f}s"
    )


# ---- inference optimization ----------------------------------------------------------------------
@app.command()
def bench(
    checkpoint: Annotated[Path, typer.Argument(help="an LTSF .pt checkpoint written by `ltsf`")],
    out: Path = Path("artifacts/optimization/benchmark.json"),
    threads: int = 1,
    repeats: int = 300,
    warmup: int = 50,
) -> None:
    """Export a checkpoint to ONNX, verify parity, quantize to INT8 and benchmark all engines (P11)."""
    import torch

    from metronome.export.onnx_export import benchmark, check_parity, export_onnx, quantize_dynamic, save_json
    from metronome.models import build

    ckpt = torch.load(checkpoint, map_location="cpu", weights_only=False)
    cfg = ckpt["config"]
    model = build(
        cfg["model"], cfg["lookback"], cfg["horizon"], len(ckpt["channels"]), **cfg.get("model_kwargs", {})
    )
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    work = out.parent / checkpoint.stem
    fp32 = export_onnx(model, cfg["lookback"], len(ckpt["channels"]), work / "model.onnx")
    import numpy as np

    x = np.random.default_rng(0).normal(size=(8, cfg["lookback"], len(ckpt["channels"]))).astype(np.float32)
    parity = check_parity(model, fp32, x)
    if not parity.ok:
        raise typer.Exit(code=2)
    int8 = quantize_dynamic(fp32, work / "model.int8.onnx")
    report = benchmark(
        model,
        fp32,
        int8,
        cfg["lookback"],
        len(ckpt["channels"]),
        threads=threads,
        repeats=repeats,
        warmup=warmup,
    )
    report["checkpoint"] = str(checkpoint)
    report["model"] = cfg["model"]
    report["parity"] = {"max_abs_diff": parity.max_abs_diff, "tolerance": parity.tolerance}
    report["n_parameters"] = sum(p.numel() for p in model.parameters())
    save_json(report, out)
    for bs, engines in report["batches"].items():
        line = " ".join(f"{k}={v['p95_ms']:.3f}ms" for k, v in engines.items())
        typer.echo(f"batch {bs}: {line}")


# ---- serving -------------------------------------------------------------------------------------
@app.command("deploy-init")
def deploy_init(
    dataset: str,
    registry: Path = Path("registry"),
    processed_dir: Path = PROCESSED,
    lookback: int = 336,
    horizon: int = 96,
    model: str = "dlinear",
    max_epochs: int = 10,
    seed: int = 0,
    threads: int = 2,
) -> None:
    """Create a registry for a dataset: stream.npz, deployment.json and a verified first version."""
    from metronome.serving.deploy import init_deployment

    report = init_deployment(
        dataset,
        processed_dir,
        registry,
        lookback=lookback,
        horizon=horizon,
        model=model,
        max_epochs=max_epochs,
        seed=seed,
        threads=threads,
    )
    typer.echo(json.dumps(report, indent=2))


@app.command()
def serve(
    registry: Path = Path("registry"),
    host: str = "127.0.0.1",
    port: int = 8000,
    threads: int = 1,
    api_key: str | None = None,
    detectors: str = "ratio-0.2,ph-0.1,adwin-0.01",
) -> None:
    """Serve the active ONNX model with monitoring and hot swap."""
    import uvicorn

    from metronome.serving.app import create_app

    application = create_app(
        registry, api_key=api_key, threads=threads, detector_specs=tuple(detectors.split(","))
    )
    uvicorn.run(application, host=host, port=port, log_level="info")


@app.command()
def worker(
    registry: Path = Path("registry"),
    api_url: str | None = "http://127.0.0.1:8000",
    api_key: str | None = None,
    stream: Path | None = None,
    max_epochs: int = 10,
    threads: int = 1,
    once: bool = False,
    poll_seconds: float = 2.0,
) -> None:
    """Train replacements for retrain jobs and activate them through the API."""
    import logging

    from metronome.serving.worker import WorkerConfig, run_worker

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    cfg = WorkerConfig(
        registry_root=registry,
        stream_path=stream or registry / "stream.npz",
        api_url=api_url,
        api_key=api_key,
        max_epochs=max_epochs,
        threads=threads,
        poll_seconds=poll_seconds,
    )
    done = run_worker(cfg, once=once)
    for d in done:
        typer.echo(f"{d['job']} -> {d['version']} val_mae_fixed={d['metrics']['val_mae_fixed']:.4f}")


@app.command()
def demo(
    registry: Path = Path("registry/etth1"),
    host: str = "127.0.0.1",
    port: int = 8000,
    threads: int = 1,
    max_epochs: int = 10,
) -> None:
    """Single-process demo: the API plus an in-process retrain worker thread (same HTTP code path)."""
    import logging
    import os
    import threading

    import uvicorn

    from metronome.serving.app import create_app
    from metronome.serving.worker import WorkerConfig, run_worker

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    api_key = os.environ.get("METRONOME_API_KEY") or None
    application = create_app(registry, api_key=api_key, threads=threads)
    cfg = WorkerConfig(
        registry_root=registry,
        stream_path=registry / "stream.npz",
        api_url=f"http://127.0.0.1:{port}",
        api_key=api_key,
        max_epochs=max_epochs,
        threads=threads,
        poll_seconds=2.0,
    )
    threading.Thread(
        target=run_worker, args=(cfg,), kwargs={"once": False}, daemon=True, name="worker"
    ).start()
    uvicorn.run(application, host=host, port=port, log_level="info")


@app.command("tf-repro")
def tf_repro(
    dataset: str = "etth1",
    seeds: str = "0,1,2",
    processed_dir: Path = PROCESSED,
    out_dir: Path = Path("artifacts/tf"),
) -> None:
    """TensorFlow reproduction of DLinear (protocol P15): parity, lockstep training, independent training."""
    from metronome.tfmodels import run_reproduction

    report = run_reproduction(
        dataset, seeds=tuple(int(s) for s in seeds.split(",")), processed_dir=processed_dir, out_dir=out_dir
    )
    typer.echo(json.dumps(report["summary"], indent=1))


@app.command()
def tune(
    dataset: str,
    kind: str = "etth",
    horizon: int = 96,
    trials: int = 40,
    threads: int = 1,
    processed_dir: Path = PROCESSED,
    out_dir: Path = Path("artifacts/tune"),
    mlflow_uri: str | None = "sqlite:///mlflow.db",
) -> None:
    """Pre-registered model improvement search (protocol P14): validation-only search, one test look."""
    from metronome.tune.search import run_search

    report = run_search(
        dataset,
        kind=kind,
        horizon=horizon,
        n_trials=trials,
        processed_dir=processed_dir,
        out_dir=out_dir,
        threads=threads,
        mlflow_uri=mlflow_uri,
        log=typer.echo,
    )
    s = report["summary"]
    typer.echo(
        f"{dataset}: selected {report['selected_params']} test MSE {s['selected_test_mse_mean']:.4f} "
        f"vs paper {s['paper_test_mse_mean']:.4f} ({s['mse_improvement_pct']:+.2f}%), "
        f"{s['n_seeds_better']}/{len(report['test_seeds'])} seeds better"
    )


@app.command()
def report(root: Path = Path(".")) -> None:
    """Aggregate artifacts -> summaries, charts, dashboard evidence (docs quote these via markers)."""
    from metronome.report.build import build_all

    out = build_all(root)
    hyp = out["cadence_summary"].get("hypotheses", {})
    for name, h in hyp.items():
        typer.echo(f"{name}: {'PASS' if h.get('pass') else 'FAIL'} ({len(h.get('rows', {}))} rows)")
    typer.echo(f"charts: {len(out['charts'])}, ltsf runs: {len(out['ltsf_summary']['runs'])}")


@app.command()
def bigdata(
    raw_dir: Path = RAW,
    out_dir: Path = Path("artifacts/bigdata"),
    local_dir: Path | None = None,
    engines: str = "polars,pandas,spark",
    repeats: int = 3,
) -> None:
    """Wide->long M4 pipeline in Polars / pandas / PySpark with cross-engine agreement (P12)."""
    from metronome.bigdata.engines import run_stage

    rep = run_stage(raw_dir, out_dir, local_dir=local_dir, engines=tuple(engines.split(",")), repeats=repeats)
    for e in rep["engines"]:
        typer.echo(
            f"{e['engine']:7s} median {e['median_seconds']:.1f}s cells={e['n_cells']:,} series={e['n_series']:,}"
        )


@app.command("bigdata-cluster")
def bigdata_cluster(
    master: str = "spark://spark-master:7077",
    master_ui: str = "http://spark-master:8080",
    workers: int = 2,
    raw_dir: Path = RAW,
    out_dir: Path = Path("artifacts/bigdata"),
    local_dir: Path | None = None,
    executor_cores: int = 2,
    executor_memory: str = "2g",
    partition_mib: int = 8,
    local_reference: bool = True,
) -> None:
    """The M4 Spark job on a standalone cluster, checked against Polars (P16). Run as the compose driver."""
    from metronome.bigdata.cluster import run_cluster_stage

    rep = run_cluster_stage(
        raw_dir,
        out_dir,
        master=master,
        master_ui=master_ui,
        n_workers=workers,
        local_dir=local_dir,
        executor_cores=executor_cores,
        executor_memory=executor_memory,
        partition_mib=partition_mib,
        local_reference=local_reference,
    )
    c = rep["cluster"]
    typer.echo(
        f"cluster {c['seconds']:.1f}s cells={c['n_cells']:,} series={c['n_series']:,} agree={rep['agree']}"
    )
    for e in rep["executors"]:
        typer.echo(f"  executor {e['id']} on {e['host']}: {e['completed_tasks']} tasks")
    if "local_same_splits" in rep:
        typer.echo(
            f"local   {rep['local_same_splits']['seconds']:.1f}s (same splits, {rep['local_same_splits']['master']})"
        )
    if not rep["passed"]:
        typer.echo(f"FAILED: agree={rep['agree']} distributed={rep['distributed']}", err=True)
        raise typer.Exit(1)


@app.command("mlflow-log")
def mlflow_log(
    tracking_uri: str = "sqlite:///mlflow.db",
    runs_dir: Path = RUNS,
    cadence_dir: Path = Path("artifacts/cadence"),
    registry: Path | None = None,
) -> None:
    """Mirror LTSF runs, cadence results and the file registry into MLflow (tracking + model registry)."""
    from metronome.tracking.mlflow_log import log_cadence, log_ltsf_runs, register_versions

    n_runs = len(log_ltsf_runs(runs_dir, tracking_uri)) if runs_dir.exists() else 0
    n_cad = len(log_cadence(cadence_dir, tracking_uri)) if cadence_dir.exists() else 0
    typer.echo(f"logged {n_runs} ltsf runs, {n_cad} cadence runs")
    if registry is not None:
        for row in register_versions(registry, tracking_uri):
            typer.echo(
                f"registry {row['version']} -> mlflow v{row['mlflow_version']} verified={row['verified']} active={row['active']}"
            )


if __name__ == "__main__":
    app()
