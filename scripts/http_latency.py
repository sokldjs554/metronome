"""Measure end-to-end HTTP latency of POST /v1/forecast against a running service (protocol P13).

python scripts/http_latency.py --url http://127.0.0.1:8000 --n 500 --out artifacts/serving/http_latency.json
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

import httpx
import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--warmup", type=int, default=50)
    ap.add_argument("--out", default="artifacts/serving/http_latency.json")
    args = ap.parse_args()

    with httpx.Client(base_url=args.url, timeout=10) as client:
        dep = client.get("/v1/deployment").json()
        ready = client.get("/ready").json()
        rng = np.random.default_rng(0)
        history = rng.normal(size=(dep["lookback"], len(dep["channels"]))).astype(float).tolist()
        body = {"history": history}
        for _ in range(args.warmup):
            client.post("/v1/forecast", json=body).raise_for_status()
        samples = []
        model_ms = []
        for _ in range(args.n):
            t0 = time.perf_counter()
            r = client.post("/v1/forecast", json=body)
            samples.append((time.perf_counter() - t0) * 1000)
            r.raise_for_status()
            model_ms.append(r.json()["latency_ms"])
    arr = np.asarray(samples)
    report = {
        "url": args.url,
        "model": ready["model"],
        "n": args.n,
        "warmup": args.warmup,
        "request": {"lookback": dep["lookback"], "channels": len(dep["channels"]), "horizon": dep["horizon"]},
        "http_ms": {
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
            "mean": float(arr.mean()),
        },
        "model_call_ms": {
            "p50": float(np.percentile(model_ms, 50)),
            "p95": float(np.percentile(model_ms, 95)),
        },
        "requests_per_s_serial": float(args.n / (arr.sum() / 1000)),
        "client": "httpx sync, keep-alive, loopback, serial",
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(
        json.dumps(report["http_ms"]),
        "model",
        json.dumps(report["model_call_ms"]),
        "median",
        statistics.median(samples),
    )


if __name__ == "__main__":
    main()
