#!/usr/bin/env python3
"""Figures for the CacheVision report (results/figures/*.png).

Every figure states its workload, units and benchmark conditions in the title
or footer. Colours follow a fixed entity -> colour mapping (a strategy keeps
its colour in every chart), validated for colour-vision deficiency; markers
and legends provide a second, non-colour channel.

Usage: python scripts/plot_results.py [--raw results/raw] [--out results/figures]
"""
import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402

# ---- palette (light mode reference palette, validated) -----------------------------
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
STRAT = {  # fixed order = fixed colour; never re-assigned by rank
    "row_major": ("#2a78d6", "o", "row-major"),
    "tiled_32x32": ("#eb6834", "s", "tiled 32x32"),
    "tiled_128x128": ("#1baf7a", "D", "tiled 128x128"),
    "morton": ("#eda100", "^", "Morton"),
    "adaptive_model": ("#e87ba4", "v", "adaptive (model)"),
    "adaptive_calib": ("#008300", "P", "adaptive (calibrated)"),
    "column_major": ("#6250d6", "X", "column-major"),
    "tiled_64x64": ("#e34948", "h", "tiled 64x64"),
}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ = LinearSegmentedColormap.from_list("blue_seq", BLUES)
DIV = LinearSegmentedColormap.from_list("div", ["#c0392b", "#e34948", "#f3b6b3", "#f0efec", "#9ec5f4", "#2a78d6", "#184f95"])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": INK, "axes.titlecolor": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold", "legend.frameon": False,
    "lines.linewidth": 2, "lines.markersize": 6, "figure.dpi": 110,
})


def ratio_ticks(ax, axis="y", suffix="x"):
    """Plain-number ticks (0.25x, 0.5x, 1x, 2x, ...) on a log axis spanning about one decade."""
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter
    lo, hi = (ax.get_ylim() if axis == "y" else ax.get_xlim())
    ticks = [t for t in [0.05, 0.1, 0.2, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8] if lo <= t <= hi]
    a = ax.yaxis if axis == "y" else ax.xaxis
    a.set_major_locator(FixedLocator(ticks))
    a.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}{suffix}"))
    a.set_minor_formatter(NullFormatter())


def footer(fig, text):
    # Constrained-layout figures use the full canvas, so put the footer below it.
    y = -0.02 if fig.get_layout_engine() is not None and "Constrained" in type(fig.get_layout_engine()).__name__ else 0.005
    fig.text(0.01, y, text, ha="left", va="top" if y < 0 else "bottom", fontsize=7.5, color=MUTED)


def save(fig, out, name):
    path = os.path.join(out, name)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print("wrote", path)


def px_of(s):
    w, h = s.split("x")
    return int(w) * int(h)


def strat_style(label):
    return STRAT.get(label, ("#898781", ".", label))


def load(raw):
    frames = [pd.read_csv(os.path.join(raw, f)) for f in ("bench_native.csv", "bench_scalar.csv")
              if os.path.exists(os.path.join(raw, f))]
    df = pd.concat(frames, ignore_index=True)
    df["size"] = [f"{w}x{h}" for w, h in zip(df.width, df.height)]
    keys = ["suite", "build_variant", "image_kind", "width", "height", "op", "mapping", "condition"]
    base = df[df.label == "row_major"][keys + ["median_ms"]].rename(columns={"median_ms": "row_ms"})
    df = df.merge(base, on=keys, how="left")
    df["speedup"] = df.row_ms / df.median_ms
    return df


