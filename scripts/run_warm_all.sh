#!/usr/bin/env bash
# Warm-start daily refit chains (protocol P6 variant) for etth1/etth2 x 3 seeds, three at a time.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
mkdir -p artifacts/logs
for ds in etth1 etth2; do
  for seed in 0 1 2; do
    name="${ds}_dlinear_s${seed}_warm"
    if [ -f "artifacts/cache/${name}.npz" ]; then echo "skip ${name}"; continue; fi
    "$PY" -m metronome.cli warm "$ds" --seed "$seed" --epochs 2 --lr 0.001 --threads 1 \
      > "artifacts/logs/${name}.log" 2>&1 &
  done
  wait
done
echo "== warm chains done $(date -u +%FT%TZ)"
