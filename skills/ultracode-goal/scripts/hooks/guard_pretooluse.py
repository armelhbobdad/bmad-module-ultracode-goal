#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""UltraCode-Goal PreToolUse guard (Claude Code hook).

Enforces invariants that must NOT live in memory (context, not enforcement):
  1. No `git commit`/`git push` while on a protected branch.
  2. No `git commit` until a "tests-ran" marker exists for the current story.
  3. Cross-Session Recall gate: while a UCG run is active (a .mem-state.json
     latch is present), claude-mem stays advisory-only and fails closed — any
     claude-mem MCP call (and any filesystem reach into .claude-mem) is denied
     unless the latch is green (present + schema_ok + recall on). Outside a run
     (no latch) the user's own claude-mem usage is never touched.

Hook contract (reads one JSON object on stdin):
  in : {tool_name, tool_input:{command,...}, cwd, ...}
  out: exit 0 + JSON {hookSpecificOutput:{hookEventName,permissionDecision,
       permissionDecisionReason}} where permissionDecision is "deny" to block.
  Defensive fallback: also exit 2 with the reason on stderr (older clients
  honor exit-code-2-blocks even when they ignore the JSON).

This hook is invoked standalone from settings.local.json. It MUST stay fully
self-contained: no sibling imports (the shared library lib/mem_common.py et al.
are NOT imported).

Config resolution (all optional, env wins so the conductor can inject per run):
  ULTRACODE_PROTECTED_BRANCHES  comma-separated; default "main,master"
  ULTRACODE_IMPL_ARTIFACTS      dir holding run state (story id + markers)
  ULTRACODE_STORY_ID            current story id; else read from
                                <impl_artifacts>/.current-story
  Marker file checked: <impl_artifacts>/.tests-ran-<story_id>
  State latch checked: <impl_artifacts>/.mem-state.json (Cross-Session Recall)
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_PROTECTED = ["main", "master"]


def _read_event() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _allow() -> None:
    """No decision needed: stay silent, let the normal permission flow run."""
    sys.exit(0)


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    # Belt-and-suspenders: clients that ignore JSON still block on exit 2.
    print(reason, file=sys.stderr)
    sys.exit(2)


def _protected_branches() -> list[str]:
    env = os.environ.get("ULTRACODE_PROTECTED_BRANCHES")
    if env:
        return [b.strip() for b in env.split(",") if b.strip()]
    return DEFAULT_PROTECTED


def _current_branch(cwd: str | None) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    branch = out.stdout.strip()
    return branch or None


def _impl_artifacts(cwd: str | None) -> Path | None:
    env = os.environ.get("ULTRACODE_IMPL_ARTIFACTS")
    if env:
        return Path(env)
    if cwd:
        return Path(cwd) / "_bmad-output" / "implementation-artifacts"
    return None


def _current_story(impl: Path | None) -> str | None:
    sid = os.environ.get("ULTRACODE_STORY_ID")
    if sid:
        return sid.strip()
    if impl is not None:
        marker = impl / ".current-story"
        if marker.is_file():
            try:
                return marker.read_text(encoding="utf-8").strip() or None
            except OSError:
                return None
    return None


# git verbs that write history. `git commit` and `git push` are the targets;
# a trailing word boundary keeps `git commit-tree`-style false positives out.
_GIT_WRITE = re.compile(
    r"\bgit\b[^\n;&|]*?\b(?P<verb>commit|push)\b", re.IGNORECASE
)


def _git_writes(command: str) -> set[str]:
    """Return {'commit','push'} subset the command would perform.

    Scans each shell-segment so a chained `git add && git commit` is caught.
    """
    verbs: set[str] = set()
    for segment in re.split(r"&&|\|\||;|\|", command):
        m = _GIT_WRITE.search(segment)
        if m and re.search(r"\bgit\b", segment):
            verbs.add(m.group("verb").lower())
    return verbs


# --- Cross-Session Recall gate (D12) -----------------------------------------
# claude-mem stays advisory-only and fails closed *during a UCG run*. The run is
# signalled by a machine latch written once at Stage 1 Ingest and removed at
# Stage 6 Finalize; its presence — not any env flag — arms this gate.

_MEM_STATE_FILENAME = ".mem-state.json"

# A claude-mem MCP call is one of two segment-exact forms:
#   plugin-install form: mcp__plugin_claude-mem_<server-seg>__<op>
#       the trailing '_' after 'plugin_claude-mem' blocks plugin_claude-memoir_*
#   bare-server form:    mcp__claude-mem__<op>  (also claude_mem; exact segment)
# Case-exact on purpose (real tool names are lowercase); missing/empty -> no match.
_CLAUDE_MEM_TOOL = re.compile(
    r"^mcp__plugin_claude-mem_[A-Za-z0-9-]+__.+$"
    r"|^mcp__claude[-_]mem__.+$"
)


def _mem_state_path(impl: Path | None) -> Path | None:
    return (impl / _MEM_STATE_FILENAME) if impl is not None else None


def _is_claude_mem_tool(tool_name: object) -> bool:
    """True iff tool_name is a claude-mem MCP call (segment-exact dual form)."""
    if not isinstance(tool_name, str) or not tool_name:
        return False
    return _CLAUDE_MEM_TOOL.match(tool_name) is not None


