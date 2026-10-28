// cachevision_bench - benchmark driver.
//
//   cachevision_bench --config benchmarks/benchmark_config.json --suites main,tile_sweep --out results/raw
//   cachevision_bench --single --op yuv --mapping identity --variant tiled:32x32 --size 4096x4096
//                     --image mixed --reps 11 --condition warm --out results/raw
//                     (--variant also takes a comma-separated list, e.g. row_major,morton,tiled:32x32)
//   cachevision_bench --memory --out results/raw          memory-hierarchy characterisation
//   cachevision_bench --sysinfo --out results/raw         host description only
//   cachevision_bench --dump --image photo --size 512x512 --data data --out results/validation
//
// All benchmarks run single-threaded on one pinned performance core.
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "adaptive.hpp"
#include "benchmark.hpp"
#include "mini_json.hpp"
#include "system_info.hpp"
#include "traversal.hpp"

using namespace cachevision;

namespace {

struct Args {
    std::string config = "benchmarks/benchmark_config.json";
    std::vector<std::string> suites;
    std::string out = "results/raw";
    std::string data = "data";
    bool quick = false, single = false, memory = false, sysinfo = false, dump = false;
    // --single / --dump
    std::string op = "yuv", mapping = "identity", variant = "row_major", image = "mixed", condition = "warm";
    int width = 1024, height = 1024, reps = 11;
    std::uint64_t memory_max = 512ull << 20;
};

[[noreturn]] void die(const std::string& m) {
    std::fprintf(stderr, "error: %s\n", m.c_str());
    std::exit(2);
}

std::vector<std::string> split(const std::string& s, char sep) {
    std::vector<std::string> v;
    std::stringstream ss(s);
    std::string p;
    while (std::getline(ss, p, sep))
        if (!p.empty()) v.push_back(p);
    return v;
}

bool parse_size(const std::string& s, int& w, int& h) {
    const auto x = s.find('x');
    if (x == std::string::npos) {
        w = h = std::atoi(s.c_str());
    } else {
        w = std::atoi(s.substr(0, x).c_str());
        h = std::atoi(s.substr(x + 1).c_str());
    }
    return w > 0 && h > 0;
}

Args parse_args(int argc, char** argv) {
    Args a;
    for (int i = 1; i < argc; ++i) {
        const std::string k = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) die("missing value for " + k);
            return argv[++i];
        };
        if (k == "--config") a.config = next();
        else if (k == "--suites") a.suites = split(next(), ',');
        else if (k == "--out") a.out = next();
        else if (k == "--data") a.data = next();
        else if (k == "--quick") a.quick = true;
        else if (k == "--single") a.single = true;
        else if (k == "--memory") a.memory = true;
        else if (k == "--memory-max-mb") a.memory_max = std::uint64_t(std::atoll(next().c_str())) << 20;
        else if (k == "--sysinfo") a.sysinfo = true;
        else if (k == "--dump") a.dump = true;
        else if (k == "--op") a.op = next();
        else if (k == "--mapping") a.mapping = next();
        else if (k == "--variant") a.variant = next();
        else if (k == "--image") a.image = next();
        else if (k == "--condition") a.condition = next();
        else if (k == "--reps") a.reps = std::atoi(next().c_str());
        else if (k == "--size") {
            if (!parse_size(next(), a.width, a.height)) die("bad --size");
        } else if (k == "--help" || k == "-h") {
            std::puts("see header comment in benchmarks/run_benchmarks.cpp");
            std::exit(0);
        } else die("unknown argument " + k);
    }
    return a;
}

std::string utc_now() {
    std::time_t t = std::time(nullptr);
    std::tm tm{};
#if defined(_WIN32)
    gmtime_s(&tm, &t);
#else
    gmtime_r(&t, &tm);
#endif
    char b[32];
    std::strftime(b, sizeof b, "%Y-%m-%dT%H:%M:%SZ", &tm);
    return b;
}

std::string read_text(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) die("cannot read " + path);
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

bool file_exists(const std::string& p) { return std::ifstream(p).good(); }

