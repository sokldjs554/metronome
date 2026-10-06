#!/usr/bin/env bash
# Inference-optimization evidence (protocol P11) and HTTP latency (P13). Run on an otherwise idle machine.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
mkdir -p artifacts/optimization artifacts/serving

"$PY" -m metronome.cli bench artifacts/runs/etth1_dlinear_336_96_s2021.pt --out artifacts/optimization/benchmark_dlinear.json --threads 1 --repeats 300
if [ -f artifacts/runs/etth1_patchtst_336_96_s2021.pt ]; then
  "$PY" -m metronome.cli bench artifacts/runs/etth1_patchtst_336_96_s2021.pt --out artifacts/optimization/benchmark_patchtst.json --threads 1 --repeats 300
fi
if curl -sf http://127.0.0.1:8000/ready >/dev/null 2>&1; then
  "$PY" scripts/http_latency.py --url http://127.0.0.1:8000 --n 500 --out artifacts/serving/http_latency.json
else
  echo "API not running on :8000 — start scripts/dev_stack.sh start first" >&2
fi
echo "== bench done $(date -u +%FT%TZ)"
