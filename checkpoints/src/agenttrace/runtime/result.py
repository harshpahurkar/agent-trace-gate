"""Shared verdict protocol between the runners and the sandboxed harnesses.

Both harnesses (Python and Node) print exactly one marker line to stdout:

    AGENTTRACE_VERDICT:{"stage": ..., "verdict": ..., ...}

The sample under test may print whatever it wants; the runner scans for the
last marker line. No marker at all means our harness broke, which is a
harness-error — never blamed on the sample.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .. import otel
from .. import verdict as V

MARKER = "AGENTTRACE_VERDICT:"

# env vars the sandbox child actually needs; everything else is dropped
_KEEP_ENV = {
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATH", "PATHEXT",
    "TEMP", "TMP", "HOME", "USERPROFILE", "LANG", "LC_ALL",
}


@dataclass
class HarnessResult:
    stage: str  # "import" | "call" | "contract" | "ok"
    verdict: str  # "pass" | "fail"
    error_type: str | None = None
    message: str = ""
    detail: dict = field(default_factory=dict)
    violations: list = field(default_factory=list)
    calls: int = 0

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"


def sandbox_env(traceparent: str | None, otel_enabled: bool) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in _KEEP_ENV}
    env["PYTHONIOENCODING"] = "utf-8"
    env["OTEL_EXPORTER_OTLP_ENDPOINT"] = otel.endpoint()
    env["OTEL_SERVICE_NAME"] = otel.SERVICE
    env["AGENTTRACE_OTEL"] = "on" if otel_enabled else "off"
    if traceparent:
        env["TRACEPARENT"] = traceparent
    return env


def parse_marker(stdout: str, stderr: str = "") -> HarnessResult:
    payload = None
    for line in stdout.splitlines():
        if line.startswith(MARKER):
            payload = line[len(MARKER):]
    if payload is None:
        tail = (stderr or stdout).strip().splitlines()[-6:]
        return HarnessResult(
            stage="harness",
            verdict="fail",
            error_type=V.HARNESS_ERROR,
            message="harness produced no verdict",
            detail={"output_tail": tail},
        )
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return HarnessResult(
            stage="harness",
            verdict="fail",
            error_type=V.HARNESS_ERROR,
            message=f"unparseable harness verdict: {exc}",
        )
    return HarnessResult(
        stage=data.get("stage", "ok"),
        verdict=data.get("verdict", "fail"),
        error_type=data.get("error_type"),
        message=data.get("message", ""),
        detail=data.get("detail") or {},
        violations=data.get("violations") or [],
        calls=int(data.get("calls") or 0),
    )
