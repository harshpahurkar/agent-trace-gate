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


def _load_dotenv(root: Path) -> None:
    """Apply <root>/.env as environment defaults. Values already set in the
    shell win — this only fills gaps, so exporting a var still overrides."""
    env_file = root / ".env"
    if not env_file.exists():
        return
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load(root: Path | None = None) -> Config:
    root = root or find_root()
    _load_dotenv(root)
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


class GitRangeError(RuntimeError):
    """`base`/`head` could not be resolved into a diff.

    Our own tooling failing to work out *what to gate* - never a statement
    about the code under test, so it must not reach the caller as a verdict.
    """


def _shares_history(root: Path, base: str, head: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", base, head],
        cwd=root, capture_output=True, text=True,
    ).returncode == 0


def diff_spec(root: Path, base: str, head: str = "HEAD") -> str:
    """The range `changed_files` will diff, as git spells it.

    Three-dot (PR semantics: what `head` added since the merge base) whenever
    the two revisions share history. When they don't — a rebuilt or grafted
    branch, a force-push over a rewritten history — there is no merge base and
    `A...B` exits 128 instead of saying so, so fall back to the two-dot tree
    comparison, which is well defined for any two commits.
    """
    sep = "..." if _shares_history(root, base, head) else ".."
    return f"{base}{sep}{head}"


def changed_files(root: Path, base: str, head: str = "HEAD") -> list[str]:
    """Repo-relative paths changed vs `base`.

    `head` defaults to the working checkout but the pre-push hook passes the
    exact commit being pushed, which is not always HEAD.
    """
    spec = diff_spec(root, base, head)
    out = subprocess.run(
        ["git", "diff", "--name-only", spec],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        detail = out.stderr.strip().splitlines()
        raise GitRangeError(
            f"could not diff {spec}: "
            + (detail[0] if detail else f"git exited {out.returncode}")
        )
    return [line.strip().replace("\\", "/") for line in out.stdout.splitlines() if line.strip()]
