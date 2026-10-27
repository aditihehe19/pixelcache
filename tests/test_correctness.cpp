// End-to-end correctness: all traversal strategies produce bit-identical
// outputs, invalid input is rejected safely, adaptive selection is valid,
// and auxiliary pieces (PPM I/O, cache model) behave as specified.
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "adaptive.hpp"
#include "cache_sim.hpp"
#include "image_types.hpp"
#include "traversal.hpp"
#include "test_util.hpp"

using namespace cachevision;

namespace {

bool same_bits(const ImageF32& a, const ImageF32& b) {
    if (a.width != b.width || a.height != b.height) return false;
    for (int y = 0; y < a.height; ++y)
        if (std::memcmp(a.row(y), b.row(y), std::size_t(a.width) * 3 * sizeof(float)) != 0) return false;
    return true;
}

ImageF32 run(const ImageU8& in, Op op, Mapping m, Strategy s, TileSize t = {}) {
    ImageF32 out = make_output(in, m);
    TraversalArgs a;
    a.op = op;
    a.mapping = m;
    a.tile = t;
    const std::string err = convert(in, out, s, a);
    if (!err.empty()) std::fprintf(stderr, "convert error: %s\n", err.c_str());
    return out;
}

}  // namespace

CV_TEST(strategies_bit_identical) {
    // Bit-identical is the expected tolerance: every strategy evaluates the same
    // float32 expression per pixel, with FP contraction disabled at build time.
    const int dims[][2] = {{1, 1}, {13, 7}, {64, 64}, {100, 37}, {257, 129}};
    for (const auto& dim : dims)
        for (SyntheticKind kind : {SyntheticKind::Gradient, SyntheticKind::Noise, SyntheticKind::Mixed}) {
            const ImageU8 in = make_synthetic(kind, dim[0], dim[1]);
            for (Op op : {Op::Unpack, Op::YUV, Op::HSV, Op::Lab})
                for (Mapping m : {Mapping::Identity, Mapping::Rotate90}) {
                    const ImageF32 ref = run(in, op, m, Strategy::RowMajor);
                    CHECK(same_bits(ref, run(in, op, m, Strategy::ColumnMajor)));
                    CHECK(same_bits(ref, run(in, op, m, Strategy::Morton)));
                    for (TileSize t : {TileSize{8, 8}, TileSize{32, 32}, TileSize{5, 3}, TileSize{1000, 1}})
                        CHECK(same_bits(ref, run(in, op, m, Strategy::Tiled, t)));
                }
        }
}

CV_TEST(output_matches_reference_formulas) {
    const ImageU8 in = make_synthetic(SyntheticKind::Noise, 31, 17);
    for (Op op : {Op::Unpack, Op::YUV, Op::HSV, Op::Lab}) {
        const ImageF32 out = run(in, op, Mapping::Identity, Strategy::Morton);
        double worst = 0;
        for (int y = 0; y < in.height; ++y)
            for (int x = 0; x < in.width; ++x) {
                double ref[3];
                reference_convert(op, in.row(y) + 3 * x, ref);
                for (int c = 0; c < 3; ++c) {
                    double e = std::fabs(out.row(y)[3 * x + c] - ref[c]);
                    if (op == Op::HSV && c == 0) e = std::fmin(e, 360.0 - e);
                    worst = std::fmax(worst, e);
                }
            }
        CHECK(worst < (op == Op::Lab ? 1e-3 : op == Op::HSV ? 1e-3 : 1e-6));
    }
}

CV_TEST(rotate90_places_pixels_correctly) {
    const ImageU8 in = make_synthetic(SyntheticKind::Noise, 5, 3);
    const ImageF32 id = run(in, Op::Unpack, Mapping::Identity, Strategy::RowMajor);
    const ImageF32 rot = run(in, Op::Unpack, Mapping::Rotate90, Strategy::Tiled, {2, 2});
    CHECK(rot.width == 3 && rot.height == 5);
    for (int y = 0; y < in.height; ++y)
        for (int x = 0; x < in.width; ++x)
            for (int c = 0; c < 3; ++c)
                CHECK(rot.row(x)[3 * (rot.width - 1 - y) + c] == id.row(y)[3 * x + c]);
}

CV_TEST(empty_and_invalid_inputs) {
    ImageU8 empty;
    ImageF32 out_empty;
    TraversalArgs a;
    for (Strategy s : {Strategy::RowMajor, Strategy::ColumnMajor, Strategy::Tiled, Strategy::Morton})
        CHECK(convert(empty, out_empty, s, a).empty());  // no-op, no crash

    ImageU8 zero_w(0, 10), zero_h(10, 0);
    CHECK(zero_w.empty() && zero_w.data == nullptr);
    CHECK(zero_h.empty() && zero_h.data == nullptr);
    ImageF32 o0 = make_output(zero_w, Mapping::Identity);
    CHECK(convert(zero_w, o0, Strategy::Morton, a).empty());

    bool threw = false;
    try { ImageU8 bad(-1, 5); } catch (const std::invalid_argument&) { threw = true; }
    CHECK(threw);
    threw = false;
    try { ImageU8 huge(1 << 20, 1 << 20); } catch (const std::length_error&) { threw = true; }
    CHECK(threw);

    ImageU8 in(8, 4);
    ImageF32 wrong(8, 8);
    CHECK(!convert(in, wrong, Strategy::RowMajor, a).empty());  // size mismatch rejected
    ImageF32 ok = make_output(in, Mapping::Identity);
    a.tile = {0, 4};
    CHECK(!convert(in, ok, Strategy::Tiled, a).empty());        // bad tile rejected
    a.tile = {4, 4};
    a.mapping = Mapping::Rotate90;
    CHECK(!convert(in, ok, Strategy::Tiled, a).empty());        // rotate needs 4x8 output
    CHECK(!convert(in, ok, Strategy::Adaptive, a).empty());     // adaptive goes through choose_tile

    ImageU8 no_data;
    no_data.width = 4;
    no_data.height = 4;
    no_data.stride = 12;
    ImageF32 o44(4, 4);
    a.mapping = Mapping::Identity;
    CHECK(!convert(no_data, o44, Strategy::RowMajor, a).empty());  // null storage rejected
}

