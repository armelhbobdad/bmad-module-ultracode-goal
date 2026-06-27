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


# ---------------------------------------------------------------------------
# Cross-Session Recall gate — the claude-mem latch path.
#
# The gate is armed by a .mem-state.json latch under impl-artifacts; tests point
# ULTRACODE_IMPL_ARTIFACTS at tmp_path so the latch (and its absence) is fully
# controlled per-test. "Green" means present + schema_ok True + recall on.
# ---------------------------------------------------------------------------

_GREEN_STATE = {
    "latch_version": 1,
    "run_id": "RUN-7",
    "claude_mem": "present",
    "schema_ok": True,
    "recall": "on",
    "tool_form": "plugin",
    "fingerprint": "abc123def4567890",
    "created_at": "2026-06-04T00:00:00Z",
}

# Live plugin-install MCP tool names (captured this session) + the lure that
# tries to smuggle a non-claude-mem op past a sloppy prefix check.
_MEM_PLUGIN_TOOLS = (
    "mcp__plugin_claude-mem_mcp-search__search",
    "mcp__plugin_claude-mem_mcp-search__save_observation",
    "mcp__plugin_claude-mem_mcp-search____IMPORTANT",
)
# Bare-server install forms (dash and underscore server segments).
_MEM_BARE_TOOLS = (
    "mcp__claude-mem__search",
    "mcp__claude_mem__search",
)
# Look-alikes that MUST NOT be treated as claude-mem (memoir != mem; memory !=
# the bare server segment; an unrelated server entirely).
_NON_MEM_TOOLS = (
    "mcp__plugin_claude-memoir_x__y",
    "mcp__claude-memory__z",
    "mcp__Neon__run_sql",
)


def _write_state(impl: Path, state) -> None:
    impl.mkdir(parents=True, exist_ok=True)
    if isinstance(state, (dict, list)):
        (impl / ".mem-state.json").write_text(json.dumps(state))
    else:
        (impl / ".mem-state.json").write_text(state)  # raw bytes-as-str payloads


def _mem_event(tool_name: str, cwd: Path, tool_input: dict | None = None) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input if tool_input is not None else {},
        "cwd": str(cwd),
    }


def _assert_mem_denied(code: int, out: dict | None) -> None:
    assert code == 2
    assert out is not None
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "Cross-Session Recall guard" in decision["permissionDecisionReason"]


# --- risk: an absent latch (no active run) must never touch claude-mem -------

def test_risk_no_latch_allows_claude_mem_and_git_guards_intact(tmp_path: Path) -> None:
    # No .mem-state.json at all: the user is outside any UCG run. A claude-mem
    # MCP call sails through, AND the existing git guard still fires.
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, "main")
    impl = tmp_path / "impl"  # deliberately no state file written

    code, out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", repo),
        repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    assert code == 0
    assert out is None

    # Same absent-latch world: protected-branch git guard unchanged.
    gcode, gout = _run_hook(
        _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert gcode == 2
    assert "Protected-branch" in gout["hookSpecificOutput"]["permissionDecisionReason"]


# --- risk: a green latch is the only state that permits claude-mem -----------

def test_risk_green_latch_allows_claude_mem_call(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, _GREEN_STATE)
    code, out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    assert code == 0
    assert out is None


# --- risk: every not-green latch shape must fail closed (deny) ---------------

def test_risk_recall_off_denies(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "recall": "off"})
    code, out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    _assert_mem_denied(code, out)


def test_risk_claude_mem_absent_denies(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "claude_mem": "absent"})
    code, out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    _assert_mem_denied(code, out)


def test_risk_schema_ok_false_denies(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "schema_ok": False})
    code, out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    _assert_mem_denied(code, out)


def test_risk_zero_byte_state_denies(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, "")  # zero-byte latch -> fail closed
    code, out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    _assert_mem_denied(code, out)


def test_risk_malformed_json_state_denies(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, "{not: valid json,,,")  # unparseable -> fail closed
    code, out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    _assert_mem_denied(code, out)


def test_risk_type_mismatch_state_denies(tmp_path: Path) -> None:
    # schema_ok as the *string* "true" and recall as the *number* 1 must NOT
    # satisfy the strict-bool / strict-str predicates.
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "schema_ok": "true", "recall": 1})
    code, out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    _assert_mem_denied(code, out)


def test_risk_future_latch_version_denies(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "latch_version": 99})
    code, out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    _assert_mem_denied(code, out)


# --- risk: the matcher must hit every live claude-mem form, including the lure

