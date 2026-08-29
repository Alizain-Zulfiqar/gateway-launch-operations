#!/usr/bin/env bash
# Gateway Launch Operations — macOS / Linux launcher (clone-and-run).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.matplotlib_cache}"
mkdir -p "$MPLCONFIGDIR"

pick_python() {
  for cmd in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
      echo "$cmd"
      return 0
    fi
  done
  return 1
}

if [[ ! -d venv ]]; then
  echo "First run: creating virtual environment (Python 3.11+ required)..."
  PY="$(pick_python)" || {
    echo "ERROR: Python 3.11+ not found. Install from https://www.python.org/downloads/"
    exit 1
  }
  "$PY" -m venv venv
  venv/bin/python -m pip install -U pip
  venv/bin/pip install -r requirements.txt
  echo ""
fi

exec venv/bin/python main.py "$@"
