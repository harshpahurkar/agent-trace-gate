"""Cursor afterFileEdit hook.

Cursor has no native OpenTelemetry export, so this hook is the entire
observability surface for the Cursor side: it maps Cursor's stdin fields
(file_path, conversation_id) onto the shared provenance recorder, which also
emits a standalone `agent.file_edit` span so Cursor activity shows up in
Jaeger next to everything else. afterFileEdit is observe-only — output is
ignored, so exiting 0 unconditionally is correct here.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hooks" / "common"))

try:
    from provenance import record

    # lstrip the BOM PowerShell 5.1 prepends when piping test payloads by hand
    payload = json.loads(sys.stdin.read().lstrip("\ufeff"))
    file_path = payload.get("file_path")
    if file_path:
        record(
            root=ROOT,
            file=file_path,
            agent="cursor",
            session_id=payload.get("conversation_id"),
            tool="afterFileEdit",
        )
except Exception:
    pass

sys.exit(0)
