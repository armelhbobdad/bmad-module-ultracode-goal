#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""The resume manifest: `preflight_check.py --assert-armed`.

One deterministic read replaces the tool-action-per-fact environment sweep the
resume rule costs on every `--max-stories` spawn. These tests pin the four
properties that make it trustworthy rather than merely convenient:

1. FAIL-CLOSED ARMING. Exit 0 requires the epic branch, both hooks with the
   all-tools PreToolUse matcher, and all five injected env vars. A missing or
   unreadable settings file, a `Bash`-only matcher (the observed inert-control
   state), or an uninjected var each fail the exit, with a reason naming it.
2. LEGITIMATE ARMINGS PASS. preflight step 5 permits the env vars either in the
   hook command strings or in the process env the hooks inherit; fail-closing
   on the inherited form would teach operators to skip the check.
3. THE LATCH IS REPORTED, NEVER CERTIFIED. `certifies` is a literal null and
   the latch never moves the exit code: exit 0 must not become an
   inherited-latch claim by proxy, because re-latching from this run's own
   measurement is a model-owned Stage 1 step on every resume.
4. THE STORY ROUTE IS ARTIFACT-DERIVED AND CONSERVATIVE. `gate-owed` (skip to
   step 5) fires only when the full discriminator holds AND --trace-output
   supplied the artifact evidence; absence of evidence routes to the ordinary
   loop, never past it.

Run: uv run --with pytest pytest scripts/tests/test_preflight_assert_armed.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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
) -> None:
    """Write a settings.local.json in the real nested shape preflight documents."""
    env_prefix = (
        " ".join(f"{v}=x" for v in _ENV_VARS) + " " if env_in_command else ""
    )
    pre_group: dict = {
        "hooks": [{"type": "command", "command": f"{env_prefix}uv run scripts/hooks/guard_pretooluse.py"}]
    }
    if matcher is not None:
        pre_group["matcher"] = matcher
    settings = {
        "hooks": {
            "PreToolUse": [pre_group] if guard else [],
            "Stop": [
                {"hooks": [{"type": "command", "command": "uv run scripts/hooks/budget_stop.py"}]}
            ]
            if budget
            else [],
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
) -> tuple[int, dict]:
    impl_dir = impl if impl is not None else root / "impl"
    impl_dir.mkdir(exist_ok=True)
    # Start from the real environment (Windows needs SystemRoot et al.), then
    # strip the five hook vars so a dev machine's own injection cannot leak a
    # green "process" source into a case that never set them.
    base_env = {k: v for k, v in os.environ.items() if k not in _ENV_VARS}
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


def test_missing_settings_file_is_not_armed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    code, out = _run(root)
    assert code == 1
    assert out["checks"]["hooks"]["settings_readable"] is False
    assert any("missing or unreadable" in r for r in out["reasons"])


def test_missing_guard_or_budget_each_fail(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root, guard=False)
    code, out = _run(root)
    assert code == 1 and any("guard" in r for r in out["reasons"])
    _arm(root, budget=False)
    code, out = _run(root)
    assert code == 1 and any("budget_stop" in r for r in out["reasons"])


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


def test_an_epic_branch_that_is_also_protected_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _arm(root)
    code, out = _run(root, "--protected-branch", "ultracode/epic-7")
    assert code == 1
    assert out["checks"]["branch"]["ok"] is False


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
