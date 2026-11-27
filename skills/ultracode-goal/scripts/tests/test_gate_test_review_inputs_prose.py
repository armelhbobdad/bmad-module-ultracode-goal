#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for what the test reviewer is handed (issue #283).

In production, `gate_eval.py` downgrades an `advance` to `reloop` when the
`test-review.md` Quality Score is below 80 or its Recommendation is `Block`,
and it reads that score as written: it cannot see what the reviewer was given.
The stage text said when `bmad-testarch-test-review` runs (Execute step 3, or
the gate after a backfill), which tree it reads and that it may not edit, but
not what it may read. A delegation could hand the reviewer the run's rulings,
`.decision-log.md` or an earlier review of the same story, and a reviewer told
that a construct was already accepted can score the same tests above the
threshold where a review of the tests alone scored them below it.

`references/gate.md` now bounds the reviewer's inputs in "Backfill the gate
evidence": the tree it reviews, the story's acceptance criteria and their
priorities, copied out of the story file rather than the file itself (for a
decomposed child, the parent ACs its sprint-status row claims), the story's
diff from its baseline, and the three records `references/execute.md` already
surfaces into a review's context (the story's mutation ledger, the Epic's class
ledger and each Operator notes entry given before launch that names the story),
and nothing else the run wrote, a ruling logged during the run as an Operator
notes entry included. The reviewer is told that nothing it was handed waives a
finding, lowers a severity or raises a score. The instructions the gate gives
every assessor still go in its brief. A delta gate's concerns-only re-check is
named as the one place a reviewer reads its own earlier artifact, and that gate
is capped at `reloop`. TEA's test review adds to a report already at the path
it writes, so every other test review first moves the story's earlier review
aside into its evidence folder. Execute step 3, where the review normally
runs, points at the rule.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the pre-edit text and one-clause mutants it must reject. The rule is
also pinned whole, so a sentence added anywhere in it fails. The list of kept
records is also checked against the sentences of execute.md and
ingest-and-scope.md that surface records into a review's context, so a record
added there in the same "surface ... into ... context" wording (a dotted file
name included) without the rule shows up here. A record ordered to a review in
other words does not: the one such order today, the mutation ledger's "a story
artifact the reviewers read", is counted on its own. Stated limit: this is a
presence proof over prose. It shows the instruction is in the files, not that
a conductor obeys it.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REFERENCES = Path(__file__).resolve().parents[2] / "references"
GATE = (_REFERENCES / "gate.md").read_text(encoding="utf-8")
EXECUTE = (_REFERENCES / "execute.md").read_text(encoding="utf-8")
INGEST = (_REFERENCES / "ingest-and-scope.md").read_text(encoding="utf-8")

_HEAD = "**The test reviewer reads the tests, not the run's account of them.**"
_CITED = '"The test reviewer reads the tests, not the run\'s account of them"'
_DELTA_HEAD = "**The delta cycle profile (`--cycle-profile`, mid-loop gates, production).**"
_SERVER_HEAD = "- **A server the gate set reuses does not follow the commit.**"
_MOVED_AC_HEAD = "**After a move, check that trace scored no moved AC, in either profile.**"
_EVIDENCE_HEAD = "**Evidence never goes in scratch.**"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def _backfill_section(text: str = GATE) -> str:
    return _section(text, "## Backfill the gate evidence")


def _paragraph(text: str, opener: str) -> str:
    """The paragraph that opens with `opener`, or "" when `text` has none."""
    start = text.find(opener)
    if start == -1:
        return ""
    end = text.find("\n\n", start)
    return text[start : end if end != -1 else len(text)]


def _rule(text: str = GATE) -> str:
    return _paragraph(_backfill_section(text), _HEAD)


def _step3(text: str = EXECUTE) -> str:
    start = text.index("\n3. **Production profile only:**")
    return text[start + 1 : text.index("\n4. ", start)]


# --- the bound on what the reviewer is handed ----------------------------------

