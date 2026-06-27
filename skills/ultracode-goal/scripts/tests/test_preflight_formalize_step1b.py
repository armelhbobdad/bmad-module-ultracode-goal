"""preflight.md step-1b: invoke formalize_check.py after preflight_check.py.

Pure static text assertions over the reference doc (the conductor's prose contract),
mirroring test_health_check_fp.py's read-references/{stage}.md pattern. No subprocess,
no network. parents[2] from scripts/tests/ reaches the ultracode-goal skill root.
"""

import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_UCG_FORMALIZE_SKILL = _SKILL_ROOT / "skills" / "ucg-formalize" / "SKILL.md"

_STEP1B_HEADING_RE = re.compile(r"^## 1b\..*$", re.MULTILINE)
_STEP1_HEADING = "## 1. Run the mechanical check"
_STEP2_HEADING = "## 2. Auto-remediation pass"
_QUALIFIED_INVOCATION = "uv run {skill-root}/scripts/formalize_check.py"
_ONE_KERNEL_TOKEN = "{skill-root}/scripts/formalize_check.py"
_FR5_FLAGS = (
    "--epic",
    "--project-root {project-root}",
    "--planning-artifacts {planning_artifacts}",
    "--impl-artifacts {workflow.implementation_artifacts}",
    "--tea-config {workflow.tea_config_path}",
)


def _text() -> str:
    return _PREFLIGHT.read_text(encoding="utf-8")


def _step1b_block(text: str) -> str:
    """The step-1b section span: from the 1b heading to the '## 2.' heading."""
    m = _STEP1B_HEADING_RE.search(text)
    assert m is not None, "step-1b heading not found"
    start = m.start()
    end = text.index(_STEP2_HEADING, start)
    return text[start:end]


def _formalize_token(text: str) -> str:
    """The '{skill-root}/scripts/<name>' token following 'uv run' on the formalize line."""
    for line in text.splitlines():
        if "uv run" in line and "formalize_check.py" in line:
            after = line.split("uv run", 1)[1].strip()
            return after.split()[0]
    raise AssertionError("no 'uv run … formalize_check.py' line found")


def test_step1b_heading_between_step1_and_step2():
    text = _text()
    matches = list(_STEP1B_HEADING_RE.finditer(text))
    assert len(matches) == 1, f"expected exactly one '## 1b.' heading, got {len(matches)}"
    i_step1 = text.index(_STEP1_HEADING)
    i_1b = matches[0].start()
    i_step2 = text.index(_STEP2_HEADING)
    assert i_step1 < i_1b < i_step2, "step-1b must sit strictly between step 1 and step 2"


def test_invocation_is_skill_root_qualified():
    assert _text().count(_QUALIFIED_INVOCATION) == 1


def test_invocation_has_all_fr5_flags_with_canonical_placeholders():
    text = _text()
    inv_line = next(
        line for line in text.splitlines() if _QUALIFIED_INVOCATION in line
    )
    for flag in _FR5_FLAGS:
        assert flag in inv_line, f"missing readiness flag/placeholder on invocation line: {flag!r}"


def test_one_kernel_token_self_contained():
    assert _text().count(_ONE_KERNEL_TOKEN) == 1


def test_step1b_states_inv3_inv4_unconditional():
    block = _step1b_block(_text())
    assert re.search(r"resolved artifact", block, re.IGNORECASE), "resolved-artifact assertion missing"
    assert re.search(
        r"fail[- ]closed|failing signal", block, re.IGNORECASE
    ), "fail-closed assertion missing"
    assert "enable_ucg_awareness" not in block
    assert not re.search(r"only (if|when) .*customization", block, re.IGNORECASE), (
        "step-1b must run unconditionally on disk, never gated on customization"
    )


def test_step1b_is_invocation_only():
    block = _step1b_block(_text()).lower()
    for forbidden in ("auto-remediate", "subagent", "and-clause", "blocked"):
        assert forbidden not in block, f"step-1b must not contain {forbidden!r} (sibling-owned)"


def test_one_kernel_two_entry_points():
    if not _UCG_FORMALIZE_SKILL.exists():
        pytest.skip("ucg-formalize SKILL.md not present")
    preflight_token = _formalize_token(_text())
    skill_token = _formalize_token(_UCG_FORMALIZE_SKILL.read_text(encoding="utf-8"))
    assert preflight_token == skill_token == _ONE_KERNEL_TOKEN
