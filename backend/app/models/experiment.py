"""ORM models.

An *experiment* is one engine job: a single-strategy run, a comparison of
several strategies in one interleaved group, or a whole benchmark suite.
Results are stored at the engine's own granularity: one `VariantResult` per
row of bench_native.csv, and one `Repetition` per row of samples_native.csv.
Summary statistics can therefore always be recomputed from the raw observations.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

STATUSES = ("queued", "running", "completed", "failed")
KINDS = ("experiment", "comparison", "suite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        CheckConstraint(f"status IN {STATUSES}", name="ck_experiment_status"),
        CheckConstraint(f"kind IN {KINDS}", name="ck_experiment_kind"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    op: Mapped[str | None] = mapped_column(String(16), index=True)
    mapping: Mapped[str | None] = mapped_column(String(16))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    image_source: Mapped[str | None] = mapped_column(String(16))
    image_detail: Mapped[str | None] = mapped_column(String(200))
    condition: Mapped[str | None] = mapped_column(String(16))
    reps: Mapped[int | None] = mapped_column(Integer)
    suite_name: Mapped[str | None] = mapped_column(String(40))

    build_variant: Mapped[str | None] = mapped_column(String(16))
    compiler: Mapped[str | None] = mapped_column(String(120))
    build_flags: Mapped[str | None] = mapped_column(String(300))
    environment_json: Mapped[str | None] = mapped_column(Text)
    cache_geometry_json: Mapped[str | None] = mapped_column(Text)
    validation_json: Mapped[str | None] = mapped_column(Text)

    engine_command: Mapped[str | None] = mapped_column(Text)   # argument list with paths replaced by placeholders
    engine_seconds: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)    # safe to show to users
    error_detail: Mapped[str | None] = mapped_column(Text)     # sanitised stderr tail, for debugging

    results: Mapped[list["VariantResult"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", passive_deletes=True,
        order_by="VariantResult.id")
    cache_rows: Mapped[list["CacheSimRow"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", passive_deletes=True,
        order_by="CacheSimRow.id")
    reports: Mapped[list["Report"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", passive_deletes=True)


class VariantResult(Base):
    __tablename__ = "variant_results"
    __table_args__ = (
        UniqueConstraint("experiment_id", "suite", "image_kind", "width", "height", "op", "mapping", "condition",
                         "build_variant", "label", name="uq_result_group_label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    # group keys, copied from the engine's CSV row
    suite: Mapped[str] = mapped_column(String(40))
    build_variant: Mapped[str] = mapped_column(String(16))
    image_kind: Mapped[str] = mapped_column(String(32))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    op: Mapped[str] = mapped_column(String(16))
    mapping: Mapped[str] = mapped_column(String(16))
    condition: Mapped[str] = mapped_column(String(16))
    # variant
    strategy: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(40))
    tile_w: Mapped[int] = mapped_column(Integer)
    tile_h: Mapped[int] = mapped_column(Integer)
    # statistics exactly as computed by the engine from the repetitions below
    reps: Mapped[int] = mapped_column(Integer)
    inner_iters: Mapped[int] = mapped_column(Integer)
    median_ms: Mapped[float] = mapped_column(Float)
    mean_ms: Mapped[float] = mapped_column(Float)
    min_ms: Mapped[float] = mapped_column(Float)
    max_ms: Mapped[float] = mapped_column(Float)
    stdev_ms: Mapped[float] = mapped_column(Float)
    p25_ms: Mapped[float] = mapped_column(Float)
    p75_ms: Mapped[float] = mapped_column(Float)
    cv_pct: Mapped[float] = mapped_column(Float)
    ns_per_px: Mapped[float] = mapped_column(Float)
    mpix_per_s: Mapped[float] = mapped_column(Float)
    tsc_ticks_per_px: Mapped[float | None] = mapped_column(Float)
    core_ghz_probe: Mapped[float | None] = mapped_column(Float)
    est_core_cycles_per_px: Mapped[float | None] = mapped_column(Float)
    model_bytes_per_px: Mapped[float | None] = mapped_column(Float)
    est_bw_gbps: Mapped[float | None] = mapped_column(Float)
    setup_ms: Mapped[float | None] = mapped_column(Float)
    setup_note: Mapped[str | None] = mapped_column(Text)
    output_hash: Mapped[str | None] = mapped_column(String(16))
    output_matches_baseline: Mapped[bool | None] = mapped_column(Boolean)
    hw_counters: Mapped[str] = mapped_column(String(40), default="unavailable")

    experiment: Mapped[Experiment] = relationship(back_populates="results")
    repetitions: Mapped[list["Repetition"]] = relationship(
        back_populates="result", cascade="all, delete-orphan", passive_deletes=True, order_by="Repetition.rep")


class Repetition(Base):
    __tablename__ = "repetitions"
    __table_args__ = (UniqueConstraint("result_id", "rep", name="uq_repetition"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("variant_results.id", ondelete="CASCADE"), index=True)
    rep: Mapped[int] = mapped_column(Integer)
    inner_iters: Mapped[int] = mapped_column(Integer)
    ms_per_run: Mapped[float] = mapped_column(Float)
    tsc_ticks_per_run: Mapped[float | None] = mapped_column(Float)
    core_ghz_probe: Mapped[float | None] = mapped_column(Float)

    result: Mapped[VariantResult] = relationship(back_populates="repetitions")


class CacheSimRow(Base):
    """One cache level of one simulated traversal. Always a MODEL output."""

    __tablename__ = "cache_sim_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(16), default="model")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    mapping: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(40))       # variant label of the experiment
    sim_label: Mapped[str] = mapped_column(String(40))   # label printed by the simulator
    tile_w: Mapped[int] = mapped_column(Integer)
    tile_h: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(8))
    accesses: Mapped[int] = mapped_column(BigInteger)
    misses: Mapped[int] = mapped_column(BigInteger)
    miss_rate: Mapped[float] = mapped_column(Float)
    misses_per_px: Mapped[float] = mapped_column(Float)
    writebacks: Mapped[int] = mapped_column(BigInteger)
    dram_read_bytes_per_px: Mapped[float] = mapped_column(Float)
    dram_write_bytes_per_px: Mapped[float] = mapped_column(Float)

    experiment: Mapped[Experiment] = relationship(back_populates="cache_rows")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (CheckConstraint("format IN ('html', 'md')", name="ck_report_format"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    format: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(80))   # server-generated, relative to the reports directory
    size_bytes: Mapped[int] = mapped_column(Integer)

    experiment: Mapped[Experiment] = relationship(back_populates="reports")
