"""Story 2.7 — formalize_check.py as a READER of TEA's emitted fields (AD-6).

AC-3: blank-cell-ONLY P×I recompute (mechanical) vs a stated-score disagreement (judgment)
vs an unsourced threshold (judgment), never originating a number. AC-4: read TEA's NFR
overallStatus (never re-derive), flag PASS-on-UNKNOWN and PASS-without-evidence as judgment
candidates, and treat a missing/unreadable nfr-assessment as a FAILING gap (fail-closed, INV-4).

Fixtures are built programmatically in tmp_path (hermetic; not linted). The TEA-reader fires
only when a test-design artifact is located under the trace_output root.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "formalize_check.py"


def _build(root: Path, *, epic: str, test_design: str | None, nfr: str | None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "planning-artifacts").mkdir()
    (root / "impl-artifacts").mkdir()
    (root / "tea").mkdir()
    trace = root / "trace_out"
    trace.mkdir()
    (root / "tea" / "config.yaml").write_text("trace_output: {project-root}/trace_out\n", encoding="utf-8")
    if test_design is not None:
        (trace / f"test-design-epic-{epic}.md").write_text(test_design, encoding="utf-8")
    if nfr is not None:
        (trace / "nfr-assessment.md").write_text(nfr, encoding="utf-8")
    (root / "planning-artifacts" / "prd-fixture.md").write_text("# PRD\n", encoding="utf-8")
    (root / "planning-artifacts" / "architecture-fixture.md").write_text("# Architecture\n", encoding="utf-8")
    (root / "impl-artifacts" / "sprint-status.yaml").write_text(
        f"development_status:\n  epic-{epic}: in-progress\n  {epic}-1-x: backlog\n", encoding="utf-8"
    )
    return root


def _verdict(root: Path, epic: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--epic", epic, "--project-root", str(root),
         "--planning-artifacts", str(root / "planning-artifacts"),
         "--impl-artifacts", str(root / "impl-artifacts"),
         "--tea-config", str(root / "tea" / "config.yaml")],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _kinds(items: list[dict]) -> list[str]:
    return [str(i.get("kind")) for i in items]


_RISK_HEADER = "| Risk ID | Category | P | I | Score | Mitigation |\n|--|--|--|--|--|--|\n"


# AC-3 -----------------------------------------------------------------------
def test_blank_only_pxi_and_judgment_routing(tmp_path):
    # (a) blank Score with stated P=3,I=2 -> MECHANICAL gap, recompute 6
    td_a = _RISK_HEADER + "| TECH-1 | TECH | 3 | 2 |  | retry |\n"
    out = _verdict(_build(tmp_path / "a", epic="40", test_design=td_a, nfr=None), "40")
    blank = [g for g in out["mechanical_gaps"] if g["kind"] == "blank_pxi_score"]
    assert len(blank) == 1 and blank[0]["remediable"] is True and blank[0]["recomputed"] == 6
    assert "risk_score_conflict" not in _kinds(out["judgment_candidates"])

    # (b) stated Score disagreeing with stated P,I -> JUDGMENT, never overwritten
    td_b = _RISK_HEADER + "| TECH-2 | TECH | 2 | 2 | 5 | validate |\n"
    out = _verdict(_build(tmp_path / "b", epic="41", test_design=td_b, nfr=None), "41")
    assert "risk_score_conflict" in _kinds(out["judgment_candidates"])
    assert "blank_pxi_score" not in _kinds(out["mechanical_gaps"])

    # (c) unsourced NFR threshold -> JUDGMENT (invented-threshold), never a filled cell
    td_c = _RISK_HEADER + "| TECH-3 | TECH | 1 | 1 | 1 | x |\n\nLatency budget: 200 ms.\n"
    out = _verdict(_build(tmp_path / "c", epic="42", test_design=td_c, nfr=None), "42")
    assert "invented_nfr_threshold" in _kinds(out["judgment_candidates"])

    # anti-vacuous: a consistent populated Score yields NEITHER finding for that cell
    td_ok = _RISK_HEADER + "| TECH-4 | TECH | 2 | 2 | 4 | x |\n"
    out = _verdict(_build(tmp_path / "ok", epic="43", test_design=td_ok, nfr=None), "43")
    assert "blank_pxi_score" not in _kinds(out["mechanical_gaps"])
    assert "risk_score_conflict" not in _kinds(out["judgment_candidates"])


# AC-4 -----------------------------------------------------------------------
_NFR_HEADER = "Overall Status: CONCERNS\n\n| Category | Status | Threshold | Evidence |\n|--|--|--|--|\n"
_CLEAN_TD = _RISK_HEADER + "| T-1 | TECH | 2 | 2 | 4 | x |\n"


def test_nfr_reader_unknown_to_concerns_and_failclosed(tmp_path):
    # PASS asserted on an UNKNOWN threshold -> judgment_candidate
    nfr_unknown = _NFR_HEADER + "| latency | PASS | UNKNOWN | bench |\n"
    out = _verdict(_build(tmp_path / "u", epic="50", test_design=_CLEAN_TD, nfr=nfr_unknown), "50")
    assert "nfr_pass_on_unknown" in _kinds(out["judgment_candidates"])

    # PASS asserted with no named evidence source -> judgment_candidate
    nfr_noevd = _NFR_HEADER + "| security | PASS | strong | none |\n"
    out = _verdict(_build(tmp_path / "n", epic="51", test_design=_CLEAN_TD, nfr=nfr_noevd), "51")
    assert "nfr_pass_without_evidence" in _kinds(out["judgment_candidates"])

    # missing nfr-assessment (test-design present) -> FAILING gap, fail-closed
    out = _verdict(_build(tmp_path / "m", epic="52", test_design=_CLEAN_TD, nfr=None), "52")
    miss = [g for g in out["mechanical_gaps"] if g["kind"] == "missing_nfr_assessment"]
    assert len(miss) == 1 and miss[0]["remediable"] is False, "missing nfr is a failing (non-neutral) gap"

    # anti-vacuous: a well-formed nfr (PASS cites evidence; UNKNOWN marked CONCERNS) -> zero nfr candidates
    nfr_ok = (
        _NFR_HEADER
        + "| latency | CONCERNS | UNKNOWN | not measured |\n"
        + "| security | PASS | TLS1.3 | test_tls.py:12 |\n"
    )
    out = _verdict(_build(tmp_path / "w", epic="53", test_design=_CLEAN_TD, nfr=nfr_ok), "53")
    nfr_kinds = {"nfr_pass_on_unknown", "nfr_pass_without_evidence", "missing_nfr_assessment", "nfr_overall_status_unreadable"}
    assert not (set(_kinds(out["judgment_candidates"])) & nfr_kinds)
    assert "missing_nfr_assessment" not in _kinds(out["mechanical_gaps"])

    # the kernel never ORIGINATES an overallStatus on its emitted surface
    assert "overallStatus" not in out and "overall_status" not in out
    assert "overallStatus" not in out.get("checks", {})
