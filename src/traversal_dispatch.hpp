// Private helper: one switch on (mapping, op) -> fully inlined instantiation.
#pragma once

#include "traversal.hpp"

namespace cachevision {
namespace detail {

template <class Map, class F>
void dispatch_op(const TraversalArgs& a, Map m, F& f) {
    switch (a.op) {
        case Op::IndexOnly: {
            IndexOnlyKernel k;
            f(m, k);
            if (a.index_acc) *a.index_acc = k.acc;
            return;
        }
        case Op::Unpack: { UnpackKernel k; f(m, k); return; }
        case Op::YUV: { YuvKernel k; f(m, k); return; }
        case Op::HSV: { HsvKernel k; f(m, k); return; }
        case Op::Lab: { LabKernel k; f(m, k); return; }
    }
}

// f is a generic callable invoked as f(MapTag{}, kernel).
template <class F>
void dispatch(const TraversalArgs& a, F&& f) {
    if (a.mapping == Mapping::Identity) dispatch_op(a, IdentityMap{}, f);
    else dispatch_op(a, Rotate90Map{}, f);
}

}  // namespace detail
}  // namespace cachevision