# The handed list is pinned as one sentence, with the two sentences on the
# criteria after it, through the start of the exclusion list, so text added at a
# join between two of its clauses changes it.
_HANDED = (
    "When you delegate `bmad-testarch-test-review`, here or at `references/execute.md`'s step 3, hand it the tree "
    "it reviews (the gate worktree here), the story's acceptance criteria and their priorities, the story's diff "
    "from its baseline, and what Execute already surfaces to a review: the story's mutation ledger, the Epic's class "
    "ledger and each Operator notes entry given before launch that names the story (`references/ingest-and-scope.md`, "
    '"Operator notes"). Hand it the criteria themselves, copied out of the story file, and not the file: its Dev '
    "Agent Record, its completion notes and any review section in it are the run's account of the work. For a "
    "decomposed child, they are the parent ACs its sprint-status row claims. Hand it nothing else the run wrote:"
)
_EXCLUDED = (
    " not a story file, not `.decision-log.md` or any other slice of it, not a ruling made during the run, one "
    "logged as an Operator notes entry included, not a scratch note, not an earlier cycle's verdict or its "
    "`reasons`, not an earlier test review or code review of this story, and not your own summary of any of these. "
    "Tell it to open none of them, and that nothing it was handed waives a finding, lowers a severity or raises a "
    "score: what it reads beyond the tests can add a finding and never removes one."
)
_BOUND = (
    _HEAD + " `gate_eval.py` reads the review's score as written, so what the reviewer was handed decides a verdict. "
    + _HANDED
    + _EXCLUDED
)


def _bounds_the_reviewer(section: str) -> bool:
    """The section holds the rule, and the rule opens with a closed list of
    inputs for both places the review runs, excludes each record of the run,
    and says that nothing handed can raise a score."""
    return _flat(_paragraph(section, _HEAD)).startswith(_BOUND)


def test_gate_bounds_what_the_test_reviewer_is_handed():
    assert _bounds_the_reviewer(_backfill_section())


# The sentences of the backfill section that spoke of the test review before
# the edit. They still stand: the rule is added beside them.
_PRE_EDIT_SENTENCES = (
    "None of the three may edit a file in the worktree, so none of them runs a mutant: an assessor that would probe "
    "one names the mutant it would run as a finding in its own artifact instead, and when you delegate NFR or test "
    "review, tell it so. `gate_eval.py` reads the three as files and checks neither their order nor their author, "
    "which is why the paragraphs below bind how each is made. "
    "(`bmad-testarch-test-review` normally runs in Execute per story: run it here only if you lack a current "
    "`test-review.md` for the story. One written before automate's backfill is not current, since no review has "
    "read the tests the backfill added.)"
)
_PRE_EDIT_SECTION = "## Backfill the gate evidence (production only)\n\n" + _PRE_EDIT_SENTENCES


def test_bound_predicate_rejects_the_pre_edit_section():
    assert not _bounds_the_reviewer(_PRE_EDIT_SECTION)
    assert _PRE_EDIT_SENTENCES in _backfill_section()


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("Hand it nothing else the run wrote:", "Hand it what helps, except:", id="open-list"),
        pytest.param("not a story file, ", "", id="story-file-handed"),
        pytest.param(
            "Hand it the criteria themselves, copied out of the story file, and not the file: its Dev Agent Record, "
            "its completion notes and any review section in it are the run's account of the work. ",
            "",
            id="criteria-from-the-file",
        ),
        pytest.param("For a decomposed child, they are the parent ACs its sprint-status row claims. ", "",
                     id="child-gets-the-siblings"),
        pytest.param("not `.decision-log.md` or any other slice of it, ", "", id="decision-log-handed"),
        pytest.param("or any other slice of it", "or a slice of it", id="note-is-a-slice"),
        pytest.param("not a ruling made during the run, one logged as an Operator notes entry included, ", "",
                     id="rulings-handed"),
        pytest.param(", one logged as an Operator notes entry included", "", id="mid-run-note-handed"),
        pytest.param("not a scratch note, ", "", id="scratch-handed"),
        pytest.param("not an earlier cycle's verdict or its `reasons`, ", "", id="earlier-verdict-handed"),
        pytest.param("not an earlier test review or code review of this story, ", "", id="earlier-reviews-handed"),
        pytest.param(", and not your own summary of any of these.", ".", id="summary-handed"),
        pytest.param("Tell it to open none of them, and that", "Tell it that", id="may-open-them"),
        pytest.param(
            "nothing it was handed waives a finding, lowers a severity or raises a score",
            "what it was handed may waive a finding the run already accepted",
            id="may-waive",
        ),
        pytest.param("lowers a severity or raises a score", "lowers a severity", id="may-raise"),
        pytest.param("can add a finding and never removes one", "can add or remove a finding", id="may-remove"),
        pytest.param(", here or at `references/execute.md`'s step 3,", " here,", id="gate-only"),
        # Text added at a join between two clauses of the handed list.
        pytest.param(
            "the story's diff from its baseline, and what Execute",
            "the story's diff from its baseline, the run's rulings, and what Execute",
            id="widened-at-the-ledger-join",
        ),
        pytest.param("step 3, hand it the tree", "step 3, hand it `.decision-log.md`, the tree",
                     id="widened-after-hand-it"),
        pytest.param('"Operator notes"). Hand it', '"Operator notes"). Hand it `.decision-log.md` too. Hand it',
                     id="sentence-after-the-kept-records"),
    ],
)
def test_bound_predicate_rejects_a_one_clause_mutant(old, new):
    section = _backfill_section()
    mutant = _flat(section).replace(old, new)
    assert mutant != _flat(section), "the mutant must actually change the text"
    assert not _bounds_the_reviewer(mutant)


