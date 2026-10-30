#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""The resume manifest: `preflight_check.py --assert-armed`.

One deterministic read replaces the tool-action-per-fact environment sweep the
resume rule costs on every `--max-stories` spawn. These tests pin the six
properties that make it trustworthy rather than merely convenient:

1. FAIL-CLOSED ARMING. Exit 0 requires the epic branch, both hooks with the
   all-tools PreToolUse matcher, all five injected env vars, and the two UCG
   story skills the run delegates to. A missing or unreadable settings file, a
   `Bash`-only matcher (the observed inert-control state), an uninjected var,
   or a story skill removed between spawns each fail the exit,
   with a reason naming it.
2. LEGITIMATE ARMINGS PASS. preflight step 5 permits the env vars either in the
   hook command strings or in the process env the hooks inherit; fail-closing
   on the inherited form would teach operators to skip the check.
3. THE LATCH IS REPORTED, NEVER CERTIFIED. `certifies` is a literal null and
   the latch never moves the exit code: exit 0 must not become an
   inherited-latch claim by proxy, because re-latching from this run's own
   measurement is a model-owned Stage 1 step on every resume. A present latch
   also reports its `latch_version` and the derived `store_ok` colour, red for
   a v1 latch and anything short of a green latch v2, and neither moves the
   exit either.
4. THE STORY ROUTE IS ARTIFACT-DERIVED AND CONSERVATIVE. `gate-owed` (skip to
   step 5) fires only when the full discriminator holds AND --trace-output
   supplied the artifact evidence; absence of evidence routes to the ordinary
   loop, never past it.
5. AN OPEN ESCALATION OUTRANKS EVERY ROUTE, AND CLOSED MEANS WHAT /ucg-resolve
   MEANS. A story whose `escalation-<story>.json` is on disk routes
   `decision-pending` ahead of the other three, unless /ucg-resolve closed the
   id it keys that sidecar by (red_ids.py's, from its `source` or from the
   sidecar's own path) or the sidecar is a handoff. A sidecar that cannot be
   read, or whose fields no id can be minted from, fails closed, and none of
   it moves the exit.
6. A CLOSED OPERATOR-EVIDENCE-OWED STORY IS RE-GATED, NOT RE-DRIVEN. The
   `.regate-<story>` marker /ucg-resolve writes on that close routes a
   baselined story `gate-owed` while its `sha=` resolves to HEAD, and is
   `stale` otherwise (a later commit, or no commit id), which routes as if it
   were absent.

Run: uv run --with pytest pytest scripts/tests/test_preflight_assert_armed.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS / "preflight_check.py"

_ENV_VARS = (
    "ULTRACODE_PROTECTED_BRANCHES",
    "ULTRACODE_IMPL_ARTIFACTS",
    "ULTRACODE_MAX_TURNS",
    "ULTRACODE_EPIC_BRANCH_PREFIX",
    "ULTRACODE_TEST_ARTIFACTS",
)


# Hermeticity WITHOUT stripping the environment: a hardcoded POSIX PATH breaks
# windows-latest CI (git/python live elsewhere and Windows needs SystemRoot),
# so the inherited env is kept and git is isolated from user/system config the
# way test_drive_epic.py does it.
_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_GIT_ENV},
    )


def _repo(tmp_path: Path, branch: str = "ultracode/epic-7") -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "seed.txt")
    _git(root, "commit", "-q", "-m", "seed")
    _git(root, "checkout", "-q", "-b", branch)
    # The story skills the run delegates to, where UCG's installer copies
    # them for Claude Code.
    for skill_id in ("ucg-create-story", "ucg-dev-story"):
        skill_dir = root / ".claude" / "skills" / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: {skill_id}\n---\n", encoding="utf-8")
    return root


def _head(root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _arm(
    root: Path,
    *,
    matcher: str | None = "*",
    guard: bool = True,
    budget: bool = True,
    env_in_command: bool = True,
    on_failure: str | None = "block",
    stop_on_failure: str | None = None,
    guard_command: str | None = None,
    budget_command: str | None = None,
) -> None:
    """Write a settings.local.json in the real nested shape preflight documents.

    `on_failure` is the guard item's `onFailure` (None leaves the key out, as
    every arming UCG 3.x or earlier made); `stop_on_failure` puts one on the
    Stop budget item, where preflight writes none. `guard_command` and
    `budget_command` replace an item's whole command string."""
    env_prefix = (
        " ".join(f"{v}=x" for v in _ENV_VARS) + " " if env_in_command else ""
    )
    guard_item: dict = {
        "type": "command",
        "command": guard_command or f"{env_prefix}uv run scripts/hooks/guard_pretooluse.py",
    }
    if on_failure is not None:
        guard_item["onFailure"] = on_failure
    pre_group: dict = {"hooks": [guard_item]}
    if matcher is not None:
        pre_group["matcher"] = matcher
    stop_item: dict = {"type": "command", "command": budget_command or "uv run scripts/hooks/budget_stop.py"}
    if stop_on_failure is not None:
        stop_item["onFailure"] = stop_on_failure
    settings = {
        "hooks": {
            "PreToolUse": [pre_group] if guard else [],
            "Stop": [{"hooks": [stop_item]}] if budget else [],
        }
    }
    claude_dir = root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "settings.local.json").write_text(
        json.dumps(settings), encoding="utf-8"
    )


def _run(
    root: Path,
    *extra: str,
    impl: Path | None = None,
    env: dict | None = None,
    timeout: float | None = None,
) -> tuple[int, dict]:
    impl_dir = impl if impl is not None else root / "impl"
    impl_dir.mkdir(exist_ok=True)
    # Start from the real environment (Windows needs SystemRoot et al.), then
    # strip the five hook vars so a dev machine's own injection cannot leak a
    # green "process" source into a case that never set them.
    base_env = {
        k: v
        for k, v in os.environ.items()
        if k not in _ENV_VARS and k != "CLAUDE_CONFIG_DIR"
    }
    # An empty home, so a skill the host keeps under ~/.claude/skills (or a
    # relocated CLAUDE_CONFIG_DIR) cannot satisfy a case (HOME on POSIX,
    # USERPROFILE on Windows).
    home = root.parent / "home"
    home.mkdir(exist_ok=True)
    base_env.update({"HOME": str(home), "USERPROFILE": str(home)})
    if env:
        base_env.update(env)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--assert-armed",
            "--project-root",
            str(root),
            "--impl-artifacts",
            str(impl_dir),
            *extra,
        ],
        capture_output=True,
        text=True,
        env=base_env,
        timeout=timeout,
    )
    assert proc.stdout, proc.stderr
    return proc.returncode, json.loads(proc.stdout)


# --- arming: fail-closed exit ------------------------------------------------


