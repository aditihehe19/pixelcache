// Single place where the frontend talks to the backend. Every call returns the
// backend's own data or throws an ApiError carrying the backend's message;
// there is no fallback data anywhere in the UI.
import type {
  AnalyticsSummary,
  CacheAnalysis,
  Capabilities,
  Comparisons,
  ExperimentConfig,
  ExperimentDetail,
  ExperimentPage,
  Health,
  JobAccepted,
  ReportOut,
  Scaling,
  SuiteInfo,
  SystemInfo,
  UploadOut,
  VariantResult,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  status: number;
  details: string[];
  constructor(status: number, message: string, details: string[] = []) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

type Query = Record<string, string | number | boolean | string[] | undefined | null>;

function qs(query?: Query): string {
  if (!query) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

// FastAPI returns {detail: string} or {detail: [{loc, msg}, ...]} for validation errors.
function describe(body: unknown, status: number): { message: string; details: string[] } {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return { message: detail, details: [] };
  if (Array.isArray(detail)) {
    const details = detail.map((d: { loc?: unknown[]; msg?: string }) => {
      const where = (d.loc ?? []).filter((x) => x !== "body").join(".");
      const msg = (d.msg ?? "invalid value").replace(/^Value error, /, "");
      return where ? `${where}: ${msg}` : msg;
    });
    return { message: "The request was rejected by validation.", details };
  }
  return { message: `Request failed (HTTP ${status}).`, details: [] };
}

async function request<T>(method: string, path: string, init?: { body?: unknown; form?: FormData; query?: Query }) {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}${qs(init?.query)}`, {
      method,
      headers: init?.form ? undefined : init?.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: init?.form ?? (init?.body !== undefined ? JSON.stringify(init.body) : undefined),
    });
  } catch {
    throw new ApiError(0, "The backend is not reachable. Is the API server running on port 8000?");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!res.ok) {
    const { message, details } = describe(body, res.status);
    throw new ApiError(res.status, message, details);
  }
  return body as T;
}

export const api = {
  health: () => request<Health>("GET", "/api/health"),
  systemInfo: (refresh = false) => request<SystemInfo>("GET", "/api/system-info", { query: { refresh } }),
  capabilities: () => request<Capabilities>("GET", "/api/capabilities"),

  createExperiment: (cfg: ExperimentConfig) => request<JobAccepted>("POST", "/api/experiments", { body: cfg }),
  compare: (cfg: ExperimentConfig) => request<JobAccepted>("POST", "/api/experiments/compare", { body: cfg }),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<UploadOut>("POST", "/api/uploads", { form });
  },
  listExperiments: (query: Query) => request<ExperimentPage>("GET", "/api/experiments", { query }),
  experiment: (id: string) => request<ExperimentDetail>("GET", `/api/experiments/${encodeURIComponent(id)}`),
  results: (id: string) => request<VariantResult[]>("GET", `/api/experiments/${encodeURIComponent(id)}/results`),
  deleteExperiment: (id: string) => request<void>("DELETE", `/api/experiments/${encodeURIComponent(id)}`),

  suites: () => request<SuiteInfo[]>("GET", "/api/benchmarks/suites"),
  runSuite: (suite: string, quick: boolean) =>
    request<JobAccepted>("POST", "/api/benchmarks/run", { body: { suite, quick } }),

  summary: () => request<AnalyticsSummary>("GET", "/api/analytics/summary"),
  scaling: (op: string, mapping: string) => request<Scaling>("GET", "/api/analytics/scaling", { query: { op, mapping } }),
  comparisons: (query: Query) => request<Comparisons>("GET", "/api/analytics/comparisons", { query }),
  cache: (experimentId?: string) =>
    request<CacheAnalysis>("GET", "/api/analytics/cache", { query: { experiment_id: experimentId } }),

  createReport: (experimentId: string, format: "html" | "md") =>
    request<ReportOut>("POST", `/api/reports/${encodeURIComponent(experimentId)}`, { body: { format } }),
  reports: () => request<ReportOut[]>("GET", "/api/reports"),
  reportUrl: (id: string) => `${BASE}/api/reports/${encodeURIComponent(id)}/download`,
};