def test_bound_predicate_rejects_the_rule_moved_out_of_the_backfill_section():
    rule = _rule()
    moved = GATE.replace(rule + "\n\n", "", 1)
    moved = moved.replace("## Run the gate\n", "## Run the gate\n\n" + rule + "\n", 1)
    assert moved != GATE
    assert not _bounds_the_reviewer(_backfill_section(moved))
    # Every clause still reads in the moved text: only the placement fails.
    assert _bounds_the_reviewer(_section(moved, "## Run the gate"))


def test_rule_names_the_decomposed_childs_criteria_as_trace_does():
    """The child's criteria are the ones trace scores for it: the parent ACs its
    sprint-status row claims, not the siblings' in the same parent file."""
    assert "the parent AC ids the child's sprint-status row claims, as the only criteria trace scores" in _flat(GATE)


# --- the records Execute already surfaces stay handed ---------------------------

_KEPT = (
    "and what Execute already surfaces to a review: the story's mutation ledger, the Epic's class ledger and each "
    "Operator notes entry given before launch that names the story (`references/ingest-and-scope.md`, "
    '"Operator notes").'
)


def _keeps_what_execute_surfaces(rule: str) -> bool:
    return _KEPT in _flat(rule)


# A record's path holds a dot (`.decision-log.md`), so a dot followed by no
# space does not end the clause.
_SURFACING = re.compile(r"\bsurfac\w*\b(?:[^.]|\.(?!\s)){0,160}?\binto\b(?:[^.]|\.(?!\s)){0,80}?context")


def _surfaced(text: str) -> list[str]:
    """Every clause that surfaces a record into a review's context, in that wording."""
    return _SURFACING.findall(text)


def test_rule_keeps_the_records_execute_surfaces():
    assert _keeps_what_execute_surfaces(_rule())
    # The list matches the sentences that order those records into a review's
    # context: the Operator note and the class ledger at step 1, the mutation
    # ledger into step 3's test review, and the Operator notes definition.
    assert _surfaced(EXECUTE) == [
        "surface that note into the `ucg-dev-story` / review context",
        "surface it into the same context",
        "surface it into the step-3 test-review context",
    ]
    assert "check the run's `.decision-log.md` for an **Operator notes** entry naming this story" in EXECUTE
    assert re.search(
        r"Read `\{workflow\.implementation_artifacts\}/\.class-ledger-<epic_id>\.md` the same way", EXECUTE
    )
    assert re.search(r"mutation-ledger-<story_id>\.md`.{0,240}?surface it into the step-3 test-review context", EXECUTE)
    assert _surfaced(INGEST) == ["surfaces the relevant note into that story's `ucg-dev-story` / review context"]
    # The one order in other words: the mutation ledger, already kept.
    assert EXECUTE.count("the reviewers read") == 1
    assert "the generated ledger is a story artifact the reviewers read" in EXECUTE
    assert "the reviewers read" not in INGEST


