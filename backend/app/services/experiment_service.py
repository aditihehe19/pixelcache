"""Experiment lifecycle: create -> queue -> run the real engine -> persist -> read.

Execution pipeline for one experiment (all steps run outside any timed region
of the engine; only the engine itself times anything):
  1. prepare the input image in a private job directory,
  2. `cachevision_bench_native --single` with every requested variant in ONE
     group (identical input, interleaved shuffled repetitions),
  3. optionally `cachevision_sim` on the same size/mapping/tiles,
  4. optionally `scripts/validate_reference.py` on the same image,
  5. store results + raw repetitions, delete the job directory.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.validation import UPLOAD_EXTENSIONS, MAX_EDGE, MIN_EDGE, ImageSource, Strategy, variant_label
from app.db.database import SessionLocal
from app.models.experiment import CacheSimRow, Experiment, Repetition, VariantResult, utcnow
from app.schemas.experiment import (CacheRowOut, ExperimentConfig, ExperimentDetail, ExperimentSummary, RepetitionOut,
                                    StrategySpec, UploadOut, VariantResultOut)
from app.services import engine_runner as er
from app.services.job_queue import JobQueue, QueueFull

log = logging.getLogger("pixelcache.experiments")


# ---- queue -----------------------------------------------------------------------

def _execute(job_id: str) -> None:
    # Imported lazily: benchmark_service imports this module.
    from app.services import benchmark_service
    execute(job_id, suite_runner=benchmark_service.run_suite_job)


queue = JobQueue(_execute, settings.max_queued_jobs)


def enqueue(db: Session, exp: Experiment) -> int:
    try:
        return queue.submit(exp.id)
    except QueueFull as e:
        db.delete(exp)
        db.commit()
        raise HTTPException(status_code=429, detail=str(e)) from None


def recover_after_restart() -> None:
    """Running jobs cannot survive a restart (their process is gone); queued ones are resubmitted."""
    with SessionLocal() as db:
        for exp in db.scalars(select(Experiment).where(Experiment.status == "running")):
            exp.status = "failed"
            exp.finished_at = utcnow()
            exp.error_message = "Interrupted: the backend stopped while this job was running."
        db.commit()
        queued = db.scalars(select(Experiment.id).where(Experiment.status == "queued")
                            .order_by(Experiment.created_at)).all()
    for job_id in queued:
        try:
            queue.submit(job_id)
        except QueueFull:
            with SessionLocal() as db:
                exp = db.get(Experiment, job_id)
                exp.status, exp.error_message = "failed", "Not resumed after restart: queue full."
                db.commit()


# ---- uploads ---------------------------------------------------------------------

def _uploads_dir() -> Path:
    d = settings.data_dir / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cleanup_uploads(max_age: timedelta = timedelta(hours=24)) -> None:
    cutoff = time.time() - max_age.total_seconds()
    for p in _uploads_dir().glob("*"):
        if p.stat().st_mtime < cutoff:
            p.unlink(missing_ok=True)


def save_upload(file: UploadFile) -> UploadOut:
    original = Path(file.filename or "upload").name
    if Path(original).suffix.lower() not in UPLOAD_EXTENSIONS:
        raise HTTPException(415, f"Unsupported file type. Allowed: {', '.join(sorted(UPLOAD_EXTENSIONS))}")
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"File larger than {settings.max_upload_bytes // (1024 * 1024)} MB")
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(415, "The file could not be decoded as an image.")
    h, w = img.shape[:2]
    if not (MIN_EDGE <= w <= MAX_EDGE and MIN_EDGE <= h <= MAX_EDGE) or w * h > settings.max_pixels:
        raise HTTPException(422, f"Image is {w}x{h}; edges must be {MIN_EDGE}..{MAX_EDGE} px and the total at most "
                                 f"{settings.max_pixels:,} pixels.")
    _cleanup_uploads()
    upload_id = hashlib.sha256(data + str(time.time_ns()).encode()).hexdigest()[:12]
    rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    target = _uploads_dir() / f"{upload_id}.ppm"
    with target.open("wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode("ascii"))
        f.write(rgb.tobytes())
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", original)[:80]
    meta = {"width": w, "height": h, "sha256": hashlib.sha256(data).hexdigest(), "original_name": safe_name,
            "bytes": len(data)}
    (_uploads_dir() / f"{upload_id}.json").write_text(json.dumps(meta), encoding="utf-8")
    return UploadOut(upload_id=upload_id, **meta)


def _upload_meta(upload_id: str) -> dict:
    path = _uploads_dir() / f"{upload_id}.json"
    if not path.exists() or not (_uploads_dir() / f"{upload_id}.ppm").exists():
        raise HTTPException(404, "Upload not found or expired; upload the image again.")
    return json.loads(path.read_text(encoding="utf-8"))


# ---- creation --------------------------------------------------------------------

def create_experiment(db: Session, cfg: ExperimentConfig, kind: str) -> Experiment:
    if kind == "comparison":
        if len(cfg.strategies) < 2:
            raise HTTPException(422, "A comparison needs at least two strategies.")
        if not any(s.strategy == Strategy.row_major for s in cfg.strategies):
            # Speedups are only meaningful against a baseline timed in the same group.
            cfg.strategies.insert(0, StrategySpec(strategy=Strategy.row_major))
    elif len(cfg.strategies) != 1:
        raise HTTPException(422, "A single experiment takes exactly one strategy; use /api/experiments/compare.")

    width, height, detail = cfg.width, cfg.height, None
    if cfg.image_source == ImageSource.upload:
        meta = _upload_meta(cfg.upload_id)
        width, height = meta["width"], meta["height"]
        detail = f"upload {meta['original_name']} sha256:{meta['sha256'][:16]}"
        for s in cfg.strategies:
            if s.strategy == Strategy.tiled and (s.tile_w > width or s.tile_h > height):
                raise HTTPException(422, f"tile {s.tile_w}x{s.tile_h} is larger than the uploaded {width}x{height} image")
    elif cfg.image_source == ImageSource.photo:
        detail = "grace_hopper.jpg (matplotlib sample data) via scripts/prepare_images.py"
    else:
        detail = f"synthetic '{cfg.image_source.value}' generated by the engine"

    names = ", ".join(variant_label(s.token) for s in cfg.strategies)
    exp = Experiment(
        kind=kind,
        name=(cfg.name or f"{cfg.op.value} {cfg.mapping.value} {width}x{height}: {names}")[:120],
        status="queued",
        config_json=cfg.model_dump_json(),
        op=cfg.op.value, mapping=cfg.mapping.value, width=width, height=height,
        image_source=cfg.image_source.value, image_detail=detail, condition=cfg.condition.value, reps=cfg.reps,
    )
    db.add(exp)
    db.commit()
    return exp


# ---- execution -------------------------------------------------------------------

def execute(job_id: str, suite_runner=None) -> None:
    with SessionLocal() as db:
        exp = db.get(Experiment, job_id)
        if exp is None or exp.status != "queued":   # deleted while waiting, or already handled
            return
        exp.status, exp.started_at = "running", utcnow()
        db.commit()

    job_dir = settings.jobs_dir / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True)
    t0 = time.perf_counter()
    status, public, detail = "completed", None, None
    try:
        with SessionLocal() as db:
            exp = db.get(Experiment, job_id)
            if exp.kind == "suite":
                suite_runner(db, exp, job_dir)
            else:
                _run_experiment(db, exp, job_dir)
    except er.EngineError as e:
        status, public, detail = "failed", e.public, e.detail
    except Exception:  # noqa: BLE001 - recorded, never swallowed
        log.exception("experiment %s failed", job_id)
        status, public = "failed", "Internal error while running the experiment."
        detail = er.sanitize(traceback.format_exc()[-3000:], job_dir)
    finally:
        if not settings.keep_job_dirs:
            shutil.rmtree(job_dir, ignore_errors=True)
        with SessionLocal() as db:
            exp = db.get(Experiment, job_id)
            if exp is not None:
                exp.status = status
                exp.finished_at = utcnow()
                exp.engine_seconds = round(time.perf_counter() - t0, 3)
                if public:
                    exp.error_message, exp.error_detail = public, detail
                db.commit()


def _prepare_input(cfg: ExperimentConfig, width: int, height: int, job_dir: Path) -> str:
    """Put the input where the engine expects it; returns the engine's --image kind."""
    if cfg.image_source in (ImageSource.gradient, ImageSource.noise, ImageSource.mixed):
        return cfg.image_source.value
    target = job_dir / f"photo_{width}x{height}.ppm"
    if cfg.image_source == ImageSource.upload:
        shutil.copyfile(_uploads_dir() / f"{cfg.upload_id}.ppm", target)
        return "photo"
    cached = settings.photo_dir / target.name
    if cached.exists():   # produced earlier by the same deterministic script
        shutil.copyfile(cached, target)
    else:
        er.run_process(Path(sys.executable),
                       [str(er.SCRIPTS["prepare_images"]), "--sizes", f"{width}x{height}", "--out", str(job_dir)],
                       cwd=settings.repo_root, timeout_s=300, job_dir=job_dir)
    if not target.exists():
        raise er.EngineError("The photo input could not be prepared.")
    return "photo"


