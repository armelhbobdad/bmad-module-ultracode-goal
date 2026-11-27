#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for where an NFR `CONCERNS` routes a story.

In production, `gate_eval.py` ANDs the NFR assessment's Overall Status onto the
trace gate: a `FAIL` or a `NOT_ASSESSED` downgrades an `advance` to `reloop`,
and a `CONCERNS` fails nothing, so it moves no verdict (the verdict is what
`gate_status` gives: `advance` on a `PASS` or `WAIVED` gate). 8.1.1's
`references/gate.md` said the opposite in the hand-authored shapes:
"`CONCERNS` is a `defer`". A conductor that took the sentence at its word
looked for a `defer` the script never returns, and the `advance` route it did
take parked nothing of the assessment, though TEA's own definition of
`CONCERNS` is that it does not block but needs follow-up.

Now:

- The status paragraph of the hand-authored `nfr-assessment.md` shape ends on
  "`CONCERNS` does not fail the AND, so it moves no verdict, and it claims the
  NFRs *were* assessed." and names no `defer` anywhere.
- The `advance` route parks on the deferred-work ledger, before the story
  passes and beside the operator-evidence AC it already parked there, each
  criterion an NFR assessment at `CONCERNS` rates `CONCERNS`, with `source`
  `nfr`, and says why: that status does not fail the AND. Only those
  criteria: not the assessment's `PASS` ones, and never a `FAIL`.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text without the change, one-clause mutants it must reject, and a
twin per clause of the predicate that only that clause rejects. The claim about
the AND is checked against `gate_eval.py` itself, run on a fixture the way a
production gate runs it (a per-story gate file, an NFR assessment, a test
review at 85 with `Approve` and a full-scope tests-ran marker), beside a `FAIL`
twin that shows the fixture's AND is live. The `source` the route names is
checked against the ledger schema, and the criteria it parks against the
tracked TEA reference under `skf-skills/tea-testarch/` (the installed TEA
skills under `.claude/skills/` are not tracked, so no test reads them). Stated
limit: this is a presence proof over prose. It shows the instruction is in the
file and agrees with the script, not that a conductor parks the criteria, or
that TEA rates the criteria a `CONCERNS` rests on.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_GATE_EVAL = _SKILL_ROOT / "scripts" / "gate_eval.py"
GATE = (_SKILL_ROOT / "references" / "gate.md").read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def _paragraph(text: str, opener: str) -> str:
    """The paragraph that opens with `opener`, or "" when `text` has none."""
    start = text.find(opener)
    if start == -1:
        return ""
    end = text.find("\n\n", start)
    return text[start : end if end != -1 else len(text)]


def _replaced(text: str, old: str, new: str) -> str:
    mutant = text.replace(old, new, 1)
    assert mutant != text, "the mutant must actually change the text"
    return mutant


# --- the status paragraph: CONCERNS does not fail the AND ------------------------

_STATUS_OPENER = "`PASS` | `CONCERNS` | `FAIL` | `NOT_ASSESSED` (the key may also be written `overallStatus:`)."
_HONEST = "Write it honestly rather than reaching for `CONCERNS` to keep a story moving;"
_CONCERNS_CLAUSE = "`CONCERNS` does not fail the AND, so it moves no verdict, and it claims the NFRs *were* assessed."
# 8.1.1's clause, the state before the change.
_PRE_EDIT_CLAUSE = "`CONCERNS` is a `defer` and claims the NFRs *were* assessed."
# The paragraph's second sentence, where a twin below adds a sentence of its own.
_DOWNGRADE = "A `FAIL`, a `NOT_ASSESSED`, or a status the scanner cannot find all downgrade `advance`→`reloop`."
# Any mention of a defer, backticked or not: no NFR status maps to one.
_DEFER = re.compile(r"\bdefer", re.I)


def _status_paragraph(text: str = GATE) -> str:
    return _paragraph(_section(text, "## Non-web stack"), _STATUS_OPENER)


def _ends_on_the_clause(flat: str) -> bool:
    return flat.endswith(_HONEST + " " + _CONCERNS_CLAUSE)


def _concerns_passes_the_and(paragraph: str) -> bool:
    """The paragraph ends on the clause, directly after the honesty clause it
    completes, and names no defer anywhere: no NFR status maps to one."""
    flat = _flat(paragraph).strip()
    return _ends_on_the_clause(flat) and _DEFER.search(flat) is None


def test_the_status_paragraph_says_concerns_does_not_fail_the_and():
    assert _concerns_passes_the_and(_status_paragraph())
    assert GATE.count(_STATUS_OPENER) == 1


