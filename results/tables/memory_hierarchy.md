## Measured memory hierarchy (median over sizes within each region)

Dependent-load latency uses a random cyclic permutation of 64-byte nodes (defeats prefetching); bandwidth uses sequential 8-byte loads/stores.

| region | latency_ns | read_GBps | write_GBps |
|---|---|---|---|
| L1 (<= L1/2) | 1.14 | 81.92 | 40.96 |
| L2 (2xL1 .. L2/2) | 3.63 | 89.88 | 37.63 |
| L3 (2xL2 .. L3/2) | 14.80 | 63.64 | 36.23 |
| DRAM (>= 4xL3) | 107.96 | 21.56 | 13.13 |