def cpu_name(raw):
    p = os.path.join(raw, "system_native.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            s = json.load(f)
        return s.get("cpu_brand", "?"), s
    return "?", {}


# ---- figures ----------------------------------------------------------------------

def fig_size_grid(df, out, cpu, metric, ylabel, name, title, logy=True):
    d = df[(df.suite == "main") & (df.build_variant == "native") & (df.condition == "warm")]
    if d.empty:
        return
    ops = [o for o in ["unpack", "yuv", "hsv", "lab"] if o in set(d.op)]
    maps = [m for m in ["identity", "rotate90"] if m in set(d.mapping)]
    fig, axes = plt.subplots(len(maps), len(ops), figsize=(3.3 * len(ops), 3.0 * len(maps)), squeeze=False)
    for i, m in enumerate(maps):
        for j, op in enumerate(ops):
            ax = axes[i][j]
            g = d[(d.mapping == m) & (d.op == op)]
            for lab in STRAT:
                s = g[g.label == lab].sort_values("pixels")
                if s.empty:
                    continue
                c, mk, nm = strat_style(lab)
                y = s[metric]
                if metric == "median_ms":
                    yerr = np.vstack([s.median_ms - s.p25_ms, s.p75_ms - s.median_ms])
                    ax.errorbar(s.pixels / 1e6, y, yerr=yerr, color=c, marker=mk, label=nm, capsize=2,
                                markeredgecolor=SURFACE, markeredgewidth=0.8)
                else:
                    ax.plot(s.pixels / 1e6, y, color=c, marker=mk, label=nm, markeredgecolor=SURFACE,
                            markeredgewidth=0.8)
            ax.set_xscale("log")
            if logy:
                ax.set_yscale("log")
            ax.set_title(f"{op} - {m}")
            if i == len(maps) - 1:
                ax.set_xlabel("image size (megapixels, log)")
            if j == 0:
                ax.set_ylabel(ylabel)
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=len(l), bbox_to_anchor=(0.5, 1.02))
    fig.suptitle(title, y=1.07, fontsize=11, fontweight="bold")
    footer(fig, f"{cpu}; 1 pinned P-core; native build (-O3 -march=native); photo input; warm cache; "
                "median of 11 reps" + ("; bars = IQR" if metric == "median_ms" else "") + ". Data: results/raw/bench_native.csv")
    fig.tight_layout()
    save(fig, out, name)


def fig_speedup(df, out, cpu):
    d = df[(df.suite == "main") & (df.build_variant == "native") & (df.condition == "warm") & (df.label != "row_major")]
    if d.empty:
        return
    ops = [o for o in ["unpack", "yuv", "hsv", "lab"] if o in set(d.op)]
    maps = ["identity", "rotate90"]
    fig, axes = plt.subplots(2, len(ops), figsize=(3.3 * len(ops), 6.0), squeeze=False, sharey="row")
    for i, m in enumerate(maps):
        for j, op in enumerate(ops):
            ax = axes[i][j]
            g = d[(d.mapping == m) & (d.op == op)]
            ax.axhline(1.0, color=AXIS, lw=1.2, zorder=0)
            for lab in STRAT:
                s = g[g.label == lab].sort_values("pixels")
                if s.empty:
                    continue
                c, mk, nm = strat_style(lab)
                ax.plot(s.pixels / 1e6, s.speedup, color=c, marker=mk, label=nm, markeredgecolor=SURFACE,
                        markeredgewidth=0.8)
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_title(f"{op} - {m}")
            if i == 1:
                ax.set_xlabel("image size (megapixels, log)")
            if j == 0:
                ax.set_ylabel("speedup vs row-major (x, log)\n>1 = faster")
    for row in axes:
        for ax in row:
            ratio_ticks(ax)
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=len(l), bbox_to_anchor=(0.5, 1.02))
    fig.suptitle("Speedup relative to the row-major baseline", y=1.07, fontsize=11, fontweight="bold")
    footer(fig, f"{cpu}; ratio of medians (11 reps) within each size/op/mapping group; warm cache; native build.")
    fig.tight_layout()
    save(fig, out, "fig_speedup_vs_row_major.png")


def fig_cycles(df, out, cpu):
    d = df[(df.suite == "main") & (df.build_variant == "native") & (df.condition == "warm")]
    sizes = [s for s in ["512x512", "4096x4096"] if s in set(d["size"])]
    if not sizes:
        return
    ops = [o for o in ["unpack", "yuv", "hsv", "lab"] if o in set(d.op)]
    labs = [l for l in STRAT if l in set(d.label)]
    fig, axes = plt.subplots(2, len(sizes), figsize=(6.5 * len(sizes), 6.2), squeeze=False)
    for i, m in enumerate(["identity", "rotate90"]):
        for j, sz in enumerate(sizes):
            ax = axes[i][j]
            g = d[(d.mapping == m) & (d["size"] == sz)]
            x = np.arange(len(ops))
            w = 0.8 / max(1, len(labs))
            for k, lab in enumerate(labs):
                c, _, nm = strat_style(lab)
                vals = [g[(g.op == op) & (g.label == lab)].est_core_cycles_per_px.mean() for op in ops]
                ax.bar(x + (k - (len(labs) - 1) / 2) * w, vals, width=w * 0.9, color=c, label=nm,
                       edgecolor=SURFACE, linewidth=0.8)
            ax.set_xticks(x, ops)
            ax.set_yscale("log")
            ax.set_title(f"{sz} - {m}")
            ax.set_ylabel("estimated core cycles / pixel (log)")
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=len(l), bbox_to_anchor=(0.5, 1.02))
    fig.suptitle("Cycles per pixel by strategy (in-cache 512x512 vs DRAM-bound 4096x4096)", y=1.07,
                 fontsize=11, fontweight="bold")
    footer(fig, f"{cpu}; cycles = ns/px x effective clock from a dependent-IMUL probe taken before every repetition "
                "round (hardware cycle counters unavailable on this platform).")
    fig.tight_layout()
    save(fig, out, "fig_cycles_per_pixel.png")


