from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from metronome.serving.app import create_app
from metronome.serving.deploy import init_deployment
from metronome.serving.registry import Registry, VerificationError
from metronome.serving.replay import load_stream
from metronome.serving.worker import WorkerConfig, run_worker

L, H = 48, 12


@pytest.fixture(scope="module")
def deployment(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """A registry with one trained version on the synthetic dataset (70 days, 3 channels)."""
    from tests.conftest import synthetic_frame

    from metronome.data.pipeline import prepare_frame
    from metronome.data.sources import PreparedSpec

    base = tmp_path_factory.mktemp("deploy")
    spec = PreparedSpec(name="synth", source="synthetic", freq="1h", stream_days=20)
    prepare_frame(synthetic_frame(drift_at=24 * 60), spec, base / "processed", source_info={})
    report = init_deployment(
        "synth", base / "processed", base / "registry", lookback=L, horizon=H, max_epochs=2, stream_days=20
    )
    return {"root": base / "registry", "report": report}


@pytest.fixture
def client(deployment: dict) -> TestClient:
    app = create_app(deployment["root"], api_key="secret", threads=1)
    return TestClient(app)


def test_init_creates_verified_active_version(deployment: dict) -> None:
    reg = Registry(deployment["root"])
    assert reg.active() == "v0001" and reg.list_versions() == ["v0001"]
    report = reg.verify("v0001")
    assert report["max_abs_diff"] < 1e-4
    assert deployment["report"]["metrics"]["val_mae_fixed"] > 0
    assert (deployment["root"] / "stream.npz").exists()


def test_health_ready_models(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/ready")
    assert ready.status_code == 200 and ready.json()["model"] == "v0001"
    models = client.get("/v1/models").json()
    assert models["active"]["version"] == "v0001" and models["versions"][0]["onnx_sha256"]
    assert client.get("/v1/deployment").json()["lookback"] == L
    assert "metronome_forecast_requests_total" in client.get("/metrics").text


def test_forecast_validates_shape_and_records(client: TestClient, deployment: dict) -> None:
    ts, values = load_stream(deployment["root"] / "stream.npz")
    hist = values[1000 - L : 1000].tolist()
    resp = client.post("/v1/forecast", json={"history": hist, "origin": str(ts[999])})
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_version"] == "v0001" and len(body["forecast"]) == H and len(body["forecast"][0]) == 3
    assert len(body["timestamps"]) == H and body["timestamps"][0] == str(ts[1000])
    bad = client.post("/v1/forecast", json={"history": hist[:10]})
    assert bad.status_code == 422
    raw = json.dumps({"history": [[1.0] * 3] * L}).replace("1.0", "NaN", 1)
    nan = client.post("/v1/forecast", content=raw, headers={"content-type": "application/json"})
    assert nan.status_code == 422
    # deliver the next 12 actuals -> the forecast resolves
    for i in range(1000, 1000 + H):
        r = client.post("/v1/observe", json={"timestamp": str(ts[i]), "values": values[i].tolist()}).json()
    assert r["resolved"] == 1
    mon = client.get("/v1/monitor").json()
    assert mon["resolved_forecasts"] >= 1 and mon["active_version"] == "v0001"


def test_activate_requires_key_and_refuses_tampered_model(client: TestClient, deployment: dict) -> None:
    assert client.post("/v1/models/v0001/activate").status_code == 401
    reg = Registry(deployment["root"])
    path = reg.model_path("v0001")
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\x00")
        with pytest.raises(VerificationError):
            reg.verify("v0001")
        resp = client.post("/v1/models/v0001/activate", headers={"X-API-Key": "secret"})
        assert resp.status_code == 422 and "hash" in resp.json()["detail"]
        assert client.get("/ready").status_code == 200  # the already-loaded model keeps serving
    finally:
        path.write_bytes(original)
    assert client.post("/v1/models/v0001/activate", headers={"X-API-Key": "secret"}).status_code == 200
    assert client.post("/v1/models/v9999/activate", headers={"X-API-Key": "secret"}).status_code == 404


def test_replay_triggers_retrain_and_worker_hot_swaps(client: TestClient, deployment: dict) -> None:
    root: Path = deployment["root"]
    start = client.post("/v1/replay/start", json={"schedule_days": 7}, headers={"X-API-Key": "secret"})
    assert start.status_code == 200 and start.json()["cursor"] == deployment["report"]["stream_start_row"]
    total_requests = 0
    for _ in range(10):
        step = client.post("/v1/replay/step", json={"steps": 24 * 6}).json()
        total_requests += len(step["retrain_requests"])
        if total_requests:
            break
    assert total_requests >= 1, "schedule should request a retrain within 60 days"
    reg = Registry(root)
    assert reg.pending_jobs()
    # with a job pending the stream refuses to advance until the worker delivers (protocol P7 lag)
    blocked = client.post("/v1/replay/step", json={"steps": 24}).json()
    assert blocked["blocked_on_retrain"] and blocked["stepped"] == 0
    cfg = WorkerConfig(registry_root=root, stream_path=root / "stream.npz", max_epochs=1, threads=1)
    done = run_worker(cfg, once=True)
    assert done and done[0]["version"] == "v0002"
    # the API process has not reloaded yet; `reload` syncs it with the registry's ACTIVE pointer
    assert client.get("/ready").json()["model"] == "v0001"
    reload = client.post("/v1/models/reload", headers={"X-API-Key": "secret"}).json()
    assert reload["changed"] and reload["to"] == "v0002"
    assert client.get("/ready").json()["model"] == "v0002"
    moved = client.post("/v1/replay/step", json={"steps": 24}).json()
    assert moved["stepped"] == 24 and not moved["blocked_on_retrain"]
    assert client.get("/v1/monitor").json()["judged_version"] == "v0002"
    events = client.get("/v1/events").json()
    assert events["swaps"][-1]["to"] == "v0002" and events["retrain_requests"]
    prov = reg.manifest("v0002")["provenance"]
    assert prov["trigger"] in {"schedule", "detector"} and prov["cutoff_row"] > L


def test_hot_swap_never_drops_a_request(client: TestClient, deployment: dict) -> None:
    _ts, values = load_stream(deployment["root"] / "stream.npz")
    hist = values[500 - L : 500].tolist()
    errors: list[str] = []
    seen: set[str] = set()
    stop = threading.Event()

    def hammer() -> None:
        while not stop.is_set():
            r = client.post("/v1/forecast", json={"history": hist})
            if r.status_code != 200:
                errors.append(r.text)
            else:
                seen.add(r.json()["model_version"])

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for version in ("v0001", "v0002", "v0001", "v0002"):
        r = client.post(f"/v1/models/{version}/activate", headers={"X-API-Key": "secret"})
        assert r.status_code == 200
    stop.set()
    for t in threads:
        t.join()
    assert not errors and seen >= {"v0001", "v0002"}


def test_detector_alarm_requests_retrain_on_drift(deployment: dict) -> None:
    """A synthetic level shift at day 60 must raise an alarm from the ratio rule in replay."""
    app = create_app(deployment["root"], api_key=None, threads=1, detector_specs=("ratio-0.2",))
    c = TestClient(app)
    c.post("/v1/models/v0001/activate")
    assert c.post("/v1/replay/start", json={"start_row": 24 * 50}).status_code == 200
    alarms = []
    for _ in range(20):
        step = c.post("/v1/replay/step", json={"steps": 24}).json()
        alarms += step["alarms"]
        if alarms:
            break
    assert alarms and alarms[0]["detectors"] == ["ratio-0.2"]
    mon = c.get("/v1/monitor").json()
    assert mon["alarms"] and mon["pending_jobs"]
    assert np.isfinite(mon["rolling_7d_mae"])


def test_read_only_registry_still_serves(
    deployment: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The serving container mounts the registry read-only: startup must verify and serve the
    ACTIVE pointer without rewriting it, and a retrain hand-off failure must not take the API down."""
    import shutil

    import metronome.serving.registry as registry_mod

    root = tmp_path / "registry"  # private copy: other tests leave jobs behind in the shared one
    shutil.copytree(deployment["root"], root, ignore=shutil.ignore_patterns("jobs", "work"))
    root.joinpath("ACTIVE").write_text("v0001\n")

    def refuse(path: Path, text: str) -> None:
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(registry_mod, "_atomic_write", refuse)
    active_before = (root / "ACTIVE").read_text()
    app = create_app(root, api_key=None, threads=1, detector_specs=("ratio-0.2",))
    c = TestClient(app)
    ready = c.get("/ready")
    assert ready.status_code == 200 and ready.json()["model"] == "v0001"
    assert (root / "ACTIVE").read_text() == active_before
    assert not (root / "ACTIVE.tmp").exists()
    # Re-activating the same version is a no-op on disk; activating another one needs the write.
    assert c.post("/v1/models/v0001/activate").status_code == 200
    # Replay through the drift so the detector asks for a retrain: the hand-off fails, serving continues.
    assert c.post("/v1/replay/start", json={"start_row": 24 * 50}).status_code == 200
    requested = None
    for _ in range(20):
        step = c.post("/v1/replay/step", json={"steps": 24})
        assert step.status_code == 200
        if step.json()["retrain_requests"]:
            requested = step.json()["retrain_requests"][0]
            break
    assert requested is not None and requested["job"] is None and "not writable" in requested["error"]
    assert c.get("/ready").status_code == 200
    assert c.get("/v1/monitor").json()["pending_jobs"] == []


def test_replay_page_is_served_only_when_bundled(
    deployment: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The public demo image bundles the browser replay and serves it at /replay; other images return 404."""
    monkeypatch.delenv("METRONOME_REPLAY_PAGE", raising=False)
    assert TestClient(create_app(deployment["root"], threads=1)).get("/replay").status_code == 404
    page = tmp_path / "replay.html"
    page.write_text("<!doctype html><title>Metronome Replay</title>", encoding="utf-8")
    monkeypatch.setenv("METRONOME_REPLAY_PAGE", str(page))
    r = TestClient(create_app(deployment["root"], threads=1)).get("/replay")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "Metronome Replay" in r.text


def test_worker_can_register_without_activating(deployment: dict) -> None:
    """activate=False (the Airflow gate's mode): the candidate is exported, verified and registered,
    but ACTIVE still names the champion until someone decides to promote it."""
    root: Path = deployment["root"]
    reg = Registry(root)
    before, versions_before = reg.active(), set(reg.list_versions())
    job = reg.request_retrain({"trigger": "airflow-weekly", "cutoff_row": None, "active_version": before})
    cfg = WorkerConfig(
        registry_root=root, stream_path=root / "stream.npz", max_epochs=1, threads=1, activate=False
    )
    done = {d["job"]: d for d in run_worker(cfg, once=True)}  # earlier tests may have left jobs pending
    assert job.stem in done, done
    candidate = done[job.stem]["version"]
    assert candidate not in versions_before and candidate in reg.list_versions()
    assert done[job.stem]["activation"] == {"skipped": True, "reason": "activation left to the caller"}
    assert reg.active() == before
    assert reg.manifest(candidate)["metrics"]["val_mae_fixed"] > 0
    assert not reg.pending_jobs()


# ---- workbench: data -> model comparison -> deployment -----------------------------------------
def test_data_profile_describes_the_deployed_dataset(client: TestClient, deployment: dict) -> None:
    assert (deployment["root"] / "dataset.json").exists(), "deploy-init keeps the dataset manifest"
    p = client.get("/v1/data/profile").json()
    assert p["dataset"] == "synth" and p["channels"] == ["ch0", "ch1", "ch2"] and p["freq"] == "1h"
    assert p["n_rows"] == 24 * 70 and p["split"]["initial_rows"] + p["split"]["stream_rows"] == p["n_rows"]
    assert p["split"]["stream_days"] == 20 and p["lookback"] == L and p["horizon"] == H
    stats = {s["name"]: s for s in p["channel_stats"]}
    assert 9 < stats["ch0"]["mean"] < 20 and stats["ch0"]["missing"] == 0
    assert len(p["sparklines"]["timestamps"]) == len(p["sparklines"]["values"]) <= 120
    assert p["validation"]["ok"] is True and p["content_sha256"]


def test_csv_check_reports_problems_without_crashing(client: TestClient) -> None:
    good = "timestamp,a,b\n" + "".join(f"2021-01-01 {h:02d}:00:00,{h},{h * 2}\n" for h in range(24))
    r = client.post("/v1/data/validate", files={"file": ("good.csv", good.encode(), "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["report"]["n_rows"] == 24 and body["report"]["channels"] == ["a", "b"]
    assert body["enough_history"]["ok"] is False  # 24 rows is far below lookback + horizon + 14 days

    bad = (
        "date,a,note\n"
        "2021-01-01 00:00:00,1,x\n"
        "2021-01-01 01:00:00,2,y\n"
        "2021-01-01 01:00:00,2,z\n"  # duplicate
        "2021-01-01 04:00:00,,w\n"  # gap + missing value
        "not a date,5,v\n"  # unparseable timestamp
    )
    r = client.post("/v1/data/validate", files={"file": ("bad.csv", bad.encode(), "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["timestamp_column"] == "date"
    assert body["bad_timestamps"] == 1 and body["dropped_columns"] == ["note"]
    rep = body["report"]
    assert rep["duplicates"] == 1 and rep["gaps"] == 1 and rep["nan_cells"] == 1
    assert any("duplicated" in p for p in rep["problems"])

    r = client.post(
        "/v1/data/validate", files={"file": ("x.bin", b"\x00\x01\x02", "application/octet-stream")}
    )
    assert r.status_code in (200, 422)  # garbage is either rejected or reported, never a 500
    r = client.post("/v1/data/validate", files={"file": ("empty.csv", b"", "text/csv")})
    assert r.status_code == 422


def test_leaderboard_lists_offline_families_and_live_versions(client: TestClient) -> None:
    lb = client.get("/v1/leaderboard").json()
    assert lb["dataset"] == "synth" and lb["families"] == ["linear", "nlinear", "dlinear", "patchtst"]
    assert lb["offline"] == []  # no LTSF runs for the synthetic set; etth1 has them in evidence.json
    assert lb["live"] and lb["live"][0]["version"] == "v0001" and lb["live"][0]["model"] == "dlinear"
    assert any(v["active"] for v in lb["live"])


def test_candidate_trains_by_family_then_gate_decides(deployment: dict) -> None:
    root: Path = deployment["root"]
    app = create_app(root, api_key="secret", threads=1)
    client = TestClient(app)
    key = {"X-API-Key": "secret"}
    before = client.get("/ready").json()["model"]

    assert client.post("/v1/candidates", json={"model": "linear"}).status_code == 401
    assert client.post("/v1/candidates", json={"model": "lstm"}, headers=key).status_code == 422
    req = client.post("/v1/candidates", json={"model": "linear", "max_epochs": 1}, headers=key)
    assert req.status_code == 200 and req.json()["trigger"] == "candidate" and req.json()["model"] == "linear"
    assert (
        client.post("/v1/candidates", json={"model": "nlinear"}, headers=key).status_code == 409
    )  # one at a time
    listed = client.get("/v1/candidates").json()
    assert listed["open_jobs"] == [req.json()["job"]]
    job = next(j for j in listed["jobs"] if j["job"] == req.json()["job"])
    assert job["status"] == "requested" and job["model"] == "linear" and job["max_epochs"] == 1

    cfg = WorkerConfig(registry_root=root, stream_path=root / "stream.npz", max_epochs=5, threads=1)
    done = {d["job"]: d for d in run_worker(cfg, once=True)}
    result = done[req.json()["job"]]
    assert result["activation"] == {"skipped": True, "reason": "activation left to the caller"}
    version = result["version"]
    assert Registry(root).manifest(version)["provenance"]["model"] == "linear"
    assert Registry(root).manifest(version)["provenance"]["max_epochs"] == 1
    assert client.get("/ready").json()["model"] == before, "a candidate never activates itself"

    job = next(j for j in client.get("/v1/candidates").json()["jobs"] if j["job"] == req.json()["job"])
    assert job["status"] == "done" and job["version"] == version and job["model"] == "linear"
    assert job["metrics"]["val_mae_fixed"] > 0 and job["better_than_active"] in (True, False)

    detail = client.get(f"/v1/models/{version}").json()
    assert detail["active"] is False and detail["provenance"]["trigger"] == "candidate"
    card = client.get(f"/v1/models/{version}/card")
    assert card.status_code == 200 and card.headers["content-type"].startswith("text/markdown")
    assert f"모델 카드 — {version}" in card.text and "linear" in card.text and "SHA-256" in card.text
    assert client.get("/v1/models/v9999").status_code == 404

    gate = client.post("/v1/candidates/promote", json={"version": version}, headers=key)
    if job["better_than_active"]:
        assert gate.status_code == 200 and gate.json()["promote"] is True
        assert client.get("/ready").json()["model"] == version
    else:
        assert gate.status_code == 409 and gate.json()["promote"] is False
        assert client.get("/ready").json()["model"] == before
        forced = client.post("/v1/candidates/promote", json={"version": version, "force": True}, headers=key)
        assert forced.status_code == 200 and forced.json()["activation"]["reason"] == "forced"
        assert client.get("/ready").json()["model"] == version
    assert client.post("/v1/candidates/promote", json={"version": version}, headers=key).status_code == 409

    back = client.post("/v1/models/rollback", headers=key)
    assert back.status_code == 200 and back.json()["rolled_back_to"] == before
    assert client.get("/ready").json()["model"] == before
    assert client.get("/v1/events").json()["swaps"][-1]["reason"] == "rollback"


def test_replay_window_feeds_the_forecast_chart(client: TestClient, deployment: dict) -> None:
    w = client.get("/v1/replay/window").json()
    assert w["replay_active"] is False and len(w["history"]) == L and len(w["history"][0]) == 3
    assert w["actual_next"] == []  # at the end of the stream there is no future to compare with
    client.post("/v1/replay/start", json={}, headers={"X-API-Key": "secret"})
    w = client.get("/v1/replay/window").json()
    assert w["replay_active"] is True and len(w["actual_next"]) == H and len(w["actual_timestamps"]) == H
    fc = client.post(
        "/v1/forecast", json={"history": w["history"], "origin": w["origin"], "record": False}
    ).json()
    assert len(fc["forecast"]) == H and fc["timestamps"][0] == w["actual_timestamps"][0]
    assert client.get("/v1/workbench").json()["active"] == client.get("/ready").json()["model"]
