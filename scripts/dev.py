#!/usr/bin/env python3
"""Start the PixelCache backend (FastAPI on :8000) and frontend (Vite on :5173) together.

    python scripts/dev.py            # both servers; Ctrl+C stops both
    python scripts/dev.py --check    # only verify prerequisites

The C++ engine stays independent: build it with CMake first (see README) and it
can still be run directly from build/ without the web application.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ".exe" if os.name == "nt" else ""


def check() -> list[str]:
    problems = []
    if not (ROOT / "build" / f"cachevision_bench_native{EXE}").exists():
        problems.append("C++ engine not built: cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build")
    for mod in ("fastapi", "uvicorn", "sqlalchemy", "multipart", "cv2", "matplotlib"):
        try:
            __import__(mod)
        except ImportError:
            problems.append(f"Python package missing ({mod}): pip install -r backend/requirements.txt")
            break
    if shutil.which("npm") is None:
        problems.append("npm not found: install Node.js 20+")
    elif not (ROOT / "frontend" / "node_modules").exists():
        problems.append("frontend dependencies missing: npm --prefix frontend install")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    problems = check()
    for p in problems:
        print("x", p)
    if args.check or problems:
        print("ok" if not problems else "")
        return 1 if problems else 0

    npm = shutil.which("npm")
    procs = [
        subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", "backend",
                          "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT),
        subprocess.Popen([npm, "--prefix", "frontend", "run", "dev"], cwd=ROOT),
    ]
    print("backend  http://127.0.0.1:8000/docs\nfrontend http://localhost:5173  (Ctrl+C stops both)")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
