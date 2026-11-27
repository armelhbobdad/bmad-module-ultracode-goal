#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for the dev step's done bar (issue #281).

`ucg-dev-story` closed a story on the repository's default test task: its steps
run the regression suite and linting "if configured", then set the story to
`review`. Step 2 of Execute's story loop then sweeps the declared gate set, the
third of its three axes: the quality tasks a repository declares beside its
default task rather than under it (a `test:coverage` threshold, a
`test:storybook`). Such a gate first ran at step 2, after the dev step had set
the story to `review`, and its red cost a fix round and a second full sweep.

Now:

- `references/execute.md`'s story loop hands `ucg-dev-story` a `declared_gates`
  input before it delegates: for each task step 2 will run that the default task
  leaves out, the command that runs it. The rule stands as a paragraph of its
  own before step 2 (`test_story_skills.py` reads step 1's item through a
  fixed-width window), names no task step 2 will not run, and leaves step 2's
  full sweep and its tests-ran marker as they were.
- `ucg-dev-story/SKILL.md` declares the input in a "Declared Gates" section,
  and step 9 runs every listed command after the full regression suite and
  before either status write, fixing a red one before a status moves. After a
  fix that changed a file the suite runs again, and no fix that turns it red,
  or that needs a dependency or a configuration file the story does not
  specify, is kept. A declared gate is no HALT condition of the workflow, in
  step 9's list or in `checklist.md`: one it cannot get green is reported and
  left to step 2's sweep, so a story never stops in the dev step on one. Steps
  7 and 8 run once per task and do not run them.
- `ucg-dev-story/LICENSE.md` lists the input among the changes from upstream,
  and `docs/how-it-works.md` says the dev step closes on those tasks too.

Each predicate returns what the text lacks, by name, so a twin can assert which
item a mutant reds. Each is checked against the live text and, as its
anti-vacuous twin, against the pre-edit text (the live text with the #281
wording taken out) and against mutants that drop or move one clause. The
halt-free bar is also pinned by absence: a sentence of the rule or of the
section, a step-9 HALT, or any other workflow line that ties a halt, a stop or
an escalation to a declared gate reds a predicate, each with a mutant twin.
Stated limit: this is a proof over prose. It shows the instruction is in the
file, not that an executor obeys it.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_execute_dev_step_declared_gates_prose.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILLS = Path(__file__).resolve().parents[3]
_REPO = _SKILLS.parent
_EXECUTE = _SKILLS / "ultracode-goal" / "references" / "execute.md"
_DEV = _SKILLS / "ucg-dev-story"
_HOW_IT_WORKS = _REPO / "docs" / "how-it-works.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _mutate(text: str, old: str, new: str) -> str:
    """`text` with its one `old` replaced, matching any run of whitespace (a
    line wrap included) wherever `old` has a space."""
    pattern = re.compile(r"\s+".join(map(re.escape, old.split(" "))))
    assert len(pattern.findall(text)) == 1, old
    return pattern.sub(lambda _: new, text, count=1)


# --- references/execute.md: the story loop's hand-off rule --------------------

_HEADING = "**Hand `ucg-dev-story` the declared gates step 2 will run.**"
_STEP2 = "\n2. Run the tests"
_NO_RULE = "the story loop has no rule handing `ucg-dev-story` the declared gates before step 2"
_OWN_PARAGRAPH = "the rule stands as a paragraph of its own"
_RULE_HALTS = "the rule ties no halt or escalation to a declared gate"
# Any word that would route a declared gate to a stop, once the rule's one
# denial is taken out.
_RULE_DENIAL = "A declared gate never halts it"
_RULE_HALT_WORD = re.compile(r"\b(?:halt|stop|escalat|block|catch-all)", re.I)