def store_bench_results(db: Session, exp: Experiment, rows, samples, system: dict) -> list[VariantResult]:
    """Insert one VariantResult per summary row and its repetitions (matched on the full group key)."""
    key = lambda r: (r.suite, r.build_variant, r.image_kind, r.width, r.height, r.op, r.mapping, r.label,  # noqa: E731
                     r.condition)
    by_key: dict[tuple, list] = {}
    for s in samples:
        by_key.setdefault(key(s), []).append(s)
    stored = []
    for r in rows:
        vr = VariantResult(experiment_id=exp.id, **r.model_dump(exclude={"pixels"}))
        reps = by_key.get(key(r), [])
        if len(reps) != r.reps:
            raise er.EngineError("Engine output is inconsistent: repetition count does not match the summary.")
        vr.repetitions = [Repetition(rep=s.rep, inner_iters=s.inner_iters, ms_per_run=s.ms_per_run,
                                     tsc_ticks_per_run=s.tsc_ticks_per_run, core_ghz_probe=s.core_ghz_probe)
                          for s in reps]
        db.add(vr)
        stored.append(vr)
    exp.environment_json = json.dumps(system) if system else None
    exp.build_variant = system.get("build_variant") or rows[0].build_variant
    exp.compiler = system.get("compiler")
    exp.build_flags = system.get("build_flags")
    db.commit()
    return stored


