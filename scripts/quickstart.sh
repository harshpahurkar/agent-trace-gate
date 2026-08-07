#!/usr/bin/env bash
# One-shot quickstart for macOS/Linux/Git Bash. Run from the repo root:
#   ./scripts/quickstart.sh
# Prerequisites: Docker running, Python 3.10+, Node 20.6+.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/4] starting Jaeger (docker compose up -d)..."
docker compose up -d

echo "[2/4] installing the checkpoint engine..."
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/python -m pip install --quiet -e ./checkpoints

echo "[3/4] installing node runtime deps..."
npm ci --no-audit --no-fund

echo "[4/4] running the seeded demo..."
./.venv/bin/agenttrace demo

echo
echo "open http://localhost:16686 -> service 'agenttrace' to explore the traces"
