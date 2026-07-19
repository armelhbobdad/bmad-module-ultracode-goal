#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Step-5 hook-env contract: the test-artifacts root the guard needs.

Static prose-contract assertions over preflight.md '## 5. Arm the environment':
the hook command must inject `ULTRACODE_TEST_ARTIFACTS`, the value it injects
must be the root TEA config resolution yields (not an unfillable `{workflow.…}`
placeholder), and step 5 must state that the skip token the guard matches is
JS/Vitest-specific. The anti-vacuous baseline is a snapshot of the section as it
stood before this contract existed. Stdlib + pytest only.
"""

import importlib.util
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_PREFLIGHT_CHECK = _SKILL_ROOT / "scripts" / "preflight_check.py"
_BASELINE = Path(__file__).resolve().parent / "fixtures" / "preflight_step5_baseline_hook_env.md"

_ENV_VAR = "ULTRACODE_TEST_ARTIFACTS"


def _load_preflight_check():
    spec = importlib.util.spec_from_file_location("preflight_check", _PREFLIGHT_CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


pf = _load_preflight_check()


def _step5(text: str | None = None) -> str:
    text = text if text is not None else _PREFLIGHT.read_text(encoding="utf-8")
    start = text.index("## 5. Arm the environment")
    try:
        end = text.index("### Launch briefing", start)
    except ValueError:
        end = len(text)
    return text[start:end]


def _hook_env_entries(block: str) -> list[str]:
    """The env assignments listed under 'Inject the hook env', one per line."""
    seg = block[block.index("Inject the hook env"):]
    return [
        line.strip()
        for line in seg.splitlines()
        if line.strip().startswith("- `ULTRACODE_")
    ]


def _entry_for(block: str, var: str) -> str | None:
    for entry in _hook_env_entries(block):
        if entry.startswith(f"- `{var}="):
            return entry
    return None


def _states_resolved_source(entry: str) -> bool:
    """True when the entry sources its value from TEA config resolution rather
    than from a workflow scalar that resolution will never fill."""
    if f"{_ENV_VAR}={{workflow." in entry:
        return False
    return "_tea_artifacts_root" in entry and "test_artifacts" in entry


def test_step5_injects_test_artifacts_env_var():
    entry = _entry_for(_step5(), _ENV_VAR)
    assert entry is not None, (
        "step 5 must write the test-artifacts root into the guard's hook command; "
        "without it the staged-acceptance-test check ships dead and nothing notices"
    )
    # it sits in the list step 5 says goes on the hook command / process env
    assert "hook command" in _step5()


def test_step5_baseline_fixture_lacks_test_artifacts_injection():
    baseline = _BASELINE.read_text(encoding="utf-8")
    assert "Inject the hook env" in baseline, "the baseline must be the same section"
    assert _entry_for(baseline, _ENV_VAR) is None
    assert _ENV_VAR not in baseline, (
        "the pre-existing prose must not already satisfy the injection contract"
    )
    # and the pre-existing injections are present in both, so the baseline is a
    # real snapshot of this list rather than an empty file that trivially lacks it
    # (asserted by shared membership, not by a raw count: the list legitimately
    # shrinks when an injection is retired, and that must not fail this test)
    assert len(_hook_env_entries(baseline)) == 5
    live = _hook_env_entries(_step5())
    assert live, "step 5 must still list hook env injections"
    for var in (
        "ULTRACODE_PROTECTED_BRANCHES",
        "ULTRACODE_IMPL_ARTIFACTS",
        "ULTRACODE_MAX_TURNS",
        "ULTRACODE_EPIC_BRANCH_PREFIX",
    ):
        assert _entry_for(baseline, var) is not None, f"{var} missing from the baseline"
        assert _entry_for(_step5(), var) is not None, f"{var} missing from step 5"
    # the contract var is the one the baseline lacks and the live section adds
    assert _entry_for(_step5(), _ENV_VAR) is not None


def test_step5_test_artifacts_value_matches_tea_resolved_root():
    root = Path("/proj")
    default = pf._tea_artifacts_root(root, {})
    substituted = pf._tea_artifacts_root(root, {"test_artifacts": "{project-root}/qa/art"})
    relative = pf._tea_artifacts_root(root, {"test_artifacts": "qa/art"})
    assert default == root / "_bmad-output" / "test-artifacts"
    assert substituted == root / "qa" / "art"
    assert relative == root / "qa" / "art"

    entry = _entry_for(_step5(), _ENV_VAR)
    assert entry is not None
    assert _states_resolved_source(entry), "the value must come from config resolution"
    # The doc's stated default is the resolver's default, spelled the same way.
    # Compare in POSIX form: the reference documents write paths with forward
    # slashes on every platform, while str() on a Path renders the native
    # separator, so a plain str() comparison passes on Linux and fails on
    # Windows for a document that is perfectly correct.
    assert default.relative_to(root).as_posix() in entry
    # and it states the two resolution rules that make the override cases above
    # land where they do
    assert "{project-root}" in entry and "substituted" in entry
    assert "relative" in entry

    # Anti-vacuous: the tempting `{workflow.…}` form (a scalar config resolution
    # never fills) satisfies neither half of the predicate.
    mutant = f"- `{_ENV_VAR}={{workflow.test_artifacts}}` (comma-separated)"
    assert not _states_resolved_source(mutant)


def test_step5_notes_test_skip_token_is_js_vitest_specific():
    def _states_the_caveat(text: str) -> bool:
        return "test.skip(" in text and (
            "JS/Vitest-specific" in text or "JS/Vitest specific" in text
        )

    block = _step5()
    assert _states_the_caveat(block), (
        "step 5 must scope the skip token it matches: a single hardcoded token is "
        "only acceptable because the acceptance tests it reads are JS-only today"
    )
    assert "pytest" in block, "and name a stack whose skips it would not see"

    # Anti-vacuous: the section as it stood before this contract says none of it.
    assert not _states_the_caveat(_BASELINE.read_text(encoding="utf-8"))
