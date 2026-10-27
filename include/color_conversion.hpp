// CacheVision - colour-space conversion kernels.
//
// Every kernel maps ONE interleaved RGB888 pixel (s[0]=R, s[1]=G, s[2]=B) to
// ONE interleaved float32 triple d[0..2]. Kernels are header-only, stateless
// and `inline` so that each traversal strategy inlines exactly the same
// arithmetic; only the visiting order differs between strategies.
//
// Numeric policy (identical for every traversal strategy):
//   * Input is 8-bit; R,G,B are normalised to [0,1] as float(c) * (1/255).
//   * All arithmetic is IEEE-754 float32, no -ffast-math, and the build uses
//     -ffp-contract=off so a vectorised loop and a scalar loop perform the
//     same sequence of rounded operations. Outputs are therefore expected to
//     be bit-identical across traversal strategies (verified by tests).
//   * No rounding/clamping is applied to outputs (float output).
//
// Conventions (documented in docs/methodology.md, validated against OpenCV
// and an independent float64 NumPy implementation by scripts/validate_reference.py):
//
//   YUV  : BT.601 luma, "analog" YUV chroma scaling, chroma offset 0.5.
//          Y = 0.299 R + 0.587 G + 0.114 B
//          U = 0.492 (B - Y) + 0.5
//          V = 0.877 (R - Y) + 0.5
//          (same coefficient set as OpenCV COLOR_RGB2YUV for float input.)
//
//   HSV  : hexcone model. V = max(R,G,B), C = V - min(R,G,B),
//          S = C / V (0 when V == 0),
//          H in degrees [0,360): 0 when C == 0, otherwise
//            V==R: 60 (G-B)/C,  V==G: 60 (B-R)/C + 120,  else 60 (R-G)/C + 240,
//          negative H wrapped by +360. Ties resolve in the order R, G, B.
//
//   Lab  : CIE 1976 L*a*b* from sRGB (IEC 61966-2-1), D65 reference white.
//          1) sRGB EOTF:  c <= 0.04045 ? c/12.92 : ((c+0.055)/1.055)^2.4,
//             evaluated in float64 once per 8-bit code into a 256-entry
//             float LUT (exact for 8-bit input, ~1 KiB, stays L1 resident).
//          2) linear RGB -> XYZ with the sRGB/D65 matrix below.
//          3) normalise by white Xn=0.95047, Yn=1, Zn=1.08883.
//          4) f(t) = t > (6/29)^3 ? cbrt(t) : t/(3 (6/29)^2) + 4/29
//          5) L = 116 f(Y) - 16,  a = 500 (f(X)-f(Y)),  b = 200 (f(Y)-f(Z)).
//          L in [0,100]; a, b unbounded (about [-86, 98] and [-108, 94] for sRGB).
#pragma once

#include <cmath>
#include <cstdint>

