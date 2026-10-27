// CacheVision - image containers.
//
// Layout conventions (used by every traversal strategy and every conversion):
//   * Input  : interleaved RGB, 8 bits per channel (RGB888), 3 bytes per pixel,
//              row-major, rows are `stride` bytes apart.
//   * Output : interleaved 3-channel float32 (12 bytes per pixel), row-major,
//              rows are `stride` floats apart.
// Buffers are allocated with 64-byte (cache-line) alignment so that row 0
// starts on a line boundary for every image. Rows are densely packed by
// default (stride == width * 3), so later rows are generally NOT line aligned;
// this is deliberate, it is the common layout of decoded images.
#pragma once

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>

namespace cachevision {

constexpr std::size_t kCacheLineBytes = 64;
constexpr int kChannels = 3;

// Owning, aligned, move-only byte buffer.
class AlignedBuffer {
public:
    AlignedBuffer() = default;
    explicit AlignedBuffer(std::size_t bytes, std::size_t alignment = kCacheLineBytes);
    ~AlignedBuffer();
    AlignedBuffer(const AlignedBuffer&) = delete;
    AlignedBuffer& operator=(const AlignedBuffer&) = delete;
    AlignedBuffer(AlignedBuffer&& other) noexcept;
    AlignedBuffer& operator=(AlignedBuffer&& other) noexcept;

    void* data() const { return ptr_; }
    std::size_t size() const { return bytes_; }

private:
    void release();
    void* ptr_ = nullptr;
    std::size_t bytes_ = 0;
};

// Throws std::invalid_argument for negative dimensions and std::length_error
// when width * height * bytes_per_pixel would overflow or exceed kMaxPixels.
constexpr std::int64_t kMaxPixels = std::int64_t(1) << 31;
void validate_dimensions(int width, int height, std::size_t bytes_per_pixel);

struct ImageU8 {
    int width = 0;
    int height = 0;
    std::size_t stride = 0;  // bytes between rows
    std::uint8_t* data = nullptr;
    AlignedBuffer storage;

    ImageU8() = default;
    ImageU8(int w, int h);  // dense rows, zero-initialised

    bool empty() const { return width == 0 || height == 0; }
    std::size_t bytes() const { return stride * std::size_t(height); }
    std::uint8_t* row(int y) const { return data + std::size_t(y) * stride; }
};

struct ImageF32 {
    int width = 0;
    int height = 0;
    std::size_t stride = 0;  // floats between rows
    float* data = nullptr;
    AlignedBuffer storage;

    ImageF32() = default;
    ImageF32(int w, int h);  // dense rows, zero-initialised

    bool empty() const { return width == 0 || height == 0; }
    std::size_t bytes() const { return stride * std::size_t(height) * sizeof(float); }
    float* row(int y) const { return data + std::size_t(y) * stride; }
};

// Half-open rectangle [x0, x1) x [y0, y1) in input-image coordinates.
struct Rect {
    int x0 = 0, y0 = 0, x1 = 0, y1 = 0;
    int width() const { return x1 - x0; }
    int height() const { return y1 - y0; }
    bool empty() const { return x1 <= x0 || y1 <= y0; }
};

inline Rect full_rect(const ImageU8& img) { return Rect{0, 0, img.width, img.height}; }

// ---- deterministic workloads -------------------------------------------------
// All synthetic generators are pure functions of (kind, width, height, seed).
enum class SyntheticKind {
    Gradient,  // smooth RGB ramps: highly coherent, branch-predictable
    Noise,     // uniform xorshift noise: incoherent, defeats branch prediction
    Mixed,     // gradient background + checker texture + noisy patches
};

const char* to_string(SyntheticKind k);
bool parse_synthetic_kind(const std::string& s, SyntheticKind& out);

ImageU8 make_synthetic(SyntheticKind kind, int width, int height, std::uint64_t seed = 0x5EEDC0FFEEULL);

// Binary PPM (P6, maxval 255). Throws std::runtime_error on failure.
ImageU8 load_ppm(const std::string& path);
void save_ppm(const std::string& path, const ImageU8& img);

// 64-bit FNV-1a-style hash over the pixel bytes of every row (padding excluded).
std::uint64_t hash_image(const ImageF32& img);
std::uint64_t hash_image(const ImageU8& img);

}  // namespace cachevision
