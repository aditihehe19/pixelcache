// CacheVision - host description and measurement environment control.
//
// Everything reported here is READ from the machine (CPUID, OS APIs) or
// MEASURED; nothing is assumed. Fields that cannot be determined are left
// empty / zero and reported as "unknown" or "unavailable".
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace cachevision {

struct CacheLevelInfo {
    int level = 0;            // 1, 2, 3
    std::string type;         // "data", "instruction", "unified"
    std::uint64_t size_bytes = 0;
    int line_bytes = 0;
    int ways = 0;             // 0 = unknown, -1 = fully associative
    int sets = 0;
    int shared_by_logical = 0;  // logical processors sharing this cache (0 = unknown)
    bool inclusive_known = false;
    bool inclusive = false;
    std::string source;       // "cpuid.4", "cpuid.8000001D", "os"
};

struct TlbInfo {
    int level = 0;
    std::string type;         // "data", "load", "store", "instruction", "unified"
    std::string page_sizes;   // e.g. "4K|2M|4M"
    int entries = 0;
    int ways = 0;             // -1 = fully associative
};

struct SystemInfo {
    std::string cpu_vendor;
    std::string cpu_brand;
    int cpu_family = 0, cpu_model = 0, cpu_stepping = 0;
    bool hybrid = false;                  // CPUID.7.EDX[15]
    int logical_processors = 0;
    int physical_cores = 0;               // 0 = unknown
    std::string core_types;               // e.g. "P:4 (8 logical), E:8" (OS efficiency classes)
    std::vector<CacheLevelInfo> caches;   // for the core the calling thread runs on
    std::vector<TlbInfo> tlbs;            // CPUID leaf 0x18 (Intel) when available
    std::uint64_t total_memory_bytes = 0;
    std::string os;
    std::string compiler;
    std::string build_flags;              // injected by CMake (CV_BUILD_FLAGS)
    std::string build_variant;            // "scalar" or "native"
    std::string simd;                     // enabled ISA extensions at compile time
    bool on_ac_power_known = false;
    bool on_ac_power = false;
    double tsc_ghz = 0.0;                 // measured against steady_clock
    std::string pinned_cpu;               // affinity actually applied ("" = none)
    std::string priority;                 // process/thread priority actually applied

    // Convenience lookups (0 when unknown).
    std::uint64_t l1d_bytes() const;
    std::uint64_t l2_bytes() const;
    std::uint64_t llc_bytes() const;
    int line_bytes() const;
};

// Pin the calling thread to one logical processor. On hybrid parts the
// highest-performance class is chosen (avoiding logical CPU 0 when possible).
// Returns a description of what was applied or "" if pinning failed.
std::string pin_current_thread_to_performance_core();
// Raise process/thread priority (no elevation required). Returns description.
std::string raise_priority();

// Collect host information. Call after pinning so CPUID describes that core.
SystemInfo collect_system_info();

// JSON object (single line per field) describing the host.
std::string system_info_json(const SystemInfo& s);

// Time-stamp counter.
std::uint64_t read_tsc();
double measure_tsc_ghz(double seconds = 0.2);

// Effective core-clock probe: a chain of dependent IMULs retires one multiply
// every 3 core cycles, so 3 x multiplies / second approximates the current core
// frequency without hardware counters. Returns GHz, or 0 if unsupported.
double probe_core_ghz(double seconds = 0.05);

// Peak working set / private bytes of this process (0 if unavailable).
struct MemoryUsage {
    std::uint64_t peak_working_set = 0;
    std::uint64_t peak_private = 0;
};
MemoryUsage process_memory_usage();

}  // namespace cachevision
