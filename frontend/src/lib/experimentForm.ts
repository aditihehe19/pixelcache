// Workbench form model. Validation mirrors backend/app/schemas/experiment.py so
// users see problems before submitting; the backend re-validates everything.
import type { Capabilities, CacheCondition, ExperimentConfig, ImageSource, Mapping, Operation, StrategyName, StrategySpec, UploadOut } from "../api/types";

export interface Tile {
  w: number | "";
  h: number | "";
}

export interface CacheLevelInput {
  kib: number | "";
  ways: number | "";
}

export interface FormState {
  mode: "single" | "compare";
  name: string;
  op: Operation;
  mapping: Mapping;
  imageSource: ImageSource;
  width: number | "";
  height: number | "";
  upload: UploadOut | null;
  single: StrategyName;
  singleTile: Tile;
  compare: StrategyName[]; // non-tiled strategies selected for comparison
  compareTiles: { w: number; h: number }[];
  reps: number | "";
  condition: CacheCondition;
  cacheSim: boolean;
  customGeometry: boolean;
  l1: CacheLevelInput;
  l2: CacheLevelInput;
  l3: CacheLevelInput;
  validateReference: boolean;
}

export const initialForm: FormState = {
  mode: "compare",
  name: "",
  op: "yuv",
  mapping: "identity",
  imageSource: "photo",
  width: 1024,
  height: 1024,
  upload: null,
  single: "row_major",
  singleTile: { w: 32, h: 32 },
  compare: ["row_major", "morton"],
  compareTiles: [{ w: 32, h: 32 }],
  reps: 11,
  condition: "warm",
  cacheSim: false,
  customGeometry: false,
  l1: { kib: 32, ways: 8 },
  l2: { kib: 1024, ways: 16 },
  l3: { kib: 16384, ways: 16 },
  validateReference: true,
};

export type Limits = Capabilities["limits"];
export type FormErrors = Partial<Record<string, string>>;

export function imageDims(s: FormState): { w: number; h: number } | null {
  if (s.imageSource === "upload") return s.upload ? { w: s.upload.width, h: s.upload.height } : null;
  if (s.width === "" || s.height === "") return null;
  return { w: s.width, h: s.height };
}

export function strategies(s: FormState): StrategySpec[] {
  if (s.mode === "single") {
    return s.single === "tiled"
      ? [{ strategy: "tiled", tile_w: Number(s.singleTile.w), tile_h: Number(s.singleTile.h) }]
      : [{ strategy: s.single }];
  }
  return [
    ...s.compare.map((x) => ({ strategy: x }) as StrategySpec),
    ...s.compareTiles.map((t) => ({ strategy: "tiled", tile_w: t.w, tile_h: t.h }) as StrategySpec),
  ];
}

/** Variant tokens exactly as the backend passes them to the engine (row-major is added to comparisons). */
export function engineTokens(s: FormState): string[] {
  const list = strategies(s).map((x) => (x.strategy === "tiled" ? `tiled:${x.tile_w}x${x.tile_h}` : x.strategy));
  if (s.mode === "compare" && !list.includes("row_major")) list.unshift("row_major");
  return list;
}

const intIn = (v: number | "", lo: number, hi: number) => v !== "" && Number.isInteger(v) && v >= lo && v <= hi;

export function validate(s: FormState, limits: Limits): FormErrors {
  const e: FormErrors = {};
  const dims = imageDims(s);
  if (s.imageSource === "upload") {
    if (!s.upload) e.upload = "Upload an image first.";
  } else {
    if (!intIn(s.width, limits.min_edge, limits.max_edge)) e.width = `Width must be an integer from ${limits.min_edge} to ${limits.max_edge}.`;
    if (!intIn(s.height, limits.min_edge, limits.max_edge)) e.height = `Height must be an integer from ${limits.min_edge} to ${limits.max_edge}.`;
    if (!e.width && !e.height && dims && dims.w * dims.h > limits.max_pixels)
      e.height = `Image exceeds the ${limits.max_pixels.toLocaleString()}-pixel limit.`;
  }
  if (!intIn(s.reps, limits.min_reps, limits.max_reps)) e.reps = `Repetitions must be ${limits.min_reps}–${limits.max_reps}.`;

  const checkTile = (w: number | "", h: number | ""): string | undefined => {
    if (!intIn(w, limits.min_tile, limits.max_tile) || !intIn(h, limits.min_tile, limits.max_tile))
      return `Tile sides must be integers from ${limits.min_tile} to ${limits.max_tile}.`;
    if (dims && (Number(w) > dims.w || Number(h) > dims.h)) return `Tile ${w}×${h} is larger than the ${dims.w}×${dims.h} image.`;
    return undefined;
  };
  if (s.mode === "single") {
    if (s.single === "tiled") {
      const t = checkTile(s.singleTile.w, s.singleTile.h);
      if (t) e.tile = t;
    }
  } else {
    const n = engineTokens(s).length;
    if (strategies(s).length < 2) e.strategies = "Select at least two strategies to compare.";
    else if (n > limits.max_variants) e.strategies = `At most ${limits.max_variants} variants per comparison (row-major included).`;
    for (const t of s.compareTiles) {
      const err = checkTile(t.w, t.h);
      if (err) e.strategies = err;
    }
  }

  if (s.cacheSim && dims && dims.w * dims.h > limits.max_sim_pixels)
    e.cacheSim = `The cache model is limited to ${limits.max_sim_pixels.toLocaleString()} pixels.`;
  if (s.cacheSim && s.customGeometry) {
    const lv: [keyof FormState, string, number, number][] = [
      ["l1", "L1", 4, 1024],
      ["l2", "L2", 64, 65536],
      ["l3", "L3", 256, 262144],
    ];
    for (const [key, name, lo, hi] of lv) {
      const v = s[key] as CacheLevelInput;
      if (!intIn(v.kib, lo, hi) || !intIn(v.ways, 1, 64)) e[key] = `${name}: size ${lo}–${hi} KiB and 1–64 ways.`;
      else if ((Number(v.kib) * 1024) % (64 * Number(v.ways)) !== 0) e[key] = `${name}: size must be a whole number of sets (64 B × ways).`;
    }
  }
  return e;
}

export function buildConfig(s: FormState): ExperimentConfig {
  const geometry =
    s.cacheSim && s.customGeometry
      ? {
          l1_kib: Number(s.l1.kib),
          l1_ways: Number(s.l1.ways),
          l2_kib: Number(s.l2.kib),
          l2_ways: Number(s.l2.ways),
          l3_kib: Number(s.l3.kib),
          l3_ways: Number(s.l3.ways),
        }
      : {};
  return {
    name: s.name.trim() || null,
    op: s.op,
    mapping: s.mapping,
    image_source: s.imageSource,
    upload_id: s.imageSource === "upload" ? s.upload?.upload_id ?? null : null,
    width: s.imageSource === "upload" ? null : Number(s.width),
    height: s.imageSource === "upload" ? null : Number(s.height),
    strategies: strategies(s),
    reps: Number(s.reps),
    condition: s.condition,
    cache_sim: { enabled: s.cacheSim, ...geometry },
    validate_reference: s.validateReference,
  };
}
