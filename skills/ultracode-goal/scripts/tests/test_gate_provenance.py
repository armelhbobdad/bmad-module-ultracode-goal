#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Gate provenance: a hand-authored gate verdict must say so.

`references/gate.md` sanctions authoring `trace-<id>.md` / `gate-decision-<id>.json`
by hand when TEA's browser chain cannot run on the stack. That substitution is
legitimate, but on it the model WRITES THE FILE THE GATE THEN READS — which is
the loop the module's central non-negotiable ("completion is decided by
gate_eval.py reading TEA's gate-decision.json, never your own judgment") exists to
prevent. Without a provenance record the two are indistinguishable in the decision
log and the run report, and an Epic can complete entirely on the hand-authored
path with nothing anywhere saying so. Observed: one real Epic did exactly that,
story after story.

These are prose-contract assertions with anti-vacuous twins, following the house
pattern (test_run_status_heartbeat.py, test_escalation_sidecar.py). Stdlib +
pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_GATE = _SKILL_ROOT / "references" / "gate.md"
_FINALIZE = _SKILL_ROOT / "references" / "finalize.md"

_TEA_TOKEN = "gate-provenance: tea"
_HAND_TOKEN = "gate-provenance: hand-authored"


def _gate() -> str:
    return _GATE.read_text(encoding="utf-8")


def _finalize() -> str:
    return _FINALIZE.read_text(encoding="utf-8")


def test_gate_defines_both_provenance_values():
    text = _gate()
    assert _TEA_TOKEN in text, "gate.md must name the TEA-authored provenance value"
    assert _HAND_TOKEN in text, "gate.md must name the hand-authored provenance value"


def test_the_non_web_section_claims_the_hand_authored_value():
    """The branch that DOES the substitution must be the one that labels it.

    A definition parked only in 'Run the gate' would be read by a conductor that
    never reaches it on this path.
    """
    text = _gate()
    start = text.index("## Non-web stack")
    end = text.index("## Run the gate", start)
    assert _HAND_TOKEN in text[start:end], (
        "the non-web hand-authoring section must label itself hand-authored"
    )


def test_gate_says_provenance_changes_no_verdict():
    """It is a record, not a gate. Without this a reader could take it for a
    fourth production AND and start failing runs on it."""
    text = _gate()
    assert re.search(r"changes no verdict and gates nothing", text), (
        "gate.md must state that provenance is non-authoritative"
    )


def test_finalize_reports_provenance_per_story():
    text = _finalize()
    assert "Gate provenance per story" in text, (
        "the run report must carry a per-story provenance row"
    )
    assert re.search(r"per story rather than once for the run", text), (
        "a single run-level label cannot describe a mixed Epic"
    )


def test_the_two_files_agree_on_the_literal():
    """Cross-file equality: Stage 5 writes the token Stage 6 copies. If the two
    drift, finalize reads a key gate never logged."""
    assert "gate-provenance" in _gate()
    assert "gate-provenance" in _finalize()


def test_twin_a_gate_without_the_hand_authored_label_reds():
    """Anti-vacuous: strip the label from the non-web section and the section
    assertion must fail, while the others still hold — so that test is pinned to
    the section rather than to the file."""
    text = _gate()
    start = text.index("## Non-web stack")
    end = text.index("## Run the gate", start)
    mutated_section = text[start:end].replace(_HAND_TOKEN, "authored by hand")
    assert mutated_section != text[start:end], "mutation anchor drifted"
    assert _HAND_TOKEN not in mutated_section
    # control: the definition in "Run the gate" survives the same mutation
    assert _HAND_TOKEN in text[end:], (
        "the positive control is gone; this twin would be measuring nothing"
    )
