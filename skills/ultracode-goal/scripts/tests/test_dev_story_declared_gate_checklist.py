#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for how `ucg-dev-story`'s definition of done counts a red declared gate.

`ucg-dev-story` runs the declared gates a run hands it (`{{declared_gates}}`)
and never halts for one: its "Declared Gates" section says one it cannot get
green is reported and left to the run's sweep, and that the **Regression
Prevention**, **Code Quality**, **Quality Gates Passed** and **No HALT
Conditions** items of `checklist.md` count a declared gate still red as
reported, never failed. In 8.1.1 those four items said no such thing: "ALL
existing tests pass", "All quality checks and validations completed
successfully", "No blocking issues", so a run of the checklist (step 9's
definition-of-done validation, step 10's checklist) read a red declared gate as
a failed definition of done, against the section that cites it.

Now:

- `checklist.md`: the first three items end with "; a gate in
  `{{declared_gates}}` still red counts as reported, never failed", and **No
  HALT Conditions** with "; a gate in `{{declared_gates}}` still red is no HALT
  condition". No other item names a declared gate.
- `SKILL.md`: the definition-of-done list step 9 validates ends on a note, "A
  gate the run handed this workflow, still red after this step, counts as
  reported, never failed." It covers only a gate the run handed the workflow,
  not the regression suite, and nothing on a run that handed it none. It does
  not say "a declared gate", because no workflow line but step 9's own action
  may name the declared gates (`test_execute_dev_step_declared_gates_prose.py`),
  and that rule still holds.
- `LICENSE.md` lists the change among those from upstream.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text without the change, one-clause mutants it must reject, and a
twin per clause of the predicate that only that clause rejects. The items the
section names are checked against the items that carry the clause, and the
halt-free bar of the sibling test is run on the live skill and on a note worded
as a halt. Stated limit: this is a presence proof over prose. It shows the
wording is in the files, not that an executor counts a red gate as reported.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_SKILLS = Path(__file__).resolve().parents[3]
_DEV = _SKILLS / "ucg-dev-story"
SKILL = (_DEV / "SKILL.md").read_text(encoding="utf-8")
CHECKLIST = (_DEV / "checklist.md").read_text(encoding="utf-8")
LICENSE = (_DEV / "LICENSE.md").read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _replaced(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    mutant = text.replace(old, new, 1)
    assert mutant != text, "the mutant must actually change the text"
    return mutant


# --- checklist.md: four items count a red declared gate as reported ---------------

_RED_GATE = "a gate in `{{declared_gates}}` still red"
_REPORTED = f"; {_RED_GATE} counts as reported, never failed"
_NO_HALT = f"; {_RED_GATE} is no HALT condition"
# A line that names the declared gates, as a phrase or as the input.
_DECLARED_GATE = re.compile(r"declared[ _]gates?", re.I)
_ITEM_CLAUSES = {
    "Regression Prevention": _REPORTED,
    "Code Quality": _REPORTED,
    "Quality Gates Passed": _REPORTED,
    "No HALT Conditions": _NO_HALT,
}
# The four items as 8.1.1 wrote them, before the clauses.
_PRE_EDIT_ITEMS = {
    "Regression Prevention": "- [ ] **Regression Prevention:** ALL existing tests pass (no regressions introduced)",
    "Code Quality": "- [ ] **Code Quality:** Linting and static checks pass when configured in project",
    "Quality Gates Passed": (
        "- [ ] **Quality Gates Passed:** All quality checks and validations completed successfully"
    ),
    "No HALT Conditions": "- [ ] **No HALT Conditions:** No blocking issues or incomplete work remaining",
}
_ONLY_THOSE = "only those four items name a declared gate"


def _item_line(checklist: str, name: str) -> str:
    return next((line for line in checklist.splitlines() if line.startswith(f"- [ ] **{name}:** ")), "")


def _checklist_counts_a_red_gate_reported(checklist: str) -> list[str]:
    """The items that lack their clause at the end of their line, by name, and
    `_ONLY_THOSE` when a line other than theirs names a declared gate."""
    missing = [name for name, clause in _ITEM_CLAUSES.items() if not _item_line(checklist, name).endswith(clause)]
    own = {_item_line(checklist, name) for name in _ITEM_CLAUSES}
    if any(_DECLARED_GATE.search(line) and line not in own for line in checklist.splitlines()):
        missing.append(_ONLY_THOSE)
    return missing


def _checklist_pre(checklist: str = CHECKLIST) -> str:
    return checklist.replace(_REPORTED, "").replace(_NO_HALT, "")


def test_the_four_items_count_a_red_declared_gate_as_reported():
    assert _checklist_counts_a_red_gate_reported(CHECKLIST) == []


def test_checklist_predicate_rejects_the_pre_edit_checklist():
    pre = _checklist_pre()
    # The change only appended the clauses: each item's own text is 8.1.1's.
    assert [_item_line(pre, name) for name in _ITEM_CLAUSES] == list(_PRE_EDIT_ITEMS.values())
    assert _checklist_counts_a_red_gate_reported(pre) == list(_ITEM_CLAUSES)


@pytest.mark.parametrize("name", list(_ITEM_CLAUSES))
def test_checklist_predicate_rejects_one_clause_dropped(name):
    line = _item_line(CHECKLIST, name)
    mutant = _replaced(CHECKLIST, line, line.removesuffix(_ITEM_CLAUSES[name]))
    assert _checklist_counts_a_red_gate_reported(mutant) == [name]


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        pytest.param("Quality Gates Passed", "counts as reported, never failed", "counts as failed",
                     id="counted-as-failed"),
        pytest.param("Regression Prevention", "counts as reported, never failed", "counts as reported, or failed",
                     id="reported-or-failed"),
        pytest.param("No HALT Conditions", "is no HALT condition", "is a HALT condition", id="a-halt-condition"),
        pytest.param("Code Quality", _RED_GATE, "a gate still red", id="any-red-gate"),
        pytest.param("Code Quality", _RED_GATE, "a gate in `{{declared_gates}}`", id="red-unsaid"),
        pytest.param("No HALT Conditions", _RED_GATE, "a red test", id="a-red-test-no-halt"),
    ],
)
def test_checklist_predicate_rejects_a_one_clause_mutant(name, old, new):
    line = _item_line(CHECKLIST, name)
    mutant = _replaced(CHECKLIST, line, _replaced(line, old, new))
    assert _checklist_counts_a_red_gate_reported(mutant) == [name]


