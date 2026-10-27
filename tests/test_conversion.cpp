// Conversion kernels vs. hand-computed values and vs. the independent float64
// reference implementations.
#include <cstdint>
#include <random>

#include "color_conversion.hpp"
#include "test_util.hpp"

using namespace cachevision;

namespace {
template <class K>
void run_kernel(const std::uint8_t rgb[3], float out[3]) {
    K k;
    k(rgb, out);
}
void kernel(Op op, const std::uint8_t rgb[3], float out[3]) {
    switch (op) {
        case Op::Unpack: run_kernel<UnpackKernel>(rgb, out); break;
        case Op::YUV: run_kernel<YuvKernel>(rgb, out); break;
        case Op::HSV: run_kernel<HsvKernel>(rgb, out); break;
        case Op::Lab: run_kernel<LabKernel>(rgb, out); break;
        default: break;
    }
}
}  // namespace

CV_TEST(yuv_known_values) {
    const std::uint8_t white[3] = {255, 255, 255}, black[3] = {0, 0, 0}, red[3] = {255, 0, 0}, blue[3] = {0, 0, 255};
    float o[3];
    kernel(Op::YUV, white, o);
    CHECK_NEAR(o[0], 1.0, 1e-6);
    CHECK_NEAR(o[1], 0.5, 1e-6);
    CHECK_NEAR(o[2], 0.5, 1e-6);
    kernel(Op::YUV, black, o);
    CHECK_NEAR(o[0], 0.0, 1e-7);
    CHECK_NEAR(o[1], 0.5, 1e-7);
    CHECK_NEAR(o[2], 0.5, 1e-7);
    kernel(Op::YUV, red, o);  // Y = .299, U = .492(0-.299)+.5, V = .877(1-.299)+.5
    CHECK_NEAR(o[0], 0.299, 1e-6);
    CHECK_NEAR(o[1], 0.492 * -0.299 + 0.5, 1e-6);
    CHECK_NEAR(o[2], 0.877 * 0.701 + 0.5, 1e-6);
    kernel(Op::YUV, blue, o);
    CHECK_NEAR(o[0], 0.114, 1e-6);
    CHECK_NEAR(o[1], 0.492 * 0.886 + 0.5, 1e-6);
}

CV_TEST(hsv_known_values) {
    struct Case { std::uint8_t rgb[3]; double h, s, v; } cases[] = {
        {{255, 0, 0}, 0, 1, 1},       {{0, 255, 0}, 120, 1, 1},   {{0, 0, 255}, 240, 1, 1},
        {{255, 255, 0}, 60, 1, 1},    {{0, 255, 255}, 180, 1, 1}, {{255, 0, 255}, 300, 1, 1},
        {{128, 128, 128}, 0, 0, 128 / 255.0}, {{0, 0, 0}, 0, 0, 0}, {{255, 255, 255}, 0, 0, 1},
        {{255, 0, 1}, 360.0 - 60.0 / 255.0, 1, 1},  // just below 360: wrap of negative hue
        {{255, 128, 0}, 60.0 * 128 / 255.0, 1, 1},
    };
    for (const auto& c : cases) {
        float o[3];
        kernel(Op::HSV, c.rgb, o);
        CHECK_NEAR(o[0], c.h, 1e-3);
        CHECK_NEAR(o[1], c.s, 1e-6);
        CHECK_NEAR(o[2], c.v, 1e-6);
        CHECK(o[0] >= 0.0f && o[0] < 360.0f);
    }
}

