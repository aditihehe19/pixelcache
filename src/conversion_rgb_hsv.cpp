// RGB -> HSV (hexcone). Kernel: HsvKernel in color_conversion.hpp.
// H in degrees [0, 360), S and V in [0, 1]. Achromatic pixels (max == min)
// get H = 0 and S = 0; black gets S = 0.
#include <algorithm>

#include "color_conversion.hpp"

namespace cachevision {

void reference_hsv(const std::uint8_t rgb[3], double out[3]) {
    const double r = rgb[0] / 255.0, g = rgb[1] / 255.0, b = rgb[2] / 255.0;
    const double v = std::max({r, g, b});
    const double mn = std::min({r, g, b});
    const double c = v - mn;
    double h = 0.0;
    if (c > 0.0) {
        // Ties resolve R, then G, then B, matching the kernel.
        if (v == r) h = 60.0 * (g - b) / c;
        else if (v == g) h = 60.0 * (b - r) / c + 120.0;
        else h = 60.0 * (r - g) / c + 240.0;
        if (h < 0.0) h += 360.0;
    }
    out[0] = h;
    out[1] = v > 0.0 ? c / v : 0.0;
    out[2] = v;
}

}  // namespace cachevision
