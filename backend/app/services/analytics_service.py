"""Aggregates over stored measurements. Nothing here invents a value: if no
rows match, the result is empty and the UI says so."""
from __future__ import annotations

import json
import statistics
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.experiment import CacheSimRow, Experiment, Repetition, VariantResult
from app.services.experiment_service import summarize

GROUP = ("suite", "build_variant", "image_kind", "width", "height", "op", "mapping", "condition")


def _key(r: VariantResult) -> tuple:
    return (r.experiment_id,) + tuple(getattr(r, k) for k in GROUP)


def summary(db: Session) -> dict:
    counts = dict(db.execute(select(Experiment.status, func.count()).group_by(Experiment.status)).all())
    kinds = dict(db.execute(select(Experiment.kind, func.count()).group_by(Experiment.kind)).all())
    n_results = db.scalar(select(func.count(VariantResult.id)))
    n_reps = db.scalar(select(func.count(Repetition.id)))
    latest = db.scalars(select(Experiment).where(Experiment.status == "completed")
                        .order_by(Experiment.finished_at.desc()).limit(1)).first()

    rows = db.scalars(select(VariantResult).join(Experiment).where(Experiment.status == "completed")).all()
    base = {_key(r): r for r in rows if r.label == "row_major"}
    best: dict[tuple, dict] = {}
    for r in rows:
        b = base.get(_key(r))
        if b is None or r.label == "row_major":
            continue
        sp = b.median_ms / r.median_ms
        k = (r.op, r.mapping)
        if k not in best or sp > best[k]["speedup"]:
            best[k] = {"op": r.op, "mapping": r.mapping, "width": r.width, "height": r.height, "label": r.label,
                       "speedup": sp, "experiment_id": r.experiment_id}
    return {
        "experiments": {"total": sum(counts.values()), **{s: counts.get(s, 0) for s in
                                                         ("queued", "running", "completed", "failed")}},
        "kinds": kinds,
        "variant_results": n_results,
        "repetitions": n_reps,
        "latest_completed": summarize(latest).model_dump(mode="json") if latest else None,
        "measured_ops": sorted({r.op for r in rows}),
        "measured_strategies": sorted({r.label for r in rows}),
        "best_speedups_vs_row_major": sorted(best.values(), key=lambda x: (x["op"], x["mapping"])),
        "hardware_counters": "unavailable" if all(r.hw_counters == "unavailable" for r in rows) else "partial",
    }


def scaling(db: Session, op: str, mapping: str, condition: str = "warm") -> dict:
    """Median ns/px per (strategy label, image size) over completed experiments."""
    rows = db.scalars(select(VariantResult).join(Experiment).where(
        Experiment.status == "completed", VariantResult.op == op, VariantResult.mapping == mapping,
        VariantResult.condition == condition)).all()
    acc: dict[tuple, list] = defaultdict(list)
    for r in rows:
        acc[(r.label, r.width, r.height)].append(r)
    points = []
    for (label, w, h), rs in sorted(acc.items(), key=lambda kv: (kv[0][0], kv[0][1] * kv[0][2])):
        points.append({"label": label, "width": w, "height": h, "pixels": w * h,
                       "ns_per_px": statistics.median(x.ns_per_px for x in rs),
                       "mpix_per_s": statistics.median(x.mpix_per_s for x in rs),
                       "median_ms": statistics.median(x.median_ms for x in rs),
                       "n_results": len(rs), "experiments": sorted({x.experiment_id for x in rs})})
    return {"op": op, "mapping": mapping, "condition": condition, "points": points}


