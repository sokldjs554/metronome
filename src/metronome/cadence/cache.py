"""Refit cache: one cold-trained model per stream day, with its errors on every later day.

A cold refit on day d depends only on (data up to d, seed), never on which policy asked for it.
So every policy can be simulated afterwards by picking, for each day, which cached model was
active. The cache stores per-(model day, evaluation day, channel) error sums on the fixed
evaluation scale (docs/protocol.md P4, P6), not forecasts, so it stays small.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import platform
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import torch

from metronome.data.pipeline import load_prepared
from metronome.data.sources import PREPARED
from metronome.data.splits import StreamSplit, stream_split
from metronome.data.windows import Scaler, make_windows
from metronome.eval.metrics import daily_error_sums
from metronome.models import build
from metronome.train.trainer import TrainConfig, fit, predict, seed_everything, state_hash


@dataclass
class CacheConfig:
    dataset: str
    seed: int = 0
    model: str = "dlinear"
    lookback: int = 336
    horizon: int = 96
    val_days: int = 14
    window: str = "expanding"  # or "sliding"
    stream_days: int | None = None  # resolved from PREPARED when None
    train: TrainConfig = field(
        default_factory=lambda: TrainConfig(lr=0.005, batch_size=32, max_epochs=10, patience=3, threads=1)
    )
    model_kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        suffix = "" if self.window == "expanding" else f"_{self.window}"
        return f"{self.dataset}_{self.model}_s{self.seed}{suffix}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["train"] = self.train.to_dict()
        return d


@dataclass
class StreamData:
    """Everything a refit job needs, loaded once per worker process."""

    values: np.ndarray  # (T, C) raw float32
    split: StreamSplit
    fixed: Scaler  # evaluation scale: statistics of the initial history
    origin_day: np.ndarray  # for every origin index in the stream, which stream day it belongs to
    stream_origins: np.ndarray  # row indices of all stream origins with a complete target

    @property
    def n_days(self) -> int:
        return self.split.n_days


def load_stream(
    dataset: str, processed_dir: Path, lookback: int, horizon: int, stream_days: int
) -> StreamData:
    ts, values, _channels, _manifest = load_prepared(dataset, processed_dir)
    split = stream_split(ts, stream_days)
    fixed = Scaler.fit(values[: split.stream_start])
    last_origin = len(values) - horizon + 1  # exclusive bound: origin + horizon <= len(values)
    origins = np.arange(split.stream_start, last_origin)
    day_of_row = np.searchsorted(split.day_starts, origins, side="right") - 1
    return StreamData(values, split, fixed, day_of_row.astype(np.int64), origins)


def _window_bounds(data: StreamData, day: int, cfg: CacheConfig) -> tuple[int, int]:
    end = int(data.split.day_starts[day])  # data strictly before the refit day
    start = max(0, end - data.split.stream_start) if cfg.window == "sliding" else 0
    return start, end


def train_day(data: StreamData, day: int, cfg: CacheConfig) -> tuple[torch.nn.Module, Scaler, dict[str, Any]]:
    """Cold-train the model for `day` and return it with its scaler and fit statistics."""
    start, end = _window_bounds(data, day, cfg)
    hist = data.values[start:end]
    day_rows = int(data.split.day_starts[1] - data.split.day_starts[0]) if data.n_days > 1 else 24
    val_rows = cfg.val_days * day_rows
    train_end = len(hist) - val_rows
    if train_end < cfg.lookback + cfg.horizon + 1:
        raise ValueError("not enough history for a train/validation split")
    scaler = Scaler.fit(hist[:train_end])
    z = scaler.transform(hist)
    x_tr, y_tr = make_windows(z[:train_end], cfg.lookback, cfg.horizon)
    # validation windows: every origin whose target starts inside the last val_days
    x_va, y_va = make_windows(z[train_end - cfg.lookback :], cfg.lookback, cfg.horizon)
    seed_everything(cfg.seed * 100_003 + day)
    model = build(cfg.model, cfg.lookback, cfg.horizon, hist.shape[1], **cfg.model_kwargs)
    result = fit(model, x_tr, y_tr, x_va, y_va, cfg.train, seed=cfg.seed * 100_003 + day)
    # validation MAE on the fixed evaluation scale, used by the ratio rule as the model's baseline
    pred_va = scaler.inverse(predict(model, x_va, cfg.train.eval_batch_size))
    truth_va = scaler.inverse(np.ascontiguousarray(y_va))
    val_mae_fixed = float(np.mean(np.abs(data.fixed.transform(pred_va) - data.fixed.transform(truth_va))))
    info = {
        "day": day,
        "train_rows": [start, start + train_end],
        "n_train_windows": len(x_tr),
        "n_val_windows": len(x_va),
        "val_mae_fixed": val_mae_fixed,
        "fit": result.to_dict(),
        "state_sha256": state_hash(model),
    }
    return model, scaler, info


def evaluate_from_day(
    data: StreamData, model: torch.nn.Module, scaler: Scaler, day: int, cfg: CacheConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Errors of `model` on every stream origin from `day` onward, aggregated per (day, channel)."""
    mask = data.origin_day >= day
    origins = data.stream_origins[mask]
    days = data.origin_day[mask]
    if len(origins) == 0:
        c = data.values.shape[1]
        return np.zeros((data.n_days, c)), np.zeros((data.n_days, c)), np.zeros(data.n_days, dtype=np.int64)
    # Build inputs on the refit scale, outputs back to raw, then onto the fixed scale.
    z = scaler.transform(data.values)
    x = np.stack([z[o - cfg.lookback : o] for o in origins])
    pred_raw = scaler.inverse(predict(model, x, cfg.train.eval_batch_size))
    truth_raw = np.stack([data.values[o : o + cfg.horizon] for o in origins])
    pred = data.fixed.transform(pred_raw)
    truth = data.fixed.transform(truth_raw)
    return daily_error_sums(pred, truth, days, data.n_days)


