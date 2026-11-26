#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for a downgrade the story's own acceptance criterion prescribes (#282).

Under `--profile production`, `gate_eval.py` downgrades an `advance` to `reloop`
when a production signal fails, and it has no waiver for one. A story's AC
ordered two steps with a bare timer, and TEA's test review scores every such
timer HIGH, which holds the score under 80. No change to the code or the tests
clears that finding while the AC stays met, yet the `reloop` route sent every
downgrade through `bmad-correct-course` and a re-run, so the story re-looped
until its turn ceiling escalated it as `budget-overrun`, a sizing decision that
does not name the AC. The fix is prose, and `gate_eval.py` still prints
`reloop`:

  - gate.md's `reloop` bullet gains an indented paragraph: on a downgrade, read
    the failed signal's findings against the story's ACs before the generalize
    step; when every finding behind the failure is behaviour an AC prescribes,
    take `escalate` with `kind` `ac-amendment-needed`, whose `decision_needed`
    names the commit under assessment and quotes each AC as it stands, beside
    the finding it forces and the amendment proposed (so a later escalation
    mints an id of its own), with no `class:` line and no
    `bmad-correct-course`; a finding the operator ruled not prescribed is not
    prescribed; the amendment is the operator's own edit, and for a decomposed
    child it is stated in the parent's story file, which the run never edits;
    an amendment, unlike a move, retires nothing a sibling reads; every gate
    cycle after the close names the main-tree story file to trace, since no commit
    carries the amendment before the story advances; a partly prescribed set
    and a signal with no finding to read keep the re-loop. The paragraph names
    no turn ceiling;
  - the `escalate` list names the case;
  - execute.md names the kind beside the other live kinds;
  - `/ucg-resolve` closes it once the story file (a child's parent's) states
    the amended AC, or on the operator's written ruling that a finding is not
    prescribed, logged under the story's key; it records `defer` while an AC
    reads as `decision_needed` quotes it, leaves the turn count standing, and
    edits no AC itself;
  - docs/gate-model.md and docs/how-it-works.md describe the route;
  - no script names the kind, and the scripts read it as a decision a resume
    stops on, never a handoff; the reason string the paragraph keys on is the
    one `gate_eval.py` prints.

Each prose predicate has a twin: the text as it stood on main, rebuilt from the
live text by taking the additions out, meets none of it, and one-clause mutants
are each caught by their clause. The script tests read the live paragraph too,
so they fail on main, save the handoff test, which is a regression guard for
unchanged scripts whose twins patch the handoff sets.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import json
import re
import time
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SKILL_ROOT.parents[1]
_SCRIPTS = _SKILL_ROOT / "scripts"
_GATE = _SKILL_ROOT / "references" / "gate.md"
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_RESOLVE = _SKILL_ROOT.parent / "ucg-resolve" / "SKILL.md"
_GATE_MODEL = _REPO_ROOT / "docs" / "gate-model.md"
_HOW_IT_WORKS = _REPO_ROOT / "docs" / "how-it-works.md"
_FRAGMENT = _REPO_ROOT / "changes" / "gate-ac-prescribed-downgrade.yaml"

_KIND = "ac-amendment-needed"
_HEAD = "**A downgrade the story's own AC prescribes is not a re-loop.**"
_CLAUSE = "; a downgrade the story's own AC prescribes, above"
_RED_BACKFILL_HEAD = "**A red backfill sweep and the `gate-gap:` lines take this route their own way.**"
_NARROWING_HEAD = "**Get an AC narrowed in writing before committing a case that pins behaviour it forbids.**"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i : text.index(end, i)]


def _reloop_bullet(gate: str) -> str:
    """The reloop route's own text, as test_reloop_scope_prose.py slices it."""
    return _between(gate, "- **`reloop`**", "- **`escalate`**")


def _escalate_bullet(gate: str) -> str:
    return next(line for line in gate.splitlines() if line.startswith("- **`escalate`**"))


def _raw_paragraph(gate: str) -> str:
    """The paragraph as the file holds it, its two-space indent included, or ''."""
    if gate.count(_HEAD) != 1:
        return ""
    start = gate.index(_HEAD) - 2
    return gate[start : gate.index("\n\n", start)]


def _paragraph(gate: str) -> str:
    return _flat(_raw_paragraph(gate)).strip()


def _gate_pre_edit(gate: str) -> str:
    """gate.md as it stood on main: no paragraph and no clause in the escalate list."""
    return gate.replace("\n\n" + _raw_paragraph(gate), "", 1).replace(_CLAUSE, "", 1)


# --- gate.md: the paragraph -------------------------------------------------------

