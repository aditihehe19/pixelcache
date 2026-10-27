# Methodology

This document fixes, before any result is interpreted, what is computed, how
it is timed, and how every reported metric is defined.

## 1. Workload definition

### Data representation

| | format | bytes/px |
|---|---|---|
| input | interleaved RGB888 (R, G, B order), row-major, dense rows, 64-byte aligned base | 3 |
| output | interleaved float32 triple, row-major, dense rows, 64-byte aligned base | 12 |

Input codes are normalised as `float(c) * (1.0f/255.0f)`. All arithmetic is
IEEE-754 float32, compiled with `-ffp-contract=off` and without fast-math.
Outputs are not rounded or clamped.

### Conversions and conventions

| op | definition |
|---|---|
| `unpack` | `d = c/255`. A memory-bound reference kernel: 3 B in, 12 B out, three multiplies. |
| `yuv` | BT.601 luma with analog-YUV chroma scaling and 0.5 offset: `Y = 0.299R + 0.587G + 0.114B`, `U = 0.492(B−Y) + 0.5`, `V = 0.877(R−Y) + 0.5`. Same coefficients as OpenCV `COLOR_RGB2YUV` for float input. |
| `hsv` | Hexcone: `V = max`, `C = V − min`, `S = C/V` (0 if V = 0), `H` in degrees [0, 360): 0 if C = 0, else `60(G−B)/C` (V = R), `60(B−R)/C + 120` (V = G), `60(R−G)/C + 240`, wrapped into [0, 360). Ties resolve R, G, B. |
| `lab` | CIE 1976 L\*a\*b\* from sRGB (IEC 61966-2-1), D65. sRGB EOTF (`c ≤ 0.04045 ? c/12.92 : ((c+0.055)/1.055)^2.4`) evaluated in float64 once per 8-bit code into a 256-entry float table; linear RGB → XYZ with the IEC 61966-2-1 matrix (0.4124564 0.3575761 0.1804375 / 0.2126729 0.7151522 0.0721750 / 0.0193339 0.1191920 0.9503041); white Xn = 0.95047, Yn = 1, Zn = 1.08883; `f(t) = t > (6/29)^3 ? cbrt(t) : t/(3(6/29)^2) + 4/29`; `L = 116f(Y) − 16`, `a = 500(f(X) − f(Y))`, `b = 200(f(Y) − f(Z))`. |
| `index_only` | No pixel memory is touched. The kernel folds the source and destination addresses into an accumulator behind a compiler barrier. Measures address generation and loop control only. |

### Output mappings

* **identity**: `out(x, y) = f(in(x, y))`. Both streams are sequential in row-major order.
* **rotate90**: `out(H−1−y, x) = f(in(x, y))` (clockwise rotation; output is H×W).
  This is the "convert + rotate" step of camera pipelines. A sequential input
  stream implies a destination stride of one output row (H·12 bytes). This is
  the textbook case where blocking matters, and it is included because a
  pointwise colour conversion on its own has **no data reuse** for tiling to
  exploit (each byte is touched exactly once).

### Traversal strategies

| strategy | order | auxiliary memory |
|---|---|---|
| `row_major` (baseline) | y outer, x inner | 0 |
| `column_major` (negative control) | x outer, y inner: input stride = W·3 bytes | 0 |
| `tiled_WxH` | W×H blocks in row-major block order, row-major inside; edge tiles clipped | 0 |
| `morton` | Z-order: increasing Morton code over the bounding 2^k square, decoded by bit de-interleaving (PEXT under BMI2), out-of-range quad blocks skipped in one step | 0 (no coordinate list) |
| `adaptive_model` | `tiled` with the tile ranked best by the analytical model | 0 |
| `adaptive_calib` | `tiled` with the fastest of the model's top 4 + the full-width tile, timed on a band of the real image | 0 |

All strategies process the same input buffer into the same output buffer and
call the same inlined kernel exactly once per pixel. The tests verify
"exactly once" and bit-identical outputs.

### Images

* **photo**: the public-domain `grace_hopper.jpg` shipped with matplotlib.
  Images ≤ 512 px are area-resampled; larger ones are mirror-tiled from a
  native-resolution 512² crop (see `data/README.md`).
* **synthetic**: `gradient`, `noise`, `mixed`, all deterministic functions of
  (kind, size, seed).

Sizes: 256², 512², 1024², 2048², 4096², 8192² (main suite), plus 2000² (tile
shape) and six "unseen" sizes for the adaptive evaluation: 1000×1000,
1920×1080, 2500×1700, 3840×2160, 5000×3000, 7680×4320. None of the unseen
sizes was used while the adaptive model was being written.

