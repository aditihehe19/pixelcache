# PixelCache web application

The web application is an orchestration and visualisation layer around the
existing C++ engine. It never computes a benchmark result itself: every
number it shows was produced by `cachevision_bench_*` or `cachevision_sim`
and parsed from their CSV/JSON output.

## 1. Audit of the existing engine (what the integration builds on)

| area | implementation | how the web app uses it |
|---|---|---|
| per-pixel kernels | `include/color_conversion.hpp`: `UnpackKernel`, `YuvKernel` (BT.601), `HsvKernel`, `LabKernel` (sRGB → CIELAB, D65), `IndexOnlyKernel` | selected through `--op` (`yuv`, `hsv`, `lab`; `unpack`/`index_only` also exposed as reference kernels) |
| traversals | `include/traversal.hpp`: `traverse_row_major`, `traverse_column_major`, `traverse_tiled`, `traverse_morton` with `IdentityMap` / `Rotate90Map` | `--variant row_major,column_major,morton,tiled:WxH` and `--mapping identity|rotate90` |
| adaptive tiles | `src/adaptive.cpp`: `rank_tiles` (cost model), `choose_tile` (calibration) | `--variant adaptive_model` / `adaptive_calib`; the chosen tile and selection time come back in the CSV (`tile_w`, `tile_h`, `setup_ms`, `setup_note`) |
| benchmark harness | `src/benchmark.cpp` `run_group`: untimed row-major baseline and hash, warm-up, shuffled interleaved repetitions, warm / CLFLUSH conditions, per-round clock probe | `cachevision_bench_native --single ...` writes `bench_native.csv` (one row per variant), `samples_native.csv` (one row per repetition), `system_native.json`, `session_native.jsonl` |
| suites | `benchmarks/benchmark_config.json` (main, tile_sweep, tile_shape, cache_condition, overhead, content, adaptive_unseen, simd_compare) | `cachevision_bench_native --config ... --suites NAME [--quick]` |
| cache model | `src/cache_sim.cpp`, `benchmarks/run_cachesim.cpp`: true-LRU, write-back, write-allocate, no prefetch, modulo set index; geometry from CPUID leaf 4 | `cachevision_sim --size WxH --mappings M --variants ... [--l1/--l2/--l3 KiB:ways]` writes `cachesim.csv` and `cachesim_geometry.json` (rows tagged `source=model`) |
| correctness | `tests/` (CTest, both build variants); `output_matches_baseline` per variant (64-bit hash vs row-major); `scripts/validate_reference.py` (float64 NumPy and OpenCV) | `output_matches_baseline` is stored per variant; the validation script is run on the experiment's own image (≤ 1 Mpixel) outside the timed run |
| inputs | synthetic `gradient`/`noise`/`mixed` generated in C++; `photo_WxH.ppm` loaded from `--data DIR` (made by `scripts/prepare_images.py`) | synthetic kinds directly; "photo" via `prepare_images.py --sizes WxH --out <job dir>`; uploaded images are decoded with OpenCV and written as `photo_WxH.ppm` in the job directory |
| host info | `src/system_info.cpp` → `cachevision_bench_native --sysinfo --out DIR` | `/api/system-info` |
| analysis | `scripts/analyze_results.py`, `plot_results.py` (fixed strategy → colour mapping) | report charts reuse the same palette and strategy styles |

Constraints found during the audit:

* Hardware performance counters are **unavailable** on the development
  machine (Windows without a PMU driver, WSL2 without a PMU). The engine
  writes `hw_counters=unavailable`, and the web app shows that rather than any
  substitute number. Cache statistics come only from the simulator and are
  labelled "simulated".
* `--single` originally accepted one variant per process. A fair comparison
  needs all variants in one group (same input buffer, shuffled interleaved
  repetitions), so `--variant` now accepts a comma-separated list (§3).
* `cachevision_sim` only took square sizes and always ran every strategy and
  both mappings. It now accepts `--size WxH`, `--variants`, `--mappings` and
  optional `--l1/--l2/--l3 KiB:ways` geometry (§3). The defaults are unchanged.
* The engine pins itself to a P-core and should not share the machine with
  another benchmark. The backend therefore runs **one job at a time**.

## 2. Integration plan (as implemented)

1. Minimal engine CLI extensions, with the timing code untouched, and the
   C++ tests re-run.
2. Backend core: settings, SQLite schema with versioned migrations, an
   engine runner (fixed binaries, argument lists, timeouts, exit-code
   checks, CSV/JSON parsing into Pydantic models), and a single-worker job
   queue with persistent status.
