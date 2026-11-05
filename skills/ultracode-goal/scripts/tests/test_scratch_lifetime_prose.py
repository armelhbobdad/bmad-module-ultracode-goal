#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""How long a story's `.scratch-<story_id>/` folder lasts (#206).

Execute's step 0 removed the folder once step 5's re-verify went green, before
the gate, and the gate's backfill and its resume removed it again. A runner or
harness built there for the declared-gate sweep was gone for every later sweep
of the same story that does not re-drive it: the re-gate a closed
`operator-evidence-owed` escalation owes (the fourth resume case), the gate's
backfill sweep, a cap-only re-loop's sweep and the step 5 the third resume case
enters at. Each one had to re-author the runner by hand, which risks measuring
another gate set.

The folder now lasts until the gate's advance route, which removes it once the
evidence commit is made, its `evidence-commit-rejected` escalation is written,
or nothing is staged (the gitignored artifact tree, where no commit is made).
A `reloop` or `escalate` verdict leaves it. This pins:

- one removal point: every sentence on the skills' surfaces and the user docs
  that names the folder beside a remove verb is one of five, step 0's rule,
  the evidence-folder rule's reason, the evidence commit's removal and its
  resume, and the resume rule's own removal for a `done` row;
- step 0's rule, its widened reason and the verdicts that leave the folder;
- the evidence commit's removal, nothing staged included, and the resume that
  removes a folder a `done` story left;
- that removal in Execute's resume rule too, before the next story's step 0
  or before Stage 6 on the last story's route: the rule loads gate.md only
  while the last advanced story's evidence is still uncommitted, so a run that
  stopped after that commit, or with nothing staged, never reaches gate.md's
  sentence. It sits after that route, so it does not split the route from the
  owed-commit checks its "that story" and "the commit" read back to;
- the fourth resume case's runner or harness, when the escalated cycle built
  one, and its fallback once the folder is gone, which re-authors what the
  declared gate set needs, in its own paragraph;
- the backfill and its resume, which leave the folder in place;
- the change fragment's account of the fourth case's fallback, keyed on the
  folder alone.

Each predicate is checked, as its anti-vacuous twin, against one-clause mutants
it must reject, the old wording among them.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_scratch_lifetime_prose.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2]
REFS = SKILL / "references"
REPO = SKILL.parents[1]
EXECUTE = (REFS / "execute.md").read_text(encoding="utf-8")
GATE = (REFS / "gate.md").read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*(\"-])")
_REMOVE = re.compile(
    r"\b(?:remov\w*|delet\w*|rm -|clean\w* up|discard\w*|wip\w*|eras\w*|prun\w*|purg\w*|clear\w* (?:out|away)"
    r"|drop\w*)\b",
    re.I,
)
# The folder by its name, as a glob, or by what it is.
_SCRATCH = re.compile(r"\.scratch-(?:<[^>]+>|\*)|\bscratch (?:directory|folder|dir)\b", re.I)
# Inside step 0, which introduces it, the folder is also "the directory".
_THE_DIRECTORY = re.compile(r"\bthe directory\b", re.I)

