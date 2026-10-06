#!/usr/bin/env bash
# Build every refit cache in docs/protocol.md P6, in priority order. Each build uses 4 worker
# processes with one torch thread each. Logs go to artifacts/logs/.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
mkdir -p artifacts/logs
run() { echo "== $(date -u +%FT%TZ) $*"; "$PY" -m metronome.cli "$@"; }

for seed in 0 1 2; do
  for ds in etth1 etth2 weather electricity20; do
    name="${ds}_dlinear_s${seed}"
    if [ -f "artifacts/cache/${name}.npz" ]; then echo "skip ${name}"; continue; fi
    run cache "$ds" --seed "$seed" --workers 4 2>&1 | tee "artifacts/logs/cache_${name}.log"
  done
done
for seed in 0 1 2; do
  for ds in etth1 etth2; do
    name="${ds}_dlinear_s${seed}_sliding"
    if [ -f "artifacts/cache/${name}.npz" ]; then echo "skip ${name}"; continue; fi
    run cache "$ds" --seed "$seed" --window sliding --workers 4 2>&1 | tee "artifacts/logs/cache_${name}.log"
  done
done
echo "== caches done $(date -u +%FT%TZ)"
