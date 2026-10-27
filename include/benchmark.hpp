// CacheVision - benchmark harness.
//
// Timed region = exactly the traversal call (or `inner_iters` back-to-back
// calls for very short runs). Image generation/loading, output allocation,
// first-touch page faults (removed by an untimed warm-up run), hashing,
// adaptive tile selection, cache flushing and CSV I/O are all outside it.
#pragma once

#include <cstdint>
#include <fstream>
#include <string>
#include <vector>

#include "adaptive.hpp"
#include "image_types.hpp"
#include "traversal.hpp"

namespace cachevision {

enum class CacheCondition {
    Warm,     // no explicit flush; buffers were touched by the preceding run
    Flushed,  // CLFLUSH of every input and output line right before each run
};
const char* to_string(CacheCondition c);
bool parse_condition(const std::string& s, CacheCondition& out);

struct Variant {
    std::string label;  // e.g. "row_major", "tiled_32x32", "morton", "adaptive_calib"
    Strategy strategy = Strategy::RowMajor;
    TileSize tile{};
    bool adaptive_calibrate = false;  // only for Strategy::Adaptive
};
Variant make_variant(Strategy s, TileSize t = {}, bool calibrate = true);

struct Stats {
    double median = 0, mean = 0, min = 0, max = 0, stdev = 0, p25 = 0, p75 = 0;
};
Stats compute_stats(std::vector<double> v);

// Evict [p, p+bytes) from every cache level (CLFLUSH per line + MFENCE).
// Note: this does not flush TLBs or page-walk caches.
void flush_from_caches(const void* p, std::size_t bytes);

class CsvWriter {
public:
    CsvWriter() = default;
    bool open(const std::string& path, const std::vector<std::string>& header);
    void row(const std::vector<std::string>& cells);
    bool is_open() const { return f_.is_open(); }

private:
    std::ofstream f_;
    bool new_file_ = false;
};

std::string fmt(double v, int precision = 6);
std::string hex64(std::uint64_t v);

struct GroupSpec {
    std::string suite;
    std::string build_variant;
    std::string image_kind;
    Op op = Op::YUV;
    Mapping mapping = Mapping::Identity;
    std::vector<Variant> variants;
    std::vector<CacheCondition> conditions{CacheCondition::Warm};
    int reps = 11;
    double min_sample_ms = 5.0;  // warm runs shorter than this are repeated inside one sample
    std::uint64_t shuffle_seed = 12345;
};

struct VariantResult {
    Variant variant;
    TileSize effective_tile{};  // tile actually used (adaptive: the chosen one)
    CacheCondition condition = CacheCondition::Warm;
    int inner_iters = 1;
    std::vector<double> ms;    // per run, one entry per repetition
    std::vector<double> tsc;   // TSC ticks per run
    Stats stats;
    double setup_ms = 0.0;     // adaptive selection time (model + calibration)
    std::string setup_note;
    std::uint64_t output_hash = 0;
    bool matches_baseline = false;
    double core_ghz = 0.0;     // median of the effective-clock probes taken before each round
};

// Runs every (variant, condition) of a group with repetitions interleaved
// across variants in a shuffled order, so slow drifts (frequency, thermal,
// background load) affect all variants alike. `out` must have the mapped
// dimensions. Per-sample rows are appended to `samples` if it is open.
std::vector<VariantResult> run_group(const GroupSpec& g, const ImageU8& in, ImageF32& out,
                                     const CacheGeometry& geom, CsvWriter& samples);

// Column layout shared by run_group's summary rows and the analysis scripts.
std::vector<std::string> summary_header();
std::vector<std::string> summary_row(const GroupSpec& g, const ImageU8& in, const VariantResult& r);
std::vector<std::string> samples_header();

// ---- memory-hierarchy characterisation ---------------------------------------
// Read/write bandwidth and dependent-load latency as a function of working-set
// size. Writes rows: test,size_bytes,value,unit,reps.
void run_memory_characterisation(CsvWriter& out, const std::string& build_variant, std::uint64_t max_bytes,
                                 bool quick);

}  // namespace cachevision
