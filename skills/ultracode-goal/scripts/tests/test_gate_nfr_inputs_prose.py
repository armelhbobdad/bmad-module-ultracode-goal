#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for what the NFR assessor is handed.

In production, `gate_eval.py` downgrades an `advance` to `reloop` when the
`nfr-assessment.md` Overall Status is `FAIL` or `NOT_ASSESSED`, and it reads
that status as written: it cannot see what the assessor was given. 8.1.0 bounded
what the test reviewer is handed ("The test reviewer reads the tests, not the
run's account of them") and said nothing of `bmad-testarch-nfr`, which takes
each threshold and each observation from what it is given. A delegation could
hand the assessor the run's own account of a measurement, a ruling that moved a
threshold or an earlier assessment of the same story, and a breach could come
back `CONCERNS` or `PASS`. A bound that went the other way and handed too little
fails too: an audit with no recorded result for a criterion reads `CONCERNS`,
which passes the AND where the result's `FAIL` would not.

`references/gate.md` now adds a paragraph, directly after the reviewer's rule
in "Backfill the gate evidence": the assessor is handed the gate worktree, at
the commit under assessment, the sources a threshold comes from (Stage 3's
test-design output, the PRD or tech spec, the architecture and its ADRs, the
epics file and the story's criteria with their thresholds, copied out of the
story file) and each file a tool wrote when it measured that commit or, after a
backfill, the `gate-backfill-base:` commit, a failing one included, and nothing
else the run wrote. It is told that nothing it was handed waives a
breach, moves a threshold or lifts a status. A delta gate's concerns-only
re-check is the one place it reads its own earlier assessment, and every other
NFR assessment first moves the story's earlier one aside into
`{workflow.implementation_artifacts}/evidence-<story_id>/`, the folder the
reviewer's rule names, under a `-cycle-<n>` name.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text without the paragraph and one-clause mutants it must reject.
The paragraph is also pinned whole and in place, so a sentence added anywhere in
it, or a paragraph put between it and the reviewer's rule, fails. Its claim
about the AND is checked against `gate_eval.py` itself, its cross-references
against the paragraphs it cites, the commits it names against what the gate
builds its worktree from and what it logs before a backfill, and its facts
about TEA against the tracked
reference skill under `skf-skills/tea-testarch/` (the installed TEA skills under
`.claude/skills/` are not tracked, so no test reads them). Stated limit: this is
a presence proof over prose. It shows the instruction is in the files, not that
a conductor obeys it or that TEA behaves as its reference says.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_REFERENCES = _SKILL_ROOT / "references"
GATE = (_REFERENCES / "gate.md").read_text(encoding="utf-8")
EXECUTE = (_REFERENCES / "execute.md").read_text(encoding="utf-8")
DEFINE_DONE = (_REFERENCES / "define-done.md").read_text(encoding="utf-8")

_REVIEW_HEAD = "**The test reviewer reads the tests, not the run's account of them.**"
_HEAD = "**The NFR assessor reads what the commit shows, not the run's account of it.**"
_DELTA_HEAD = "**The delta cycle profile (`--cycle-profile`, mid-loop gates, production).**"
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


def _without_the_rule(text: str = GATE) -> str:
    """The gate text without this paragraph: the state before the edit."""
    rule = _rule(text)
    assert rule, "the live text must hold the paragraph"
    return text.replace(rule + "\n\n", "", 1)


# The paragraph's sentences, in order. The whole-paragraph pin at the end joins
# them, so each predicate below may key on one of them.
_WHY = (
    _HEAD + " `gate_eval.py` reads the assessment's Overall Status as written, and TEA's NFR audit takes each "
    "threshold and each observation from what it is given, so what the assessor was handed decides a verdict too."
)
_HANDED = (
    "When you delegate `bmad-testarch-nfr`, hand it the tree it audits (the gate worktree, at the commit under "
    "assessment), the sources a threshold comes from (Stage 3's test-design output, the PRD or tech spec, the "
    "architecture and its ADRs, the epics file, and the story's acceptance criteria with each threshold they state, "
    "copied out of the story file as above), and each file a tool wrote when it measured that commit or, after a "
    "backfill, the `gate-backfill-base:` commit (a results file, a report, a scan or a log), a failing one included: "
    "one left out reads `CONCERNS`, which does not fail the gate's AND, where its `FAIL` does."
)
_EXCLUDED = (
    "Hand it nothing else the run wrote: nothing the paragraph above keeps from the reviewer, a ruling made during "
    "the run among them, no earlier NFR assessment of this story and no account of a measurement, yours included."
)
_NO_WAIVER = (
    "Tell it to open none of them, and that nothing it was handed waives a breach, moves a threshold or lifts a "
    "status: a threshold is what its source states, and a result no tool recorded proves no pass."
)
# The measured files copied into the worktree, and the criteria and sources taken
# from the main tree after a move or an amendment; test_gate_nfr_measured_files_prose.py
# checks them.
_MEASURED_COPIED = (
    "TEA's NFR audit takes evidence only from files under the root it audits, and those measured files sit outside "
    "the worktree, so copy each into the worktree before the assessment, untracked and not as a link, at its path "
    "relative to `{project-root}` under a `.ucg-measured/` folder you name to the assessor, and after the cycle's "
    "rebuild when it has one, which would discard them, as the worktree's removal does once the verdict is recorded."
)
_MAIN_TREE = (
    "On each gate cycle that names the main-tree story file to trace, after a move or once an AC amendment is "
    "closed, copy the criteria out of that file (a decomposed child's parent's), not the file itself, and hand each "
    "other `oracle=` source of the `.moved-<story_id>` record from the main tree, since the worktree's copies still "
    "state the old AC."
)
_BRIEF = "The instructions this file gives every assessor still go in its brief, as above."
_DELTA_READER = (
    "A delta gate's concerns-only re-check is the one place the assessor reads its own earlier assessment, as the "
    "paragraph above says of a reviewer."
)
_MOVE_ASIDE = (
    "TEA adds each step's output to an assessment already at the path it writes, so before every NFR assessment but "
    "that re-check, move the story's earlier `nfr-assessment-<story_id>.md`, when there is one, aside into "
    "`{workflow.implementation_artifacts}/evidence-<story_id>/` under a `-cycle-<n>` name, as the paragraph above "
    "moves a test review."
)
_SENTENCES = (_WHY, _HANDED, _EXCLUDED, _NO_WAIVER, _MEASURED_COPIED, _MAIN_TREE, _BRIEF, _DELTA_READER, _MOVE_ASIDE)


def _mutant(old: str, new: str) -> str:
    rule = _flat(_rule())
    mutant = rule.replace(old, new)
    assert mutant != rule, "the mutant must actually change the text"
    return mutant


# --- the assessor is handed what a verdict needs --------------------------------

_HANDED_OPENER = "When you delegate `bmad-testarch-nfr`, hand it "
_TREE = "the tree it audits (the gate worktree, at the commit under assessment), "
_THRESHOLD_SOURCES = (
    "Stage 3's test-design output",
    "the PRD or tech spec",
    "the architecture and its ADRs",
    "the epics file",
    "the story's acceptance criteria with each threshold they state",
)
_BACKFILL_BASE = " or, after a backfill, the `gate-backfill-base:` commit"
_MEASURED = (
    "each file a tool wrote when it measured that commit" + _BACKFILL_BASE + " (a results file, a report, a scan or "
    "a log), a failing one included"
)
_LEFT_OUT = "one left out reads `CONCERNS`, which does not fail the gate's AND, where its `FAIL` does."


def _handed_sentence(rule: str) -> str:
    """The sentence that lists what the assessor is handed, or "" when there is none."""
    flat = _flat(rule)
    start = flat.find(_HANDED_OPENER)
    if start == -1:
        return ""
    end = flat.find(" Hand it nothing else the run wrote:", start)
    return flat[start : end if end != -1 else len(flat)]


def _assessor_is_not_starved(rule: str) -> bool:
    """The handed list keeps every source a threshold comes from and every file a
    tool wrote when it measured the commit, a failing one included, and says why
    leaving one out is not neutral: it reads CONCERNS, which passes the AND."""
    handed = _handed_sentence(rule)
    if not handed.startswith(_HANDED_OPENER + _TREE):
        return False
    sources = re.search(r"the sources a threshold comes from \(([^()]*)\), and ", handed)
    if sources is None:
        return False
    listed = sources.group(1)
    if not all(source in listed for source in _THRESHOLD_SOURCES):
        return False
    # The measured results follow the sources in the same list, unqualified, and
    # the sentence ends on the reason a missing one matters.
    return handed.endswith(", and " + _MEASURED + ": " + _LEFT_OUT) and handed.index(sources.group(0)) < handed.index(
        _MEASURED
    )


def test_the_nfr_assessor_is_not_starved_of_thresholds_or_measured_results():
    assert _assessor_is_not_starved(_rule())


def test_not_starved_predicate_rejects_the_text_without_the_paragraph():
    assert not _assessor_is_not_starved(_backfill_section(_without_the_rule()))
    # The reviewer's rule, which stands above it, hands the assessor nothing.
    assert not _assessor_is_not_starved(_paragraph(_backfill_section(), _REVIEW_HEAD))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("(Stage 3's test-design output, the PRD or tech spec,", "(the PRD or tech spec,",
                     id="test-design-dropped"),
        pytest.param("the PRD or tech spec, the architecture", "the tech spec, the architecture", id="prd-dropped"),
        pytest.param("the PRD or tech spec, the architecture", "the PRD, the architecture", id="tech-spec-dropped"),
        pytest.param("the PRD or tech spec, the architecture", "the architecture", id="prd-and-tech-spec-dropped"),
        pytest.param("the architecture and its ADRs, ", "", id="architecture-dropped"),
        pytest.param("the architecture and its ADRs", "the architecture", id="adrs-dropped"),
        pytest.param("the epics file, and ", "", id="epics-dropped"),
        pytest.param(", and the story's acceptance criteria with each threshold they state", "",
                     id="story-criteria-dropped"),
        pytest.param("the story's acceptance criteria with each threshold they state",
                     "the story's acceptance criteria", id="criteria-without-thresholds"),
        pytest.param(", and " + _MEASURED + ": one left out", ": one left out", id="measured-results-dropped"),
        pytest.param(", a failing one included:", ", a failing one where it helps:", id="failing-result-optional"),
        pytest.param(", a failing one included:", ", a passing one included:", id="passing-results-only"),
        pytest.param(", a failing one included:", ":", id="failing-result-unstated"),
        pytest.param("each file a tool wrote", "a file a tool wrote", id="one-result-is-enough"),
        pytest.param(
            ": one left out reads `CONCERNS`, which does not fail the gate's AND, where its `FAIL` does.",
            ".",
            id="why-dropped",
        ),
        pytest.param("which does not fail the gate's AND, where its `FAIL` does",
                     "which fails the gate's AND as its `FAIL` does", id="concerns-said-to-fail"),
        pytest.param("hand it " + _TREE, "hand it ", id="tree-dropped"),
        # Text added at a join between two clauses of the handed list.
        pytest.param("a scan or a log), a failing one included",
                     "a scan or a log, the run's account of it), a failing one included", id="account-in-the-list"),
    ],
)
def test_not_starved_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _assessor_is_not_starved(_mutant(old, new))


