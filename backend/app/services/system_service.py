"""Host description via the engine's own `--sysinfo` probe (CPUID + OS APIs).

Every property is returned with its provenance so the UI can distinguish
detected facts from unavailable ones. The probe takes ~0.3 s (it measures the
TSC rate) and is cached for the lifetime of the backend process.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
from pathlib import Path

from app.core.config import settings
from app.schemas.benchmark import Detected, SystemInfoOut
from app.services import engine_runner as er

_lock = threading.Lock()
_cache: dict | None = None


def _probe() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="sysinfo-", dir=settings.data_dir))
    try:
        er.run_process(settings.bench_bin, ["--sysinfo", "--out", str(tmp)], cwd=tmp, timeout_s=30, job_dir=tmp)
        return json.loads((tmp / "system_native.json").read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def raw_system_info(refresh: bool = False) -> dict | None:
    global _cache
    with _lock:
        if _cache is None or refresh:
            try:
                _cache = _probe()
            except (er.EngineError, OSError, ValueError):
                _cache = None
        return _cache


def system_info(refresh: bool = False) -> SystemInfoOut:
    if not settings.bench_bin.exists():
        return SystemInfoOut(available=False, reason="The C++ engine is not built (build/cachevision_bench_native).")
    s = raw_system_info(refresh)
    if s is None:
        return SystemInfoOut(available=False, reason="The engine's --sysinfo probe failed.")

    def d(value, source):  # noqa: ANN001
        return Detected(value=value if value not in ("", None) else None,
                        source=source if value not in ("", None) else "unavailable")

    caches = [c for c in s.get("caches", [])]
    return SystemInfoOut(
        available=True,
        cpu=d(s.get("cpu_brand"), "cpuid"),
        hybrid=d(s.get("hybrid"), "cpuid.7"),
        logical_processors=d(s.get("logical_processors"), "os"),
        physical_cores=d(s.get("physical_cores") or None, "os"),
        core_types=d(s.get("core_types") or None, "os (efficiency classes)"),
        memory_bytes=d(s.get("total_memory_bytes"), "os"),
        os=d(s.get("os"), "os"),
        compiler=d(s.get("compiler"), "compile-time"),
        build_flags=d(s.get("build_flags"), "compile-time"),
        simd=d(s.get("simd_enabled_at_compile_time"), "compile-time"),
        tsc_ghz=d(s.get("tsc_ghz_measured"), "measured"),
        ac_power=d(None if s.get("ac_power") == "unknown" else s.get("ac_power"), "os"),
        pinned_cpu=d(None if s.get("pinned_cpu") == "none" else s.get("pinned_cpu"), "os"),
        caches=caches,
        tlbs=Detected(value=s.get("tlbs") or None,
                      source="cpuid.18" if s.get("tlbs") else "unavailable (CPUID leaf 0x18 returned no data)"),
        hardware_counters=Detected(value=None, source="unavailable: " + s.get("hardware_counters", "")),
    )
