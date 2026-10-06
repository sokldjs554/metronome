"""Assemble the self-contained browser demo page from the replay record and the offline evidence.

python scripts/build_demo_page.py --record artifacts/demo/replay_record.json --registry registry/etth1 \
    --out artifacts/demo/metronome-replay.html
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", default="artifacts/demo/replay_record.json")
    ap.add_argument("--registry", default="registry/etth1")
    ap.add_argument("--template", default="scripts/demo_template.html")
    ap.add_argument("--evidence", default="src/metronome/static/evidence.json")
    ap.add_argument("--summary", default="artifacts/cadence_summary.json")
    ap.add_argument("--out", default="artifacts/demo/metronome-replay.html")
    args = ap.parse_args()

    rec = json.loads(Path(args.record).read_text())
    dep = rec["deployment"]
    z = np.load(Path(args.registry) / "stream.npz")
    ts = z["timestamps"].astype("datetime64[ns]")
    values = z["values"].astype(np.float32)
    lookback, horizon = int(dep["lookback"]), int(dep["horizon"])
    start_row = int(rec["replay"]["start_row"])
    first_row = start_row - lookback
    sub = values[first_row:]
    day_labels_full = sorted({str(t)[:10] for t in ts[start_row:]})
    swap_schedule = [
        {
            "version": rec["versions"][0]["version"],
            "from_row": start_row,
            "trigger": "initial",
            "cutoff_time": rec["versions"][0]["provenance"]["cutoff_time"],
            "alarm_day": None,
        }
    ]
    for v in rec["versions"][1:]:
        prov = v["provenance"]
        alarm_day = None
        for req in rec["retrain_requests"]:
            if req.get("job") == prov.get("job_id") and req.get("alarms"):
                alarm_day = req["alarms"][0]["day"]
        swap_schedule.append(
            {
                "version": v["version"],
                "from_row": int(prov["cutoff_row"]),
                "trigger": prov.get("trigger"),
                "cutoff_time": prov["cutoff_time"],
                "alarm_day": alarm_day,
            }
        )
    evidence = json.loads(Path(args.evidence).read_text()) if Path(args.evidence).exists() else None
    summary = json.loads(Path(args.summary).read_text()) if Path(args.summary).exists() else {}
    hyp = summary.get("hypotheses", {})
    hyp_text = ""
    if hyp:
        names = {
            "H1": "재학습은 도움이 된다",
            "H2": "감시 정책이 적은 재학습으로 이득의 80%",
            "H3": "웜 스타트 1/3 비용",
            "H4": "확장 창 ≥ 슬라이딩 창",
        }
        hyp_text = "사전 등록 가설 판정 — " + ", ".join(
            f"{k}({names.get(k, k)}): {'통과' if v.get('pass') else '기각'}" for k, v in hyp.items()
        )
    demo = {
        "lookback": lookback,
        "horizon": horizon,
        "channels": dep["channels"],
        "fixed_scaler": dep["fixed_scaler"],
        "first_row": first_row,
        "start_row": start_row,
        "n_rows": len(values),
        "n_days": len(day_labels_full),
        "first_time": str(ts[first_row])[:19],
        "step_hours": 1,
        "values": [[round(float(x), 3) for x in row] for row in sub],
        "versions": rec["versions"],
        "swap_schedule": swap_schedule,
        "alarms": rec["alarms"],
        "daily_server": [{"day": d["day"], "mae": d["mae"]} for d in rec["daily"]],
        "day_labels_full": day_labels_full,
        "day_labels": [d[5:] for d in day_labels_full],
        "evidence": evidence,
        "hypotheses_text": hyp_text,
    }
    blob = json.dumps(demo, separators=(",", ":"), ensure_ascii=False)
    html = Path(args.template).read_text().replace("/*__DEMO_JSON__*/null", blob)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(
        f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB), versions={len(rec['versions'])}, swaps={len(swap_schedule) - 1}"
    )


if __name__ == "__main__":
    main()
