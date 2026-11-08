#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for the re-gate after the operator moves an AC out of the story (issue #222).

`/ucg-resolve` closed an `operator-evidence-owed` escalation on the operator's
written move of an AC to another story, and the re-gate had no form for the
moved AC. TEA's trace still scored it (NONE), the gate read FAIL or CONCERNS,
and `operator_owed.py`, finding an open AC the story no longer tags, read
`owed: false`, so the story went to a re-loop with nothing to build.

Now `references/gate.md` defines the moved-AC form inside the operator-evidence
route: the AC's numbered item leaves `## Acceptance Criteria` for a note under
an H2 heading of its own after that section, naming the retired number, the
owner and the ruling, with no `<n>.` and no `**Gate-ability:**` text; the number
is retired and never reused, no other AC is renumbered, and the AC leaves the
ATDD checklist's `acceptanceCriteria`. WAIVED is no route for it, and a
decomposed child's AC is not moved this way. The move is recorded durably as
`moved: AC-<n> to <owner> per <ruling>` lines in the decision log, which every
later cycle, the evidence commit and its resume read; it re-logs the moved AC's
open `gate-gap:` lines as owned, and parks one `med` row per moved AC on
`advance` or `defer`. Every gate cycle after a move names the main-tree story
file to trace (the move is uncommitted) and tells trace nothing of the move,
and before `gate_eval.py` runs, `moved_ac_check.py --commit` refuses, in
either profile and whatever the gate status, while trace's matrix holds a row
for a moved AC, cannot be read or measured another commit: that refusal is
logged as the cycle's verdict, settles the re-gate marker, and escalates
`operator-evidence-owed` again, never the `reloop` route, naming the commit and
what must change. A passed check leaves the routes as they were. `/ucg-resolve`
closes on a move only once the story file carries the form, closes a refusal
only once the operator confirms the change it asked for, and writes a
`moved=AC-<n>` line for every recorded move into `.regate-<story_id>`.
`references/execute.md`'s fourth resume case, `references/define-done.md`'s
numbering rule and `docs/gate-model.md` say the same.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text with the #222 wording taken out (the pre-edit text) and
against one-clause mutants it must reject. Locality twins move the check out of
"Run the gate" and the form out of the operator-evidence route. The documented
command is parsed with the script's own parser, and `operator_owed.py`'s own
reader is run on a story in the form, so the note is shown to start no AC and
to fold into none, and its twin, a note left in the list quoting the tag, is
shown to retag the AC above it. Stated limit: this is a presence proof over
prose. It shows the instruction is in the file, not that an executor obeys it.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import re
import shlex
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_REFS = _SKILL_ROOT / "references"
_GATE = _REFS / "gate.md"
_EXECUTE = _REFS / "execute.md"
_DEFINE_DONE = _REFS / "define-done.md"
_RESOLVE = _SKILL_ROOT.parent / "ucg-resolve" / "SKILL.md"
_GATE_MODEL = _REPO / "docs" / "gate-model.md"
_ARCHITECTURE = _REPO / "docs" / "architecture.md"
_FRAGMENT = _REPO / "changes" / "gate-moved-ac-regate.yaml"

_FORM_REF = '"A moved AC leaves the story\'s list"'
_CHECK_REF = '"After a move, check that trace scored no moved AC"'

_CHECK_HEAD = "**After a move, check that trace scored no moved AC, in either profile.**"
_FORM_HEAD = "**A moved AC leaves the story's list.**"
_ROUTE_BULLET = "- **A FAIL only operator evidence can change is not a re-loop.**"
_COMMAND = (
    "uv run {skill-root}/scripts/moved_ac_check.py --trace-output {workflow.trace_output_dir} --story <story_id> "
    "--commit <the full sha git rev-parse prints for the commit under assessment> --moved AC-<n>"
)
_COMMAND_BLOCK = "```\n" + _COMMAND + "\n```"
_RECORD = "`{workflow.implementation_artifacts}/.moved-<story_id>`"

# Each #222 edit inside an existing sentence, as (pre-edit text, live text).
_NAMING = (
    "Ask for nothing beyond those names, those frontmatter keys and, for a story with an operator-evidence AC, the "
    "live results file trace reads (\"Operator evidence is a recorded live result\" above): the provenance stays "
    "`tea` only while TEA's own steps computed the content.",
    "Ask for nothing beyond those names, those frontmatter keys, the live results file trace reads for a story with "
    "an operator-evidence AC (\"Operator evidence is a recorded live result\" above) and, on every gate cycle of a "
    "story with a `.moved-<story_id>` record, the story file trace reads the story's criteria from and every "
    "`oracle=` path that record lists, each named absolute in the main tree: the move, and an operator's edit of an "
    "oracle source, are edits no commit carries until the story advances (" + _FORM_REF + ", under \"Route "
    "on the verdict\"), so the worktree's copies still state the AC. Name the files and nothing of the move, which "
    "the files themselves state: the provenance stays `tea` only while TEA's own steps computed the content.",
)
_SETTLES = (
    "and a logged verdict leaves no re-gate owed.",
    "and a logged verdict leaves no re-gate owed. A refusal of the check after a move (" + _CHECK_REF + ", under "
    "\"Run the gate\") is logged as this cycle's verdict too, so it settles the marker the same way, and "
    "`/ucg-resolve` writes a fresh one when it closes the escalation that refusal takes.",
)
_PATHS = (
    "its live results file when it has an operator-evidence AC, this gate's ledger rows and the decision log",
    "its live results file when it has an operator-evidence AC or moved one out, its story file, its ATDD checklist "
    "and every `oracle=` path its `.moved-<story_id>` lists, when it has that record (" + _FORM_REF + " below), this "
    "gate's ledger rows and the decision log",
)
_RECORD_RETIRED = (
    "Then refresh `.commit-<story_id>` from `HEAD`, so this story's range in the gate trail includes the evidence "
    "commit.",
    "Then refresh `.commit-<story_id>` from `HEAD`, so this story's range in the gate trail includes the evidence "
    "commit. Once that commit is made, by this route or by a resume (the resume after a commit hook's escalation "
    "included), or nothing is staged for it, or a resume finds the gate's files committed already, remove " + _RECORD
    + ": the story's committed file and its ledger rows now hold each move.",
)
_CLOSE_NAMED = (
    "and that `/ucg-resolve` closes it once the records are there or once the operator narrows or moves the AC in "
    "writing, and `evidence` is TEA's gap line for the first of those ACs.",
    "and that `/ucg-resolve` closes it once the records are there, once the operator narrows the AC in writing, or "
    "once the story file carries the operator's written move of the AC out of the story (" + _FORM_REF + " below), and "
    "`evidence` is TEA's gap line for the first of those ACs.",
)
_ATTENDED = (
    "Attended, the operator may record it now; then re-gate the same commit in-session.",
    "Attended, the operator may record it now, or move the AC in that form, which you record as the `/ucg-resolve` "
    "close would, logging their in-session ruling as a named Operator notes entry in `.decision-log.md` and citing it "
    "as `Operator notes <entry>`: the form on disk before the re-gate, the owner as an owned line names one, the AC's "
    "open `gate-gap:` lines logged again as owned, and the `.moved-<story_id>` record; then re-gate the same commit "
    "in-session. For a decomposed child's AC, record `defer`, propose the re-plan and stop there, re-gating nothing.",
)
_MARKER = (
    "Otherwise `/ucg-resolve` closes it with the records on disk and writes `.regate-<story_id>`, and the resume "
    "re-gates that commit rather than re-driving the story",
    "Otherwise `/ucg-resolve` closes it with the records on disk, or with the move in the story file and its "
    "`.moved-<story_id>` record, and writes `.regate-<story_id>`, and the resume re-gates that commit rather than "
    "re-driving the story",
)
# The owned-line paragraph (#221) hands a whole criterion to this form.
_WHOLE_CRITERION = (
    "the bar the clause move in `references/execute.md`'s \"Two stories green only together\" sets.",
    "the bar the clause move in `references/execute.md`'s \"Two stories green only together\" sets. A ruling that "
    "assigns a whole criterion elsewhere is a move of the AC, which takes the moved-AC form (" + _FORM_REF + ", under "
    "\"Route on the verdict\"), not this marker alone: whoever applies that form, for any written ruling (the "
    "`/ucg-resolve` close, you in an attended run, or the re-read at each cycle's start below, which takes the latest "
    "ruling for each AC as it does for each line), writes the story's `.moved-<story_id>` record and logs each open "
    "line of the criterion the move retired again with the marker, and those lines reach the ledger inside the moved "
    "AC's row and not as rows of their own.",
)
# The two sentences that give each open line a row name the one exception.
_OWNED_ROW = (
    "and it reaches the ledger once, as the row an `advance` or a `defer` gives every open line (the bullets above), "
    "with",
    "and it reaches the ledger once, as the row an `advance` or a `defer` gives every open line (the bullets above), "
    "except an owned line on a moved AC, which rides that AC's row, with",
)
_CARRY_ROW = (
    "each open line becomes a ledger row with `source` `gate` and `severity` `med`, whatever its criterion's "
    "priority.",
    "each open line becomes a ledger row with `source` `gate` and `severity` `med`, whatever its criterion's "
    "priority, except an owned line on a moved AC, which rides that AC's row.",
)
_SOURCE = (
    "`gate` (CONCERNS, an operator-evidence AC's evidence still owed, or an open `gate-gap:` line:",
    "`gate` (CONCERNS, an operator-evidence AC's evidence still owed, an AC the operator moved out of the story, or an "
    "open `gate-gap:` line:",
)
_ESCALATE = (
    "budget exhausted on a FAIL; or a FAIL only operator evidence can change, above)",
    "budget exhausted on a FAIL; a FAIL only operator evidence can change, above; or any gate cycle of a story with a "
    "`.moved-<story_id>` record whose check exits 1 or 2, under \"Run the gate\")",
)
_GATE_EDITS = (
    _NAMING, _SETTLES, _PATHS, _RECORD_RETIRED, _CLOSE_NAMED, _ATTENDED, _MARKER, _ESCALATE, _WHOLE_CRITERION, _SOURCE,
    _OWNED_ROW, _CARRY_ROW,
)
# The `owed: false` route as the bullet ends it: nothing after it in the bullet.
_OWED_FALSE_ENDS = "On `owed: false`, the `reloop` route below stands; log the script's `reasons`."

