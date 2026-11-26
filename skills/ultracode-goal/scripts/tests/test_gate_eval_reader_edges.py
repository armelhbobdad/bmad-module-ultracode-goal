#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""`gate_eval.py` reads a value behind an icon, and its fallback readers run in linear time.

Two defects in the production-signal readers, and three readings pinned as intended.

An icon between a label and its value. The labelled readers took the label, the
separator and then the value, so a value written behind an icon was no labelled
line. TEA 1.27.2's NFR workflow loads the knowledge fragment
`adr-quality-readiness-checklist.md` (its step-01-load-context.md lists it), and
that fragment's sample report writes each category's status as
`**Overall Status:** ⚠️ CONCERNS (2/4 criteria met)`. An audit whose only status
line was written that way read as no status, and the production AND failed it as
"Overall Status not found". The three labelled readers now take one optional icon
between the separator and the value: an emoji or symbol character, an optional
variation selector (U+FE0F), then spaces or tabs. An icon after the value
(`**Overall Status:** PASS ✅`, as TEA's own nfr-report-template.md writes it,
and `- Overall Status: FAIL ❌` at its sign-off) was always read and still is.

Quadratic fallback readers. The fallback regexes (used for a file with no
labelled line) joined three repeats, `[*:_\\s]*[`*]*\\s*`, the first of which
shares `*` with the second and whitespace with the third, so a long run of
asterisks or spaces after a label with no value behind it cost time quadratic in
its length (minutes for 200,000 characters). They are now `[*:_\\s]*(?:`[`*]*\\s*)?`,
which accepts the same strings: `*` and whitespace are in the first class, so a
separator leaves it only at its first backtick. An exhaustive comparison over
every string of up to six characters from the separator's alphabet and a stray
letter finds the two separators equal on each, and each fallback reads the
value the old one read with every string of up to four between label and value.
A rewrite that drops or narrows one clause disagrees by the third character.

Pinned as intended, unchanged: `Recommendation: Blocked` reads as Block; a
heading that ends in `Recommendation: Block`, in a review with no labelled
Recommendation line, reads as Block; a bare `Score: 70/100` line beside a quoted
`> **Quality Score**: 85/100` line reads the labelled 85.

Each predicate is checked on the shipped script and on twins: the script with
the change taken out (the icon allowance emptied, the old separator put back)
and one-clause mutants it must reject. The time-bound tests run in a child
process under a CPU-time bound and a wall-clock timeout. The old fallback's
quadratic cost is shown at a modest length only, so the suite stays fast.

Stated limit: the icon is one character from the arrows, technical symbols,
geometric shapes, miscellaneous symbols, dingbats, symbols-and-arrows blocks or
the emoji planes. A two-character emoji sequence (a joiner sequence, a flag or a
skin-tone modifier), emphasis around the value after the icon, and an icon
before the label are still not labelled lines, and the fallback readers do not
take an icon at all. No such form is in the reports TEA 1.27.2's NFR or test-review
skills write (step-03f-aggregate-scores.md prints `📊 Overall Quality Score:` to the
console only).

Run: uv run --with pytest pytest scripts/tests/test_gate_eval_reader_edges.py
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "gate_eval.py"
STORY = "61-1-sample-story"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


gate_eval = _load(SCRIPT, "gate_eval_reader_edges_under_test")


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
    return _load(_write_mutant(tmp_path, name, *pairs), f"gate_eval_edges_mutant_{name}")


# --- The change, as the mutation anchors that take it out ---------------------

_ICON_SRC = (
    "_VALUE_ICON = (\n"
    '    r"(?:[\\u2190-\\u21ff\\u2300-\\u23ff\\u25a0-\\u27bf\\u2b00-\\u2bff\\U0001f000-\\U0001faff]"\n'
    '    r"\\ufe0f?[ \\t]*)?"\n'
    ")"
)
_ICON_TAIL_SRC = 'r"\\ufe0f?[ \\t]*)?"'
# The labelled readers as they were: no icon between the separator and the value.
_NO_ICON = (_ICON_SRC, '_VALUE_ICON = r""')
# One clause out at a time.
_NO_VARIATION_SELECTOR = (_ICON_TAIL_SRC, 'r"[ \\t]*)?"')
_NO_SPACE_AFTER_ICON = (_ICON_TAIL_SRC, 'r"\\ufe0f?)?"')
_ICON_REQUIRED = (_ICON_TAIL_SRC, 'r"\\ufe0f?[ \\t]*)"')
_NO_EMOJI_PLANES = ("\\u2b00-\\u2bff\\U0001f000-\\U0001faff]", "\\u2b00-\\u2bff]")
# An icon that may be left out inside the group puts the spaces after it right
# beside the separator's own spaces: two side-by-side repeats sharing a character.
_ICON_OPTIONAL_INSIDE = ("\\U0001f000-\\U0001faff]\"\n", "\\U0001f000-\\U0001faff]?\"\n")

_FALLBACK_SEP_SRC = '_FALLBACK_SEP = r"[*:_\\s]*(?:`[`*]*\\s*)?"'
# The old three-repeat separator, put back.
_OLD_FALLBACK = (_FALLBACK_SEP_SRC, '_FALLBACK_SEP = r"[*:_\\s]*[`*]*\\s*"')

