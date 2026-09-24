#!/usr/bin/env bash
# One-shot project setup: create .venv if missing, install requirements.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Creating .venv..."
    python -m venv .venv
fi

.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt

echo "Done. Run: source .venv/bin/activate"