def _run_experiment(db: Session, exp: Experiment, job_dir: Path) -> None:
    cfg = ExperimentConfig.model_validate_json(exp.config_json)
    w, h = exp.width, exp.height
    image_kind = _prepare_input(cfg, w, h, job_dir)
    tokens = [s.token for s in cfg.strategies]

    args = er.bench_single_args(op=cfg.op.value, mapping=cfg.mapping.value, tokens=tokens, width=w, height=h,
                                image_kind=image_kind, reps=cfg.reps, condition=cfg.condition.value, job_dir=job_dir)
    run = er.run_process(settings.bench_bin, args, cwd=job_dir, timeout_s=settings.experiment_timeout_s,
                         job_dir=job_dir)
    exp.engine_command = json.dumps(run.argv_public)
    db.commit()
    rows, samples, system = er.parse_bench(job_dir)
    expected = {variant_label(t) for t in tokens}
    got = {r.label for r in rows}
    if got != expected:
        raise er.EngineError("Engine output does not match the requested strategies.",
                             f"expected {sorted(expected)}, got {sorted(got)}")
    stored = store_bench_results(db, exp, rows, samples, system)

    # Cache model on exactly what was timed: adaptive variants use the tile they chose.
    if cfg.cache_sim.enabled:
        if w * h > settings.max_sim_pixels:
            exp.cache_geometry_json = json.dumps({"skipped": f"image larger than the {settings.max_sim_pixels:,}-pixel "
                                                             "simulation limit"})
        else:
            token_for = {}
            for vr in stored:
                t = f"tiled:{vr.tile_w}x{vr.tile_h}" if vr.strategy in ("tiled", "adaptive") else vr.label
                token_for.setdefault(t, []).append(vr)
            sim_tokens = list(token_for)
            er.run_process(settings.sim_bin, er.sim_args(width=w, height=h, mapping=cfg.mapping.value,
                                                         tokens=sim_tokens, custom=cfg.cache_sim.custom_levels(),
                                                         job_dir=job_dir),
                           cwd=job_dir, timeout_s=settings.sim_timeout_s, job_dir=job_dir)
            sim_rows, geometry = er.parse_sim(job_dir)
            sim_label_to_token = {variant_label(t): t for t in sim_tokens}
            for r in sim_rows:
                for vr in token_for.get(sim_label_to_token.get(r.label, ""), []):
                    db.add(CacheSimRow(experiment_id=exp.id, source=r.source, width=r.width, height=r.height,
                                       mapping=r.mapping, label=vr.label, sim_label=r.label, tile_w=r.tile_w,
                                       tile_h=r.tile_h, level=r.level, accesses=r.accesses, misses=r.misses,
                                       miss_rate=r.miss_rate, misses_per_px=r.misses_per_px, writebacks=r.writebacks,
                                       dram_read_bytes_per_px=r.dram_read_bytes_per_px,
                                       dram_write_bytes_per_px=r.dram_write_bytes_per_px))
            exp.cache_geometry_json = json.dumps(geometry)
        db.commit()

    # Reference validation of the conversion on this very image (outside any timing).
    if not cfg.validate_reference:
        exp.validation_json = json.dumps({"ran": False, "reason": "disabled in the experiment configuration"})
    elif cfg.op.value == "index_only":
        exp.validation_json = json.dumps({"ran": False, "reason": "index_only produces no pixel output"})
    elif w * h > settings.max_validation_pixels:
        exp.validation_json = json.dumps({"ran": False, "reason": f"image larger than the "
                                                                  f"{settings.max_validation_pixels:,}-pixel validation "
                                                                  "limit (the output hash check still applies)"})
    else:
        out_dir = job_dir / "validation"
        out_dir.mkdir()
        er.run_process(Path(sys.executable),
                       [str(er.SCRIPTS["validate_reference"]), "--bench", str(settings.bench_bin), "--data",
                        str(job_dir), "--images", f"{image_kind}:{w}x{h}", "--out", str(out_dir)],
                       cwd=settings.repo_root, timeout_s=settings.validation_timeout_s, job_dir=job_dir, check=False)
        exp.validation_json = json.dumps({"ran": True, "references": er.parse_validation(out_dir, cfg.op.value)})
    db.commit()


