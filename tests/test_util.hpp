// Tiny self-contained test harness (no external framework required).
#pragma once

#include <cmath>
#include <cstdio>
#include <functional>
#include <string>
#include <vector>

namespace cvtest {

struct Registry {
    std::vector<std::pair<std::string, std::function<void()>>> tests;
    int failures = 0;
    int checks = 0;
    static Registry& get() {
        static Registry r;
        return r;
    }
};

struct Register {
    Register(const char* name, std::function<void()> f) { Registry::get().tests.emplace_back(name, std::move(f)); }
};

inline void fail(const char* file, int line, const std::string& msg) {
    ++Registry::get().failures;
    std::fprintf(stderr, "  FAIL %s:%d: %s\n", file, line, msg.c_str());
}

inline int run_all() {
    auto& r = Registry::get();
    for (auto& t : r.tests) {
        const int before = r.failures;
        t.second();
        std::fprintf(stderr, "%s %s\n", r.failures == before ? "[ ok ]" : "[FAIL]", t.first.c_str());
    }
    std::fprintf(stderr, "%zu tests, %d checks, %d failures\n", r.tests.size(), r.checks, r.failures);
    return r.failures == 0 ? 0 : 1;
}

}  // namespace cvtest

#define CV_TEST(name)                                         \
    static void name();                                       \
    static cvtest::Register reg_##name(#name, &name);         \
    static void name()

#define CHECK(cond)                                                              \
    do {                                                                         \
        ++cvtest::Registry::get().checks;                                        \
        if (!(cond)) cvtest::fail(__FILE__, __LINE__, "CHECK(" #cond ")");      \
    } while (0)

#define CHECK_NEAR(a, b, tol)                                                                          \
    do {                                                                                               \
        ++cvtest::Registry::get().checks;                                                              \
        const double va_ = double(a), vb_ = double(b);                                                 \
        if (!(std::fabs(va_ - vb_) <= (tol)))                                                          \
            cvtest::fail(__FILE__, __LINE__,                                                           \
                         std::string(#a " = ") + std::to_string(va_) + ", " #b " = " + std::to_string(vb_) + \
                             ", tol " + std::to_string(double(tol)));                                  \
    } while (0)

#define CV_TEST_MAIN() \
    int main() { return cvtest::run_all(); }