# The readers as they were before this change, verbatim (origin at v8.1.0).
_OLD_SEP = r"[*:_\s]*[`*]*\s*"
_OLD_SCORE = r"(?:Quality\s+Score|score)[*:_\s]*[`*]*\s*(\d{1,3})\s*/\s*100"
_OLD_RECOMMENDATION = (
    r"Recommendation[*:_\s]*[`*]*\s*"
    r"(Approve with Comments|Approve|Request Changes|Block)"
)
_OLD_NFR = r"(?:Overall\s+Status|overallStatus)[*:_\s]*[`*]*\s*(PASS|CONCERNS|FAIL|NOT_ASSESSED)"


def _first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1) if match else None


# --- (a) An icon between the label and the value ------------------------------

# TEA 1.27.2, bmad-testarch-nfr/resources/knowledge/adr-quality-readiness-checklist.md
# line 338, loaded by the NFR workflow's steps-c/step-01-load-context.md line 65.
_TEA_ADR_LINE = "**Overall Status:** ⚠️ CONCERNS (2/4 criteria met)"

_WARNING = "\u26a0\ufe0f"  # warning sign with its variation selector
_CHECK = "\u2705"  # white heavy check mark
_CROSS = "\u274c"  # cross mark
_GREEN = "\U0001f7e2"  # large green circle (an emoji plane)
_NO_ENTRY = "\u26d4"  # no entry
_HEAVY_CHECK = "\u2714\ufe0f"  # heavy check mark with its variation selector
_ARROW = "\u27a1\ufe0f"  # black rightwards arrow with its variation selector
_ICONS = (_WARNING, _CHECK, _CROSS, _GREEN, _NO_ENTRY, _HEAVY_CHECK, _ARROW)


def _readers(module):
    """Each label's labelled reader, as (label, read the distinct labelled values)."""
    return {
        "score": module._labelled_review_scores,
        "recommendation": module._labelled_review_recommendations,
        "status": module._labelled_nfr_statuses,
    }


# TEA's stock lines for each label, filled: the template's own form (value then
# icon), the same line with the icon moved before the value, the bold list and
# plain list forms, and the NFR sign-off. `{i}` is the icon.
_STOCK = [
    # test-review-template.md line 11, `**Quality Score**: {score}/100 ({grade} - {assessment})`
    ("score", "**Quality Score**: 85/100 {i} (B - Good)", 85, "after"),
    ("score", "**Quality Score**: {i} 85/100 (B - Good)", 85, "before"),
    ("score", "- **Quality Score:** {i} 85/100", 85, "before"),
    ("score", "- Quality Score: {i} 85/100", 85, "before"),
    # test-review-template.md lines 28 and 389, `**Recommendation**: {...}`
    ("recommendation", "**Recommendation**: Approve {i}", "Approve", "after"),
    ("recommendation", "**Recommendation**: {i} Approve", "Approve", "before"),
    ("recommendation", "**Recommendation**: {i} Approve with Comments", "Approve with Comments", "before"),
    ("recommendation", "- **Recommendation**: {i} Request Changes", "Request Changes", "before"),
    ("recommendation", "- Recommendation: {i} Block", "Block", "before"),
    # nfr-report-template.md line 13, `**Overall Status:** {OVERALL_STATUS} {STATUS_ICON}`
    ("status", "**Overall Status:** CONCERNS {i}", "CONCERNS", "after"),
    ("status", "**Overall Status:** {i} CONCERNS", "CONCERNS", "before"),
    # nfr-report-template.md line 462, `- Overall Status: {OVERALL_STATUS} {OVERALL_ICON}`
    ("status", "- Overall Status: FAIL {i}", "FAIL", "after"),
    ("status", "- Overall Status: {i} FAIL", "FAIL", "before"),
    ("status", "- **Overall Status:** {i} PASS", "PASS", "before"),
    # The ADR fragment's form, icon first and a note after the value.
    ("status", "**Overall Status:** {i} CONCERNS (2/4 criteria met)", "CONCERNS", "before"),
]


