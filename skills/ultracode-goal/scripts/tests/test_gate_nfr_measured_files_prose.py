#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for the measured files, criteria and sources the NFR assessor
reads.

`references/gate.md` hands the NFR assessor the gate worktree and each file a
tool wrote when it measured the commit under assessment (a results file, a
report, a scan or a log). Those files are written in the main tree: the
backfill sweep runs over it, and every assessor's output goes home there. TEA's
NFR audit takes evidence only from files under the root it audits, so a breach
recorded only in such a file never reached the audit, the criterion read
`CONCERNS`, which does not fail the gate's AND, and the story could advance.
The NFR assessor's paragraph now has the conductor copy each measured file into
the gate worktree before the assessment, untracked and not as a link, at its
path relative to `{project-root}` under a `.ucg-measured/` folder it names to
the assessor, so two files of one name do not overwrite each other. On a cycle
that rebuilds the worktree the copy is made after the rebuild, which would
discard it, as the worktree's removal does once the verdict is recorded.

After a move of an acceptance criterion, or once an AC amendment is closed, no
commit carries the edit before the story advances, so the worktree's story file
and each oracle source the operator edited still state the old AC, and the gate
already names the main-tree story file to trace. The paragraph now has the
conductor, on those gate cycles, copy the criteria out of that file (a
decomposed child's parent's), not the file itself, and hand each other
`oracle=` source of the `.moved-<story_id>` record from the main tree. An
`oracle=` line can name the story file, which the operator edits when the
moved-AC check refuses, so "other" keeps that file out of the assessor's hands
even then, as the test reviewer's paragraph keeps it. The sentence names the amendment and
not its escalation kind, which `test_gate_ac_prescribed_downgrade_prose.py`
keeps to its own paragraph.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text without the new sentences and one-clause mutants it must
reject. The cross-references are checked against the paragraphs they rest on:
the main-tree folders the measured files land in, the rebuild, the cycles that
skip it and the removal that discard the copies, the naming of the main-tree
story file to trace after a move and after an amendment, and the record's
`oracle=` lines, one of which can name the story file. The whole-paragraph pin
in `test_gate_nfr_inputs_prose.py` holds these sentences in place.

Facts about TEA are checked against the tracked reference skill under
`skf-skills/tea-testarch/`: its NFR audit builds a supplied-evidence ledger,
the allowlist for factual claims, names a criterion no supplied evidence
supports as a gap, and gives an omitted criterion `CONCERNS`, which does not
block. Stated limits: that the ledger admits only regular files under the root
the audit names, so neither a file outside the worktree nor a link counts, is
stated in the installed TEA alone. The tracked reference does not state it (a
test below checks that it still does not), and no test reads the installed
copies under `.claude/skills/`, which are not tracked. This is a presence proof
over prose: it shows the instruction is in the files, not that a conductor
obeys it or that TEA behaves as its reference says.

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

_REVIEW_HEAD = "**The test reviewer reads the tests, not the run's account of them.**"
_HEAD = "**The NFR assessor reads what the commit shows, not the run's account of it.**"
_REBUILD_HEAD = "**Rebuild the worktree once automate has finished (production).**"
_MOVED_AC_HEAD = "**After a move, check that trace scored no moved AC, in either profile.**"
_MOVE_HEAD = "**A moved AC leaves the story's list.**"
_DOWNGRADE_HEAD = "**A downgrade the story's own AC prescribes is not a re-loop.**"

