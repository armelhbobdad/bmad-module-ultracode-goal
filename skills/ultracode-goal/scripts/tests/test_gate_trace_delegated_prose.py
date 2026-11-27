#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for where trace runs and who writes the files that stand in for it.

`gate_eval.py` maps trace's `gate_status` to the verdict. Under `--light` that
is the whole verdict, and in production the NFR and test-review ANDs can only
lower it. The script reads the status as given and cannot tell who wrote the
file. 8.1.1 bound where a test review and an NFR assessment are written ("No test
review and no NFR assessment is written in your own context") and did not bind
`bmad-testarch-trace`, so a conductor could run trace, or write the two trace
files of the non-web section's fallback, in the context that holds every ruling
of the run. The line that opens the gate's assessors also said `gate_eval.py`
"consumes all three artifacts without caring how they were produced", which read
as leave to produce them any way at all.

`references/gate.md` now adds one sentence to that paragraph, right after the
refused-write route and before the hand-authored file: trace decides the verdict
first, so it is bound the same way, in either profile; each `bmad-testarch-trace`
run is delegated to such an agent (one started without this conversation, never
a fork, as the delegation sentence above it says); such an agent writes the two
trace files of the non-web section's fallback; no `gate_status` is changed in a
file trace or such an agent wrote; and each case below it (a session that cannot
start such an agent, TEA's execution-mode error, a session that cannot wait under
`sequential`) holds for trace as for an assessment, so the paragraph still names
no stop. The light route now runs trace "delegated as below", and the opening
line now says `gate_eval.py` reads the three as files and checks neither their
order nor their author, which is why the paragraphs below bind how each is made.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text without the change (gate.md as 8.1.1 shipped it, rebuilt from
the live text by undoing the three edits) and one-clause mutants it must reject.
test_gate_own_context_prose.py pins the paragraph whole, with this sentence in
it, and its stop-word check and the paragraph's other sentences are reused here,
so both files pin one text. The claim about the verdict is checked against
`gate_eval.py`'s own statement of its mapping, and the claim that each case holds
for trace against the tracked reference skill under `skf-skills/tea-testarch/`
(the installed skills under `.claude/skills/` are not tracked, so no test reads
them): trace's step 4 resolves `tea_execution_mode` and `tea_capability_probe`
the way test review's step 3 and the NFR audit's step 4 do.

Stated limits: this is a presence proof over prose. It shows the instruction is
in the files, not that a conductor obeys it, that an agent it starts can or
cannot start agents, or that TEA behaves as its reference says. The tracked
reference cites its sentence that sequential mode runs each worker to completion
to ATDD's and automate's steps only, so the wait case's reason is checked for
trace only as far as that sentence stands in the shared section that names
trace's step 4. That `gate_eval.py` checks neither order nor author is a
negative: the test checks only that the script takes the three as a directory
and two paths and names no provenance and no file time, which a check of either
would have to add.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_REFERENCES = _SKILL_ROOT / "references"
GATE = (_REFERENCES / "gate.md").read_text(encoding="utf-8")
GATE_EVAL = (_SKILL_ROOT / "scripts" / "gate_eval.py").read_text(encoding="utf-8")


def _own_context_pins():
    """test_gate_own_context_prose.py, loaded under its own name, for the
    paragraph's other sentences and its stop-word check."""
    path = Path(__file__).with_name("test_gate_own_context_prose.py")
    spec = importlib.util.spec_from_file_location("ucg_own_context_prose_pins_for_trace", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_PINS = _own_context_pins()

_HEAD = _PINS._HEAD
_REVIEW_HEAD = _PINS._REVIEW_HEAD
_NFR_HEAD = _PINS._NFR_HEAD
_WHY = _PINS._WHY
_DELEGATE = _PINS._DELEGATE
_ANTECEDENT = _PINS._DELEGATES + _PINS._FRESH
_REFUSED = _PINS._REFUSED
_HAND_AUTHORED = _PINS._HAND_AUTHORED
_NO_AGENT = _PINS._NO_AGENT
_MODE_CASE = _PINS._MODE_CASE
_WAIT_CASE = _PINS._WAIT_CASE
_LOGGED = _PINS._LOGGED


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def _backfill_section(text: str = GATE) -> str:
    return _section(text, "## Backfill the gate evidence")


def _paragraph(text: str, opener: str) -> str:
    """The paragraph that opens with `opener`, or "" when `text` has none."""
    start = text.find(opener)
    if start == -1:
        return ""
    end = text.find("\n\n", start)
    return text[start : end if end != -1 else len(text)]


def _rule(text: str = GATE) -> str:
    return _paragraph(_backfill_section(text), _HEAD)


# The trace sentence, clause by clause. Each predicate below keys on one clause.
_TRACE_OPENER = "Trace decides the verdict first"
_EITHER_PROFILE = _TRACE_OPENER + ", so it is bound the same way, in either profile:"
_DELEGATE_TRACE = " delegate each `bmad-testarch-trace` run to such an agent,"
_FALLBACK_FILES = (
    " have one write each trace file the non-web section has you author (the epic pair, and an `e2e-trace-summary` "
    "written instead, included),"
)
_NO_STATUS = " and change no `gate_status` in a file trace or such an agent wrote;"
_CASES = " the route above and each case below hold for trace as for an assessment."
_TRACE = _EITHER_PROFILE + _DELEGATE_TRACE + _FALLBACK_FILES + _NO_STATUS + _CASES

# The opening line of the gate's assessors, before and after.
_LICENCE = (
    "`gate_eval.py` reads the three as files and checks neither their order nor their author, which is why the "
    "paragraphs below bind how each is made."
)
_OLD_LICENCE = "`gate_eval.py` consumes all three artifacts without caring how they were produced."
_LIGHT_ROUTE = (
    "In **`--light`**, skip all of the above and run only `bmad-testarch-trace`, delegated as the paragraph after the "
    "NFR assessor's says, then the gate with `--profile light` (trace gate only, with no NFR/review AND)."
)
_OLD_LIGHT_ROUTE = _LIGHT_ROUTE.replace(", delegated as the paragraph after the NFR assessor's says,", ",")


def _undo(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, f"the live text must hold this exactly once: {old!r}"
    return text.replace(old, new, 1)


def _pre_edit_gate() -> str:
    """gate.md without the change: the trace sentence cut, the opening line and
    the light route as 8.1.1 shipped them."""
    text = _undo(GATE, " " + _TRACE, "")
    text = _undo(text, _LICENCE, _OLD_LICENCE)
    return _undo(text, _LIGHT_ROUTE, _OLD_LIGHT_ROUTE)


def _trace_sentence(rule: str) -> str:
    """The sentence that opens with "Trace decides the verdict first", or ""."""
    flat = _flat(rule)
    start = flat.find(_TRACE_OPENER)
    if start == -1:
        return ""
    end = flat.find(". ", start)
    return flat[start : end + 1 if end != -1 else len(flat)].strip()


def _mutant(old: str, new: str) -> str:
    rule = _flat(_rule())
    mutant = rule.replace(old, new)
    assert mutant != rule, "the mutant must actually change the text"
    return mutant


def _gate_mutant(old: str, new: str) -> str:
    mutant = GATE.replace(old, new)
    assert mutant != GATE, "the mutant must actually change the text"
    return mutant


def test_the_sentence_is_the_one_the_whole_paragraph_pin_holds():
    """test_gate_own_context_prose.py pins the paragraph whole with this sentence
    in it, so these predicates and that pin hold one text."""
    assert _PINS._TRACE == _TRACE
    assert _PINS._rule_is_whole(_rule())
    assert _trace_sentence(_rule()) == _TRACE


def test_the_pre_edit_text_is_gate_md_without_the_three_edits():
    pre = _pre_edit_gate()
    assert _TRACE_OPENER not in pre
    assert _OLD_LICENCE in pre and _LICENCE not in pre
    assert _OLD_LIGHT_ROUTE in pre and _LIGHT_ROUTE not in pre
    # The 8.1.1 paragraph: the refused-write route runs straight into the hand-authored file.
    assert (_REFUSED + " " + _HAND_AUTHORED) in _flat(_rule(pre))


# --- the sentence sits between the refused-write route and the hand-authored file


def _sits_between_the_route_and_the_hand_authored_file(rule: str) -> bool:
    """The trace sentence, once, directly follows the refused-write route, which
    follows the three bans, and directly precedes the hand-authored file, so the
    cases after it read on from it."""
    flat = _flat(rule)
    sentence = _trace_sentence(rule)
    if not sentence or flat.count(_TRACE_OPENER) != 1:
        return False
    return (_REFUSED + " " + sentence + " " + _HAND_AUTHORED) in flat


def test_the_trace_sentence_sits_after_the_refused_write_route_and_before_the_hand_authored_file():
    assert _sits_between_the_route_and_the_hand_authored_file(_rule())


def test_placement_predicate_rejects_the_text_without_the_sentence():
    assert not _sits_between_the_route_and_the_hand_authored_file(_rule(_pre_edit_gate()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_REFUSED + " " + _TRACE, _TRACE + " " + _REFUSED, id="before-the-route"),
        pytest.param(_TRACE + " " + _HAND_AUTHORED, _HAND_AUTHORED + " " + _TRACE, id="after-the-hand-authored-file"),
        pytest.param(_WHY + " " + _DELEGATE, _WHY + " " + _TRACE + " " + _DELEGATE, id="also-after-the-why"),
        pytest.param(
            _TRACE + " " + _HAND_AUTHORED + " " + _NO_AGENT + " " + _MODE_CASE + " " + _WAIT_CASE + " " + _LOGGED,
            _HAND_AUTHORED + " " + _NO_AGENT + " " + _MODE_CASE + " " + _WAIT_CASE + " " + _LOGGED + " " + _TRACE,
            id="after-the-log",
        ),
    ],
)
def test_placement_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _sits_between_the_route_and_the_hand_authored_file(_mutant(old, new))


# --- it binds trace in either profile -------------------------------------------


def _binds_trace_in_either_profile(rule: str) -> bool:
    """The sentence says why trace is bound (it decides the verdict first), that
    it is bound as the assessments are, and that this holds in either profile,
    the light one included, where trace is the whole gate."""
    return _trace_sentence(rule).startswith(_EITHER_PROFILE + _DELEGATE_TRACE)


def test_the_rule_binds_trace_in_either_profile():
    assert _binds_trace_in_either_profile(_rule())


def test_profile_predicate_rejects_the_text_without_the_sentence():
    assert not _binds_trace_in_either_profile(_rule(_pre_edit_gate()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("in either profile:", "in production:", id="production-only"),
        pytest.param("in either profile:", "under `--light`:", id="light-only"),
        pytest.param(", in either profile:", ":", id="profile-unstated"),
        pytest.param("so it is bound the same way", "so it may be bound the same way", id="optional"),
        pytest.param("so it is bound the same way", "so it is bound more loosely", id="looser"),
        pytest.param(_TRACE_OPENER + ",", "Trace runs last,", id="reason-changed"),
    ],
)
def test_profile_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _binds_trace_in_either_profile(_mutant(old, new))


def test_trace_s_status_decides_the_verdict_first():
    """The reason the sentence gives, from `gate_eval.py`'s statement of its own
    mapping: it reads trace's `gate_status` as given, that status is the whole
    decision under `--light`, and in production the two ANDs only downgrade an
    otherwise-advance verdict."""
    script = _flat(GATE_EVAL)
    assert "here we read gate_status as given." in script
    assert "light -> the trace gate is the whole decision." in script
    assert (
        "production -> additionally AND two signals; any failure downgrades an otherwise-advance verdict to reloop "
        "(never below"
    ) in script


# --- each trace run is delegated to such an agent --------------------------------


def _delegates_each_trace_run(rule: str) -> bool:
    """Each trace run, not the first or the gate's alone, goes to "such an agent",
    and the delegation sentence that gives "such an agent" its kind (started for
    that one job, without this conversation, never a fork) stands before it."""
    sentence = _trace_sentence(rule)
    if not sentence or (_EITHER_PROFILE + _DELEGATE_TRACE) not in sentence:
        return False
    flat = _flat(rule)
    return _ANTECEDENT in flat and flat.index(_ANTECEDENT) < flat.index(sentence)


def test_each_trace_run_is_delegated_to_such_an_agent():
    assert _delegates_each_trace_run(_rule())


def test_delegation_predicate_rejects_the_text_without_the_sentence():
    assert not _delegates_each_trace_run(_rule(_pre_edit_gate()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(" delegate each `bmad-testarch-trace` run", " you may delegate each `bmad-testarch-trace` run",
                     id="optional"),
        pytest.param("delegate each `bmad-testarch-trace` run", "delegate the first `bmad-testarch-trace` run",
                     id="first-run-only"),
        pytest.param("delegate each `bmad-testarch-trace` run to such an agent", "run `bmad-testarch-trace` yourself",
                     id="own-context"),
        pytest.param("run to such an agent,", "run to an agent,", id="an-agent-of-any-kind"),
        pytest.param("run to such an agent,", "run to a fork,", id="a-fork"),
        pytest.param("run to such an agent,", "run to the agent that wrote the test review,", id="a-shared-agent"),
        # "Such an agent" loses the kind the delegation sentence gave it.
        pytest.param("," + _PINS._FRESH, ":", id="antecedent-loses-its-kind"),
        # The sentence moved ahead of the one that gives "such an agent" its kind.
        pytest.param(
            _DELEGATE + " " + _REFUSED + " " + _TRACE,
            _TRACE + " " + _DELEGATE + " " + _REFUSED,
            id="before-the-delegation-sentence",
        ),
    ],
)
def test_delegation_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _delegates_each_trace_run(_mutant(old, new))


# --- such an agent writes each trace file the non-web section has you author -------

_TWO_FILES = "The two trace files described next are the fallback for when trace halts or cannot run"
# The two other trace files that section has you author: the summary written in place of the slim decision, and the
# epic's own pair where the roll-up cannot be given sprint-status.
_SUMMARY_INSTEAD = "If you instead write the always-present `e2e-trace-summary.json`"
_EPIC_PAIR = "hand-author the same two files named for the epic id"
_NONWEB_HEAD = "## Non-web stack"


def _agent_writes_the_fallback_files(rule: str, text: str = GATE) -> bool:
    """Where trace cannot run, "one" (such an agent, from the clause before) writes
    each trace file the non-web section has you author, and that section does
    describe the two trace files of the fallback, the summary written instead and
    the epic pair the clause names."""
    if (_DELEGATE_TRACE + _FALLBACK_FILES) not in _trace_sentence(rule):
        return False
    nonweb = _flat(_section(text, _NONWEB_HEAD))
    return all(phrase in nonweb for phrase in (_TWO_FILES, _SUMMARY_INSTEAD, _EPIC_PAIR))


def test_such_an_agent_writes_the_two_trace_files_of_the_non_web_fallback():
    assert _agent_writes_the_fallback_files(_rule())
    # The two files the fallback names, each with its own shape below it.
    nonweb = _section(GATE, _NONWEB_HEAD)
    assert "\n**`trace-<id>.md`** " in nonweb
    assert "\n**`gate-decision-<id>.json`** " in nonweb


def test_fallback_predicate_rejects_the_text_without_the_sentence():
    pre = _pre_edit_gate()
    assert not _agent_writes_the_fallback_files(_rule(pre), pre)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(" have one write each trace file", " write each trace file", id="conductor-writes-them"),
        pytest.param("have one write", "have any agent write", id="an-agent-of-any-kind"),
        pytest.param("each trace file the non-web", "the trace report the non-web", id="report-only"),
        pytest.param("each trace file the non-web", "the gate decision the non-web", id="decision-only"),
        pytest.param(_FALLBACK_FILES, "", id="dropped"),
        # "One" no longer follows the clause that names such an agent.
        pytest.param(_DELEGATE_TRACE + _FALLBACK_FILES, _FALLBACK_FILES + _DELEGATE_TRACE, id="before-such-an-agent"),
    ],
)
def test_fallback_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _agent_writes_the_fallback_files(_mutant(old, new))


