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
    """Pull the two linear layers out of a DLinear ONNX graph.

    torch.onnx exports nn.Linear as MatMul(x, W^T) + Add(bias); the transposed weight gets an
    anonymous initializer name (onnx::MatMul_N), so each weight is resolved through the Add node
    that consumes it, keyed by the bias name (seasonal.proj.bias / trend.proj.bias).
    """
    model = onnx.load(str(onnx_path))
    inits = {t.name: numpy_helper.to_array(t) for t in model.graph.initializer}
    matmul_weight = {}  # output tensor name -> initializer array (lookback, horizon)
    for node in model.graph.node:
        if node.op_type == "MatMul" and node.input[1] in inits:
            matmul_weight[node.output[0]] = inits[node.input[1]]
    picked: dict[str, np.ndarray] = {}
    for node in model.graph.node:
        if node.op_type != "Add":
            continue
        bias = [i for i in node.input if i in inits and inits[i].ndim == 1]
        prod = [i for i in node.input if i in matmul_weight]
        if len(bias) != 1 or len(prod) != 1:
            continue
        branch = (
            "seasonal" if "seasonal" in bias[0].lower() else "trend" if "trend" in bias[0].lower() else None
        )
        if branch is None:
            continue
        picked[f"{branch}_w"] = matmul_weight[prod[0]].T  # -> (horizon, lookback)
        picked[f"{branch}_b"] = inits[bias[0]]
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
    ap.add_argument(
        "--collect-only",
        action="store_true",
        help="do not replay; read the finished replay state from the running server",
    )
    args = ap.parse_args()
    reg = Path(args.registry)
    c = httpx.Client(base_url=args.url, timeout=120)
    dep = c.get("/v1/deployment").json()
    steps: list[dict[str, object]] = []
    alarms: list[dict[str, object]] = []
    requests: list[dict[str, object]] = []
    t0 = time.time()
    blocked_total = 0.0
    if args.collect_only:
        state = c.get("/v1/replay").json()
        start = {"cursor": state["started_at"], "n_rows": state["n_rows"]}
        steps = [{"cursor": state["cursor"], "time": state["current_time"], "stepped": state["steps"]}]
        requests = c.get("/v1/events").json()["retrain_requests"]
        # With wait_for_retrain every alarm turned into a request, so the requests carry all alarms.
        alarms = [a for r in requests for a in r.get("alarms", [])]
    else:
        start = c.post("/v1/replay/start", json={}).json()
        print("replay start", start["cursor"], "/", start["n_rows"])
    while not args.collect_only:
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