# The two sentences this contract adds.
_COPY = (
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

# The text they build on.
_MEASURED_LIST = (
    "and each file a tool wrote when it measured that commit or, after a backfill, the `gate-backfill-base:` commit "
    "(a results file, a report, a scan or a log), a failing one included"
)


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


def _review(text: str = GATE) -> str:
    return _paragraph(_backfill_section(text), _REVIEW_HEAD)


def _without(text: str, *sentences: str) -> str:
    """`text` without each of `sentences`: the state before the edit."""
    for sentence in sentences:
        shorter = text.replace(" " + sentence, "", 1)
        assert shorter != text, "the live text must hold the sentence"
        text = shorter
    return text


_PRE_EDIT = _without(GATE, _COPY, _MAIN_TREE)


def _mutant(text: str, old: str, new: str) -> str:
    flat = _flat(text)
    mutant = flat.replace(old, new)
    assert mutant != flat, "the mutant must actually change the text"
    return mutant


# Ends a sentence: a full stop, a space and a capital. The record's name,
# `.moved-<story_id>`, holds a dot that ends none.
_IN_SENTENCE = r"(?:(?!\. [A-Z]).)*?"


# --- why the measured files are copied ---------------------------------------------

_WHY = (
    "TEA's NFR audit takes evidence only from files under the root it audits, and those measured files sit outside "
    "the worktree, so "
)


def _says_why_measured_files_are_copied(rule: str) -> bool:
    """The reason names TEA's root rule, which bounds where the audit takes its
    evidence from, and where the measured files sit, and it follows the handed
    list that names them, since "those measured files" points back at it."""
    flat = _flat(rule)
    if _WHY not in flat or _MEASURED_LIST not in flat:
        return False
    return flat.index(_MEASURED_LIST) < flat.index(_WHY)


def test_rule_says_why_the_measured_files_are_copied():
    assert _says_why_measured_files_are_copied(_rule())


def test_why_predicate_rejects_the_text_without_the_sentence():
    assert not _says_why_measured_files_are_copied(_rule(_PRE_EDIT))
    # The reviewer's paragraph hands nothing a tool measured.
    assert not _says_why_measured_files_are_copied(_review())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("takes evidence only from files under the root it audits", "takes evidence from any file it is "
                     "given", id="any-file"),
        pytest.param("takes evidence only from files under the root it audits", "takes evidence only from the files "
                     "it is named", id="root-unnamed"),
        pytest.param("takes evidence only from files under", "takes evidence first from files under",
                     id="only-dropped"),
        pytest.param("those measured files sit outside the worktree", "those measured files sit in the worktree",
                     id="said-to-be-inside"),
        pytest.param(", and those measured files sit outside the worktree, so", ", so", id="where-unstated"),
    ],
)
def test_why_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _says_why_measured_files_are_copied(_mutant(_rule(), old, new))


def test_why_predicate_rejects_the_reason_placed_before_the_files_it_names():
    flat = _flat(_rule())
    moved = flat.replace(" " + _COPY, "").replace(
        "When you delegate `bmad-testarch-nfr`,", _COPY + " When you delegate `bmad-testarch-nfr`,"
    )
    assert moved != flat and _COPY in moved and _MEASURED_LIST in moved
    assert not _says_why_measured_files_are_copied(moved)


def test_the_measured_files_are_written_in_the_main_tree():
    """"Sit outside the worktree": the sweep the gate's backfill runs, as
    Execute's does, runs over the main tree, and every assessor's output lands
    in the main tree's folders, resolved against `{project-root}`, so a file a
    tool wrote when it measured the commit is a main-tree file with a path
    relative to `{project-root}`."""
    backfill = _flat(_backfill_section())
    assert "run the full three-axis sweep over the main tree, cache-defeated and printed" in backfill
    measure = _flat(_section(GATE, "## Measure the commit, not the working tree"))
    assert "Their OUTPUTS go home: every artifact an assessor writes" in measure
    assert "lands in the MAIN tree's resolved dirs" in measure
    assert (
        "resolved to absolute paths against `{project-root}` BEFORE any assessor is pointed at the worktree" in measure
    )


# --- the copy goes into the worktree, untracked, not linked, under a named folder ---

_WHERE = re.compile(
    re.escape("sit outside the worktree, so copy each into the worktree before the assessment, untracked and not as "
              "a link, ")
    + _IN_SENTENCE
    + re.escape("under a `.ucg-measured/` folder you name to the assessor, and after")
)


def _copies_into_the_worktree(rule: str) -> bool:
    """Each measured file is copied into the gate worktree, as an untracked
    file and not a link, under one folder the assessor is told of."""
    return _WHERE.search(_flat(rule)) is not None


def test_rule_copies_each_measured_file_into_the_worktree():
    assert _copies_into_the_worktree(_rule())


def test_where_predicate_rejects_the_text_without_the_sentence():
    assert not _copies_into_the_worktree(_rule(_PRE_EDIT))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("copy each into the worktree before", "name each path to the assessor before",
                     id="named-not-copied"),
        pytest.param("copy each into the worktree before", "copy one into the worktree before", id="one-is-enough"),
        pytest.param("copy each into the worktree before", "copy each beside the worktree before",
                     id="outside-the-worktree"),
        pytest.param("untracked and not as a link,", "not as a link,", id="may-be-tracked"),
        pytest.param("untracked and not as a link,", "untracked,", id="may-be-a-link"),
        pytest.param("untracked and not as a link,", "untracked, as a link,", id="linked"),
        pytest.param("untracked and not as a link,", "staged and not as a link,", id="staged"),
        pytest.param("under a `.ucg-measured/` folder you name to the assessor,", "under a `.ucg-measured/` folder,",
                     id="folder-unnamed-to-the-assessor"),
        pytest.param("under a `.ucg-measured/` folder you name to the assessor,", "anywhere in it,",
                     id="no-folder"),
    ],
)
def test_where_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _copies_into_the_worktree(_mutant(_rule(), old, new))


