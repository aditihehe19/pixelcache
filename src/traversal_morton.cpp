// Morton / Z-order traversal (bit de-interleaving, out-of-range block skipping).
// In builds with BMI2 enabled (-march=native on Intel since Haswell) the
// de-interleave is a single PEXT; otherwise it is 6 shift/or/and steps.
#include "traversal_dispatch.hpp"

namespace cachevision {

void run_morton(const ImageU8& in, const ImageF32& out, Rect r, const TraversalArgs& a) {
    detail::dispatch(a, [&](auto map, auto& k) {
        traverse_morton<decltype(map)>(in, out, r, k);
    });
}

}  // namespace cachevision