_CHECKS = {
    "keys on the downgrade's own reason": lambda s: (
        "On a `reloop` whose `reasons` hold `production signal failed; advance downgraded to reloop` (a PASS or "
        "WAIVED gate, with no gate FAIL)" in s
    ),
    "takes only a signal that failed on a file the script read": lambda s: (
        "take each production signal that failed on a file the script read (a test-review score below 80, a "
        "`Block`, an NFR `FAIL`)" in s
    ),
    "reads the findings behind the failure against the ACs, before the generalize step": lambda s: (
        "read the findings behind its failure (each violation a failed test review deducts for, each criterion a "
        "failed NFR assessment rates `FAIL`) against the story's acceptance criteria before the generalize step "
        "above starts" in s
    ),
    "says when a finding is prescribed": lambda s: (
        "A finding is prescribed when an AC, as written, requires the very behaviour the finding faults, so that no "
        "change to the code or the tests clears it while the AC stays met" in s
    ),
    # The operator's written ruling, logged by the /ucg-resolve close, outranks the conductor's reading.
    "takes a finding the operator ruled not prescribed as not prescribed": lambda s: (
        "A finding the operator has ruled not prescribed (a ruling `/ucg-resolve` logs under the story's key) is not "
        "prescribed: the next gate re-loops on it." in s
    ),
    # Every failed signal read, none of them with nothing listed, and none of their findings unprescribed.
    "escalates only when every finding of every failed signal is prescribed": lambda s: (
        "When every production signal that failed was read and has findings behind its failure, and every one of "
        "those findings is prescribed, no re-loop changes the verdict, since no re-loop changes the AC" in s
    ),
    "takes escalate with the kind": lambda s: bool(re.search(r"take `escalate` with `kind` `ac-amendment-needed`", s)),
    # `source` and `evidence` feed the minted id and what the operator reads.
    "fills source and evidence from the failed signal's file": lambda s: (
        "Its `source` is the failed signal's file (the test review's, when it and the NFR assessment both failed)" in s
        and "its `evidence` is the line of the first such finding, quoted from that file" in s
    ),
    # The id is minted from kind, source and decision_needed: naming the commit and the AC's text keeps a later
    # escalation from minting the id a close already holds, and the quote is what the close compares.
    "names the commit and quotes each AC, the finding it forces and the amendment": lambda s: (
        "Its `decision_needed` names the commit under assessment and, for each such AC, quotes the AC as it stands "
        "and names the finding it forces and the amendment you propose, so a later escalation of the story is a "
        "decision of its own and never one `/ucg-resolve` has closed already." in s
    ),
    "spends no re-loop": lambda s: "Write no `class:` line, start no `bmad-correct-course` and re-run nothing" in s,
    "says the gate has no waiver": lambda s: (
        "the gate has no waiver for a failed production signal, and TEA's test review waives no violation for the "
        "story's context" in s
    ),
    "waits on the operator's own amendment": lambda s: (
        "so the story stays escalated until its story file states the amended AC" in s
        and "That amendment is the operator's own edit, never the run's" in s
    ),
    "gates the re-driven story in full": lambda s: (
        "the resume after the `/ucg-resolve` close drives the story again and gates it as the full instrument, since "
        "the AC it is measured against has changed." in s
    ),
    # Trace reads the story's criteria in the gate worktree, and the amendment is uncommitted until the advance.
    "names the main-tree story file to trace after the close": lambda s: (
        "No commit carries the amendment before the story advances, so the gate worktree's copy of the story file "
        "still states the old AC." in s
        and "On every gate cycle of the story after that close (its `.decision-log.md` entry under the story's key is "
        "the record), name to trace, absolute in the main tree, the story file trace reads the story's criteria from "
        "(a decomposed child's parent's), as a gate cycle after a move does: that name is one more beside those "
        "\"Run the gate\" lists." in s
    ),
    "states a decomposed child's AC in the parent's story file": lambda s: (
        "A decomposed child has no story file of its own: its ACs are only the parent ACs its sprint-status row "
        "claims, so `decision_needed` names the parent's story file, and the amended AC is stated there, by the "
        "operator's own edit of a file the run never edits and every sibling reads." in s
    ),
    "says an amendment, unlike a move, retires nothing a sibling reads": lambda s: (
        "An amendment keeps the AC's number and its claim, so, unlike a move, it retires nothing a sibling reads." in s
    ),
    "keeps the route for findings no AC prescribes, leaving the prescribed ones unfixed": lambda s: (
        "Otherwise the route above stands, for each finding no AC prescribes" in s
        and "name the prescribed findings in this re-loop's `.decision-log.md` entry, give them no `class:` line and "
        "leave them unfixed, since a fix would break the AC" in s
        and "the next gate takes this paragraph if the downgrade still stands" in s
    ),
    "keeps the route for a signal with no finding to read": lambda s: (
        "and for a signal that failed with no finding to read (no file given, a file missing or unreadable, a score "
        "or status that could not be found, an NFR status of `NOT_ASSESSED`, or no finding listed behind the "
        "failure)" in s
    ),
}


def test_the_paragraph_states_its_contract():
    gate = _read(_GATE)
    paragraph = _paragraph(gate)
    assert paragraph.startswith(_HEAD)
    assert sorted(name for name, check in _CHECKS.items() if not check(paragraph)) == []
    # Twin: the same checks find nothing in the rest of the file.
    rest = _flat(gate.replace(_raw_paragraph(gate), ""))
    assert sorted(name for name, check in _CHECKS.items() if not check(rest)) == sorted(_CHECKS)


