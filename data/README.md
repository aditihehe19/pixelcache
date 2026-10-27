# Benchmark inputs

Nothing in this folder needs to be downloaded. All inputs are regenerated
deterministically and are excluded from git (`data/*.ppm`).

## `photo_<W>x<H>.ppm` – standard colour image

Created by `python scripts/prepare_images.py` from **`grace_hopper.jpg`** (512×600,
public-domain US Navy photograph), which ships with matplotlib in
`matplotlib/mpl-data/sample_data/`.

* Targets ≤ 512 on both sides: centred crop with the target aspect ratio, then
  `cv2.INTER_AREA` down-sampling.
* Larger targets: the centred 512×512 crop at native resolution, mirror-tiled
  (`numpy.pad(..., mode="symmetric")`) to the target size. This keeps real
  photographic local statistics (edges, texture, colour distribution) at every
  size, instead of an artificially smooth up-scaled image.

`photo_manifest.csv` records the SHA-256 of every file plus the matplotlib,
OpenCV and NumPy versions used, so a reproduction can verify that it uses
byte-identical inputs.

## Synthetic images (generated in C++, never stored)

`make_synthetic()` in `src/image_types.cpp` is a pure function of
(kind, width, height, seed):

| kind | content | purpose |
|---|---|---|
| `gradient` | smooth R/G/B ramps | perfectly coherent data, predictable branches |
| `noise` | SplitMix64 position hash per pixel | incoherent data, defeats branch prediction |
| `mixed` | gradient + 32 px checker + noisy 64 px patches | fallback when a photo is missing |

## Format and working set

| | layout | bytes / pixel |
|---|---|---|
| input | interleaved RGB888, row-major, dense rows | 3 |
| output | interleaved float32 × 3, row-major, dense rows | 12 |

Working set = 15 bytes/pixel: 3.75 MiB at 512², 60 MiB at 2048², 240 MiB at
4096², 960 MiB at 8192². The CPU used for the reported results has a 48 KiB
L1D, 1.25 MiB L2 and 18 MiB L3, so only images of about 1100×1100 or smaller
fit in the last-level cache.
