// CacheVision - trace-driven cache/TLB simulator (MODEL, not measurement).
//
// Hardware counters are not readable on the development machine, so this
// simulator provides a complementary, clearly labelled model: it replays the
// exact address stream produced by the real traversal templates (same code,
// a recording kernel instead of a conversion kernel) through a
// set-associative, true-LRU, write-back, write-allocate hierarchy whose
// geometry is read from CPUID.
//
// Known simplifications (all reported alongside the results):
//   * no hardware prefetching (so sequential streams show compulsory misses
//     that real prefetchers largely hide),
//   * modulo set indexing on virtual addresses (real L2/L3 are physically
//     indexed and the L3 uses a slice hash),
//   * non-inclusive levels, no coherence traffic, no code/stack/LUT accesses,
//   * a TLB is modelled as a cache of 4 KiB page translations.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace cachevision {

struct SimLevelConfig {
    std::string name;
    std::uint64_t size_bytes = 0;
    int line_bytes = 64;  // page size for a TLB
    int ways = 8;         // -1 = fully associative
};

struct SimLevelStats {
    std::uint64_t accesses = 0;
    std::uint64_t misses = 0;
    std::uint64_t writebacks = 0;  // dirty evictions to the next level
};

class SimCache {
public:
    explicit SimCache(const SimLevelConfig& c);
    // Returns true on hit. On a miss the line is installed; if a dirty line is
    // evicted, `evicted_dirty` receives its line address and `had_dirty_victim`
    // is set. Only `demand` accesses are counted in accesses/misses
    // (write-backs from the level above are installs, not demand traffic).
    bool access(std::uint64_t line_addr, bool write, bool demand, bool& had_dirty_victim,
                std::uint64_t& evicted_dirty);
    const SimLevelConfig& config() const { return cfg_; }
    SimLevelStats stats;

private:
    SimLevelConfig cfg_;
    int ways_ = 1;
    std::uint64_t sets_ = 1;
    int line_shift_ = 6;
    std::vector<std::uint64_t> tags_;   // sets_ * ways_, ~0 = invalid
    std::vector<std::uint64_t> stamp_;  // LRU timestamps
    std::vector<std::uint8_t> dirty_;
    std::uint64_t clock_ = 0;
};

class SimHierarchy {
public:
    SimHierarchy(const std::vector<SimLevelConfig>& caches, const std::vector<SimLevelConfig>& tlbs);
    void read(std::uint64_t addr, std::uint32_t bytes) { access(addr, bytes, false); }
    void write(std::uint64_t addr, std::uint32_t bytes) { access(addr, bytes, true); }

    std::vector<SimCache> caches;  // L1 first
    std::vector<SimCache> tlbs;    // first-level first
    std::uint64_t dram_read_lines = 0, dram_write_lines = 0;

private:
    void access(std::uint64_t addr, std::uint32_t bytes, bool write);
    int line_shift_ = 6, page_shift_ = 12;
    void access_line(std::size_t level, std::uint64_t line, bool write);
    void writeback(std::size_t level, std::uint64_t line);
};

}  // namespace cachevision
