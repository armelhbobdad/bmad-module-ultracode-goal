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


def _load_gate_eval():
    """Import the script as a module, for the pure predicates.

    Everything else here drives it as a SUBPROCESS on purpose - that is the
    surface a caller uses. A couple of checks below are about one pure function's
    classification rule, where a subprocess would only let us observe it through
    three layers of resolution.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("gate_eval_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


gate_eval_module = _load_gate_eval()


def run_gate(
    trace_output, profile="light", nfr=None, test_review=None, story=None, epic_level=False
):
    cmd = [sys.executable, str(SCRIPT), "--trace-output", str(trace_output), "--profile", profile]
    if nfr is not None:
        cmd += ["--nfr", str(nfr)]
    if test_review is not None:
        cmd += ["--test-review", str(test_review)]
    if story is not None:
        cmd += ["--story", str(story)]
    if epic_level:
        cmd += ["--epic-level"]
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


def test_undecodable_report_does_not_advance_on_an_unpointed_at_file(tmp_path):
    """An unreadable report is a hint that could not be READ, not a missing hint.

    The catch that keeps a non-UTF-8 markdown file from crashing resolution must
    not also classify it as carrying no hint: `reports` here is the unfiltered
    `*.md` glob, so this reader cannot know the file it failed to decode was not
    a trace report pointing at a FAILING gate. Skipping it silently let
    resolution fall through to the unpointed-at `gate-decision.json` and advance.
    """
    (tmp_path / "traceability-matrix.md").write_bytes(
        b"---\nworkflowType: 'testarch-trace'\ngateDecisionFile: real-gate.json\n"
        b"note: \xff\xfe not utf-8\n---\n# report\n"
    )
    # The file the undecodable report points at says FAIL.
    (tmp_path / "real-gate.json").write_text(
        json.dumps({"gate_status": "FAIL", "p0_status": "NOT_MET", "p1_status": "MET", "overall_status": "MET"}),
        encoding="utf-8",
    )
    # The file nobody pointed at says PASS. Resolving THIS one is the fail-open.
    write_slim(tmp_path, "PASS")

    result = run_gate(tmp_path, profile="light")

    assert result["verdict"] != "advance", (
        "a story whose only gate hint could not be decoded must not advance on a "
        "file nobody pointed at"
    )
    assert result["gate_status"] != "PASS"


def test_decodable_non_trace_report_still_does_not_refuse(tmp_path):
    """Twin: the catch must stay narrow.

    A readable markdown file that simply is not a trace report carries no hint,
    and must not fail the gate closed - otherwise any stray note in the artifact
    directory would block every story.
    """
    (tmp_path / "notes.md").write_text("# just a note, no frontmatter\n", encoding="utf-8")
    write_slim(tmp_path, "PASS")

    result = run_gate(tmp_path, profile="light")

    assert result["gate_status"] == "PASS"
    assert result["verdict"] == "advance"


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


def test_production_omitted_nfr_flag_is_failing_not_silent(tmp_path):
    """A flag that is never passed must not buy a higher verdict than a failing one.

    An omitted path used to be skipped in silence: the AND did not run, the field
    rendered `null`, and the verdict was computed WITHOUT the signal. So a run
    that forgot `--nfr` advanced where a run that supplied a FAILING nfr would
    have re-looped, and `null` beside `--profile production` read as "missing or
    malformed" - the opposite of "not asked for".
    """
    write_slim(tmp_path, "PASS")
    review = tmp_path / "test-review.md"
    write_review(review, 90, "Approve")
    result = run_gate(tmp_path, profile="production", test_review=review)

    assert result["verdict"] == "reloop"
    assert any("--nfr not supplied" in r for r in result["reasons"])
    assert any("--epic-level" in r for r in result["reasons"]), "the reason names the escape"


def test_production_omitted_test_review_flag_is_failing_not_silent(tmp_path):
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    write_nfr(nfr, "PASS")
    result = run_gate(tmp_path, profile="production", nfr=nfr)

    assert result["verdict"] == "reloop"
    assert any("--test-review not supplied" in r for r in result["reasons"])


def test_epic_level_declares_the_omission_instead_of_implying_it(tmp_path):
    """The epic roll-up has no aggregate to AND, and now says so explicitly.

    `references/gate.md` is right that omitting the flags is CORRECT at the epic
    level - TEA writes both artifacts per story - but "correct omission" and
    "forgotten flag" were the same input. `--epic-level` separates them.
    """
    write_slim(tmp_path, "PASS")
    result = run_gate(tmp_path, profile="production", epic_level=True)

    assert result["verdict"] == "advance"
    assert result["nfr_status"] is None
    assert result["review_score"] is None
    assert any("epic-level roll-up" in r for r in result["reasons"])


def test_epic_level_still_cannot_lift_a_failing_trace_gate(tmp_path):
    """The escape skips the ANDs; it never touches the gate status itself."""
    write_slim(tmp_path, "FAIL", p0="NOT_MET")
    result = run_gate(tmp_path, profile="production", epic_level=True)
    assert result["verdict"] == "reloop"


def test_epic_level_is_a_no_op_under_light(tmp_path):
    """`--profile light` runs no ANDs anyway, so the flag decides nothing.

    It is still REPORTED truthfully in `epic_level` - the caller did declare it -
    so the comparison excludes that key and asserts every deciding field is
    untouched.
    """
    write_slim(tmp_path, "PASS")
    plain = run_gate(tmp_path, profile="light")
    flagged = run_gate(tmp_path, profile="light", epic_level=True)

    assert {k: v for k, v in plain.items() if k != "epic_level"} == {
        k: v for k, v in flagged.items() if k != "epic_level"
    }
    assert plain["epic_level"] is False and flagged["epic_level"] is True


def test_production_both_flags_omitted_names_both(tmp_path):
    """Two omissions are two reasons, not one."""
    write_slim(tmp_path, "PASS")
    result = run_gate(tmp_path, profile="production")
    assert result["verdict"] == "reloop"
    assert any("--nfr not supplied" in r for r in result["reasons"])
    assert any("--test-review not supplied" in r for r in result["reasons"])


def test_an_omitted_flag_cannot_lower_a_verdict_below_reloop(tmp_path):
    """The downgrade floor is unchanged: only an otherwise-advance verdict moves."""
    write_slim(tmp_path, "CONCERNS")
    result = run_gate(tmp_path, profile="production")
    assert result["verdict"] == "defer", "a CONCERNS defer is not dragged to reloop"


def test_epic_level_refuses_to_combine_with_a_supplied_path(tmp_path):
    """`--epic-level` asserts there is nothing to AND, so a path contradicts it.

    Without this, the flag wins silently and DISCARDS an explicitly named
    artifact - including a FAILING one. `references/gate.md` already calls the
    hybrid the mirror mistake; this puts it in the invocation-error lane a
    missing `--story` already occupies.
    """
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    write_nfr(nfr, "FAIL")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--trace-output", str(tmp_path), "--profile",
         "production", "--epic-level", "--nfr", str(nfr)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 2, proc.stdout
    assert "--epic-level" in proc.stderr


def test_epic_level_is_reported_machine_readably(tmp_path):
    """`reasons` wording is explicitly non-contractual, so the fact needs a key.

    Without it a consumer cannot tell an `advance` that ANDed both production
    signals from one that skipped them, and `nfr_status: null` alone does not say.
    """
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    review = tmp_path / "test-review.md"
    write_nfr(nfr, "PASS")
    write_review(review, 92, "Approve")

    anded = run_gate(tmp_path, profile="production", nfr=nfr, test_review=review)
    skipped = run_gate(tmp_path, profile="production", epic_level=True)

    assert anded["verdict"] == skipped["verdict"] == "advance"
    assert anded["epic_level"] is False
    assert skipped["epic_level"] is True, "the two advances are distinguishable"
    assert run_gate(tmp_path, profile="light")["epic_level"] is False


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


def test_the_shipped_epic_level_invocation_passes_the_flag():
    """Drift here reloops a passing epic, silently.

    `--epic-level` is only correct because the surface that performs the epic
    roll-up — gate.md's fenced invocation — actually passes it. If it drops it,
    the roll-up hits the omitted-flag rule and downgrades an epic PASS to
    `reloop` with no other
    symptom - which is exactly the class of silent doc/code drift the omitted-flag
    fix exists to remove.
    """
    gate_md = (SCRIPT.parent.parent / "references" / "gate.md").read_text(encoding="utf-8")
    # Fenced invocations only. Prose ALSO names the flags while discussing them,
    # and a prose match would assert against a sentence rather than a command.
    fenced = [ln.strip() for ln in gate_md.splitlines() if ln.strip().startswith("uv run ")]
    epic_cmd = next((ln for ln in fenced if "<epic_id>" in ln), None)
    assert epic_cmd, "references/gate.md no longer shows an epic-level invocation"
    assert "--epic-level" in epic_cmd, epic_cmd
    assert "--nfr" not in epic_cmd and "--test-review" not in epic_cmd, (
        "the epic roll-up must not combine --epic-level with a signal path"
    )

    # And the per-story invocation must still carry both paths.
    story_cmd = next(
        (ln for ln in fenced if "--profile production" in ln and "<story_id>" in ln), None
    )
    assert story_cmd, "references/gate.md no longer shows a per-story production invocation"
    assert "--nfr" in story_cmd and "--test-review" in story_cmd, story_cmd
    assert "--epic-level" not in story_cmd, story_cmd


# --- Anti-vacuous twin: mutate a COPY of the script, assert the test reds -----


def _write_mutant(tmp_path, name, *pairs):
    """Copy the shipped script, apply each textual mutation in turn, return the copy.

    Takes MANY (old, new) pairs, not one, because the resolver no longer has a
    single guard between an absent story and a neighbour's PASS. Three
    independent clauses now refuse it, so deleting any one of them on its own
    leaves the refusal intact and a one-shot mutation can no longer reproduce the
    historical field failure. A twin that mutated one clause and saw the fail-open
    NOT come back would look like a passing test while proving nothing; these
    twins therefore remove every clause on the path and assert the failure returns.
    """
    src = SCRIPT.read_text(encoding="utf-8")
    tmp_path.mkdir(parents=True, exist_ok=True)
    for index, (old, new) in enumerate(pairs):
        assert old in src, f"mutation anchor {index} drifted out of gate_eval.py: {name}"
        src = src.replace(old, new, 1)
    path = tmp_path / f"mutant_{name}.py"
    path.write_text(src, encoding="utf-8")
    return path


_FAIL_CLOSED_CLAUSE = (
    "        elif _is_per_story_named(trace_output) and not _owns_a_per_story_summary(\n"
    "            trace_output, story\n"
    "        ):\n"
    "            return None\n"
)

# The ownership + containment test applied to a `gateDecisionFile` hint. Neutralizing
# it restores the pre-fix behaviour of following any hint verbatim, which is the
# second guard each twin below has to remove before its fail-open reappears.
_HINT_GUARD = (
    "    if story and story.strip():\n"
    "        if _has_trailing_id(resolved.stem):\n"
    "            return candidate if _stem_matches_story(resolved.stem, story) else None\n"
    "        return None if _holds_another_storys_artifact(trace_output, story) else candidate\n"
    "    return candidate\n"
)
_HINT_GUARD_REMOVED = "    return candidate\n"

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
) + _FAIL_CLOSED_CLAUSE

_PRE_FIX_SCOPING_CLAUSE = (
    "        elif scoped_slim is None and _is_per_story_named(trace_output):\n"
    "            return None\n"
)


def test_mutant_without_fail_closed_clause_reports_neighbours_pass(tmp_path):
    """Twin for test_absent_story_in_per_story_named_dir_is_not_evaluated.

    Concrete mutation, in TWO parts because there are now two guards on this
    path: delete the fail-closed clause from _resolve_gate_file, AND stop the
    `gateDecisionFile` hint from being ownership-checked. Resolution then falls
    through to the unscoped read exactly as it did before either fix, and the
    absent story 4-9 reports the NEIGHBOUR story 2-1's PASS — which is the
    assertion the named test above makes, so that test reds.

    Deleting only the fail-closed clause is NOT enough any more, and that is the
    point of the second pair rather than an inconvenience: the hint check catches
    the same fail-open one step later, so the two clauses are independent guards
    over one hole. If NOT_EVALUATED survived BOTH deletions, neither clause would
    be what produces it and the named test would prove nothing.
    """
    mutant = _write_mutant(
        tmp_path / "src",
        "no_fail_closed",
        (_FAIL_CLOSED_CLAUSE, ""),
        (_HINT_GUARD, _HINT_GUARD_REMOVED),
    )
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
        (
            "        elif _is_per_story_named(trace_output) and not _owns_a_per_story_summary(\n"
            "            trace_output, story\n"
            "        ):\n",
            "        else:\n",
        ),
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

    Concrete mutation, in TWO parts: restore the pre-fix scoping clause verbatim,
    so a story with a slim gate file but no trace report falls through with
    `reports` still holding every report in the directory, AND stop the
    `gateDecisionFile` hint from being ownership-checked. The hint loop then
    hands back epic 11's gate — a PASS — as story 92-6c's verdict, which is
    exactly the field failure.

    As with the twin above, the reversion alone no longer reproduces it: the hint
    check refuses epic 11's file for story 92-6c on its own, so both guards have
    to go before the historical verdict comes back. If CONCERNS survived both,
    neither clause would be what produces it.
    """
    mutant = _write_mutant(
        tmp_path / "src",
        "no_own_slim",
        (_OWN_SLIM_WINS_CLAUSE, _PRE_FIX_SCOPING_CLAUSE),
        (_HINT_GUARD, _HINT_GUARD_REMOVED),
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


def test_an_nfr_named_for_a_story_does_not_buy_it_out_of_fail_closed(tmp_path):
    """A markdown file merely NAMED for a story is not a trace report.

    `references/gate.md` tells the non-web author to write
    `nfr-assessment-<id>.md` and `test-review-<id>.md` into the same directory as
    the trace pair, and both match the id-component test. So a story that
    produced its NFR and review but never authored its trace pair looked
    "present" to the resolver: `scoped` was non-empty, the fail-closed return was
    skipped, neither file carries a `gateDecisionFile` hint, and resolution fell
    through to the UNSCOPED summary - handing an artifact-less story a PASS.

    That is the same fail-open class as the neighbour's-gate defect, reached by a
    different door, and the per-story naming rule makes the door mandatory.
    """
    write_trace_report(tmp_path, "trace-1-1.md", "gate-decision-1-1.json")
    write_named_slim(tmp_path, "gate-decision-1-1.json", "CONCERNS")
    # The always-written summary, carrying someone else's PASS.
    (tmp_path / "e2e-trace-summary.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )
    # Story 1-2: NFR and review present, trace pair absent.
    (tmp_path / "nfr-assessment-1-2.md").write_text(
        "**Overall Status:** PASS\n", encoding="utf-8"
    )
    (tmp_path / "test-review-1-2.md").write_text(
        "**Quality Score**: 95/100\n**Recommendation**: Approve\n", encoding="utf-8"
    )

    result = run_gate(tmp_path, profile="light", story="1-2")
    assert result["gate_status"] == "NOT_EVALUATED"
    assert result["verdict"] == "escalate"
    assert any("no trace report or gate decision" in r for r in result["reasons"])


def test_a_declared_trace_report_still_scopes_normally(tmp_path):
    """The narrowing must not stop a real trace report from scoping.

    Same directory shape as above, except story 1-2 DID author its trace pair.
    """
    write_trace_report(tmp_path, "trace-1-1.md", "gate-decision-1-1.json")
    write_named_slim(tmp_path, "gate-decision-1-1.json", "FAIL", p0="NOT_MET")
    write_trace_report(tmp_path, "trace-1-2.md", "gate-decision-1-2.json")
    write_named_slim(tmp_path, "gate-decision-1-2.json", "PASS")
    (tmp_path / "nfr-assessment-1-2.md").write_text(
        "**Overall Status:** PASS\n", encoding="utf-8"
    )

    result = run_gate(tmp_path, profile="light", story="1-2")
    assert result["gate_status"] == "PASS"
    assert any("gate-decision-1-2.json" in r for r in result["reasons"])


def test_an_undeclared_trace_report_no_longer_suppresses_fail_closed(tmp_path):
    """A `trace-<id>.md` with no workflowType contributes no hint either way.

    gate.md says such a report "is skipped", and the hint loop already skips it -
    so before this change it could suppress the fail-closed branch while being
    unable to resolve anything, which is the worst of both.
    """
    write_trace_report(tmp_path, "trace-9-1.md", "gate-decision-9-1.json")
    write_named_slim(tmp_path, "gate-decision-9-1.json", "PASS")
    (tmp_path / "trace-9-2.md").write_text("# no frontmatter at all\n", encoding="utf-8")
    # The generic summary is what an un-narrowed resolver falls through TO. Without
    # it the story reaches NOT_EVALUATED by a different route and the test passes
    # either way, discriminating nothing.
    (tmp_path / "e2e-trace-summary.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )

    result = run_gate(tmp_path, profile="light", story="9-2")
    assert result["gate_status"] == "NOT_EVALUATED"
    assert result["verdict"] == "escalate"


@pytest.mark.parametrize(
    "stem,named",
    [
        ("trace-2-1", True),
        ("gate-decision-4", True),
        # The shapes the ORIGINAL last-component-is-numeric rule called generic.
        # Every one of them is what this module writes once a story is split or
        # slugged, which is the normal case in any real epic.
        ("trace-92-0a", True),
        ("trace-5-8-some-slug", True),
        ("gate-decision-92-7f-the-departure-record", True),
        ("nfr-assessment-1-2", True),
        # Genuinely generic: the single-story dir whose unscoped fallback is
        # documented and must keep working.
        ("trace", False),
        ("gate-decision", False),
        ("e2e-trace-summary", False),
        # Not one of ours at all. Its first component is `traceability`, not
        # `trace`, so the prefix must not match on a substring.
        ("traceability-matrix", False),
    ],
)
def test_a_stem_is_named_for_a_story_by_structure_not_by_a_numeric_tail(stem, named):
    assert gate_eval_module._has_trailing_id(stem) is named


def test_an_artifact_less_story_cannot_advance_on_a_slugged_neighbours_gate(tmp_path):
    """The fail-closed branch must fire in a directory of SLUGGED per-story names.

    `_is_per_story_named` is the discriminator that switches fail-closed on. It
    asked whether a stem's last component is numeric, which is false for every
    slugged or alpha-suffixed id - so a directory full of real per-story
    artifacts reported itself generic, the branch never fired, and an
    artifact-less story resolved a neighbour's gate.

    Measured before the fix: `--story 92-7f-never-driven` against a directory
    holding only 92-0a's artifacts returned PASS. That story wrote nothing.
    """
    write_trace_report(tmp_path, "trace-92-0a-alpha.md", "gate-decision-92-0a-alpha.json")
    write_named_slim(tmp_path, "gate-decision-92-0a-alpha.json", "PASS")

    result = run_gate(tmp_path, profile="light", story="92-7f-never-driven")
    assert result["gate_status"] == "NOT_EVALUATED"
    assert result["verdict"] == "escalate"
    assert not any("92-0a" in r for r in result["reasons"]), "resolved a neighbour's gate"


def test_production_nfr_not_assessed_downgrades_advance_to_reloop(tmp_path):
    """`NOT_ASSESSED` means the NFRs were never evaluated, so it must fail the AND.

    It is in `_scan_nfr_overall_status`'s alternation, so it parses cleanly and
    never reaches the "status not found" branch. It therefore used to read as
    "present and not FAIL" and PASS the production AND, advancing a story on an
    NFR audit that had assessed nothing -- while an *unreadable* NFR file failed
    closed. The two are now consistent.
    """
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    review = tmp_path / "test-review.md"
    write_nfr(nfr, "NOT_ASSESSED")
    write_review(review, 92, "Approve")

    result = run_gate(tmp_path, profile="production", nfr=nfr, test_review=review)

    assert result["verdict"] == "reloop"
    assert result["nfr_status"] == "NOT_ASSESSED"
    assert any("NOT_ASSESSED" in r for r in result["reasons"]), result["reasons"]


def test_production_nfr_not_assessed_is_inert_under_light(tmp_path):
    """Control on the profile axis: `--light` runs no ANDs, so the same artifact
    still advances there. Without this, the test above would also pass on a
    build that had simply broken the light profile."""
    write_slim(tmp_path, "PASS")
    nfr = tmp_path / "nfr-assessment.md"
    write_nfr(nfr, "NOT_ASSESSED")

    result = run_gate(tmp_path, profile="light")

    assert result["verdict"] == "advance"


# ---------------------------------------------------------------------------
# The last-resort fall-through.
#
# The fail-closed `return None` in `_resolve_gate_file` is guarded by `elif`, so
# it is reachable only when `scoped` is EMPTY. A story that authored a DECLARED
# trace report but no resolvable gate file skipped it entirely and was handed the
# directory's UNSCOPED gate-decision.json -- a neighbour's verdict -- or, one file
# along, the shared e2e-trace-summary.json.
# ---------------------------------------------------------------------------


def _declared_trace(d, story, hint=None):
    fm = "---\nworkflowType: testarch-trace\n"
    if hint:
        fm += "gateDecisionFile: %s\n" % hint
    fm += "---\n# trace\n"
    (d / ("trace-%s.md" % story)).write_text(fm, encoding="utf-8")


def _per_story_slim(d, story, status):
    (d / ("gate-decision-%s.json" % story)).write_text(
        json.dumps({"gate_status": status, "p0_status": "MET",
                    "p1_status": "MET", "overall_status": "MET"}),
        encoding="utf-8",
    )


def test_story_with_a_trace_report_but_no_gate_file_fails_closed(tmp_path):
    """A declared trace report must not buy a pass out of the fail-closed lane."""
    _declared_trace(tmp_path, "4-1")            # neighbour, fully evaluated
    _per_story_slim(tmp_path, "4-1", "PASS")
    _declared_trace(tmp_path, "4-2")            # this story: report, no gate file
    write_slim(tmp_path, "PASS")                # the UNSCOPED file it used to grab

    result = run_gate(tmp_path, profile="light", story="4-2")

    assert result["gate_status"] == "NOT_EVALUATED"
    assert result["verdict"] == "escalate"
    assert any("4-2" in r for r in result["reasons"]), result["reasons"]


def test_story_with_a_trace_report_does_not_inherit_the_shared_summary(tmp_path):
    """One file along, the generic summary is the same unscoped read."""
    _declared_trace(tmp_path, "4-1")
    _per_story_slim(tmp_path, "4-1", "PASS")
    _declared_trace(tmp_path, "4-2")
    write_summary(tmp_path, "PASS")             # shared, belongs to no story

    result = run_gate(tmp_path, profile="light", story="4-2")

    assert result["gate_status"] == "NOT_EVALUATED"
    assert result["verdict"] == "escalate"


def test_story_with_its_own_gate_file_still_resolves(tmp_path):
    """Control: the narrowing must not break the ordinary per-story read."""
    _declared_trace(tmp_path, "4-1")
    _per_story_slim(tmp_path, "4-1", "PASS")
    _declared_trace(tmp_path, "4-2")
    _per_story_slim(tmp_path, "4-2", "CONCERNS")

    result = run_gate(tmp_path, profile="light", story="4-2")

    assert result["gate_status"] == "CONCERNS"
    assert result["verdict"] == "defer"


def test_single_story_generic_dir_still_uses_the_unscoped_fallback(tmp_path):
    """Control: the documented single-story shape is unchanged.

    `references/gate.md` sanctions an isolated directory whose artifacts carry no
    id; passing `--story` there must resolve exactly as before.
    """
    (tmp_path / "trace.md").write_text(
        "---\nworkflowType: testarch-trace\n---\n# trace\n", encoding="utf-8"
    )
    write_slim(tmp_path, "PASS")

    result = run_gate(tmp_path, profile="light", story="4-2")

    assert result["gate_status"] == "PASS"
    assert result["verdict"] == "advance"
