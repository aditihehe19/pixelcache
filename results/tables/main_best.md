## Main suite: fastest strategy per configuration

| mapping | op | size | best | best_ns_px | row_major_ns_px | speedup_best_vs_row | morton_vs_row | column_vs_row |
|---|---|---|---|---|---|---|---|---|
| identity | hsv | 256x256 | column_major | 3.529 | 3.843 | 1.089 | 0.660 | 1.089 |
| identity | hsv | 512x512 | adaptive_model | 3.406 | 3.466 | 1.018 | 0.654 | 0.966 |
| identity | hsv | 1024x1024 | adaptive_model | 3.400 | 3.488 | 1.026 | 0.617 | 0.633 |
| identity | hsv | 2048x2048 | adaptive_calib | 3.320 | 3.330 | 1.003 | 0.611 | 0.223 |
| identity | hsv | 4096x4096 | adaptive_model | 3.273 | 3.295 | 1.007 | 0.548 | 0.175 |
| identity | hsv | 8192x8192 | adaptive_calib | 3.359 | 3.450 | 1.027 | 0.534 |  |
| identity | lab | 256x256 | adaptive_calib | 23.375 | 24.380 | 1.043 | 0.846 | 1.016 |
| identity | lab | 512x512 | adaptive_model | 23.295 | 24.319 | 1.044 | 0.840 | 1.013 |
| identity | lab | 1024x1024 | adaptive_model | 21.432 | 21.449 | 1.001 | 0.829 | 0.943 |
| identity | lab | 2048x2048 | adaptive_model | 21.287 | 21.334 | 1.002 | 0.788 | 0.573 |
| identity | lab | 4096x4096 | adaptive_calib | 20.843 | 21.109 | 1.013 | 0.747 | 0.537 |
| identity | lab | 8192x8192 | row_major | 21.582 | 21.582 | 1.000 | 0.716 |  |
| identity | unpack | 256x256 | row_major | 0.239 | 0.239 | 1.000 | 0.133 | 0.106 |
| identity | unpack | 512x512 | adaptive_model | 0.369 | 0.382 | 1.036 | 0.210 | 0.117 |
| identity | unpack | 1024x1024 | adaptive_model | 0.433 | 0.471 | 1.087 | 0.236 | 0.096 |
| identity | unpack | 2048x2048 | tiled_32x32 | 0.996 | 1.027 | 1.031 | 0.485 | 0.069 |
| identity | unpack | 4096x4096 | row_major | 1.008 | 1.008 | 1.000 | 0.418 | 0.058 |
| identity | unpack | 8192x8192 | row_major | 1.088 | 1.088 | 1.000 | 0.396 |  |
| identity | yuv | 256x256 | adaptive_model | 0.771 | 0.811 | 1.052 | 0.295 | 0.332 |
| identity | yuv | 512x512 | adaptive_model | 0.800 | 0.947 | 1.184 | 0.326 | 0.274 |
| identity | yuv | 1024x1024 | adaptive_model | 0.867 | 0.890 | 1.027 | 0.281 | 0.170 |
| identity | yuv | 2048x2048 | adaptive_calib | 1.006 | 1.041 | 1.035 | 0.311 | 0.070 |
| identity | yuv | 4096x4096 | row_major | 1.166 | 1.166 | 1.000 | 0.297 | 0.061 |
| identity | yuv | 8192x8192 | adaptive_calib | 1.153 | 1.171 | 1.016 | 0.295 |  |
| rotate90 | hsv | 256x256 | column_major | 3.790 | 3.959 | 1.045 | 0.649 | 1.045 |
| rotate90 | hsv | 512x512 | column_major | 3.588 | 3.731 | 1.040 | 0.664 | 1.040 |
| rotate90 | hsv | 1024x1024 | column_major | 3.689 | 4.353 | 1.180 | 0.760 | 1.180 |
| rotate90 | hsv | 2048x2048 | adaptive_model | 4.010 | 10.237 | 2.553 | 1.764 | 0.871 |
| rotate90 | hsv | 4096x4096 | adaptive_calib | 4.414 | 14.698 | 3.330 | 2.332 | 1.140 |
| rotate90 | hsv | 8192x8192 | adaptive_calib | 4.774 | 15.133 | 3.170 | 2.121 |  |
| rotate90 | lab | 256x256 | adaptive_calib | 24.025 | 24.908 | 1.037 | 0.811 | 1.007 |
| rotate90 | lab | 512x512 | adaptive_calib | 22.184 | 24.265 | 1.094 | 0.847 | 1.049 |
| rotate90 | lab | 1024x1024 | row_major | 21.776 | 21.776 | 1.000 | 0.812 | 0.961 |
| rotate90 | lab | 2048x2048 | tiled_128x128 | 22.461 | 23.018 | 1.025 | 0.843 | 0.763 |
| rotate90 | lab | 4096x4096 | adaptive_model | 23.535 | 24.803 | 1.054 | 0.841 | 0.639 |
| rotate90 | lab | 8192x8192 | tiled_128x128 | 27.028 | 27.374 | 1.013 | 0.829 |  |
| rotate90 | unpack | 256x256 | adaptive_calib | 0.835 | 2.269 | 2.716 | 1.065 | 1.803 |
| rotate90 | unpack | 512x512 | adaptive_model | 0.969 | 3.201 | 3.304 | 1.461 | 2.175 |
| rotate90 | unpack | 1024x1024 | column_major | 1.427 | 4.591 | 3.216 | 1.870 | 3.216 |
| rotate90 | unpack | 2048x2048 | adaptive_calib | 2.137 | 10.365 | 4.850 | 3.882 | 1.314 |
| rotate90 | unpack | 4096x4096 | adaptive_calib | 2.295 | 14.924 | 6.504 | 5.172 | 1.927 |
| rotate90 | unpack | 8192x8192 | adaptive_calib | 2.740 | 15.073 | 5.501 | 4.612 |  |
| rotate90 | yuv | 256x256 | adaptive_calib | 1.329 | 2.444 | 1.839 | 0.818 | 1.278 |
| rotate90 | yuv | 512x512 | adaptive_model | 1.504 | 3.029 | 2.015 | 0.958 | 1.500 |
| rotate90 | yuv | 1024x1024 | column_major | 2.162 | 4.778 | 2.210 | 1.440 | 2.210 |
| rotate90 | yuv | 2048x2048 | morton | 3.653 | 10.284 | 2.815 | 2.815 | 1.382 |
| rotate90 | yuv | 4096x4096 | morton | 3.854 | 14.958 | 3.881 | 3.881 | 1.573 |
| rotate90 | yuv | 8192x8192 | morton | 4.402 | 15.170 | 3.446 | 3.446 |  |
