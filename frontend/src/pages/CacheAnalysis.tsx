import { FlaskConical } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import { CacheMissChart } from "../components/charts";
import { Button, EmptyState, ErrorState, KeyValue, Loading, Notice, PageHeader, Panel, SourceTag, inputCls } from "../components/ui";
import { fmtBytes, fmtDate } from "../lib/format";
import { OP_NAMES } from "../lib/strategies";
import { useApi } from "../lib/useApi";
import { CacheTable } from "./ExperimentResults";

export default function CacheAnalysis() {
  const [selected, setSelected] = useState<string>();
  const cache = useApi(() => api.cache(selected), [selected]);
  const sys = useApi(() => api.systemInfo(), []);
  const d = cache.data;

  return (
    <>
      <PageHeader
        title="Cache analysis"
        subtitle="Results of the trace-driven cache model. It replays the exact address stream of each traversal; it does not read the processor's performance counters."
        actions={
          <Link to="/experiments/new">
            <Button>
              <FlaskConical size={14} /> New simulated run
            </Button>
          </Link>
        }
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="What the model is" aside={<SourceTag kind="simulated" />}>
          <ul className="list-disc space-y-1.5 pl-5 text-[13px] text-ink-2">
            <li>
              Three set-associative data-cache levels with <b className="text-ink">true LRU</b> replacement, <b className="text-ink">write-back</b>,{" "}
              <b className="text-ink">write-allocate</b>, non-inclusive, 64-byte lines.
            </li>
            <li>Each pixel issues a 3-byte read (RGB888 input) and a 12-byte write (float32 × 3 output) at the addresses the real traversal code produces.</li>
            <li>
              <b className="text-ink">Not modelled:</b> hardware prefetchers, physical-address indexing and L3 slice hashing, TLBs (CPUID leaf 0x18 is masked on
              the development machine), code, stack and lookup-table accesses.
            </li>
            <li>So it explains capacity and conflict (associativity) misses well, and cannot show latency that prefetchers hide.</li>
            <li>Configurable through the workbench: image size, mapping, strategies and tiles, and optionally L1/L2/L3 size and associativity.</li>
          </ul>
        </Panel>
        <Panel title="This machine (CPUID leaf 4)">
          {sys.data?.available ? (
            <KeyValue
              rows={[
                ...sys.data.caches
                  .filter((c) => c.source.startsWith("cpuid"))
                  .map((c) => [`L${c.level} ${c.type}`, `${fmtBytes(c.size_bytes)} · ${c.ways}-way · ${c.sets} sets · ${c.line_bytes} B`] as [string, string]),
                ["TLB geometry", sys.data.tlbs?.value ? "reported" : "unavailable"],
              ]}
            />
          ) : sys.error ? (
            <ErrorState error={sys.error} />
          ) : sys.data ? (
            <p className="text-ink-2">{sys.data.reason}</p>
          ) : (
            <Loading />
          )}
        </Panel>
      </div>

      <div className="mt-6 space-y-4">
        {cache.error ? (
          <ErrorState error={cache.error} onRetry={cache.reload} />
        ) : !d ? (
          <Loading />
        ) : d.experiments.length === 0 ? (
          <EmptyState
            title="No simulated runs stored yet"
            action={
              <Link to="/experiments/new">
                <Button variant="primary">Open the workbench</Button>
              </Link>
            }
          >
            Enable “Simulate cache behaviour” for an experiment. Comparing a power-of-two size (2048×2048) with a nearby one (2000×2000) under the rotated
            mapping shows associativity conflicts clearly.
          </EmptyState>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="sim-exp" className="text-[13px] text-ink-2">
                Simulated experiment
              </label>
              <select id="sim-exp" className={`${inputCls.replace("w-full", "")} w-auto max-w-full`} value={d.selected ?? ""} onChange={(e) => setSelected(e.target.value)}>
                {d.experiments.map((e) => (
                  <option key={e.experiment_id} value={e.experiment_id}>
                    {e.experiment_id} · {OP_NAMES[e.op] ?? e.op} {e.mapping} {e.width}×{e.height} · {e.geometry_source} · {fmtDate(e.created_at)}
                  </option>
                ))}
              </select>
              {d.selected && (
                <Link to={`/experiments/${d.selected}`} className="text-[13px] text-accent hover:underline">
                  open experiment
                </Link>
              )}
            </div>
            {d.geometry && (
              <Notice>
                Geometry <span className="num">{d.geometry.source}</span>:{" "}
                {d.geometry.levels?.map((l) => `${l.name} ${fmtBytes(l.size_bytes)} ${l.ways}-way`).join(" · ")}. {d.source_note}
              </Notice>
            )}
            {d.rows.length > 0 && (
              <>
                <div className="grid gap-4 lg:grid-cols-2">
                  <CacheMissChart rows={d.rows} metric="misses_per_px" />
                  <CacheMissChart rows={d.rows} metric="miss_rate" />
                </div>
                <Panel title="Hits and misses" aside={<SourceTag kind="simulated" />}>
                  <CacheTable rows={d.rows} />
                </Panel>
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}
