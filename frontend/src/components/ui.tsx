import { AlertTriangle, CircleCheck, CircleDashed, CircleX, Info, Loader2 } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { ApiError } from "../api/client";
import type { JobStatus } from "../api/types";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

// ---- layout ----------------------------------------------------------------------

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3 border-b border-line pb-4">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Panel({
  title,
  aside,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("rounded-md border border-line bg-surface", className)}>
      {(title || aside) && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          {title && <h2 className="text-[13px] font-semibold uppercase tracking-wide text-ink-2">{title}</h2>}
          {aside}
        </div>
      )}
      <div className={cx("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

// ---- buttons -----------------------------------------------------------------------

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" };

export function Button({ variant = "secondary", className, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      className={cx(
        "inline-flex items-center gap-1.5 rounded border px-3 py-1.5 text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "border-accent bg-accent text-accent-ink hover:brightness-110",
        variant === "secondary" && "border-line-strong bg-surface text-ink hover:bg-sunken",
        variant === "ghost" && "border-transparent text-ink-2 hover:bg-sunken hover:text-ink",
        variant === "danger" && "border-err/40 bg-surface text-err hover:bg-err-soft",
        className,
      )}
    />
  );
}

// ---- status & provenance --------------------------------------------------------

const STATUS: Record<JobStatus, { cls: string; icon: ReactNode; text: string }> = {
  queued: { cls: "bg-sunken text-ink-2", icon: <CircleDashed size={13} />, text: "queued" },
  running: { cls: "bg-accent-soft text-accent", icon: <Loader2 size={13} className="animate-spin" />, text: "running" },
  completed: { cls: "bg-ok-soft text-ok", icon: <CircleCheck size={13} />, text: "completed" },
  failed: { cls: "bg-err-soft text-err", icon: <CircleX size={13} />, text: "failed" },
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const s = STATUS[status];
  return (
    <span className={cx("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium", s.cls)}>
      {s.icon}
      {s.text}
    </span>
  );
}

const SOURCES = {
  measured: { cls: "border-ok/40 text-ok", text: "measured", title: "Timed by the C++ engine on this machine" },
  simulated: {
    cls: "border-accent/40 text-accent",
    text: "simulated",
    title: "Output of the trace-driven cache model (cachevision_sim), not hardware counters",
  },
  estimate: {
    cls: "border-warn/40 text-warn",
    text: "estimate",
    title: "Derived from measurements with a model (e.g. ns/px x probed clock); not a counter reading",
  },
  unavailable: { cls: "border-line-strong text-muted", text: "unavailable", title: "Not available on this platform" },
} as const;

export function SourceTag({ kind }: { kind: keyof typeof SOURCES }) {
  const s = SOURCES[kind];
  return (
    <span title={s.title} className={cx("rounded border px-1.5 py-px text-[10px] font-semibold uppercase tracking-wider", s.cls)}>
      {s.text}
    </span>
  );
}

export function KeyValue({ rows, mono = true }: { rows: [ReactNode, ReactNode][]; mono?: boolean }) {
  return (
    <dl className="grid grid-cols-[minmax(110px,max-content)_1fr] gap-x-4 gap-y-1.5 text-[13px]">
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-ink-2">{k}</dt>
          <dd className={cx("min-w-0 break-words text-ink", mono && "num")}>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

// ---- states ----------------------------------------------------------------------

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-6 text-ink-2">
      <Loader2 size={16} className="animate-spin" /> {label}…
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError | Error; onRetry?: () => void }) {
  const details = error instanceof ApiError ? error.details : [];
  return (
    <div role="alert" className="rounded-md border border-err/30 bg-err-soft px-4 py-3 text-err">
      <div className="flex items-start gap-2">
        <AlertTriangle size={16} className="mt-0.5 shrink-0" />
        <div className="min-w-0">
          <p className="font-medium">{error.message}</p>
          {details.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-[13px]">
              {details.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
          {onRetry && (
            <button onClick={onRetry} className="mt-2 text-[13px] underline underline-offset-2">
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-line-strong px-6 py-10 text-center">
      <p className="font-medium text-ink">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-xl text-ink-2">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn"; children: ReactNode }) {
  return (
    <div
      className={cx(
        "flex items-start gap-2 rounded border px-3 py-2 text-[13px]",
        tone === "info" ? "border-accent/25 bg-accent-soft text-ink" : "border-warn/30 bg-warn-soft text-ink",
      )}
    >
      {tone === "info" ? <Info size={15} className="mt-0.5 shrink-0 text-accent" /> : <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warn" />}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

// ---- form fields -------------------------------------------------------------------

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: string;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-[13px] font-medium text-ink">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-xs text-err" role="alert">
          {error}
        </p>
      ) : (
        hint && <p className="text-xs text-muted">{hint}</p>
      )}
    </div>
  );
}

export const inputCls =
  "w-full rounded border border-line-strong bg-surface px-2 py-1.5 text-[13px] text-ink placeholder:text-muted focus:border-accent";

export function NumberInput({
  value,
  onChange,
  min,
  max,
  id,
  invalid,
  ariaLabel,
}: {
  value: number | "";
  onChange: (v: number | "") => void;
  min?: number;
  max?: number;
  id?: string;
  invalid?: boolean;
  ariaLabel?: string;
}) {
  return (
    <input
      id={id}
      aria-label={ariaLabel}
      aria-invalid={invalid || undefined}
      type="number"
      inputMode="numeric"
      min={min}
      max={max}
      value={value}
      onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      className={cx(inputCls, "num", invalid && "border-err")}
    />
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string; disabled?: boolean }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  const name = useId();
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap rounded border border-line-strong bg-sunken p-0.5">
      {options.map((o) => (
        <label
          key={o.value}
          className={cx(
            "cursor-pointer rounded px-2.5 py-1 text-[13px] has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-[var(--focus)]",
            value === o.value ? "bg-surface font-medium text-ink shadow-[0_0_0_1px_var(--line)]" : "text-ink-2 hover:text-ink",
            o.disabled && "cursor-not-allowed opacity-50",
          )}
        >
          <input
            type="radio"
            name={name}
            className="sr-only"
            value={o.value}
            checked={value === o.value}
            disabled={o.disabled}
            onChange={() => onChange(o.value)}
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}

export function Checkbox({
  checked,
  onChange,
  children,
  disabled,
  description,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  children: ReactNode;
  disabled?: boolean;
  description?: ReactNode;
}) {
  return (
    <label className={cx("flex cursor-pointer items-start gap-2 text-[13px]", disabled && "cursor-not-allowed opacity-60")}>
      <input
        type="checkbox"
        className="mt-0.5 accent-[var(--accent)]"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="text-ink">{children}</span>
        {description && <span className="block text-xs text-muted">{description}</span>}
      </span>
    </label>
  );
}

// ---- dialog ----------------------------------------------------------------------

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
  busy,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal?.();
    if (!open && d.open) d.close?.();
  }, [open]);
  if (!open) return null;
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      aria-labelledby="confirm-title"
      className="m-auto w-[min(440px,92vw)] rounded-md border border-line bg-surface p-0 text-ink backdrop:bg-black/30"
    >
      <div className="p-5">
        <h2 id="confirm-title" className="text-base font-semibold">
          {title}
        </h2>
        <div className="mt-2 text-ink-2">{children}</div>
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={busy} autoFocus>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  );
}

export const tableCls = "w-full border-collapse text-[13px]";
export const thCls = "border-b border-line px-2 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-ink-2 whitespace-nowrap";
export const tdCls = "border-b border-line px-2 py-1.5 align-top";
