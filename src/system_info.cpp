// Host description: CPUID, OS APIs, and a few measurements (TSC rate,
// effective core clock). Windows and Linux are supported; other platforms
// compile but report "unknown" for most fields.
#include "system_info.hpp"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <set>
#include <sstream>
#include <thread>

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <psapi.h>
#else
#include <sched.h>
#include <sys/resource.h>
#include <sys/utsname.h>
#include <unistd.h>
#endif

#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
#define CV_X86 1
#if defined(_MSC_VER)
#include <intrin.h>
#else
#include <cpuid.h>
#include <x86intrin.h>
#endif
#endif

namespace cachevision {

namespace {

int g_pinned_cpu = -1;

struct Regs {
    unsigned a = 0, b = 0, c = 0, d = 0;
};

Regs cpuid(unsigned leaf, unsigned sub = 0) {
    Regs r;
#if defined(CV_X86)
#if defined(_MSC_VER)
    int v[4];
    __cpuidex(v, int(leaf), int(sub));
    r.a = unsigned(v[0]); r.b = unsigned(v[1]); r.c = unsigned(v[2]); r.d = unsigned(v[3]);
#else
    __cpuid_count(leaf, sub, r.a, r.b, r.c, r.d);
#endif
#else
    (void)leaf; (void)sub;
#endif
    return r;
}

std::string trim(std::string s) {
    const auto b = s.find_first_not_of(" \t\r\n");
    const auto e = s.find_last_not_of(" \t\r\n");
    return b == std::string::npos ? std::string() : s.substr(b, e - b + 1);
}

std::string json_escape(const std::string& s) {
    std::string o;
    for (char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += c; }
        else if (c == '\n') o += "\\n";
        else if (static_cast<unsigned char>(c) < 0x20) o += ' ';
        else o += c;
    }
    return o;
}

void read_cpuid_identity(SystemInfo& s) {
#if defined(CV_X86)
    Regs r = cpuid(0);
    char vendor[13] = {};
    std::memcpy(vendor + 0, &r.b, 4);
    std::memcpy(vendor + 4, &r.d, 4);
    std::memcpy(vendor + 8, &r.c, 4);
    s.cpu_vendor = vendor;
    const unsigned max_leaf = r.a;

    Regs f = cpuid(1);
    unsigned family = (f.a >> 8) & 0xF, model = (f.a >> 4) & 0xF;
    if (family == 0xF) family += (f.a >> 20) & 0xFF;
    if (family == 0x6 || family >= 0xF) model += ((f.a >> 16) & 0xF) << 4;
    s.cpu_family = int(family);
    s.cpu_model = int(model);
    s.cpu_stepping = int(f.a & 0xF);
    if (max_leaf >= 7) s.hybrid = (cpuid(7, 0).d >> 15) & 1;

    if (cpuid(0x80000000).a >= 0x80000004) {
        char brand[49] = {};
        for (unsigned i = 0; i < 3; ++i) {
            Regs b = cpuid(0x80000002 + i);
            std::memcpy(brand + 16 * i + 0, &b.a, 4);
            std::memcpy(brand + 16 * i + 4, &b.b, 4);
            std::memcpy(brand + 16 * i + 8, &b.c, 4);
            std::memcpy(brand + 16 * i + 12, &b.d, 4);
        }
        s.cpu_brand = trim(brand);
    }

    // Deterministic cache parameters: Intel leaf 4, AMD leaf 0x8000001D.
    unsigned cache_leaf = 0;
    if (s.cpu_vendor == "GenuineIntel" && max_leaf >= 4) cache_leaf = 4;
    else if (s.cpu_vendor == "AuthenticAMD" && cpuid(0x80000000).a >= 0x8000001D) cache_leaf = 0x8000001D;
    if (cache_leaf) {
        for (unsigned sub = 0; sub < 16; ++sub) {
            Regs c = cpuid(cache_leaf, sub);
            const unsigned type = c.a & 0x1F;
            if (type == 0) break;
            CacheLevelInfo ci;
            ci.level = int((c.a >> 5) & 0x7);
            ci.type = type == 1 ? "data" : type == 2 ? "instruction" : "unified";
            ci.line_bytes = int((c.b & 0xFFF) + 1);
            const unsigned partitions = ((c.b >> 12) & 0x3FF) + 1;
            ci.ways = ((c.a >> 9) & 1) ? -1 : int(((c.b >> 22) & 0x3FF) + 1);
            ci.sets = int(c.c + 1);
            const unsigned ways = ((c.b >> 22) & 0x3FF) + 1;
            ci.size_bytes = std::uint64_t(ways) * partitions * std::uint64_t(ci.line_bytes) * std::uint64_t(ci.sets);
            ci.shared_by_logical = int(((c.a >> 14) & 0xFFF) + 1);  // max IDs sharing (upper bound)
            ci.inclusive_known = true;
            ci.inclusive = (c.d >> 1) & 1;
            ci.source = cache_leaf == 4 ? "cpuid.4" : "cpuid.8000001D";
            s.caches.push_back(ci);
        }
    }

    // TLB parameters: Intel leaf 0x18.
    if (s.cpu_vendor == "GenuineIntel" && max_leaf >= 0x18) {
        const unsigned max_sub = cpuid(0x18, 0).a;
        for (unsigned sub = 0; sub <= max_sub && sub < 32; ++sub) {
            Regs t = cpuid(0x18, sub);
            const unsigned type = t.d & 0x1F;
            if (type == 0) continue;
            TlbInfo ti;
            ti.level = int((t.d >> 5) & 0x7);
            static const char* kTypes[] = {"null", "data", "instruction", "unified", "load", "store"};
            ti.type = type < 6 ? kTypes[type] : "other";
            std::string ps;
            if (t.b & 1) ps += "4K|";
            if (t.b & 2) ps += "2M|";
            if (t.b & 4) ps += "4M|";
            if (t.b & 8) ps += "1G|";
            if (!ps.empty()) ps.pop_back();
            ti.page_sizes = ps;
            const bool fully = (t.d >> 8) & 1;
            const int ways = int((t.b >> 16) & 0xFFFF);
            ti.ways = fully ? -1 : ways;
            ti.entries = ways * int(t.c);
            s.tlbs.push_back(ti);
        }
    }
#else
    (void)s;
#endif
}

std::string compiled_simd() {
    std::string v;
#if defined(__SSE2__) || defined(_M_X64)
    v += "SSE2 ";
#endif
#if defined(__SSE4_2__)
    v += "SSE4.2 ";
#endif
#if defined(__AVX__)
    v += "AVX ";
#endif
#if defined(__AVX2__)
    v += "AVX2 ";
#endif
#if defined(__FMA__)
    v += "FMA ";
#endif
#if defined(__BMI2__)
    v += "BMI2 ";
#endif
#if defined(__AVX512F__)
    v += "AVX512F ";
#endif
    return trim(v);
}

std::string compiler_string() {
#if defined(__clang__)
    return std::string("clang ") + __clang_version__;
#elif defined(__GNUC__)
    return std::string("gcc ") + __VERSION__;
#elif defined(_MSC_VER)
    return "msvc " + std::to_string(_MSC_FULL_VER);
#else
    return "unknown";
#endif
}

#if defined(_WIN32)

template <class F>
void for_each_lpi(LOGICAL_PROCESSOR_RELATIONSHIP rel, F&& f) {
    DWORD len = 0;
    GetLogicalProcessorInformationEx(rel, nullptr, &len);
    if (len == 0) return;
    std::string buf(len, '\0');
    auto* base = reinterpret_cast<SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX*>(&buf[0]);
    if (!GetLogicalProcessorInformationEx(rel, base, &len)) return;
    for (DWORD off = 0; off < len;) {
        auto* p = reinterpret_cast<SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX*>(&buf[0] + off);
        f(*p);
        off += p->Size;
    }
}

int popcount64(std::uint64_t v) {
    int n = 0;
    while (v) { v &= v - 1; ++n; }
    return n;
}

void read_os_windows(SystemInfo& s) {
    // Cores and efficiency classes.
    int cores = 0;
    std::set<int> classes;
    int max_class = 0;
    for_each_lpi(RelationProcessorCore, [&](SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX& p) {
        ++cores;
        classes.insert(p.Processor.EfficiencyClass);
        if (p.Processor.EfficiencyClass > max_class) max_class = p.Processor.EfficiencyClass;
    });
    s.physical_cores = cores;
    s.logical_processors = int(GetActiveProcessorCount(ALL_PROCESSOR_GROUPS));
    if (classes.size() > 1) {
        std::ostringstream os;
        for (int cls : classes) {
            int n = 0, logical = 0;
            for_each_lpi(RelationProcessorCore, [&](SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX& p) {
                if (p.Processor.EfficiencyClass == cls) {
                    ++n;
                    logical += popcount64(p.Processor.GroupMask[0].Mask);
                }
            });
            os << (cls == max_class ? "P" : "E") << "(class " << cls << "): " << n << " cores/" << logical
               << " logical; ";
        }
        s.core_types = trim(os.str());
    }

    // OS view of the caches attached to the pinned logical processor.
    if (g_pinned_cpu >= 0) {
        for_each_lpi(RelationCache, [&](SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX& p) {
            const CACHE_RELATIONSHIP& c = p.Cache;
            if (!((c.GroupMask.Mask >> g_pinned_cpu) & 1)) return;
            CacheLevelInfo ci;
            ci.level = c.Level;
            ci.type = c.Type == CacheData ? "data" : c.Type == CacheInstruction ? "instruction" : "unified";
            ci.size_bytes = c.CacheSize;
            ci.line_bytes = c.LineSize;
            ci.ways = c.Associativity == CACHE_FULLY_ASSOCIATIVE ? -1 : int(c.Associativity);
            ci.sets = (ci.ways > 0 && ci.line_bytes > 0) ? int(c.CacheSize / (std::uint64_t(ci.ways) * ci.line_bytes)) : 0;
            ci.shared_by_logical = popcount64(c.GroupMask.Mask);
            ci.source = "os";
            s.caches.push_back(ci);
        });
    }

    MEMORYSTATUSEX ms;
    ms.dwLength = sizeof(ms);
    if (GlobalMemoryStatusEx(&ms)) s.total_memory_bytes = ms.ullTotalPhys;

    // RtlGetVersion reports the real version regardless of manifest.
    using RtlGetVersionFn = LONG(WINAPI*)(PRTL_OSVERSIONINFOW);
    RTL_OSVERSIONINFOW vi{};
    vi.dwOSVersionInfoSize = sizeof(vi);
    HMODULE nt = GetModuleHandleW(L"ntdll.dll");
    auto fn = nt ? reinterpret_cast<RtlGetVersionFn>(reinterpret_cast<void*>(GetProcAddress(nt, "RtlGetVersion"))) : nullptr;
    if (fn && fn(&vi) == 0) {
        std::ostringstream os;
        os << "Windows " << vi.dwMajorVersion << "." << vi.dwMinorVersion << " build " << vi.dwBuildNumber;
        s.os = os.str();
    } else {
        s.os = "Windows (version unknown)";
    }

    SYSTEM_POWER_STATUS ps;
    if (GetSystemPowerStatus(&ps) && ps.ACLineStatus != 255) {
        s.on_ac_power_known = true;
        s.on_ac_power = ps.ACLineStatus == 1;
    }
}

#elif defined(__linux__)

std::string read_file(const std::string& p) {
    std::ifstream f(p);
    std::stringstream ss;
    ss << f.rdbuf();
    return trim(ss.str());
}

std::uint64_t parse_size(const std::string& v) {
    if (v.empty()) return 0;
    std::uint64_t n = std::strtoull(v.c_str(), nullptr, 10);
    const char u = v.back();
    if (u == 'K') n <<= 10;
    else if (u == 'M') n <<= 20;
    else if (u == 'G') n <<= 30;
    return n;
}

int count_cpu_list(const std::string& list) {
    int n = 0;
    std::stringstream ss(list);
    std::string part;
    while (std::getline(ss, part, ',')) {
        const auto dash = part.find('-');
        if (dash == std::string::npos) { if (!trim(part).empty()) ++n; }
        else n += std::atoi(part.c_str() + dash + 1) - std::atoi(part.c_str()) + 1;
    }
    return n;
}

void read_os_linux(SystemInfo& s) {
    s.logical_processors = int(sysconf(_SC_NPROCESSORS_ONLN));
    std::set<std::string> cores;
    for (int c = 0; c < s.logical_processors; ++c) {
        const std::string base = "/sys/devices/system/cpu/cpu" + std::to_string(c) + "/topology/";
        const std::string pkg = read_file(base + "physical_package_id"), core = read_file(base + "core_id");
        if (!core.empty()) cores.insert(pkg + ":" + core);
    }
    s.physical_cores = int(cores.size());
    const std::string pc = read_file("/sys/devices/cpu_core/cpus"), ec = read_file("/sys/devices/cpu_atom/cpus");
    if (!pc.empty() || !ec.empty())
        s.core_types = "P: logical " + pc + " (" + std::to_string(count_cpu_list(pc)) + "); E: logical " + ec + " (" +
                       std::to_string(count_cpu_list(ec)) + ")";

    const int cpu = g_pinned_cpu >= 0 ? g_pinned_cpu : 0;
    for (int i = 0; i < 8; ++i) {
        const std::string base = "/sys/devices/system/cpu/cpu" + std::to_string(cpu) + "/cache/index" + std::to_string(i) + "/";
        const std::string lvl = read_file(base + "level");
        if (lvl.empty()) break;
        CacheLevelInfo ci;
        ci.level = std::atoi(lvl.c_str());
        const std::string t = read_file(base + "type");
        ci.type = t == "Data" ? "data" : t == "Instruction" ? "instruction" : "unified";
        ci.size_bytes = parse_size(read_file(base + "size"));
        ci.line_bytes = std::atoi(read_file(base + "coherency_line_size").c_str());
        ci.ways = std::atoi(read_file(base + "ways_of_associativity").c_str());
        ci.sets = std::atoi(read_file(base + "number_of_sets").c_str());
        ci.shared_by_logical = count_cpu_list(read_file(base + "shared_cpu_list"));
        ci.source = "os";
        s.caches.push_back(ci);
    }

    s.total_memory_bytes = std::uint64_t(sysconf(_SC_PHYS_PAGES)) * std::uint64_t(sysconf(_SC_PAGESIZE));

    struct utsname u;
    std::string os = "Linux";
    if (uname(&u) == 0) os = std::string(u.sysname) + " " + u.release;
    std::ifstream rel("/etc/os-release");
    std::string line;
    while (std::getline(rel, line))
        if (line.rfind("PRETTY_NAME=", 0) == 0) {
            std::string v = line.substr(12);
            if (v.size() >= 2 && v.front() == '"') v = v.substr(1, v.size() - 2);
            os += " (" + v + ")";
        }
    s.os = os;

    for (const char* ac : {"/sys/class/power_supply/AC/online", "/sys/class/power_supply/ACAD/online",
                           "/sys/class/power_supply/ADP1/online"}) {
        const std::string v = read_file(ac);
        if (!v.empty()) {
            s.on_ac_power_known = true;
            s.on_ac_power = v == "1";
            break;
        }
    }
}

#endif

}  // namespace