3. API routes, analytics computed from stored repetitions, and an HTML or
   Markdown report generator.
4. Backend tests: unit tests with a fake engine for failure paths, plus an
   end-to-end test that runs the real engine.
5. React frontend against the real API contract, with TypeScript types
   mirroring the Pydantic schemas.
6. Browser verification of the full workflow, then documentation.

## 3. Engine changes made for the integration

* `benchmarks/run_benchmarks.cpp`: `--variant` in `--single` mode accepts
  `a,b,c` (duplicates removed). One variant still works exactly as before.
* `benchmarks/run_cachesim.cpp`: new optional `--size WxH`, `--variants`
  (including any `tiled:WxH`), `--mappings`, and `--l1/--l2/--l3 KiB:ways`.
  The geometry file reports `source: cpuid | custom | generic-defaults`.
  Without options it behaves exactly as before.

## 4. Architecture

```
 Browser (React + TypeScript, Vite :5173)
   │  fetch /api/...  (Vite dev proxy → :8000; CORS limited to the frontend origin)
   ▼
 FastAPI backend (:8000)  backend/app
   ├─ api/routes        health · experiments · benchmarks · analytics · reports
   ├─ schemas           Pydantic request/response models (mirrored in frontend/src/api/types.ts)
   ├─ services
   │    experiment_service   create → queue → run pipeline → persist → read
   │    job_queue            ONE worker thread (benchmarks never overlap)
   │    engine_runner        fixed binaries, argv lists, timeouts, exit codes, CSV/JSON → Pydantic
   │    benchmark_service    suites from benchmarks/benchmark_config.json
   │    analytics_service    aggregates over stored rows only
   │    report_service       HTML/Markdown reports (charts via scripts/plot_results.py styles)
   │    system_service       engine --sysinfo, with a provenance for every field
   ├─ db                SQLAlchemy engine/session, versioned migrations (schema_version)
   └─ models            Experiment ─< VariantResult ─< Repetition ; Experiment ─< CacheSimRow, Report
   │
   │  subprocess.run([fixed binary, *validated args], cwd=<job dir>, timeout=…)   (no shell)
   ▼
 C++ engine (build/)                            Python scripts (scripts/)
   cachevision_bench_native  --single / suites    prepare_images.py   (photo inputs)
   cachevision_sim           cache model          validate_reference.py (NumPy + OpenCV)
        │ bench_native.csv, samples_native.csv, system_native.json, cachesim.csv, cachesim_geometry.json
        ▼
   parsed, validated, stored in SQLite (backend/data/pixelcache.db); job directory deleted
```

### Job lifecycle

`POST` creates an `experiments` row with status `queued` and puts its id on
the queue (HTTP 202). The single worker marks it `running`, creates
`backend/data/jobs/<id>/`, runs the pipeline, stores results in one
transaction per step, and sets `completed` or `failed` with a user-safe
message and a sanitised stderr excerpt. The job directory is then deleted.
On start-up, jobs left `running` by a previous process are marked `failed`
("interrupted"), and `queued` jobs are resubmitted.

## 5. API reference

Interactive OpenAPI documentation is served at `http://127.0.0.1:8000/docs`.

| method & path | purpose |
|---|---|
| `GET /api/health` | status, database connectivity, schema version, engine binaries present, queue state |
| `GET /api/system-info` | host description from the engine's CPUID/OS probe; each field has `{value, source}`, where source is `cpuid`, `os`, `measured`, `compile-time` or `unavailable` |
| `GET /api/capabilities` | operations, strategies, mappings, image sources and limits accepted by the engine |
| `POST /api/uploads` | multipart image (PNG/JPEG/BMP/PPM/TIFF ≤ 25 MB); decoded with OpenCV, stored as RGB888; returns `upload_id`, size, SHA-256 |
| `POST /api/experiments` | one strategy (`ExperimentConfig`); 202 + job id |
| `POST /api/experiments/compare` | 2–12 strategies in one interleaved group (row-major added if missing); 202 + job id |
| `GET /api/experiments` | paginated list; filters `status, op, mapping, kind, strategy, q` |
| `GET /api/experiments/{id}` | configuration, status, queue position, results with repetitions and speedups, cache rows, validation, environment, sanitised engine command, errors |
| `GET /api/experiments/{id}/results` | measured variants with every repetition |
| `DELETE /api/experiments/{id}` | delete history (cascades to results, repetitions, cache rows, report files); 409 while running |
| `GET /api/benchmarks/suites` | suites in `benchmark_config.json` with group counts (full / quick) |
| `POST /api/benchmarks/run` | run a suite (`{suite, quick}`) through the engine's suite driver |
| `GET /api/benchmarks/{id}` | status and results of a suite run |
| `GET /api/analytics/summary` | counts, latest completed run, largest within-run speedups over row-major |
| `GET /api/analytics/scaling?op&mapping` | median ns/px and Mpix/s per strategy and image size over stored results |
| `GET /api/analytics/comparisons?experiment_ids&op&mapping&width&height&labels` | comparable rows across runs, within-run speedups, warnings when inputs, conversions, conditions, builds or sizes differ |
| `GET /api/analytics/cache?experiment_id` | simulated cache rows (accesses, hits, misses, miss rate, misses/px, write-backs, DRAM bytes/px) and the geometry used |
| `POST /api/reports/{experiment_id}` | generate a report (`{"format": "html" | "md"}`) from stored data |
| `GET /api/reports` | list generated reports |
| `GET /api/reports/{id}/download` | download the report file |

