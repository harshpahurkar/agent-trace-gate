"""Launch the Node harness in an isolated subprocess.

`node --import instrument.mjs` bootstraps the OpenTelemetry NodeSDK before a
single line of the untrusted sample evaluates; harness.mjs then imports the
sample, Proxy-wraps the contract entrypoint into a `code.call` span, invokes
it, and zod-validates the return value. Same verdict-marker protocol and the
same timeout/env containment as the Python runner.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .. import verdict as V
from .result import HarnessResult, parse_marker, sandbox_env


def run(
    sample: Path,
    contract: Path | None,
    repo_root: Path,
    timeout: float,
    traceparent: str | None,
    otel_enabled: bool,
) -> HarnessResult:
    node = shutil.which("node")
    if not node:
        return HarnessResult(
            stage="harness",
            verdict="fail",
            error_type=V.HARNESS_ERROR,
            message="node not found on PATH",
        )
    instrument = (repo_root / "runtime-node" / "instrument.mjs").resolve()
    harness = (repo_root / "runtime-node" / "harness.mjs").resolve()
    cmd = [
        node,
        "--no-warnings",
        "--import", instrument.as_uri(),
        str(harness),
        str(sample.resolve()),
        str(contract.resolve()) if contract else "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=repo_root,  # bare-specifier resolution against the root node_modules
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
