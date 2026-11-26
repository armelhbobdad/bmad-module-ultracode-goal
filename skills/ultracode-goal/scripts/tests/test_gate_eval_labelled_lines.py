#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""`gate_eval.py` reads a review's own labelled score, recommendation and NFR status.

The three production-signal scanners took the first match anywhere in the file,
so a review that quoted an earlier score, an earlier Approve or an earlier
status above its own result was judged on the quoted value: a review scoring
its own tests 62 that opened by quoting a previous 91 advanced the story.

TEA writes each signal on a line of its own (`**Quality Score**: 85/100`,
`**Recommendation**: Approve` twice with one value, and the NFR audit's
`**Overall Status:** PASS` near the top and `- Overall Status: PASS` at its
sign-off). The scanners now read those labelled lines first:

- one distinct Quality Score is the score; two or more fail the signal, with a
  reason naming them, and `review_score` prints null;
- Block on any labelled Recommendation line is Block;
- the NFR status is the most severe labelled value (FAIL, NOT_ASSESSED,
  CONCERNS, PASS);
- a file with no labelled line is read by the old regexes, unchanged, and each
  scanner falls back on its own;
- when the labelled Recommendations or NFR statuses disagree, a reason says so
  beside the status one;
- a labelled line may open with a byte-order mark, and CRLF line ends read as
  LF ones.

Each rule has a twin that runs the same text through a mutant of the script with
the rule taken out and shows the wrong reading come back, or that shows the old
first-match reading of the same text is the wrong one. The leading marks and the
label separator are one character class each; a time-bound test reads a long run
of each of their characters in a child process, under a CPU-time bound and a
wall-clock timeout, and its twins show a nested, a doubled or a one-mark repeat
never finishing.

Run: uv run --with pytest pytest scripts/tests/test_gate_eval_labelled_lines.py
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "gate_eval.py"
STORY = "61-1-sample-story"

# The printed key set of a per-story production gate with no conditional flag
# (docs/_internal/STABILITY.md). The fix changes no key.
_KEYS = {
    "verdict", "gate_status", "p0_status", "p1_status", "overall_status",
    "nfr_status", "review_score", "epic_level", "reasons",
}

# The readers as they were before labelled lines: the first match anywhere in
# the file. They are the fallback now, kept verbatim, so they are also pinned
# against the script's source below.
_FIRST_MATCH_SCORE = r"(?:Quality\s+Score|score)[*:_\s]*[`*]*\s*(\d{1,3})\s*/\s*100"
_FIRST_MATCH_RECOMMENDATION = (
    r"Recommendation[*:_\s]*[`*]*\s*"
    r"(Approve with Comments|Approve|Request Changes|Block)"
)
_FIRST_MATCH_NFR = (
    r"(?:Overall\s+Status|overallStatus)[*:_\s]*[`*]*\s*(PASS|CONCERNS|FAIL|NOT_ASSESSED)"
)

# Most severe first, the order gate_eval.py reads them in: FAIL and NOT_ASSESSED
# fail the production AND, CONCERNS and PASS do not.
_SEVERITY = ("FAIL", "NOT_ASSESSED", "CONCERNS", "PASS")


def _first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1) if match else None


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


gate_eval = _load(SCRIPT, "gate_eval_labelled_under_test")


def _write_mutant(tmp_path: Path, name: str, *pairs: tuple[str, str]) -> Path:
    """Copy the shipped script with each (old, new) replacement applied once."""
    src = SCRIPT.read_text(encoding="utf-8")
    for index, (old, new) in enumerate(pairs):
        assert old in src, f"mutation anchor {index} drifted out of gate_eval.py: {name}"
        src = src.replace(old, new, 1)
    path = tmp_path / f"mutant_{name}.py"
    path.write_text(src, encoding="utf-8")
    return path


def _mutant(tmp_path: Path, name: str, *pairs: tuple[str, str]):
    return _load(_write_mutant(tmp_path, name, *pairs), f"gate_eval_mutant_{name}")


# --- The rules, as the mutation anchors that take each one out ---------------

_SCORE_LABELLED_STEP = (
    "    scores = _labelled_review_scores(text)\n"
    "    if scores:\n"
    "        return scores[0] if len(scores) == 1 else None\n"
)
_RECOMMENDATION_LABELLED_STEP = (
    "    labelled = _labelled_review_recommendations(text)\n"
    "    if labelled:\n"
    '        return next((value for value in labelled if value.lower() == "block"), labelled[0])\n'
)
_NFR_LABELLED_STEP = (
    "    labelled = _labelled_nfr_statuses(text)\n"
    "    if labelled:\n"
    "        return next(status for status in _NFR_SEVERITY if status in labelled)\n"
)
# Two distinct scores read as the first one, and their reason is never written.
_NO_DISTINCT_RULE = (
    ("        return scores[0] if len(scores) == 1 else None\n", "        return scores[0]\n"),
    ("            if len(scores) > 1:\n", "            if False:\n"),
)
# The first labelled Recommendation, Block or not.
_NO_ANY_BLOCK_RULE = (
    '        return next((value for value in labelled if value.lower() == "block"), labelled[0])\n',
    "        return labelled[0]\n",
)
# The first labelled NFR status, however mild.
_NO_MOST_SEVERE_RULE = (
    "        return next(status for status in _NFR_SEVERITY if status in labelled)\n",
    "        return labelled[0]\n",
)
# Labelled lines only: a file without one reads as no signal at all.
_NO_FALLBACK = (
    (
        "    if scores:\n        return scores[0] if len(scores) == 1 else None\n",
        "    return scores[0] if len(scores) == 1 else None\n",
    ),
    (
        "    if labelled:\n"
        '        return next((value for value in labelled if value.lower() == "block"), labelled[0])\n',
        '    return next((value for value in labelled if value.lower() == "block"), labelled[0] if labelled else None)\n',
    ),
    (
        "    if labelled:\n        return next(status for status in _NFR_SEVERITY if status in labelled)\n",
        "    return next((status for status in _NFR_SEVERITY if status in labelled), None)\n",
    ),
)
# No reason says that the labelled Recommendations or NFR statuses disagree.
_NO_DISAGREEMENT_REASONS = (
    (
        "        if nfr_text is not None and len(statuses := _labelled_nfr_statuses(nfr_text)) > 1:\n",
        "        if False:\n",
    ),
    ("            if len(recommendations) > 1:\n", "            if False:\n"),
)
# The leading marks as shipped, which the mark twins below take a character from.
_LINE_MARKS_SRC = '_LINE_MARKS = r"^\\ufeff?[ \\t>#*_+\\-0-9.)]*"'