def _mem_latch_green(state_path: Path | None) -> bool:
    """Re-read the latch every call (no memoization) and apply the predicate.

    Green (allow claude-mem) iff the latch parses as a v1 object with
    claude_mem == "present" AND schema_ok is exactly True (strict bool) AND
    recall == "on" (strict str). Anything else — absent-but-required, zero-byte,
    malformed JSON, type mismatch, latch_version > 1 — fails closed (not green).

    NOTE: an *absent* state file is handled by the caller (no active run -> allow
    everything); this function is only consulted once a run is known to be live.
    """
    if state_path is None or not state_path.is_file():
        return False
    try:
        raw = state_path.read_text(encoding="utf-8")
    except OSError:
        return False
    if not raw.strip():
        return False  # zero-byte / whitespace-only
    try:
        state = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(state, dict):
        return False
    if state.get("latch_version") != 1:  # missing or >1 -> fail closed
        return False
    # Strict type + value checks: a stringy "true" or a numeric 1 must NOT pass.
    if state.get("claude_mem") != "present":
        return False
    if state.get("schema_ok") is not True:
        return False
    if state.get("recall") != "on":
        return False
    return True


def _input_paths(tool_input: dict) -> list[str]:
    """File-ish strings a Read/Grep/Glob call would touch (file_path / path)."""
    out: list[str] = []
    for key in ("file_path", "path"):
        val = tool_input.get(key)
        if isinstance(val, str) and val:
            out.append(val)
    return out


def _mem_gate(event: dict, impl: Path | None) -> None:
    """Apply the Cross-Session Recall gate for ALL tool names.

    Runs before any Bash-only git logic. Re-reads the latch per call. If no run
    is active (latch absent), this is a no-op (returns) — the user's own
    claude-mem usage outside a run is never broken.
    """
    state_path = _mem_state_path(impl)
    if state_path is None:
        # Cannot locate impl-artifacts (no cwd in the event, env unset): the
        # run state is UNKNOWABLE, not provably absent. Uncertain implies deny
        # for claude-mem calls; everything else passes through untouched.
        if _is_claude_mem_tool(event.get("tool_name")):
            _deny(
                "Cross-Session Recall guard: cannot locate impl-artifacts "
                "(event carries no cwd and ULTRACODE_IMPL_ARTIFACTS is unset), "
                "so the recall latch is unknowable — failing closed on this "
                "claude-mem call. Set ULTRACODE_IMPL_ARTIFACTS on the hook "
                "command to restore latch resolution."
            )
        return
    # No latch file -> no active UCG run -> never gate claude-mem.
    if not state_path.is_file():
        return

    green = _mem_latch_green(state_path)
    if green:
        return  # run active but recall is on and the contract pin is good.

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    # 1) Direct claude-mem MCP calls.
    if _is_claude_mem_tool(tool_name):
        _deny(
            "Cross-Session Recall guard: claude-mem is advisory-only and fails "
            "closed during a UltraCode-Goal run; the .mem-state.json latch is "
            "not green (absent/off/unverified), so this claude-mem MCP call is "
            "blocked. Recall is voice-never-vote and stays off the gate path."
        )

    # 2) Filesystem reach-arounds into the claude-mem store.
    if tool_name == "Bash":
        command = tool_input.get("command")
        if isinstance(command, str) and ".claude-mem" in command:
            _deny(
                "Cross-Session Recall guard: refusing a Bash command touching "
                "'.claude-mem' while the run's recall latch is not green. "
                "claude-mem must not be read around the advisory gate."
            )
    elif tool_name in ("Read", "Grep", "Glob"):
        for candidate in _input_paths(tool_input):
            if ".claude-mem" in candidate:
                _deny(
                    "Cross-Session Recall guard: refusing a "
                    f"{tool_name} of a '.claude-mem' path while the run's recall "
                    "latch is not green. claude-mem stays advisory-only."
                )
    # Anything else: fall through to the existing git logic.


def main() -> None:
    event = _read_event()

    cwd = event.get("cwd")
    impl = _impl_artifacts(cwd)

    # Cross-Session Recall gate runs for EVERY tool name, before the Bash-only
    # git logic below. It either denies (and exits) or returns to let the rest
    # of the guard proceed unchanged.
    _mem_gate(event, impl)

    if event.get("tool_name") != "Bash":
        _allow()

    command = (event.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str):
        _allow()

    verbs = _git_writes(command)
    if not verbs:
        _allow()

    protected = _protected_branches()
    branch = _current_branch(cwd)

    if branch is not None and branch in protected:
        _deny(
            f"Protected-branch guard: refusing `git {'/'.join(sorted(verbs))}` "
            f"on '{branch}'. UltraCode-Goal commits one green story per commit "
            f"on an epic branch ('{os.environ.get('ULTRACODE_EPIC_BRANCH_PREFIX', 'ultracode/epic-')}<id>'), "
            f"never on {protected}. Switch to the epic branch first."
        )

    if "commit" in verbs:
        impl = _impl_artifacts(cwd)
        story = _current_story(impl)
        marker = (impl / f".tests-ran-{story}") if (impl and story) else None
        if marker is None or not marker.is_file():
            target = str(marker) if marker else "<impl-artifacts>/.tests-ran-<story>"
            _deny(
                "Tests-ran guard: refusing `git commit` — no tests-ran marker "
                f"for the current story ({story or 'unknown'}). Run the story's "
                f"test/lint/build to green and write {target} before committing. "
                "Commit only at a verified-green story boundary."
            )

    _allow()


if __name__ == "__main__":
    main()
