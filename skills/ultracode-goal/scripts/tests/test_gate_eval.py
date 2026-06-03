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


def run_gate(trace_output, profile="light", nfr=None, test_review=None):
    cmd = [sys.executable, str(SCRIPT), "--trace-output", str(trace_output), "--profile", profile]
    if nfr is not None:
        cmd += ["--nfr", str(nfr)]
    if test_review is not None:
        cmd += ["--test-review", str(test_review)]
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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
