"""Backend settings.

Everything that touches the filesystem or the engine comes from here, never
from a request: executable paths, the data directory and limits are fixed at
start-up (environment variables or `backend/.env`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
EXE = ".exe" if os.name == "nt" else ""


def _load_dotenv(path: Path) -> None:
    """Minimal KEY=VALUE reader so a .env file works without extra packages."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def _path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).resolve() if value else default


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    build_dir: Path
    bench_bin: Path
    sim_bin: Path
    data_dir: Path            # backend state: database, job directories, reports
    photo_dir: Path           # repository data/ folder with photo_WxH.ppm inputs
    database_url: str
    frontend_origins: tuple[str, ...]
    experiment_timeout_s: int
    suite_timeout_s: int
    sim_timeout_s: int
    validation_timeout_s: int
    max_queued_jobs: int
    max_upload_bytes: int
    max_pixels: int
    max_sim_pixels: int
    max_validation_pixels: int
    max_request_bytes: int = field(default=0)
    keep_job_dirs: bool = False   # debugging aid: keep raw engine output after parsing
    post_limit_per_minute: int = 30

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"


def load_settings() -> Settings:
    _load_dotenv(REPO_ROOT / "backend" / ".env")
    build = _path("PIXELCACHE_BUILD_DIR", REPO_ROOT / "build")
    data = _path("PIXELCACHE_DATA_DIR", REPO_ROOT / "backend" / "data")
    max_upload = _int("PIXELCACHE_MAX_UPLOAD_MB", 25) * 1024 * 1024
    origins = os.environ.get("PIXELCACHE_FRONTEND_ORIGIN", "http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        repo_root=REPO_ROOT,
        build_dir=build,
        bench_bin=build / f"cachevision_bench_native{EXE}",
        sim_bin=build / f"cachevision_sim{EXE}",
        data_dir=data,
        photo_dir=REPO_ROOT / "data",
        database_url=os.environ.get("PIXELCACHE_DATABASE_URL", f"sqlite:///{(data / 'pixelcache.db').as_posix()}"),
        frontend_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        experiment_timeout_s=_int("PIXELCACHE_EXPERIMENT_TIMEOUT_S", 900),
        suite_timeout_s=_int("PIXELCACHE_SUITE_TIMEOUT_S", 7200),
        sim_timeout_s=_int("PIXELCACHE_SIM_TIMEOUT_S", 600),
        validation_timeout_s=_int("PIXELCACHE_VALIDATION_TIMEOUT_S", 300),
        max_queued_jobs=_int("PIXELCACHE_MAX_QUEUED_JOBS", 8),
        max_upload_bytes=max_upload,
        max_pixels=_int("PIXELCACHE_MAX_PIXELS", 8192 * 8192),
        max_sim_pixels=_int("PIXELCACHE_MAX_SIM_PIXELS", 4096 * 4096),
        max_validation_pixels=_int("PIXELCACHE_MAX_VALIDATION_PIXELS", 1024 * 1024),
        max_request_bytes=max_upload + 1024 * 1024,
        keep_job_dirs=os.environ.get("PIXELCACHE_KEEP_JOB_DIRS", "0") == "1",
        post_limit_per_minute=_int("PIXELCACHE_POST_LIMIT_PER_MINUTE", 30),
    )


settings = load_settings()