namespace cachevision {

enum class Op {
    IndexOnly,  // traversal + address generation only; touches no pixel memory
    Unpack,     // RGB888 -> normalised float RGB (memory-bound reference kernel)
    YUV,
    HSV,
    Lab,
};

const char* to_string(Op op);
bool parse_op(const char* s, Op& out);

namespace coef {
constexpr float kInv255 = 1.0f / 255.0f;

constexpr float kYr = 0.299f, kYg = 0.587f, kYb = 0.114f;
constexpr float kU = 0.492f, kV = 0.877f, kChromaOffset = 0.5f;

// sRGB (linear) -> CIE XYZ, D65. IEC 61966-2-1 matrix.
constexpr float kM[3][3] = {
    {0.4124564f, 0.3575761f, 0.1804375f},
    {0.2126729f, 0.7151522f, 0.0721750f},
    {0.0193339f, 0.1191920f, 0.9503041f},
};
constexpr float kXn = 0.95047f, kYn = 1.0f, kZn = 1.08883f;
constexpr float kInvXn = 1.0f / kXn, kInvZn = 1.0f / kZn;
constexpr float kLabEps = 216.0f / 24389.0f;           // (6/29)^3
constexpr float kLabLinScale = 24389.0f / 27.0f / 116.0f;  // 1 / (3 (6/29)^2)
constexpr float kLabLinOffset = 16.0f / 116.0f;           // 4/29
}  // namespace coef

// 256-entry sRGB-code -> linear-light table (float64 evaluation, float storage).
extern const float* const kSrgbToLinear;

// ---- per-pixel kernels -------------------------------------------------------

struct UnpackKernel {
    inline void operator()(const std::uint8_t* s, float* d) const {
        d[0] = float(s[0]) * coef::kInv255;
        d[1] = float(s[1]) * coef::kInv255;
        d[2] = float(s[2]) * coef::kInv255;
    }
};

struct YuvKernel {
    inline void operator()(const std::uint8_t* s, float* d) const {
        const float r = float(s[0]) * coef::kInv255;
        const float g = float(s[1]) * coef::kInv255;
        const float b = float(s[2]) * coef::kInv255;
        const float y = coef::kYr * r + coef::kYg * g + coef::kYb * b;
        d[0] = y;
        d[1] = coef::kU * (b - y) + coef::kChromaOffset;
        d[2] = coef::kV * (r - y) + coef::kChromaOffset;
    }
};

struct HsvKernel {
    inline void operator()(const std::uint8_t* s, float* d) const {
        const float r = float(s[0]) * coef::kInv255;
        const float g = float(s[1]) * coef::kInv255;
        const float b = float(s[2]) * coef::kInv255;
        const float v = r > g ? (r > b ? r : b) : (g > b ? g : b);
        const float mn = r < g ? (r < b ? r : b) : (g < b ? g : b);
        const float c = v - mn;
        float h = 0.0f;
        if (c > 0.0f) {
            if (v == r)      h = 60.0f * (g - b) / c;
            else if (v == g) h = 60.0f * (b - r) / c + 120.0f;
            else             h = 60.0f * (r - g) / c + 240.0f;
            if (h < 0.0f) h += 360.0f;
        }
        d[0] = h;
        d[1] = v > 0.0f ? c / v : 0.0f;
        d[2] = v;
    }
};

inline float lab_f(float t) {
    return t > coef::kLabEps ? std::cbrt(t) : t * coef::kLabLinScale + coef::kLabLinOffset;
}

struct LabKernel {
    inline void operator()(const std::uint8_t* s, float* d) const {
        const float r = kSrgbToLinear[s[0]];
        const float g = kSrgbToLinear[s[1]];
        const float b = kSrgbToLinear[s[2]];
        const float x = (coef::kM[0][0] * r + coef::kM[0][1] * g + coef::kM[0][2] * b) * coef::kInvXn;
        const float y = (coef::kM[1][0] * r + coef::kM[1][1] * g + coef::kM[1][2] * b);
        const float z = (coef::kM[2][0] * r + coef::kM[2][1] * g + coef::kM[2][2] * b) * coef::kInvZn;
        const float fx = lab_f(x), fy = lab_f(y), fz = lab_f(z);
        d[0] = 116.0f * fy - 16.0f;
        d[1] = 500.0f * (fx - fy);
        d[2] = 200.0f * (fy - fz);
    }
};

// Address-generation-only kernel used to measure traversal overhead. It folds
// both addresses into an accumulator behind an optimisation barrier, so the
// loop cannot be removed or turned into a closed form, but no pixel memory is
// loaded or stored.
struct IndexOnlyKernel {
    std::uintptr_t acc = 0;
    inline void operator()(const std::uint8_t* s, float* d) {
        acc += reinterpret_cast<std::uintptr_t>(s) ^ reinterpret_cast<std::uintptr_t>(d);
#if defined(__GNUC__) || defined(__clang__)
        __asm__ volatile("" : "+r"(acc));
#endif
    }
};

// ---- independent float64 reference implementations (tests/validation) -------
// Straightforward transcriptions of the formulas above, written separately from
// the kernels (double precision, pow() instead of a LUT) so tests do not just
// compare a kernel against itself.
void reference_unpack(const std::uint8_t rgb[3], double out[3]);
void reference_yuv(const std::uint8_t rgb[3], double out[3]);
void reference_hsv(const std::uint8_t rgb[3], double out[3]);
void reference_lab(const std::uint8_t rgb[3], double out[3]);
void reference_convert(Op op, const std::uint8_t rgb[3], double out[3]);

}  // namespace cachevision
