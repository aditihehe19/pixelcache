// Mirrors backend/app/schemas/*.py. Keep in sync when a schema changes.

export type Operation = "yuv" | "hsv" | "lab" | "unpack" | "index_only";
export type Mapping = "identity" | "rotate90";
export type StrategyName =
  | "row_major"
  | "column_major"
  | "tiled"
  | "morton"
  | "adaptive_model"
  | "adaptive_calib";
export type ImageSource = "gradient" | "noise" | "mixed" | "photo" | "upload";
export type CacheCondition = "warm" | "flushed";
export type JobStatus = "queued" | "running" | "completed" | "failed";
export type ExperimentKind = "experiment" | "comparison" | "suite";

export interface StrategySpec {
  strategy: StrategyName;
  tile_w?: number | null;
  tile_h?: number | null;
}

export interface CacheSimConfig {
  enabled: boolean;
  l1_kib?: number | null;
  l1_ways?: number | null;
  l2_kib?: number | null;
  l2_ways?: number | null;
  l3_kib?: number | null;
  l3_ways?: number | null;
}

export interface ExperimentConfig {
  name?: string | null;
  op: Operation;
  mapping: Mapping;
  image_source: ImageSource;
  upload_id?: string | null;
  width?: number | null;
  height?: number | null;
  strategies: StrategySpec[];
  reps: number;
  condition: CacheCondition;
  cache_sim: CacheSimConfig;
  validate_reference: boolean;
}

export interface JobAccepted {
  id: string;
  kind: ExperimentKind;
  status: JobStatus;
  queue_position: number;
}

export interface Repetition {
  rep: number;
  inner_iters: number;
  ms_per_run: number;
  tsc_ticks_per_run: number | null;
  core_ghz_probe: number | null;
}

export interface VariantResult {
  id: number;
  suite: string;
  build_variant: string;
  image_kind: string;
  width: number;
  height: number;
  op: string;
  mapping: string;
  condition: string;
  strategy: string;
  label: string;
  tile_w: number;
  tile_h: number;
  reps: number;
  inner_iters: number;
  median_ms: number;
  mean_ms: number;
  min_ms: number;
  max_ms: number;
  stdev_ms: number;
  p25_ms: number;
  p75_ms: number;
  cv_pct: number;
  ns_per_px: number;
  mpix_per_s: number;
  tsc_ticks_per_px: number | null;
  core_ghz_probe: number | null;
  est_core_cycles_per_px: number | null;
  model_bytes_per_px: number | null;
  est_bw_gbps: number | null;
  setup_ms: number | null;
  setup_note: string | null;
  output_hash: string | null;
  output_matches_baseline: boolean | null;
  hw_counters: string;
  speedup_vs_row_major: number | null;
  repetitions: Repetition[];
}

export interface CacheRow {
  source: "model";
  width: number;
  height: number;
  mapping: string;
  label: string;
  sim_label: string;
  tile_w: number;
  tile_h: number;
  level: string;
  accesses: number;
  misses: number;
  miss_rate: number;
  misses_per_px: number;
  writebacks: number;
  dram_read_bytes_per_px: number;
  dram_write_bytes_per_px: number;
}

export interface ExperimentSummary {
  id: string;
  kind: ExperimentKind;
  name: string;
  status: JobStatus;
  created_at: string;
  finished_at: string | null;
  op: string | null;
  mapping: string | null;
  width: number | null;
  height: number | null;
  image_source: string | null;
  condition: string | null;
  reps: number | null;
  suite_name: string | null;
  strategies: string[];
  best_label: string | null;
  best_median_ms: number | null;
  row_major_median_ms: number | null;
  all_outputs_match: boolean | null;
  result_count: number;
}

export interface ValidationChannel {
  channel: string;
  max_abs_err: number;
  mean_abs_err: number;
  p99_abs_err: number;
  tolerance: number | null;
  pass: boolean | null;
}

export interface ValidationInfo {
  ran: boolean;
  reason?: string;
  references?: Record<string, { channels: ValidationChannel[]; judged: boolean; passed: boolean | null }>;
}

export interface CacheGeometry {
  source?: string;
  cpu?: string;
  levels?: { name: string; size_bytes: number; line_bytes: number; ways: number }[];
  policy?: string;
  skipped?: string;
}

export interface ExperimentDetail extends ExperimentSummary {
  started_at: string | null;
  config: Record<string, unknown>;
  image_detail: string | null;
  build_variant: string | null;
  compiler: string | null;
  build_flags: string | null;
  environment: Record<string, unknown> | null;
  cache_geometry: CacheGeometry | null;
  validation: ValidationInfo | null;
  engine_command: string[] | null;
  engine_seconds: number | null;
  error_message: string | null;
  error_detail: string | null;
  queue_position: number | null;
  results: VariantResult[];
  cache: CacheRow[];
}