def test_fallback_predicate_rejects_a_non_web_section_without_the_two_files():
    moved = _gate_mutant(_TWO_FILES, "The trace report described next is the fallback for when trace halts or cannot run")
    assert not _agent_writes_the_fallback_files(_rule(moved), moved)


# --- no gate_status is changed in a file trace or such an agent wrote -----------


def _changes_no_gate_status(rule: str) -> bool:
    """The conductor changes no `gate_status` in a file either writer made: trace
    itself, or the agent that wrote the fallback's two files."""
    return _NO_STATUS in _trace_sentence(rule)


def test_no_gate_status_is_changed_in_a_file_trace_or_such_an_agent_wrote():
    assert _changes_no_gate_status(_rule())
    # The field named is the one the verdict reads from either trace file.
    assert "`gate_status` alone drives the `--light` verdict" in _flat(_section(GATE, _NONWEB_HEAD))


def test_status_predicate_rejects_the_text_without_the_sentence():
    assert not _changes_no_gate_status(_rule(_pre_edit_gate()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("change no `gate_status`", "change no `p0_status`", id="another-field"),
        pytest.param("in a file trace or such an agent wrote;", "in a file trace wrote;", id="agent-file-editable"),
        pytest.param("in a file trace or such an agent wrote;", "in a file such an agent wrote;",
                     id="trace-file-editable"),
        pytest.param("and change no `gate_status`", "and change a `gate_status` only on a ruling",
                     id="ruling-may-change-it"),
        pytest.param("such an agent wrote;", "such an agent wrote, unless an operator note lifts it;",
                     id="a-note-may-lift-it"),
        pytest.param(_NO_STATUS, ";", id="dropped"),
    ],
)
def test_status_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _changes_no_gate_status(_mutant(old, new))