_RULE_CLAUSES = {
    "it enumerates the declared tasks before delegating": (
        "So before delegating, enumerate the repo's declared quality tasks as step 2's third axis does"
    ),
    "it names the input": "pass `declared_gates`",
    "it holds only what step 2 runs and the default task leaves out": (
        "for each task step 2 will run that the default task leaves out, the command that runs it"
    ),
    "it cites the sub-skill's section": (
        'Its "Declared Gates" section has it run each one beside its regression suite'
    ),
    "it narrows a command to the story's packages where it can": (
        "for the packages its changes touch where the command can be narrowed to them"
    ),
    "a red one is fixed before review": "fix a red one before the story moves to `review`",
    "a declared gate never halts the dev step": _RULE_DENIAL,
    "one still red is named in the completion notes": "one it cannot get green is named in its completion notes",
    "one it cannot clear is left to step 2": (
        "the story moves to `review` as it would without the input, and step 2's sweep meets that red"
    ),
    "it names no gate the sweep skips": "Name no task step 2 will not run",
    "a re-loop gets the same list": "the same list on a re-loop",
    "it passes nothing when the default task runs every gate": (
        "pass nothing when the default task already runs every declared gate"
    ),
    "it is no sweep": (
        "This is the dev step's done bar, never the sweep: it may be package-scoped and cached, it writes no "
        "tests-ran marker, and step 2 still owes its own sweep on all three axes"
    ),
}


def _story_loop(execute: str) -> str:
    """The story loop up to its step 2, where a story's own hand-off rules sit."""
    start = execute.index("### The story loop")
    return execute[start : execute.index(_STEP2, start)]


def _hand_off_rule(execute: str) -> str:
    """The rule's paragraph, or '' when the loop before step 2 has none."""
    loop = _story_loop(execute)
    at = loop.find(_HEADING)
    return "" if at == -1 else loop[at:].split("\n\n")[0]


def _hands_the_declared_gates(execute: str) -> list[str]:
    rule = _hand_off_rule(execute)
    if not rule:
        return [_NO_RULE]
    flat = _flat(rule)
    missing = [name for name, clause in _RULE_CLAUSES.items() if clause not in flat]
    loop = _story_loop(execute)
    # Its own paragraph: a blank line before it, and no other bold lead run
    # into it after its heading.
    if not loop[: loop.index(_HEADING)].endswith("\n\n") or flat.count("**") != 2:
        missing.append(_OWN_PARAGRAPH)
    elif _RULE_HALT_WORD.search(flat.replace(_RULE_DENIAL, "")):
        missing.append(_RULE_HALTS)
    return missing


def _execute_pre(execute: str) -> str:
    """The story loop as it was before #281: the rule and its blank line out."""
    rule = _hand_off_rule(execute)
    assert rule and execute.count("\n\n" + rule) == 1
    return execute.replace("\n\n" + rule, "", 1)


def _step2(execute: str) -> str:
    start = execute.index(_STEP2)
    return execute[start : execute.index("\n3. **Production profile only:**", start)]


def test_the_story_loop_hands_the_dev_step_the_declared_gates():
    assert _hands_the_declared_gates(_read(_EXECUTE)) == []


def test_the_hand_off_predicate_rejects_the_pre_edit_loop():
    pre = _execute_pre(_read(_EXECUTE))
    assert "**An operator-evidence AC is not `ucg-dev-story`'s to satisfy.**" in _story_loop(pre)
    assert _hands_the_declared_gates(pre) == [_NO_RULE]


@pytest.mark.parametrize(
    ("old", "new", "missing"),
    [
        pytest.param(
            "Name no task step 2 will not run, pass", "Pass", ["it names no gate the sweep skips"],
            id="any-declared-task",
        ),
        pytest.param(
            "for each task step 2 will run that the default task leaves out, the command that runs it",
            "the command of every quality task the repo declares",
            ["it holds only what step 2 runs and the default task leaves out"],
            id="every-declared-task",
        ),
        pytest.param(
            "and fix a red one before the story moves to `review`.", "and report a red one.",
            ["a red one is fixed before review"],
            id="review-on-a-red",
        ),
        pytest.param(
            "A declared gate never halts it: one it cannot get green is named in its completion notes, the story "
            "moves to `review` as it would without the input, and step 2's sweep meets that red as it meets any "
            "other.",
            "One it cannot get green halts it.",
            [
                "a declared gate never halts the dev step",
                "one still red is named in the completion notes",
                "one it cannot clear is left to step 2",
                _RULE_HALTS,
            ],
            id="halts-on-a-red",
        ),
        pytest.param(
            "one it cannot get green is named in its completion notes, the story",
            "one it cannot get green is ignored, the story",
            ["one still red is named in the completion notes"],
            id="unreported-red",
        ),
        pytest.param(
            ", for the packages its changes touch where the command can be narrowed to them, and fix", ", and fix",
            ["it narrows a command to the story's packages where it can"],
            id="never-narrowed",
        ),
        pytest.param(
            "it writes no tests-ran marker, and step 2 still owes its own sweep on all three axes",
            "and a green one stands in for step 2's sweep of those tasks",
            ["it is no sweep"],
            id="replaces-the-sweep",
        ),
        pytest.param(
            "This is the dev step's done bar, never the sweep: it may",
            "This is the dev step's done bar and stands in for the sweep's third axis: it may",
            ["it is no sweep"],
            id="stands-in-for-the-third-axis",
        ),
        pytest.param(
            ", pass the same list on a re-loop,", ",", ["a re-loop gets the same list"],
            id="first-pass-only",
        ),
    ],
)
def test_the_hand_off_predicate_rejects_a_dropped_clause(old, new, missing):
    assert _hands_the_declared_gates(_mutate(_read(_EXECUTE), old, new)) == missing