_EXECUTE_EDITS = (
    (
        "then re-gating it in Stage 5, whose trace counts the operator's records.",
        "then re-gating it in Stage 5, whose trace counts the operator's records and, for a story with a "
        "`{workflow.implementation_artifacts}/.moved-<story_id>` record, reads the main tree's story file and the "
        "sources that record lists, and whose check that trace scored no moved AC runs before `gate_eval.py` "
        "(`references/gate.md`, " + _CHECK_REF + ").",
    ),
)
_DEFINE_DONE_EDITS = (
    (
        "numbered after the story's last AC so no existing number moves, with its own `**Gate-ability:** "
        "operator-evidence` line.",
        "numbered after the highest number the story has ever used, so no existing number moves and no retired number "
        "comes back: the number of an AC the operator moved out of the story stays retired (`references/gate.md`, "
        + _FORM_REF + "), since live records key on `AC-<n>`. It carries its own `**Gate-ability:** "
        "operator-evidence` line.",
    ),
)
# ucg-resolve is hard-wrapped, so its edits are read flattened.
_RESOLVE_WAITS = (
    "An AC the operator moves out of the story in writing needs no record, and the close waits for the move "
    "instead: the story file must carry it in the moved-AC form (`{ucg-root}/references/gate.md`, \"A moved AC "
    "leaves the story's list\"), its number starting no item under `## Acceptance Criteria` and a note under an H2 "
    "heading of its own after that section naming that number, the owner and the ruling. Until it does, record "
    "`defer`."
)
_RESOLVE_RECORDS = (
    "When it does, write `{workflow.implementation_artifacts}/.moved-<story_id>`, one line per AC it moves, opened by "
    "its `AC-<n>`, `AC-<n> to <owner> per <ruling>`, adding to any lines already there, and an `oracle=<absolute "
    "path>` line for each oracle source the operator edited with the move (a relative one resolved against "
    "`{project-root}`, and only a path inside the work tree `git rev-parse --show-toplevel` prints); log each open "
    "`gate-gap:` line on the moved AC again, under the story's key, with `owned-by` the same owner per the same "
    "ruling; and log the move in the story's `.decision-log.md` entry as a `moved:` line, which records it for a "
    "reader and which no step reads."
)
_RESOLVE_RETURN = (
    "A written return of a moved AC to the story is applied here too, as `{ucg-root}/references/gate.md`, \"A moved "
    "AC leaves the story's list\", says: its line leaves the record, and the record goes once no AC line is left."
)
_RESOLVE_CHILD = (
    "A decomposed child's AC is not moved this way: it lives in its parent's story file, which is never edited and "
    "which every sibling reads; record `defer` and propose a re-plan of the split instead."
)
_RESOLVE_REFUSAL = (
    "An escalation whose `decision_needed` opens with \"The moved-AC check refused (exit 1)\" closes, its moved ACs "
    "owing no record, only once the operator states in writing that each source it names no longer lists the AC for "
    "this story and you have added each source they edited inside the work tree to `.moved-<story_id>` as an "
    "`oracle=<absolute path>` line, or once they return the AC in writing; until then record `defer`. One that opens "
    "with \"The moved-AC check refused (exit 2)\" closes at once when it is the story's first exit-2 refusal at that "
    "commit; when it says one came before at that commit, it closes only once the operator confirms in writing that "
    "trace can write its files there, and until then record `defer`."
)
_RESOLVE_CONTRACT = (
    "Every reader of the file but one keys on `id` and `action` alone (`{ucg-root}/scripts/red_ids.py`, which "
    "preflight and the resume read it through), so `history` changes no suppression. The one is the gate's re-read "
    "of rulings at the start of each cycle (`{ucg-root}/references/gate.md`, \"An owned `gate-gap:` line is not this "
    "story's to close\"), which reads the `answer` and the `history` of each `close` entry and applies only the "
    "latest ruling for each line or AC: a later return or reassignment replaces an earlier one."
)
_RESOLVE_EDITS = (
    ("If one is missing, say which and record `defer`.", "If one is missing, say which and record `defer`. "
     + _RESOLVE_WAITS + " " + _RESOLVE_RECORDS + " " + _RESOLVE_RETURN + " " + _RESOLVE_CHILD + " "
     + _RESOLVE_REFUSAL),
    ("is the operator's story edit: record it, then close.",
     "is the operator's story edit: record it, naming each AC a move retires, then close."),
    ("Every reader of the file keys on `id` and `action` alone (`{ucg-root}/scripts/red_ids.py`, which preflight and "
     "the resume read it through), so `history` changes no suppression.", _RESOLVE_CONTRACT),
)
_GATE_MODEL_ADDED = (
    " A criterion the operator moves out of the story leaves the story's numbered list for a section of its own that "
    "names its owner and the ruling, its number retired and never reused, and `/ucg-resolve` closes on the move only "
    "once the story file carries it, recording each moved criterion in a per-story `.moved-<story_id>` file. A "
    "decomposed child's criterion is not moved this way, since its parent's story file is never edited. TEA's trace "
    "has no status for a moved criterion and can still score it from the epic, the PRD or the test design, so every "
    "gate cycle of a story with that record names the main-tree story file, and every recorded oracle source, to "
    "trace, and before `gate_eval.py` runs, `scripts/moved_ac_check.py --commit` reads TEA's coverage matrix for "
    "the commit under assessment: while a row still holds a moved criterion, or the trace files cannot be read or "
    "measured another commit, the story escalates `operator-evidence-owed` again, with a `decision_needed` that opens "
    "\"The moved-AC check refused\" and its exit code, instead of re-looping with nothing left to build."
)
_GATE_MODEL_ANCHOR = "so `/ucg-resolve` closes it only on a new `pass` record or on that written change."


def _flat(text: str) -> str:
    return " ".join(text.split())


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _paragraph(text: str, head: str) -> str:
    """The paragraph that opens with `head`, to the blank line after it."""
    if head not in text:
        return ""
    start = text.index(head)
    end = text.find("\n\n", start)
    return text[start:] if end == -1 else text[start:end]


def _section(text: str, heading: str) -> str:
    if heading not in text:
        return ""
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start : end if end != -1 else len(text)]