def test_gate_md_no_longer_calls_an_nfr_concerns_a_defer():
    assert "`CONCERNS` is a `defer`" not in _flat(GATE)
    assert _PRE_EDIT_CLAUSE not in _flat(GATE)


def test_concerns_predicate_rejects_the_pre_edit_paragraph():
    pre = _replaced(_flat(_status_paragraph()), _CONCERNS_CLAUSE, _PRE_EDIT_CLAUSE)
    assert not _concerns_passes_the_and(pre)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("does not fail the AND", "fails the AND", id="fails-the-and"),
        pytest.param(", so it moves no verdict,", ",", id="verdict-unsaid"),
        pytest.param("it moves no verdict", "it moves the verdict to `reloop`", id="verdict-to-reloop"),
        pytest.param("it moves no verdict", "it moves every verdict to `advance`", id="verdict-to-advance"),
        pytest.param("it moves no verdict", "it can move a verdict", id="can-move-a-verdict"),
        pytest.param(", and it claims the NFRs *were* assessed.", ".", id="claim-dropped"),
        pytest.param("claims the NFRs *were* assessed", "claims nothing about the NFRs", id="claim-denied"),
        pytest.param("`CONCERNS` does not fail the AND,", "`CONCERNS` does not fail the AND, it is a `defer`,",
                     id="still-a-defer"),
        pytest.param(_HONEST + " ", "", id="honesty-clause-dropped"),
        pytest.param(" " + _CONCERNS_CLAUSE, "", id="dropped"),
    ],
)
def test_concerns_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _concerns_passes_the_and(_replaced(_flat(_status_paragraph()), old, new))


@pytest.mark.parametrize(
    "added",
    [
        pytest.param(" A `CONCERNS` maps `advance` to `defer`.", id="backticked"),
        pytest.param(" A `CONCERNS` makes the story a defer.", id="plain-word"),
    ],
)
def test_concerns_predicate_rejects_a_defer_elsewhere_in_the_paragraph(added):
    """Twin for the clause that names no defer: the paragraph keeps its correct
    ending, so only that clause can reject the sentence a twin adds after the
    downgrade sentence."""
    mutant = _replaced(_flat(_status_paragraph()), _DOWNGRADE, _DOWNGRADE + added)
    assert _ends_on_the_clause(mutant.strip())
    assert not _concerns_passes_the_and(mutant)


# --- the claim is what gate_eval.py does -----------------------------------------

_STORY = "61-1"


