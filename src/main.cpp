// cachevision - small command-line front end.
//
//   cachevision info
//   cachevision convert <in.ppm> <out.f32> [--op yuv|hsv|lab|unpack]
//                       [--strategy row_major|column_major|tiled|morton|adaptive]
//                       [--tile 32x32] [--mapping identity|rotate90]
//
// The output file is raw interleaved float32 (width*height*3 values, row-major);
// dimensions are printed on stdout.
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>

#include "adaptive.hpp"
#include "system_info.hpp"
#include "traversal.hpp"

using namespace cachevision;

namespace {
int usage() {
    std::fprintf(stderr,
                 "usage:\n  cachevision info\n  cachevision convert <in.ppm> <out.f32> [--op OP] [--strategy S] "
                 "[--tile WxH] [--mapping M]\n");
    return 2;
}
}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) return usage();
    const std::string cmd = argv[1];
    if (cmd == "info") {
        SystemInfo s = collect_system_info();
        s.pinned_cpu = "";
        std::fputs(system_info_json(s).c_str(), stdout);
        return 0;
    }
    if (cmd != "convert" || argc < 4) return usage();

    TraversalArgs a;
    Strategy strategy = Strategy::RowMajor;
    for (int i = 4; i + 1 < argc; i += 2) {
        const std::string k = argv[i], v = argv[i + 1];
        if (k == "--op" && !parse_op(v.c_str(), a.op)) return usage();
        if (k == "--strategy" && !parse_strategy(v.c_str(), strategy)) return usage();
        if (k == "--mapping" && !parse_mapping(v.c_str(), a.mapping)) return usage();
        if (k == "--tile" && std::sscanf(v.c_str(), "%dx%d", &a.tile.w, &a.tile.h) != 2) return usage();
    }
    try {
        const ImageU8 in = load_ppm(argv[2]);
        ImageF32 out = make_output(in, a.mapping);
        if (strategy == Strategy::Adaptive) {
            const AdaptiveDecision d =
                choose_tile(in, out, a.op, a.mapping, geometry_from(collect_system_info()), true);
            a.tile = d.chosen;
            strategy = Strategy::Tiled;
            std::fprintf(stderr, "adaptive: %s\n", d.describe().c_str());
        }
        const auto t0 = std::chrono::steady_clock::now();
        const std::string err = convert(in, out, strategy, a);
        const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        if (!err.empty()) {
            std::fprintf(stderr, "error: %s\n", err.c_str());
            return 1;
        }
        std::ofstream f(argv[3], std::ios::binary);
        for (int y = 0; y < out.height; ++y)
            f.write(reinterpret_cast<const char*>(out.row(y)), std::streamsize(std::size_t(out.width) * 3 * sizeof(float)));
        std::printf("%d %d 3 float32 (%s, %s, %.3f ms single cold run)\n", out.width, out.height, to_string(a.op),
                    to_string(strategy), ms);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "error: %s\n", e.what());
        return 1;
    }
    return 0;
}
