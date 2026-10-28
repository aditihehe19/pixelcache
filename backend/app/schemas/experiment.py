"""Request/response schemas for experiments (single runs and comparisons)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import settings
from app.core.validation import (MAX_EDGE, MAX_REPS, MAX_TILE, MAX_VARIANTS, MIN_EDGE, MIN_REPS, MIN_TILE,
                                 CacheCondition, ImageSource, Mapping, Operation, Strategy, variant_token)

# ---- requests --------------------------------------------------------------------


class StrategySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Strategy
    tile_w: int | None = Field(default=None, ge=MIN_TILE, le=MAX_TILE)
    tile_h: int | None = Field(default=None, ge=MIN_TILE, le=MAX_TILE)

    @model_validator(mode="after")
    def _tiles_only_for_tiled(self) -> "StrategySpec":
        if self.strategy == Strategy.tiled:
            if self.tile_w is None or self.tile_h is None:
                raise ValueError("tile_w and tile_h are required for the tiled strategy")
        elif self.tile_w is not None or self.tile_h is not None:
            raise ValueError(f"tile_w/tile_h only apply to the tiled strategy, not {self.strategy.value}")
        return self

    @property
    def token(self) -> str:
        return variant_token(self.strategy, self.tile_w, self.tile_h)


class CacheSimConfig(BaseModel):
    """Options of `cachevision_sim`. Omitted levels use the CPUID geometry."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    l1_kib: int | None = Field(default=None, ge=4, le=1024)
    l1_ways: int | None = Field(default=None, ge=1, le=64)
    l2_kib: int | None = Field(default=None, ge=64, le=65536)
    l2_ways: int | None = Field(default=None, ge=1, le=64)
    l3_kib: int | None = Field(default=None, ge=256, le=262144)
    l3_ways: int | None = Field(default=None, ge=1, le=64)

    @model_validator(mode="after")
    def _pairs(self) -> "CacheSimConfig":
        for lvl in ("l1", "l2", "l3"):
            kib, ways = getattr(self, f"{lvl}_kib"), getattr(self, f"{lvl}_ways")
            if (kib is None) != (ways is None):
                raise ValueError(f"{lvl}: give both size (KiB) and associativity, or neither")
            if kib is not None and (kib * 1024) % (64 * ways) != 0:
                raise ValueError(f"{lvl}: size must be a whole number of sets (size / (64 B x ways))")
        return self

    def custom_levels(self) -> dict[str, tuple[int, int]]:
        out = {}
        for lvl in ("l1", "l2", "l3"):
            kib, ways = getattr(self, f"{lvl}_kib"), getattr(self, f"{lvl}_ways")
            if kib is not None:
                out[lvl] = (kib, ways)
        return out


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    op: Operation
    mapping: Mapping = Mapping.identity
    image_source: ImageSource = ImageSource.photo
    upload_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{12}$")
    width: int | None = Field(default=None, ge=MIN_EDGE, le=MAX_EDGE)
    height: int | None = Field(default=None, ge=MIN_EDGE, le=MAX_EDGE)
    strategies: list[StrategySpec] = Field(min_length=1, max_length=MAX_VARIANTS)
    reps: int = Field(default=11, ge=MIN_REPS, le=MAX_REPS)
    condition: CacheCondition = CacheCondition.warm
    cache_sim: CacheSimConfig = Field(default_factory=CacheSimConfig)
    validate_reference: bool = True

    @model_validator(mode="after")
    def _check(self) -> "ExperimentConfig":
        if self.image_source == ImageSource.upload:
            if not self.upload_id:
                raise ValueError("upload_id is required when image_source is 'upload'")
            if self.width is not None or self.height is not None:
                raise ValueError("width/height come from the uploaded image; do not set them")
        else:
            if self.upload_id is not None:
                raise ValueError("upload_id is only valid with image_source 'upload'")
            if self.width is None or self.height is None:
                raise ValueError("width and height are required for generated and photo inputs")
            if self.width * self.height > settings.max_pixels:
                raise ValueError(f"image exceeds the {settings.max_pixels:,}-pixel limit")
            for s in self.strategies:
                if s.strategy == Strategy.tiled and (s.tile_w > self.width or s.tile_h > self.height):
                    raise ValueError(f"tile {s.tile_w}x{s.tile_h} is larger than the {self.width}x{self.height} image")
        tokens = [s.token for s in self.strategies]
        if len(set(tokens)) != len(tokens):
            raise ValueError("each strategy/tile combination may appear only once")
        return self


# ---- responses -------------------------------------------------------------------


class JobAccepted(BaseModel):
    id: str
    kind: str
    status: str
    queue_position: int


class RepetitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rep: int
    inner_iters: int
    ms_per_run: float
    tsc_ticks_per_run: float | None
    core_ghz_probe: float | None


class VariantResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    suite: str
    build_variant: str
    image_kind: str
    width: int
    height: int
    op: str
    mapping: str
    condition: str
    strategy: str
    label: str
    tile_w: int
    tile_h: int
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
    speedup_vs_row_major: float | None = None   # same experiment and group only
    repetitions: list[RepetitionOut] = []


class CacheRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: Literal["model"]
    width: int
    height: int
    mapping: str
    label: str
    sim_label: str
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


class ExperimentSummary(BaseModel):
    id: str
    kind: str
    name: str
    status: str
    created_at: datetime
    finished_at: datetime | None
    op: str | None
    mapping: str | None
    width: int | None
    height: int | None
    image_source: str | None
    condition: str | None
    reps: int | None
    suite_name: str | None
    strategies: list[str]
    best_label: str | None = None
    best_median_ms: float | None = None
    row_major_median_ms: float | None = None
    all_outputs_match: bool | None = None
    result_count: int = 0


class ExperimentDetail(ExperimentSummary):
    started_at: datetime | None
    config: dict[str, Any]
    image_detail: str | None
    build_variant: str | None
    compiler: str | None
    build_flags: str | None
    environment: dict[str, Any] | None
    cache_geometry: dict[str, Any] | None
    validation: dict[str, Any] | None
    engine_command: list[str] | None
    engine_seconds: float | None
    error_message: str | None
    error_detail: str | None
    queue_position: int | None = None
    results: list[VariantResultOut] = []
    cache: list[CacheRowOut] = []


class ExperimentPage(BaseModel):
    items: list[ExperimentSummary]
    total: int
    page: int
    page_size: int


class UploadOut(BaseModel):
    upload_id: str
    width: int
    height: int
    sha256: str
    original_name: str
    bytes: int
