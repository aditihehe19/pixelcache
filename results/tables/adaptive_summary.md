## Adaptive tiling: aggregate

**identity** (18 configs): geomean speedup vs row-major - adaptive_calib 1.00x, adaptive_model 1.00x, morton 0.50x, tiled_128x128 0.87x, tiled_16x16 0.80x, tiled_256x256 0.89x, tiled_32x32 0.94x, tiled_64x64 0.79x, tiled_8x8 0.66x. adaptive_calib within 5% of the oracle tile in 18, adaptive_model in 18; geomean slowdown vs oracle 0.954 (calib) / 0.957 (model).

**rotate90** (18 configs): geomean speedup vs row-major - adaptive_calib 1.25x, adaptive_model 1.15x, morton 0.86x, tiled_128x128 1.23x, tiled_16x16 1.21x, tiled_256x256 1.13x, tiled_32x32 1.23x, tiled_64x64 1.19x, tiled_8x8 1.05x. adaptive_calib within 5% of the oracle tile in 13, adaptive_model in 10; geomean slowdown vs oracle 1.043 (calib) / 1.126 (model).
