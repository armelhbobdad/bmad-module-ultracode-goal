#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for a `gate-gap:` line the operator assigned elsewhere (issue #221).

An open `gate-gap:` line on a P0 criterion named a risk the operator had
assigned, in writing, to a later story. The gate still measured it and
backfilled a test for it at every cycle, even at the re-gate of the same commit
a closed `operator-evidence-owed` escalation owes, because the line names the
commit automate measured and the empty-diff trigger runs automate for any open
line naming another commit. A red backfill sweep then re-looped the story for
work the operator had ruled out, and a green one committed past the commit the
operator's records were made at.

`references/gate.md` now lets such a line carry `owned-by <owner> per
<ruling>` at its end, written only on a written ruling that names this story,
the criterion or the risk, and the owner (an Operator notes entry given before
launch counts from the story's first cycle). Automate's scope, its re-run, the
empty-diff trigger, the rule that logs a carried line afresh naming this commit,
and the re-loop findings ("neither `unmeasured`, `unkilled` nor owned") all
leave an owned line out; the P0 backfill and P0 risk rules name it as their one
exception; a test automate backfills for one anyway is never staged and is
logged. An owned line never closes in its story, every cycle copies it
unchanged, and it reaches the ledger once, on `advance` or `defer`, as the
`med` row every open line becomes, naming the owner and the ruling. The
INVARIANT, the ledger's columns and the escalation kinds are unchanged.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text with the #221 wording taken out (the pre-edit text) and against
one-clause mutants it must reject. A locality twin moves the owned-line
paragraph out of the backfill section. A replay of the same-commit re-gate, on
gate.md's own sentences, shows a story whose only open line is owned runs no
automate and commits nothing, and that the pre-edit text re-loops it or commits
past the records. Stated limit: this is a presence proof over prose. It shows
the instruction is in the file, not that an executor obeys it.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_GATE = _SKILL_ROOT / "references" / "gate.md"
_FRAGMENT = _REPO / "changes" / "gate-owned-gap-lines.yaml"

_HEAD = "**An owned `gate-gap:` line is not this story's to close.**"
_OWNED = '"An owned `gate-gap:` line is not this story\'s to close"'
_CARRY_LAST_BULLET = "- Whatever the route, a line stays open, so the story's next gate cycle, when there is one, copies it."
_NEXT_HEAD = "**Operator evidence is a recorded live result, in either profile.**"

# Each #221 edit as (pre-edit text, live text). The pre-edit text is the live
# text with every live side put back to its pre-edit side.
_STAGING = (
    "A path it lists that the summary does not name is not part of the backfill and stays unstaged.",
    "A path it lists that the summary does not name is not part of the backfill and stays unstaged. Neither is a test "
    "the summary names for a risk or a gap an owned `gate-gap:` line names (" + _OWNED + " below): move it aside, "
    "unstaged, into the story's scratch folder, `{workflow.implementation_artifacts}/.scratch-<story_id>/`, at its "
    "repo-relative path under that folder, creating the folder when it is gone, which keeps it out of every default "
    "source glob (`references/execute.md`, step 0), and log the move in `.decision-log.md`. The gap it was written "
    "for is none the cycle backfilled, so the next cycle re-runs no row for it as one (\"At most one automate pass "
    "finishes per gate cycle\" below).",
)
_BACKFILLED_RERUN = (
    "the mutation rows behind each gap the previous cycle backfilled (the `scripts/mutate_check.py` table rows "
    "recorded in the summary named for that cycle's `gate-backfill-base:` commit) and behind each open",
    "the mutation rows behind each gap the previous cycle backfilled (the `scripts/mutate_check.py` table rows "
    "recorded in the summary named for that cycle's `gate-backfill-base:` commit), never a gap whose test step 1 of "
    "\"When automate backfills\" moved aside for an owned line, and behind each open",
)
_RED_FINDINGS = (
    "every open `gate-gap:` line of this cycle that is neither `unmeasured` nor `unkilled` as its findings",
    "every open `gate-gap:` line of this cycle that is neither `unmeasured`, `unkilled` nor owned as its findings",
)
_ROUTE_RED_FINDINGS = (
    "every open `gate-gap:` line of its cycle that is neither `unmeasured` nor `unkilled` as its findings",
    "every open `gate-gap:` line of its cycle that is neither `unmeasured`, `unkilled` nor owned as its findings",
)
_ROUTE_FINDINGS = (
    "each open `gate-gap:` line that is neither `unmeasured` nor `unkilled` is among the findings",
    "each open `gate-gap:` line that is neither `unmeasured`, `unkilled` nor owned is among the findings",
)
_CARRY_FINDINGS = (
    "each open line that is neither `unmeasured` nor `unkilled` is one of the findings",
    "each open line that is neither `unmeasured`, `unkilled` nor owned is one of the findings",
)
_SCOPE = (
    "plus the mutation rows behind the previous cycle's backfilled gaps and behind every open `gate-gap:` line:",
    "plus the mutation rows behind the previous cycle's backfilled gaps and behind every open `gate-gap:` line that is "
    "not owned (" + _OWNED + " below):",
)
_RERUN = (
    "and behind each open `gate-gap:` line (the rows recorded in the summary the line names).",
    "and behind each open `gate-gap:` line that is not owned (the rows recorded in the summary the line names).",
)
_TRIGGER = (
    "When that diff is empty, automate still runs, for the open `gate-gap:` lines alone, when any of them names a "
    "commit other than the commit under assessment. Otherwise skip automate and the rebuild, and carry the open lines "
    "unchanged, `unmeasured` ones included.",
    "When that diff is empty, automate still runs, for the open `gate-gap:` lines that are not owned and nothing else, "
    "when any of them names a commit other than the commit under assessment. Otherwise skip automate and the rebuild, "
    "and carry the open lines unchanged, `unmeasured` and owned ones included.",
)
_NAMES_THE_COMMIT = (
    "so automate has nothing left to look at there unless an open line names another commit, and the gate is still "
    "the full instrument. Each automate pass leaves every open line naming the commit that pass measured, so no cycle "
    "runs automate at a commit an earlier cycle's pass has measured.",
    "so automate has nothing left to look at there unless an open line that is not owned names another commit, and "
    "the gate is still the full instrument. Each automate pass leaves every open line that is not owned naming the "
    "commit that pass measured, so no cycle runs automate at a commit an earlier cycle's pass has measured, and an "
    "owned line, which keeps the commit it names, never makes automate run.",
)
_P0_BACKFILL = (
    "So only a gap on a criterion other than P0 is ever reported rather than backfilled.",
    "So only a gap on a criterion other than P0 is ever reported rather than backfilled, and a gap on a P0 criterion "
    "goes without a backfill on purpose only when an owned line names it, which automate leaves alone (" + _OWNED
    + " below).",
)
_P0_RISK = (
    "An `unmeasured` line is not a finding, since no mutant has run for it yet, and like every `gate-gap:` line it "
    "never changes the route the verdict takes.",
    "An `unmeasured` line is not a finding, since no mutant has run for it yet, and like every `gate-gap:` line it "
    "never changes the route the verdict takes. A risk an owned line names is the exception: automate does not "
    "measure it, and its line stays as it was logged (" + _OWNED + " below).",
)
_FIELDS = (
    "and an `unkilled` line also says `unkilled` and names the test that did not kill its rows.",
    "and an `unkilled` line also says `unkilled` and names the test that did not kill its rows. An owned line ends "
    "with its `owned-by` marker (" + _OWNED + " below).",
)
_AFRESH = (
    "A carried line that pass does not close is logged afresh in place of the copied line, naming this commit",
    "A carried line that is not owned and that pass does not close is logged afresh in place of the copied line, "
    "naming this commit",
)
_ROW = (
    "and an `unkilled` line's row says the backfilled test did not kill the mutant, which may be equivalent.",
    "and an `unkilled` line's row says the backfilled test did not kill the mutant, which may be equivalent. An owned "
    "line's row also names its owner and the ruling in `reason`, and its `suggested_action` names the owner.",
)
_ONLY_EVER = (
    "so a `gate-gap:` line on a P0 criterion is only ever a risk or a gap nobody has measured yet, a backfilled test "
    "that was never written, or a backfilled test that did not kill its mutant.",
    "so a `gate-gap:` line on a P0 criterion is only ever a risk or a gap nobody has measured yet, a backfilled test "
    "that was never written, a backfilled test that did not kill its mutant, or a risk or a gap a written ruling "
    "assigned to another owner (" + _OWNED + ", under the same section).",
)
_SOURCE = (
    "a backfilled test that was never written, or a backfilled test that did not kill its mutant), `code-review`",
    "a backfilled test that was never written, a backfilled test that did not kill its mutant, or a risk or a gap a "
    "written ruling assigned to another owner), `code-review`",
)
_EDITS = (
    _STAGING, _BACKFILLED_RERUN, _RED_FINDINGS, _ROUTE_RED_FINDINGS, _ROUTE_FINDINGS, _CARRY_FINDINGS, _SCOPE, _RERUN, _TRIGGER,
    _NAMES_THE_COMMIT, _P0_BACKFILL, _P0_RISK, _FIELDS, _AFRESH, _ROW, _ONLY_EVER, _SOURCE,
)

# The owned-line paragraph's clauses.
_MARKER = (
    "Only then, log the line with `owned-by <owner> per <ruling>` at its end, after every field above: `<owner>` is "
    "the story key of a story of this Epic not yet `done`, and any other owner, a `done` story or one outside this "
    "Epic included, takes the ledger-row form, `\"<Epic heading> <ledger id>\"` (a ledger id is unique only within "
    "its heading), and `<ruling>` cites the ruling as `Operator notes <entry>` or `decision <id>`, with `<id>` the "
    "`.decisions.json` id `/ucg-resolve` recorded it under."
)
_RULING = (
    "The ruling names this story, the criterion or the risk, and the owner; one that names less is not this ruling, "
    "and neither is a general or standing delegation, wherever it is written"
)
_FIRST_CYCLE = (
    "An Operator notes entry given before launch (`references/ingest-and-scope.md`, \"Operator notes\") counts from "
    "the story's first cycle: when you delegate automate there, name the risk or the gap the entry assigns and tell "
    "automate neither to measure nor to backfill it, then log its line `unmeasured`, with the marker."
)
_EACH_CYCLE = (
    "At the start of each gate cycle, before automate's scope and the empty-diff trigger are decided, read the rulings "
    "again (the Operator notes entries, and the `answer` and the `history` of each entry of "
    "`{workflow.implementation_artifacts}/.decisions.json` whose `action` is `close`, the store `/ucg-resolve` records "
    "every answer in), taking only the latest ruling for each line, an entry's `answer` over its `history` and a later "
    "entry over an earlier one, since a later return or reassignment replaces an earlier ruling, and log each open "
    "line whose marker that ruling changes in this cycle's entry, with the marker it now gives or with none, in place "
    "of the copy the carry makes."
)
_ONE_LINE = "Keep the line one line of prose: never a heading, with no JSON object and no `|` in it."
_OUT_OF_SCOPE = (
    "An owned line is outside automate's scope in every cycle: automate re-runs no row behind it, neither measures "
    "nor backfills the risk or the gap it names, and writes no row and no test for it, so when you delegate "
    "automate, name each owned line and tell it so."
)
_NEVER_STAGED = (
    "A test its summary names for one anyway is never staged: step 1 of \"When automate backfills\" above moves it "
    "aside and logs the move."
)
_NEVER_CLOSES = (
    "An owned line never closes in this story: each cycle copies it unchanged and never logs it afresh, and only a "
    "later written ruling takes the marker off, by logging the line again without it, which puts the line back in "
    "automate's scope."
)
_LEDGER_ONCE = (
    "It is none of a re-loop's findings, so it gets no `class:` line, and it reaches the ledger once, as the row an "
    "`advance` or a `defer` gives every open line (the bullets above), with `source` `gate`, `severity` `med` and "
    "`story` this story, its `reason` the line's state (`unmeasured`, `unkilled`, or the summary that recorded its "
    "rows) with the owner and the ruling, and its `suggested_action` naming the owner."
)
_NO_OTHER_GATE = (
    "The owner takes the work up from that row, never from this line: no story's gate reads another story's "
    "`gate-gap:` lines."
)

_LEDGER_HEADER = "| id | source | severity | story | reason | suggested_action | status |"
_INVARIANT = (
    "**INVARIANT: a P0/critical FAIL never defers.** A failing gate (or a P0/P1/overall threshold miss) is `reloop` "
    "or `escalate`, never `defer`. Only non-gate-blocking work (CONCERNS, non-critical findings, parked decisions, and "
    "the rows open `gate-gap:` lines become) is allowed onto the ledger. If you find yourself about to write a FAIL "
    "or a critical finding to the ledger, you are violating the gate: re-loop within budget or escalate instead. A "
    "row from a `gate-gap:` line is neither a FAIL nor a critical finding, whatever its criterion's priority, so it "
    "belongs on the ledger and never re-loops or escalates the story."
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _paragraph(text: str) -> str:
    """The owned-line paragraph, from its bold head to the blank line after it."""
    if _HEAD not in text:
        return ""
    start = text.index(_HEAD)
    end = text.find("\n\n", start)
    return text[start:] if end == -1 else text[start:end]


def _section(text: str, heading: str) -> str:
    if heading not in text:
        return ""
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start : end if end != -1 else len(text)]


# --- the pre-edit text: the live text with the #221 wording taken out -------------


def _pre_edit(text: str) -> str:
    paragraph = _paragraph(text)
    if paragraph:
        text = text.replace(paragraph + "\n\n", "", 1)
    for old, new in _EDITS:
        text = text.replace(new, old, 1)
    return text


def test_the_pre_edit_text_is_a_real_reconstruction():
    live = _read(_GATE)
    pre = _pre_edit(live)
    for old, new in _EDITS:
        assert live.count(new) == 1, new[:80]
        assert pre.count(old) == 1 and new not in pre, old[:80]
    assert _HEAD not in pre and "owned" not in pre
    assert len(live) - len(pre) == len(_paragraph(live)) + 2 + sum(len(new) - len(old) for old, new in _EDITS)
    # The carry's last bullet is followed again by the operator-evidence paragraph.
    assert _CARRY_LAST_BULLET + "\n\n" + _NEXT_HEAD in pre


# --- the owned-line paragraph ----------------------------------------------------


def _is_placed_after_the_carry(text: str) -> bool:
    """Once in the file, in the backfill section, right after the carry's
    bullets and before the operator-evidence paragraph."""
    if text.count(_HEAD) != 1:
        return False
    paragraph = _paragraph(text)
    return bool(
        _CARRY_LAST_BULLET + "\n\n" + paragraph + "\n\n" + _NEXT_HEAD in text
        and _HEAD in _section(text, "## Backfill the gate evidence (production only)")
    )


def _defines_the_marker(paragraph: str) -> bool:
    return _MARKER in _flat(paragraph)


def _needs_a_written_ruling(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(
        "A written operator ruling can assign a risk or a gap a `gate-gap:` line names, on a criterion the story "
        "keeps, to another story of this Epic or to a row of the deferred-work ledger. Only then," in flat
        and _RULING in flat
    )


def _counts_an_operator_note_from_cycle_one(paragraph: str) -> bool:
    return _FIRST_CYCLE in _flat(paragraph)


def _rereads_the_rulings_each_cycle(paragraph: str) -> bool:
    return _EACH_CYCLE in _flat(paragraph)


def _keeps_the_line_one_line(paragraph: str) -> bool:
    return _ONE_LINE in _flat(paragraph)


def _leaves_it_out_of_automates_scope(paragraph: str) -> bool:
    return _OUT_OF_SCOPE in _flat(paragraph)


def _never_stages_its_test(paragraph: str) -> bool:
    return _NEVER_STAGED in _flat(paragraph)


def _never_closes_it(paragraph: str) -> bool:
    return _NEVER_CLOSES in _flat(paragraph)


def _parks_it_once(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(_LEDGER_ONCE in flat and "escalat" not in flat and "`kind`" not in flat)


def _leaves_it_to_its_owner(paragraph: str) -> bool:
    return _NO_OTHER_GATE in _flat(paragraph)


_CLAUSES = (
    _defines_the_marker,
    _needs_a_written_ruling,
    _counts_an_operator_note_from_cycle_one,
    _rereads_the_rulings_each_cycle,
    _keeps_the_line_one_line,
    _leaves_it_out_of_automates_scope,
    _never_stages_its_test,
    _never_closes_it,
    _parks_it_once,
    _leaves_it_to_its_owner,
)


def _rules_the_owned_line(text: str) -> bool:
    paragraph = _paragraph(text)
    return _is_placed_after_the_carry(text) and all(clause(paragraph) for clause in _CLAUSES)


def test_the_gate_defines_an_owned_line():
    assert _rules_the_owned_line(_read(_GATE))


def test_the_owned_line_predicate_rejects_the_pre_edit_gate_md():
    pre = _pre_edit(_read(_GATE))
    assert not _rules_the_owned_line(pre)
    assert not _is_placed_after_the_carry(pre)
    assert not any(clause(_paragraph(pre)) for clause in _CLAUSES)


@pytest.mark.parametrize(
    ("clause", "old", "new"),
    [
        pytest.param(_defines_the_marker, " at its end, after every field above", "", id="marker-anywhere"),
        pytest.param(_defines_the_marker, "`decision <id>`, with `<id>` the `.decisions.json` id `/ucg-resolve` "
                     "recorded it under", "`decision <id>`", id="ruling-id-unnamed"),
        pytest.param(_defines_the_marker, " (a ledger id is unique only within its heading)", "",
                     id="bare-ledger-id"),
        pytest.param(_defines_the_marker, ", and any other owner, a `done` story or one outside this Epic included, "
                     "takes the ledger-row form, `\"<Epic heading> <ledger id>\"`", "", id="story-owner-only"),
        pytest.param(_defines_the_marker, "the story key of a story of this Epic not yet `done`", "the story key",
                     id="any-story-owns-it"),
        pytest.param(_needs_a_written_ruling, "a risk or a gap a `gate-gap:` line names, on a criterion the story "
                     "keeps,", "the criterion or the risk a `gate-gap:` line names", id="whole-criterion-owned"),
        pytest.param(_needs_a_written_ruling, "A written operator ruling", "A ruling", id="unwritten-ruling"),
        pytest.param(_needs_a_written_ruling, ", and neither is a general or standing delegation, wherever it is "
                     "written", "", id="delegation-counts"),
        pytest.param(_needs_a_written_ruling, "one that names less is not this ruling", "one that names less "
                     "still counts", id="partial-ruling-counts"),
        pytest.param(_counts_an_operator_note_from_cycle_one, "counts from the story's first cycle", "counts from "
                     "the story's second cycle", id="note-from-cycle-two"),
        pytest.param(_counts_an_operator_note_from_cycle_one, "tell automate neither to measure nor to backfill it",
                     "tell automate to measure it", id="note-measured"),
        pytest.param(_rereads_the_rulings_each_cycle, "At the start of each gate cycle, before automate's scope and "
                     "the empty-diff trigger are decided,", "Once the cycle's verdict is logged,",
                     id="rulings-read-after-automate"),
        pytest.param(_rereads_the_rulings_each_cycle, ", and the `answer` and the `history` of each entry of "
                     "`{workflow.implementation_artifacts}/.decisions.json` whose `action` is `close`, the store "
                     "`/ucg-resolve` records every answer in", "", id="decisions-unread"),
        pytest.param(_rereads_the_rulings_each_cycle, "the `answer` and the `history` of each entry of "
                     "`{workflow.implementation_artifacts}/.decisions.json` whose `action` is `close`, the store "
                     "`/ucg-resolve` records every answer in", "the `/ucg-resolve` decisions logged in "
                     "`.decision-log.md`", id="decisions-read-from-the-log"),
        pytest.param(_rereads_the_rulings_each_cycle, " and the `history`", "", id="history-unread"),
        pytest.param(_rereads_the_rulings_each_cycle, ", taking only the latest ruling for each line, an entry's "
                     "`answer` over its `history` and a later entry over an earlier one, since a later return or "
                     "reassignment replaces an earlier ruling,", "", id="every-ruling-applied"),
        pytest.param(_rereads_the_rulings_each_cycle, ", with the marker it now gives or with none,", ", with its "
                     "marker,", id="return-never-unmarks"),
        pytest.param(_keeps_the_line_one_line, "never a heading, ", "", id="heading-allowed"),
        pytest.param(_keeps_the_line_one_line, "with no JSON object and no `|` in it", "with no `|` in it",
                     id="json-allowed"),
        pytest.param(_leaves_it_out_of_automates_scope, "automate re-runs no row behind it, ", "",
                     id="rows-re-run"),
        pytest.param(_leaves_it_out_of_automates_scope, "neither measures nor backfills", "measures but never "
                     "backfills", id="measured"),
        pytest.param(_leaves_it_out_of_automates_scope, "and writes no row and no test for it", "and writes no "
                     "test for it", id="rows-written"),
        pytest.param(_leaves_it_out_of_automates_scope, ", so when you delegate automate, name each owned line and "
                     "tell it so", "", id="automate-untold"),
        pytest.param(_never_stages_its_test, "is never staged", "is staged with the backfill", id="staged"),
        pytest.param(_never_stages_its_test, " and logs the move", "", id="unlogged"),
        pytest.param(_never_closes_it, "never closes in this story", "closes once its rows read killed",
                     id="closes"),
        pytest.param(_never_closes_it, "copies it unchanged and never logs it afresh", "logs it afresh naming "
                     "this commit", id="renamed"),
        pytest.param(_never_closes_it, "only a later written ruling takes the marker off", "a later pass takes "
                     "the marker off", id="marker-dropped-by-a-pass"),
        pytest.param(_parks_it_once, "It is none of a re-loop's findings, so it gets no `class:` line, and it",
                     "It is one of a re-loop's findings, and it", id="a-finding"),
        pytest.param(_parks_it_once, "reaches the ledger once", "reaches the ledger at every cycle",
                     id="every-cycle"),
        pytest.param(_parks_it_once, "`severity` `med`", "`severity` `high`", id="high"),
        pytest.param(_parks_it_once, " with the owner and the ruling, and its `suggested_action` naming the owner",
                     "", id="owner-unnamed"),
        pytest.param(_parks_it_once, "and `story` this story", "and `story` its owner", id="owners-row"),
        pytest.param(_leaves_it_to_its_owner, "no story's gate reads another story's `gate-gap:` lines",
                     "the owning story's gate copies the line into its own entry", id="owner-gate-acts"),
    ],
)
def test_each_owned_line_clause_rejects_its_one_clause_mutant(clause, old, new):
    paragraph = _flat(_paragraph(_read(_GATE)))
    assert paragraph.count(old) == 1, "the mutant must change the one clause it names"
    mutant = paragraph.replace(old, new)
    assert mutant != paragraph, "the mutant must actually change the text"
    assert clause(paragraph)
    assert not clause(mutant)


def test_an_escalation_or_a_new_kind_in_the_paragraph_is_rejected():
    """The owned line takes no route of its own: no new escalation kind."""
    paragraph = _flat(_paragraph(_read(_GATE)))
    mutant = paragraph.replace(_NO_OTHER_GATE, _NO_OTHER_GATE + " Without a ruling, escalate with `kind` `gap-owned`.")
    assert mutant != paragraph
    assert _parks_it_once(paragraph) and not _parks_it_once(mutant)


@pytest.mark.parametrize("where", ["route-on-the-verdict", "before-the-carry", "ledger-schema"])
def test_the_owned_line_paragraph_is_anchored_after_the_carry(where):
    """Locality twin: the paragraph moved out of place must red, not only the
    paragraph removed."""
    live = _read(_GATE)
    paragraph = _paragraph(live)
    without = live.replace(paragraph + "\n\n", "", 1)
    if where == "route-on-the-verdict":
        anchor = "**A logged verdict settles an owed re-gate.**"
    elif where == "before-the-carry":
        anchor = "**A reported gap stays open until a later pass measures it closed.**"
    else:
        anchor = "## Deferred-work ledger schema"
    mutant = without.replace(anchor, paragraph + "\n\n" + anchor, 1)
    assert mutant != without and _HEAD in mutant
    assert not _is_placed_after_the_carry(mutant)
    # The clauses still read, so only the placement check catches the move.
    assert all(clause(_paragraph(mutant)) for clause in _CLAUSES)


# --- backfill staging: a test written for an owned line is moved aside -------------

_STEP_ONE = "1. Stage the test files this pass's summary"
_REMOVE_VERB = re.compile(
    r"\b(?:remov\w*|delet\w*|rm -|clean\w* up|discard\w*|wip\w*|eras\w*|prun\w*|purg\w*|drop\w*)\b", re.I
)


def _moves_an_owned_lines_test_aside(gate: str) -> bool:
    """In step 1 of the backfill commit: such a test is moved into the run's
    own folder and the move logged, so it does not sit in the main tree for a
    later sweep's glob to run."""
    flat = _flat(gate)
    if _STEP_ONE not in flat or "2. With them staged" not in flat:
        return False
    start = flat.index(_STEP_ONE)
    return _STAGING[1] in flat[start : flat.index("2. With them staged", start)]


def test_a_test_for_an_owned_line_is_moved_aside_into_the_scratch_folder():
    gate = _read(_GATE)
    assert _moves_an_owned_lines_test_aside(gate)
    assert not _moves_an_owned_lines_test_aside(_pre_edit(gate))
    # The folder's sentence holds no remove verb (test_scratch_lifetime_prose.py).
    assert not _REMOVE_VERB.search(_STAGING[1])


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("move it aside, unstaged, into the story's scratch folder, "
                     "`{workflow.implementation_artifacts}/.scratch-<story_id>/`, at its repo-relative path under that "
                     "folder, creating the folder when it is gone, which keeps it out of every default source glob "
                     "(`references/execute.md`, step 0), and log the move", "leave it unstaged and log that automate "
                     "wrote it", id="left-in-the-tree"),
        pytest.param(", and log the move in `.decision-log.md`", "", id="move-unlogged"),
        pytest.param(", at its repo-relative path under that folder, creating the folder when it is gone", "",
                     id="path-lost"),
        pytest.param(" The gap it was written for is none the cycle backfilled, so the next cycle re-runs no row for "
                     "it as one (\"At most one automate pass finishes per gate cycle\" below).", "",
                     id="re-run-as-backfilled"),
    ],
)
def test_the_staging_predicate_rejects_a_mutant(old, new):
    gate = _read(_GATE)
    flat = _flat(gate)
    assert flat.count(old) == 1
    assert not _moves_an_owned_lines_test_aside(flat.replace(old, new))


# --- every rule that measures, re-runs, renames or routes a line leaves it out -----


def _excludes_the_owned_line_everywhere(text: str) -> bool:
    flat = _flat(text)
    return bool(
        all(new in flat for _, new in _EDITS)
        and flat.count("neither `unmeasured`, `unkilled` nor owned") == 4
        and "neither `unmeasured` nor `unkilled`" not in flat
    )


def test_every_rule_that_would_act_on_an_owned_line_leaves_it_out():
    assert _excludes_the_owned_line_everywhere(_read(_GATE))


@pytest.mark.parametrize(
    ("old", "new"),
    [pytest.param(new, old, id=f"edit-{i}") for i, (old, new) in enumerate(_EDITS)],
)
def test_each_exclusion_rejects_its_pre_edit_wording(old, new):
    """One edit put back at a time: each one is load-bearing."""
    flat = _flat(_read(_GATE))
    assert flat.count(old) == 1
    mutant = flat.replace(old, new, 1)
    assert mutant != flat
    assert not _excludes_the_owned_line_everywhere(mutant)


def test_the_invariant_the_ledger_columns_and_the_kinds_are_unchanged():
    live = _read(_GATE)
    invariant = next(line for line in live.splitlines() if line.startswith("**INVARIANT"))
    assert invariant == _INVARIANT
    assert live.count(_LEDGER_HEADER) == 1
    assert _LEDGER_HEADER in _pre_edit(live)
    kinds = sorted(set(re.findall(r"`kind` `([a-z-]+)`", live)))
    assert kinds == sorted(set(re.findall(r"`kind` `([a-z-]+)`", _pre_edit(live))))


def test_the_new_prose_holds_no_em_dash_and_never_writes_the_overruled_phrase():
    live = _read(_GATE)
    for added in (_paragraph(live), *(new for _, new in _EDITS)):
        assert chr(0x2014) not in added
    fragment = _read(_FRAGMENT)
    assert chr(0x2014) not in fragment
    for text in (live, fragment):
        assert "open P0 gap" not in _flat(text)


# --- the same-commit re-gate, replayed on gate.md's own sentences ------------------


def _replay_owned_regates(gate: str, regates: int, backfill_red: bool) -> list[str]:
    """Replay the field case: cycle 1 measured C0, committed a backfill for
    another gap as C1 and logged the P0 risk the operator assigned to a later
    story as an `unmeasured` line naming C0. The gate at C1 escalated
    `operator-evidence-owed`, the operator recorded at C1, and each entry is one
    re-gate of C1 (an empty diff). A backfill for the risk tests code the later
    story builds, so its sweep is red when `backfill_red`, and green otherwise.
    Each entry is `skip` (automate and the rebuild skipped), `ran` (automate ran
    and wrote nothing), `reloop` (a red backfill sweep) or the commit a green
    backfill made past the records; the replay stops at a re-loop or a commit."""
    flat = _flat(gate)
    owned_marked = _HEAD in flat
    trigger = "When that diff is empty, automate still runs, for the open `gate-gap:` lines"
    assert trigger in flat
    trigger_skips_owned = (
        "When that diff is empty, automate still runs, for the open `gate-gap:` lines that are not owned and nothing "
        "else, when any of them names a commit other than the commit under assessment" in flat
    )
    left_alone = _OUT_OF_SCOPE in flat
    keeps_its_commit = "and an owned line, which keeps the commit it names, never makes automate run" in flat
    measures_afresh = "For an `unmeasured` line" in flat and "it measures the gap afresh instead" in flat
    p0_gets_a_test = "a gap automate finds on a P0 criterion gets a test" in flat
    no_staging_exclusion = _STAGING[1] not in flat
    assert measures_afresh and p0_gets_a_test
    head, line_names, out = 1, 0, []
    for _ in range(regates):
        if line_names == head or (owned_marked and trigger_skips_owned):
            out.append("skip")
            continue
        # Automate runs for the line, which names a commit other than the one under assessment.
        if owned_marked and (left_alone or not no_staging_exclusion):
            # It writes nothing for the line, or the test it wrote is left unstaged: nothing is committed.
            out.append("ran")
            if not keeps_its_commit:
                line_names = head
            continue
        # The pass measures the risk afresh, a row confirms the gap, and the P0 rule backfills it.
        if backfill_red:
            out.append("reloop")
        else:
            out.append(f"C{head + 1}")
        break
    return out


@pytest.mark.parametrize("backfill_red", [True, False], ids=["red-backfill", "green-backfill"])
def test_a_regate_whose_only_open_line_is_owned_runs_no_automate_and_commits_nothing(backfill_red):
    assert _replay_owned_regates(_read(_GATE), 4, backfill_red) == ["skip", "skip", "skip", "skip"]


@pytest.mark.parametrize(
    ("backfill_red", "expected"), [(True, ["reloop"]), (False, ["C2"])], ids=["red-backfill", "green-backfill"]
)
def test_replay_on_the_pre_edit_text_reloops_or_commits_past_the_records(backfill_red, expected):
    """The mutant twin: the field failure, read off the pre-edit sentences."""
    assert _replay_owned_regates(_pre_edit(_read(_GATE)), 4, backfill_red) == expected


def test_replay_without_the_trigger_exclusion_runs_automate_at_every_regate():
    """With the trigger put back alone, automate measures nothing for the
    owned line but still runs at every re-gate of the same commit, since the
    owned line keeps naming C0."""
    mutant = _read(_GATE).replace(_TRIGGER[1], _TRIGGER[0], 1)
    assert mutant != _read(_GATE)
    assert _replay_owned_regates(mutant, 3, True) == ["ran", "ran", "ran"]


# --- the fragment ------------------------------------------------------------------

_FRAGMENT_SAYS = (
    "type: added",
    "scope: ultracode-goal",
    "issues: [221]",
    "`owned-by <owner> per <ruling>`",
    "written only when a written operator ruling",
    "on a criterion the story keeps",
    "a story of this Epic not yet `done`",
    "At the start of each gate cycle the rulings are read again",
    "is moved aside, unstaged, into the story's `.scratch-<story_id>/` folder and logged",
    "an owned line alone never makes it run",
    "a re-gate whose only open line is owned skips automate and commits nothing",
    "is never one of a re-loop's findings",
    "copied unchanged into every cycle until a later written ruling takes the marker off",
    "On `advance` or `defer` it becomes one `med` deferred-work row",
)


def test_the_fragment_says_what_the_prose_does():
    fragment = _flat(_read(_FRAGMENT))
    assert [s for s in _FRAGMENT_SAYS if s not in fragment] == []