# --- TEA's own shapes ---------------------------------------------------------


def _tea_review(score: int, recommendation: str, *, raw: int | None = None, preface: str = "") -> str:
    """A filled test review in the shape of TEA 1.27.2's test-review-template.md.

    It keeps every line of the template that carries another score or the word
    Recommendation: the raw score and its cap, the breakdown ledger, the
    Recommendations heading, the Decision copy of the recommendation, the
    per-recommendation quotes and the trend and related-review tables.
    """
    raw = score + 4 if raw is None else raw
    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D"
    return f"""---
stepsCompleted: ['step-01-load-context', 'step-04-generate-report']
lastStep: 'step-04-generate-report'
lastSaved: '2026-11-26'
workflowType: 'testarch-test-review'
inputDocuments: []
---
{preface}
# Test Quality Review: sample.spec.ts

**Quality Score**: {score}/100 ({grade} - Good)
**Raw Deduction Score**: {raw}/100
**Score Cap**: {score}/100
**Score Override Rule**: highest finding severity caps the raw score
**Review Date**: 2026-11-26
**Review Scope**: single
**Reviewer**: TEA Agent

---

## Executive Summary

**Overall Assessment**: Good

**Recommendation**: {recommendation}
**Verdict Rule**: computed from the deduped violation counts

**Context Basis**: pr_diff

**Context Waivers Applied**: 0

**Execution Mode**: subagent

### Key Weaknesses

- [M4] a fixture is shared across tests

---

## Quality Score Breakdown

```text
Starting Score:          100
Critical Violations:     -0 x 10 = -0
High Violations:         -1 x 5 = -5
Medium Violations:       -3 x 2 = -6
Low Violations:          -0 x 1 = -0

Total Bonus:             +5

Raw Deduction Score:     {raw}/100
Score Cap:               {score}/100 (High)
Effective Score:         {score}/100
Grade:                   {grade}
```

## Recommendations (Should Fix)

### 1. Give each test its own fixture

## Decision

**Recommendation**: {recommendation}

**Rationale**:
The findings above decide it.

**For Approve**:

> Test quality is excellent/good with {score}/100 score.

**For Block**:

> Test quality is insufficient with {score}/100 score.

## Appendix

### Quality Trends

| Review Date | Score  | Grade | Critical Issues | Trend    |
| ----------- | ------ | ----- | --------------- | -------- |
| 2026-11-20  | 91/100 | A     | 0               | Improved |
| 2026-11-26  | {score}/100 | {grade} | 0          | Declined |

### Related Reviews

| File          | Score  | Grade | Critical | Status   |
| ------------- | ------ | ----- | -------- | -------- |
| other.spec.ts | 95/100 | A     | 0        | Approved |

**Suite Average**: 77/100 (C)
"""


def _tea_nfr(status: str, *, signoff: str | None = None, preface: str = "") -> str:
    """A filled NFR audit in the shape of TEA 1.27.2's nfr-report-template.md.

    The status sits near the top and again at the sign-off (`signoff` lets the
    two copies disagree); the findings table, the domain statuses and the gate
    YAML's `overall_status` are kept, since each carries a status word.
    """
    signoff = status if signoff is None else signoff
    return f"""---
stepsCompleted: ['step-01-load-context', 'step-05-generate-report']
workflowType: 'testarch-nfr-assess'
inputDocuments: []
---

# NFR Evidence Audit - Sample Feature

**Date:** 2026-11-26
**Story:** {STORY} (if applicable)
{preface}**Overall Status:** {status} ✅

---

## Executive Summary

**Assessment:** 3 PASS, 1 CONCERNS, 0 FAIL

**Blockers:** 0 none

**Recommendation:** proceed to trace

---

## Performance Assessment

### Response Time (p95)

- **Status:** CONCERNS
- **Threshold:** 200ms

## Findings Summary

| Category                    | Criteria Met | PASS | CONCERNS | FAIL | Overall Status |
| --------------------------- | ------------ | ---- | -------- | ---- | -------------- |
| 1. Testability & Automation | 4/4          | 4    | 0        | 0    | PASS           |
| **Total**                   | **26/29**    | **25** | **1**  | **0** | **{status}**  |

## Gate YAML Snippet

```yaml
nfr_assessment:
  story_id: '{STORY}'
  overall_status: '{status}'
```

## Sign-Off

**NFR Evidence Audit:**

- Overall Status: {signoff} ✅
- Critical Issues: 0

**Gate Status:** PASS
"""