@pytest.mark.parametrize(
    ("old", "new", "lost"),
    [
        pytest.param(
            "every one of those findings is prescribed", "any of those findings is prescribed",
            "escalates only when every finding of every failed signal is prescribed",
            id="one-prescribed-finding-escalates",
        ),
        pytest.param(
            "When every production signal that failed was read and has findings behind its failure,",
            "When a production signal that failed was read,",
            "escalates only when every finding of every failed signal is prescribed",
            id="an-unread-signal-beside-escalates",
        ),
        pytest.param(
            " by the operator's own edit of a file the run never edits and every sibling reads", " by the run",
            "states a decomposed child's AC in the parent's story file", id="run-edits-the-parent",
        ),
        pytest.param(
            "`decision_needed` names the parent's story file", "`decision_needed` names the child's story file",
            "states a decomposed child's AC in the parent's story file", id="child-file-named",
        ),
        pytest.param(
            "That amendment is the operator's own edit, never the run's", "Make that amendment yourself",
            "waits on the operator's own amendment", id="run-amends-the-ac",
        ),
        pytest.param(
            "Write no `class:` line, start no `bmad-correct-course` and re-run nothing",
            "Run `bmad-correct-course` once more",
            "spends no re-loop", id="one-more-reloop",
        ),
        pytest.param(
            ", or no finding listed behind the failure)", ")",
            "keeps the route for a signal with no finding to read", id="empty-list-escalates",
        ),
        pytest.param(
            "Otherwise the route above stands, for each finding no AC prescribes",
            "Otherwise escalate as well, for each finding no AC prescribes",
            "keeps the route for findings no AC prescribes, leaving the prescribed ones unfixed",
            id="mixed-set-escalates",
        ),
        pytest.param(
            " before the generalize step above starts", " after the generalize step",
            "reads the findings behind the failure against the ACs, before the generalize step",
            id="read-after-generalizing",
        ),
        pytest.param(
            "Its `source` is the failed signal's file", "Its `source` is the trace report's path",
            "fills source and evidence from the failed signal's file", id="source-the-trace-report",
        ),
        pytest.param(
            "(the test review's, when it and the NFR assessment both failed)",
            "(the NFR assessment's, when it and the test review both failed)",
            "fills source and evidence from the failed signal's file", id="source-swapped-when-both-failed",
        ),
        pytest.param(
            "its `evidence` is the line of the first such finding, quoted from that file",
            "its `evidence` is the verdict's first reason",
            "fills source and evidence from the failed signal's file", id="evidence-the-first-reason",
        ),
        # The decision as first written: no commit, so a repeat at a later commit mints the closed id.
        pytest.param(
            "names the commit under assessment and, for each such AC,", "names, for each such AC,",
            "names the commit and quotes each AC, the finding it forces and the amendment", id="no-commit-named",
        ),
        # The AC named but not quoted: the close has nothing to compare the story file with.
        pytest.param(
            "quotes the AC as it stands and names the finding it forces", "names the AC and the finding it forces",
            "names the commit and quotes each AC, the finding it forces and the amendment", id="ac-not-quoted",
        ),
        pytest.param(
            "is not prescribed: the next gate re-loops on it.", "is still prescribed: the next gate escalates on it.",
            "takes a finding the operator ruled not prescribed as not prescribed", id="ruling-overridden",
        ),
        pytest.param(
            ", and TEA's test review waives no violation for the story's context", "",
            "says the gate has no waiver", id="tea-waiver-dropped",
        ),
        pytest.param(
            ", since the AC it is measured against has changed.", ".",
            "gates the re-driven story in full", id="no-reason-for-the-full-gate",
        ),
        # Trace left on the worktree's copy, which still states the old AC.
        pytest.param(
            ", absolute in the main tree, the story file", " the story file",
            "names the main-tree story file to trace after the close", id="worktree-copy-named",
        ),
        pytest.param(
            "On every gate cycle of the story after that close", "On the first gate cycle after that close",
            "names the main-tree story file to trace after the close", id="named-once",
        ),
        pytest.param(
            " (a decomposed child's parent's), as a gate cycle", ", as a gate cycle",
            "names the main-tree story file to trace after the close", id="child-names-no-parent",
        ),
        pytest.param(
            "its ACs are only the parent ACs its sprint-status row claims", "its ACs are its parent's",
            "states a decomposed child's AC in the parent's story file", id="child-owns-every-parent-ac",
        ),
        pytest.param(
            "so, unlike a move, it retires nothing a sibling reads", "so, like a move, it retires the AC for each sibling",
            "says an amendment, unlike a move, retires nothing a sibling reads", id="amendment-retires",
        ),
    ],
)
def test_the_paragraph_pin_rejects_a_mutant(old, new, lost):
    paragraph = _paragraph(_read(_GATE))
    assert paragraph.count(old) == 1, "the mutant must change the one clause it names"
    assert not _CHECKS[lost](paragraph.replace(old, new))


def test_the_route_as_it_stood_meets_none_of_it():
    gate = _read(_GATE)
    pre = _gate_pre_edit(gate)
    assert _HEAD not in pre and _KIND not in pre and _CLAUSE not in pre
    assert len(gate) - len(pre) == 2 + len(_raw_paragraph(gate)) + len(_CLAUSE)
    old_reloop = _reloop_bullet(pre)
    # The route on main: every downgrade went through correct-course and a re-run.
    assert "or a production signal downgraded an advance" in old_reloop
    assert "Otherwise, run `bmad-correct-course` to diagnose and adjust, then re-run the story" in old_reloop
    # On main the red-backfill paragraph followed the bullet's first paragraph.
    assert "(`references/execute.md`, \"Promoting the turn-budget marker\").\n\n  " + _RED_BACKFILL_HEAD in pre
    assert sorted(name for name, check in _CHECKS.items() if not check(_flat(old_reloop))) == sorted(_CHECKS)


