#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for gate_eval.py.

Run: uv run --script scripts/tests/test_gate_eval.py
(or: uv run --with pytest pytest scripts/tests/test_gate_eval.py)

Covers the full verdict mapping (PASS/WAIVED/CONCERNS/FAIL/NOT_EVALUATED), the
missing-slim-file fallback to e2e-trace-summary.json, frontmatter-hinted gate
file resolution, and the production AND with nfr/test-review (including the
downgrade-to-reloop floor).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "gate_eval.py"


def run_gate(trace_output, profile="light", nfr=None, test_review=None, story=None):
    cmd = [sys.executable, str(SCRIPT), "--trace-output", str(trace_output), "--profile", profile]
    if nfr is not None:
        cmd += ["--nfr", str(nfr)]
    if test_review is not None:
        cmd += ["--test-review", str(test_review)]
    if story is not None:
        cmd += ["--story", str(story)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def write_slim(dir_path, gate_status, p0="MET", p1="MET", overall="MET"):
    payload = {
        "schema_version": "0.1.0",
        "gate_status": gate_status,
        "p0_status": p0,
        "p1_status": p1,
        "overall_status": overall,
    }
    (dir_path / "gate-decision.json").write_text(json.dumps(payload), encoding="utf-8")


def write_summary(dir_path, gate_status=None, p0="MET", p1="MET", overall="MET"):
    """Write e2e-trace-summary.json; omit gate fields when gate_status is None."""
    payload = {"schema_version": "0.1.0", "snapshot_at": "2026-06-03T00:00:00Z"}
    if gate_status is not None:
        payload["gate_status"] = gate_status
        payload["gate_criteria"] = {
            "p0_status": p0,
            "p1_status": p1,
            "overall_status": overall,
        }
    (dir_path / "e2e-trace-summary.json").write_text(json.dumps(payload), encoding="utf-8")


NFR_TEMPLATE = """---
workflowType: 'testarch-nfr-assess'
---

# NFR Evidence Audit - Demo

**Date:** 2026-06-03
**Overall Status:** {status}

## Executive Summary
"""


def write_nfr(path, status):
    path.write_text(NFR_TEMPLATE.format(status=status), encoding="utf-8")


REVIEW_TEMPLATE = """---
workflowType: 'testarch-test-review'
---

# Test Quality Review: demo.spec.ts

**Quality Score**: {score}/100 (B - Good)
**Review Date**: 2026-06-03

## Executive Summary

**Recommendation**: {recommendation}
"""


def write_review(path, score, recommendation):
    path.write_text(REVIEW_TEMPLATE.format(score=score, recommendation=recommendation), encoding="utf-8")


# --- Verdict mapping from the slim gate-decision.json -----------------------

@pytest.mark.parametrize(
    "gate_status,verdict",
    [
        ("PASS", "advance"),
        ("WAIVED", "advance"),
        ("CONCERNS", "defer"),
        ("FAIL", "reloop"),
        ("NOT_EVALUATED", "escalate"),
    ],
)
def test_verdict_mapping(tmp_path, gate_status, verdict):
    write_slim(tmp_path, gate_status)
    result = run_gate(tmp_path, profile="light")
    assert result["verdict"] == verdict
    assert result["gate_status"] == gate_status


def test_slim_carries_priority_statuses(tmp_path):
    write_slim(tmp_path, "PASS", p0="MET", p1="PARTIAL", overall="MET")
    result = run_gate(tmp_path, profile="light")
    assert result["p0_status"] == "MET"
    assert result["p1_status"] == "PARTIAL"
    assert result["overall_status"] == "MET"


def test_unrecognized_gate_status_escalates(tmp_path):
    write_slim(tmp_path, "BOGUS")
    result = run_gate(tmp_path, profile="light")
    assert result["verdict"] == "escalate"


# --- Missing-slim-file fallback (NOT a failure) -----------------------------

def test_missing_slim_falls_back_to_summary(tmp_path):
    # No gate-decision.json; the always-written summary carries the gate.
    write_summary(tmp_path, gate_status="PASS")
    result = run_gate(tmp_path, profile="light")
    assert result["verdict"] == "advance"
    assert result["gate_status"] == "PASS"
    assert any("not a failure" in r for r in result["reasons"])


def test_missing_slim_summary_concerns(tmp_path):
    write_summary(tmp_path, gate_status="CONCERNS", p1="PARTIAL")
    result = run_gate(tmp_path, profile="light")
    assert result["verdict"] == "defer"
    assert result["p1_status"] == "PARTIAL"


def test_summary_without_gate_fields_is_not_evaluated(tmp_path):
    # Not gate-eligible: summary exists but has no gate_status/gate_criteria.
    write_summary(tmp_path, gate_status=None)
    result = run_gate(tmp_path, profile="light")
    assert result["gate_status"] == "NOT_EVALUATED"
    assert result["verdict"] == "escalate"


def test_no_artifacts_at_all_escalates(tmp_path):
    result = run_gate(tmp_path, profile="light")
    assert result["gate_status"] == "NOT_EVALUATED"
    assert result["verdict"] == "escalate"


def test_slim_preferred_over_summary(tmp_path):
    write_slim(tmp_path, "PASS")
    write_summary(tmp_path, gate_status="FAIL")
    result = run_gate(tmp_path, profile="light")
    # The slim file wins when both are present.
    assert result["gate_status"] == "PASS"
    assert result["verdict"] == "advance"


def test_frontmatter_hint_resolves_gate_file(tmp_path):
    (tmp_path / "traceability-matrix.md").write_text(
        "---\nworkflowType: 'testarch-trace'\ngateDecisionFile: custom-gate.json\n---\n# report\n",
        encoding="utf-8",
    )
    payload = {"gate_status": "FAIL", "p0_status": "NOT_MET", "p1_status": "MET", "overall_status": "MET"}
    (tmp_path / "custom-gate.json").write_text(json.dumps(payload), encoding="utf-8")
    result = run_gate(tmp_path, profile="light")
    assert result["gate_status"] == "FAIL"
    assert result["verdict"] == "reloop"
    assert any("custom-gate.json" in r for r in result["reasons"])


# --- Production AND with nfr / test-review -----------------------------------

def test_production_all_green_advances(tmp_path):
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    review = tmp_path / "test-review.md"
    write_nfr(nfr, "PASS")
    write_review(review, 92, "Approve")
    result = run_gate(tmp_path, profile="production", nfr=nfr, test_review=review)
    assert result["verdict"] == "advance"
    assert result["nfr_status"] == "PASS"
    assert result["review_score"] == 92


def test_production_nfr_fail_downgrades_advance_to_reloop(tmp_path):
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    review = tmp_path / "test-review.md"
    write_nfr(nfr, "FAIL")
    write_review(review, 92, "Approve")
    result = run_gate(tmp_path, profile="production", nfr=nfr, test_review=review)
    assert result["verdict"] == "reloop"
    assert result["nfr_status"] == "FAIL"


def test_production_nfr_concerns_keeps_advance(tmp_path):
    # Only FAIL trips the NFR signal; CONCERNS is acceptable.
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    review = tmp_path / "test-review.md"
    write_nfr(nfr, "CONCERNS")
    write_review(review, 85, "Approve with Comments")
    result = run_gate(tmp_path, profile="production", nfr=nfr, test_review=review)
    assert result["verdict"] == "advance"
    assert result["nfr_status"] == "CONCERNS"


def test_production_low_review_score_downgrades(tmp_path):
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    review = tmp_path / "test-review.md"
    write_nfr(nfr, "PASS")
    write_review(review, 79, "Request Changes")
    result = run_gate(tmp_path, profile="production", nfr=nfr, test_review=review)
    assert result["verdict"] == "reloop"
    assert result["review_score"] == 79


def test_production_boundary_score_80_advances(tmp_path):
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    review = tmp_path / "test-review.md"
    write_nfr(nfr, "PASS")
    write_review(review, 80, "Approve with Comments")
    result = run_gate(tmp_path, profile="production", nfr=nfr, test_review=review)
    assert result["verdict"] == "advance"


def test_production_block_recommendation_downgrades(tmp_path):
    # High score but a Block recommendation still trips the signal.
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    review = tmp_path / "test-review.md"
    write_nfr(nfr, "PASS")
    write_review(review, 90, "Block")
    result = run_gate(tmp_path, profile="production", nfr=nfr, test_review=review)
    assert result["verdict"] == "reloop"


def test_production_missing_nfr_file_downgrades(tmp_path):
    write_slim(tmp_path, "PASS")
    review = tmp_path / "test-review.md"
    write_review(review, 95, "Approve")
    result = run_gate(
        tmp_path, profile="production", nfr=tmp_path / "absent.md", test_review=review
    )
    assert result["verdict"] == "reloop"


def test_production_signals_do_not_lift_concerns(tmp_path):
    # The downgrade floor is reloop; production signals never raise a verdict.
    # A CONCERNS gate stays defer even when nfr/review are green.
    write_slim(tmp_path, "CONCERNS")
    nfr = tmp_path / "nfr-assessment.md"
    review = tmp_path / "test-review.md"
    write_nfr(nfr, "PASS")
    write_review(review, 99, "Approve")
    result = run_gate(tmp_path, profile="production", nfr=nfr, test_review=review)
    assert result["verdict"] == "defer"


def test_production_fail_stays_reloop_regardless_of_signals(tmp_path):
    write_slim(tmp_path, "FAIL", p0="NOT_MET")
    nfr = tmp_path / "nfr-assessment.md"
    review = tmp_path / "test-review.md"
    write_nfr(nfr, "FAIL")
    write_review(review, 10, "Block")
    result = run_gate(tmp_path, profile="production", nfr=nfr, test_review=review)
    assert result["verdict"] == "reloop"


def test_light_profile_ignores_production_signals(tmp_path):
    # Even with a failing nfr passed in, --light decides on the gate alone.
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    write_nfr(nfr, "FAIL")
    result = run_gate(tmp_path, profile="light", nfr=nfr)
    assert result["verdict"] == "advance"
    assert result["nfr_status"] is None


# --- --story selector in a shared multi-story trace dir ----------


def write_named_slim(dir_path, name, gate_status, p0="MET", p1="MET", overall="MET"):
    payload = {
        "schema_version": "0.1.0",
        "gate_status": gate_status,
        "p0_status": p0,
        "p1_status": p1,
        "overall_status": overall,
    }
    (dir_path / name).write_text(json.dumps(payload), encoding="utf-8")


def write_trace_report(dir_path, name, gate_decision_file):
    (dir_path / name).write_text(
        "---\n"
        "workflowType: 'testarch-trace'\n"
        f"gateDecisionFile: {gate_decision_file}\n"
        "---\n# trace report\n",
        encoding="utf-8",
    )


def test_story_selector_picks_current_not_oldest_in_shared_dir(tmp_path):
    # Two stories share one trace dir. The lexically-first (oldest) report is the
    # FAILing story 11-1; the current story 11-6 PASSes.
    write_trace_report(tmp_path, "trace-11-1.md", "gate-decision-11-1.json")
    write_named_slim(tmp_path, "gate-decision-11-1.json", "FAIL", p0="NOT_MET")
    write_trace_report(tmp_path, "trace-11-6.md", "gate-decision-11-6.json")
    write_named_slim(tmp_path, "gate-decision-11-6.json", "PASS")

    # Bug repro: with no --story the unscoped glob resolves the oldest (11-1).
    unscoped = run_gate(tmp_path, profile="light")
    assert unscoped["gate_status"] == "FAIL"

    # Fix: --story scopes resolution to the current story's artifacts.
    scoped = run_gate(tmp_path, profile="light", story="11-6")
    assert scoped["gate_status"] == "PASS"
    assert scoped["verdict"] == "advance"


def test_story_selector_disambiguates_epic_from_story(tmp_path):
    # Epic-level (11) and a story (11-6) coexist; end-anchored matching keeps them
    # apart so --story 11 never resolves the 11-6 report and vice versa.
    write_trace_report(tmp_path, "trace-11.md", "gate-decision-11.json")
    write_named_slim(tmp_path, "gate-decision-11.json", "FAIL", p0="NOT_MET")
    write_trace_report(tmp_path, "trace-11-6.md", "gate-decision-11-6.json")
    write_named_slim(tmp_path, "gate-decision-11-6.json", "PASS")

    assert run_gate(tmp_path, profile="light", story="11-6")["gate_status"] == "PASS"
    assert run_gate(tmp_path, profile="light", story="11")["gate_status"] == "FAIL"


def test_story_selector_epic_id_not_confused_with_child_story(tmp_path):
    # The E-E collision: a single-component epic id (1) must resolve the epic
    # report, NOT child story 1-1 whose LAST component also equals 1 — and
    # trace-1-1.md sorts BEFORE trace-1.md, so an unscoped/suffix match would
    # wrongly return the child's gate as the epic verdict (the false-verdict
    # class this selector exists to prevent). Reachable in-repo: epic 1 / story 1-1.
    write_trace_report(tmp_path, "trace-1-1.md", "gate-decision-1-1.json")
    write_named_slim(tmp_path, "gate-decision-1-1.json", "FAIL", p0="NOT_MET")
    write_trace_report(tmp_path, "trace-1.md", "gate-decision-1.json")
    write_named_slim(tmp_path, "gate-decision-1.json", "PASS")
    # Epic-level gate scoped to epic id 1 reads the epic's PASS, not 1-1's FAIL.
    assert run_gate(tmp_path, profile="light", story="1")["gate_status"] == "PASS"
    # The child story still resolves itself.
    assert run_gate(tmp_path, profile="light", story="1-1")["gate_status"] == "FAIL"


def test_story_selector_convention_slim_without_hint(tmp_path):
    # No trace-report hint; the conventionally-named per-story slim file is used,
    # and a decoy sibling story's slim file must NOT be picked.
    write_named_slim(tmp_path, "gate-decision-9-1.json", "FAIL", p0="NOT_MET")
    write_named_slim(tmp_path, "gate-decision-9-2.json", "PASS")
    result = run_gate(tmp_path, profile="light", story="9-2")
    assert result["gate_status"] == "PASS"
    assert any("gate-decision-9-2.json" in r for r in result["reasons"])


def test_story_selector_separator_insensitive(tmp_path):
    # --story 7-3 resolves a dot-separated artifact name (7.3) and vice versa.
    write_named_slim(tmp_path, "gate-decision-7.3.json", "PASS")
    result = run_gate(tmp_path, profile="light", story="7-3")
    assert result["gate_status"] == "PASS"


def test_story_selector_falls_back_to_unscoped_when_no_match(tmp_path):
    # A single-story dir with a non-story-named report still resolves when a
    # caller passes --story that matches nothing here (graceful fallback).
    (tmp_path / "traceability-matrix.md").write_text(
        "---\nworkflowType: 'testarch-trace'\ngateDecisionFile: custom-gate.json\n---\n# report\n",
        encoding="utf-8",
    )
    write_named_slim(tmp_path, "custom-gate.json", "PASS")
    result = run_gate(tmp_path, profile="light", story="3-4")
    assert result["gate_status"] == "PASS"
    assert result["verdict"] == "advance"


def test_story_selector_per_story_summary_fallback(tmp_path):
    # No slim file; the per-story summary is preferred over a sibling story's.
    write_summary(tmp_path, gate_status=None)  # shared, no gate fields
    other = tmp_path / "e2e-trace-summary-5-1.json"
    other.write_text(json.dumps({"gate_status": "FAIL"}), encoding="utf-8")
    mine = tmp_path / "e2e-trace-summary-5-2.json"
    mine.write_text(json.dumps({"gate_status": "PASS"}), encoding="utf-8")
    result = run_gate(tmp_path, profile="light", story="5-2")
    assert result["gate_status"] == "PASS"


def test_no_story_flag_is_backward_compatible(tmp_path):
    # The default (no --story) path is unchanged: slim gate-decision.json wins.
    write_slim(tmp_path, "PASS")
    result = run_gate(tmp_path, profile="light")
    assert result["gate_status"] == "PASS"


# --- --story fails closed on a genuine no-match ------------------------------


def _per_story_dir(tmp_path):
    """A shared dir holding TWO stories' per-story-named artifacts (2-1, 4-2)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    write_trace_report(tmp_path, "trace-2-1.md", "gate-decision-2-1.json")
    write_named_slim(tmp_path, "gate-decision-2-1.json", "PASS")
    write_trace_report(tmp_path, "trace-4-2.md", "gate-decision-4-2.json")
    write_named_slim(tmp_path, "gate-decision-4-2.json", "FAIL", p0="NOT_MET")
    return tmp_path


def test_absent_story_in_per_story_named_dir_is_not_evaluated(tmp_path):
    # The fail-open this closes: story 4-9 wrote NOTHING here, yet the unscoped
    # fallback used to hand back the first report's gate — reporting an
    # unevaluated story as a green PASS/advance. A per-story-named dir means the
    # requested story is genuinely absent, so the read fails closed.
    _per_story_dir(tmp_path)
    result = run_gate(tmp_path, profile="light", story="4-9")

    assert result["gate_status"] == "NOT_EVALUATED"
    assert result["verdict"] == "escalate"
    # Explicitly NOT the neighbouring story's verdict.
    assert result["verdict"] != "advance"
    assert result["p0_status"] is None
    assert result["p1_status"] is None
    assert result["overall_status"] is None
    # The reasons name the story that was asked for and say why no fallback ran.
    assert any("4-9" in r for r in result["reasons"])
    assert any("named per story" in r for r in result["reasons"])
    assert not any("gate-decision-2-1.json" in r for r in result["reasons"])


def test_absent_story_in_per_story_named_dir_without_reports(tmp_path):
    # Same rule keyed on the gate-decision names alone (no trace reports at all):
    # gate-decision-4-2.json is named for a story, so the dir is per-story-named.
    write_named_slim(tmp_path, "gate-decision-4-2.json", "PASS")
    result = run_gate(tmp_path, profile="light", story="4-9")
    assert result["gate_status"] == "NOT_EVALUATED"
    assert result["verdict"] == "escalate"


def test_generic_named_dir_still_resolves_unmatched_story(tmp_path):
    # PRESERVED documented fallback: a dir holding ONE story's artifacts under
    # generic names (trace.md / gate-decision.json) carries no story id to match,
    # so --story must still resolve it rather than fail closed.
    (tmp_path / "trace.md").write_text(
        "---\nworkflowType: 'testarch-trace'\n---\n# trace report\n", encoding="utf-8"
    )
    write_slim(tmp_path, "PASS")
    result = run_gate(tmp_path, profile="light", story="4-9")
    assert result["gate_status"] == "PASS"
    assert result["verdict"] == "advance"
    assert any("gate-decision.json" in r for r in result["reasons"])


def test_present_story_still_resolves_in_per_story_named_dir(tmp_path):
    # The fail-closed rule must not swallow a story that IS present: 4-2 resolves
    # its own gate-decision-4-2.json, not the sibling 2-1 PASS.
    _per_story_dir(tmp_path)
    result = run_gate(tmp_path, profile="light", story="4-2")
    assert result["gate_status"] == "FAIL"
    assert result["verdict"] == "reloop"
    assert any("gate-decision-4-2.json" in r for r in result["reasons"])


def test_epic_level_resolution_still_works_alongside_children(tmp_path):
    # Epic-level gate: --story 4 resolves the epic's OWN artifact, never child 4-1
    # (whose stem also ends in a numeric component).
    write_trace_report(tmp_path, "trace-4-1.md", "gate-decision-4-1.json")
    write_named_slim(tmp_path, "gate-decision-4-1.json", "FAIL", p0="NOT_MET")
    write_trace_report(tmp_path, "trace-4.md", "gate-decision-4.json")
    write_named_slim(tmp_path, "gate-decision-4.json", "PASS")

    epic = run_gate(tmp_path, profile="light", story="4")
    assert epic["gate_status"] == "PASS"
    assert any("gate-decision-4.json" in r for r in epic["reasons"])
    # And an epic with no artifacts of its own still fails closed here.
    assert run_gate(tmp_path, profile="light", story="9")["gate_status"] == "NOT_EVALUATED"


def test_own_slim_wins_over_a_neighbours_frontmatter_hint(tmp_path):
    # A story that wrote its own slim gate file but NO trace report must resolve
    # that file — never the first frontmatter hint in the shared directory.
    #
    # Observed in the field: `--story` matched no `trace-*.md`, so scoping left
    # every report in play and the hint loop returned an unrelated epic's gate.
    # The wrong answer was a PASS, which is the verdict nobody re-reads.
    write_trace_report(tmp_path, "trace-11-0.md", "gate-decision-11-0.json")
    write_named_slim(tmp_path, "gate-decision-11-0.json", "PASS")
    write_named_slim(tmp_path, "gate-decision-92-6c.json", "CONCERNS")

    result = run_gate(tmp_path, profile="light", story="92-6c")
    assert result["gate_status"] == "CONCERNS"
    assert result["verdict"] == "defer"
    assert any("gate-decision-92-6c.json" in r for r in result["reasons"])
    assert not any("gate-decision-11-0.json" in r for r in result["reasons"])


# --- Anti-vacuous twin: mutate a COPY of the script, assert the test reds -----


def _write_mutant(tmp_path, name, old, new):
    """Copy the shipped script, apply one textual mutation, return the copy."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert old in src, f"mutation anchor drifted out of gate_eval.py: {name}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"mutant_{name}.py"
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    return path


_FAIL_CLOSED_CLAUSE = (
    "        elif _is_per_story_named(trace_output):\n"
    "            return None\n"
)

# The clause that stops a story's OWN slim gate file from being passed over in
# favour of a neighbour's frontmatter hint. The mutation below rewrites the two
# scoping clauses back into the single pre-fix one, which is what let story B be
# handed story A's verdict.
_OWN_SLIM_WINS_CLAUSE = (
    "        elif scoped_slim is not None:\n"
    "            # This story wrote no trace report but DID write its own slim gate\n"
    "            # file. Falling through here would leave ``reports`` as every report\n"
    "            # in the directory and let the hint loop below return a NEIGHBOUR's\n"
    "            # gate — observed handing an unrelated epic's PASS back as this\n"
    "            # story's verdict. The story's own file wins, before any hint is read.\n"
    "            return scoped_slim\n"
    "        elif _is_per_story_named(trace_output):\n"
    "            return None\n"
)

_PRE_FIX_SCOPING_CLAUSE = (
    "        elif scoped_slim is None and _is_per_story_named(trace_output):\n"
    "            return None\n"
)


def test_mutant_without_fail_closed_clause_reports_neighbours_pass(tmp_path):
    """Twin for test_absent_story_in_per_story_named_dir_is_not_evaluated.

    Concrete mutation: delete the fail-closed clause from _resolve_gate_file, so
    resolution falls through to the unscoped read exactly as it did before the
    fix. The absent story 4-9 then reports the NEIGHBOUR story 2-1's PASS —
    which is the assertion the named test above makes, so that test reds. If the
    NOT_EVALUATED survived this deletion, the clause would not be what produces
    it and the named test would prove nothing.
    """
    mutant = _write_mutant(tmp_path / "src", "no_fail_closed", _FAIL_CLOSED_CLAUSE, "")
    trace = _per_story_dir(tmp_path / "trace")

    proc = subprocess.run(
        [sys.executable, str(mutant), "--trace-output", str(trace),
         "--profile", "light", "--story", "4-9"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)

    # The pre-fix fail-open, reproduced against the mutant.
    assert result["gate_status"] == "PASS"
    assert result["verdict"] == "advance"
    assert any("gate-decision-2-1.json" in r for r in result["reasons"])


def test_mutant_always_fail_closed_reds_the_generic_fallback(tmp_path):
    """Twin for test_generic_named_dir_still_resolves_unmatched_story.

    Concrete mutation: drop the _is_per_story_named guard so ANY no-match fails
    closed. The generic-name dir then returns NOT_EVALUATED instead of its PASS,
    reding the named test above. This isolates the per-story-named condition as
    load-bearing rather than the fail-close being unconditional.
    """
    mutant = _write_mutant(
        tmp_path / "src",
        "always_fail_closed",
        "        elif _is_per_story_named(trace_output):\n",
        "        else:\n",
    )
    trace = tmp_path / "trace"
    trace.mkdir(parents=True)
    (trace / "trace.md").write_text(
        "---\nworkflowType: 'testarch-trace'\n---\n# trace report\n", encoding="utf-8"
    )
    write_slim(trace, "PASS")

    proc = subprocess.run(
        [sys.executable, str(mutant), "--trace-output", str(trace),
         "--profile", "light", "--story", "4-9"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)

    assert result["gate_status"] == "NOT_EVALUATED"
    assert result["verdict"] == "escalate"


def test_mutant_without_own_slim_clause_reports_another_epics_pass(tmp_path):
    """Twin for test_own_slim_wins_over_a_neighbours_frontmatter_hint.

    Concrete mutation: restore the pre-fix scoping clause verbatim, so a story
    with a slim gate file but no trace report falls through with `reports` still
    holding every report in the directory. The hint loop then hands back epic
    11's gate — a PASS — as story 92-6c's verdict, which is exactly the field
    failure. If CONCERNS survived this reversion, the new clause would not be
    what produces it.
    """
    mutant = _write_mutant(
        tmp_path / "src", "no_own_slim", _OWN_SLIM_WINS_CLAUSE, _PRE_FIX_SCOPING_CLAUSE
    )
    trace = tmp_path / "trace"
    trace.mkdir(parents=True)
    write_trace_report(trace, "trace-11-0.md", "gate-decision-11-0.json")
    write_named_slim(trace, "gate-decision-11-0.json", "PASS")
    write_named_slim(trace, "gate-decision-92-6c.json", "CONCERNS")

    proc = subprocess.run(
        [sys.executable, str(mutant), "--trace-output", str(trace),
         "--profile", "light", "--story", "92-6c"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)

    # The pre-fix fail-open, reproduced against the mutant: a neighbour's PASS.
    assert result["gate_status"] == "PASS"
    assert result["verdict"] == "advance"
    assert any("gate-decision-11-0.json" in r for r in result["reasons"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
