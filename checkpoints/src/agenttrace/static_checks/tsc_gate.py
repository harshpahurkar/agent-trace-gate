"""tsc --noEmit as the static gate for Node targets.

Plain-JS samples are checked with --allowJs/--checkJs, so no build step enters
the quickstart. Diagnostic codes we care about:

    TS2307              cannot find module          -> hallucinated-import
    TS2304/TS2339/TS2551  name/property not found   -> hallucinated-api
    other TSxxxx errors                             -> type-error

`--module nodenext` also turns on esModuleInterop so `import _ from "lodash"`
type-checks against @types/lodash the way Node actually loads it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .. import verdict as V

_CODE_MAP = {
    "TS2307": V.HALLUCINATED_IMPORT,
    "TS2304": V.HALLUCINATED_API,
    "TS2339": V.HALLUCINATED_API,
    "TS2551": V.HALLUCINATED_API,
}

# path/to/file.mjs(12,9): error TS2339: Property 'slugify' does not exist ...
_DIAG_RE = re.compile(r"^(?P<file>.+?)\((?P<line>\d+),\d+\):\s+error\s+(?P<code>TS\d+):\s+(?P<msg>.*)$")


@dataclass
class Diagnostic:
    file: str
    line: int
    code: str
    message: str
    error_type: str

    def short(self) -> str:
        return f"{self.code}: {self.message}"


def _tsc_command(repo_root: Path) -> list[str]:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node not found on PATH — required for the Node static gate")
    tsc_js = repo_root / "node_modules" / "typescript" / "bin" / "tsc"
    if not tsc_js.exists():
        raise RuntimeError("typescript not installed — run `npm ci` at the repo root")
    return [node, str(tsc_js)]


def run(file: Path, repo_root: Path, timeout: float = 120) -> list[Diagnostic]:
    proc = subprocess.run(
        [
            *_tsc_command(repo_root),
            "--noEmit",
            "--allowJs",
            "--checkJs",
            "--skipLibCheck",
            "--pretty", "false",
            "--target", "es2022",
            "--module", "nodenext",
            "--moduleResolution", "nodenext",
            str(file),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=repo_root,
    )
    wanted = str(file.resolve())
    diags = []
    for line in proc.stdout.splitlines():
        match = _DIAG_RE.match(line.strip())
        if not match:
            continue
        diag_file = str((repo_root / match["file"]).resolve())
        if diag_file != wanted:
            continue  # lib/env noise from other files isn't the sample's fault
        diags.append(
            Diagnostic(
                file=match["file"],
                line=int(match["line"]),
                code=match["code"],
                message=match["msg"],
                error_type=_CODE_MAP.get(match["code"], V.TYPE_ERROR),
            )
        )
    return diags