def _operator_route(gate: str) -> str:
    """The operator-evidence route, its command and the form after it, up to the reloop bullet."""
    if _ROUTE_BULLET not in gate:
        return ""
    start = gate.index(_ROUTE_BULLET)
    return gate[start : gate.index("- **`reloop`**", start)]


def _close_bullet(resolve: str) -> str:
    close = re.search(r"- \*\*`close`\*\*.*?(?=\n- \*\*`|\n\n)", resolve, re.DOTALL)
    return _flat(close.group(0)) if close else ""


def _fourth_case(execute: str) -> str:
    head = "**A fourth case: a closed `operator-evidence-owed` story owes a re-gate, not a re-drive.**"
    return _paragraph(execute, head)


def _split_step(define_done: str) -> str:
    return _paragraph(define_done, "**A criterion with an operator half is split here.**")


# --- the pre-edit texts: the live texts with the #222 wording taken out -------------


def _gate_pre_edit(text: str) -> str:
    check = _paragraph(text, _CHECK_HEAD)
    if check:
        text = text.replace("\n\n" + check + "\n\n" + _COMMAND_BLOCK, "", 1)
    form = _paragraph(text, _FORM_HEAD)
    if form:
        text = text.replace(form + "\n\n", "", 1)
    for old, new in _GATE_EDITS:
        text = text.replace(new, old, 1)
    return text


def _pre_edit(text: str, edits) -> str:
    for old, new in edits:
        text = text.replace(new, old, 1)
    return text


def _resolve_pre_edit(text: str) -> str:
    return _pre_edit(_flat(text), _RESOLVE_EDITS)


def _gate_model_pre_edit(text: str) -> str:
    return text.replace(_GATE_MODEL_ANCHOR + _GATE_MODEL_ADDED, _GATE_MODEL_ANCHOR, 1)


def test_the_pre_edit_texts_are_real_reconstructions():
    live = _read(_GATE)
    pre = _gate_pre_edit(live)
    check, form = _paragraph(live, _CHECK_HEAD), _paragraph(live, _FORM_HEAD)
    assert check and form
    for old, new in _GATE_EDITS:
        assert live.count(new) == 1 and pre.count(old) == 1 and new not in pre, old[:80]
    assert "moved" not in _section(pre, "## Run the gate") and _FORM_HEAD not in pre
    assert len(live) - len(pre) == (
        2 + len(check) + 2 + len(_COMMAND_BLOCK) + len(form) + 2 + sum(len(n) - len(o) for o, n in _GATE_EDITS)
    )
    # The naming paragraph is followed again by the production command, and the
    # operator-evidence command by the reloop bullet.
    assert "content.\n\nProduction:" in pre
    assert "--tests-ran {workflow.implementation_artifacts}/.tests-ran-<story_id>\n```\n\n- **`reloop`**" in pre
    for path, edits in ((_EXECUTE, _EXECUTE_EDITS), (_DEFINE_DONE, _DEFINE_DONE_EDITS)):
        text = _read(path)
        for old, new in edits:
            assert text.count(new) == 1 and _pre_edit(text, edits).count(old) == 1, old[:80]
    resolve = _flat(_read(_RESOLVE))
    for old, new in _RESOLVE_EDITS:
        assert resolve.count(new) == 1 and _resolve_pre_edit(_read(_RESOLVE)).count(old) == 1, old[:80]
    model = _read(_GATE_MODEL)
    assert len(model) - len(_gate_model_pre_edit(model)) == len(_GATE_MODEL_ADDED)


# --- gate.md: the trace delegation, the check and its place ------------------------


def _names_the_main_tree_story_file(gate: str) -> bool:
    naming = _flat(_paragraph(gate, "**Name the per-story paths trace writes, in either profile.**"))
    return bool(
        "on every gate cycle of a story with a `.moved-<story_id>` record, the story file trace reads the story's "
        "criteria from and every `oracle=` path that record lists, each named absolute in the main tree" in naming
        and "so the worktree's copies still state the AC" in naming
        and "Name the files and nothing of the move, which the files themselves state: the provenance stays `tea` "
        "only while TEA's own steps computed the content." in naming
    )


def _check_is_placed(gate: str) -> bool:
    """Once, in "Run the gate", right after the naming paragraph and right before
    the production command, its own command between them."""
    if gate.count(_CHECK_HEAD) != 1:
        return False
    naming = _paragraph(gate, "**Name the per-story paths trace writes, in either profile.**")
    check = _paragraph(gate, _CHECK_HEAD)
    return bool(
        naming + "\n\n" + check + "\n\n" + _COMMAND_BLOCK + "\n\nProduction:" in gate
        and _CHECK_HEAD in _section(gate, "## Run the gate")
    )


def _check_runs_on_every_cycle_after_a_move(check: str) -> bool:
    flat = _flat(check)
    return bool(
        "in either profile" in flat
        and "On every gate cycle of a story with a " + _RECORD + " record" in flat
        and "Once trace has written its files and before `gate_eval.py` runs, run the command below, with `--commit` "
        "the full sha `git rev-parse <the commit under assessment>` prints and one `--moved AC-<n>` for each line of "
        "the record that is not an `oracle=` line, taken from the `AC-<n>` that opens it." in flat
        and "Run it whatever `gate_status` trace wrote." in flat
    )


def _check_sets_the_old_trace_aside(check: str) -> bool:
    """The re-gate measures the commit the last gate did, so only a fresh trace
    tells this cycle's files from the last one's."""
    flat = _flat(check)
    return bool(
        "move the story's previous `trace-<story_id>.md`, `gate-decision-<story_id>.json` and "
        "`e2e-trace-summary-<story_id>.json` aside, all three in one step, before you delegate trace, into "
        "`{workflow.implementation_artifacts}/evidence-<story_id>/`, each under its own name with `-cycle-<n>` before "
        "its extension, `<n>` the first number from 1 that no file there carries yet, so nothing there is "
        "overwritten, and a trace that writes nothing, or only some of its files, leaves the check nothing of an "
        "earlier cycle to read, and it exits 2." in flat
        and "A resume that finds some of the three moved aside and some still in place moves the rest aside the same "
        "way before trace." in flat
        and "A resume that finds them moved aside still routes `gate-owed`: through `references/execute.md`'s fourth "
        "resume case while the `.regate-<story_id>` marker is fresh, and otherwise through its third, which finds "
        "neither the trace report nor the gate decision." in flat
    )


def _check_says_why(check: str) -> bool:
    return (
        "Trace scores every criterion it resolves, from the story, the epic, the PRD or the test design, and has no "
        "status for a moved one, so an AC that left the story's list can still be a row of its coverage matrix"
    ) in _flat(check)


def _check_reads_its_exit_codes(check: str) -> bool:
    flat = _flat(check)
    return bool(
        "Exit 0 means no row is a moved AC: run `gate_eval.py` as below and take the route its verdict gives, the "
        "ordinary routes unchanged, since what it scores is then only criteria the story still owns." in flat
        and "Exit 1 means a row is one, and exit 2 that the trace files could not be read, are not this trace's or "
        "measured another commit, since the script reads them as `operator_owed.py` does and fails closed. On either, "
        "run no `gate_eval.py`." in flat
    )


def _check_escalates_and_never_reloops(check: str) -> bool:
    flat = _flat(check)
    return bool(
        "as this cycle's verdict, a fenced JSON object holding only `verdict` and `reasons`, "
        "`{\"verdict\": \"escalate\", \"reasons\": [...]}`, with the script's `reasons`" in flat
        and "Then take `escalate` with `kind` `operator-evidence-owed` again: `source` is the trace report's path, "
        "`evidence` is the script's first reason," in flat
        and "Write no `class:` line and take no `reloop` route, since no re-loop changes what trace reads." in flat
    )