def fig_tile_sweep(df, out, cpu):
    d = df[(df.suite == "tile_sweep") & (df.build_variant == "native")]
    if d.empty:
        return
    ops = [o for o in ["yuv", "lab"] if o in set(d.op)]
    sizes = sorted(set(d["size"]), key=px_of)
    cols = {s: BLUES[min(len(BLUES) - 1, 2 + i)] for i, s in enumerate(sizes)}
    fig, axes = plt.subplots(2, len(ops), figsize=(5.2 * len(ops), 6.4), squeeze=False)
    for i, m in enumerate(["identity", "rotate90"]):
        for j, op in enumerate(ops):
            ax = axes[i][j]
            for s in sizes:
                g = d[(d.mapping == m) & (d.op == op) & (d["size"] == s)]
                t = g[g.strategy == "tiled"].sort_values("tile_w")
                if t.empty:
                    continue
                ax.plot(t.tile_w, t.ns_per_px, color=cols[s], marker="o", label=s, markeredgecolor=SURFACE)
                r = g[g.label == "row_major"].ns_per_px
                if len(r):
                    ax.axhline(r.iloc[0], color=cols[s], ls=":", lw=1.2)
            ax.set_xscale("log", base=2)
            ax.set_yscale("log")
            ax.set_xticks([8, 16, 32, 64, 128, 256, 512], ["8", "16", "32", "64", "128", "256", "512"])
            ax.set_title(f"{op} - {m}")
            ax.set_xlabel("square tile edge (pixels)")
            ax.set_ylabel("ns / pixel (log)")
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=len(l), bbox_to_anchor=(0.5, 1.02), title="image size")
    fig.suptitle("Tile size vs performance (dotted: row-major at the same size)", y=1.08, fontsize=11,
                 fontweight="bold")
    footer(fig, f"{cpu}; photo input; warm cache; native build; median of 7 reps.")
    fig.tight_layout()
    save(fig, out, "fig_tile_size_vs_performance.png")


def heatmap(ax, mat, xlabels, ylabels, cmap, norm, fmt, title, xlabel, ylabel):
    im = ax.imshow(mat, cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(len(xlabels)), xlabels)
    ax.set_yticks(range(len(ylabels)), ylabels)
    ax.grid(False)
    for (r, c), v in np.ndenumerate(mat):
        if np.isfinite(v):
            rgba = im.cmap(im.norm(v))
            lum = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
            ax.text(c, r, fmt.format(v), ha="center", va="center", fontsize=7, color=INK if lum > 0.55 else SURFACE)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    return im


def fig_heatmap_tile_vs_size(df, out, cpu):
    d = df[(df.suite == "tile_sweep") & (df.build_variant == "native") & (df.strategy == "tiled")]
    if d.empty:
        return
    ops = [o for o in ["yuv", "lab"] if o in set(d.op)]
    sizes = sorted(set(d["size"]), key=px_of)
    tiles = sorted(set(d.tile_w))
    fig, axes = plt.subplots(2, len(ops), figsize=(5.6 * len(ops), 7.2), squeeze=False, layout="constrained")
    lim = max(2.0, float(np.nanmax(np.abs(np.log2(d.speedup)))))
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim)
    for i, m in enumerate(["identity", "rotate90"]):
        for j, op in enumerate(ops):
            g = d[(d.mapping == m) & (d.op == op)]
            mat = np.full((len(tiles), len(sizes)), np.nan)
            ann = np.full_like(mat, np.nan)
            for r, t in enumerate(tiles):
                for c, s in enumerate(sizes):
                    v = g[(g.tile_w == t) & (g["size"] == s)].speedup
                    if len(v):
                        mat[r, c] = np.log2(v.iloc[0])
                        ann[r, c] = v.iloc[0]
            im = axes[i][j].imshow(mat, cmap=DIV, norm=norm, aspect="auto")
            axes[i][j].grid(False)
            axes[i][j].set_xticks(range(len(sizes)), [s.split("x")[0] for s in sizes])
            axes[i][j].set_yticks(range(len(tiles)), [f"{t}x{t}" for t in tiles])
            for (r, c), v in np.ndenumerate(ann):
                if np.isfinite(v):
                    axes[i][j].text(c, r, f"{v:.2f}", ha="center", va="center", fontsize=7,
                                    color=INK if abs(mat[r, c]) < lim * 0.6 else SURFACE)
            axes[i][j].set_title(f"{op} - {m}")
            axes[i][j].set_xlabel("image edge (square images, pixels)")
            axes[i][j].set_ylabel("tile")
    cb = fig.colorbar(im, ax=axes, shrink=0.8)
    cb.set_label("speedup vs row-major (log2 scale; blue = faster, red = slower)")
    ticks = [t for t in [-3, -2, -1, 0, 1, 2, 3] if -lim <= t <= lim]
    cb.set_ticks(ticks, labels=[f"{2.0 ** t:g}x" for t in ticks])
    fig.suptitle("Tile size x image size: speedup relative to row-major", fontsize=11, fontweight="bold")
    footer(fig, f"{cpu}; photo input; warm cache; native build; ratio of medians (7 reps).")
    save(fig, out, "fig_heatmap_tile_vs_size.png")