_STEP0_START = "\n0. **Set the current story and record its baseline commit**"
_STEP0_REMOVAL = (
    "**Remove the directory on the gate's advance route, once its evidence commit is made, its "
    "`evidence-commit-rejected` escalation is written, or nothing is staged for it** (`references/gate.md`, \"Commit "
    "the gate's evidence before the next story starts\"), never earlier, and never later: the next story's step 0 "
    "must not find it."
)
_STEP0_KEEP = (
    "A `reloop` or `escalate` verdict leaves it in place, since the story still owes a cycle or a re-gate that runs "
    "the sweep again."
)
_STEP0_OUTLIVES = (
    "The directory outlives the step-4 commit and step 5 **deliberately**: step 5 re-runs the same declared-gate sweep "
    "on the committed tree, and the gate's backfill sweep, a cap-only re-loop's sweep and the step 5 a resume enters "
    "at (the third and fourth cases above) run it again without re-driving the story, so a runner or harness built "
    "here is still needed there, and one lost before then gets re-authored by hand, a real, measured cost that risks "
    "measuring a different gate set."
)
_STEP0_OLD_REMOVAL = (
    "**Remove the directory after step 5's re-verify goes green, before the story advances**, never earlier, and "
    "never later: the next story's step 0 must not find it."
)
_RULE_LEAD = (
    "**Evidence never goes in scratch.** The scratch directory is removed when the story advances, while the story "
    "record and the gate trail (`references/finalize.md`) cite their evidence after that, so the story's evidence has "
    "a folder of its own, `{workflow.implementation_artifacts}/evidence-<story_id>/`, which no step removes."
)
_GATE_REMOVAL = (
    "Once the commit is made, the escalation below is written, or nothing is staged, remove `.scratch-<story_id>/`: "
    "this is where `references/execute.md` step 0 has it removed, and the next story's step 0 must not find it."
)
_GATE_RESUME = (
    "A resume that finds `.scratch-<story_id>/` for a story whose row is already `done` removes it before the next "
    "story's step 0."
)
# Execute's resume rule loads gate.md only while the last advanced story's
# evidence is still uncommitted, so it removes a `done` row's folder itself.
_RESUME_REMOVAL = (
    "Before the next story's step 0, or before Stage 6 on that route, remove `.scratch-<story_id>/` of each story of "
    "this Epic whose row is already `done` (`references/gate.md`, \"Commit the gate's evidence before the next story "
    "starts\"): a run that stopped after that story's evidence commit, or with nothing staged for it, left the folder "
    "there."
)
# Its first wording, which sat between the owed-commit checks and the last
# story's route, so that route's "that story" and "the commit" read back to it.
_OLD_RESUME_REMOVAL = (
    "Then remove `.scratch-<story_id>/` of each story of this Epic whose row is already `done` (`references/gate.md`, "
    "\"Commit the gate's evidence before the next story starts\"): a run that stopped after that story's evidence "
    "commit, or with nothing staged for it, left the folder there, and the next story's step 0 must not find it."
)
# The five sentences that name the folder beside a remove verb, each exempt by
# its own text, so a removal added inside one makes it a sentence the scan lists.
_REMOVALS = (
    ("execute.md", _STEP0_REMOVAL),
    ("execute.md", _RULE_LEAD),
    ("execute.md", _RESUME_REMOVAL),
    ("gate.md", _GATE_REMOVAL),
    ("gate.md", _GATE_RESUME),
)


def _surfaces() -> dict[str, str]:
    """Every skill's SKILL.md and stage references, and the user docs."""
    skills = REPO / "skills"
    paths = [*sorted(skills.glob("*/SKILL.md")), *sorted(skills.glob("*/references/*.md")),
             *sorted((REPO / "docs").glob("*.md"))]
    texts = {}
    for path in paths:
        name = path.name if path.parent == REFS else path.relative_to(REPO).as_posix()
        texts[name] = path.read_text(encoding="utf-8")
    return texts


def _step0(execute: str) -> str:
    start = execute.index(_STEP0_START)
    end = execute.find("\n\n", start + 1)
    return execute[start:] if end == -1 else execute[start:end]


def _removal_sentences(texts: dict[str, str]) -> list[tuple[str, str]]:
    """Each sentence that names the scratch folder beside a remove verb."""
    found = set()
    for name, text in texts.items():
        candidates = [s for s in _SENTENCE.split(_flat(text)) if _SCRATCH.search(s)]
        if name == "execute.md" and _STEP0_START in text:
            candidates += [s for s in _SENTENCE.split(_flat(_step0(text))) if _THE_DIRECTORY.search(s)]
        found.update((name, s.strip()) for s in candidates if _REMOVE.search(s))
    return sorted(found)