@pytest.mark.parametrize(
    "added",
    [
        pytest.param(" When the sub-skill halts on one, take the sub-skill halt catch-all's route.", id="halt-route"),
        pytest.param(" When one stays red, escalate as the catch-all below does.", id="escalation"),
        pytest.param(" A red one blocks the story at `in-progress`.", id="blocks-the-story"),
    ],
)
def test_the_hand_off_predicate_rejects_a_halt_tied_to_a_declared_gate(added):
    # The halt-free bar is pinned by absence too: every clause kept, one
    # sentence that routes a red gate to a stop is enough to red the rule.
    anchor = "and step 2's sweep meets that red as it meets any other."
    mutant = _mutate(_read(_EXECUTE), anchor, anchor + added)
    assert _hands_the_declared_gates(mutant) == [_RULE_HALTS]


def test_the_hand_off_predicate_rejects_the_next_paragraph_run_into_the_rule():
    execute = _read(_EXECUTE)
    rule = _hand_off_rule(execute)
    assert execute.count(rule + "\n\n**Get an AC narrowed") == 1
    merged = execute.replace(rule + "\n\n**Get an AC narrowed", rule + " **Get an AC narrowed", 1)
    assert _hands_the_declared_gates(merged) == [_OWN_PARAGRAPH]


_STEP1_RULE = "**For a decomposed child row, skip `ucg-create-story` entirely**"
_STEP1_LAST_PINNED = "never a `ucg-create-story` run for the child"


def test_the_hand_off_predicate_rejects_the_rule_inside_step_1():
    # A rule run into step 1's item, inside its decomposed-child rule and before
    # that rule's last pinned phrase, is not a paragraph of its own.
    execute = _read(_EXECUTE)
    rule = _hand_off_rule(execute)
    anchor = "and the parent's file unedited."
    pre = _execute_pre(execute)
    assert pre.count(anchor) == 1
    assert pre.index(anchor) < pre.index(_STEP1_LAST_PINNED, pre.index(_STEP1_RULE))
    moved = pre.replace(anchor, f"{anchor} {rule}", 1)
    assert moved.count(_HEADING) == 1
    assert _hands_the_declared_gates(moved) == [_OWN_PARAGRAPH]


def test_the_hand_off_predicate_rejects_the_rule_moved_into_step_2():
    execute = _read(_EXECUTE)
    rule = _hand_off_rule(execute)
    anchor = "\n\n**Defeat the build cache at least once.**"
    moved = _execute_pre(execute).replace(anchor, f"\n\n{rule}{anchor}", 1)
    assert moved.count(_HEADING) == 1
    assert _hands_the_declared_gates(moved) == [_NO_RULE]


_THIRD_AXIS = "- **The repo's DECLARED gate set, not its default task.**"