CV_TEST(adaptive_selection_is_valid_and_exact) {
    CacheGeometry g;  // documented defaults; selection must work without CPUID
    const int dims[][2] = {{1, 1}, {37, 5}, {300, 200}, {1920, 64}};
    for (const auto& dim : dims) {
        const ImageU8 in = make_synthetic(SyntheticKind::Mixed, dim[0], dim[1]);
        for (Mapping m : {Mapping::Identity, Mapping::Rotate90}) {
            ImageF32 out = make_output(in, m);
            for (bool calib : {false, true}) {
                const AdaptiveDecision d = choose_tile(in, out, Op::YUV, m, g, calib);
                CHECK(d.chosen.w >= 1 && d.chosen.w <= in.width);
                CHECK(d.chosen.h >= 1 && d.chosen.h <= in.height);
                CHECK(d.calibrated == calib);
                CHECK(!d.ranked.empty());
                CHECK(same_bits(run(in, Op::YUV, m, Strategy::RowMajor), run(in, Op::YUV, m, Strategy::Tiled, d.chosen)));
            }
        }
    }
}

CV_TEST(adaptive_model_prefers_blocking_only_when_strided) {
    // Not a performance claim: checks the model's qualitative logic. With both
    // streams contiguous along x, long runs are never worse; with a strided
    // output stream, the full-width tile must be ranked below some 2-D tile.
    CacheGeometry g;
    const auto id = rank_tiles(4096, 4096, Mapping::Identity, g);
    CHECK(id.front().tile.w >= 1024);
    const auto rot = rank_tiles(4096, 4096, Mapping::Rotate90, g);
    CHECK(rot.front().tile.h > 1 && rot.front().tile.w < 4096);
}

CV_TEST(ppm_round_trip_and_hash) {
    const ImageU8 a = make_synthetic(SyntheticKind::Mixed, 33, 21);
    const std::string path = "cachevision_test_roundtrip.ppm";
    save_ppm(path, a);
    const ImageU8 b = load_ppm(path);
    std::remove(path.c_str());
    CHECK(b.width == 33 && b.height == 21);
    CHECK(hash_image(a) == hash_image(b));
    const ImageU8 c = make_synthetic(SyntheticKind::Mixed, 33, 21, 999);
    CHECK(hash_image(a) != hash_image(c));
    bool threw = false;
    try { load_ppm("does_not_exist.ppm"); } catch (const std::runtime_error&) { threw = true; }
    CHECK(threw);
}

CV_TEST(synthetic_images_are_deterministic) {
    for (SyntheticKind k : {SyntheticKind::Gradient, SyntheticKind::Noise, SyntheticKind::Mixed})
        CHECK(hash_image(make_synthetic(k, 97, 53)) == hash_image(make_synthetic(k, 97, 53)));
}

CV_TEST(cache_model_compulsory_misses) {
    // A sequential stream of N bytes through an empty cache misses exactly
    // ceil(N / 64) times when it does not wrap around the cache.
    SimHierarchy h({{"L1D", 32768, 64, 8}, {"L2", 262144, 64, 8}}, {});
    for (std::uint64_t a = 0; a + 3 <= 16384; a += 3) h.read(a, 3);
    CHECK(h.caches[0].stats.misses == 16384 / 64);
    CHECK(h.caches[1].stats.misses == 16384 / 64);
    // Re-reading the same 16 KiB hits in L1.
    const auto before = h.caches[0].stats.misses;
    for (std::uint64_t a = 0; a < 16384; a += 64) h.read(a, 1);
    CHECK(h.caches[0].stats.misses == before);
    // Streaming 1 MiB through a 32 KiB L1 evicts the first lines (LRU).
    for (std::uint64_t a = 1 << 20; a < 2 << 20; a += 64) h.read(a, 1);
    const auto before2 = h.caches[0].stats.misses;
    h.read(0, 1);
    CHECK(h.caches[0].stats.misses == before2 + 1);
    // Dirty lines are written back when evicted.
    SimHierarchy w({{"L1D", 4096, 64, 4}}, {});
    for (std::uint64_t a = 0; a < 8192; a += 64) w.write(a, 64);
    CHECK(w.caches[0].stats.writebacks == 64);
    CHECK(w.dram_write_lines == 64);
}

CV_TEST_MAIN()
