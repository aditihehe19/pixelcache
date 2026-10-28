"""Experiment reports (self-contained HTML or Markdown) built only from stored data.

Sections are labelled by provenance: "Measurements" (engine output), "Model
output" (cache simulator), and "Interpretation", which is rule-based text derived
from the measurements and explicitly marked as interpretation, not evidence.
"""
from __future__ import annotations

import base64
import html
import io
import json
import sys
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.experiment import Experiment, Report
from app.services.experiment_service import detail as experiment_detail

sys.path.insert(0, str(settings.repo_root / "scripts"))
import plot_results as pr  # noqa: E402  (reuses the project's palette and strategy styles)
import matplotlib.pyplot as plt  # noqa: E402

COMPULSORY_MISSES_PER_PX = 15 / 64  # 3 B read + 12 B written per pixel, 64-byte lines


# ---- charts ----------------------------------------------------------------------

def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _style(label: str) -> tuple[str, str, str]:
    if label in pr.STRAT:
        return pr.STRAT[label]
    if label.startswith("tiled_"):
        return ("#e34948", "h", label.replace("_", " "))
    return ("#898781", "o", label)


def _runtime_chart(results) -> str:
    fig, ax = plt.subplots(figsize=(7.5, 0.55 * len(results) + 1.4))
    labels = [r.label for r in results]
    med = [r.median_ms for r in results]
    err = [[r.median_ms - r.p25_ms for r in results], [r.p75_ms - r.median_ms for r in results]]
    ax.barh(labels, med, xerr=err, color=[_style(l)[0] for l in labels], capsize=3, edgecolor=pr.SURFACE)
    ax.invert_yaxis()
    ax.set_xlabel("median time per run (ms); whiskers = interquartile range")
    ax.set_title("Runtime by traversal (measured)")
    return _png(fig)


def _reps_chart(results) -> str:
    fig, ax = plt.subplots(figsize=(7.5, 0.55 * len(results) + 1.4))
    for i, r in enumerate(results):
        xs = [x.ms_per_run for x in r.repetitions]
        ax.scatter(xs, [i] * len(xs), color=_style(r.label)[0], marker=_style(r.label)[1], s=28, zorder=3)
    ax.set_yticks(range(len(results)), [r.label for r in results])
    ax.invert_yaxis()
    ax.set_xlabel("time per run (ms), one marker per repetition")
    ax.set_title("Every repetition (measured)")
    return _png(fig)


def _cache_chart(rows, labels) -> str:
    levels = [l for l in ("L1D", "L2", "L3") if any(c.level == l for c in rows)]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    width = 0.8 / max(1, len(labels))
    for k, lab in enumerate(labels):
        vals = [next((c.misses_per_px for c in rows if c.label == lab and c.level == lv), 0.0) for lv in levels]
        ax.bar([i + (k - (len(labels) - 1) / 2) * width for i in range(len(levels))], vals, width=width * 0.9,
               color=_style(lab)[0], label=lab, edgecolor=pr.SURFACE)
    ax.axhline(COMPULSORY_MISSES_PER_PX, color=pr.AXIS, ls="--", lw=1)
    ax.set_xticks(range(len(levels)), levels)
    ax.set_ylabel("simulated misses per pixel")
    ax.set_title("Cache model (SIMULATED, not hardware counters); dashed = compulsory 15/64")
    ax.legend(fontsize=7)
    return _png(fig)


# ---- content ---------------------------------------------------------------------

