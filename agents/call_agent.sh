#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
ROLE="${1:?role required}"
PROMPT_FILE="${2:?prompt file required}"
WORKDIR="${3:?workdir required}"

if [[ "$ROLE" == "referral" || "$ROLE" == "buyer" ]]; then
  exec "$PYTHON_BIN" "$ROOT/agents/live_referral.py" "$PROMPT_FILE" "$WORKDIR"
fi

if [[ "$ROLE" == "seller-c" ]]; then
  exec "$PYTHON_BIN" "$ROOT/agents/mock_seller.py" seller-c "${SR_TASK_ID:?SR_TASK_ID required}"
fi

exec "$PYTHON_BIN" "$ROOT/agents/live_seller.py" "$ROLE" "$PROMPT_FILE" "$WORKDIR"
