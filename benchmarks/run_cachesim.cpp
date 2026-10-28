// cachevision_sim - replays the address streams of every traversal through
// the trace-driven cache/TLB model (see include/cache_sim.hpp).
//
//   cachevision_sim --sizes 256,512,1024,2048,4096 --out results/raw
//   cachevision_sim --size 1920x1080 --mappings rotate90 --variants row_major,tiled:32x32,morton
//                   --l1 32:8 --l2 1024:16 --l3 16384:16 --out <dir>
//
// --sizes takes square edges; --size takes one WxH (either may be given).
// --variants filters the strategy list (default: row_major, column_major,
// morton, tiled 8..256, adaptive_model); tiled:WxH accepts any tile.
// --l1/--l2/--l3 KiB:ways replace the CPUID geometry for "what-if" studies
// (64-byte lines; the geometry file then reports source=custom).
//
// Output (cachesim.csv) is SIMULATED, not measured; every row carries
// source=model so it can never be confused with hardware counters.
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "adaptive.hpp"
#include "benchmark.hpp"
#include "cache_sim.hpp"
#include "system_info.hpp"
#include "traversal.hpp"

using namespace cachevision;

namespace {

constexpr std::uint64_t kInBase = 1ull << 32;   // synthetic, page-aligned base addresses
constexpr std::uint64_t kOutBase = 1ull << 40;

struct RecordKernel {
    SimHierarchy* h;
    std::uintptr_t in_base, out_base;
    void operator()(const std::uint8_t* s, float* d) {
        h->read(kInBase + (reinterpret_cast<std::uintptr_t>(s) - in_base), 3);
        h->write(kOutBase + (reinterpret_cast<std::uintptr_t>(d) - out_base), 12);
    }
};

struct SimVariant {
    std::string label;
    Strategy s;
    TileSize t;
};

template <class Map>
void replay(const SimVariant& v, const ImageU8& in, const ImageF32& out, RecordKernel& k) {
    const Rect r = full_rect(in);
    switch (v.s) {
        case Strategy::RowMajor: traverse_row_major<Map>(in, out, r, k); break;
        case Strategy::ColumnMajor: traverse_column_major<Map>(in, out, r, k); break;
        case Strategy::Tiled:
        case Strategy::Adaptive: traverse_tiled<Map>(in, out, r, v.t, k); break;
        case Strategy::Morton: traverse_morton<Map>(in, out, r, k); break;
    }
}

std::vector<std::string> split(const std::string& s) {
    std::vector<std::string> v;
    std::stringstream ss(s);
    std::string p;
    while (std::getline(ss, p, ','))
        if (!p.empty()) v.push_back(p);
    return v;
}

int usage(const char* why) {
    std::fprintf(stderr,
                 "error: %s\nusage: cachevision_sim [--sizes a,b,c] [--size WxH] [--mappings identity,rotate90]\n"
                 "       [--variants v1,v2] [--l1 KiB:ways] [--l2 KiB:ways] [--l3 KiB:ways] [--out dir]\n",
                 why);
    return 2;
}

// Parses "KiB:ways" into a level config with 64-byte lines.
bool parse_level(const std::string& s, const char* name, SimLevelConfig& out) {
    unsigned kib = 0;
    int ways = 0;
    if (std::sscanf(s.c_str(), "%u:%d", &kib, &ways) != 2 || kib == 0 || kib > (1u << 20) || ways <= 0 || ways > 64)
        return false;
    const std::uint64_t bytes = std::uint64_t(kib) * 1024;
    if (bytes % (64ull * std::uint64_t(ways)) != 0) return false;  // whole number of sets
    out = {name, bytes, 64, ways};
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::pair<int, int>> sizes;
    std::vector<std::string> variant_filter, mapping_filter;
    SimLevelConfig custom[3];
    bool has_custom[3] = {false, false, false};
    std::string out_dir = "results/raw";
    for (int i = 1; i + 1 < argc; i += 2) {
        const std::string k = argv[i], v = argv[i + 1];
        if (k == "--sizes") {
            for (const auto& e : split(v)) {
                const int n = std::atoi(e.c_str());
                if (n <= 0 || n > 16384) return usage("bad --sizes");
                sizes.emplace_back(n, n);
            }
        } else if (k == "--size") {
            int w = 0, h = 0;
            if (std::sscanf(v.c_str(), "%dx%d", &w, &h) != 2 || w <= 0 || h <= 0 || w > 16384 || h > 16384)
                return usage("bad --size");
            sizes.emplace_back(w, h);
        } else if (k == "--variants") variant_filter = split(v);
        else if (k == "--mappings") mapping_filter = split(v);
        else if (k == "--l1") { if (!parse_level(v, "L1D", custom[0])) return usage("bad --l1"); has_custom[0] = true; }
        else if (k == "--l2") { if (!parse_level(v, "L2", custom[1])) return usage("bad --l2"); has_custom[1] = true; }
        else if (k == "--l3") { if (!parse_level(v, "L3", custom[2])) return usage("bad --l3"); has_custom[2] = true; }
        else if (k == "--out") out_dir = v;
        else return usage(("unknown argument " + k).c_str());
    }
    if (argc % 2 == 0) return usage("every option needs a value");
    if (sizes.empty())
        for (int n : {256, 512, 1024, 2048, 4096}) sizes.emplace_back(n, n);
    std::vector<Mapping> mappings;
    for (const auto& m : mapping_filter) {
        Mapping mm;
        if (!parse_mapping(m.c_str(), mm)) return usage("bad --mappings");
        mappings.push_back(mm);
    }
    if (mappings.empty()) mappings = {Mapping::Identity, Mapping::Rotate90};

    pin_current_thread_to_performance_core();
    const SystemInfo sys = collect_system_info();

    // Geometry from CPUID (data/unified caches) and CPUID leaf 0x18 (TLBs).
    std::vector<SimLevelConfig> caches, tlbs;
    for (int lvl = 1; lvl <= 3; ++lvl)
        for (const auto& c : sys.caches)
            if (c.source.rfind("cpuid", 0) == 0 && c.level == lvl && c.type != "instruction") {
                caches.push_back({"L" + std::to_string(lvl) + (lvl == 1 ? "D" : ""), c.size_bytes, c.line_bytes, c.ways});
                break;
            }
    for (const auto& t : sys.tlbs)
        if (t.level == 1 && (t.type == "load" || t.type == "data") && t.page_sizes.find("4K") != std::string::npos) {
            tlbs.push_back({"DTLB", std::uint64_t(t.entries) * 4096, 4096, t.ways});
            break;
        }
    for (const auto& t : sys.tlbs)
        if (t.level == 2 && (t.type == "unified" || t.type == "data") && t.page_sizes.find("4K") != std::string::npos) {
            tlbs.push_back({"STLB", std::uint64_t(t.entries) * 4096, 4096, t.ways});
            break;
        }
    const bool from_cpuid = caches.size() == 3;
    if (!from_cpuid) {
        std::fprintf(stderr, "warning: CPUID cache geometry unavailable; using a generic 32K/1M/16M model\n");
        caches = {{"L1D", 32768, 64, 8}, {"L2", 1 << 20, 64, 16}, {"L3", 16u << 20, 64, 16}};
    }
    const bool any_custom = has_custom[0] || has_custom[1] || has_custom[2];
    for (int l = 0; l < 3; ++l)
        if (has_custom[l]) caches[std::size_t(l)] = custom[l];
    const char* geometry_source = any_custom ? "custom" : (from_cpuid ? "cpuid" : "generic-defaults");

    {
        std::ofstream g(out_dir + "/cachesim_geometry.json");
        if (!g) return usage("cannot write to --out directory");
        g << "{\n  \"source\": \"" << geometry_source << "\",\n  \"cpu\": \""
          << sys.cpu_brand << "\",\n  \"levels\": [\n";
        auto all = caches;
        all.insert(all.end(), tlbs.begin(), tlbs.end());
        for (std::size_t i = 0; i < all.size(); ++i)
            g << "    {\"name\": \"" << all[i].name << "\", \"size_bytes\": " << all[i].size_bytes
              << ", \"line_bytes\": " << all[i].line_bytes << ", \"ways\": " << all[i].ways << "}"
              << (i + 1 < all.size() ? "," : "") << "\n";
        g << "  ],\n  \"policy\": \"true LRU, write-back, write-allocate, non-inclusive, no prefetch, modulo set index\"\n}\n";
    }

    CsvWriter csv;
    csv.open(out_dir + "/cachesim.csv", {"source", "width", "height", "pixels", "mapping", "label", "tile_w", "tile_h",
                                          "level", "accesses", "misses", "miss_rate", "misses_per_px", "writebacks",
                                          "dram_read_bytes_per_px", "dram_write_bytes_per_px"});

    const CacheGeometry geom = geometry_from(sys);
    for (const auto& [w, hgt] : sizes) {
        const ImageU8 in(w, hgt);
        for (Mapping m : mappings) {
            const ImageF32 out = make_output(in, m);
            const auto ranked = rank_tiles(in.width, in.height, m, geom);
            std::vector<SimVariant> vs;
            if (variant_filter.empty()) {
                vs = {{"row_major", Strategy::RowMajor, {}},
                      {"column_major", Strategy::ColumnMajor, {}},
                      {"morton", Strategy::Morton, {}}};
                for (int t : {8, 16, 32, 64, 128, 256})
                    vs.push_back({"tiled_" + std::to_string(t) + "x" + std::to_string(t), Strategy::Tiled, {t, t}});
                vs.push_back({"adaptive_model", Strategy::Adaptive, ranked.front().tile});
            }
            for (const auto& name : variant_filter) {
                int tw = 0, th = 0;
                if (name == "row_major") vs.push_back({name, Strategy::RowMajor, {}});
                else if (name == "column_major") vs.push_back({name, Strategy::ColumnMajor, {}});
                else if (name == "morton") vs.push_back({name, Strategy::Morton, {}});
                else if (name == "adaptive_model") vs.push_back({name, Strategy::Adaptive, ranked.front().tile});
                else if (std::sscanf(name.c_str(), "tiled:%dx%d", &tw, &th) == 2 && tw > 0 && th > 0)
                    vs.push_back({"tiled_" + std::to_string(tw) + "x" + std::to_string(th), Strategy::Tiled, {tw, th}});
                else return usage(("unknown variant " + name).c_str());
            }

            for (const auto& v : vs) {
                SimHierarchy h(caches, tlbs);
                RecordKernel k{&h, reinterpret_cast<std::uintptr_t>(in.data), reinterpret_cast<std::uintptr_t>(out.data)};
                if (m == Mapping::Identity) replay<IdentityMap>(v, in, out, k);
                else replay<Rotate90Map>(v, in, out, k);
                const double px = double(w) * hgt;
                auto emit = [&](const std::string& level, const SimLevelStats& st) {
                    csv.row({"model", std::to_string(w), std::to_string(hgt), fmt(px, 12), to_string(m), v.label,
                             std::to_string(v.t.w), std::to_string(v.t.h), level, std::to_string(st.accesses),
                             std::to_string(st.misses), fmt(st.accesses ? double(st.misses) / st.accesses : 0.0, 6),
                             fmt(st.misses / px, 6), std::to_string(st.writebacks),
                             fmt(double(h.dram_read_lines) * 64 / px, 6), fmt(double(h.dram_write_lines) * 64 / px, 6)});
                };
                for (const auto& c : h.caches) emit(c.config().name, c.stats);
                for (const auto& t : h.tlbs) emit(t.config().name, t.stats);
                std::fprintf(stderr, "sim %dx%d %s %-16s L1D miss/px %.3f  L2 %.3f  L3 %.3f  DRAM %.1f B/px\n", w,
                             hgt, to_string(m), v.label.c_str(), h.caches[0].stats.misses / px,
                             h.caches.size() > 1 ? h.caches[1].stats.misses / px : 0.0,
                             h.caches.size() > 2 ? h.caches[2].stats.misses / px : 0.0,
                             double(h.dram_read_lines + h.dram_write_lines) * 64 / px);
            }
        }
    }
    return 0;
}
