## Correctness

Output hashes: 1250/1250 timed configurations produced output bit-identical to the row-major baseline. Max absolute error over all validation images and channels, by reference:

| op | numpy64 | opencv |
|---|---|---|
| hsv | 2.44e-04 | 1.83e-03 |
| lab | 9.63e-05 | 4.27e-01 |
| unpack | 7.43e-08 | 5.96e-08 |
| yuv | 1.67e-07 | 2.38e-07 |