@pytest.mark.parametrize("tool_name", _MEM_PLUGIN_TOOLS + _MEM_BARE_TOOLS)
def test_risk_matcher_hits_live_claude_mem_names(tmp_path: Path, tool_name: str) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "recall": "off"})  # not green -> must deny
    code, out = _run_hook(
        _mem_event(tool_name, tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    _assert_mem_denied(code, out)


# --- risk: the matcher must NOT over-reach onto look-alike tool names ---------

@pytest.mark.parametrize("tool_name", _NON_MEM_TOOLS)
def test_risk_matcher_ignores_lookalike_names(tmp_path: Path, tool_name: str) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "recall": "off"})  # not green
    code, out = _run_hook(
        _mem_event(tool_name, tmp_path, {"query": "x"}),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    # Not a claude-mem tool and not a filesystem reach-around -> allowed through.
    assert code == 0
    assert out is None


# --- risk: empty / missing tool_name is not a match -> allowed ---------------

def test_risk_empty_tool_name_allowed(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "recall": "off"})  # not green
    code, out = _run_hook(_mem_event("", tmp_path), tmp_path,
                          {"ULTRACODE_IMPL_ARTIFACTS": str(impl)})
    assert code == 0
    assert out is None


def test_risk_missing_tool_name_allowed(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "recall": "off"})  # not green
    event = {"hook_event_name": "PreToolUse", "tool_input": {}, "cwd": str(tmp_path)}
    code, out = _run_hook(event, tmp_path, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)})
    assert code == 0
    assert out is None


# --- risk: filesystem reach-arounds into the claude-mem store ----------------

def test_risk_not_green_denies_bash_touching_claude_mem(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "recall": "off"})  # not green
    event = _mem_event(
        "Bash", tmp_path, {"command": "sqlite3 ~/.claude-mem/store.db '.tables'"}
    )
    code, out = _run_hook(event, tmp_path, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)})
    _assert_mem_denied(code, out)


def test_risk_not_green_denies_read_of_claude_mem_path(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "recall": "off"})  # not green
    event = _mem_event(
        "Read", tmp_path, {"file_path": "/home/u/.claude-mem/x.json"}
    )
    code, out = _run_hook(event, tmp_path, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)})
    _assert_mem_denied(code, out)


def test_risk_not_green_denies_grep_under_claude_mem_path(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "recall": "off"})  # not green
    event = _mem_event(
        "Grep", tmp_path, {"pattern": "secret", "path": "/home/u/.claude-mem"}
    )
    code, out = _run_hook(event, tmp_path, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)})
    _assert_mem_denied(code, out)


def test_risk_green_latch_allows_filesystem_claude_mem_access(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, _GREEN_STATE)  # green -> the extension does not fire
    for event in (
        _mem_event("Bash", tmp_path, {"command": "ls ~/.claude-mem"}),
        _mem_event("Read", tmp_path, {"file_path": "/home/u/.claude-mem/x.json"}),
        _mem_event("Grep", tmp_path, {"pattern": "x", "path": "/home/u/.claude-mem"}),
    ):
        code, out = _run_hook(event, tmp_path, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)})
        assert code == 0, event["tool_name"]
        assert out is None, event["tool_name"]


def test_risk_no_latch_allows_filesystem_claude_mem_access(tmp_path: Path) -> None:
    impl = tmp_path / "impl"  # no state file -> not an active run
    for event in (
        _mem_event("Bash", tmp_path, {"command": "ls ~/.claude-mem"}),
        _mem_event("Read", tmp_path, {"file_path": "/home/u/.claude-mem/x.json"}),
        _mem_event("Grep", tmp_path, {"pattern": "x", "path": "/home/u/.claude-mem"}),
    ):
        code, out = _run_hook(event, tmp_path, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)})
        assert code == 0, event["tool_name"]
        assert out is None, event["tool_name"]


# --- risk: deleting the latch mid-run reverts to absent semantics (allow) -----

def test_risk_latch_deleted_between_calls_behaves_as_absent(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, {**_GREEN_STATE, "recall": "off"})  # not green: would deny

    first_code, first_out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    _assert_mem_denied(first_code, first_out)

    # Stage 6 Finalize removes the latch (no caching across calls): now allow.
    (impl / ".mem-state.json").unlink()
    second_code, second_out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    assert second_code == 0
    assert second_out is None

# --- risk: unknowable run state must fail closed for claude-mem calls --------

def test_risk_unresolvable_impl_artifacts_fails_closed_for_claude_mem(tmp_path: Path) -> None:
    # Event carries NO cwd and ULTRACODE_IMPL_ARTIFACTS is unset (empty): the
    # latch location is unknowable — not provably absent. A claude-mem call
    # must DENY (uncertain implies deny), while a non-claude-mem tool passes
    # through untouched. Regression for the review fail-open finding.
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "mcp__plugin_claude-mem_mcp-search__save_observation",
        "tool_input": {},
    }
    code, out = _run_hook(event, tmp_path, {"ULTRACODE_IMPL_ARTIFACTS": ""})
    _assert_mem_denied(code, out)

    benign = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
    }
    bcode, bout = _run_hook(benign, tmp_path, {"ULTRACODE_IMPL_ARTIFACTS": ""})
    assert bcode == 0
    assert bout is None

