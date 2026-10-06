#!/usr/bin/env bash
# Remaining experiment queue, cheapest-and-most-informative first, so that an interrupted run still
# covers the protocol's main table (3 seeds on etth1/etth2/weather, 1+ seed on electricity20),
# the sliding-window and warm-start variants for seed 0, and only then the expensive extra seeds.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
mkdir -p artifacts/logs
run() { echo "== $(date -u +%FT%TZ) $*"; "$PY" -m metronome.cli "$@"; }
build() {
  local ds=$1 seed=$2; shift 2
  local suffix=""
  for a in "$@"; do [ "$a" = "sliding" ] && suffix="_sliding"; done
  local name="${ds}_dlinear_s${seed}${suffix}"
  if [ -f "artifacts/cache/${name}.npz" ]; then echo "skip ${name}"; return; fi
  run cache "$ds" --seed "$seed" --workers 4 "$@" 2>&1 | tee "artifacts/logs/cache_${name}.log"
}

for ds in etth1 etth2 weather; do build "$ds" 2; done
build etth1 0 --window sliding
build etth2 0 --window sliding
SEEDS="0" bash scripts/run_warm_all.sh
echo "== main table + seed-0 variants done $(date -u +%FT%TZ)"
build electricity20 1
build electricity20 2
for seed in 1 2; do build etth1 "$seed" --window sliding; build etth2 "$seed" --window sliding; done
SEEDS="1 2" bash scripts/run_warm_all.sh
echo "== caches done $(date -u +%FT%TZ)"