# --- each case below holds for trace as for an assessment ------------------------


def _cases_hold_for_trace(rule: str) -> bool:
    """The sentence ends by carrying each case after it over to trace, and those
    cases (no such agent, TEA's mode error, a session that cannot wait under
    `sequential`) do stand below it, in that order, with the log sentence that
    covers each closing the paragraph."""
    sentence = _trace_sentence(rule)
    if not sentence.endswith(_NO_STATUS + _CASES):
        return False
    flat = _flat(rule)
    start = flat.index(sentence)
    positions = [flat.find(case, start) for case in (_NO_AGENT, _MODE_CASE, _WAIT_CASE)]
    return -1 not in positions and positions == sorted(positions) and flat.strip().endswith(_LOGGED)


def test_each_case_below_holds_for_trace():
    assert _cases_hold_for_trace(_rule())


def test_cases_predicate_rejects_the_text_without_the_sentence():
    assert not _cases_hold_for_trace(_rule(_pre_edit_gate()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("each case below hold", "no case below hold", id="no-case"),
        pytest.param("each case below hold", "the first case below hold", id="first-case-only"),
        pytest.param("hold for trace as for an assessment.", "hold for an assessment only.", id="assessments-only"),
        pytest.param("each case below hold", "each case above hold", id="cases-above"),
        pytest.param(";" + _CASES, ".", id="dropped"),
        # The sentence moved after the cases it speaks of.
        pytest.param(
            _TRACE + " " + _HAND_AUTHORED + " " + _NO_AGENT + " " + _MODE_CASE + " " + _WAIT_CASE,
            _HAND_AUTHORED + " " + _NO_AGENT + " " + _MODE_CASE + " " + _WAIT_CASE + " " + _TRACE,
            id="after-the-cases",
        ),
        pytest.param(" " + _MODE_CASE, "", id="mode-case-gone"),
        pytest.param(" " + _WAIT_CASE, "", id="wait-case-gone"),
    ],
)
def test_cases_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _cases_hold_for_trace(_mutant(old, new))


