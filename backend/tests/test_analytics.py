"""Analytics calculations on hand-built rows (isolated: no engine involved)."""
from __future__ import annotations

from app.db.database import SessionLocal
from app.models.experiment import Experiment, VariantResult
from app.services import analytics_service


def _result(eid: str, label: str, median: float, **kw) -> VariantResult:
    base = dict(experiment_id=eid, suite="single", build_variant="native", image_kind="gradient", width=100,
                height=100, op="lab", mapping="identity", condition="warm", strategy=label.split("_")[0], label=label,
                tile_w=0, tile_h=0, reps=3, inner_iters=1, median_ms=median, mean_ms=median, min_ms=median,
                max_ms=median, stdev_ms=0.0, p25_ms=median, p75_ms=median, cv_pct=0.0, ns_per_px=median * 100,
                mpix_per_s=10 / median, hw_counters="unavailable", output_matches_baseline=True)
    base.update(kw)
    return VariantResult(**base)


def test_speedups_and_comparison_warnings():
    with SessionLocal() as db:
        a = Experiment(kind="comparison", name="A", status="completed", config_json="{}", op="lab",
                       mapping="identity", width=100, height=100)
        b = Experiment(kind="comparison", name="B", status="completed", config_json="{}", op="lab",
                       mapping="identity", width=100, height=100)
        db.add_all([a, b])
        db.flush()
        db.add_all([_result(a.id, "row_major", 2.0), _result(a.id, "morton", 4.0),
                    _result(b.id, "row_major", 1.0, image_kind="noise"), _result(b.id, "morton", 0.5,
                                                                                 image_kind="noise")])
        db.commit()
        out = analytics_service.comparisons(db, op="lab", mapping="identity", width=100, height=100,
                                            labels=["morton"], experiment_ids=[a.id, b.id])
        sp = {(r["experiment_id"], r["label"]): r["speedup_vs_row_major_same_run"] for r in out["rows"]}
        assert sp[(a.id, "morton")] == 0.5      # 2.0 / 4.0, within run A
        assert sp[(b.id, "morton")] == 2.0      # 1.0 / 0.5, within run B, never across runs
        assert any("input images" in w for w in out["warnings"])
        assert any("separate runs" in w for w in out["warnings"])

        summary = analytics_service.summary(db)
        best = [x for x in summary["best_speedups_vs_row_major"] if x["op"] == "lab"]
        assert best and best[0]["speedup"] >= 2.0

        scaling = analytics_service.scaling(db, "lab", "identity")
        pts = [p for p in scaling["points"] if p["label"] == "row_major" and p["pixels"] == 10_000]
        assert pts and pts[0]["n_results"] >= 2 and pts[0]["median_ms"] == 1.5   # median of 2.0 and 1.0

        for e in (a, b):
            db.delete(e)
        db.commit()