def _fmt(v, nd=3) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def _interpretation(d, env: dict) -> list[str]:
    notes: list[str] = []
    rs = d.results
    if not rs:
        return notes
    groups = {(r.op, r.mapping, r.width, r.height, r.condition) for r in rs}
    if len(groups) == 1:
        best = min(rs, key=lambda r: r.median_ms)
        row = next((r for r in rs if r.label == "row_major"), None)
        if row and best.label != "row_major":
            notes.append(f"{best.label} was the fastest variant, {row.median_ms / best.median_ms:.2f}x faster than "
                         "row-major in this run.")
        elif row:
            notes.append("Row-major was the fastest variant in this run.")
        ws = 15 * rs[0].width * rs[0].height
        llc = max((c.get("size_bytes", 0) for c in env.get("caches", []) if c.get("level") == 3), default=0)
        if llc:
            where = "fits in" if ws <= llc else "exceeds"
            notes.append(f"The working set (3 B in + 12 B out per pixel = {ws / 2**20:.1f} MiB) {where} the "
                         f"{llc / 2**20:.0f} MiB last-level cache, so the run is "
                         f"{'mostly cache-resident' if ws <= llc else 'bound by DRAM traffic for memory-bound kernels'}.")
        for r in rs:
            if row and r.label == "column_major" and r.median_ms > 2 * row.median_ms:
                notes.append(f"Column-major was {r.median_ms / row.median_ms:.1f}x slower than row-major: a stride of "
                             "one image row touches a new cache line for nearly every pixel.")
            if row and r.label == "morton" and r.median_ms > 1.2 * row.median_ms:
                notes.append("Morton order was slower than row-major. Its locality is good, but per-pixel address "
                             "generation (bit de-interleaving) and the loss of vectorisable inner loops cost more.")
        if rs[0].mapping == "rotate90" and row and any(r.strategy in ("tiled", "adaptive") and
                                                       r.median_ms < 0.8 * row.median_ms for r in rs):
            notes.append("With the rotated output, blocking helped: inside a tile, successive output lines are filled "
                         "while they are still cached, whereas row-major writes one 12-byte pixel per output line.")
        if rs[0].op == "lab":
            notes.append("CIELAB is compute-heavy (three cube roots per pixel), so memory-order effects are partly "
                         "hidden behind arithmetic.")
    noisy = [r.label for r in rs if r.cv_pct > 5]
    if noisy:
        notes.append(f"Run-to-run variation exceeded 5% (CV) for {', '.join(noisy[:6])}; treat differences "
                     "under about 5% as ties.")
    if d.cache:
        worst = max(d.cache, key=lambda c: c.misses_per_px)
        notes.append(f"In the cache model, {worst.label} has the most {worst.level} misses ({worst.misses_per_px:.3f} "
                     f"per pixel versus the compulsory {COMPULSORY_MISSES_PER_PX:.3f}). This is a model without "
                     "hardware prefetching, so it explains conflict and capacity effects but not prefetch-hidden "
                     "latency.")
    return notes


def _limitations(d, env: dict) -> list[str]:
    out = ["Hardware performance counters (cycles, instructions, cache misses) were unavailable; cycle figures are "
           "estimates from an effective-clock probe and cache figures come only from the simulator.",
           "Results describe one machine, one pinned core, and one compiler build; other CPUs, page sizes or compilers "
           "move the crossovers.",
           "Background processes share the last-level cache and memory bus; repetitions are interleaved to spread "
           "slow drifts across variants, not to remove them."]
    ghz = [x.core_ghz_probe for r in d.results for x in r.repetitions if x.core_ghz_probe]
    if ghz:
        out.append(f"The effective core clock varied between {min(ghz):.2f} and {max(ghz):.2f} GHz across "
                   "repetition rounds (dynamic frequency scaling).")
    if env.get("ac_power", "").startswith("no"):
        out.append("The machine was on battery power, which lowers and destabilises clock frequencies.")
    if d.reps and d.reps < 7:
        out.append(f"Only {d.reps} repetitions were run; medians and IQRs are correspondingly uncertain.")
    return out


def _tables(d) -> tuple[list[str], list[list[str]]]:
    head = ["variant", "tile", "median ms", "IQR ms", "CV %", "ns/px", "Mpix/s", "est. cycles/px", "speedup vs row",
            "output = baseline", "reps"]
    rows = []
    for r in d.results:
        rows.append([r.label, f"{r.tile_w}x{r.tile_h}" if r.tile_w else "-", _fmt(r.median_ms, 4),
                     f"{r.p25_ms:.4f}-{r.p75_ms:.4f}", _fmt(r.cv_pct, 2), _fmt(r.ns_per_px, 3), _fmt(r.mpix_per_s, 1),
                     _fmt(r.est_core_cycles_per_px, 1), _fmt(r.speedup_vs_row_major, 2),
                     {True: "yes (bit-identical)", False: "NO", None: "n/a"}[r.output_matches_baseline], str(r.reps)])
    return head, rows