// Loads/generates the input outside any timed region. `kind_out` records
// what was actually used (a missing photo falls back to "mixed_fallback").
ImageU8 get_image(const std::string& kind, int w, int h, const std::string& data_dir, std::string& kind_out) {
    if (kind == "photo") {
        const std::string path = data_dir + "/photo_" + std::to_string(w) + "x" + std::to_string(h) + ".ppm";
        if (file_exists(path)) {
            ImageU8 img = load_ppm(path);
            if (img.width != w || img.height != h) die(path + " has unexpected dimensions");
            kind_out = "photo";
            return img;
        }
        std::fprintf(stderr, "warning: %s not found (run scripts/prepare_images.py); using synthetic 'mixed'\n",
                     path.c_str());
        kind_out = "mixed_fallback";
        return make_synthetic(SyntheticKind::Mixed, w, h);
    }
    SyntheticKind k;
    if (!parse_synthetic_kind(kind, k)) die("unknown image kind " + kind);
    kind_out = kind;
    return make_synthetic(k, w, h);
}

Variant parse_variant(const std::string& s) {
    if (s.rfind("tiled:", 0) == 0) {
        int w = 0, h = 0;
        if (!parse_size(s.substr(6), w, h)) die("bad tile in " + s);
        return make_variant(Strategy::Tiled, TileSize{w, h});
    }
    if (s == "adaptive_model") return make_variant(Strategy::Adaptive, {}, false);
    if (s == "adaptive_calib") return make_variant(Strategy::Adaptive, {}, true);
    Strategy st;
    if (!parse_strategy(s.c_str(), st) || st == Strategy::Tiled || st == Strategy::Adaptive)
        die("unknown variant " + s);
    return make_variant(st);
}

struct Session {
    std::string build_variant;
    SystemInfo sys;
    CacheGeometry geom;
    CsvWriter summary, samples;
    std::chrono::steady_clock::time_point t0 = std::chrono::steady_clock::now();
};

void log_session(const Args& a, Session& s, const std::string& phase, double core_ghz) {
    std::ofstream f(a.out + "/session_" + s.build_variant + ".jsonl", std::ios::app);
    const MemoryUsage mu = process_memory_usage();
    const double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - s.t0).count();
    f << "{\"utc\": \"" << utc_now() << "\", \"phase\": \"" << phase << "\", \"core_ghz_probe\": " << core_ghz
      << ", \"elapsed_s\": " << el << ", \"peak_working_set_bytes\": " << mu.peak_working_set
      << ", \"peak_private_bytes\": " << mu.peak_private << ", \"suites\": \"";
    for (const auto& x : a.suites) f << x << ";";
    f << "\", \"quick\": " << (a.quick ? "true" : "false") << "}\n";
}

void run_one_group(Session& s, GroupSpec& g, const ImageU8& in, ImageF32& out) {
    const auto t0 = std::chrono::steady_clock::now();
    const auto results = run_group(g, in, out, s.geom, s.samples);
    for (const auto& r : results) s.summary.row(summary_row(g, in, r));
    const double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    // Progress line: best variant by median.
    const VariantResult* best = nullptr;
    bool all_match = true;
    for (const auto& r : results) {
        if (!best || r.stats.median < best->stats.median) best = &r;
        if (g.op != Op::IndexOnly && !r.matches_baseline) all_match = false;
    }
    std::fprintf(stderr, "[%s] %s %dx%d %s/%s: %zu results in %.1fs, fastest %s %.3f ms%s\n", g.suite.c_str(),
                 g.image_kind.c_str(), in.width, in.height, to_string(g.op), to_string(g.mapping), results.size(), el,
                 best ? best->variant.label.c_str() : "-", best ? best->stats.median : 0.0,
                 all_match ? "" : "  ** OUTPUT MISMATCH **");
}

