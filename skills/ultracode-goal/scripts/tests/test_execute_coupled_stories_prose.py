#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for two stories that are green only together (issue #181).

A sprint plan coupled two stories so that each one's commit was red without the
other's: the earlier story owed clauses only the later story's build could
satisfy. Step 5 advances a story only on its own green committed HEAD, so the
story loop had no route, and the conductor invented one: it moved the clauses
to the later story, in both story files, under a standing delegation UCG does
not recognise.

The story loop now names the case and pins:

  - the shapes that break the per-story artifacts are forbidden (one commit for
    both, an uncommitted earlier story, one gate commit), and driving the two
    rows as one unit is only the operator's re-plan, outside the run;
  - each clause moves forward only once a run on the earlier story's tree
    measures that its code exists only in the later story's build;
  - the move narrows the earlier story's AC, so it stays the operator's
    decision, as the 3.1.0 narrowing rule beside it keeps it: the ruling is an
    Operator notes entry given before launch that names both stories and
    authorizes the move, or the answer to a `coupled-stories` escalation, and a
    general or standing delegation is neither;
  - what the move writes depends on the pair: both story files state it when
    both have one; two decomposed children of one parent move a whole AC, and
    only one whose every clause is measured, and the new split record, both
    child rows' citations in `sprint-status.yaml` and both children's ATDD
    checklists carry the changed claim map, since the row is what step 1 hands
    the dev agent; an AC that also holds a clause no run measured, a child
    beside a story that has a file, or children of two parents, have no move,
    so no note authorizes one and the run escalates for a re-plan; the
    scaffolded cases move with their clause, and the log names both stories.

execute.md's sidecar section names the kind as a live one, `/ucg-resolve`
closes it by logging the proposal beside the answer before it deletes the
sidecar, and the scripts read a `coupled-stories` sidecar as a decision a
resume stops on, never a handoff.

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
EXECUTE = (_SKILL_ROOT / "references" / "execute.md").read_text(encoding="utf-8")
RESOLVE = (_SKILL_ROOT.parent / "ucg-resolve" / "SKILL.md").read_text(encoding="utf-8")
_FRAGMENT = _REPO_ROOT / "changes" / "execute-coupled-stories.yaml"

_LEAD = "**Two stories green only together: move the clauses in writing, never share a commit.**"
_NARROWING = "**Get an AC narrowed in writing before committing a case that pins behaviour it forbids.**"
_CLOSE_LEAD = "**Closing a `coupled-stories` escalation records the move, and the resumed run makes it.**"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _mutate(text: str, old: str, new: str) -> str:
    """`text` with its one `old` replaced, matching any run of whitespace (a
    line wrap included) wherever `old` has a space."""
    pattern = re.compile(r"\s+".join(map(re.escape, old.split(" "))))
    assert len(pattern.findall(text)) == 1, old
    return pattern.sub(lambda _: new, text, count=1)


def _story_loop(text: str) -> str:
    """The story loop up to its step 2, where a story's own rules sit."""
    start = text.index("### The story loop")
    return text[start : text.index("\n2. Run the tests", start)]


def _paragraph(text: str) -> str:
    loop = _story_loop(text)
    start = loop.index(_LEAD)
    return _norm(loop[start:].split("\n\n")[0])