def _placed(gate: str) -> bool:
    """Inside the reloop bullet, after its first paragraph and before the red-backfill one, an indented
    paragraph of its own that names no turn ceiling and none of the strings the slices beside it reserve."""
    if gate.count(_HEAD) != 1:
        return False
    reloop = _reloop_bullet(gate)
    if _HEAD not in reloop:
        return False
    paragraph = _paragraph(gate)
    return bool(
        reloop.index("**within the remaining turn budget**") < reloop.index(_HEAD) < reloop.index(_RED_BACKFILL_HEAD)
        and "\n\n  " + _HEAD in reloop
        # The turn bound in any of its names, the counter file included.
        and not re.search(r"max_turns|turn (?:ceiling|budget|count)|\.budget-", paragraph)
        and "one finding" not in paragraph
        and "gate-gap:" not in paragraph
        and ".class-ledger-" not in paragraph
        and "operator_owed.py" not in paragraph
        and not re.search(r"\bgaps?\b|\bunkilled\b|\bunmeasured\b", paragraph)
    )


def test_the_paragraph_sits_inside_the_reloop_route():
    gate = _read(_GATE)
    assert _placed(gate)
    # The operator-evidence command still leads straight into the reloop bullet's
    # opening once the moved-AC paragraph is set aside (test_gate_moved_ac_regate_prose.py).
    assert "\n- **`reloop`** (gate_status FAIL, or a production signal downgraded an advance" in gate


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The ceiling named in the paragraph: the route would then hang on the turn bound.
        pytest.param(
            "if the downgrade still stands.", "if the downgrade still stands, within `{workflow.max_turns_per_story}`.",
            id="names-the-ceiling",
        ),
        # The bound named in other words.
        pytest.param(
            "if the downgrade still stands.", "if the downgrade still stands and turn budget remains.",
            id="names-the-budget",
        ),
        pytest.param(
            "if the downgrade still stands.", "if the downgrade still stands, within the story's turn count.",
            id="names-the-count",
        ),
        pytest.param(
            "if the downgrade still stands.",
            "if the downgrade still stands, unless `.budget-<story_id>.json` is at the ceiling.",
            id="names-the-counter-file",
        ),
        # Moved out of the bullet, to a top-level bullet before it.
        pytest.param("\n\n  " + _HEAD, "\n\n- " + _HEAD, id="top-level-bullet"),
    ],
)
def test_the_placement_pin_rejects_a_mutant(old, new):
    gate = _read(_GATE)
    assert gate.count(old) == 1
    assert not _placed(gate.replace(old, new, 1))


def test_the_paragraph_cites_the_narrowing_rule_execute_md_holds():
    """The paragraph leans on execute.md's rule that no re-loop changes an AC; the head it cites is real."""
    paragraph = _paragraph(_read(_GATE))
    cited = _NARROWING_HEAD.strip("*").rstrip(".")
    assert f'(`references/execute.md`, "{cited}")' in paragraph
    execute = _read(_EXECUTE)
    assert execute.count(_NARROWING_HEAD) == 1
    assert "no re-loop changes the AC" in execute[execute.index(_NARROWING_HEAD) :].split("\n\n")[0]


_NAMING_HEAD = "**Name the per-story paths trace writes, in either profile.**"
_AFTER_A_MOVE = (
    "on every gate cycle of a story with a `.moved-<story_id>` record, the story file trace reads the story's "
    "criteria from and every `oracle=` path that record lists, each named absolute in the main tree"
)


def _mirrors_the_naming_after_a_move(gate: str) -> bool:
    """The paragraph names the main-tree story file 'as a gate cycle after a move does': that naming is real,
    in the paragraph under "Run the gate" that bounds what trace is asked for, in the words the paragraph uses."""
    if gate.count(_NAMING_HEAD) != 1:
        return False
    naming = _flat(gate[gate.index(_NAMING_HEAD) :].split("\n\n")[0])
    run_the_gate = gate.index("## Run the gate")
    return bool(
        run_the_gate < gate.index(_NAMING_HEAD) < gate.index("## Route on the verdict")
        and _AFTER_A_MOVE in naming
        and "Ask for nothing beyond those names" in naming
        and "the story file trace reads the story's criteria from (a decomposed child's parent's), as a gate cycle "
        "after a move does" in _paragraph(gate)
    )


def test_the_main_tree_naming_is_the_one_a_move_takes():
    gate = _read(_GATE)
    assert _mirrors_the_naming_after_a_move(gate)
    # Twins: the move's naming gone from "Run the gate", and the gate as it stood on main.
    assert gate.count(_AFTER_A_MOVE) == 1
    assert not _mirrors_the_naming_after_a_move(gate.replace(_AFTER_A_MOVE, "on every gate cycle", 1))
    assert not _mirrors_the_naming_after_a_move(_gate_pre_edit(gate))


# --- gate.md: the escalate list ---------------------------------------------------


