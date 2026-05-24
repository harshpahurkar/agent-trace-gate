"""Static import resolution for Python targets.

Walks the AST for import statements, then resolves each top-level module name
through progressively wider oracles:

    builtin -> stdlib -> importable in this environment -> installed distribution

Anything still unresolved is a candidate hallucination and gets handed to the
registry check (PyPI 404 == the package does not exist anywhere).
This layered approach — AST walk plus environment introspection — is the same
oracle design arXiv:2601.19106 validated at 100% precision / 87.6% recall for
hallucinated-API detection.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from importlib import metadata, util


@dataclass
class FoundImport:
    module: str  # top-level module name
    line: int
    resolution: str = "unknown"  # builtin | stdlib | installed | unknown


def scan_imports(source: str, filename: str = "<sample>") -> list[FoundImport]:
    """Collect unique top-level imported module names with first line seen."""
    tree = ast.parse(source, filename=filename)
    first_seen: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                first_seen.setdefault(alias.name.split(".")[0], node.lineno)
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import inside the sample's own package
            if node.module and node.level == 0:
                first_seen.setdefault(node.module.split(".")[0], node.lineno)
    return [FoundImport(module=m, line=ln) for m, ln in sorted(first_seen.items(), key=lambda kv: kv[1])]


def resolve(name: str) -> str:
    """Classify one top-level module name against the local environment."""
    if name in sys.builtin_module_names:
        return "builtin"
    if name in getattr(sys, "stdlib_module_names", ()):
        return "stdlib"
    try:
        if util.find_spec(name) is not None:
            return "installed"
    except (ImportError, ValueError):
        pass
    try:
        if name in metadata.packages_distributions():
            return "installed"
    except Exception:
        pass
    return "unknown"


def check_file(source: str, filename: str = "<sample>") -> list[FoundImport]:
    found = scan_imports(source, filename)
    for imp in found:
        imp.resolution = resolve(imp.module)
    return found