def test_the_threshold_sources_are_the_ones_define_done_extracts_from():
    """Stage 3 runs test-design and extracts each NFR threshold from the PRD, the
    architecture, the ADRs, the epics and the stories; the paragraph hands the
    assessor those sources, the test-design output first."""
    assert DEFINE_DONE.startswith("# Stage 3")
    assert "Run `bmad-testarch-test-design` in **Epic-Level Mode** for the Epic." in DEFINE_DONE
    assert (
        "extract the concrete threshold from PRD / architecture / ADRs / epics / stories" in DEFINE_DONE
        and "In production these feed `bmad-testarch-nfr` at the gate" in DEFINE_DONE
    )
    listed = re.search(r"the sources a threshold comes from \(([^()]*)\)", _flat(_rule())).group(1)
    assert listed.startswith("Stage 3's test-design output, ")
    for source in ("PRD", "architecture", "ADRs", "epics", "story's acceptance criteria"):
        assert source in listed


def test_the_tech_spec_beside_the_prd_is_the_document_tea_reads_first():
    """Stage 3 names no tech spec, and TEA's NFR audit reads one first: its step
    1 reads `tech-spec.md` as its primary input, then `PRD.md`. The paragraph
    names the two side by side, so a project that keeps its thresholds in a tech
    spec hands the assessor that file."""
    assert "tech spec" not in _flat(DEFINE_DONE).lower()
    nfr = _flat((_tea_reference() / "references" / "pattern-nfr.md").read_text(encoding="utf-8"))
    assert "Step 1 reads `tech-spec.md` (primary), `PRD.md`, story or test-design docs" in nfr
    listed = re.search(r"the sources a threshold comes from \(([^()]*)\)", _flat(_rule())).group(1)
    assert "Stage 3's test-design output, the PRD or tech spec, the architecture" in listed