@pytest.mark.parametrize("label,template,value,where", _STOCK)
@pytest.mark.parametrize("icon", _ICONS)
def test_a_stock_line_reads_with_its_icon_before_or_after_the_value(label, template, value, where, icon):
    line = template.format(i=icon) + "\n"
    assert _readers(gate_eval)[label](line) == [value]


@pytest.mark.parametrize("label,template,value,where", _STOCK)
def test_a_stock_line_reads_without_an_icon(label, template, value, where):
    line = re.sub(r" ?\{i\}", "", template) + "\n"
    assert _readers(gate_eval)[label](line) == [value]


def test_tea_adr_line_reads_as_concerns():
    assert gate_eval._labelled_nfr_statuses(_TEA_ADR_LINE + "\n") == ["CONCERNS"]
    assert gate_eval._scan_nfr_overall_status(_TEA_ADR_LINE + "\n") == "CONCERNS"


@pytest.mark.parametrize("label,template,value,where", _STOCK)
def test_twin_without_the_icon_allowance_only_an_icon_after_the_value_reads(tmp_path, label, template, value, where):
    line = template.format(i=_WARNING) + "\n"
    mutant = _mutant(tmp_path, f"no_icon_{label}_{where}", _NO_ICON)
    assert _readers(mutant)[label](line) == ([value] if where == "after" else [])
    # The same line without an icon reads in the old form too.
    assert _readers(mutant)[label](re.sub(r" ?\{i\}", "", template) + "\n") == [value]


def test_twin_without_the_icon_allowance_the_adr_line_is_no_status(tmp_path):
    mutant = _mutant(tmp_path, "no_icon_adr", _NO_ICON)
    assert mutant._labelled_nfr_statuses(_TEA_ADR_LINE + "\n") == []
    # The old fallback cannot take the icon either, so the file read as no status.
    assert mutant._scan_nfr_overall_status(_TEA_ADR_LINE + "\n") is None
    assert _first_match(_OLD_NFR, _TEA_ADR_LINE) is None


@pytest.mark.parametrize(
    "name,mutation,line,shipped",
    [
        # Each clause has a line that needs it.
        ("no_variation_selector", _NO_VARIATION_SELECTOR, "**Overall Status:** \u26a0\ufe0f CONCERNS", ["CONCERNS"]),
        ("no_space_after_icon", _NO_SPACE_AFTER_ICON, "**Overall Status:** \u26a0\ufe0f CONCERNS", ["CONCERNS"]),
        ("icon_required", _ICON_REQUIRED, "**Overall Status:** CONCERNS", ["CONCERNS"]),
        ("no_emoji_planes", _NO_EMOJI_PLANES, "**Overall Status:** \U0001f7e2 PASS", ["PASS"]),
    ],
)
def test_twin_each_clause_of_the_icon_is_needed(tmp_path, name, mutation, line, shipped):
    assert gate_eval._labelled_nfr_statuses(line + "\n") == shipped
    mutant = _mutant(tmp_path, name, mutation)
    assert mutant._labelled_nfr_statuses(line + "\n") == []