# ---- multiprocessing plumbing: workers load the stream once and process many days ----------
_WORKER: dict[str, Any] = {}


def _init_worker(dataset: str, processed_dir: str, cfg_dict: dict[str, Any]) -> None:
    torch.set_num_threads(1)
    cfg = CacheConfig(**{**cfg_dict, "train": TrainConfig(**cfg_dict["train"])})
    _WORKER["cfg"] = cfg
    assert cfg.stream_days is not None
    _WORKER["data"] = load_stream(dataset, Path(processed_dir), cfg.lookback, cfg.horizon, cfg.stream_days)


def _run_day(day: int) -> dict[str, Any]:
    cfg: CacheConfig = _WORKER["cfg"]
    data: StreamData = _WORKER["data"]
    started = time.perf_counter()
    model, scaler, info = train_day(data, day, cfg)
    abs_sum, sq_sum, count = evaluate_from_day(data, model, scaler, day, cfg)
    info["wall_seconds"] = time.perf_counter() - started
    info["abs_sum"] = abs_sum
    info["sq_sum"] = sq_sum
    info["count"] = count
    if day == 0:
        info["state_dict"] = {k: v.numpy() for k, v in model.state_dict().items()}
        info["scaler"] = scaler.to_dict()
    return info


def build_cache(
    cfg: CacheConfig,
    processed_dir: Path,
    cache_dir: Path,
    *,
    workers: int = 4,
    days: list[int] | None = None,
    progress: bool = True,
) -> Path:
    """Train every stream day's model (in parallel) and write `<cache_dir>/<name>.npz` + `.json`."""
    if cfg.stream_days is None:
        cfg = replace(cfg, stream_days=PREPARED[cfg.dataset].stream_days)
    assert cfg.stream_days is not None
    data = load_stream(cfg.dataset, processed_dir, cfg.lookback, cfg.horizon, cfg.stream_days)
    n_days = data.n_days
    todo = list(range(n_days)) if days is None else days
    cache_dir.mkdir(parents=True, exist_ok=True)
    n_channels = data.values.shape[1]
    abs_sum = np.full((n_days, n_days, n_channels), np.nan, dtype=np.float64)
    sq_sum = np.full_like(abs_sum, np.nan)
    count = np.zeros(n_days, dtype=np.int64)
    meta: list[dict[str, Any]] = [{} for _ in range(n_days)]
    day0: dict[str, Any] = {}
    started = time.perf_counter()
    ctx = mp.get_context("spawn")  # never fork a process that may already own torch/OpenMP threads
    with ctx.Pool(
        workers, initializer=_init_worker, initargs=(cfg.dataset, str(processed_dir), cfg.to_dict())
    ) as pool:
        for i, info in enumerate(pool.imap_unordered(_run_day, todo, chunksize=1)):
            d = info["day"]
            abs_sum[d] = info.pop("abs_sum")
            sq_sum[d] = info.pop("sq_sum")
            abs_sum[d, :d] = np.nan  # a model is never evaluated on days before it exists
            sq_sum[d, :d] = np.nan
            count = np.maximum(count, info.pop("count"))
            if "state_dict" in info:
                day0 = {"state_dict": info.pop("state_dict"), "scaler": info.pop("scaler")}
            meta[d] = info
            if progress and (i % 10 == 0 or i + 1 == len(todo)):
                elapsed = time.perf_counter() - started
                print(f"[{cfg.name}] {i + 1}/{len(todo)} days, {elapsed / 60:.1f} min", flush=True)
    out = cache_dir / f"{cfg.name}.npz"
    np.savez_compressed(
        out,
        abs_sum=abs_sum,
        sq_sum=sq_sum,
        count=count,
        train_seconds=np.array([m.get("fit", {}).get("seconds", np.nan) for m in meta]),
        val_mae_fixed=np.array([m.get("val_mae_fixed", np.nan) for m in meta]),
        epochs=np.array([m.get("fit", {}).get("epochs", 0) for m in meta]),
        day_starts=data.split.day_starts,
        **({f"day0_{k}": v for k, v in day0["state_dict"].items()} if day0 else {}),
    )
    summary = {
        "config": cfg.to_dict(),
        "n_days": n_days,
        "n_channels": n_channels,
        "stream_start": data.split.stream_start,
        "fixed_scaler": data.fixed.to_dict(),
        "day0_scaler": day0.get("scaler"),
        "days": meta,
        "wall_seconds": time.perf_counter() - started,
        "env": {"torch": torch.__version__, "python": platform.python_version(), "cpu": os.cpu_count()},
    }
    (cache_dir / f"{cfg.name}.json").write_text(json.dumps(summary, indent=1))
    return out


