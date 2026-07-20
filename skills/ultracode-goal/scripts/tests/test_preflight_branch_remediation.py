"""Contract: step 2 owns the `git_branch` remediation, and step 4 stays unconditional.

`preflight_check.py` emits `git_branch` as a remediable blocker that counts toward
`budget`. Step 4's first AND-clause requires `budget == 0`. So the clearing action
has to live in step 2's enumerated remediation list: step 5, the only other place
the doc creates the Epic branch, is headed "only when the gate passes" and can
never clear a blocker the gate is waiting on.

Two poles, because the wrong fix for this is attractive and would pass a naive
presence check:
  - step 2 names the branch remediation (this file), and
  - step 4's `budget == 0` clause gains NO carve-out for it (a carve-out would let
    the run launch while still on a protected branch, breaking execute.md's
    Epic-branch precondition and the branch-deletion rollback).

Every assertion carries an anti-vacuous twin, matching the house pattern in
test_preflight_step2_foldin.py.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_PREFLIGHT = (
    Path(__file__).resolve().parents[1] / ".." / "references" / "preflight.md"
).resolve()


def _text() -> str:
    return _PREFLIGHT.read_text(encoding="utf-8")


def _section(title_prefix: str, next_prefix: str) -> str:
    text = _text()
    start = text.index(title_prefix)
    end = text.index(next_prefix, start)
    return text[start:end]


def _step2() -> str:
    return _section("## 2. Auto-remediation pass", "## 3. ")


def _step4() -> str:
    return _section("## 4. Hard gate", "## 5. ")


def _step5() -> str:
    return _section("## 5. Arm the environment", "### Launch briefing")


# --- the blocker the script actually emits ----------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


@pytest.fixture(autouse=True)
def _hermetic_git_env(monkeypatch):
    """Scrub inherited GIT_* so git runs against the temp repo, not the host repo."""
    for var in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/")


def _load_preflight():
    script = Path(__file__).resolve().parents[1] / "preflight_check.py"
    spec = importlib.util.spec_from_file_location("preflight_check_premise", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo_on(tmp_path: Path, branch: str) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    _git(root, "checkout", "-q", "-b", branch)
    return root


def _report(root: Path, monkeypatch):
    pf = _load_preflight()
    monkeypatch.setattr(pf, "_claude_version", lambda: "9.9.9", raising=False)
    return pf.build_report(
        project_root=root,
        epic="1",
        tea_config=root / "_bmad" / "tea" / "config.yaml",
        impl_artifacts=root / "_bmad-output" / "implementation-artifacts",
        protected_branches=["main", "master"],
    )


def test_git_branch_is_remediable_and_counts_toward_budget(tmp_path, monkeypatch):
    """The premise, exercised rather than grepped.

    An earlier version of this test scanned the script's SOURCE for the strings
    `"remediable": True` and `len(blockers)`, which a neighbouring blocker's
    literal satisfied just as well — it could not have failed. This runs the real
    report builder on a real repo and reads the emitted blocker.
    """
    report = _report(_repo_on(tmp_path, "main"), monkeypatch)

    entries = [b for b in report["blockers"] if b["id"] == "git_branch"]
    assert len(entries) == 1, "being on a protected branch must emit git_branch"
    assert entries[0]["remediable"] is True, (
        "git_branch must stay remediable: step 2's bullet is premised on it"
    )
    assert report["budget"] == len(report["blockers"]), (
        "budget must count every blocker, git_branch included — the whole "
        "circularity turns on this being true"
    )


def test_git_branch_absent_off_a_protected_branch(tmp_path, monkeypatch):
    """The discriminating pole: the same repo on an epic branch emits no git_branch.

    Without this, the assertion above would pass against a build_report that
    emitted git_branch unconditionally.
    """
    report = _report(_repo_on(tmp_path, "ultracode/epic-1"), monkeypatch)

    assert not [b for b in report["blockers"] if b["id"] == "git_branch"]


# --- step 2 owns the remediation --------------------------------------------

def _names_branch_remediation(block: str) -> bool:
    """True only for prose that instructs CREATING the epic branch in step 2."""
    bullet = re.search(r"^- \*\*On a protected branch\*\*.*$", block, re.M)
    if not bullet:
        return False
    line = bullet.group(0)
    creates = re.search(r"\bcreate\b", line, re.I)
    names_prefix = "{workflow.epic_branch_prefix}" in line
    rechecks = re.search(r"re-?run the check", line, re.I)
    return bool(creates and names_prefix and rechecks)


def test_step2_enumerates_the_branch_remediation():
    assert _names_branch_remediation(_step2()), (
        "step 2's remediation list must name creating the Epic branch: "
        "git_branch is remediable and budget-counted, so nothing downstream "
        "of the `budget == 0` gate can be what clears it"
    )


def test_step2_branch_bullet_anti_vacuous():
    """A bullet that mentions the blocker without instructing the fix must fail."""
    hollow = "- **On a protected branch** (`git_branch`): this is a blocker.\n"
    assert not _names_branch_remediation(hollow)


def test_branch_precedes_the_committing_remediation():
    """`git checkout -b` carries the tree across; a remediation commit made on a
    protected branch escapes the branch-deletion rollback."""
    block = _step2()
    assert re.search(r"[Bb]ranch \*\*before\*\* the `git_clean` clear", block), (
        "the bullet must state that branching precedes the committing remediation"
    )
    ordering = re.search(r"\*\*Ordering\.\*\*.*$", block, re.M)
    assert ordering, "the ordering paragraph must survive"
    assert "git_branch" in ordering.group(0), (
        "the ordering paragraph must no longer claim framework -> ci is the only "
        "load-bearing chain"
    )


def test_step2_states_the_pre_gate_git_mutation():
    """Genuine behaviour change: git state now moves before the hard gate, so a
    run blocked at step 4 is left on a branch it never briefed the operator on."""
    assert re.search(
        r"ahead of the hard gate|before the hard gate", _step2(), re.I
    ), "step 2 must surface that it mutates git state ahead of the gate"


# --- step 4 must NOT gain a carve-out ---------------------------------------


def test_step4_budget_clause_has_no_git_branch_carve_out():
    """The rejected wrong fix. Excluding git_branch from `budget == 0` would let
    the run launch on a protected branch, which execute.md forbids as a
    precondition and which the branch-deletion rollback depends on."""
    s4 = _step4()
    assert re.search(r"`budget == 0`", s4), "the first AND-clause must survive"
    assert not re.search(
        r"budget == 0[^\n]*(except|excluding|other than|apart from)", s4, re.I
    ), "step 4's budget clause must stay unconditional"
    assert not re.search(r"git_branch", s4), (
        "step 4 must not name git_branch at all: the blocker clears in step 2, "
        "and naming it here is how a carve-out gets introduced"
    )


def test_step4_carve_out_twin():
    """Anti-vacuous: the mutant the assertion above exists to catch must trip it."""
    mutant = "- post-remediation script `budget == 0` excluding the `git_branch` blocker"
    assert re.search(
        r"budget == 0[^\n]*(except|excluding|other than|apart from)", mutant, re.I
    )


# --- step 5 re-asserts rather than solely creating --------------------------


def test_step5_reasserts_the_branch_and_gives_the_miss_a_failure_path():
    s5 = _step5()
    assert re.search(r"Assert you are on", s5), (
        "step 5's Epic-branch bullet must assert rather than unconditionally create"
    )
    assert re.search(r"`budget == 0` does \*\*not\*\* by itself put you on it", s5), (
        "step 5 must state that clearing the gate does not imply being on the "
        "Epic branch: git_branch fires on protected branches only"
    )
    # And the off-branch case must be RESOLVED here, not bounced to a step-2
    # bullet that cannot fire for it. An earlier draft said "return to step 2",
    # which livelocked: step 2's only branch bullet is conditioned on git_branch,
    # the step-1 re-run returns the same budget, and step 4 passes again.
    assert not re.search(r"return to step 2", s5, re.I), (
        "step 5 must not route the off-branch case back to step 2: that bullet "
        "is conditioned on git_branch, which by definition did not fire"
    )
    assert re.search(r"check out the base", s5, re.I), (
        "step 5 must name the resolving action for a run started off-branch"
    )


def test_step5_keeps_the_dirty_tree_check():
    """`git_clean` is measured at the END of step 2, and step 3 writes its scan
    sidecar and appends to the decision log afterwards, so `budget == 0` does not
    imply a clean tree here. The check must stay unconditional."""
    s5 = _step5()
    assert re.search(r"tree is dirty|`git_clean: false`", s5), (
        "step 5 must still require resolving a dirty tree before branching"
    )
    assert not re.search(
        r"tree is already clean by this point", s5, re.I
    ), "that invariant is false: git_clean counts untracked files"


@pytest.mark.parametrize(
    "phrase",
    [
        "denied outright by the PreToolUse guard",
        "step 5 never runs because the gate never passes",
    ],
)
def test_retired_claims_stay_out(phrase: str):
    """Two claims that were wrong and must not come back.

    The guard is DISARMED during step 2 (the stale-hook pre-arming paragraph
    mandates it before any remediation commit), so it cannot deny a remediation
    commit. And the generic "clear each remediable blocker" instruction already
    covers git_branch, so the omission was a gap in the enumerated list, not a
    structural deadlock.
    """
    assert phrase not in _text(), f"retired claim reintroduced: {phrase}"
