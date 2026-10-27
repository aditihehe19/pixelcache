// sRGB -> CIE L*a*b* (D65). Kernel: LabKernel in color_conversion.hpp.
//
// The sRGB transfer function is evaluated in float64 for each of the 256
// possible 8-bit codes and stored as float. For 8-bit input this is exact up
// to float rounding and turns a pow() per channel into one L1-resident load.
// The table is 1 KiB, identical for every traversal strategy.
#include <cmath>

#include "color_conversion.hpp"

namespace cachevision {

namespace {
double srgb_eotf(double c) { return c <= 0.04045 ? c / 12.92 : std::pow((c + 0.055) / 1.055, 2.4); }

struct SrgbTable {
    alignas(64) float v[256];
    SrgbTable() {
        for (int i = 0; i < 256; ++i) v[i] = float(srgb_eotf(i / 255.0));
    }
};
const SrgbTable g_srgb_table;
}  // namespace

const float* const kSrgbToLinear = g_srgb_table.v;

void reference_lab(const std::uint8_t rgb[3], double out[3]) {
    // Independent float64 path: pow() instead of the LUT, double matrix.
    const double r = srgb_eotf(rgb[0] / 255.0);
    const double g = srgb_eotf(rgb[1] / 255.0);
    const double b = srgb_eotf(rgb[2] / 255.0);
    const double X = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b;
    const double Y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b;
    const double Z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b;
    const double eps = 216.0 / 24389.0, kappa = 24389.0 / 27.0;
    auto f = [&](double t) { return t > eps ? std::cbrt(t) : (kappa * t + 16.0) / 116.0; };
    const double fx = f(X / 0.95047), fy = f(Y / 1.0), fz = f(Z / 1.08883);
    out[0] = 116.0 * fy - 16.0;
    out[1] = 500.0 * (fx - fy);
    out[2] = 200.0 * (fy - fz);
}

}  // namespace cachevision
