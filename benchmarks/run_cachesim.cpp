// cachevision_sim - replays the address streams of every traversal through
// the trace-driven cache/TLB model (see include/cache_sim.hpp).
//
//   cachevision_sim --sizes 256,512,1024,2048,4096 --out results/raw
//
// Output (results/raw/cachesim.csv) is SIMULATED, not measured; every row
// carries source=model so it can never be confused with hardware counters.
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

std::vector<int> parse_list(const std::string& s) {
    std::vector<int> v;
    std::stringstream ss(s);
    std::string p;
    while (std::getline(ss, p, ',')) v.push_back(std::atoi(p.c_str()));
    return v;
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<int> sizes = {256, 512, 1024, 2048, 4096};
    std::string out_dir = "results/raw";
    for (int i = 1; i + 1 < argc; i += 2) {
        const std::string k = argv[i];
        if (k == "--sizes") sizes = parse_list(argv[i + 1]);
        else if (k == "--out") out_dir = argv[i + 1];
        else {
            std::fprintf(stderr, "usage: cachevision_sim [--sizes a,b,c] [--out dir]\n");
            return 2;
        }
    }

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

    {
        std::ofstream g(out_dir + "/cachesim_geometry.json");
        g << "{\n  \"source\": \"" << (from_cpuid ? "cpuid" : "generic-defaults") << "\",\n  \"cpu\": \""
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
    for (int n : sizes) {
        const ImageU8 in(n, n);
        for (Mapping m : {Mapping::Identity, Mapping::Rotate90}) {
            const ImageF32 out = make_output(in, m);
            std::vector<SimVariant> vs = {{"row_major", Strategy::RowMajor, {}},
                                          {"column_major", Strategy::ColumnMajor, {}},
                                          {"morton", Strategy::Morton, {}}};
            for (int t : {8, 16, 32, 64, 128, 256})
                vs.push_back({"tiled_" + std::to_string(t) + "x" + std::to_string(t), Strategy::Tiled, {t, t}});
            const auto ranked = rank_tiles(in.width, in.height, m, geom);
            vs.push_back({"adaptive_model", Strategy::Adaptive, ranked.front().tile});

            for (const auto& v : vs) {
                SimHierarchy h(caches, tlbs);
                RecordKernel k{&h, reinterpret_cast<std::uintptr_t>(in.data), reinterpret_cast<std::uintptr_t>(out.data)};
                if (m == Mapping::Identity) replay<IdentityMap>(v, in, out, k);
                else replay<Rotate90Map>(v, in, out, k);
                const double px = double(n) * n;
                auto emit = [&](const std::string& level, const SimLevelStats& st) {
                    csv.row({"model", std::to_string(n), std::to_string(n), fmt(px, 12), to_string(m), v.label,
                             std::to_string(v.t.w), std::to_string(v.t.h), level, std::to_string(st.accesses),
                             std::to_string(st.misses), fmt(st.accesses ? double(st.misses) / st.accesses : 0.0, 6),
                             fmt(st.misses / px, 6), std::to_string(st.writebacks),
                             fmt(double(h.dram_read_lines) * 64 / px, 6), fmt(double(h.dram_write_lines) * 64 / px, 6)});
                };
                for (const auto& c : h.caches) emit(c.config().name, c.stats);
                for (const auto& t : h.tlbs) emit(t.config().name, t.stats);
                std::fprintf(stderr, "sim %d %s %-16s L1D miss/px %.3f  L2 %.3f  L3 %.3f  DRAM %.1f B/px\n", n,
                             to_string(m), v.label.c_str(), h.caches[0].stats.misses / px,
                             h.caches.size() > 1 ? h.caches[1].stats.misses / px : 0.0,
                             h.caches.size() > 2 ? h.caches[2].stats.misses / px : 0.0,
                             double(h.dram_read_lines + h.dram_write_lines) * 64 / px);
            }
        }
    }
    return 0;
}
