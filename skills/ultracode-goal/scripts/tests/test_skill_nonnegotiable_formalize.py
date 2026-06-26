"""Story 2.6 — extend the SKILL launch Non-negotiable to require formalize ready.

Static grep/diff-equivalent assertions over SKILL.md (the one launch bullet) plus the
now-active cross-file verdict-token equality against preflight.md's step-4 clause
(story 2.4 has landed). Stdlib + pytest only.
"""

import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_SKILL = _SKILL_ROOT / "SKILL.md"
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"


def _skill_text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def test_ac1_same_line_conjunction():
    lines = [
        ln for ln in _skill_text().splitlines()
        if re.search(r"preflight_check\.py.*formalize_check\.py returns ready", ln)
    ]
    assert len(lines) == 1, "exactly one bullet conjoins preflight + formalize-ready"
    assert "Launch the unattended run only when" in lines[0], "it is the launch Non-negotiable bullet"


def test_ac2_exact_verdict_token():
    found = re.findall(r"formalize_check\.py returns [a-z]+", _skill_text())
    assert found == ["formalize_check.py returns ready"], "verdict word is the exact FR-5 literal 'ready'"


def test_ac3_single_bullet_scope_no_time_number():
    text = _skill_text()
    section = text.split("## Non-negotiables", 1)[1].split("\n## ", 1)[0]
    assert len(re.findall(r"^- \*\*", section, re.M)) == 6, "Non-negotiable bullet count unchanged"
    assert "preflight_check.py" in text, "conjunctive extension, not a replacement"
    launch = next(ln for ln in text.splitlines() if "Launch the unattended run only when" in ln)
    assert not re.search(
        r"\b\d+ ?(s|sec|secs|second|seconds|min|mins|minute|minutes|ms|hr|hrs|hours?)\b", launch
    ), "no authored wall-clock / timeout number in the launch bullet"


def test_ac4_cross_file_verdict_equality():
    s4_start = _PREFLIGHT.read_text(encoding="utf-8").index("## 4. Hard gate")
    pre = _PREFLIGHT.read_text(encoding="utf-8")
    s4 = pre[s4_start: pre.index("## 5.", s4_start)]
    m = re.search(r"formalize_check\.py verdict is `?([a-z]+)`?", s4)
    if m is None:
        pytest.skip("preflight.md 4th clause absent (pre-2.4)")
    skill_match = re.search(r"formalize_check\.py returns ([a-z]+)", _skill_text())
    assert skill_match is not None, "SKILL launch bullet must name the formalize verdict token"
    assert m.group(1) == skill_match.group(1) == "ready", "INV-9: the verdict literal must not drift"
