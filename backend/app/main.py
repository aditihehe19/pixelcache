"""PixelCache API: orchestration layer between the web UI and the C++ engine.

Run from the repository root:
    python -m uvicorn app.main:app --app-dir backend --port 8000
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analytics, benchmarks, experiments, health, reports
from app.core.config import settings
from app.db.database import engine
from app.db.migrations import migrate
from app.services import experiment_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pixelcache")


@asynccontextmanager
async def lifespan(_: FastAPI):
    for d in (settings.data_dir, settings.jobs_dir, settings.reports_dir):
        d.mkdir(parents=True, exist_ok=True)
    version = migrate(engine)
    experiment_service.recover_after_restart()
    experiment_service.queue.start()
    log.info("schema v%d; engine %s; simulator %s", version,
             "found" if settings.bench_bin.exists() else "MISSING", "found" if settings.sim_bin.exists() else "MISSING")
    yield
    experiment_service.queue.stop()


app = FastAPI(title="PixelCache API", version="1.0",
              description="Runs the CacheVision C++ engine, stores experiments and serves analytics.",
              lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=list(settings.frontend_origins), allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Content-Type"], allow_credentials=False)

_rate_lock = threading.Lock()
_recent_posts: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def guard(request: Request, call_next):
    # Request size: reject oversized bodies before they are read.
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.max_request_bytes:
        return JSONResponse({"detail": "Request body too large."}, status_code=413)
    # Basic abuse protection: job-creating requests per client per minute.
    if request.method == "POST":
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with _rate_lock:
            q = _recent_posts[client]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= settings.post_limit_per_minute:
                return JSONResponse({"detail": "Too many requests; slow down."}, status_code=429)
            q.append(now)
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error", exc_info=exc)
    return JSONResponse({"detail": "Internal server error."}, status_code=500)


for module in (health, experiments, benchmarks, analytics, reports):
    app.include_router(module.router)
