#!/usr/bin/env bash
# Paper-reproduction and leaderboard runs under the standard LTSF split (docs/protocol.md P10).
# Single-threaded so it can share the machine with the cache builds.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
mkdir -p artifacts/logs artifacts/runs
run() { echo "== $(date -u +%FT%TZ) $*"; "$PY" -m metronome.cli "$@"; }
have() { [ -f "artifacts/runs/$1.json" ]; }

# 1) reproduction targets first
for ds in etth1 etth2; do
  have "${ds}_dlinear_336_96_s2021" || run ltsf "$ds" --model dlinear --kind etth --horizon 96
done
for ds in etth1 etth2; do
  have "${ds}_patchtst_336_96_s2021" || run ltsf "$ds" --model patchtst --kind etth --horizon 96
done
# 2) linear family at every horizon, baselines
for ds in etth1 etth2; do
  for model in naive seasonal_naive linear nlinear dlinear; do
    for h in 96 192 336 720; do
      have "${ds}_${model}_336_${h}_s2021" || run ltsf "$ds" --model "$model" --kind etth --horizon "$h"
    done
  done
done
# 3) leaderboard on the other prepared datasets (70/10/20 split), H=96
for ds in weather electricity20; do
  for model in naive seasonal_naive linear nlinear dlinear; do
    have "${ds}_${model}_336_96_s2021" || run ltsf "$ds" --model "$model" --kind other --horizon 96
  done
done
echo "== ltsf done $(date -u +%FT%TZ)"