def build_report(d, fmt: str) -> tuple[str, str]:
    env = d.environment or {}
    title = f"PixelCache report: {d.name}"
    head, rows = _tables(d)
    single_group = len({(r.op, r.mapping, r.width, r.height, r.condition) for r in d.results}) == 1
    charts = []
    if d.results and single_group:
        charts.append(("Runtime by traversal", _runtime_chart(d.results)))
        charts.append(("Repetitions", _reps_chart(d.results)))
    if d.cache:
        labels = list(dict.fromkeys(c.label for c in d.cache))
        charts.append(("Cache model", _cache_chart(d.cache, labels)))

    cfg = d.config
    config_lines = [("experiment id", d.id), ("kind", d.kind), ("created", d.created_at.isoformat()),
                    ("conversion", d.op or "suite"), ("output mapping", d.mapping or "-"),
                    ("image", f"{d.width}x{d.height}" if d.width else "suite sizes"),
                    ("image source", d.image_detail or d.image_source or "-"),
                    ("cache condition", d.condition or "-"), ("repetitions per variant", d.reps or "-"),
                    ("strategies", ", ".join(d.strategies)), ("suite", d.suite_name or "-")]
    env_lines = [("CPU", env.get("cpu_brand", "unknown")), ("OS", env.get("os", "unknown")),
                 ("compiler", d.compiler or env.get("compiler", "unknown")), ("build flags", d.build_flags or "unknown"),
                 ("SIMD at compile time", env.get("simd_enabled_at_compile_time", "unknown")),
                 ("pinned core", env.get("pinned_cpu", "unknown")), ("AC power", env.get("ac_power", "unknown")),
                 ("TSC (measured)", f"{env.get('tsc_ghz_measured', 0):.3f} GHz" if env.get("tsc_ghz_measured") else "unknown"),
                 ("hardware counters", "unavailable on this platform")]
    caches = [f"L{c['level']} {c['type']}: {c['size_bytes'] // 1024} KiB, {c['ways']}-way, {c['line_bytes']} B lines "
              f"({c['source']})" for c in env.get("caches", []) if str(c.get("source", "")).startswith("cpuid")]
    validation = d.validation or {}
    method = ("Each variant runs the same inlined per-pixel kernel; only the visiting order differs. The engine pins "
              "itself to a performance core, removes first-touch effects with an untimed warm-up, runs a row-major "
              "baseline to hash the reference output, then times all variants in shuffled, interleaved rounds "
              f"({d.reps or 'configured'} repetitions each, one run per repetition). Input generation, cache flushing, "
              "hashing, adaptive tile selection, the cache model and reference validation all happen outside the "
              "timed region.")
    interp = _interpretation(d, env)
    limits = _limitations(d, env)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if fmt == "md":
        md = [f"# {title}", "", f"_Generated {generated} from stored experiment data._", "",
              "## Research objective", "",
              "Measure how memory traversal order affects the run time, throughput and (simulated) cache behaviour "
              "of colour-space conversion, with the conversion arithmetic held constant.", "",
              "## Configuration", ""] + [f"- **{k}**: {v}" for k, v in config_lines] + [
              "", "## Environment", ""] + [f"- **{k}**: {v}" for k, v in env_lines] + [f"- {c}" for c in caches] + [
              "", "## Methodology", "", method, "", "## Measurements", "",
              "| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + \
             ["| " + " | ".join(r) + " |" for r in rows]
        for name, b64 in charts:
            md += ["", f"![{name}](data:image/png;base64,{b64})"]
        md += ["", "## Correctness", "", _validation_text(validation, d)]
        if d.cache:
            md += ["", "## Model output (cache simulator)", "",
                   "| variant | level | accesses | misses | miss rate | misses/px |", "|---|---|---|---|---|---|"]
            md += [f"| {c.label} | {c.level} | {c.accesses} | {c.misses} | {c.miss_rate:.4f} | {c.misses_per_px:.4f} |"
                   for c in d.cache]
        md += ["", "## Interpretation (rule-based, derived from the measurements above)", ""] + \
              [f"- {n}" for n in interp or ["No automatic interpretation applies."]]
        md += ["", "## Limitations and sources of noise", ""] + [f"- {n}" for n in limits]
        return title, "\n".join(md) + "\n"

    e = html.escape
    kv = lambda items: "".join(f"<tr><th>{e(str(k))}</th><td>{e(str(v))}</td></tr>" for k, v in items)  # noqa: E731
    table = ("<table class='data'><thead><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr></thead><tbody>" +
             "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>")
    cache_table = ""
    if d.cache:
        cache_table = ("<h2>Model output (cache simulator)</h2><p class='note'>Simulated by cachevision_sim: "
                       "true-LRU, write-allocate, no prefetching. Not hardware counters.</p><table class='data'><thead>"
                       "<tr><th>variant</th><th>level</th><th>accesses</th><th>misses</th><th>miss rate</th>"
                       "<th>misses/px</th></tr></thead><tbody>" +
                       "".join(f"<tr><td>{e(c.label)}</td><td>{c.level}</td><td>{c.accesses}</td><td>{c.misses}</td>"
                               f"<td>{c.miss_rate:.4f}</td><td>{c.misses_per_px:.4f}</td></tr>" for c in d.cache) +
                       "</tbody></table>")
    figs = "".join(f"<figure><img alt='{e(n)}' src='data:image/png;base64,{b}'><figcaption>{e(n)}</figcaption></figure>"
                   for n, b in charts)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>
body{{font-family:"Segoe UI",system-ui,sans-serif;background:#fbfaf7;color:#1b2433;max-width:980px;margin:32px auto;padding:0 16px;line-height:1.5}}
h1{{font-size:1.5rem}} h2{{font-size:1.1rem;border-bottom:1px solid #ddd8cc;padding-bottom:4px;margin-top:2rem}}
table{{border-collapse:collapse;font-size:.85rem;margin:8px 0}} th,td{{border:1px solid #ddd8cc;padding:4px 8px;text-align:left}}
table.data td{{font-family:ui-monospace,Consolas,monospace}} .note{{color:#5b6472;font-size:.85rem}}
figure{{margin:16px 0}} img{{max-width:100%}} figcaption{{font-size:.8rem;color:#5b6472}}
</style></head><body>
<h1>{e(title)}</h1><p class="note">Generated {generated} from stored experiment data (experiment {e(d.id)}).</p>
<h2>Research objective</h2><p>Measure how memory traversal order affects the run time, throughput and (simulated) cache behaviour of colour-space conversion, with the conversion arithmetic held constant.</p>
<h2>Configuration</h2><table>{kv(config_lines)}</table>
<h2>Hardware and software environment</h2><table>{kv(env_lines)}</table><ul>{''.join(f'<li>{e(c)}</li>' for c in caches)}</ul>
<h2>Methodology</h2><p>{e(method)}</p>
<h2>Measurements</h2>{table}{figs}
<h2>Correctness</h2><p>{e(_validation_text(validation, d))}</p>{cache_table}
<h2>Interpretation <span class="note">(rule-based, derived from the measurements above; not additional evidence)</span></h2>
<ul>{''.join(f'<li>{e(n)}</li>' for n in interp) or '<li>No automatic interpretation applies.</li>'}</ul>
<h2>Limitations and sources of noise</h2><ul>{''.join(f'<li>{e(n)}</li>' for n in limits)}</ul>
<p class="note">Configuration as submitted: {e(json.dumps(cfg))}</p>
</body></html>"""
    return title, doc


def _validation_text(validation: dict, d) -> str:
    match = [r.output_matches_baseline for r in d.results if r.output_matches_baseline is not None]
    parts = []
    if match:
        parts.append(f"{sum(match)}/{len(match)} variant outputs were bit-identical to the row-major baseline "
                     "(64-bit hash of the whole output).")
    if validation.get("ran"):
        for ref, info in validation.get("references", {}).items():
            worst = max(info["channels"], key=lambda c: c["max_abs_err"])
            verdict = {True: "within tolerance", False: "OUTSIDE tolerance", None: "reported only"}[info["passed"]]
            parts.append(f"Against {ref}: worst channel {worst['channel']} max |error| {worst['max_abs_err']:.3g} "
                         f"({verdict}).")
    elif validation:
        parts.append(f"Reference validation not run: {validation.get('reason', 'n/a')}.")
    return " ".join(parts) or "No correctness information was recorded."


# ---- persistence -----------------------------------------------------------------

def create_report(db: Session, exp: Experiment, fmt: str) -> Report:
    if exp.status != "completed":
        raise HTTPException(409, "Reports can only be generated for completed experiments.")
    d = experiment_detail(exp)
    title, content = build_report(d, fmt)
    rep = Report(experiment_id=exp.id, format=fmt, title=title[:200], filename="", size_bytes=0)
    db.add(rep)
    db.flush()
    rep.filename = f"{rep.id}.{fmt}"
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    (settings.reports_dir / rep.filename).write_bytes(data)
    rep.size_bytes = len(data)
    db.commit()
    return rep


def list_reports(db: Session) -> list[Report]:
    return list(db.scalars(select(Report).order_by(Report.created_at.desc())))


def report_path(db: Session, report_id: str):
    rep = db.get(Report, report_id) if len(report_id) == 12 and report_id.isalnum() else None
    if rep is None:
        raise HTTPException(404, "Report not found.")
    path = (settings.reports_dir / rep.filename).resolve()
    if path.parent != settings.reports_dir.resolve() or not path.exists():
        raise HTTPException(404, "Report file is missing.")
    return rep, path