export interface ExperimentPage {
  items: ExperimentSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface UploadOut {
  upload_id: string;
  width: number;
  height: number;
  sha256: string;
  original_name: string;
  bytes: number;
}

export interface Detected<T = unknown> {
  value: T | null;
  source: string;
}

export interface CacheLevelInfo {
  level: number;
  type: string;
  size_bytes: number;
  line_bytes: number;
  ways: number;
  sets: number;
  shared_by_logical: number;
  inclusive: boolean | null;
  source: string;
}

export interface SystemInfo {
  available: boolean;
  reason: string | null;
  cpu: Detected<string> | null;
  hybrid: Detected<boolean> | null;
  logical_processors: Detected<number> | null;
  physical_cores: Detected<number> | null;
  core_types: Detected<string> | null;
  memory_bytes: Detected<number> | null;
  os: Detected<string> | null;
  compiler: Detected<string> | null;
  build_flags: Detected<string> | null;
  simd: Detected<string> | null;
  tsc_ghz: Detected<number> | null;
  ac_power: Detected<string> | null;
  pinned_cpu: Detected<string> | null;
  caches: CacheLevelInfo[];
  tlbs: Detected | null;
  hardware_counters: Detected | null;
}

export interface Health {
  status: string;
  database: string;
  schema_version: number;
  engine: { benchmark_binary: boolean; simulator_binary: boolean; build_dir: string };
  queue: { running: string | null; pending: number; max_pending: number; worker_alive: boolean };
}

export interface Capabilities {
  operations: { value: Operation; label: string }[];
  strategies: { value: StrategyName; label: string }[];
  mappings: Mapping[];
  image_sources: { value: ImageSource; label: string }[];
  conditions: CacheCondition[];
  limits: {
    min_edge: number;
    max_edge: number;
    max_pixels: number;
    min_tile: number;
    max_tile: number;
    min_reps: number;
    max_reps: number;
    max_variants: number;
    max_sim_pixels: number;
    max_validation_pixels: number;
    max_upload_mb: number;
  };
  engine_available: boolean;
  simulator_available: boolean;
}

export interface SuiteInfo {
  name: string;
  description: string;
  sizes: number[][];
  ops: string[];
  mappings: string[];
  variants: string[];
  conditions: string[];
  reps: number;
  groups: number;
  quick_groups: number;
}

export interface AnalyticsSummary {
  experiments: { total: number; queued: number; running: number; completed: number; failed: number };
  kinds: Record<string, number>;
  variant_results: number;
  repetitions: number;
  latest_completed: ExperimentSummary | null;
  measured_ops: string[];
  measured_strategies: string[];
  best_speedups_vs_row_major: {
    op: string;
    mapping: string;
    width: number;
    height: number;
    label: string;
    speedup: number;
    experiment_id: string;
  }[];
  hardware_counters: string;
}

export interface ScalingPoint {
  label: string;
  width: number;
  height: number;
  pixels: number;
  ns_per_px: number;
  mpix_per_s: number;
  median_ms: number;
  n_results: number;
  experiments: string[];
}

export interface Scaling {
  op: string;
  mapping: string;
  condition: string;
  points: ScalingPoint[];
}

export interface ComparisonRow {
  experiment_id: string;
  experiment_name: string;
  created_at: string;
  suite: string;
  image_kind: string;
  width: number;
  height: number;
  op: string;
  mapping: string;
  condition: string;
  build_variant: string;
  label: string;
  tile_w: number;
  tile_h: number;
  reps: number;
  median_ms: number;
  p25_ms: number;
  p75_ms: number;
  cv_pct: number;
  ns_per_px: number;
  mpix_per_s: number;
  est_core_cycles_per_px: number | null;
  core_ghz_probe: number | null;
  output_matches_baseline: boolean | null;
  speedup_vs_row_major_same_run: number | null;
}

export interface Comparisons {
  rows: ComparisonRow[];
  warnings: string[];
}

export interface CacheAnalysis {
  experiments: {
    experiment_id: string;
    name: string;
    width: number;
    height: number;
    mapping: string;
    op: string;
    geometry_source: string;
    created_at: string;
  }[];
  selected: string | null;
  geometry: CacheGeometry | null;
  rows: (Omit<CacheRow, "source"> & { hits: number; source: string })[];
  source_note: string;
}

export interface ReportOut {
  id: string;
  experiment_id: string;
  created_at: string;
  format: "html" | "md";
  title: string;
  size_bytes: number;
}
