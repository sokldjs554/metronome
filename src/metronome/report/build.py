"""Aggregate cadence and LTSF artifacts across seeds, judge the pre-registered hypotheses, and write
`artifacts/cadence_summary.json`, `artifacts/ltsf_summary.json`, charts and `static/evidence.json`.

Documents under docs/ quote these summaries through `<!-- num:... -->` markers, so a regenerated
summary that changes a number makes the numbers check fail until the prose is updated too.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from metronome.report.svg import Point, Series, line_chart, pareto_chart

REPRESENTATIVE = ("ratio-0.2", "ph-0.1", "adwin-0.01")
CACHE_RE = re.compile(r"^(?P<dataset>[a-z0-9]+)_(?P<model>[a-z]+)_s(?P<seed>\d+)(?:_(?P<variant>[a-z]+))?$")


def _mean(xs: list[float]) -> float:
    return float(statistics.fmean(xs)) if xs else float("nan")


def _policy_kind(policy: str) -> str:
    return policy.split("+")[0].split("-")[0]


def _is_gated(policy: str) -> bool:
    return policy.endswith("+gate")


def summarize_cadence(cadence_dir: Path) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(cadence_dir.glob("*.json")):
        data = json.loads(path.read_text())
        m = CACHE_RE.match(data["cache"])
        if not m:
            continue
        variant = m.group("variant") or "expanding"
        groups[(m.group("dataset"), m.group("model"), variant)].append(data)

    datasets: dict[str, Any] = {}
    for (dataset, model, variant), seeds in sorted(groups.items()):
        policies_present = sorted({p for s in seeds for p in s["policies"]}, key=_policy_sort_key)
        policies: dict[str, Any] = {}
        for policy in policies_present:
            rows = [s["policies"][policy] for s in seeds if policy in s["policies"]]
            never = [s["policies"]["never"]["mae"] for s in seeds if policy in s["policies"]]
            daily = [s["policies"]["periodic-1"]["mae"] for s in seeds if policy in s["policies"]]
            maes = [r["mae"] for r in rows]
            comp_never = [
                c
                for s in seeds
                for c in s["comparisons"]
                if c["policy"] == policy and c["reference"] == "never"
            ]
            comp_daily = [
                c
                for s in seeds
                for c in s["comparisons"]
                if c["policy"] == policy and c["reference"] == "periodic-1"
            ]
            gain = [
                (n - m_) / (n - d) if (n - d) > 0 else float("nan")
                for n, d, m_ in zip(never, daily, maes, strict=True)
            ]
            policies[policy] = {
                "kind": _policy_kind(policy),
                "gated": _is_gated(policy),
                "n_seeds": len(rows),
                "mae_mean": _mean(maes),
                "mae_min": min(maes),
                "mae_max": max(maes),
                "mse_mean": _mean([r["mse"] for r in rows]),
                "n_refits_mean": _mean([r["n_refits"] for r in rows]),
                "n_trained_mean": _mean([r.get("n_trained", r["n_refits"]) for r in rows]),
                "n_refits_min": min(r["n_refits"] for r in rows),
                "n_refits_max": max(r["n_refits"] for r in rows),
                "train_seconds_mean": _mean([r["train_seconds"] for r in rows]),
                "improvement_vs_never_pct": _mean(
                    [(n - m_) / n * 100 for n, m_ in zip(never, maes, strict=True)]
                ),
                "gain_fraction_of_daily": _mean([g for g in gain if g == g])
                if any(g == g for g in gain)
                else None,
                "ci_vs_never": _ci(comp_never),
                "ci_vs_daily": _ci(comp_daily),
            }
        datasets.setdefault(dataset, {})[variant] = {
            "model": model,
            "seeds": sorted(s["seed"] for s in seeds),
            "n_days": len(seeds[0]["policies"]["never"]["daily_mae"]),
            "policies": policies,
        }
    summary = {"datasets": datasets, "representative": list(REPRESENTATIVE)}
    summary["hypotheses"] = judge_hypotheses(summary)
    return summary


def _ci(comps: list[dict[str, Any]]) -> dict[str, float] | None:
    if not comps:
        return None
    return {
        "diff_mean": _mean([c["diff"] for c in comps]),
        "lo_mean": _mean([c["lo"] for c in comps]),
        "hi_mean": _mean([c["hi"] for c in comps]),
        "all_seeds_hi_below_zero": all(c["hi"] < 0 for c in comps),
    }


def _policy_sort_key(p: str) -> tuple[int, float, int]:
    base, _, gate = p.partition("+")
    kind, _, val = base.partition("-")
    order = {"never": 0, "periodic": 1, "warm": 2, "ratio": 3, "ph": 4, "adwin": 5}
    try:
        v = float(val)
    except ValueError:
        v = 0.0
    return order.get(kind, 9), v, 1 if gate else 0


def judge_hypotheses(summary: dict[str, Any]) -> dict[str, Any]:
    ds = summary["datasets"]
    out: dict[str, Any] = {}
    # H1: periodic-1 < never on every dataset with CI upper bound < 0
    h1_rows = {}
    for name, variants in ds.items():
        pol = variants.get("expanding", {}).get("policies", {})
        if "periodic-1" in pol and pol["periodic-1"]["ci_vs_never"]:
            ci = pol["periodic-1"]["ci_vs_never"]
            h1_rows[name] = {
                "mae_never": pol["never"]["mae_mean"],
                "mae_daily": pol["periodic-1"]["mae_mean"],
                "improvement_pct": pol["periodic-1"]["improvement_vs_never_pct"],
                "ci_hi": ci["hi_mean"],
                "pass": pol["periodic-1"]["mae_mean"] < pol["never"]["mae_mean"] and ci["hi_mean"] < 0,
            }
    out["H1"] = {"rows": h1_rows, "pass": bool(h1_rows) and all(r["pass"] for r in h1_rows.values())}
    # H2: a representative triggered policy reaches >= 80% of the daily gain with <= 91 refits
    h2_rows = {}
    for name, variants in ds.items():
        pol = variants.get("expanding", {}).get("policies", {})
        best = None
        for rep in REPRESENTATIVE:
            if rep in pol and pol[rep]["gain_fraction_of_daily"] is not None:
                row = {
                    "policy": rep,
                    "gain_fraction": pol[rep]["gain_fraction_of_daily"],
                    "n_refits": pol[rep]["n_refits_mean"],
                    "pass": pol[rep]["gain_fraction_of_daily"] >= 0.8 and pol[rep]["n_refits_mean"] <= 91,
                }
                if (
                    best is None
                    or (row["pass"] and not best["pass"])
                    or (row["pass"] == best["pass"] and row["gain_fraction"] > best["gain_fraction"])
                ):
                    best = row
        if best:
            h2_rows[name] = best
    out["H2"] = {"rows": h2_rows, "pass": any(r["pass"] for r in h2_rows.values())}
    # H3: warm-1 within +1% MAE of periodic-1 at <= 1/3 of the training seconds (etth1, etth2)
    h3_rows = {}
    for name in ("etth1", "etth2"):
        pol = ds.get(name, {}).get("expanding", {}).get("policies", {})
        if "warm-1" in pol and "periodic-1" in pol:
            w, c = pol["warm-1"], pol["periodic-1"]
            h3_rows[name] = {
                "mae_warm": w["mae_mean"],
                "mae_cold": c["mae_mean"],
                "seconds_warm": w["train_seconds_mean"],
                "seconds_cold": c["train_seconds_mean"],
                "pass": w["mae_mean"] <= c["mae_mean"] * 1.01
                and w["train_seconds_mean"] <= c["train_seconds_mean"] / 3,
            }
    out["H3"] = {"rows": h3_rows, "pass": bool(h3_rows) and all(r["pass"] for r in h3_rows.values())}
    # H4: expanding periodic-7 <= sliding periodic-7 (etth1, etth2)
    h4_rows = {}
    for name in ("etth1", "etth2"):
        v = ds.get(name, {})
        if "expanding" in v and "sliding" in v and "periodic-7" in v["sliding"]["policies"]:
            e, s = (
                v["expanding"]["policies"]["periodic-7"]["mae_mean"],
                v["sliding"]["policies"]["periodic-7"]["mae_mean"],
            )
            h4_rows[name] = {"mae_expanding": e, "mae_sliding": s, "pass": e <= s}
    out["H4"] = {"rows": h4_rows, "pass": bool(h4_rows) and all(r["pass"] for r in h4_rows.values())}
    return out


def summarize_ltsf(runs_dir: Path, paper_reference: Path | None) -> dict[str, Any]:
    paper = json.loads(paper_reference.read_text()) if paper_reference and paper_reference.exists() else {}
    runs: dict[str, Any] = {}
    for path in sorted(runs_dir.glob("*.json")):
        r = json.loads(path.read_text())
        cfg = r["config"]
        key = f"{cfg['dataset']}/{cfg['model']}/{cfg['horizon']}"
        entry: dict[str, Any] = {
            "dataset": cfg["dataset"],
            "model": cfg["model"],
            "lookback": cfg["lookback"],
            "horizon": cfg["horizon"],
            "seed": cfg["seed"],
            "mse": r["metrics"]["mse"],
            "mae": r["metrics"]["mae"],
            "epochs": (r.get("fit") or {}).get("epochs"),
            "train_seconds": (r.get("fit") or {}).get("seconds"),
            "n_parameters": r["n_parameters"],
        }
        paper_key = {
            "dlinear": "dlinear",
            "nlinear": "nlinear",
            "linear": "linear",
            "patchtst": "patchtst42",
        }.get(cfg["model"])
        ref = paper.get(paper_key or "", {}).get(cfg["dataset"], {}).get(str(cfg["horizon"]))
        if ref:
            entry["paper"] = ref
            entry["mse_rel_diff_pct"] = (entry["mse"] - ref["mse"]) / ref["mse"] * 100
            entry["mae_rel_diff_pct"] = (entry["mae"] - ref["mae"]) / ref["mae"] * 100
            entry["within_3pct"] = abs(entry["mse_rel_diff_pct"]) <= 3.0
        runs[key] = entry
    return {
        "runs": runs,
        "paper_source": {k: v.get("source") for k, v in paper.items() if isinstance(v, dict)},
    }


def build_charts(cadence_dir: Path, summary: dict[str, Any], charts_dir: Path) -> list[Path]:
    written = []
    for dataset, variants in summary["datasets"].items():
        pol = variants.get("expanding", {}).get("policies")
        if not pol:
            continue
        points = []
        for policy, p in pol.items():
            if policy == "warm-1":
                continue
            points.append(
                Point(p["n_refits_mean"], p["mae_mean"], policy, p["kind"], p["mae_min"], p["mae_max"])
            )
        written.append(
            pareto_chart(
                points,
                charts_dir / f"pareto_{dataset}.svg",
                f"{dataset}: 재학습 횟수 대 스트림 MAE (시드 {len(variants['expanding']['seeds'])}개 평균, 막대 = 최소–최대)",
            )
        )
    # error-over-time example: first seed of the first dataset, never vs periodic-7 vs periodic-1
    for dataset in summary["datasets"]:
        path = cadence_dir / f"{dataset}_dlinear_s0.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        series = []
        for policy, color in (("never", "#8a8f8c"), ("periodic-7", "#1f6f5f"), ("periodic-1", "#c8742b")):
            if policy not in data["policies"]:
                continue
            daily = np.array(data["policies"][policy]["daily_mae"], dtype=float)
            # 14-day rolling mean for readability
            k = 14
            smooth = np.convolve(np.nan_to_num(daily), np.ones(k) / k, mode="valid")
            series.append(Series(policy, list(range(k - 1, len(daily))), smooth.tolist(), color))
        if series:
            written.append(
                line_chart(
                    series,
                    charts_dir / f"daily_{dataset}.svg",
                    f"{dataset} 시드 0: 일별 MAE (14일 이동평균)",
                    "스트림 일자",
                    "MAE (고정 척도)",
                )
            )
    return written


def write_evidence(summary: dict[str, Any], path: Path) -> Path:
    datasets = {}
    for dataset, variants in summary["datasets"].items():
        pol = variants.get("expanding", {}).get("policies")
        if not pol:
            continue
        rows = [
            {"policy": k, "mae": v["mae_mean"], "n_refits": v["n_refits_mean"]}
            for k, v in pol.items()
            if k != "warm-1"
        ]
        rep = summary["hypotheses"]["H2"]["rows"].get(dataset)
        rep_row = next((r for r in rows if rep and r["policy"] == rep["policy"]), None)
        datasets[dataset] = {"policies": rows, "representative": rep_row}
    note = "사전 등록 프로토콜(docs/protocol.md)의 오프라인 실험. DLinear 콜드 재학습 캐시, 시드 3개 평균, 고정 척도 MAE."
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"note": note, "datasets": datasets}, indent=1, ensure_ascii=False))
    return path


def build_all(root: Path) -> dict[str, Any]:
    cadence_dir = root / "artifacts" / "cadence"
    summary = summarize_cadence(cadence_dir) if cadence_dir.exists() else {"datasets": {}, "hypotheses": {}}
    (root / "artifacts" / "cadence_summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False)
    )
    ltsf = summarize_ltsf(root / "artifacts" / "runs", root / "artifacts" / "paper_reference.json")
    (root / "artifacts" / "ltsf_summary.json").write_text(json.dumps(ltsf, indent=1, ensure_ascii=False))
    charts = (
        build_charts(cadence_dir, summary, root / "docs" / "assets" / "charts") if summary["datasets"] else []
    )
    evidence = write_evidence(summary, root / "src" / "metronome" / "static" / "evidence.json")
    return {
        "cadence_summary": summary,
        "ltsf_summary": ltsf,
        "charts": [str(c) for c in charts],
        "evidence": str(evidence),
    }