@pytest.mark.parametrize(
    "line",
    [
        # Two icons, a mathematical sign, an ASCII mark, emphasis after the
        # icon, an icon before the label, a line end after the icon: none is a
        # labelled line.
        "**Overall Status:** \u26a0\ufe0f\u26a0\ufe0f CONCERNS",
        "**Overall Status:** \u2264 PASS",
        "**Overall Status:** ~ PASS",
        "**Overall Status:** \u26a0\ufe0f **CONCERNS**",
        "\u26a0\ufe0f Overall Status: CONCERNS",
        "**Overall Status:** \u26a0\ufe0f\nCONCERNS",
    ],
)
def test_only_one_icon_then_the_value_is_taken(line):
    assert gate_eval._labelled_nfr_statuses(line + "\n") == []


# The whole gate on an NFR audit in TEA's shape.

def _tea_nfr(status_lines: str) -> str:
    return f"""---
stepsCompleted: ['step-01-load-context', 'step-05-generate-report']
workflowType: 'testarch-nfr-assess'
---

# NFR Evidence Audit - Sample Feature

**Date:** 2026-11-26
**Story:** {STORY} (if applicable)
{status_lines}

## Gate YAML Snippet

```yaml
nfr_assessment:
  story_id: '{STORY}'
  overall_status: 'CONCERNS'
```
"""


_REVIEW = "**Quality Score**: 90/100 (A - Excellent)\n\n**Recommendation**: Approve\n"


