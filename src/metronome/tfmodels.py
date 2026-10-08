"""DLinear in TensorFlow/Keras, the same model as `metronome.models.linear.DLinear` (docs/protocol.md P15).

Same centered moving average with edge replication, same two shared linear maps over the time axis, so a
PyTorch state dict moves to Keras one to one (`load_torch_state`). `fit_tf` mirrors the PyTorch trainer:
Adam, lr halved every epoch, batch order from `numpy.random.default_rng(seed)`, patience on validation
MSE, best weights restored. Only the PyTorch path is used in serving; this module exists to show the
model and its training reproduce across frameworks.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import tensorflow as tf


class TFDLinear(tf.keras.Model):
    def __init__(
        self, lookback: int, horizon: int, channels: int, kernel_size: int = 25, seed: int | None = None
    ) -> None:
        super().__init__()
        if kernel_size < 1 or kernel_size % 2 == 0:
            raise ValueError("kernel_size must be a positive odd integer")
        self.lookback, self.horizon, self.channels, self.kernel_size = (
            lookback,
            horizon,
            channels,
            kernel_size,
        )
        # PyTorch nn.Linear default: weights and bias ~ U(-1/sqrt(fan_in), 1/sqrt(fan_in)).
        bound = 1.0 / np.sqrt(lookback)

        def init(offset: int) -> tf.keras.initializers.Initializer:
            return tf.keras.initializers.RandomUniform(
                -bound, bound, seed=None if seed is None else seed * 4 + offset
            )

        self.seasonal = tf.keras.layers.Dense(
            horizon, kernel_initializer=init(0), bias_initializer=init(1), name="seasonal"
        )
        self.trend = tf.keras.layers.Dense(
            horizon, kernel_initializer=init(2), bias_initializer=init(3), name="trend"
        )
        self(tf.zeros((1, lookback, channels)))  # build the weights

    def moving_average(self, x: tf.Tensor) -> tf.Tensor:  # (B, L, C) -> (B, L, C)
        pad = (self.kernel_size - 1) // 2
        front = tf.repeat(x[:, :1, :], pad, axis=1)
        back = tf.repeat(x[:, -1:, :], pad, axis=1)
        xp = tf.concat([front, x, back], axis=1)
        return tf.nn.avg_pool1d(xp, ksize=self.kernel_size, strides=1, padding="VALID")

    def call(self, x: tf.Tensor) -> tf.Tensor:
        trend = self.moving_average(x)
        seasonal = x - trend
        s = self.seasonal(tf.transpose(seasonal, [0, 2, 1]))  # (B, C, H)
        t = self.trend(tf.transpose(trend, [0, 2, 1]))
        return tf.transpose(s + t, [0, 2, 1])  # (B, H, C)


def load_torch_state(model: TFDLinear, state: dict[str, np.ndarray]) -> None:
    """Copy a PyTorch DLinear state dict (nn.Linear weight is (H, L); Keras kernel is (L, H))."""
    for branch in ("seasonal", "trend"):
        layer = getattr(model, branch)
        layer.set_weights(
            [np.asarray(state[f"{branch}.proj.weight"]).T, np.asarray(state[f"{branch}.proj.bias"])]
        )


def predict_tf(model: TFDLinear, x: np.ndarray, batch_size: int = 1024) -> np.ndarray:
    out = [model(x[i : i + batch_size], training=False).numpy() for i in range(0, len(x), batch_size)]
    return np.concatenate(out, axis=0)


def fit_tf(
    model: TFDLinear,
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    *,
    seed: int,
    lr: float = 0.005,
    batch_size: int = 32,
    max_epochs: int = 20,
    patience: int = 3,
) -> dict[str, Any]:
    """The PyTorch recipe (`dlinear_recipe`) in TensorFlow; Adam epsilon set to PyTorch's 1e-8."""
    rng = np.random.default_rng(seed)
    opt = tf.keras.optimizers.Adam(learning_rate=lr, epsilon=1e-8)
    loss_fn = tf.keras.losses.MeanSquaredError()

    @tf.function(reduce_retracing=True)
    def step(xb: tf.Tensor, yb: tf.Tensor) -> tf.Tensor:
        with tf.GradientTape() as tape:
            loss = loss_fn(yb, model(xb, training=True))
        grads = tape.gradient(loss, model.trainable_variables)
        opt.apply_gradients(zip(grads, model.trainable_variables, strict=True))
        return loss

    best_val, best_epoch, best_weights, bad = float("inf"), 0, model.get_weights(), 0
    started, epochs = time.perf_counter(), 0
    for epoch in range(1, max_epochs + 1):
        opt.learning_rate.assign(lr * 0.5 ** (epoch - 1))
        order = rng.permutation(len(x_train))
        for i in range(0, len(order), batch_size):
            idx = order[i : i + batch_size]
            step(tf.constant(x_train[idx], tf.float32), tf.constant(y_train[idx], tf.float32))
        val = float(np.mean((predict_tf(model, x_val) - y_val) ** 2))
        epochs = epoch
        if val < best_val - 1e-12:
            best_val, best_epoch, best_weights, bad = val, epoch, model.get_weights(), 0
        else:
            bad += 1
            if bad >= patience:
                break
    model.set_weights(best_weights)
    return {
        "epochs": epochs,
        "best_epoch": best_epoch,
        "best_val": best_val,
        "seconds": time.perf_counter() - started,
    }


