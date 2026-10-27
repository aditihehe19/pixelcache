#include "cache_sim.hpp"

#include <stdexcept>

namespace cachevision {

namespace {
int log2_exact(std::uint64_t v) {
    int k = 0;
    while ((std::uint64_t(1) << k) < v) ++k;
    if ((std::uint64_t(1) << k) != v) throw std::invalid_argument("line/page size must be a power of two");
    return k;
}
constexpr std::uint64_t kInvalid = ~std::uint64_t(0);
}  // namespace

SimCache::SimCache(const SimLevelConfig& c) : cfg_(c) {
    if (c.size_bytes == 0 || c.line_bytes <= 0) throw std::invalid_argument("bad cache config " + c.name);
    line_shift_ = log2_exact(std::uint64_t(c.line_bytes));
    const std::uint64_t lines = c.size_bytes / std::uint64_t(c.line_bytes);
    ways_ = c.ways < 0 ? int(lines) : c.ways;
    if (ways_ <= 0) throw std::invalid_argument("bad associativity for " + c.name);
    sets_ = lines / std::uint64_t(ways_);
    if (sets_ == 0) sets_ = 1;
    tags_.assign(sets_ * std::uint64_t(ways_), kInvalid);
    stamp_.assign(tags_.size(), 0);  // invalid ways keep stamp 0 and are chosen first
    dirty_.assign(tags_.size(), 0);
}

bool SimCache::access(std::uint64_t line_addr, bool write, bool demand, bool& had_dirty_victim,
                      std::uint64_t& evicted_dirty) {
    if (demand) ++stats.accesses;
    ++clock_;
    had_dirty_victim = false;
    const std::size_t base = std::size_t((line_addr % sets_) * std::uint64_t(ways_));
    std::size_t victim = base;
    std::uint64_t oldest = kInvalid;
    for (int w = 0; w < ways_; ++w) {
        const std::size_t i = base + std::size_t(w);
        if (tags_[i] == line_addr) {
            stamp_[i] = clock_;
            if (write) dirty_[i] = 1;
            return true;
        }
        if (stamp_[i] < oldest) {
            oldest = stamp_[i];
            victim = i;
        }
    }
    if (demand) ++stats.misses;
    if (tags_[victim] != kInvalid && dirty_[victim]) {
        had_dirty_victim = true;
        evicted_dirty = tags_[victim];
        ++stats.writebacks;
    }
    tags_[victim] = line_addr;
    stamp_[victim] = clock_;
    dirty_[victim] = write ? 1 : 0;
    return false;
}

SimHierarchy::SimHierarchy(const std::vector<SimLevelConfig>& c, const std::vector<SimLevelConfig>& t) {
    if (c.empty()) throw std::invalid_argument("need at least one cache level");
    for (const auto& x : c) caches.emplace_back(x);
    for (const auto& x : t) tlbs.emplace_back(x);
    for (std::size_t i = 1; i < caches.size(); ++i)
        if (caches[i].config().line_bytes != caches[0].config().line_bytes)
            throw std::invalid_argument("all cache levels must share one line size");
    line_shift_ = log2_exact(std::uint64_t(caches[0].config().line_bytes));
    if (!tlbs.empty()) page_shift_ = log2_exact(std::uint64_t(tlbs[0].config().line_bytes));
}

void SimHierarchy::writeback(std::size_t level, std::uint64_t line) {
    if (level >= caches.size()) {
        ++dram_write_lines;
        return;
    }
    // Full-line write from the level above: install dirty without a fill.
    bool dv = false;
    std::uint64_t ev = 0;
    caches[level].access(line, true, false, dv, ev);
    if (dv) writeback(level + 1, ev);
}

void SimHierarchy::access_line(std::size_t level, std::uint64_t line, bool write) {
    if (level >= caches.size()) {
        ++dram_read_lines;  // demand fill: reads and write-allocate (RFO) fills
        return;
    }
    bool dv = false;
    std::uint64_t ev = 0;
    const bool hit = caches[level].access(line, write && level == 0, true, dv, ev);
    if (dv) writeback(level + 1, ev);
    if (!hit) access_line(level + 1, line, false);
}

void SimHierarchy::access(std::uint64_t addr, std::uint32_t bytes, bool write) {
    if (bytes == 0) return;
    const std::uint64_t first = addr >> line_shift_, last = (addr + bytes - 1) >> line_shift_;
    for (std::uint64_t line = first; line <= last; ++line) {
        if (!tlbs.empty()) {  // translation (page granularity), then data
            const std::uint64_t page = (line << line_shift_) >> page_shift_;
            bool dv = false;
            std::uint64_t ev = 0;
            for (auto& t : tlbs)
                if (t.access(page, false, true, dv, ev)) break;
        }
        access_line(0, line, write);
    }
}

}  // namespace cachevision
