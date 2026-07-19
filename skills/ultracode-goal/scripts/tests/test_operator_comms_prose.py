"""Prose contract over the two attended operator-comms surfaces, plus the viewer affordance.

Three shipped reference files carry this story's whole deliverable, so every
assertion here is a static read of shipped markdown (plus one adapter source):

  - `references/gate.md`, "Run the gate" - the verdict is formed there and, until
    now, went only to `.decision-log.md`. The added clause prints it once into an
    attended transcript, at the verdict's own moment rather than on the heartbeat
    cadence, without displacing the durable record.
  - `references/preflight.md`, "Launch briefing (interactive only)" - the screen
    an operator reads before crossing the autonomy line. It now says what the
    terminal health check does, honestly in both run modes, and it does that
    WITHOUT disturbing the five bullets already there.
  - `references/finalize.md`, gate trail - the detection-gated viewer affordance.

Two of the twins are FIXTURE-backed and were captured verbatim from the shipped
files BEFORE this story's edit landed, so the red they produce is a real pre-edit
state and not a hand-written strawman:

  - `fixtures/gate_run_the_gate_no_ticker.md` - records to `.decision-log.md`,
    prints nothing.
  - `fixtures/preflight_briefing_five_bullets.md` - the five-bullet briefing.

The third fixture, `fixtures/execute_ticker_line.md`, is a PRESERVATION snapshot,
not a twin: a ticker already ships in `references/execute.md` on the heartbeat
cadence, this story does not edit it, and the string compare here is what pins it
unchanged. The two lines fire on different clocks on purpose.

The remaining twins are in-process mutants, built by mutating the LIVE slice, so
each red is attributable to the one clause it removes.

STATED BOUND, and it is the whole scope of this module. Everything below is
static prose and source text. Nothing here runs a gate, renders a transcript, or
diffs two runs' artifacts. In particular the viewer-purity assertion proves only
that no `hunk` token reaches the artifact- and envelope-DEFINING surfaces; the
runtime half - that a viewer-present render leaves gate artifacts and the
envelope byte-identical - is proven separately, against a real invocation with a
stub viewer on PATH, in `test_ucg_status_renderer.py`. Neither claims the other's
half, and this module runs no two-run byte-diff.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_operator_comms_prose.py -v
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_GATE = _SKILL_ROOT / "references" / "gate.md"
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_FINALIZE = _SKILL_ROOT / "references" / "finalize.md"
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_ADAPTER = _SKILL_ROOT / "scripts" / "headless_envelope.py"

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_GATE_PRE_EDIT = _FIXTURES / "gate_run_the_gate_no_ticker.md"
_BRIEFING_PRE_EDIT = _FIXTURES / "preflight_briefing_five_bullets.md"
_TICKER_SNAPSHOT = _FIXTURES / "execute_ticker_line.md"

# The durable record the print must never displace, verbatim.
_RECORD_SENTENCE = (
    "Record the full verdict JSON and its `reasons` in `.decision-log.md` for this story."
)

# Ids that must never reach a shipped doc (this repo's plan-id hygiene rule).
_PLAN_ID = re.compile(r"\b(?:FR|AD|AC|NFR|INV)-\d+\b")

# Anchored at a word START only, not at both ends: `chunk` is not a hit, but
# `hunk_show` is - an identifier that embeds the viewer name is exactly the shape
# a leak into a machine surface takes, and a closing \b would miss it (`_` is a
# word character).
_HUNK = re.compile(r"\bhunk", re.I)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


envelope = _load("headless_envelope", _ADAPTER)


# --- generic slicing ---------------------------------------------------------


def _paragraphs(block: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", block) if p.strip()]


def _bullets(block: str) -> list[str]:
    return [line.strip() for line in block.splitlines() if line.startswith("- ")]


def _sentences(paragraph: str) -> list[str]:
    """Split on a period followed by whitespace.

    Safe over this prose because every in-word period here sits inside backticks
    (`gate_eval.py`, `.decision-log.md`, `run-result.json`) and is followed by a
    backtick rather than a space.
    """
    return [s for s in re.split(r"(?<=\.)\s+", paragraph) if s]


# --- surface slices ----------------------------------------------------------


def _gate_run_section(text: str | None = None) -> str:
    """`gate.md` from '## Run the gate' to '## Route on the verdict'.

    Accepts a fixture that is already exactly that slice (no trailing heading).
    """
    text = _GATE.read_text(encoding="utf-8") if text is None else text
    start = text.index("## Run the gate")
    try:
        end = text.index("## Route on the verdict", start)
    except ValueError:
        end = len(text)
    return text[start:end]


def _briefing_block(text: str | None = None) -> str:
    text = _PREFLIGHT.read_text(encoding="utf-8") if text is None else text
    start = text.index("### Launch briefing (interactive only)")
    try:
        end = text.index("## Progression", start)
    except ValueError:
        end = len(text)
    return text[start:end]


def _ticker_line(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("**Attended runs also get a ticker.**"):
            return line
    raise AssertionError("the execute.md heartbeat ticker sentence is missing")


def _kill_switch_bullet(block: str) -> str:
    hits = [b for b in _bullets(block) if b.startswith("- **Kill switch:**")]
    assert len(hits) == 1, f"expected exactly one kill-switch bullet, got {len(hits)}"
    return hits[0]


# --- the attended gate print --------------------------------------------------


def _print_paragraph(section: str) -> str:
    """The single paragraph instructing the transcript print, or '' if not exactly one.

    Returning '' for zero AND for two is deliberate: 'exactly one line' is not a
    property prose can hold if two paragraphs each order a print.
    """
    hits = [
        p
        for p in _paragraphs(section)
        if re.search(r"\bprints?\b", p, re.I) and "transcript" in p.lower()
    ]
    return hits[0] if len(hits) == 1 else ""


_CHECK_PRINT = "names a transcript print"
_CHECK_ATTENDED = "scopes the print to attended runs"
_CHECK_STORY_ID = "names the story id field"
_CHECK_GATE_STATUS = "names the gate_status field"
_CHECK_VERDICT = "names the routing verdict field"
_CHECK_ONE_LINE = "states the one-line-per-story bound"
_CHECK_MOMENT = "anchors the print to the verdict moment, not the heartbeat cadence"
_CHECK_ADDITIVE = "states the print is additive to the .decision-log.md record"
_CHECK_HEADLESS = "skips the print in headless"
_CHECK_RECORD = "keeps the .decision-log.md record sentence"

#: Every check that is about the PRINT itself. The record check is deliberately
#: excluded: the pre-edit fixture keeps that sentence, so a twin that reds on all
#: of these and none of that one is red for the missing print alone.
PRINT_CHECKS = (
    _CHECK_PRINT,
    _CHECK_ATTENDED,
    _CHECK_STORY_ID,
    _CHECK_GATE_STATUS,
    _CHECK_VERDICT,
    _CHECK_ONE_LINE,
    _CHECK_MOMENT,
    _CHECK_ADDITIVE,
    _CHECK_HEADLESS,
)


def _states_headless_skip(section: str) -> bool:
    """True only when the print paragraph itself carries the headless skip."""
    paragraph = _print_paragraph(section)
    if not paragraph:
        return False
    return bool(re.search(r"skip[^.]{0,80}headless\s*\(`-H`\)", paragraph, re.I))


def print_contract_failures(section: str) -> list[str]:
    """Every way a 'Run the gate' slice fails to pin the attended one-liner.

    Keys on the clauses, not on any whole-file property, so the same helper can be
    handed the pre-edit fixture and a headless-stripped mutant and must report the
    right findings for each.
    """
    found: list[str] = []
    paragraph = _print_paragraph(section)

    if not (re.search(r"\bprint\b", paragraph, re.I) and "transcript" in paragraph.lower()):
        found.append(_CHECK_PRINT)
    if not re.search(r"\battended\b", paragraph, re.I):
        found.append(_CHECK_ATTENDED)
    if not re.search(r"story id", paragraph, re.I):
        found.append(_CHECK_STORY_ID)
    if "`gate_status`" not in paragraph:
        found.append(_CHECK_GATE_STATUS)
    if not re.search(r"\bverdict\b", paragraph, re.I):
        found.append(_CHECK_VERDICT)
    if not (
        re.search(r"exactly\s+\*{0,2}one\*{0,2}\b", paragraph, re.I)
        and re.search(r"one line per story", paragraph, re.I)
    ):
        found.append(_CHECK_ONE_LINE)
    if not re.search(
        r"moment the verdict is formed|not on the heartbeat cadence", paragraph, re.I
    ):
        found.append(_CHECK_MOMENT)
    if not (
        re.search(r"\badditive\b", paragraph, re.I)
        and re.search(r"(never|not)\s+a\s+substitute", paragraph, re.I)
    ):
        found.append(_CHECK_ADDITIVE)
    if not _states_headless_skip(section):
        found.append(_CHECK_HEADLESS)
    if _RECORD_SENTENCE not in section:
        found.append(_CHECK_RECORD)
    return found


def test_gate_prints_one_line_verdict_attended():
    section = _gate_run_section()
    assert print_contract_failures(section) == []

    # The print is additive: the durable record sentence is still the one that
    # closes the surrounding paragraph, not something the print replaced.
    assert _RECORD_SENTENCE in section
    paragraph = _print_paragraph(section)
    assert _RECORD_SENTENCE not in paragraph, (
        "the record sentence must stay where it was, not be folded into the print clause"
    )

    # Plan-id hygiene over the added prose.
    assert _PLAN_ID.search(paragraph) is None, paragraph

    # No fan-out claim: the print is a sequential-spine surface, and the fan-out's
    # worktree agents share no transcript.
    assert not re.search(r"--parallel|fan-out|worktree", paragraph, re.I), paragraph


def test_pre_edit_gate_slice_fails_print_assertions():
    # Anti-vacuous twin, fixture-backed: the verbatim pre-edit slice records the
    # verdict to `.decision-log.md` and prints nothing. It must fail EVERY
    # print-specific check - set equality, so a fixture that reds on only some of
    # them (a partial edit sneaking in) is caught too.
    fixture = _gate_run_section(_GATE_PRE_EDIT.read_text(encoding="utf-8"))
    assert set(print_contract_failures(fixture)) == set(PRINT_CHECKS)


def test_pre_edit_gate_fixture_differs_only_by_print():
    # Twin integrity. An emptied or truncated fixture would red the assertions
    # above while proving nothing about the print, so pin what the fixture still
    # has: the record sentence and the invocation, verbatim.
    raw = _GATE_PRE_EDIT.read_text(encoding="utf-8")
    fixture = _gate_run_section(raw)
    assert _CHECK_RECORD not in print_contract_failures(fixture)
    assert _RECORD_SENTENCE in fixture
    assert "gate_eval.py --trace-output {workflow.trace_output_dir} --story <story_id>" in fixture
    assert "--profile light" in fixture and "--profile production" in fixture

    # It is a real slice of the shipped file, not a summary of one: everything in
    # the fixture is still present, byte-for-byte, in the live section. Only the
    # print paragraph was added on top.
    live = _gate_run_section()
    added = [p for p in _paragraphs(live) if p not in _paragraphs(fixture)]
    assert len(added) == 1, [p[:60] for p in added]
    assert added[0] == _print_paragraph(live)


# --- the launch briefing ------------------------------------------------------


def _states_health_check_dispositions(block: str) -> bool:
    """True only for a briefing bullet naming the check AND both run modes."""
    hits = [b for b in _bullets(block) if re.search(r"health check", b, re.I)]
    if len(hits) != 1:
        return False
    bullet = hits[0]
    terminal = re.search(r"terminal self-audit|terminal self-improvement", bullet, re.I)
    attended = re.search(r"attended[^.]{0,120}halt", bullet, re.I)
    headless = re.search(r"headless[^.]{0,140}queue[^.]{0,140}never block", bullet, re.I)
    return bool(terminal and attended and headless)


def test_briefing_gains_health_check_line_kill_switch_intact():
    live = _briefing_block()
    pre_edit = _briefing_block(_BRIEFING_PRE_EDIT.read_text(encoding="utf-8"))

    # (a) the health check is named, with both dispositions stated honestly.
    assert _states_health_check_dispositions(live)

    # (b) nothing was displaced: every pre-edit bullet survives byte-for-byte.
    assert len(_bullets(pre_edit)) == 5, _bullets(pre_edit)
    assert set(_bullets(pre_edit)) <= set(_bullets(live)), (
        set(_bullets(pre_edit)) - set(_bullets(live))
    )

    # (c) the kill-switch bullet is string-equal to its pre-edit text.
    assert _kill_switch_bullet(live) == _kill_switch_bullet(pre_edit)

    # The subsection is still interactive-only; the new bullets did not turn the
    # briefing into something headless reaches.
    assert "headless skips this subsection entirely" in live
    assert "Headless never reaches this subsection." in live

    # Plan-id hygiene over the added bullets.
    for bullet in set(_bullets(live)) - set(_bullets(pre_edit)):
        assert _PLAN_ID.search(bullet) is None, bullet


def test_pre_edit_briefing_fixture_lacks_health_check_bullet():
    # Anti-vacuous twin, fixture-backed and single-sourced: the SAME fixture must
    # fail (a) and pass (c). A twin that manufactured its red by mangling the
    # kill-switch text would break (c), so the red is attributable to the missing
    # health-check bullet alone.
    pre_edit = _briefing_block(_BRIEFING_PRE_EDIT.read_text(encoding="utf-8"))
    assert not _states_health_check_dispositions(pre_edit)
    assert not any(re.search(r"health check", b, re.I) for b in _bullets(pre_edit))
    assert _kill_switch_bullet(pre_edit) == _kill_switch_bullet(_briefing_block())


# --- headless prints neither transcript surface -------------------------------


def _without_headless_clause(section: str) -> str:
    """The live slice with the print paragraph's headless sentence removed.

    The print instruction itself survives - that is the point: an attended-blind
    print that would pollute a headless transcript.
    """
    paragraph = _print_paragraph(section)
    assert paragraph, "no print paragraph to mutate"
    kept = [s for s in _sentences(paragraph) if not re.search(r"headless|`-H`", s, re.I)]
    assert len(kept) < len(_sentences(paragraph)), "the mutant removed nothing"
    return section.replace(paragraph, " ".join(kept))


def test_headless_skips_both_transcript_surfaces():
    section = _gate_run_section()

    # (1) the new gate print carries its own headless skip.
    assert _states_headless_skip(section)

    # Authored twin: strip ONLY the headless half-sentence from the live slice.
    # Everything else about the print still holds, so the single finding is the
    # skip - which the pre-edit fixture could never show, having no print at all.
    mutant = _without_headless_clause(section)
    assert not _states_headless_skip(mutant)
    assert print_contract_failures(mutant) == [_CHECK_HEADLESS]

    # (2) the pre-existing heartbeat ticker in execute.md is untouched, headless
    # skip included. It fires on the heartbeat cadence, the new line fires at the
    # gate; they are not the same surface and this story edits neither into the
    # other.
    snapshot = _TICKER_SNAPSHOT.read_text(encoding="utf-8").rstrip("\n")
    assert "Skip the ticker in headless (`-H`)" in snapshot, (
        "the snapshot must itself carry the headless clause, or the compare proves nothing"
    )
    assert _ticker_line(_EXECUTE.read_text(encoding="utf-8")) == snapshot


# --- the detection-gated viewer affordance ------------------------------------


def _hunk_group_finalize() -> str:
    hits = [p for p in _paragraphs(_FINALIZE.read_text(encoding="utf-8")) if _HUNK.search(p)]
    return hits[0] if len(hits) == 1 else ""


def _hunk_group_briefing() -> str:
    hits = [b for b in _bullets(_briefing_block()) if _HUNK.search(b)]
    return hits[0] if len(hits) == 1 else ""


def hunk_affordance_failures(group: str) -> list[str]:
    """Every way a viewer mention fails to be detection-gated and silent when absent."""
    found: list[str] = []
    if not _HUNK.search(group or ""):
        return ["no viewer mention in a single sentence-group"]
    if not re.search(r"on PATH|which hunk|detected", group, re.I):
        found.append("no detection predicate")
    if not re.search(
        r"(absent|without|missing|not (installed|present|detected))[^.]{0,160}"
        r"(nothing is printed|print nothing|nothing printed|prints nothing)",
        group,
        re.I,
    ):
        found.append("no absent-case no-op clause")
    if not re.search(r"unchanged|exactly as (they|it) did before", group, re.I):
        found.append("no unchanged-behavior clause")
    for form in ("hunk show", "hunk diff"):
        if form not in group:
            found.append(f"missing command form: {form}")
    return found


def test_hunk_affordance_is_detection_gated():
    for label, group in (("finalize.md", _hunk_group_finalize()), ("briefing", _hunk_group_briefing())):
        assert hunk_affordance_failures(group) == [], (label, hunk_affordance_failures(group))
        assert _PLAN_ID.search(group) is None, (label, group)

    # It is detect-and-degrade, never a dependency: no preflight check, no
    # allowlist entry, no warning on absence.
    finalize_group = _hunk_group_finalize()
    assert re.search(r"do not add a preflight check", finalize_group, re.I)
    assert re.search(r"no warning", finalize_group, re.I)
    assert re.search(r"never checked for at launch", _hunk_group_briefing(), re.I)

    # Authored twin: the bare unconditional suggestion, which would print a broken
    # command on every machine without the viewer.
    mutant = "Use hunk show <commit> to review the story's diff."
    failures = hunk_affordance_failures(mutant)
    assert "no detection predicate" in failures, failures
    assert "no absent-case no-op clause" in failures, failures
    assert "missing command form: hunk diff" in failures, failures


# --- the viewer reaches no machine surface ------------------------------------


def _fenced_json(block: str, must_contain: str) -> str:
    hits = [b for b in re.findall(r"```json\n(.*?)```", block, re.S) if must_contain in b]
    assert len(hits) == 1, f"expected exactly one json block containing {must_contain!r}"
    return hits[0]


def _five_key_sentence() -> str:
    text = _FINALIZE.read_text(encoding="utf-8")
    hits = [p for p in _paragraphs(text) if "five-canonical-key shape" in p]
    assert len(hits) == 1, "expected exactly one five-canonical-key sentence"
    return hits[0]


def envelope_purity_failures(
    *, verdict_json: str, envelope_json: str, five_key_sentence: str, adapter_src: str
) -> list[str]:
    """Every way the viewer token could have leaked into an artifact/envelope definition."""
    found: list[str] = []
    for label, text in (
        ("gate.md verdict JSON", verdict_json),
        ("finalize.md envelope JSON", envelope_json),
        ("finalize.md five-key sentence", five_key_sentence),
        ("headless_envelope.py", adapter_src),
    ):
        if _HUNK.search(text):
            found.append(f"viewer token in {label}")
    keys = tuple(json.loads(envelope_json))
    if keys != envelope.CANONICAL_KEYS:
        found.append(f"envelope keys are {keys}, not the canonical {envelope.CANONICAL_KEYS}")
    return found


def test_hunk_absent_from_artifact_and_envelope_surfaces():
    verdict_json = _fenced_json(_gate_run_section(), '"verdict"')
    finalize_text = _FINALIZE.read_text(encoding="utf-8")
    envelope_json = _fenced_json(finalize_text, '"status": "complete"')
    adapter_src = _ADAPTER.read_text(encoding="utf-8")
    sentence = _five_key_sentence()

    assert envelope_purity_failures(
        verdict_json=verdict_json,
        envelope_json=envelope_json,
        five_key_sentence=sentence,
        adapter_src=adapter_src,
    ) == []

    # The shipped key set is exactly the five, with `reason` the documented sixth
    # on a blocked exit - unchanged by this story.
    assert envelope.CANONICAL_KEYS == (
        "status",
        "skill",
        "decision_log",
        "report",
        "deferred_work",
    )
    assert "`reason`" in sentence and "sixth" in sentence

    # The affordance DOES ship, in report prose - so the emptiness above is
    # attributable to keeping it out of the machine surfaces, not to the story
    # never having added it anywhere.
    assert _HUNK.search(finalize_text), "the viewer affordance must ship somewhere in finalize.md"

    # Authored twin: the convenience key, added to the envelope definition, with
    # the command a real leak would actually carry as its value.
    mutant = json.dumps(
        {**json.loads(envelope_json), "hunk_show": "hunk show <commit>"}, indent=1
    )
    failures = envelope_purity_failures(
        verdict_json=verdict_json,
        envelope_json=mutant,
        five_key_sentence=sentence,
        adapter_src=adapter_src,
    )
    assert "viewer token in finalize.md envelope JSON" in failures, failures
    assert any(f.startswith("envelope keys are") for f in failures), failures


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
