"""Launch the Python harness in an isolated subprocess.

`python -I` gives isolated mode (no PYTHONPATH / user site / script dir on
sys.path) while still seeing the engine's own virtualenv, so the harness can
import opentelemetry and pydantic. The child runs in a scratch cwd with a
stripped environment plus a hard wall-clock timeout — observation-grade
containment, not a security boundary (see docs/limitations.md).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from .. import verdict as V
from .result import HarnessResult, parse_marker, sandbox_env

HARNESS = Path(__file__).with_name("py_harness.py")


def run(
    sample: Path,
    contract: Path | None,
    timeout: float,
    traceparent: str | None,
    otel_enabled: bool,
) -> HarnessResult:
    cmd = [
        sys.executable,
        "-I",
        str(HARNESS),
        str(sample.resolve()),
        str(contract.resolve()) if contract else "-",
    ]
    with tempfile.TemporaryDirectory(prefix="agenttrace-") as scratch:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=scratch,
                env=sandbox_env(traceparent, otel_enabled),
            )
        except subprocess.TimeoutExpired:
            return HarnessResult(
                stage="call",
                verdict="fail",
                error_type=V.TIMEOUT,
                message=f"sandbox exceeded {timeout:g}s wall-clock limit",
            )
    return parse_marker(proc.stdout, proc.stderr)
