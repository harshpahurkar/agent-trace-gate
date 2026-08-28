"""Resolving the range that `agenttrace check --base` gates.

These are the paths where the gate can fail *before* any checkpoint runs - a
bad ref, or two revisions with no common ancestor. Neither is a claim about the
code under test, so neither may surface as a verdict or as a traceback.
"""

import subprocess
from pathlib import Path

import pytest

from agenttrace import cli, config


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, check=True,
                         capture_output=True, text=True)
    return out.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.name", "test")
    _git(r, "config", "user.email", "test@example.com")
    return r


def _commit(repo: Path, name: str) -> str:
    # distinct bodies, so a delete + add is not collapsed into a rename
    (repo / name).write_text("value = %r" % name + chr(10))
    _git(repo, "add", name)
    _git(repo, "commit", "-qm", "add " + name)
    return _git(repo, "rev-parse", "HEAD")


def test_unrelated_histories_fall_back_to_a_plain_tree_diff(repo):
    """A rebuilt or grafted branch shares no merge base with the remote tip.
    `git diff A...B` exits 128 there; the gate must still report what changed."""
    base = _commit(repo, "a.py")
    _git(repo, "checkout", "-q", "--orphan", "rebuilt")
    _git(repo, "rm", "-rq", "--cached", ".")
    head = _commit(repo, "b.py")

    assert config.changed_files(repo, base, head) == ["a.py", "b.py"]


def test_unknown_revision_reports_cleanly_instead_of_a_traceback(repo):
    """A base ref that does not resolve is our problem, not the sample's, so it
    arrives as a typed error the CLI can render as one line."""
    _commit(repo, "a.py")

    with pytest.raises(config.GitRangeError) as exc:
        config.changed_files(repo, "no-such-ref", "HEAD")

    assert "no-such-ref" in str(exc.value)


def test_check_exits_two_when_the_range_cannot_be_resolved(repo, monkeypatch):
    """Exit 1 means a checkpoint verdict failed. A gate that never ran must not
    borrow that meaning - the pre-push hook keys its message off the difference."""
    _commit(repo, "a.py")
    (repo / "checkpoints.toml").write_text("timeout = 5" + chr(10))
    monkeypatch.chdir(repo)

    assert cli.main(["check", "--base", "no-such-ref", "--otel", "off"]) == 2
