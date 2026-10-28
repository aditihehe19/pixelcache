"""Controlled invocation of the C++ engine and parsing of its output.

Rules enforced here (and relied on by every caller):
  * Only three programs can ever be started: the benchmark binary, the cache
    simulator (both at fixed paths from settings) and the current Python
    interpreter running one of two repository scripts.
  * Arguments are passed as a list (no shell), every token is a string built
    from validated enums/integers, and variant tokens are re-checked against
    the engine's grammar right before launch.
  * Each run has a timeout, captured stdout/stderr and an exit-code check.
  * Engine output files are parsed into Pydantic models; anything missing or
    malformed is an error, never silently replaced by a default.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator

from app.core.config import settings
from app.core.validation import VARIANT_TOKEN

SCRIPTS = {
    "prepare_images": settings.repo_root / "scripts" / "prepare_images.py",
    "validate_reference": settings.repo_root / "scripts" / "validate_reference.py",
}


class EngineError(Exception):
    """A failed engine step. `public` is safe to show to users; `detail` is a sanitised log excerpt."""

    def __init__(self, public: str, detail: str = "") -> None:
        super().__init__(public)
        self.public = public
        self.detail = detail


@dataclass
class ProcessResult:
    argv_public: list[str]
    returncode: int
    stdout: str
    stderr: str
    seconds: float


def sanitize(text: str, *dirs: Path) -> str:
    """Replace absolute paths with placeholders before text leaves the server."""
    replacements = [(str(d), "<job>") for d in dirs]
    replacements += [(str(settings.data_dir), "<data>"), (str(settings.build_dir), "<build>"),
                     (str(settings.repo_root), "<repo>"), (str(Path.home()), "<home>")]
    for old, new in sorted(replacements, key=lambda r: -len(r[0])):
        for variant in {old, old.replace("\\", "/")}:
            text = text.replace(variant, new)
    return text


def _allowed_program(program: Path) -> bool:
    return program in (settings.bench_bin, settings.sim_bin, Path(sys.executable))


def run_process(program: Path, args: list[str], cwd: Path, timeout_s: int, job_dir: Path,
                check: bool = True) -> ProcessResult:
    if not _allowed_program(program):
        raise EngineError("internal error: refusing to start an unexpected program")
    if program == Path(sys.executable) and (not args or Path(args[0]) not in SCRIPTS.values()):
        raise EngineError("internal error: refusing to run an unexpected script")
    if not program.exists():
        raise EngineError(f"{program.name} is not built. Build the engine first (see README: cmake --build build).")
    if any(not isinstance(a, str) or "\x00" in a for a in args):
        raise EngineError("internal error: invalid engine argument")

    argv = [str(program), *args]
    public = [sanitize(a, job_dir) for a in argv]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_s, shell=False,
                              stdin=subprocess.DEVNULL, creationflags=creationflags, encoding="utf-8",
                              errors="replace")
    except subprocess.TimeoutExpired as e:  # subprocess.run kills the child before raising
        tail = (e.stderr or "")[-2000:] if isinstance(e.stderr, str) else ""
        raise EngineError(f"{program.name} exceeded the {timeout_s} s time limit and was stopped.",
                          sanitize(tail, job_dir)) from None
    except OSError as e:
        raise EngineError(f"{program.name} could not be started.", sanitize(str(e), job_dir)) from None
    result = ProcessResult(public, proc.returncode, proc.stdout, proc.stderr, time.perf_counter() - t0)
    if check and proc.returncode != 0:
        raise EngineError(f"{Path(argv[0]).name} exited with code {proc.returncode}.",
                          sanitize((proc.stderr or proc.stdout)[-4000:], job_dir))
    return result


# ---- argument builders ------------------------------------------------------------

def bench_single_args(*, op: str, mapping: str, tokens: list[str], width: int, height: int, image_kind: str,
                      reps: int, condition: str, job_dir: Path) -> list[str]:
    for t in tokens:
        if not VARIANT_TOKEN.match(t):
            raise EngineError("internal error: invalid variant token")
    return ["--single", "--op", op, "--mapping", mapping, "--variant", ",".join(tokens),
            "--size", f"{width}x{height}", "--image", image_kind, "--reps", str(reps),
            "--condition", condition, "--data", str(job_dir), "--out", str(job_dir)]


def bench_suite_args(*, suite: str, quick: bool, job_dir: Path) -> list[str]:
    args = ["--config", str(settings.repo_root / "benchmarks" / "benchmark_config.json"), "--suites", suite,
            "--data", str(settings.photo_dir), "--out", str(job_dir)]
    return args + (["--quick"] if quick else [])


def sim_args(*, width: int, height: int, mapping: str, tokens: list[str], custom: dict[str, tuple[int, int]],
             job_dir: Path) -> list[str]:
    for t in tokens:
        if t != "adaptive_model" and not VARIANT_TOKEN.match(t):
            raise EngineError("internal error: invalid simulator variant")
    args = ["--size", f"{width}x{height}", "--mappings", mapping, "--variants", ",".join(tokens)]
    for lvl, (kib, ways) in custom.items():
        args += [f"--{lvl}", f"{int(kib)}:{int(ways)}"]
    return args + ["--out", str(job_dir)]


# ---- parsing ---------------------------------------------------------------------

def _na(v: Any) -> Any:
    return None if v in ("NA", "", None) else v


class BenchRow(BaseModel):
    suite: str
    build_variant: str
    image_kind: str
    width: int
    height: int
    pixels: float
    op: str
    mapping: str
    strategy: str
    label: str
    tile_w: int
    tile_h: int
    condition: str
    reps: int
    inner_iters: int
    median_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float
    stdev_ms: float
    p25_ms: float
    p75_ms: float
    cv_pct: float
    ns_per_px: float
    mpix_per_s: float
    tsc_ticks_per_px: float | None
    core_ghz_probe: float | None
    est_core_cycles_per_px: float | None
    model_bytes_per_px: float | None
    est_bw_gbps: float | None
    setup_ms: float | None
    setup_note: str | None
    output_hash: str | None
    output_matches_baseline: bool | None
    hw_counters: str

    @field_validator("*", mode="before")
    @classmethod
    def _missing(cls, v: Any) -> Any:
        return _na(v)

    @field_validator("output_matches_baseline", mode="before")
    @classmethod
    def _flag(cls, v: Any) -> Any:
        return None if v is None else str(v) == "1"


class SampleRow(BaseModel):
    suite: str
    build_variant: str
    image_kind: str
    width: int
    height: int
    op: str
    mapping: str
    label: str
    condition: str
    rep: int
    inner_iters: int
    ms_per_run: float
    tsc_ticks_per_run: float | None
    core_ghz_probe: float | None

    @field_validator("*", mode="before")
    @classmethod
    def _missing(cls, v: Any) -> Any:
        return _na(v)


class SimRow(BaseModel):
    source: str
    width: int
    height: int
    mapping: str
    label: str
    tile_w: int
    tile_h: int
    level: str
    accesses: int
    misses: int
    miss_rate: float
    misses_per_px: float
    writebacks: int
    dram_read_bytes_per_px: float
    dram_write_bytes_per_px: float


def _read_rows(path: Path, model: type[BaseModel], what: str) -> list[Any]:
    if not path.exists():
        raise EngineError(f"The engine finished but produced no {what} file.")
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return [model.model_validate(row) for row in csv.DictReader(f)]
    except (ValidationError, ValueError) as e:
        raise EngineError(f"The engine's {what} output could not be parsed.", str(e)[:2000]) from None


def parse_bench(job_dir: Path, build_variant: str = "native") -> tuple[list[BenchRow], list[SampleRow], dict]:
    rows = _read_rows(job_dir / f"bench_{build_variant}.csv", BenchRow, "benchmark summary")
    samples = _read_rows(job_dir / f"samples_{build_variant}.csv", SampleRow, "repetition")
    sys_path = job_dir / f"system_{build_variant}.json"
    system = json.loads(sys_path.read_text(encoding="utf-8")) if sys_path.exists() else {}
    if not rows:
        raise EngineError("The engine finished without reporting any measurement.")
    return rows, samples, system


def parse_sim(job_dir: Path) -> tuple[list[SimRow], dict]:
    rows = _read_rows(job_dir / "cachesim.csv", SimRow, "cache simulation")
    geo_path = job_dir / "cachesim_geometry.json"
    geometry = json.loads(geo_path.read_text(encoding="utf-8")) if geo_path.exists() else {}
    if any(r.source != "model" for r in rows):
        raise EngineError("Unexpected cache-simulation source tag.")
    return rows, geometry


def parse_validation(out_dir: Path, op: str) -> dict:
    """Rows of validate_reference.py for one op, grouped by reference."""
    path = out_dir / "validation_summary.csv"
    if not path.exists():
        raise EngineError("Reference validation produced no summary.")
    refs: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["op"] != op:
                continue
            ref = refs.setdefault(row["reference"], {"channels": [], "judged": True, "passed": True})
            judged = row["pass"] != "n/a"
            ref["channels"].append({
                "channel": row["channel"], "max_abs_err": float(row["max_abs_err"]),
                "mean_abs_err": float(row["mean_abs_err"]), "p99_abs_err": float(row["p99_abs_err"]),
                "tolerance": None if row["tolerance"] == "n/a" else float(row["tolerance"]),
                "pass": None if not judged else row["pass"] == "1",
            })
            if not judged:
                ref["judged"] = False
            elif row["pass"] != "1":
                ref["passed"] = False
    for ref in refs.values():
        if not ref["judged"]:
            ref["passed"] = None
    return refs