def _run(script: Path, tmp_path: Path, review_text: str, nfr_text: str) -> dict:
    trace = tmp_path / "test-artifacts"
    trace.mkdir()
    (trace / f"gate-decision-{STORY}.json").write_text(
        json.dumps({"schema_version": "0.1.0", "gate_status": "PASS", "p0_status": "MET",
                    "p1_status": "MET", "overall_status": "MET"}),
        encoding="utf-8",
    )
    review = trace / "test-review.md"
    review.write_text(review_text, encoding="utf-8")
    nfr = trace / "nfr-assessment.md"
    nfr.write_text(nfr_text, encoding="utf-8")
    marker = trace / f".tests-ran-{STORY}"
    marker.write_text("baseline=0123abc\nscope=full\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--trace-output", str(trace), "--profile", "production",
         "--story", STORY, "--nfr", str(nfr), "--test-review", str(review),
         "--tests-ran", str(marker)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_an_audit_whose_only_status_follows_an_icon_advances(tmp_path):
    result = _run(SCRIPT, tmp_path, _REVIEW, _tea_nfr(_TEA_ADR_LINE))
    assert result["nfr_status"] == "CONCERNS"
    assert result["verdict"] == "advance"
    assert not any("not found" in reason for reason in result["reasons"])


def test_twin_without_the_icon_allowance_that_audit_reloops_as_not_found(tmp_path):
    mutant = _write_mutant(tmp_path, "no_icon_gate", _NO_ICON)
    run = tmp_path / "run"
    run.mkdir()
    result = _run(mutant, run, _REVIEW, _tea_nfr(_TEA_ADR_LINE))
    assert result["nfr_status"] is None
    assert result["verdict"] == "reloop"
    assert any("Overall Status not found" in reason for reason in result["reasons"])


def test_a_category_status_behind_an_icon_joins_the_most_severe_reading(tmp_path):
    """TEA's own top line (value then icon) and an ADR-form category line (icon
    then value): both are labelled lines now, and the most severe is read."""
    lines = "**Overall Status:** PASS ✅\n\n### 1. Testability & Automation\n\n" + _TEA_ADR_LINE
    result = _run(SCRIPT, tmp_path, _REVIEW, _tea_nfr(lines))
    assert result["nfr_status"] == "CONCERNS"
    assert result["verdict"] == "advance"
    assert any("more than one Overall Status (PASS, CONCERNS)" in r for r in result["reasons"])

    mutant = _write_mutant(tmp_path, "no_icon_category", _NO_ICON)
    run = tmp_path / "run"
    run.mkdir()
    old = _run(mutant, run, _REVIEW, _tea_nfr(lines))
    assert old["nfr_status"] == "PASS"
    assert not any("more than one" in r for r in old["reasons"])


# --- (c) The fallback readers: the same language, in linear time ---------------

_ALPHABET = ("*", ":", "_", " ", "\n", "`", "x")


def _strings(max_len: int):
    for length in range(max_len + 1):
        for chars in itertools.product(_ALPHABET, repeat=length):
            yield "".join(chars)


def _first_disagreement(candidate: str, max_len: int) -> str | None:
    """The first string up to max_len the candidate separator and the old one
    disagree on, as a whole match, or None when they agree on every one."""
    old = re.compile(_OLD_SEP)
    new = re.compile(candidate)
    for text in _strings(max_len):
        if (old.fullmatch(text) is None) != (new.fullmatch(text) is None):
            return text
    return None


def test_the_linear_separator_accepts_exactly_the_old_language():
    # 137,257 strings: every string of up to six characters over the alphabet.
    assert _first_disagreement(gate_eval._FALLBACK_SEP, 6) is None


@pytest.mark.parametrize(
    "name,candidate,witness",
    [
        ("no_backtick_group", r"[*:_\s]*", "`"),
        ("group_required", r"[*:_\s]*`[`*]*\s*", ""),
        ("group_without_star", r"[*:_\s]*(?:`[`]*\s*)?", "`*"),
        ("group_without_space", r"[*:_\s]*(?:`[`*]*)?", "` "),
        ("first_class_without_star", r"[:_\s]*(?:`[`*]*\s*)?", "*"),
        ("first_class_without_space", r"[*:_]*(?:`[`*]*\s*)?", " "),
    ],
)
def test_twin_a_one_clause_rewrite_is_caught_by_the_comparison(name, candidate, witness):
    assert _first_disagreement(candidate, 4) == witness


_FALLBACK_CASES = (
    ("score", "Quality Score", "85/100", _OLD_SCORE, lambda m, t: m._scan_review_score(t), int),
    ("recommendation", "Recommendation", "Approve with Comments", _OLD_RECOMMENDATION,
     lambda m, t: m._scan_review_recommendation(t), str),
    ("status", "Overall Status", "concerns", _OLD_NFR, lambda m, t: m._scan_nfr_overall_status(t), str.upper),
)


def _fallback_disagreement(module, max_len: int):
    """The first (label, text) whose fallback reading differs from the old reader's.

    The label opens mid-line (`Earlier: `), so no line is labelled and the
    scanner's fallback does the reading."""
    for _, label, value, old_pattern, scan, cast in _FALLBACK_CASES:
        for middle in _strings(max_len):
            text = "Earlier: " + label + middle + value + "\n"
            old = _first_match(old_pattern, text)
            if scan(module, text) != (None if old is None else cast(old)):
                return label, text
    return None


def test_each_fallback_reads_what_the_old_reader_read():
    # 2,801 strings between label and value, for each of the three readers.
    assert _fallback_disagreement(gate_eval, 4) is None


def test_twin_the_function_comparison_catches_a_wrong_fallback(tmp_path):
    mutant = _mutant(
        tmp_path, "fallback_without_backtick", (_FALLBACK_SEP_SRC, '_FALLBACK_SEP = r"[*:_\\s]*"')
    )
    found = _fallback_disagreement(mutant, 2)
    assert found is not None and "`" in found[1]


def test_a_backtick_quoted_value_reads_as_before():
    """A value in backticks after the separator, the form the second part of the
    separator exists for, reads as the old reader read it."""
    text = "Earlier: Overall Status:** `PASS`\n"
    assert gate_eval._scan_nfr_overall_status(text) == "PASS"
    assert _first_match(_OLD_NFR, text) == "PASS"


_TIME_BOUND = 5.0  # seconds for one read in a twin; the shipped reads take milliseconds
_SWEEP_CPU_BOUND = 20.0  # seconds of CPU for the whole sweep below, which takes about 3 here
_WALL_TIMEOUT = 120  # seconds of wall time; a read still running by then fails the test
_LONG = 200_000

# Run in a child so that a read which never ends fails the test at the wall-clock
# timeout instead of hanging the suite; the child reports the CPU time it spent.
_SWEEP_CHILD = textwrap.dedent(r'''
    import importlib.util, json, sys, time
    job = json.load(sys.stdin)
    spec = importlib.util.spec_from_file_location("m", job["script"])
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    long = job["long"]
    scanners = (
        ("Quality Score", "85/100", m._scan_review_score, 85, m._LABELLED_SCORE_RE),
        ("Recommendation", "Approve", m._scan_review_recommendation, "Approve", m._LABELLED_RECOMMENDATION_RE),
        ("Overall Status", "PASS", m._scan_nfr_overall_status, "PASS", m._LABELLED_NFR_STATUS_RE),
    )
    start = time.process_time()
    for label, value, scan, expected, pattern in scanners:
        for prefix, runs in (("Earlier: ", job["runs"]), ("**", job["line_start_runs"])):
            for run, in_language in runs:
                body = prefix + label + run * (long // len(run))
                assert scan(body + "x\n") is None, (label, prefix, run)
                # A labelled line takes any mix of its separator characters; the
                # fallback takes its own language only, as the old one did.
                read = expected if in_language or prefix == "**" else None
                assert scan(body + value + "\n") == read, (label, prefix, run)
        for icon_run in job["icon_runs"]:
            text = "**" + label + ":** " + icon_run * (long // len(icon_run)) + "x\n"
            assert pattern.findall(text) == [], (label, icon_run)
    print(time.process_time() - start)
''')
# Each with whether a long run of it is in the fallback separator's language.
# The fallback's first class (`*`, `:`, whitespace including a line end), the
# backtick that opens its second part, mixes of the two parts, and a backtick, a
# space, then a backtick again, which the language does not hold. A label that
# opens a line is read by the labelled reader first, then the fallback.
_RUNS = (
    ("*", True), (":", True), (" ", True), ("\n", True), ("`", True), ("*`", True), ("` ", False),
)
_LINE_START_RUNS = (("*", True), (" ", True))
# After an icon: a long run of spaces, of icons, of variation selectors.
_ICON_RUNS = ("\u26a0\ufe0f" + " " * 7, " ", "\u26a0", "\ufe0f", "\u26a0\ufe0f ")


def _sweep(script: Path, timeout: float) -> float:
    job = {"script": str(script), "long": _LONG, "runs": _RUNS, "line_start_runs": _LINE_START_RUNS,
           "icon_runs": _ICON_RUNS}
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _SWEEP_CHILD],
        input=json.dumps(job), capture_output=True, text=True, check=True, timeout=timeout,
    )
    return float(proc.stdout)


