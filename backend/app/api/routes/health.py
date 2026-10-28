"""Health, host description and engine capabilities."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.validation import (MAX_EDGE, MAX_REPS, MAX_TILE, MAX_VARIANTS, MIN_EDGE, MIN_REPS, MIN_TILE,
                                 OPERATION_LABELS, STRATEGY_LABELS, CacheCondition, ImageSource, Mapping)
from app.db.database import engine, get_db
from app.db.migrations import current_version
from app.schemas.benchmark import Capabilities, HealthOut, SystemInfoOut
from app.services import system_service
from app.services.experiment_service import queue

router = APIRouter(prefix="/api", tags=["health"])

IMAGE_SOURCE_LABELS = {
    ImageSource.photo: "Standard photo (grace_hopper.jpg, mirror-tiled to size)",
    ImageSource.gradient: "Synthetic: smooth gradient",
    ImageSource.noise: "Synthetic: uniform noise",
    ImageSource.mixed: "Synthetic: gradient + texture + noise patches",
    ImageSource.upload: "Uploaded image",
}


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001
        database = "unavailable"
    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        database=database,
        schema_version=current_version(engine),
        engine={"benchmark_binary": settings.bench_bin.exists(), "simulator_binary": settings.sim_bin.exists(),
                "build_dir": "<repo>/build"},
        queue=queue.snapshot(),
    )


@router.get("/system-info", response_model=SystemInfoOut)
def system_info(refresh: bool = False) -> SystemInfoOut:
    return system_service.system_info(refresh)


@router.get("/capabilities", response_model=Capabilities)
def capabilities() -> Capabilities:
    return Capabilities(
        operations=[{"value": k.value, "label": v} for k, v in OPERATION_LABELS.items()],
        strategies=[{"value": k.value, "label": v} for k, v in STRATEGY_LABELS.items()],
        mappings=[m.value for m in Mapping],
        image_sources=[{"value": k.value, "label": v} for k, v in IMAGE_SOURCE_LABELS.items()],
        conditions=[c.value for c in CacheCondition],
        limits={"min_edge": MIN_EDGE, "max_edge": MAX_EDGE, "max_pixels": settings.max_pixels,
                "min_tile": MIN_TILE, "max_tile": MAX_TILE, "min_reps": MIN_REPS, "max_reps": MAX_REPS,
                "max_variants": MAX_VARIANTS, "max_sim_pixels": settings.max_sim_pixels,
                "max_validation_pixels": settings.max_validation_pixels,
                "max_upload_mb": settings.max_upload_bytes // (1024 * 1024)},
        engine_available=settings.bench_bin.exists(),
        simulator_available=settings.sim_bin.exists(),
    )