def test_the_folder_is_named_nowhere_else():
    """No other paragraph, and no other stage reference, gives the folder
    another use."""
    assert _flat(GATE).count("`.ucg-measured/`") == 1
    assert "`.ucg-measured/`" in _flat(_rule())
    for reference in sorted(_REFERENCES.glob("*.md")):
        if reference.name != "gate.md":
            assert ".ucg-measured" not in reference.read_text(encoding="utf-8"), reference.name


def test_a_copy_is_not_how_the_gate_brings_in_dependencies():
    """"Not as a link" sets the measured files apart from the dependency
    folders, which the gate links from the main tree into the worktree."""
    measure = _flat(_section(GATE, "## Measure the commit, not the working tree"))
    assert "Link each such directory the repo has (root *and* nested) from the main tree into the worktree" in measure


# --- each copy keeps its path relative to the project root -------------------------

_PATH = re.compile(
    re.escape("copy each into the worktree before the assessment, ")
    + _IN_SENTENCE
    + re.escape(" at its path relative to `{project-root}` under a `.ucg-measured/` folder")
)


def _copy_keeps_its_path(rule: str) -> bool:
    """Each copy sits at the measured file's path relative to `{project-root}`
    under the folder, so two measured files of one name in different folders
    (a repo whose packages nest, each measured by a tool that writes a file of
    the same name, say) do not overwrite each other, and the assessor can tell
    which file a result came from."""
    return _PATH.search(_flat(rule)) is not None


def test_rule_keeps_each_copy_at_its_path_relative_to_the_project_root():
    assert _copy_keeps_its_path(_rule())


def test_path_predicate_rejects_the_text_without_the_sentence():
    assert not _copy_keeps_its_path(_rule(_PRE_EDIT))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("at its path relative to `{project-root}` under", "under", id="flattened"),
        pytest.param("at its path relative to `{project-root}`", "under its own name", id="name-only"),
        pytest.param("relative to `{project-root}`", "relative to the worktree", id="worktree-relative"),
    ],
)
def test_path_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _copy_keeps_its_path(_mutant(_rule(), old, new))


# --- the copy is made after the rebuild, when there is one, and before the assessment

_WHEN = re.compile(
    re.escape("so copy each into the worktree before the assessment, ")
    + _IN_SENTENCE
    + re.escape(
        ", and after the cycle's rebuild when it has one, which would discard them, as the worktree's removal does "
        "once the verdict is recorded."
    )
)


def _copies_after_the_rebuild_before_the_assessment(rule: str) -> bool:
    """The copy is made before the assessment and, on a cycle that rebuilds the
    worktree, after the rebuild, and the sentence says what discards the
    copies: the rebuild, and the worktree's removal once the verdict is
    recorded."""
    return _WHEN.search(_flat(rule)) is not None


def test_rule_copies_after_the_rebuild_and_before_the_assessment():
    assert _copies_after_the_rebuild_before_the_assessment(_rule())


def test_when_predicate_rejects_the_text_without_the_sentence():
    assert not _copies_after_the_rebuild_before_the_assessment(_rule(_PRE_EDIT))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("copy each into the worktree before the assessment", "copy each into the worktree after the "
                     "assessment", id="after-the-audit"),
        pytest.param("and after the cycle's rebuild", "and before the cycle's rebuild", id="before-the-rebuild"),
        pytest.param("the cycle's rebuild when it has one,", "the cycle's rebuild,", id="every-cycle-rebuilds"),
        pytest.param(", which would discard them, as", ", as", id="rebuild-discard-unstated"),
        pytest.param(", as the worktree's removal does once the verdict is recorded.", ".", id="removal-unstated"),
        pytest.param("as the worktree's removal does once the verdict is recorded",
                     "and keep them in the worktree for the next cycle", id="kept-across-cycles"),
        pytest.param(
            ", and after the cycle's rebuild when it has one, which would discard them, as the worktree's removal "
            "does once the verdict is recorded.",
            ".",
            id="when-dropped",
        ),
    ],
)
def test_when_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _copies_after_the_rebuild_before_the_assessment(_mutant(_rule(), old, new))