def test_the_kept_operator_notes_are_the_pre_launch_ones():
    """Ingest records the pre-launch notes as named Operator notes entries, and
    the gate logs an in-session ruling the same way, so the rule keeps only the
    entries given before launch."""
    assert "record each as a named **Operator notes** entry in `.decision-log.md`" in INGEST
    assert "logging their in-session ruling as a named Operator notes entry in `.decision-log.md`" in _flat(GATE)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(
            "the story's mutation ledger, the Epic's class ledger and each Operator notes entry",
            "the Epic's class ledger and each Operator notes entry",
            id="mutation-ledger-dropped",
        ),
        pytest.param(
            "the story's mutation ledger, the Epic's class ledger and each Operator notes entry",
            "the story's mutation ledger and each Operator notes entry",
            id="class-ledger-dropped",
        ),
        pytest.param(
            "the Epic's class ledger and each Operator notes entry given before launch that names the story "
            '(`references/ingest-and-scope.md`, "Operator notes").',
            "and the Epic's class ledger.",
            id="operator-note-dropped",
        ),
        pytest.param("each Operator notes entry given before launch that names the story",
                     "every Operator notes entry", id="any-operator-note"),
        pytest.param("each Operator notes entry given before launch that names", "each Operator notes entry that names",
                     id="mid-run-operator-note"),
    ],
)
def test_kept_records_predicate_rejects_a_list_without_them(old, new):
    rule = _flat(_rule())
    mutant = rule.replace(old, new)
    assert mutant != rule, "the mutant must actually change the text"
    assert not _keeps_what_execute_surfaces(mutant)


@pytest.mark.parametrize(
    "added",
    [
        pytest.param("surface the run's rulings into the same context", id="rulings"),
        pytest.param("surface `.decision-log.md` into the step-3 test-review context", id="dotted-path"),
    ],
)
def test_surfacing_list_rejects_a_record_added_to_the_review_context(added):
    old = "surface it into the same context:"
    mutant = EXECUTE.replace(old, "surface it into the same context, and " + added + ":", 1)
    assert mutant != EXECUTE
    assert len(_surfaced(mutant)) == len(_surfaced(EXECUTE)) + 1


# --- the assessor's brief still goes ---------------------------------------------

_BRIEF = (
    "The instructions this file gives every assessor are not records of the run and still go in its brief, among "
    "them that it edits no file and runs no mutant (above), and the runner config and server brief that \"A server "
    "the gate set reuses does not follow the commit\" (below) sets."
)


def _keeps_the_assessor_brief(rule: str) -> bool:
    return _BRIEF in _flat(rule)


def test_rule_keeps_the_instructions_every_assessor_is_given():
    assert _keeps_the_assessor_brief(_rule())
    # What it points at: the no-mutant instruction above it in the section, and
    # the server caveat below, which tells every assessor what to run with.
    flat = _flat(_backfill_section())
    assert flat.index("and when you delegate NFR or test review, tell it so.") < flat.index(_BRIEF)
    server = _flat(_paragraph(_section(GATE, "## Measure the commit, not the working tree"), _SERVER_HEAD))
    assert "Tell every assessor to run the runner with it" in server
    assert "tell every assessor, automate included, in its brief, which URL answers" in server


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_BRIEF + " ", "", id="dropped"),
        pytest.param("and still go in its brief", "and stay out of its brief", id="left-out"),
        pytest.param(", and the runner config and server brief that \"A server the gate set reuses does not follow "
                     "the commit\" (below) sets.", ".", id="server-brief-dropped"),
        pytest.param("that it edits no file and runs no mutant (above), and ", "", id="no-mutant-dropped"),
    ],
)
def test_brief_predicate_rejects_a_rule_that_drops_the_instructions(old, new):
    rule = _flat(_rule())
    mutant = rule.replace(old, new)
    assert mutant != rule, "the mutant must actually change the text"
    assert not _keeps_the_assessor_brief(mutant)


def test_brief_predicate_rejects_the_pre_edit_section():
    assert not _keeps_the_assessor_brief(_PRE_EDIT_SECTION)


# --- the delta re-check is the one reader of an earlier review -------------------

_DELTA_READER = (
    "A delta gate's concerns-only re-check (\"The delta cycle profile\", under \"Run the gate\") is the one place a "
    "reviewer reads its own earlier artifact, with the diff from the previous gate's `assessed-commit` line to the "
    "commit under assessment, and that gate's verdict is capped at `reloop`."
)


