import { Download, FileText, GitCompare, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ApiError, api } from "../api/client";
import type { ExperimentDetail, ReportOut, ScalingPoint, VariantResult } from "../api/types";
import {
  CacheMissChart,
  CyclesChart,
  RepetitionsChart,
  RuntimeChart,
  ScalingChart,
  SpeedupChart,
  ThroughputChart,
  TileSizeChart,
} from "../components/charts";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  KeyValue,
  Loading,
  Notice,
  PageHeader,
  Panel,
  Segmented,
  SourceTag,
  StatusBadge,
  cx,
  tableCls,
  tdCls,
  thCls,
} from "../components/ui";
import { fmtBytes, fmtDate, fmtDuration, fmtMs, fmtNum, secondsSince, sizeLabel } from "../lib/format";
import { OP_NAMES, strategyColor, strategyName } from "../lib/strategies";
import { useApi } from "../lib/useApi";

const active = (d?: ExperimentDetail) => !!d && (d.status === "queued" || d.status === "running");

export default function ExperimentResults() {
  const { id = "" } = useParams();
  const exp = useApi(() => api.experiment(id), [id], { pollMs: 1500, shouldPoll: active });
  if (exp.error) return <ErrorState error={exp.error} onRetry={exp.reload} />;
  if (!exp.data) return <Loading label="Loading experiment" />;
  return <ExperimentView d={exp.data} />;
}

export function ExperimentView({ d }: { d: ExperimentDetail }) {
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [actionError, setActionError] = useState<ApiError>();

  async function remove() {
    setDeleting(true);
    try {
      await api.deleteExperiment(d.id);
      navigate("/history");
    } catch (e) {
      setActionError(e instanceof ApiError ? e : new ApiError(0, String(e)));
      setDeleting(false);
      setConfirm(false);
    }
  }

  return (
    <>
      <PageHeader
        title={d.name}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
            <span className="num text-ink">{d.id}</span>
            <span>{d.kind}</span>
            <StatusBadge status={d.status} />
            <span>created {fmtDate(d.created_at)}</span>
            {d.engine_seconds !== null && <span>wall time {fmtDuration(d.engine_seconds)}</span>}
          </span>
        }
        actions={
          <>
            {d.status === "completed" && d.kind !== "suite" && (
              <Link to={`/compare?ids=${d.id}`}>
                <Button>
                  <GitCompare size={14} /> Compare
                </Button>
              </Link>
            )}
            <Button variant="danger" onClick={() => setConfirm(true)} disabled={d.status === "running"} title={d.status === "running" ? "Running experiments cannot be deleted" : undefined}>
              <Trash2 size={14} /> Delete
            </Button>
          </>
        }
      />
      {actionError && (
        <div className="mb-4">
          <ErrorState error={actionError} />
        </div>
      )}
      <ConfirmDialog open={confirm} title="Delete this experiment?" confirmLabel="Delete" busy={deleting} onConfirm={() => void remove()} onCancel={() => setConfirm(false)}>
        This removes <span className="num">{d.id}</span>, its {d.result_count} stored results, every repetition and any generated reports. It cannot be undone.
      </ConfirmDialog>

      {active(d) && <PendingPanel d={d} />}
      {d.status === "failed" && <FailurePanel d={d} />}
      {d.status === "completed" && (d.kind === "suite" ? <SuiteResults d={d} /> : <CompletedResults d={d} />)}
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <ConfigPanel d={d} />
        <EnvironmentPanel d={d} />
      </div>
    </>
  );
}

function PendingPanel({ d }: { d: ExperimentDetail }) {
  const since = secondsSince(d.status === "running" ? d.started_at : d.created_at);
  return (
    <Panel title="Status">
      <div className="space-y-2">
        <p className="text-ink">
          {d.status === "queued"
            ? d.queue_position && d.queue_position > 0
              ? `Waiting in the queue (position ${d.queue_position}). Benchmarks run one at a time so they never share the machine.`
              : "Waiting for the worker."
            : "The engine is running. This page refreshes automatically."}
        </p>
        <p className="num text-xs text-muted">
          {d.status === "running" ? "running for" : "waiting for"} {fmtDuration(since)}
        </p>
        <Notice>Timings are only taken inside the engine; this page shows no progress estimate because the engine reports none.</Notice>
      </div>
    </Panel>
  );
}

function FailurePanel({ d }: { d: ExperimentDetail }) {
  return (
    <Panel title="Failure">
      <div className="space-y-3">
        <ErrorState error={new Error(d.error_message ?? "The experiment failed.")} />
        {d.error_detail && (
          <details className="text-[13px]">
            <summary className="cursor-pointer text-ink-2">Engine output (sanitised)</summary>
            <pre className="num mt-2 max-h-80 overflow-auto rounded bg-sunken p-3 text-xs">{d.error_detail}</pre>
          </details>
        )}
        <p className="text-xs text-muted">No measurements are shown for failed runs.</p>
      </div>
    </Panel>
  );
}

