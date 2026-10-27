## Tile sweep: best and worst square tile per configuration

| mapping | op | size | row_major_ns_px | best_tile | best_ns_px | best_speedup_vs_row | worst_tile | worst_ns_px |
|---|---|---|---|---|---|---|---|---|
| identity | lab | 512x512 | 24.901 | tiled_128x128 | 24.878 | 1.001 | tiled_8x8 | 26.051 |
| identity | lab | 1024x1024 | 27.185 | tiled_16x16 | 27.343 | 0.994 | tiled_8x8 | 28.555 |
| identity | lab | 2048x2048 | 24.486 | tiled_128x128 | 25.558 | 0.958 | tiled_8x8 | 26.528 |
| identity | lab | 4096x4096 | 23.318 | tiled_64x64 | 25.841 | 0.902 | tiled_256x256 | 26.216 |
| identity | lab | 8192x8192 | 22.553 | tiled_8x8 | 25.228 | 0.894 | tiled_512x512 | 26.761 |
| identity | yuv | 512x512 | 0.971 | tiled_512x512 | 0.976 | 0.995 | tiled_8x8 | 3.200 |
| identity | yuv | 1024x1024 | 1.041 | tiled_32x32 | 1.082 | 0.963 | tiled_8x8 | 3.293 |
| identity | yuv | 2048x2048 | 1.149 | tiled_32x32 | 1.285 | 0.895 | tiled_8x8 | 3.492 |
| identity | yuv | 4096x4096 | 1.250 | tiled_32x32 | 1.366 | 0.915 | tiled_8x8 | 3.652 |
| identity | yuv | 8192x8192 | 1.230 | tiled_512x512 | 1.447 | 0.850 | tiled_8x8 | 3.731 |
| rotate90 | lab | 512x512 | 24.715 | tiled_256x256 | 24.661 | 1.002 | tiled_8x8 | 26.022 |
| rotate90 | lab | 1024x1024 | 25.788 | tiled_128x128 | 25.716 | 1.003 | tiled_8x8 | 27.720 |
| rotate90 | lab | 2048x2048 | 26.453 | tiled_128x128 | 25.809 | 1.025 | tiled_8x8 | 27.523 |
| rotate90 | lab | 4096x4096 | 27.117 | tiled_64x64 | 26.295 | 1.031 | tiled_256x256 | 27.288 |
| rotate90 | lab | 8192x8192 | 27.945 | tiled_8x8 | 26.979 | 1.036 | tiled_512x512 | 28.057 |
| rotate90 | yuv | 512x512 | 3.275 | tiled_16x16 | 1.723 | 1.900 | tiled_32x32 | 3.432 |
| rotate90 | yuv | 1024x1024 | 5.759 | tiled_128x128 | 3.939 | 1.462 | tiled_512x512 | 5.328 |
| rotate90 | yuv | 2048x2048 | 10.170 | tiled_64x64 | 4.344 | 2.341 | tiled_512x512 | 6.482 |
| rotate90 | yuv | 4096x4096 | 15.637 | tiled_8x8 | 4.707 | 3.322 | tiled_256x256 | 7.729 |
| rotate90 | yuv | 8192x8192 | 18.992 | tiled_16x16 | 4.987 | 3.808 | tiled_512x512 | 10.074 |