// ---- pinning and priority ----------------------------------------------------

std::string pin_current_thread_to_performance_core() {
#if defined(_WIN32)
    // Choose the highest efficiency class (= performance cores on hybrid
    // parts); within it, the first core whose mask does not include CPU 0.
    int best_class = -1, chosen = -1;
    for_each_lpi(RelationProcessorCore, [&](SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX& p) {
        const int cls = p.Processor.EfficiencyClass;
        const std::uint64_t mask = p.Processor.GroupMask[0].Mask;
        if (p.Processor.GroupMask[0].Group != 0 || mask == 0) return;
        int first = 0;
        while (!((mask >> first) & 1)) ++first;
        const bool better = cls > best_class || (cls == best_class && chosen == 0 && first != 0);
        if (better) {
            best_class = cls;
            chosen = first;
        }
    });
    if (chosen < 0) return "";
    if (!SetThreadAffinityMask(GetCurrentThread(), DWORD_PTR(1) << chosen)) return "";
    SetThreadIdealProcessor(GetCurrentThread(), DWORD(chosen));
    Sleep(1);  // let the scheduler migrate the thread
    g_pinned_cpu = chosen;
    return "logical CPU " + std::to_string(chosen) + " (efficiency class " + std::to_string(best_class) + ")";
#elif defined(__linux__)
    int chosen = -1;
    std::ifstream f("/sys/devices/cpu_core/cpus");  // hybrid: P-core list, e.g. "0-7"
    std::string list;
    if (f && std::getline(f, list) && !list.empty()) {
        const int lo = std::atoi(list.c_str());
        const auto dash = list.find('-');
        const int hi = dash == std::string::npos ? lo : std::atoi(list.c_str() + dash + 1);
        chosen = hi > lo ? lo + 2 : lo;  // skip CPU 0 and its SMT sibling when possible
        if (chosen > hi) chosen = lo;
    } else {
        const long n = sysconf(_SC_NPROCESSORS_ONLN);
        chosen = n > 2 ? 2 : 0;
    }
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(chosen, &set);
    if (sched_setaffinity(0, sizeof(set), &set) != 0) return "";
    g_pinned_cpu = chosen;
    return "logical CPU " + std::to_string(chosen);
#else
    return "";
#endif
}

