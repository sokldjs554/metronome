"""Before/after table for the 2026-10-09 correction (docs/protocol.md change log): the policy
numbers of the committed cadence results against a fresh simulation, per dataset (expanding
window, pre-registered seeds 0-2 unless --seeds says otherwise).

    python scripts/review_before_after.py artifacts/cadence_before artifacts/cadence --seeds 0 1 2
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

NAME = re.compile(r"^(?P<dataset>[a-z0-9]+)_dlinear_s(?P<seed>\d+)(?P<variant>_sliding)?$")
POLICIES = (
    "never",
    "periodic-1",
    "periodic-7",
    "periodic-7+gate",
    "ratio-0.2",
    "ratio-0.2+gate",
    "ph-0.1",
    "ph-0.1+gate",
    "adwin-0.01",
)


def load(dir_: Path, seeds: set[int]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(dir_.glob("*.json")):
        m = NAME.match(path.stem)
        if not m or m.group("variant") or int(m.group("seed")) not in seeds:
            continue
        out[m.group("dataset")].append(json.loads(path.read_text())["policies"])
    return out


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    args = ap.parse_args()
    before, after = load(args.before, set(args.seeds)), load(args.after, set(args.seeds))
    print("| 데이터셋 | 정책 | MAE 전 → 후 | 교체 전 → 후 | 학습 전 → 후 | 거절 후(사유) |")
    print("|---|---|---|---|---|---|")
    for dataset in sorted(after):
        for policy in POLICIES:
            b = [s[policy] for s in before.get(dataset, []) if policy in s]
            a = [s[policy] for s in after[dataset] if policy in s]
            if not a:
                continue
            fb = f"{mean([r['mae'] for r in b]):.4f}" if b else "—"
            rb = f"{mean([r['n_refits'] for r in b]):.1f}" if b else "—"
            tb = f"{mean([r.get('n_trained', r['n_refits']) for r in b]):.1f}" if b else "—"
            reasons: dict[str, float] = defaultdict(float)
            for r in a:
                for k, v in r.get("rejections", {}).items():
                    reasons[k] += v / len(a)
            why = ", ".join(f"{k} {v:.1f}" for k, v in sorted(reasons.items())) or "—"
            print(
                f"| {dataset} | {policy} | {fb} → {mean([r['mae'] for r in a]):.4f} | {rb} → {mean([r['n_refits'] for r in a]):.1f} "
                f"| {tb} → {mean([r.get('n_trained', r['n_refits']) for r in a]):.1f} | {why} |"
            )


if __name__ == "__main__":
    main()
