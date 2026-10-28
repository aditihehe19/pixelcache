import { ChevronLeft, ChevronRight, GitCompare, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { ApiError, api } from "../api/client";
import type { ExperimentSummary } from "../api/types";
import { Button, ConfirmDialog, EmptyState, ErrorState, Loading, PageHeader, StatusBadge, cx, inputCls, tableCls, tdCls, thCls } from "../components/ui";
import { fmtDate, fmtMs, sizeLabel } from "../lib/format";
import { OP_NAMES, strategyName } from "../lib/strategies";
import { useApi } from "../lib/useApi";

const PAGE_SIZE = 20;

export default function History() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ status: "", op: "", mapping: "", kind: "", strategy: "", q: "" });
  const [selected, setSelected] = useState<string[]>([]);
  const [toDelete, setToDelete] = useState<ExperimentSummary>();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<ApiError>();
  const list = useApi(() => api.listExperiments({ page, page_size: PAGE_SIZE, ...filters }), [page, JSON.stringify(filters)], {
    pollMs: 3000,
    shouldPoll: (d) => !!d?.items.some((x) => x.status === "queued" || x.status === "running"),
  });
  const setFilter = (k: keyof typeof filters, v: string) => {
    setFilters((f) => ({ ...f, [k]: v }));
    setPage(1);
  };
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id].slice(-6)));

  async function remove() {
    if (!toDelete) return;
    setDeleting(true);
    setError(undefined);
    try {
      await api.deleteExperiment(toDelete.id);
      setSelected((s) => s.filter((x) => x !== toDelete.id));
      setToDelete(undefined);
      list.reload();
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
      setToDelete(undefined);
    } finally {
      setDeleting(false);
    }
  }

  const select = (k: keyof typeof filters, label: string, opts: [string, string][]) => (
    <select aria-label={label} className={cx(inputCls.replace("w-full", ""), "w-auto")} value={filters[k]} onChange={(e) => setFilter(k, e.target.value)}>
      <option value="">{label}: all</option>
      {opts.map(([v, l]) => (
        <option key={v} value={v}>
          {l}
        </option>
      ))}
    </select>
  );

  return (
    <>
      <PageHeader
        title="Experiment history"
        subtitle="Every stored run. Select up to six completed experiments to compare them side by side."
        actions={
          <Button variant="primary" disabled={selected.length === 0} onClick={() => navigate(`/compare?ids=${selected.join(",")}`)}>
            <GitCompare size={14} /> Compare selected ({selected.length})
          </Button>
        }
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="relative">
          <Search size={14} className="absolute left-2 top-2 text-muted" />
          <input aria-label="Search by name or id" placeholder="name or id" className={cx(inputCls.replace("w-full", ""), "w-56 pl-7")} value={filters.q} onChange={(e) => setFilter("q", e.target.value)} />
        </label>
        {select("status", "status", [["completed", "completed"], ["failed", "failed"], ["running", "running"], ["queued", "queued"]])}
        {select("op", "conversion", Object.entries(OP_NAMES))}
        {select("mapping", "mapping", [["identity", "identity"], ["rotate90", "rotate90"]])}
        {select("strategy", "strategy", [["row_major", "row-major"], ["column_major", "column-major"], ["tiled", "tiled"], ["morton", "Morton"], ["adaptive_model", "adaptive (model)"], ["adaptive_calib", "adaptive (calibrated)"]])}
        {select("kind", "type", [["experiment", "single"], ["comparison", "comparison"], ["suite", "suite"]])}
      </div>
      {error && <div className="mb-3"><ErrorState error={error} /></div>}
      {list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : !list.data ? (
        <Loading />
      ) : list.data.items.length === 0 ? (
        <EmptyState title={list.data.total === 0 && Object.values(filters).every((v) => !v) ? "No experiments yet" : "No experiments match these filters"}>
          {list.data.total === 0 && <Link to="/experiments/new" className="text-accent hover:underline">Run one from the workbench.</Link>}
        </EmptyState>
      ) : (
        <>
          <div className="overflow-x-auto rounded-md border border-line bg-surface">
            <table className={tableCls}>
              <thead>
                <tr>
                  <th className={thCls}>
                    <span className="sr-only">select</span>
                  </th>
                  {["id", "date", "conversion", "image", "traversal", "tile", "status", "median (fastest)", "correctness", ""].map((h, i) => (
                    <th key={i} className={thCls}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((e) => {
                  const tiles = e.strategies.filter((s) => s.startsWith("tiled_")).map((s) => s.replace("tiled_", ""));
                  return (
                    <tr key={e.id} className="hover:bg-sunken/60">
                      <td className={tdCls}>
                        <input
                          type="checkbox"
                          aria-label={`select ${e.id}`}
                          className="accent-[var(--accent)]"
                          disabled={e.status !== "completed" || e.kind === "suite"}
                          checked={selected.includes(e.id)}
                          onChange={() => toggle(e.id)}
                        />
                      </td>
                      <td className={cx(tdCls, "num")}>
                        <Link to={`/experiments/${e.id}`} className="text-accent hover:underline">
                          {e.id}
                        </Link>
                      </td>
                      <td className={cx(tdCls, "whitespace-nowrap text-ink-2")}>{fmtDate(e.created_at)}</td>
                      <td className={tdCls}>{e.kind === "suite" ? `suite ${e.suite_name}` : `${OP_NAMES[e.op ?? ""] ?? e.op} · ${e.mapping}`}</td>
                      <td className={cx(tdCls, "num")}>{e.kind === "suite" ? "-" : sizeLabel(e.width, e.height)}</td>
                      <td className={cx(tdCls, "max-w-[220px]")}>{e.strategies.map(strategyName).join(", ")}</td>
                      <td className={cx(tdCls, "num")}>{tiles.join(", ") || "-"}</td>
                      <td className={tdCls}>
                        <StatusBadge status={e.status} />
                      </td>
                      <td className={cx(tdCls, "num whitespace-nowrap")}>
                        {e.best_median_ms !== null ? `${fmtMs(e.best_median_ms)} (${strategyName(e.best_label ?? "")})` : "-"}
                      </td>
                      <td className={tdCls}>
                        {e.all_outputs_match === null ? <span className="text-muted">-</span> : e.all_outputs_match ? <span className="text-ok">bit-identical</span> : <span className="text-err">mismatch</span>}
                      </td>
                      <td className={tdCls}>
                        <button
                          aria-label={`delete ${e.id}`}
                          disabled={e.status === "running"}
                          onClick={() => setToDelete(e)}
                          className="rounded p-1 text-muted hover:bg-err-soft hover:text-err disabled:opacity-40"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-between text-[13px] text-ink-2">
            <span className="num">
              {list.data.total} experiment{list.data.total === 1 ? "" : "s"} · page {page} of {pages}
            </span>
            <div className="flex gap-1">
              <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="previous page">
                <ChevronLeft size={14} />
              </Button>
              <Button variant="ghost" disabled={page >= pages} onClick={() => setPage((p) => p + 1)} aria-label="next page">
                <ChevronRight size={14} />
              </Button>
            </div>
          </div>
        </>
      )}
      <ConfirmDialog
        open={!!toDelete}
        title="Delete this experiment?"
        confirmLabel="Delete"
        busy={deleting}
        onConfirm={() => void remove()}
        onCancel={() => setToDelete(undefined)}
      >
        <span className="num">{toDelete?.id}</span> ({toDelete?.name}) and all of its stored measurements and reports will be removed.
      </ConfirmDialog>
    </>
  );
}
