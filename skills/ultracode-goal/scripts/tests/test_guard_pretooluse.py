#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Exercise the PreToolUse guard's deny/allow paths via the real stdin/stdout
hook contract (run the hook as a subprocess, feed JSON on stdin)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_pretooluse.py"

# git env vars that, if inherited from the host (e.g. a git hook context), would
# point every `git` invocation below at the live repo instead of the temp repos
# these tests create — making the fixtures depend on the runner's git state.
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
    """Scrub inherited GIT_* env so git runs against the temp repos, not the host."""
    for var in _GIT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(repo: Path, branch: str) -> None:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "checkout", "-q", "-b", branch)
    (repo / "f.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")


def _run_hook(event: dict, cwd: Path, env_extra: dict | None = None) -> tuple[int, dict | None]:
    import os

    env = {**os.environ, **(env_extra or {})}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )
    out = None
    if proc.stdout.strip():
        out = json.loads(proc.stdout)
    return proc.returncode, out


def _commit_event(cwd: Path) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git add -A && git commit -m wip"},
        "cwd": str(cwd),
    }


def test_protected_branch_denies_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, "main")

    code, out = _run_hook(_commit_event(repo), repo)

    assert code == 2  # defensive exit-code-2-blocks fallback
    assert out is not None
    decision = out["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert "Protected-branch" in decision["permissionDecisionReason"]


def test_protected_branch_denies_push(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, "master")
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin master"},
        "cwd": str(repo),
    }

    code, out = _run_hook(event, repo)

    assert code == 2
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_custom_protected_branches_env(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, "release")  # not in the default protected set

    code, out = _run_hook(
        _commit_event(repo), repo, {"ULTRACODE_PROTECTED_BRANCHES": "release,trunk"}
    )

    assert code == 2
    assert "Protected-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_epic_branch_commit_denied_without_tests_marker(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, "ultracode/epic-42")
    impl = repo / "impl"
    impl.mkdir()
    (impl / ".current-story").write_text("STORY-1")

    code, out = _run_hook(
        _commit_event(repo),
        repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )

    assert code == 2  # off a protected branch, but no tests-ran marker
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Tests-ran guard" in reason
    assert "STORY-1" in reason


def test_epic_branch_commit_allowed_with_tests_marker(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, "ultracode/epic-42")
    impl = repo / "impl"
    impl.mkdir()
    (impl / ".current-story").write_text("STORY-1")
    (impl / ".tests-ran-STORY-1").write_text("ok")

    code, out = _run_hook(
        _commit_event(repo),
        repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )

    assert code == 0  # green story boundary: allow, no decision JSON
    assert out is None


def test_non_git_bash_is_allowed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, "main")
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "cwd": str(repo),
    }

    code, out = _run_hook(event, repo)

    assert code == 0
    assert out is None


def test_non_bash_tool_is_allowed(tmp_path: Path) -> None:
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "x", "old_string": "a", "new_string": "b"},
        "cwd": str(tmp_path),
    }
    code, out = _run_hook(event, tmp_path)
    assert code == 0
    assert out is None