def _tea_reference() -> Path:
    """The tracked reference skill for the TEA version this module targets."""
    group = _REPO / "skf-skills" / "tea-testarch"
    active = group / "active"
    version = active.resolve().name if active.is_dir() else active.read_text(encoding="utf-8").strip()
    return group / version / "tea-testarch"


def test_trace_resolves_tea_s_execution_mode_as_the_assessments_do():
    """The fact the mode case rests on for trace: TEA resolves the mode and the
    probe in trace's step 4 the way it does in test review's step 3 and the NFR
    audit's step 4, so a delegated trace can end in the same error; and the
    sentence the wait case's reason rests on stands in that same shared section
    (its citations are ATDD's and automate's: see the stated limit)."""
    tea = _tea_reference()
    shared_text = (tea / "references" / "pattern-atdd-and-automate.md").read_text(encoding="utf-8")
    shared = _flat(_section(shared_text, "## Shared execution-mode resolution"))
    assert (
        "NFR step 4, test-review step 3 and trace step 4 resolve `tea_execution_mode` (default `auto`) and "
        "`tea_capability_probe` (default `true`) the same way:"
    ) in shared
    assert "with probing off an unexecutable mode fails with an explicit error." in shared
    assert "Parallel modes launch workers non-blocking; sequential runs each to completion." in shared
    trace = _flat((tea / "references" / "pattern-gate-decision.md").read_text(encoding="utf-8"))
    assert "Step 4 reads `tea_execution_mode` (default `auto`: agent-team, else subagent, else sequential)" in trace