def test_the_escalate_bullet_names_the_case():
    gate = _read(_GATE)
    bullet = _escalate_bullet(gate)
    assert bullet.count(_CLAUSE) == 1
    assert bullet.index("`evaluated: false` above") < bullet.index(_CLAUSE) < bullet.index("budget exhausted")
    # The strings the moved-AC and operator-evidence pins hold stay whole.
    assert (
        "budget exhausted on a FAIL; a FAIL only operator evidence can change, above; or any gate cycle of a story "
        "with a `.moved-<story_id>` record whose check exits 1 or 2" in bullet
    )
    assert "a FAIL whose operator-evidence check could not read trace's coverage matrix, `evaluated: false` above" in bullet
    # Twin: the bullet on main does not name it.
    assert _CLAUSE not in _escalate_bullet(_gate_pre_edit(gate))


# --- execute.md: the live kind ----------------------------------------------------

_LIVE_KIND = (
    "So is `ac-amendment-needed`: a production signal failed on findings the story's own AC prescribes, which no "
    "re-loop clears, so the story waits for the operator's own amendment of that AC in its story file, or for a "
    "decomposed child in its parent's"
)


def _sidecar_section(execute: str) -> str:
    start = execute.index("### Escalation sidecar")
    return _flat(execute[start : re.compile(r"\n#{2,3} ").search(execute, start + 1).start()])


def _names_the_live_kind(execute: str, gate: str) -> bool:
    section = _sidecar_section(execute)
    if _LIVE_KIND not in section:
        return False
    tail = section[section.index(_LIVE_KIND) :].split(").")[0]
    cited = _HEAD.strip("*").rstrip(".")
    return f'(`references/gate.md`, "{cited}"' in tail and _HEAD in gate


def test_execute_names_the_live_kind():
    execute, gate = _read(_EXECUTE), _read(_GATE)
    assert _names_the_live_kind(execute, gate)
    assert "`kind` is **open vocabulary**" in execute
    # Twins: the kind renamed, the sentence removed (execute.md on main), and a gate with no such paragraph.
    assert not _names_the_live_kind(execute.replace("So is `ac-amendment-needed`", "So is `something-else`"), gate)
    sentence = " " + _LIVE_KIND + " (`references/gate.md`, \"A downgrade the story's own AC prescribes is not a re-loop\")."
    assert execute.count(sentence) == 1
    assert not _names_the_live_kind(execute.replace(sentence, "", 1), gate)
    assert not _names_the_live_kind(execute, _gate_pre_edit(gate))


# --- ucg-resolve: the close -------------------------------------------------------

_CLOSE_LEAD = "**Closing an `ac-amendment-needed` escalation needs the amended AC in the story file.**"

_RESOLVE_CHECKS = {
    "has a close rule for the kind": lambda r: r.startswith(_CLOSE_LEAD),
    "cites the gate's paragraph": lambda r: (
        "(`{ucg-root}/references/gate.md`, \"A downgrade the story's own AC prescribes is not a re-loop\")" in r
    ),
    "the amendment is the operator's": lambda r: "The amendment is the operator's own story edit" in r,
    "closes only once the story file states each amended AC": lambda r: (
        "once the story file states the amended text of each AC the escalation names, record the ruling and close" in r
    ),
    # Re-gating the same commit would repeat the downgrade: the amended AC needs the story driven again.
    "the resumed run re-drives the story": lambda r: (
        "record the ruling and close, and the resumed run drives the story again." in r and ".regate-" not in r
    ),
    # No reset, so the resume's step-0 ceiling read still applies; the text says so.
    "leaves the turn count standing": lambda r: (
        "Its turn count stands, so a count already at the ceiling escalates the resume as `budget-overrun` first." in r
        and ".budget-" not in r
    ),
    "defers while an AC still reads as decision_needed quotes it": lambda r: (
        "While an AC it names still reads as `decision_needed` quotes it, say which and record `defer`: a resume "
        "would drive the story to the same downgrade." in r
    ),
    "closes on a written not-prescribed ruling": lambda r: (
        "An operator's written ruling that the finding such an AC forces is not prescribed closes it too, in place of "
        "the amendment, and the next gate re-loops on that finding." in r
    ),
    # The gate keys its main-tree naming and its reading of a ruled finding on this entry.
    "logs the ruling under the story's key": lambda r: (
        "Log either ruling in `.decision-log.md` under the story's key, where every later gate cycle of the story "
        "reads it." in r
    ),
    "waits on the parent's story file for a decomposed child": lambda r: (
        "A decomposed child's AC lives in its parent's story file, which the run never edits and which every sibling "
        "reads, so for a child the close waits on the parent's story file stating the amended text, the operator's "
        "own edit of that file." in r
    ),
    "says an amendment, unlike a move, retires nothing a sibling reads": lambda r: (
        "An amendment keeps the AC's number and its claim, so, unlike a move, it retires nothing a sibling reads." in r
    ),
    "edits no AC itself": lambda r: "This surface never edits an AC itself." in r,
}


def _close_bullet(resolve: str) -> str:
    """ucg-resolve's `close` disposition as its neighbours' tests take it: up to the next bullet or blank line."""
    close = re.search(r"- \*\*`close`\*\*.*?(?=\n- \*\*`|\n\n)", resolve, re.DOTALL)
    return _flat(close.group(0)) if close else ""