## 2. Measurement procedure

1. **Environment control.** The benchmark thread is pinned to one logical CPU
   of the highest efficiency class (a P-core on the hybrid i5-12500H; logical
   CPU 0 avoided). Process priority is HIGH and thread priority HIGHEST (no
   elevation). Single-threaded throughout.
2. **Setup (untimed).** Load or generate the input, allocate the output, run
   the row-major baseline once and hash its output.
3. **Per variant (untimed).** Adaptive tile selection (time recorded as
   `setup_ms`). One warm-up run, which also removes first-touch page faults.
   Output hash compared with the baseline (`output_matches_baseline`).
4. **Inner repetition (warm only).** If one run takes less than 5 ms,
   `inner_iters = ceil(5 ms / t)` back-to-back runs form one sample, and the
   sample time is divided by `inner_iters`. This keeps every sample well
   above the timer resolution.
5. **Timed repetitions.** `reps` rounds (11, or 7 for the large sweeps). Each
   round times every variant once, in an order shuffled with a fixed seed. So
   slow drifts (clock, temperature, background load) hit all strategies
   alike instead of biasing whichever ran last. Before each round a clock
   probe (20 ms ramp-up, then 2 ms of measurement) records the effective
   core frequency.
6. **Timer.** `std::chrono::steady_clock` (QueryPerformanceCounter on
   Windows) around the traversal call(s), plus `rdtsc` for TSC ticks. A
   compiler memory barrier follows each call. Outputs live in heap memory
   that is hashed after timing, so the work cannot be eliminated.

### Cache conditions

* **warm**: no explicit flush. Buffers were touched by the immediately
  preceding run. When the working set (15 B/px) exceeds the 18 MiB L3, this
  is a streaming / capacity-miss regime regardless of the label.
* **flushed**: `CLFLUSH` of every 64-byte line of the input and output
  buffers, plus `MFENCE`, before each timed run. CLFLUSH invalidates the line
  in every cache level of the coherence domain. TLBs, page-walk caches and
  the 1 KiB Lab table are **not** flushed, so this is "data evicted", not a
  verified cold machine state.

## 3. Metrics and their denominators

| metric | definition |
|---|---|
| `median_ms` (+ mean, min, max, stdev, p25, p75) | over the `reps` samples of one variant |
| `cv_pct` | 100 · stdev / mean |
| `ns_per_px` | median_ms · 10^6 / (W·H) |
| `mpix_per_s` | W·H / median time |
| `tsc_ticks_per_px` | median TSC ticks per run / (W·H). The TSC runs at a constant 3.11 GHz (measured), **not** at the core clock. |
| `core_ghz_probe` | median of the per-round effective-clock probes: a chain of dependent 64-bit IMULs (3-cycle latency), so frequency = 3 × IMULs / s. A chain of dependent add-immediates is deliberately not used: Golden Cove P-cores fold those at rename and retire several per cycle (measured: an apparent 12–22 GHz). |
| `est_core_cycles_per_px` | ns_per_px × core_ghz_probe. An **estimate**: it assumes the clock measured just before a round held during that round. |
| `model_bytes_per_px`, `est_bw_gbps` | compulsory-traffic **model**: 3 B read + 12 B written + 12 B write-allocate (RFO) read = 27 B/px for every conversion; bandwidth = 27 · W·H / time. Not a DRAM measurement. |
| `setup_ms` | adaptive selection time (model + calibration), excluded from `median_ms` |
| `aux_bytes` | traversal-specific heap memory: 0 for every strategy |
| peak memory | process peak working set / private bytes, in `session_*.jsonl` |
| speedup | median(row_major) / median(variant) within one (suite, build, image, size, op, mapping, condition) group |

### Hardware counters

Cycles, instructions, L1D/L2/LLC misses and DRAM traffic need PMU access.
On the measurement machine none is available: Windows exposes no user-mode
PMU API without a kernel driver (VTune, PCM, WPR with elevation), and the
WSL2 VM exposes no `cpu` PMU (no `arch_perfmon` flag, no
`/sys/bus/event_source/devices/cpu`). Every `hw_*` value is therefore
`unavailable`, never estimated. `scripts/collect_perf.sh` collects them on a
Linux host with `perf`, using a differential method (R1 and R2 repetitions,
`(count(R2) − count(R1)) / (R2 − R1)`) that cancels all setup work.

What stands in for counters is labelled as such:

* **Cache model** (`cachevision_sim`, rows tagged `source=model`): the exact
  address stream of each traversal is replayed through a set-associative,
  true-LRU, write-back, write-allocate L1D/L2/L3 with the CPUID geometry
  (48 KiB/12-way, 1.25 MiB/10-way, 18 MiB/12-way, 64 B lines). It has no
  prefetchers, uses modulo set indexing (the real L3 hashes across slices),
  and does not model the TLB, because CPUID leaf 0x18 returns zeros under
  Hyper-V on this machine. Miss rate = misses / demand accesses at that
  level; misses/px = misses / (W·H).
* **Memory characterisation**: dependent-load latency over a random cyclic
  permutation of 64-byte nodes (defeats prefetchers), plus sequential read
  and write bandwidth, both as a function of working-set size. This measures
  the latency plateaus and cache capacities empirically.

## 4. Compiler and SIMD

GCC 16.2 (WinLibs, x86_64-w64-mingw32, UCRT), C++17, `-O3 -march=native
-ffp-contract=off`. Two binaries:

* `cachevision_bench_native`: auto-vectorisation on (AVX2 on this CPU).
* `cachevision_bench_scalar`: identical flags plus `-fno-tree-vectorize
  -fno-tree-slp-vectorize`.

`results/vectorization_report.md` lists which loops GCC vectorised in each
variant, from the real compile commands. Strategies are only ever compared
within one variant. The `simd_compare` suite measures the variants against
each other explicitly.

## 5. Adaptive tiling

The selector (`src/adaptive.cpp`) never sees benchmark results. Its inputs
are image width and height, bytes per pixel of each stream (3 in, 12 out),
the direction in which each stream is contiguous (from the mapping), L1D and
L2 size, associativity and sets (CPUID), the line size, and an L1 DTLB size
(64 entries **assumed**, because CPUID 0x18 is masked on this host).

For each candidate tile (widths 8…1024 and full width, heights 1…256) it
estimates extra line transfers per pixel:

* a stream contiguous along x is cut into `th` runs per tile; one contiguous
  along y (rotated output) into `tw` runs;
* a y-contiguous stream re-touches each of its `tw` live lines once per tile
  row. If they do not survive between rows, every access misses;
* each run leaves a partial line at its edge, reused by the neighbouring tile
  only if it survives. The reuse distance is one tile footprint (x-contiguous)
  or one band of tiles (y-contiguous);
* "survives in level ℓ" requires capacity (reuse footprint ≤ ½ of ℓ) **and**
  associativity: lines `pitch` bytes apart can occupy only
  `sets / gcd(pitch/64, sets)` sets, i.e. at most that many × ways lines;
* weights: 1 per line re-fetched from L2, +4 if also not in L2, 2 per DTLB
  overflow, 1 per inner-loop start.

These weights were fixed from rough latency ratios before any benchmark ran.
They were not fitted. `adaptive_model` uses the top-ranked tile.
`adaptive_calib` times the model's top 4 plus the full-width tile (equivalent
to row-major) on a full-width band of about 1 Mpixel of the real image, with
the real strides (1 warm-up + median of 3), and picks the fastest. Its
calibration time is reported separately, together with the break-even number
of runs.

Evaluation compares against row-major, every fixed tile, and the *oracle*:
the best fixed tile chosen after the fact, which no real system could know.

## 6. Correctness (independent of performance)

* `tests/test_conversion`: known colours (primaries, greys, white, black, hue
  wrap), the sRGB table versus `pow`, every kernel versus the float64
  references on 200 000 random colours + the grey axis + the cube corners.
  Tolerances are derived from float32 error propagation and documented in
  the test.
* `tests/test_traversal`: every strategy visits every pixel of 15 image
  shapes (1×1 … 1000×7, non-power-of-two, 1-pixel-wide) and 6 sub-regions
  exactly once, for 9 tile shapes including tiles larger than the image.
  Morton order equals increasing Morton code and stays monotone on
  rectangles. Rotate90 is a bijection with the correct destination.
* `tests/test_correctness`: all strategies × ops × mappings × 3 image kinds
  are **bit-identical**. Empty and invalid inputs are rejected safely,
  adaptive tiles are valid and exact, and the cache-model sanity checks pass.
* `scripts/validate_reference.py`: dumps outputs and compares them with an
  independent float64 NumPy transcription and with OpenCV `cvtColor`.

## 7. Reproduction

```bash
python scripts/run_pipeline.py --clean        # build, test, validate, benchmark, model, analyse, plot
python scripts/run_pipeline.py --quick        # minutes instead of tens of minutes
```

`results/raw/` holds every raw measurement (`bench_*.csv` summaries,
`samples_*.csv` per repetition, `memory_native.csv`, `cachesim.csv`,
`system_*.json`, `session_*.jsonl`). The tables and figures are regenerated
from it by `analyze_results.py` and `plot_results.py`.