# --- the paragraph still names no stop -------------------------------------------


def _trace_adds_no_stop(rule: str) -> bool:
    """The paragraph holds the trace sentence and, with it, still names no stop of
    any kind, by the stop-word check test_gate_own_context_prose.py applies."""
    return bool(_trace_sentence(rule)) and _PINS._adds_no_stop(rule)


def test_the_paragraph_with_the_trace_sentence_names_no_stop():
    assert _trace_adds_no_stop(_rule())
    assert _PINS._STOP_WORDS.search(_TRACE) is None


def test_no_stop_predicate_rejects_the_text_without_the_sentence():
    assert not _trace_adds_no_stop(_rule(_pre_edit_gate()))


@pytest.mark.parametrize(
    "stop",
    [
        pytest.param(" a trace no agent can run escalates the story.", id="escalates"),
        pytest.param(" a trace no agent can run halts the run.", id="halts"),
        pytest.param(" a trace no agent can run parks the story.", id="parks"),
        pytest.param(" a trace no agent can run blocks the story.", id="blocks"),
        pytest.param(" a trace no agent can run re-loops the story.", id="re-loops"),
        pytest.param(" the run waits for the operator before trace.", id="waits"),
        pytest.param(" a trace no agent can run pauses the run.", id="pauses"),
        pytest.param(" a trace no agent can run aborts the run.", id="aborts"),
        pytest.param(" a trace no agent can run ends the run.", id="ends-the-run"),
        pytest.param(" a trace no agent can run stops the run.", id="stops"),
    ],
)
def test_no_stop_predicate_rejects_a_stop_in_the_trace_sentence(stop):
    assert not _trace_adds_no_stop(_mutant(_CASES, stop))