def _check_says_what_must_change(check: str) -> bool:
    """The refusal's escalation opens with a phrase the close keys on, is a new
    decision each time (a new red id), names the commit a close writes into the
    marker, and says what the operator changes."""
    flat = _flat(check)
    return bool(
        "and `decision_needed` opens with \"The moved-AC check refused (exit 1)\" or \"The moved-AC check refused "
        "(exit 2)\", then names this run's id, the refusal's number for this story (one past the refusals of this "
        "story the decision log already records), `assessed_commit` (the script's, or the commit under assessment "
        "when it printed none), each moved AC, and what must change before a re-gate can pass, so each refusal is a "
        "decision of its own and never one `/ucg-resolve` has closed already." in flat
        and "On exit 1, that is each source in the script's `oracle_sources` that still states a moved AC for this "
        "story (when it names none, the story file, the epic, the PRD and the test design), which the operator edits "
        "in the main tree so it no longer does, or a written return of the AC to the story." in flat
        and "Resolve a relative source against `{project-root}`, and name one outside the work tree `git rev-parse "
        "--show-toplevel` prints, or one that names no file, as a source the operator must clear themselves, since "
        "only a path inside the work tree is recorded and committed." in flat
        and "On exit 2, it is that the trace files are missing, not this trace's or of another commit, so the re-gate "
        "runs trace again, and `decision_needed` says whether an exit-2 refusal of this story at this commit came "
        "before." in flat
        and "`/ucg-resolve` keys its close on that opening phrase." in flat
    )


_CHECK_CLAUSES = (
    _check_runs_on_every_cycle_after_a_move,
    _check_sets_the_old_trace_aside,
    _check_says_why,
    _check_reads_its_exit_codes,
    _check_escalates_and_never_reloops,
    _check_says_what_must_change,
)


def _rules_the_check(gate: str) -> bool:
    check = _paragraph(gate, _CHECK_HEAD)
    return bool(
        _names_the_main_tree_story_file(gate)
        and _check_is_placed(gate)
        and all(clause(check) for clause in _CHECK_CLAUSES)
    )


def test_the_gate_checks_trace_scored_no_moved_ac_before_gate_eval():
    assert _rules_the_check(_read(_GATE))


def test_the_check_predicate_rejects_the_pre_edit_gate_md():
    pre = _gate_pre_edit(_read(_GATE))
    assert not _rules_the_check(pre)
    assert not _names_the_main_tree_story_file(pre) and not _check_is_placed(pre)
    assert not any(clause(_paragraph(pre, _CHECK_HEAD)) for clause in _CHECK_CLAUSES)


_REMOVE_VERB = re.compile(
    r"\b(?:remov\w*|delet\w*|rm -|clean\w* up|discard\w*|wip\w*|eras\w*|prun\w*|purg\w*|drop\w*)\b", re.I
)


def test_the_sentence_naming_the_evidence_folder_holds_no_remove_verb():
    """test_story_evidence_folder_prose.py: the folder is never removed, so no
    sentence that names it holds a remove verb."""
    check = _flat(_paragraph(_read(_GATE), _CHECK_HEAD))
    sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`*(\"-])", check) if "evidence-<story_id>" in s]
    assert sentences and not any(_REMOVE_VERB.search(s) for s in sentences)


@pytest.mark.parametrize(
    ("clause", "old", "new"),
    [
        pytest.param(_check_runs_on_every_cycle_after_a_move, " Run it whatever `gate_status` trace wrote.", "",
                     id="fail-only"),
        pytest.param(_check_runs_on_every_cycle_after_a_move, ", in either profile", ", in production",
                     id="production-only"),
        pytest.param(_check_runs_on_every_cycle_after_a_move, "Once trace has written its files and before "
                     "`gate_eval.py` runs", "Once `gate_eval.py` has run", id="after-gate-eval"),
        pytest.param(_check_runs_on_every_cycle_after_a_move, "On every gate cycle of a story with a " + _RECORD
                     + " record", "On the re-gate after a move", id="re-gate-only"),
        pytest.param(_check_runs_on_every_cycle_after_a_move, "for each line of the record that is not an `oracle=` "
                     "line, taken from the `AC-<n>` that opens it", "for each AC the record names",
                     id="ids-read-from-anywhere"),
        pytest.param(_check_runs_on_every_cycle_after_a_move, "the full sha `git rev-parse <the commit under "
                     "assessment>` prints", "`HEAD`", id="short-commit"),
        pytest.param(_check_sets_the_old_trace_aside, "move the story's previous `trace-<story_id>.md`, "
                     "`gate-decision-<story_id>.json` and `e2e-trace-summary-<story_id>.json` aside", "leave the "
                     "story's previous trace files where they are", id="old-trace-read"),
        pytest.param(_check_sets_the_old_trace_aside, ", all three in one step", "", id="one-at-a-time"),
        pytest.param(_check_sets_the_old_trace_aside, "`<n>` the first number from 1 that no file there carries yet, "
                     "so nothing there is overwritten", "`<n>` the cycle's number", id="overwrites"),
        pytest.param(_check_sets_the_old_trace_aside, ", or only some of its files,", "", id="partial-trace"),
        pytest.param(_check_sets_the_old_trace_aside, " A resume that finds some of the three moved aside and some "
                     "still in place moves the rest aside the same way before trace.", "", id="partial-move-resumed"),
        pytest.param(_check_sets_the_old_trace_aside, "A resume that finds them moved aside still routes "
                     "`gate-owed`", "A resume that finds them moved aside re-drives the story",
                     id="resume-unrouted"),
        pytest.param(_check_says_why, "and has no status for a moved one", "and skips a moved one",
                     id="trace-skips-it"),
        pytest.param(_check_reads_its_exit_codes, "On either, run no `gate_eval.py`.", "On exit 1, run no "
                     "`gate_eval.py`.", id="unreadable-runs-the-gate"),
        pytest.param(_check_reads_its_exit_codes, "and fails closed", "and reads an unreadable one as no row",
                     id="fail-open"),
        pytest.param(_check_reads_its_exit_codes, " and take the route its verdict gives, the ordinary routes "
                     "unchanged, since what it scores is then only criteria the story still owns", "",
                     id="routes-after-a-pass-unsaid"),
        pytest.param(_check_reads_its_exit_codes, ", are not this trace's or measured another commit",
                     " or are not this trace's", id="stale-trace-unnamed"),
        pytest.param(_check_escalates_and_never_reloops, "Write no `class:` line and take no `reloop` route",
                     "Take the `reloop` route", id="reloops"),
        pytest.param(_check_escalates_and_never_reloops, "as this cycle's verdict, a fenced JSON object holding "
                     "only `verdict` and `reasons`, `{\"verdict\": \"escalate\", \"reasons\": [...]}`, with the "
                     "script's `reasons`", "the refusal as prose", id="no-verdict-record"),
        pytest.param(_check_says_what_must_change, "opens with \"The moved-AC check refused (exit 1)\" or \"The "
                     "moved-AC check refused (exit 2)\", then names", "says the check refused, and names",
                     id="no-lead-phrase"),
        pytest.param(_check_says_what_must_change, "this run's id, the refusal's number for this story (one past the "
                     "refusals of this story the decision log already records), ", "", id="same-red-id"),
        pytest.param(_check_says_what_must_change, "(one past the refusals of this story the decision log already "
                     "records)", "", id="number-uncounted"),
        pytest.param(_check_says_what_must_change, "`assessed_commit` (the script's, or the commit under "
                     "assessment when it printed none), ", "", id="no-commit-for-the-marker"),
        pytest.param(_check_says_what_must_change, ", and what must change before a re-gate can pass", "",
                     id="nothing-to-change"),
        pytest.param(_check_says_what_must_change, "which the operator edits in the main tree so it no longer does",
                     "which the operator edits", id="edit-where-trace-cannot-see-it"),
        pytest.param(_check_says_what_must_change, ", or a written return of the AC to the story", "",
                     id="return-unoffered"),
        pytest.param(_check_says_what_must_change, "Resolve a relative source against `{project-root}`, and name",
                     "Name", id="relative-unresolved"),
        pytest.param(_check_says_what_must_change, "since only a path inside the work tree is recorded and "
                     "committed", "since every path is recorded", id="outside-path-recorded"),
        pytest.param(_check_says_what_must_change, "so the re-gate runs trace again", "so the operator re-records",
                     id="exit-2-no-retrace"),
        pytest.param(_check_says_what_must_change, ", and `decision_needed` says whether an exit-2 refusal of this "
                     "story at this commit came before", "", id="exit-2-unbounded"),
        pytest.param(_check_says_what_must_change, " `/ucg-resolve` keys its close on that opening phrase.", "",
                     id="close-unkeyed"),
    ],
)
def test_each_check_clause_rejects_its_one_clause_mutant(clause, old, new):
    check = _flat(_paragraph(_read(_GATE), _CHECK_HEAD))
    assert check.count(old) == 1, "the mutant must change the one clause it names"
    mutant = check.replace(old, new)
    assert mutant != check
    assert clause(check) and not clause(mutant)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(" Name the files and nothing of the move, which the files themselves state:", " Tell trace "
                     "which AC moved:", id="trace-told"),
        pytest.param(", each named absolute in the main tree", "", id="worktree-copy"),
        pytest.param(" and every `oracle=` path that record lists", "", id="sources-unnamed"),
    ],
)
def test_the_naming_predicate_rejects_a_mutant(old, new):
    gate = _read(_GATE)
    mutant = gate.replace(old, new, 1)
    assert mutant != gate
    assert not _names_the_main_tree_story_file(mutant)


