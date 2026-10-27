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
_UCG_FORMALIZE_SKILL = _SKILL_ROOT.parent / "ucg-formalize" / "SKILL.md"

_STEP1B_HEADING_RE = re.compile(r"^## 1b\..*$", re.MULTILINE)
_STEP1_HEADING = "## 1. Run the mechanical check"
_STEP2_HEADING = "## 2. Auto-remediation pass"
_QUALIFIED_INVOCATION = "uv run {skill-root}/scripts/formalize_check.py"
# The two entry points name the SAME kernel, each qualified so it resolves from
# any cwd — but they no longer spell the root identically, and that is correct.
# preflight.md lives inside the module, so its root is `{skill-root}`;
# ucg-formalize is a TOP-LEVEL skill whose own `{skill-root}` would point at its
# own directory, which holds no scripts, so it qualifies with `{ucg-root}` (the
# parent module dir). What must not drift is the kernel itself.
_ONE_KERNEL_SCRIPT = "/scripts/formalize_check.py"
_VALID_KERNEL_ROOTS = ("{skill-root}", "{ucg-root}")
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
    assert _text().count("{skill-root}" + _ONE_KERNEL_SCRIPT) == 1


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


def test_an_operator_scoped_run_names_its_stories():
    block = re.sub(r"\s+", " ", _step1b_block(_text()))
    assert "When Stage 1 recorded an operator-scoped subset" in block
    assert "append one `--story <key>` per story in it" in block
    assert "as its `sprint-status.yaml` row spells it" in block
    # A mistyped or done key fails closed instead of narrowing the read.
    assert "is a gap with `remediable: false` (`story_not_in_scope`)" in block
    # Every later re-run carries the same flags.
    assert "\"step 1b's command\", it means this command with those `--story` flags, unchanged" in block
    # The default stays the whole not-done set, and headless never narrows it.
    assert "Otherwise pass no `--story`" in block
    assert "a headless run never narrows it" in block
    inv_line = next(line for line in _text().splitlines() if _QUALIFIED_INVOCATION in line)
    assert "--story" not in inv_line


def test_step2_swaps_a_parent_set_done_for_its_children_on_a_scoped_run():
    text = _text()
    start = text.index(_STEP2_HEADING)
    block = re.sub(r"\s+", " ", text[start : text.index("## 3.", start)])
    assert (
        "On an operator-scoped run, also take its key off step 1b's `--story` list "
        "and add its child rows' keys, both before the closing re-run"
    ) in block


def test_stage1_records_the_operator_scoped_subset_by_key():
    text = re.sub(r"\s+", " ", (_SKILL_ROOT / "references" / "ingest-and-scope.md").read_text(encoding="utf-8"))
    assert "**An operator-scoped subset is recorded by key.**" in text
    assert "Stage 2 passes each to the readiness check as `--story <key>`" in text


def test_one_kernel_two_entry_points():
    if not _UCG_FORMALIZE_SKILL.exists():
        pytest.skip("ucg-formalize SKILL.md not present")
    preflight_token = _formalize_token(_text())
    skill_token = _formalize_token(_UCG_FORMALIZE_SKILL.read_text(encoding="utf-8"))

    # ONE kernel: both entry points must end in the same script path, so the two
    # callers can never drift onto divergent kernels.
    assert preflight_token.endswith(_ONE_KERNEL_SCRIPT), preflight_token
    assert skill_token.endswith(_ONE_KERNEL_SCRIPT), skill_token

    # ...and each must still be ROOT-QUALIFIED, which is what makes it resolve
    # from the project cwd the caller actually runs in. A bare `scripts/…` here
    # is the regression this pair has always guarded against.
    for token in (preflight_token, skill_token):
        assert token[: -len(_ONE_KERNEL_SCRIPT)] in _VALID_KERNEL_ROOTS, (
            "kernel invocation is not root-qualified: %r" % token
        )
