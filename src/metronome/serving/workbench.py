"""Workbench routes: the dashboard steps that walk data -> model comparison -> deployment.

Kept apart from app.py so the serving core (forecast, observe, verified swap) stays small. Every
route here reads the same registry and ServiceState. Nothing trains inside the API process:
candidate models are jobs the worker picks up, so the serving image stays ONNX-only. The CSV check
needs polars (the train extras); without it the route says so instead of failing oddly.
"""

from __future__ import annotations

import io
import itertools
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from metronome import __version__
from metronome.data.freq import parse_duration
from metronome.serving import gate
from metronome.serving.registry import RegistryError, VerificationError
from metronome.serving.replay import load_stream

if TYPE_CHECKING:
    from metronome.serving.app import ServiceState

FAMILIES = ("linear", "nlinear", "dlinear", "patchtst")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_ROWS = 200_000
SPARKLINE_POINTS = 120
STATIC = Path(__file__).resolve().parent.parent / "static"
TIMESTAMP_NAMES = ("timestamp", "date", "datetime", "time", "ds", "date time")


class CandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    model: str = Field(default="dlinear", description="one of " + ", ".join(FAMILIES))
    max_epochs: int = Field(default=5, ge=1, le=50)


class PromoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    force: bool = Field(default=False, description="activate even when the gate says no (recorded as forced)")
    reason: str = Field(default="dashboard", description="who asks: dashboard, worker, airflow-weekly, ...")
    champion: str | None = Field(
        default=None, description="the live version the caller compared against; refused if it changed"
    )


# ---- data --------------------------------------------------------------------------------------
def channel_stats(values: np.ndarray, channels: list[str]) -> list[dict[str, Any]]:
    out = []
    for i, name in enumerate(channels):
        col = np.asarray(values[:, i], dtype=np.float64)
        finite = np.isfinite(col)
        good = col[finite]
        out.append(
            {
                "name": name,
                "mean": float(good.mean()) if good.size else None,
                "std": float(good.std()) if good.size else None,
                "min": float(good.min()) if good.size else None,
                "max": float(good.max()) if good.size else None,
                "missing": int((~finite).sum()),
            }
        )
    return out


def sparklines(ts: np.ndarray, values: np.ndarray, points: int = SPARKLINE_POINTS) -> dict[str, Any]:
    """Bucket means so the browser can draw every channel without downloading the whole stream."""
    n = len(ts)
    if n == 0:
        return {"timestamps": [], "values": []}
    edges = np.linspace(0, n, min(points, n) + 1).astype(int)
    stamps, rows = [], []
    for a, b in itertools.pairwise(edges):
        if b <= a:
            continue
        stamps.append(str(ts[a]))
        rows.append([float(x) for x in np.nanmean(values[a:b], axis=0)])
    return {"timestamps": stamps, "values": rows}


def data_profile(state: ServiceState) -> dict[str, Any]:
    dep = state.deployment
    ts, values = load_stream(state.registry.root / "stream.npz")
    n = len(ts)
    split = int(dep.stream_start or dep.lookback)
    split = min(max(split, 0), n)
    per_day = 86400.0 / parse_duration(dep.freq).total_seconds()
    manifest_path = state.registry.root / "dataset.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    return {
        "dataset": dep.dataset,
        "freq": dep.freq,
        "lookback": dep.lookback,
        "horizon": dep.horizon,
        "channels": dep.channels,
        "n_rows": n,
        "start": str(ts[0]) if n else None,
        "end": str(ts[-1]) if n else None,
        "split": {
            "initial_rows": split,
            "stream_rows": n - split,
            "initial_days": round(split / per_day, 1),
            "stream_days": round((n - split) / per_day, 1),
            "stream_start_time": str(ts[split]) if split < n else None,
        },
        "channel_stats": channel_stats(values, dep.channels),
        "sparklines": sparklines(ts, values),
        "fixed_scaler": dep.fixed_scaler,
        "source": manifest.get("source", {}),
        "spec": manifest.get("spec", {}),
        "content_sha256": manifest.get("content_sha256"),
        "filled_rows": manifest.get("filled_rows"),
        "validation": manifest.get("validation"),
    }


