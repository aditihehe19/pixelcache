#include "image_types.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <new>
#include <utility>

#if defined(_WIN32)
#include <malloc.h>
#endif

namespace cachevision {

// ---- AlignedBuffer -------------------------------------------------------------

AlignedBuffer::AlignedBuffer(std::size_t bytes, std::size_t alignment) : bytes_(bytes) {
    if (bytes == 0) return;
#if defined(_WIN32)
    ptr_ = _aligned_malloc(bytes, alignment);
#else
    if (posix_memalign(&ptr_, alignment, bytes) != 0) ptr_ = nullptr;
#endif
    if (!ptr_) throw std::bad_alloc();
}

AlignedBuffer::~AlignedBuffer() { release(); }

AlignedBuffer::AlignedBuffer(AlignedBuffer&& o) noexcept : ptr_(o.ptr_), bytes_(o.bytes_) {
    o.ptr_ = nullptr;
    o.bytes_ = 0;
}

AlignedBuffer& AlignedBuffer::operator=(AlignedBuffer&& o) noexcept {
    if (this != &o) {
        release();
        ptr_ = o.ptr_;
        bytes_ = o.bytes_;
        o.ptr_ = nullptr;
        o.bytes_ = 0;
    }
    return *this;
}

void AlignedBuffer::release() {
    if (!ptr_) return;
#if defined(_WIN32)
    _aligned_free(ptr_);
#else
    std::free(ptr_);
#endif
    ptr_ = nullptr;
    bytes_ = 0;
}

// ---- images --------------------------------------------------------------------

void validate_dimensions(int width, int height, std::size_t bytes_per_pixel) {
    if (width < 0 || height < 0) throw std::invalid_argument("image dimensions must be non-negative");
    const std::int64_t px = std::int64_t(width) * std::int64_t(height);
    if (px > kMaxPixels) throw std::length_error("image exceeds kMaxPixels");
    if (bytes_per_pixel && std::uint64_t(px) > std::numeric_limits<std::size_t>::max() / bytes_per_pixel)
        throw std::length_error("image byte size overflows size_t");
}

ImageU8::ImageU8(int w, int h) {
    validate_dimensions(w, h, 3);
    width = w;
    height = h;
    stride = std::size_t(w) * 3;
    if (!empty()) {
        storage = AlignedBuffer(bytes());
        data = static_cast<std::uint8_t*>(storage.data());
        std::memset(data, 0, bytes());
    }
}

ImageF32::ImageF32(int w, int h) {
    validate_dimensions(w, h, 3 * sizeof(float));
    width = w;
    height = h;
    stride = std::size_t(w) * 3;
    if (!empty()) {
        storage = AlignedBuffer(bytes());
        data = static_cast<float*>(storage.data());
        std::memset(data, 0, bytes());
    }
}

// ---- synthetic workloads -------------------------------------------------------

const char* to_string(SyntheticKind k) {
    switch (k) {
        case SyntheticKind::Gradient: return "gradient";
        case SyntheticKind::Noise: return "noise";
        case SyntheticKind::Mixed: return "mixed";
    }
    return "?";
}

bool parse_synthetic_kind(const std::string& s, SyntheticKind& out) {
    if (s == "gradient") { out = SyntheticKind::Gradient; return true; }
    if (s == "noise") { out = SyntheticKind::Noise; return true; }
    if (s == "mixed") { out = SyntheticKind::Mixed; return true; }
    return false;
}

namespace {
// SplitMix64 finaliser used as a position hash, so noise depends only on
// (seed, x, y) and not on generation order or image size.
inline std::uint64_t mix(std::uint64_t z) {
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}
}  // namespace

ImageU8 make_synthetic(SyntheticKind kind, int width, int height, std::uint64_t seed) {
    ImageU8 img(width, height);
    const double iw = width > 1 ? 1.0 / (width - 1) : 0.0;
    const double ih = height > 1 ? 1.0 / (height - 1) : 0.0;
    for (int y = 0; y < height; ++y) {
        std::uint8_t* p = img.row(y);
        for (int x = 0; x < width; ++x, p += 3) {
            const double u = x * iw, v = y * ih;
            const std::uint64_t h = mix(seed ^ (std::uint64_t(y) << 32 | std::uint32_t(x)));
            switch (kind) {
                case SyntheticKind::Gradient:
                    p[0] = std::uint8_t(255.0 * u + 0.5);
                    p[1] = std::uint8_t(255.0 * v + 0.5);
                    p[2] = std::uint8_t(255.0 * (1.0 - 0.5 * (u + v)) + 0.5);
                    break;
                case SyntheticKind::Noise:
                    p[0] = std::uint8_t(h);
                    p[1] = std::uint8_t(h >> 8);
                    p[2] = std::uint8_t(h >> 16);
                    break;
                case SyntheticKind::Mixed: {
                    // Smooth background, 32 px checker texture, and 64 px noisy
                    // patches on a sparse pseudo-random subset of 64x64 cells.
                    double r = 200.0 * u + 30.0, g = 180.0 * v + 40.0, b = 120.0 + 100.0 * (u - v);
                    if (((x >> 5) + (y >> 5)) & 1) { r *= 0.6; g *= 0.6; b *= 0.6; }
                    const std::uint64_t cell = mix(seed + (std::uint64_t(y >> 6) << 32 | std::uint32_t(x >> 6)));
                    if ((cell & 7) == 0) {
                        r = double(h & 255);
                        g = double((h >> 8) & 255);
                        b = double((h >> 16) & 255);
                    }
                    auto clamp8 = [](double c) { return std::uint8_t(c < 0 ? 0 : c > 255 ? 255 : c + 0.5); };
                    p[0] = clamp8(r);
                    p[1] = clamp8(g);
                    p[2] = clamp8(b);
                    break;
                }
            }
        }
    }
    return img;
}

// ---- PPM I/O -------------------------------------------------------------------

namespace {
void skip_ws_and_comments(std::istream& is) {
    for (;;) {
        int c = is.peek();
        if (c == '#') {
            std::string line;
            std::getline(is, line);
        } else if (c == ' ' || c == '\n' || c == '\r' || c == '\t') {
            is.get();
        } else {
            return;
        }
    }
}
}  // namespace

ImageU8 load_ppm(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open " + path);
    std::string magic;
    f >> magic;
    if (magic != "P6") throw std::runtime_error(path + ": not a binary PPM (P6)");
    int w = 0, h = 0, maxval = 0;
    skip_ws_and_comments(f);
    f >> w;
    skip_ws_and_comments(f);
    f >> h;
    skip_ws_and_comments(f);
    f >> maxval;
    f.get();  // single whitespace before raster
    if (!f || w <= 0 || h <= 0 || maxval != 255) throw std::runtime_error(path + ": unsupported PPM header");
    ImageU8 img(w, h);
    f.read(reinterpret_cast<char*>(img.data), std::streamsize(img.bytes()));
    if (!f) throw std::runtime_error(path + ": truncated raster");
    return img;
}

void save_ppm(const std::string& path, const ImageU8& img) {
    std::ofstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot write " + path);
    f << "P6\n" << img.width << " " << img.height << "\n255\n";
    for (int y = 0; y < img.height; ++y)
        f.write(reinterpret_cast<const char*>(img.row(y)), std::streamsize(std::size_t(img.width) * 3));
}

// ---- hashing -------------------------------------------------------------------

namespace {
// FNV-1a style hash over 8-byte words (tail bytes individually). Used only to
// compare outputs of different strategies, not as a cryptographic digest.
inline std::uint64_t fnv1a(std::uint64_t h, const unsigned char* p, std::size_t n) {
    std::size_t i = 0;
    for (; i + 8 <= n; i += 8) {
        std::uint64_t w;
        std::memcpy(&w, p + i, 8);
        h ^= w;
        h *= 0x100000001B3ULL;
    }
    for (; i < n; ++i) {
        h ^= p[i];
        h *= 0x100000001B3ULL;
    }
    return h;
}
}  // namespace

std::uint64_t hash_image(const ImageF32& img) {
    std::uint64_t h = 0xCBF29CE484222325ULL;
    for (int y = 0; y < img.height; ++y)
        h = fnv1a(h, reinterpret_cast<const unsigned char*>(img.row(y)), std::size_t(img.width) * 3 * sizeof(float));
    return h;
}

std::uint64_t hash_image(const ImageU8& img) {
    std::uint64_t h = 0xCBF29CE484222325ULL;
    for (int y = 0; y < img.height; ++y) h = fnv1a(h, img.row(y), std::size_t(img.width) * 3);
    return h;
}

}  // namespace cachevision