def test_the_folder_is_removed_at_one_point_only():
    assert _removal_sentences(_surfaces()) == sorted(_REMOVALS)


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        # The first rule, restored in step 0.
        ("execute.md", _STEP0_REMOVAL, _STEP0_OLD_REMOVAL),
        # The first rule, added beside the new one by the folder's name.
        ("execute.md", None, "Remove `.scratch-<story_id>/` once step 5's re-verify goes green."),
        # The backfill's removal, restored.
        ("gate.md", "and leave `.scratch-<story_id>/` in place, the claim check's message files included:",
         "and remove `.scratch-<story_id>/` again: the claim check's message files recreated it, and"),
        # The backfill resume's removal, restored.
        ("gate.md", "with `HEAD` still `<sha>`, rebuild the worktree",
         "with `HEAD` still `<sha>`, remove `.scratch-<story_id>/` if it is still there, rebuild the worktree"),
        # A removal on another route or surface.
        ("gate.md", None, "On a `reloop`, delete `.scratch-<story_id>/` before the next cycle."),
        ("finalize.md", None, "Remove every `.scratch-*` folder once the Epic's verdict is logged."),
        ("skills/ultracode-goal/SKILL.md", None, "Drop the story's scratch folder once its sweep is green."),
        ("docs/operating-tips.md", None, "You can delete the scratch directory once step 5 is green."),
        # A removal added inside a sentence the scan exempts.
        ("gate.md", "or nothing is staged, remove `.scratch-<story_id>/`:",
         "or step 5's re-verify goes green, remove `.scratch-<story_id>/`:"),
        ("execute.md", "of each story of this Epic whose row is already `done` (",
         "of each story of this Epic, `done` or not, ("),
        # The resume rule's removal in its first wording, a sentence nobody listed.
        ("execute.md", _RESUME_REMOVAL, _OLD_RESUME_REMOVAL),
    ],
)
def test_the_scan_lists_a_removal_at_another_point(name, old, new):
    texts = _surfaces()
    if old is None:
        texts[name] += "\n\n" + new + "\n"
    else:
        assert texts[name].count(old) == 1, old
        texts[name] = texts[name].replace(old, new)
    assert _removal_sentences(texts) != sorted(_REMOVALS)


# --- step 0: kept until the advance route, and why ---------------------------------


def _step0_keeps_scratch_until_advance(execute: str) -> bool:
    try:
        step0 = _flat(_step0(execute))
    except ValueError:
        return False
    sentences = _SENTENCE.split(step0)
    return bool(
        _STEP0_OUTLIVES in sentences
        and _STEP0_REMOVAL in sentences
        and _STEP0_KEEP in sentences
        and sentences.index(_STEP0_OUTLIVES) < sentences.index(_STEP0_REMOVAL) < sentences.index(_STEP0_KEEP)
        and not re.search(r"after step 5's re-verify goes green", step0, re.I)
    )


def test_step0_keeps_the_folder_until_the_advance_route():
    assert _step0_keeps_scratch_until_advance(EXECUTE)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (_STEP0_REMOVAL, _STEP0_OLD_REMOVAL),
        (_STEP0_REMOVAL, _STEP0_REMOVAL + " Remove the directory after step 5's re-verify goes green, when no runner "
         "is left."),
        # The nothing-staged case dropped: a gitignored artifact tree leaves every story's folder behind.
        (", its `evidence-commit-rejected` escalation is written, or nothing is staged for it**",
         ", or its `evidence-commit-rejected` escalation is written**"),
        ("once its evidence commit is made, its `evidence-commit-rejected` escalation is written, or nothing is staged "
         "for it**", "once its evidence commit is made**"),
        # The verdicts that keep it, dropped or narrowed.
        (" " + _STEP0_KEEP, ""),
        ("A `reloop` or `escalate` verdict leaves it in place", "A `reloop` verdict leaves it in place"),
        # The reason narrowed back to step 5 alone.
        ("and the gate's backfill sweep, a cap-only re-loop's sweep and the step 5 a resume enters at (the third and "
         "fourth cases above) run it again without re-driving the story, ", ""),
        ("the step 5 a resume enters at (the third and fourth cases above)", "the step 5 the third case enters at"),
        # The rule moved out of step 0.
        (" " + _STEP0_REMOVAL, ""),
    ],
)
def test_step0_predicate_rejects_an_earlier_or_narrower_rule(old, new):
    mutant = EXECUTE.replace(old, new)
    assert mutant != EXECUTE, "the mutant must actually change the text"
    assert not _step0_keeps_scratch_until_advance(mutant)


