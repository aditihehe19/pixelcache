import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ErrorBar,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CacheRow, ScalingPoint, VariantResult } from "../api/types";
import { fmtNum } from "../lib/format";
import { strategyColor, strategyName } from "../lib/strategies";
import { SourceTag } from "./ui";

const AXIS = { stroke: "var(--line-strong)", tick: { fill: "var(--ink-2)", fontSize: 11 } };

export function ChartFrame({
  title,
  subtitle,
  source,
  height = 260,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  source: "measured" | "simulated" | "estimate";
  height?: number;
  children: ReactNode;
}) {
  return (
    <figure className="rounded-md border border-line bg-surface p-3" aria-label={title}>
      <figcaption className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[13px] font-semibold text-ink">{title}</p>
          {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
        </div>
        <SourceTag kind={source} />
      </figcaption>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {children as React.ReactElement}
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

function barHeight(n: number): number {
  return Math.max(150, 46 + n * 34);
}

/** Median time per run with interquartile whiskers, one bar per variant. */
export function RuntimeChart({ results }: { results: VariantResult[] }) {
  const data = results.map((r) => ({
    name: strategyName(r.label),
    label: r.label,
    median: r.median_ms,
    err: [r.median_ms - r.p25_ms, r.p75_ms - r.median_ms],
  }));
  return (
    <ChartFrame
      title="Runtime per traversal"
      subtitle={`median time per run (ms); whiskers: interquartile range of ${results[0]?.reps ?? 0} repetitions`}
      source="measured"
      height={barHeight(data.length)}
    >
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 18 }}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" {...AXIS} label={{ value: "milliseconds", position: "insideBottom", offset: -10, fill: "var(--ink-2)", fontSize: 11 }} />
        <YAxis type="category" dataKey="name" width={130} {...AXIS} />
        <Tooltip formatter={(v: unknown) => [`${fmtNum(Number(v), 4)} ms`, "median"]} />
        <Bar dataKey="median" isAnimationActive={false} barSize={18}>
          {data.map((d) => (
            <Cell key={d.label} fill={strategyColor(d.label)} />
          ))}
          <ErrorBar dataKey="err" direction="x" width={5} strokeWidth={1.4} stroke="var(--ink)" />
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

export function ThroughputChart({ results }: { results: VariantResult[] }) {
  const data = results.map((r) => ({ name: strategyName(r.label), label: r.label, v: r.mpix_per_s }));
  return (
    <ChartFrame title="Throughput" subtitle="megapixels per second (from the median run time)" source="measured" height={barHeight(data.length)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 18 }}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" {...AXIS} label={{ value: "Mpixel/s", position: "insideBottom", offset: -10, fill: "var(--ink-2)", fontSize: 11 }} />
        <YAxis type="category" dataKey="name" width={130} {...AXIS} />
        <Tooltip formatter={(v: unknown) => [`${fmtNum(Number(v), 1)} Mpix/s`, "throughput"]} />
        <Bar dataKey="v" isAnimationActive={false} barSize={18}>
          {data.map((d) => (
            <Cell key={d.label} fill={strategyColor(d.label)} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

export function SpeedupChart({ results }: { results: VariantResult[] }) {
  const data = results
    .filter((r) => r.speedup_vs_row_major !== null)
    .map((r) => ({ name: strategyName(r.label), label: r.label, v: r.speedup_vs_row_major as number }));
  return (
    <ChartFrame
      title="Speedup relative to row-major"
      subtitle="ratio of medians within this run (> 1 is faster than the baseline)"
      source="measured"
      height={barHeight(data.length)}
    >
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 18 }}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" {...AXIS} label={{ value: "× row-major", position: "insideBottom", offset: -10, fill: "var(--ink-2)", fontSize: 11 }} />
        <YAxis type="category" dataKey="name" width={130} {...AXIS} />
        <ReferenceLine x={1} stroke="var(--ink-2)" strokeDasharray="4 3" />
        <Tooltip formatter={(v: unknown) => [`${fmtNum(Number(v), 2)}×`, "speedup"]} />
        <Bar dataKey="v" isAnimationActive={false} barSize={18}>
          {data.map((d) => (
            <Cell key={d.label} fill={strategyColor(d.label)} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

export function CyclesChart({ results }: { results: VariantResult[] }) {
  const data = results
    .filter((r) => r.est_core_cycles_per_px !== null)
    .map((r) => ({ name: strategyName(r.label), label: r.label, v: r.est_core_cycles_per_px as number }));
  return (
    <ChartFrame
      title="Core cycles per pixel"
      subtitle="ns/pixel × effective clock from the IMUL probe; hardware cycle counters were unavailable"
      source="estimate"
      height={barHeight(data.length)}
    >
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 18 }}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" {...AXIS} label={{ value: "cycles / pixel", position: "insideBottom", offset: -10, fill: "var(--ink-2)", fontSize: 11 }} />
        <YAxis type="category" dataKey="name" width={130} {...AXIS} />
        <Tooltip formatter={(v: unknown) => [`${fmtNum(Number(v), 1)} cycles`, "estimate"]} />
        <Bar dataKey="v" isAnimationActive={false} barSize={18}>
          {data.map((d) => (
            <Cell key={d.label} fill={strategyColor(d.label)} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

/** Every repetition of every variant: shows variability and drift across rounds. */
export function RepetitionsChart({ results }: { results: VariantResult[] }) {
  return (
    <ChartFrame
      title="Individual repetitions"
      subtitle="time of each run in round order (rounds are shuffled across variants)"
      source="measured"
      height={260}
    >
      <ScatterChart margin={{ left: 8, right: 16, top: 4, bottom: 18 }}>
        <CartesianGrid />
        <XAxis type="number" dataKey="rep" name="round" allowDecimals={false} {...AXIS}
          label={{ value: "repetition round", position: "insideBottom", offset: -10, fill: "var(--ink-2)", fontSize: 11 }} />
        <YAxis type="number" dataKey="ms" name="ms per run" {...AXIS} width={64}
          label={{ value: "ms per run", angle: -90, position: "insideLeft", fill: "var(--ink-2)", fontSize: 11 }} />
        <Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={(v: unknown) => fmtNum(Number(v), 4)} />
        <Legend verticalAlign="top" height={24} iconSize={9} wrapperStyle={{ fontSize: 11 }} />
        {results.map((r) => (
          <Scatter
            key={r.label}
            name={strategyName(r.label)}
            data={r.repetitions.map((x) => ({ rep: x.rep, ms: x.ms_per_run }))}
            fill={strategyColor(r.label)}
            isAnimationActive={false}
          />
        ))}
      </ScatterChart>
    </ChartFrame>
  );
}

const COMPULSORY = 15 / 64;

/** Simulated misses per pixel per cache level, grouped by variant. */
export function CacheMissChart({ rows, metric = "misses_per_px" }: { rows: Pick<CacheRow, "label" | "level" | "misses_per_px" | "miss_rate">[]; metric?: "misses_per_px" | "miss_rate" }) {
  const levels = ["L1D", "L2", "L3"].filter((l) => rows.some((r) => r.level === l));
  const labels = [...new Set(rows.map((r) => r.label))];
  const data = levels.map((lv) => {
    const point: Record<string, string | number> = { level: lv };
    for (const lab of labels) {
      const row = rows.find((r) => r.level === lv && r.label === lab);
      if (row) point[lab] = row[metric];
    }
    return point;
  });
  return (
    <ChartFrame
      title={metric === "misses_per_px" ? "Cache misses per pixel by level" : "Miss rate by level"}
      subtitle={
        metric === "misses_per_px"
          ? "dashed line: compulsory 15/64 (3 B read + 12 B written per pixel, 64 B lines)"
          : "misses / demand accesses at that level"
      }
      source="simulated"
      height={280}
    >
      <BarChart data={data} margin={{ left: 8, right: 16, top: 4, bottom: 18 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="level" {...AXIS} label={{ value: "cache level", position: "insideBottom", offset: -10, fill: "var(--ink-2)", fontSize: 11 }} />
        <YAxis {...AXIS} width={56} label={{ value: metric === "misses_per_px" ? "misses / pixel" : "miss rate", angle: -90, position: "insideLeft", fill: "var(--ink-2)", fontSize: 11 }} />
        {metric === "misses_per_px" && <ReferenceLine y={COMPULSORY} stroke="var(--ink-2)" strokeDasharray="4 3" />}
        <Tooltip formatter={(v: unknown, name: unknown) => [fmtNum(Number(v), 4), strategyName(String(name))]} />
        <Legend verticalAlign="top" height={24} iconSize={9} wrapperStyle={{ fontSize: 11 }} formatter={(v: string) => strategyName(v)} />
        {labels.map((lab) => (
          <Bar key={lab} dataKey={lab} fill={strategyColor(lab)} isAnimationActive={false} />
        ))}
      </BarChart>
    </ChartFrame>
  );
}

/** ns/pixel (or Mpix/s) against image size across stored experiments. */
export function ScalingChart({ points, metric, height = 280 }: { points: ScalingPoint[]; metric: "ns_per_px" | "mpix_per_s"; height?: number }) {
  const labels = [...new Set(points.map((p) => p.label))];
  const sizes = [...new Set(points.map((p) => p.pixels))].sort((a, b) => a - b);
  const data = sizes.map((px) => {
    const row: Record<string, number> = { px: px / 1e6 };
    for (const p of points.filter((q) => q.pixels === px)) row[p.label] = p[metric];
    return row;
  });
  return (
    <ChartFrame
      title={metric === "ns_per_px" ? "Time per pixel vs image size" : "Throughput vs image size"}
      subtitle="median over stored results at each size; x axis logarithmic"
      source="measured"
      height={height}
    >
      <LineChart data={data} margin={{ left: 8, right: 16, top: 4, bottom: 18 }}>
        <CartesianGrid />
        <XAxis dataKey="px" type="number" scale="log" domain={["auto", "auto"]} {...AXIS}
          tickFormatter={(v: number) => (v >= 1 ? `${fmtNum(Number(v), 1)}` : `${fmtNum(Number(v), 2)}`)}
          label={{ value: "megapixels", position: "insideBottom", offset: -10, fill: "var(--ink-2)", fontSize: 11 }} />
        <YAxis {...AXIS} width={56} label={{ value: metric === "ns_per_px" ? "ns / pixel" : "Mpixel/s", angle: -90, position: "insideLeft", fill: "var(--ink-2)", fontSize: 11 }} />
        <Tooltip formatter={(v: unknown, name: unknown) => [fmtNum(Number(v), 3), strategyName(String(name))]} labelFormatter={(v: unknown) => `${fmtNum(Number(v), 2)} MP`} />
        <Legend verticalAlign="top" height={24} iconSize={9} wrapperStyle={{ fontSize: 11 }} formatter={(v: string) => strategyName(v)} />
        {labels.map((lab) => (
          <Line key={lab} dataKey={lab} stroke={strategyColor(lab)} strokeWidth={2} dot={{ r: 3 }} connectNulls isAnimationActive={false} />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

/** Time per pixel against tile edge for square tiles (from any set of tiled results). */
export function TileSizeChart({ results }: { results: VariantResult[] }) {
  const tiles = results
    .filter((r) => r.strategy === "tiled" && r.tile_w === r.tile_h)
    .sort((a, b) => a.tile_w - b.tile_w)
    .map((r) => ({ tile: r.tile_w, ns: r.ns_per_px }));
  const row = results.find((r) => r.label === "row_major");
  return (
    <ChartFrame title="Tile size vs time per pixel" subtitle="square tiles in this run; dashed: row-major" source="measured">
      <LineChart data={tiles} margin={{ left: 8, right: 16, top: 4, bottom: 18 }}>
        <CartesianGrid />
        <XAxis dataKey="tile" type="number" scale="log" domain={["auto", "auto"]} {...AXIS}
          label={{ value: "tile edge (pixels, log)", position: "insideBottom", offset: -10, fill: "var(--ink-2)", fontSize: 11 }} />
        <YAxis {...AXIS} width={56} label={{ value: "ns / pixel", angle: -90, position: "insideLeft", fill: "var(--ink-2)", fontSize: 11 }} />
        {row && <ReferenceLine y={row.ns_per_px} stroke={strategyColor("row_major")} strokeDasharray="4 3" />}
        <Tooltip formatter={(v: unknown) => [`${fmtNum(Number(v), 3)} ns/px`, "tiled"]} labelFormatter={(v: unknown) => `${String(v)}×${String(v)}`} />
        <Line dataKey="ns" stroke="#eb6834" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
      </LineChart>
    </ChartFrame>
  );
}