def test_a_long_run_after_a_label_is_read_in_linear_time():
    """200,000 characters of each kind of separator run after each label, with
    and without a value at the end, through the full scanners: the fallback reads
    the mid-line label, and the labelled reader then the fallback read the one at
    the line start. Also a long run of spaces, icons or variation selectors after
    an icon on a labelled line."""
    try:
        cpu = _sweep(SCRIPT, timeout=_WALL_TIMEOUT)
    except subprocess.TimeoutExpired:
        pytest.fail(f"the reads were still running after {_WALL_TIMEOUT}s of wall time")
    assert cpu < _SWEEP_CPU_BOUND, f"took {cpu:.1f}s of CPU"


@pytest.mark.parametrize("run", ["*", " "])
def test_twin_the_old_fallback_is_far_slower_on_the_same_kind_of_line(run):
    """The old separator on a run of 2,000 (it costs minutes on 200,000, so the
    suite never runs it there) against the shipped one on the same text."""
    text = "Earlier: Overall Status" + run * 2_000 + "x\n"
    old = re.compile(_OLD_NFR, re.IGNORECASE)
    new = re.compile(r"(?:Overall\s+Status|overallStatus)" + gate_eval._FALLBACK_SEP
                     + r"(PASS|CONCERNS|FAIL|NOT_ASSESSED)", re.IGNORECASE)
    start = time.process_time()
    assert old.search(text) is None
    old_cpu = time.process_time() - start
    start = time.process_time()
    for _ in range(10):
        assert new.search(text) is None
    new_cpu = (time.process_time() - start) / 10
    assert old_cpu > 0.01, f"old read took only {old_cpu:.4f}s"
    assert old_cpu > 20 * new_cpu, (old_cpu, new_cpu)