_CHECKS = {
    "names the case: the earlier commit cannot be green alone": lambda p: (
        "so that the earlier story's commit cannot be green alone" in p
        and "the earlier story owes a clause only the later story's build can satisfy" in p
    ),
    "ties it to step 5's own-commit rule": lambda p: "Step 5 advances a story only on its own green commit" in p,
    "forbids one commit, an uncommitted story and one gate commit": lambda p: (
        "Do not commit them together, leave the earlier story uncommitted, or gate both at one commit" in p
    ),
    "says why: every per-story artifact is one story's": lambda p: all(
        s in p for s in ("the tests-ran marker", "`.baseline-<story_id>`", "`.commit-<story_id>`", "are each one story's")
    ),
    "leaves driving the rows as one unit to the operator's re-plan": lambda p: (
        "Driving the two rows as one unit is not a route this run takes either" in p
        and "only the operator re-plans rows, outside the run" in p
    ),
    "moves clauses forward to an in-scope, not-done story": lambda p: (
        "move each such clause forward, to the later story" in p and "an in-scope, not-`done` story of this Epic" in p
    ),
    "keeps the move the operator's decision, as the narrowing is": lambda p: (
        "it is the operator's decision, as the narrowing above is: never move a clause on your own ruling" in p
    ),
    "measures each clause before the earlier story's next commit": lambda p: (
        "before the earlier story's next commit, capture for each clause a run on the earlier story's tree" in p
        and "to a file under `{workflow.implementation_artifacts}`" in p
        and "exists only in the later story's build" in p
        and "Only a clause so measured moves." in p
    ),
    "takes an Operator notes entry naming both stories as the ruling": lambda p: (
        "An **Operator notes** entry given before launch" in p
        and "that names both stories and authorizes moving clauses from the earlier story to the later one" in p
        and "is that ruling for each measured clause it covers" in p
        and "so where a move fits that clause (below), apply the move without escalating and cite that note" in p
    ),
    "refuses a note naming one story, or a standing delegation": lambda p: (
        "A note that does not name both stories is not that ruling" in p
        and "and neither is a general or standing delegation" in p
    ),
    "escalates otherwise, with the kind and what it names": lambda p: (
        "Otherwise escalate for the earlier story as the sub-skill halt catch-all below does" in p
        and "`kind` `coupled-stories`" in p
        and "`source` the measurement file" in p
        and all(s in p for s in ("both story keys", "each clause", "its measurement", "the wording you propose"))
        and "(for two decomposed children, the changed claim map)" in p
    ),
    "proposes only a re-plan for a later story outside the run": lambda p: (
        "when the later story is outside this run's scope, propose only a re-plan" in p
    ),
    "applies the ruling only once /ucg-resolve has closed it": lambda p: (
        "Once `/ucg-resolve` has closed it, take the ruling from the entry it logs in `.decision-log.md`" in p
    ),
    "every record of the move lands before the next commit": lambda p: (
        "What the move writes depends on the pair, and all of it lands before the earlier story's next commit." in p
    ),
    "both story files state the move when both have one": lambda p: (
        "When both stories have a story file, write the ruling into both story files, each citing it" in p
        and "names the later story's AC that now owns each moved clause" in p
        and "the later story gains each clause as an AC of its own" in p
    ),
    "two children of one parent move whole ACs, parent file unedited": lambda p: (
        "Between two decomposed children of one parent, which have no story file, only a whole claimed AC moves" in p
        and "a new reconciling run records the split with the changed claim map" in p
        and "the parent's story file stays unedited" in p
    ),
    # A clause moves only once measured, and between two children only a whole
    # AC moves, so an AC holding a clause no run measured has no move: moving
    # it whole on a note would take that clause off the earlier child on no
    # ruling, and no record of the split can hold a clause alone.
    "two children move an AC only when each of its clauses is measured": lambda p: (
        "only a whole claimed AC moves, and only when each of its clauses is so measured" in p
        and "An AC the earlier child claims that also holds a clause no run so measured has no move to apply: "
        "that clause may not move, and the AC cannot move without it." in p
    ),
    # The row is the authority on what a child owes (the sizing section), so a
    # move the split record alone carries still hands the earlier child the
    # moved AC at step 1, and still leaves it out of the later child's trace.
    "the move rewrites both child rows and both checklists": lambda p: (
        "the same pass rewrites the AC citation in both child rows' comments in `sprint-status.yaml`" in p
        and "which step 1 takes `claimed_acs` from and the trace is written from" in p
        and "the AC numbers in both children's `atdd-checklist-<child key>.md` frontmatter" in p
        and "so no record of the split still gives the earlier child the AC it handed on" in p
    ),
    # A child gains no AC of its own and loses only a whole one its parent's
    # split must still place, so neither side of a mixed pair can record a move.
    "a child beside a filed story, or across parents, gets only a re-plan": lambda p: (
        "Any other pair (a decomposed child beside a story that has a file, or children of two parents) "
        "has no move to apply" in p
        and "Escalate for the earlier story as above, proposing only a re-plan" in p
    ),
    # Where no move fits, a pre-launch note is no ruling to apply one, so the
    # note route's "without escalating" never reaches those pairs.
    "a note authorizes no move where none fits": lambda p: (
        "No note can authorize a move where none fits. Escalate for the earlier story as above" in p
    ),
    "moves the scaffolded cases between generatedTestFiles lists": lambda p: (
        "Move each clause's scaffolded cases with it" in p and "`generatedTestFiles`" in p
    ),
    "logs it under both stories": lambda p: (
        "Log the move under both stories in `.decision-log.md`, with the changed claim map for two children" in p
    ),
}