def test_fully_armed_environment_exits_zero(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    code, out = _run(root)
    assert out["reasons"] == []
    assert out["armed"] is True
    assert code == 0
    assert out["checks"]["hooks"]["matcher_all_tools"] is True


def test_the_manifest_reports_whether_git_tracks_the_artifact_tree(tmp_path: Path) -> None:
    # A resumed session has no step-1 report, and execute.md's ignored-tree rule
    # keys on this fact; it never moves the exit code.
    root = _repo(tmp_path)
    _arm(root)
    code, out = _run(root)
    assert out["checks"]["impl_artifacts_tracked"] is True
    assert code == 0
    (root / ".gitignore").write_text("impl/\n", encoding="utf-8")
    code, out = _run(root)
    assert out["checks"]["impl_artifacts_tracked"] is False
    assert out["reasons"] == [] and code == 0, out


def test_an_omitted_matcher_key_counts_as_all_tools(tmp_path: Path) -> None:
    """preflight step 5: omitting the matcher selects every tool, like `*`."""
    root = _repo(tmp_path)
    _arm(root, matcher=None)
    code, out = _run(root)
    assert code == 0 and out["armed"] is True


def test_bash_only_matcher_fails_with_the_inert_control_reason(tmp_path: Path) -> None:
    """The observed real-world state: hooks present, recall invariant inert."""
    root = _repo(tmp_path)
    _arm(root, matcher="Bash")
    code, out = _run(root)
    assert code == 1 and out["armed"] is False
    assert out["checks"]["hooks"]["guard_present"] is True
    assert out["checks"]["hooks"]["matcher_all_tools"] is False
    assert any("all-tools" in r for r in out["reasons"])


# --- arming: the guard's onFailure -------------------------------------------
# Claude Code 2.1.295+ refuses the tool call when a hook item with
# `"onFailure": "block"` cannot start, exits with a code other than 0 or 2, or
# times out. Without the key (every arming UCG 3.x or earlier made) each of
# those lets the call run unchecked, and a value Claude Code does not accept
# drops the whole item, so the guard does not run at all.

_ON_FAILURE_REASON = 'PreToolUse guard is not armed with "onFailure": "block" on every item'


def _on_failure_reason(out: dict) -> str:
    matches = [r for r in out["reasons"] if r.startswith(_ON_FAILURE_REASON)]
    assert len(matches) == 1, out["reasons"]
    return matches[0]


def test_the_armed_guard_reports_its_on_failure_value(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    code, out = _run(root)
    assert code == 0 and out["reasons"] == []
    hooks = out["checks"]["hooks"]
    assert hooks["guard_on_failure_block"] is True
    assert hooks["guard_on_failure"] == ["block"]


@pytest.mark.parametrize(
    "value,shown",
    [
        pytest.param(None, "missing", id="missing"),
        pytest.param("Block", '"Block"', id="wrong-case"),
        pytest.param("continue", '"continue"', id="continue"),
        pytest.param("BLOCK", '"BLOCK"', id="upper-case"),
        pytest.param(True, "true", id="not-a-string"),
    ],
)
def test_a_guard_item_without_on_failure_block_is_not_armed(tmp_path: Path, value, shown: str) -> None:
    """A 3.x arming (no key), a value Claude Code drops the item for, and the
    one it accepts but that lets a crash through each fail closed, with a
    reason that names what it found and the re-merge that fixes it."""
    root = _repo(tmp_path)
    _arm(root, on_failure=value)
    code, out = _run(root)
    assert code == 1 and out["armed"] is False
    hooks = out["checks"]["hooks"]
    assert hooks["guard_present"] is True and hooks["matcher_all_tools"] is True
    assert hooks["guard_on_failure_block"] is False
    assert hooks["guard_on_failure"] == [value]
    reason = _on_failure_reason(out)
    assert f"(found: {shown})" in reason
    assert "Re-merge the hooks as preflight.md step 5's Hooks bullet says" in reason
    assert "replace, never append; on a resume purge nothing" in reason
    # The only reason: nothing else about this arming is wrong.
    assert len(out["reasons"]) == 1, out["reasons"]


def test_on_failure_on_the_stop_hook_alone_does_not_arm_the_guard(tmp_path: Path) -> None:
    """The key sits on the guard's own item: Claude Code ignores it on Stop,
    and a copy there says nothing about the PreToolUse guard."""
    root = _repo(tmp_path)
    _arm(root, on_failure=None, stop_on_failure="block")
    code, out = _run(root)
    assert code == 1
    assert out["checks"]["hooks"]["guard_on_failure"] == [None]
    assert "(found: missing)" in _on_failure_reason(out)


def test_on_failure_on_the_stop_hook_beside_the_guards_is_no_reason(tmp_path: Path) -> None:
    """Control: preflight writes none on Stop, but one there is inert, and the
    assertion reads the guard's items only."""
    root = _repo(tmp_path)
    _arm(root, stop_on_failure="continue")
    code, out = _run(root)
    assert code == 0 and out["reasons"] == []


def test_two_guard_items_one_without_on_failure_is_not_armed(tmp_path: Path) -> None:
    """A merge that appended instead of replacing leaves a 3.x item beside the
    fresh one: Claude Code runs both, and the one without the key still lets a
    crash through. Every guard item must carry it."""
    root = _repo(tmp_path)
    _arm(root)
    path = root / ".claude" / "settings.local.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    fresh = settings["hooks"]["PreToolUse"][0]["hooks"][0]
    stale = {key: value for key, value in fresh.items() if key != "onFailure"}
    settings["hooks"]["PreToolUse"].append({"matcher": "*", "hooks": [stale]})
    path.write_text(json.dumps(settings), encoding="utf-8")
    code, out = _run(root)
    assert code == 1 and out["armed"] is False
    assert out["checks"]["hooks"]["guard_on_failure"] == ["block", None]
    assert '(found: "block", missing)' in _on_failure_reason(out)

    # Control: the same two items, both carrying it, pass.
    stale["onFailure"] = "block"
    path.write_text(json.dumps(settings), encoding="utf-8")
    code, out = _run(root)
    assert code == 0 and out["reasons"] == []


def test_a_guard_under_stop_with_on_failure_is_still_not_armed(tmp_path: Path) -> None:
    """The event stays part of the identity: an item that names the guard
    under hooks.Stop is never run before a tool call, whatever it carries."""
    root = _repo(tmp_path)
    _arm(root, guard=False)
    path = root / ".claude" / "settings.local.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    settings["hooks"]["Stop"][0]["hooks"].append(
        {"type": "command", "command": "uv run scripts/hooks/guard_pretooluse.py", "onFailure": "block"}
    )
    path.write_text(json.dumps(settings), encoding="utf-8")
    code, out = _run(root)
    assert code == 1
    assert out["checks"]["hooks"]["guard_present"] is False
    assert out["checks"]["hooks"]["guard_on_failure"] == []
    assert not any(r.startswith(_ON_FAILURE_REASON) for r in out["reasons"])


# --- arming: each hook command starts its script ------------------------------
# Claude Code hands a hook's command to a shell, which splits it at every
# unquoted space. Preflight writes `<env> uv run '<script>'` with each injected
# value and the script path in single quotes, so a path with a space stays one
# word. Unquoted, the rest of that path becomes the command the shell runs (it
# exits 127) or the file `uv run` is given, so the hook never starts: under the
# guard's "onFailure": "block" every tool call is refused, and the Stop budget
# hook silently does not run. The manifest reads each command the way the
# shell splits it, and never runs it.

_SPLIT_REASON = "UCG hook command does not start its script as written"


def _split_reason(out: dict) -> str:
    matches = [r for r in out["reasons"] if r.startswith(_SPLIT_REASON)]
    assert len(matches) == 1, out["reasons"]
    return matches[0]


def _spaced_command(root: Path, script: str, *, quote_env: bool = True, quote_script: bool = True) -> str:
    """The template filled in under a folder whose name holds a space, the way
    preflight.md step 5 writes it (quoted) or the way 4.0.0's draft did."""
    spaced = root / "sp ace"

    def word(value: str, quoted: bool) -> str:
        return f"'{value}'" if quoted else value

    values = {
        "ULTRACODE_PROTECTED_BRANCHES": "main,master",
        "ULTRACODE_IMPL_ARTIFACTS": (spaced / "impl").as_posix(),
        "ULTRACODE_MAX_TURNS": "25",
        "ULTRACODE_EPIC_BRANCH_PREFIX": "ultracode/epic-",
        "ULTRACODE_TEST_ARTIFACTS": (spaced / "ta").as_posix(),
    }
    env = " ".join(f"{key}={word(value, quote_env)}" for key, value in values.items())
    path = (spaced / "skill" / "scripts" / "hooks" / script).as_posix()
    return f"{env} uv run {word(path, quote_script)}"


def _process_env(root: Path) -> dict[str, str]:
    """The five vars in the process env, for a command that spells none of
    them, with a real epic-branch prefix: the branch check reads it."""
    return {
        "ULTRACODE_PROTECTED_BRANCHES": "main,master",
        "ULTRACODE_IMPL_ARTIFACTS": str(root / "impl"),
        "ULTRACODE_MAX_TURNS": "25",
        "ULTRACODE_EPIC_BRANCH_PREFIX": "ultracode/epic-",
        "ULTRACODE_TEST_ARTIFACTS": str(root / "ta"),
    }


def test_a_quoted_arming_under_a_path_with_a_space_is_armed(tmp_path: Path) -> None:
    """Control: the shape preflight.md step 5 writes passes, spaces and all."""
    root = _repo(tmp_path)
    _arm(
        root,
        guard_command=_spaced_command(root, "guard_pretooluse.py"),
        budget_command=_spaced_command(root, "budget_stop.py"),
    )
    code, out = _run(root)
    assert out["reasons"] == [] and code == 0, out["reasons"]
    hooks = out["checks"]["hooks"]
    assert hooks["commands_start_scripts"] is True
    assert hooks["command_problems"] == []


@pytest.mark.parametrize(
    "quote_env,quote_script,shown",
    [
        # The reviewed failure: the template filled in literally. The shell
        # runs the rest of the first spaced value as the command (exit 127).
        pytest.param(False, False, "the shell would run", id="nothing-quoted"),
        pytest.param(False, True, "the shell would run", id="values-unquoted"),
        pytest.param(True, False, "uv run would be given", id="script-path-unquoted"),
    ],
)
def test_an_unquoted_guard_under_a_path_with_a_space_is_not_armed(
    tmp_path: Path, quote_env: bool, quote_script: bool, shown: str
) -> None:
    root = _repo(tmp_path)
    _arm(
        root,
        guard_command=_spaced_command(root, "guard_pretooluse.py", quote_env=quote_env, quote_script=quote_script),
        budget_command=_spaced_command(root, "budget_stop.py"),
    )
    code, out = _run(root)
    assert code == 1 and out["armed"] is False
    hooks = out["checks"]["hooks"]
    # Every other fact about this arming holds: the env vars are spelled in
    # the command, the matcher covers every tool, the key is there.
    assert hooks["guard_present"] and hooks["matcher_all_tools"] and hooks["guard_on_failure_block"]
    assert out["checks"]["hook_env"]["ok"] is True
    assert hooks["commands_start_scripts"] is False
    assert len(hooks["command_problems"]) == 1
    problem = hooks["command_problems"][0]
    assert problem.startswith("guard_pretooluse.py under PreToolUse: ") and shown in problem
    reason = _split_reason(out)
    assert "in single quotes" in reason
    assert "Re-merge the hooks as preflight.md step 5's Hooks bullet says" in reason
    assert "replace, never append; on a resume purge nothing" in reason
    assert len(out["reasons"]) == 1, out["reasons"]


def test_an_unquoted_budget_hook_is_not_armed_either(tmp_path: Path) -> None:
    """A Stop hook that cannot start is skipped without a word: the budget
    layer is then gone while the arming reads as complete."""
    root = _repo(tmp_path)
    _arm(
        root,
        guard_command=_spaced_command(root, "guard_pretooluse.py"),
        budget_command=_spaced_command(root, "budget_stop.py", quote_env=False, quote_script=False),
    )
    code, out = _run(root)
    assert code == 1
    problems = out["checks"]["hooks"]["command_problems"]
    assert len(problems) == 1 and problems[0].startswith("budget_stop.py under Stop: ")
    assert "budget_stop.py under Stop" in _split_reason(out)


@pytest.mark.parametrize(
    "command,shown",
    [
        pytest.param(
            "ULTRACODE_MAX_TURNS='25 uv run 'scripts/hooks/guard_pretooluse.py'",
            "its quoting does not parse",
            id="unbalanced-quote",
        ),
        pytest.param("python3 'scripts/hooks/guard_pretooluse.py'", 'the shell would run "python3"', id="not-uv"),
        pytest.param("uv 'scripts/hooks/guard_pretooluse.py'", "uv is given", id="no-run"),
        pytest.param(
            "'scripts/hooks/guard_pretooluse.py'",
            'the shell would run "scripts/hooks/guard_pretooluse.py"',
            id="script-as-the-command",
        ),
        pytest.param("ULTRACODE_MAX_TURNS=guard_pretooluse.py", "the shell would run nothing", id="assignments-only"),
        pytest.param(
            "uv run 'scripts/hooks/guard_pretooluse.py.bak'", "uv run would be given", id="another-file"
        ),
    ],
)
def test_a_guard_command_that_would_not_start_the_guard_is_not_armed(
    tmp_path: Path, command: str, shown: str
) -> None:
    root = _repo(tmp_path)
    _arm(root, guard_command=command)
    code, out = _run(root, env=_process_env(root))
    assert code == 1
    problems = out["checks"]["hooks"]["command_problems"]
    assert len(problems) == 1 and shown in problems[0], problems
    assert len(out["reasons"]) == 1, out["reasons"]


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("uv run scripts/hooks/guard_pretooluse.py", id="relative-unquoted-no-space"),
        pytest.param("/opt/tools/bin/uv run '/srv/my proj/skill/scripts/hooks/guard_pretooluse.py'", id="uv-by-path"),
        pytest.param("uv run --quiet '/srv/p/scripts/hooks/guard_pretooluse.py'", id="uv-run-option"),
        pytest.param(
            "ULTRACODE_IMPL_ARTIFACTS='/srv/it'\\''s here/impl' uv run \"/srv/it's here/guard_pretooluse.py\"",
            id="a-quote-inside-a-value",
        ),
    ],
)
def test_a_guard_command_the_shell_splits_as_written_is_armed(tmp_path: Path, command: str) -> None:
    """Controls: what counts is how the shell splits the command, not one
    spelling of it, and the script path is never opened."""
    root = _repo(tmp_path)
    _arm(root, guard_command=command)
    code, out = _run(root, env=_process_env(root))
    assert out["reasons"] == [] and code == 0, out["reasons"]