def _resolve_unmet(resolve: str) -> list[str]:
    bullet = _close_bullet(resolve)
    if _CLOSE_LEAD not in bullet:
        return sorted(_RESOLVE_CHECKS)
    rule = bullet[bullet.index(_CLOSE_LEAD) :]
    return sorted(name for name, check in _RESOLVE_CHECKS.items() if not check(rule))


def test_ucg_resolve_closes_it_only_on_the_amended_ac():
    resolve = _read(_RESOLVE)
    assert _resolve_unmet(resolve) == []
    # The rule sits last in the close bullet, right before the `defer` bullet.
    assert "itself.\n- **`defer`**" in resolve
    # Twin: the SKILL.md on main, the rule cut out, meets none of it.
    start = resolve.index("  " + _CLOSE_LEAD)
    rule = resolve[start : resolve.index("- **`defer`**", start)]
    assert _resolve_unmet(resolve.replace(rule, "", 1)) == sorted(_RESOLVE_CHECKS)
    # Twin: the rule after a blank line has left the close bullet.
    assert _resolve_unmet(resolve.replace(rule, "\n" + rule, 1)) == sorted(_RESOLVE_CHECKS)


@pytest.mark.parametrize(
    ("old", "new", "lost"),
    [
        pytest.param(
            "once the story file states the amended text of each AC the escalation names, record the ruling and close",
            "record the ruling and close",
            "closes only once the story file states each amended AC", id="closes-before-the-edit",
        ),
        pytest.param(
            "still reads as `decision_needed` quotes it, say which and record `defer`",
            "still reads as `decision_needed` quotes it, say which and close anyway",
            "defers while an AC still reads as decision_needed quotes it", id="closes-on-the-old-ac",
        ),
        # The comparison as first written, against an earlier text nothing records.
        pytest.param(
            "still reads as `decision_needed` quotes it", "still reads as it did",
            "defers while an AC still reads as decision_needed quotes it", id="compares-with-nothing-recorded",
        ),
        pytest.param(
            "record the ruling and close, and the resumed run drives the story again.",
            "record the ruling, write `.regate-<story_id>` and close, and the resume re-gates that commit.",
            "the resumed run re-drives the story", id="re-gates-the-same-commit",
        ),
        pytest.param(
            "The amendment is the operator's own story edit", "The amendment is this surface's story edit",
            "the amendment is the operator's", id="surface-owns-the-amendment",
        ),
        pytest.param(
            "Its turn count stands, so a count already at the ceiling escalates the resume as `budget-overrun` first.",
            "It also deletes `.budget-<story_id>.json`.",
            "leaves the turn count standing", id="close-resets-the-count",
        ),
        pytest.param(
            "is not prescribed closes it too, in place of the amendment,", "is not prescribed is recorded as `defer`,",
            "closes on a written not-prescribed ruling", id="ruling-never-closes",
        ),
        pytest.param(
            "Log either ruling in `.decision-log.md` under the story's key,", "Log either ruling in `.decisions.json`,",
            "logs the ruling under the story's key", id="logged-off-the-story",
        ),
        pytest.param(
            "so, unlike a move, it retires nothing a sibling reads", "so, like a move, it retires the AC for each sibling",
            "says an amendment, unlike a move, retires nothing a sibling reads", id="amendment-retires",
        ),
        pytest.param(
            "so for a child the close waits on the parent's story file stating the amended text",
            "so for a child record `defer` and propose a re-plan",
            "waits on the parent's story file for a decomposed child", id="child-never-closes",
        ),
        pytest.param(
            "This surface never edits an AC itself.", "Write the amended AC into the story file yourself.",
            "edits no AC itself", id="surface-edits-the-ac",
        ),
    ],
)
def test_the_resolve_pin_rejects_a_mutant(old, new, lost):
    resolve = _read(_RESOLVE)
    assert _flat(resolve).count(old) == 1, "the mutant must change the one clause it names"
    bullet = _close_bullet(resolve)
    rule = bullet[bullet.index(_CLOSE_LEAD) :]
    assert not _RESOLVE_CHECKS[lost](rule.replace(old, new))


# --- the docs ---------------------------------------------------------------------

_GATE_MODEL_SAYS = (
    "One downgrade leaves the re-loop. When every failed signal's file was read and lists the findings behind the "
    "failure, and each of them is behaviour one of the story's own acceptance criteria prescribes",
    "The skill then stops with an escalation of kind `ac-amendment-needed` that names each such criterion, the "
    "finding it forces and a proposed amendment, and the story is driven again once its story file states the "
    "amended criterion (for a decomposed child, its parent's story file, which the run never edits), an edit only "
    "the operator makes.",
    "An amendment keeps the criterion's number and its claim, so, unlike a move, it retires nothing a sibling reads.",
    "`gate_eval.py` still prints `reloop` for such a story: the route is the skill's, read from the findings, and "
    "the gate has no waiver for a failed production signal.",
    "A finding no criterion prescribes keeps the re-loop, and so does a signal that failed with no finding to read",
)
# Every failed signal read and listing findings, every finding prescribed, and a decomposed child's parent's file.
_HOW_IT_WORKS_SAYS = (
    "A production-signal downgrade whose failed signals were all read and list findings, each of them behaviour one "
    "of the story's own acceptance criteria prescribes, escalates at once too, with kind `ac-amendment-needed`, since "
    "no re-loop changes the criterion: the story is driven again once the operator amends it in the story file (for "
    "a decomposed child, its parent's)."
)


