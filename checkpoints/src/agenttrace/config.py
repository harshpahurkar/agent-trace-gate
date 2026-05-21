"""Load checkpoints.toml — the declaration of what the gate watches.

Each [[targets]] entry names a file, its language, the contract that defines
its expected boundary behaviour, and (for the seeded demo samples) the verdict
the pipeline is *supposed* to reach. `expect` is what lets the CI proof job
assert that every seeded bug is actually caught.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

CONFIG_NAME = "checkpoints.toml"


@dataclass
class Target:
    name: str
    file: str
    language: str  # "python" | "node"
    contract: str | None = None
    expect: str | None = None


@dataclass
class Config:
    root: Path
    targets: list[Target]
    timeout: float = 20.0

    def target_for(self, path: str | Path) -> Target | None:
        wanted = (self.root / path).resolve()
        for t in self.targets:
            if (self.root / t.file).resolve() == wanted:
                return t
        return None


def find_root(start: Path | None = None) -> Path:
    """Walk up from `start` until we find checkpoints.toml (or a .git dir)."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / CONFIG_NAME).exists():
            return candidate
    raise FileNotFoundError(
        f"{CONFIG_NAME} not found in {here} or any parent — run from inside the repo"
    )


def load(root: Path | None = None) -> Config:
    root = root or find_root()
    with open(root / CONFIG_NAME, "rb") as fh:
        raw = tomllib.load(fh)

    settings = raw.get("settings", {})
    timeout = float(os.environ.get("AGENTTRACE_TIMEOUT", settings.get("timeout_seconds", 20)))
    targets = [
        Target(
            name=t["name"],
            file=t["file"],
            language=t["language"],
            contract=t.get("contract"),
            expect=t.get("expect"),
        )
        for t in raw.get("targets", [])
    ]
    return Config(root=root, targets=targets, timeout=timeout)


def changed_files(root: Path, base: str) -> list[str]:
    """Repo-relative paths changed vs `base` (three-dot diff, like a PR)."""
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in out.stdout.splitlines() if line.strip()]