def _names_the_delta_reader(rule: str) -> bool:
    return _DELTA_READER in _flat(rule)


def test_rule_names_the_delta_recheck_as_the_one_reader_of_an_earlier_review():
    assert _names_the_delta_reader(_rule())
    # The cited paragraph exists under that section and says what the rule
    # says of it.
    delta = _flat(_paragraph(_section(GATE, "## Run the gate"), _DELTA_HEAD))
    assert (
        "the others verify their own prior artifact against the diff from the previous gate's `assessed-commit` "
        "line to the commit under assessment" in delta
    )
    assert "(a concerns-only re-check;" in delta
    assert "the script caps the verdict at `reloop`" in delta


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(", and that gate's verdict is capped at `reloop`.", ".", id="uncapped"),
        pytest.param("is the one place a reviewer", "is one place a reviewer", id="not-the-only-reader"),
        pytest.param(" (\"The delta cycle profile\", under \"Run the gate\")", "", id="uncited"),
        pytest.param(", with the diff from the previous gate's `assessed-commit` line to the commit under assessment",
                     "", id="no-diff"),
    ],
)
def test_delta_predicate_rejects_an_uncapped_or_widened_reader(old, new):
    rule = _flat(_rule())
    mutant = rule.replace(old, new)
    assert mutant != rule, "the mutant must actually change the text"
    assert not _names_the_delta_reader(mutant)


# --- an earlier review is moved aside before a new one ---------------------------

_MOVE_ASIDE = (
    "TEA adds each step's output to a test review already at the path it writes, rather than starting a new one. "
    "So before every test review but that re-check, move the story's earlier `test-review-<story_id>.md`, when "
    "there is one, aside into `{workflow.implementation_artifacts}/evidence-<story_id>/`, under its own name with "
    "`-cycle-<n>` before its extension, `<n>` the first number from 1 that no file there carries yet."
)


def _moves_the_earlier_review_aside(rule: str) -> bool:
    """The rule moves an earlier review out of the path TEA writes, into the
    folder no step removes, without overwriting one, before every review but
    the delta re-check, which reads it."""
    flat = _flat(rule)
    if _MOVE_ASIDE not in flat or _DELTA_READER not in flat:
        return False
    # "that re-check" points back at the delta sentence, so the move follows it.
    return flat.index(_DELTA_READER) < flat.index(_MOVE_ASIDE)


def test_rule_moves_the_earlier_review_aside():
    assert _moves_the_earlier_review_aside(_rule())


def test_move_aside_follows_the_evidence_folder_conventions():
    # The folder is Execute's, which no step removes.
    evidence = _flat(_paragraph(EXECUTE, _EVIDENCE_HEAD))
    assert "`{workflow.implementation_artifacts}/evidence-<story_id>/`, which no step removes." in evidence
    # The name is the one the moved-AC check gives trace's earlier files there.
    moved_ac = _flat(_paragraph(_section(GATE, "## Run the gate"), _MOVED_AC_HEAD))
    assert (
        "into `{workflow.implementation_artifacts}/evidence-<story_id>/`, each under its own name with `-cycle-<n>` "
        "before its extension, `<n>` the first number from 1 that no file there carries yet" in moved_ac
    )
    # The per-story name the gate gives the review.
    assert "`test-review-<id>.md`" in _flat(GATE)


def test_move_aside_predicate_rejects_the_pre_edit_section():
    assert not _moves_the_earlier_review_aside(_PRE_EDIT_SECTION)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(" " + _MOVE_ASIDE, "", id="dropped"),
        pytest.param(
            " So before every test review but that re-check, move the story's earlier `test-review-<story_id>.md`, "
            "when there is one, aside into `{workflow.implementation_artifacts}/evidence-<story_id>/`, under its own "
            "name with `-cycle-<n>` before its extension, `<n>` the first number from 1 that no file there carries "
            "yet.",
            "",
            id="move-dropped",
        ),
        pytest.param("before every test review but that re-check", "before every test review", id="re-check-too"),
        pytest.param("before every test review but that re-check", "before a re-loop's review", id="re-loop-only"),
        pytest.param("`{workflow.implementation_artifacts}/evidence-<story_id>/`",
                     "`{workflow.implementation_artifacts}/.scratch-<story_id>/`", id="into-scratch"),
        pytest.param(", under its own name with `-cycle-<n>` before its extension, `<n>` the first number from 1 that "
                     "no file there carries yet.", ".", id="overwrites"),
    ],
)
def test_move_aside_predicate_rejects_a_one_clause_mutant(old, new):
    rule = _flat(_rule())
    mutant = rule.replace(old, new)
    assert mutant != rule, "the mutant must actually change the text"
    assert not _moves_the_earlier_review_aside(mutant)