def test_the_criteria_are_copied_out_as_for_the_reviewer():
    """"As above" is the reviewer's rule, which copies the criteria out of the
    story file and keeps the file itself from the reviewer."""
    assert "copied out of the story file as above)" in _handed_sentence(_rule())
    review = _flat(_paragraph(_backfill_section(), _REVIEW_HEAD))
    assert "Hand it the criteria themselves, copied out of the story file, and not the file:" in review


# --- the tree is the gate worktree at the commit under assessment ---------------

_ANCHOR = "(the gate worktree, at the commit under assessment)"


def _audits_the_commit_under_assessment(rule: str) -> bool:
    """The tree the assessor audits is the gate worktree at the commit under
    assessment, named first in the handed list, so "that commit" in the measured
    results after it is that commit and no other."""
    handed = _handed_sentence(rule)
    if not handed.startswith(_HANDED_OPENER + "the tree it audits " + _ANCHOR + ", "):
        return False
    return re.search(r"each file a tool wrote when it measured that commit\b", handed) is not None


def test_rule_hands_the_gate_worktree_at_the_commit_under_assessment():
    assert _audits_the_commit_under_assessment(_rule())


def test_the_gate_builds_its_worktree_at_the_commit_under_assessment():
    """The anchor names the commit the gate makes its worktree from, rebuilds it
    at after automate, and moves to after a backfill commit."""
    flat = _flat(GATE)
    measure = _flat(_section(GATE, "## Measure the commit, not the working tree"))
    assert "create a worktree of the commit under assessment with `git worktree add <tmp-path> <commit>`" in measure
    assert "then rebuild the gate worktree at the commit under assessment" in _flat(_backfill_section())
    assert (
        "The new commit is now the commit under assessment: the worktree is rebuilt at it, trace, NFR and test review "
        "measure it" in flat
    )