def test_checklist_predicate_rejects_a_clause_moved_to_another_item():
    line = _item_line(CHECKLIST, "Code Quality")
    other = _item_line(CHECKLIST, "Test Framework Compliance")
    mutant = _replaced(CHECKLIST, line, line.removesuffix(_REPORTED))
    mutant = _replaced(mutant, other, other + _REPORTED)
    assert _checklist_counts_a_red_gate_reported(mutant) == ["Code Quality", _ONLY_THOSE]


# --- the section names the items that carry the clause ----------------------------

_SECTION_CLAIM = re.compile(r"whose ((?:\*\*[^*]+\*\*(?:, | and ))+\*\*[^*]+\*\*) items count a declared gate still red")


def _section(skill: str) -> str:
    start = skill.index("\n## Declared Gates\n")
    return skill[start : skill.index("\n## ", start + 1)]


def _section_and_checklist_agree(skill: str, checklist: str) -> bool:
    """The items the "Declared Gates" section says count a red declared gate as
    reported are the items of `checklist.md` whose line carries the clause."""
    match = _SECTION_CLAIM.search(_flat(_section(skill)))
    if match is None:
        return False
    named = re.findall(r"\*\*([^*]+)\*\*", match.group(1))
    carrying = [
        name
        for name in re.findall(r"^- \[ \] \*\*([^*]+):\*\*", checklist, re.MULTILINE)
        if _RED_GATE in _item_line(checklist, name)
    ]
    return sorted(named) == sorted(carrying) and len(named) == len(set(named))


def test_the_section_names_the_items_that_carry_the_clause():
    assert _section_and_checklist_agree(SKILL, CHECKLIST)