@pytest.mark.parametrize("where", ["after-the-production-command", "route-on-the-verdict"])
def test_the_check_is_anchored_before_gate_eval(where):
    """Locality twin: the check moved after the gate, or into the routes, must
    red, not only the check removed."""
    live = _read(_GATE)
    block = _paragraph(live, _CHECK_HEAD) + "\n\n" + _COMMAND_BLOCK
    without = live.replace("\n\n" + block, "", 1)
    anchor = "Light:\n" if where == "after-the-production-command" else "**A logged verdict settles an owed re-gate.**"
    mutant = without.replace(anchor, block + "\n\n" + anchor, 1)
    assert mutant != without and _CHECK_HEAD in mutant
    assert not _check_is_placed(mutant)
    assert all(clause(_paragraph(mutant, _CHECK_HEAD)) for clause in _CHECK_CLAUSES)


def test_the_documented_command_parses_with_the_scripts_own_parser():
    spec = importlib.util.spec_from_file_location("moved_ac_check", _SKILL_ROOT / "scripts" / "moved_ac_check.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    line = next(ln for ln in _read(_GATE).splitlines() if ln.startswith("uv run {skill-root}/scripts/moved_ac_check"))
    sha = "a14e48a79010dd124366db59af51d8586e85ab33"
    line = line.replace("AC-<n>", "AC-7").replace("<the full sha git rev-parse prints for the commit under assessment>", sha)
    argv = shlex.split(re.sub(r"\{[^}]+\}|<[^>]+>", "x", line))[3:]
    args = module.build_parser().parse_args(argv)
    assert args.moved == ["AC-7"] and args.story == "x" and args.trace_output == "x" and args.commit == sha


def test_the_script_has_its_line_in_the_architecture_layout():
    assert "── moved_ac_check.py " in _read(_ARCHITECTURE)


# --- gate.md: the operator-evidence route and the form -----------------------------


def _route_names_the_form(route: str) -> bool:
    flat = _flat(route)
    return bool(_CLOSE_NAMED[1] in flat and _ATTENDED[1] in flat and _MARKER[1] in flat)


def _owed_false_keeps_the_reloop(route: str) -> bool:
    """A passed check keeps every moved AC out of what the gate scores, so an
    `owed: false` names criteria the story still owns: the `reloop` route stands,
    and the bullet ends with that sentence, nothing after it."""
    lines = route.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith(_ROUTE_BULLET)), None)
    if start is None:
        return False
    # The bullet runs on through every following line indented two spaces.
    end = next((i for i in range(start + 1, len(lines)) if not lines[i].startswith("  ")), len(lines))
    bullet = " ".join(line.strip() for line in lines[start:end])
    return bullet.endswith(" " + _OWED_FALSE_ENDS)


_FORM_OWNER = (
    "names the retired number, the owner, as an owned `gate-gap:` line names one (a story of this Epic not yet "
    "`done`, or else a ledger row as `\"<Epic heading> <ledger id>\"`), and the ruling (`Operator notes <entry>` or "
    "`decision <id>`, with `<id>` its `.decisions.json` id)."
)
_FORM_RECORD = (
    "Whoever applies this form, for any written ruling (the `/ucg-resolve` close, you at the operator's written "
    "direction in an attended run, or you for an Operator notes entry or an answer to another escalation that the "
    "re-read at each cycle's start finds), writes " + _RECORD + ", one line per moved AC opened by its `AC-<n>`, "
    "`AC-<n> to <owner> per <ruling>`, adding to any lines already there, and logs a `moved:` line in "
    "`.decision-log.md` that records the move for a reader and that no step reads. The record also takes an "
    "`oracle=<absolute path>` line for each oracle source the operator edited, with the move or after a refusal of "
    "the check: a relative one is resolved against `{project-root}`, and only a path inside the work tree `git "
    "rev-parse --show-toplevel` prints is recorded. Every later gate cycle of the story, the commit that carries the "
    "gate's files and a resume read the moved set from the `AC-<n>` that opens each line that is not an `oracle=` "
    "line, and the sources from the `oracle=` lines, of this record alone."
)
_FORM_RETURN = (
    "A written return of a moved AC to the story is applied by the `/ucg-resolve` close, or by you at the operator's "
    "written direction in an attended run: it deletes the AC's line from the record, and the record once no AC line "
    "is left, so no check runs then; puts the numbered item back under its old number; takes its entry out of the "
    "H2 note; restores it to the checklist's `acceptanceCriteria`; and logs its open `gate-gap:` lines again without "
    "the `owned-by` marker. The advance route removes the record once the commit that carries the gate's files is "
    "made (\"Commit the gate's evidence before the next story starts\", above)."
)
_FORM_RELOGS = (
    "Whoever records the move also logs each open `gate-gap:` line on the moved AC again with `owned-by` the same owner per the same "
    "ruling (\"An owned `gate-gap:` line is not this story's to close\", under \"Backfill the gate evidence\"), so "
    "automate leaves it alone."
)
_FORM_ROW = (
    "On `advance` or `defer`, append one ledger row per moved AC, with `source` `gate`, `severity` `med`, `story` this "
    "story, a `reason` naming the AC, its owner, the ruling and each owned `gate-gap:` line on it, which then writes "
    "no row of its own, and a `suggested_action` naming the owner, written once, as an owned line's row is."
)
_FORM_CHILD = (
    "A decomposed child's AC is not moved in this form: it lives in its parent's story file, which is never edited "
    "and which every sibling reads, so retiring it there would retire it for each of them; `/ucg-resolve` records "
    "`defer` for such a move and proposes a re-plan of the split instead."
)


def _form_leaves_the_list(form: str) -> bool:
    flat = _flat(form)
    return bool(
        "The AC's numbered item leaves `## Acceptance Criteria`, and a note under an H2 heading of its own after "
        "that section, one that does not say \"acceptance criteria\", " + _FORM_OWNER in flat
        and "and the story file then carries the move in this form and no other" in flat
    )


def _form_note_reads_as_no_ac(form: str) -> bool:
    return (
        "The note starts with no `<n>.` and holds no `**Gate-ability:**` text: the parsers that read the section fold "
        "an unnumbered line into the AC above it and read a tag there as that AC's" in _flat(form)
    )


def _form_retires_the_number(form: str) -> bool:
    flat = _flat(form)
    return bool(
        "The number is retired: no other AC is renumbered and no later AC takes it (`references/define-done.md`, "
        "step 1), since live records key on `AC-<n>`." in flat
        and "The AC also leaves the `acceptanceCriteria` list of the story's ATDD checklist" in flat
    )


def _form_rides_the_evidence_commit(form: str) -> bool:
    return (
        "and no commit carries them before the re-gate, since nothing may land after the assessed commit: the commit "
        "that carries the gate's files once the story advances stages them" in _flat(form)
    )


def _form_records_the_move_durably(form: str) -> bool:
    return _FORM_RECORD in _flat(form)


def _form_returns_a_moved_ac(form: str) -> bool:
    return _FORM_RETURN in _flat(form)


def _form_hands_its_lines_to_the_owner(form: str) -> bool:
    return _FORM_RELOGS in _flat(form)


def _form_parks_each_moved_ac_once(form: str) -> bool:
    return _FORM_ROW in _flat(form)


def _form_leaves_a_decomposed_child_alone(form: str) -> bool:
    return _FORM_CHILD in _flat(form)


