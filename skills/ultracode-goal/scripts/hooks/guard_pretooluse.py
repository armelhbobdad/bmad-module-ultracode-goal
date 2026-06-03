#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""UltraCode-Goal PreToolUse guard (Claude Code hook).

Enforces two invariants that must NOT live in memory (context, not enforcement):
  1. No `git commit`/`git push` while on a protected branch.
  2. No `git commit` until a "tests-ran" marker exists for the current story.

Hook contract (reads one JSON object on stdin):
  in : {tool_name, tool_input:{command,...}, cwd, ...}
  out: exit 0 + JSON {hookSpecificOutput:{hookEventName,permissionDecision,
       permissionDecisionReason}} where permissionDecision is "deny" to block.
  Defensive fallback: also exit 2 with the reason on stderr (older clients
  honor exit-code-2-blocks even when they ignore the JSON).

Config resolution (all optional, env wins so the conductor can inject per run):
  ULTRACODE_PROTECTED_BRANCHES  comma-separated; default "main,master"
  ULTRACODE_IMPL_ARTIFACTS      dir holding run state (story id + markers)
  ULTRACODE_STORY_ID            current story id; else read from
                                <impl_artifacts>/.current-story
  Marker file checked: <impl_artifacts>/.tests-ran-<story_id>
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


def main() -> None:
    event = _read_event()
    if event.get("tool_name") != "Bash":
        _allow()

    command = (event.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str):
        _allow()

    verbs = _git_writes(command)
    if not verbs:
        _allow()

    cwd = event.get("cwd")
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