CV_TEST(lab_known_values) {
    // Reference values: CIE L*a*b* of sRGB primaries under D65 (standard tables,
    // e.g. Lindbloom's calculator with the same sRGB matrix / D65 white).
    struct Case { std::uint8_t rgb[3]; double L, a, b; } cases[] = {
        {{255, 255, 255}, 100.0, 0.0, 0.0},
        {{0, 0, 0}, 0.0, 0.0, 0.0},
        {{255, 0, 0}, 53.2408, 80.0925, 67.2032},
        {{0, 255, 0}, 87.7347, -86.1827, 83.1793},
        {{0, 0, 255}, 32.2970, 79.1875, -107.8602},
        {{128, 128, 128}, 53.5850, 0.0, 0.0},
    };
    for (const auto& c : cases) {
        float o[3];
        kernel(Op::Lab, c.rgb, o);
        CHECK_NEAR(o[0], c.L, 0.02);
        CHECK_NEAR(o[1], c.a, 0.05);
        CHECK_NEAR(o[2], c.b, 0.05);
    }
}

CV_TEST(srgb_table_matches_pow) {
    for (int i = 0; i < 256; ++i) {
        const double c = i / 255.0;
        const double lin = c <= 0.04045 ? c / 12.92 : std::pow((c + 0.055) / 1.055, 2.4);
        CHECK_NEAR(kSrgbToLinear[i], lin, 1e-7);
    }
}

// Every kernel against the float64 reference over all 2^24 colours would take
// a while; a dense random sample plus the full grey axis and all corners is
// used instead. Tolerances reflect float32 arithmetic on values of that range:
//  * hue = 60 (g-b)/c amplifies the ~1e-7 rounding of the normalised inputs
//    by 1/c; for the smallest non-zero chroma (c = 1/255) that is ~3e-5
//    relative, i.e. up to ~2e-3 degrees once the 120/240 offsets are added.
//  * Lab: cbrt and the 500x / 200x scale factors amplify float32 rounding.
CV_TEST(kernels_match_float64_reference) {
    std::mt19937 rng(7);
    std::uniform_int_distribution<int> d(0, 255);
    struct Tol { Op op; double t[3]; } tols[] = {
        {Op::Unpack, {1e-7, 1e-7, 1e-7}},
        {Op::YUV, {2e-7, 2e-7, 2e-7}},
        {Op::HSV, {2e-3, 1e-6, 1e-7}},   // hue in degrees
        {Op::Lab, {2e-4, 5e-4, 5e-4}},   // L in [0,100], a/b ~ +-100
    };
    double worst[4][3] = {};
    for (int n = 0; n < 200000 + 256 + 8; ++n) {
        std::uint8_t rgb[3];
        if (n < 256) rgb[0] = rgb[1] = rgb[2] = std::uint8_t(n);
        else if (n < 264) { for (int c = 0; c < 3; ++c) rgb[c] = ((n - 256) >> c) & 1 ? 255 : 0; }
        else for (auto& c : rgb) c = std::uint8_t(d(rng));
        for (int t = 0; t < 4; ++t) {
            float o[3] = {};
            double r[3];
            kernel(tols[t].op, rgb, o);
            reference_convert(tols[t].op, rgb, r);
            for (int c = 0; c < 3; ++c) {
                double err = std::fabs(o[c] - r[c]);
                if (tols[t].op == Op::HSV && c == 0) err = std::fmin(err, 360.0 - err);  // circular hue
                if (err > worst[t][c]) worst[t][c] = err;
            }
        }
    }
    for (int t = 0; t < 4; ++t) {
        std::fprintf(stderr, "    %-6s max |err| vs float64: %.3g %.3g %.3g\n", to_string(tols[t].op), worst[t][0],
                     worst[t][1], worst[t][2]);
        for (int c = 0; c < 3; ++c) CHECK(worst[t][c] <= tols[t].t[c]);
    }
}

CV_TEST(op_names_round_trip) {
    for (Op op : {Op::IndexOnly, Op::Unpack, Op::YUV, Op::HSV, Op::Lab}) {
        Op back;
        CHECK(parse_op(to_string(op), back));
        CHECK(back == op);
    }
    Op dummy;
    CHECK(!parse_op("rgb2xyz", dummy));
}

CV_TEST_MAIN()