function ResultsTable({ results, showGroup = false }: { results: VariantResult[]; showGroup?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className={tableCls}>
        <thead>
          <tr>
            {showGroup && <th className={thCls}>group</th>}
            <th className={thCls}>variant</th>
            <th className={thCls}>tile</th>
            <th className={cx(thCls, "text-right")}>median</th>
            <th className={cx(thCls, "text-right")}>IQR (ms)</th>
            <th className={cx(thCls, "text-right")}>CV %</th>
            <th className={cx(thCls, "text-right")}>ns/px</th>
            <th className={cx(thCls, "text-right")}>Mpix/s</th>
            <th className={cx(thCls, "text-right")} title="estimate: ns/px × probed clock">cycles/px*</th>
            <th className={cx(thCls, "text-right")}>vs row-major</th>
            <th className={thCls}>output</th>
            <th className={cx(thCls, "text-right")}>reps</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr key={r.id}>
              {showGroup && (
                <td className={cx(tdCls, "num text-xs text-ink-2")}>
                  {OP_NAMES[r.op] ?? r.op} {r.mapping} {r.width}×{r.height} {r.image_kind} {r.condition}
                </td>
              )}
              <td className={tdCls}>
                <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: strategyColor(r.label) }} />
                {strategyName(r.label)}
                {r.setup_note && <span className="block text-xs text-muted" title={r.setup_note}>selection {fmtMs(r.setup_ms)} (excluded from timing)</span>}
              </td>
              <td className={cx(tdCls, "num")}>{r.tile_w ? `${r.tile_w}×${r.tile_h}` : "-"}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{fmtMs(r.median_ms)}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right text-ink-2")}>
                {fmtNum(r.p25_ms, 3)}–{fmtNum(r.p75_ms, 3)}
              </td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right", r.cv_pct > 5 && "text-warn")}>{fmtNum(r.cv_pct, 1)}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{fmtNum(r.ns_per_px, 3)}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{fmtNum(r.mpix_per_s, 1)}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right text-ink-2")}>{fmtNum(r.est_core_cycles_per_px, 1)}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{r.speedup_vs_row_major === null ? "n/a" : `${fmtNum(r.speedup_vs_row_major, 2)}×`}</td>
              <td className={tdCls}>
                {r.output_matches_baseline === null ? (
                  <span className="text-muted">n/a</span>
                ) : r.output_matches_baseline ? (
                  <span className="text-ok">bit-identical</span>
                ) : (
                  <span className="font-medium text-err">differs</span>
                )}
              </td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{r.reps}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">
        Times are medians of interleaved repetitions measured by the engine. *cycles/px is an estimate (ns/px × effective clock from an IMUL probe);
        hardware counters were <SourceTag kind="unavailable" />. CV above 5% is highlighted.
      </p>
    </div>
  );
}

function CompletedResults({ d }: { d: ExperimentDetail }) {
  const results = d.results;
  if (results.length === 0) return <EmptyState title="The run completed without results" />;
  const squareTiles = results.filter((r) => r.strategy === "tiled" && r.tile_w === r.tile_h);
  const anyMismatch = results.some((r) => r.output_matches_baseline === false);
  return (
    <div className="space-y-5">
      {anyMismatch && <Notice tone="warn">At least one variant produced output that differs from the row-major baseline. Its timing should not be compared.</Notice>}
      <Panel title="Measurements" aside={<SourceTag kind="measured" />}>
        <ResultsTable results={results} />
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <RuntimeChart results={results} />
        {results.length > 1 ? <SpeedupChart results={results} /> : <ThroughputChart results={results} />}
        {results.length > 1 && <ThroughputChart results={results} />}
        <CyclesChart results={results} />
        <div className="lg:col-span-2">
          <RepetitionsChart results={results} />
        </div>
        {squareTiles.length >= 2 && <TileSizeChart results={results} />}
      </div>
      <CacheSection d={d} />
      <CorrectnessPanel d={d} />
      <ReportsPanel d={d} />
    </div>
  );
}