def fig_heatmap_shape(df, out, cpu):
    d = df[(df.suite == "tile_shape") & (df.build_variant == "native")]
    if d.empty:
        return
    from matplotlib.colors import LogNorm
    from matplotlib.ticker import FuncFormatter
    sizes = sorted(set(d["size"]), key=px_of, reverse=True)
    maps = [m for m in ["rotate90", "identity"] if m in set(d.mapping)]
    fig, axes = plt.subplots(len(maps), len(sizes), figsize=(5.6 * len(sizes), 4.4 * len(maps)), squeeze=False,
                             layout="constrained")
    for i, m in enumerate(maps):
        row_t = d[(d.mapping == m) & (d.strategy == "tiled")]
        norm = LogNorm(vmin=row_t.ns_per_px.min(), vmax=row_t.ns_per_px.max())  # shared within the row
        for j, s in enumerate(sizes):
            g = d[(d.mapping == m) & (d["size"] == s)]
            t = g[g.strategy == "tiled"]
            ws, hs = sorted(set(t.tile_w)), sorted(set(t.tile_h))
            mat = np.full((len(hs), len(ws)), np.nan)
            for r, h in enumerate(hs):
                for c, w in enumerate(ws):
                    v = t[(t.tile_w == w) & (t.tile_h == h)].ns_per_px
                    if len(v):
                        mat[r, c] = v.iloc[0]
            row = g[g.label == "row_major"].ns_per_px.iloc[0]
            im = heatmap(axes[i][j], mat, [str(w) for w in ws], [str(h) for h in hs], SEQ.reversed(), norm,
                         "{:.2f}", f"yuv {m} {s} (row-major {row:.2f} ns/px)", "tile width (px)", "tile height (px)")
        cb = fig.colorbar(im, ax=axes[i].tolist(), shrink=0.9)
        cb.set_label("ns / pixel (darker = faster)")
        cb.ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        cb.ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: f"{v:g}" if f"{v:g}"[0] in "1235" else ""))
    fig.suptitle("Rectangular tiles: power-of-two image (2048) vs non-power-of-two image (2000); "
                 "shared colour scale per row", fontsize=11, fontweight="bold")
    footer(fig, f"{cpu}; photo input; warm cache; native build; median of 7 reps. Output row pitch 2048*12 B is a "
                "multiple of 4 KiB, so output rows alias in the same cache sets.")
    save(fig, out, "fig_heatmap_tile_shape.png")