def _form_has_no_waiver_and_no_reloop(form: str) -> bool:
    flat = _flat(form)
    return bool(
        "WAIVED is no route for a moved AC: TEA keeps a waived criterion in every count" in flat
        and "Every gate cycle of a story with that record names the main-tree story file and its sources to trace and "
        "checks trace's matrix before `gate_eval.py` runs" in flat
        and "so an AC the operator moved never reaches the `reloop` route." in flat
    )


_FORM_CLAUSES = (
    _form_leaves_the_list,
    _form_note_reads_as_no_ac,
    _form_retires_the_number,
    _form_rides_the_evidence_commit,
    _form_records_the_move_durably,
    _form_returns_a_moved_ac,
    _form_hands_its_lines_to_the_owner,
    _form_parks_each_moved_ac_once,
    _form_leaves_a_decomposed_child_alone,
    _form_has_no_waiver_and_no_reloop,
)


def _form_is_in_the_route(gate: str) -> bool:
    """Once, inside the operator-evidence route, after its command."""
    if gate.count(_FORM_HEAD) != 1:
        return False
    route = _operator_route(gate)
    return bool(
        _FORM_HEAD in route
        and route.index("uv run {skill-root}/scripts/operator_owed.py") < route.index(_FORM_HEAD)
    )


def _rules_the_route(gate: str) -> bool:
    route = _operator_route(gate)
    form = _paragraph(gate, _FORM_HEAD)
    return bool(
        _route_names_the_form(route)
        and _owed_false_keeps_the_reloop(route)
        and _form_is_in_the_route(gate)
        and all(clause(form) for clause in _FORM_CLAUSES)
        and _SETTLES[1] in _flat(gate)
        and _PATHS[1] in _flat(gate)
        and _WHOLE_CRITERION[1] in _flat(gate)
        and _SOURCE[1] in _flat(gate)
        and _RECORD_RETIRED[1] in _flat(gate)
        and _OWNED_ROW[1] in _flat(gate)
        and _CARRY_ROW[1] in _flat(gate)
    )


def test_the_route_defines_the_moved_ac_form():
    assert _rules_the_route(_read(_GATE))


def test_the_route_predicate_rejects_the_pre_edit_gate_md():
    pre = _gate_pre_edit(_read(_GATE))
    assert not _rules_the_route(pre)
    assert not _route_names_the_form(_operator_route(pre))
    assert not any(clause(_paragraph(pre, _FORM_HEAD)) for clause in _FORM_CLAUSES)


@pytest.mark.parametrize(
    "after",
    [
        # The exception as first written, which escalated every `owed: false` on
        # a move's re-gate, a real defect in a criterion the story owns included.
        " The re-gate after a move is the exception: there `owed: false` takes `escalate` with `kind` "
        "`operator-evidence-owed` again.",
        # Any other sentence after it in the bullet, whatever its words.
        " After a move, though, hold the story for the operator.",
        # A sentence on a continuation line of the bullet.
        "\n  After a move, though, hold the story for the operator.",
    ],
)
def test_nothing_follows_the_owed_false_route_in_its_bullet(after):
    route = _operator_route(_read(_GATE))
    assert _owed_false_keeps_the_reloop(route)
    assert route.count(_OWED_FALSE_ENDS) == 1
    mutant = route.replace(_OWED_FALSE_ENDS, _OWED_FALSE_ENDS + after)
    assert mutant != route and not _owed_false_keeps_the_reloop(mutant)


@pytest.mark.parametrize(
    ("clause", "old", "new"),
    [
        pytest.param(_form_leaves_the_list, "a note under an H2 heading of its own after that section",
                     "a note in its place", id="note-in-place"),
        pytest.param(_form_leaves_the_list, ", one that does not say \"acceptance criteria\",", "",
                     id="heading-unbounded"),
        pytest.param(_form_leaves_the_list, " and no other", "", id="other-forms"),
        pytest.param(_form_leaves_the_list, " (a story of this Epic not yet `done`, or else a ledger row as "
                     "`\"<Epic heading> <ledger id>\"`)", " (any story key)", id="any-owner"),
        pytest.param(_form_note_reads_as_no_ac, "starts with no `<n>.` and holds no `**Gate-ability:**` text",
                     "keeps the AC's number", id="numbered-note"),
        pytest.param(_form_note_reads_as_no_ac, " and holds no `**Gate-ability:**` text", "", id="tagged-note"),
        pytest.param(_form_retires_the_number, "no other AC is renumbered and no later AC takes it", "the ACs after "
                     "it are renumbered", id="renumbered"),
        pytest.param(_form_retires_the_number, " The AC also leaves the `acceptanceCriteria` list of the story's ATDD "
                     "checklist;", "", id="checklist-kept"),
        pytest.param(_form_rides_the_evidence_commit, "and no commit carries them before the re-gate", "and a commit "
                     "carries them before the re-gate", id="committed-first"),
        pytest.param(_form_records_the_move_durably, "of this record alone", "of the `moved:` lines of "
                     "`.decision-log.md`", id="moved-set-from-the-log"),
        pytest.param(_form_records_the_move_durably, "the commit that carries the gate's files and a resume read",
                     "read", id="evidence-commit-forgets"),
        pytest.param(_form_records_the_move_durably, "writes " + _RECORD + ", one line per moved AC opened by its "
                     "`AC-<n>`, `AC-<n> to <owner> per <ruling>`, adding to any lines already there, and logs", "logs",
                     id="no-record"),
        pytest.param(_form_records_the_move_durably, "the moved set from the `AC-<n>` that opens each line that is "
                     "not an `oracle=` line", "the moved set from every `AC-<n>` the record holds",
                     id="ids-read-from-anywhere"),
        pytest.param(_form_records_the_move_durably, ", with the move or after a refusal of the check", " after a "
                     "refusal of the check", id="move-edits-unrecorded"),
        pytest.param(_form_records_the_move_durably, ", and only a path inside the work tree `git rev-parse "
                     "--show-toplevel` prints is recorded", "", id="outside-path-recorded"),
        pytest.param(_form_records_the_move_durably, ", or you for an Operator notes entry or an answer to another "
                     "escalation that the re-read at each cycle's start finds", "", id="other-rulings-unrecorded"),
        pytest.param(_form_records_the_move_durably, "(the `/ucg-resolve` close, you at the operator's written "
                     "direction in an attended run, or", "(", id="attended-unrecorded"),
        pytest.param(_form_returns_a_moved_ac, " A written return of a moved AC to the story is applied by the "
                     "`/ucg-resolve` close, or by you at the operator's written direction in an attended run: it "
                     "deletes the AC's line from the record, and the record once no AC line is left, so no check runs "
                     "then; puts the numbered item back under its old number; takes its entry out of the H2 note; "
                     "restores it to the checklist's `acceptanceCriteria`; and logs its open `gate-gap:` lines again "
                     "without the `owned-by` marker.", "", id="never-returned"),
        pytest.param(_form_returns_a_moved_ac, ", and the record once no AC line is left, so no check runs then", "",
                     id="empty-record-kept"),
        pytest.param(_form_returns_a_moved_ac, " restores it to the checklist's `acceptanceCriteria`;", "",
                     id="checklist-unrestored"),
        pytest.param(_form_returns_a_moved_ac, " takes its entry out of the H2 note;", "", id="note-kept"),
        pytest.param(_form_returns_a_moved_ac, "logs its open `gate-gap:` lines again without the `owned-by` marker",
                     "leaves its open `gate-gap:` lines as they are", id="lines-stay-owned"),
        pytest.param(_form_returns_a_moved_ac, " The advance route removes the record once the commit that carries "
                     "the gate's files is made (\"Commit the gate's evidence before the next story starts\", above).",
                     "", id="record-outlives-the-story"),
        pytest.param(_form_hands_its_lines_to_the_owner, "with `owned-by` the same owner per the same ruling",
                     "unchanged", id="open-lines-stay-in-scope"),
        pytest.param(_form_parks_each_moved_ac_once, "append one ledger row per moved AC", "append no ledger row",
                     id="no-row"),
        pytest.param(_form_parks_each_moved_ac_once, ", written once, as an owned line's row is", "",
                     id="row-every-cycle"),
        pytest.param(_form_parks_each_moved_ac_once, "and a `suggested_action` naming the owner", "",
                     id="owner-unnamed-in-the-row"),
        pytest.param(_form_parks_each_moved_ac_once, " and each owned `gate-gap:` line on it, which then writes no row "
                     "of its own", "", id="one-row-per-owned-line-too"),
        pytest.param(_form_leaves_a_decomposed_child_alone, "A decomposed child's AC is not moved in this form",
                     "A decomposed child's AC is moved in its parent's story file", id="child-moved-in-the-parent"),
        pytest.param(_form_leaves_a_decomposed_child_alone, "`/ucg-resolve` records `defer` for such a move and "
                     "proposes a re-plan of the split instead", "`/ucg-resolve` closes it", id="child-closes"),
        pytest.param(_form_has_no_waiver_and_no_reloop, "WAIVED is no route for a moved AC", "WAIVED is a route for "
                     "a moved AC", id="waived"),
        pytest.param(_form_has_no_waiver_and_no_reloop, "Every gate cycle of a story with that record names the "
                     "main-tree story file and its sources", "The re-gate after a move names the main-tree story file",
                     id="re-gate-only"),
    ],
)
def test_each_form_clause_rejects_its_one_clause_mutant(clause, old, new):
    form = _flat(_paragraph(_read(_GATE), _FORM_HEAD))
    assert form.count(old) == 1, "the mutant must change the one clause it names"
    mutant = form.replace(old, new)
    assert mutant != form
    assert clause(form) and not clause(mutant)