# --- the light route points at the rule below ------------------------------------


def _light_route_points_below(text: str = GATE) -> bool:
    """The light profile's one step runs trace "delegated as below", and below it,
    in the same section, stands the paragraph whose trace sentence delegates each
    trace run in either profile, the light one included."""
    section = _flat(_backfill_section(text))
    if section.count(_LIGHT_ROUTE) != 1:
        return False
    rule = _rule(text)
    if not rule or not _binds_trace_in_either_profile(rule):
        return False
    return section.index(_LIGHT_ROUTE) < section.index(_flat(rule))


def test_the_light_route_runs_trace_delegated_as_below():
    assert _light_route_points_below()


def test_light_route_predicate_rejects_the_text_without_the_change():
    assert not _light_route_points_below(_pre_edit_gate())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(", delegated as the paragraph after the NFR assessor's says, then", ", then", id="dropped"),
        pytest.param("the paragraph after the NFR assessor's says", "the paragraph before the reviewer's says", id="points-above"),
        pytest.param(", delegated as the paragraph after the NFR assessor's says, then", " yourself, then", id="yourself"),
        pytest.param(", delegated as the paragraph after the NFR assessor's says, then", ", delegated where you can, then", id="where-you-can"),
        # The rule below no longer covers the light profile.
        pytest.param("so it is bound the same way, in either profile:", "so it is bound the same way, in production:",
                     id="rule-below-binds-production-only"),
    ],
)
def test_light_route_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _light_route_points_below(_gate_mutant(old, new))


