"""End-to-end with the REAL C++ engine (skipped if it is not built).

configure -> submit -> engine runs -> results persisted -> retrieved ->
analytics -> report generated and downloaded -> survives a restart -> deleted.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.db.database import SessionLocal
from app.models.experiment import CacheSimRow, Experiment, Repetition, VariantResult
from app.services import experiment_service
from tests.conftest import requires_engine, small_config, wait_for


@requires_engine
def test_full_workflow_with_real_engine(client):
    cfg = small_config(
        op="hsv", mapping="rotate90", width=200, height=120, reps=5, validate_reference=True,
        strategies=[{"strategy": "tiled", "tile_w": 16, "tile_h": 16}, {"strategy": "morton"},
                    {"strategy": "adaptive_calib"}],
        cache_sim={"enabled": True, "l1_kib": 32, "l1_ways": 8})
    r = client.post("/api/experiments/compare", json=cfg)
    assert r.status_code == 202
    eid = r.json()["id"]
    d = wait_for(client, eid)
    assert d["status"] == "completed", d["error_message"]

    # row_major was added as the baseline; every requested strategy came back
    labels = {x["label"] for x in d["results"]}
    assert labels == {"row_major", "tiled_16x16", "morton", "adaptive_calib"}
    for res in d["results"]:
        assert res["reps"] == 5 and len(res["repetitions"]) == 5
        assert res["output_matches_baseline"] is True          # bit-identical to row-major
        assert res["hw_counters"] == "unavailable"
        assert res["median_ms"] > 0 and res["speedup_vs_row_major"] > 0
    adaptive = next(x for x in d["results"] if x["label"] == "adaptive_calib")
    assert adaptive["tile_w"] > 0 and adaptive["setup_ms"] > 0

    # simulated cache rows use the custom L1 and are labelled as a model
    assert d["cache_geometry"]["source"] == "custom"
    assert {c["level"] for c in d["cache"]} == {"L1D", "L2", "L3"}
    assert all(c["source"] == "model" for c in d["cache"])
    assert {c["label"] for c in d["cache"]} == labels

    # reference validation ran on the same image
    assert d["validation"]["ran"] is True
    assert d["validation"]["references"]["numpy64"]["passed"] is True
    assert d["environment"]["cpu_brand"]
    assert "<job>" in " ".join(d["engine_command"])            # no internal paths leak

    # persisted in the database with every repetition
    with SessionLocal() as db:
        assert db.scalar(select(func.count(VariantResult.id)).where(VariantResult.experiment_id == eid)) == 4
        assert db.scalar(select(func.count(Repetition.id)).join(VariantResult)
                         .where(VariantResult.experiment_id == eid)) == 20
        assert db.scalar(select(func.count(CacheSimRow.id)).where(CacheSimRow.experiment_id == eid)) == 12

    # /results returns the same measurements
    res = client.get(f"/api/experiments/{eid}/results").json()
    assert sorted(x["median_ms"] for x in res) == sorted(x["median_ms"] for x in d["results"])

    # analytics are computed from the stored rows
    summary = client.get("/api/analytics/summary").json()
    assert summary["experiments"]["completed"] >= 1 and summary["repetitions"] >= 20
    comp = client.get("/api/analytics/comparisons", params={"op": "hsv", "mapping": "rotate90"}).json()
    assert any(row["experiment_id"] == eid for row in comp["rows"])
    cache = client.get("/api/analytics/cache", params={"experiment_id": eid}).json()
    assert cache["selected"] == eid and len(cache["rows"]) == 12
    scaling = client.get("/api/analytics/scaling", params={"op": "hsv", "mapping": "rotate90"}).json()
    assert any(p["label"] == "morton" and p["pixels"] == 200 * 120 for p in scaling["points"])

    # reports in both formats, downloadable
    for fmt in ("html", "md"):
        rep = client.post(f"/api/reports/{eid}", json={"format": fmt})
        assert rep.status_code == 201
        dl = client.get(f"/api/reports/{rep.json()['id']}/download")
        assert dl.status_code == 200
        text = dl.text
        assert "Interpretation" in text and "Limitations" in text and "SIMULATED" in text.upper()
        assert "morton" in text
    assert len(client.get("/api/reports").json()) >= 2

    # history survives a restart of the application
    experiment_service.queue.stop()
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as again:
        d2 = again.get(f"/api/experiments/{eid}").json()
        assert d2["status"] == "completed" and len(d2["results"]) == 4
        page = again.get("/api/experiments", params={"status": "completed"}).json()
        assert any(item["id"] == eid for item in page["items"])
    experiment_service.queue.start()

    # deletion removes the experiment, its results and its report files
    assert client.delete(f"/api/experiments/{eid}").status_code == 204
    assert client.get(f"/api/experiments/{eid}").status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(func.count(VariantResult.id)).where(VariantResult.experiment_id == eid)) == 0


def test_restart_marks_interrupted_jobs_failed():
    with SessionLocal() as db:
        exp = Experiment(kind="experiment", name="interrupted", status="running", config_json="{}")
        db.add(exp)
        db.commit()
        eid = exp.id
    experiment_service.recover_after_restart()
    with SessionLocal() as db:
        exp = db.get(Experiment, eid)
        assert exp.status == "failed" and "Interrupted" in exp.error_message
        db.delete(exp)
        db.commit()


def test_cannot_delete_running_experiment(client):
    with SessionLocal() as db:
        exp = Experiment(kind="experiment", name="busy", status="running", config_json="{}")
        db.add(exp)
        db.commit()
        eid = exp.id
    assert client.delete(f"/api/experiments/{eid}").status_code == 409
    with SessionLocal() as db:
        db.delete(db.get(Experiment, eid))
        db.commit()


def test_report_requires_completed_experiment(client):
    with SessionLocal() as db:
        exp = Experiment(kind="experiment", name="queued", status="failed", config_json="{}")
        db.add(exp)
        db.commit()
        eid = exp.id
    assert client.post(f"/api/reports/{eid}").status_code == 409


def test_queue_full_returns_429(client, monkeypatch):
    from app.services.job_queue import QueueFull

    def full(_):
        raise QueueFull("8 jobs are already waiting")
    monkeypatch.setattr(experiment_service.queue, "submit", full)
    r = client.post("/api/experiments", json=small_config())
    assert r.status_code == 429