def _holds(text: str) -> list[str]:
    try:
        paragraph = _paragraph(text)
    except ValueError:
        return list(_CHECKS)
    return [name for name, check in _CHECKS.items() if not check(paragraph)]


def test_the_story_loop_names_the_coupled_stories_route():
    assert _holds(EXECUTE) == []


def test_it_sits_after_the_narrowing_rule_which_still_escalates():
    """The 3.1.0 rule holds: the conductor never narrows an AC by itself."""
    loop = _story_loop(EXECUTE)
    assert loop.index(_NARROWING) < loop.index(_LEAD)
    narrowing = _norm(loop[loop.index(_NARROWING) :].split("\n\n")[0])
    assert "Narrowing it is the operator's decision, so escalate for it" in narrowing
    assert "commit the case only once the story file states the narrowed AC" in narrowing


@pytest.mark.parametrize(
    ("old", "new", "caught_by"),
    [
        # The conductor decides the move itself: the 3.1.0 protection is gone.
        (
            "it is the operator's decision, as the narrowing above is: never move a clause on your own ruling",
            "the conductor decides it",
            "keeps the move the operator's decision, as the narrowing is",
        ),
        # The move applied before the operator answered.
        (
            "Once `/ucg-resolve` has closed it, take the ruling",
            "Then take the ruling",
            "applies the ruling only once /ucg-resolve has closed it",
        ),
        # A shared gate commit allowed.
        (
            "leave the earlier story uncommitted, or gate both at one commit",
            "or leave the earlier story uncommitted",
            "forbids one commit, an uncommitted story and one gate commit",
        ),
        # The two rows driven as one unit inside the run.
        (
            "Driving the two rows as one unit is not a route this run takes either",
            "Driving the two rows as one unit is a route this run may take",
            "leaves driving the rows as one unit to the operator's re-plan",
        ),
        # Clauses moved to a story the run will not drive.
        (
            "an in-scope, not-`done` story of this Epic",
            "any story of the plan",
            "moves clauses forward to an in-scope, not-done story",
        ),
        # A clause moved on a guess, with no measurement.
        (" Only a clause so measured moves.", "", "measures each clause before the earlier story's next commit"),
        # Any note counts, whichever stories it names.
        (
            "that names both stories and authorizes moving",
            "that authorizes moving",
            "takes an Operator notes entry naming both stories as the ruling",
        ),
        # A standing delegation read as the ruling (the GMC case).
        (
            "and neither is a general or standing delegation",
            "but a general or standing delegation is",
            "refuses a note naming one story, or a standing delegation",
        ),
        # The scaffolded cases left behind under the earlier story's checklist.
        (
            "Move each clause's scaffolded cases with it",
            "Leave each clause's scaffolded cases where they are",
            "moves the scaffolded cases between generatedTestFiles lists",
        ),
        # Only the split record moves: the earlier child's row still hands it
        # the moved AC at step 1.
        (
            ", and the same pass rewrites the AC citation in both child rows' comments in `sprint-status.yaml`, "
            "which step 1 takes `claimed_acs` from and the trace is written from, and the AC numbers in both "
            "children's `atdd-checklist-<child key>.md` frontmatter (`references/define-done.md`), so no record of "
            "the split still gives the earlier child the AC it handed on.",
            ".",
            "the move rewrites both child rows and both checklists",
        ),
        # The rows rewritten, the checklists left citing the old map.
        (
            "and the AC numbers in both children's `atdd-checklist-<child key>.md` frontmatter",
            "and leaves each child's ATDD checklist as it is",
            "the move rewrites both child rows and both checklists",
        ),
        # A mixed pair given the two-children route.
        (
            "has no move to apply either",
            "moves as two children do",
            "a child beside a filed story, or across parents, gets only a re-plan",
        ),
        # A pre-launch note read as authorizing a move no record can hold.
        (
            "No note can authorize a move where none fits.",
            "A note can authorize a move where none fits.",
            "a note authorizes no move where none fits",
        ),
        # The note route applied to every pair, a pair with no move included.
        (
            "so where a move fits that clause (below), apply the move",
            "so apply the move",
            "takes an Operator notes entry naming both stories as the ruling",
        ),
        # Two children move an AC whole on a note, a clause no run measured
        # included (the contradiction round 2 found).
        (
            ", and only when each of its clauses is so measured, while the parent's story file stays unedited:",
            ", while the parent's story file stays unedited:",
            "two children move an AC only when each of its clauses is measured",
        ),
        (
            "An AC the earlier child claims that also holds a clause no run so measured has no move to apply: "
            "that clause may not move, and the AC cannot move without it.",
            "When only one clause of that AC is measured, an Operator notes entry naming both children still "
            "moves the whole AC, its other clauses included, without escalating.",
            "two children move an AC only when each of its clauses is measured",
        ),
        (
            " An AC the earlier child claims that also holds a clause no run so measured has no move to apply: "
            "that clause may not move, and the AC cannot move without it.",
            "",
            "two children move an AC only when each of its clauses is measured",
        ),
        # A mixed pair driven on as it stands, with no escalation.
        (
            "Escalate for the earlier story as above, proposing only a re-plan, as for a later story outside this "
            "run's scope.",
            "Drive both rows as they stand.",
            "a child beside a filed story, or across parents, gets only a re-plan",
        ),
        # A children's escalation that proposes story-file wording neither child has.
        (
            " (for two decomposed children, the changed claim map)",
            "",
            "escalates otherwise, with the kind and what it names",
        ),
        # The children's records written after the earlier child's next commit.
        (
            "and all of it lands before the earlier story's next commit.",
            "and the children's records follow at their next gate.",
            "every record of the move lands before the next commit",
        ),
        # The decision-log record of the split left on the old map.
        (
            ", with the changed claim map for two children",
            "",
            "logs it under both stories",
        ),
    ],
)
def test_a_weakened_route_is_caught(old, new, caught_by):
    assert caught_by in _holds(_mutate(EXECUTE, old, new))


