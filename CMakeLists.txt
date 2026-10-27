cmake_minimum_required(VERSION 3.16)
project(CacheVision VERSION 1.0 LANGUAGES CXX)

# ---------------------------------------------------------------------------
# Two build variants of the same sources, so that SIMD effects are never
# confused with memory-access effects:
#   native : -O3 -march=native               (auto-vectorisation ON)
#   scalar : -O3 -march=native -fno-tree-vectorize -fno-tree-slp-vectorize
#            (identical ISA and optimisation level, auto-vectorisation OFF)
# Both use -ffp-contract=off (no FMA contraction) and no -ffast-math, so every
# traversal strategy and both variants evaluate the same rounded float32
# operations per pixel; outputs are bit-identical (verified by the tests).
# ---------------------------------------------------------------------------

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

option(CV_MARCH_NATIVE "Compile with -march=native (otherwise -march=x86-64-v2)" ON)

set(CV_CORE_SOURCES
  src/image_types.cpp
  src/conversion_rgb_yuv.cpp
  src/conversion_rgb_hsv.cpp
  src/conversion_rgb_lab.cpp
  src/traversal_common.cpp
  src/traversal_row_major.cpp
  src/traversal_tiled.cpp
  src/traversal_morton.cpp
  src/adaptive.cpp
  src/benchmark.cpp
  src/system_info.cpp
  src/cache_sim.cpp
)

if(MSVC)
  set(CV_COMMON_FLAGS /O2 /fp:precise /W3)
  set(CV_NATIVE_FLAGS /arch:AVX2)
  set(CV_SCALAR_FLAGS /arch:AVX2)  # MSVC has no portable switch to disable auto-vectorisation
else()
  if(CV_MARCH_NATIVE)
    set(CV_ARCH -march=native)
  else()
    set(CV_ARCH -march=x86-64-v2)
  endif()
  set(CV_COMMON_FLAGS -O3 ${CV_ARCH} -ffp-contract=off -fno-fast-math -Wall -Wextra)
  set(CV_NATIVE_FLAGS "")
  set(CV_SCALAR_FLAGS -fno-tree-vectorize -fno-tree-slp-vectorize)
endif()

function(cv_add_core variant)
  set(lib cachevision_core_${variant})
  add_library(${lib} STATIC ${CV_CORE_SOURCES})
  target_include_directories(${lib} PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
  if(variant STREQUAL "native")
    set(vflags ${CV_COMMON_FLAGS} ${CV_NATIVE_FLAGS})
  else()
    set(vflags ${CV_COMMON_FLAGS} ${CV_SCALAR_FLAGS})
  endif()
  target_compile_options(${lib} PUBLIC ${vflags})
  string(REPLACE ";" " " flag_str "${vflags}")
  target_compile_definitions(${lib} PUBLIC
    CV_BUILD_VARIANT="${variant}"
    CV_BUILD_FLAGS="${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}: ${flag_str}")
  if(WIN32)
    target_link_libraries(${lib} PUBLIC psapi)
  endif()
endfunction()

cv_add_core(native)
cv_add_core(scalar)

# Benchmark drivers (one per variant) and tools.
add_executable(cachevision_bench_native benchmarks/run_benchmarks.cpp)
target_link_libraries(cachevision_bench_native PRIVATE cachevision_core_native)
add_executable(cachevision_bench_scalar benchmarks/run_benchmarks.cpp)
target_link_libraries(cachevision_bench_scalar PRIVATE cachevision_core_scalar)

add_executable(cachevision_sim benchmarks/run_cachesim.cpp)
target_link_libraries(cachevision_sim PRIVATE cachevision_core_native)

add_executable(cachevision src/main.cpp)
target_link_libraries(cachevision PRIVATE cachevision_core_native)

# Tests (correctness is checked for both variants).
enable_testing()
foreach(variant native scalar)
  foreach(t test_conversion test_traversal test_correctness)
    add_executable(${t}_${variant} tests/${t}.cpp)
    target_link_libraries(${t}_${variant} PRIVATE cachevision_core_${variant})
    target_include_directories(${t}_${variant} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tests)
    add_test(NAME ${t}_${variant} COMMAND ${t}_${variant} WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
  endforeach()
endforeach()

# Static runtime on MinGW so binaries run outside the toolchain shell.
if(MINGW)
  foreach(tgt cachevision_bench_native cachevision_bench_scalar cachevision_sim cachevision)
    target_link_options(${tgt} PRIVATE -static)
  endforeach()
  foreach(variant native scalar)
    foreach(t test_conversion test_traversal test_correctness)
      target_link_options(${t}_${variant} PRIVATE -static)
    endforeach()
  endforeach()
endif()
