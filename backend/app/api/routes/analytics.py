"""Aggregates computed from stored measurements."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services import analytics_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

Op = Literal["yuv", "hsv", "lab", "unpack", "index_only"]
Mapping = Literal["identity", "rotate90"]


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    return analytics_service.summary(db)


@router.get("/scaling")
def scaling(op: Op = "yuv", mapping: Mapping = "identity", condition: Literal["warm", "flushed"] = "warm",
            db: Session = Depends(get_db)) -> dict:
    return analytics_service.scaling(db, op, mapping, condition)


@router.get("/comparisons")
def comparisons(op: Op | None = None, mapping: Mapping | None = None,
                width: int | None = Query(None, ge=1, le=16384), height: int | None = Query(None, ge=1, le=16384),
                labels: list[str] = Query(default=[], max_length=20),
                experiment_ids: list[str] = Query(default=[], max_length=20),
                db: Session = Depends(get_db)) -> dict:
    labels = [l for l in labels if l.replace("_", "").isalnum() and len(l) <= 40]
    experiment_ids = [e for e in experiment_ids if len(e) == 12 and e.isalnum()]
    return analytics_service.comparisons(db, op=op, mapping=mapping, width=width, height=height, labels=labels,
                                         experiment_ids=experiment_ids)


@router.get("/cache")
def cache(experiment_id: str | None = Query(None, pattern=r"^[0-9a-f]{12}$"), db: Session = Depends(get_db)) -> dict:
    return analytics_service.cache(db, experiment_id)
