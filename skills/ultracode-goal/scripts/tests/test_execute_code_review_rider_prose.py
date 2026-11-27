#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for what the code review may do with the context it is handed.

Execute's step 1 surfaces two things into a story's review context: an
Operator notes entry from `.decision-log.md` that names the story, and the
Epic's class ledger, the defect classes earlier reviews caught. Both are there
to make the reviewers look harder. Nothing told `bmad-code-review` so, and a
note such as "the operator accepts the retry delay" reads as easily as leave to
drop a finding, or to file it lower. `bmad-code-review` files each finding at a
severity, and a story it leaves with no `high` or `medium` finding is one it
lets close, so a lowered severity is a finding the story no longer answers.

`references/execute.md` step 3 now ends on a sentence of its own, after the
pointer to the rule that no test review runs in the conductor's context: "Tell
`bmad-code-review` that each Operator notes entry and the class ledger that
step 1 hands the review can add a finding and never waive one or lower its
severity."

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the step without the sentence, one-clause mutants it must reject, and
a twin per clause of the predicate that only that clause rejects.
Step 3 is also pinned whole by `test_gate_own_context_prose.py`, which now
carries this sentence; that pin is checked here to reject the step without it.
The sentence's antecedents are checked against step 1, and its facts about the
review against the tracked reference skill under `skf-skills/bmad-method-bmm/`
(the installed skills under `.claude/skills/` are not tracked, so no test reads
them). That reference says how the review files and closes on severities; it
does not say how the review weighs context it is handed, so that is not
checked. Stated limit: this is a presence proof over prose. It shows the
instruction is in the file, not that a conductor passes it on or that the
review obeys it.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
EXECUTE = (_SKILL_ROOT / "references" / "execute.md").read_text(encoding="utf-8")

_RIDER = (
    "Tell `bmad-code-review` that each Operator notes entry and the class ledger that step 1 hands the review can "
    "add a finding and never waive one or lower its severity."
)
_POINTER = (
    "Run the test review in an agent you start for it, never a fork, as `references/gate.md`'s \"No test review and "
    "no NFR assessment is written in your own context\" says."
)
_STEP3_START = "3. **Production profile only:** `bmad-testarch-test-review`, then `bmad-code-review`."


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _step(text: str, opener: str, next_opener: str) -> str:
    start = text.index(opener)
    return text[start + 1 : text.index(next_opener, start)]


def _step1(text: str = EXECUTE) -> str:
    return _step(text, "\n1. `ucg-create-story`", "\n2. ")


def _step3(text: str = EXECUTE) -> str:
    return _step(text, "\n3. **Production profile only:**", "\n4. ")


def _replaced(text: str, old: str, new: str) -> str:
    mutant = text.replace(old, new, 1)
    assert mutant != text, "the mutant must actually change the text"
    return mutant


# --- step 3 ends on the sentence --------------------------------------------------

_STEP4 = "\n4. **Commit at green**"


def _ends_on_the_rider(text: str) -> bool:
    step = _flat(_step3(text)).strip()
    return step.startswith(_STEP3_START) and step.endswith(_POINTER + " " + _RIDER)


def _step3_ends_on_the_rider(text: str = EXECUTE) -> bool:
    """Step 3, the step that runs `bmad-code-review`, ends on the sentence,
    directly after the pointer it follows, and no other step holds it: nothing
    after it can take it back, and no other step's review is told it."""
    return _ends_on_the_rider(text) and _flat(text).count(_RIDER) == 1


def test_step_3_tells_the_code_review_the_context_never_waives_a_finding():
    assert _step3_ends_on_the_rider()


def test_rider_predicate_rejects_the_step_without_it():
    assert not _step3_ends_on_the_rider(_replaced(EXECUTE, " " + _RIDER, ""))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("can add a finding and never waive one or lower its severity",
                     "can add or waive a finding", id="may-waive"),
        pytest.param(" or lower its severity", "", id="may-lower-the-severity"),
        pytest.param("never waive one", "may waive one", id="waiver-allowed"),
        pytest.param("can add a finding and never", "can never", id="may-not-add"),
        pytest.param("Tell `bmad-code-review`", "Tell `bmad-testarch-test-review`", id="tells-the-test-reviewer"),
        pytest.param("each Operator notes entry and the class ledger", "each Operator notes entry",
                     id="class-ledger-left-out"),
        pytest.param("each Operator notes entry and the class ledger", "the class ledger",
                     id="operator-notes-left-out"),
        pytest.param("each Operator notes entry", "the first Operator notes entry", id="one-entry-only"),
        pytest.param("that step 1 hands the review", "that step 2 hands the review", id="wrong-step"),
        pytest.param(_RIDER, _RIDER + " An Operator notes entry may waive a finding it names.", id="taken-back"),
    ],
)
def test_rider_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _step3_ends_on_the_rider(_replaced(EXECUTE, old, new))