def _write(path: Path, content: str | bytes) -> None:
    # Bytes are written as given, so a CRLF file keeps its line ends on any OS.
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _story_tree(
    tmp_path: Path, review_text: str | bytes, nfr_text: str | bytes
) -> tuple[Path, Path, Path, Path]:
    trace = tmp_path / "test-artifacts"
    trace.mkdir()
    (trace / f"gate-decision-{STORY}.json").write_text(
        json.dumps({"schema_version": "0.1.0", "gate_status": "PASS", "p0_status": "MET",
                    "p1_status": "MET", "overall_status": "MET"}),
        encoding="utf-8",
    )
    review = trace / "test-review.md"
    _write(review, review_text)
    nfr = trace / "nfr-assessment.md"
    _write(nfr, nfr_text)
    marker = trace / f".tests-ran-{STORY}"
    marker.write_text("baseline=0123abc\nscope=full\n", encoding="utf-8")
    return trace, review, nfr, marker


def _run(script: Path, tmp_path: Path, review_text: str | bytes, nfr_text: str | bytes) -> dict:
    trace, review, nfr, marker = _story_tree(tmp_path, review_text, nfr_text)
    proc = subprocess.run(
        [sys.executable, str(script), "--trace-output", str(trace), "--profile", "production",
         "--story", STORY, "--nfr", str(nfr), "--test-review", str(review),
         "--tests-ran", str(marker)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _readings(module, text: str) -> tuple:
    return (
        module._scan_review_score(text),
        module._scan_review_recommendation(text),
        module._scan_nfr_overall_status(text),
    )


# --- The fallback is today's reader, unchanged --------------------------------


def test_the_fallback_regexes_are_the_old_readers_verbatim():
    source = SCRIPT.read_text(encoding="utf-8")
    assert _FIRST_MATCH_SCORE in source
    assert "".join(
        ['r"Recommendation[*:_\\s]*[`*]*\\s*"\n', '        r"(Approve with Comments|Approve|Request Changes|Block)"']
    ) in source
    assert _FIRST_MATCH_NFR in source


# --- TEA's stock forms read as before -----------------------------------------


@pytest.mark.parametrize(
    "score,recommendation,verdict",
    [
        (92, "Approve", "advance"),
        (85, "Approve with Comments", "advance"),
        (80, "Approve with Comments", "advance"),
        (79, "Request Changes", "reloop"),
        (88, "Block", "reloop"),
    ],
)
def test_a_stock_tea_review_reads_as_before(tmp_path, score, recommendation, verdict):
    text = _tea_review(score, recommendation)
    assert gate_eval._scan_review_score(text) == score
    assert gate_eval._scan_review_recommendation(text) == recommendation
    # As before: the first match anywhere read the same values from this shape.
    assert int(_first_match(_FIRST_MATCH_SCORE, text)) == score
    assert _first_match(_FIRST_MATCH_RECOMMENDATION, text) == recommendation

    result = _run(SCRIPT, tmp_path, text, _tea_nfr("PASS"))
    assert result["verdict"] == verdict
    assert result["review_score"] == score
    assert set(result) == _KEYS | {"sweep_scope"}
    # TEA writes the Recommendation twice with one value: no disagreement.
    assert not any("holds more than one" in r for r in result["reasons"])


@pytest.mark.parametrize("status,verdict", [("PASS", "advance"), ("CONCERNS", "advance"), ("FAIL", "reloop")])
def test_a_stock_tea_nfr_audit_reads_as_before(tmp_path, status, verdict):
    text = _tea_nfr(status)
    assert gate_eval._scan_nfr_overall_status(text) == status
    assert _first_match(_FIRST_MATCH_NFR, text).upper() == status

    result = _run(SCRIPT, tmp_path, _tea_review(90, "Approve"), text)
    assert result["verdict"] == verdict
    assert result["nfr_status"] == status
    assert not any("holds more than one" in r for r in result["reasons"])


def test_the_same_score_on_two_labelled_lines_is_one_score():
    text = _tea_review(84, "Approve with Comments") + "\n**Quality Score**: 84/100\n"
    assert gate_eval._labelled_review_scores(text) == [84]
    assert gate_eval._scan_review_score(text) == 84


@pytest.mark.parametrize(
    "line",
    [
        "**Quality Score**: 85/100",
        "Quality Score: 85/100",
        "- **Quality Score:** 85/100",
        "> **Quality Score**: 85/100",
        "### Quality Score: 85 / 100",
        "1. Quality Score: 85/100",
        "   __Quality Score__ `85/100`",
        "quality score: 85/100",
        "+ Quality Score: 85/100",
        "\tQuality Score: 85/100",
        "1) Quality Score: 85/100",
        "\ufeff**Quality Score**: 85/100",
    ],
)
def test_a_labelled_line_opens_with_its_label(line):
    assert gate_eval._labelled_review_scores(line + "\n") == [85]


@pytest.mark.parametrize(
    "line,first_match",
    [
        ("## Quality Score Breakdown", None),
        ("| 2026-11-20 | Quality Score: 91/100 |", "91"),
        ("The earlier review gave a Quality Score of 91/100.", None),
        ("Earlier: Quality Score: 91/100", "91"),
        ("**Quality Score**:\n91/100", "91"),
        ("Raw Deduction Score: 91/100", "91"),
        ("score: 91/100", "91"),
        ("**Quality\nScore**: 91/100", "91"),
        ("**Quality Score**: 91\n/100", "91"),
    ],
)
def test_a_line_that_does_not_open_with_the_label_and_its_value_is_not_labelled(line, first_match):
    assert gate_eval._labelled_review_scores(line + "\n") == []
    # The old reader takes most of these, so it is the line rule that leaves
    # them out, not the value form.
    assert _first_match(_FIRST_MATCH_SCORE, line) == first_match


# Each character the leading marks take has a line that needs it, and a twin
# that takes the character out and finds that line no longer labelled.
@pytest.mark.parametrize(
    "name,line,marks_without",
    [
        ("plus", "+ Quality Score: 85/100", '_LINE_MARKS = r"^\\ufeff?[ \\t>#*_\\-0-9.)]*"'),
        ("tab", "\t**Quality Score**: 85/100", '_LINE_MARKS = r"^\\ufeff?[ >#*_+\\-0-9.)]*"'),
        ("paren", "1) Quality Score: 85/100", '_LINE_MARKS = r"^\\ufeff?[ \\t>#*_+\\-0-9.]*"'),
        ("bom", "\ufeff**Quality Score**: 85/100", '_LINE_MARKS = r"^[ \\t>#*_+\\-0-9.)]*"'),
    ],
)
def test_twin_without_its_mark_the_line_is_not_labelled(tmp_path, name, line, marks_without):
    assert gate_eval._labelled_review_scores(line + "\n") == [85]
    mutant = _mutant(tmp_path, f"no_mark_{name}", (_LINE_MARKS_SRC, marks_without))
    assert mutant._labelled_review_scores(line + "\n") == []


# Neither the label, the separator nor the value crosses a line end; each twin
# lets one of them cross and finds a split line labelled.
@pytest.mark.parametrize(
    "name,line,crossing",
    [
        ("label", "**Quality\nScore**: 91/100", ('r"Quality[ \\t]+Score"', 'r"Quality\\s+Score"')),
        ("separator", "**Quality Score**:\n91/100", ('_LABEL_SEP = r"[*:_` \\t]*"', '_LABEL_SEP = r"[*:_`\\s]*"')),
        (
            "value",
            "**Quality Score**: 91\n/100",
            ('r"(\\d{1,3})[ \\t]*/[ \\t]*100"', 'r"(\\d{1,3})\\s*/\\s*100"'),
        ),
    ],
)
def test_twin_a_line_end_inside_the_label_or_value_would_be_crossed(tmp_path, name, line, crossing):
    assert gate_eval._labelled_review_scores(line + "\n") == []
    mutant = _mutant(tmp_path, f"crosses_{name}", crossing)
    assert mutant._labelled_review_scores(line + "\n") == [91]


# --- Case, the overallStatus key, a byte-order mark and CRLF line ends ----------

# The review's own lowercase lines above a quoted earlier cycle in TEA's case.
_LOWERCASE_REVIEW = (
    "quality score: 62/100\n"
    "recommendation: block\n"
    "\n"
    "> **Quality Score**: 91/100 (previous cycle)\n"
    "> **Recommendation**: Approve (previous cycle)\n"
)
_LOWERCASE_NFR = "overall status: fail\n\n- Overall Status: PASS (the audit before the cache change)\n"
# A lowercase Block below a quoted earlier Approve.
_LOWERCASE_BLOCK_BELOW = "> **Recommendation**: Approve (previous cycle)\n\nrecommendation: block\n"


def test_a_lowercase_label_and_value_are_labelled(tmp_path):
    assert gate_eval._labelled_review_scores(_LOWERCASE_REVIEW) == [62, 91]
    assert gate_eval._scan_review_score(_LOWERCASE_REVIEW) is None
    assert gate_eval._scan_review_recommendation(_LOWERCASE_REVIEW) == "block"
    assert gate_eval._scan_review_recommendation(_LOWERCASE_BLOCK_BELOW) == "block"
    assert gate_eval._scan_nfr_overall_status(_LOWERCASE_NFR) == "FAIL"
    # A lowercase status alone reads upper-cased, as the fallback's does.
    assert gate_eval._scan_nfr_overall_status("overall status: fail\n") == "FAIL"

    result = _run(SCRIPT, tmp_path, _LOWERCASE_REVIEW, _LOWERCASE_NFR)
    assert result["verdict"] == "reloop"
    assert result["review_score"] is None
    assert result["nfr_status"] == "FAIL"
    assert "test-review recommendation is Block" in result["reasons"]


def test_twin_case_sensitive_labelled_lines_read_the_quoted_values(tmp_path):
    mutant = _mutant(
        tmp_path, "case_sensitive",
        ("_LABELLED_FLAGS = re.IGNORECASE | re.MULTILINE", "_LABELLED_FLAGS = re.MULTILINE"),
    )
    assert _readings(mutant, _LOWERCASE_REVIEW)[:2] == (91, "Approve")
    assert mutant._scan_nfr_overall_status(_LOWERCASE_NFR) == "PASS"


def test_twin_a_case_sensitive_block_misses_a_lowercase_one(tmp_path):
    mutant = _mutant(
        tmp_path, "block_case_sensitive",
        (
            '        return next((value for value in labelled if value.lower() == "block"), labelled[0])\n',
            '        return next((value for value in labelled if value == "Block"), labelled[0])\n',
        ),
    )
    assert mutant._scan_review_recommendation(_LOWERCASE_BLOCK_BELOW) == "Approve"


# A hand-written audit that keeps its own status in frontmatter, under the key
# references/gate.md allows, and quotes the last audit in its body.
_CAMEL_NFR = (
    "---\noverallStatus: FAIL\n---\n\n# NFR notes for the sample feature\n\n"
    "- Overall Status: PASS (the audit before the cache change)\n"
)


def test_the_overallstatus_key_is_a_label():
    assert gate_eval._labelled_nfr_statuses(_CAMEL_NFR) == ["FAIL", "PASS"]
    assert gate_eval._scan_nfr_overall_status(_CAMEL_NFR) == "FAIL"


def test_twin_without_the_overallstatus_label_the_quoted_pass_is_read(tmp_path):
    mutant = _mutant(
        tmp_path, "no_camel_label",
        ('r"(?:Overall[ \\t]+Status|overallStatus)"', 'r"(?:Overall[ \\t]+Status)"'),
    )
    assert mutant._scan_nfr_overall_status(_CAMEL_NFR) == "PASS"


# A review and an audit in the shape references/gate.md gives for a hand-written
# file, whose own value sits on line 1 behind a byte-order mark, above a quoted
# earlier value. TEA's own files open with frontmatter instead.
_BOM_REVIEW = (
    "\ufeff**Quality Score**: 62/100\n**Recommendation**: Request Changes\n\n"
    "> **Quality Score**: 91/100 (previous cycle)\n"
)
_BOM_NFR = (
    "\ufeff**Overall Status:** FAIL\n\n## History\n\n"
    "- Overall Status: PASS (the audit before the cache change)\n"
)


def test_a_byte_order_mark_does_not_hide_the_first_line(tmp_path):
    assert gate_eval._labelled_review_scores(_BOM_REVIEW) == [62, 91]
    assert gate_eval._scan_nfr_overall_status(_BOM_NFR) == "FAIL"

    result = _run(SCRIPT, tmp_path, _BOM_REVIEW, _BOM_NFR)
    # The files carry the mark, and the script's UTF-8 read keeps it.
    assert (tmp_path / "test-artifacts" / "test-review.md").read_bytes().startswith(b"\xef\xbb\xbf")
    assert result["verdict"] == "reloop"
    assert result["review_score"] is None
    assert result["nfr_status"] == "FAIL"
    assert any("more than one Quality Score (62/100, 91/100)" in r for r in result["reasons"])
    assert "nfr overallStatus is FAIL" in result["reasons"]


def test_twin_without_the_byte_order_mark_the_quoted_values_advance(tmp_path):
    mutant = _write_mutant(tmp_path, "no_bom", (_LINE_MARKS_SRC, '_LINE_MARKS = r"^[ \\t>#*_+\\-0-9.)]*"'))
    result = _run(mutant, tmp_path, _BOM_REVIEW, _BOM_NFR)
    assert result["verdict"] == "advance"
    assert result["review_score"] == 91
    assert result["nfr_status"] == "PASS"


_CRLF_REVIEW = _tea_review(
    62, "Block",
    preface="\n> **Quality Score**: 91/100 (previous cycle)\n> **Recommendation**: Approve (previous cycle)\n",
)
_CRLF_NFR = _tea_nfr("FAIL", preface="> Overall Status: PASS (the audit before the cache change)\n\n")


def _crlf(text: str) -> str:
    return text.replace("\n", "\r\n")


def test_crlf_line_ends_read_as_lf_ones(tmp_path):
    # Straight through the scanners, each line still ending in a carriage return.
    assert gate_eval._labelled_review_scores(_crlf(_CRLF_REVIEW)) == [91, 62]
    assert gate_eval._scan_review_recommendation(_crlf(_CRLF_REVIEW)) == "Block"
    assert gate_eval._scan_nfr_overall_status(_crlf(_CRLF_NFR)) == "FAIL"
    assert _readings(gate_eval, _crlf(_CRLF_REVIEW)) == _readings(gate_eval, _CRLF_REVIEW)

    # And from files written with CRLF bytes.
    result = _run(SCRIPT, tmp_path, _crlf(_CRLF_REVIEW).encode("utf-8"), _crlf(_CRLF_NFR).encode("utf-8"))
    assert result["verdict"] == "reloop"
    assert result["review_score"] is None
    assert result["nfr_status"] == "FAIL"
    assert any("more than one Quality Score (91/100, 62/100)" in r for r in result["reasons"])
    assert "test-review recommendation is Block" in result["reasons"]


def test_twin_the_first_match_reading_of_the_crlf_files_advances(tmp_path):
    # Every labelled step out, the two-score reason with them: the old reader.
    mutant = _write_mutant(
        tmp_path, "no_labelled_steps",
        (_SCORE_LABELLED_STEP, ""), (_RECOMMENDATION_LABELLED_STEP, ""), (_NFR_LABELLED_STEP, ""),
        _NO_DISTINCT_RULE[1],
    )
    result = _run(mutant, tmp_path, _crlf(_CRLF_REVIEW).encode("utf-8"), _crlf(_CRLF_NFR).encode("utf-8"))
    assert result["verdict"] == "advance"
    assert result["review_score"] == 91
    assert result["nfr_status"] == "PASS"


# --- Score: the review's own labelled line, not a quoted earlier one ----------

_QUOTED_SCORE = "\nThe previous review of this story read Quality Score: 91/100, so this one re-checks it.\n"


def test_a_quoted_earlier_score_above_the_own_score_line_is_not_read(tmp_path):
    text = _tea_review(62, "Request Changes", preface=_QUOTED_SCORE)
    assert gate_eval._scan_review_score(text) == 62

    result = _run(SCRIPT, tmp_path, text, _tea_nfr("PASS"))
    assert result["verdict"] == "reloop"
    assert result["review_score"] == 62
    assert "test-review score 62 < 80" in result["reasons"]


def test_twin_the_first_match_reading_takes_the_quoted_score(tmp_path):
    text = _tea_review(62, "Request Changes", preface=_QUOTED_SCORE)
    assert int(_first_match(_FIRST_MATCH_SCORE, text)) == 91

    mutant = _write_mutant(tmp_path, "no_labelled_score", (_SCORE_LABELLED_STEP, ""))
    result = _run(mutant, tmp_path, text, _tea_nfr("PASS"))
    assert result["verdict"] == "advance"
    assert result["review_score"] == 91


# --- Score: two different labelled values fail the signal ---------------------


@pytest.mark.parametrize("first,second", [(91, 62), (62, 91)])
def test_two_different_quality_scores_fail_with_their_own_reason(tmp_path, first, second):
    text = _tea_review(second, "Approve", preface=f"\n**Quality Score**: {first}/100 (previous cycle)\n")

    result = _run(SCRIPT, tmp_path, text, _tea_nfr("PASS"))
    assert result["verdict"] == "reloop"
    # null, not either value: the reader cannot tell which one is the review's
    # own, and null is what a production gate already prints for a score it
    # could not read.
    assert result["review_score"] is None
    assert set(result) == _KEYS | {"sweep_scope"}
    reason = next(r for r in result["reasons"] if "more than one Quality Score" in r)
    assert "test-review.md" in reason
    assert f"{first}/100" in reason and f"{second}/100" in reason
    assert not any("score not found" in r for r in result["reasons"])

    assert gate_eval._labelled_review_scores(text) == [first, second]
    assert gate_eval._scan_review_score(text) is None


def test_twin_without_the_distinct_score_rule_the_first_score_advances(tmp_path):
    text = _tea_review(62, "Approve", preface="\n**Quality Score**: 91/100 (previous cycle)\n")
    mutant = _write_mutant(tmp_path, "no_distinct_rule", *_NO_DISTINCT_RULE)
    result = _run(mutant, tmp_path, text, _tea_nfr("PASS"))
    assert result["verdict"] == "advance"
    assert result["review_score"] == 91


# --- Recommendation: Block on any labelled line --------------------------------


def test_a_quoted_earlier_approve_above_a_block_is_not_read(tmp_path):
    text = _tea_review(88, "Block", preface="\nThe previous cycle's review read Recommendation: Approve.\n")
    assert gate_eval._scan_review_recommendation(text) == "Block"

    result = _run(SCRIPT, tmp_path, text, _tea_nfr("PASS"))
    assert result["verdict"] == "reloop"
    assert "test-review recommendation is Block" in result["reasons"]


def test_twin_the_first_match_reading_takes_the_quoted_approve(tmp_path):
    text = _tea_review(88, "Block", preface="\nThe previous cycle's review read Recommendation: Approve.\n")
    assert _first_match(_FIRST_MATCH_RECOMMENDATION, text) == "Approve"

    mutant = _write_mutant(tmp_path, "no_labelled_recommendation", (_RECOMMENDATION_LABELLED_STEP, ""))
    result = _run(mutant, tmp_path, text, _tea_nfr("PASS"))
    assert result["verdict"] == "advance"


_QUOTED_APPROVE_BLOCK = "\n> **Recommendation**: Approve (previous cycle)\n"


def test_block_on_any_labelled_line_is_block(tmp_path):
    text = _tea_review(88, "Block", preface=_QUOTED_APPROVE_BLOCK)

    result = _run(SCRIPT, tmp_path, text, _tea_nfr("PASS"))
    assert result["verdict"] == "reloop"
    assert "test-review recommendation is Block" in result["reasons"]

    assert gate_eval._LABELLED_RECOMMENDATION_RE.findall(text)[0] == "Approve"
    assert gate_eval._scan_review_recommendation(text) == "Block"


def test_twin_the_first_labelled_recommendation_misses_the_block(tmp_path):
    text = _tea_review(88, "Block", preface=_QUOTED_APPROVE_BLOCK)
    mutant = _mutant(tmp_path, "no_any_block", _NO_ANY_BLOCK_RULE)
    assert mutant._scan_review_recommendation(text) == "Approve"


# --- NFR: the most severe labelled status ---------------------------------------


def test_a_quoted_earlier_pass_above_the_own_fail_is_not_read(tmp_path):
    text = _tea_nfr("FAIL", preface="The audit before the cache change read Overall Status: PASS.\n\n")
    assert gate_eval._scan_nfr_overall_status(text) == "FAIL"

    result = _run(SCRIPT, tmp_path, _tea_review(90, "Approve"), text)
    assert result["verdict"] == "reloop"
    assert result["nfr_status"] == "FAIL"


def test_twin_the_first_match_reading_takes_the_quoted_pass(tmp_path):
    text = _tea_nfr("FAIL", preface="The audit before the cache change read Overall Status: PASS.\n\n")
    assert _first_match(_FIRST_MATCH_NFR, text) == "PASS"

    mutant = _write_mutant(tmp_path, "no_labelled_nfr", (_NFR_LABELLED_STEP, ""))
    result = _run(mutant, tmp_path, _tea_review(90, "Approve"), text)
    assert result["verdict"] == "advance"
    assert result["nfr_status"] == "PASS"


@pytest.mark.parametrize("top,signoff", list(itertools.permutations(_SEVERITY, 2)))
def test_the_most_severe_labelled_status_wins(top, signoff):
    text = _tea_nfr(top, signoff=signoff)
    expected = min(top, signoff, key=_SEVERITY.index)
    assert gate_eval._scan_nfr_overall_status(text) == expected


def test_a_failing_status_at_the_sign_off_fails_the_and(tmp_path):
    result = _run(SCRIPT, tmp_path, _tea_review(90, "Approve"), _tea_nfr("PASS", signoff="NOT_ASSESSED"))
    assert result["verdict"] == "reloop"
    assert result["nfr_status"] == "NOT_ASSESSED"


def test_twin_the_first_labelled_status_misses_a_later_fail(tmp_path):
    mutant = _mutant(tmp_path, "no_most_severe", _NO_MOST_SEVERE_RULE)
    assert mutant._scan_nfr_overall_status(_tea_nfr("PASS", signoff="FAIL")) == "PASS"
    wrong = [
        (top, signoff)
        for top, signoff in itertools.permutations(_SEVERITY, 2)
        if mutant._scan_nfr_overall_status(_tea_nfr(top, signoff=signoff))
        != min(top, signoff, key=_SEVERITY.index)
    ]
    assert len(wrong) == 6, wrong


# --- A reason says when the labelled values disagree ------------------------------

_NFR_DISAGREES = (
    "nfr file nfr-assessment.md holds more than one Overall Status (PASS, FAIL); the most severe is read"
)
_RECOMMENDATION_DISAGREES = (
    "test-review file test-review.md holds more than one Recommendation (Approve, Block); "
    "a Block on any of them is read"
)


def test_disagreeing_labelled_values_get_a_reason_beside_the_status_one(tmp_path):
    result = _run(
        SCRIPT, tmp_path, _tea_review(88, "Block", preface=_QUOTED_APPROVE_BLOCK), _tea_nfr("PASS", signoff="FAIL")
    )
    assert result["verdict"] == "reloop"
    reasons = result["reasons"]
    # The status reasons are as they were; each new one follows its own.
    assert reasons.index(_NFR_DISAGREES) == reasons.index("nfr overallStatus is FAIL") + 1
    assert reasons.index(_RECOMMENDATION_DISAGREES) == reasons.index("test-review recommendation is Block") + 1


def test_a_disagreement_that_fails_nothing_still_gets_its_reason(tmp_path):
    result = _run(
        SCRIPT, tmp_path,
        _tea_review(90, "Request Changes", preface=_QUOTED_APPROVE_BLOCK),
        _tea_nfr("CONCERNS", signoff="PASS"),
    )
    assert result["verdict"] == "advance"
    assert (
        "test-review file test-review.md holds more than one Recommendation (Approve, Request Changes); "
        "the first is read"
    ) in result["reasons"]
    assert (
        "nfr file nfr-assessment.md holds more than one Overall Status (CONCERNS, PASS); the most severe is read"
    ) in result["reasons"]


def test_agreeing_labelled_values_are_one_value():
    # Compared without case: the same value twice is no disagreement.
    assert gate_eval._labelled_review_recommendations(
        "**Recommendation**: Approve\n\nrecommendation: approve\n"
    ) == ["Approve"]
    assert gate_eval._labelled_nfr_statuses("**Overall Status:** pass\n\n- Overall Status: PASS\n") == ["PASS"]


def test_twin_without_the_reasons_nothing_says_the_values_disagree(tmp_path):
    mutant = _write_mutant(tmp_path, "no_disagreement_reasons", *_NO_DISAGREEMENT_REASONS)
    result = _run(
        mutant, tmp_path, _tea_review(88, "Block", preface=_QUOTED_APPROVE_BLOCK), _tea_nfr("PASS", signoff="FAIL")
    )
    assert result["verdict"] == "reloop"
    assert not any("PASS" in r and "FAIL" in r for r in result["reasons"])
    assert not any("Approve" in r and "Block" in r for r in result["reasons"])


# --- A file with no labelled line reads as today ---------------------------------

_HAND_REVIEW = """# Review of sample.spec.ts

I read the four tests by hand. Final score: 85/100, with two medium findings.
My Recommendation: Approve with Comments.
"""
_HAND_NFR = """# NFR notes for the sample feature

Latency holds under load; one log line is missing. The audit's Overall Status: CONCERNS.
"""


def test_a_file_with_no_labelled_line_reads_as_today(tmp_path):
    assert _readings(gate_eval, _HAND_REVIEW + _HAND_NFR) == (85, "Approve with Comments", "CONCERNS")
    assert (
        int(_first_match(_FIRST_MATCH_SCORE, _HAND_REVIEW)),
        _first_match(_FIRST_MATCH_RECOMMENDATION, _HAND_REVIEW),
        _first_match(_FIRST_MATCH_NFR, _HAND_NFR),
    ) == (85, "Approve with Comments", "CONCERNS")

    result = _run(SCRIPT, tmp_path, _HAND_REVIEW, _HAND_NFR)
    assert result["verdict"] == "advance"
    assert result["review_score"] == 85
    assert result["nfr_status"] == "CONCERNS"


def test_each_scanner_falls_back_on_its_own():
    text = "**Quality Score**: 85/100\n\nOn reflection my Recommendation: Block.\n"
    assert gate_eval._scan_review_score(text) == 85
    assert gate_eval._scan_review_recommendation(text) == "Block"


def test_twin_without_the_fallback_a_hand_written_file_reads_as_nothing(tmp_path):
    mutant = _mutant(tmp_path, "no_fallback", *_NO_FALLBACK)
    assert _readings(mutant, _HAND_REVIEW + _HAND_NFR) == (None, None, None)
    assert mutant._scan_review_recommendation(
        "**Quality Score**: 85/100\n\nOn reflection my Recommendation: Block.\n"
    ) is None


# --- Time: a long line of marks is read in linear time ---------------------------

_TIME_BOUND = 5.0  # seconds for one read; the shipped ones take milliseconds
# Seconds of CPU for the whole sweep below, which takes about 3 here. A repeat
# that turns quadratic takes minutes on one of its runs.
_SWEEP_CPU_BOUND = 15.0
_WALL_TIMEOUT = 120  # seconds of wall time; a read still running by then fails the test
_LONG = 200_000
# A long run of each character the leading marks take, the optional byte-order
# mark before them included, and of each character the separator takes.
_LEADING_CHARACTERS = "\ufeff \t>#*_+-0123456789.)"
_SEPARATOR_CHARACTERS = "*:_` \t"

# Run in a child so that a read which never ends fails the test at the wall-clock
# timeout instead of hanging the suite; the child reports the CPU time it spent,
# which other work on a loaded machine does not inflate as it does wall time.
_SWEEP_CHILD = textwrap.dedent(r'''
    import importlib.util, json, sys, time
    job = json.load(sys.stdin)
    spec = importlib.util.spec_from_file_location("m", job["script"])
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    long = job["long"]
    patterns = (
        ("Quality Score", m._LABELLED_SCORE_RE),
        ("Recommendation", m._LABELLED_RECOMMENDATION_RE),
        ("Overall Status", m._LABELLED_NFR_STATUS_RE),
    )
    # Lines that hold no label, so the fallback finds nothing to start from.
    scanned = [character * long + "\n" for character in job["leading"]]
    scanned += ["- > # * _ + 1. " * (long // 14) + "\n", ("-" * 50 + "\n") * (long // 51)]
    start = time.process_time()
    for text in scanned:
        m._scan_review_score(text)
        m._scan_review_recommendation(text)
        m._scan_nfr_overall_status(text)
    for text in scanned + ["*" * long + "Quality Score" + "*" * long + "x\n"]:
        for _, pattern in patterns:
            pattern.findall(text)
    for label, pattern in patterns:
        for run in job["separators"]:
            assert pattern.findall("**" + label + run * long + "x\n") == [], (label, run)
    print(time.process_time() - start)
''')


def _sweep(script: Path, leading: str, timeout: float) -> float:
    job = {"script": str(script), "long": _LONG, "leading": leading, "separators": _SEPARATOR_CHARACTERS}
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _SWEEP_CHILD],
        input=json.dumps(job), capture_output=True, text=True, check=True, timeout=timeout,
    )
    return float(proc.stdout)