def fig_sim(raw, out, cpu):
    p = os.path.join(raw, "cachesim.csv")
    if not os.path.exists(p):
        return
    sim = pd.read_csv(p)
    sim["px"] = sim.width * sim.height
    levels = [l for l in ["L1D", "L2", "L3"] if l in set(sim.level)]
    fig, axes = plt.subplots(2, len(levels), figsize=(4.2 * len(levels), 6.2), squeeze=False, sharey=True)
    for i, m in enumerate(["identity", "rotate90"]):
        for j, lv in enumerate(levels):
            ax = axes[i][j]
            g = sim[(sim.mapping == m) & (sim.level == lv)]
            for lab in STRAT:
                s = g[g.label == lab].sort_values("px")
                if s.empty:
                    continue
                c, mk, nm = strat_style(lab)
                pow2 = s[(s.width & (s.width - 1)) == 0]
                other = s[(s.width & (s.width - 1)) != 0]
                ax.plot(pow2.px / 1e6, pow2.misses_per_px, color=c, marker=mk, label=nm, markeredgecolor=SURFACE)
                ax.scatter(other.px / 1e6, other.misses_per_px, s=55, facecolor="none", edgecolor=c, marker=mk,
                           linewidth=1.4, zorder=4)
            ax.axhline(15 / 64, color=AXIS, ls="--", lw=1)
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_title(f"{lv} - {m}")
            if i == 1:
                ax.set_xlabel("image size (megapixels, log)")
            if j == 0:
                ax.set_ylabel("simulated misses / pixel (log)")
    for row in axes:
        for ax in row:
            ratio_ticks(ax, suffix="")
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=len(l), bbox_to_anchor=(0.5, 1.02))
    fig.suptitle("Cache model (SIMULATED): demand misses per pixel; dashed = compulsory 15/64; "
                 "hollow = 2000x2000 (not a power of two)", y=1.07,
                 fontsize=11, fontweight="bold")
    footer(fig, f"Trace-driven true-LRU model with {cpu} geometry from CPUID; no prefetching. Not hardware counters.")
    fig.tight_layout()
    save(fig, out, "fig_cachesim_misses_vs_size.png")


def fig_model_vs_measured(df, raw, out, cpu):
    p = os.path.join(raw, "cachesim.csv")
    if not os.path.exists(p):
        return
    sim = pd.read_csv(p)
    sim["size"] = [f"{w}x{h}" for w, h in zip(sim.width, sim.height)]
    meas = df[(df.build_variant == "native") & (df.op == "yuv") & (df.condition == "warm") &
              (df.suite.isin(["main", "tile_sweep"]))].groupby(["mapping", "size", "label"]).ns_per_px.median()
    sizes = [s for s in ["2048x2048", "4096x4096"] if s in set(sim["size"])]
    if not sizes:
        return
    fig, axes = plt.subplots(1, len(sizes), figsize=(6.0 * len(sizes), 4.6), squeeze=False)
    for j, s in enumerate(sizes):
        ax = axes[0][j]
        for k, m in enumerate(["identity", "rotate90"]):
            g = sim[(sim["size"] == s) & (sim.mapping == m) & (sim.level == "L2")]
            for _, r in g.iterrows():
                key = (m, s, r.label)
                if key not in meas.index:
                    continue
                ax.scatter(r.misses_per_px, meas[key], s=40, color=SERIES[k], marker="o" if k == 0 else "s",
                           edgecolor=SURFACE, linewidth=0.8, label=m if r.label == "row_major" else None, zorder=3)
                ax.annotate(r.label.replace("tiled_", "t").replace("adaptive_", "ad_"), (r.misses_per_px, meas[key]),
                            textcoords="offset points", xytext=(4, 3), fontsize=7, color=INK2)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("simulated L2 misses / pixel (model)")
        ax.set_ylabel("measured ns / pixel")
        ax.set_title(f"yuv, {s}")
        ax.legend(loc="upper left")
    fig.suptitle("Model vs measurement: simulated L2 misses against measured time", fontsize=11, fontweight="bold")
    footer(fig, f"{cpu}; measured: warm cache, native build, median of reps; model: no prefetching.")
    fig.tight_layout()
    save(fig, out, "fig_model_vs_measured.png")