def test_agreement_predicate_rejects_the_pre_edit_checklist():
    assert not _section_and_checklist_agree(SKILL, _checklist_pre())


def test_agreement_predicate_rejects_a_section_that_names_another_item():
    mutant = _replaced(SKILL, "**Code Quality**, **Quality Gates Passed**",
                       "**Code Quality**, **Test Coverage**, **Quality Gates Passed**")
    assert not _section_and_checklist_agree(mutant, CHECKLIST)


def test_agreement_predicate_rejects_a_checklist_item_the_section_does_not_name():
    other = _item_line(CHECKLIST, "Test Framework Compliance")
    assert not _section_and_checklist_agree(SKILL, _replaced(CHECKLIST, other, other + _REPORTED))


# --- SKILL.md: the definition-of-done list ends on the note -----------------------

_NOTE = "A gate the run handed this workflow, still red after this step, counts as reported, never failed."
_DOD_OPEN = (
    '<action if="{{parent_story_path}} is not provided">Validate definition-of-done checklist with essential '
    "requirements:"
)
_LAST_ITEM = "- Only permitted story sections were modified"
_STEP8 = '<step n="8" goal="Validate and mark task complete ONLY when fully done">\n'


def _step(skill: str, number: int) -> str:
    start = skill.index(f'<step n="{number}"')
    return skill[start : skill.index("</step>", start)]


def _dod_list_ends_on(skill: str, note: str) -> bool:
    step9 = _step(skill, 9)
    start = step9.find(_DOD_OPEN)
    if start == -1:
        return False
    body = step9[start : step9.index("</action>", start)]
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return lines[-2:] == [_LAST_ITEM, note]


def _dod_list_ends_on_the_note(skill: str) -> bool:
    """In step 9, the definition-of-done action's list ends on its last item
    and then the note, alone on its line and not an item of the list, directly
    before the action closes; the skill holds the note once."""
    return _dod_list_ends_on(skill, _NOTE) and skill.count(_NOTE) == 1


def test_the_definition_of_done_list_ends_on_the_note():
    assert _dod_list_ends_on_the_note(SKILL)


def _note_line(skill: str = SKILL) -> str:
    return next(line for line in skill.splitlines(keepends=True) if line.strip() == _NOTE)


def test_note_predicate_rejects_the_pre_edit_skill():
    pre = _replaced(SKILL, _note_line(), "")
    assert _NOTE not in pre
    assert not _dod_list_ends_on_the_note(pre)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("counts as reported, never failed.", "counts as failed.", id="counted-as-failed"),
        pytest.param("counts as reported, never failed.", "counts as reported, or failed.", id="reported-or-failed"),
        pytest.param(_NOTE, "- " + _NOTE, id="made-a-list-item"),
        pytest.param("still red after this step", "green after this step", id="a-green-gate"),
        pytest.param("still red after this step", "red before this step", id="red-before-this-step"),
    ],
)
def test_note_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _dod_list_ends_on_the_note(_replaced(SKILL, old, new))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The first wording, which covered the regression suite too, and every
        # run, whether it handed the workflow a gate or not.
        pytest.param(_NOTE, "A gate this step could not get green counts as reported, never failed.",
                     id="a-gate-this-step-could-not-get-green"),
        pytest.param("A gate the run handed this workflow, still red", "Any gate still red", id="any-red-gate"),
        pytest.param("A gate the run handed this workflow,", "The regression suite, or a gate the run handed this "
                     "workflow,", id="the-suite-too"),
        pytest.param("A gate the run handed this workflow,", "A gate the repository declares,",
                     id="every-declared-gate-of-the-repo"),
    ],
)
def test_note_predicate_rejects_a_note_that_reaches_past_a_handed_gate(old, new):
    """The note covers only a gate the run handed the workflow: not the
    regression suite, not a gate the repository declares and the run did not
    hand over, and nothing on a run that handed none."""
    assert not _dod_list_ends_on_the_note(_replaced(SKILL, old, new))


