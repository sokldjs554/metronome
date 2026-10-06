#!/usr/bin/env bash
# Idle-machine measurements, in order: serving stack up -> ONNX/INT8 benchmarks (P11) -> HTTP latency
# (P13) -> big-data engines (P12, 3 repeats) -> stack down -> resume the remaining cache queue.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
export MLFLOW_DISABLE_AGENT_HINT=1
echo "== final stage start $(date -u +%FT%TZ)"
PY="$PY" bash scripts/dev_stack.sh restart
PY="$PY" bash scripts/run_bench_all.sh
PY="$PY" bash scripts/dev_stack.sh stop
rm -rf artifacts/bigdata
"$PY" -m metronome.cli bigdata --local-dir /home/user/data-raw --repeats 3 --out-dir artifacts/bigdata 2>&1 | grep -vE "WARN|INFO|Picked up JAVA|^\s*$"
echo "== final stage done $(date -u +%FT%TZ)"
PY="$PY" nohup setsid bash scripts/run_cache_rest.sh >> artifacts/logs/run_cache_all.log 2>&1 < /dev/null &
echo "== cache queue resumed $(date -u +%FT%TZ)"
