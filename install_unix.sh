#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if ! command -v python3.11 >/dev/null 2>&1; then
  echo "Install Python 3.11 64-bit using your OS package manager, then retry."
  exit 1
fi
python3.11 -m venv .venv
.venv/bin/python setup_runtime.py
echo "Start with: .venv/bin/python app.py"