def _step2_carries_the_third_axis(execute: str) -> bool:
    """Step 2 still holds the axis the rule takes its list from, as the third:
    package breadth first, then language, then the declared gate set, whose
    excluded tasks step 2 runs or names as not run."""
    step2 = _step2(execute)
    return (
        "**Scope the sweep on three axes, not one.** Package breadth above is the first;" in _flat(step2)
        and "- **Language.**" in step2
        and _THIRD_AXIS in step2
        and step2.index("- **Language.**") < step2.index(_THIRD_AXIS)
        and "Run the excluded ones too, or state explicitly which you are not running and why." in step2
    )


def test_the_rule_cites_the_third_axis_step_2_still_carries():
    # The rule takes its list from step 2's third axis and leaves that axis,
    # and step 2's full sweep, as they were.
    execute = _read(_EXECUTE)
    assert _step2_carries_the_third_axis(execute)
    assert _HEADING not in _step2(execute)


def test_the_third_axis_check_rejects_a_step_2_without_it():
    execute = _read(_EXECUTE)
    bullet = next(line for line in execute.splitlines(keepends=True) if line.startswith(_THIRD_AXIS))
    assert not _step2_carries_the_third_axis(execute.replace(bullet, "", 1))


# --- ucg-dev-story/SKILL.md: the input and step 9 ------------------------------

_SECTION = "\n## Declared Gates\n"
_NO_SECTION = 'the skill has no "Declared Gates" section'
_STEP9_SUITE = "<action>Run the full regression suite (do not skip)</action>"
_GATES_GUARD = '<action if="{{declared_gates}} is provided">'
_STEP9_DENIAL = "never HALT for a declared gate"
_STEP9_GATES = (
    f"{_GATES_GUARD}Run every command in {{{{declared_gates}}}} (do not skip); fix a red one and run it again, "
    "and after a fix that changed any file run the full regression suite again, before any status moves, keeping "
    f'no fix that turns the suite red; {_STEP9_DENIAL}: report one still red as "Declared Gates" says</action>'
)
_STORY_FILE_WRITE = 'Update the story Status to: "review"'
_SPRINT_STATUS_WRITE = 'Update development_status[{{story_key}}] = "review"'
_NO_STEP9_RUN = "step 9 runs every declared gate"
_AFTER_SUITE = "step 9 runs them after the full regression suite"
_BEFORE_STORY_FILE = "step 9 runs them before it sets the story file's Status"
_BEFORE_SPRINT_STATUS = "step 9 runs them before it sets the sprint-status row"
_STEP9_ONLY = "no workflow line but step 9's action names the declared gates"
_SECTION_HALTS = "the section ties no halt to a declared gate"
_STEP9_HALTS = "step 9 ties no HALT to a declared gate"

# The section's own denials, the only places it may name a halt or a stop.
_SECTION_DENIALS = (
    "never halt for it",
    "A declared gate is no HALT condition of this workflow",
    "**No HALT Conditions**",
    "stops nothing",
)
_HALT_WORD = re.compile(r"\b(?:halt|stop|escalat|block)", re.I)
_GATE_WORD = re.compile(r"declared|\bgates?\b", re.I)
_DECLARED_GATE = re.compile(r"declared[ _]gates?", re.I)
_CHECKLIST_ITEMS = ("Regression Prevention", "Code Quality", "Quality Gates Passed", "No HALT Conditions")