def test_missing_settings_file_is_not_armed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    code, out = _run(root)
    assert code == 1
    assert out["checks"]["hooks"]["settings_readable"] is False
    assert any("missing or unreadable" in r for r in out["reasons"])


def test_a_story_skill_removed_since_launch_fails_the_resume(tmp_path: Path) -> None:
    """ucg-dev-story goes missing from an armed run between spawns (a manual
    deletion, or an install interrupted between removing and re-copying the
    UCG skills)."""
    root = _repo(tmp_path)
    _arm(root)
    shutil.rmtree(root / ".claude" / "skills" / "ucg-dev-story")
    code, out = _run(root)
    assert code == 1 and out["armed"] is False
    skills = out["checks"]["skills"]
    assert skills["installed"] == {"ucg-create-story": True, "ucg-dev-story": False}
    assert skills["missing"] == ["ucg-dev-story"]
    assert skills["ok"] is False
    assert any(r.startswith("UCG story skill(s) not installed: ucg-dev-story.") for r in out["reasons"])


def test_the_help_and_the_docs_name_the_ucg_story_skills() -> None:
    """The manifest probes UCG's story skills, never BMAD's deprecated shims,
    so text that says "the BMAD story skills" sends an operator to install
    shims that cannot pass it."""
    # A width wide enough that argparse wraps no help line: it breaks a line
    # after a hyphen, which would split `ucg-create-story` at whatever column
    # the wording happens to reach.
    env = {**os.environ, "COLUMNS": "1000"}
    proc = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, timeout=60, env=env)
    assert proc.returncode == 0, proc.stderr
    help_text = " ".join(proc.stdout.split())
    assert "the UCG story skills (ucg-create-story, ucg-dev-story)" in help_text
    preflight_md = SCRIPTS.parent / "references" / "preflight.md"
    for path in (SCRIPT, preflight_md):
        text = " ".join(path.read_text(encoding="utf-8").split())
        assert "BMAD story skill" not in text, path.name
    doc = " ".join(SCRIPT.read_text(encoding="utf-8").split())
    assert "the UCG story skills (a manual deletion between spawns" in doc
    step5 = " ".join(preflight_md.read_text(encoding="utf-8").split())
    assert "injected env, and the UCG story skills `ucg-create-story` and `ucg-dev-story`) in one read" in step5