void run_suite(const Args& a, Session& s, const std::string& name, const json::Value& suite,
               const json::Value& defaults) {
    auto get = [&](const char* key) -> const json::Value& {
        if (suite.has(key)) return suite[key];
        if (defaults.has(key)) return defaults[key];
        die("suite " + name + " lacks '" + key + "'");
    };
    std::vector<std::pair<int, int>> sizes;
    for (const auto& v : get("sizes").arr) {
        if (v.type == json::Value::Array) sizes.emplace_back(int(v.arr.at(0).as_number()), int(v.arr.at(1).as_number()));
        else sizes.emplace_back(int(v.as_number()), int(v.as_number()));
    }
    std::vector<std::string> images, ops, maps, variants, conds;
    for (const auto& v : get("images").arr) images.push_back(v.as_string());
    for (const auto& v : get("ops").arr) ops.push_back(v.as_string());
    for (const auto& v : get("mappings").arr) maps.push_back(v.as_string());
    for (const auto& v : get("variants").arr) variants.push_back(v.as_string());
    for (const auto& v : get("conditions").arr) conds.push_back(v.as_string());
    int reps = int(get("reps").as_number());
    double min_ms = get("min_sample_ms").as_number();
    std::uint64_t max_px = suite.has("max_pixels_for_column_major") ? std::uint64_t(suite["max_pixels_for_column_major"].as_number()) : ~0ull;
    if (a.quick) {
        reps = std::min(reps, 3);
        min_ms = std::min(min_ms, 1.0);
    }

    for (const auto& [w, h] : sizes) {
        if (a.quick && std::int64_t(w) * h > 2048 * 2048) continue;
        for (const auto& kind : images) {
            std::string kind_used;
            const ImageU8 in = get_image(kind, w, h, a.data, kind_used);
            for (const auto& mname : maps) {
                Mapping m;
                if (!parse_mapping(mname.c_str(), m)) die("bad mapping " + mname);
                ImageF32 out = make_output(in, m);
                for (const auto& oname : ops) {
                    GroupSpec g;
                    g.suite = name;
                    g.build_variant = s.build_variant;
                    g.image_kind = kind_used;
                    if (!parse_op(oname.c_str(), g.op)) die("bad op " + oname);
                    g.mapping = m;
                    g.reps = reps;
                    g.min_sample_ms = min_ms;
                    g.conditions.clear();
                    for (const auto& c : conds) {
                        CacheCondition cc;
                        if (!parse_condition(c, cc)) die("bad condition " + c);
                        g.conditions.push_back(cc);
                    }
                    for (const auto& vn : variants) {
                        Variant v = parse_variant(vn);
                        if (v.strategy == Strategy::ColumnMajor && std::uint64_t(w) * h > max_px) continue;
                        g.variants.push_back(v);
                    }
                    run_one_group(s, g, in, out);
                }
            }
        }
    }
}

void dump_outputs(const Args& a, const std::string& build_variant) {
    std::string kind_used;
    const ImageU8 in = get_image(a.image, a.width, a.height, a.data, kind_used);
    const std::string base = a.out + "/" + kind_used + "_" + std::to_string(a.width) + "x" + std::to_string(a.height);
    save_ppm(base + "_input.ppm", in);
    std::ofstream man(a.out + "/dump_manifest.csv", std::ios::app);
    for (Op op : {Op::Unpack, Op::YUV, Op::HSV, Op::Lab}) {
        ImageF32 out = make_output(in, Mapping::Identity);
        TraversalArgs ta;
        ta.op = op;
        const std::string err = convert(in, out, Strategy::RowMajor, ta);
        if (!err.empty()) die(err);
        const std::string path = base + "_" + to_string(op) + ".f32";
        std::ofstream f(path, std::ios::binary);
        for (int y = 0; y < out.height; ++y)
            f.write(reinterpret_cast<const char*>(out.row(y)), std::streamsize(std::size_t(out.width) * 3 * sizeof(float)));
        man << build_variant << "," << kind_used << "," << a.width << "," << a.height << "," << to_string(op) << ","
            << path << "," << base + "_input.ppm" << "\n";
    }
    std::fprintf(stderr, "dumped %s outputs to %s_*\n", kind_used.c_str(), base.c_str());
}

}  // namespace

