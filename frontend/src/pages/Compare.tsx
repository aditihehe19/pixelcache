import { Link, useSearchParams } from "react-router";
import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, Legend, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { ChartFrame } from "../components/charts";
import { EmptyState, ErrorState, Loading, Notice, PageHeader, Panel, SourceTag, cx, tableCls, tdCls, thCls } from "../components/ui";
import { fmtMs, fmtNum } from "../lib/format";
import { OP_NAMES, strategyColor, strategyName } from "../lib/strategies";
import { useApi } from "../lib/useApi";

export default function Compare() {
  const [params] = useSearchParams();
  const ids = (params.get("ids") ?? "").split(",").filter((x) => /^[0-9a-f]{12}$/.test(x));
  const cmp = useApi(() => api.comparisons({ experiment_ids: ids }), [ids.join(",")], { enabled: ids.length > 0 });

  if (ids.length === 0)
    return (
      <>
        <PageHeader title="Compare experiments" />
        <EmptyState title="No experiments selected">
          Select completed experiments in the <Link to="/history" className="text-accent hover:underline">history</Link> and choose “Compare selected”.
        </EmptyState>
      </>
    );
  if (cmp.error) return <ErrorState error={cmp.error} onRetry={cmp.reload} />;
  if (!cmp.data) return <Loading label="Loading measurements" />;
  const rows = cmp.data.rows;
  const data = rows.map((r) => ({
    key: `${r.experiment_id}:${r.label}`,
    name: `${strategyName(r.label)} · ${r.experiment_id.slice(0, 6)}`,
    label: r.label,
    ns: r.ns_per_px,
    err: [r.ns_per_px * (1 - r.p25_ms / r.median_ms), r.ns_per_px * (r.p75_ms / r.median_ms - 1)],
  }));

  return (
    <>
      <PageHeader title="Compare experiments" subtitle={`${ids.length} experiment${ids.length > 1 ? "s" : ""}, ${rows.length} measured variants.`} />
      <div className="space-y-4">
        {cmp.data.warnings.map((w) => (
          <Notice key={w} tone="warn">
            {w}
          </Notice>
        ))}
        {rows.length === 0 ? (
          <EmptyState title="These experiments have no stored measurements" />
        ) : (
          <>
            <ChartFrame title="Time per pixel by variant and run" subtitle="ns/pixel (normalises different image sizes); whiskers: interquartile range" source="measured" height={Math.max(180, 50 + rows.length * 26)}>
              <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 18 }}>
                <CartesianGrid horizontal={false} />
                <XAxis type="number" tick={{ fill: "var(--ink-2)", fontSize: 11 }} stroke="var(--line-strong)" label={{ value: "ns / pixel", position: "insideBottom", offset: -10, fill: "var(--ink-2)", fontSize: 11 }} />
                <YAxis type="category" dataKey="name" width={190} tick={{ fill: "var(--ink-2)", fontSize: 11 }} stroke="var(--line-strong)" />
                <Tooltip formatter={(v: unknown) => [`${fmtNum(Number(v), 3)} ns/px`, "median"]} />
                <Legend content={() => null} />
                <Bar dataKey="ns" isAnimationActive={false} barSize={14}>
                  {data.map((d) => (
                    <Cell key={d.key} fill={strategyColor(d.label)} />
                  ))}
                  <ErrorBar dataKey="err" direction="x" width={4} stroke="var(--ink)" />
                </Bar>
              </BarChart>
            </ChartFrame>
            <Panel title="Measurements" aside={<SourceTag kind="measured" />}>
              <div className="overflow-x-auto">
                <table className={tableCls}>
                  <thead>
                    <tr>
                      {["experiment", "conversion", "image", "input", "cache", "variant", "median", "ns/px", "CV %", "clock (GHz)", "speedup (same run)"].map((h) => (
                        <th key={h} className={thCls}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={`${r.experiment_id}-${r.label}`}>
                        <td className={cx(tdCls, "num")}>
                          <Link to={`/experiments/${r.experiment_id}`} className="text-accent hover:underline">
                            {r.experiment_id}
                          </Link>
                        </td>
                        <td className={tdCls}>
                          {OP_NAMES[r.op] ?? r.op} · {r.mapping}
                        </td>
                        <td className={cx(tdCls, "num")}>
                          {r.width}×{r.height}
                        </td>
                        <td className={tdCls}>{r.image_kind}</td>
                        <td className={tdCls}>{r.condition}</td>
                        <td className={tdCls}>{strategyName(r.label)}</td>
                        <td className={cx(tdCls, "num")}>{fmtMs(r.median_ms)}</td>
                        <td className={cx(tdCls, "num")}>{fmtNum(r.ns_per_px, 3)}</td>
                        <td className={cx(tdCls, "num", r.cv_pct > 5 && "text-warn")}>{fmtNum(r.cv_pct, 1)}</td>
                        <td className={cx(tdCls, "num")}>{fmtNum(r.core_ghz_probe, 2)}</td>
                        <td className={cx(tdCls, "num")}>{r.speedup_vs_row_major_same_run === null ? "n/a" : `${fmtNum(r.speedup_vs_row_major_same_run, 2)}×`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-xs text-muted">
                Speedups are only computed within a run, where row-major was timed in the same interleaved group. Across runs, compare ns/pixel and check the
                probed clock.
              </p>
            </Panel>
          </>
        )}
      </div>
    </>
  );
}