@pytest.mark.parametrize(
    ("predicate", "old", "new"),
    [
        pytest.param(_route_names_the_form, " and its `.moved-<story_id>` record", "", id="close-without-a-record"),
        pytest.param(_route_names_the_form, ", logging their in-session ruling as a named Operator notes entry in "
                     "`.decision-log.md` and citing it as `Operator notes <entry>`", "", id="attended-ruling-uncited"),
        pytest.param(_route_names_the_form, ", the AC's open `gate-gap:` lines logged again as owned", "",
                     id="attended-lines-unowned"),
        pytest.param(_route_names_the_form, " For a decomposed child's AC, record `defer`, propose the re-plan and "
                     "stop there, re-gating nothing.", "", id="attended-child-re-gated"),
        pytest.param(_route_names_the_form, "stop there, re-gating nothing", "re-gate the same commit",
                     id="attended-child-re-gates"),
    ],
)
def test_each_route_clause_rejects_its_one_clause_mutant(predicate, old, new):
    route = _flat(_operator_route(_read(_GATE)))
    assert route.count(old) == 1
    mutant = route.replace(old, new)
    assert mutant != route
    assert predicate(route) and not predicate(mutant)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_WHOLE_CRITERION[1], _WHOLE_CRITERION[0], id="whole-criterion-owned"),
        pytest.param(_SOURCE[1], _SOURCE[0], id="source-list"),
        pytest.param("whoever applies that form, for any written ruling (the `/ucg-resolve` close, you in an attended "
                     "run, or the re-read at each cycle's start below, which takes the latest ruling for each AC as it "
                     "does for each line), writes the story's `.moved-<story_id>` record and logs",
                     "whoever records the move logs", id="nobody-writes-the-record"),
        pytest.param(", which takes the latest ruling for each AC as it does for each line", "",
                     id="move-rulings-unordered"),
        pytest.param(", and those lines reach the ledger inside the moved AC's row and not as rows of their own", "",
                     id="a-row-per-line"),
        pytest.param(_RECORD_RETIRED[1], _RECORD_RETIRED[0], id="record-kept-after-the-commit"),
        pytest.param(" (the resume after a commit hook's escalation included)", "", id="record-kept-on-a-resume"),
        pytest.param(", or a resume finds the gate's files committed already", "", id="record-kept-when-committed"),
        pytest.param(_OWNED_ROW[1], _OWNED_ROW[0], id="owned-line-own-row"),
        pytest.param(_CARRY_ROW[1], _CARRY_ROW[0], id="carry-line-own-row"),
    ],
)
def test_the_owned_paragraph_and_the_ledger_name_the_move(old, new):
    gate = _read(_GATE)
    assert gate.count(old) == 1
    assert _rules_the_route(gate)
    assert not _rules_the_route(gate.replace(old, new))


@pytest.mark.parametrize("where", ["reloop-bullet", "ledger-schema"])
def test_the_form_is_anchored_in_the_operator_route(where):
    live = _read(_GATE)
    form = _paragraph(live, _FORM_HEAD)
    without = live.replace(form + "\n\n", "", 1)
    anchor = "- **`escalate`**" if where == "reloop-bullet" else "## Deferred-work ledger schema"
    mutant = without.replace(anchor, form + "\n\n" + anchor, 1)
    assert mutant != without and _FORM_HEAD in mutant
    assert not _form_is_in_the_route(mutant)
    assert all(clause(_paragraph(mutant, _FORM_HEAD)) for clause in _FORM_CLAUSES)


_ESCALATE_CASE = (
    "or any gate cycle of a story with a `.moved-<story_id>` record whose check exits 1 or 2, under \"Run the gate\""
)


def test_the_escalate_bullet_names_the_refused_check():
    bullet = next(ln for ln in _read(_GATE).splitlines() if ln.startswith("- **`escalate`**"))
    assert _ESCALATE_CASE in bullet and "a FAIL only operator evidence can change" in bullet
    pre = next(ln for ln in _gate_pre_edit(_read(_GATE)).splitlines() if ln.startswith("- **`escalate`**"))
    assert _ESCALATE_CASE not in pre


def test_the_new_gate_prose_holds_no_em_dash_and_no_gate_eval_change():
    live = _read(_GATE)
    for added in (_paragraph(live, _CHECK_HEAD), _paragraph(live, _FORM_HEAD), *(n for _, n in _GATE_EDITS)):
        assert chr(0x2014) not in added
    assert "--moved" not in _read(_SKILL_ROOT / "scripts" / "gate_eval.py")
    # The partial-AC sentence and the close the earlier prose tests pin keep their words.
    route = _flat(_operator_route(live))
    assert "asks the operator to record the rest or to narrow or move the AC in writing" in route


# --- ucg-resolve, execute.md, define-done.md, docs ------------------------------------


def _resolve_waits_for_the_form(close: str, resolve: str | None = None) -> bool:
    """The close bullet's rules, and the `.decisions.json` reader contract in
    section 3, which `resolve` (the whole file, flattened) holds."""
    return bool(
        _RESOLVE_WAITS in close
        and _RESOLVE_RECORDS in close
        and _RESOLVE_RETURN in close
        and _RESOLVE_CHILD in close
        and _RESOLVE_REFUSAL in close
        and (resolve is None or _RESOLVE_CONTRACT in resolve)
        and "record it, naming each AC a move retires, then close." in close
        # The marker is the two lines it always was: the moved set lives in the record.
        and "as two lines, `sha=` the assessed commit the sidecar names" in close
        and "moved=" not in close
    )