def test_step0_cites_the_paragraph_that_removes_the_folder():
    cited = re.search(r'\(`references/gate\.md`, "([^"]+)"\)', _STEP0_REMOVAL).group(1)
    assert f"**{cited}.**" in GATE


def test_the_rewritten_step0_line_has_no_em_dash_left():
    """The removal rule shares one line with the rest of step 0, which held
    seven em dashes; `validate:em-dash --strict` reads the whole added line."""
    line = next(line for line in EXECUTE.splitlines() if line.startswith(_STEP0_START.lstrip("\n")))
    assert chr(0x2014) not in line


# --- the gate's advance route removes it ------------------------------------------

_EVIDENCE_COMMIT = "**Commit the gate's evidence before the next story starts.**"


def _gate_removes_scratch_on_the_advance_route(gate: str) -> bool:
    flat = _flat(gate)
    try:
        advance = flat.index("- **`advance`**")
        start = flat.index(_EVIDENCE_COMMIT, advance)
        end = flat.index("When **every story of the Epic", start)
    except ValueError:
        return False
    sentences = _SENTENCE.split(flat[start:end])
    return bool(
        _GATE_REMOVAL in sentences
        and _GATE_RESUME in sentences
        and sentences.index(_GATE_REMOVAL) + 1 == sentences.index(_GATE_RESUME)
    )


def test_the_advance_route_removes_the_folder_whatever_the_commit_does():
    assert _gate_removes_scratch_on_the_advance_route(GATE)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The old trigger: nothing staged, as on a gitignored artifact tree, left the folder.
        ("Once the commit is made, the escalation below is written, or nothing is staged,",
         "Once the commit is made, or the escalation below is written,"),
        # The old resume, which missed a run that stopped with nothing to commit.
        (_GATE_RESUME, "A resume that finds the folder left by a run that stopped after this commit removes it before "
         "the next story's step 0."),
        (" " + _GATE_RESUME, ""),
        # The removal dropped from the advance route.
        (" " + _GATE_REMOVAL, ""),
    ],
)
def test_advance_route_predicate_rejects_a_narrower_removal(old, new):
    flat = _flat(GATE)
    mutant = flat.replace(old, new)
    assert mutant != flat, "the mutant must actually change the text"
    assert not _gate_removes_scratch_on_the_advance_route(mutant)


def test_advance_route_predicate_rejects_the_removal_on_the_reloop_route():
    flat = _flat(GATE)
    moved = flat.replace(" " + _GATE_REMOVAL, "").replace(
        "- **`reloop`** (", "- **`reloop`** (" + _GATE_REMOVAL + " ", 1
    )
    assert moved != flat
    assert not _gate_removes_scratch_on_the_advance_route(moved)


# --- Execute's resume rule removes a `done` row's folder before step 0 ---------------
#
# The resume rule reads gate.md's evidence-commit paragraph only while the last
# advanced story's evidence is still uncommitted. A run that stopped after that
# commit, or with nothing staged, before the removal, never reaches gate.md's
# resume sentence, so the rule says it itself, before the next story's step 0 or
# before Stage 6 on the last story's route. It sits after that route: the
# route's "that story" and "the commit" read back to the owed-commit checks, so
# a sentence between them about every `done` row would be what they name.

_RESUME_RULE = "**On resume, re-enter Execute at the first story whose last logged gate verdict is not advance;"
_OWED_CHECK = (
    "Before the next story's step 0, also check whether the last advanced story's gate evidence is still uncommitted"
)
_EVERY_MARKER = "Check every `.evidence-owed-<story_id>` of this Epic's stories this way"
_LAST_STORY = "When that story is the Epic's last, so every story reads `done`"
_LAST_ROUTE_END = "Stage 1 resolved no in-scope story for that resume"
# The sentence after the hooks assertion, which itself follows the removal.
_PAST_HOOKS_ASSERTION = "A presence-only read passes on a prior run's"
_EVIDENCE_FOLDER = re.compile(r"`evidence-<story_id>/`")


