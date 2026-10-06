"""One training loop for every PyTorch forecaster: seeded, early-stopped, warm-startable."""

from __future__ import annotations

import copy
import hashlib
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


@dataclass
class TrainConfig:
    lr: float = 0.005
    batch_size: int = 32
    max_epochs: int = 10
    patience: int = 3
    lr_schedule: Literal["halving", "onecycle", "constant"] = "halving"
    pct_start: float = 0.3
    loss: Literal["mse", "mae"] = "mse"
    threads: int = 1
    eval_batch_size: int = 1024
    grad_clip: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FitResult:
    epochs: int
    best_epoch: int
    best_val: float
    seconds: float
    stopped_early: bool
    history: list[dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def state_hash(model: nn.Module) -> str:
    h = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        h.update(name.encode())
        h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def _loss(kind: str, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return F.mse_loss(pred, target) if kind == "mse" else F.l1_loss(pred, target)


def _batches(n: int, batch_size: int, rng: np.random.Generator | None) -> list[np.ndarray]:
    order = rng.permutation(n) if rng is not None else np.arange(n)
    return [order[i : i + batch_size] for i in range(0, n, batch_size)]


def _to_tensor(a: np.ndarray, idx: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(np.ascontiguousarray(a[idx], dtype=np.float32))


@torch.inference_mode()
def evaluate_loss(model: nn.Module, x: np.ndarray, y: np.ndarray, kind: str, batch_size: int) -> float:
    model.eval()
    total, count = 0.0, 0
    for idx in _batches(len(x), batch_size, None):
        xb, yb = _to_tensor(x, idx), _to_tensor(y, idx)
        total += float(_loss(kind, model(xb), yb)) * len(idx)
        count += len(idx)
    return total / max(count, 1)


@torch.inference_mode()
def predict(model: nn.Module, x: np.ndarray, batch_size: int = 1024) -> np.ndarray:
    model.eval()
    out = []
    for idx in _batches(len(x), batch_size, None):
        out.append(model(_to_tensor(x, idx)).numpy())
    if out:
        return np.concatenate(out, axis=0)
    horizon = int(getattr(model, "horizon", x.shape[1]))
    return np.empty((0, horizon, x.shape[2]), dtype=np.float32)


def fit(
    model: nn.Module,
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    cfg: TrainConfig,
    seed: int,
) -> FitResult:
    """Train in place and leave the model holding the weights of the best validation epoch.

    `seed` fixes the batch order; weight initialization is the caller's responsibility (so that
    warm starts can pass an already-initialized model).
    """
    torch.set_num_threads(cfg.threads)
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    opt = torch.optim.Adam(model.parameters(), lr=cfg.lr)
    steps_per_epoch = max(1, -(-len(x_train) // cfg.batch_size))
    scheduler: torch.optim.lr_scheduler.LRScheduler | None = None
    if cfg.lr_schedule == "onecycle":
        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            opt,
            max_lr=cfg.lr,
            steps_per_epoch=steps_per_epoch,
            epochs=cfg.max_epochs,
            pct_start=cfg.pct_start,
        )
    best_val, best_epoch, best_state = float("inf"), 0, copy.deepcopy(model.state_dict())
    history: list[dict[str, float]] = []
    bad_epochs = 0
    started = time.perf_counter()
    epochs_run = 0
    stopped_early = False
    for epoch in range(1, cfg.max_epochs + 1):
        if cfg.lr_schedule == "halving":
            for group in opt.param_groups:
                group["lr"] = cfg.lr * (0.5 ** (epoch - 1))
        model.train()
        running, seen = 0.0, 0
        for idx in _batches(len(x_train), cfg.batch_size, rng):
            xb, yb = _to_tensor(x_train, idx), _to_tensor(y_train, idx)
            opt.zero_grad(set_to_none=True)
            loss = _loss(cfg.loss, model(xb), yb)
            loss.backward()
            if cfg.grad_clip:
                nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip)
            opt.step()
            if scheduler is not None:
                scheduler.step()
            running += loss.item() * len(idx)
            seen += len(idx)
        val = (
            evaluate_loss(model, x_val, y_val, cfg.loss, cfg.eval_batch_size)
            if len(x_val)
            else running / max(seen, 1)
        )
        history.append(
            {"epoch": epoch, "train": running / max(seen, 1), "val": val, "lr": opt.param_groups[0]["lr"]}
        )
        epochs_run = epoch
        if val < best_val - 1e-12:
            best_val, best_epoch, best_state = val, epoch, copy.deepcopy(model.state_dict())
            bad_epochs = 0
        else:
            bad_epochs += 1
            if bad_epochs >= cfg.patience:
                stopped_early = True
                break
    model.load_state_dict(best_state)
    model.eval()
    return FitResult(
        epochs=epochs_run,
        best_epoch=best_epoch,
        best_val=best_val,
        seconds=time.perf_counter() - started,
        stopped_early=stopped_early,
        history=history,
    )