def test_a_story_loop_without_the_route_is_caught():
    loop = _story_loop(EXECUTE)
    paragraph = loop[loop.index(_LEAD) :].split("\n\n")[0].rstrip("\n")
    assert paragraph + "\n\n" in EXECUTE
    assert _holds(EXECUTE.replace(paragraph + "\n\n", "", 1)) == list(_CHECKS)


# --- the kind, where kinds are named ---------------------------------------------


_LIVE_KIND = "So is `coupled-stories`: the earlier of two stories that are green only together"


def _names_the_live_kind(text: str) -> bool:
    start = text.index("### Escalation sidecar")
    section = _norm(text[start : re.compile(r"\n#{2,3} ").search(text, start + 1).start()])
    if _LIVE_KIND not in section:
        return False
    return "which only the operator may rule on" in section[section.index(_LIVE_KIND) :].split(").")[0]


def test_the_sidecar_section_names_coupled_stories_a_live_kind():
    assert _names_the_live_kind(EXECUTE)
    # Twins: the kind gone from the list, or named with no operator ruling.
    assert not _names_the_live_kind(_mutate(EXECUTE, "So is `coupled-stories`", "So is `something-else`"))
    assert not _names_the_live_kind(
        _mutate(EXECUTE, "which only the operator may rule on", "which the conductor rules on")
    )


def _close_bullet(text: str) -> str:
    """ucg-resolve's `close` disposition, up to the `defer` bullet."""
    close = re.search(r"- \*\*`close`\*\*.*?(?=\n- \*\*`|\n\n)", text, re.DOTALL)
    assert close is not None
    return close.group(0)


_RESOLVE_CHECKS = {
    "has a close rule for the kind": lambda c: _CLOSE_LEAD in c,
    "names every record a children's move rewrites": lambda c: (
        "or for two decomposed children into every record of their split (the split record, both child rows in "
        "`sprint-status.yaml` and both ATDD checklists)" in c
    ),
    "logs decision_needed verbatim under both stories before deleting the sidecar": lambda c: (
        "write the sidecar's `decision_needed` verbatim into this answer's `.decision-log.md` entry" in c
        and "under both story keys it names" in c
        and "before you delete the sidecar" in c
    ),
    "edits no story file: the ruling is the operator's, the run applies it": lambda c: (
        "This surface edits neither story file and moves no test case" in c
        and "the ruling is the operator's, and the resumed run applies it" in c
    ),
    "closes a re-plan only once the operator made it": lambda c: (
        "re-plans the rows instead" in c and "record `defer` until they have made it, then `close`" in c
    ),
}


def _resolve_holds(text: str) -> list[str]:
    bullet = _norm(_close_bullet(text))
    if _CLOSE_LEAD not in bullet:
        return list(_RESOLVE_CHECKS)
    rule = bullet[bullet.index(_CLOSE_LEAD) :]
    return [name for name, check in _RESOLVE_CHECKS.items() if not check(rule)]


def test_ucg_resolve_closes_a_coupled_stories_escalation():
    assert _resolve_holds(RESOLVE) == []