def _gate_model_says(text: str) -> bool:
    if "## The production AND" not in text:
        return False
    section = _flat(_between(text, "## The production AND", "## The sweep-scope cap"))
    return all(clause in section for clause in _GATE_MODEL_SAYS)


def test_the_docs_name_the_route():
    model, how = _read(_GATE_MODEL), _read(_HOW_IT_WORKS)
    assert _gate_model_says(model)
    assert _HOW_IT_WORKS_SAYS in _flat(how)
    # The paragraph sits after the AND's diagram, and the light-profile sentence still closes the section.
    assert "class A,D,K verdict\n```\n\nOne downgrade leaves the re-loop." in model
    # Twins: the docs on main, each addition cut out.
    paragraph = model[model.index("One downgrade leaves the re-loop.") :].split("\n\n")[0]
    assert not _gate_model_says(model.replace(paragraph + "\n\n", "", 1))
    assert _HOW_IT_WORKS_SAYS not in _flat(how.replace(" " + _HOW_IT_WORKS_SAYS, "", 1))
    # The sentences the new text sits beside still say what they said: the script's verdict is unchanged.
    assert "any failure downgrades it to `reloop`" in model
    assert "escalates at once with kind `operator-evidence-owed`, since no re-loop can produce that evidence." in how


# --- the scripts read the kind as a decision ----------------------------------------


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_STORY = "61-1-sample-story"
_COMMIT = "4b6f0c1d2e3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c"
_LATER_COMMIT = "9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d"
_SOURCE = "_bmad-output/test-artifacts/test-review-61-1-sample-story.md"
_AC_AS_IT_STANDS = '"3. The reload starts 500 ms after the save."'
_FINDING_AND_AMENDMENT = (
    "The review faults its 500 ms timer as a hard wait (H1, HIGH); amend AC 3 to: "
    '"3. The reload starts once the save has answered."'
)


def _decision(commit: str | None) -> str:
    """A `decision_needed` in the shape the paragraph gives; `None` is the shape it first gave, with no commit."""
    lead = f"At commit {commit}: " if commit else ""
    return f"{lead}AC 3 reads {_AC_AS_IT_STANDS}. {_FINDING_AND_AMENDMENT}"


_SIDECAR = {
    "source": _SOURCE,
    "kind": _KIND,
    "decision_needed": _decision(_COMMIT),
    "evidence": "H1 hard wait (HIGH): tests/sample.spec.ts:42 waits 500 ms between the save and the reload.",
}


def _stops_on_it(preflight_check, drive_epic, impl: Path, project_root: Path, started: float) -> bool:
    """A resume reads the sidecar as an open decision, and the driver reads it as no handoff."""
    escalation = preflight_check._escalation_of(impl, _STORY, project_root)
    return bool(
        escalation["state"] == "open"
        and escalation["kind"] == _KIND
        and "blocker" in escalation
        and drive_epic.handoff_kind(impl, _STORY, started) is None
    )


def test_no_script_names_the_kind_and_a_resume_stops_on_it(tmp_path: Path, monkeypatch):
    """`kind` is open vocabulary, so no script changes for it. These pin that it stays a decision:
    decision-pending until /ucg-resolve closes it, and an escalation, not a handoff, to the driver."""
    scripts = sorted([*_SCRIPTS.glob("*.py"), *(_SCRIPTS / "hooks").glob("*.py"), *(_SCRIPTS / "lib").glob("*.py")])
    assert scripts
    assert [p.name for p in scripts if _KIND in _read(p)] == []
    preflight_check, drive_epic, red_ids = _load("preflight_check"), _load("drive_epic"), _load("red_ids")
    assert _KIND not in preflight_check._HANDOFF_KINDS | drive_epic.HANDOFF_KINDS
    impl = tmp_path / "impl"
    impl.mkdir()
    started = time.time()
    (impl / f"escalation-{_STORY}.json").write_text(json.dumps(_SIDECAR), encoding="utf-8")
    assert _stops_on_it(preflight_check, drive_epic, impl, tmp_path, started)
    # Twins: a handoff set that took the kind would let a run move past a story whose AC nobody amended.
    with monkeypatch.context() as patch:
        patch.setattr(drive_epic, "HANDOFF_KINDS", drive_epic.HANDOFF_KINDS | {_KIND})
        assert not _stops_on_it(preflight_check, drive_epic, impl, tmp_path, started)
    with monkeypatch.context() as patch:
        patch.setattr(preflight_check, "_HANDOFF_KINDS", preflight_check._HANDOFF_KINDS | {_KIND})
        assert not _stops_on_it(preflight_check, drive_epic, impl, tmp_path, started)
    # /ucg-resolve's close, keyed by the id red_ids.py mints, is read as closed.
    rid = red_ids.mint_id(_SIDECAR["kind"], _SIDECAR["source"], _SIDECAR["decision_needed"])
    (impl / ".decisions.json").write_text(
        json.dumps({"decisions": [{"id": rid, "answer": "AC 3 amended in the story file.", "action": "close"}]}),
        encoding="utf-8",
    )
    assert preflight_check._escalation_of(impl, _STORY, tmp_path)["state"] == "closed"