def test_anchor_predicate_rejects_the_text_without_the_paragraph():
    assert not _audits_the_commit_under_assessment(_backfill_section(_without_the_rule()))
    # The reviewer's rule names the gate worktree without the anchor.
    assert not _audits_the_commit_under_assessment(_paragraph(_backfill_section(), _REVIEW_HEAD))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_ANCHOR, "(the gate worktree)", id="anchor-dropped"),
        pytest.param("at the commit under assessment)", "at `HEAD`)", id="at-head"),
        pytest.param("at the commit under assessment)", "at the story's baseline)", id="at-baseline"),
        pytest.param("at the commit under assessment)", "at the previous gate's `assessed-commit`)",
                     id="at-the-previous-gate"),
        pytest.param("(the gate worktree, at", "(the main tree, at", id="main-tree"),
        pytest.param("when it measured that commit", "when it measured the main tree", id="measured-elsewhere"),
    ],
)
def test_anchor_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _audits_the_commit_under_assessment(_mutant(old, new))


# --- after a backfill, the measured files include the backfill base's -----------


def _measures_the_backfill_base(rule: str) -> bool:
    """The measured files are the ones a tool wrote at the commit under
    assessment, named first, or, after a backfill, at the `gate-backfill-base:`
    commit, the commit automate measured, which a backfill commit leaves behind:
    one clause of the same list item, ahead of its examples."""
    handed = _handed_sentence(rule)
    if not handed.startswith(_HANDED_OPENER + _TREE):
        return False
    return (", and each file a tool wrote when it measured that commit" + _BACKFILL_BASE + " (a results file") in handed


def test_rule_hands_the_files_measured_at_the_backfill_base():
    assert _measures_the_backfill_base(_rule())


