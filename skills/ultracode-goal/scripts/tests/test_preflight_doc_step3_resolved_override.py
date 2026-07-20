"""Step-3 resolved-RED override: the decide-loop actually closes.

Doc-shape assertions over preflight.md '## 3.' — the semantic intervention scan
consumes `.decisions.json` as a fail-closed resolved-RED override, matched BY ID
ONLY, so a RED an operator already answered does not re-fire at the next preflight.

The twin is a real paired fixture, not an authored mutant: `preflight_step3_no_decisions_override.md`
is the verbatim pre-edit `## 3.` section, captured before this edit landed. The SAME
helper that green-lights the shipped section must come back RED against it, and a
third test pins the fixture's integrity so that red stays attributable to the missing
override consumption alone (a gutted or truncated fixture would red for the wrong reason).

Stdlib + pytest only.
"""

import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "preflight_step3_no_decisions_override.md"

# Tolerates both inputs: the full doc (next section follows) and the sliced fixture
# (section runs to EOF).
_SECTION_RE = re.compile(r"^## 3\..*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)


def _sections(text: str) -> list[str]:
    return [m.group(0) for m in _SECTION_RE.finditer(text)]


def _section(text: str | None = None) -> str:
    text = text if text is not None else _PREFLIGHT.read_text(encoding="utf-8")
    found = _sections(text)
    assert found, "step-3 section not found"
    return found[0]


def _assert_override_consumption(section: str) -> None:
    """The AC's whole contract, in one helper so the shipped section and the pre-edit
    fixture are judged by byte-identical criteria."""
    # (1) the override file is named
    assert ".decisions.json" in section, "step 3 must name the `.decisions.json` override"

    # (2) the match is scoped to id equality ...
    assert re.search(
        r"match(ing|ed)? by [`*]*id[`*]* only|by [`*]*id[`*]* only",
        section,
        re.IGNORECASE,
    ), "the override must be scoped to id-equality matching"

    # ... and a source/evidence TEXT match is explicitly NOT the matcher
    assert re.search(
        r"never by [`*]*source[`*]*",
        section,
        re.IGNORECASE,
    ), "step 3 must state that a `source` text match is NOT the matcher"
    assert re.search(
        r"never by [`*]*evidence[`*]*",
        section,
        re.IGNORECASE,
    ), "step 3 must state that an `evidence` text match is NOT the matcher"

    # (3) fail-closed clause (a): an override matching no still-present RED is ignored
    assert re.search(
        r"(naming|match(es|ing)?) no still-present RED[^.\n]{0,40}(is )?ignored"
        r"|stale answer cannot pre-authorize",
        section,
        re.IGNORECASE,
    ), "missing fail-closed clause: an override naming no still-present RED is ignored"

    # (4) fail-closed clause (b): an unreadable override file clears nothing
    assert re.search(
        r"(unreadable|unparseable)[^\n]{0,80}clears nothing"
        r"|clears nothing[^\n]{0,80}(unreadable|unparseable)",
        section,
        re.IGNORECASE,
    ), "missing fail-closed clause: an unreadable `.decisions.json` clears nothing"

    # the two clauses are DISTINCT sentences, not one restated
    assert re.search(r"every scanned RED stands", section, re.IGNORECASE), (
        "the unreadable-file clause must state that every scanned RED stands"
    )


def test_step3_consumes_decisions_override_fail_closed():
    section = _section()
    _assert_override_consumption(section)

    # Only an `action` of `close` suppresses; a `defer` clears nothing.
    assert re.search(
        r"[`\"']?close[`\"']?[^.\n]{0,60}(drop|suppress|clear)"
        r"|(drop|suppress|clear)[^.\n]{0,80}[`\"']?close[`\"']?",
        section,
        re.IGNORECASE,
    ), "the override must suppress only on an `action` of `close`"
    assert re.search(
        r"defer[^.\n]{0,80}clears nothing|defer[^.\n]{0,80}still stands",
        section,
        re.IGNORECASE,
    ), "a `defer` must clear nothing and leave its RED standing"

    # The id it matches on is line-free, so an answer survives a re-scan that moved
    # the finding — the override is worthless against a line-bearing id.
    assert re.search(r"line number(s)? (are |is )?\*{0,2}exclude", section, re.IGNORECASE), (
        "the id recipe must exclude line numbers"
    )

    # The override is applied in step 3, where the reds are received — never in step 4,
    # whose no-RED clause also unions the formalize subagent's reds.
    full = _PREFLIGHT.read_text(encoding="utf-8")
    step4 = full[full.index("## 4. Hard gate"):]
    assert ".decisions.json" not in step4, (
        "the override must not reach step 4: that clause also unions formalize reds, "
        "which this suppression never authorized"
    )


def test_pre_edit_step3_fixture_lacks_override_consumption():
    # AC's paired twin: the verbatim pre-edit section, fed to the SAME helper, is RED.
    fixture_section = _section(_FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(AssertionError):
        _assert_override_consumption(fixture_section)


def test_pre_edit_fixture_differs_only_by_the_override_sentences():
    """Twin-integrity: the fixture must red for the RIGHT reason. An emptied or
    truncated fixture would also fail the helper while proving nothing."""
    fixture_text = _FIXTURE.read_text(encoding="utf-8")

    # still exactly one `## 3.` section
    assert len(_sections(fixture_text)) == 1, "fixture must slice to exactly one step-3 section"

    # still carries the three-key JSON contract fence, byte-identical to the shipped one
    def _first_json_fence(text: str) -> str:
        m = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
        assert m is not None, "json contract fence missing"
        return m.group(1)

    fixture_fence = _first_json_fence(fixture_text)
    shipped_fence = _first_json_fence(_section())
    assert fixture_fence == shipped_fence, (
        "fixture's three-key contract fence is not byte-identical to the shipped one"
    )
    for key in ("reds", "concerns", "advisories_checked"):
        assert f'"{key}"' in fixture_fence, f"fixture fence must still carry {key!r}"

    # still carries the single-throwaway-subagent delegation instruction
    assert "Delegate the read to one throwaway subagent" in fixture_text, (
        "fixture must still carry the delegation instruction"
    )

    # and it is the pre-edit section: no override consumption anywhere in it
    assert ".decisions.json" not in fixture_text
    assert ".preflight-reds.json" not in fixture_text
