// Fixed strategy -> colour mapping, identical to scripts/plot_results.py (STRAT),
// so a strategy has the same colour in the web UI, the reports and the paper figures.
// The palette was validated for colour-vision deficiency in the analysis scripts;
// charts additionally label every series, so colour is never the only cue.
const FIXED: Record<string, string> = {
  row_major: "#2a78d6",
  tiled_32x32: "#eb6834",
  tiled_128x128: "#1baf7a",
  morton: "#eda100",
  adaptive_model: "#e87ba4",
  adaptive_calib: "#008300",
  column_major: "#6250d6",
  tiled_64x64: "#e34948",
};

// Other tile sizes get a stable colour derived from the label itself.
const TILE_EXTRA = ["#b4651a", "#0f8a8a", "#a33b3b", "#7a6a10", "#3d7a4f", "#8a4f9e"];

export function strategyColor(label: string): string {
  if (FIXED[label]) return FIXED[label];
  let h = 0;
  for (const c of label) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return TILE_EXTRA[h % TILE_EXTRA.length];
}

export function strategyName(label: string): string {
  if (label === "row_major") return "row-major";
  if (label === "column_major") return "column-major";
  if (label === "morton") return "Morton";
  if (label === "adaptive_model") return "adaptive (model)";
  if (label === "adaptive_calib") return "adaptive (calibrated)";
  const m = /^tiled_(\d+)x(\d+)$/.exec(label);
  if (m) return `tiled ${m[1]}×${m[2]}`;
  return label;
}

export const OP_NAMES: Record<string, string> = {
  yuv: "YUV",
  hsv: "HSV",
  lab: "CIELAB",
  unpack: "unpack",
  index_only: "index only",
};

export const STRATEGY_HELP: Record<string, string> = {
  row_major: "Left to right, top to bottom. Unit stride in both buffers: the baseline.",
  column_major: "Top to bottom, then left to right. Stride of one image row: a negative control.",
  tiled: "Rectangular blocks, row-major inside each block. Edge tiles are clipped.",
  morton: "Z-order via bit de-interleaving. Square locality at every scale, more address arithmetic.",
  adaptive_model: "Tile chosen by the analytical cache model (capacity + associativity), no timing.",
  adaptive_calib: "Model's top 4 tiles plus full width, timed on a 1-Mpixel band; the fastest wins.",
};