def test_the_backfill_base_is_the_commit_automate_measured_and_not_the_one_assessed():
    """The gate logs `gate-backfill-base:` naming `HEAD`, the commit automate
    measured, before it commits a backfill, and the backfill commit then becomes
    the commit under assessment, so a file a tool wrote at the base measured a
    commit "that commit" no longer names."""
    flat = _flat(_backfill_section())
    assert (
        "log `gate-backfill-base: <sha>` in `.decision-log.md`, naming `HEAD`, the commit automate measured, then "
        "commit the backfill" in flat
    )
    assert "The new commit is now the commit under assessment:" in flat


def test_backfill_base_predicate_rejects_the_text_without_the_paragraph():
    assert not _measures_the_backfill_base(_backfill_section(_without_the_rule()))
    assert not _measures_the_backfill_base(_paragraph(_backfill_section(), _REVIEW_HEAD))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_BACKFILL_BASE, "", id="backfill-base-dropped"),
        pytest.param("the `gate-backfill-base:` commit", "the backfill commit", id="names-the-backfill-commit"),
        pytest.param("the `gate-backfill-base:` commit", "the story's baseline", id="names-the-baseline"),
        pytest.param("the `gate-backfill-base:` commit", "the previous gate's `assessed-commit`",
                     id="names-the-previous-gate"),
        pytest.param(" or, after a backfill, the", " or the", id="base-without-its-condition"),
        pytest.param("after a backfill", "before a backfill", id="before-a-backfill"),
        pytest.param("when it measured that commit or,", "when it measured", id="base-only"),
    ],
)
def test_backfill_base_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _measures_the_backfill_base(_mutant(old, new))


# --- nothing else the run wrote --------------------------------------------------


def _hands_nothing_else(rule: str) -> bool:
    """The handed list is closed, the exclusion reaches every record the reviewer
    is kept from, and it names the run's rulings, an earlier assessment and any
    account of a measurement, the conductor's own included."""
    flat = _flat(rule)
    return _HANDED in flat and (_HANDED + " " + _EXCLUDED + " Tell it to open none of them, and that") in flat


def test_rule_hands_the_assessor_nothing_else_the_run_wrote():
    assert _hands_nothing_else(_rule())
    # "The paragraph above" is the reviewer's rule, and it keeps the run's
    # records from the reviewer.
    review = _flat(_paragraph(_backfill_section(), _REVIEW_HEAD))
    assert (
        "Hand it nothing else the run wrote: not a story file, not `.decision-log.md` or any other slice of it, not a "
        "ruling made during the run, one logged as an Operator notes entry included, not a scratch note" in review
    )


def test_nothing_else_predicate_rejects_the_text_without_the_paragraph():
    assert not _hands_nothing_else(_backfill_section(_without_the_rule()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("Hand it nothing else the run wrote:", "Hand it what helps, except:", id="open-list"),
        pytest.param("nothing the paragraph above keeps from the reviewer, ", "", id="reviewer-exclusions-dropped"),
        pytest.param(", a ruling made during the run among them", "", id="rulings-handed"),
        pytest.param("no earlier NFR assessment of this story and ", "", id="earlier-assessment-handed"),
        pytest.param(" and no account of a measurement, yours included.", ".", id="account-handed"),
        pytest.param("no account of a measurement, yours included.", "no account of a measurement but yours.",
                     id="own-account-handed"),
        pytest.param("Tell it to open none of them, and that", "Tell it that", id="may-open-them"),
    ],
)
def test_nothing_else_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _hands_nothing_else(_mutant(old, new))


# --- nothing handed waives a breach ----------------------------------------------


def _nothing_waives(rule: str) -> bool:
    return _NO_WAIVER in _flat(rule)


def test_rule_says_nothing_handed_waives_a_breach_moves_a_threshold_or_lifts_a_status():
    assert _nothing_waives(_rule())


