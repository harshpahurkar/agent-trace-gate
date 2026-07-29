"""Shared provenance recorder used by both agent hooks (Claude Code + Cursor).

Stdlib only, deliberately: hook subprocesses run outside any virtualenv, and
Claude Code does not propagate OTEL_* env vars to hooks — so this module
appends to the ledger and hand-rolls a single OTLP/JSON span POST with
urllib instead of pulling in the SDK.

Every failure path is swallowed: a provenance hiccup must never block or slow
the agent that triggered it.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

LEDGER = Path(".agent-trace") / "provenance.jsonl"
_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


def record(
    root: str | Path,
    file: str,
    agent: str,
    session_id: str | None = None,
    tool: str | None = None,
    traceparent: str | None = None,
) -> dict:
    root = Path(root)
    entry = {
        "file": _relativize(root, file),
        "agent": agent,
        "session_id": session_id,
        "tool": tool,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "traceparent": traceparent,
    }
    try:
        ledger = root / LEDGER
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass

    emit_span(
        "agent.file_edit",
        {
            "code.filepath": entry["file"],
            "agent.name": agent,
            "agent.session_id": session_id or "",
            "agent.tool": tool or "",
        },
        traceparent=traceparent,
    )
    return entry


def _relativize(root: Path, file: str) -> str:
    p = Path(file)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(root.resolve())
        except ValueError:
            pass
    return p.as_posix()


def emit_span(name: str, attributes: dict, traceparent: str | None = None) -> None:
    """POST one span via OTLP/JSON. Joins the agent's trace when a W3C
    traceparent is available (Claude Code's beta tracing propagates
    TRACEPARENT to subprocesses); otherwise starts a fresh trace."""
    endpoint = os.environ.get("AGENTTRACE_HOOK_OTLP", "http://localhost:4318").rstrip("/")

    parent_span_id = None
    trace_id = uuid.uuid4().hex
    if traceparent:
        match = _TRACEPARENT.match(traceparent.strip().lower())
        if match:
            trace_id, parent_span_id = match.group(1), match.group(2)

    now = time.time_ns()
    span = {
        "traceId": trace_id,
        "spanId": uuid.uuid4().hex[:16],
        "name": name,
        "kind": 1,
        "startTimeUnixNano": str(now),
        "endTimeUnixNano": str(now + 1_000_000),
        "attributes": [
            {"key": k, "value": {"stringValue": str(v)}} for k, v in attributes.items()
        ],
    }
    if parent_span_id:
        span["parentSpanId"] = parent_span_id

    body = json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "agent-hooks"}}
                        ]
                    },
                    "scopeSpans": [{"scope": {"name": "agenttrace.hooks"}, "spans": [span]}],
                }
            ]
        }
    ).encode()

    try:
        request = urllib.request.Request(
            endpoint + "/v1/traces", data=body, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(request, timeout=1.5).close()
    except OSError:
        pass  # collector down — the ledger entry is still on disk
