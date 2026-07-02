"""Read the provenance ledger the agent hooks write.

`.agent-trace/provenance.jsonl` gets one line per AI file edit:

    {"file": "src/x.py", "agent": "claude-code", "session_id": "...",
     "tool": "Edit", "ts": "2026-08-27T18:04:11+00:00", "traceparent": null}

`agenttrace check` uses it locally to gate exactly the files an agent touched;
in CI (fresh checkout, no ledger) it falls back to `git diff` vs the PR base.
"""

from __future__ import annotations

import json
from pathlib import Path

LEDGER = Path(".agent-trace") / "provenance.jsonl"


def read_ledger(root: Path) -> dict[str, dict]:
    """Latest ledger entry per repo-relative file path."""
    path = root / LEDGER
    entries: dict[str, dict] = {}
    if not path.exists():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        file = entry.get("file")
        if not file:
            continue
        rel = _relativize(root, file)
        if rel:
            entries[rel] = entry
    return entries


def _relativize(root: Path, file: str) -> str | None:
    p = Path(file)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(root.resolve())
        except ValueError:
            return None
    return p.as_posix()
