// CacheVision - adaptive tile selection (research extension).
//
// The selector never looks at benchmark results. It works in two stages:
//
//  1. Analytical model. For every candidate tile (tw x th) it estimates the
//     extra cache-line transfers per pixel caused by the tile shape, using
//     only the image geometry, bytes per pixel of each stream, the direction
//     in which each stream is contiguous (which depends on the output
//     mapping), and the cache/TLB sizes read from CPUID:
//       * A stream that is contiguous along x is cut into `th` runs per tile;
//         one contiguous along y (Rotate90 output) is cut into `tw` runs.
//       * A y-contiguous stream is written one pixel per tile row, so each of
//         its `tw` live lines is re-touched once per tile row. If those lines
//         do not survive between tile rows, every access misses.
//       * Each run leaves about one partially used line at its edge. That
//         line is re-used by the neighbouring tile only if it survives until
//         then: the reuse distance is one tile footprint for x-contiguous
//         streams (neighbour = next tile) and a whole band of tiles for
//         y-contiguous streams (neighbour = next tile row).
//       * "Survives in level X" requires both capacity (reuse footprint <=
//         1/2 of the level) and associativity: the live lines of one stream
//         sit `pitch` bytes apart, so they can only use
//         sets / gcd(pitch / line, sets) distinct sets (pitch a multiple of
//         the line size), i.e. at most that many sets x ways lines. Images
//         whose row pitch is a large power of two therefore conflict.
//       * A line that does not survive in L1 costs w_l1, one that does not
//         survive in L2 costs w_l2 (in addition).
//       * Each tile touches one page per run of a strided stream; tiles that
//         touch more pages than the first-level DTLB holds pay w_tlb per run.
//       * Each inner loop start costs w_loop (loop setup, exit mispredict).
//     Weights are fixed constants chosen from first principles before any
//     benchmark was run (see docs/methodology.md); they are not fitted.
//
//  2. Optional calibration. The top-K model candidates plus the full-width
//     tile (== row-major order) are timed on a band of the real image with
//     the real buffers; the fastest is chosen. Calibration time is reported
//     separately so it can be amortised honestly.
#pragma once

#include <string>
#include <vector>

#include "image_types.hpp"
#include "system_info.hpp"
#include "traversal.hpp"

namespace cachevision {

struct AdaptiveModelParams {
    double l1_budget_fraction = 0.5;
    double l2_budget_fraction = 0.5;
    double w_l1 = 1.0;    // cost of re-fetching a line from L2   (unit)
    double w_l2 = 4.0;    // cost of re-fetching a line from LLC/DRAM
    double w_tlb = 2.0;   // cost of a first-level DTLB miss
    double w_loop = 1.0;  // cost of starting one inner loop
    int top_k = 4;
};

struct CacheGeometry {
    std::uint64_t l1d_bytes = 48 * 1024;
    std::uint64_t l2_bytes = 1280 * 1024;
    int l1_ways = 12, l1_sets = 64;
    int l2_ways = 10, l2_sets = 2048;
    int line_bytes = 64;
    int dtlb_entries = 64;      // ASSUMED unless dtlb_from_cpuid
    int page_bytes = 4096;
    bool from_cpuid = false;      // caches: false = the defaults above were used
    bool dtlb_from_cpuid = false; // CPUID.18h may be masked (e.g. under Hyper-V)
};
CacheGeometry geometry_from(const SystemInfo& s);

struct TileCandidate {
    TileSize tile;
    double model_cost = 0.0;          // modelled extra cost per pixel (arbitrary units)
    double footprint_bytes = 0.0;     // lines touched by one tile, in bytes
    double calib_ns_per_px = -1.0;    // -1 = not calibrated
};

struct AdaptiveDecision {
    TileSize chosen;
    bool calibrated = false;
    std::vector<TileCandidate> ranked;  // model ranking (best first), calibrated subset annotated
    double model_ms = 0.0;
    double calib_ms = 0.0;
    int calib_rows = 0;
    std::string describe() const;
};

// Model-only ranking of all candidate tiles for this workload.
std::vector<TileCandidate> rank_tiles(int width, int height, Mapping mapping, const CacheGeometry& g,
                                      const AdaptiveModelParams& p = {});

// Full selector. When `calibrate` is false the model's best tile is returned.
AdaptiveDecision choose_tile(const ImageU8& in, const ImageF32& out, Op op, Mapping mapping,
                             const CacheGeometry& g, bool calibrate, const AdaptiveModelParams& p = {});

}  // namespace cachevision