def _resume_rule_removes_a_done_rows_scratch(execute: str) -> bool:
    if execute.count(_RESUME_RULE) != 1:
        return False
    sentences = _SENTENCE.split(_flat(execute[execute.index(_RESUME_RULE) :].split("\n\n")[0]))

    def at(prefix: str) -> int:
        return next((i for i, s in enumerate(sentences) if s.startswith(prefix)), -1)

    owed, every, last, route_end = at(_OWED_CHECK), at(_EVERY_MARKER), at(_LAST_STORY), at(_LAST_ROUTE_END)
    removal = sentences.index(_RESUME_REMOVAL) if _RESUME_REMOVAL in sentences else -1
    return bool(
        -1 not in (owed, every, last, route_end, removal)
        # The owed-commit checks run straight into the last story's route, which
        # the removal follows: after the owed evidence commit, whose message file
        # recreates the folder, and before Stage 6 on that route.
        and owed < every and last == every + 1 and route_end == last + 1 and removal == route_end + 1
        and not any(_EVIDENCE_FOLDER.search(s) and _REMOVE.search(s) for s in sentences)
    )


def test_the_resume_rule_removes_a_done_rows_folder_before_step0():
    assert _resume_rule_removes_a_done_rows_scratch(EXECUTE)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The pre-fix text: the removal lived only in gate.md, which this resume never loads.
        (" " + _RESUME_REMOVAL, ""),
        # Narrowed back to the one story whose owed commit loads gate.md.
        ("of each story of this Epic whose row is already `done`", "of the last advanced story"),
        # The nothing-staged case dropped: a gitignored artifact tree makes no commit to stop after.
        (", or with nothing staged for it,", ""),
        # The evidence folder removed beside it, which the story record and the gate trail still cite.
        (_RESUME_REMOVAL, _RESUME_REMOVAL + " Remove `evidence-<story_id>/` too, since no later step reads it."),
        # The last story's route dropped: Stage 6 would start with that folder still there.
        ("Before the next story's step 0, or before Stage 6 on that route, remove",
         "Before the next story's step 0, remove"),
        # The next story's step 0 dropped, which must not find the folder.
        ("Before the next story's step 0, or before Stage 6 on that route, remove", "Before Stage 6 on that route, remove"),
        # A sentence put between the last story's route and the removal, so "that route" names another.
        (_RESUME_REMOVAL, "Log the route taken. " + _RESUME_REMOVAL),
    ],
)
def test_resume_predicate_rejects_a_narrower_or_wider_removal(old, new):
    mutant = EXECUTE.replace(old, new)
    assert mutant != EXECUTE, "the mutant must actually change the text"
    assert not _resume_rule_removes_a_done_rows_scratch(mutant)


@pytest.mark.parametrize(
    ("anchor", "sentence"),
    [
        # Back between the owed-commit checks and the last story's route, where
        # that route's "that story" and "the commit" read back to it, in either wording.
        (_LAST_STORY, _RESUME_REMOVAL),
        (_LAST_STORY, _OLD_RESUME_REMOVAL),
        # Inside the last story's route, between its two sentences.
        (_LAST_ROUTE_END, _RESUME_REMOVAL),
        # Ahead of the owed evidence commit, whose message file recreates the folder.
        (_OWED_CHECK, _RESUME_REMOVAL),
        # Past the hooks assertion, away from the route its "that route" names.
        (_PAST_HOOKS_ASSERTION, _RESUME_REMOVAL),
        # Into step 0, beside the advance route's rule, which a resume past that commit never meets.
        (_STEP0_REMOVAL, _RESUME_REMOVAL),
        # Into the fourth case, a paragraph of its own.
        ("**A fourth case:", _RESUME_REMOVAL),
    ],
)
def test_resume_predicate_rejects_the_removal_moved_elsewhere(anchor, sentence):
    cut = EXECUTE.replace(" " + _RESUME_REMOVAL, "")
    assert cut != EXECUTE and cut.count(anchor) == 1, anchor
    moved = cut.replace(anchor, sentence + " " + anchor, 1)
    assert not _resume_rule_removes_a_done_rows_scratch(moved)


