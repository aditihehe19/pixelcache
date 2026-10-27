// RGB -> YUV (BT.601 luma, analog-YUV chroma scale, +0.5 chroma offset).
// The per-pixel kernel lives in color_conversion.hpp (YuvKernel) so that it can
// be inlined into every traversal. This file holds the independent float64
// reference and the shared Op helpers.
#include <cstring>

#include "color_conversion.hpp"

namespace cachevision {

const char* to_string(Op op) {
    switch (op) {
        case Op::IndexOnly: return "index_only";
        case Op::Unpack: return "unpack";
        case Op::YUV: return "yuv";
        case Op::HSV: return "hsv";
        case Op::Lab: return "lab";
    }
    return "?";
}

bool parse_op(const char* s, Op& out) {
    static const struct { const char* name; Op op; } kOps[] = {
        {"index_only", Op::IndexOnly}, {"unpack", Op::Unpack}, {"yuv", Op::YUV},
        {"hsv", Op::HSV}, {"lab", Op::Lab},
    };
    for (const auto& e : kOps)
        if (std::strcmp(s, e.name) == 0) { out = e.op; return true; }
    return false;
}

void reference_unpack(const std::uint8_t rgb[3], double out[3]) {
    for (int c = 0; c < 3; ++c) out[c] = rgb[c] / 255.0;
}

void reference_yuv(const std::uint8_t rgb[3], double out[3]) {
    const double r = rgb[0] / 255.0, g = rgb[1] / 255.0, b = rgb[2] / 255.0;
    const double y = 0.299 * r + 0.587 * g + 0.114 * b;
    out[0] = y;
    out[1] = 0.492 * (b - y) + 0.5;
    out[2] = 0.877 * (r - y) + 0.5;
}

void reference_convert(Op op, const std::uint8_t rgb[3], double out[3]) {
    switch (op) {
        case Op::IndexOnly:
        case Op::Unpack: reference_unpack(rgb, out); return;
        case Op::YUV: reference_yuv(rgb, out); return;
        case Op::HSV: reference_hsv(rgb, out); return;
        case Op::Lab: reference_lab(rgb, out); return;
    }
}

}  // namespace cachevision
