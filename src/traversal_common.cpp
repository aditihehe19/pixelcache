// Names, parsing and the validating conversion front door.
#include <cstring>

#include "traversal.hpp"

namespace cachevision {

const char* to_string(Strategy s) {
    switch (s) {
        case Strategy::RowMajor: return "row_major";
        case Strategy::ColumnMajor: return "column_major";
        case Strategy::Tiled: return "tiled";
        case Strategy::Morton: return "morton";
        case Strategy::Adaptive: return "adaptive";
    }
    return "?";
}

const char* to_string(Mapping m) { return m == Mapping::Identity ? "identity" : "rotate90"; }

bool parse_strategy(const char* s, Strategy& out) {
    static const struct { const char* name; Strategy s; } kS[] = {
        {"row_major", Strategy::RowMajor}, {"column_major", Strategy::ColumnMajor},
        {"tiled", Strategy::Tiled}, {"morton", Strategy::Morton}, {"adaptive", Strategy::Adaptive},
    };
    for (const auto& e : kS)
        if (std::strcmp(s, e.name) == 0) { out = e.s; return true; }
    return false;
}

bool parse_mapping(const char* s, Mapping& out) {
    if (std::strcmp(s, "identity") == 0) { out = Mapping::Identity; return true; }
    if (std::strcmp(s, "rotate90") == 0) { out = Mapping::Rotate90; return true; }
    return false;
}

ImageF32 make_output(const ImageU8& in, Mapping m) {
    int w = 0, h = 0;
    output_dims(m, in.width, in.height, w, h);
    return ImageF32(w, h);
}

std::string convert(const ImageU8& in, ImageF32& out, Strategy s, const TraversalArgs& a) {
    if (in.width < 0 || in.height < 0) return "invalid input dimensions";
    if (in.empty()) {
        if (!out.empty()) return "output must be empty for an empty input";
        return "";  // nothing to do
    }
    if (!in.data) return "input has no pixel storage";
    if (in.stride < std::size_t(in.width) * 3) return "input stride smaller than a row";
    int ow = 0, oh = 0;
    output_dims(a.mapping, in.width, in.height, ow, oh);
    if (out.width != ow || out.height != oh) return "output dimensions do not match the mapping";
    if (!out.data) return "output has no pixel storage";
    if (out.stride < std::size_t(out.width) * 3) return "output stride smaller than a row";

    const Rect r = full_rect(in);
    switch (s) {
        case Strategy::RowMajor: run_row_major(in, out, r, a); return "";
        case Strategy::ColumnMajor: run_column_major(in, out, r, a); return "";
        case Strategy::Tiled:
            if (a.tile.w <= 0 || a.tile.h <= 0) return "tile dimensions must be positive";
            run_tiled(in, out, r, a);
            return "";
        case Strategy::Morton: run_morton(in, out, r, a); return "";
        case Strategy::Adaptive: return "use choose_tile() + Strategy::Tiled for adaptive tiling";
    }
    return "unknown strategy";
}

}  // namespace cachevision
