## Auto-vectorised (native) vs scalar build (ns/px)

Same sources, same -O3 -march=native; the scalar build adds -fno-tree-vectorize -fno-tree-slp-vectorize. See results/vectorization_report.md for which loops vectorise.

| mapping | op | size | label | native | scalar | scalar/native |
|---|---|---|---|---|---|---|
| identity | hsv | 1024x1024 | morton | 5.975 | 5.700 | 0.954 |
| identity | hsv | 1024x1024 | row_major | 3.648 | 3.538 | 0.970 |
| identity | hsv | 1024x1024 | tiled_64x64 | 3.887 | 3.807 | 0.980 |
| identity | hsv | 4096x4096 | morton | 6.568 | 6.315 | 0.961 |
| identity | hsv | 4096x4096 | row_major | 3.563 | 3.521 | 0.988 |
| identity | hsv | 4096x4096 | tiled_64x64 | 4.044 | 4.048 | 1.001 |
| identity | lab | 1024x1024 | morton | 29.539 | 28.802 | 0.975 |
| identity | lab | 1024x1024 | row_major | 23.960 | 23.603 | 0.985 |
| identity | lab | 1024x1024 | tiled_64x64 | 24.181 | 23.488 | 0.971 |
| identity | lab | 4096x4096 | morton | 31.482 | 29.570 | 0.939 |
| identity | lab | 4096x4096 | row_major | 22.865 | 21.563 | 0.943 |
| identity | lab | 4096x4096 | tiled_64x64 | 25.093 | 23.480 | 0.936 |
| identity | unpack | 1024x1024 | morton | 2.148 | 2.156 | 1.004 |
| identity | unpack | 1024x1024 | row_major | 0.492 | 0.912 | 1.855 |
| identity | unpack | 1024x1024 | tiled_64x64 | 0.524 | 0.991 | 1.891 |
| identity | unpack | 4096x4096 | morton | 2.503 | 2.504 | 1.000 |
| identity | unpack | 4096x4096 | row_major | 1.021 | 1.154 | 1.130 |
| identity | unpack | 4096x4096 | tiled_64x64 | 1.258 | 1.348 | 1.071 |
| identity | yuv | 1024x1024 | morton | 3.387 | 3.169 | 0.935 |
| identity | yuv | 1024x1024 | row_major | 0.939 | 1.906 | 2.029 |
| identity | yuv | 1024x1024 | tiled_64x64 | 1.146 | 1.957 | 1.708 |
| identity | yuv | 4096x4096 | morton | 4.167 | 3.696 | 0.887 |
| identity | yuv | 4096x4096 | row_major | 1.203 | 2.102 | 1.747 |
| identity | yuv | 4096x4096 | tiled_64x64 | 2.010 | 2.224 | 1.106 |
| rotate90 | hsv | 1024x1024 | morton | 5.914 | 5.828 | 0.985 |
| rotate90 | hsv | 1024x1024 | row_major | 4.544 | 4.894 | 1.077 |
| rotate90 | hsv | 1024x1024 | tiled_64x64 | 4.391 | 4.409 | 1.004 |
| rotate90 | hsv | 4096x4096 | morton | 6.613 | 6.058 | 0.916 |
| rotate90 | hsv | 4096x4096 | row_major | 14.462 | 14.422 | 0.997 |
| rotate90 | hsv | 4096x4096 | tiled_64x64 | 5.020 | 4.809 | 0.958 |
| rotate90 | lab | 1024x1024 | morton | 29.827 | 28.755 | 0.964 |
| rotate90 | lab | 1024x1024 | row_major | 26.410 | 23.669 | 0.896 |
| rotate90 | lab | 1024x1024 | tiled_64x64 | 25.015 | 23.648 | 0.945 |
| rotate90 | lab | 4096x4096 | morton | 31.329 | 28.980 | 0.925 |
| rotate90 | lab | 4096x4096 | row_major | 25.532 | 24.103 | 0.944 |
| rotate90 | lab | 4096x4096 | tiled_64x64 | 25.079 | 23.559 | 0.939 |
| rotate90 | unpack | 1024x1024 | morton | 2.602 | 2.629 | 1.010 |
| rotate90 | unpack | 1024x1024 | row_major | 4.707 | 4.393 | 0.933 |
| rotate90 | unpack | 1024x1024 | tiled_64x64 | 3.462 | 3.444 | 0.995 |
| rotate90 | unpack | 4096x4096 | morton | 3.064 | 2.896 | 0.945 |
| rotate90 | unpack | 4096x4096 | row_major | 14.877 | 14.414 | 0.969 |
| rotate90 | unpack | 4096x4096 | tiled_64x64 | 4.292 | 4.127 | 0.962 |
| rotate90 | yuv | 1024x1024 | morton | 3.512 | 3.517 | 1.001 |
| rotate90 | yuv | 1024x1024 | row_major | 4.893 | 4.530 | 0.926 |
| rotate90 | yuv | 1024x1024 | tiled_64x64 | 3.558 | 3.393 | 0.954 |
| rotate90 | yuv | 4096x4096 | morton | 4.014 | 3.788 | 0.944 |
| rotate90 | yuv | 4096x4096 | row_major | 14.803 | 14.617 | 0.987 |
| rotate90 | yuv | 4096x4096 | tiled_64x64 | 4.493 | 4.123 | 0.918 |