def test_the_comparison_accepts_the_old_separator_put_back(tmp_path):
    """The comparison is against the old readers, so the old separator put back
    passes it: a failure above is the new separator's, not the comparison's."""
    mutant = _mutant(tmp_path, "old_fallback", _OLD_FALLBACK)
    assert _fallback_disagreement(mutant, 3) is None


def test_twin_an_icon_left_optional_inside_its_group_is_quadratic(tmp_path):
    mutant = _write_mutant(tmp_path, "icon_optional_inside", _ICON_OPTIONAL_INSIDE)
    child = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('m', sys.argv[1])\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "m._LABELLED_NFR_STATUS_RE.findall('**Overall Status' + ' ' * 200000 + 'x\\n')\n"
    )
    shipped = subprocess.run(
        [sys.executable, "-I", "-c", child, str(SCRIPT)], capture_output=True, text=True,
        check=True, timeout=60,
    )
    assert shipped.returncode == 0
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run(
            [sys.executable, "-I", "-c", child, str(mutant)], capture_output=True, text=True,
            check=True, timeout=_TIME_BOUND,
        )


# --- (d) Readings pinned as intended -------------------------------------------


def test_recommendation_blocked_reads_as_block():
    """Intended: `Recommendation: Blocked` reads as Block. The value is matched as
    a prefix, so a review that says its tests are blocked fails the signal."""
    line = "Recommendation: Blocked\n"
    assert gate_eval._labelled_review_recommendations(line) == ["Block"]
    assert gate_eval._scan_review_recommendation(line) == "Block"
    assert gate_eval._scan_review_recommendation("Earlier: Recommendation: Blocked\n") == "Block"


def test_twin_a_word_boundary_after_the_value_would_not_read_blocked(tmp_path):
    mutant = _mutant(
        tmp_path, "word_boundary",
        ('+ r"(Approve with Comments|Approve|Request Changes|Block)",\n    _LABELLED_FLAGS,',
         '+ r"(Approve with Comments|Approve|Request Changes|Block)\\b",\n    _LABELLED_FLAGS,'),
    )
    assert mutant._labelled_review_recommendations("Recommendation: Blocked\n") == []


def test_a_heading_that_ends_in_recommendation_block_reads_as_block():
    """Intended, the strict reading: in a review with no labelled Recommendation
    line, a heading that ends in `Recommendation: Block` reads as Block. The
    heading is no labelled line (it does not open with the label), so the
    fallback reads it, and Block fails the signal."""
    text = "# Test Quality Review\n\n### Final Recommendation: Block\n\nThe suite is not ready.\n"
    assert gate_eval._labelled_review_recommendations(text) == []
    assert gate_eval._scan_review_recommendation(text) == "Block"


def test_twin_without_the_fallback_the_heading_reads_as_nothing(tmp_path):
    mutant = _mutant(
        tmp_path, "no_recommendation_fallback",
        ("    if labelled:\n"
         '        return next((value for value in labelled if value.lower() == "block"), labelled[0])\n',
         '    return next((value for value in labelled if value.lower() == "block"), labelled[0] if labelled else None)\n'),
    )
    assert mutant._scan_review_recommendation("### Final Recommendation: Block\n") is None


def test_a_bare_score_beside_a_quoted_quality_score_reads_the_labelled_line():
    """Intended: a bare `Score: 70/100` line beside a quoted
    `> **Quality Score**: 85/100` line reads 85. The quoted line opens with its
    label after the quote mark, so it is a labelled line, and a bare `Score`
    label is never one."""
    for text in ("Score: 70/100\n> **Quality Score**: 85/100\n", "> **Quality Score**: 85/100\nScore: 70/100\n"):
        assert gate_eval._labelled_review_scores(text) == [85]
        assert gate_eval._scan_review_score(text) == 85


def test_twin_the_first_match_reading_takes_the_bare_score():
    assert _first_match(_OLD_SCORE, "Score: 70/100\n> **Quality Score**: 85/100\n") == "70"
    # And without the labelled line the bare score is the fallback's reading.
    assert gate_eval._scan_review_score("Score: 70/100\n") == 70
