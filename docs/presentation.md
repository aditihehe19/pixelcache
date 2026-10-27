---
marp: true
title: CacheVision - cache-aware colour-space conversion
paginate: true
size: 16:9
style: |
  section { font-family: "Segoe UI", system-ui, sans-serif; font-size: 26px; background: #fcfcfb; color: #0b0b0b; }
  h1 { color: #184f95; font-size: 44px; }
  h2 { color: #184f95; }
  table { font-size: 20px; }
  img { max-height: 470px; }
  .small { font-size: 18px; color: #52514e; }
---

# CacheVision

## How memory traversal order shapes colour-space conversion performance

A Computer Organization & Architecture study:
RGB → YUV / HSV / CIELAB on an Intel Core i5-12500H

<span class="small">Repository: github.com/aditihehe19/pixelcache · all numbers from `results/raw/`</span>

---

## Research question

> How do memory-access and traversal strategies affect execution time, cache
> behaviour, memory traffic and throughput of colour conversion across image sizes?

Hypotheses (to test, not assume):

1. Row-major traversal benefits from spatial locality and prefetching
2. Spatial tiling improves cache reuse for large images
3. Morton / Z-order improves locality but costs indexing overhead
4. The best strategy and tile depend on size, architecture and operation

---

## What is compared

| | |
|---|---|
| **kernels** | unpack (memory-bound), YUV (BT.601), HSV (branchy), Lab (≈80 cycles/px) |
| **traversals** | row-major (baseline), tiled W×H, Morton (PEXT de-interleave, O(1) memory), column-major (control), adaptive |
| **mappings** | identity, and *convert + rotate 90°* (output written column-wise) |
| **data** | RGB888 in (3 B/px), float32 out (12 B/px): 15 B/px working set |
| **sizes** | 256² … 8192² plus six "unseen" sizes, up to 7680×4320 |

Every traversal inlines the **same** per-pixel kernel. All 1250 timed
outputs are **bit-identical** to the baseline, so every time difference comes
from memory order.

---

## Method

* One pinned P-core, high priority, single thread, GCC 16 `-O3 -march=native`
* Warm-up outside timing, median of 7–11 repetitions, **shuffled interleaving** of strategies
* Effective clock probe (dependent IMUL chain) before each round
* Warm vs **CLFLUSH-ed** caches; native (AVX2) vs scalar build
* PMU counters **unavailable** (Windows/WSL2), so instead:
  * measured latency/bandwidth vs working set
  * a trace-driven **cache model** that replays the real traversal code
* Validated against a float64 NumPy reference and OpenCV 4.12

---

## The machine's memory hierarchy (measured)

![w:1100](../results/figures/fig_memory_hierarchy.png)

L1 1.1 ns · L2 3.6 ns · L3 14.8 ns · DRAM 108 ns, with steps exactly at 48 KiB, 1.25 MiB and 18 MiB (CPUID)

---

## Result 1: pure conversion, row-major wins

![w:1100](../results/figures/fig_speedup_vs_row_major.png)

---

## Why tiling cannot help a pointwise conversion

* Every byte is touched **once**: all misses are compulsory (model: 15/64 = 0.234 misses/px for row-major *and* every tile)
* Tiles still cost time: 2–43% slower (32–512 px), **3× slower** at 8×8
  * short inner loops waste the AVX2 loop
  * every tile row is a short stream, so the prefetcher never ramps up
* Column-major (stride = one row): **17× slower** at 4096², with 9× the compulsory misses
* Morton: misses near compulsory, but **5.5 cycles/px** of address generation, 2.4–3.4× slower

---

## Result 2: the LLC boundary

| unpack, row-major | 256² | 512² | 1024² | 2048² | 4096² |
|---|---|---|---|---|---|
| working set | 1 MB | 4 MB | 16 MB | 63 MB | 252 MB |
| ns/px (warm) | 0.24 | 0.38 | 0.47 | 1.03 | 1.01 |
| flushed / warm | 2.85 | 1.99 | 2.28 | **1.02** | **0.97** |

* Throughput drops 4.3× when the image no longer fits in the 18 MiB L3
* Past the LLC, "warm" is already cold: at ≈27 B/px ≈ 27 GB/s, the loop is **bandwidth-bound**

---

## Result 3: convert + rotate, where blocking pays

![w:1100](../results/figures/fig_heatmap_tile_vs_size.png)

Row-major rotate is **15× slower** than plain conversion; tiles recover up to 3.8×, adaptive up to 6.5×

---

## Result 4: power-of-two images alias in the cache

![w:1050](../results/figures/fig_heatmap_tile_shape.png)

2048² rotate: 11.55 ns/px · 2000² rotate: 3.66 ns/px. Pitch 2048·12 B = 384 lines ≡ 0 (mod 64 sets), so all rows map to **one L1 set** and the best tile is 8 px wide (12 ways)

---

## Result 5: arithmetic intensity decides sensitivity

| @4096², worst / best traversal | unpack | YUV | HSV | Lab |
|---|---|---|---|---|
| identity | 17× | 16× | 5.7× | 1.9× |
| rotate90 | 6.5× | 3.9× | 3.3× | 1.6× |

* Lab (≈80 cycles/px): the out-of-order core overlaps misses with compute
* SIMD: 2.0× in cache, only **1.13×** once DRAM-bound (roofline)
* HSV on random noise is **3.7×** slower than on a photo: branch mispredictions, not memory

---

## Adaptive tiling (extension)

Model: per-stream runs, edge-line reuse distance, **capacity + associativity** (sets / gcd(pitch, sets)), DTLB, loop cost, plus 1-Mpixel calibration. Evaluated on 6 unseen sizes × 3 ops × 2 mappings:

| geomean vs row-major | identity | rotate90 |
|---|---|---|
| adaptive (calibrated) | **1.00×** | **1.25×** |
| best fixed tile, post hoc | 0.95× | 1.30× |
| fixed 32×32 / 128×128 | 0.94× / 0.87× | 1.23× / 1.23× |

Within 5% of the oracle in 31/36 configurations. It never loses noticeably to row-major and handles aliasing, but **it does not beat a good fixed tile by much**

---

## Model vs measurement

![w:950](../results/figures/fig_model_vs_measured.png)

The cache model ranks rotate strategies well (Spearman 0.84 at 4096²) but cannot see address-generation cost or prefetching

---

## Verdicts

| hypothesis | verdict |
|---|---|
| H1 row-major locality | **supported**: fastest for every pointwise case |
| H2 tiling helps large images | **rejected** for pure conversion, **supported** for convert + rotate (2.3–6.5×) |
| H3 Morton | locality yes, overhead yes: tuning-free win only for power-of-two rotations |
| H4 it depends | **supported**: best tile = none / 8 px / 16–128 px / irrelevant (Lab) |

---

## Limitations

* No hardware counters: misses come from a model (no prefetch, virtual addresses)
* One laptop CPU (P-core), Windows 4 KiB pages, clock drift 4.4 → 3.3 GHz (mitigated by interleaving)
* Noise: median CV 2–7%; differences under 5% treated as ties
* Interleaved RGB888 → float32 layout and the GCC 16 vectoriser shape the absolute numbers
* Adaptive: weights a priori, DTLB size assumed, oracle is post hoc

---

## Take-aways

1. Pointwise conversion: **keep it row-major**; tiling only adds overhead
2. Any strided layout change: **block it** (or use Z-order when tuning is impossible)
3. **Associativity matters as much as capacity**: beware power-of-two pitches
4. Compute-heavy kernels hide memory effects; memory-bound ones expose them up to 17×
5. Measure, model, validate: 1250/1250 bit-identical outputs, every number reproducible with `python scripts/run_pipeline.py`