std::string raise_priority() {
#if defined(_WIN32)
    std::string r;
    r += SetPriorityClass(GetCurrentProcess(), HIGH_PRIORITY_CLASS) ? "process=HIGH" : "process=unchanged";
    r += SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_HIGHEST) ? ", thread=HIGHEST" : ", thread=unchanged";
    return r;
#elif defined(__linux__)
    return setpriority(PRIO_PROCESS, 0, -5) == 0 ? "nice=-5" : "nice unchanged (needs privileges)";
#else
    return "unchanged";
#endif
}

// ---- timing --------------------------------------------------------------------

std::uint64_t read_tsc() {
#if defined(CV_X86)
    return __rdtsc();
#else
    return std::uint64_t(std::chrono::steady_clock::now().time_since_epoch().count());
#endif
}

double measure_tsc_ghz(double seconds) {
    using clk = std::chrono::steady_clock;
    const auto t0 = clk::now();
    const std::uint64_t c0 = read_tsc();
    while (std::chrono::duration<double>(clk::now() - t0).count() < seconds) {
    }
    const auto t1 = clk::now();
    const std::uint64_t c1 = read_tsc();
    return double(c1 - c0) / std::chrono::duration<double, std::nano>(t1 - t0).count();
}

double probe_core_ghz(double seconds) {
#if defined(CV_X86) && (defined(__GNUC__) || defined(__clang__))
    // A chain of dependent 64-bit IMULs (3-cycle latency on Intel Core since
    // Sandy Bridge and on AMD Zen). Dependent add-immediate chains are NOT
    // used: Golden Cove (Alder Lake P-cores) folds them at rename and retires
    // several per cycle, which would overstate the clock.
    using clk = std::chrono::steady_clock;
    auto chain = [](int iters) {
        std::uint64_t x = 3;
        for (int i = 0; i < iters; ++i)
            __asm__ volatile(
                "imul %0, %0\n\timul %0, %0\n\timul %0, %0\n\timul %0, %0\n\t"
                "imul %0, %0\n\timul %0, %0\n\timul %0, %0\n\timul %0, %0\n\t"
                : "+r"(x));
        return x;
    };
    // Ramp-up: let the core leave any low-power state before measuring.
    const auto r0 = clk::now();
    while (std::chrono::duration<double>(clk::now() - r0).count() < 0.02) chain(4096);
    std::uint64_t iters = 0;
    const auto t0 = clk::now();
    double elapsed = 0.0;
    do {
        chain(4096);
        iters += 4096;
        elapsed = std::chrono::duration<double, std::nano>(clk::now() - t0).count();
    } while (elapsed < seconds * 1e9);
    return double(iters) * 8.0 * 3.0 / elapsed;
#else
    (void)seconds;
    return 0.0;
#endif
}

