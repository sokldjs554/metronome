"""Replay the whole held-out stream through a running API + worker and record everything the
browser demo needs: alarms, retrain requests, swaps, per-day MAE, and every version's weights.

python scripts/record_replay.py --url http://127.0.0.1:8000 --registry registry/etth1 --out artifacts/demo/replay_record.json
"""

from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

import httpx
import numpy as np
import onnx
from onnx import numpy_helper


def dlinear_weights(onnx_path: Path) -> dict[str, object]:
    """Pull the two linear layers out of a DLinear ONNX graph (names from torch.onnx export)."""
    model = onnx.load(str(onnx_path))
    inits = {t.name: numpy_helper.to_array(t) for t in model.graph.initializer}
    picked: dict[str, np.ndarray] = {}
    for name, arr in inits.items():
        key = name.lower()
        if "seasonal" in key and arr.ndim == 2:
            picked["seasonal_w"] = arr
        elif "seasonal" in key and arr.ndim == 1:
            picked["seasonal_b"] = arr
        elif "trend" in key and arr.ndim == 2:
            picked["trend_w"] = arr
        elif "trend" in key and arr.ndim == 1:
            picked["trend_b"] = arr
    if len(picked) != 4:
        raise RuntimeError(f"unexpected initializers in {onnx_path}: {list(inits)}")

    def b64(a: np.ndarray) -> str:
        return base64.b64encode(np.ascontiguousarray(a, dtype=np.float32).tobytes()).decode()

    h, lb = picked["seasonal_w"].shape
    return {
        "horizon": int(h),
        "lookback": int(lb),
        "seasonal_w": b64(picked["seasonal_w"]),
        "seasonal_b": b64(picked["seasonal_b"]),
        "trend_w": b64(picked["trend_w"]),
        "trend_b": b64(picked["trend_b"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--registry", default="registry/etth1")
    ap.add_argument("--out", default="artifacts/demo/replay_record.json")
    ap.add_argument("--step", type=int, default=24)
    args = ap.parse_args()
    reg = Path(args.registry)
    c = httpx.Client(base_url=args.url, timeout=120)
    dep = c.get("/v1/deployment").json()
    start = c.post("/v1/replay/start", json={}).json()
    print("replay start", start["cursor"], "/", start["n_rows"])
    steps: list[dict[str, object]] = []
    alarms: list[dict[str, object]] = []
    requests: list[dict[str, object]] = []
    t0 = time.time()
    blocked_total = 0.0
    while True:
        r = c.post("/v1/replay/step", json={"steps": args.step}).json()
        if r["blocked_on_retrain"]:
            blocked_total += 1.0
            time.sleep(1.0)
            continue
        pos = r["position"]
        alarms.extend(r["alarms"])
        requests.extend(r["retrain_requests"])
        steps.append({"cursor": pos["cursor"], "time": pos["current_time"], "stepped": r["stepped"]})
        if r["stepped"] == 0 or pos["cursor"] >= pos["n_rows"]:
            break
        if len(steps) % 30 == 0:
            print(
                f"  {pos['current_time'][:10]} alarms={len(alarms)} requests={len(requests)} {time.time() - t0:.0f}s"
            )
    events = c.get("/v1/events").json()
    models = c.get("/v1/models").json()
    monitor = c.get("/v1/monitor").json()
    versions = []
    for v in models["versions"]:
        manifest = json.loads((reg / "versions" / v["version"] / "manifest.json").read_text())
        versions.append(
            {
                "version": v["version"],
                "created_at": manifest["created_at"],
                "scaler": manifest["scaler"],
                "metrics": manifest["metrics"],
                "provenance": manifest["provenance"],
                "onnx_sha256": manifest["onnx_sha256"],
                "weights": dlinear_weights(reg / "versions" / v["version"] / "model.onnx"),
            }
        )
    record = {
        "deployment": dep,
        "replay": {
            "start_row": start["cursor"],
            "n_rows": start["n_rows"],
            "steps": len(steps),
            "wall_seconds": time.time() - t0,
            "waited_for_worker_s": blocked_total,
        },
        "alarms": alarms,
        "retrain_requests": requests,
        "swaps": events["swaps"],
        "daily": monitor["daily"],
        "detectors": [d["name"] for d in monitor["detectors"]],
        "versions": versions,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record))
    print(
        f"done: {len(steps)} steps, {len(alarms)} alarms, {len(requests)} retrain requests, "
        f"{len(events['swaps'])} swaps, {len(versions)} versions, {time.time() - t0:.0f}s -> {out}"
    )


if __name__ == "__main__":
    main()