# ---- reading ---------------------------------------------------------------------

def _speedups(results: list[VariantResult]) -> dict[int, float | None]:
    base = {}
    for r in results:
        if r.label == "row_major":
            base[(r.suite, r.build_variant, r.image_kind, r.width, r.height, r.op, r.mapping, r.condition)] = r
    out = {}
    for r in results:
        b = base.get((r.suite, r.build_variant, r.image_kind, r.width, r.height, r.op, r.mapping, r.condition))
        out[r.id] = (b.median_ms / r.median_ms) if b is not None and r.median_ms > 0 else None
    return out


def summarize(exp: Experiment) -> ExperimentSummary:
    cfg = json.loads(exp.config_json)
    strategies = [variant_label(StrategySpec(**s).token) for s in cfg.get("strategies", [])] or \
        sorted({r.label for r in exp.results})
    best = min(exp.results, key=lambda r: r.median_ms) if exp.results else None
    row = next((r for r in exp.results if r.label == "row_major"), None)
    matches = [r.output_matches_baseline for r in exp.results if r.output_matches_baseline is not None]
    return ExperimentSummary(
        id=exp.id, kind=exp.kind, name=exp.name, status=exp.status, created_at=exp.created_at,
        finished_at=exp.finished_at, op=exp.op, mapping=exp.mapping, width=exp.width, height=exp.height,
        image_source=exp.image_source, condition=exp.condition, reps=exp.reps, suite_name=exp.suite_name,
        strategies=strategies, best_label=best.label if best and exp.kind != "suite" else None,
        best_median_ms=best.median_ms if best and exp.kind != "suite" else None,
        row_major_median_ms=row.median_ms if row and exp.kind != "suite" else None,
        all_outputs_match=all(matches) if matches else None, result_count=len(exp.results))


