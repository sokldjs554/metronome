"""Create a registry from a prepared dataset: deployment.json, stream.npz and the first version.

The first version is trained on the initial history (everything before the evaluation stream),
exactly like day 0 of the offline refit cache, so the live service starts where the experiment
starts.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from metronome.data.pipeline import load_prepared
from metronome.data.sources import PREPARED
from metronome.data.splits import stream_split
from metronome.data.windows import Scaler
from metronome.serving.registry import Deployment, Registry
from metronome.serving.replay import write_stream
from metronome.serving.worker import export_and_register, train_replacement


def init_deployment(
    dataset: str,
    processed_dir: Path,
    registry_root: Path,
    *,
    lookback: int = 336,
    horizon: int = 96,
    model: str = "dlinear",
    max_epochs: int = 10,
    seed: int = 0,
    threads: int = 1,
    stream_days: int | None = None,
) -> dict[str, Any]:
    ts, values, channels, manifest = load_prepared(dataset, processed_dir)
    days = stream_days if stream_days is not None else PREPARED[dataset].stream_days
    split = stream_split(ts, days)
    fixed = Scaler.fit(values[: split.stream_start])
    registry = Registry(registry_root)
    registry.init(
        Deployment(
            dataset=dataset,
            lookback=lookback,
            horizon=horizon,
            channels=channels,
            fixed_scaler=fixed.to_dict(),
            freq=PREPARED[dataset].freq if dataset in PREPARED else "1h",
            stream_start=int(split.stream_start),
        )
    )
    stream_path = write_stream(registry_root / "stream.npz", ts, values)
    t0 = time.perf_counter()
    net, scaler, metrics = train_replacement(
        values,
        split.stream_start,
        lookback,
        horizon,
        model_name=model,
        max_epochs=max_epochs,
        seed=seed,
        threads=threads,
        fixed=fixed.to_dict(),
    )
    provenance = {
        "trigger": "initial",
        "cutoff_row": int(split.stream_start),
        "cutoff_time": str(ts[split.stream_start - 1]),
        "train_rows": [0, int(split.stream_start)],
        "model": model,
        "seed": seed,
        "dataset_content_sha256": manifest.get("content_sha256"),
    }
    version = export_and_register(
        registry,
        net,
        scaler,
        metrics,
        provenance,
        values,
        int(split.stream_start),
        registry_root / "work" / "initial",
    )
    report = registry.activate(version)
    return {
        "registry": str(registry_root),
        "stream": str(stream_path),
        "version": version,
        "stream_start_row": int(split.stream_start),
        "metrics": metrics,
        "activation": report,
        "seconds": time.perf_counter() - t0,
    }
