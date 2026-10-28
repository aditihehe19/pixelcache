"""Health, capabilities, request validation and identifier handling (no engine needed)."""
from __future__ import annotations

import pytest

from tests.conftest import small_config


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] == "ok"
    assert body["schema_version"] == 1
    assert body["queue"]["worker_alive"] is True


def test_capabilities_lists_engine_vocabulary(client):
    caps = client.get("/api/capabilities").json()
    assert {o["value"] for o in caps["operations"]} >= {"yuv", "hsv", "lab"}
    assert {s["value"] for s in caps["strategies"]} == {"row_major", "column_major", "tiled", "morton",
                                                        "adaptive_model", "adaptive_calib"}
    assert caps["limits"]["min_reps"] >= 1


@pytest.mark.parametrize("patch, fragment", [
    ({"op": "rgb2xyz"}, "op"),
    ({"strategies": [{"strategy": "tiled"}]}, "tile_w and tile_h are required"),
    ({"strategies": [{"strategy": "morton", "tile_w": 8, "tile_h": 8}]}, "only apply to the tiled"),
    ({"reps": 1}, "reps"),
    ({"reps": 500}, "reps"),
    ({"width": 8}, "width"),
    ({"width": 8192, "height": 8192 * 2}, "height"),
    ({"image_source": "upload"}, "upload_id is required"),
    ({"upload_id": "abcdefabcdef"}, "only valid with image_source"),
    ({"strategies": [{"strategy": "tiled", "tile_w": 512, "tile_h": 8}]}, "larger than"),
    ({"strategies": [{"strategy": "morton"}, {"strategy": "morton"}]}, "only once"),
    ({"cache_sim": {"enabled": True, "l1_kib": 48}}, "both size"),
    ({"cache_sim": {"enabled": True, "l1_kib": 48, "l1_ways": 7}}, "whole number of sets"),
    ({"unexpected": 1}, "Extra inputs"),
])
def test_invalid_configurations_are_rejected(client, patch, fragment):
    r = client.post("/api/experiments", json=small_config(**patch))
    assert r.status_code == 422
    assert fragment in r.text


def test_single_experiment_requires_exactly_one_strategy(client):
    r = client.post("/api/experiments", json=small_config(strategies=[{"strategy": "row_major"},
                                                                     {"strategy": "morton"}]))
    assert r.status_code == 422
    assert "exactly one strategy" in r.text


def test_comparison_requires_two_strategies(client):
    r = client.post("/api/experiments/compare", json=small_config())
    assert r.status_code == 422
    assert "at least two" in r.text


@pytest.mark.parametrize("path", ["/api/experiments/nothere", "/api/experiments/0123456789ab",
                                  "/api/experiments/0123456789ab/results", "/api/benchmarks/0123456789ab"])
def test_unknown_or_malformed_ids_return_404(client, path):
    assert client.get(path).status_code == 404


def test_delete_and_report_unknown_ids(client):
    assert client.delete("/api/experiments/0123456789ab").status_code == 404
    assert client.post("/api/reports/0123456789ab").status_code == 404
    assert client.get("/api/reports/0123456789ab/download").status_code == 404
    assert client.get("/api/reports/../../etc/download").status_code == 404


def test_unknown_suite(client):
    r = client.post("/api/benchmarks/run", json={"suite": "does_not_exist", "quick": True})
    assert r.status_code == 404


def test_suite_listing_reads_benchmark_config(client):
    suites = {s["name"]: s for s in client.get("/api/benchmarks/suites").json()}
    assert {"main", "tile_sweep", "overhead"} <= set(suites)
    assert suites["overhead"]["groups"] == 2 * 4 * 1  # sizes x ops x mappings (one image)


def test_request_size_limit(client):
    from app.core.config import settings
    r = client.post("/api/uploads", headers={"content-length": str(settings.max_request_bytes + 1),
                                             "content-type": "application/octet-stream"}, content=b"x")
    assert r.status_code == 413


def test_upload_validation(client):
    import cv2
    import numpy as np

    ok, png = cv2.imencode(".png", np.full((40, 50, 3), 128, np.uint8))
    r = client.post("/api/uploads", files={"file": ("tiny.png", png.tobytes(), "image/png")})
    assert r.status_code == 201
    assert (r.json()["width"], r.json()["height"]) == (50, 40)

    r = client.post("/api/uploads", files={"file": ("bad.png", b"not an image", "image/png")})
    assert r.status_code == 415
    r = client.post("/api/uploads", files={"file": ("script.sh", b"#!/bin/sh", "text/plain")})
    assert r.status_code == 415
    ok, small = cv2.imencode(".png", np.zeros((4, 4, 3), np.uint8))
    r = client.post("/api/uploads", files={"file": ("small.png", small.tobytes(), "image/png")})
    assert r.status_code == 422


def test_migrations_are_idempotent():
    from app.db.database import engine
    from app.db.migrations import migrate
    assert migrate(engine) == 1
    assert migrate(engine) == 1