def test_the_rebuild_and_the_removal_discard_what_was_copied_in():
    """The rebuild removes the worktree and adds it again from the commit, which
    holds that commit's tracked files and nothing else, before trace, NFR and
    test review start, so a copy made before it is gone. The removal once the
    verdict is recorded is forced because copied-in untracked inputs make the
    plain form refuse, so an untracked copy goes with it."""
    rebuild = _flat(_paragraph(_section(GATE, "## Measure the commit, not the working tree"), _REBUILD_HEAD))
    assert "remove it with `git worktree remove --force <tmp-path>`, add it again with `git worktree add" in rebuild
    assert "before trace, NFR and test review start" in rebuild
    assert (
        "A worktree just added from the commit holds that commit's tracked files and nothing a mutation or a copied "
        "test left behind" in rebuild
    )
    assert "then rebuild the gate worktree at the commit under assessment" in _flat(_backfill_section())
    measure = _flat(_section(GATE, "## Measure the commit, not the working tree"))
    assert (
        "Once the story's verdict is recorded, remove the worktree with `git worktree remove --force <tmp-path>` (the "
        "copied-in untracked inputs below make the unforced form refuse" in measure
    )


def test_a_cycle_without_an_automate_pass_has_no_rebuild():
    """"When it has one": a cycle with no automate pass skips the rebuild, so
    the copy waits for no rebuild there."""
    rebuild = _flat(_paragraph(_section(GATE, "## Measure the commit, not the working tree"), _REBUILD_HEAD))
    assert (
        "skip the rebuild only when no automate pass ran in this cycle (`--light`, or a later cycle that skips it), "
        "or when a red backfill sweep ended the cycle before trace, so that no other assessor runs in it." in rebuild
    )


# --- after a move or an amendment, the criteria come from the main tree -----------

_CRITERIA = re.compile(
    r"On each gate cycle that names the main-tree story file to trace, after a move or once an AC amendment is "
    r"closed, copy the criteria out of that file \(a decomposed child's parent's\), " + _IN_SENTENCE
    + r", since the worktree's copies still state the old AC\."
)


def _criteria_come_from_the_main_tree(rule: str) -> bool:
    """On a cycle after a move or a closed amendment, the criteria handed are
    copied out of the main tree's story file the cycle names to trace, a
    decomposed child's parent's, and the sentence says why: the worktree's copy
    states the old AC."""
    return _CRITERIA.search(_flat(rule)) is not None


def test_rule_copies_the_criteria_out_of_the_main_tree_after_a_move_or_an_amendment():
    assert _criteria_come_from_the_main_tree(_rule())


def test_criteria_predicate_rejects_the_text_without_the_sentence():
    assert not _criteria_come_from_the_main_tree(_rule(_PRE_EDIT))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("On each gate cycle that names", "On the first gate cycle that names", id="first-cycle-only"),
        pytest.param("after a move or once an AC amendment is closed,", "after a move,", id="amendment-dropped"),
        pytest.param("after a move or once an AC amendment is closed,", "once an AC amendment is closed,",
                     id="move-dropped"),
        pytest.param("once an AC amendment is closed,", "once an AC amendment is proposed,", id="before-the-close"),
        pytest.param("names the main-tree story file to trace", "names the worktree's story file to trace",
                     id="worktree-file-named"),
        pytest.param("names the main-tree story file to trace", "names a story file to trace", id="tree-unnamed"),
        pytest.param("copy the criteria out of that file", "copy the criteria out of the worktree's story file",
                     id="worktree-criteria"),
        pytest.param(" (a decomposed child's parent's)", "", id="child-without-its-parent"),
        pytest.param(", since the worktree's copies still state the old AC.", ".", id="why-dropped"),
    ],
)
def test_criteria_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _criteria_come_from_the_main_tree(_mutant(_rule(), old, new))


# --- and each other oracle source of the moved-AC record from the main tree -------

_SOURCES = re.compile(
    r"after a move or once an AC amendment is closed, " + _IN_SENTENCE + r" and hand each (?:other )?`oracle=` "
    r"source of the `\.moved-<story_id>` record from the main tree, since the worktree's copies still state the old "
    r"AC\."
)


def _oracle_sources_come_from_the_main_tree(rule: str) -> bool:
    """On the same cycles, each `oracle=` source the record lists is handed from
    the main tree, where the operator's edit is. Which of them is handed, every
    one but the story file, is the exemption's predicate below."""
    return _SOURCES.search(_flat(rule)) is not None