_SECTION_CLAUSES = {
    "it declares the input": (
        "- `{{declared_gates}}`: the commands that run the quality gates the run will sweep and the default test "
        "task leaves out."
    ),
    "it takes the input beside a story path or a child's inputs": (
        "the run passes one more input, with a story path or with a decomposed child's inputs"
    ),
    "step 9 runs them after the full regression suite, narrowed where they can be": (
        "Step 9 runs every command in `{{declared_gates}}` after the full regression suite, for the packages this "
        "story's changes touch when the command can be narrowed to them, and whole otherwise."
    ),
    "the red-gate bullet's lead denies a halt": "**Fix a red one before any status moves, and never halt for it.**",
    "a red one is fixed, and the suite run again, before a status moves": (
        "Fix a red one and run it again, and after a fix that changed any file run the full regression suite "
        "again, before step 9 sets a status to `review`, in the story file or in `sprint-status.yaml`."
    ),
    "no fix that turns the suite red is kept": (
        "Keep no fix that turns the suite red: undo it, and treat that gate as one this workflow cannot get green."
    ),
    "no fix reaches past the story's dependencies and configuration": (
        "A fix that needs a dependency or a configuration file the story does not specify is not made: that gate "
        "is then one this workflow cannot get green."
    ),
    "a declared gate is no halt condition": (
        "A declared gate is no HALT condition of this workflow: not a regression failure, an implementation "
        "failure or a definition-of-done failure, in step 9's list or in `checklist.md`"
    ),
    "the checklist counts one still red as reported": (
        "whose **Regression Prevention**, **Code Quality**, **Quality Gates Passed** and **No HALT Conditions** "
        "items count a declared gate still red as reported, never failed."
    ),
    "one still red is reported and the status moves as before": (
        "One this workflow cannot get green, whether this story's changes turned it red or it was red before them, "
        "stops nothing: name it, with its last output, in the completion notes (step 10's summary for a "
        "decomposed child), and let step 9 set the status as it would without the input."
    ),
    "it runs no gate the input does not list, and the other checks as written": (
        "A declared gate the input does not list is the run's to sweep, not this workflow's; the checks steps 7 to "
        "9 run without the input still run as written."
    ),
    "without the input the workflow is unchanged": "When it is not provided, the workflow runs as written.",
}


def _section(skill: str) -> str:
    at = skill.find(_SECTION)
    if at == -1:
        return ""
    end = skill.find("\n## ", at + len(_SECTION))
    return skill[at : end if end != -1 else len(skill)]


def _step(skill: str, number: int) -> str:
    start = skill.index(f'<step n="{number}"')
    return skill[start : skill.index("</step>", start)]


def _closes_on_the_declared_gates(skill: str) -> list[str]:
    section = _flat(_section(skill))
    missing = [] if section else [_NO_SECTION]
    missing += [name for name, clause in _SECTION_CLAUSES.items() if clause not in section]
    rest = section
    for denial in _SECTION_DENIALS:
        rest = rest.replace(denial, "")
    if _HALT_WORD.search(rest):
        missing.append(_SECTION_HALTS)
    step9 = _step(skill, 9)
    gates = step9.find(_STEP9_GATES)
    if gates == -1:
        missing.append(_NO_STEP9_RUN)
    else:
        suite = step9.find(_STEP9_SUITE)
        if suite == -1 or gates < suite:
            missing.append(_AFTER_SUITE)
        for write, name in ((_STORY_FILE_WRITE, _BEFORE_STORY_FILE), (_SPRINT_STATUS_WRITE, _BEFORE_SPRINT_STATUS)):
            at = step9.find(write)
            if at == -1 or at < gates:
                missing.append(name)
    # A HALT in step 9 on a line that names a gate, whatever it calls it, once
    # the action's own denial is taken out.
    if any(
        _HALT_WORD.search(line) and _GATE_WORD.search(line)
        for line in (raw.replace(_STEP9_DENIAL, "") for raw in step9.splitlines())
    ):
        missing.append(_STEP9_HALTS)
    # Nothing else in the workflow may name the declared gates: not a step that
    # runs them, not a definition-of-done item, not a HALT condition.
    workflow = skill[skill.index("<workflow>") :]
    own = next((line for line in step9.splitlines(keepends=True) if line.strip().startswith(_GATES_GUARD)), "")
    if _DECLARED_GATE.search(workflow.replace(step9, step9.replace(own, "", 1), 1)):
        missing.append(_STEP9_ONLY)
    return missing


def _gates_line(skill: str) -> str:
    return next(line for line in skill.splitlines(keepends=True) if line.strip() == _STEP9_GATES)


def _skill_pre(skill: str) -> str:
    """The skill as it was before #281: the section and the step-9 action out."""
    without = skill[: skill.index("## Declared Gates\n")] + skill[skill.index("## Execution\n") :]
    pre = without.replace(_gates_line(without), "", 1)
    assert "{{declared_gates}}" not in pre and "Declared Gates" not in pre
    return pre


def _gates_line_after(skill: str, anchor: str) -> str:
    """The skill with step 9's action moved to the line after `anchor`."""
    line = _gates_line(skill)
    without = skill.replace(line, "", 1)
    assert without.count(anchor) == 1, anchor
    end = without.index("\n", without.index(anchor)) + 1
    return without[:end] + line + without[end:]