`ExperimentConfig`:

```json
{
  "name": "optional",
  "op": "yuv | hsv | lab | unpack | index_only",
  "mapping": "identity | rotate90",
  "image_source": "photo | gradient | noise | mixed | upload",
  "upload_id": "only with image_source=upload",
  "width": 2048, "height": 2048,
  "strategies": [{"strategy": "row_major"}, {"strategy": "tiled", "tile_w": 32, "tile_h": 32},
                 {"strategy": "morton"}, {"strategy": "adaptive_calib"}],
  "reps": 11,
  "condition": "warm | flushed",
  "cache_sim": {"enabled": true, "l1_kib": 32, "l1_ways": 8},
  "validate_reference": true
}
```

Errors use FastAPI's format: `{"detail": "message"}` or, for validation,
`{"detail": [{"loc": [...], "msg": "..."}]}`. Status codes: 404 for unknown or
malformed ids, 409 for an action invalid in the current state, 413 for oversized
bodies or uploads, 415 for unsupported files, 422 for invalid configurations,
429 when the queue is full or more than 30 POSTs per minute arrive from one
client.

## 6. Where every metric comes from

| metric | source | label in the UI |
|---|---|---|
| median / mean / min / max / p25 / p75 / stdev / CV of run time | engine (`std::chrono::steady_clock` around the traversal call), from the stored repetitions | measured |
| ns/pixel, Mpix/s, speedup vs row-major | derived from measured medians (speedups only within one run) | measured |
| TSC ticks/pixel | engine (`rdtsc`, constant 3.11 GHz reference clock) | measured |
| core cycles/pixel | ns/px × effective clock from a dependent-IMUL probe before each round | estimate |
| bytes/pixel, bandwidth | compulsory-traffic model (3 + 12 + 12 B/px) | estimate |
| cache accesses, hits, misses, miss rate, write-backs, DRAM bytes | `cachevision_sim` trace-driven LRU model | simulated |
| hardware counters (cycles, instructions, L1/L2/LLC misses) | not accessible on the development machine (Windows, no PMU driver; WSL2, no PMU) | unavailable |
| output equality | engine: 64-bit hash of each variant's output vs the row-major output | measured |
| numerical error | `validate_reference.py`: float64 NumPy and OpenCV on the same image | measured |

## 7. Security and reliability measures

* Pydantic models with `extra="forbid"`, enums for every categorical field, and
  range checks for sizes, tiles, repetitions and cache geometry. Every check
  is repeated in the frontend for usability; the backend's checks are
  authoritative.
* The engine runner can only start the two engine binaries at their
  configured paths, or the current Python interpreter on two specific
  repository scripts. It passes argument lists (`shell=False`), re-checks
  variant tokens against the engine grammar, applies a timeout, and checks the
  exit code.
* Error text returned to the browser replaces absolute paths with
  placeholders (`<repo>`, `<build>`, `<data>`, `<job>`, `<home>`).
* Uploads: extension allow-list, a 25 MB limit enforced while reading, decoding
  by OpenCV (anything undecodable is rejected), size limits, and server-chosen
  file names. Uploads expire after 24 h.
* Request bodies over the limit are rejected from `Content-Length`. POSTs are
  rate-limited per client, the queue is bounded, and there is exactly one
  benchmark worker.
* CORS allows only the configured frontend origin(s). Report downloads resolve
  file names from the database, never from the request path.
* SQLite runs with foreign keys on (cascading deletes) and WAL journaling. Each
  pipeline step commits in its own transaction.