def test_rule_hands_each_oracle_source_from_the_main_tree():
    assert _oracle_sources_come_from_the_main_tree(_rule())


def test_sources_predicate_rejects_the_text_without_the_sentence():
    assert not _oracle_sources_come_from_the_main_tree(_rule(_PRE_EDIT))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(" and hand each other `oracle=` source of the `.moved-<story_id>` record from the main tree", "",
                     id="sources-dropped"),
        pytest.param("hand each other `oracle=` source", "hand the first other `oracle=` source", id="one-source"),
        pytest.param("record from the main tree,", "record from the gate worktree,", id="worktree-sources"),
        pytest.param("of the `.moved-<story_id>` record", "of the `.regate-<story_id>` marker", id="wrong-record"),
        pytest.param(", since the worktree's copies still state the old AC.", ".", id="why-dropped"),
    ],
)
def test_sources_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _oracle_sources_come_from_the_main_tree(_mutant(_rule(), old, new))


def test_the_main_tree_story_file_is_the_one_the_gate_names_to_trace():
    """"Names the main-tree story file to trace": after a move the gate names
    the main tree's story file and every `oracle=` path to trace, and after an
    amendment's close the story file, a decomposed child's parent's, since no
    commit carries either edit before the advance. A decomposed child's AC is
    never moved, so the parent's file is the amendment's case. The record's
    `oracle=` lines name the sources the operator edited."""
    flat = _flat(GATE)
    assert (
        "on every gate cycle of a story with a `.moved-<story_id>` record, the story file trace reads the story's "
        "criteria from and every `oracle=` path that record lists, each named absolute in the main tree" in flat
    )
    assert "so the worktree's copies still state the AC." in flat
    downgrade = _flat(_paragraph(GATE, _DOWNGRADE_HEAD))
    assert (
        "No commit carries the amendment before the story advances, so the gate worktree's copy of the story file "
        "still states the old AC." in downgrade
    )
    assert (
        "name to trace, absolute in the main tree, the story file trace reads the story's criteria from (a decomposed "
        "child's parent's), as a gate cycle after a move does" in downgrade
    )
    move = _flat(_paragraph(GATE, _MOVE_HEAD))
    assert "The record also takes an `oracle=<absolute path>` line for each oracle source the operator edited" in move
    assert "A decomposed child's AC is not moved in this form" in move
    assert "names the main-tree story file and its sources to trace" in move
    # The kind name stays in its own paragraph, as the downgrade's test asks.
    assert "ac-amendment-needed" not in _flat(_rule())


# --- the story file itself is never handed, even when an oracle= line names it ----

_KEPT = "Hand it nothing else the run wrote: nothing the paragraph above keeps from the reviewer,"
_REVIEWER_KEPT = "Hand it nothing else the run wrote: not a story file,"
_NAMED = "On each gate cycle that names the main-tree story file to trace,"
_EXEMPT = (
    "copy the criteria out of that file (a decomposed child's parent's), not the file itself, and hand each other "
    "`oracle=` source"
)
_EXEMPTED = re.compile(re.escape(_NAMED) + _IN_SENTENCE + " " + re.escape(_EXEMPT))
_HANDS_A_STORY_FILE = re.compile(r"\bhand (?:it |each )?(?:the |a )?(?:main tree's |worktree's )?story file", re.I)


def _story_file_kept_from_the_assessor(rule: str, review: str) -> bool:
    """The story file the cycle names to trace is exempted: its criteria are
    copied out of it, "not the file itself", and of the record's `oracle=`
    sources only the other ones are handed, so a line that names the story
    file hands it not. The assessor's exclusion still reaches all the
    reviewer's, which names a story file, and no sentence of the paragraph
    hands one."""
    flat, flat_review = _flat(rule), _flat(review)
    if _KEPT not in flat or _REVIEWER_KEPT not in flat_review:
        return False
    if _EXEMPTED.search(flat) is None:
        return False
    return _HANDS_A_STORY_FILE.search(flat) is None


def test_the_story_file_is_still_kept_from_the_assessor():
    assert _story_file_kept_from_the_assessor(_rule(), _review())


