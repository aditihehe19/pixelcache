"""Benchmark suites (benchmarks/benchmark_config.json) run through the engine's suite driver."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.benchmark import BenchmarkRunRequest, SuiteInfo
from app.schemas.experiment import ExperimentDetail, JobAccepted
from app.services import benchmark_service
from app.services import experiment_service as svc

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])


@router.get("/suites", response_model=list[SuiteInfo])
def suites() -> list[SuiteInfo]:
    return benchmark_service.list_suites()


@router.post("/run", response_model=JobAccepted, status_code=202)
def run(req: BenchmarkRunRequest, db: Session = Depends(get_db)) -> JobAccepted:
    exp = benchmark_service.create_suite_run(db, req)
    pos = svc.enqueue(db, exp)
    return JobAccepted(id=exp.id, kind=exp.kind, status=exp.status, queue_position=pos)


@router.get("/{benchmark_id}", response_model=ExperimentDetail)
def get(benchmark_id: str, db: Session = Depends(get_db)) -> ExperimentDetail:
    exp = svc.get_or_404(db, benchmark_id)
    if exp.kind != "suite":
        raise HTTPException(404, "Benchmark run not found (this id is an experiment).")
    return svc.detail(exp)
