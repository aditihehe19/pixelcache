## Does the cache model rank strategies like the measurements? (yuv)

Spearman rank correlation across strategies between simulated misses/px and measured ns/px at the same size and mapping.

| mapping | size | n | spearman_L1_vs_time | spearman_L2_vs_time |
|---|---|---|---|---|
| identity | 1024x1024 | 10 | 0.51 | 0.52 |
| identity | 2048x2048 | 10 | 0.46 | 0.52 |
| identity | 256x256 | 6 | 0.39 |  |
| identity | 4096x4096 | 10 | 0.68 | 0.52 |
| identity | 512x512 | 10 | 0.29 |  |
| rotate90 | 1024x1024 | 10 | 0.05 | 0.54 |
| rotate90 | 2048x2048 | 10 | 0.51 | 0.68 |
| rotate90 | 256x256 | 6 | -0.33 |  |
| rotate90 | 4096x4096 | 10 | 0.48 | 0.84 |
| rotate90 | 512x512 | 10 | 0.33 |  |
