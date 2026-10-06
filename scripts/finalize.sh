#!/usr/bin/env bash
# After the experiment scripts finish: simulate every cache, aggregate, fill the documents' numbers,
# and re-run the checks. Idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}

names=$(ls artifacts/cache/*.npz | grep -v _warm | xargs -n1 basename | sed 's/.npz//')
"$PY" -m metronome.cli simulate $names
"$PY" -m metronome.cli report
"$PY" scripts/check_numbers.py --fix README.md docs/results.md docs/reproduction.md docs/serving.md docs/bigdata.md || true
"$PY" scripts/check_numbers.py --require-markers README.md docs/results.md docs/reproduction.md docs/serving.md docs/bigdata.md
echo "== finalize done $(date -u +%FT%TZ)"