def _load_gate_eval():
    spec = importlib.util.spec_from_file_location("gate_eval_nfr_concerns_routing", _GATE_EVAL)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _run_gate(folder: Path, gate_status: str, nfr_status: str) -> dict:
    """`gate_eval.py` run as a production per-story gate is run: a per-story
    gate file, an NFR assessment, a test review at 85 with `Approve`, and a
    full-scope tests-ran marker."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"gate-decision-{_STORY}.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "gate_status": gate_status,
                "p0_status": "MET",
                "p1_status": "MET",
                "overall_status": "MET",
            }
        ),
        encoding="utf-8",
    )
    nfr = folder / f"nfr-assessment-{_STORY}.md"
    nfr.write_text(
        "---\nworkflowType: 'testarch-nfr-assess'\n---\n\n# NFR Evidence Audit - Sample\n\n"
        f"**Date:** 2026-06-03\n**Overall Status:** {nfr_status}\n\n## Executive Summary\n",
        encoding="utf-8",
    )
    review = folder / f"test-review-{_STORY}.md"
    review.write_text(
        "---\nworkflowType: 'testarch-test-review'\n---\n\n# Test Quality Review: sample.spec.ts\n\n"
        "**Quality Score**: 85/100 (B - Good)\n**Review Date**: 2026-06-03\n\n## Executive Summary\n\n"
        "**Recommendation**: Approve\n",
        encoding="utf-8",
    )
    marker = folder / f".tests-ran-{_STORY}"
    marker.write_text("baseline=" + "a" * 40 + "\nscope=full\n", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable, str(_GATE_EVAL), "--trace-output", str(folder), "--story", _STORY,
            "--profile", "production", "--nfr", str(nfr), "--test-review", str(review), "--tests-ran", str(marker),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize("gate_status", ["PASS", "WAIVED", "CONCERNS"])
def test_gate_eval_moves_no_verdict_on_an_nfr_concerns(tmp_path, gate_status):
    """"It moves no verdict": the verdict is the one `gate_status` gives,
    `advance` on a PASS or WAIVED gate and `defer` on a CONCERNS one, and the
    same one an NFR PASS gives, so never a `defer` the NFR status made."""
    result = _run_gate(tmp_path / "concerns", gate_status, "CONCERNS")
    assert result["gate_status"] == gate_status
    assert result["nfr_status"] == "CONCERNS"
    assert result["review_score"] == 85
    assert result["sweep_scope"] == "full"
    assert result["verdict"] == _load_gate_eval().GATE_VERDICT[gate_status]
    assert result["verdict"] == {"PASS": "advance", "WAIVED": "advance", "CONCERNS": "defer"}[gate_status]
    # The NFR CONCERNS adds nothing to the verdict: a PASS gives the same one.
    assert result["verdict"] == _run_gate(tmp_path / "pass", gate_status, "PASS")["verdict"]


@pytest.mark.parametrize("gate_status", ["PASS", "WAIVED"])
def test_the_fixture_s_and_is_live(tmp_path, gate_status):
    """Twin: the same fixture with an NFR FAIL re-loops, so the advance above is
    the AND passing a CONCERNS, not an AND that never ran."""
    result = _run_gate(tmp_path, gate_status, "FAIL")
    assert result["nfr_status"] == "FAIL"
    assert result["verdict"] == "reloop"


# --- the advance route parks the CONCERNS criteria of an NFR CONCERNS -----------

_ADVANCE_OPENER = "- **`advance`** (gate_status PASS or WAIVED) → the story passes ("
_OWED = "an operator-evidence AC still owed its evidence is parked on the ledger first, as `defer` below says"
_CRITERIA = "each criterion an NFR assessment at `CONCERNS` rates `CONCERNS`"
_SOURCE = "with `source` `nfr`"
_REASON = "since that status does not fail the AND"
_NFR_PARKED = f", and so is {_CRITERIA}, {_SOURCE}, {_REASON}"
_SYNC = "). **Sync the story's row in `sprint-status.yaml` to `done` before moving on**"


def _advance_bullet(text: str = GATE) -> str:
    return _paragraph(_section(text, "## Route on the verdict"), "- **`advance`**")


def _advance_parks_nfr_concerns(bullet: str) -> bool:
    """The clause sits in the parenthetical that names what is parked on the
    ledger first, before the story passes and before the `done` sync, and
    "so is" takes "is parked on the ledger first" from the operator-evidence
    clause it follows. It names only the criteria the assessment rates
    `CONCERNS`, the ledger `source` they take, and why they are parked."""
    return _flat(bullet).startswith(_ADVANCE_OPENER + _OWED + _NFR_PARKED + _SYNC)


def test_the_advance_route_parks_each_concerns_criterion_of_an_nfr_concerns():
    assert _advance_parks_nfr_concerns(_advance_bullet())


def test_advance_predicate_rejects_the_pre_edit_bullet():
    pre = _replaced(_flat(_advance_bullet()), _NFR_PARKED, "")
    assert pre.startswith(_ADVANCE_OPENER + _OWED + _SYNC)
    assert not _advance_parks_nfr_concerns(pre)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # Only the criteria rated CONCERNS: not the assessment as a whole, not
        # its PASS criteria, and never a FAIL (the INVARIANT: a FAIL never goes
        # to the ledger).
        pytest.param(_CRITERIA, "the NFR `CONCERNS`", id="status-not-criteria"),
        pytest.param(_CRITERIA, "each criterion an NFR assessment at `CONCERNS` assesses", id="every-criterion"),
        pytest.param("rates `CONCERNS`", "rates `PASS` or `CONCERNS`", id="pass-criteria-too"),
        pytest.param("rates `CONCERNS`", "rates `CONCERNS` or `FAIL`", id="fail-criteria-parked"),
        pytest.param("an NFR assessment at `CONCERNS`", "an NFR assessment at `FAIL`", id="nfr-fail-parked"),
        pytest.param("each criterion", "the first criterion", id="first-criterion-only"),
        pytest.param(_CRITERIA, "each finding of a test review", id="test-review-findings"),
        # The ledger row's source.
        pytest.param(", " + _SOURCE, "", id="source-unsaid"),
        pytest.param("`source` `nfr`", "`source` `gate`", id="source-gate"),
        pytest.param("`source` `nfr`", "`source` `code-review`", id="source-code-review"),
        # The reason, and where the clause sits.
        pytest.param(", " + _REASON, "", id="reason-dropped"),
        pytest.param(_REASON, "since that status fails the AND", id="fails-the-and"),
        pytest.param(", and so is each criterion", ", but not each criterion", id="not-parked"),
        pytest.param("is parked on the ledger first", "is parked on the ledger once the story is `done`",
                     id="parked-after-the-pass"),
    ],
)
def test_advance_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _advance_parks_nfr_concerns(_replaced(_flat(_advance_bullet()), old, new))


def test_advance_predicate_rejects_the_clause_moved_after_the_sync():
    bullet = _flat(_advance_bullet())
    moved = (
        _replaced(bullet, _NFR_PARKED, "")
        + f" Each criterion an NFR assessment at `CONCERNS` rates `CONCERNS` is parked on the ledger too, {_SOURCE}."
    )
    assert not _advance_parks_nfr_concerns(moved)


def test_the_route_and_the_status_paragraph_give_one_reason():
    """Both sentences that speak of an NFR `CONCERNS` say it does not fail the
    AND, so neither can drift back to a `defer` alone."""
    assert "`CONCERNS` does not fail the AND" in _flat(_status_paragraph())
    assert f"rates `CONCERNS`, {_SOURCE}, {_REASON})" in _flat(_advance_bullet())


# --- the source the route names is the ledger's ----------------------------------

_SOURCE_NAMED = re.compile(r"with `source` `([^`]+)`")


def _schema(text: str = GATE) -> str:
    return _flat(_section(text, "## Deferred-work ledger schema"))


def _source_is_the_ledger_s_for_a_non_fail_nfr_finding(bullet: str, schema: str) -> bool:
    """The `source` the advance route names for the parked criteria is the one
    the ledger schema lists for a non-FAIL NFR finding."""
    named = _SOURCE_NAMED.findall(_flat(bullet))
    return len(named) == 1 and f"`{named[0]}` (non-FAIL finding)" in schema


def test_the_route_names_the_ledger_s_source_for_a_non_fail_nfr_finding():
    assert _source_is_the_ledger_s_for_a_non_fail_nfr_finding(_advance_bullet(), _schema())
    # "As `defer` below says": the defer route sits below the advance route.
    route = _section(GATE, "## Route on the verdict")
    assert route.index("- **`advance`**") < route.index("- **`defer`**")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("`source` `nfr`", "`source` `gate`", id="gate"),
        pytest.param("`source` `nfr`", "`source` `nfr-concerns`", id="not-in-the-schema"),
        pytest.param(", " + _SOURCE, "", id="unsaid"),
    ],
)
def test_source_predicate_rejects_a_source_the_schema_does_not_give(old, new):
    assert not _source_is_the_ledger_s_for_a_non_fail_nfr_finding(
        _replaced(_flat(_advance_bullet()), old, new), _schema()
    )


def test_source_predicate_rejects_a_schema_without_the_nfr_source():
    """Twin on the schema side: with `nfr` gone from the schema's sources, the
    route's `source` names nothing the ledger takes."""
    schema = _replaced(_schema(), "`nfr` (non-FAIL finding), ", "")
    assert not _source_is_the_ledger_s_for_a_non_fail_nfr_finding(_advance_bullet(), schema)