@pytest.mark.parametrize(
    ("old", "new", "caught_by"),
    [
        # The proposal deleted with the sidecar: the resume has nothing to apply.
        (
            "before you delete the sidecar",
            "after you delete the sidecar",
            "logs decision_needed verbatim under both stories before deleting the sidecar",
        ),
        # The decide-surface rewrites the stories itself.
        (
            "This surface edits neither story file",
            "This surface edits both story files",
            "edits no story file: the ruling is the operator's, the run applies it",
        ),
        # A re-plan closed before it exists: the resume re-drives the old rows.
        (
            "record `defer` until they have made it, then `close`",
            "record `close`",
            "closes a re-plan only once the operator made it",
        ),
        # A children's move said to be written into story files neither child has.
        (
            "into both story files, or for two decomposed children into every record of their split (the split "
            "record, both child rows in `sprint-status.yaml` and both ATDD checklists).",
            "into both story files.",
            "names every record a children's move rewrites",
        ),
    ],
)
def test_a_weakened_close_is_caught(old, new, caught_by):
    assert caught_by in _resolve_holds(_mutate(RESOLVE, old, new))


def test_a_close_bullet_without_the_rule_is_caught():
    bullet = _close_bullet(RESOLVE)
    rule = bullet[bullet.index("  **Closing a `coupled-stories` escalation") :]
    assert _resolve_holds(RESOLVE.replace(rule, "", 1)) == list(_RESOLVE_CHECKS)


# --- the scripts read the kind as a decision --------------------------------------


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_STORY = "96-0-i-the-earlier"
_SIDECAR = {
    "source": "impl/coupled-96-0-i.md",
    "kind": "coupled-stories",
    "decision_needed": "Move AC 7 (a) from 96-0-i to 96-0-j as measured, or re-plan the rows.",
    "evidence": "AC 7 (a): the handler it needs lands only in 96-0-j's build.",
}


def test_a_coupled_stories_sidecar_is_a_decision_a_resume_stops_on(tmp_path: Path):
    """No script changes for the kind: it is open vocabulary. These pin that it
    stays a decision (decision-pending until /ucg-resolve closes it, and an
    escalation, not a handoff, to the driver), so adding it to a handoff set
    would let a run re-drive a story whose AC nobody has ruled on."""
    preflight_check, drive_epic, red_ids = _load("preflight_check"), _load("drive_epic"), _load("red_ids")
    impl = tmp_path / "impl"
    impl.mkdir()
    started = time.time()
    (impl / f"escalation-{_STORY}.json").write_text(json.dumps(_SIDECAR), encoding="utf-8")

    escalation = preflight_check._escalation_of(impl, _STORY, tmp_path)
    assert escalation["state"] == "open"
    assert "blocker" in escalation
    assert drive_epic.handoff_kind(impl, _STORY, started) is None
    assert "coupled-stories" not in preflight_check._HANDOFF_KINDS | drive_epic.HANDOFF_KINDS

    # /ucg-resolve's close, keyed by the id red_ids.py mints, is read as closed.
    rid = red_ids.mint_id(_SIDECAR["kind"], _SIDECAR["source"], _SIDECAR["decision_needed"])
    (impl / ".decisions.json").write_text(
        json.dumps({"decisions": [{"id": rid, "answer": "Move AC 7 (a) as proposed.", "action": "close"}]}),
        encoding="utf-8",
    )
    assert preflight_check._escalation_of(impl, _STORY, tmp_path)["state"] == "closed"


# --- the change fragment ---------------------------------------------------------


def test_the_fragment_describes_the_route():
    fragment = _FRAGMENT.read_text(encoding="utf-8")
    assert fragment.startswith("type: changed\n")
    assert "\n  - 181\n" in fragment
    flat = _norm(fragment)
    for token in (
        "`kind` `coupled-stories`",
        "Operator notes entry given before launch that names both stories",
        "A general or standing delegation is not a ruling.",
        "`/ucg-resolve` closes that escalation",
        "`generatedTestFiles`",
        "both child rows' criteria citations in `sprint-status.yaml` and both children's ATDD checklists",
        "only a whole claimed criterion moves, and only when each of its clauses is so measured.",
        "A criterion that also holds a clause no run so measured has no move, and neither does a decomposed child "
        "coupled with a story that has a file, or with a child of another parent: no Operator notes entry can "
        "authorize one, so the run escalates proposing only a re-plan.",
    ):
        assert token in flat, token
    assert chr(0x2014) not in fragment, "an em dash in the fragment"
