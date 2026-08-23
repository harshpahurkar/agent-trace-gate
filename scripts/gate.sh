#!/usr/bin/env bash
# The full local gate — everything a CI job would have run, on your machine.
#
#   ./scripts/gate.sh
#
# Runs the seeded proof (both detection paths), the unit tests, and the
# provenance-ledger gate. Exits nonzero if anything fails, so it is safe to
# bind to a git hook, a file watcher, or a keybinding.
set -uo pipefail
cd "$(dirname "$0")/.."

if [ -x ".venv/bin/agenttrace" ]; then
  AGENTTRACE=".venv/bin/agenttrace"; PY=".venv/bin/python"
elif [ -x ".venv/Scripts/agenttrace.exe" ]; then
  AGENTTRACE=".venv/Scripts/agenttrace.exe"; PY=".venv/Scripts/python.exe"
else
  AGENTTRACE="agenttrace"; PY="python"
fi

status=0
step() {
  echo ""
  echo "-- $1 ---------------------------------------"
  shift
  "$@" || status=1
}

step "seeded proof (static checkpoints)"        "$AGENTTRACE" demo --report ci
step "seeded proof (runtime detonation paths)"  "$AGENTTRACE" demo --skip-static --report ci
step "unit tests"                               "$PY" -m pytest tests -q
step "ledger gate"                              "$AGENTTRACE" check --report ci

echo ""
if [ "$status" -eq 0 ]; then
  echo "gate: PASS"
else
  echo "gate: FAIL"
fi
exit "$status"