def check_uploaded_csv(
    raw: bytes, freq: str, timestamp_column: str | None, *, lookback: int, horizon: int
) -> dict[str, Any]:
    """Run the pipeline's schema checks on a CSV someone uploaded; pure so tests can call it."""
    try:
        import polars as pl
    except ImportError as exc:  # serving image without the train extras
        raise HTTPException(status_code=501, detail="CSV checks need the train extras (polars)") from exc
    from metronome.data.schema import TIMESTAMP, SchemaError, validate_frame

    try:
        df = pl.read_csv(io.BytesIO(raw), infer_schema_length=10_000)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"could not parse the file as CSV: {exc}") from exc
    if df.height == 0 or not df.columns:
        raise HTTPException(status_code=422, detail="the CSV has no rows")
    if df.height > MAX_UPLOAD_ROWS:
        raise HTTPException(status_code=413, detail=f"more than {MAX_UPLOAD_ROWS:,} rows")

    col = timestamp_column
    if col is None:
        lowered = {c.lower().strip(): c for c in df.columns}
        col = next((lowered[n] for n in TIMESTAMP_NAMES if n in lowered), df.columns[0])
    if col not in df.columns:
        raise HTTPException(status_code=422, detail=f"no column named {col!r}")

    dtype = df.schema[col]
    if dtype == pl.Utf8 or dtype == pl.String:
        stamps = df[col].str.strip_chars().str.to_datetime(strict=False, time_unit="ns")
    elif dtype == pl.Date or isinstance(dtype, pl.Datetime):
        stamps = df[col].cast(pl.Datetime("ns"))
    else:
        raise HTTPException(status_code=422, detail=f"column {col!r} is {dtype}, not a timestamp")
    bad_timestamps = int(stamps.is_null().sum())
    df = df.with_columns(stamps.alias(TIMESTAMP)).filter(pl.col(TIMESTAMP).is_not_null())
    if col != TIMESTAMP:
        df = df.drop(col)

    dropped: list[str] = []
    casts = []
    for c in df.columns:
        if c == TIMESTAMP:
            continue
        if df.schema[c].is_numeric():
            casts.append(pl.col(c).cast(pl.Float64))
        elif df[c].cast(pl.Float64, strict=False).is_null().sum() == df.height:
            dropped.append(c)  # text column with no numbers in it
        else:
            casts.append(pl.col(c).cast(pl.Float64, strict=False))
    df = df.drop(dropped).with_columns(casts) if casts else df.drop(dropped)
    channels = [c for c in df.columns if c != TIMESTAMP]
    if not channels:
        raise HTTPException(status_code=422, detail="no numeric value columns next to the timestamp")

    ts = df[TIMESTAMP].to_numpy().astype("datetime64[ns]")
    out_of_order = int((np.diff(ts).astype(np.int64) < 0).sum()) if len(ts) > 1 else 0
    df = df.sort(TIMESTAMP)
    try:
        report = validate_frame(df, freq, strict=False)
    except SchemaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = report.to_dict()
    if out_of_order:
        result["non_monotonic"] = out_of_order
        result["problems"].append(f"{out_of_order} rows arrive out of order (sorted before the other checks)")
        result["ok"] = False
    if bad_timestamps:
        result["problems"].append(f"{bad_timestamps} timestamps could not be parsed (rows dropped)")
        result["ok"] = False
    values = df.select(channels).to_numpy()
    min_rows = lookback + horizon + 24 * 14
    preview = [
        {TIMESTAMP: str(r[0]), **{c: r[i + 1] for i, c in enumerate(channels)}}
        for r in df.head(5).iter_rows()
    ]
    return {
        "ok": bool(result["ok"]),
        "timestamp_column": col,
        "bad_timestamps": bad_timestamps,
        "dropped_columns": dropped,
        "report": result,
        "channel_stats": channel_stats(values, channels),
        "preview": preview,
        "enough_history": {"needed_rows": min_rows, "have_rows": int(df.height), "ok": df.height >= min_rows},
    }