def test_the_resume_rule_cites_the_paragraph_that_removes_a_done_rows_folder():
    cited = re.search(r'\(`references/gate\.md`, "([^"]+)"\)', _RESUME_REMOVAL).group(1)
    gate = _flat(GATE)
    heading = f"**{cited}.**"
    assert gate.count(heading) == 1
    assert _GATE_RESUME in gate[gate.index(heading) : gate.index("When **every story of the Epic", gate.index(heading))]


# --- the fourth resume case re-measures with any runner, or re-authors it ------------

_FOURTH_CASE = "**A fourth case: a closed `operator-evidence-owed` story owes a re-gate, not a re-drive.**"
# Most stories build no runner, and the folder is always there by then (step
# 4's claim check writes its message file in it), so the case presumes neither.
_RUNNER = (
    "re-measuring `HEAD` at step 5 with any runner or harness the escalated cycle built in `.scratch-<story_id>/` "
    "(step 0 keeps that directory until the story advances), then re-gating it in Stage 5"
)
# Whether the cycle built one cannot be told once the folder is gone, since no
# step logs it, so the fallback is keyed on the folder alone and re-authors what
# the declared gate set needs.
_FALLBACK = (
    "When that directory is gone (a run under an earlier rule removed it at step 5, or an operator did), re-author any "
    "runner or harness the story's declared gate set needs before step 5 runs."
)
# Its first wording, conditioned on what the cycle built, which nothing records.
_OLD_FALLBACK = (
    "When the cycle built one there and that directory is gone (a run under an earlier rule removed it at step 5, or "
    "an operator did), re-author it for the story's declared gate set before step 5 runs."
)
_FALLBACK_CHECK = (
    "Check it against the gates the escalated cycle's step-5 capture in `evidence-<story_id>/` names, when that folder "
    "holds one, so the re-gate measures the gate set that cycle measured."
)


def _fourth_case_names_its_runner(execute: str) -> bool:
    if execute.count(_FOURTH_CASE) != 1:
        return False
    paragraph = _flat(execute[execute.index(_FOURTH_CASE) :].split("\n\n")[0])
    sentences = _SENTENCE.split(paragraph)
    runner = next((i for i, s in enumerate(sentences) if _RUNNER in s), -1)
    return bool(
        runner != -1
        and sentences[runner + 1 : runner + 3] == [_FALLBACK, _FALLBACK_CHECK]
    )


def test_the_fourth_case_re_measures_with_the_cycles_runner():
    assert _fourth_case_names_its_runner(EXECUTE)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The pre-fix text: a step 5 with no runner named, and no fallback.
        (" with any runner or harness the escalated cycle built in `.scratch-<story_id>/` (step 0 keeps that directory "
         "until the story advances)", ""),
        (" " + _FALLBACK + " " + _FALLBACK_CHECK, ""),
        (" " + _FALLBACK_CHECK, ""),
        # The first wording, which presumed a runner every story left behind.
        ("with any runner or harness the escalated cycle built in", "with the runner the escalated cycle left in"),
        ("any runner or harness the escalated cycle built", "any runner the escalated cycle built"),
        # The fallback conditioned on what the cycle built, which no step logs, in its first wording or in part.
        (_FALLBACK, _OLD_FALLBACK),
        ("When that directory is gone", "When the cycle built one there and that directory is gone"),
        ("re-author any runner or harness the story's declared gate set needs",
         "re-author any runner or harness the escalated cycle built"),
        # The fallback narrowed to a runner alone, or to the one runner a story is presumed to have.
        ("re-author any runner or harness the story's declared gate set needs",
         "re-author any runner the story's declared gate set needs"),
        ("re-author any runner or harness the story's declared gate set needs",
         "re-author the runner for the story's declared gate set"),
        # A fallback that restores a runner from the evidence folder, which holds nothing runnable.
        ("re-author any runner or harness the story's declared gate set needs",
         "restore any runner or harness from `evidence-<story_id>/`"),
        ("when that folder holds one, ", ""),
        # The fallback moved into a paragraph of its own, which a reader of the fourth case never reaches.
        (" " + _FALLBACK, "\n\n" + _FALLBACK),
    ],
)
def test_fourth_case_predicate_rejects_a_case_with_no_runner(old, new):
    mutant = EXECUTE.replace(old, new)
    assert mutant != EXECUTE, "the mutant must actually change the text"
    assert not _fourth_case_names_its_runner(mutant)


