"""Test configuration.

Every test session gets its own data directory (database, job dirs, reports),
so tests never touch backend/data. Settings are read at import time, hence
the environment is prepared before the application is imported.
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="pixelcache-tests-")
os.environ["PIXELCACHE_DATA_DIR"] = _TMP
os.environ["PIXELCACHE_POST_LIMIT_PER_MINUTE"] = "100000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
ENGINE_BUILT = settings.bench_bin.exists() and settings.sim_bin.exists()
requires_engine = pytest.mark.skipif(not ENGINE_BUILT, reason="C++ engine not built (cmake --build build)")


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Tests that use the database directly may run before any TestClient starts the app."""
    from app.db.database import engine
    from app.db.migrations import migrate
    migrate(engine)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def wait_for(client, experiment_id: str, timeout: float = 240.0) -> dict:
    """Poll an experiment until it leaves queued/running."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        d = client.get(f"/api/experiments/{experiment_id}").json()
        if d["status"] in ("completed", "failed"):
            return d
        time.sleep(0.2)
    raise AssertionError(f"experiment {experiment_id} did not finish within {timeout}s")


def small_config(**overrides) -> dict:
    cfg = {"op": "yuv", "mapping": "identity", "image_source": "gradient", "width": 96, "height": 64,
           "strategies": [{"strategy": "row_major"}], "reps": 3, "validate_reference": False}
    cfg.update(overrides)
    return cfg
