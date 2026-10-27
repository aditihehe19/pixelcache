# Architecture

CacheVision keeps four concerns apart: **what is computed** (conversion
kernels), **in which order memory is touched** (traversals), **how it is
measured** (benchmark harness, cache model), and **how results are judged**
(validation, analysis). A change to one never changes the others.

```
             +-------------------------+        +---------------------------+
 inputs ---> | image_types             |        | system_info               |
 (PPM /      |  aligned RGB888 / F32   |        |  CPUID caches, pinning,   |
 synthetic)  +-----------+-------------+        |  TSC, clock probe, memory |
                         |                      +-------------+-------------+
                         v                                    |
  +-----------------------------------+     +----------------v--------------+
  | color_conversion.hpp  (WHAT)      |     | adaptive  (tile selection)    |
  |  UnpackKernel  YuvKernel          |     |  analytical model + optional  |
  |  HsvKernel     LabKernel          |     |  calibration on a real band   |
  |  IndexOnlyKernel                  |     +----------------+--------------+
  +-----------------+-----------------+                      |
                    | inlined into                           |
  +-----------------v-----------------------------------------v-------------+
  | traversal.hpp  (ORDER)                                                   |
  |  traverse_row_major / column_major / tiled / morton  <Map, Kernel>      |
  |  IdentityMap | Rotate90Map  (destination address policy)                |
  +-----------------+-------------------------------------+------------------+
                    |                                     |
     +--------------v-------------+          +------------v-------------+
     | benchmark  (MEASURE)       |          | cache_sim  (MODEL)       |
     |  interleaved reps, warm /  |          |  same templates, a       |
     |  CLFLUSH, stats, CSV       |          |  recording kernel, LRU   |
     +--------------+-------------+          +------------+-------------+
                    |   results/raw/*.csv                 |
                    +------------------+------------------+
                                       v
               scripts/analyze_results.py, plot_results.py, validate_reference.py
```

## Source map

| path | role |
|---|---|
| `include/image_types.hpp`, `src/image_types.cpp` | `AlignedBuffer` (64-byte aligned), `ImageU8` / `ImageF32`, dimension validation, deterministic synthetic images, PPM I/O, output hashing |
| `include/color_conversion.hpp` | per-pixel kernels (header-only so every traversal inlines identical arithmetic) and the documented conventions |
| `src/conversion_rgb_yuv.cpp`, `_hsv.cpp`, `_lab.cpp` | independent float64 reference implementations, the sRGB LUT, op names |
| `include/traversal.hpp` | traversal templates, output mappings, Morton bit helpers, type-erased entry points |
| `src/traversal_row_major.cpp`, `_tiled.cpp`, `_morton.cpp`, `_common.cpp` | one dispatch per call (op × mapping → template instantiation), validating `convert()` front door |
| `include/adaptive.hpp`, `src/adaptive.cpp` | tile cost model and calibration |
| `include/benchmark.hpp`, `src/benchmark.cpp` | timing loop, cache flushing, statistics, CSV, memory-hierarchy probes |
| `include/system_info.hpp`, `src/system_info.cpp` | CPUID (leaf 4 caches, 0x18 TLBs), Windows/Linux topology, P-core pinning, priority, TSC, clock probe, peak memory |
| `include/cache_sim.hpp`, `src/cache_sim.cpp` | trace-driven set-associative LRU cache/TLB model |
| `include/mini_json.hpp` | dependency-free reader for `benchmarks/benchmark_config.json` |
| `benchmarks/run_benchmarks.cpp` | `cachevision_bench_{native,scalar}` driver (suites, single mode, memory, dump) |
| `benchmarks/run_cachesim.cpp` | `cachevision_sim` |
| `src/main.cpp` | `cachevision` CLI (`info`, `convert`) |
| `tests/` | `test_conversion`, `test_traversal`, `test_correctness` (built for both variants, run by CTest) |
| `scripts/` | pipeline, image preparation, validation, vectorisation report, perf collection, analysis, plots |

## Design decisions

**Kernels are functors inlined into templates.** A traversal is
`template <class Map, class Kernel> void traverse_X(in, out, rect, Kernel&)`.
The type-erased entry points (`run_row_major`, ...) switch once on
(op, mapping) and call a fully inlined instantiation, so there is no
per-pixel indirect call in any strategy, and every strategy executes the
same per-pixel instructions. Only the loop structure around them differs.

**Destination mapping is a compile-time policy.** `IdentityMap` gives
`dst(x, y) = out + 12·(y·W + x)`; `Rotate90Map` gives the clockwise-rotated
position. Traversals step pointers with `Map::step_x/step_y`, so the
identity case has a constant 12-byte step that the compiler can vectorise,
and the rotated case has a constant stride of one output row.

**Morton order without a coordinate list.** Codes are iterated in increasing
order over the bounding 2^k square, decoded with bit de-interleaving (PEXT
with BMI2, otherwise 6 mask/shift steps). When a decoded point falls outside
the region, the largest aligned quad block starting at that code is skipped
in one step (its origin is outside, so all of it is). Rectangular and
non-power-of-two images are therefore handled exactly with O(1) auxiliary
memory.

**Regions instead of whole images.** Every traversal works on a half-open
rectangle. This is what lets adaptive calibration time candidates on a
full-width band of the real image with the real strides, and it gives the
tests boundary cases for free.

**The cache model reuses the real traversal code.** `cachevision_sim`
instantiates the same templates with a `RecordKernel` that forwards the
source (3 B read) and destination (12 B write) addresses to the simulator, so
the simulated and the timed address streams are identical by construction.

**Two build variants of one source tree.** `cachevision_core_native`
(auto-vectorisation on) and `cachevision_core_scalar` (same flags plus
`-fno-tree-vectorize -fno-tree-slp-vectorize`) are separate static libraries
linked into separate benchmark binaries. Both use `-ffp-contract=off` and no
fast-math, which makes their outputs bit-identical as well.

## Error handling

`convert()` returns an error string instead of crashing for empty images,
missing storage, short strides, mismatched output dimensions, non-positive
tiles and the adaptive strategy (which must go through `choose_tile`). Image
constructors throw `std::invalid_argument` for negative dimensions and
`std::length_error` for sizes that would overflow. Empty images are valid
no-ops for every strategy.
