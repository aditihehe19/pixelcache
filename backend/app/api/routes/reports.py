"""Report generation and download."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.report import ReportOut, ReportRequest
from app.services import experiment_service, report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/{experiment_id}", response_model=ReportOut, status_code=201)
def create_report(experiment_id: str, req: ReportRequest | None = None, db: Session = Depends(get_db)) -> ReportOut:
    exp = experiment_service.get_or_404(db, experiment_id)
    return ReportOut.model_validate(report_service.create_report(db, exp, (req or ReportRequest()).format))


@router.get("", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db)) -> list[ReportOut]:
    return [ReportOut.model_validate(r) for r in report_service.list_reports(db)]


@router.get("/{report_id}/download")
def download(report_id: str, db: Session = Depends(get_db)) -> FileResponse:
    rep, path = report_service.report_path(db, report_id)
    media = "text/html" if rep.format == "html" else "text/markdown"
    return FileResponse(path, media_type=media, filename=f"pixelcache-report-{rep.experiment_id}-{rep.id}.{rep.format}")
