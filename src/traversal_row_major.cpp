// Row-major (baseline) and column-major (negative control) traversals.
#include "traversal_dispatch.hpp"

namespace cachevision {

void run_row_major(const ImageU8& in, const ImageF32& out, Rect r, const TraversalArgs& a) {
    detail::dispatch(a, [&](auto map, auto& k) {
        traverse_row_major<decltype(map)>(in, out, r, k);
    });
}

void run_column_major(const ImageU8& in, const ImageF32& out, Rect r, const TraversalArgs& a) {
    detail::dispatch(a, [&](auto map, auto& k) {
        traverse_column_major<decltype(map)>(in, out, r, k);
    });
}

}  // namespace cachevision
