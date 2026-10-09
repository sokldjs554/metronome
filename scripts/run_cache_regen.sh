#!/usr/bin/env bash
# Rebuild every refit cache with the backward evaluation window (each model also evaluated on its
# validation span before its day; docs/protocol.md change log 2026-10-09). Training is deterministic
# (seeded, one thread per worker), so the forward part reproduces the previous caches bit for bit;
# scripts/compare_caches.py checks that before the new caches replace the old ones.
# Order: pre-registered seeds first (headline tables), then the extra seeds, then the sliding variants.
# Resumable: finished caches are skipped.
#   OUT=artifacts/cache_v2 scripts/run_cache_regen.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
OUT=${OUT:-artifacts/cache_v2}
mkdir -p artifacts/logs "$OUT"
build() {  # build <dataset> <seed> [--window sliding]
  local ds=$1 seed=$2; shift 2
  local suffix=""
  for a in "$@"; do [ "$a" = "sliding" ] && suffix="_sliding"; done
  local name="${ds}_dlinear_s${seed}${suffix}"
  if [ -f "$OUT/${name}.npz" ]; then echo "skip ${name}"; return; fi
  echo "== $(date -u +%FT%TZ) cache ${name}"
  "$PY" -m metronome.cli cache "$ds" --seed "$seed" --workers 4 --cache-dir "$OUT" "$@" 2>&1 | tee "artifacts/logs/regen_${name}.log"
}
for seed in 0 1 2; do for ds in etth2 etth1 weather; do build "$ds" "$seed"; done; done
for seed in 0 1 2; do build electricity20 "$seed"; done
for seed in 3 4 5 6 7; do for ds in etth2 etth1 weather; do build "$ds" "$seed"; done; done
for seed in 0 1 2; do for ds in etth1 etth2; do build "$ds" "$seed" --window sliding; done; done
echo "== regen done $(date -u +%FT%TZ)"