def fig_memory(raw, out, cpu, sysinfo):
    p = os.path.join(raw, "memory_native.csv")
    if not os.path.exists(p):
        return
    mem = pd.read_csv(p)
    caches = [(c["level"], c["size_bytes"]) for c in sysinfo.get("caches", [])
              if c["source"].startswith("cpuid") and c["type"] != "instruction"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    lat = mem[mem.test == "latency"].sort_values("size_bytes")
    axes[0].plot(lat.size_bytes, lat.value, color=SERIES[0], marker="o", markeredgecolor=SURFACE)
    axes[0].set_ylabel("dependent-load latency (ns, log)")
    axes[0].set_yscale("log")
    for k, test in enumerate(["read_bw", "write_bw"]):
        b = mem[mem.test == test].sort_values("size_bytes")
        axes[1].plot(b.size_bytes, b.value, color=SERIES[k], marker="os"[k], markeredgecolor=SURFACE,
                     label={"read_bw": "read (8-byte loads)", "write_bw": "write (8-byte stores)"}[test])
    axes[1].set_ylabel("bandwidth (GB/s)")
    axes[1].legend()
    for ax in axes:
        ax.set_xscale("log", base=2)
        ax.set_xlabel("working-set size (bytes, log2)")
        for lvl, sz in caches:
            ax.axvline(sz, color=AXIS, ls="--", lw=1)
            ax.text(sz, ax.get_ylim()[1], f" L{lvl} {sz // 1024} KiB", rotation=90, va="top", ha="right",
                    fontsize=7, color=MUTED)
    axes[0].set_title("Latency vs working set (random cyclic chase)")
    axes[1].set_title("Sequential bandwidth vs working set")
    fig.suptitle("Measured memory hierarchy of the benchmark core", fontsize=11, fontweight="bold")
    footer(fig, f"{cpu}; 1 pinned P-core; 4 KiB pages; dashed = cache sizes reported by CPUID leaf 4.")
    fig.tight_layout()
    save(fig, out, "fig_memory_hierarchy.png")


def fig_cache_condition(df, out, cpu):
    d = df[(df.suite == "cache_condition") & (df.build_variant == "native")]
    if d.empty:
        return
    ops = [o for o in ["unpack", "yuv", "lab"] if o in set(d.op)]
    fig, axes = plt.subplots(1, len(ops), figsize=(4.2 * len(ops), 3.8), squeeze=False)
    for j, op in enumerate(ops):
        ax = axes[0][j]
        for lab in [l for l in STRAT if l in set(d.label)]:
            for cond, ls in (("warm", "-"), ("flushed", "--")):
                s = d[(d.op == op) & (d.label == lab) & (d.condition == cond)].sort_values("pixels")
                if s.empty:
                    continue
                c, mk, nm = strat_style(lab)
                ax.plot(s.pixels / 1e6, s.ns_per_px, color=c, ls=ls, marker=mk, markeredgecolor=SURFACE,
                        label=f"{nm} ({cond})")
        ax.set_xscale("log")
        ax.set_title(op)
        ax.set_xlabel("image size (megapixels, log)")
        ax.set_ylabel("ns / pixel")
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.12))
    fig.suptitle("Warm (solid) vs CLFLUSH-ed (dashed) caches before each run", y=1.2, fontsize=11,
                 fontweight="bold")
    footer(fig, f"{cpu}; identity mapping; photo input; native build; median of 11 reps; TLBs are not flushed.")
    fig.tight_layout()
    save(fig, out, "fig_cache_condition.png")


def fig_overhead(df, out, cpu):
    d = df[(df.suite == "overhead") & (df.build_variant == "native")]
    if d.empty:
        return
    sizes = sorted(set(d["size"]), key=px_of)
    labs = [l for l in ["row_major", "tiled_8x8", "tiled_32x32", "tiled_128x128", "morton", "column_major"]
            if l in set(d.label)]
    ops = [o for o in ["index_only", "unpack", "yuv", "lab"] if o in set(d.op)]
    fig, axes = plt.subplots(1, len(sizes), figsize=(6.4 * len(sizes), 4.0), squeeze=False)
    for j, s in enumerate(sizes):
        ax = axes[0][j]
        x = np.arange(len(labs))
        w = 0.8 / len(ops)
        for k, op in enumerate(ops):
            vals = [d[(d["size"] == s) & (d.label == lab) & (d.op == op)].ns_per_px.mean() for lab in labs]
            ax.bar(x + (k - (len(ops) - 1) / 2) * w, vals, width=w * 0.9, color=SERIES[k], label=op,
                   edgecolor=SURFACE, linewidth=0.8)
        ax.set_xticks(x, [l.replace("_", " ") for l in labs], rotation=20)
        ax.set_yscale("log")
        ax.set_ylabel("ns / pixel (log)")
        ax.set_title(f"{s}")
        ax.legend(ncol=4, loc="upper left")
    fig.suptitle("Where the time goes: address generation (index_only) vs memory (unpack) vs compute",
                 fontsize=11, fontweight="bold")
    footer(fig, f"{cpu}; identity mapping; photo input; warm cache; native build; median of 11 reps.")
    fig.tight_layout()
    save(fig, out, "fig_overhead.png")


