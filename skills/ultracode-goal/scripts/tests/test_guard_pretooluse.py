#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Exercise the PreToolUse guard's deny/allow paths via the real stdin/stdout
hook contract (run the hook as a subprocess, feed JSON on stdin)."""

import importlib.util
import json
import os
import re
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
    '    for segment in re.split(r"&&|\\|\\||;|\\|", command):\n'
    "        verbs |= _segment_write_verbs(segment, depth)"
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