function CacheSection({ d }: { d: ExperimentDetail }) {
  const geo = d.cache_geometry;
  if (!geo) return null;
  if (geo.skipped) return <Notice>Cache model not run: {geo.skipped}.</Notice>;
  return (
    <Panel title="Cache model" aside={<SourceTag kind="simulated" />}>
      <div className="space-y-4">
        <p className="text-[13px] text-ink-2">
          {geo.policy}. Geometry: <span className="num">{geo.source}</span>{" "}
          {geo.levels?.map((l) => `${l.name} ${fmtBytes(l.size_bytes)} ${l.ways}-way`).join(" · ")}. Hardware prefetchers are not modelled.
        </p>
        <div className="grid gap-4 lg:grid-cols-2">
          <CacheMissChart rows={d.cache} metric="misses_per_px" />
          <CacheMissChart rows={d.cache} metric="miss_rate" />
        </div>
        <CacheTable rows={d.cache} />
      </div>
    </Panel>
  );
}

export function CacheTable({ rows }: { rows: { label: string; level: string; accesses: number; misses: number; miss_rate: number; misses_per_px: number; writebacks: number; dram_read_bytes_per_px: number }[] }) {
  return (
    <div className="overflow-x-auto">
      <table className={tableCls}>
        <thead>
          <tr>
            {["variant", "level", "accesses", "hits", "misses", "miss rate", "misses/px", "write-backs", "DRAM read B/px"].map((h, i) => (
              <th key={h} className={cx(thCls, i > 1 && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={`${c.label}-${c.level}`}>
              <td className={tdCls}>{strategyName(c.label)}</td>
              <td className={cx(tdCls, "num")}>{c.level}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{c.accesses.toLocaleString()}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{(c.accesses - c.misses).toLocaleString()}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{c.misses.toLocaleString()}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{fmtNum(c.miss_rate, 4)}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{fmtNum(c.misses_per_px, 4)}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{c.writebacks.toLocaleString()}</td>
              <td className={cx(tdCls, "num whitespace-nowrap text-right")}>{fmtNum(c.dram_read_bytes_per_px, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CorrectnessPanel({ d }: { d: ExperimentDetail }) {
  const matches = d.results.filter((r) => r.output_matches_baseline !== null);
  const v = d.validation;
  return (
    <Panel title="Correctness">
      <div className="space-y-3 text-[13px]">
        <p>
          <span className="num">{matches.filter((r) => r.output_matches_baseline).length}/{matches.length}</span> variant outputs are bit-identical to the
          row-major baseline (64-bit hash of the full output, computed outside the timed runs).
        </p>
        {!v ? null : v.ran && v.references ? (
          <div className="overflow-x-auto">
            <table className={tableCls}>
              <thead>
                <tr>
                  {["reference", "channel", "max |error|", "mean |error|", "tolerance", "verdict"].map((h) => (
                    <th key={h} className={thCls}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(v.references).flatMap(([ref, info]) =>
                  info.channels.map((c) => (
                    <tr key={`${ref}-${c.channel}`}>
                      <td className={tdCls}>{ref === "numpy64" ? "float64 NumPy (same convention)" : "OpenCV cvtColor"}</td>
                      <td className={cx(tdCls, "num")}>{c.channel}</td>
                      <td className={cx(tdCls, "num")}>{c.max_abs_err.toExponential(2)}</td>
                      <td className={cx(tdCls, "num")}>{c.mean_abs_err.toExponential(2)}</td>
                      <td className={cx(tdCls, "num")}>{c.tolerance === null ? "reported only" : c.tolerance.toExponential(1)}</td>
                      <td className={tdCls}>
                        {c.pass === null ? <span className="text-muted">n/a</span> : c.pass ? <span className="text-ok">within</span> : <span className="text-err">outside</span>}
                      </td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted">OpenCV's float Lab uses its own approximation, so its Lab gap is reported rather than judged (see docs/results.md).</p>
          </div>
        ) : (
          <p className="text-ink-2">Reference validation not run: {v.reason}.</p>
        )}
      </div>
    </Panel>
  );
}

function ReportsPanel({ d }: { d: ExperimentDetail }) {
  const [busy, setBusy] = useState<string>();
  const [made, setMade] = useState<ReportOut[]>([]);
  const [error, setError] = useState<ApiError>();
  const make = async (fmt: "html" | "md") => {
    setBusy(fmt);
    setError(undefined);
    try {
      const r = await api.createReport(d.id, fmt);
      setMade((m) => [r, ...m]);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      setBusy(undefined);
    }
  };
  return (
    <Panel title="Report">
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => void make("html")} disabled={!!busy}>
          <FileText size={14} /> {busy === "html" ? "Generating…" : "Generate HTML report"}
        </Button>
        <Button onClick={() => void make("md")} disabled={!!busy}>
          <FileText size={14} /> {busy === "md" ? "Generating…" : "Generate Markdown report"}
        </Button>
        <Link to="/reports" className="text-[13px] text-accent hover:underline">
          all reports
        </Link>
      </div>
      {error && <div className="mt-3"><ErrorState error={error} /></div>}
      {made.length > 0 && (
        <ul className="mt-3 space-y-1 text-[13px]">
          {made.map((r) => (
            <li key={r.id}>
              <a className="inline-flex items-center gap-1 text-accent hover:underline" href={api.reportUrl(r.id)}>
                <Download size={13} /> {r.format.toUpperCase()} report <span className="num">{r.id}</span> ({fmtBytes(r.size_bytes)})
              </a>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function SuiteResults({ d }: { d: ExperimentDetail }) {
  const ops = useMemo(() => [...new Set(d.results.map((r) => r.op))], [d.results]);
  const maps = useMemo(() => [...new Set(d.results.map((r) => r.mapping))], [d.results]);
  const [op, setOp] = useState(ops[0] ?? "");
  const [mapping, setMapping] = useState(maps[0] ?? "");
  const sel = d.results.filter((r) => r.op === op && r.mapping === mapping);
  const points: ScalingPoint[] = sel.map((r) => ({
    label: r.label,
    width: r.width,
    height: r.height,
    pixels: r.width * r.height,
    ns_per_px: r.ns_per_px,
    mpix_per_s: r.mpix_per_s,
    median_ms: r.median_ms,
    n_results: 1,
    experiments: [d.id],
  }));
  if (d.results.length === 0) return <EmptyState title="The suite completed without results" />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Segmented label="conversion" value={op} onChange={setOp} options={ops.map((o) => ({ value: o, label: OP_NAMES[o] ?? o }))} />
        <Segmented label="mapping" value={mapping} onChange={setMapping} options={maps.map((m) => ({ value: m, label: m }))} />
      </div>
      {new Set(points.map((p) => p.pixels)).size > 1 && <ScalingChart points={points} metric="ns_per_px" />}
      <Panel title={`${d.results.length} results in this suite run`} aside={<SourceTag kind="measured" />}>
        <ResultsTable results={sel} showGroup />
      </Panel>
      <ReportsPanel d={d} />
    </div>
  );
}

function ConfigPanel({ d }: { d: ExperimentDetail }) {
  return (
    <Panel title="Configuration">
      <KeyValue
        rows={[
          ["conversion", d.op ? `${OP_NAMES[d.op] ?? d.op}` : d.suite_name ? `suite ${d.suite_name}` : "n/a"],
          ["mapping", d.mapping ?? "per suite"],
          ["image", d.width ? sizeLabel(d.width, d.height) : "per suite"],
          ["input", d.image_detail ?? d.image_source ?? "n/a"],
          ["cache state", d.condition ?? "per suite"],
          ["repetitions", d.reps ?? "per suite"],
          ["strategies", d.strategies.map(strategyName).join(", ") || "per suite"],
        ]}
      />
      {d.engine_command && (
        <>
          <p className="mb-1 mt-4 text-xs font-medium text-ink-2">Engine command (paths replaced by placeholders)</p>
          <pre className="num overflow-x-auto whitespace-pre-wrap break-all rounded bg-sunken p-2 text-[11.5px]">{d.engine_command.join(" ")}</pre>
        </>
      )}
    </Panel>
  );
}

function EnvironmentPanel({ d }: { d: ExperimentDetail }) {
  const env = (d.environment ?? {}) as Record<string, unknown>;
  const caches = ((env.caches as Record<string, unknown>[] | undefined) ?? []).filter((c) => String(c.source).startsWith("cpuid"));
  if (!d.environment) {
    return (
      <Panel title="Environment">
        <p className="text-ink-2">{d.status === "completed" ? "No environment was recorded." : "Recorded by the engine when the run finishes."}</p>
      </Panel>
    );
  }
  return (
    <Panel title="Environment">
      <KeyValue
        rows={[
          ["CPU", String(env.cpu_brand ?? "unknown")],
          ["OS", String(env.os ?? "unknown")],
          ["compiler", d.compiler ?? "unknown"],
          ["flags", d.build_flags ?? "unknown"],
          ["SIMD", String(env.simd_enabled_at_compile_time ?? "unknown")],
          ["pinned core", String(env.pinned_cpu ?? "unknown")],
          ["AC power", String(env.ac_power ?? "unknown")],
          ["TSC", env.tsc_ghz_measured ? `${fmtNum(Number(env.tsc_ghz_measured), 3)} GHz (measured)` : "unknown"],
          ...caches.map(
            (c) =>
              [`L${c.level} ${c.type}`, `${fmtBytes(Number(c.size_bytes))}, ${c.ways}-way, ${c.line_bytes} B lines`] as [string, string],
          ),
          ["hardware counters", "unavailable"],
        ]}
      />
    </Panel>
  );
}
