## Image content vs time (2048x2048, ns/px)

Memory access patterns are content-independent; any difference comes from data-dependent control flow (HSV branches, Lab cbrt threshold).

| op | label | gradient | mixed | noise | photo |
|---|---|---|---|---|---|
| hsv | morton | 5.145 | 7.177 | 18.329 | 6.290 |
| hsv | row_major | 2.752 | 4.366 | 13.262 | 3.627 |
| hsv | tiled_64x64 | 2.961 | 4.547 | 13.489 | 4.008 |
| lab | morton | 33.049 | 34.959 | 50.907 | 29.045 |
| lab | row_major | 29.364 | 29.491 | 42.619 | 22.390 |
| lab | tiled_64x64 | 28.037 | 29.241 | 43.742 | 23.386 |
| yuv | morton | 3.711 | 3.723 | 3.809 | 3.687 |
| yuv | row_major | 1.093 | 1.095 | 1.102 | 1.092 |
| yuv | tiled_64x64 | 1.835 | 1.828 | 1.847 | 1.834 |