def test_dev_story_closes_on_the_declared_gates():
    assert _closes_on_the_declared_gates(_read(_DEV / "SKILL.md")) == []


def test_the_dev_story_predicate_rejects_the_pre_edit_skill():
    pre = _skill_pre(_read(_DEV / "SKILL.md"))
    assert _STEP9_SUITE in _step(pre, 9)
    assert _closes_on_the_declared_gates(pre) == [_NO_SECTION, *_SECTION_CLAUSES, _NO_STEP9_RUN]


@pytest.mark.parametrize(
    ("anchor", "missing"),
    [
        pytest.param(
            '<action if="definition-of-done validation fails">HALT - Address DoD failures before completing</action>',
            [_BEFORE_STORY_FILE, _BEFORE_SPRINT_STATUS],
            id="after-both-status-writes",
        ),
        pytest.param(
            f'<action if="{{{{parent_story_path}}}} is not provided">{_STORY_FILE_WRITE}</action>',
            [_BEFORE_STORY_FILE],
            id="after-the-story-file-write",
        ),
        pytest.param(
            "Verify every AC in {{claimed_acs}} is implemented and tested",
            [_AFTER_SUITE],
            id="before-the-regression-suite",
        ),
        pytest.param(
            "Run full test suite to ensure NO regressions introduced</action>",
            [_NO_STEP9_RUN, _STEP9_ONLY],
            id="once-per-task-in-step-8",
        ),
    ],
)
def test_the_dev_story_predicate_rejects_the_action_moved(anchor, missing):
    moved = _gates_line_after(_read(_DEV / "SKILL.md"), anchor)
    assert _closes_on_the_declared_gates(moved) == missing


@pytest.mark.parametrize(
    ("old", "new", "missing"),
    [
        pytest.param(
            "Step 9 runs every command in `{{declared_gates}}` after the full regression suite, for the packages "
            "this story's changes touch when the command can be narrowed to them, and whole otherwise.",
            "Step 9 runs every command in `{{declared_gates}}` after the full regression suite, whole, never narrowed.",
            ["step 9 runs them after the full regression suite, narrowed where they can be"],
            id="never-narrowed",
        ),
        pytest.param(
            ", and after a fix that changed any file run the full regression suite again, before step 9 sets",
            ", before step 9 sets",
            ["a red one is fixed, and the suite run again, before a status moves"],
            id="no-suite-run-after-a-fix",
        ),
        pytest.param(
            "Keep no fix that turns the suite red: undo it, and treat that gate as one this workflow cannot get "
            "green. ",
            "",
            ["no fix that turns the suite red is kept"],
            id="a-fix-may-red-the-suite",
        ),
        pytest.param(
            "A fix that needs a dependency or a configuration file the story does not specify is not made: that "
            "gate is then one this workflow cannot get green. ",
            "",
            ["no fix reaches past the story's dependencies and configuration"],
            id="a-fix-may-add-a-dependency",
        ),
        pytest.param(
            "**Code Quality**, **Quality Gates Passed** and **No HALT Conditions** items",
            "**Code Quality** and **Quality Gates Passed** items",
            ["the checklist counts one still red as reported"],
            id="checklist-item-left-out",
        ),
        pytest.param(
            "count a declared gate still red as reported, never failed.", "fail on a declared gate still red.",
            ["the checklist counts one still red as reported"],
            id="checklist-fails-a-red",
        ),
        pytest.param(
            "whether this story's changes turned it red or it was red before them, stops", "stops",
            ["one still red is reported and the status moves as before"],
            id="either-origin-of-a-red-dropped",
        ),
        pytest.param(
            "; the checks steps 7 to 9 run without the input still run as written.", ".",
            ["it runs no gate the input does not list, and the other checks as written"],
            id="other-checks-unsaid",
        ),
    ],
)
def test_the_dev_story_predicate_rejects_a_dropped_clause(old, new, missing):
    assert _closes_on_the_declared_gates(_mutate(_read(_DEV / "SKILL.md"), old, new)) == missing


_FINAL_DOD_HALT = '<action if="definition-of-done validation fails">HALT - Address DoD failures before completing</action>'


