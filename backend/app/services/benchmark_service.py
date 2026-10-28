"""Benchmark suites from benchmarks/benchmark_config.json, run through the engine's own driver."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.experiment import Experiment
from app.schemas.benchmark import BenchmarkRunRequest, SuiteInfo
from app.services import engine_runner as er
from app.services.experiment_service import store_bench_results

CONFIG_PATH = settings.repo_root / "benchmarks" / "benchmark_config.json"
QUICK_MAX_PIXELS = 2048 * 2048  # mirrors the engine's --quick rule


def _load_config() -> dict:
    # The config allows // comments (the engine's mini_json skips them).
    text = "\n".join(line for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("//"))
    return json.loads(text)


def _sizes(suite: dict) -> list[tuple[int, int]]:
    return [(int(s), int(s)) if isinstance(s, (int, float)) else (int(s[0]), int(s[1])) for s in suite["sizes"]]


def list_suites() -> list[SuiteInfo]:
    cfg = _load_config()
    d = cfg.get("defaults", {})
    out = []
    for name, s in cfg["suites"].items():
        get = lambda k: s.get(k, d.get(k))  # noqa: E731
        sizes = _sizes(s)
        per_size = len(get("images")) * len(get("mappings")) * len(get("ops"))
        out.append(SuiteInfo(
            name=name, description=s.get("description", ""), sizes=[list(x) for x in sizes], ops=get("ops"),
            mappings=get("mappings"), variants=get("variants"), conditions=get("conditions"), reps=int(get("reps")),
            groups=len(sizes) * per_size,
            quick_groups=sum(1 for w, h in sizes if w * h <= QUICK_MAX_PIXELS) * per_size))
    return out


def create_suite_run(db: Session, req: BenchmarkRunRequest) -> Experiment:
    suites = {s.name: s for s in list_suites()}
    if req.suite not in suites:
        raise HTTPException(404, f"Unknown suite '{req.suite}'.")
    info = suites[req.suite]
    if req.quick and info.quick_groups == 0:
        raise HTTPException(422, "Every size in this suite exceeds the quick-mode limit; run it without quick.")
    exp = Experiment(kind="suite", name=(req.name or f"suite {req.suite}{' (quick)' if req.quick else ''}")[:120],
                     status="queued", config_json=req.model_dump_json(), suite_name=req.suite)
    db.add(exp)
    db.commit()
    return exp


def _ensure_photos(suite_name: str, quick: bool, job_dir: Path) -> None:
    """Generate any missing photo_WxH.ppm the suite needs (deterministic script, written to data/)."""
    suite = _load_config()["suites"][suite_name]
    images = suite.get("images", _load_config().get("defaults", {}).get("images", []))
    if "photo" not in images:
        return
    missing = [f"{w}x{h}" for w, h in _sizes(suite)
               if not (quick and w * h > QUICK_MAX_PIXELS) and not (settings.photo_dir / f"photo_{w}x{h}.ppm").exists()]
    if not missing:
        return
    tmp = job_dir / "photos"
    tmp.mkdir()
    er.run_process(Path(sys.executable), [str(er.SCRIPTS["prepare_images"]), "--sizes", ",".join(missing),
                                          "--out", str(tmp)], cwd=settings.repo_root, timeout_s=900, job_dir=job_dir)
    settings.photo_dir.mkdir(exist_ok=True)
    for p in tmp.glob("photo_*.ppm"):   # move only the images; keep data/photo_manifest.csv intact
        if re.fullmatch(r"photo_\d+x\d+\.ppm", p.name):
            shutil.move(str(p), settings.photo_dir / p.name)


def run_suite_job(db: Session, exp: Experiment, job_dir: Path) -> None:
    req = BenchmarkRunRequest.model_validate_json(exp.config_json)
    _ensure_photos(req.suite, req.quick, job_dir)
    run = er.run_process(settings.bench_bin, er.bench_suite_args(suite=req.suite, quick=req.quick, job_dir=job_dir),
                         cwd=job_dir, timeout_s=settings.suite_timeout_s, job_dir=job_dir)
    exp.engine_command = json.dumps(run.argv_public)
    db.commit()
    rows, samples, system = er.parse_bench(job_dir)
    store_bench_results(db, exp, rows, samples, system)