def test_a_gate_the_run_handed_is_one_the_section_says_the_run_passes():
    """The note's antecedent: the section says the run passes the gates as the
    one more input, `{{declared_gates}}`, which step 9's action is guarded on."""
    section = _flat(_section(SKILL))
    assert "To close on them here, the run passes one more input" in section
    assert "- `{{declared_gates}}`: the commands that run the quality gates the run will sweep" in section
    assert '<action if="{{declared_gates}} is provided">' in _step(SKILL, 9)


def test_note_predicate_rejects_the_note_moved():
    line = _note_line()
    without = _replaced(SKILL, line, "")
    # Above the list, on the action's own line.
    above = _replaced(without, _DOD_OPEN + "\n", _DOD_OPEN + "\n" + line)
    assert not _dod_list_ends_on_the_note(above)
    # Into step 8, which checks one task and not the story.
    into_8 = _replaced(without, _STEP8, _STEP8 + line)
    assert not _dod_list_ends_on_the_note(into_8)


def test_note_predicate_rejects_a_second_copy_in_step_8():
    """Twin for the clause that the skill holds the note once: step 9 keeps it
    intact, so only that clause can reject the copy added to step 8."""
    copied = _replaced(SKILL, _STEP8, _STEP8 + _note_line())
    assert _dod_list_ends_on(copied, _NOTE)
    assert not _dod_list_ends_on_the_note(copied)


# --- the workflow still names no declared gate outside step 9's action ------------


def _declared_gates_pins():
    """test_execute_dev_step_declared_gates_prose.py, loaded under its own name,
    for its predicate over the skill."""
    path = Path(__file__).with_name("test_execute_dev_step_declared_gates_prose.py")
    spec = importlib.util.spec_from_file_location("ucg_declared_gates_prose_pins", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_the_note_keeps_the_declared_gates_in_step_9_s_action_and_adds_no_halt():
    """The sibling's predicate holds on the skill with the note: no workflow
    line but step 9's action names the declared gates, and no line of step 9
    ties a halt to a gate."""
    assert _declared_gates_pins()._closes_on_the_declared_gates(SKILL) == []


def test_the_sibling_predicate_rejects_the_note_worded_with_declared_gate_or_a_halt():
    """Why the note says "a gate the run handed this workflow": worded "a
    declared gate" it would name the declared gates outside step 9's action,
    and worded as a halt it would tie one to a gate."""
    pins = _declared_gates_pins()
    declared = _replaced(SKILL, "A gate the run handed this workflow,", "A declared gate the run handed this workflow,")
    assert pins._closes_on_the_declared_gates(declared) == [pins._STEP9_ONLY]
    halting = _replaced(SKILL, "counts as reported, never failed.", "halts the workflow.")
    assert pins._closes_on_the_declared_gates(halting) == [pins._STEP9_HALTS]


# --- LICENSE.md lists the change ---------------------------------------------------

_LICENSE_CLAUSE = (
    "a clause on four checklist items and a note under the definition-of-done list on a declared gate still red"
)


def _license_lists_the_change(license_text: str) -> bool:
    flat = _flat(license_text)
    start = flat.find("The changes from upstream are limited to:")
    end = flat.find("The workflow steps are otherwise unchanged.")
    return start != -1 and end != -1 and _LICENSE_CLAUSE in flat[start:end]


def test_the_attribution_lists_the_clause_and_the_note():
    assert _license_lists_the_change(LICENSE)
    # "Four checklist items": the four that carry the clause.
    assert len(_ITEM_CLAUSES) == 4


def test_license_predicate_rejects_the_pre_edit_attribution():
    flat = _flat(LICENSE)
    assert not _license_lists_the_change(_replaced(flat, "; " + _LICENSE_CLAUSE, ""))


def test_license_predicate_rejects_the_clause_outside_the_list():
    flat = _flat(LICENSE)
    moved = _replaced(
        _replaced(flat, "; " + _LICENSE_CLAUSE, ""),
        "The workflow steps are otherwise unchanged.",
        "The workflow steps are otherwise unchanged. Also " + _LICENSE_CLAUSE + ".",
    )
    assert not _license_lists_the_change(moved)