MemoryUsage process_memory_usage() {
    MemoryUsage m;
#if defined(_WIN32)
    PROCESS_MEMORY_COUNTERS_EX pmc{};
    pmc.cb = sizeof(pmc);
    if (GetProcessMemoryInfo(GetCurrentProcess(), reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&pmc), sizeof(pmc))) {
        m.peak_working_set = pmc.PeakWorkingSetSize;
        m.peak_private = pmc.PeakPagefileUsage;
    }
#elif defined(__linux__)
    struct rusage ru;
    if (getrusage(RUSAGE_SELF, &ru) == 0) m.peak_working_set = std::uint64_t(ru.ru_maxrss) * 1024;
#endif
    return m;
}

// ---- collection ----------------------------------------------------------------

SystemInfo collect_system_info() {
    SystemInfo s;
    read_cpuid_identity(s);
#if defined(_WIN32)
    read_os_windows(s);
#elif defined(__linux__)
    read_os_linux(s);
#else
    s.os = "unknown";
#endif
    s.compiler = compiler_string();
#if defined(CV_BUILD_FLAGS)
    s.build_flags = CV_BUILD_FLAGS;
#endif
#if defined(CV_BUILD_VARIANT)
    s.build_variant = CV_BUILD_VARIANT;
#endif
    s.simd = compiled_simd();
    s.tsc_ghz = measure_tsc_ghz(0.2);
    return s;
}

