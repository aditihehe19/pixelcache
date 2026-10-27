// Adaptive tile selection: analytical model + optional on-line calibration.
// See include/adaptive.hpp for the model description.
#include "adaptive.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <numeric>
#include <sstream>

namespace cachevision {

CacheGeometry geometry_from(const SystemInfo& s) {
    CacheGeometry g;
    const CacheLevelInfo* l1 = nullptr;
    const CacheLevelInfo* l2 = nullptr;
    for (const auto& c : s.caches) {
        if (c.source.rfind("cpuid", 0) != 0 || c.type == "instruction") continue;
        if (c.level == 1 && !l1) l1 = &c;
        if (c.level == 2 && !l2) l2 = &c;
    }
    if (l1 && l2 && l1->ways > 0 && l2->ways > 0) {
        g.l1d_bytes = l1->size_bytes;
        g.l1_ways = l1->ways;
        g.l1_sets = l1->sets;
        g.l2_bytes = l2->size_bytes;
        g.l2_ways = l2->ways;
        g.l2_sets = l2->sets;
        g.line_bytes = l1->line_bytes;
        g.from_cpuid = true;
    }
    for (const auto& t : s.tlbs) {
        if (t.level == 1 && (t.type == "data" || t.type == "load") && t.page_sizes.find("4K") != std::string::npos) {
            g.dtlb_entries = t.entries;
            g.dtlb_from_cpuid = true;
            break;
        }
    }
    return g;
}

namespace {

struct Stream {
    bool contiguous_along_x;
    double bpp;        // bytes per pixel of this stream
    double runs;       // contiguous runs per tile
    double run_bytes;  // bytes per run
    double pitch;      // bytes between consecutive runs
};

struct Level {
    double budget;  // usable capacity in bytes
    int sets, ways;
};

double pages_touched(const Stream& s, double page) {
    if (s.pitch >= page) return s.runs * (1.0 + s.run_bytes / page);
    return s.runs * s.pitch / page + 1.0;
}

// Lines of one stream that can be resident at once: runs are `pitch` bytes
// apart, so with modulo set indexing they reach sets / gcd(pitch/line, sets)
// distinct sets when the pitch is a whole number of lines.
double conflict_capacity_lines(const Level& lv, double pitch, int line) {
    const long long p = (long long)pitch;
    if (p <= 0 || p % line != 0) return double(lv.sets) * lv.ways;  // spreads over all sets
    const long long stride = p / line;
    const long long distinct = lv.sets / std::gcd(stride, (long long)lv.sets);
    return double(distinct) * lv.ways;
}

bool survives(const Level& lv, double live_lines, double pitch, int line, double reuse_bytes) {
    return reuse_bytes <= lv.budget && live_lines <= conflict_capacity_lines(lv, pitch, line);
}

}  // namespace

std::vector<TileCandidate> rank_tiles(int width, int height, Mapping mapping, const CacheGeometry& g,
                                      const AdaptiveModelParams& p) {
    std::vector<TileCandidate> out;
    if (width <= 0 || height <= 0) return out;
    const int tws[] = {8, 16, 32, 64, 128, 256, 512, 1024, width};
    const int ths[] = {1, 2, 4, 8, 16, 32, 64, 128, 256};
    const double W = width, H = height, page = g.page_bytes;
    const int L = g.line_bytes;
    const Level levels[2] = {{p.l1_budget_fraction * double(g.l1d_bytes), g.l1_sets, g.l1_ways},
                             {p.l2_budget_fraction * double(g.l2_bytes), g.l2_sets, g.l2_ways}};
    const double weight[2] = {p.w_l1, p.w_l2};

    for (int tw0 : tws) {
        for (int th0 : ths) {
            const int tw = std::min(tw0, width), th = std::min(th0, height);
            const bool dup = std::any_of(out.begin(), out.end(), [&](const TileCandidate& c) {
                return c.tile.w == tw && c.tile.h == th;
            });
            if (dup) continue;

            const Stream in{true, 3.0, double(th), tw * 3.0, W * 3.0};
            const Stream os = mapping == Mapping::Identity ? Stream{true, 12.0, double(th), tw * 12.0, W * 12.0}
                                                           : Stream{false, 12.0, double(tw), th * 12.0, H * 12.0};
            const Stream streams[2] = {in, os};

            double footprint = 0.0, row_bytes = 0.0;  // per tile / per tile row
            for (const auto& s : streams) {
                footprint += s.runs * (s.run_bytes + L);
                row_bytes += s.contiguous_along_x ? (tw * s.bpp + L) : s.runs * L;
            }
            const double tiles_per_band = std::ceil(W / tw);
            const double px = double(tw) * double(th);

            double cost = p.w_loop / tw;  // one inner loop per tile row segment
            double pages = 0.0;
            for (const auto& s : streams) {
                for (int l = 0; l < 2; ++l) {
                    if (!s.contiguous_along_x &&
                        !survives(levels[l], s.runs, s.pitch, L, row_bytes)) {
                        cost += weight[l] * (1.0 - s.bpp / L);  // every access misses at this level
                        continue;
                    }
                    const double reuse = s.contiguous_along_x ? footprint : footprint * tiles_per_band;
                    if (!survives(levels[l], s.runs, s.pitch, L, reuse)) cost += weight[l] * s.runs / px;
                }
                pages += pages_touched(s, page);
            }
            if (pages > g.dtlb_entries) cost += p.w_tlb * pages / px;

            TileCandidate c;
            c.tile = TileSize{tw, th};
            c.model_cost = cost;
            c.footprint_bytes = footprint;
            out.push_back(c);
        }
    }
    std::stable_sort(out.begin(), out.end(), [](const TileCandidate& a, const TileCandidate& b) {
        if (a.model_cost != b.model_cost) return a.model_cost < b.model_cost;
        if (a.tile.w != b.tile.w) return a.tile.w > b.tile.w;  // prefer longer runs
        return a.tile.h > b.tile.h;
    });
    return out;
}

AdaptiveDecision choose_tile(const ImageU8& in, const ImageF32& out, Op op, Mapping mapping, const CacheGeometry& g,
                             bool calibrate, const AdaptiveModelParams& p) {
    using clk = std::chrono::steady_clock;
    AdaptiveDecision d;
    const auto t0 = clk::now();
    d.ranked = rank_tiles(in.width, in.height, mapping, g, p);
    d.model_ms = std::chrono::duration<double, std::milli>(clk::now() - t0).count();
    if (d.ranked.empty()) {
        d.chosen = TileSize{1, 1};
        return d;
    }
    d.chosen = d.ranked.front().tile;
    if (!calibrate) return d;

    // Candidate set: model top-K plus the full-width tile (row-major order),
    // so calibration can always fall back to the baseline.
    std::vector<std::size_t> idx;
    for (std::size_t i = 0; i < d.ranked.size() && int(idx.size()) < p.top_k; ++i) idx.push_back(i);
    for (std::size_t i = 0; i < d.ranked.size(); ++i)
        if (d.ranked[i].tile.w == in.width && d.ranked[i].tile.h == 1 &&
            std::find(idx.begin(), idx.end(), i) == idx.end())
            idx.push_back(i);

    // Calibration band: full width (keeps every stride identical to the real
    // run), about 1 Mpixel tall, and at least as tall as the tallest candidate.
    int rows = int(std::ceil((1 << 20) / double(in.width)));
    for (std::size_t i : idx) rows = std::max(rows, d.ranked[i].tile.h);
    rows = std::max(1, std::min(rows, in.height));
    d.calib_rows = rows;
    const Rect band{0, 0, in.width, rows};
    const double band_px = double(in.width) * rows;

    const auto c0 = clk::now();
    double best = 1e300;
    for (std::size_t i : idx) {
        TraversalArgs a;
        a.op = op;
        a.mapping = mapping;
        a.tile = d.ranked[i].tile;
        run_tiled(in, out, band, a);  // warm-up
        double samples[3];
        for (double& s : samples) {
            const auto s0 = clk::now();
            run_tiled(in, out, band, a);
            s = std::chrono::duration<double, std::nano>(clk::now() - s0).count();
        }
        std::sort(samples, samples + 3);
        d.ranked[i].calib_ns_per_px = samples[1] / band_px;
        if (d.ranked[i].calib_ns_per_px < best) {
            best = d.ranked[i].calib_ns_per_px;
            d.chosen = d.ranked[i].tile;
        }
    }
    d.calib_ms = std::chrono::duration<double, std::milli>(clk::now() - c0).count();
    d.calibrated = true;
    return d;
}

std::string AdaptiveDecision::describe() const {
    std::ostringstream o;
    o << chosen.w << "x" << chosen.h << (calibrated ? " (calibrated on " : " (model only")
      << (calibrated ? std::to_string(calib_rows) + " rows" : "") << "; candidates:";
    int shown = 0;
    for (const auto& c : ranked) {
        if (!calibrated && shown >= 4) break;
        if (calibrated && c.calib_ns_per_px < 0) continue;
        o << " " << c.tile.w << "x" << c.tile.h << "[m=" << c.model_cost;
        if (c.calib_ns_per_px >= 0) o << ",t=" << c.calib_ns_per_px << "ns";
        o << "]";
        ++shown;
    }
    o << ")";
    return o.str();
}

}  // namespace cachevision