# ---- models ------------------------------------------------------------------------------------
def _job_records(state: ServiceState) -> list[dict[str, Any]]:
    jobs_dir = state.registry.root / "jobs"
    if not jobs_dir.exists():
        return []
    active = state.active.model.version if state.active.model else None
    out = []
    for path in sorted(jobs_dir.glob("*.json")):
        job = json.loads(path.read_text())
        rec: dict[str, Any] = {
            "job": job.get("job_id", path.stem),
            "status": job.get("status"),
            "trigger": job.get("trigger"),
            "model": job.get("model"),
            "max_epochs": job.get("max_epochs"),
            "requested_at": job.get("requested_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "seconds": job.get("seconds"),
            "version": job.get("version"),
            "error": job.get("error"),
            "cutoff_time": job.get("cutoff_time"),
        }
        version = job.get("version")
        if version:
            try:
                m = state.registry.manifest(version)
            except RegistryError:
                m = {}
            metrics = m.get("metrics", {})
            rec["model"] = m.get("provenance", {}).get("model", rec["model"])
            rec["metrics"] = {
                "val_mae_fixed": metrics.get("val_mae_fixed"),
                "train_seconds": metrics.get("train_seconds"),
                "epochs": metrics.get("epochs"),
                "export_parity_max_abs_diff": metrics.get("export_parity_max_abs_diff"),
            }
            rec["active"] = version == active
            # The gate's own record (same windows, same scale for both models); never a comparison
            # of this candidate's validation MAE with a champion number from another period.
            rec["gate"] = state.registry.gate_record(version)
        out.append(rec)
    return out


def leaderboard(state: ServiceState) -> dict[str, Any]:
    dep = state.deployment
    evidence_path = STATIC / "evidence.json"
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    offline = [
        row
        for row in evidence.get("leaderboard", {}).get(dep.dataset, [])
        if row.get("horizon") in (None, dep.horizon)
    ]
    active = state.active.model.version if state.active.model else None
    live = []
    for v in state.registry.list_versions():
        m = state.registry.manifest(v)
        metrics, prov = m.get("metrics", {}), m.get("provenance", {})
        live.append(
            {
                "version": v,
                "model": prov.get("model"),
                "trigger": prov.get("trigger"),
                "created_at": m.get("created_at"),
                "val_mae_fixed": metrics.get("val_mae_fixed"),
                "train_seconds": metrics.get("train_seconds"),
                "epochs": metrics.get("epochs"),
                "active": v == active,
            }
        )
    return {
        "dataset": dep.dataset,
        "horizon": dep.horizon,
        "offline": offline,
        "offline_note": evidence.get("leaderboard_note"),
        "live": live,
        "families": list(FAMILIES),
    }


def model_card(state: ServiceState, version: str) -> str:
    m = state.registry.manifest(version)
    dep = state.deployment
    metrics, prov = m.get("metrics", {}), m.get("provenance", {})
    active = state.active.model.version == version if state.active.model else False
    rows = prov.get("train_rows") or [None, None]
    lines = [
        f"# Metronome 모델 카드 — {version}",
        "",
        f"- 데이터셋: {dep.dataset} ({dep.freq}, {len(dep.channels)}채널: {', '.join(dep.channels)})",
        f"- 모델: {prov.get('model', '?')}, 시드 {prov.get('seed', '?')}, "
        f"에포크 {metrics.get('epochs', '?')}, 학습 {float(metrics.get('train_seconds') or 0):.1f}s",
        f"- 학습 구간: 행 {rows[0]}–{rows[1]} (마지막 시각 {prov.get('cutoff_time', '?')}), 계기: {prov.get('trigger', '?')}",
        f"- 검증 MAE (고정 척도): {float(metrics.get('val_mae_fixed') or float('nan')):.4f}, "
        f"검증 MSE (표준화): {float(metrics.get('val_mse_standardized') or float('nan')):.4f}, 검증 구간: 마지막 14일",
        f"- PyTorch ↔ ONNX 최대 편차: {float(metrics.get('export_parity_max_abs_diff') or 0):.2e} "
        f"(허용 {m.get('parity_tolerance')})",
        f"- model.onnx SHA-256: `{m.get('onnx_sha256')}`",
        f"- reference.npz SHA-256: `{m.get('reference_sha256')}`",
        f"- 등록: {m.get('created_at')}, 현재 활성: {'예' if active else '아니오'}",
        "",
        "## 입출력 계약",
        "",
        f"- 입력 `history`: {dep.lookback} × {len(dep.channels)} 실수 행렬(원 단위, 표준화는 서버가 함)",
        f"- 출력 `forecast`: {dep.horizon} × {len(dep.channels)} (다음 {dep.horizon} 스텝, {dep.freq} 간격)",
        "- 서비스는 활성화 전에 해시와 참조 입출력을 다시 검증하고, 실패하면 교체하지 않습니다",
        "",
        "## 호출 예",
        "",
        "```bash",
        "curl -s -X POST $BASE/v1/forecast -H 'content-type: application/json' \\",
        f'  -d \'{{"history": [[...{len(dep.channels)} values...] x {dep.lookback}], "origin": "2017-07-01T00:00:00"}}\'',
        "```",
        "",
        f"_metronome {__version__}_",
    ]
    return "\n".join(lines) + "\n"


def previous_version(state: ServiceState) -> str | None:
    current = state.active.model.version if state.active.model else None
    for event in reversed(state.active.events):
        if event.to_version == current and event.from_version and event.from_version != current:
            return str(event.from_version)
    versions = state.registry.list_versions()
    if current in versions and versions.index(current) > 0:
        return versions[versions.index(current) - 1]
    return None


def replay_window(state: ServiceState) -> dict[str, Any]:
    dep = state.deployment
    rp = state.replay
    if rp is not None:
        ts, values, cursor = rp.timestamps, rp.values, rp.cursor
    else:
        ts, values = load_stream(state.registry.root / "stream.npz")
        cursor = len(ts)
    cursor = int(min(max(cursor, dep.lookback), len(ts)))
    hist = values[cursor - dep.lookback : cursor]
    nxt = values[cursor : cursor + dep.horizon]
    return {
        "origin": str(ts[cursor - 1]),
        "channels": dep.channels,
        "history": hist.tolist(),
        "history_timestamps": [str(t) for t in ts[cursor - dep.lookback : cursor]],
        "actual_next": nxt.tolist(),
        "actual_timestamps": [str(t) for t in ts[cursor : cursor + dep.horizon]],
        "replay_active": rp is not None,
    }


# ---- routes ------------------------------------------------------------------------------------
def add_workbench_routes(app: FastAPI, state: ServiceState, require_key: Any) -> None:
    @app.get("/v1/data/profile")
    def profile() -> dict[str, Any]:
        return data_profile(state)

    @app.post("/v1/data/validate")
    async def validate(
        file: UploadFile = File(...),
        freq: str | None = Form(default=None),
        timestamp_column: str | None = Form(default=None),
    ) -> dict[str, Any]:
        raw = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413, detail=f"file larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB"
            )
        dep = state.deployment
        result = check_uploaded_csv(
            raw, freq or dep.freq, timestamp_column, lookback=dep.lookback, horizon=dep.horizon
        )
        return {"filename": file.filename, "bytes": len(raw), "freq": freq or dep.freq, **result}

    @app.get("/v1/leaderboard")
    def leaderboard_route() -> dict[str, Any]:
        return leaderboard(state)

    @app.get("/v1/candidates")
    def candidates() -> dict[str, Any]:
        champion = state.active.model
        rolling = state.monitor.state().get("rolling_7d_mae")
        return {
            "champion": {
                "version": champion.version if champion else None,
                "val_mae_fixed": champion.manifest.get("metrics", {}).get("val_mae_fixed")
                if champion
                else None,
                "rolling_7d_mae": rolling,
                "gate": state.registry.gate_record(champion.version) if champion else None,
            },
            "gate_rule": {
                "window_days": gate.WINDOW_DAYS,
                "per_day": state.per_day,
                "horizon": state.deployment.horizon,
                "scale": "fixed",
                "text": "후보와 현재 모델을 후보의 학습 마감 전 14일 중 정답이 모두 도착한 날들의 같은 origin 에서 고정 척도로 비교",
            },
            "jobs": _job_records(state),
            "open_jobs": [p.stem for p in state.registry.open_jobs()],
        }

    @app.post("/v1/candidates", dependencies=[Depends(require_key)])
    def train_candidate(req: CandidateRequest) -> dict[str, Any]:
        if req.model not in FAMILIES:
            raise HTTPException(status_code=422, detail=f"model must be one of {FAMILIES}")
        if state.registry.open_jobs():
            raise HTTPException(status_code=409, detail="a retrain job is already open; wait for the worker")
        record = state.request_retrain(
            {"trigger": "candidate", "model": req.model, "max_epochs": req.max_epochs, "activate": False}
        )
        if record.get("error"):
            raise HTTPException(status_code=503, detail=record["error"])
        return record

    @app.post("/v1/candidates/promote", dependencies=[Depends(require_key)])
    def promote(req: PromoteRequest) -> Any:
        """Integrity, then the gate (candidate vs the live model on the same resolved windows),
        then the swap. 200 = went live, 409 = kept (the record says why), 422 = integrity failed."""
        from metronome.serving.app import PromotionRefused

        try:
            state.registry.manifest(req.version)
        except RegistryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            record = state.promote(
                req.version, via=req.reason, force=req.force, expected_champion=req.champion
            )
        except PromotionRefused as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except VerificationError as exc:
            raise HTTPException(status_code=422, detail=f"refused: {exc}") from exc
        if not record["applied"]:
            return JSONResponse(status_code=409, content={"detail": f"gate: {record['reason']}", **record})
        return record

    @app.get("/v1/models/{version}")
    def model_detail(version: str) -> dict[str, Any]:
        try:
            manifest = state.registry.manifest(version)
        except RegistryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        active = state.active.model.version == version if state.active.model else False
        return {**manifest, "active": active}

    @app.get("/v1/models/{version}/card", response_class=PlainTextResponse)
    def model_card_route(version: str) -> PlainTextResponse:
        try:
            text = model_card(state, version)
        except RegistryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return PlainTextResponse(
            text,
            media_type="text/markdown; charset=utf-8",
            headers={"content-disposition": f'inline; filename="metronome-{version}-card.md"'},
        )

    @app.post("/v1/models/rollback", dependencies=[Depends(require_key)])
    def rollback() -> dict[str, Any]:
        """Explicit return to the previous version: integrity check and swap, no gate; recorded as
        `rollback` so it is never read as a gate pass."""
        prev = previous_version(state)
        if prev is None:
            raise HTTPException(status_code=409, detail="no earlier version to roll back to")
        try:
            activation = state.activate(prev, reason="rollback")
        except VerificationError as exc:
            raise HTTPException(status_code=422, detail=f"refused: {exc}") from exc
        state.record_override(prev, "rollback", "rollback", activation)
        return {"rolled_back_to": prev, **activation}

    @app.get("/v1/replay/window")
    def window() -> dict[str, Any]:
        return replay_window(state)

    @app.get("/v1/workbench")
    def workbench_summary() -> dict[str, Any]:
        """One call for the dashboard header: what is deployed, what is pending, since when."""
        return {
            "version": __version__,
            "dataset": state.deployment.dataset,
            "active": state.active.model.version if state.active.model else None,
            "versions": len(state.registry.list_versions()),
            "open_jobs": [p.stem for p in state.registry.open_jobs()],
            "uptime_s": time.time() - state.started_at,
        }