@pytest.mark.parametrize(
    ("old", "new", "missing"),
    [
        # The halt-free bar keeps the worst case at what a run met before the
        # input, a red that step 2's sweep meets. Each mutant ties a halt to a
        # declared gate, or names one where a HALT condition or another step
        # would meet it.
        pytest.param(
            "A declared gate is no HALT condition of this workflow: not a regression failure, an implementation "
            "failure or a definition-of-done failure",
            "A red one is a regression failure, and HALT if unable to fix it",
            ["a declared gate is no halt condition", _SECTION_HALTS],
            id="section-names-a-red-a-regression",
        ),
        pytest.param(
            "The run's sweep, which runs every declared gate again, owns it from there.",
            "The run's sweep, which runs every declared gate again, owns it from there. HALT when one is still red "
            "after three fixes.",
            [_SECTION_HALTS],
            id="section-adds-a-halt",
        ),
        pytest.param(
            "in the story file or in `sprint-status.yaml`.",
            "in the story file or in `sprint-status.yaml`. Then run the full regression suite again, and HALT if it "
            "is red.",
            [_SECTION_HALTS],
            id="section-halts-on-the-suite-after-a-fix",
        ),
        pytest.param(
            "red before them, stops nothing:", "red before them, HALTs the workflow:",
            ["one still red is reported and the status moves as before", _SECTION_HALTS],
            id="section-stops-on-one",
        ),
        pytest.param(
            "**Fix a red one before any status moves, and never halt for it.**",
            "**Fix a red one before any status moves.**",
            ["the red-gate bullet's lead denies a halt"],
            id="section-lead-drops-the-denial",
        ),
        pytest.param(
            "keeping no fix that turns the suite red; never HALT for a declared gate: report one still red as "
            '"Declared Gates" says</action>',
            "and HALT if unable to fix it</action>",
            [_NO_STEP9_RUN, _STEP9_HALTS],
            id="step-9-action-halts",
        ),
        pytest.param(
            f"{_STEP9_GATES}\n",
            f'{_STEP9_GATES}\n    <action if="a command in {{{{declared_gates}}}} is still red">HALT - Fix the '
            "declared gate before completing</action>\n",
            [_STEP9_HALTS, _STEP9_ONLY],
            id="step-9-adds-a-halt-on-the-input",
        ),
        pytest.param(
            '<action if="regression failures exist">',
            '<action if="regression failures exist or a declared gate is red">',
            [_STEP9_HALTS, _STEP9_ONLY],
            id="step-9-regression-halt-widened",
        ),
        pytest.param(
            _FINAL_DOD_HALT,
            f'{_FINAL_DOD_HALT}\n    <action if="a quality gate is still red">HALT - Fix the gates before '
            "completing</action>",
            [_STEP9_HALTS],
            id="step-9-halts-on-a-gate-by-another-name",
        ),
        pytest.param(
            "      - Code quality checks pass (linting, static analysis if configured)\n",
            "      - Code quality checks pass (linting, static analysis if configured)\n"
            "      - Every command in the declared gates passes\n",
            [_STEP9_ONLY],
            id="definition-of-done-counts-a-gate",
        ),
        pytest.param(
            "<action>Run linting and code quality checks if configured in project</action>",
            "<action>Run linting and code quality checks if configured in project</action>\n"
            "    <action>Run every declared gate command as well</action>",
            [_STEP9_ONLY],
            id="step-7-runs-the-gates",
        ),
    ],
)
def test_the_dev_story_predicate_rejects_a_halt_tied_to_a_declared_gate(old, new, missing):
    skill = _read(_DEV / "SKILL.md")
    assert skill.count(old) == 1, old
    assert _closes_on_the_declared_gates(skill.replace(old, new, 1)) == missing


def test_the_dev_story_predicate_tells_a_halting_action_from_an_edited_one():
    # An edit to step 9's action that adds no halt reds only its presence;
    # the halting edit above reds the absence check as well.
    skill = _mutate(
        _read(_DEV / "SKILL.md"),
        ", and after a fix that changed any file run the full regression suite again, before any status moves,",
        ", before any status moves,",
    )
    assert _closes_on_the_declared_gates(skill) == [_NO_STEP9_RUN]