def detail(exp: Experiment) -> ExperimentDetail:
    s = summarize(exp)
    sp = _speedups(exp.results)
    results = []
    for r in exp.results:
        out = VariantResultOut.model_validate(r)
        out.speedup_vs_row_major = sp.get(r.id)
        out.repetitions = [RepetitionOut.model_validate(x) for x in r.repetitions]
        results.append(out)
    load = lambda v: json.loads(v) if v else None  # noqa: E731
    return ExperimentDetail(
        **s.model_dump(), started_at=exp.started_at, config=json.loads(exp.config_json),
        image_detail=exp.image_detail, build_variant=exp.build_variant, compiler=exp.compiler,
        build_flags=exp.build_flags, environment=load(exp.environment_json),
        cache_geometry=load(exp.cache_geometry_json), validation=load(exp.validation_json),
        engine_command=load(exp.engine_command), engine_seconds=exp.engine_seconds,
        error_message=exp.error_message, error_detail=exp.error_detail, queue_position=queue.position(exp.id),
        results=results, cache=[CacheRowOut.model_validate(c) for c in exp.cache_rows])


def get_or_404(db: Session, experiment_id: str) -> Experiment:
    if not re.fullmatch(r"[0-9a-f]{12}", experiment_id or ""):
        raise HTTPException(404, "Experiment not found.")
    exp = db.scalar(select(Experiment).where(Experiment.id == experiment_id).options(
        selectinload(Experiment.results).selectinload(VariantResult.repetitions),
        selectinload(Experiment.cache_rows)))
    if exp is None:
        raise HTTPException(404, "Experiment not found.")
    return exp


def list_experiments(db: Session, *, page: int, page_size: int, status: str | None, op: str | None,
                     mapping: str | None, kind: str | None, strategy: str | None, q: str | None):
    stmt = select(Experiment)
    if status:
        stmt = stmt.where(Experiment.status == status)
    if op:
        stmt = stmt.where(Experiment.op == op)
    if mapping:
        stmt = stmt.where(Experiment.mapping == mapping)
    if kind:
        stmt = stmt.where(Experiment.kind == kind)
    if strategy:
        stmt = stmt.where(Experiment.config_json.contains(f'"strategy":"{strategy}"'))
    if q:
        stmt = stmt.where(Experiment.name.ilike(f"%{q}%") | Experiment.id.ilike(f"{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Experiment.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
                      .options(selectinload(Experiment.results))).all()
    return [summarize(e) for e in rows], total


def delete_experiment(db: Session, experiment_id: str) -> None:
    exp = get_or_404(db, experiment_id)
    if exp.status == "running":
        raise HTTPException(409, "This experiment is running; wait for it to finish before deleting it.")
    if exp.status == "queued":
        queue.discard(exp.id)
    files = [settings.reports_dir / r.filename for r in exp.reports]
    db.delete(exp)
    db.commit()
    for f in files:
        f.unlink(missing_ok=True)


def utc_age(dt: datetime | None) -> float | None:
    return None if dt is None else (datetime.now(timezone.utc) - dt).total_seconds()
