#!/usr/bin/env bash
# Warm-start daily refit chains (protocol P6 variant) for etth1/etth2, one process per seed in parallel.
#   SEEDS="0" scripts/run_warm_all.sh      # only seed 0
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
SEEDS=${SEEDS:-"0 1 2"}
mkdir -p artifacts/logs
for ds in etth1 etth2; do
  for seed in $SEEDS; do
    name="${ds}_dlinear_s${seed}_warm"
    if [ -f "artifacts/cache/${name}.npz" ]; then echo "skip ${name}"; continue; fi
    "$PY" -m metronome.cli warm "$ds" --seed "$seed" --epochs 2 --lr 0.001 --threads 1 \
      > "artifacts/logs/${name}.log" 2>&1 &
  done
done
wait
echo "== warm chains done $(date -u +%FT%TZ)"