def test_no_waiver_predicate_rejects_the_text_without_the_paragraph():
    assert not _nothing_waives(_backfill_section(_without_the_rule()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("nothing it was handed waives a breach", "what it was handed may waive a breach",
                     id="may-waive"),
        pytest.param("waives a breach, moves a threshold or lifts a status", "waives a breach or lifts a status",
                     id="may-move-a-threshold"),
        pytest.param("waives a breach, moves a threshold or lifts a status", "waives a breach or moves a threshold",
                     id="may-lift-a-status"),
        pytest.param(": a threshold is what its source states, and a result", ": a result",
                     id="threshold-from-anywhere"),
        pytest.param("a result no tool recorded proves no pass", "a result the run recalls proves a pass",
                     id="recalled-result-passes"),
    ],
)
def test_no_waiver_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _nothing_waives(_mutant(old, new))


# --- the delta re-check is the one reader of an earlier assessment ---------------


def _names_the_delta_reader(rule: str) -> bool:
    return _DELTA_READER in _flat(rule)


def test_rule_names_the_delta_recheck_as_the_one_reader_of_an_earlier_assessment():
    assert _names_the_delta_reader(_rule())


def test_the_delta_reader_cites_what_the_reviewer_rule_and_the_delta_profile_say():
    """"As the paragraph above says of a reviewer": the reviewer's rule names the
    re-check, its diff and its cap, and the delta profile paragraph it cites says
    what the rule says of it."""
    review = _flat(_paragraph(_backfill_section(), _REVIEW_HEAD))
    assert (
        "A delta gate's concerns-only re-check (\"The delta cycle profile\", under \"Run the gate\") is the one place "
        "a reviewer reads its own earlier artifact, with the diff from the previous gate's `assessed-commit` line to "
        "the commit under assessment, and that gate's verdict is capped at `reloop`." in review
    )
    delta = _flat(_paragraph(_section(GATE, "## Run the gate"), _DELTA_HEAD))
    assert delta.startswith(_DELTA_HEAD + " ")
    assert "the others verify their own prior artifact against the diff" in delta
    assert "(a concerns-only re-check;" in delta
    assert "the script caps the verdict at `reloop`" in delta
    # The re-check is one an NFR assessor runs too: the delta profile names the
    # NFR artifact among the ones a re-check reads.
    assert "left no trace, NFR or test review artifact to re-check" in delta


def test_delta_predicate_rejects_the_text_without_the_paragraph():
    assert not _names_the_delta_reader(_backfill_section(_without_the_rule()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("is the one place the assessor", "is one place the assessor", id="not-the-only-reader"),
        pytest.param(", as the paragraph above says of a reviewer.", ".", id="uncapped"),
        pytest.param("A delta gate's concerns-only re-check", "A delta gate", id="full-delta-gate-reads-it"),
        pytest.param("A delta gate's concerns-only re-check", "A re-loop's assessment", id="re-loop-reads-it"),
    ],
)
def test_delta_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _names_the_delta_reader(_mutant(old, new))


# --- an earlier assessment is moved aside before a new one -----------------------


def _moves_the_earlier_assessment_aside(rule: str) -> bool:
    """The rule moves an earlier assessment out of the path TEA writes, into the
    folder the reviewer's earlier review goes to and under the same kind of name,
    before every assessment but the delta re-check, which reads it."""
    flat = _flat(rule)
    if _MOVE_ASIDE not in flat or _DELTA_READER not in flat:
        return False
    # "That re-check" points back at the delta sentence, so the move follows it.
    return flat.index(_DELTA_READER) < flat.index(_MOVE_ASIDE)


def test_rule_moves_the_earlier_assessment_aside():
    assert _moves_the_earlier_assessment_aside(_rule())


def test_move_aside_cites_the_reviewer_rule_and_the_evidence_folder():
    """"As the paragraph above moves a test review": the reviewer's rule gives the
    folder in full and the `-cycle-<n>` name, the folder is Execute's, which no step
    removes, and the per-story name is the one the gate gives the assessment."""
    review = _flat(_paragraph(_backfill_section(), _REVIEW_HEAD))
    assert (
        "move the story's earlier `test-review-<story_id>.md`, when there is one, aside into "
        "`{workflow.implementation_artifacts}/evidence-<story_id>/`, under its own name with `-cycle-<n>` before its "
        "extension, `<n>` the first number from 1 that no file there carries yet." in review
    )
    evidence = _flat(_paragraph(EXECUTE, _EVIDENCE_HEAD))
    assert "`{workflow.implementation_artifacts}/evidence-<story_id>/`, which no step removes." in evidence
    assert "`nfr-assessment-<id>.md`" in _flat(GATE)
    assert "--nfr <…/nfr-assessment-<story_id>.md>" in _flat(GATE)
    # The folder the assessment moves into is the one the reviewer's rule names,
    # written in full the same way.
    folder = re.compile(r"aside into `([^`]+)`")
    nfr_folder = folder.search(_flat(_rule())).group(1)
    assert nfr_folder == folder.search(review).group(1)
    assert nfr_folder == "{workflow.implementation_artifacts}/evidence-<story_id>/"


