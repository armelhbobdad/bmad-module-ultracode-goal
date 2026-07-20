"""Contract: test-design is stack-agnostic, and define-done must not license skipping it.

A health-check finding asked for a "skip test-design on a non-web stack" path
here, citing an empty test-design output directory across several Epic runs as
established practice. The premise is false, and the practice was the defect.

`bmad-testarch-test-design` is risk-and-priority analysis over the planning
corpus; its output is a document. The browser coupling in that upstream workflow
lives in its knowledge resources and its QA output template, while the executable
Create-path analytical steps carry none. Only the browser GENERATORS are web-only:
ATDD in this stage, and the automate-to-trace pair at the gate. Preflight's
framework fitness caveat is scoped to those, and reading it as "the whole chain is
web-only" is what emptied the directory and left the acceptance criteria with no
risk backbone to sharpen against.

So this file pins the correction in both directions: the stage must say
test-design runs on any stack, and must NOT anywhere license skipping it. Each
assertion carries an anti-vacuous twin, per the house pattern.
"""

import re
from pathlib import Path

_DEFINE_DONE = (
    Path(__file__).resolve().parents[1] / ".." / "references" / "define-done.md"
).resolve()


def _text() -> str:
    return _DEFINE_DONE.read_text(encoding="utf-8")


def _states_stack_agnostic(text: str) -> bool:
    """True only for prose that says test-design runs regardless of stack."""
    runs_anywhere = re.search(
        r"[Tt]est-design runs on any stack|runs on any stack", text
    )
    scopes_the_caveat = re.search(r"browser generator", text, re.I)
    return bool(runs_anywhere and scopes_the_caveat)


def test_stage_states_test_design_is_stack_agnostic():
    assert _states_stack_agnostic(_text()), (
        "define-done must state that test-design runs on any stack, and scope "
        "the fitness caveat to the browser generators it actually covers"
    )


def test_stack_agnostic_claim_anti_vacuous():
    """Prose that merely mentions non-web stacks must not satisfy the contract."""
    hollow = (
        "Run `bmad-testarch-test-design` in Epic-Level Mode. On a non-web stack, "
        "consider whether the TEA chain applies."
    )
    assert not _states_stack_agnostic(hollow)


# An AFFIRMATIVE instruction to skip test-design. Deliberately requires
# `test-design` as the direct object of `skip`, because the file's other `skip`
# uses are legitimate (ATDD under `--light`, and the `test.skip()` red-phase
# marker) and the shipped prohibition itself reads "do not skip **it**".
# Bounded, non-nested quantifiers only: an earlier `[^.]{0,60}` draft backtracked
# catastrophically on this same file.
_LICENSES_SKIP = re.compile(
    r"\bskip\s+(?:the\s+|per-Epic\s+|TEA\s+)?test-design\b"
    r"|\btest-design\b[^.\n]{0,40}?\b(?:is|was|be)\s+skipped\b",
    re.I,
)


def test_stage_never_licenses_skipping_test_design():
    """The finding's own ask, which must NOT be in the shipped file."""
    match = _LICENSES_SKIP.search(_text())
    assert not match, (
        "define-done must not license skipping test-design on any stack; the "
        "substitution when the browser steps cannot run is gate.md's "
        f"hand-authored trace artifacts. Matched: {match.group(0) if match else ''}"
    )


def test_skip_detector_is_discriminating():
    """Anti-vacuous twin: it catches the ask, and clears the prohibition."""
    asked_for = (
        "When the resolved framework is not a browser/E2E stack, skip test-design "
        "and hand-author the per-story trace artifacts instead."
    )
    assert _LICENSES_SKIP.search(asked_for), "the detector must catch the ask"

    # ...and must NOT fire on the shipped prohibition, nor on the legitimate
    # ATDD skip, or it would forbid the very sentence it exists to protect.
    assert not _LICENSES_SKIP.search(
        "**Test-design runs on any stack — do not skip it on a non-web module.**"
    )
    assert not _LICENSES_SKIP.search(
        "run step 1 (`bmad-create-story`) but **skip step 2 (`bmad-testarch-atdd`)**"
    )


def test_light_note_does_not_overstate_the_trace_dependency():
    """Upstream trace loads test-design "if available" and can decide without it.

    The pre-edit sentence said trace "needs" the matrix "regardless of profile",
    which is stronger than upstream's own contract.
    """
    text = _text()
    assert "consumes its risk scores" in text, (
        "the --light note must describe the dependency as consumption when "
        "available, not as a hard requirement"
    )
    assert "trace needs its risk matrix" not in text, (
        "the overstated wording must stay retired"
    )


def test_stage_does_not_enumerate_what_the_gate_opens():
    """Which artifacts `gate_eval.py` opens belongs to gate.md, which states it twice.

    A third, narrower restatement here is a drift source, and one drafted during
    this fix was wrong twice over: it reasoned from gate_eval.py when the
    sentence is about `bmad-testarch-trace` (the PRODUCER, not the reader), and
    it claimed nothing machine-reads test-design when `formalize_check.py` does,
    blind to profile.

    The bare NAME is fine and pre-dates this work (the P0-P3 bullet legitimately
    says the gate keys its thresholds to those priorities). What must stay out is
    an enumeration of the files it opens.
    """
    text = _text()
    enumerates = re.search(
        r"gate_eval\.py[^.\n]{0,60}?\b(opens|reads only|never a)\b", text, re.I
    )
    assert not enumerates, (
        "define-done must not enumerate what gate_eval.py opens; that contract "
        f"is gate.md's. Matched: {enumerates.group(0) if enumerates else ''}"
    )


def test_gate_enumeration_detector_is_discriminating():
    """Twin: the drafted-and-rejected sentence must be caught, the kept one cleared."""
    rejected = (
        "under `--light` `gate_eval.py` opens only `trace-<id>.md` and "
        "`gate-decision-<id>.json`, never a risk matrix or a priority file"
    )
    assert re.search(
        r"gate_eval\.py[^.\n]{0,60}?\b(opens|reads only|never a)\b", rejected, re.I
    )

    kept = (
        "The gate Stage 5 reads (`gate_eval.py`) keys P0, P1, and overall "
        "thresholds to these priorities"
    )
    assert not re.search(
        r"gate_eval\.py[^.\n]{0,60}?\b(opens|reads only|never a)\b", kept, re.I
    )
