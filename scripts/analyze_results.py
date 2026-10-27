#!/usr/bin/env python3
"""Turn raw benchmark CSVs into comparison tables and a machine-readable summary.

Inputs  (results/raw/): bench_<variant>.csv, samples_<variant>.csv, memory_native.csv,
                        cachesim.csv, system_native.json, session_*.jsonl
Outputs: results/tables/*.md, results/summary_tables.md, results/summary.json

Every number written here is derived from the raw CSVs; nothing is typed in by hand.
Speedups are ratios of medians: speedup = median(row_major) / median(variant) within
the same (suite, build, image, size, op, mapping, condition) group.
"""
import argparse
import json
import math
import os

import numpy as np
import pandas as pd

GROUP = ["suite", "build_variant", "image_kind", "width", "height", "op", "mapping", "condition"]


def md_table(df, floatfmt="{:.3g}", index=True):
    """Small dependency-free markdown table writer."""
    d = df.reset_index() if index else df
    cols = [str(c) for c in d.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, row in d.iterrows():
        cells = []
        for v in row.values:
            if isinstance(v, (float, np.floating)):
                cells.append("" if math.isnan(v) else floatfmt.format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def geomean(x):
    x = np.asarray([v for v in x if v > 0 and np.isfinite(v)], dtype=float)
    return float(np.exp(np.log(x).mean())) if len(x) else float("nan")


def size_label(w, h):
    return f"{w}x{h}"


def add_speedup(df):
    base = df[df.label == "row_major"][GROUP + ["median_ms"]].rename(columns={"median_ms": "row_ms"})
    out = df.merge(base, on=GROUP, how="left")
    out["speedup_vs_row"] = out.row_ms / out.median_ms
    return out


def load(raw):
    frames = []
    for v in ("native", "scalar"):
        p = os.path.join(raw, f"bench_{v}.csv")
        if os.path.exists(p):
            frames.append(pd.read_csv(p))
    if not frames:
        raise SystemExit(f"no bench_*.csv in {raw}")
    df = pd.concat(frames, ignore_index=True)
    df["size"] = [size_label(w, h) for w, h in zip(df.width, df.height)]
    df["mpix"] = df.pixels / 1e6
    return add_speedup(df)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join("results", "raw"))
    ap.add_argument("--out", default="results")
    args = ap.parse_args()
    tdir = os.path.join(args.out, "tables")
    os.makedirs(tdir, exist_ok=True)
    df = load(args.raw)
    nat = df[df.build_variant == "native"]
    summary = {"source": "derived from results/raw by scripts/analyze_results.py"}
    sections = []

    def emit(name, title, body, note=""):
        text = f"## {title}\n\n{note + chr(10) + chr(10) if note else ''}{body}\n"
        with open(os.path.join(tdir, name + ".md"), "w", encoding="utf-8") as f:
            f.write(text)
        sections.append(text)

    # ---- environment ---------------------------------------------------------------
    sysp = os.path.join(args.raw, "system_native.json")
    if os.path.exists(sysp):
        with open(sysp, encoding="utf-8") as f:
            summary["system"] = json.load(f)
    ghz = nat.core_ghz_probe.astype(float)
    summary["core_ghz_probe"] = {"min": float(ghz.min()), "median": float(ghz.median()), "max": float(ghz.max())}

    # ---- correctness ----------------------------------------------------------------
    judged = df[df.op != "index_only"]
    ok = int((judged.output_matches_baseline == 1).sum())
    summary["output_equality"] = {"configs": int(len(judged)), "bit_identical_to_row_major": ok}
    vpath = os.path.join(args.out, "validation", "validation_summary.csv")
    if os.path.exists(vpath):
        v = pd.read_csv(vpath, keep_default_na=False, dtype={"pass": str})  # keep "n/a" as text
        j = v[v["pass"].astype(str) != "n/a"]
        summary["validation"] = {"judged": int(len(j)), "passed": int((j["pass"].astype(str) == "1").sum()),
                                 "reported_only": int(len(v) - len(j))}
        worst = v.assign(err=v.max_abs_err.astype(float)).groupby(["op", "reference"]).err.max().unstack()
        emit("correctness", "Correctness", md_table(worst, "{:.2e}"),
             f"Output hashes: {ok}/{len(judged)} timed configurations produced output bit-identical to the "
             "row-major baseline. Max absolute error over all validation images and channels, by reference:")

    # ---- variability ----------------------------------------------------------------
    var = nat.groupby("suite").cv_pct.describe(percentiles=[0.5, 0.9])[["count", "50%", "90%", "max"]]
    var.columns = ["configs", "median CV %", "p90 CV %", "max CV %"]
    var["configs"] = var["configs"].astype(int)
    emit("variability", "Run-to-run variability (coefficient of variation of repetitions)", md_table(var, "{:.2f}"))
    summary["variability"] = {s: {"median_cv_pct": float(r["median CV %"]), "p90_cv_pct": float(r["p90 CV %"])}
                              for s, r in var.iterrows()}

    # ---- main suite -----------------------------------------------------------------
    main_df = nat[(nat.suite == "main") & (nat.condition == "warm")]
    order = ["row_major", "column_major", "tiled_32x32", "tiled_128x128", "morton", "adaptive_model", "adaptive_calib"]
    best_rows = []
    for (mapping, op), g in main_df.groupby(["mapping", "op"]):
        piv = g.pivot_table(index="size", columns="label", values="ns_per_px", aggfunc="first")
        piv = piv.reindex(sorted(piv.index, key=lambda s: int(s.split("x")[0]) * int(s.split("x")[1])))
        piv = piv[[c for c in order if c in piv.columns]]
        sp = g.pivot_table(index="size", columns="label", values="speedup_vs_row", aggfunc="first").reindex(piv.index)
        sp = sp[[c for c in order if c in sp.columns]]
        emit(f"main_{mapping}_{op}", f"Main suite: {op}, {mapping} - ns per pixel (median of reps)",
             md_table(piv, "{:.3f}") + "\n\nSpeedup vs row-major (ratio of medians):\n\n" + md_table(sp, "{:.2f}"))
        for size, row in piv.iterrows():
            b = row.idxmin()
            best_rows.append({"mapping": mapping, "op": op, "size": size, "best": b, "best_ns_px": row[b],
                              "row_major_ns_px": row.get("row_major", np.nan),
                              "speedup_best_vs_row": row.get("row_major", np.nan) / row[b],
                              "morton_vs_row": row.get("row_major", np.nan) / row.get("morton", np.nan),
                              "column_vs_row": row.get("row_major", np.nan) / row.get("column_major", np.nan)})
    best = pd.DataFrame(best_rows)
    if len(best):
        emit("main_best", "Main suite: fastest strategy per configuration", md_table(best, "{:.3f}", index=False))
        summary["main_best"] = best.to_dict(orient="records")

    # Throughput ranges per op/mapping for the narrative.
    thr = main_df[main_df.label == "row_major"].groupby(["op", "mapping"]).mpix_per_s.agg(["min", "max"])
    summary["row_major_mpix_per_s"] = {f"{o}/{m}": {"min": float(r["min"]), "max": float(r["max"])}
                                       for (o, m), r in thr.iterrows()}

    # ---- tile sweep -------------------------------------------------------------------
    ts = nat[nat.suite == "tile_sweep"]
    if len(ts):
        rows = []
        for (mapping, op, size), g in ts.groupby(["mapping", "op", "size"]):
            tiles = g[g.strategy == "tiled"]
            b = tiles.loc[tiles.ns_per_px.idxmin()]
            w = tiles.loc[tiles.ns_per_px.idxmax()]
            r = g[g.label == "row_major"].ns_per_px.iloc[0]
            rows.append({"mapping": mapping, "op": op, "size": size, "pixels": int(g.pixels.iloc[0]),
                         "row_major_ns_px": r, "best_tile": b.label, "best_ns_px": b.ns_per_px,
                         "best_speedup_vs_row": r / b.ns_per_px, "worst_tile": w.label, "worst_ns_px": w.ns_per_px})
        t = pd.DataFrame(rows).sort_values(["mapping", "op", "pixels"]).drop(columns="pixels")
        emit("tile_sweep", "Tile sweep: best and worst square tile per configuration", md_table(t, "{:.3f}", index=False))
        summary["tile_sweep"] = t.to_dict(orient="records")

    # ---- tile shape -------------------------------------------------------------------
    tsh = nat[nat.suite == "tile_shape"]
    for (size, mapping), g in tsh.groupby(["size", "mapping"]):
        tiles = g[g.strategy == "tiled"]
        piv = tiles.pivot_table(index="tile_h", columns="tile_w", values="ns_per_px", aggfunc="first")
        piv.index = piv.index.astype(int)
        piv.index.name = "tile_h (rows) / tile_w (cols)"
        r = g[g.label == "row_major"].ns_per_px.iloc[0]
        b = tiles.loc[tiles.ns_per_px.idxmin()]
        emit(f"tile_shape_{size}_{mapping}", f"Tile shape {size} {mapping} (yuv): ns/px by tile height (rows) x width (cols)",
             md_table(piv, "{:.2f}"), f"Row-major: {r:.3f} ns/px. Best: {b.label} at {b.ns_per_px:.3f} ns/px "
             f"({r / b.ns_per_px:.2f}x vs row-major).")
        summary.setdefault("tile_shape", {})[f"{size}/{mapping}"] = {
            "row_major_ns_px": float(r), "best": b.label, "best_ns_px": float(b.ns_per_px)}

    # ---- adaptive on unseen sizes ----------------------------------------------------
    ad = nat[nat.suite == "adaptive_unseen"]
    if len(ad):
        rows = []
        for (mapping, op, size), g in ad.groupby(["mapping", "op", "size"]):
            r = g[g.label == "row_major"].iloc[0]
            fixed = g[g.strategy == "tiled"]
            oracle = fixed.loc[fixed.median_ms.idxmin()]
            am = g[g.label == "adaptive_model"].iloc[0]
            ac = g[g.label == "adaptive_calib"].iloc[0]
            gain_ms = r.median_ms - ac.median_ms
            rows.append({
                "mapping": mapping, "op": op, "size": size, "pixels": int(r.pixels),
                "row_ns_px": r.ns_per_px, "oracle_fixed": oracle.label, "oracle_ns_px": oracle.ns_per_px,
                "model_tile": f"{am.tile_w}x{am.tile_h}", "model_ns_px": am.ns_per_px,
                "calib_tile": f"{ac.tile_w}x{ac.tile_h}", "calib_ns_px": ac.ns_per_px,
                "calib_speedup_vs_row": r.median_ms / ac.median_ms,
                "calib_vs_oracle": ac.median_ms / oracle.median_ms,
                "model_vs_oracle": am.median_ms / oracle.median_ms,
                "calib_setup_ms": ac.setup_ms,
                "break_even_runs": (ac.setup_ms / gain_ms) if gain_ms > 0 else float("inf"),
            })
        a = pd.DataFrame(rows).sort_values(["mapping", "op", "pixels"]).drop(columns="pixels")
        emit("adaptive_unseen", "Adaptive tiling on unseen dimensions",
             md_table(a, "{:.3f}", index=False),
             "oracle_fixed = the best of the fixed tiles 8..256 chosen *after the fact* (not available to a real "
             "system). *_vs_oracle > 1 means slower than that oracle. break_even_runs = calibration time / time "
             "saved per run vs row-major (inf = never pays off).")
        agg = {}
        for mapping, g in a.groupby("mapping"):
            fixed_labels = sorted(set(ad[ad.strategy == "tiled"].label))
            per_fixed = {}
            for lab in fixed_labels:
                sub = ad[(ad.mapping == mapping) & (ad.label == lab)]
                per_fixed[lab] = geomean(sub.speedup_vs_row)
            agg[mapping] = {
                "geomean_speedup_vs_row": {
                    "adaptive_calib": geomean(ad[(ad.mapping == mapping) & (ad.label == "adaptive_calib")].speedup_vs_row),
                    "adaptive_model": geomean(ad[(ad.mapping == mapping) & (ad.label == "adaptive_model")].speedup_vs_row),
                    "morton": geomean(ad[(ad.mapping == mapping) & (ad.label == "morton")].speedup_vs_row),
                    **per_fixed},
                "geomean_calib_vs_oracle": geomean(g.calib_vs_oracle),
                "geomean_model_vs_oracle": geomean(g.model_vs_oracle),
                "calib_within_5pct_of_oracle": int((g.calib_vs_oracle <= 1.05).sum()),
                "model_within_5pct_of_oracle": int((g.model_vs_oracle <= 1.05).sum()),
                "calib_not_slower_than_row_2pct": int((g.calib_speedup_vs_row >= 0.98).sum()),
                "configs": int(len(g)),
            }
        summary["adaptive_unseen"] = agg
        lines = []
        for mapping, v in agg.items():
            gm = v["geomean_speedup_vs_row"]
            lines.append(f"**{mapping}** ({v['configs']} configs): geomean speedup vs row-major - " +
                         ", ".join(f"{k} {val:.2f}x" for k, val in gm.items()) +
                         f". adaptive_calib within 5% of the oracle tile in {v['calib_within_5pct_of_oracle']}, "
                         f"adaptive_model in {v['model_within_5pct_of_oracle']}; geomean slowdown vs oracle "
                         f"{v['geomean_calib_vs_oracle']:.3f} (calib) / {v['geomean_model_vs_oracle']:.3f} (model).")
        emit("adaptive_summary", "Adaptive tiling: aggregate", "\n\n".join(lines))

    # ---- cache condition ------------------------------------------------------------
    cc = nat[nat.suite == "cache_condition"]
    if len(cc):
        p = cc.pivot_table(index=["op", "label", "size"], columns="condition", values="ns_per_px", aggfunc="first")
        p["flushed/warm"] = p["flushed"] / p["warm"]
        p = p.reset_index()
        p["px"] = [int(s.split("x")[0]) ** 2 for s in p["size"]]
        p = p.sort_values(["op", "label", "px"]).drop(columns="px").set_index(["op", "label", "size"])
        emit("cache_condition", "Warm vs flushed caches (ns/px)", md_table(p, "{:.3f}"),
             "flushed = CLFLUSH of every input and output line before each timed run (TLBs not flushed).")
        summary["cache_condition_ratio"] = {f"{o}/{l}/{s}": float(r["flushed/warm"]) for (o, l, s), r in p.iterrows()}

    # ---- overhead decomposition ------------------------------------------------------
    ov = nat[nat.suite == "overhead"]
    if len(ov):
        p = ov.pivot_table(index=["size", "label"], columns="op", values="ns_per_px", aggfunc="first")
        p = p[[c for c in ["index_only", "unpack", "yuv", "lab"] if c in p.columns]]
        p["unpack-index"] = p["unpack"] - p["index_only"]
        emit("overhead", "Traversal overhead decomposition (ns/px)", md_table(p, "{:.3f}"),
             "index_only = address generation + loop control, no pixel memory touched. unpack adds the memory "
             "traffic with almost no arithmetic. Differences are indicative only: an out-of-order core overlaps "
             "these costs, so they are not strictly additive.")
        summary["overhead_ns_px"] = {f"{s}/{l}": {k: float(v) for k, v in r.items()} for (s, l), r in p.iterrows()}

    # ---- content dependence ----------------------------------------------------------
    co = nat[nat.suite == "content"]
    if len(co):
        p = co.pivot_table(index=["op", "label"], columns="image_kind", values="ns_per_px", aggfunc="first")
        emit("content", "Image content vs time (2048x2048, ns/px)", md_table(p, "{:.3f}"),
             "Memory access patterns are content-independent; any difference comes from data-dependent "
             "control flow (HSV branches, Lab cbrt threshold).")
        summary["content_ns_px"] = {f"{o}/{l}": {k: float(v) for k, v in r.items()} for (o, l), r in p.iterrows()}

    # ---- SIMD ------------------------------------------------------------------------
    sc = df[df.suite == "simd_compare"]
    if sc.build_variant.nunique() == 2:
        p = sc.pivot_table(index=["mapping", "op", "size", "label"], columns="build_variant", values="ns_per_px",
                           aggfunc="first")
        p["scalar/native"] = p["scalar"] / p["native"]
        emit("simd", "Auto-vectorised (native) vs scalar build (ns/px)", md_table(p, "{:.3f}"),
             "Same sources, same -O3 -march=native; the scalar build adds -fno-tree-vectorize "
             "-fno-tree-slp-vectorize. See results/vectorization_report.md for which loops vectorise.")
        summary["simd_ratio"] = {"/".join(map(str, k)): float(r["scalar/native"]) for k, r in p.iterrows()}

    # ---- cache model ------------------------------------------------------------------
    simp = os.path.join(args.raw, "cachesim.csv")
    if os.path.exists(simp):
        sim = pd.read_csv(simp)
        sim["size"] = [size_label(w, h) for w, h in zip(sim.width, sim.height)]
        p = sim.pivot_table(index=["mapping", "size", "label"], columns="level", values="misses_per_px", aggfunc="first")
        dram = sim.groupby(["mapping", "size", "label"])[["dram_read_bytes_per_px", "dram_write_bytes_per_px"]].first()
        p = p.join(dram)
        emit("cachesim", "Cache model (SIMULATED, not measured): misses per pixel and DRAM bytes per pixel",
             md_table(p, "{:.3f}"), "True-LRU, write-allocate, no prefetching; geometry from CPUID. See "
             "include/cache_sim.hpp for all simplifications.")
        # Rank agreement between model and measurement (same address streams).
        meas = nat[(nat.suite.isin(["main", "tile_sweep"])) & (nat.op == "yuv") & (nat.condition == "warm")]
        rows = []
        for (mapping, size), g in sim.groupby(["mapping", "size"]):
            m = meas[(meas.mapping == mapping) & (meas["size"] == size)].groupby("label").ns_per_px.median()
            l1 = g[g.level == "L1D"].set_index("label").misses_per_px
            l2 = g[g.level == "L2"].set_index("label").misses_per_px
            common = sorted(set(m.index) & set(l1.index))
            if len(common) >= 4:
                rows.append({"mapping": mapping, "size": size, "n": len(common),
                             "spearman_L1_vs_time": pd.Series(l1[common]).rank().corr(pd.Series(m[common]).rank()),
                             "spearman_L2_vs_time": pd.Series(l2[common]).rank().corr(pd.Series(m[common]).rank())})
        if rows:
            r = pd.DataFrame(rows)
            emit("model_vs_measured", "Does the cache model rank strategies like the measurements? (yuv)",
                 md_table(r, "{:.2f}", index=False), "Spearman rank correlation across strategies between "
                 "simulated misses/px and measured ns/px at the same size and mapping.")
            summary["model_vs_measured"] = r.to_dict(orient="records")

    # ---- memory hierarchy --------------------------------------------------------------
    memp = os.path.join(args.raw, "memory_native.csv")
    if os.path.exists(memp) and "system" in summary:
        mem = pd.read_csv(memp)
        caches = {c["level"]: c["size_bytes"] for c in summary["system"]["caches"]
                  if c["source"].startswith("cpuid") and c["type"] != "instruction"}
        l1, l2, l3 = caches.get(1, 0), caches.get(2, 0), caches.get(3, 0)
        bands = {"L1 (<= L1/2)": (0, l1 / 2), "L2 (2xL1 .. L2/2)": (2 * l1, l2 / 2),
                 "L3 (2xL2 .. L3/2)": (2 * l2, l3 / 2), "DRAM (>= 4xL3)": (4 * l3, 1e18)}
        rows = []
        for name, (lo, hi) in bands.items():
            b = mem[(mem.size_bytes >= lo) & (mem.size_bytes <= hi)]
            rows.append({"region": name,
                         "latency_ns": b[b.test == "latency"].value.median(),
                         "read_GBps": b[b.test == "read_bw"].value.median(),
                         "write_GBps": b[b.test == "write_bw"].value.median()})
        r = pd.DataFrame(rows)
        emit("memory_hierarchy", "Measured memory hierarchy (median over sizes within each region)",
             md_table(r, "{:.2f}", index=False), "Dependent-load latency uses a random cyclic permutation of "
             "64-byte nodes (defeats prefetching); bandwidth uses sequential 8-byte loads/stores.")
        summary["memory_hierarchy"] = r.to_dict(orient="records")

    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=float)
    with open(os.path.join(args.out, "summary_tables.md"), "w", encoding="utf-8") as f:
        f.write("# CacheVision - summary tables\n\nGenerated by `scripts/analyze_results.py` from `results/raw/`. "
                "All times are medians over repetitions on one pinned performance core.\n\n")
        f.write("\n".join(sections))
    print(f"wrote {len(sections)} tables to {tdir} and results/summary.json")


if __name__ == "__main__":
    main()
