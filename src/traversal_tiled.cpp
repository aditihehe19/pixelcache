// Spatial blocking: tiles of a.tile.w x a.tile.h, clipped at the region edge.
#include "traversal_dispatch.hpp"

namespace cachevision {

void run_tiled(const ImageU8& in, const ImageF32& out, Rect r, const TraversalArgs& a) {
    detail::dispatch(a, [&](auto map, auto& k) {
        traverse_tiled<decltype(map)>(in, out, r, a.tile, k);
    });
}

}  // namespace cachevision