def test_move_aside_predicate_rejects_the_text_without_the_paragraph():
    assert not _moves_the_earlier_assessment_aside(_backfill_section(_without_the_rule()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(" " + _MOVE_ASIDE, "", id="dropped"),
        pytest.param("before every NFR assessment but that re-check", "before every NFR assessment",
                     id="re-check-too"),
        pytest.param("before every NFR assessment but that re-check", "before a re-loop's assessment",
                     id="re-loop-only"),
        pytest.param("aside into `{workflow.implementation_artifacts}/evidence-<story_id>/`",
                     "aside into `{workflow.implementation_artifacts}/.scratch-<story_id>/`", id="into-scratch"),
        pytest.param("aside into `{workflow.implementation_artifacts}/evidence-<story_id>/`",
                     "aside into `evidence-<story_id>/`", id="folder-without-its-root"),
        pytest.param("aside into `{workflow.implementation_artifacts}/evidence-<story_id>/`",
                     "aside into `{test_artifacts}/evidence-<story_id>/`", id="under-the-tea-root"),
        pytest.param(" under a `-cycle-<n>` name,", ",", id="overwrites"),
        pytest.param(", as the paragraph above moves a test review.", ".", id="unnamed-convention"),
        pytest.param("move the story's earlier `nfr-assessment-<story_id>.md`, when there is one, aside into",
                     "delete the story's earlier `nfr-assessment-<story_id>.md`, when there is one, from",
                     id="deleted"),
    ],
)
def test_move_aside_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _moves_the_earlier_assessment_aside(_mutant(old, new))


def test_move_aside_predicate_rejects_the_move_placed_before_the_re_check_it_excepts():
    rule = _flat(_rule())
    mutant = rule.replace(" " + _MOVE_ASIDE, "").replace(" " + _DELTA_READER, " " + _MOVE_ASIDE + " " + _DELTA_READER)
    assert mutant != rule and _MOVE_ASIDE in mutant and _DELTA_READER in mutant
    assert not _moves_the_earlier_assessment_aside(mutant)


# --- the paragraph holds these sentences and nothing else, in its place ----------


def _rule_is_whole(rule: str) -> bool:
    return _flat(rule).strip() == " ".join(_SENTENCES)


def test_rule_holds_nothing_else():
    assert _rule_is_whole(_rule())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_MOVE_ASIDE, _MOVE_ASIDE + " A summary of the run's measurements may go with it.",
                     id="appended"),
        pytest.param(_BRIEF, _BRIEF + " So may the decision log.", id="after-the-brief"),
        pytest.param(_WHY, _WHY + " An operator's ruling may set a threshold.", id="after-the-why"),
    ],
)
def test_whole_rule_predicate_rejects_an_added_sentence(old, new):
    assert not _rule_is_whole(_mutant(old, new))


def _in_place(text: str) -> bool:
    """The paragraph sits in "Backfill the gate evidence", directly after the
    reviewer's rule."""
    section = _backfill_section(text)
    review = _paragraph(section, _REVIEW_HEAD)
    rule = _paragraph(section, _HEAD)
    return bool(review and rule) and (review + "\n\n" + rule) in section


def test_rule_sits_directly_after_the_reviewer_rule():
    assert _in_place(GATE)


