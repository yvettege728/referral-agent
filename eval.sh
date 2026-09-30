#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then PYTHON="$ROOT/.venv/bin/python"; else PYTHON=python3; fi
fi
# The same eight tasks and interventions are used in both arms.
TASKS=(01 02 04 03 01 04 02 03)
exec "$PYTHON" "$ROOT/evaluate.py" "$@" "${TASKS[@]}"
