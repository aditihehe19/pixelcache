## Warm vs flushed caches (ns/px)

flushed = CLFLUSH of every input and output line before each timed run (TLBs not flushed).

| op | label | size | flushed | warm | flushed/warm |
|---|---|---|---|---|---|
| lab | morton | 256x256 | 25.787 | 26.578 | 0.970 |
| lab | morton | 512x512 | 29.185 | 28.858 | 1.011 |
| lab | morton | 1024x1024 | 29.084 | 29.685 | 0.980 |
| lab | morton | 2048x2048 | 29.996 | 30.813 | 0.974 |
| lab | morton | 4096x4096 | 29.659 | 31.325 | 0.947 |
| lab | row_major | 256x256 | 21.671 | 21.792 | 0.994 |
| lab | row_major | 512x512 | 24.009 | 23.799 | 1.009 |
| lab | row_major | 1024x1024 | 23.540 | 24.041 | 0.979 |
| lab | row_major | 2048x2048 | 23.580 | 23.901 | 0.987 |
| lab | row_major | 4096x4096 | 21.985 | 23.315 | 0.943 |
| lab | tiled_64x64 | 256x256 | 21.448 | 21.946 | 0.977 |
| lab | tiled_64x64 | 512x512 | 24.186 | 23.526 | 1.028 |
| lab | tiled_64x64 | 1024x1024 | 23.800 | 24.448 | 0.973 |
| lab | tiled_64x64 | 2048x2048 | 24.733 | 25.377 | 0.975 |
| lab | tiled_64x64 | 4096x4096 | 24.171 | 25.313 | 0.955 |
| unpack | morton | 256x256 | 2.092 | 2.050 | 1.021 |
| unpack | morton | 512x512 | 2.176 | 2.024 | 1.075 |
| unpack | morton | 1024x1024 | 2.301 | 2.179 | 1.056 |
| unpack | morton | 2048x2048 | 2.575 | 2.449 | 1.051 |
| unpack | morton | 4096x4096 | 2.278 | 2.544 | 0.896 |
| unpack | row_major | 256x256 | 0.777 | 0.273 | 2.849 |
| unpack | row_major | 512x512 | 0.831 | 0.418 | 1.986 |
| unpack | row_major | 1024x1024 | 1.117 | 0.490 | 2.280 |
| unpack | row_major | 2048x2048 | 1.082 | 1.064 | 1.017 |
| unpack | row_major | 4096x4096 | 1.010 | 1.038 | 0.973 |
| unpack | tiled_64x64 | 256x256 | 0.687 | 0.280 | 2.451 |
| unpack | tiled_64x64 | 512x512 | 0.933 | 0.429 | 2.175 |
| unpack | tiled_64x64 | 1024x1024 | 1.162 | 0.559 | 2.078 |
| unpack | tiled_64x64 | 2048x2048 | 1.267 | 1.244 | 1.019 |
| unpack | tiled_64x64 | 4096x4096 | 1.241 | 1.254 | 0.990 |
| yuv | morton | 256x256 | 3.163 | 3.063 | 1.033 |
| yuv | morton | 512x512 | 3.422 | 3.209 | 1.066 |
| yuv | morton | 1024x1024 | 3.387 | 3.309 | 1.024 |
| yuv | morton | 2048x2048 | 3.575 | 3.749 | 0.954 |
| yuv | morton | 4096x4096 | 3.533 | 3.888 | 0.909 |
| yuv | row_major | 256x256 | 1.053 | 0.885 | 1.190 |
| yuv | row_major | 512x512 | 1.061 | 0.902 | 1.176 |
| yuv | row_major | 1024x1024 | 1.059 | 0.912 | 1.162 |
| yuv | row_major | 2048x2048 | 1.113 | 1.087 | 1.024 |
| yuv | row_major | 4096x4096 | 1.093 | 1.134 | 0.964 |
| yuv | tiled_64x64 | 256x256 | 1.347 | 0.874 | 1.542 |
| yuv | tiled_64x64 | 512x512 | 1.484 | 0.926 | 1.601 |
| yuv | tiled_64x64 | 1024x1024 | 1.606 | 1.163 | 1.380 |
| yuv | tiled_64x64 | 2048x2048 | 1.795 | 1.746 | 1.028 |
| yuv | tiled_64x64 | 4096x4096 | 1.843 | 1.939 | 0.951 |