namespace {
const CacheLevelInfo* find_cache(const SystemInfo& s, int level, bool data_or_unified) {
    // Prefer CPUID-derived entries, fall back to OS entries.
    for (int pass = 0; pass < 2; ++pass)
        for (const auto& c : s.caches) {
            const bool cpuid_src = c.source.rfind("cpuid", 0) == 0;
            if ((pass == 0) != cpuid_src) continue;
            if (c.level == level && (!data_or_unified || c.type != "instruction")) return &c;
        }
    return nullptr;
}
}  // namespace

std::uint64_t SystemInfo::l1d_bytes() const {
    const auto* c = find_cache(*this, 1, true);
    return c ? c->size_bytes : 0;
}
std::uint64_t SystemInfo::l2_bytes() const {
    const auto* c = find_cache(*this, 2, true);
    return c ? c->size_bytes : 0;
}
std::uint64_t SystemInfo::llc_bytes() const {
    for (int lvl = 4; lvl >= 1; --lvl)
        if (const auto* c = find_cache(*this, lvl, true)) return c->size_bytes;
    return 0;
}
int SystemInfo::line_bytes() const {
    const auto* c = find_cache(*this, 1, true);
    return c ? c->line_bytes : 0;
}

std::string system_info_json(const SystemInfo& s) {
    std::ostringstream o;
    o << "{\n";
    auto kv = [&](const char* k, const std::string& v, bool comma = true) {
        o << "  \"" << k << "\": \"" << json_escape(v) << "\"" << (comma ? ",\n" : "\n");
    };
    auto kn = [&](const char* k, double v, bool comma = true) {
        o << "  \"" << k << "\": " << v << (comma ? ",\n" : "\n");
    };
    kv("cpu_vendor", s.cpu_vendor);
    kv("cpu_brand", s.cpu_brand);
    kn("cpu_family", s.cpu_family);
    kn("cpu_model", s.cpu_model);
    kn("cpu_stepping", s.cpu_stepping);
    o << "  \"hybrid\": " << (s.hybrid ? "true" : "false") << ",\n";
    kn("logical_processors", s.logical_processors);
    kn("physical_cores", s.physical_cores);
    kv("core_types", s.core_types);
    kn("total_memory_bytes", double(s.total_memory_bytes));
    kv("os", s.os);
    kv("compiler", s.compiler);
    kv("build_variant", s.build_variant);
    kv("build_flags", s.build_flags);
    kv("simd_enabled_at_compile_time", s.simd);
    kv("ac_power", s.on_ac_power_known ? (s.on_ac_power ? "yes" : "no (battery)") : "unknown");
    kn("tsc_ghz_measured", s.tsc_ghz);
    kv("pinned_cpu", s.pinned_cpu.empty() ? "none" : s.pinned_cpu);
    kv("priority", s.priority);
    o << "  \"caches\": [\n";
    for (std::size_t i = 0; i < s.caches.size(); ++i) {
        const auto& c = s.caches[i];
        o << "    {\"level\": " << c.level << ", \"type\": \"" << c.type << "\", \"size_bytes\": " << c.size_bytes
          << ", \"line_bytes\": " << c.line_bytes << ", \"ways\": " << c.ways << ", \"sets\": " << c.sets
          << ", \"shared_by_logical\": " << c.shared_by_logical << ", \"inclusive\": "
          << (c.inclusive_known ? (c.inclusive ? "true" : "false") : "null") << ", \"source\": \"" << c.source
          << "\"}" << (i + 1 < s.caches.size() ? "," : "") << "\n";
    }
    o << "  ],\n  \"tlbs\": [\n";
    for (std::size_t i = 0; i < s.tlbs.size(); ++i) {
        const auto& t = s.tlbs[i];
        o << "    {\"level\": " << t.level << ", \"type\": \"" << t.type << "\", \"page_sizes\": \"" << t.page_sizes
          << "\", \"entries\": " << t.entries << ", \"ways\": " << t.ways << ", \"source\": \"cpuid.18\"}"
          << (i + 1 < s.tlbs.size() ? "," : "") << "\n";
    }
    o << "  ],\n";
    o << "  \"hardware_counters\": \"unavailable on this build/platform (no PMU access); see scripts/collect_perf.sh for Linux perf\"\n";
    o << "}\n";
    return o.str();
}

}  // namespace cachevision