def _state_after_a_close(preflight_check, impl: Path, project_root: Path, closed: str, later: str) -> str:
    """How a resume reads a later sidecar of the story once /ucg-resolve has closed the first one."""
    red_ids = _load("red_ids")
    (impl / ".decisions.json").write_text(
        json.dumps({"decisions": [{"id": red_ids.mint_id(_KIND, _SOURCE, closed), "answer": "AC 3 amended.",
                                   "action": "close"}]}),
        encoding="utf-8",
    )
    sidecar = {**_SIDECAR, "decision_needed": later}
    (impl / f"escalation-{_STORY}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return preflight_check._escalation_of(impl, _STORY, project_root)["state"]


def test_a_later_escalation_of_the_story_mints_an_id_of_its_own(tmp_path: Path):
    """The id is minted from `kind`, `source` and `decision_needed`, and `source` is the same per-story test
    review every cycle, so only the decision can tell a later escalation from the one a close answered."""
    assert _CHECKS["names the commit and quotes each AC, the finding it forces and the amendment"](
        _paragraph(_read(_GATE))
    )
    red_ids, preflight_check = _load("red_ids"), _load("preflight_check")
    first = red_ids.mint_id(_KIND, _SOURCE, _decision(_COMMIT))
    later = red_ids.mint_id(_KIND, _SOURCE, _decision(_LATER_COMMIT))
    assert first != later
    impl = tmp_path / "impl"
    impl.mkdir()
    assert _state_after_a_close(preflight_check, impl, tmp_path, _decision(_COMMIT), _decision(_LATER_COMMIT)) == "open"
    # Twin: the decision as the paragraph first gave it names no commit, so the same AC, finding and amendment
    # at a later commit mint the closed id, and the resume never stops on the later escalation.
    assert _state_after_a_close(preflight_check, impl, tmp_path, _decision(None), _decision(None)) == "closed"


def _review_and_nfr(folder: Path, score: int, recommendation: str) -> tuple[Path, Path]:
    """A test review and an NFR assessment in TEA's labelled forms."""
    review = folder / f"test-review-{score}.md"
    review.write_text(f"**Quality Score**: {score}/100\n**Recommendation**: {recommendation}\n", encoding="utf-8")
    nfr = folder / "nfr-assessment.md"
    nfr.write_text("**Overall Status:** PASS\n", encoding="utf-8")
    return review, nfr


def test_the_reason_the_paragraph_keys_on_is_the_one_gate_eval_prints(tmp_path: Path):
    """The paragraph keys on a `reasons` string, which docs/_internal/STABILITY.md calls non-contractual
    wording: a reworded reason would switch the route off with every prose pin still green."""
    quoted = re.search(r"whose `reasons` hold `([^`]+)`", _paragraph(_read(_GATE)))
    assert quoted, "the paragraph quotes no reason"
    gate_eval = _load("gate_eval")
    review, nfr = _review_and_nfr(tmp_path, 74, "Request Changes")
    reasons: list[str] = []
    assert gate_eval.apply_production_and("advance", nfr, review, reasons) == ("reloop", "PASS", 74)
    assert quoted.group(1) in reasons
    # Twins: a review that passes prints no such reason, and a FAIL gate is not downgraded, so neither keys it.
    review, nfr = _review_and_nfr(tmp_path, 89, "Approve")
    reasons = []
    assert gate_eval.apply_production_and("advance", nfr, review, reasons) == ("advance", "PASS", 89)
    assert quoted.group(1) not in reasons
    review, nfr = _review_and_nfr(tmp_path, 74, "Request Changes")
    reasons = []
    assert gate_eval.apply_production_and("reloop", nfr, review, reasons)[0] == "reloop"
    assert quoted.group(1) not in reasons


# --- the change fragment ----------------------------------------------------------


def test_the_fragment_is_typed_changed_and_names_the_kind():
    fragment = _read(_FRAGMENT)
    assert fragment.startswith("type: changed\nscope: ultracode-goal, ucg-resolve\nsummary: |\n")
    assert fragment.endswith("\nissues: [282]\n")
    assert re.findall(r"(?m)^([a-z_]+):", fragment) == ["type", "scope", "summary", "issues"]
    flat = _flat(fragment)
    for token in (
        "escalation of `kind` `ac-amendment-needed`",
        "`gate_eval.py` is unchanged and still prints `reloop`",
        "the gate has no waiver for a failed production signal",
        "or of the parent's story file for a decomposed child, which the run never edits",
        "whose decision names the commit under assessment and quotes each criterion as it stands",
        "it writes no `class:` line and spends no re-loop",
        "or once the operator rules in writing that a finding is not prescribed",
        "records `defer` while a criterion still reads as the decision quotes it, and never edits a criterion itself",
        "drives the story again on the turn count it had",
        "names the main-tree story file to trace, since no commit carries the amendment before then",
        "A downgrade with findings no criterion prescribes re-loops for those findings as before",
        "`NOT_ASSESSED`",
    ):
        assert token in flat, token
    assert "\u2014" not in fragment and "\u00a7" not in fragment
