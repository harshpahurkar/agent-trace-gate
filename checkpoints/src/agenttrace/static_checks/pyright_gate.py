"""pyright as the static API-surface oracle for Python targets.

`pyright --outputjson` gives machine-readable diagnostics; the rules we map:

    reportMissingImports / reportMissingModuleSource  -> hallucinated-import
    reportAttributeAccessIssue / reportUndefinedVariable -> hallucinated-api
    anything else at error severity                   -> type-error

Note pyright's JSON has shifted over releases: diagnostics carry either a
`file` path or a `uri` (microsoft/pyright#6740) — we accept both.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from .. import verdict as V

_RULE_MAP = {
    "reportMissingImports": V.HALLUCINATED_IMPORT,
    "reportMissingModuleSource": V.HALLUCINATED_IMPORT,
    "reportAttributeAccessIssue": V.HALLUCINATED_API,
    "reportUndefinedVariable": V.HALLUCINATED_API,
}


@dataclass
class Diagnostic:
    file: str
    line: int  # 1-based
    rule: str | None
    message: str
    error_type: str

    def short(self) -> str:
        return self.message.splitlines()[0]


def _diag_file(diag: dict) -> str:
    if "file" in diag:
        return diag["file"]
    if "uri" in diag:
        uri = diag["uri"]
        if isinstance(uri, dict):  # newer pyright: {"_key": "...", "_filePath": "..."}
            return uri.get("_filePath") or uri.get("_key") or ""
        return unquote(urlparse(uri).path).lstrip("/")
    return ""


def run(file: Path, timeout: float = 240) -> list[Diagnostic]:
    """Run pyright over one file, returning error-severity diagnostics only.

    First invocation downloads the bundled pyright distribution, hence the
    generous timeout.
    """
    proc = subprocess.run(
        [
            sys.executable, "-m", "pyright",
            "--outputjson",
            "--level", "error",
            "--pythonpath", sys.executable,
            str(file),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if not proc.stdout.strip():
        raise RuntimeError(f"pyright produced no output (stderr: {proc.stderr.strip()[:400]})")
    payload = json.loads(proc.stdout)

    diags = []
    for diag in payload.get("generalDiagnostics", []):
        if diag.get("severity") != "error":
            continue
        rule = diag.get("rule")
        diags.append(
            Diagnostic(
                file=_diag_file(diag),
                line=diag.get("range", {}).get("start", {}).get("line", 0) + 1,
                rule=rule,
                message=diag.get("message", ""),
                error_type=_RULE_MAP.get(rule or "", V.TYPE_ERROR),
            )
        )
    return diags
