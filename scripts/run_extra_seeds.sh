#!/usr/bin/env bash
# Extra seeds (3..7) for the cold-refit cache of etth1, etth2 and weather: the protocol's post-hoc
# robustness extension (docs/protocol.md, change log 2026-10-07). Seed-major order, so an interrupted
# run still leaves every finished seed complete across all three datasets. Resumable: finished
# caches are skipped. No sliding/warm variants (H3/H4 stay on seeds 0-2).
#   SEEDS="3 4" scripts/run_extra_seeds.sh     # a subset
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
SEEDS=${SEEDS:-"3 4 5 6 7"}
DATASETS=${DATASETS:-"etth1 etth2 weather"}
mkdir -p artifacts/logs
for seed in $SEEDS; do
  for ds in $DATASETS; do
    name="${ds}_dlinear_s${seed}"
    if [ -f "artifacts/cache/${name}.npz" ]; then echo "skip ${name}"; continue; fi
    echo "== $(date -u +%FT%TZ) cache ${ds} seed ${seed}"
    "$PY" -m metronome.cli cache "$ds" --seed "$seed" --workers 4 2>&1 | tee "artifacts/logs/cache_${name}.log"
  done
  echo "== seed ${seed} done $(date -u +%FT%TZ)"
done
echo "== extra seeds done $(date -u +%FT%TZ)"