def run_reproduction(
    dataset: str = "etth1",
    *,
    seeds: tuple[int, ...] = (0, 1, 2),
    lookback: int = 336,
    horizon: int = 96,
    processed_dir: Path = Path("data/processed"),
    out_dir: Path = Path("artifacts/tf"),
) -> dict[str, Any]:
    """P15. For each seed: (a) lockstep — PyTorch init copied into Keras, same batch order, both trained;
    (b) independent — Keras with its own PyTorch-like init. Test split evaluated once per run."""
    import torch

    from metronome.data.pipeline import load_prepared
    from metronome.data.splits import ltsf_borders
    from metronome.data.windows import Scaler, make_windows
    from metronome.eval.ltsf import dlinear_recipe
    from metronome.models import build
    from metronome.train.trainer import fit, predict, seed_everything

    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.threading.set_intra_op_parallelism_threads(1)
    _ts, values, channels, manifest = load_prepared(dataset, processed_dir)
    b1, b2 = ltsf_borders(len(values), lookback, "etth")
    z = Scaler.fit(values[b1[0] : b2[0]]).transform(values)
    (x_tr, y_tr), (x_va, y_va), (x_te, y_te) = (
        make_windows(z[b1[i] : b2[i]], lookback, horizon) for i in range(3)
    )
    x_tr, y_tr, x_va, y_va, x_te, y_te = (
        np.ascontiguousarray(a, dtype=np.float32) for a in (x_tr, y_tr, x_va, y_va, x_te, y_te)
    )

    def metrics(pred: np.ndarray) -> dict[str, float]:
        return {
            "test_mse": float(np.mean((pred - y_te) ** 2)),
            "test_mae": float(np.mean(np.abs(pred - y_te))),
        }

    runs = []
    for seed in seeds:
        seed_everything(seed)
        torch_model = build("dlinear", lookback, horizon, len(channels))
        init_state = {k: v.detach().numpy().copy() for k, v in torch_model.state_dict().items()}
        tf_lock = TFDLinear(lookback, horizon, len(channels))
        load_torch_state(tf_lock, init_state)
        x_probe = x_te[:256]
        with torch.no_grad():
            init_diff = float(
                np.max(np.abs(torch_model(torch.from_numpy(x_probe)).numpy() - predict_tf(tf_lock, x_probe)))
            )
        torch_fit = fit(torch_model, x_tr, y_tr, x_va, y_va, dlinear_recipe(1), seed)
        lock_fit = fit_tf(tf_lock, x_tr, y_tr, x_va, y_va, seed=seed)
        p_torch, p_lock = predict(torch_model, x_te), predict_tf(tf_lock, x_te)
        tf_indep = TFDLinear(lookback, horizon, len(channels), seed=seed)
        indep_fit = fit_tf(tf_indep, x_tr, y_tr, x_va, y_va, seed=seed)
        runs.append(
            {
                "seed": seed,
                "init_max_abs_diff": init_diff,
                "torch": {**metrics(p_torch), "epochs": torch_fit.epochs, "best_epoch": torch_fit.best_epoch},
                "tf_lockstep": {**metrics(p_lock), **lock_fit},
                "lockstep_pred_max_abs_diff": float(np.max(np.abs(p_torch - p_lock))),
                "tf_independent": {**metrics(predict_tf(tf_indep, x_te)), **indep_fit},
            }
        )
        print(json.dumps(runs[-1]))

    def mean(key: str, field: str) -> float:
        return float(np.mean([r[key][field] for r in runs]))

    summary = {
        "torch_test_mse_mean": mean("torch", "test_mse"),
        "tf_lockstep_test_mse_mean": mean("tf_lockstep", "test_mse"),
        "tf_independent_test_mse_mean": mean("tf_independent", "test_mse"),
        "lockstep_mse_rel_diff_pct_max": max(
            abs(r["tf_lockstep"]["test_mse"] - r["torch"]["test_mse"]) / r["torch"]["test_mse"] * 100
            for r in runs
        ),
        "lockstep_same_best_epoch": all(
            r["tf_lockstep"]["best_epoch"] == r["torch"]["best_epoch"] for r in runs
        ),
        "independent_vs_torch_pct": (mean("tf_independent", "test_mse") - mean("torch", "test_mse"))
        / mean("torch", "test_mse")
        * 100,
        "init_max_abs_diff_max": max(r["init_max_abs_diff"] for r in runs),
    }
    summary["p15_pass"] = (
        summary["init_max_abs_diff_max"] < 1e-5
        and summary["lockstep_mse_rel_diff_pct_max"] <= 1.0
        and abs(summary["independent_vs_torch_pct"]) <= 3.0
    )
    report = {
        "dataset": dataset,
        "lookback": lookback,
        "horizon": horizon,
        "seeds": list(seeds),
        "dataset_content_sha256": manifest["content_sha256"],
        "versions": {"tensorflow": tf.__version__, "torch": torch.__version__},
        "runs": runs,
        "summary": summary,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{dataset}_h{horizon}.json").write_text(json.dumps(report, indent=1))
    return report
