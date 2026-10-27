// Traversal coverage and ordering: every valid pixel exactly once, correct
// boundary handling, Morton order on rectangular / non-power-of-two images.
#include <algorithm>
#include <cstdint>
#include <vector>

#include "traversal.hpp"
#include "test_util.hpp"

using namespace cachevision;

namespace {

// Records which input pixel was visited (from the source pointer) and which
// destination it was paired with; touches no pixel memory.
struct Recorder {
    const ImageU8* in;
    const ImageF32* out;
    std::vector<int> visits;                  // per input pixel
    std::vector<std::pair<int, int>> order;   // visiting order (x, y)
    std::vector<std::size_t> dst_index;       // float offset / 3 for each visit
    void operator()(const std::uint8_t* s, float* d) {
        const std::size_t off = std::size_t(s - in->data);
        const int y = int(off / in->stride), x = int((off % in->stride) / 3);
        visits[std::size_t(y) * in->width + x]++;
        order.emplace_back(x, y);
        dst_index.push_back(std::size_t(d - out->data) / 3);
    }
};

enum class S { Row, Col, Tiled, Morton };

template <class Map>
Recorder record(S s, const ImageU8& in, const ImageF32& out, Rect r, TileSize t = {}) {
    Recorder rec{&in, &out, std::vector<int>(std::size_t(in.width) * in.height, 0), {}, {}};
    switch (s) {
        case S::Row: traverse_row_major<Map>(in, out, r, rec); break;
        case S::Col: traverse_column_major<Map>(in, out, r, rec); break;
        case S::Tiled: traverse_tiled<Map>(in, out, r, t, rec); break;
        case S::Morton: traverse_morton<Map>(in, out, r, rec); break;
    }
    return rec;
}

bool exactly_once_in_rect(const Recorder& rec, const ImageU8& in, Rect r) {
    for (int y = 0; y < in.height; ++y)
        for (int x = 0; x < in.width; ++x) {
            const bool inside = x >= r.x0 && x < r.x1 && y >= r.y0 && y < r.y1;
            if (rec.visits[std::size_t(y) * in.width + x] != (inside ? 1 : 0)) return false;
        }
    return true;
}

const int kDims[][2] = {{1, 1}, {1, 9}, {9, 1}, {2, 2}, {3, 5}, {7, 13}, {17, 5}, {64, 64}, {100, 37},
                        {37, 100}, {129, 65}, {257, 3}, {3, 257}, {255, 256}, {1000, 7}};
const TileSize kTiles[] = {{1, 1}, {8, 8}, {16, 16}, {32, 32}, {7, 3}, {64, 1}, {1, 64}, {128, 128}, {500, 500}};

}  // namespace

CV_TEST(every_strategy_visits_every_pixel_once) {
    for (const auto& dim : kDims) {
        ImageU8 in(dim[0], dim[1]);
        ImageF32 out = make_output(in, Mapping::Identity);
        const Rect r = full_rect(in);
        CHECK(exactly_once_in_rect(record<IdentityMap>(S::Row, in, out, r), in, r));
        CHECK(exactly_once_in_rect(record<IdentityMap>(S::Col, in, out, r), in, r));
        CHECK(exactly_once_in_rect(record<IdentityMap>(S::Morton, in, out, r), in, r));
        for (TileSize t : kTiles) CHECK(exactly_once_in_rect(record<IdentityMap>(S::Tiled, in, out, r, t), in, r));
    }
}

CV_TEST(sub_regions_and_incomplete_tiles) {
    ImageU8 in(53, 41);
    ImageF32 out = make_output(in, Mapping::Identity);
    const Rect regions[] = {{0, 0, 53, 41}, {5, 3, 50, 40}, {0, 0, 1, 41}, {52, 0, 53, 41}, {10, 10, 10, 20},
                            {7, 9, 8, 10}};
    for (Rect r : regions) {
        CHECK(exactly_once_in_rect(record<IdentityMap>(S::Row, in, out, r), in, r));
        CHECK(exactly_once_in_rect(record<IdentityMap>(S::Col, in, out, r), in, r));
        CHECK(exactly_once_in_rect(record<IdentityMap>(S::Morton, in, out, r), in, r));
        for (TileSize t : kTiles) CHECK(exactly_once_in_rect(record<IdentityMap>(S::Tiled, in, out, r, t), in, r));
    }
}