def build_warm_chain(
    cfg: CacheConfig, processed_dir: Path, cache_dir: Path, *, epochs: int = 2, lr: float = 1e-3
) -> Path:
    """Sequential daily refits that start from yesterday's weights (protocol P6, warm-start variant).

    Day 0 is a cold fit identical to the cache's day 0. Day d > 0 continues from model d-1 with a
    short, low-lr fit on the same window as a cold refit would use. Stores the errors of model d on
    day d+1 only (that is all a daily-refit policy ever uses).
    """
    torch.set_num_threads(cfg.train.threads)
    if cfg.stream_days is None:
        cfg = replace(cfg, stream_days=PREPARED[cfg.dataset].stream_days)
    assert cfg.stream_days is not None
    data = load_stream(cfg.dataset, processed_dir, cfg.lookback, cfg.horizon, cfg.stream_days)
    n_days = data.n_days
    c = data.values.shape[1]
    abs_next = np.full((n_days, c), np.nan)
    sq_next = np.full((n_days, c), np.nan)
    count = np.zeros(n_days, dtype=np.int64)
    seconds = np.zeros(n_days)
    model, scaler, info0 = train_day(data, 0, cfg)
    seconds[0] = info0["fit"]["seconds"]
    warm_cfg = TrainConfig(
        **{
            **cfg.train.to_dict(),
            "max_epochs": epochs,
            "patience": epochs,
            "lr": lr,
            "lr_schedule": "constant",
        }
    )
    started = time.perf_counter()
    for day in range(n_days):
        if day > 0:
            start, end = _window_bounds(data, day, cfg)
            hist = data.values[start:end]
            day_rows = int(data.split.day_starts[1] - data.split.day_starts[0])
            train_end = len(hist) - cfg.val_days * day_rows
            scaler = Scaler.fit(hist[:train_end])
            z = scaler.transform(hist)
            x_tr, y_tr = make_windows(z[:train_end], cfg.lookback, cfg.horizon)
            x_va, y_va = make_windows(z[train_end - cfg.lookback :], cfg.lookback, cfg.horizon)
            res = fit(model, x_tr, y_tr, x_va, y_va, warm_cfg, seed=cfg.seed * 100_003 + day)
            seconds[day] = res.seconds
        a, s, cnt = evaluate_from_day(data, model, scaler, day, cfg)
        nxt = day + 1
        if nxt < n_days:
            abs_next[nxt], sq_next[nxt], count[nxt] = a[nxt], s[nxt], cnt[nxt]
        if day == 0:
            abs_next[0], sq_next[0], count[0] = a[0], s[0], cnt[0]
        if day % 30 == 0:
            print(
                f"[warm {cfg.name}] day {day}/{n_days} {(time.perf_counter() - started) / 60:.1f} min",
                flush=True,
            )
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{cfg.name}_warm.npz"
    np.savez_compressed(out, abs_next=abs_next, sq_next=sq_next, count=count, train_seconds=seconds)
    (cache_dir / f"{cfg.name}_warm.json").write_text(
        json.dumps(
            {
                "config": cfg.to_dict(),
                "epochs": epochs,
                "lr": lr,
                "wall_seconds": time.perf_counter() - started,
            },
            indent=1,
        )
    )
    return out
