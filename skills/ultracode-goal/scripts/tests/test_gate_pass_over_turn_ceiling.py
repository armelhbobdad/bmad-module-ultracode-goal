"""Prose contract: a passing gate overrides the turn-count escalation.

The Stop hook writes a turn-ceiling marker once a story's count reaches
`max_turns_per_story`. Execute used to promote that marker to a `budget-overrun`
escalation as soon as the story's drive ended, so a story that then passed its
gate still carried an open escalation asking to re-scope, split or hand off a
story that was already done. In a real project every such escalation was left
open. Now the gate decides: a story it advances gets a sizing note, and only a
story it escalates on the turn count is escalated from the marker.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against a single-clause mutant. Stdlib + pytest only.
"""

import re
from pathlib import Path

import pytest

_REFS = Path(__file__).resolve().parents[2] / "references"


def _read(name: str) -> str:
    return (_REFS / name).read_text(encoding="utf-8")


def _promotion(text: str) -> str:
    m = re.search(r"\*\*Promoting the turn-budget marker\.\*\*[^\n]*", text)
    assert m, "the promotion paragraph must be present"
    return m.group(0)


def _gate_pass_wins(section: str) -> bool:
    return bool(
        re.search(
            r"\*\*When the gate advances the story \(`advance`, or `defer`, whose route advances anyway\), "
            r"do not promote the marker\.\*\*",
            section,
        )
        and re.search(r"Log a sizing note in `\.decision-log\.md` instead", section)
        and re.search(r"\*\*When the gate escalates the story on the turn count\*\*", section)
        and re.search(r"A marker counts only while the story's recorded count", section)
        and re.search(r"A cap-only `reloop` \(a sweep-scope or delta cap\) is not that verdict", section)
    )


def test_execute_lets_a_passing_gate_win():
    assert _gate_pass_wins(_promotion(_read("execute.md")))


@pytest.mark.parametrize(
    "clause",
    [
        "**When the gate advances the story (`advance`, or `defer`, whose route advances anyway), do not promote the marker.**",
        "Log a sizing note in `.decision-log.md` instead",
        "**When the gate escalates the story on the turn count**",
        "A marker counts only while the story's recorded count",
        "A cap-only `reloop` (a sweep-scope or delta cap) is not that verdict",
    ],
)
def test_gate_pass_predicate_rejects_a_single_dropped_clause(clause):
    section = _promotion(_read("execute.md"))
    mutant = section.replace(clause, "")
    assert mutant != section, "the mutant must actually change the text"
    assert not _gate_pass_wins(mutant)


_PING_DEFERS = "A marker whose story the gate advanced is never promoted or pinged"


def test_the_escalation_ping_waits_for_the_gate():
    assert _PING_DEFERS in _read("execute.md")


def test_a_cap_only_regate_is_not_a_turn_count_escalation():
    assert "A cap-only re-gate re-measures without re-driving the story, so the turn-ceiling rule below never turns it into `escalate`." in _read("gate.md")


def test_an_unmarked_turn_count_escalation_still_gets_its_kind():
    # The gate can escalate on the count before the hook wrote a marker; the
    # sidecar must still be budget-overrun, or /ucg-resolve never resets the count.
    section = _promotion(_read("execute.md"))
    assert "write the same `budget-overrun` sidecar then from `{workflow.implementation_artifacts}/.budget-<story_id>.json`" in section


def test_the_gate_routes_carry_the_rule():
    gate = _read("gate.md")
    advance = re.search(r"- \*\*`advance`\*\*[^\n]*", gate)
    assert advance, "the advance route must be present"
    assert "do **not** promote it: log the sizing note" in advance.group(0)
    assert re.search(
        r"When the hook left a turn-budget marker for this story, that escalation's sidecar is the marker's promotion",
        gate,
    )


def test_the_run_report_carries_the_sizing_note():
    finalize = _read("finalize.md")
    per_story = re.search(r"- Per-story outcome:[^\n]*", finalize)
    assert per_story
    assert "For a story that advanced with its count at or past the turn ceiling, its sizing note" in per_story.group(0)
    assert "when the session ended before the note was logged" in per_story.group(0)