def _names_checklist_items(checklist: str) -> list[str]:
    """The checklist items the section names that `checklist.md` lacks."""
    return [name for name in _CHECKLIST_ITEMS if f"- [ ] **{name}:**" not in checklist]


def test_the_section_names_checklist_items_that_exist():
    section = _flat(_section(_read(_DEV / "SKILL.md")))
    assert all(f"**{name}**" in section for name in _CHECKLIST_ITEMS)
    assert _names_checklist_items(_read(_DEV / "checklist.md")) == []


def test_the_checklist_item_check_rejects_a_renamed_item():
    checklist = _read(_DEV / "checklist.md").replace("**Quality Gates Passed:**", "**Quality Gates Met:**", 1)
    assert _names_checklist_items(checklist) == ["Quality Gates Passed"]


def test_the_rule_and_the_skill_name_one_input():
    rule = _flat(_hand_off_rule(_read(_EXECUTE)))
    named = re.search(r"pass `(\w+)`", rule)
    assert named is not None
    assert f"- `{{{{{named.group(1)}}}}}`:" in _flat(_section(_read(_DEV / "SKILL.md")))


def test_the_input_check_rejects_a_renamed_input():
    skill = _read(_DEV / "SKILL.md").replace("{{declared_gates}}", "{{quality_gates}}")
    rule = _flat(_hand_off_rule(_read(_EXECUTE)))
    named = re.search(r"pass `(\w+)`", rule)
    assert named is not None
    assert f"- `{{{{{named.group(1)}}}}}`:" not in _flat(_section(skill))


# --- ucg-dev-story/LICENSE.md and docs/how-it-works.md ---------------------------

_LICENSE_CLAUSE = (
    'a declared-gates input (the "Declared Gates" section and its action in step 9), under which the skill also '
    "runs, before it sets a story to review, the quality gates a run names, and fixes a red one where it can"
)
_LICENSE_UNLISTED = "the list of changes from upstream names the declared-gates input"
_DOCS_CLAUSE = (
    "`ucg-dev-story` implements the feature and un-skips the story's ATDD tests, and also runs each declared "
    "quality task the story's sweep will run that the default test task leaves out, fixing its reds where it can →"
)


def _attributes_the_declared_gates(license_text: str) -> list[str]:
    flat = _flat(license_text)
    start = flat.find("The changes from upstream are limited to:")
    end = flat.find("The workflow steps are otherwise unchanged.")
    if start == -1 or end == -1:
        return ["the attribution lists its changes from upstream"]
    return [] if _LICENSE_CLAUSE in flat[start:end] else [_LICENSE_UNLISTED]


def _docs_close_on_the_declared_gates(text: str) -> bool:
    return _DOCS_CLAUSE in _flat(text)


def test_the_attribution_lists_the_declared_gates_input():
    assert _attributes_the_declared_gates(_read(_DEV / "LICENSE.md")) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(f"; {_LICENSE_CLAUSE};", ";", id="pre-edit"),
        pytest.param(
            f"; {_LICENSE_CLAUSE}; and em dashes replaced by other punctuation. The workflow steps are otherwise "
            "unchanged.",
            f"; and em dashes replaced by other punctuation. The workflow steps are otherwise unchanged. Also "
            f"{_LICENSE_CLAUSE}.",
            id="outside-the-list",
        ),
    ],
)
def test_the_attribution_predicate_rejects_its_mutants(old, new):
    mutant = _mutate(_read(_DEV / "LICENSE.md"), old, new)
    assert _attributes_the_declared_gates(mutant) == [_LICENSE_UNLISTED]


def test_how_it_works_says_the_dev_step_closes_on_the_declared_gates():
    assert _docs_close_on_the_declared_gates(_read(_HOW_IT_WORKS))


def test_the_docs_predicate_rejects_the_pre_edit_wording():
    clause = (
        ", and also runs each declared quality task the story's sweep will run that the default test task leaves "
        "out, fixing its reds where it can"
    )
    pre = _mutate(_read(_HOW_IT_WORKS), clause, "")
    assert "`ucg-dev-story` implements the feature and un-skips the story's ATDD tests →" in _flat(pre)
    assert not _docs_close_on_the_declared_gates(pre)
