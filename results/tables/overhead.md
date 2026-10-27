## Traversal overhead decomposition (ns/px)

index_only = address generation + loop control, no pixel memory touched. unpack adds the memory traffic with almost no arithmetic. Differences are indicative only: an out-of-order core overlaps these costs, so they are not strictly additive.

| size | label | index_only | unpack | yuv | lab | unpack-index |
|---|---|---|---|---|---|---|
| 1024x1024 | column_major | 0.456 | 4.887 | 5.247 | 26.918 | 4.431 |
| 1024x1024 | morton | 1.416 | 2.265 | 3.532 | 33.266 | 0.850 |
| 1024x1024 | row_major | 0.270 | 0.496 | 0.964 | 26.304 | 0.226 |
| 1024x1024 | tiled_128x128 | 0.346 | 0.544 | 1.061 | 25.619 | 0.198 |
| 1024x1024 | tiled_32x32 | 0.306 | 0.553 | 0.975 | 26.309 | 0.247 |
| 1024x1024 | tiled_8x8 | 0.445 | 1.117 | 3.082 | 27.684 | 0.672 |
| 4096x4096 | column_major | 0.464 | 19.073 | 19.621 | 40.225 | 18.609 |
| 4096x4096 | morton | 1.475 | 2.673 | 4.104 | 29.517 | 1.198 |
| 4096x4096 | row_major | 0.269 | 1.037 | 1.178 | 21.858 | 0.768 |
| 4096x4096 | tiled_128x128 | 0.348 | 1.217 | 1.597 | 24.390 | 0.870 |
| 4096x4096 | tiled_32x32 | 0.313 | 1.089 | 1.322 | 24.159 | 0.776 |
| 4096x4096 | tiled_8x8 | 0.466 | 1.377 | 3.524 | 24.264 | 0.912 |