def test_long_lines_of_marks_are_read_in_linear_time():
    """A nested repeat in the leading marks never finishes on a line of dashes,
    and two side-by-side repeats that share a character make a long run of that
    character cost time quadratic in its length. Both are one character class
    here, and each character either class takes gets a long run of its own.

    The full scanners are timed on lines that hold no label, where the fallback
    finds nothing to start from. The labelled patterns are also timed on a label
    followed by a long separator run. The fallback regexes are not timed on that
    input: they are the old readers, unchanged, and that input takes them time
    quadratic in its length."""
    try:
        cpu = _sweep(SCRIPT, _LEADING_CHARACTERS, timeout=_WALL_TIMEOUT)
    except subprocess.TimeoutExpired:
        pytest.fail(f"the reads were still running after {_WALL_TIMEOUT}s of wall time")
    assert cpu < _SWEEP_CPU_BOUND, f"took {cpu:.1f}s of CPU"


def test_twin_a_repeat_that_bites_on_one_mark_needs_a_run_of_that_mark(tmp_path):
    mutant = _write_mutant(
        tmp_path, "hash_run", (_LINE_MARKS_SRC, '_LINE_MARKS = r"^\\ufeff?[ \\t>#*_+\\-0-9.)]*#*"')
    )
    # Mixed and short lines of marks never show it...
    assert _sweep(mutant, "", timeout=_WALL_TIMEOUT) < _SWEEP_CPU_BOUND
    # ...a long run of the one mark it bites on does.
    with pytest.raises(subprocess.TimeoutExpired):
        _sweep(mutant, "#", timeout=_TIME_BOUND)