CV_TEST(morton_order_matches_definition) {
    // On a power-of-two square the visiting order must be exactly increasing
    // Morton code (x in even bits).
    ImageU8 in(16, 16);
    ImageF32 out = make_output(in, Mapping::Identity);
    const Recorder rec = record<IdentityMap>(S::Morton, in, out, full_rect(in));
    CHECK(rec.order.size() == 256);
    for (std::size_t i = 0; i < rec.order.size(); ++i)
        CHECK(morton_encode(std::uint32_t(rec.order[i].first), std::uint32_t(rec.order[i].second)) == i);
    // First 2x2 quad is the "Z": (0,0) (1,0) (0,1) (1,1).
    CHECK(rec.order[1] == std::make_pair(1, 0));
    CHECK(rec.order[2] == std::make_pair(0, 1));
    CHECK(rec.order[3] == std::make_pair(1, 1));
}

CV_TEST(morton_rectangular_order_is_monotone) {
    // For any rectangle the visited pixels must appear in strictly increasing
    // Morton order (the bounding-square order restricted to the rectangle).
    const int dims[][2] = {{4096, 3}, {3, 4096}, {100, 37}, {37, 100}, {1, 1}, {1, 1000}, {513, 257}};
    for (const auto& dim : dims) {
        ImageU8 in(dim[0], dim[1]);
        ImageF32 out = make_output(in, Mapping::Identity);
        const Recorder rec = record<IdentityMap>(S::Morton, in, out, full_rect(in));
        CHECK(exactly_once_in_rect(rec, in, full_rect(in)));
        bool monotone = true;
        for (std::size_t i = 1; i < rec.order.size(); ++i)
            if (morton_encode(rec.order[i - 1].first, rec.order[i - 1].second) >=
                morton_encode(rec.order[i].first, rec.order[i].second))
                monotone = false;
        CHECK(monotone);
    }
}

CV_TEST(morton_bit_helpers) {
    for (std::uint32_t x : {0u, 1u, 2u, 3u, 1023u, 65535u, 123456u})
        for (std::uint32_t y : {0u, 1u, 5u, 777u, 65535u, 654321u}) {
            const std::uint64_t m = morton_encode(x, y);
            CHECK(morton_x(m) == x);
            CHECK(morton_y(m) == y);
        }
    CHECK(ceil_log2(1) == 0);
    CHECK(ceil_log2(2) == 1);
    CHECK(ceil_log2(3) == 2);
    CHECK(ceil_log2(4096) == 12);
    CHECK(ceil_log2(4097) == 13);
}

CV_TEST(tiled_order_is_tile_by_tile) {
    ImageU8 in(10, 7);
    ImageF32 out = make_output(in, Mapping::Identity);
    const Recorder rec = record<IdentityMap>(S::Tiled, in, out, full_rect(in), TileSize{4, 3});
    // Tile index (tx, ty) must be non-decreasing in row-major tile order, and
    // inside a tile the pixels are row-major.
    int last_tile = -1;
    bool ok = true;
    for (std::size_t i = 0; i < rec.order.size(); ++i) {
        const int tile = (rec.order[i].second / 3) * 3 + rec.order[i].first / 4;
        if (tile < last_tile) ok = false;
        last_tile = tile;
    }
    CHECK(ok);
    CHECK(rec.order.front() == std::make_pair(0, 0));
    CHECK(rec.order[4] == std::make_pair(0, 1));  // second row of the first 4x3 tile
    CHECK(rec.order.back() == std::make_pair(9, 6));
}

CV_TEST(rotate90_mapping_is_a_bijection) {
    for (const auto& dim : kDims) {
        ImageU8 in(dim[0], dim[1]);
        ImageF32 out = make_output(in, Mapping::Rotate90);
        CHECK(out.width == in.height && out.height == in.width);
        for (S s : {S::Row, S::Col, S::Morton, S::Tiled}) {
            const Recorder rec = record<Rotate90Map>(s, in, out, full_rect(in), TileSize{8, 8});
            std::vector<int> hit(std::size_t(out.width) * out.height, 0);
            bool ok = true;
            for (std::size_t i = 0; i < rec.order.size(); ++i) {
                const auto [x, y] = rec.order[i];
                const std::size_t expect = std::size_t(x) * out.width + std::size_t(out.width - 1 - y);
                if (rec.dst_index[i] != expect) ok = false;
                hit[rec.dst_index[i]]++;
            }
            CHECK(ok);
            CHECK(std::all_of(hit.begin(), hit.end(), [](int h) { return h == 1; }));
        }
    }
}

CV_TEST(names_round_trip) {
    for (Strategy s : {Strategy::RowMajor, Strategy::ColumnMajor, Strategy::Tiled, Strategy::Morton, Strategy::Adaptive}) {
        Strategy b;
        CHECK(parse_strategy(to_string(s), b) && b == s);
    }
    Mapping m;
    CHECK(parse_mapping("identity", m) && m == Mapping::Identity);
    CHECK(parse_mapping("rotate90", m) && m == Mapping::Rotate90);
    CHECK(!parse_mapping("flip", m));
}

CV_TEST_MAIN()