int main(int argc, char** argv) {
    const Args a = parse_args(argc, argv);

    Session s;
#if defined(CV_BUILD_VARIANT)
    s.build_variant = CV_BUILD_VARIANT;
#else
    s.build_variant = "unknown";
#endif
    const std::string pinned = pin_current_thread_to_performance_core();
    const std::string prio = raise_priority();
    s.sys = collect_system_info();
    s.sys.pinned_cpu = pinned;
    s.sys.priority = prio;
    s.geom = geometry_from(s.sys);

    {
        std::ofstream f(a.out + "/system_" + s.build_variant + ".json");
        if (!f) die("cannot write to " + a.out + " (does the directory exist?)");
        f << system_info_json(s.sys);
    }
    std::fprintf(stderr, "cachevision_bench [%s] on %s, pinned: %s, L1D=%llu L2=%llu LLC=%llu (geometry %s)\n",
                 s.build_variant.c_str(), s.sys.cpu_brand.c_str(), pinned.empty() ? "no" : pinned.c_str(),
                 static_cast<unsigned long long>(s.sys.l1d_bytes()), static_cast<unsigned long long>(s.sys.l2_bytes()),
                 static_cast<unsigned long long>(s.sys.llc_bytes()), s.geom.from_cpuid ? "from CPUID" : "DEFAULTS");
    if (a.sysinfo) return 0;

    log_session(a, s, "start", probe_core_ghz(0.2));

    if (a.dump) {
        dump_outputs(a, s.build_variant);
        return 0;
    }

    if (a.memory) {
        CsvWriter mem;
        mem.open(a.out + "/memory_" + s.build_variant + ".csv", {"build_variant", "test", "size_bytes", "value", "unit", "reps"});
        run_memory_characterisation(mem, s.build_variant, a.memory_max, a.quick);
        log_session(a, s, "end_memory", probe_core_ghz(0.2));
        return 0;
    }

    s.summary.open(a.out + "/bench_" + s.build_variant + ".csv", summary_header());
    s.samples.open(a.out + "/samples_" + s.build_variant + ".csv", samples_header());

    if (a.single) {
        GroupSpec g;
        g.suite = "single";
        g.build_variant = s.build_variant;
        if (!parse_op(a.op.c_str(), g.op)) die("bad --op");
        if (!parse_mapping(a.mapping.c_str(), g.mapping)) die("bad --mapping");
        CacheCondition c;
        if (!parse_condition(a.condition, c)) die("bad --condition");
        g.conditions = {c};
        g.reps = a.reps;
        g.min_sample_ms = 0.0;  // one run per sample: makes perf-stat differencing exact
        // --variant accepts a comma-separated list: all variants then share one
        // group (same input buffer, shuffled interleaved repetitions), which is
        // what a fair side-by-side comparison needs.
        for (const auto& name : split(a.variant, ',')) {
            Variant v = parse_variant(name);
            const bool dup = std::any_of(g.variants.begin(), g.variants.end(),
                                         [&](const Variant& x) { return x.label == v.label; });
            if (!dup) g.variants.push_back(v);
        }
        if (g.variants.empty()) die("empty --variant");
        const ImageU8 in = get_image(a.image, a.width, a.height, a.data, g.image_kind);
        ImageF32 out = make_output(in, g.mapping);
        if (g.reps > 0) run_one_group(s, g, in, out);
        log_session(a, s, "end_single", probe_core_ghz(0.2));
        return 0;
    }

    const json::Value cfg = json::parse(read_text(a.config));
    const json::Value& defaults = cfg.has("defaults") ? cfg["defaults"] : json::Value{};
    const json::Value& suites = cfg["suites"];
    std::vector<std::string> names = a.suites;
    if (names.empty())
        for (const auto& kv : suites.obj) names.push_back(kv.first);
    for (const auto& n : names) {
        if (!suites.has(n)) die("no suite named " + n);
        std::fprintf(stderr, "=== suite %s ===\n", n.c_str());
        run_suite(a, s, n, suites[n], defaults);
        log_session(a, s, "end_suite_" + n, probe_core_ghz(0.1));
    }
    return 0;
}
