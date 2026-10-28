export function fmtNum(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  if (Math.abs(v) >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  return v.toFixed(digits);
}

export function fmtMs(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  if (v < 1) return `${(v * 1000).toFixed(1)} µs`;
  if (v < 1000) return `${v.toFixed(v < 10 ? 3 : 1)} ms`;
  return `${(v / 1000).toFixed(2)} s`;
}

export function fmtBytes(b: number | null | undefined): string {
  if (b === null || b === undefined) return "n/a";
  if (b >= 2 ** 30) return `${(b / 2 ** 30).toFixed(1)} GiB`;
  if (b >= 2 ** 20) return `${(b / 2 ** 20).toFixed(b >= 10 * 2 ** 20 ? 0 : 2)} MiB`;
  if (b >= 2 ** 10) return `${(b / 2 ** 10).toFixed(0)} KiB`;
  return `${b} B`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "n/a";
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

export function sizeLabel(w: number | null | undefined, h: number | null | undefined): string {
  return w && h ? `${w}×${h}` : "n/a";
}

export function secondsSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return (Date.now() - d.getTime()) / 1000;
}
