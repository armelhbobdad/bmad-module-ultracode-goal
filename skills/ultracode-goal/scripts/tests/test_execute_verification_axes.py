"""Execute steps 0/2/4/5: what makes a green sweep actually mean something.

Static prose-contract assertions over `references/execute.md`. Every clause here
was written against a run that shipped a false green in the field, and each is
pinned by a NAMED check so the anti-vacuous twin can assert that *every* one of
them reds against the verbatim pre-edit file, not merely that something did.

The twin is `fixtures/execute_pre_verification_axes.md`, a byte copy of the file
as it stood before these clauses landed - the same shape
`test_execute_baseline_marker.py` uses for step 0.

What each group defends, in the words of the run that found it:

  - LANGUAGE: `turbo run test --force` reported "8 successful, 8 total" with
    6540 tests passing and zero of those tasks was the Rust crate the story was
    almost entirely written in. A task count is not a coverage claim.
  - DECLARED GATE SET: `test:storybook` is a sibling turbo task rather than a
    dependency of `test`, so two stories sat RED since the baseline commit with
    every intervening P0 sweep green.
  - CACHE: `bun run test` returned "Cached: 8 cached, >>> FULL TURBO" in 719ms
    immediately after a commit, replaying an answer taken while the story's new
    files were still untracked. Committing changes tracking state, not bytes.
  - BUFFERING: `cargo test 2>&1 | tail -50` emitted nothing for 45 minutes and a
    healthy build was killed on the suspicion it had hung.
  - HOOK REJECTION: a commit rejected by lefthook leaves HEAD unmoved, so the
    tests-ran marker still matches character for character and the guard waves
    the retry through carrying evidence collected before the fix.
  - SCRATCH: /tmp was refused by the permission layer, so a generator landed in
    an untracked repo-root directory that only explicit staging kept out of the
    commit.
  - LARGE LOG: the decision log reached 288 KB, and Write/Edit both refuse a file
    that has not been Read, so both sanctioned paths closed at once.

Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_PRE_EDIT = _FIXTURES / "execute_pre_verification_axes.md"


def _text(source: Path | None = None) -> str:
    return (source or _EXECUTE).read_text(encoding="utf-8")


def _step(number: int, text: str) -> str:
    """Slice one numbered bullet out of the sequential-spine loop.

    THE LAST STEP IS BOUNDED AT ITS OWN BLANK LINE, not at EOF. There is no
    `6. ` marker to stop at, so returning `text[start:]` handed step 5 the whole
    remaining 21 KB - the work bound, the /goal condition, the escalation
    sidecar, the entire `--parallel` fan-out and the heartbeat. Every "step 5
    says X" check was then really a "somewhere in the back half of the file says
    X" check, and prose relocated out of step 5 into any later section kept them
    green. `test_execute_doc_step4_staging._step5` already bounds this way.
    """
    start = text.index(f"\n{number}. ")
    for following in range(number + 1, 7):
        marker = f"\n{following}. "
        at = text.find(marker, start)
        if at != -1:
            return text[start:at]
    end = text.find("\n\n", start)
    return text[start:] if end == -1 else text[start:end]


# One named check per bound property. Kept deliberately literal: these are the
# words a reader has to find, and a looser regex would pass on a paraphrase that
# drops the actionable half.
_CHECKS = {
    # --- step 2: the three axes -------------------------------------------
    "step2 names LANGUAGE as an axis of breadth": lambda t: bool(
        re.search(r"axes.*language|language.*axis", _step(2, t), re.I | re.S)
    ),
    "step2 says a task count is not a coverage claim": lambda t: bool(
        re.search(r"task count is not a coverage claim", _step(2, t), re.I)
    ),
    "step2 names a per-language suite to run explicitly": lambda t: bool(
        re.search(r"cargo test|go test|pytest", _step(2, t))
    ),
    "step2 distinguishes the declared gate set from the default task": lambda t: bool(
        re.search(r"declared gate set.*not its default task", _step(2, t), re.I)
    ),
    "step2 names a sibling task that the default excludes": lambda t: bool(
        re.search(r"test:storybook|test:coverage|coverage-ratchet", _step(2, t))
    ),
    "step2 requires the sweep be cache-defeating": lambda t: bool(
        re.search(r"cache-defeating", _step(2, t), re.I)
    ),
    "step2 requires the evidence to state whether the run was cached": lambda t: bool(
        re.search(r"whether the run was cached", _step(2, t), re.I)
    ),
    "step2 forbids piping a long command through a filter": lambda t: bool(
        re.search(r"never pipe a long command through a filter", _step(2, t), re.I)
    ),
    "step2 names the redirect-then-read remedy": lambda t: bool(
        re.search(r">\s*<log>\s*2>&1|redirect to a file", _step(2, t), re.I)
    ),
    "step2 warns that commit hooks are unreachable from this sweep": lambda t: bool(
        re.search(r"commit hooks carries gates this sweep structurally cannot see", _step(2, t), re.I)
    ),
    "step2 names the Write tool for the tests-ran marker": lambda t: bool(
        re.search(r"Write that marker with the Write tool", _step(2, t), re.I)
    ),
    "step2 attributes the printf refusal to the harness, not the guard": lambda t: bool(
        re.search(r"guard permits it", _step(2, t), re.I)
    ),
    # --- step 5: the re-verify --------------------------------------------
    "step5 requires the re-verify be cache-defeating": lambda t: bool(
        re.search(r"run it cache-defeating", _step(5, t), re.I)
    ),
    "step5 explains why the cache key is unchanged by a commit": lambda t: bool(
        re.search(r"tracking state.*not one of its bytes", _step(5, t), re.I | re.S)
    ),
    # --- step 4: the hook-rejected commit ----------------------------------
    "step4 names a rejection that is not the guard's": lambda t: bool(
        re.search(r"rejected by something that is NOT the guard", _step(4, t))
    ),
    "step4 requires a FRESH marker after a hook rejection": lambda t: bool(
        re.search(r"write a \*\*fresh\*\* `\.tests-ran", _step(4, t), re.I)
    ),
    "step4 says the freshness clause cannot see this case": lambda t: bool(
        re.search(r"keys on the BASELINE, not on the code state", _step(4, t))
    ),
    # --- step 4: the unreadably large decision log -------------------------
    "step4 rules the too-large-to-Read decision log": lambda t: bool(
        re.search(r"too large to Read affordably", _step(4, t), re.I)
    ),
    "step4 names the slice-then-cat remedy": lambda t: bool(
        re.search(r"dlog-slice-<story_id>-<n>\.md", _step(4, t))
    ),
    "step4 makes the slice name unique per APPEND, not per story": lambda t: bool(
        # A per-story name walks back into the deadlock it escapes: a story's
        # second entry finds the slice already on disk, so Write wants a Read.
        re.search(r"unique per append, not per story", _step(4, t), re.I)
    ),
    "step4 explains why that Bash call clears the guard": lambda t: bool(
        re.search(r"leading token is `cat`", _step(4, t))
    ),
    # --- step 0: scratch build space ---------------------------------------
    "step0 names a scratch build directory": lambda t: bool(
        re.search(r"\.scratch-<story_id>/", _step(0, t))
    ),
    "step0 rules out /tmp with its reason": lambda t: bool(
        re.search(r"Not `/tmp`", _step(0, t))
    ),
    "step0 requires the scratch dir be removed before the commit": lambda t: bool(
        re.search(r"remove the directory before the step-4 commit", _step(0, t), re.I)
    ),
}


def _unmet(text: str) -> list[str]:
    return sorted(name for name, check in _CHECKS.items() if not check(text))


def test_execute_pins_every_verification_axis():
    assert _unmet(_text()) == []


def test_the_pre_edit_file_fails_every_one_of_them():
    """Twin: the verbatim pre-edit file must red on ALL of the checks above.

    Not "at least one" - if any check already passed before these clauses landed,
    that check is pinning something it did not introduce and proves nothing about
    this change.
    """
    pre_edit = _text(_PRE_EDIT)
    assert sorted(_unmet(pre_edit)) == sorted(_CHECKS), (
        "these checks already pass on the pre-edit file, so they are vacuous: "
        f"{sorted(set(_CHECKS) - set(_unmet(pre_edit)))}"
    )


def test_the_pre_edit_fixture_is_a_real_snapshot():
    """The twin must red for the RIGHT reason: an emptied file proves nothing."""
    pre_edit = _text(_PRE_EDIT)
    live = _text()
    for anchor in (
        "# Stage 4 — Execute",
        "## Default — Sequential `/goal` spine",
        "### The per-invocation work bound (`--max-stories N`)",
        "### Escalation sidecar",
        "## Run-status heartbeat",
    ):
        assert anchor in pre_edit, f"the fixture is not a real execute.md: {anchor!r}"
        assert anchor in live, f"control: the live file still carries {anchor!r}"
    # NOT a line-level subset check. These clauses EXTEND existing sentences, and
    # each numbered step is one long line, so every touched step is a changed
    # line by construction. What must survive is the meaning, so the twin pins
    # the load-bearing sentences of the steps this change reaches into: if any of
    # them were dropped while widening the step, the checks above would still
    # pass and the file would be quietly worse.
    for survivor in (
        "copied, never re-derived",                      # step 2's marker rule
        "denies a commit whose staged index is empty",                     # step 4's guard denial
        "stage this story's source + test paths explicitly",
        "a story's **new** files are still untracked at step 2",  # step 5's reason
        "never overwrite it",                            # step 0's resume rule
        "scope that test run wide enough to catch cross-package regressions",
    ):
        assert survivor in pre_edit, f"the fixture is not a real execute.md: {survivor!r}"
        assert survivor in live, f"widening the step dropped: {survivor!r}"
    # Every numbered step of the spine is still there, and nothing was renumbered.
    for number in range(0, 6):
        assert f"\n{number}. " in live, f"step {number} vanished"
    assert len(live) > len(pre_edit)


def test_step5_still_inherits_step2s_full_scope():
    """Widening step 2 is worthless if step 5 re-runs something narrower."""
    step5 = _step(5, _text())
    assert re.search(r"same wide scope as step 2", step5, re.I)
    assert re.search(r"all three axes", step5, re.I), (
        "step 5 must name the axes it inherits, or a reader re-runs only the "
        "package-breadth half"
    )
    assert re.search(r"declared gate set", step5, re.I)


def test_the_checks_are_anchored_to_their_step_not_to_the_file():
    """Locality twin: RELOCATED prose must red, not just deleted prose.

    The anti-vacuous twin above proves these words are new. It cannot prove they
    are in the right STEP - and a check that merely scans the file would stay
    green while step 5 lost its cache-defeat instruction to some later section,
    which is the exact false green (`>>> FULL TURBO` in 719ms right after a
    commit) the clause was written against.

    So: cut step 5's two sentences out of step 5, paste them verbatim into a
    later section, and require the step-5 checks to red while a step-2 control
    stays green.
    """
    live = _text()
    step5 = _step(5, live)
    moved = "**Run it cache-defeating.**"
    assert moved in step5, "the sentence under test is not in step 5"

    cut_at = step5.index(moved)
    relocated_body, relocated_tail = step5[:cut_at].rstrip(), step5[cut_at:]
    mutant = live.replace(step5, relocated_body, 1).replace(
        "## Run-status heartbeat", f"## Run-status heartbeat\n\n{relocated_tail}\n", 1
    )

    unmet = _unmet(mutant)
    step5_checks = {name for name in _CHECKS if name.startswith("step5 ")}
    assert set(unmet) == step5_checks, (
        "relocating step 5's prose into a later section must red exactly the "
        f"step-5 checks and nothing else; got {unmet}"
    )
    # The control: step 2's checks are untouched by a step-5 relocation, so the
    # twin is isolating locality rather than just breaking the document.
    assert not any(name.startswith("step2 ") for name in unmet)
