#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for lib/mem_common.py (Cross-Session Recall shared library).

mem_common is the only pure-library module in scripts/ — it has no CLI, so
(unlike the other script tests, which drive subprocesses) it is imported
directly. We insert the scripts dir on sys.path and import the namespace
subpackage exactly as the CLIs do (``from lib import mem_common``).

Covers the load-bearing pure functions: the taxonomy mapping, git-remote
normalization (ssh/https/scp/port collapse), high-precision secret redaction,
untrusted-text neutralization (bidi/backtick strip + clamp), the repo
fingerprint across its basis branches, and the state-file latch roundtrip.

Run: uv run --with pytest pytest test_mem_common.py -v
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from lib import mem_common as mc  # noqa: E402  (after sys.path mutation)

# Same GIT_* scrub as test_mem_recall: keep repo_fingerprint() pinned to the
# temp repos these tests build, never the host checkout.
_GIT_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
)


@pytest.fixture(autouse=True)
def _hermetic_git_env(monkeypatch):
    for var in _GIT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(repo: Path, remote: str | None = "https://github.com/acme/widget.git") -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    if remote:
        _git(repo, "remote", "add", "origin", remote)


# ---------------------------------------------------------------------------
# canonical_class — unknown collapses to "other"
# ---------------------------------------------------------------------------


def test_canonical_class_keeps_known_collapses_unknown_and_none():
    assert mc.canonical_class("test-flake") == "test-flake"
    assert mc.canonical_class("security") == "security"
    assert mc.canonical_class("not-a-real-class") == "other"
    assert mc.canonical_class(None) == "other"
    # Surrounding whitespace is stripped before the membership check.
    assert mc.canonical_class("  build-error  ") == "build-error"
    # The taxonomy is the frozen 12-class contract callers rely on.
    assert len(mc.TAXONOMY) == 12
    assert "other" in mc.TAXONOMY


# ---------------------------------------------------------------------------
# normalize_remote — ssh / https / scp forms collapse to one key
# ---------------------------------------------------------------------------


def test_normalize_remote_collapses_ssh_and_https_forms():
    https = mc.normalize_remote("https://github.com/Acme/Widget.git/")
    ssh = mc.normalize_remote("git@github.com:Acme/Widget.git")
    scp_scheme = mc.normalize_remote("ssh://git@github.com/Acme/Widget.git")
    assert https == ssh == scp_scheme == "github.com/acme/widget"


def test_normalize_remote_preserves_host_port():
    # A numeric "host:port" must NOT be rewritten as "host/port".
    assert mc.normalize_remote("ssh://git@example.com:22/org/repo.git") == "example.com:22/org/repo"
    assert mc.normalize_remote("git@example.com:2222/org/repo.git") == "example.com:2222/org/repo"


# ---------------------------------------------------------------------------
# redact — high-precision secret scrubbing
# ---------------------------------------------------------------------------


def test_redact_scrubs_known_credential_shapes():
    assert mc.redact("id AKIAABCDEFGHIJKLMNOP done") == "id [redacted] done"
    assert mc.redact("gh token gh" + "p_" + "a" * 30) == "gh token [redacted]"
    assert mc.redact("use sk-" + "B" * 24 + " now") == "use [redacted] now"
    assert "[redacted]" in mc.redact("Authorization: Bearer abcdefghijklmnop")
    # key=value assignment redacts the value but stops at whitespace.
    assert mc.redact("token=supersecretvalue here") == "[redacted] here"


def test_redact_leaves_ordinary_prose_and_handles_none():
    text = "the build failed because the test was flaky on retry"
    assert mc.redact(text) == text
    assert mc.redact(None) == ""
    assert mc.redact("") == ""


# ---------------------------------------------------------------------------
# neutralize — defang untrusted free text
# ---------------------------------------------------------------------------


def test_neutralize_strips_fences_collapses_ws_and_clamps():
    assert mc.neutralize("a```b   c\n\nd") == "ab c d"
    # Bidi controls (Trojan Source) are dropped entirely.
    assert mc.neutralize("safe‮txet") == "safetxet"
    # Clamp to 80 codepoints on a boundary; idempotent.
    out = mc.neutralize("x" * 200)
    assert len(out) == 80
    assert mc.neutralize(out) == out
    assert mc.neutralize(None) == ""


# ---------------------------------------------------------------------------
# repo_fingerprint — stable per-repo identity across basis branches
# ---------------------------------------------------------------------------


def test_repo_fingerprint_none_outside_git(tmp_path):
    fp = mc.repo_fingerprint(tmp_path)
    assert fp == {"basis": None, "value": None}


@pytest.mark.skipif(not __import__("shutil").which("git"), reason="git not on PATH")
def test_repo_fingerprint_remote_root_is_stable_and_deterministic(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo, remote="git@github.com:acme/widget.git")
    fp = mc.repo_fingerprint(repo)
    assert fp["basis"] == "remote+root"
    assert isinstance(fp["value"], str) and len(fp["value"]) == 16
    # Same repo -> same fingerprint (deterministic, no clock/random input).
    assert mc.repo_fingerprint(repo) == fp


@pytest.mark.skipif(not __import__("shutil").which("git"), reason="git not on PATH")
def test_repo_fingerprint_local_basis_when_no_remote(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo, remote=None)
    fp = mc.repo_fingerprint(repo)
    assert fp["basis"] == "local"
    assert fp["value"].startswith("local:")


# ---------------------------------------------------------------------------
# state-file latch — write/read/remove roundtrip
# ---------------------------------------------------------------------------


def test_state_path_is_under_impl_artifacts(tmp_path):
    assert mc.state_path(tmp_path) == tmp_path / ".mem-state.json"


def test_state_roundtrip_write_read_remove(tmp_path):
    state = {
        "latch_version": mc.LATCH_VERSION,
        "run_id": "r1",
        "claude_mem": "present",
        "recall": "off",
    }
    path = mc.write_state(tmp_path, state)
    assert path.exists()
    assert mc.read_state(tmp_path) == state
    # First remove succeeds, second is a no-op (idempotent close-out).
    assert mc.remove_state(tmp_path) is True
    assert mc.remove_state(tmp_path) is False


def test_read_state_returns_none_on_missing_and_corrupt(tmp_path):
    # Missing file.
    assert mc.read_state(tmp_path) is None
    # Corrupt JSON -> None, never raises.
    mc.state_path(tmp_path).write_text("{not json", encoding="utf-8")
    assert mc.read_state(tmp_path) is None
    # Valid JSON but not an object -> None.
    mc.state_path(tmp_path).write_text("[1, 2, 3]", encoding="utf-8")
    assert mc.read_state(tmp_path) is None