def test_an_unexpandable_config_dir_still_emits_the_manifest(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    code, out = _run(root, env={"CLAUDE_CONFIG_DIR": "~nosuchuser_zz/claude"})
    assert code == 0 and out["armed"] is True
    assert out["checks"]["skills"]["ok"] is True


def test_missing_guard_or_budget_each_fail(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root, guard=False)
    code, out = _run(root)
    assert code == 1 and any("guard" in r for r in out["reasons"])
    _arm(root, budget=False)
    code, out = _run(root)
    assert code == 1 and any("budget_stop" in r for r in out["reasons"])


def test_an_unborn_epic_branch_is_not_armed(tmp_path: Path) -> None:
    """The epic branch name alone is not enough: with nothing committed under it,
    the branch has no base and its deletion would take the pre-run tree with it.
    The branch read stays the commit-resolving one, so this fails closed."""
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q", "-b", "ultracode/epic-7")
    for skill_id in ("ucg-create-story", "ucg-dev-story"):
        skill_dir = root / ".claude" / "skills" / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: {skill_id}\n---\n", encoding="utf-8")
    _arm(root)
    code, out = _run(root)
    assert code == 1
    assert out["checks"]["branch"]["ok"] is False


def test_wrong_branch_fails_and_names_the_prefix(tmp_path: Path) -> None:
    root = _repo(tmp_path, branch="feature/unrelated")
    _arm(root)
    code, out = _run(root)
    assert code == 1
    assert out["checks"]["branch"]["ok"] is False
    assert any("epic branch" in r for r in out["reasons"])


# --- hook env: both legitimate sources ---------------------------------------


def test_env_in_hook_command_strings_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root, env_in_command=True)
    _, out = _run(root)
    assert out["checks"]["hook_env"]["ok"] is True
    assert set(out["checks"]["hook_env"]["sources"].values()) == {"settings"}


def test_env_inherited_from_process_passes(tmp_path: Path) -> None:
    """preflight.md permits the process-env form; fail-closing on it would
    fail a legitimate arming.

    The values are realistic on purpose: ULTRACODE_EPIC_BRANCH_PREFIX feeds the
    branch check's expected prefix (env wins, the hooks' own semantic), so a
    nonsense value here would fail the branch assertion and hide what this test
    is about.
    """
    root = _repo(tmp_path)
    _arm(root, env_in_command=False)
    env = {
        "ULTRACODE_PROTECTED_BRANCHES": "main,master",
        "ULTRACODE_IMPL_ARTIFACTS": str(root / "impl"),
        "ULTRACODE_MAX_TURNS": "25",
        "ULTRACODE_EPIC_BRANCH_PREFIX": "ultracode/epic-",
        "ULTRACODE_TEST_ARTIFACTS": str(root / "ta"),
    }
    code, out = _run(root, env=env)
    assert code == 0
    assert set(out["checks"]["hook_env"]["sources"].values()) == {"process"}


def test_uninjected_env_fails_and_lists_the_missing_vars(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root, env_in_command=False)
    code, out = _run(root)
    assert code == 1
    assert set(out["checks"]["hook_env"]["missing"]) == set(_ENV_VARS)
    assert any("hardcoded fallbacks" in r for r in out["reasons"])


# --- the latch: reported, never certified ------------------------------------


def test_latch_never_moves_the_exit_and_never_certifies(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    (impl / ".mem-state.json").write_text(
        json.dumps(
            {"claude_mem": "present", "recall": "on", "run_id": "epic-7-20260101T000000Z"}
        ),
        encoding="utf-8",
    )
    code, out = _run(root, "--run-id", "epic-7-20260804T120000Z", impl=impl)
    latch = out["checks"]["latch"]
    assert code == 0, "a foreign latch is reported, not a failure"
    assert latch["state"] == "present"
    assert latch["owned_by_this_run"] is False
    assert latch["certifies"] is None, (
        "exit 0 must never become an inherited-latch claim by proxy"
    )


def test_absent_latch_is_a_reported_state_not_a_failure(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    code, out = _run(root)
    assert code == 0
    assert out["checks"]["latch"] == {"state": "absent", "certifies": None}


# --- the story route: artifact-derived, conservative --------------------------


def _story_files(
    impl: Path, story: str, *, baseline: str | None, marker_baseline: str | None
) -> None:
    if baseline is not None:
        (impl / f".baseline-{story}").write_text(baseline + "\n", encoding="utf-8")
    if marker_baseline is not None:
        (impl / f".tests-ran-{story}").write_text(
            f"baseline={marker_baseline}\nresult=green\n", encoding="utf-8"
        )


def test_no_baseline_routes_to_story_boundary(tmp_path: Path) -> None:
    """The normal `--max-stories` case: nothing to re-read, write it fresh."""
    root = _repo(tmp_path)
    _arm(root)
    code, out = _run(root, "--story", "7-2")
    assert code == 0
    story = out["checks"]["story"]
    assert story["baseline"] == "absent"
    assert story["route"] == "story-boundary"


def test_committed_green_ungated_routes_to_gate_owed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    base = _head(root)
    _story_files(impl, "7-2", baseline=base, marker_baseline=base)
    (root / "work.txt").write_text("done\n", encoding="utf-8")
    _git(root, "add", "work.txt")
    _git(root, "commit", "-q", "-m", "story 7-2")
    trace = root / "trace"
    trace.mkdir()
    _, out = _run(root, "--story", "7-2", "--trace-output", str(trace), impl=impl)
    story = out["checks"]["story"]
    assert story["commits_past_baseline"] == 1
    assert story["tests_ran_fresh"] is True
    assert story["gate_artifacts"] == "absent"
    assert story["route"] == "gate-owed"


def test_no_commits_past_baseline_blocks_gate_owed(tmp_path: Path) -> None:
    """Marker fresh, dir present, but nothing committed: the discriminator's
    commits leg must hold, or a story that died before its commit skips its
    own implementation."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    base = _head(root)
    _story_files(impl, "7-2", baseline=base, marker_baseline=base)
    trace = root / "trace"
    trace.mkdir()
    _, out = _run(root, "--story", "7-2", "--trace-output", str(trace), impl=impl)
    story = out["checks"]["story"]
    assert story["commits_past_baseline"] == 0
    assert story["route"] == "mid-story"


def test_gate_owed_requires_trace_output_evidence(tmp_path: Path) -> None:
    """Without --trace-output the discriminator cannot hold in full: absence of
    evidence must route to the ordinary loop, never past steps 1-4."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    base = _head(root)
    _story_files(impl, "7-2", baseline=base, marker_baseline=base)
    (root / "work.txt").write_text("done\n", encoding="utf-8")
    _git(root, "add", "work.txt")
    _git(root, "commit", "-q", "-m", "story 7-2")
    _, out = _run(root, "--story", "7-2", impl=impl)
    story = out["checks"]["story"]
    assert story["gate_artifacts"] == "unknown"
    assert story["route"] == "mid-story"


def test_a_nonexistent_trace_dir_is_unknown_not_absent(tmp_path: Path) -> None:
    """An unverifiable location is never verified absence: gate-owed must not
    fire on a --trace-output that does not exist or is not a directory."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    base = _head(root)
    _story_files(impl, "7-2", baseline=base, marker_baseline=base)
    (root / "work.txt").write_text("done\n", encoding="utf-8")
    _git(root, "add", "work.txt")
    _git(root, "commit", "-q", "-m", "story 7-2")
    _, out = _run(root, "--story", "7-2", "--trace-output", str(root / "no-such"), impl=impl)
    assert out["checks"]["story"]["gate_artifacts"] == "unknown"
    assert out["checks"]["story"]["route"] == "mid-story"


def test_generic_artifacts_in_an_isolated_dir_read_present(tmp_path: Path) -> None:
    """TEA's untouched generic output (gate-decision.json with no story id) is
    the one-story-directory shape gate_eval's unscoped fallback reads; the
    manifest must agree, or it routes gate-owed past a real gate decision."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    base = _head(root)
    _story_files(impl, "7-2", baseline=base, marker_baseline=base)
    (root / "work.txt").write_text("done\n", encoding="utf-8")
    _git(root, "add", "work.txt")
    _git(root, "commit", "-q", "-m", "story 7-2")
    trace = root / "trace"
    trace.mkdir()
    (trace / "gate-decision.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )
    _, out = _run(root, "--story", "7-2", "--trace-output", str(trace), impl=impl)
    assert out["checks"]["story"]["gate_artifacts"] == "present"
    assert out["checks"]["story"]["route"] == "mid-story"


def test_guard_under_the_wrong_event_is_not_armed(tmp_path: Path) -> None:
    """A guard command sitting under hooks.Stop is never invoked before a tool
    call; an event-blind read certified exactly that arming."""
    root = _repo(tmp_path)
    settings = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {"type": "command", "command": "uv run scripts/hooks/guard_pretooluse.py"},
                        {"type": "command", "command": "uv run scripts/hooks/budget_stop.py"},
                    ]
                }
            ]
        }
    }
    claude_dir = root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "settings.local.json").write_text(json.dumps(settings), encoding="utf-8")
    code, out = _run(root)
    assert code == 1
    assert out["checks"]["hooks"]["guard_present"] is False


