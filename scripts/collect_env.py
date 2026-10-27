#!/usr/bin/env python3
"""Record the measurement environment that the C++ binary cannot see.

Writes results/environment.json with: OS power plan / governor, AC power,
battery, Python package versions, CMake/compiler versions, git commit, and a
snapshot of the busiest background processes (noise sources).
Run once before and once after a benchmark session (--tag before/after).
"""
import argparse
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as e:  # noqa: BLE001 - environment probing must never fail the pipeline
        return f"unavailable ({e.__class__.__name__})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("results", "environment.json"))
    ap.add_argument("--tag", default="before")
    ap.add_argument("--cxx", default="g++")
    args = ap.parse_args()

    env = {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "tag": args.tag, "platform": platform.platform(), "machine": platform.machine(),
           "python": sys.version.split()[0]}
    for mod in ("numpy", "pandas", "matplotlib", "cv2", "psutil"):
        try:
            m = __import__(mod)
            env[f"{mod}_version"] = getattr(m, "__version__", "?")
        except ImportError:
            env[f"{mod}_version"] = "not installed"
    env["cmake"] = run(["cmake", "--version"]).splitlines()[0] if shutil.which("cmake") else "not found"
    env["cxx"] = run([args.cxx, "--version"]).splitlines()[0] if shutil.which(args.cxx) else "not found"
    env["git_commit"] = run(["git", "rev-parse", "HEAD"]) or "not a git checkout"

    if os.name == "nt":
        env["power_plan"] = run(["powercfg", "/getactivescheme"])
    else:
        gov = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
        env["cpufreq_governor"] = open(gov).read().strip() if os.path.exists(gov) else "unknown"
        nt = "/sys/devices/system/cpu/intel_pstate/no_turbo"
        env["intel_no_turbo"] = open(nt).read().strip() if os.path.exists(nt) else "unknown"

    try:
        import psutil
        bat = psutil.sensors_battery()
        env["ac_power"] = None if bat is None else bool(bat.power_plugged)
        env["battery_percent"] = None if bat is None else bat.percent
        env["logical_cpus"] = psutil.cpu_count()
        env["physical_cpus"] = psutil.cpu_count(logical=False)
        env["total_memory_bytes"] = psutil.virtual_memory().total
        env["available_memory_bytes"] = psutil.virtual_memory().available
        procs = []
        for p in psutil.process_iter(["name", "cpu_percent"]):
            p.cpu_percent(None)
        psutil.cpu_percent(interval=1.0)
        for p in psutil.process_iter(["name"]):
            try:
                procs.append((p.cpu_percent(None), p.info["name"]))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(reverse=True)
        env["system_cpu_percent_1s"] = psutil.cpu_percent(interval=None)
        env["top_processes_cpu_percent"] = [{"name": n, "cpu_percent": round(c, 1)} for c, n in procs[:8]]
    except ImportError:
        env["psutil"] = "not installed: AC power and background load not recorded"

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    data = {}
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            data = json.load(f)
    data[args.tag] = env
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"environment ({args.tag}): AC power={env.get('ac_power')}, battery={env.get('battery_percent')}%, "
          f"power plan={env.get('power_plan', env.get('cpufreq_governor'))}")


if __name__ == "__main__":
    main()
