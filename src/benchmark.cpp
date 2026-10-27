#include "benchmark.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <functional>
#include <numeric>
#include <random>
#include <sstream>

#include "system_info.hpp"

#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
#include <emmintrin.h>
#define CV_HAVE_CLFLUSH 1
#endif

namespace cachevision {

namespace {
using clk = std::chrono::steady_clock;

// Compiler barrier: the optimiser must assume all memory was read/written.
inline void clobber_memory() {
#if defined(__GNUC__) || defined(__clang__)
    __asm__ volatile("" : : : "memory");
#endif
}

void run_variant(const ImageU8& in, ImageF32& out, Op op, Mapping m, Strategy s, TileSize t, std::uintptr_t* acc) {
    TraversalArgs a;
    a.op = op;
    a.mapping = m;
    a.tile = t;
    a.index_acc = acc;
    const Rect r = full_rect(in);
    switch (s) {
        case Strategy::RowMajor: run_row_major(in, out, r, a); break;
        case Strategy::ColumnMajor: run_column_major(in, out, r, a); break;
        case Strategy::Tiled:
        case Strategy::Adaptive: run_tiled(in, out, r, a); break;
        case Strategy::Morton: run_morton(in, out, r, a); break;
    }
    clobber_memory();
}
}  // namespace

const char* to_string(CacheCondition c) { return c == CacheCondition::Warm ? "warm" : "flushed"; }

bool parse_condition(const std::string& s, CacheCondition& out) {
    if (s == "warm") { out = CacheCondition::Warm; return true; }
    if (s == "flushed") { out = CacheCondition::Flushed; return true; }
    return false;
}

Variant make_variant(Strategy s, TileSize t, bool calibrate) {
    Variant v;
    v.strategy = s;
    v.tile = s == Strategy::Tiled ? t : TileSize{0, 0};  // tile is meaningless for other orders
    v.adaptive_calibrate = calibrate;
    switch (s) {
        case Strategy::Tiled: v.label = "tiled_" + std::to_string(t.w) + "x" + std::to_string(t.h); break;
        case Strategy::Adaptive: v.label = calibrate ? "adaptive_calib" : "adaptive_model"; break;
        default: v.label = to_string(s);
    }
    return v;
}

Stats compute_stats(std::vector<double> v) {
    Stats s;
    if (v.empty()) return s;
    std::sort(v.begin(), v.end());
    auto q = [&](double p) {  // linear interpolation between order statistics
        const double pos = p * double(v.size() - 1);
        const std::size_t i = std::size_t(pos);
        const double f = pos - double(i);
        return i + 1 < v.size() ? v[i] * (1 - f) + v[i + 1] * f : v[i];
    };
    s.min = v.front();
    s.max = v.back();
    s.median = q(0.5);
    s.p25 = q(0.25);
    s.p75 = q(0.75);
    s.mean = std::accumulate(v.begin(), v.end(), 0.0) / double(v.size());
    double ss = 0;
    for (double x : v) ss += (x - s.mean) * (x - s.mean);
    s.stdev = v.size() > 1 ? std::sqrt(ss / double(v.size() - 1)) : 0.0;
    return s;
}

void flush_from_caches(const void* p, std::size_t bytes) {
#if defined(CV_HAVE_CLFLUSH)
    const char* c = static_cast<const char*>(p);
    const std::uintptr_t start = reinterpret_cast<std::uintptr_t>(c) & ~std::uintptr_t(63);
    const std::uintptr_t end = reinterpret_cast<std::uintptr_t>(c) + bytes;
    _mm_mfence();
    for (std::uintptr_t a = start; a < end; a += 64) _mm_clflush(reinterpret_cast<const void*>(a));
    _mm_mfence();
#else
    (void)p;
    (void)bytes;
#endif
}

// ---- CSV -------------------------------------------------------------------------

bool CsvWriter::open(const std::string& path, const std::vector<std::string>& header) {
    std::ifstream probe(path);
    new_file_ = !probe.good() || probe.peek() == std::ifstream::traits_type::eof();
    probe.close();
    f_.open(path, std::ios::app);
    if (!f_) return false;
    if (new_file_) row(header);
    return true;
}

void CsvWriter::row(const std::vector<std::string>& cells) {
    for (std::size_t i = 0; i < cells.size(); ++i) {
        const std::string& c = cells[i];
        if (c.find_first_of(",\"\n") != std::string::npos) {
            f_ << '"';
            for (char ch : c) f_ << (ch == '"' ? "\"\"" : std::string(1, ch));
            f_ << '"';
        } else {
            f_ << c;
        }
        f_ << (i + 1 < cells.size() ? "," : "\n");
    }
    f_.flush();
}

std::string fmt(double v, int precision) {
    if (!std::isfinite(v)) return "NA";
    std::ostringstream o;
    o.precision(precision);
    o << v;
    return o.str();
}

std::string hex64(std::uint64_t v) {
    char b[19];
    std::snprintf(b, sizeof b, "%016llx", static_cast<unsigned long long>(v));
    return b;
}

// ---- groups ------------------------------------------------------------------------

std::vector<VariantResult> run_group(const GroupSpec& g, const ImageU8& in, ImageF32& out,
                                     const CacheGeometry& geom, CsvWriter& samples) {
    std::vector<VariantResult> results;
    if (in.empty()) return results;

    // Reference output hash from the baseline order.
    std::uintptr_t acc = 0;
    run_variant(in, out, g.op, g.mapping, Strategy::RowMajor, {}, &acc);
    const std::uint64_t ref_hash = g.op == Op::IndexOnly ? 0 : hash_image(out);

    // Resolve adaptive tiles, warm up (first touch), verify output.
    struct Prepared {
        Variant v;
        Strategy s;
        TileSize tile;
        double setup_ms;
        std::string note;
        std::uint64_t hash;
    };
    std::vector<Prepared> prep;
    for (const Variant& v : g.variants) {
        Prepared p{v, v.strategy, v.tile, 0.0, "", 0};
        if (v.strategy == Strategy::Adaptive) {
            const AdaptiveDecision d = choose_tile(in, out, g.op, g.mapping, geom, v.adaptive_calibrate);
            p.tile = d.chosen;
            p.setup_ms = d.model_ms + d.calib_ms;
            p.note = d.describe();
        }
        if (g.op != Op::IndexOnly) std::memset(out.data, 0, out.bytes());
        run_variant(in, out, g.op, g.mapping, p.s, p.tile, &acc);
        p.hash = g.op == Op::IndexOnly ? 0 : hash_image(out);
        prep.push_back(p);
    }

    for (CacheCondition cond : g.conditions) {
        // Inner repetition count per variant (warm only).
        std::vector<int> inner(prep.size(), 1);
        if (cond == CacheCondition::Warm) {
            for (std::size_t i = 0; i < prep.size(); ++i) {
                const auto t0 = clk::now();
                run_variant(in, out, g.op, g.mapping, prep[i].s, prep[i].tile, &acc);
                const double ms = std::chrono::duration<double, std::milli>(clk::now() - t0).count();
                inner[i] = std::max(1, std::min(10000, int(std::ceil(g.min_sample_ms / std::max(ms, 1e-6)))));
            }
        }

        std::vector<VariantResult> rs(prep.size());
        for (std::size_t i = 0; i < prep.size(); ++i) {
            rs[i].variant = prep[i].v;
            rs[i].effective_tile = prep[i].tile;
            rs[i].condition = cond;
            rs[i].inner_iters = inner[i];
            rs[i].setup_ms = prep[i].setup_ms;
            rs[i].setup_note = prep[i].note;
            rs[i].output_hash = prep[i].hash;
            rs[i].matches_baseline = prep[i].hash == ref_hash;
        }

        std::vector<std::size_t> order(prep.size());
        std::iota(order.begin(), order.end(), 0);
        std::mt19937_64 rng(g.shuffle_seed);
        std::vector<double> round_ghz;
        for (int rep = 0; rep < g.reps; ++rep) {
            std::shuffle(order.begin(), order.end(), rng);
            // Effective clock right before this round (DVFS can move it).
            const double ghz = probe_core_ghz(0.002);
            round_ghz.push_back(ghz);
            for (std::size_t i : order) {
                if (cond == CacheCondition::Flushed) {
                    flush_from_caches(in.data, in.bytes());
                    flush_from_caches(out.data, out.bytes());
                }
                const int n = inner[i];
                const std::uint64_t c0 = read_tsc();
                const auto t0 = clk::now();
                for (int k = 0; k < n; ++k) run_variant(in, out, g.op, g.mapping, prep[i].s, prep[i].tile, &acc);
                const auto t1 = clk::now();
                const std::uint64_t c1 = read_tsc();
                const double ms = std::chrono::duration<double, std::milli>(t1 - t0).count() / n;
                const double ticks = double(c1 - c0) / n;
                rs[i].ms.push_back(ms);
                rs[i].tsc.push_back(ticks);
                if (samples.is_open()) {
                    samples.row({g.suite, g.build_variant, g.image_kind, std::to_string(in.width),
                                 std::to_string(in.height), to_string(g.op), to_string(g.mapping),
                                 prep[i].v.label, to_string(cond), std::to_string(rep), std::to_string(n),
                                 fmt(ms, 8), fmt(ticks, 10), fmt(ghz, 4)});
                }
            }
        }
        const double ghz_median = compute_stats(round_ghz).median;
        for (auto& r : rs) {
            r.stats = compute_stats(r.ms);
            r.core_ghz = ghz_median;
            results.push_back(std::move(r));
        }
    }
    // Keep the accumulator observable so IndexOnly work cannot be discarded.
    if (acc == 0x5A5A5A5A5A5A5A5AULL) std::printf("#");
    return results;
}

std::vector<std::string> summary_header() {
    return {"suite", "build_variant", "image_kind", "width", "height", "pixels", "in_bytes", "out_bytes",
            "working_set_bytes", "op", "mapping", "strategy", "label", "tile_w", "tile_h", "condition", "reps",
            "inner_iters", "median_ms", "mean_ms", "min_ms", "max_ms", "stdev_ms", "p25_ms", "p75_ms", "cv_pct",
            "ns_per_px", "mpix_per_s", "tsc_ticks_per_px", "core_ghz_probe", "est_core_cycles_per_px",
            "model_bytes_per_px", "est_bw_gbps", "setup_ms", "setup_note", "aux_bytes", "output_hash",
            "output_matches_baseline", "hw_counters"};
}

std::vector<std::string> samples_header() {
    return {"suite", "build_variant", "image_kind", "width", "height", "op", "mapping", "label", "condition",
            "rep", "inner_iters", "ms_per_run", "tsc_ticks_per_run", "core_ghz_probe"};
}

std::vector<std::string> summary_row(const GroupSpec& g, const ImageU8& in, const VariantResult& r) {
    const double px = double(in.width) * double(in.height);
    const double in_bytes = double(in.bytes());
    const double out_bytes = px * 12.0;
    // Compulsory traffic model: read 3 B, write 12 B; a write miss also reads
    // the line first (write-allocate / RFO), hence 3 + 12 + 12 = 27 B/px.
    const double model_bpp = g.op == Op::IndexOnly ? 0.0 : 27.0;
    const double med = r.stats.median;
    const double ns_px = med * 1e6 / px;
    std::vector<double> tsc_sorted = r.tsc;
    std::sort(tsc_sorted.begin(), tsc_sorted.end());
    const double tsc_med = tsc_sorted.empty() ? 0.0 : tsc_sorted[tsc_sorted.size() / 2];
    const double cv = r.stats.mean > 0 ? 100.0 * r.stats.stdev / r.stats.mean : 0.0;
    return {g.suite,
            g.build_variant,
            g.image_kind,
            std::to_string(in.width),
            std::to_string(in.height),
            fmt(px, 12),
            fmt(in_bytes, 12),
            fmt(out_bytes, 12),
            fmt(in_bytes + out_bytes, 12),
            to_string(g.op),
            to_string(g.mapping),
            to_string(r.variant.strategy),
            r.variant.label,
            std::to_string(r.effective_tile.w),
            std::to_string(r.effective_tile.h),
            to_string(r.condition),
            std::to_string(r.ms.size()),
            std::to_string(r.inner_iters),
            fmt(med, 8),
            fmt(r.stats.mean, 8),
            fmt(r.stats.min, 8),
            fmt(r.stats.max, 8),
            fmt(r.stats.stdev, 8),
            fmt(r.stats.p25, 8),
            fmt(r.stats.p75, 8),
            fmt(cv, 4),
            fmt(ns_px, 6),
            fmt(px / (med * 1e3), 6),
            fmt(tsc_med / px, 6),
            fmt(r.core_ghz, 4),
            fmt(ns_px * r.core_ghz, 6),
            fmt(model_bpp, 4),
            fmt(model_bpp > 0 ? model_bpp * px / (med * 1e6) : 0.0, 6),
            fmt(r.setup_ms, 6),
            r.setup_note,
            "0",  // no strategy allocates auxiliary memory (Morton decodes on the fly)
            hex64(r.output_hash),
            g.op == Op::IndexOnly ? "NA" : (r.matches_baseline ? "1" : "0"),
            "unavailable"};
}

// ---- memory-hierarchy characterisation ---------------------------------------------

namespace {

double time_until(double min_ms, const std::function<void()>& f, int& reps_out) {
    // Repeat f() until at least min_ms has elapsed (>= 3 repetitions), then
    // return the median time of a single call in nanoseconds.
    std::vector<double> t;
    double total = 0;
    while (total < min_ms || t.size() < 3) {
        const auto t0 = clk::now();
        f();
        const double ns = std::chrono::duration<double, std::nano>(clk::now() - t0).count();
        t.push_back(ns);
        total += ns / 1e6;
        if (t.size() > 2000) break;
    }
    reps_out = int(t.size());
    return compute_stats(t).median;
}

}  // namespace

void run_memory_characterisation(CsvWriter& out, const std::string& build_variant, std::uint64_t max_bytes,
                                 bool quick) {
    std::vector<std::uint64_t> sizes;
    for (std::uint64_t s = 4096; s <= max_bytes; s *= 2) {
        sizes.push_back(s);
        if (s * 3 / 2 <= max_bytes && s >= 16384) sizes.push_back(s * 3 / 2);
    }
    std::sort(sizes.begin(), sizes.end());
    const double min_ms = quick ? 5.0 : 40.0;

    for (std::uint64_t bytes : sizes) {
        const std::size_t n = std::size_t(bytes / 8);
        AlignedBuffer buf(n * 8, 4096);
        auto* p = static_cast<std::uint64_t*>(buf.data());
        for (std::size_t i = 0; i < n; ++i) p[i] = i;
        int reps = 0;

        // Read bandwidth: 4 independent accumulators.
        volatile std::uint64_t sink = 0;
        double ns = time_until(min_ms, [&] {
            std::uint64_t a0 = 0, a1 = 0, a2 = 0, a3 = 0;
            for (std::size_t i = 0; i + 4 <= n; i += 4) {
                a0 += p[i];
                a1 += p[i + 1];
                a2 += p[i + 2];
                a3 += p[i + 3];
            }
            sink = sink + a0 + a1 + a2 + a3;
        }, reps);
        out.row({build_variant, "read_bw", std::to_string(bytes), fmt(double(bytes) / ns, 6), "GB/s",
                 std::to_string(reps)});

        // Write bandwidth (regular stores, write-allocate).
        std::uint64_t k = 1;
        ns = time_until(min_ms, [&] {
            const std::uint64_t kk = k++;
            for (std::size_t i = 0; i < n; ++i) p[i] = i ^ kk;
            clobber_memory();
        }, reps);
        out.row({build_variant, "write_bw", std::to_string(bytes), fmt(double(bytes) / ns, 6), "GB/s",
                 std::to_string(reps)});

        // Dependent-load latency: random cyclic permutation of 64-byte nodes
        // (Sattolo), so every load depends on the previous one and hardware
        // prefetchers cannot predict the next address.
        const std::size_t nodes = std::size_t(bytes / 64);
        if (nodes >= 2) {
            std::vector<std::uint32_t> perm(nodes);
            std::iota(perm.begin(), perm.end(), 0u);
            std::mt19937 rng(42);
            for (std::size_t i = nodes - 1; i > 0; --i) {
                std::uniform_int_distribution<std::size_t> d(0, i - 1);
                std::swap(perm[i], perm[d(rng)]);
            }
            for (std::size_t i = 0; i < nodes; ++i) p[std::size_t(i) * 8] = std::uint64_t(perm[i]) * 8;
            const std::size_t steps = quick ? (1u << 18) : std::max<std::size_t>(1u << 20, std::min<std::size_t>(nodes * 2, 1u << 23));
            std::uint64_t idx = 0;
            ns = time_until(quick ? 1.0 : 10.0, [&] {
                std::uint64_t j = idx;
                for (std::size_t s = 0; s < steps; ++s) j = p[j];
                idx = j;
            }, reps);
            out.row({build_variant, "latency", std::to_string(bytes), fmt(ns / double(steps), 6), "ns/load",
                     std::to_string(reps)});
            sink = sink + idx;
        }
        (void)sink;
        std::fprintf(stderr, "  memory: %llu bytes done\n", static_cast<unsigned long long>(bytes));
    }
}

}  // namespace cachevision
