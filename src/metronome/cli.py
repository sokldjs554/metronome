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
    typer.echo(f"wrote {build_cache(cfg, processed_dir, cache_dir, workers=workers)}")


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


if __name__ == "__main__":
    app()
