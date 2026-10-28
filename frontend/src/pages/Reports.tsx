import { Download, FileText } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ApiError, api } from "../api/client";
import { Button, EmptyState, ErrorState, Field, Loading, PageHeader, Panel, Segmented, cx, inputCls, tableCls, tdCls, thCls } from "../components/ui";
import { fmtBytes, fmtDate } from "../lib/format";
import { useApi } from "../lib/useApi";

export default function Reports() {
  const reports = useApi(() => api.reports(), []);
  const completed = useApi(() => api.listExperiments({ status: "completed", page_size: 100 }), []);
  const [experiment, setExperiment] = useState("");
  const [format, setFormat] = useState<"html" | "md">("html");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError>();
  const chosen = experiment || completed.data?.items[0]?.id || "";

  async function generate() {
    if (!chosen) return;
    setBusy(true);
    setError(undefined);
    try {
      await api.createReport(chosen, format);
      reports.reload();
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Research reports"
        subtitle="Reports are generated from the stored experiment data: configuration, environment, methodology, measurements, charts, correctness, interpretation and limitations."
      />
      <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
        <Panel title="Generate">
          {completed.error ? (
            <ErrorState error={completed.error} />
          ) : !completed.data ? (
            <Loading />
          ) : completed.data.items.length === 0 ? (
            <p className="text-ink-2">
              Reports need a completed experiment. <Link to="/experiments/new" className="text-accent hover:underline">Run one first.</Link>
            </p>
          ) : (
            <div className="space-y-3">
              <Field label="Experiment" htmlFor="report-exp">
                <select id="report-exp" className={inputCls} value={chosen} onChange={(e) => setExperiment(e.target.value)}>
                  {completed.data.items.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.id} · {e.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Format" hint="HTML is self-contained (charts embedded); Markdown embeds charts as data URIs.">
                <Segmented
                  label="Format"
                  value={format}
                  onChange={setFormat}
                  options={[
                    { value: "html", label: "HTML" },
                    { value: "md", label: "Markdown" },
                  ]}
                />
              </Field>
              {error && <ErrorState error={error} />}
              <Button variant="primary" onClick={() => void generate()} disabled={busy}>
                <FileText size={14} /> {busy ? "Generating…" : "Generate report"}
              </Button>
            </div>
          )}
        </Panel>
        <Panel title="Generated reports" bodyClassName="p-0">
          {reports.error ? (
            <div className="p-4">
              <ErrorState error={reports.error} onRetry={reports.reload} />
            </div>
          ) : !reports.data ? (
            <div className="p-4">
              <Loading />
            </div>
          ) : reports.data.length === 0 ? (
            <div className="p-4">
              <EmptyState title="No reports yet">Generate one from a completed experiment.</EmptyState>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className={tableCls}>
                <thead>
                  <tr>
                    {["created", "experiment", "title", "format", "size", ""].map((h) => (
                      <th key={h} className={cx(thCls, "first:pl-4")}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {reports.data.map((r) => (
                    <tr key={r.id}>
                      <td className={cx(tdCls, "whitespace-nowrap pl-4 text-ink-2")}>{fmtDate(r.created_at)}</td>
                      <td className={cx(tdCls, "num")}>
                        <Link to={`/experiments/${r.experiment_id}`} className="text-accent hover:underline">
                          {r.experiment_id}
                        </Link>
                      </td>
                      <td className={tdCls}>{r.title.replace(/^PixelCache report: /, "")}</td>
                      <td className={cx(tdCls, "num uppercase")}>{r.format}</td>
                      <td className={cx(tdCls, "num")}>{fmtBytes(r.size_bytes)}</td>
                      <td className={tdCls}>
                        <a href={api.reportUrl(r.id)} className="inline-flex items-center gap-1 text-accent hover:underline">
                          <Download size={13} /> download
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