def test_a_non_object_latch_is_unreadable_not_a_crash(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    (impl / ".mem-state.json").write_text("[1, 2, 3]", encoding="utf-8")
    code, out = _run(root, impl=impl)
    assert code == 0
    assert out["checks"]["latch"] == {"state": "unreadable", "certifies": None}


def test_a_latch_nested_too_deep_to_parse_is_unreadable_not_a_crash(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    (impl / ".mem-state.json").write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
    code, out = _run(root, impl=impl)
    assert code == 0
    assert out["checks"]["latch"] == {"state": "unreadable", "certifies": None}


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO (POSIX)")
def test_a_fifo_under_the_latch_name_is_unreadable_not_a_hang(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    os.mkfifo(impl / ".mem-state.json")
    code, out = _run(root, impl=impl, timeout=60)
    assert code == 0
    assert out["checks"]["latch"] == {"state": "unreadable", "certifies": None}


def test_a_gated_story_is_mid_story_not_gate_owed(tmp_path: Path) -> None:
    """Its gate artifact resolved, so nothing routes past the ordinary loop."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    base = _head(root)
    _story_files(impl, "7-2", baseline=base, marker_baseline=base)
    (root / "work.txt").write_text("done\n", encoding="utf-8")
    _git(root, "add", "work.txt")
    _git(root, "commit", "-q", "-m", "story 7-2")
    trace = root / "trace"
    trace.mkdir()
    (trace / "gate-decision-7-2.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )
    _, out = _run(root, "--story", "7-2", "--trace-output", str(trace), impl=impl)
    assert out["checks"]["story"]["gate_artifacts"] == "present"
    assert out["checks"]["story"]["route"] == "mid-story"


def test_a_stale_tests_ran_marker_blocks_gate_owed(tmp_path: Path) -> None:
    """A marker whose baseline= differs is a replay; the discriminator must
    hold IN FULL (execute.md's third-class rule)."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    base = _head(root)
    _story_files(impl, "7-2", baseline=base, marker_baseline="0" * 40)
    (root / "work.txt").write_text("done\n", encoding="utf-8")
    _git(root, "add", "work.txt")
    _git(root, "commit", "-q", "-m", "story 7-2")
    trace = root / "trace"
    trace.mkdir()
    _, out = _run(root, "--story", "7-2", "--trace-output", str(trace), impl=impl)
    story = out["checks"]["story"]
    assert story["tests_ran_fresh"] is False
    assert story["route"] == "mid-story"


def test_story_and_latch_blocks_never_flip_a_failed_arming_green(tmp_path: Path) -> None:
    """The exit is the arming verdict alone, in both directions."""
    root = _repo(tmp_path, branch="feature/unrelated")
    _arm(root, matcher="Bash")
    code, out = _run(root, "--story", "7-2")
    assert code == 1 and out["armed"] is False
    assert out["checks"]["story"]["route"] == "story-boundary"


def test_an_owned_latch_reports_true_and_still_never_certifies(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    (impl / ".mem-state.json").write_text(
        json.dumps({"claude_mem": "present", "recall": "on", "run_id": "epic-7-X"}),
        encoding="utf-8",
    )
    code, out = _run(root, "--run-id", "epic-7-X", impl=impl)
    latch = out["checks"]["latch"]
    assert code == 0
    assert latch["owned_by_this_run"] is True
    assert latch["certifies"] is None


# --- the latch: version and store_ok colour (latch v2) -------------------------
# A present latch also reports its latch_version and the derived store_ok
# colour, read through lib/mem_common.py's latch_view. Reporting only: neither
# moves the exit code, adds a reason, or certifies anything.

_LATCH_RUN = "epic-7-20260804T120000Z"

_V1_GREEN_BY_OLD_RULES = {
    "latch_version": 1,
    "run_id": _LATCH_RUN,
    "claude_mem": "present",
    "schema_ok": True,
    "recall": "on",
    "tool_form": "plugin",
    "fingerprint": "0123456789abcdef",
    "created_at": "2026-08-04T12:00:00Z",
}


def _v2_latch(store_root: Path, overrides: dict | None = None) -> dict:
    state = {
        "latch_version": 2,
        "run_id": _LATCH_RUN,
        "backend": "jsonl",
        "store_ok": True,
        "recall": "on",
        "store": str(store_root),
        "fingerprint": "0123456789abcdef",
        "created_at": "2026-08-04T12:00:00Z",
    }
    state.update(overrides or {})
    return state


def _write_latch(impl: Path, state: dict) -> None:
    impl.mkdir(exist_ok=True)
    (impl / ".mem-state.json").write_text(json.dumps(state), encoding="utf-8")


def test_a_v1_latch_reports_version_1_and_reads_red(tmp_path: Path) -> None:
    """CSR-INT-030 (AC-16): even a v1 latch that was green by the claude-mem
    rules reads red; its own fields keep reporting as before."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    _write_latch(impl, _V1_GREEN_BY_OLD_RULES)
    code, out = _run(root, "--run-id", _LATCH_RUN, impl=impl)
    latch = out["checks"]["latch"]
    assert code == 0 and out["armed"] is True and out["reasons"] == []
    assert latch["latch_version"] == 1
    assert latch["store_ok"] is False
    assert latch["certifies"] is None
    assert latch["state"] == "present"
    assert latch["claude_mem"] == "present"
    assert latch["recall"] == "on"
    assert latch["run_id"] == _LATCH_RUN
    assert latch["owned_by_this_run"] is True


def test_a_green_v2_latch_reports_green_and_still_never_certifies(tmp_path: Path) -> None:
    """CSR-INT-034 (AC-16): the colour is reported, never certified."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    _write_latch(impl, _v2_latch(tmp_path / "store"))
    code, out = _run(root, "--run-id", _LATCH_RUN, impl=impl)
    latch = out["checks"]["latch"]
    assert code == 0 and out["armed"] is True and out["reasons"] == []
    assert latch["latch_version"] == 2
    assert latch["store_ok"] is True
    assert latch["owned_by_this_run"] is True
    assert latch["certifies"] is None


@pytest.mark.parametrize(
    "overrides, version",
    [
        ({"store_ok": False}, 2),
        ({"store_ok": "true"}, 2),
        ({"recall": "off"}, 2),
        ({"backend": "claude-mem"}, 2),
        ({"store": ""}, 2),
        ({"store": "{workflow.cross_session_recall_store}"}, 2),
        ({"store": None}, 2),
        ({"store": "relative/store"}, 2),
        ({"store": "/abs/st\0ore"}, 2),
        ({"latch_version": 3}, 3),
        ({"latch_version": True}, None),
        ({"latch_version": "2"}, None),
    ],
    ids=[
        "store-not-ok", "store-ok-a-string", "recall-off", "other-backend", "store-empty",
        "store-unresolved", "store-null", "store-relative", "store-nul", "version-3",
        "version-bool", "version-string",
    ],
)
def test_a_latch_short_of_green_v2_reads_red(
    overrides: dict, version: int | None, tmp_path: Path
) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    _write_latch(impl, _v2_latch(tmp_path / "store", overrides))
    code, out = _run(root, "--run-id", _LATCH_RUN, impl=impl)
    latch = out["checks"]["latch"]
    assert code == 0 and out["reasons"] == []
    assert latch["latch_version"] == version
    assert latch["store_ok"] is False
    assert latch["certifies"] is None


@pytest.mark.parametrize("name", ["my$proj", "{x}", "50%"])
def test_a_green_v2_latch_under_an_odd_folder_name_reads_green(name: str, tmp_path: Path) -> None:
    """The latch holds the resolved store, taken as written: a "$", braces or
    "%" in a folder name never turn a green latch red."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    _write_latch(impl, _v2_latch(tmp_path / name / ".recall"))
    code, out = _run(root, "--run-id", _LATCH_RUN, impl=impl)
    latch = out["checks"]["latch"]
    assert code == 0 and out["reasons"] == []
    assert latch["latch_version"] == 2
    assert latch["store_ok"] is True


def test_a_versionless_latch_reads_red(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    _write_latch(impl, {"claude_mem": "present", "recall": "on", "run_id": _LATCH_RUN})
    code, out = _run(root, impl=impl)
    latch = out["checks"]["latch"]
    assert code == 0
    assert latch["latch_version"] is None
    assert latch["store_ok"] is False
    assert "owned_by_this_run" not in latch


def test_a_green_v2_latch_never_flips_a_failed_arming(tmp_path: Path) -> None:
    """The exit stays the arming verdict alone, and the latch adds no reason."""
    root = _repo(tmp_path, branch="feature/unrelated")
    _arm(root, matcher="Bash")
    impl = root / "impl"
    impl.mkdir()
    _, without_latch = _run(root, impl=impl)
    _write_latch(impl, _v2_latch(tmp_path / "store"))
    code, out = _run(root, impl=impl)
    assert code == 1 and out["armed"] is False
    assert out["checks"]["latch"]["store_ok"] is True
    assert out["reasons"] == without_latch["reasons"]


def test_the_latch_mem_recall_writes_reads_green_here(tmp_path: Path) -> None:
    """End to end: the latch `mem_recall.py latch --store` writes is the one
    this report reads green."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    home = tmp_path / "home"
    home.mkdir()
    store = tmp_path / "store"
    proc = subprocess.run(
        [
            sys.executable, str(SCRIPTS / "mem_recall.py"), "latch",
            "--impl-artifacts", str(impl), "--run-id", _LATCH_RUN, "--recall", "on",
            "--store", str(store), "--cwd", str(root),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, **_GIT_ENV, "HOME": str(home), "USERPROFILE": str(home)},
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["latch"]["store_ok"] is True
    code, out = _run(root, "--run-id", _LATCH_RUN, impl=impl)
    latch = out["checks"]["latch"]
    assert code == 0
    assert latch["latch_version"] == 2
    assert latch["store_ok"] is True
    assert latch["owned_by_this_run"] is True
    assert latch["certifies"] is None


def test_an_epic_branch_that_is_also_protected_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    code, out = _run(root, "--protected-branch", "ultracode/epic-7")
    assert code == 1
    assert out["checks"]["branch"]["ok"] is False


# --- an open escalation outranks every route ----------------------------------

_ESC_STORY = "7-2-the-story"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _sidecar(
    impl: Path,
    *,
    kind: str = "gate-fail-needs-operator",
    decision: str = "Pick (a) or (b).",
    source: str = "impl/7-2-the-story.md:12",
) -> dict:
    """A typed sidecar in the shape execute.md fixes: four string fields."""
    body = {"source": source, "kind": kind, "decision_needed": decision, "evidence": "one line"}
    impl.mkdir(exist_ok=True)
    (impl / f"escalation-{_ESC_STORY}.json").write_text(json.dumps(body), encoding="utf-8")
    return body


def _record(impl: Path, body: dict, *, action: str, decision: str | None = None) -> None:
    """A .decisions.json entry keyed the way /ucg-resolve keys a typed sidecar."""
    rid = _load("red_ids").mint_id(
        body["kind"], body["source"], body["decision_needed"] if decision is None else decision
    )
    (impl / ".decisions.json").write_text(
        json.dumps({"decisions": [{"id": rid, "answer": "a", "action": action}]}),
        encoding="utf-8",
    )


def _committed_green(root: Path, impl: Path) -> Path:
    """Committed past a fresh baseline, a matching tests-ran marker, and a
    per-story-named trace dir holding nothing for this story: gate-owed."""
    impl.mkdir(exist_ok=True)
    base = _head(root)
    _story_files(impl, _ESC_STORY, baseline=base, marker_baseline=base)
    (root / "work.txt").write_text("done\n", encoding="utf-8")
    _git(root, "add", "work.txt")
    _git(root, "commit", "-q", "-m", "story 7-2")
    trace = root / "trace"
    trace.mkdir()
    (trace / "trace-7-1.md").write_text("x\n", encoding="utf-8")
    return trace


def test_an_open_escalation_routes_decision_pending_at_a_story_boundary(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    _sidecar(impl)
    code, out = _run(root, "--story", _ESC_STORY, impl=impl)
    story = out["checks"]["story"]
    # The exit stays the arming verdict: the route is what the resume reads.
    assert code == 0 and out["armed"] is True and out["reasons"] == []
    assert story["baseline"] == "absent"
    assert story["route"] == "decision-pending"
    assert story["escalation"]["state"] == "open"
    assert story["escalation"]["readable"] is True
    assert story["escalation"]["kind"] == "gate-fail-needs-operator"


def test_an_open_escalation_outranks_gate_owed(tmp_path: Path) -> None:
    """The reproduced shape: committed, green, un-gated, and a decision nobody
    closed. Gating it would act on that decision."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    trace = _committed_green(root, impl)
    _, out = _run(root, "--story", _ESC_STORY, "--trace-output", str(trace), impl=impl)
    assert out["checks"]["story"]["route"] == "gate-owed"  # the twin: no sidecar
    _sidecar(impl)
    _, out = _run(root, "--story", _ESC_STORY, "--trace-output", str(trace), impl=impl)
    assert out["checks"]["story"]["gate_artifacts"] == "absent"
    assert out["checks"]["story"]["route"] == "decision-pending"


def test_an_open_escalation_outranks_mid_story(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    _story_files(impl, _ESC_STORY, baseline=_head(root), marker_baseline=None)
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    assert out["checks"]["story"]["route"] == "mid-story"  # the twin: no sidecar
    _sidecar(impl)
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    assert out["checks"]["story"]["route"] == "decision-pending"


def test_no_sidecar_reports_null_escalation(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    _, out = _run(root, "--story", _ESC_STORY)
    assert out["checks"]["story"]["escalation"] is None
    assert out["checks"]["story"]["route"] == "story-boundary"


def test_a_closed_id_is_residue_not_a_pending_decision(tmp_path: Path) -> None:
    """/ucg-resolve never re-asks a closed id, so routing on it would stop the
    resume on a question no surface offers."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    body = _sidecar(impl)
    _record(impl, body, action="close")
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    escalation = out["checks"]["story"]["escalation"]
    assert escalation["state"] == "closed"
    assert escalation["id"] == _load("red_ids").mint_id(
        body["kind"], body["source"], body["decision_needed"]
    )
    assert "blocker" not in escalation
    assert out["checks"]["story"]["route"] == "story-boundary"


def test_a_deferred_id_stays_pending(tmp_path: Path) -> None:
    """A `defer` leaves the sidecar on disk and the decision open."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    body = _sidecar(impl)
    _record(impl, body, action="defer")
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    assert out["checks"]["story"]["escalation"]["state"] == "open"
    assert out["checks"]["story"]["route"] == "decision-pending"


def test_a_close_for_a_reworded_decision_does_not_close_this_one(tmp_path: Path) -> None:
    """Recognition is exact, as red_ids.py's is: a reword is another decision."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    body = _sidecar(impl)
    _record(impl, body, action="close", decision="Pick (a), (b) or (c).")
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    assert out["checks"]["story"]["route"] == "decision-pending"


@pytest.mark.parametrize(
    "decisions",
    ["{not json", "[" * 100_000 + "]" * 100_000, json.dumps({"decisions": "x"})],
    # Short ids: a long one lengthens tmp_path past what git accepts.
    ids=["bad-json", "too-deep", "not-a-list"],
)
def test_an_unreadable_decisions_file_closes_nothing(tmp_path: Path, decisions: str) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    _sidecar(impl)
    (impl / ".decisions.json").write_text(decisions, encoding="utf-8")
    code, out = _run(root, "--story", _ESC_STORY, impl=impl)
    assert code == 0
    assert out["checks"]["story"]["route"] == "decision-pending"


@pytest.mark.parametrize(
    "raw",
    [
        "{not json",
        "[]",
        json.dumps({"source": "s", "kind": 3, "decision_needed": "d"}),
        # Under the size cap, so it is the nesting that fails the parse.
        "[" * 20_000 + "]" * 20_000,
        json.dumps({"source": "s", "kind": "k", "decision_needed": "d", "pad": "x" * 70_000}),
        # A lone surrogate parses from its JSON escape but encodes to no UTF-8,
        # so no id can be minted from the field that holds it.
        '{"source": "s", "kind": "k", "decision_needed": "Pick (a) or (b) \\ud800.", "evidence": "e"}',
        '{"source": "s\\udc80", "kind": "story-decomposed", "decision_needed": "d", "evidence": "e"}',
    ],
    ids=["bad-json", "array", "kind-not-str", "too-deep", "oversize", "surrogate", "surrogate-handoff"],
)
def test_an_unreadable_sidecar_fails_closed(tmp_path: Path, raw: str) -> None:
    """Something escalated, and nothing here can say it was answered."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    (impl / f"escalation-{_ESC_STORY}.json").write_text(raw, encoding="utf-8")
    code, out = _run(root, "--story", _ESC_STORY, impl=impl)
    escalation = out["checks"]["story"]["escalation"]
    assert code == 0
    assert escalation["state"] == "open" and escalation["readable"] is False
    assert "cannot be read" in escalation["blocker"]["decision_needed"]
    assert out["checks"]["story"]["route"] == "decision-pending"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_a_dangling_link_under_the_sidecar_name_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    try:
        os.symlink(impl / "gone.json", impl / f"escalation-{_ESC_STORY}.json")
    except OSError:
        pytest.skip("symlinks are not permitted here")
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    assert out["checks"]["story"]["escalation"]["readable"] is False
    assert out["checks"]["story"]["route"] == "decision-pending"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO (POSIX)")
def test_a_fifo_under_the_sidecar_name_is_unreadable_not_a_hang(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    os.mkfifo(impl / f"escalation-{_ESC_STORY}.json")
    code, out = _run(root, "--story", _ESC_STORY, impl=impl, timeout=60)
    assert code == 0
    assert out["checks"]["story"]["escalation"]["readable"] is False
    assert out["checks"]["story"]["route"] == "decision-pending"


@pytest.mark.parametrize("kind", ["story-decomposed", "defined-not-driven"])
def test_a_handoff_kind_does_not_set_the_route(tmp_path: Path, kind: str) -> None:
    """Work handed to this invocation, not a decision (execute.md's handoff)."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    _sidecar(impl, kind=kind)
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    escalation = out["checks"]["story"]["escalation"]
    assert escalation["state"] == "handoff"
    assert "blocker" not in escalation
    assert out["checks"]["story"]["route"] == "story-boundary"


def test_a_sidecar_for_another_story_does_not_touch_this_one(tmp_path: Path) -> None:
    """The sidecar is matched by its exact name only, never by a prefix."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    body = {"source": "s", "kind": "k", "decision_needed": "d", "evidence": "e"}
    for other in ("7-1", "7-2"):
        (impl / f"escalation-{other}.json").write_text(json.dumps(body), encoding="utf-8")
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    assert out["checks"]["story"]["escalation"] is None
    assert out["checks"]["story"]["route"] == "story-boundary"


def test_the_blocker_renders_a_one_line_reason_naming_the_sidecar(tmp_path: Path) -> None:
    """execute.md hands `escalation.blocker` to the headless adapter as the one
    blocker; the envelope's `reason` must then name the sidecar."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    _sidecar(impl)
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    blocker = out["checks"]["story"]["escalation"]["blocker"]
    log = tmp_path / "decision-log.md"
    log.write_text("", encoding="utf-8")
    envelope = _load("headless_envelope").build_headless_envelope([blocker], str(log))
    assert envelope["status"] == "blocked"
    assert f"escalation-{_ESC_STORY}.json" in envelope["reason"]
    assert "decision-pending" in envelope["reason"]
    assert "/ucg-resolve" in envelope["reason"]
    assert "\n" not in envelope["reason"]


def _close(impl: Path, rid: str) -> None:
    (impl / ".decisions.json").write_text(
        json.dumps({"decisions": [{"id": rid, "answer": "a", "action": "close"}]}),
        encoding="utf-8",
    )


@pytest.mark.parametrize("spelling", ["relative", "absolute"])
def test_a_close_keyed_by_the_sidecar_path_is_residue_too(tmp_path: Path, spelling: str) -> None:
    """The field case: real /ucg-resolve closes keyed the id by the sidecar's
    own path, not its `source`, and left the sidecar on disk. Reading that as
    open stopped the resume on a decision the operator had closed."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    body = _sidecar(impl)
    name = f"escalation-{_ESC_STORY}.json"
    path = f"impl/{name}" if spelling == "relative" else str(impl / name)
    _close(impl, _load("red_ids").mint_id(body["kind"], path, body["decision_needed"]))
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    escalation = out["checks"]["story"]["escalation"]
    assert escalation["state"] == "closed"
    # The id reported stays the documented one, minted from `source`.
    assert escalation["id"] == _load("red_ids").mint_id(body["kind"], body["source"], body["decision_needed"])
    assert "blocker" not in escalation
    assert out["checks"]["story"]["route"] == "story-boundary"


def test_a_path_keyed_close_of_another_sidecar_does_not_close_this_one(tmp_path: Path) -> None:
    """Twin: the path id binds the path and the decision's wording, so a
    close keyed by a sibling story's sidecar path leaves this one open."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    body = _sidecar(impl)
    _close(impl, _load("red_ids").mint_id(body["kind"], "impl/escalation-7-1.json", body["decision_needed"]))
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    assert out["checks"]["story"]["escalation"]["state"] == "open"
    assert out["checks"]["story"]["route"] == "decision-pending"


# --- a closed operator-evidence-owed story owes a re-gate ---------------------


def _failed_gate(root: Path, impl: Path) -> tuple[Path, str]:
    """The story an operator-evidence-owed escalation leaves: committed past a
    fresh baseline, green, and its FAIL gate's artifacts in the trace dir."""
    trace = _committed_green(root, impl)
    (trace / f"trace-{_ESC_STORY}.md").write_text("---\nworkflowType: testarch-trace\n---\n", encoding="utf-8")
    (trace / f"gate-decision-{_ESC_STORY}.json").write_text(
        json.dumps({"gate_status": "FAIL"}), encoding="utf-8"
    )
    return trace, _head(root)


def _regate(impl: Path, sha: str) -> None:
    """The marker /ucg-resolve writes when it closes the escalation."""
    (impl / f".regate-{_ESC_STORY}").write_text(
        f"sha={sha}\ndecision=operator-evidence-owed:trace/trace-{_ESC_STORY}.md:0123456789ab\n",
        encoding="utf-8",
    )


def test_a_closed_operator_evidence_owed_story_is_re_gated_not_re_driven(tmp_path: Path) -> None:
    """The reproduced shape: after the close the sidecar is gone and the FAIL
    gate's artifacts block gate-owed, so the resume re-drove the story from
    step 0, where the ceiling read could escalate it and steps 1-4 could commit
    past the commit the operator's records were made at."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    trace, head = _failed_gate(root, impl)
    _, out = _run(root, "--story", _ESC_STORY, "--trace-output", str(trace), impl=impl)
    story = out["checks"]["story"]
    assert story["gate_artifacts"] == "present" and story["escalation"] is None
    assert story["regate"] is None
    assert story["route"] == "mid-story"  # the twin: no marker
    _regate(impl, head)
    for extra in (("--trace-output", str(trace)), ()):
        code, out = _run(root, "--story", _ESC_STORY, *extra, impl=impl)
        story = out["checks"]["story"]
        assert code == 0
        assert story["regate"]["state"] == "fresh"
        assert story["regate"]["sha"] == head
        assert story["regate"]["decision"].startswith("operator-evidence-owed:")
        assert story["route"] == "gate-owed"


def test_a_regate_marker_short_sha_naming_head_is_fresh(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    trace, head = _failed_gate(root, impl)
    _regate(impl, head[:12].upper())
    _, out = _run(root, "--story", _ESC_STORY, "--trace-output", str(trace), impl=impl)
    assert out["checks"]["story"]["regate"]["state"] == "fresh"
    assert out["checks"]["story"]["route"] == "gate-owed"


def test_a_regate_marker_behind_head_is_stale(tmp_path: Path) -> None:
    """A later commit makes the operator's records stale: route as without it."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    trace, head = _failed_gate(root, impl)
    _regate(impl, head)
    (root / "later.txt").write_text("later\n", encoding="utf-8")
    _git(root, "add", "later.txt")
    _git(root, "commit", "-q", "-m", "after the assessed commit")
    _, out = _run(root, "--story", _ESC_STORY, "--trace-output", str(trace), impl=impl)
    story = out["checks"]["story"]
    assert story["regate"]["state"] == "stale"
    assert story["regate"]["sha"] == head
    assert story["route"] == "mid-story"


@pytest.mark.parametrize(
    "raw",
    ["sha=HEAD\n", "sha=\n", "decision=x\n", "sha=" + "0" * 40 + "\n", "sha=zz\n", b"sha=\xff\n", "x" * 5000],
    ids=["ref-name", "empty", "no-sha", "no-such-commit", "not-hex", "not-utf8", "oversize"],
)
def test_a_regate_marker_that_names_no_head_commit_is_stale(tmp_path: Path, raw: str | bytes) -> None:
    """Fail closed: only a commit id that resolves to HEAD skips steps 0-4."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    trace, _ = _failed_gate(root, impl)
    marker = impl / f".regate-{_ESC_STORY}"
    if isinstance(raw, bytes):
        marker.write_bytes(raw)
    else:
        marker.write_text(raw, encoding="utf-8")
    code, out = _run(root, "--story", _ESC_STORY, "--trace-output", str(trace), impl=impl)
    assert code == 0
    assert out["checks"]["story"]["regate"]["state"] == "stale"
    assert out["checks"]["story"]["route"] == "mid-story"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO (POSIX)")
def test_a_fifo_under_the_regate_name_is_stale_not_a_hang(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    trace, _ = _failed_gate(root, impl)
    os.mkfifo(impl / f".regate-{_ESC_STORY}")
    _, out = _run(root, "--story", _ESC_STORY, "--trace-output", str(trace), impl=impl, timeout=60)
    assert out["checks"]["story"]["regate"]["state"] == "stale"
    assert out["checks"]["story"]["route"] == "mid-story"


def test_an_open_escalation_outranks_a_fresh_regate(tmp_path: Path) -> None:
    """The re-gate escalated again: the new sidecar is the pending decision."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    trace, head = _failed_gate(root, impl)
    _regate(impl, head)
    _sidecar(impl, kind="operator-evidence-owed")
    _, out = _run(root, "--story", _ESC_STORY, "--trace-output", str(trace), impl=impl)
    assert out["checks"]["story"]["regate"]["state"] == "fresh"
    assert out["checks"]["story"]["route"] == "decision-pending"


def test_a_fresh_regate_without_a_baseline_is_not_gate_owed(tmp_path: Path) -> None:
    """Step 5 re-reads the baseline; with none, nothing routes past step 0."""
    root = _repo(tmp_path)
    _arm(root)
    impl = root / "impl"
    impl.mkdir()
    _regate(impl, _head(root))
    _, out = _run(root, "--story", _ESC_STORY, impl=impl)
    assert out["checks"]["story"]["regate"]["state"] == "fresh"
    assert out["checks"]["story"]["route"] == "story-boundary"


# --- the doc contract ---------------------------------------------------------


def test_execute_resume_rule_names_the_manifest_invocation() -> None:
    """The mechanization must live where the sweep it replaces is mandated —
    and as a runnable command, not a flag mention."""
    import re

    execute = (SCRIPTS.parent / "references" / "execute.md").read_text(encoding="utf-8")
    spans = re.findall(r"`([^`]*--assert-armed[^`]*)`", execute)
    assert spans, "no backticked --assert-armed invocation in execute.md"
    cmd = max(spans, key=len)
    for token in (
        "preflight_check.py",
        "--project-root",
        "--impl-artifacts",
        "--epic-branch-prefix",
        "--story",
        "--run-id",
        "--trace-output",
    ):
        assert token in cmd, f"invocation is missing {token}: {cmd}"
    assert "reported, never certified" in execute.lower()


def test_preflight_step5_names_the_assert_mode() -> None:
    preflight = (SCRIPTS.parent / "references" / "preflight.md").read_text(encoding="utf-8")
    assert "--assert-armed" in preflight


def test_resume_rule_stops_on_an_open_escalation() -> None:
    """The route only helps if the resume rule says what to do on it: drive
    nothing, overwrite nothing, and hand the blocker to the adapter."""
    execute = (SCRIPTS.parent / "references" / "execute.md").read_text(encoding="utf-8")
    for token in ("`decision-pending`", "`/ucg-resolve`", "`escalation.blocker`", "write no sidecar"):
        assert token in execute, f"execute.md's resume rule is missing {token}"
    skill = (SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
    resume = next(line for line in skill.splitlines() if line.startswith("**Resume.**"))
    for token in ("`decision-pending`", "`/ucg-resolve`"):
        assert token in resume, f"SKILL.md's Resume paragraph is missing {token}"


def test_ucg_resolve_names_the_value_a_sidecar_id_is_minted_from() -> None:
    """The reader accepts a close keyed by `source` or by the sidecar's path,
    but /ucg-resolve must mint with one value, said plainly: `source`."""
    resolve = " ".join((SCRIPTS.parents[1] / "ucg-resolve" / "SKILL.md").read_text(encoding="utf-8").split())
    assert "`<artifact path>` is the sidecar's `source` field" in resolve
    assert "never the path of the sidecar file itself" in resolve
    execute = " ".join((SCRIPTS.parent / "references" / "execute.md").read_text(encoding="utf-8").split())
    assert "a close keyed by the sidecar file's own path, as earlier passes keyed some, counts too" in execute