def test_placement_predicate_rejects_a_moved_or_separated_paragraph():
    rule = _rule()
    without = _without_the_rule()
    assert not _in_place(without)
    # Moved out of the backfill section, every clause intact.
    moved = without.replace("## Run the gate\n", "## Run the gate\n\n" + rule + "\n", 1)
    assert moved != without and not _in_place(moved)
    # Swapped with the reviewer's rule.
    review = _paragraph(GATE, _REVIEW_HEAD)
    swapped = GATE.replace(review + "\n\n" + rule, rule + "\n\n" + review, 1)
    assert swapped != GATE and not _in_place(swapped)
    # A paragraph put between it and the reviewer's rule.
    split = GATE.replace(review + "\n\n", review + "\n\nAn assessor may read the decision log.\n\n", 1)
    assert split != GATE and not _in_place(split)


# --- the AND the paragraph describes is the one gate_eval.py runs ----------------


def _load_gate_eval():
    spec = importlib.util.spec_from_file_location("gate_eval_nfr_inputs", _SKILL_ROOT / "scripts" / "gate_eval.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _verdict_for(gate_eval, folder: Path, status: str) -> tuple[str, str | None, int | None]:
    """The production AND on an otherwise-advance verdict, with a passing review
    and an NFR assessment whose Overall Status is `status`."""
    nfr = folder / f"nfr-assessment-61-1-sample-story-{status.lower()}.md"
    nfr.write_text(f"# NFR Assessment\n\n**Overall Status:** {status}\n", encoding="utf-8")
    review = folder / "test-review-61-1-sample-story.md"
    review.write_text("**Quality Score**: 89/100\n**Recommendation**: Approve\n", encoding="utf-8")
    return gate_eval.apply_production_and("advance", nfr, review, [])


@pytest.mark.parametrize(
    ("status", "verdict"),
    [
        pytest.param("PASS", "advance", id="pass"),
        pytest.param("CONCERNS", "advance", id="concerns"),
        pytest.param("FAIL", "reloop", id="fail"),
        pytest.param("NOT_ASSESSED", "reloop", id="not-assessed"),
    ],
)
def test_gate_eval_reads_the_status_as_written_and_concerns_passes_the_and(tmp_path: Path, status, verdict):
    gate_eval = _load_gate_eval()
    assert _verdict_for(gate_eval, tmp_path, status) == (verdict, status, 89)


def test_the_paragraph_claims_what_gate_eval_does_with_concerns_and_fail(tmp_path: Path):
    """The reason a measured result may not be left out: CONCERNS, what an audit
    without it reads, passes the AND where the result's FAIL does not."""
    gate_eval = _load_gate_eval()
    concerns, fail = _verdict_for(gate_eval, tmp_path, "CONCERNS")[0], _verdict_for(gate_eval, tmp_path, "FAIL")[0]
    assert (concerns, fail) == ("advance", "reloop")
    rule = _flat(_rule())
    assert _LEFT_OUT in rule
    # Twin: the paragraph does not claim the other way round, that CONCERNS
    # fails the AND, which the script refutes.
    assert not re.search(r"`CONCERNS`, which (?:also )?fails the gate's AND", rule)


# --- the facts about TEA the paragraph rests on ----------------------------------


def _tea_reference() -> Path:
    """The tracked reference skill for the TEA version this module targets."""
    group = _REPO / "skf-skills" / "tea-testarch"
    active = group / "active"
    version = active.resolve().name if active.is_dir() else active.read_text(encoding="utf-8").strip()
    return group / version / "tea-testarch"


def test_tea_takes_thresholds_from_test_design_and_reads_a_missing_one_as_concerns():
    """TEA's NFR audit takes its thresholds first from the test-design output,
    reads an unknown threshold as CONCERNS and never PASS, and names a criterion
    no supplied evidence supports as a gap; CONCERNS does not block and FAIL is a
    breached threshold."""
    nfr = _flat((_tea_reference() / "references" / "pattern-nfr.md").read_text(encoding="utf-8"))
    assert "Step 2 takes thresholds first from a test-design NFR section" in nfr
    assert "`UNKNOWN` threshold ⇒ `CONCERNS`, never `PASS`" in nfr
    assert "an unsupported criterion yields one gap `'<label>: no supplied implementation evidence'`" in nfr
    assert "| `CONCERNS` | Partial or weak; does not block but needs follow-up" in nfr
    assert "| `FAIL` | Not implemented or threshold breached" in nfr
    # The per-story path the move-aside names stands in for TEA's own report path.
    assert "`{test_artifacts}/nfr-assessment.md`" in nfr
