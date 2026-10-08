"""Throughput and latency of POST /v1/forecast under concurrent clients (extension of protocol P13).

P13 measured one client sending requests back to back. This script keeps the same server (uvicorn,
1 worker, loopback) and the same batch-1 request, and adds N clients hitting it at once, so the
numbers say what one serving process sustains before latency climbs.

    python scripts/http_load.py --url http://127.0.0.1:8000 --levels 1,8,32 --per-client 200 \
        --out artifacts/serving/http_load.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import numpy as np


def run_level(url: str, body: dict[str, Any], clients: int, per_client: int, warmup: int) -> dict[str, Any]:
    """`clients` threads, each with its own keep-alive connection, start together after warming up."""
    start = threading.Barrier(clients + 1)

    def one_client(_: int) -> list[float]:
        latencies: list[float] = []
        with httpx.Client(base_url=url, timeout=60) as client:
            for _ in range(warmup):
                client.post("/v1/forecast", json=body).raise_for_status()
            start.wait()
            for _ in range(per_client):
                t0 = time.perf_counter()
                r = client.post("/v1/forecast", json=body)
                latencies.append((time.perf_counter() - t0) * 1000)
                r.raise_for_status()
        return latencies

    with ThreadPoolExecutor(max_workers=clients) as pool:
        futures = [pool.submit(one_client, i) for i in range(clients)]
        start.wait()
        t0 = time.perf_counter()
        samples = [ms for f in futures for ms in f.result()]
        wall = time.perf_counter() - t0
    arr = np.asarray(samples)
    return {
        "clients": clients,
        "requests": int(arr.size),
        "wall_s": wall,
        "requests_per_s": float(arr.size / wall),
        "http_ms": {
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
            "mean": float(arr.mean()),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--levels", default="1,8,32", help="comma-separated client counts")
    ap.add_argument("--per-client", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--out", default="artifacts/serving/http_load.json")
    args = ap.parse_args()

    with httpx.Client(base_url=args.url, timeout=10) as client:
        dep = client.get("/v1/deployment").json()
        ready = client.get("/ready").json()
    rng = np.random.default_rng(0)
    history = rng.normal(size=(dep["lookback"], len(dep["channels"]))).astype(float).tolist()
    body = {"history": history}

    levels: dict[str, dict[str, Any]] = {}
    for n in (int(x) for x in args.levels.split(",")):
        levels[str(n)] = run_level(args.url, body, n, args.per_client, args.warmup)
        print(
            n,
            "clients:",
            json.dumps({k: round(v, 3) for k, v in levels[str(n)]["http_ms"].items()}),
            f"{levels[str(n)]['requests_per_s']:.0f} req/s",
        )

    report = {
        "url": args.url,
        "model": ready["model"],
        "per_client": args.per_client,
        "warmup": args.warmup,
        "request": {"lookback": dep["lookback"], "channels": len(dep["channels"]), "horizon": dep["horizon"]},
        "levels": levels,
        "server": "metronome serve (uvicorn, 1 worker), loopback",
        "client": "httpx sync, one thread and keep-alive connection per client, started together",
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