def comparisons(db: Session, *, op: str | None, mapping: str | None, width: int | None, height: int | None,
                labels: list[str], experiment_ids: list[str]) -> dict:
    stmt = select(VariantResult, Experiment).join(Experiment).where(Experiment.status == "completed")
    if experiment_ids:
        stmt = stmt.where(Experiment.id.in_(experiment_ids))
    if op:
        stmt = stmt.where(VariantResult.op == op)
    if mapping:
        stmt = stmt.where(VariantResult.mapping == mapping)
    if width:
        stmt = stmt.where(VariantResult.width == width)
    if height:
        stmt = stmt.where(VariantResult.height == height)
    if labels:
        stmt = stmt.where(VariantResult.label.in_(labels + ["row_major"]))
    pairs = db.execute(stmt.order_by(Experiment.created_at, VariantResult.id).limit(2000)).all()

    base = {_key(r): r for r, _ in pairs if r.label == "row_major"}
    out = []
    for r, e in pairs:
        if labels and r.label not in labels and r.label != "row_major":
            continue
        b = base.get(_key(r))
        out.append({"experiment_id": e.id, "experiment_name": e.name, "created_at": e.created_at.isoformat(),
                    "suite": r.suite, "image_kind": r.image_kind, "width": r.width, "height": r.height, "op": r.op,
                    "mapping": r.mapping, "condition": r.condition, "build_variant": r.build_variant,
                    "label": r.label, "tile_w": r.tile_w, "tile_h": r.tile_h, "reps": r.reps,
                    "median_ms": r.median_ms, "p25_ms": r.p25_ms, "p75_ms": r.p75_ms, "cv_pct": r.cv_pct,
                    "ns_per_px": r.ns_per_px, "mpix_per_s": r.mpix_per_s,
                    "est_core_cycles_per_px": r.est_core_cycles_per_px, "core_ghz_probe": r.core_ghz_probe,
                    "output_matches_baseline": r.output_matches_baseline,
                    "speedup_vs_row_major_same_run": (b.median_ms / r.median_ms) if b is not None else None})

    warnings = []
    for field, what in (("op", "conversions"), ("image_kind", "input images"), ("condition", "cache conditions"),
                        ("build_variant", "build variants (SIMD vs scalar)"), ("mapping", "output mappings")):
        vals = sorted({str(x[field]) for x in out})
        if len(vals) > 1:
            warnings.append(f"Rows use different {what}: {', '.join(vals)}. Their times are not directly comparable.")
    sizes = sorted({(x["width"], x["height"]) for x in out})
    if len(sizes) > 1:
        warnings.append("Rows cover several image sizes; compare ns/pixel rather than total milliseconds.")
    if len({x["experiment_id"] for x in out}) > 1:
        warnings.append("Rows come from separate runs. Only speedups within one run were measured with interleaved "
                        "repetitions on identical input; across runs, clock speed and background load may differ "
                        "(compare core_ghz_probe).")
    return {"rows": out, "warnings": warnings}


def cache(db: Session, experiment_id: str | None) -> dict:
    exps = db.execute(select(Experiment).where(Experiment.status == "completed",
                                               Experiment.cache_geometry_json.is_not(None))
                      .order_by(Experiment.created_at.desc())).scalars().all()
    listing = []
    for e in exps:
        geo = json.loads(e.cache_geometry_json)
        if "skipped" in geo:
            continue
        listing.append({"experiment_id": e.id, "name": e.name, "width": e.width, "height": e.height,
                        "mapping": e.mapping, "op": e.op, "geometry_source": geo.get("source"),
                        "created_at": e.created_at.isoformat()})
    selected = experiment_id or (listing[0]["experiment_id"] if listing else None)
    rows, geometry = [], None
    if selected:
        e = db.get(Experiment, selected)
        if e and e.cache_geometry_json:
            geometry = json.loads(e.cache_geometry_json)
            rows = [{"label": c.label, "sim_label": c.sim_label, "level": c.level, "accesses": c.accesses,
                     "misses": c.misses, "hits": c.accesses - c.misses, "miss_rate": c.miss_rate,
                     "misses_per_px": c.misses_per_px, "writebacks": c.writebacks,
                     "dram_read_bytes_per_px": c.dram_read_bytes_per_px,
                     "dram_write_bytes_per_px": c.dram_write_bytes_per_px, "tile_w": c.tile_w, "tile_h": c.tile_h,
                     "width": c.width, "height": c.height, "mapping": c.mapping, "source": c.source}
                    for c in db.scalars(select(CacheSimRow).where(CacheSimRow.experiment_id == selected)
                                        .order_by(CacheSimRow.id))]
    return {"experiments": listing, "selected": selected, "geometry": geometry, "rows": rows,
            "source_note": "Simulated by cachevision_sim (trace-driven LRU model, no prefetching). "
                           "These are not hardware performance-counter measurements."}
