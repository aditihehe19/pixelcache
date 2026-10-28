"""Experiments: create (single / comparison), upload inputs, list, read, delete."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.experiment import (ExperimentConfig, ExperimentDetail, ExperimentPage, JobAccepted, UploadOut,
                                    VariantResultOut)
from app.services import experiment_service as svc

router = APIRouter(prefix="/api", tags=["experiments"])


def _accept(db: Session, cfg: ExperimentConfig, kind: str) -> JobAccepted:
    exp = svc.create_experiment(db, cfg, kind)
    pos = svc.enqueue(db, exp)
    return JobAccepted(id=exp.id, kind=exp.kind, status=exp.status, queue_position=pos)


@router.post("/experiments", response_model=JobAccepted, status_code=202)
def create_experiment(cfg: ExperimentConfig, db: Session = Depends(get_db)) -> JobAccepted:
    """Run one traversal strategy. The job runs in the background; poll GET /api/experiments/{id}."""
    return _accept(db, cfg, "experiment")


@router.post("/experiments/compare", response_model=JobAccepted, status_code=202)
def compare(cfg: ExperimentConfig, db: Session = Depends(get_db)) -> JobAccepted:
    """Run several strategies in one interleaved group on identical input (row-major is added if missing)."""
    return _accept(db, cfg, "comparison")


@router.post("/uploads", response_model=UploadOut, status_code=201)
def upload_image(file: UploadFile = File(...)) -> UploadOut:
    """Upload an input image (PNG/JPEG/BMP/PPM/TIFF). It is decoded server-side and stored as RGB888."""
    return svc.save_upload(file)


@router.get("/experiments", response_model=ExperimentPage)
def list_experiments(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    status: Literal["queued", "running", "completed", "failed"] | None = None,
    op: Literal["yuv", "hsv", "lab", "unpack", "index_only"] | None = None,
    mapping: Literal["identity", "rotate90"] | None = None,
    kind: Literal["experiment", "comparison", "suite"] | None = None,
    strategy: Literal["row_major", "column_major", "tiled", "morton", "adaptive_model", "adaptive_calib"] | None = None,
    q: str | None = Query(None, max_length=60),
    db: Session = Depends(get_db),
) -> ExperimentPage:
    items, total = svc.list_experiments(db, page=page, page_size=page_size, status=status, op=op, mapping=mapping,
                                        kind=kind, strategy=strategy, q=q)
    return ExperimentPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/experiments/{experiment_id}", response_model=ExperimentDetail)
def get_experiment(experiment_id: str, db: Session = Depends(get_db)) -> ExperimentDetail:
    return svc.detail(svc.get_or_404(db, experiment_id))


@router.get("/experiments/{experiment_id}/results", response_model=list[VariantResultOut])
def get_results(experiment_id: str, db: Session = Depends(get_db)) -> list[VariantResultOut]:
    return svc.detail(svc.get_or_404(db, experiment_id)).results


@router.delete("/experiments/{experiment_id}", status_code=204)
def delete_experiment(experiment_id: str, db: Session = Depends(get_db)) -> Response:
    svc.delete_experiment(db, experiment_id)
    return Response(status_code=204)
