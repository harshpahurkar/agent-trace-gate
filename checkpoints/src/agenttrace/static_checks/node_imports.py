"""Static import scan for Node targets.

A lightweight specifier scan (static `import ... from`, side-effect imports,
dynamic `import()`, and `require()`), filtered down to bare specifiers. Local
resolution order:

    node: prefix / builtin module -> declared in package.json -> node_modules

Unresolved bare specifiers go to the npm registry check. This is intentionally
a demo-grade scanner, not a full ES parser — `tsc --noEmit` (TS2307) backs it
up in the static.types checkpoint.
"""

from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_IMPORT_PATTERNS = (
    re.compile(r"""import\s+[\w${},*\s]+\s+from\s+['"]([^'"]+)['"]"""),
    re.compile(r"""import\s*['"]([^'"]+)['"]"""),
    re.compile(r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
)

# fallback when node isn't available to ask directly
_COMMON_BUILTINS = {
    "assert", "buffer", "child_process", "crypto", "events", "fs", "http",
    "https", "module", "net", "os", "path", "process", "readline", "stream",
    "timers", "tls", "url", "util", "worker_threads", "zlib",
}


@dataclass
class FoundImport:
    module: str  # bare package name (scope-aware)
    line: int
    resolution: str = "unknown"  # builtin | installed | unknown


@functools.lru_cache(maxsize=1)
def builtin_modules() -> frozenset[str]:
    node = shutil.which("node")
    if node:
        try:
            out = subprocess.run(
                [node, "-p", "JSON.stringify(require('module').builtinModules)"],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            return frozenset(json.loads(out.stdout))
        except Exception:
            pass
    return frozenset(_COMMON_BUILTINS)


def package_name(specifier: str) -> str:
    """'lodash/fp' -> 'lodash', '@scope/pkg/sub' -> '@scope/pkg'."""
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") else parts[0]


def scan_imports(source: str) -> list[FoundImport]:
    first_seen: dict[str, int] = {}
    for lineno, line in enumerate(source.splitlines(), start=1):
        for pattern in _IMPORT_PATTERNS:
            for match in pattern.finditer(line):
                spec = match.group(1)
                if spec.startswith((".", "/", "file:")):
                    continue  # relative/absolute — not a package
                first_seen.setdefault(package_name(spec.removeprefix("node:")), lineno)
    return [FoundImport(module=m, line=ln) for m, ln in sorted(first_seen.items(), key=lambda kv: kv[1])]


def resolve(name: str, repo_root: Path) -> str:
    if name in builtin_modules():
        return "builtin"
    pkg_json = repo_root / "package.json"
    if pkg_json.exists():
        try:
            manifest = json.loads(pkg_json.read_text(encoding="utf-8"))
            declared = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
            if name in declared:
                return "installed"
        except Exception:
            pass
    if (repo_root / "node_modules" / Path(*name.split("/"))).exists():
        return "installed"
    return "unknown"


def check_file(source: str, repo_root: Path) -> list[FoundImport]:
    found = scan_imports(source)
    for imp in found:
        imp.resolution = resolve(imp.module, repo_root)
    return found
