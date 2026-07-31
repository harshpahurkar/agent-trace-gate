"""Claude Code PostToolUse hook (matcher: Edit|Write).

Receives the hook payload as JSON on stdin, appends the touched file to the
provenance ledger, and emits an `agent.file_edit` span. Exit 0 always —
provenance must never block the agent.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hooks" / "common"))

try:
    from provenance import record

    # lstrip the BOM PowerShell 5.1 prepends when piping test payloads by hand
    payload = json.loads(sys.stdin.read().lstrip("\ufeff"))
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if file_path:
        record(
            root=ROOT,
            file=file_path,
            agent="claude-code",
            session_id=payload.get("session_id"),
            tool=payload.get("tool_name"),
            traceparent=os.environ.get("TRACEPARENT"),
        )
except Exception:
    pass

sys.exit(0)