def fig_simd(df, out, cpu):
    d = df[df.suite == "simd_compare"]
    if d.build_variant.nunique() < 2:
        return
    p = d.pivot_table(index=["size", "mapping", "op", "label"], columns="build_variant", values="ns_per_px",
                      aggfunc="first").reset_index()
    p["ratio"] = p.scalar / p.native
    sizes = sorted(set(p["size"]), key=px_of)
    fig, axes = plt.subplots(len(sizes), 2, figsize=(11, 3.4 * len(sizes)), squeeze=False, sharey=True)
    for i, s in enumerate(sizes):
        for j, m in enumerate(["identity", "rotate90"]):
            ax = axes[i][j]
            g = p[(p["size"] == s) & (p.mapping == m)]
            ops = [o for o in ["unpack", "yuv", "hsv", "lab"] if o in set(g.op)]
            labs = [l for l in ["row_major", "tiled_64x64", "morton"] if l in set(g.label)]
            x = np.arange(len(ops))
            w = 0.8 / len(labs)
            for k, lab in enumerate(labs):
                c = strat_style(lab)[0]
                vals = [g[(g.op == o) & (g.label == lab)].ratio.mean() for o in ops]
                ax.bar(x + (k - (len(labs) - 1) / 2) * w, vals, width=w * 0.9, color=c, label=lab.replace("_", " "),
                       edgecolor=SURFACE, linewidth=0.8)
            ax.axhline(1.0, color=AXIS, lw=1.2)
            ax.set_xticks(x, ops)
            ax.set_title(f"{s} - {m}")
            ax.set_ylabel("scalar time / vectorised time")
            ax.legend()
    fig.suptitle("Effect of auto-vectorisation (same code, -fno-tree-vectorize vs default)", fontsize=11,
                 fontweight="bold")
    footer(fig, f"{cpu}; photo input; warm cache; >1 means the vectorised build is faster.")
    fig.tight_layout()
    save(fig, out, "fig_simd_effect.png")


def fig_adaptive(df, out, cpu):
    d = df[(df.suite == "adaptive_unseen") & (df.build_variant == "native")]
    if d.empty:
        return
    ops = [o for o in ["yuv", "hsv", "lab"] if o in set(d.op)]
    sizes = sorted(set(d["size"]), key=px_of)
    fig, axes = plt.subplots(2, len(ops), figsize=(4.6 * len(ops), 6.6), squeeze=False, sharey="row")
    show = [("oracle", "#52514e", "*", "best fixed tile (oracle, post hoc)"),
            ("tiled_32x32",) + strat_style("tiled_32x32"), ("tiled_128x128",) + strat_style("tiled_128x128"),
            ("morton",) + strat_style("morton"), ("adaptive_model",) + strat_style("adaptive_model"),
            ("adaptive_calib",) + strat_style("adaptive_calib")]
    for i, m in enumerate(["identity", "rotate90"]):
        for j, op in enumerate(ops):
            ax = axes[i][j]
            g = d[(d.mapping == m) & (d.op == op)]
            x = np.arange(len(sizes))
            ax.axhline(1.0, color=AXIS, lw=1.2)
            for key, c, mk, nm in show:
                ys = []
                for s in sizes:
                    gs = g[g["size"] == s]
                    if key == "oracle":
                        t = gs[gs.strategy == "tiled"]
                        ys.append(t.speedup.max() if len(t) else np.nan)
                    else:
                        v = gs[gs.label == key].speedup
                        ys.append(v.iloc[0] if len(v) else np.nan)
                ax.plot(x, ys, color=c, marker=mk, label=nm, lw=1.6 if key != "oracle" else 1.0,
                        ls="-" if key != "oracle" else ":", markeredgecolor=SURFACE, markersize=7)
            ax.set_xticks(x, [s.replace("x", "\nx") for s in sizes], fontsize=7)
            ax.set_yscale("log")
            ax.set_title(f"{op} - {m}")
            if j == 0:
                ax.set_ylabel("speedup vs row-major (x, log)")
    for row in axes:
        for ax in row:
            ratio_ticks(ax)
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.06))
    fig.suptitle("Adaptive tiling on image dimensions never used during development", y=1.10, fontsize=11,
                 fontweight="bold")
    footer(fig, f"{cpu}; photo input; warm cache; native build; median of 7 reps; adaptive times exclude the "
                "one-off selection cost (reported separately).")
    fig.tight_layout()
    save(fig, out, "fig_adaptive_vs_fixed.png")