def test_move_aside_predicate_rejects_the_move_placed_before_the_re_check_it_excepts():
    rule = _flat(_rule())
    mutant = rule.replace(" " + _MOVE_ASIDE, "").replace(" " + _DELTA_READER, " " + _MOVE_ASIDE + " " + _DELTA_READER)
    assert mutant != rule and _MOVE_ASIDE in mutant and _DELTA_READER in mutant
    assert not _moves_the_earlier_review_aside(mutant)


# --- the rule holds these sentences and nothing else ----------------------------


def _rule_is_whole(rule: str) -> bool:
    return _flat(rule).strip() == " ".join((_BOUND, _BRIEF, _DELTA_READER, _MOVE_ASIDE))


def test_rule_holds_nothing_else():
    assert _rule_is_whole(_rule())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_MOVE_ASIDE, _MOVE_ASIDE + " A summary of the run's rulings may go with it.", id="appended"),
        pytest.param(_BRIEF, _BRIEF + " So may the decision log.", id="after-the-brief"),
    ],
)
def test_whole_rule_predicate_rejects_an_added_sentence(old, new):
    rule = _flat(_rule())
    mutant = rule.replace(old, new)
    assert mutant != rule, "the mutant must actually change the text"
    assert not _rule_is_whole(mutant)


# --- Execute step 3 points at the rule ------------------------------------------

_POINTER = (
    "Hand the test reviewer only what `references/gate.md`'s " + _CITED + " lists, and move the story's earlier "
    "review aside as it says, on a re-loop's review too: unless the gate runs a test review of its own, it reads "
    "this one's score."
)


def _step3_points_at_the_rule(step: str) -> bool:
    flat = _flat(step)
    return flat.startswith("3. **Production profile only:** `bmad-testarch-test-review`") and _POINTER in flat


def test_execute_step_3_points_at_the_rule():
    assert _step3_points_at_the_rule(_step3())
    # The name step 3 cites is the rule's opener, in the backfill section.
    assert _HEAD == "**" + _CITED.strip('"') + ".**"
    assert _HEAD in _backfill_section()


_PRE_EDIT_STEP_3 = (
    "3. **Production profile only:** `bmad-testarch-test-review`, then `bmad-code-review`. A `CONCERNS`-grade or "
    "non-critical finding appends to `{workflow.deferred_work_path}` and the story proceeds. A **P0 / critical FAIL "
    "never defers** \u2014 re-loop within the turn budget or escalate."
)


def test_step_3_predicate_rejects_the_pre_edit_step():
    assert not _step3_points_at_the_rule(_PRE_EDIT_STEP_3)
    # The step's own text still opens it; the edit only replaced its dash.
    assert _step3().startswith(_PRE_EDIT_STEP_3.replace("** \u2014 re-loop", "**: re-loop") + " ")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(", on a re-loop's review too:", ":", id="first-review-only"),
        pytest.param(_CITED, '"The delta cycle profile"', id="cites-another-paragraph"),
        pytest.param("Hand the test reviewer only what", "Hand the test reviewer at least what", id="open-list"),
        pytest.param(", and move the story's earlier review aside as it says", "", id="no-move-aside"),
        # Only one test review's score: the gate reads its own when it runs one.
        pytest.param(
            ": unless the gate runs a test review of its own, it reads this one's score.",
            ": the gate reads this review's score unless a backfill there makes it stale.",
            id="exclusive-claim",
        ),
    ],
)
def test_step_3_predicate_rejects_a_one_clause_mutant(old, new):
    step = _step3()
    mutant = step.replace(old, new)
    assert mutant != step, "the mutant must actually change the text"
    assert not _step3_points_at_the_rule(mutant)
