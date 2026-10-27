#!/usr/bin/env python3
"""End-to-end reproduction: build -> test -> inputs -> validate -> benchmark -> model -> analyse -> plot.

    python scripts/run_pipeline.py                 # everything (tens of minutes)
    python scripts/run_pipeline.py --quick         # smoke run, small sizes, few reps
    python scripts/run_pipeline.py --skip-build --steps bench,analyze,plot

Raw outputs go to results/raw/ (CSV/JSON). Re-running appends to the CSVs, so
pass --clean to start a fresh session.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = ".exe" if os.name == "nt" else ""
STEPS = ["build", "test", "images", "env", "validate", "vector", "sysinfo", "memory", "bench", "scalar", "sim",
         "analyze", "plot"]


def sh(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    t0 = time.time()
    subprocess.run(cmd, check=True, cwd=ROOT, **kw)
    print(f"  ({time.time() - t0:.1f}s)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default="build")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--clean", action="store_true", help="delete results/raw before running")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--steps", default=",".join(STEPS))
    ap.add_argument("--suites", default="main,tile_sweep,tile_shape,cache_condition,overhead,content,adaptive_unseen,simd_compare")
    ap.add_argument("--cmake-args", default="", help="extra arguments for the CMake configure step")
    args = ap.parse_args()
    steps = [s for s in args.steps.split(",") if s]
    if args.skip_build and "build" in steps:
        steps.remove("build")
    b = os.path.join(ROOT, args.build_dir)
    raw = os.path.join(ROOT, "results", "raw")
    if args.clean and os.path.isdir(raw):
        shutil.rmtree(raw)
    os.makedirs(raw, exist_ok=True)
    quick = ["--quick"] if args.quick else []

    if "build" in steps:
        sh(["cmake", "-S", ".", "-B", args.build_dir, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release"]
           + (args.cmake_args.split() if args.cmake_args else []))
        sh(["cmake", "--build", args.build_dir])
    if "test" in steps:
        with open(os.path.join(ROOT, "results", "test_log.txt"), "w", encoding="utf-8") as log:
            sh(["ctest", "--test-dir", args.build_dir, "--output-on-failure", "-V"], stdout=log, stderr=subprocess.STDOUT)
        print("  tests passed (log: results/test_log.txt)")
    if "images" in steps:
        sh([sys.executable, "scripts/prepare_images.py"])
    if "env" in steps:
        sh([sys.executable, "scripts/collect_env.py", "--tag", "before"])
    if "validate" in steps:
        sh([sys.executable, "scripts/validate_reference.py", "--bench", os.path.join(b, "cachevision_bench_native" + EXE)])
    if "vector" in steps:
        sh([sys.executable, "scripts/vectorization_report.py", "--build", args.build_dir])
    native = os.path.join(b, "cachevision_bench_native" + EXE)
    scalar = os.path.join(b, "cachevision_bench_scalar" + EXE)
    if "sysinfo" in steps:
        sh([native, "--sysinfo", "--out", raw])
        sh([scalar, "--sysinfo", "--out", raw])
    if "memory" in steps:
        sh([native, "--memory", "--out", raw] + quick)
    if "bench" in steps:
        sh([native, "--config", "benchmarks/benchmark_config.json", "--suites", args.suites, "--out", raw] + quick)
    if "scalar" in steps:
        sh([scalar, "--config", "benchmarks/benchmark_config.json", "--suites", "simd_compare", "--out", raw] + quick)
    if "sim" in steps:
        sizes = "256,512,1024" if args.quick else "256,512,1024,2000,2048,4096"
        sh([os.path.join(b, "cachevision_sim" + EXE), "--sizes", sizes, "--out", raw])
    if "env" in steps:
        sh([sys.executable, "scripts/collect_env.py", "--tag", "after"])
    if "analyze" in steps:
        sh([sys.executable, "scripts/analyze_results.py"])
    if "plot" in steps:
        sh([sys.executable, "scripts/plot_results.py"])
    print("done; raw data:", ", ".join(os.path.basename(p) for p in sorted(glob.glob(os.path.join(raw, "*")))))


if __name__ == "__main__":
    main()