def fig_variability(df, raw, out, cpu):
    sp = os.path.join(raw, "samples_native.csv")
    if not os.path.exists(sp):
        return
    s = pd.read_csv(sp)
    d = df[df.build_variant == "native"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    suites = [x for x in ["main", "tile_sweep", "tile_shape", "cache_condition", "overhead", "content",
                          "adaptive_unseen", "simd_compare"] if x in set(d.suite)]
    data = [d[d.suite == x].cv_pct.values for x in suites]
    bp = axes[0].boxplot(data, patch_artist=True, showfliers=True)
    for b in bp["boxes"]:
        b.set(facecolor=BLUES[1], edgecolor=BLUES[5])
    for k in ("medians",):
        for mline in bp[k]:
            mline.set(color=INK, lw=1.5)
    axes[0].set_xticks(range(1, len(suites) + 1), [x.replace("_", "\n") for x in suites], fontsize=7)
    axes[0].set_yscale("log")
    axes[0].set_ylabel("coefficient of variation of reps (%, log)")
    axes[0].set_title("Run-to-run variability per suite")
    sel = s[(s.suite == "main") & (s.op == "yuv") & (s.width == 4096) & (s.mapping == "identity")]
    if sel.empty:
        sel = s[(s.suite == "main") & (s.op == "yuv")]
    labs = [l for l in STRAT if l in set(sel.label)]
    vals = [sel[sel.label == l].ms_per_run.values for l in labs]
    bp2 = axes[1].boxplot(vals, patch_artist=True)
    for b, l in zip(bp2["boxes"], labs):
        b.set(facecolor=strat_style(l)[0], edgecolor=INK2, alpha=0.85)
    for mline in bp2["medians"]:
        mline.set(color=INK, lw=1.5)
    axes[1].set_xticks(range(1, len(labs) + 1), [strat_style(l)[2] for l in labs], rotation=25, fontsize=7)
    axes[1].set_yscale("log")
    axes[1].set_ylabel("time per run (ms, log)")
    axes[1].set_title("Every repetition: yuv, 4096x4096, identity")
    fig.suptitle("Measurement variability", fontsize=11, fontweight="bold")
    footer(fig, f"{cpu}; repetitions interleaved across strategies in shuffled order; warm cache; native build.")
    fig.tight_layout()
    save(fig, out, "fig_variability.png")


def fig_correctness(out, cpu):
    p = os.path.join("results", "validation", "validation_summary.csv")
    if not os.path.exists(p):
        return
    v = pd.read_csv(p)
    v["err"] = v.max_abs_err.astype(float)
    g = v.groupby(["op", "reference", "channel"], sort=False).err.max().reset_index()
    fig, ax = plt.subplots(figsize=(11, 3.8))
    labels = [f"{r.op}\n{r.channel}" for r in g[g.reference == "numpy64"].itertuples()]
    x = np.arange(len(labels))
    for k, ref in enumerate(["numpy64", "opencv"]):
        vals = g[g.reference == ref].err.values
        ax.bar(x + (k - 0.5) * 0.4, np.maximum(vals, 1e-9), width=0.36, color=SERIES[k],
               label={"numpy64": "vs float64 NumPy reference (same convention)",
                      "opencv": "vs OpenCV cvtColor (float32)"}[ref], edgecolor=SURFACE)
    ax.set_xticks(x, labels, fontsize=7)
    ax.set_yscale("log")
    ax.set_ylabel("max absolute error (output units, log)")
    ax.legend(loc="upper left")
    ax.set_title("Numerical error of the C++ conversions (worst over 4 test images)")
    footer(fig, "Units: H in degrees, L* in 0..100, others in [0,1]. OpenCV float Lab uses an internal "
                "approximation (sawtooth error on the grey axis), so its gap is reported, not judged.")
    fig.tight_layout()
    save(fig, out, "fig_correctness.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join("results", "raw"))
    ap.add_argument("--out", default=os.path.join("results", "figures"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    df = load(args.raw)
    cpu, sysinfo = cpu_name(args.raw)
    fig_size_grid(df, args.out, cpu, "median_ms", "runtime (ms, log)", "fig_runtime_vs_size.png",
                  "Runtime vs image size")
    fig_size_grid(df, args.out, cpu, "mpix_per_s", "throughput (Mpixel/s, log)", "fig_throughput_vs_size.png",
                  "Throughput vs image size")
    fig_speedup(df, args.out, cpu)
    fig_cycles(df, args.out, cpu)
    fig_tile_sweep(df, args.out, cpu)
    fig_heatmap_tile_vs_size(df, args.out, cpu)
    fig_heatmap_shape(df, args.out, cpu)
    fig_sim(args.raw, args.out, cpu)
    fig_model_vs_measured(df, args.raw, args.out, cpu)
    fig_memory(args.raw, args.out, cpu, sysinfo)
    fig_cache_condition(df, args.out, cpu)
    fig_overhead(df, args.out, cpu)
    fig_simd(df, args.out, cpu)
    fig_adaptive(df, args.out, cpu)
    fig_variability(df, args.raw, args.out, cpu)
    fig_correctness(args.out, cpu)


if __name__ == "__main__":
    main()