def test_light_route_predicate_rejects_the_rule_moved_above_it():
    rule = _rule()
    without = GATE.replace(rule + "\n\n", "", 1)
    opener = "`bmad-testarch-nfr` (produces `nfr-assessment.md`)"
    assert without != GATE and without.count("\n" + opener) == 1
    moved = without.replace("\n" + opener, "\n" + rule + "\n\n" + opener, 1)
    assert _flat(_rule(moved)) == _flat(rule)
    assert not _light_route_points_below(moved)


# --- the opening line no longer licenses any author ------------------------------


def _licence_withdrawn(text: str = GATE) -> bool:
    """The opening line says `gate_eval.py` reads the three as files and checks
    neither their order nor their author, which is why the paragraphs below bind
    how each is made; those paragraphs (the reviewer's, the NFR assessor's and
    the one that binds who writes each, trace included) stand below it, in that
    order; and the old "without caring how they were produced" is nowhere in
    gate.md."""
    flat = _flat(text)
    if "without caring" in flat or "consumes all three artifacts" in flat:
        return False
    section = _flat(_backfill_section(text))
    start = section.find(_LICENCE)
    if start == -1:
        return False
    positions = [section.find(head, start) for head in (_REVIEW_HEAD, _NFR_HEAD, _HEAD)]
    return -1 not in positions and positions == sorted(positions)


def test_the_opening_line_says_what_the_script_does_not_check():
    assert _licence_withdrawn()
    assert GATE.count(_LICENCE) == 1


def test_licence_predicate_rejects_the_text_without_the_change():
    assert not _licence_withdrawn(_pre_edit_gate())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_LICENCE, _LICENCE + " " + _OLD_LICENCE, id="old-licence-kept-beside"),
        pytest.param("checks neither their order nor their author", "checks their author", id="author-checked"),
        pytest.param(" nor their author", "", id="author-unstated"),
        pytest.param(", which is why the paragraphs below bind how each is made.", ".", id="why-dropped"),
        pytest.param("which is why the paragraphs below bind", "which is why the paragraphs above bind",
                     id="paragraphs-above"),
        pytest.param("## Run the gate\n", "## Run the gate\n\n" + _OLD_LICENCE + "\n", id="old-licence-elsewhere"),
        pytest.param("## Run the gate\n",
                     "## Run the gate\n\n`gate_eval.py` reads trace's files without caring who wrote them.\n",
                     id="licence-reworded-elsewhere"),
    ],
)
def test_licence_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _licence_withdrawn(_gate_mutant(old, new))


def test_licence_predicate_rejects_a_binding_paragraph_moved_above_the_line():
    review = _paragraph(GATE, _REVIEW_HEAD)
    without = GATE.replace(review + "\n\n", "", 1)
    moved = without.replace("## Backfill the gate evidence", review + "\n\n## Backfill the gate evidence", 1)
    assert moved != without and moved.count(_REVIEW_HEAD) == 1
    assert not _licence_withdrawn(moved)


def test_gate_eval_takes_the_three_as_files_and_names_no_author_or_file_time():
    """What the opening line says of the script, as far as a text check reaches:
    it takes trace's artifacts as a directory and the NFR assessment and the test
    review as paths, and its source names no provenance and no file time, so
    neither an author nor an order is read (a check of either would have to add
    one of those, and this test would see it)."""
    assert '"--trace-output", required=True, help="Directory holding the trace gate artifacts."' in GATE_EVAL
    flat = _flat(GATE_EVAL)
    assert "help=\"PATH to the story's nfr-assessment markdown" in flat
    assert "help=\"PATH to the story's test-review markdown" in flat
    assert "provenance" not in GATE_EVAL
    assert "mtime" not in GATE_EVAL