def _repo_tea_reference() -> Path:
    """The tracked reference skill for the TEA version this module targets."""
    group = _REPO / "skf-skills" / "tea-testarch"
    active = group / "active"
    version = active.resolve().name if active.is_dir() else active.read_text(encoding="utf-8").strip()
    return group / version / "tea-testarch"


def _tea_nfr() -> str:
    return _flat((_repo_tea_reference() / "references" / "pattern-nfr.md").read_text(encoding="utf-8"))


def test_tea_s_concerns_needs_follow_up():
    """The reason the criteria are parked rather than dropped or re-looped, from
    the tracked TEA reference: a `CONCERNS` does not block but needs follow-up."""
    assert "| `CONCERNS` | Partial or weak; does not block but needs follow-up" in _tea_nfr()


def test_tea_rates_each_criterion_and_rolls_up_the_worst():
    """What "each criterion an NFR assessment at `CONCERNS` rates `CONCERNS`"
    rests on, from the tracked TEA reference: TEA rates criteria one by one (an
    omitted one gets a `CONCERNS` of its own), and a domain's status is its
    worst finding, so a criterion's own rating, not the status above it, tells
    which ones to park. The route parks those rated `CONCERNS`, and so never a
    `FAIL`. (The reference states no roll-up from domains to the Overall
    Status, so this does not claim one.)"""
    nfr = _tea_nfr()
    assert "an omitted criterion gets a synthesized `CONCERNS`" in nfr
    assert "Domain status = worst finding (FAIL > CONCERNS > PASS)" in nfr
