#!/usr/bin/env bash
# Build every refit cache in docs/protocol.md P6. Each build uses 4 worker processes with one
# torch thread each; existing caches are skipped, so the script can be re-run after an interruption.
# Order: the cheap datasets for all seeds first, then the sliding/warm variants, then the expensive
# electricity20 seeds, so a partial run still covers the protocol's main table.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
mkdir -p artifacts/logs
run() { echo "== $(date -u +%FT%TZ) $*"; "$PY" -m metronome.cli "$@"; }
build() {  # build <dataset> <seed> [extra args...]; name is derived like CacheConfig.name
  local ds=$1 seed=$2; shift 2
  local suffix=""
  for a in "$@"; do [ "$a" = "sliding" ] && suffix="_sliding"; done
  local name="${ds}_dlinear_s${seed}${suffix}"
  if [ -f "artifacts/cache/${name}.npz" ]; then echo "skip ${name}"; return; fi
  run cache "$ds" --seed "$seed" --workers 4 "$@" 2>&1 | tee "artifacts/logs/cache_${name}.log"
}

build electricity20 0
for seed in 0 1 2; do for ds in etth1 etth2 weather; do build "$ds" "$seed"; done; done
for seed in 1 2; do build electricity20 "$seed"; done
for seed in 0 1 2; do for ds in etth1 etth2; do build "$ds" "$seed" --window sliding; done; done
echo "== caches done $(date -u +%FT%TZ)"