def test_ucg_resolve_closes_on_a_move_only_once_the_form_is_on_disk():
    resolve = _read(_RESOLVE)
    assert _resolve_waits_for_the_form(_close_bullet(resolve), _flat(resolve))
    pre = _resolve_pre_edit(resolve)
    assert not _resolve_waits_for_the_form(pre, pre)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(" Until it does, record `defer`.", "", id="closes-before-the-edit"),
        pytest.param("and a note under an H2 heading of its own after that section", "and a note in its place",
                     id="note-in-place"),
        pytest.param("write `{workflow.implementation_artifacts}/.moved-<story_id>`, one line per AC it moves, opened "
                     "by its `AC-<n>`, `AC-<n> to <owner> per <ruling>`, adding to any lines already there, and", "and",
                     id="no-record"),
        pytest.param("adding to any lines already there", "in place of any lines there", id="earlier-moves-lost"),
        pytest.param(", and an `oracle=<absolute path>` line for each oracle source the operator edited with the move "
                     "(a relative one resolved against `{project-root}`, and only a path inside the work tree `git "
                     "rev-parse --show-toplevel` prints)", "", id="move-edits-unrecorded"),
        pytest.param("; log each open `gate-gap:` line on the moved AC again, under the story's key, with `owned-by` "
                     "the same owner per the same ruling", "", id="open-lines-unowned"),
        pytest.param("which records it for a reader and which no step reads", "which the next gate reads",
                     id="log-line-read"),
        pytest.param(" " + _RESOLVE_RETURN, "", id="return-unapplied"),
        pytest.param("record `defer` and propose a re-plan of the split instead", "edit the parent's story file",
                     id="child-moved-in-the-parent"),
        pytest.param("opens with \"The moved-AC check refused (exit 1)\"", "says the check refused",
                     id="refusal-unkeyed"),
        pytest.param(" and you have added each source they edited inside the work tree to `.moved-<story_id>` as an "
                     "`oracle=<absolute path>` line", "", id="sources-unrecorded"),
        pytest.param(", or once they return the AC in writing", "", id="return-closes-nothing"),
        pytest.param("only once the operator states in writing that each source it names no longer lists the AC for "
                     "this story", "as soon as the form is on disk", id="refusal-closes-unchanged"),
        pytest.param("closes at once when it is the story's first exit-2 refusal at that commit; when it says one came "
                     "before at that commit, it closes only once the operator confirms in writing that trace can "
                     "write its files there, and until then record `defer`", "closes at once",
                     id="exit-2-unbounded"),
        pytest.param("as two lines, `sha=` the", "as lines, `moved=` the moved ACs, `sha=` the", id="marker-moved"),
        pytest.param("Every reader of the file but one keys", "Every reader of the file keys", id="contract-unchanged"),
        pytest.param(", which reads the `answer` and the `history` of each `close` entry and applies only the latest "
                     "ruling for each line or AC: a later return or reassignment replaces an earlier one", "",
                     id="reader-unnamed"),
    ],
)
def test_the_resolve_predicate_rejects_a_mutant(old, new):
    resolve = _flat(_read(_RESOLVE))
    close = _close_bullet(_read(_RESOLVE))
    assert resolve.count(old) == 1
    mutant = resolve.replace(old, new)
    assert not _resolve_waits_for_the_form(close.replace(old, new), mutant)


def test_the_resolve_additions_stay_inside_the_close_bullet():
    """The close bullet is sliced up to the next `- **`` bullet or blank line,
    so an addition after either would leave the slice."""
    resolve = _read(_RESOLVE)
    close = _close_bullet(resolve)
    for _, new in _RESOLVE_EDITS[:2]:
        assert new in close
    # The reader contract lives in section 3, outside the close bullet.
    assert _RESOLVE_CONTRACT not in close and _RESOLVE_CONTRACT in _flat(resolve)
    assert _flat(resolve).count(_RESOLVE_WAITS) == 1


def _execute_regates_after_a_move(fourth: str) -> bool:
    flat = _flat(fourth)
    return all(new in flat for _, new in _EXECUTE_EDITS)


def test_the_fourth_resume_case_reads_the_main_tree_story_file_and_the_check():
    execute = _read(_EXECUTE)
    assert _execute_regates_after_a_move(_fourth_case(execute))
    assert not _execute_regates_after_a_move(_fourth_case(_pre_edit(execute, _EXECUTE_EDITS)))


def test_a_retired_number_is_never_reused():
    define_done = _read(_DEFINE_DONE)
    step = _flat(_split_step(define_done))
    assert all(new in step for _, new in _DEFINE_DONE_EDITS)
    assert "numbered after the story's last AC" not in step
    pre = _flat(_split_step(_pre_edit(define_done, _DEFINE_DONE_EDITS)))
    assert not any(new in pre for _, new in _DEFINE_DONE_EDITS)


def test_the_gate_model_says_what_the_move_and_the_check_do():
    model = _read(_GATE_MODEL)
    assert _GATE_MODEL_ANCHOR + _GATE_MODEL_ADDED in model
    assert _GATE_MODEL_ADDED not in _gate_model_pre_edit(model)
    # The pinned sentences of the operator-evidence passage keep their words.
    assert "counted `pass` record" in model and "is still owed: the record covers only part of" in _flat(model)
    assert not re.search(r"correct-course`? narrows", _flat(model))


_FRAGMENT_SAYS = (
    "type: fixed",
    "scope: ultracode-goal, ucg-resolve",
    "issues: [222]",
    "leaves the story's numbered list for a section of its own after `## Acceptance Criteria`",
    "Its number is never reused, no other criterion is renumbered",
    "`/ucg-resolve` closes on a move only once the story file carries that form",
    "a per-story `.moved-<story_id>` record",
    "A decomposed child's criterion is not moved this way",
    "names the main-tree story file, and every recorded oracle source, to trace",
    "A later written return of the criterion undoes the form",
    "40 or 64 hex digits, never a prefix",
    "at once the first time at that commit and on the operator's written confirmation after that",
    "`moved_ac_check.py` reads TEA's coverage matrix as `operator_owed.py` does, checked against the full sha",
    "and is never re-looped",
    "opens with `The moved-AC check refused` and its exit code",
    "one `med` deferred-work row per moved criterion",
    "A passed check leaves the gate's routes as they were",
)


def test_the_fragment_says_what_the_prose_does():
    fragment = _flat(_read(_FRAGMENT))
    assert [s for s in _FRAGMENT_SAYS if s not in fragment] == []
    assert chr(0x2014) not in fragment


# --- operator_owed.py reads the form's note as no AC, folding into none ------------


def _operator_owed():
    spec = importlib.util.spec_from_file_location("operator_owed", _SKILL_ROOT / "scripts" / "operator_owed.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _ac(n: int, tag: str | None) -> str:
    gate_ability = f"   **Gate-ability:** {tag}.\n" if tag else ""
    return f"{n}. **Criterion {n}.**\n   **Verification:** case-{n}.\n{gate_ability}"


# AC 6 carries no tag line at all, AC 7 is the operator-evidence AC the operator
# moved, and AC 8 is one still owed.
_KEPT = {1: "ci-machine", 2: "ci-machine", 3: "ci-machine", 4: "ci-machine", 5: "ci-machine", 6: None,
         8: "operator-evidence"}
_NOTE = "The former AC 7 is retired from this story: owned-by 4-5 per decision r-1a2b3c4d."
_QUOTING_NOTE = "The former AC 7, **Gate-ability:** operator-evidence, now belongs to story 4-5."


def _story(acs: dict[int, str | None], after_six: str = "", section: str = "") -> str:
    body = ""
    for n in sorted(acs):
        body += _ac(n, acs[n])
        if n == 6 and after_six:
            body += after_six + "\n"
        body += "\n"
    return f"# Story 4-2\n\n## Acceptance Criteria\n\n{body}{section}## Tasks\n\n- [ ] Task 1 (AC: 1)\n"


def _numbers(owed, story: str) -> list[int]:
    (section,) = owed._AC_SECTION.findall(story)
    return [int(m.group(1)) for line in section.splitlines() if (m := owed._AC_START.match(line))]


def test_the_forms_note_starts_no_ac_and_folds_into_none():
    owed = _operator_owed()
    form = _story(_KEPT, section="## Moved out of this story\n\n" + _NOTE + "\n\n")
    assert _numbers(owed, form) == [1, 2, 3, 4, 5, 6, 8]
    assert owed.operator_acs(form) == {8} == owed.operator_acs(_story(_KEPT))
    # The heading of its own ends the section even for a note that breaks the
    # no-tag rule, which is there for the parsers that do not stop at it.
    quoting = _story(_KEPT, section="## Moved out of this story\n\n" + _QUOTING_NOTE + "\n\n")
    assert owed.operator_acs(quoting) == {8}


def test_a_note_left_in_the_list_retags_the_ac_above_it():
    """The twin: a note "in its place" that quotes the moved AC's tag folds into
    AC 6, which then reads as an operator-evidence AC it never was."""
    owed = _operator_owed()
    in_place = _story(_KEPT, after_six=_QUOTING_NOTE)
    assert _numbers(owed, in_place) == [1, 2, 3, 4, 5, 6, 8]
    assert owed.operator_acs(in_place) == {6, 8}


def test_a_note_that_keeps_the_number_is_read_as_the_ac():
    """The other twin: a note numbered as the moved AC starts AC 7 again, which
    a matrix row `AC-7` maps onto."""
    owed = _operator_owed()
    numbered = _story(_KEPT | {7: None}).replace("7. **Criterion 7.**", "7. Moved to story 4-5.")
    assert 7 in _numbers(owed, numbered)
    assert owed.operator_acs(numbered) == {8}