_CHILD = (
    "import importlib.util, sys, time\n"
    "spec = importlib.util.spec_from_file_location('m', sys.argv[1])\n"
    "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
    "text = sys.argv[2] + sys.argv[3] * int(sys.argv[4]) + 'x\\n'\n"
    "start = time.process_time(); m._LABELLED_SCORE_RE.findall(text)\n"
    "print(time.process_time() - start)\n"
)


def _timed_child(script: Path, prefix: str, run: str, count: int, timeout: float) -> float:
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _CHILD, str(script), prefix, run, str(count)],
        capture_output=True, text=True, check=True, timeout=timeout,
    )
    return float(proc.stdout)


def test_twin_a_nested_repeat_in_the_leading_marks_never_finishes(tmp_path):
    assert _timed_child(SCRIPT, "", "-", 60, timeout=60) < _TIME_BOUND
    mutant = _write_mutant(
        tmp_path, "nested_marks",
        (_LINE_MARKS_SRC, '_LINE_MARKS = r"^\\ufeff?(?:[ \\t>#*_+\\-0-9.)]+)*"'),
    )
    with pytest.raises(subprocess.TimeoutExpired):
        _timed_child(mutant, "", "-", 60, timeout=_TIME_BOUND)


def test_twin_two_side_by_side_repeats_in_the_separator_are_quadratic(tmp_path):
    assert _timed_child(SCRIPT, "**Quality Score", "*", _LONG, timeout=60) < _TIME_BOUND
    mutant = _write_mutant(
        tmp_path, "doubled_separator",
        ('_LABEL_SEP = r"[*:_` \\t]*"', '_LABEL_SEP = r"[*:_ \\t]*[`*]*[ \\t]*"'),
    )
    with pytest.raises(subprocess.TimeoutExpired):
        _timed_child(mutant, "**Quality Score", "*", _LONG, timeout=_TIME_BOUND)
