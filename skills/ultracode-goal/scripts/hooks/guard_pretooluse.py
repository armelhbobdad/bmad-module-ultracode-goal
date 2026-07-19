#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""UltraCode-Goal PreToolUse guard (Claude Code hook).

Enforces invariants that must NOT live in memory (context, not enforcement):
  1. No `git commit`/`git push` while on a protected branch.
  2. No `git commit` until a "tests-ran" marker exists for the current story.
  3. No `git commit` while the staged index is empty (a commit that captures no
     work), or while the staged-index probe cannot answer (fail closed).
  4. Un-skip proof: in production (an atdd-checklist for the current story is on
     disk), no `git commit` while the STAGED CONTENT of any acceptance-test file
     that checklist enumerates still contains `test.skip(`. This reads the blob
     being committed, not a diff, so it also catches a story's first commit,
     where there is no prior blob to compare against.
  5. Cross-Session Recall gate: while a UCG run is active (a .mem-state.json
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
  ULTRACODE_TEST_ARTIFACTS      TEA test-artifacts root; arms the un-skip proof.
                                No default is derived here on purpose (see
                                _test_artifacts): unset means the check is out
                                of scope, never a deny.
  Marker file checked: <impl_artifacts>/.tests-ran-<story_id>
  State latch checked: <impl_artifacts>/.mem-state.json (Cross-Session Recall)
  Checklist read: <test_artifacts>/atdd-checklist-<story_id>.md, keyed by the
                  SAME story id the tests-ran marker uses (the id resolved by
                  _current_story). A story_key/story_id drift here would make
                  the un-skip proof silently inert, the worst failure mode a
                  deny guard has.
  Skip token matched: the literal `test.skip(`. That token is JS/Vitest-specific
                  (the Playwright/Vitest form TEA's ATDD generates, which is
                  web/JS-only today); a pytest or Go acceptance suite marks
                  skips differently and this check would not see them.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

DEFAULT_PROTECTED = ["main", "master"]


def _read_event() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _allow() -> NoReturn:
    """No decision needed: stay silent, let the normal permission flow run."""
    sys.exit(0)


def _deny(reason: str) -> NoReturn:
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


def _note(message: str) -> None:
    """Say something on stderr and RETURN (no decision, no exit).

    stdout is the decision channel: anything printed there is parsed as the
    hook's verdict, so a path that reaches no decision must stay off it.
    """
    print(message, file=sys.stderr)


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


def _staged_index_nonempty(cwd: str | None) -> bool:
    """True only when something is provably staged for the next commit.

    `git diff --cached --quiet` implies `--exit-code`: 0 means nothing is
    staged, 1 means something is, and any other code (128 outside a repo, for
    one) means the probe could not answer. Unlike _current_branch above, which
    swallows the same failures and fails OPEN by returning None, this one fails
    CLOSED: an unanswerable probe reports "nothing staged" so the caller blocks
    the commit rather than waving through a commit it could not inspect.
    """
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False  # git missing, timeout, ...: cannot answer -> fail closed
    if out.returncode == 0:
        return False  # nothing staged
    if out.returncode == 1:
        return True  # something staged
    return False  # any other exit code is a probe failure -> fail closed


def _impl_artifacts(cwd: str | None) -> Path | None:
    env = os.environ.get("ULTRACODE_IMPL_ARTIFACTS")
    if env:
        return Path(env)
    if cwd:
        return Path(cwd) / "_bmad-output" / "implementation-artifacts"
    return None


def _test_artifacts() -> Path | None:
    """TEA test-artifacts root, from env ONLY.

    Mirrors _impl_artifacts above but deliberately WITHOUT its cwd-derived
    fallback. Hooks armed by a run that predates the un-skip proof inject no
    ULTRACODE_TEST_ARTIFACTS; synthesizing a path here would pull every such
    session into scope and brick its commits on a checklist it never wrote.
    Unset means out of scope (an advisory note, never a deny); fail-closed
    behavior applies only *within* scope, once the var is set.
    """
    env = os.environ.get("ULTRACODE_TEST_ARTIFACTS")
    if env:
        return Path(env)
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


# --- Un-skip proof ----------------------------------------------------------
# In production the story's atdd-checklist is the ground truth for which files
# carry its acceptance tests. This clause reads the STAGED post-image of each of
# them and refuses a commit that would capture a still-skipped acceptance test.
# It asserts absence in the blob being committed, so it holds on a story's first
# commit as well as on later ones; it is not a diff of "was the marker removed".

_SKIP_TOKEN = "test.skip("

# Path-shaped tokens naming a JS/TS acceptance-test file. Deliberately loose on
# the leading segment ({project-root}/…, an absolute path, a bare relative one)
# and strict on the extension, so prose around the paths is not mistaken for one.
_TEST_FILE = re.compile(
    r"""[^\s`'"()\[\],]+\.(?:spec|test)\.(?:[cm]?[jt]sx?)\b"""
)


def _checklist_test_files(text: str) -> list[str]:
    """Every acceptance-test path the checklist names, in order, deduplicated."""
    found: list[str] = []
    for match in _TEST_FILE.finditer(text):
        token = match.group(0)
        if token not in found:
            found.append(token)
    return found


def _repo_relative(raw: str, cwd: str | None) -> str:
    """Normalize a checklist entry to the repo-relative form `git show :` needs.

    Checklist entries may be `{project-root}`-prefixed or absolute; `git show :`
    accepts neither. Anything that still cannot be made repo-relative is passed
    through unchanged so the read fails loudly rather than being skipped.
    """
    text = raw.replace("\\", "/")
    if "{project-root}" in text:
        return text.split("{project-root}", 1)[1].lstrip("/")
    if text.startswith("./"):
        text = text[2:]
    if text.startswith("/") and cwd:
        try:
            return str(Path(text).relative_to(Path(cwd)))
        except ValueError:
            return text
    return text


def _staged_blob(path: str, cwd: str | None) -> tuple[bool, str]:
    """Return (readable, staged content) for one path via `git show :<path>`.

    `:<path>` addresses the index, i.e. exactly the bytes this commit would
    write. readable is False when the probe could not answer at all (git
    missing, timeout, path not in the index): the caller fails closed on it.
    """
    try:
        out = subprocess.run(
            ["git", "show", f":{path}"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        return False, ""
    if out.returncode != 0:
        return False, ""
    return True, out.stdout


def _unskip_gate(cwd: str | None, story: str | None) -> None:
    """Deny a commit whose staged acceptance tests still carry the skip marker.

    Scope, in order:
      - test-artifacts root unresolvable (env unset) -> out of scope, note only.
      - no story id -> nothing to look up.
      - no checklist for this story -> inert. That is the `--light` profile,
        where acceptance tests are not generated at all.
      - checklist present but unreadable -> deny (in scope, cannot verify).
      - checklist naming no acceptance-test file -> inert. Doc-only and refactor
        stories are legitimate and must not be blocked.
    Every enumerated file is read from the index whether or not this commit
    touched it: the checklist, not the diff, says what the story must deliver.
    """
    tests_root = _test_artifacts()
    if tests_root is None:
        _note(
            "Un-skip proof: ULTRACODE_TEST_ARTIFACTS is unset, so the staged "
            "acceptance-test check is out of scope for this commit and made no "
            "decision. Inject it on the guard's hook command (preflight step 5) "
            "to arm the check."
        )
        return
    if not story:
        return

    checklist = tests_root / f"atdd-checklist-{story}.md"
    if not checklist.is_file():
        return  # no acceptance tests for this story: nothing to prove
    try:
        text = checklist.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        _deny(
            "Un-skip proof: refusing `git commit` — the acceptance-test "
            f"checklist {checklist} exists but could not be read, so the staged "
            "acceptance tests cannot be verified un-skipped. Failing closed. "
            "Repair or regenerate the checklist, then commit."
        )

    files = [_repo_relative(entry, cwd) for entry in _checklist_test_files(text)]
    if not files:
        return  # checklist names no acceptance-test file (doc-only story)

    still_skipped: list[str] = []
    for rel in files:
        readable, blob = _staged_blob(rel, cwd)
        if not readable:
            _deny(
                "Un-skip proof: refusing `git commit` — `git show :"
                f"{rel}` failed, so the staged content of an acceptance-test "
                f"file named by {checklist.name} could not be read. Failing "
                "closed. Stage that file (`git add <path>`) in a prior, "
                "SEPARATE tool call, or fix the path the checklist names."
            )
        if _SKIP_TOKEN in blob:
            still_skipped.append(rel)
    if still_skipped:
        _deny(
            "Un-skip proof: refusing `git commit` — the staged content of "
            f"{', '.join(still_skipped)} still contains `{_SKIP_TOKEN}`, so this "
            "commit would capture a story whose acceptance tests are skipped "
            "rather than green. Un-skip every acceptance test the checklist "
            f"({checklist.name}) enumerates, drive them to green, restage those "
            "paths in a prior, SEPARATE tool call, then commit."
        )


# --- Cross-Session Recall gate ----------------------------------------------
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
        if not _staged_index_nonempty(cwd):
            _deny(
                "Empty-index guard: refusing `git commit` — the staged index is "
                "empty (or could not be read), so this commit would capture no "
                "work. Stage this story's paths in a prior, SEPARATE tool call "
                "(`git add <this story's paths>`), then commit as a second, "
                "distinct tool call. `git commit -a` and commit-time pathspecs "
                "are unsupported inside a story loop: the guard evaluates the "
                "command string before it runs, so anything they would stage "
                "does not exist yet at that point."
            )
        _unskip_gate(cwd, story)

    _allow()


if __name__ == "__main__":
    main()
