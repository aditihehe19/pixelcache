import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { Capabilities, ExperimentDetail } from "../api/types";
import History from "../pages/History";
import { ExperimentView } from "../pages/ExperimentResults";
import { WorkbenchForm } from "../pages/Workbench";
import capsJson from "./fixtures/capabilities.json";
import experimentJson from "./fixtures/experiment.json";

const caps = capsJson as Capabilities;
const experiment = experimentJson as unknown as ExperimentDetail;

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => vi.restoreAllMocks());

describe("API client", () => {
  it("turns FastAPI validation errors into readable messages", async () => {
    mockFetch(422, { detail: [{ loc: ["body", "strategies", 0], msg: "Value error, tile_w and tile_h are required for the tiled strategy" }] });
    const err = await api.health().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.details).toEqual(["strategies.0: tile_w and tile_h are required for the tiled strategy"]);
  });

  it("reports an unreachable backend instead of failing silently", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const err = await api.health().catch((e) => e);
    expect(err.status).toBe(0);
    expect(err.message).toMatch(/not reachable/);
  });
});

describe("Workbench form", () => {
  const renderForm = () =>
    render(
      <MemoryRouter>
        <WorkbenchForm caps={caps} l3Bytes={18 * 2 ** 20} />
      </MemoryRouter>,
    );

  it("shows tile fields only for the tiled strategy", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByText("Single strategy"));
    expect(screen.queryByLabelText("tile width")).not.toBeInTheDocument();
    await user.click(screen.getByText("Spatial tiling"));
    expect(screen.getByLabelText("tile width")).toBeInTheDocument();
  });

  it("blocks submission of invalid input and never calls the API", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    renderForm();
    const width = screen.getByLabelText("width");
    await user.clear(width);
    await user.type(width, "5");
    await user.click(screen.getByRole("button", { name: /run comparison/i }));
    expect(screen.getByText(/Width must be an integer from 16 to 8192/)).toBeInTheDocument();
    // The suite panel loads its list with a GET on mount; nothing may be POSTed.
    expect(fetchSpy.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  });

  it("shows the server's rejection when it refuses a configuration", async () => {
    const user = userEvent.setup();
    mockFetch(429, { detail: "8 jobs are already waiting; try again later" });
    renderForm();
    await user.click(screen.getByRole("button", { name: /run comparison/i }));
    expect(await screen.findByText(/8 jobs are already waiting/)).toBeInTheDocument();
  });

  it("previews the exact engine arguments, including the row-major baseline", () => {
    renderForm();
    expect(screen.getByText(/--variant row_major,morton,tiled:32x32/)).toBeInTheDocument();
  });
});

describe("Experiment results", () => {
  const renderView = (d: ExperimentDetail) =>
    render(
      <MemoryRouter>
        <ExperimentView d={d} />
      </MemoryRouter>,
    );

  it("renders the measured variants with their correctness and provenance", () => {
    renderView(experiment);
    const table = screen.getAllByRole("table")[0];
    for (const name of ["row-major", "Morton", "adaptive (calibrated)", "tiled 32×32"]) {
      expect(within(table).getByText(name)).toBeInTheDocument();
    }
    expect(within(table).getAllByText("bit-identical")).toHaveLength(4);
    expect(screen.getAllByText("simulated").length).toBeGreaterThan(0);
    expect(screen.getAllByText("measured").length).toBeGreaterThan(0);
    expect(screen.getAllByText("unavailable").length).toBeGreaterThan(0);
  });

  it("shows the failure message and no measurements for a failed run", () => {
    renderView({ ...experiment, status: "failed", results: [], cache: [], error_message: "cachevision_bench_native.exe exited with code 2.", error_detail: "error: bad --size" });
    expect(screen.getByText(/exited with code 2/)).toBeInTheDocument();
    expect(screen.getByText(/No measurements are shown for failed runs/)).toBeInTheDocument();
    expect(screen.queryByText("Measurements")).not.toBeInTheDocument();
  });

  it("shows queue state for a queued run without inventing progress", () => {
    renderView({ ...experiment, status: "queued", results: [], cache: [], queue_position: 2 });
    expect(screen.getByText(/position 2/)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});

describe("History", () => {
  it("shows a loading state, then an empty state from the API", async () => {
    let resolve!: (r: Response) => void;
    vi.spyOn(globalThis, "fetch").mockReturnValue(new Promise((r) => (resolve = r)));
    render(
      <MemoryRouter>
        <History />
      </MemoryRouter>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/Loading/);
    resolve(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }));
    expect(await screen.findByText("No experiments yet")).toBeInTheDocument();
  });
});