def test_kept_predicate_rejects_the_text_without_the_sentence():
    # Before the edit the paragraph named no main-tree story file at all.
    assert not _story_file_kept_from_the_assessor(_rule(_PRE_EDIT), _review(_PRE_EDIT))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("hand each other `oracle=` source", "hand each `oracle=` source", id="exemption-dropped"),
        pytest.param(", not the file itself, and hand", ", and hand", id="not-the-file-itself-dropped"),
        pytest.param("copy the criteria out of that file", "hand that file", id="file-handed"),
        pytest.param("(a decomposed child's parent's), not the file itself, and hand each other",
                     "(a decomposed child's parent's), hand it the story file too, and hand each other",
                     id="file-handed-beside-the-criteria"),
        pytest.param("nothing the paragraph above keeps from the reviewer, ", "", id="exclusion-narrowed"),
    ],
)
def test_kept_predicate_rejects_a_one_clause_mutant_of_the_rule(old, new):
    assert not _story_file_kept_from_the_assessor(_mutant(_rule(), old, new), _review())


def test_kept_predicate_rejects_a_reviewer_rule_that_hands_the_file():
    mutant = _mutant(_review(), "not a story file, ", "")
    assert not _story_file_kept_from_the_assessor(_rule(), mutant)


def test_an_oracle_line_can_name_the_story_file():
    """"Each other `oracle=` source" is not idle: the moved-AC check's refusal
    names the story file among the sources the operator edits in the main tree
    when the script names none, and the record takes an `oracle=` line for each
    oracle source the operator edited, so a line can name the story file
    itself."""
    check = _flat(_paragraph(GATE, _MOVED_AC_HEAD))
    assert (
        "(when it names none, the story file, the epic, the PRD and the test design), which the operator edits in "
        "the main tree so it no longer does" in check
    )
    move = _flat(_paragraph(GATE, _MOVE_HEAD))
    assert (
        "The record also takes an `oracle=<absolute path>` line for each oracle source the operator edited, with the "
        "move or after a refusal of the check" in move
    )


# --- what a measured file left out of the audit costs ----------------------------


def _load_gate_eval():
    spec = importlib.util.spec_from_file_location("gate_eval_measured_files", _SKILL_ROOT / "scripts" / "gate_eval.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.mark.parametrize(
    ("status", "verdict"),
    [
        pytest.param("CONCERNS", "advance", id="concerns-passes"),
        pytest.param("FAIL", "reloop", id="fail-holds"),
    ],
)
def test_an_audit_without_the_breach_lets_the_story_advance(tmp_path: Path, status, verdict):
    """A breach the audit never read leaves `CONCERNS`, which passes the AND on
    an otherwise-advance verdict, where the breach's `FAIL` holds the story."""
    gate_eval = _load_gate_eval()
    nfr = tmp_path / "nfr-assessment-61-1-sample-story.md"
    nfr.write_text(f"# NFR Assessment\n\n**Overall Status:** {status}\n", encoding="utf-8")
    review = tmp_path / "test-review-61-1-sample-story.md"
    review.write_text("**Quality Score**: 89/100\n**Recommendation**: Approve\n", encoding="utf-8")
    assert gate_eval.apply_production_and("advance", nfr, review, [])[0] == verdict


# --- the facts about TEA the copy rests on ----------------------------------------


def _tea_nfr_reference() -> str:
    """The tracked reference for the TEA version this module targets."""
    group = _REPO / "skf-skills" / "tea-testarch"
    active = group / "active"
    version = active.resolve().name if active.is_dir() else active.read_text(encoding="utf-8").strip()
    return _flat((group / version / "tea-testarch" / "references" / "pattern-nfr.md").read_text(encoding="utf-8"))


def test_tea_takes_evidence_only_from_its_supplied_ledger():
    """The ledger is the allowlist for factual claims, a criterion no supplied
    evidence supports is a gap, an omitted criterion reads `CONCERNS`, and
    `CONCERNS` does not block."""
    nfr = _tea_nfr_reference()
    assert "build the `supplied_evidence_ledger` (the allowlist for factual claims)" in nfr
    assert "an unsupported criterion yields one gap `'<label>: no supplied implementation evidence'`" in nfr
    assert "an omitted criterion gets a synthesized `CONCERNS`" in nfr
    assert "| `CONCERNS` | Partial or weak; does not block but needs follow-up" in nfr


def test_the_root_rule_is_not_in_the_tracked_reference():
    """The stated limit: the tracked reference names no root the ledger is
    bounded by and no check that an entry is a regular file. When a regenerated
    reference states them, check them here instead."""
    nfr = _tea_nfr_reference()
    assert "supplied_project_root" not in nfr
    assert "regular file" not in nfr