def test_rider_predicate_rejects_the_sentence_moved():
    without = _replaced(EXECUTE, " " + _RIDER, "")
    # Ahead of the pointer, in step 3.
    before = _replaced(without, _POINTER, _RIDER + " " + _POINTER)
    assert not _step3_ends_on_the_rider(before)
    # Into step 4, the commit step.
    assert without.count(_STEP4) == 1
    into_4 = _replaced(without, _STEP4, _STEP4 + " " + _RIDER)
    assert not _step3_ends_on_the_rider(into_4)


def test_rider_predicate_rejects_a_second_copy_in_step_4():
    """Twin for the clause that no other step holds the sentence: step 3 keeps
    it intact, so only that clause can reject the copy added to step 4."""
    assert EXECUTE.count(_STEP4) == 1
    copied = _replaced(EXECUTE, _STEP4, _STEP4 + " " + _RIDER)
    assert _ends_on_the_rider(copied)
    assert not _step3_ends_on_the_rider(copied)


# --- the whole-step pin carries the sentence --------------------------------------


def _own_context_pins():
    """test_gate_own_context_prose.py, loaded under its own name, for its
    whole-step pin of step 3."""
    path = Path(__file__).with_name("test_gate_own_context_prose.py")
    spec = importlib.util.spec_from_file_location("ucg_own_context_prose_pins", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_the_whole_step_pin_holds_with_the_sentence_and_rejects_the_step_without_it():
    pins = _own_context_pins()
    assert pins._CODE_REVIEW_RIDER == _RIDER
    step = _step3()
    assert pins._step3_points_at_the_rule(step)
    assert not pins._step3_points_at_the_rule(_replaced(step, " " + _RIDER, ""))


# --- step 1 hands the review both things the sentence names -----------------------

_OPERATOR_NOTES = (
    "check the run's `.decision-log.md` for an **Operator notes** entry naming this story (a pre-launch hint like "
    "\"watch the auth flow in story 3\") and surface that note into the `ucg-dev-story` / review context for this story"
)
_CLASS_LEDGER = "Read `{workflow.implementation_artifacts}/.class-ledger-<epic_id>.md` the same way when it exists"
_SAME_CONTEXT = "and surface it into the same context"


def _step1_hands_the_review_both(step: str) -> bool:
    """Step 1 surfaces an Operator notes entry naming the story into the review
    context, and then the class ledger into the same context, so "each
    Operator notes entry and the class ledger that step 1 hands the review"
    names what step 1 does hand it."""
    flat = _flat(step)
    if _OPERATOR_NOTES not in flat or _CLASS_LEDGER not in flat:
        return False
    ledger = flat.index(_CLASS_LEDGER)
    return flat.index(_OPERATOR_NOTES) < ledger and flat.find(_SAME_CONTEXT, ledger) != -1


def test_step_1_hands_the_review_the_operator_notes_and_the_class_ledger():
    assert _step1_hands_the_review_both(_step1())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(" / review context for this story", " context for this story", id="notes-to-the-dev-step-only"),
        pytest.param(_CLASS_LEDGER, "Ignore the class ledger", id="ledger-not-read"),
        pytest.param(_SAME_CONTEXT, "and keep it to yourself", id="ledger-not-surfaced"),
    ],
)
def test_step_1_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _step1_hands_the_review_both(_replaced(_flat(_step1()), old, new))


# --- what a severity decides in the review ----------------------------------------


def _repo_bmm_reference() -> Path:
    """The tracked reference skill for the BMAD Method version this module targets."""
    group = _REPO / "skf-skills" / "bmad-method-bmm"
    active = group / "active"
    version = active.resolve().name if active.is_dir() else active.read_text(encoding="utf-8").strip()
    return group / version / "bmad-method-bmm"


def test_the_review_files_findings_at_a_severity_and_closes_on_it():
    """The facts "lower its severity" rests on, from the tracked BMAD Method
    reference: each finding has a severity, and the review leaves a story open
    while a `high` or `medium` one remains."""
    skill = _flat((_repo_bmm_reference() / "SKILL.md").read_text(encoding="utf-8"))
    assert "`bmad-code-review` uses `decision_needed`, `patch`, `defer` with severity `high`/`medium`/`low`." in skill
    assert (
        "`bmad-code-review` sets the story `done` only when every decision-needed and patch finding is resolved and "
        "no high/medium remains; otherwise `in-progress`."
    ) in skill
