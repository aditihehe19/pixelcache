import { Play, Plus, Upload, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { ApiError, api } from "../api/client";
import type { Capabilities, ImageSource, StrategyName } from "../api/types";
import {
  Button,
  Checkbox,
  ErrorState,
  Field,
  KeyValue,
  Loading,
  NumberInput,
  Notice,
  PageHeader,
  Panel,
  Segmented,
  cx,
  inputCls,
} from "../components/ui";
import { buildConfig, engineTokens, imageDims, initialForm, validate, type FormState } from "../lib/experimentForm";
import { fmtBytes, fmtNum } from "../lib/format";
import { OP_NAMES, STRATEGY_HELP, strategyName } from "../lib/strategies";
import { useApi } from "../lib/useApi";

const SIZE_PRESETS: [number, number][] = [
  [256, 256],
  [512, 512],
  [1024, 1024],
  [2000, 2000],
  [2048, 2048],
  [1920, 1080],
  [4096, 4096],
];
const TILE_PRESETS = [8, 16, 32, 64, 128, 256];
const NON_TILED: StrategyName[] = ["row_major", "column_major", "morton", "adaptive_model", "adaptive_calib"];

export default function Workbench() {
  const caps = useApi(() => api.capabilities(), []);
  const sys = useApi(() => api.systemInfo(), []);
  if (caps.error) return <ErrorState error={caps.error} onRetry={caps.reload} />;
  if (!caps.data) return <Loading label="Loading engine capabilities" />;
  return <WorkbenchForm caps={caps.data} l3Bytes={sys.data?.caches.find((c) => c.level === 3 && c.source.startsWith("cpuid"))?.size_bytes} />;
}

export function WorkbenchForm({ caps, l3Bytes }: { caps: Capabilities; l3Bytes?: number }) {
  const navigate = useNavigate();
  const [s, setS] = useState<FormState>(initialForm);
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<ApiError>();
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<ApiError>();
  const [newTile, setNewTile] = useState<{ w: number | ""; h: number | "" }>({ w: 64, h: 64 });
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setS((x) => ({ ...x, [k]: v }));

  const limits = caps.limits;
  const errors = useMemo(() => validate(s, limits), [s, limits]);
  const valid = Object.keys(errors).length === 0;
  const dims = imageDims(s);
  const pixels = dims ? dims.w * dims.h : 0;
  const workingSet = pixels * 15;
  const validationPossible = pixels > 0 && pixels <= limits.max_validation_pixels && s.op !== "index_only";
  const show = (k: string) => (touched ? errors[k] : undefined);

  async function onUpload(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    setUploadError(undefined);
    try {
      const up = await api.upload(file);
      setS((x) => ({ ...x, upload: up }));
    } catch (e) {
      setUploadError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      setUploading(false);
    }
  }

  async function submit() {
    setTouched(true);
    if (!valid || !caps.engine_available) return;
    setSubmitting(true);
    setSubmitError(undefined);
    try {
      // Send the user's choice unchanged: when the image is too large the backend
      // records the precise reason instead of "disabled by the user".
      const cfg = buildConfig(s);
      const job = s.mode === "single" ? await api.createExperiment(cfg) : await api.compare(cfg);
      navigate(`/experiments/${job.id}`);
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e : new ApiError(0, String(e)));
      setSubmitting(false);
    }
  }

  const toggleCompare = (v: StrategyName) =>
    set("compare", s.compare.includes(v) ? s.compare.filter((x) => x !== v) : [...s.compare, v]);
  const addTile = (w: number, h: number) => {
    if (!s.compareTiles.some((t) => t.w === w && t.h === h)) set("compareTiles", [...s.compareTiles, { w, h }]);
  };

  return (
    <>
      <PageHeader
        title="Experiment workbench"
        subtitle="Configure a run of the C++ engine. A comparison times all selected strategies in one interleaved group on the same input, so their numbers are directly comparable."
      />
      {!caps.engine_available && (
        <div className="mb-4">
          <Notice tone="warn">
            The benchmark binary is not built, so experiments cannot run. Build it with{" "}
            <span className="num">cmake -S . -B build -G Ninja && cmake --build build</span> and restart the backend.
          </Notice>
        </div>
      )}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <form
          className="space-y-5"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <Panel title="1 · Workload">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Conversion">
                <Segmented
                  label="Conversion"
                  value={s.op}
                  onChange={(v) => set("op", v)}
                  options={caps.operations.map((o) => ({ value: o.value, label: OP_NAMES[o.value] ?? o.value }))}
                />
              </Field>
              <Field
                label="Output mapping"
                hint={s.mapping === "rotate90" ? "Output rotated 90°: writes become strided by one output row (transpose-like)." : "Output written in the same order as the input."}
              >
                <Segmented
                  label="Output mapping"
                  value={s.mapping}
                  onChange={(v) => set("mapping", v)}
                  options={[
                    { value: "identity", label: "identity" },
                    { value: "rotate90", label: "convert + rotate 90°" },
                  ]}
                />
              </Field>
              <Field label="Input image" htmlFor="image-source">
                <select
                  id="image-source"
                  className={inputCls}
                  value={s.imageSource}
                  onChange={(e) => set("imageSource", e.target.value as ImageSource)}
                >
                  {caps.image_sources.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </Field>
              {s.imageSource === "upload" ? (
                <Field
                  label="Image file"
                  hint={`PNG, JPEG, BMP, PPM or TIFF up to ${limits.max_upload_mb} MB; decoded on the server.`}
                  error={show("upload")}
                >
                  <label className={cx(inputCls, "flex cursor-pointer items-center gap-2")}>
                    <Upload size={14} />
                    <span className="truncate">{uploading ? "Uploading…" : s.upload ? s.upload.original_name : "Choose a file"}</span>
                    <input type="file" className="sr-only" accept=".png,.jpg,.jpeg,.bmp,.ppm,.tif,.tiff" onChange={(e) => void onUpload(e.target.files?.[0])} />
                  </label>
                  {s.upload && (
                    <p className="num text-xs text-ink-2">
                      {s.upload.width}×{s.upload.height} · sha256 {s.upload.sha256.slice(0, 12)}…
                    </p>
                  )}
                  {uploadError && <ErrorState error={uploadError} />}
                </Field>
              ) : (
                <Field label="Image size (pixels)" error={show("width") ?? show("height")}>
                  <div className="flex items-center gap-2">
                    <NumberInput ariaLabel="width" value={s.width} onChange={(v) => set("width", v)} min={limits.min_edge} max={limits.max_edge} invalid={!!show("width")} />
                    <span className="text-muted">×</span>
                    <NumberInput ariaLabel="height" value={s.height} onChange={(v) => set("height", v)} min={limits.min_edge} max={limits.max_edge} invalid={!!show("height")} />
                  </div>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {SIZE_PRESETS.map(([w, h]) => (
                      <button
                        type="button"
                        key={`${w}x${h}`}
                        onClick={() => setS((x) => ({ ...x, width: w, height: h }))}
                        className={cx(
                          "num rounded border px-1.5 py-0.5 text-xs",
                          s.width === w && s.height === h ? "border-accent text-accent" : "border-line text-ink-2 hover:border-line-strong",
                        )}
                      >
                        {w}×{h}
                      </button>
                    ))}
                  </div>
                </Field>
              )}
            </div>
          </Panel>

          <Panel title="2 · Traversal">
            <div className="mb-4">
              <Segmented
                label="Experiment type"
                value={s.mode}
                onChange={(v) => set("mode", v)}
                options={[
                  { value: "compare", label: "Compare strategies" },
                  { value: "single", label: "Single strategy" },
                ]}
              />
            </div>
            {s.mode === "single" ? (
              <div className="grid gap-4 md:grid-cols-2">
                <fieldset className="space-y-1.5">
                  <legend className="mb-1 text-[13px] font-medium">Strategy</legend>
                  {caps.strategies.map((o) => (
                    <label key={o.value} className="flex cursor-pointer items-start gap-2 text-[13px]">
                      <input type="radio" name="single-strategy" className="mt-0.5 accent-[var(--accent)]" checked={s.single === o.value} onChange={() => set("single", o.value)} />
                      <span>
                        {o.label}
                        <span className="block text-xs text-muted">{STRATEGY_HELP[o.value]}</span>
                      </span>
                    </label>
                  ))}
                </fieldset>
                {s.single === "tiled" && (
                  <Field label="Tile size (width × height)" error={show("tile")} hint="Edge tiles are clipped when the image is not a multiple of the tile.">
                    <div className="flex items-center gap-2">
                      <NumberInput ariaLabel="tile width" value={s.singleTile.w} onChange={(v) => set("singleTile", { ...s.singleTile, w: v })} invalid={!!show("tile")} />
                      <span className="text-muted">×</span>
                      <NumberInput ariaLabel="tile height" value={s.singleTile.h} onChange={(v) => set("singleTile", { ...s.singleTile, h: v })} invalid={!!show("tile")} />
                    </div>
                  </Field>
                )}
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                <fieldset className="space-y-2">
                  <legend className="mb-1 text-[13px] font-medium">Strategies</legend>
                  {NON_TILED.map((v) => (
                    <Checkbox key={v} checked={s.compare.includes(v)} onChange={() => toggleCompare(v)} description={STRATEGY_HELP[v]}>
                      {caps.strategies.find((o) => o.value === v)?.label ?? v}
                    </Checkbox>
                  ))}
                </fieldset>
                <div className="space-y-2">
                  <p className="text-[13px] font-medium">Tiled variants</p>
                  <div className="flex flex-wrap gap-1.5">
                    {s.compareTiles.length === 0 && <span className="text-xs text-muted">none</span>}
                    {s.compareTiles.map((t) => (
                      <span key={`${t.w}x${t.h}`} className="num inline-flex items-center gap-1 rounded border border-line-strong bg-sunken px-2 py-0.5 text-xs">
                        {t.w}×{t.h}
                        <button
                          type="button"
                          aria-label={`remove tile ${t.w}x${t.h}`}
                          onClick={() => set("compareTiles", s.compareTiles.filter((x) => x !== t))}
                          className="text-muted hover:text-err"
                        >
                          <X size={12} />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {TILE_PRESETS.map((n) => (
                      <button key={n} type="button" onClick={() => addTile(n, n)} className="num rounded border border-line px-1.5 py-0.5 text-xs text-ink-2 hover:border-line-strong">
                        + {n}×{n}
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <NumberInput ariaLabel="new tile width" value={newTile.w} onChange={(v) => setNewTile({ ...newTile, w: v })} />
                    <span className="text-muted">×</span>
                    <NumberInput ariaLabel="new tile height" value={newTile.h} onChange={(v) => setNewTile({ ...newTile, h: v })} />
                    <Button type="button" onClick={() => newTile.w !== "" && newTile.h !== "" && addTile(newTile.w, newTile.h)}>
                      <Plus size={14} /> Add
                    </Button>
                  </div>
                  <p className="text-xs text-muted">Row-major is always included as the baseline for speedups.</p>
                </div>
              </div>
            )}
            {show("strategies") && (
              <p role="alert" className="mt-3 text-xs text-err">
                {show("strategies")}
              </p>
            )}
          </Panel>

          <Panel title="3 · Measurement">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Repetitions per strategy" error={show("reps")} hint={`${limits.min_reps}–${limits.max_reps}; the median and interquartile range are reported.`}>
                <NumberInput ariaLabel="repetitions" value={s.reps} onChange={(v) => set("reps", v)} min={limits.min_reps} max={limits.max_reps} invalid={!!show("reps")} />
              </Field>
              <Field label="Cache state before each run" hint={s.condition === "flushed" ? "CLFLUSH of every input and output line before each timed run (TLBs are not flushed)." : "No flush: buffers were touched by the preceding run."}>
                <Segmented
                  label="Cache state"
                  value={s.condition}
                  onChange={(v) => set("condition", v)}
                  options={[
                    { value: "warm", label: "warm" },
                    { value: "flushed", label: "flushed" },
                  ]}
                />
              </Field>
              <div className="space-y-2 md:col-span-2">
                <Checkbox
                  checked={s.validateReference && validationPossible}
                  disabled={!validationPossible}
                  onChange={(v) => set("validateReference", v)}
                  description={
                    validationPossible
                      ? "Compares the conversion against a float64 NumPy reference and OpenCV on this exact image, outside the timed run."
                      : s.op === "index_only"
                        ? "index_only produces no pixels to validate."
                        : `Only for images up to ${limits.max_validation_pixels.toLocaleString()} pixels. The bit-exact output check against row-major always runs.`
                  }
                >
                  Reference validation
                </Checkbox>
              </div>
            </div>
          </Panel>

          <Panel title="4 · Cache model (optional)">
            <div className="space-y-3">
              <Checkbox
                checked={s.cacheSim}
                onChange={(v) => set("cacheSim", v)}
                disabled={!caps.simulator_available}
                description="Replays each strategy's exact address stream through the trace-driven LRU model (cachevision_sim). Results are simulated, not hardware counters."
              >
                Simulate cache behaviour for the same image and tiles
              </Checkbox>
              {show("cacheSim") && <p role="alert" className="text-xs text-err">{show("cacheSim")}</p>}
              {s.cacheSim && (
                <>
                  <Checkbox checked={s.customGeometry} onChange={(v) => set("customGeometry", v)} description="Default: the geometry this CPU reports through CPUID. Line size is fixed at 64 bytes.">
                    Use a custom cache geometry ("what-if")
                  </Checkbox>
                  {s.customGeometry && (
                    <div className="grid gap-3 sm:grid-cols-3">
                      {(["l1", "l2", "l3"] as const).map((k) => (
                        <Field key={k} label={`${k.toUpperCase()} size (KiB) / ways`} error={show(k)}>
                          <div className="flex items-center gap-1.5">
                            <NumberInput ariaLabel={`${k} KiB`} value={s[k].kib} onChange={(v) => set(k, { ...s[k], kib: v })} invalid={!!show(k)} />
                            <NumberInput ariaLabel={`${k} ways`} value={s[k].ways} onChange={(v) => set(k, { ...s[k], ways: v })} invalid={!!show(k)} />
                          </div>
                        </Field>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </Panel>

          <Panel title="5 · Name (optional)">
            <input className={inputCls} maxLength={120} placeholder="generated from the configuration if empty" value={s.name} onChange={(e) => set("name", e.target.value)} aria-label="Experiment name" />
          </Panel>

          {submitError && <ErrorState error={submitError} />}
          <div className="flex items-center gap-3">
            <Button type="submit" variant="primary" disabled={submitting || !caps.engine_available || (touched && !valid)}>
              <Play size={14} /> {submitting ? "Submitting…" : s.mode === "single" ? "Run experiment" : "Run comparison"}
            </Button>
            {touched && !valid && <span className="text-xs text-err">Fix the highlighted fields first.</span>}
          </div>
        </form>

        <aside className="space-y-4 xl:sticky xl:top-6 xl:self-start">
          <Panel title="Summary">
            <KeyValue
              rows={[
                ["conversion", `${OP_NAMES[s.op]} · ${s.mapping}`],
                ["image", dims ? `${dims.w}×${dims.h} (${(pixels / 1e6).toFixed(2)} MP)` : "n/a"],
                ["working set", dims ? `${fmtBytes(workingSet)} (3 B in + 12 B out per pixel)` : "n/a"],
                ["vs last-level cache", l3Bytes && dims ? (workingSet <= l3Bytes ? `fits in ${fmtBytes(l3Bytes)} L3` : `exceeds ${fmtBytes(l3Bytes)} L3 (DRAM-bound)`) : "unknown"],
                ["variants", engineTokens(s).map((t) => strategyName(t.replace(":", "_"))).join(", ")],
                ["repetitions", s.reps === "" ? "n/a" : `${s.reps} each, interleaved`],
                ["cache model", s.cacheSim ? (s.customGeometry ? "custom geometry" : "CPUID geometry") : "off"],
                ["est. timed runs", s.reps === "" ? "n/a" : fmtNum(engineTokens(s).length * Number(s.reps), 0)],
              ]}
              mono={false}
            />
          </Panel>
          <Panel title="Engine arguments">
            <p className="mb-2 text-xs text-muted">What the backend passes to the engine (paths are filled in server-side).</p>
            <pre className="num overflow-x-auto whitespace-pre-wrap break-all rounded bg-sunken p-2 text-[11.5px] leading-relaxed text-ink">
              {[
                "cachevision_bench_native --single",
                `--op ${s.op} --mapping ${s.mapping}`,
                `--variant ${engineTokens(s).join(",")}`,
                `--size ${dims ? `${dims.w}x${dims.h}` : "?"} --image ${s.imageSource === "upload" || s.imageSource === "photo" ? "photo" : s.imageSource}`,
                `--reps ${s.reps} --condition ${s.condition}`,
              ].join("\n  ")}
            </pre>
          </Panel>
          <SuitePanel />
        </aside>
      </div>
    </>
  );
}

function SuitePanel() {
  const navigate = useNavigate();
  const suites = useApi(() => api.suites(), []);
  const [suite, setSuite] = useState("overhead");
  const [quick, setQuick] = useState(true);
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);
  const info = suites.data?.find((x) => x.name === suite);
  return (
    <Panel title="Benchmark suites">
      <p className="mb-3 text-xs text-muted">
        Predefined suites from <span className="num">benchmarks/benchmark_config.json</span>, run by the engine's own suite driver.
      </p>
      {suites.error ? (
        <ErrorState error={suites.error} />
      ) : !suites.data ? (
        <Loading />
      ) : (
        <div className="space-y-2">
          <select aria-label="Suite" className={inputCls} value={suite} onChange={(e) => setSuite(e.target.value)}>
            {suites.data.map((x) => (
              <option key={x.name} value={x.name}>
                {x.name}
              </option>
            ))}
          </select>
          {info && (
            <p className="text-xs text-ink-2">
              {info.description}. <span className="num">{quick ? info.quick_groups : info.groups}</span> groups ×{" "}
              <span className="num">{info.variants.length}</span> variants.
            </p>
          )}
          <Checkbox checked={quick} onChange={setQuick} description="Sizes up to 2048×2048, at most 3 repetitions. Full suites can take tens of minutes.">
            Quick mode
          </Checkbox>
          {error && <ErrorState error={error} />}
          <Button
            disabled={busy || (info ? (quick ? info.quick_groups : info.groups) === 0 : true)}
            onClick={async () => {
              setBusy(true);
              setError(undefined);
              try {
                const job = await api.runSuite(suite, quick);
                navigate(`/experiments/${job.id}`);
              } catch (e) {
                setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
                setBusy(false);
              }
            }}
          >
            <Play size={14} /> Run suite
          </Button>
        </div>
      )}
    </Panel>
  );
}
