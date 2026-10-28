import { Cpu, FileText, FlaskConical, History, LayoutGrid, Menu, Moon, Sun, Table2 } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { api } from "../api/client";
import { useApi } from "../lib/useApi";
import { cx } from "./ui";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutGrid, end: true },
  { to: "/experiments/new", label: "Workbench", icon: FlaskConical },
  { to: "/history", label: "History", icon: History },
  { to: "/cache-analysis", label: "Cache analysis", icon: Table2 },
  { to: "/reports", label: "Reports", icon: FileText },
];

function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState<string>(() => {
    try {
      return localStorage.getItem("pixelcache-theme") ?? "light";
    } catch {
      return "light";
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("pixelcache-theme", theme);
    } catch {
      /* storage unavailable: theme simply is not remembered */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

function EngineStatus() {
  const health = useApi(() => api.health(), [], { pollMs: 5000, shouldPoll: () => true });
  if (health.error) {
    return (
      <p className="flex items-center gap-2 text-xs text-err">
        <span className="h-2 w-2 rounded-full bg-err" /> API unreachable
      </p>
    );
  }
  const h = health.data;
  if (!h) return <p className="text-xs text-muted">checking engine…</p>;
  const ok = h.engine.benchmark_binary && h.database === "ok";
  return (
    <div className="space-y-0.5 text-xs">
      <p className="flex items-center gap-2 text-ink-2">
        <span className={cx("h-2 w-2 rounded-full", ok ? "bg-ok" : "bg-err")} />
        {ok ? "engine ready" : !h.engine.benchmark_binary ? "engine not built" : "database error"}
      </p>
      <p className="num text-muted">
        {h.queue.running ? `running ${h.queue.running}` : "idle"} · {h.queue.pending} queued
      </p>
    </div>
  );
}

export function Layout() {
  const [theme, toggleTheme] = useTheme();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[220px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <div className="flex items-center justify-between border-b border-line bg-surface px-4 py-2 lg:hidden">
        <span className="flex items-center gap-2 font-semibold">
          <Cpu size={16} /> PixelCache
        </span>
        <button aria-label="Toggle navigation" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="rounded p-1.5 hover:bg-sunken">
          <Menu size={18} />
        </button>
      </div>
      <aside
        className={cx(
          "border-r border-line bg-surface lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col",
          open ? "block" : "hidden lg:flex",
        )}
      >
        <div className="hidden px-5 pb-4 pt-5 lg:block">
          <p className="flex items-center gap-2 text-[15px] font-semibold text-ink">
            <Cpu size={17} className="text-accent" /> PixelCache
          </p>
          <p className="mt-0.5 text-xs text-muted">cache-aware colour conversion lab</p>
        </div>
        <nav aria-label="Main" className="flex flex-col gap-0.5 px-2 py-2 lg:py-0">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cx(
                  "flex items-center gap-2.5 rounded px-3 py-1.5 text-[13px]",
                  isActive ? "bg-accent-soft font-medium text-accent" : "text-ink-2 hover:bg-sunken hover:text-ink",
                )
              }
            >
              <Icon size={15} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-3 border-t border-line px-5 py-4">
          <EngineStatus />
          <button onClick={toggleTheme} className="flex items-center gap-2 text-xs text-ink-2 hover:text-ink" aria-label="Toggle colour theme">
            {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
            {theme === "dark" ? "Light theme" : "Dark theme"}
          </button>
        </div>
      </aside>
      <main id="main" className="mx-auto w-full max-w-[1240px] px-4 py-6 sm:px-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  );
}
