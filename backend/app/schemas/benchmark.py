"""Schemas for benchmark suites, system info, health and analytics."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SuiteInfo(BaseModel):
    name: str
    description: str
    sizes: list[list[int]]
    ops: list[str]
    mappings: list[str]
    variants: list[str]
    conditions: list[str]
    reps: int
    groups: int            # sizes x images x mappings x ops
    quick_groups: int      # groups left in --quick mode (sizes <= 2048x2048)


class BenchmarkRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str = Field(pattern=r"^[a-z_]{1,40}$")
    quick: bool = True
    name: str | None = Field(default=None, max_length=120)


class HealthOut(BaseModel):
    status: str
    database: str
    schema_version: int
    engine: dict[str, Any]
    queue: dict[str, Any]


class Detected(BaseModel):
    """A host property with its provenance, so the UI never presents an unknown as a fact."""

    value: Any
    source: str   # e.g. "cpuid.4", "os", "measured", "compile-time", "unavailable"


class SystemInfoOut(BaseModel):
    available: bool
    reason: str | None = None
    cpu: Detected | None = None
    hybrid: Detected | None = None
    logical_processors: Detected | None = None
    physical_cores: Detected | None = None
    core_types: Detected | None = None
    memory_bytes: Detected | None = None
    os: Detected | None = None
    compiler: Detected | None = None
    build_flags: Detected | None = None
    simd: Detected | None = None
    tsc_ghz: Detected | None = None
    ac_power: Detected | None = None
    pinned_cpu: Detected | None = None
    caches: list[dict[str, Any]] = []
    tlbs: Detected | None = None
    hardware_counters: Detected | None = None


class Capabilities(BaseModel):
    operations: list[dict[str, str]]
    strategies: list[dict[str, str]]
    mappings: list[str]
    image_sources: list[dict[str, str]]
    conditions: list[str]
    limits: dict[str, int]
    engine_available: bool
    simulator_available: bool