# --- the backfill and its resume leave it in place ----------------------------------

_BACKFILL_LEAVE = (
    "and leave `.scratch-<story_id>/` in place, the claim check's message files included: `references/execute.md` "
    "step 0 keeps it until the story advances, since a cap-only re-loop or a re-gate of this story may still run its "
    "sweep."
)


def _between(text: str, start: str, end: str) -> str:
    at = text.index(start)
    return text[at : text.index(end, at)]


def _backfill_leaves_scratch(gate: str) -> bool:
    flat = _flat(gate)
    try:
        backfill = _between(flat, "**When automate backfills, commit the backfill before trace runs.**",
                            "**A red backfill sweep ends the cycle at a re-loop.**")
        resume = _between(flat, "**A resume after a backfill does not run automate again.**",
                          "At any other `HEAD`, the story is not in this case")
    except ValueError:
        return False
    removals = [
        s for s in _SENTENCE.split(backfill + " " + resume) if _SCRATCH.search(s) and _REMOVE.search(s)
    ]
    return _BACKFILL_LEAVE in backfill and not removals


def test_the_backfill_and_its_resume_leave_the_folder():
    assert _backfill_leaves_scratch(GATE)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("and leave `.scratch-<story_id>/` in place, the claim check's message files included: `references/execute.md` "
         "step 0 keeps it until the story advances, since a cap-only re-loop or a re-gate of this story may still run "
         "its sweep.",
         "and remove `.scratch-<story_id>/` again: the claim check's message files recreated it, and "
         "`references/execute.md` step 0 has it removed before the story advances."),
        ("with `HEAD` still `<sha>`, rebuild the worktree",
         "with `HEAD` still `<sha>`, remove `.scratch-<story_id>/` if it is still there, rebuild the worktree"),
        (", since a cap-only re-loop or a re-gate of this story may still run its sweep", ""),
    ],
)
def test_backfill_predicate_rejects_a_removal_before_trace(old, new):
    flat = _flat(GATE)
    mutant = flat.replace(old, new)
    assert mutant != flat, "the mutant must actually change the text"
    assert not _backfill_leaves_scratch(mutant)


FRAGMENT = (REPO / "changes" / "scratch-kept-until-advance.yaml").read_text(encoding="utf-8")


def test_the_fragment_says_when_the_folder_goes():
    assert re.search(r"^type: changed$", FRAGMENT, re.M)
    assert re.search(r"^issues: \[206\]$", FRAGMENT, re.M)
    for token in ("`.scratch-<story_id>/`", "`operator-evidence-owed`", "`reloop`", "`escalate`",
                  "`evidence-commit-rejected`"):
        assert token in FRAGMENT, token


_FRAGMENT_FALLBACK = (
    "and when the folder is gone, re-authors any runner or harness the story's declared gate set needs and checks it "
    "against the gates named by the escalated cycle's step-5 capture in `evidence-<story_id>/`."
)


def _fragment_keys_the_fallback_on_the_folder(fragment: str) -> bool:
    flat = _flat(fragment)
    return _FRAGMENT_FALLBACK in flat and "when it built one" not in flat


def test_the_fragment_keys_the_fourth_cases_fallback_on_the_folder_alone():
    assert _fragment_keys_the_fallback_on_the_folder(FRAGMENT)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # Its first wording, conditioned on what the cycle built, which no step logs.
        ("and when the folder is gone, re-authors any runner or harness the story's declared gate set needs",
         "and when it built one and the folder is gone, re-authors it for the story's declared gate set"),
        ("and when the folder is gone,", "and when it built one and the folder is gone,"),
    ],
)
def test_fragment_predicate_rejects_a_fallback_conditioned_on_what_was_built(old, new):
    mutant = FRAGMENT.replace(old, new)
    assert mutant != FRAGMENT, "the mutant must actually change the text"
    assert not _fragment_keys_the_fallback_on_the_folder(mutant)
