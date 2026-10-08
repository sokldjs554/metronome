"""FastAPI service: forecasts from the active ONNX model, residual monitoring, zero-downtime swaps.

The process never trains. When the monitor (or a schedule) asks for a retrain, it writes a job
into the registry and keeps serving the current model; a separate worker trains, registers and
activates the replacement through this API.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Annotated, Any

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from metronome import __version__
from metronome.data.freq import parse_duration
from metronome.serving.model import ActiveModel, ServingModel
from metronome.serving.monitor import ResidualMonitor
from metronome.serving.registry import Registry, RegistryError, VerificationError
from metronome.serving.replay import ReplayState, load_stream

LOGGER = logging.getLogger("metronome.serving")
STATIC = Path(__file__).resolve().parent.parent / "static"


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    history: list[list[FiniteFloat]] = Field(min_length=1, max_length=4096)
    origin: str | None = Field(default=None, description="ISO timestamp of the last history row")
    record: bool = True


class ObserveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: str
    values: list[FiniteFloat] = Field(min_length=1, max_length=4096)


class ReplayStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str | None = None
    start_row: int | None = Field(default=None, ge=0)
    schedule_days: int | None = Field(default=None, ge=1)
    wait_for_retrain: bool = True


class ReplayStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: int = Field(default=24, ge=1, le=24 * 60)


class ServiceState:
    def __init__(
        self, registry: Registry, threads: int, detector_specs: tuple[str, ...], auto_retrain: bool
    ) -> None:
        self.registry = registry
        self.threads = threads
        self.deployment = registry.deployment()
        self.active = ActiveModel()
        self.auto_retrain = auto_retrain
        step_ns = int(parse_duration(self.deployment.freq).total_seconds() * 1e9)
        fixed = self.deployment.fixed_scaler
        self.monitor = ResidualMonitor(
            horizon=self.deployment.horizon,
            step_ns=step_ns,
            fixed_mean=np.asarray(fixed["mean"]),
            fixed_std=np.asarray(fixed["std"]),
            detector_specs=detector_specs,
        )
        self.replay: ReplayState | None = None
        self.started_at = time.time()
        self.retrain_requests: list[dict[str, Any]] = []
        self.load_error: str | None = None
        reg = CollectorRegistry()
        self.prom = reg
        self.m_requests = Counter(
            "metronome_forecast_requests_total", "forecast requests", ["version"], registry=reg
        )
        self.m_latency = Histogram(
            "metronome_forecast_latency_seconds",
            "forecast latency",
            buckets=(0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.5),
            registry=reg,
        )
        self.m_swaps = Counter("metronome_model_swaps_total", "model hot swaps", registry=reg)
        self.m_rolling = Gauge("metronome_rolling_7d_mae", "rolling 7-day MAE (fixed scale)", registry=reg)
        self.m_active = Gauge("metronome_active_version_info", "active version", ["version"], registry=reg)

    def load_active(self) -> None:
        version = self.registry.active()
        if version is None:
            self.load_error = "registry has no ACTIVE version"
            return
        try:
            self.activate(version, reason="startup")
            self.load_error = None
        except (VerificationError, RegistryError) as exc:
            self.load_error = str(exc)
            LOGGER.error("refusing to serve %s: %s", version, exc)

    def activate(self, version: str, reason: str) -> dict[str, Any]:
        model = ServingModel(self.registry, version, threads=self.threads)  # verifies, raises on mismatch
        self.registry.activate(version)
        event = self.active.swap(model, reason=reason)
        self.monitor.set_baseline(model.manifest.get("metrics", {}).get("val_mae_fixed"), version=version)
        self.m_swaps.inc()
        self.m_active.clear()
        self.m_active.labels(version=version).set(1)
        return {
            "from": event.from_version,
            "to": event.to_version,
            "reason": reason,
            "parity_max_abs_diff": model.verification["max_abs_diff"],
        }

    def request_retrain(self, reason: dict[str, Any]) -> dict[str, Any]:
        cutoff = self.replay.cursor if self.replay is not None else None
        current = self.replay.position().get("current_time") if self.replay is not None else None
        payload = {
            **reason,
            "cutoff_row": cutoff,
            "cutoff_time": current,
            "active_version": self.active.model.version if self.active.model else None,
        }
        try:
            path = self.registry.request_retrain(payload)
        except OSError as exc:  # read-only registry mount: keep serving, report the hand-off failure
            LOGGER.error("cannot write retrain job to %s: %s", self.registry.root, exc)
            return {"job": None, "error": f"registry not writable: {exc.strerror or exc}", **payload}
        record = {"job": path.stem, **payload}
        self.retrain_requests.append(record)
        return record


def create_app(
    registry_root: Path,
    *,
    api_key: str | None = None,
    threads: int = 1,
    detector_specs: tuple[str, ...] = ("ratio-0.2", "ph-0.1", "adwin-0.01"),
    auto_retrain: bool = True,
) -> FastAPI:
    state = ServiceState(Registry(registry_root), threads, detector_specs, auto_retrain)
    state.load_active()
    app = FastAPI(title="Metronome", version=__version__, docs_url="/docs")
    app.state.service = state

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo the offending input back: a NaN/Inf in the body would make the default
        # handler's JSON response fail (500) instead of returning 422.
        errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    api_key = api_key if api_key is not None else os.environ.get("METRONOME_API_KEY")

    def require_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if api_key and x_api_key != api_key:
            raise HTTPException(status_code=401, detail="invalid API key")

    # ---- liveness / readiness ----------------------------------------------------------------
    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "uptime_s": time.time() - state.started_at}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        if state.active.model is None:
            raise HTTPException(status_code=503, detail=state.load_error or "no active model")
        return {"ready": True, "model": state.active.model.version}

    @app.get("/v1/deployment")
    def deployment() -> dict[str, Any]:
        return state.deployment.to_dict()

    # ---- models --------------------------------------------------------------------------------
    @app.get("/v1/models")
    def models() -> dict[str, Any]:
        out = []
        for v in state.registry.list_versions():
            m = state.registry.manifest(v)
            out.append(
                {
                    "version": v,
                    "created_at": m.get("created_at"),
                    "metrics": m.get("metrics", {}),
                    "provenance": m.get("provenance", {}),
                    "onnx_sha256": m["onnx_sha256"],
                }
            )
        active = state.active.model.summary() if state.active.model else None
        return {"active": active, "versions": out, "load_error": state.load_error}

    @app.post("/v1/models/{version}/activate", dependencies=[Depends(require_key)])
    def activate(version: str, reason: str = "manual") -> dict[str, Any]:
        try:
            return state.activate(version, reason=reason)
        except VerificationError as exc:
            raise HTTPException(status_code=422, detail=f"refused: {exc}") from exc
        except RegistryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/models/reload", dependencies=[Depends(require_key)])
    def reload() -> dict[str, Any]:
        wanted = state.registry.active()
        current = state.active.model.version if state.active.model else None
        if wanted is None:
            raise HTTPException(status_code=404, detail="registry has no ACTIVE version")
        if wanted == current:
            return {"changed": False, "active": current}
        try:
            return {"changed": True, **state.activate(wanted, reason="reload")}
        except VerificationError as exc:
            raise HTTPException(status_code=422, detail=f"refused: {exc}") from exc

    # ---- inference -----------------------------------------------------------------------------
    @app.post("/v1/forecast")
    def forecast(req: ForecastRequest) -> dict[str, Any]:
        if state.active.model is None:
            raise HTTPException(status_code=503, detail="no active model")
        model = state.active.model  # hold this reference for the whole request
        hist = np.asarray(req.history, dtype=np.float32)
        if hist.shape != (model.lookback, len(model.channels)):
            raise HTTPException(
                status_code=422,
                detail=f"history must be {model.lookback} x {len(model.channels)}, got {list(hist.shape)}",
            )
        t0 = time.perf_counter()
        out = model.forecast(hist[None])[0]
        latency = time.perf_counter() - t0
        state.m_requests.labels(version=model.version).inc()
        state.m_latency.observe(latency)
        response: dict[str, Any] = {
            "model_version": model.version,
            "forecast": out.tolist(),
            "channels": model.channels,
            "latency_ms": latency * 1000.0,
        }
        if req.origin is not None:
            try:
                origin = np.datetime64(req.origin, "ns")
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"bad origin timestamp: {exc}") from exc
            step = np.timedelta64(state.monitor.step_ns, "ns")
            response["timestamps"] = [str(origin + step * (h + 1)) for h in range(model.horizon)]
            if req.record:
                state.monitor.record_forecast(origin, model.version, out)
        return response

    @app.post("/v1/observe")
    def observe(req: ObserveRequest) -> dict[str, Any]:
        if len(req.values) != len(state.deployment.channels):
            raise HTTPException(status_code=422, detail=f"expected {len(state.deployment.channels)} values")
        try:
            ts = np.datetime64(req.timestamp, "ns")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"bad timestamp: {exc}") from exc
        result = state.monitor.observe(ts, np.asarray(req.values, dtype=np.float32))
        rolling = state.monitor.state()["rolling_7d_mae"]
        if rolling is not None:
            state.m_rolling.set(rolling)
        result["retrain_requested"] = None
        if result["alarms"] and state.auto_retrain and not state.registry.open_jobs():
            result["retrain_requested"] = state.request_retrain(
                {"trigger": "detector", "alarms": result["alarms"]}
            )
        return result

    # ---- monitoring ----------------------------------------------------------------------------
    @app.get("/v1/monitor")
    def monitor() -> dict[str, Any]:
        return {
            "active_version": state.active.model.version if state.active.model else None,
            "pending_jobs": [p.stem for p in state.registry.open_jobs()],
            **state.monitor.state(),
        }

    @app.get("/v1/events")
    def events() -> dict[str, Any]:
        return {
            "swaps": [
                {"at": e.at, "from": e.from_version, "to": e.to_version, "reason": e.reason}
                for e in state.active.events
            ],
            "retrain_requests": state.retrain_requests[-50:],
        }

    @app.get("/metrics")
    def metrics() -> PlainTextResponse:
        return PlainTextResponse(generate_latest(state.prom).decode(), media_type=CONTENT_TYPE_LATEST)

    # ---- replay (demo / integration) ---------------------------------------------------------
    @app.post("/v1/replay/start", dependencies=[Depends(require_key)])
    def replay_start(req: ReplayStartRequest) -> dict[str, Any]:
        path = (
            Path(req.path)
            if req.path
            else Path(os.environ.get("METRONOME_STREAM", state.registry.root / "stream.npz"))
        )
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"stream file {path} not found")
        ts, values = load_stream(path)
        if values.shape[1] != len(state.deployment.channels):
            raise HTTPException(status_code=422, detail="stream channel count does not match deployment")
        default_start = state.deployment.stream_start or state.deployment.lookback
        start = req.start_row if req.start_row is not None else default_start
        start = max(start, state.deployment.lookback)
        state.replay = ReplayState(
            path, ts, values, cursor=start, started_at=start, retrain_schedule_days=req.schedule_days
        )
        # the active model counts as freshly deployed at the start of the replay
        state.replay.last_retrain_day = str(ts[start - 1].astype("datetime64[D]"))
        state.monitor = ResidualMonitor(
            horizon=state.deployment.horizon,
            step_ns=state.monitor.step_ns,
            fixed_mean=state.monitor.fixed_mean,
            fixed_std=state.monitor.fixed_std,
            detector_specs=tuple(d.name for d in state.monitor.detectors),
        )
        if state.active.model is not None:
            state.monitor.set_baseline(
                state.active.model.manifest.get("metrics", {}).get("val_mae_fixed"),
                version=state.active.model.version,
            )
        state.replay.wait_for_retrain = req.wait_for_retrain
        return state.replay.position()

    @app.post("/v1/replay/step")
    def replay_step(req: ReplayStepRequest) -> dict[str, Any]:
        rp = state.replay
        if rp is None:
            raise HTTPException(status_code=409, detail="replay not started")
        if state.active.model is None:
            raise HTTPException(status_code=503, detail="no active model")
        alarms: list[dict[str, Any]] = []
        blocked = False
        requests: list[dict[str, Any]] = []
        done = 0
        with rp._lock:
            for _ in range(req.steps):
                if rp.cursor >= rp.n_rows:
                    break
                if rp.wait_for_retrain and state.registry.open_jobs():
                    blocked = (
                        True  # the stream waits for the worker, as the offline protocol assumes a one-day lag
                    )
                    break
                model = state.active.model
                origin_idx = rp.cursor - 1
                history = rp.values[rp.cursor - model.lookback : rp.cursor]
                out = model.forecast(history[None])[0]
                state.monitor.record_forecast(rp.timestamps[origin_idx], model.version, out)
                state.m_requests.labels(version=model.version).inc()
                result = state.monitor.observe(rp.timestamps[rp.cursor], rp.values[rp.cursor])
                rp.cursor += 1
                rp.steps += 1
                done += 1
                day = str(rp.timestamps[rp.cursor - 1].astype("datetime64[D]"))
                if result["alarms"]:
                    alarms.extend(result["alarms"])
                    if state.auto_retrain and not state.registry.open_jobs():
                        requests.append(
                            state.request_retrain({"trigger": "detector", "alarms": result["alarms"]})
                        )
                        rp.last_retrain_day = day
                if rp.retrain_schedule_days and _day_boundary(rp) and not state.registry.open_jobs():
                    last = rp.last_retrain_day
                    if last is None or _days_between(last, day) >= rp.retrain_schedule_days:
                        requests.append(
                            state.request_retrain(
                                {"trigger": "schedule", "every_days": rp.retrain_schedule_days}
                            )
                        )
                        rp.last_retrain_day = day
        rolling = state.monitor.state()["rolling_7d_mae"]
        if rolling is not None:
            state.m_rolling.set(rolling)
        return {
            "stepped": done,
            "blocked_on_retrain": blocked,
            "position": rp.position(),
            "alarms": alarms,
            "retrain_requests": requests,
        }

    @app.get("/v1/replay")
    def replay_position() -> dict[str, Any]:
        if state.replay is None:
            return {"active": False}
        return {"active": True, **state.replay.position()}

    # ---- dashboard -----------------------------------------------------------------------------
    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

        @app.get("/", include_in_schema=False)
        def index(_: Request) -> FileResponse:
            return FileResponse(STATIC / "index.html")

    # ---- self-contained browser replay (docs/demo), bundled only into the public demo image ------
    replay_page = os.environ.get("METRONOME_REPLAY_PAGE")

    @app.get("/replay", include_in_schema=False)
    def replay_page_route() -> FileResponse:
        path = Path(replay_page) if replay_page else None
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="replay page is not bundled in this image")
        return FileResponse(path, media_type="text/html; charset=utf-8")

    return app


def _day_boundary(rp: ReplayState) -> bool:
    if rp.cursor < 2:
        return False
    prev = rp.timestamps[rp.cursor - 2].astype("datetime64[D]")
    cur = rp.timestamps[rp.cursor - 1].astype("datetime64[D]")
    return bool(prev != cur)


def _days_between(a: str, b: str) -> int:
    return int((np.datetime64(b, "D") - np.datetime64(a, "D")).astype(int))
