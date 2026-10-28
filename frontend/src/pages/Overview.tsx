import { ArrowRight, FlaskConical } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import { ScalingChart } from "../components/charts";
import { Button, EmptyState, ErrorState, KeyValue, Loading, PageHeader, Panel, Segmented, SourceTag, StatusBadge } from "../components/ui";
import { fmtBytes, fmtDate, fmtNum, sizeLabel } from "../lib/format";
import { OP_NAMES, STRATEGY_HELP, strategyName } from "../lib/strategies";
import { useApi } from "../lib/useApi";

export default function Overview() {
  const summary = useApi(() => api.summary(), []);
  const caps = useApi(() => api.capabilities(), []);
  const sys = useApi(() => api.systemInfo(), []);
  const measuredOps = summary.data?.measured_ops ?? [];
  // Default to the workload of the largest recorded speedup (it has a row-major
  // baseline), otherwise the first measured conversion.
  const firstBest = summary.data?.best_speedups_vs_row_major[0];
  const [op, setOp] = useState<string>("");
  const [mapping, setMapping] = useState<"identity" | "rotate90" | "">("");
  const chartOp = op || firstBest?.op || measuredOps[0] || "";
  const chartMapping = mapping || (firstBest?.mapping as "identity" | "rotate90" | undefined) || "identity";
  const scaling = useApi(() => api.scaling(chartOp, chartMapping), [chartOp, chartMapping], { enabled: !!chartOp });

  const l3 = useMemo(() => sys.data?.caches.find((c) => c.level === 3 && c.source.startsWith("cpuid")), [sys.data]);

  return (
    <>
      <PageHeader
        title="PixelCache"
        subtitle={
          <>
            How do memory-traversal order, spatial tiling and cache geometry change the cost of colour-space conversion?
            Every number here comes from the C++ engine (<span className="num">cachevision_bench</span>) or its cache
            model, run on this machine.
          </>
        }
        actions={
          <Link to="/experiments/new">
            <Button variant="primary">
              <FlaskConical size={15} /> New experiment
            </Button>
          </Link>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Engine" className="lg:col-span-1">
          {caps.error ? (
            <ErrorState error={caps.error} onRetry={caps.reload} />
          ) : !caps.data ? (
            <Loading />
          ) : (
            <KeyValue
              rows={[
                ["benchmark binary", caps.data.engine_available ? "built" : "missing: build with CMake"],
                ["cache simulator", caps.data.simulator_available ? "built" : "missing"],
                ["CPU", sys.data?.cpu?.value ?? (sys.loading ? "…" : "unknown")],
                ["last-level cache", l3 ? `${fmtBytes(l3.size_bytes)}, ${l3.ways}-way` : "unknown"],
                ["hardware counters", <span key="hc" className="inline-flex items-center gap-2">unavailable <SourceTag kind="unavailable" /></span>],
              ]}
            />
          )}
        </Panel>

        <Panel title="Stored measurements" className="lg:col-span-1">
          {summary.error ? (
            <ErrorState error={summary.error} onRetry={summary.reload} />
          ) : !summary.data ? (
            <Loading />
          ) : (
            <KeyValue
              rows={[
                ["completed experiments", summary.data.experiments.completed],
                ["failed / queued", `${summary.data.experiments.failed} / ${summary.data.experiments.queued + summary.data.experiments.running}`],
                ["variant results", summary.data.variant_results],
                ["individual repetitions", summary.data.repetitions],
                ["conversions measured", summary.data.measured_ops.map((o) => OP_NAMES[o] ?? o).join(", ") || "none yet"],
              ]}
            />
          )}
        </Panel>

        <Panel title="Most recent result" className="lg:col-span-1">
          {!summary.data ? (
            summary.loading ? <Loading /> : null
          ) : summary.data.latest_completed ? (
            <div className="space-y-2">
              <Link to={`/experiments/${summary.data.latest_completed.id}`} className="font-medium text-accent hover:underline">
                {summary.data.latest_completed.name}
              </Link>
              <KeyValue
                rows={[
                  ["id", summary.data.latest_completed.id],
                  ["finished", fmtDate(summary.data.latest_completed.finished_at)],
                  ["image", sizeLabel(summary.data.latest_completed.width, summary.data.latest_completed.height)],
                  [
                    "fastest",
                    summary.data.latest_completed.best_label
                      ? `${strategyName(summary.data.latest_completed.best_label)} (${fmtNum(summary.data.latest_completed.best_median_ms, 3)} ms)`
                      : "n/a",
                  ],
                ]}
              />
              <StatusBadge status="completed" />
            </div>
          ) : (
            <p className="text-ink-2">No experiment has completed yet.</p>
          )}
        </Panel>
      </div>

      <section className="mt-6">
        {summary.data && summary.data.variant_results === 0 ? (
          <EmptyState
            title="No measurements yet"
            action={
              <Link to="/experiments/new">
                <Button variant="primary">
                  Open the workbench <ArrowRight size={14} />
                </Button>
              </Link>
            }
          >
            Run a first comparison, for example YUV on a 1024×1024 photo with row-major, tiled 32×32 and Morton, and its
            measurements will appear here. Charts are drawn only from stored results.
          </EmptyState>
        ) : (
          summary.data && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-[13px] font-semibold uppercase tracking-wide text-ink-2">Measured scaling</h2>
                <div className="flex flex-wrap gap-2">
                  <Segmented
                    label="conversion"
                    value={chartOp}
                    onChange={setOp}
                    options={measuredOps.map((o) => ({ value: o, label: OP_NAMES[o] ?? o }))}
                  />
                  <Segmented
                    label="mapping"
                    value={chartMapping}
                    onChange={setMapping}
                    options={[
                      { value: "identity", label: "identity" },
                      { value: "rotate90", label: "rotate 90°" },
                    ]}
                  />
                </div>
              </div>
              {scaling.error ? (
                <ErrorState error={scaling.error} />
              ) : scaling.data && scaling.data.points.length > 0 ? (
                <ScalingChart points={scaling.data.points} metric="ns_per_px" />
              ) : scaling.loading ? (
                <Loading />
              ) : (
                <EmptyState title="No stored results for this conversion and mapping" />
              )}
              {summary.data.best_speedups_vs_row_major.length > 0 && (
                <Panel title="Largest speedups over row-major (within one run)">
                  <ul className="grid gap-1 text-[13px] sm:grid-cols-2">
                    {summary.data.best_speedups_vs_row_major.map((b) => (
                      <li key={`${b.op}-${b.mapping}`} className="flex flex-wrap items-baseline gap-x-2">
                        <span className="text-ink-2">
                          {OP_NAMES[b.op] ?? b.op}, {b.mapping}:
                        </span>
                        <Link to={`/experiments/${b.experiment_id}`} className="num text-accent hover:underline">
                          {strategyName(b.label)} {fmtNum(b.speedup, 2)}×
                        </Link>
                        <span className="num text-muted">at {sizeLabel(b.width, b.height)}</span>
                      </li>
                    ))}
                  </ul>
                </Panel>
              )}
            </div>
          )
        )}
      </section>

      {caps.data && (
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <Panel title="Traversal strategies">
            <ul className="space-y-2 text-[13px]">
              {caps.data.strategies.map((s) => (
                <li key={s.value}>
                  <span className="font-medium text-ink">{s.label}</span>
                  <span className="block text-ink-2">{STRATEGY_HELP[s.value]}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Conversions">
            <ul className="space-y-1.5 text-[13px]">
              {caps.data.operations.map((o) => (
                <li key={o.value} className="flex gap-2">
                  <span className="num w-20 shrink-0 text-ink-2">{o.value}</span>
                  <span>{o.label}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted">
              All strategies run the same inlined per-pixel kernel; outputs are checked bit-for-bit against the row-major
              baseline in every run.
            </p>
          </Panel>
        </div>
      )}
    </>
  );
}
