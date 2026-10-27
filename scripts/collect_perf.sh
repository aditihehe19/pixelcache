#!/usr/bin/env bash
# Hardware-counter collection with Linux `perf stat` (Linux only).
#
# perf stat counts the whole process, which includes image generation, the
# untimed warm-up run and hashing. To isolate the timed runs we use a
# differential measurement: the same configuration is run with R1 and R2
# repetitions (single mode performs exactly one traversal per repetition), and
#     per-run count = (count(R2) - count(R1)) / (R2 - R1)
# cancels every fixed cost. Each difference is repeated `perf stat -r N` times.
#
# Counters that the CPU/kernel does not support are reported by perf as
# "<not supported>" and are written as NA, never estimated.
#
# Usage: scripts/collect_perf.sh [build/cachevision_bench_native] [results/raw/perf_counters.csv]
# Requires: perf, and kernel.perf_event_paranoid <= 2 (or root) for user-space counting.
set -euo pipefail

BENCH=${1:-build/cachevision_bench_native}
OUT=${2:-results/raw/perf_counters.csv}
R1=${R1:-2}
R2=${R2:-12}
PERF_REPEAT=${PERF_REPEAT:-3}
SIZES=${SIZES:-"512 1024 2048 4096"}
OPS=${OPS:-"unpack yuv lab"}
MAPPINGS=${MAPPINGS:-"identity rotate90"}
VARIANTS=${VARIANTS:-"row_major column_major tiled:32x32 tiled:128x128 morton"}
EVENTS_WANTED="cycles,instructions,L1-dcache-loads,L1-dcache-load-misses,l2_rqsts.miss,l2_rqsts.references,LLC-loads,LLC-load-misses,LLC-stores,LLC-store-misses,dTLB-load-misses"

if ! command -v perf >/dev/null 2>&1; then
  echo "perf not found: hardware counters unavailable on this machine (nothing written)" >&2
  exit 1
fi

# Keep only events this machine supports.
EVENTS=""
for e in ${EVENTS_WANTED//,/ }; do
  if perf stat -e "$e" -x, true 2>&1 | grep -qv "not supported\|not counted\|invalid\|Cannot"; then
    EVENTS="${EVENTS:+$EVENTS,}$e"
  else
    echo "event $e unsupported here -> NA" >&2
  fi
done
echo "events: $EVENTS" >&2

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$(dirname "$OUT")"
[ -s "$OUT" ] || echo "width,height,op,mapping,variant,event,per_run_count,per_pixel,source" > "$OUT"

count() {  # count <reps> <args...>  -> "event,value" lines (mean over perf -r)
  local reps=$1; shift
  perf stat -x, -r "$PERF_REPEAT" -e "$EVENTS" -o "$TMP/perf.txt" \
    "$BENCH" --single --reps "$reps" --out "$TMP" "$@" >/dev/null 2>&1
  awk -F, '!/^#/ && NF>3 {print $3","$1}' "$TMP/perf.txt"
}

for n in $SIZES; do
  for op in $OPS; do
    for map in $MAPPINGS; do
      for v in $VARIANTS; do
        args=(--op "$op" --mapping "$map" --variant "$v" --size "${n}x${n}" --image mixed --condition warm)
        count "$R1" "${args[@]}" > "$TMP/a.txt"
        count "$R2" "${args[@]}" > "$TMP/b.txt"
        join -t, <(sort "$TMP/a.txt") <(sort "$TMP/b.txt") | while IFS=, read -r ev a b; do
          if [[ "$a" =~ ^[0-9.]+$ && "$b" =~ ^[0-9.]+$ ]]; then
            per_run=$(awk -v a="$a" -v b="$b" -v r1="$R1" -v r2="$R2" 'BEGIN{printf "%.1f", (b-a)/(r2-r1)}')
            per_px=$(awk -v p="$per_run" -v n="$n" 'BEGIN{printf "%.6f", p/(n*n)}')
          else
            per_run=NA; per_px=NA
          fi
          echo "$n,$n,$op,$map,$v,$ev,$per_run,$per_px,perf-stat-differential" >> "$OUT"
        done
        echo "done $n $op $map $v" >&2
      done
    done
  done
done
echo "wrote $OUT" >&2
