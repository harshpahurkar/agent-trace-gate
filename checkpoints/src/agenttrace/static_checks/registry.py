"""Package-registry oracle: does this dependency exist at all?

A 404 from PyPI / the npm registry on a module the local environment can't
resolve is the signature of a hallucinated dependency — the raw material for
slopsquatting attacks (19.7% of packages referenced across 576k LLM-generated
samples were hallucinated; 205,474 unique fake names — arXiv:2406.10279).

Freshly-registered packages are also flagged: a "real" package younger than
90 days matching an import an LLM just suggested is exactly what a
slopsquatted trap looks like.

Results are cached in registry-cache.json at the repo root (committed), so CI
stays deterministic and offline runs still classify the seeded samples.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

CACHE_FILE = "registry-cache.json"
YOUNG_PACKAGE_DAYS = 90


@dataclass
class RegistryResult:
    ecosystem: str  # "pypi" | "npm"
    package: str
    exists: bool | None  # None => registry unreachable and not cached
    age_days: int | None = None
    from_cache: bool = False

    @property
    def young(self) -> bool:
        return self.age_days is not None and self.age_days < YOUNG_PACKAGE_DAYS


def _cache_path(root: Path) -> Path:
    return root / CACHE_FILE


def _load_cache(root: Path) -> dict:
    try:
        return json.loads(_cache_path(root).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(root: Path, cache: dict) -> None:
    try:
        _cache_path(root).write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass  # read-only checkout (CI) — cache just doesn't refresh


def _age_days(earliest_iso: str | None) -> int | None:
    if not earliest_iso:
        return None
    try:
        created = datetime.fromisoformat(earliest_iso.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - created).days)
    except ValueError:
        return None


def _fetch_pypi(client: httpx.Client, package: str) -> tuple[bool, str | None]:
    resp = client.get(f"https://pypi.org/pypi/{package}/json")
    if resp.status_code == 404:
        return False, None
    resp.raise_for_status()
    uploads = [
        f.get("upload_time_iso_8601")
        for files in resp.json().get("releases", {}).values()
        for f in files
        if f.get("upload_time_iso_8601")
    ]
    return True, min(uploads) if uploads else None


def _fetch_npm(client: httpx.Client, package: str) -> tuple[bool, str | None]:
    resp = client.get(f"https://registry.npmjs.org/{package}")
    if resp.status_code == 404:
        return False, None
    resp.raise_for_status()
    return True, resp.json().get("time", {}).get("created")


def check(package: str, ecosystem: str, root: Path) -> RegistryResult:
    """Look a package up in its public registry, cache-first."""
    cache = _load_cache(root)
    key = f"{ecosystem}:{package}"

    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            fetch = _fetch_pypi if ecosystem == "pypi" else _fetch_npm
            exists, earliest = fetch(client, package)
    except httpx.HTTPError:
        if key in cache:
            hit = cache[key]
            return RegistryResult(
                ecosystem, package, hit.get("exists"), hit.get("age_days"), from_cache=True
            )
        return RegistryResult(ecosystem, package, exists=None)

    result = RegistryResult(ecosystem, package, exists, _age_days(earliest))
    cache[key] = {
        "exists": result.exists,
        "age_days": result.age_days,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _save_cache(root, cache)
    return result
