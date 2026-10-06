#!/usr/bin/env bash
# Local two-process stack for development and demo capture.
#   scripts/dev_stack.sh init      # fresh registry (deletes registry/<dataset>) and v0001
#   scripts/dev_stack.sh start     # API on :8000 + worker, logs in artifacts/logs
#   scripts/dev_stack.sh stop
#   scripts/dev_stack.sh restart   # init + stop + start
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
DATASET=${DATASET:-etth1}
PORT=${PORT:-8000}
REG="$PWD/registry/$DATASET"
LOGS="$PWD/artifacts/logs"
mkdir -p "$LOGS"

stop() {
  for f in "$LOGS/serve.pid" "$LOGS/worker.pid"; do
    if [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null; then
      kill "$(cat "$f")" 2>/dev/null || true
    fi
    rm -f "$f"
  done
  sleep 1
}

init() {
  rm -rf "$REG"
  "$PY" -m metronome.cli deploy-init "$DATASET" --registry "$REG" --threads 2 --max-epochs 10 2>/dev/null \
    | grep -E '"version"|val_mae_fixed|max_abs_diff' || true
}

start() {
  nohup setsid "$PY" -m metronome.cli serve --registry "$REG" --host 127.0.0.1 --port "$PORT" --threads 1 \
    > "$LOGS/serve.log" 2>&1 < /dev/null &
  echo $! > "$LOGS/serve.pid"
  for _ in $(seq 1 40); do curl -sf "http://127.0.0.1:$PORT/ready" >/dev/null 2>&1 && break; sleep 0.5; done
  nohup setsid "$PY" -m metronome.cli worker --registry "$REG" --api-url "http://127.0.0.1:$PORT" --threads 1 \
    --max-epochs 10 --poll-seconds 1 > "$LOGS/worker.log" 2>&1 < /dev/null &
  echo $! > "$LOGS/worker.pid"
  sleep 1
  curl -s "http://127.0.0.1:$PORT/ready"; echo
}

case "${1:-}" in
  init) init ;;
  start) start ;;
  stop) stop ;;
  restart) stop; init; start ;;
  *) echo "usage: $0 {init|start|stop|restart}"; exit 2 ;;
esac
