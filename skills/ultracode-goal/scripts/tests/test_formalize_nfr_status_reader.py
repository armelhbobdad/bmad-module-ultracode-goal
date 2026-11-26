#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""`formalize_check.py` reads an NFR audit's Overall Status with gate_eval's own reader.

The readiness kernel kept its own copy of the NFR status pattern: the fallback
regex alone, while gate_eval.py reads the audit's labelled lines first and falls
back only for a file with none. A status the gate reads from a labelled line the
fallback cannot take (a value behind an icon, as TEA 1.27.2's ADR knowledge
fragment writes `**Overall Status:** ⚠️ CONCERNS`, or a separator that holds a
backtick before a colon) is readable at the gate (the icon form since this change) and was an
`nfr_overall_status_unreadable` judgment candidate in the kernel, which
/ucg-formalize and the preflight clause that runs it read as owed, so the
readiness verdict came back `blocked` over a file the gate reads.

The kernel now calls gate_eval's `_scan_nfr_overall_status`, imported lazily from
the folder it ships in (as it imports preflight_check), so it flags an audit as
unreadable exactly when the gate's production AND fails it as status-not-found.
It takes the full reader, not the fallback alone and not the labelled lines
alone: a file with no labelled line IS read by the fallback, so the full reader
reads every file the fallback reads and the switch only clears candidates, and a
hand-written audit whose status sits inside a sentence has no labelled line but
is read at the gate. The candidate's shape is unchanged.

Each predicate runs on the shipped kernel and on twins: the kernel with its old
copy of the fallback put back (the text without the change), and the kernel
reading the labelled lines alone (a one-clause mutant it must reject).

Stated limit: the kernel reads only whether a status is there. Which status the
gate reads (the most severe labelled one) never reaches the kernel's output.

Run: uv run --with pytest pytest scripts/tests/test_formalize_nfr_status_reader.py
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS / "formalize_check.py"
GATE_EVAL = SCRIPTS / "gate_eval.py"
EPIC = "61"
REL = "test-artifacts/nfr-assessment.md"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


formalize = _load(SCRIPT, "formalize_nfr_status_under_test")
gate_eval = _load(GATE_EVAL, "gate_eval_for_formalize_nfr_status")

_CALL = "    overall = _gate_eval_nfr_status(text)\n"
# The kernel as it was: its own copy of the fallback regex.
_OLD_COPY = (
    _CALL,
    "    overall = re.search(\n"
    '        r"(?:Overall\\s+Status|overallStatus)[*:_\\s]*[`*]*\\s*(PASS|CONCERNS|FAIL|NOT_ASSESSED)",\n'
    "        text,\n"
    "        re.IGNORECASE,\n"
    "    )\n",
)
# The kernel reading the labelled lines alone.
_LABELLED_ONLY = (
    "    return gate_eval._scan_nfr_overall_status(text)\n",
    "    return (gate_eval._labelled_nfr_statuses(text) or [None])[0]\n",
)


def _mutant_dir(tmp_path: Path, name: str, *pairs: tuple[str, str]) -> Path:
    """A mutated kernel beside copies of the siblings it imports."""
    folder = tmp_path / name
    folder.mkdir()
    for sibling in ("preflight_check.py", "gate_eval.py"):
        shutil.copy(SCRIPTS / sibling, folder / sibling)
    src = SCRIPT.read_text(encoding="utf-8")
    for index, (old, new) in enumerate(pairs):
        assert old in src, f"mutation anchor {index} drifted out of formalize_check.py: {name}"
        src = src.replace(old, new, 1)
    (folder / "formalize_check.py").write_text(src, encoding="utf-8")
    return folder / "formalize_check.py"


def _mutant(tmp_path: Path, name: str, *pairs: tuple[str, str]):
    return _load(_mutant_dir(tmp_path, name, *pairs), f"formalize_nfr_status_mutant_{name}")


def _unreadable(module, text: str) -> bool:
    return any(
        candidate["kind"] == "nfr_overall_status_unreadable"
        for candidate in module._scan_nfr_assessment(text, REL)
    )


# --- Audits in TEA's shapes and in hand-written ones ----------------------------

# TEA 1.27.2's ADR knowledge fragment (adr-quality-readiness-checklist.md line 338).
_ADR = "## Testability\n\n**Overall Status:** ⚠️ CONCERNS (2/4 criteria met)\n"
# nfr-report-template.md lines 13 and 462: the value, then its icon.
_TEMPLATE = "**Overall Status:** PASS ✅\n\n## Sign-Off\n\n- Overall Status: PASS ✅\n"
_BACKTICK_COLON = "**Overall Status**`:` CONCERNS\n"
_SENTENCE = "The audit's own overallStatus: FAIL, after the cache change.\n"
_NONE = "## Findings\n\n| Category | Status |\n|--|--|\n| security | PASS |\n"
_NO_VALUE = "**Overall Status:** to be decided\n"
_MATH_SIGN = "**Overall Status:** ≤ PASS\n"

_CORPUS = {
    "adr": _ADR,
    "template": _TEMPLATE,
    "backtick_colon": _BACKTICK_COLON,
    "sentence": _SENTENCE,
    "none": _NONE,
    "no_value": _NO_VALUE,
    "math_sign": _MATH_SIGN,
}


