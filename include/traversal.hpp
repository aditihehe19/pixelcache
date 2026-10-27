// CacheVision - traversal strategies.
//
// A traversal decides the ORDER in which input pixels are visited. It never
// changes what is computed: every strategy calls the same inlined per-pixel
// kernel exactly once per pixel of the region, with pointers to that pixel's
// source and destination.
//
// The destination address is given by an output mapping:
//   Identity : out(x, y) = convert(in(x, y))                  (out is W x H)
//   Rotate90 : out(H-1-y, x) = convert(in(x, y))  [clockwise] (out is H x W)
// Rotate90 is the "convert + rotate" step of camera pipelines. It makes the
// destination stream strided when the source is sequential, which is the
// classic access pattern where blocking matters.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

#include "color_conversion.hpp"
#include "image_types.hpp"

#if defined(__BMI2__)
#include <immintrin.h>
#endif

namespace cachevision {

enum class Strategy {
    RowMajor,     // baseline: y outer, x inner
    ColumnMajor,  // negative control: x outer, y inner (stride = row pitch)
    Tiled,        // rectangular blocks, row-major inside and between blocks
    Morton,       // Z-order over pixels via bit de-interleaving
    Adaptive,     // Tiled with a tile chosen at run time (see adaptive.hpp)
};

enum class Mapping { Identity, Rotate90 };

const char* to_string(Strategy s);
const char* to_string(Mapping m);
bool parse_strategy(const char* s, Strategy& out);
bool parse_mapping(const char* s, Mapping& out);

struct TileSize {
    int w = 32;
    int h = 32;
};

// Output dimensions required by a mapping for a given input size.
inline void output_dims(Mapping m, int in_w, int in_h, int& out_w, int& out_h) {
    out_w = (m == Mapping::Identity) ? in_w : in_h;
    out_h = (m == Mapping::Identity) ? in_h : in_w;
}

// ---- output mappings (compile-time policies) ---------------------------------
struct IdentityMap {
    static float* dst(const ImageF32& out, int x, int y) {
        return out.data + std::size_t(y) * out.stride + std::size_t(3) * std::size_t(x);
    }
    static std::ptrdiff_t step_x(const ImageF32&) { return 3; }
    static std::ptrdiff_t step_y(const ImageF32& out) { return std::ptrdiff_t(out.stride); }
};

struct Rotate90Map {  // out.width == in.height
    static float* dst(const ImageF32& out, int x, int y) {
        return out.data + std::size_t(x) * out.stride + std::size_t(3) * std::size_t(out.width - 1 - y);
    }
    static std::ptrdiff_t step_x(const ImageF32& out) { return std::ptrdiff_t(out.stride); }
    static std::ptrdiff_t step_y(const ImageF32&) { return -3; }
};

// ---- Morton helpers ----------------------------------------------------------
// Gather the even bits of v (bit 0, 2, 4, ...) into the low 32 bits.
inline std::uint32_t morton_compact(std::uint64_t v) {
#if defined(__BMI2__)
    return static_cast<std::uint32_t>(_pext_u64(v, 0x5555555555555555ULL));
#else
    v &= 0x5555555555555555ULL;
    v = (v | (v >> 1)) & 0x3333333333333333ULL;
    v = (v | (v >> 2)) & 0x0F0F0F0F0F0F0F0FULL;
    v = (v | (v >> 4)) & 0x00FF00FF00FF00FFULL;
    v = (v | (v >> 8)) & 0x0000FFFF0000FFFFULL;
    v = (v | (v >> 16)) & 0x00000000FFFFFFFFULL;
    return static_cast<std::uint32_t>(v);
#endif
}
inline std::uint32_t morton_x(std::uint64_t code) { return morton_compact(code); }
inline std::uint32_t morton_y(std::uint64_t code) { return morton_compact(code >> 1); }

inline std::uint64_t morton_spread(std::uint32_t v) {
    std::uint64_t x = v;
    x = (x | (x << 16)) & 0x0000FFFF0000FFFFULL;
    x = (x | (x << 8)) & 0x00FF00FF00FF00FFULL;
    x = (x | (x << 4)) & 0x0F0F0F0F0F0F0F0FULL;
    x = (x | (x << 2)) & 0x3333333333333333ULL;
    x = (x | (x << 1)) & 0x5555555555555555ULL;
    return x;
}
inline std::uint64_t morton_encode(std::uint32_t x, std::uint32_t y) {
    return morton_spread(x) | (morton_spread(y) << 1);
}

inline int ceil_log2(std::uint32_t v) {
    int k = 0;
    while ((std::uint64_t(1) << k) < v) ++k;
    return k;
}

inline int count_trailing_zeros64(std::uint64_t v) {
#if defined(__GNUC__) || defined(__clang__)
    return __builtin_ctzll(v);
#else
    int n = 0;
    while (!(v & 1)) { v >>= 1; ++n; }
    return n;
#endif
}

// ---- traversal templates -----------------------------------------------------
// Kernel: callable `k(const uint8_t* src_px, float* dst_px)`.
// Map   : IdentityMap or Rotate90Map.
// Region: half-open rectangle in input coordinates (caller guarantees it lies
//         inside the input image and that `out` has the mapped dimensions).

template <class Map, class Kernel>
void traverse_row_major(const ImageU8& in, const ImageF32& out, Rect r, Kernel& k) {
    const std::ptrdiff_t dx = Map::step_x(out);
    for (int y = r.y0; y < r.y1; ++y) {
        const std::uint8_t* s = in.row(y) + std::size_t(3) * std::size_t(r.x0);
        float* d = Map::dst(out, r.x0, y);
        for (int x = r.x0; x < r.x1; ++x) {
            k(s, d);
            s += 3;
            d += dx;
        }
    }
}

template <class Map, class Kernel>
void traverse_column_major(const ImageU8& in, const ImageF32& out, Rect r, Kernel& k) {
    const std::ptrdiff_t sy = std::ptrdiff_t(in.stride);
    const std::ptrdiff_t dy = Map::step_y(out);
    for (int x = r.x0; x < r.x1; ++x) {
        const std::uint8_t* s = in.row(r.y0) + std::size_t(3) * std::size_t(x);
        float* d = Map::dst(out, x, r.y0);
        for (int y = r.y0; y < r.y1; ++y) {
            k(s, d);
            s += sy;
            d += dy;
        }
    }
}

// Tiles are anchored at the region origin; edge tiles are clipped, so
// dimensions that are not multiples of the tile size are handled exactly.
template <class Map, class Kernel>
void traverse_tiled(const ImageU8& in, const ImageF32& out, Rect r, TileSize t, Kernel& k) {
    const std::ptrdiff_t dx = Map::step_x(out);
    for (int ty = r.y0; ty < r.y1; ty += t.h) {
        const int yend = (r.y1 - ty < t.h) ? r.y1 : ty + t.h;
        for (int tx = r.x0; tx < r.x1; tx += t.w) {
            const int xend = (r.x1 - tx < t.w) ? r.x1 : tx + t.w;
            for (int y = ty; y < yend; ++y) {
                const std::uint8_t* s = in.row(y) + std::size_t(3) * std::size_t(tx);
                float* d = Map::dst(out, tx, y);
                for (int x = tx; x < xend; ++x) {
                    k(s, d);
                    s += 3;
                    d += dx;
                }
            }
        }
    }
}

// Z-order traversal of an arbitrary W x H region.
// Codes run over the bounding 2^k x 2^k square. A code is decoded to local
// (x, y) by de-interleaving bits (x = even bits, y = odd bits). When the decoded
// point lies outside the region, the largest aligned quad-block that starts at
// this code is skipped in one step: such a block covers [x, x+2^j) x [y, y+2^j)
// with its origin already out of range, so every point inside it is out of
// range too. Hence rectangular and non-power-of-two regions cost
// O(pixels + perimeter * log(size)) iterations, and no coordinate list is ever
// allocated (auxiliary memory: O(1)).
template <class Map, class Kernel>
void traverse_morton(const ImageU8& in, const ImageF32& out, Rect r, Kernel& k) {
    const std::uint32_t rw = std::uint32_t(r.width()), rh = std::uint32_t(r.height());
    if (r.empty()) return;
    const int lg = ceil_log2(rw > rh ? rw : rh);
    const std::uint64_t end = std::uint64_t(1) << (2 * lg);
    std::uint64_t m = 0;
    while (m < end) {
        const std::uint32_t lx = morton_x(m), ly = morton_y(m);
        if (lx < rw && ly < rh) {
            const int x = r.x0 + int(lx), y = r.y0 + int(ly);
            k(in.row(y) + std::size_t(3) * std::size_t(x), Map::dst(out, x, y));
            ++m;
        } else {
            const int tz = m ? count_trailing_zeros64(m) : 2 * lg;
            m += std::uint64_t(1) << (tz & ~1);
        }
    }
}

// ---- type-erased entry points (explicitly instantiated in src/) ---------------
// These are the functions the benchmark calls. Each one dispatches ONCE on
// (op, mapping) to a fully inlined template instantiation; there is no
// per-pixel indirect call. `index_acc` receives the IndexOnly accumulator.
struct TraversalArgs {
    Op op = Op::YUV;
    Mapping mapping = Mapping::Identity;
    TileSize tile{};
    std::uintptr_t* index_acc = nullptr;  // optional, IndexOnly only
};

void run_row_major(const ImageU8& in, const ImageF32& out, Rect r, const TraversalArgs& a);
void run_column_major(const ImageU8& in, const ImageF32& out, Rect r, const TraversalArgs& a);
void run_tiled(const ImageU8& in, const ImageF32& out, Rect r, const TraversalArgs& a);
void run_morton(const ImageU8& in, const ImageF32& out, Rect r, const TraversalArgs& a);

// Validating front door. Returns an empty string on success or an error
// message (empty/invalid images, mismatched output size, bad tile size, ...).
// Strategy::Adaptive is NOT accepted here; use adaptive.hpp.
std::string convert(const ImageU8& in, ImageF32& out, Strategy s, const TraversalArgs& a);

// Allocate an output image with the dimensions required by `m`.
ImageF32 make_output(const ImageU8& in, Mapping m);

}  // namespace cachevision
