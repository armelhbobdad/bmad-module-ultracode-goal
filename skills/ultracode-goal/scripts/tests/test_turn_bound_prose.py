"""Prose contract over the turn bound: who can start `/goal`, and what the count sees.

A real run showed that the conductor never starts `/goal`. It is a built-in slash
command with no tool surface, so an attended session, a `-H` session and a
`drive_epic.py` spawn all run without one unless the operator starts it, and then
on the operator's own condition. Yet the references and docs called the
in-condition "…or stop after N turns" clause "the real bound". The turn count the
Stop hook records is the only one every session keeps, and it advances once per
response, so it cannot see re-loops spent inside a single response.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against a single-clause mutant or the pre-edit wording it must reject.
Stdlib + pytest only.
"""

import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"

# Wording that stated the `/goal` turn clause as the active bound, or `/goal` as
# what drives Execute. Matched case-insensitively.
_RETIRED = (
    "the turn clause inside the condition is the real bound",
    "wrap the loop in a single `/goal`",
    "what the `/goal` driver reads to pace itself",
    "after `/goal` returns",
    "the real in-loop bound",
    "primary runaway guard",
    "enforced inside the `/goal` condition",
    "the hard bounds are the in-condition turn clause",
    "the loop is wrapped in a single `/goal`",
    "the `/goal` loop drives execution",
    "the `/goal` evaluator that drives execution",
    "the `/goal` loop that drives execute",
    "paced by claude code's `/goal` evaluator",
    "encoded in the `/goal` condition and enforced at the gate",
    "it is also that loop's condition",
    "the same number `run-status.json` reports",
    "the bound that holds in every session",
)

# Paraphrases of the retired wording, each carrying its phrase verbatim, so the
# twin below proves every phrase in the list matches real old prose. Three of
# them ("it is also that loop's condition", "the same number `run-status.json`
# reports", "the bound that holds in every session") come from a first draft of
# this fix that a review rejected, not from main.
_PRE_EDIT = (
    "Wrap the loop in a single `/goal` whose condition is under 4000 characters. "
    "A Stop hook cannot force `/goal` to halt mid-condition, so the turn clause inside "
    "the condition is the real bound. This printed evidence is what keeps the run "
    "judgeable mid-flight and what the `/goal` driver reads to pace itself. "
    "Execute is the sole promoter of that markdown, after `/goal` returns, read any marker.",
    "the in-condition \"stop after N turns\" clause inside the `/goal` condition (the real "
    "in-loop bound). Today the in-`/goal`-condition turn cap is the primary runaway guard.",
    "The per-story turn ceiling is the skill's own, enforced inside the `/goal` condition "
    "and the budget_stop.py Stop hook.",
    "So at this layer the ceiling is advisory; the hard bounds are the in-condition turn "
    "clause and the gate re-loop budget.",
    "The loop is wrapped in a single `/goal` whose condition encodes the Definition-of-Done.",
    "Claude Code primitives: the `/goal` loop drives execution. The `/goal` evaluator that "
    "drives execution can only see what the run surfaces.",
    "The `/goal` loop that drives Execute ends with an evaluator confirming the condition.",
    "The per-story loop is paced by Claude Code's `/goal` evaluator (an LLM). UCG's is a "
    "turn cap, encoded in the `/goal` condition and enforced at the gate.",
    "when the operator did start a `/goal`, it is also that loop's condition. The bound that "
    "holds in every session is the turn count (the same number `run-status.json` reports).",
)

_SURFACES = (
    _EXECUTE,
    _SKILL_ROOT / "scripts" / "hooks" / "budget_stop.py",
    _SKILL_ROOT / "scripts" / "drive_epic.py",
    _REPO / "docs" / "architecture.md",
    _REPO / "docs" / "troubleshooting.md",
    _REPO / "docs" / "why-ultracode-goal.md",
    _REPO / "docs" / "how-it-works.md",
    _REPO / "docs" / "comparison.md",
    _REPO / "docs" / "gate-model.md",
    _REPO / "ROADMAP.md",
)


def _execute() -> str:
    return _EXECUTE.read_text(encoding="utf-8")


def _states_the_count_honestly(text: str) -> bool:
    return bool(
        re.search(r"The conductor cannot start `/goal` itself", text)
        and re.search(r"`\{workflow\.implementation_artifacts\}/\.budget-<story_id>\.json`", text)
        and re.search(r"cannot see re-loops spent inside a single response", text)
        and re.search(r"\*\*Before a story's step 0\*\* on the `story-boundary` and `mid-story` resume routes", text)
        and re.search(r"A `gate-owed` story is exempt", text)
        and re.search(r"`kind` `budget-overrun`", text)
    )


def test_execute_states_what_the_turn_count_can_and_cannot_see():
    assert _states_the_count_honestly(_execute())


@pytest.mark.parametrize(
    "clause",
    [
        "cannot see re-loops spent inside a single response",
        "A `gate-owed` story is exempt",
    ],
)
def test_turn_count_predicate_rejects_a_single_dropped_clause(clause):
    mutant = _execute().replace(clause, "")
    assert mutant != _execute(), "the mutant must actually change the text"
    assert not _states_the_count_honestly(mutant)


def test_the_retired_bound_claims_stay_out_of_every_surface():
    for surface in _SURFACES:
        text = surface.read_text(encoding="utf-8").lower()
        for phrase in _RETIRED:
            assert phrase not in text, f"{surface.name} still says {phrase!r}"


def test_every_retired_phrase_matches_the_pre_edit_wording():
    """Twin of the check above: each phrase really catches the old sentence."""
    old = " ".join(_PRE_EDIT).lower()
    for phrase in _RETIRED:
        assert phrase in old, phrase


_WHO_CAN_START = re.compile(r"conductor cannot (start one|start `/goal`)")


def test_the_docs_say_who_can_start_goal():
    for name in ("architecture.md", "troubleshooting.md", "why-ultracode-goal.md", "how-it-works.md"):
        text = (_REPO / "docs" / name).read_text(encoding="utf-8")
        assert _WHO_CAN_START.search(text), name


def test_who_can_start_predicate_rejects_the_pre_edit_docs():
    assert not _WHO_CAN_START.search(" ".join(_PRE_EDIT))


def test_gate_names_the_count_its_reloop_budget_reads():
    gate = (_SKILL_ROOT / "references" / "gate.md").read_text(encoding="utf-8")
    assert re.search(
        r"the count is the `turns` value the Stop hook records in "
        r"`\{workflow\.implementation_artifacts\}/\.budget-<story_id>\.json`",
        gate,
    )