@pytest.mark.parametrize("name", sorted(_CORPUS))
def test_the_kernel_finds_a_status_exactly_when_the_gate_does(name):
    text = _CORPUS[name]
    assert _unreadable(formalize, text) == (gate_eval._scan_nfr_overall_status(text) is None)


@pytest.mark.parametrize("name,readable", [
    ("adr", True), ("template", True), ("backtick_colon", True), ("sentence", True),
    ("none", False), ("no_value", False), ("math_sign", False),
])
def test_which_audits_are_readable(name, readable):
    assert _unreadable(formalize, _CORPUS[name]) is not readable


@pytest.mark.parametrize("name", ["adr", "backtick_colon"])
def test_twin_the_old_copy_flags_a_status_the_gate_reads(tmp_path, name):
    text = _CORPUS[name]
    assert gate_eval._scan_nfr_overall_status(text) is not None
    mutant = _mutant(tmp_path, f"old_copy_{name}", _OLD_COPY)
    assert _unreadable(mutant, text)
    assert not _unreadable(formalize, text)


def test_twin_the_old_copy_agrees_where_the_fallback_reads(tmp_path):
    mutant = _mutant(tmp_path, "old_copy_agrees", _OLD_COPY)
    for name in ("template", "sentence", "none", "no_value"):
        assert _unreadable(mutant, _CORPUS[name]) == _unreadable(formalize, _CORPUS[name]), name


def test_twin_the_labelled_lines_alone_miss_a_status_in_a_sentence(tmp_path):
    assert gate_eval._scan_nfr_overall_status(_SENTENCE) == "FAIL"
    mutant = _mutant(tmp_path, "labelled_only", _LABELLED_ONLY)
    assert _unreadable(mutant, _SENTENCE)
    assert not _unreadable(formalize, _SENTENCE)
    # Both read TEA's labelled lines.
    assert not _unreadable(mutant, _ADR)


def test_the_candidate_keeps_its_shape():
    assert formalize._scan_nfr_assessment("## Findings\n\nNothing assessed yet.\n", REL) == [
        {
            "source": f"{REL}:1",
            "kind": "nfr_overall_status_unreadable",
            "why_machine_cannot_decide": "nfr-assessment has no parseable overallStatus "
            "(PASS/CONCERNS/FAIL/NOT_ASSESSED); the kernel reads this field, it never originates it",
        }
    ]


def test_the_kernel_keeps_no_copy_of_the_pattern():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "Overall\\s+Status" not in source
    assert "_OVERALL_STATUS_RE" not in source
    assert "    return gate_eval._scan_nfr_overall_status(text)\n" in source
    assert _CALL in source


# --- The kernel end to end -------------------------------------------------------

_TEST_DESIGN = (
    "| Risk ID | Category | P | I | Score | Mitigation |\n|--|--|--|--|--|--|\n"
    "| T-1 | TECH | 2 | 2 | 4 | x |\n"
)


def _build(root: Path, nfr: str) -> Path:
    root.mkdir(parents=True)
    for folder in ("planning-artifacts", "impl-artifacts", "tea", "test-artifacts"):
        (root / folder).mkdir()
    (root / "tea" / "config.yaml").write_text(
        "test_artifacts: {project-root}/test-artifacts\n", encoding="utf-8"
    )
    (root / "test-artifacts" / f"test-design-epic-{EPIC}.md").write_text(_TEST_DESIGN, encoding="utf-8")
    (root / "test-artifacts" / "nfr-assessment.md").write_text(f"**Story:** {EPIC}-1\n" + nfr, encoding="utf-8")
    (root / "planning-artifacts" / "prd-fixture.md").write_text("# PRD\n", encoding="utf-8")
    (root / "planning-artifacts" / "architecture-fixture.md").write_text("# Architecture\n", encoding="utf-8")
    (root / "impl-artifacts" / "sprint-status.yaml").write_text(
        f"development_status:\n  epic-{EPIC}: in-progress\n  {EPIC}-1-sample-story: backlog\n",
        encoding="utf-8",
    )
    return root


def _verdict(script: Path, root: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(script), "--epic", EPIC, "--project-root", str(root),
         "--planning-artifacts", str(root / "planning-artifacts"),
         "--impl-artifacts", str(root / "impl-artifacts"),
         "--tea-config", str(root / "tea" / "config.yaml")],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _kinds(out: dict) -> list[str]:
    return [candidate["kind"] for candidate in out["judgment_candidates"]]


def test_an_audit_whose_status_follows_an_icon_raises_no_candidate(tmp_path):
    out = _verdict(SCRIPT, _build(tmp_path / "root", _ADR))
    assert "nfr_overall_status_unreadable" not in _kinds(out)


def test_twin_the_old_copy_raises_the_candidate_and_blocks(tmp_path):
    mutant = _mutant_dir(tmp_path, "old_copy_cli", _OLD_COPY)
    out = _verdict(mutant, _build(tmp_path / "root", _ADR))
    assert "nfr_overall_status_unreadable" in _kinds(out)
    assert out["verdict"] == "blocked"


def test_an_audit_with_no_status_still_raises_the_candidate(tmp_path):
    out = _verdict(SCRIPT, _build(tmp_path / "root", _NONE))
    assert "nfr_overall_status_unreadable" in _kinds(out)
    assert out["verdict"] == "blocked"
