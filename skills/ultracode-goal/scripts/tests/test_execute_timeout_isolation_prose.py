#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for a sweep timeout that passes in isolation (issue #251).

`references/execute.md` step 2's loaded-machine paragraph read a timeout in a
wide sweep as "not yet a red: re-run that package in isolation before treating
it as one", then stopped. It never said what a passing isolation run leaves:
whether the sweep is its step's green, which sweep the marker comes from, what
record the run owes, or where the isolation run is captured. Only the second
sweep of the unexplained-red route (#213) ruled the case, and step 5 and the
gate's backfill sweep point back at this paragraph, so all of them inherited
the gap.

The paragraph now says: each isolation run runs once, on its own (one package
at a time, with no other suite or build the run started), at the same tree,
unchanged, cache-defeated, with the test command and time bound the sweep gave
the package; the sweep's capture is kept and the isolation run is captured in
`evidence-<story_id>/` under an `isolation-` stem, never a `sweep-` one, so
gate.md's "numbered capture of its second sweep" cannot pick it up; a pass puts
no red in that sweep, so a sweep that ran every task it scheduled and whose
only reds were such timeouts is its step's green; step 2 and the gate steps
that write a marker after their sweep write it from that sweep, and at step 5
the marker stands with nothing committed; each such pass logs one `timeout:`
line in `.decision-log.md` naming the package, the `HEAD` the sweep ran at and
both captures; the timeout owes no `flaky:` line and no deferred-work row,
since host contention is not deferred work; a sweep that left tasks unrun and
whose only reds were timeouts runs once more with every task run, before any
isolation run, and is read instead, no fix at the gate's backfill; and a
package that fails in isolation too makes the timeout that sweep's red. The
line's old em dash is reworded.

Its review added: the same-tree, cache-defeated, same-bound isolation run (a
raised bound, an edited test or, at step 5, a runner replaying step 2's cached
green would otherwise clear the timeout), and the plural wording that rules a
sweep where contention timed out several packages. Its second review added: one
attempt, one package at a time (a retry until it passes clears a recurring
timeout, a crowded run brings the contention back), and the proviso that the
sweep ran every task it scheduled (a runner that stops at its first failure
leaves packages unrun, and the sweep would otherwise read green over them). Its
third review added the route for a sweep that left tasks unrun, which the
proviso had left neither green nor red; its fourth limited that route to a
sweep whose only reds were timeouts, ran it before any isolation run, and bound
"on its own" to what the run started, which is all it controls.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the paragraph as it stood before #251 (a reconstruction checked
against its pinned text) and against a one-clause mutant it must reject.
Stated limit: this is a presence proof over prose. It shows the instruction is
in the file, not that an executor obeys it.

Stdlib + pytest only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_GATE = _SKILL_ROOT / "references" / "gate.md"

_EM_DASH = chr(0x2014)
_LOADED_HEAD = "**A wide sweep is also a loaded machine.**"
_ISOLATION_SENTENCE = (
    "A timeout in a wide sweep is therefore not yet a red: re-run that package in isolation before treating it as one"
)
_LAST_PRE_EDIT_SENTENCE_END = "do not schedule a long native build beside a wall-clock-bounded suite."
_REWORDED = "concurrent native builds, and a case bounded"
_PRE_EDIT_DASH = "concurrent native builds " + _EM_DASH + " and a case bounded"
# The paragraph as origin/main carried it before #251, em dash included.
_PRE_EDIT_PARAGRAPH = (
    "**A wide sweep is also a loaded machine.** Running every language's suite plus the declared gate set, "
    "cache-defeating, means suites share a host with concurrent native builds " + _EM_DASH + " and a case bounded "
    "by a wall-clock timeout can fail from contention alone (measured: a 180-second-bounded case took 197s beside a "
    "concurrent `cargo test` + clippy + type-check, and 93s alone). A timeout in a wide sweep is therefore not yet a "
    "red: re-run that package in isolation before treating it as one, and where the two can be sequenced, do not "
    "schedule a long native build beside a wall-clock-bounded suite."
)
_SAME_RUN_SENTENCE_HEAD = "Run each isolation run once, on its own"
_PASS_SENTENCE_HEAD = "When that package then passes in isolation, the timeout puts no red in that sweep"
_LOG_SENTENCE_HEAD = "For each such pass, log one `timeout:` line in `.decision-log.md`"
_UNRUN_SENTENCE_HEAD = "A sweep that left tasks unrun"
_FAIL_SENTENCE_HEAD = "When that package fails in isolation too"
# The two gate.md steps the paragraph names as writing a marker after their sweep.
_GATE_BACKFILL_STEP3 = " 3. Once the sweep is green"
_GATE_CAP_ONLY_REFRESH = (
    "re-run the full three-axis sweep where the sweep cap fired and refresh the marker with `scope=full`"
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _execute() -> str:
    return _EXECUTE.read_text(encoding="utf-8")


def _gate() -> str:
    return _GATE.read_text(encoding="utf-8")


def _step2(text: str) -> str:
    start = text.index("\n2. ")
    return text[start : text.index("\n3. ", start)]


def _step5(text: str) -> str:
    start = text.index("\n5. **Re-verify on the committed HEAD.**")
    return text[start : text.index("\n\n", start)]


def _paragraph(text: str) -> str:
    """The loaded-machine paragraph, from its bold head to the blank line after it."""
    if _LOADED_HEAD not in text:
        return ""
    start = text.index(_LOADED_HEAD)
    end = text.find("\n\n", start)
    return text[start:] if end == -1 else text[start:end]


# --- the pre-edit text: the live text with the #251 wording taken out ----------


def _execute_pre_edit(text: str) -> str:
    """execute.md as it stood before #251: the paragraph ends at its scheduling
    advice, and its em dash is back."""
    paragraph = _paragraph(text)
    end = paragraph.index(_LAST_PRE_EDIT_SENTENCE_END) + len(_LAST_PRE_EDIT_SENTENCE_END)
    pre = paragraph[:end].replace(_REWORDED, _PRE_EDIT_DASH, 1)
    return text.replace(paragraph, pre, 1)


def test_the_pre_edit_text_is_a_real_reconstruction():
    """The twins below must red for the right reason: the reconstruction gives
    back the pinned pre-#251 paragraph and leaves the rest of the file whole."""
    live = _execute()
    pre = _execute_pre_edit(live)
    assert _paragraph(pre) == _PRE_EDIT_PARAGRAPH
    assert live.replace(_paragraph(live), "", 1) == pre.replace(_PRE_EDIT_PARAGRAPH, "", 1)


# --- the rule's clauses ------------------------------------------------------------


def _isolation_run_is_the_same_run(paragraph: str) -> bool:
    """The isolation run tests the code the sweep tested, under the bound the
    sweep set, once and with nothing else the run started beside it (the run
    controls nothing more on the host): a raised bound, an edited
    test, a cached green (at step 5 a commit leaves the cache key as step 2 left
    it) or a retry until it passes proves nothing."""
    return (
        _SAME_RUN_SENTENCE_HEAD + " (one package at a time, with no other suite or build this run started still "
        "running), at the same tree, "
        "changing nothing between the sweep and it, cache-defeated, with the test command and time bound the sweep "
        "gave that package: a raised bound, an edited test, a cached result or a second attempt proves nothing about "
        "contention."
    ) in _flat(paragraph)


def _captures_the_isolation_run(paragraph: str) -> bool:
    """Both captures go to the evidence folder, the isolation run under a stem
    of its own, named as the evidence rule names a capture."""
    return (
        "Keep that sweep's capture in `evidence-<story_id>/`, and capture the isolation run there too as "
        "`isolation-<step>-<short sha>.log`, named by the step whose sweep timed out and the `HEAD` that sweep ran at "
        "(`isolation-step2-<short sha>.log`, `isolation-step5-<short sha>.log`, `isolation-backfill-<short sha>.log`), "
        "a name already taken getting the next free number (\"Evidence never goes in scratch\", above)"
    ) in _flat(paragraph)


def _keeps_the_isolation_stem_apart(paragraph: str) -> bool:
    """gate.md's scoped backfill accepts "the numbered capture of its second
    sweep": a one-package run must never pass for one."""
    return "its stem is not `sweep-`, so it is never read as the numbered capture of a second sweep." in _flat(
        paragraph
    )


def _a_pass_leaves_the_step_green(paragraph: str) -> bool:
    """Each timeout whose package passes alone puts no red in the sweep, so a
    sweep where contention timed out several packages is green once all pass,
    and only when it ran every task it scheduled."""
    return (
        _PASS_SENTENCE_HEAD + ", so a sweep that ran every task it scheduled and whose only reds were such timeouts "
        "is its step's green:"
    ) in _flat(paragraph)


def _an_incomplete_sweep_runs_again(paragraph: str) -> bool:
    """A runner that stops at its first failure leaves packages unrun: when its
    only reds were timeouts, that sweep is no green yet, runs once more in full
    before any isolation run and is read instead, and the re-run, which changes
    nothing, spends no backfill fix. A sweep stopped by another red is red, and
    takes its step's route."""
    return (
        _UNRUN_SENTENCE_HEAD + " (a runner that stops at its first failure, turbo without `--continue` say) and "
        "whose only reds were timeouts is no green yet: before any isolation run, run it once more at the same tree "
        "and scope, cache-defeated, with every task run, captured under the next free number, and read that sweep "
        "instead; at the gate's backfill that re-run is no fix, so it counts toward neither of its two fixes."
    ) in _flat(paragraph)


def _the_marker_comes_from_that_sweep(paragraph: str) -> bool:
    """Step 2 and the gate steps that write a marker after their sweep write it
    from the sweep that timed out, as the #213 paragraph says of a second sweep."""
    return (
        "step 2 writes its marker from that sweep, and a gate step that writes one after its sweep by its own rule "
        "(`references/gate.md`: the backfill's step 3 once its sweep is green, a cap-only re-loop's `scope=full` "
        "refresh) writes it from that sweep too;"
    ) in _flat(paragraph)


def _step5_commits_nothing(paragraph: str) -> bool:
    return "at step 5 the marker stands, and step 5 commits nothing for it." in _flat(paragraph)


def _logs_a_timeout_line(paragraph: str) -> bool:
    """One line per pass, and only a pass logs one: a timeout that fails in
    isolation is a red, which its step's route records."""
    return (
        _LOG_SENTENCE_HEAD + " naming the package, the `HEAD` the sweep ran at, the sweep's capture and the isolation "
        "run's capture;"
    ) in _flat(paragraph)


def _owes_no_flake_record(paragraph: str) -> bool:
    """No `flaky:` line (which #213 always pairs with a `sweep` row) and no
    deferred-work row: contention on the host is not deferred work."""
    return (
        "the timeout owes no `flaky:` line of its own and no row to `{workflow.deferred_work_path}`, since "
        "contention on the host is not deferred work."
    ) in _flat(paragraph)


def _a_failing_isolation_run_is_a_red(paragraph: str) -> bool:
    return (
        _FAIL_SENTENCE_HEAD + ", the timeout is that sweep's red, and takes its step's route." in _flat(paragraph)
    )


def _in_order(paragraph: str) -> bool:
    """The outcome follows the sentence that sends the timeout to isolation:
    how the isolation run runs, then the pass and the line it logs, then a
    sweep that left tasks unrun, then the fail."""
    flat = _flat(paragraph)
    order = (
        _ISOLATION_SENTENCE,
        _SAME_RUN_SENTENCE_HEAD,
        _PASS_SENTENCE_HEAD,
        _LOG_SENTENCE_HEAD,
        _UNRUN_SENTENCE_HEAD,
        _FAIL_SENTENCE_HEAD,
    )
    if not all(flat.count(s) == 1 for s in order):
        return False
    positions = [flat.index(s) for s in order]
    return positions == sorted(positions)


_CLAUSES = (
    _isolation_run_is_the_same_run,
    _captures_the_isolation_run,
    _keeps_the_isolation_stem_apart,
    _a_pass_leaves_the_step_green,
    _the_marker_comes_from_that_sweep,
    _step5_commits_nothing,
    _logs_a_timeout_line,
    _owes_no_flake_record,
    _an_incomplete_sweep_runs_again,
    _a_failing_isolation_run_is_a_red,
    _in_order,
)


def _is_placed_in_step2(text: str) -> bool:
    """Once in the file, inside the loaded-machine paragraph of step 2, and not
    in step 5, whose pointer already sends a timeout back here."""
    paragraph = _paragraph(text)
    return bool(
        text.count(_LOADED_HEAD) == 1
        and text.count(_PASS_SENTENCE_HEAD) == 1
        and _PASS_SENTENCE_HEAD in paragraph
        and paragraph in _step2(text)
        and _PASS_SENTENCE_HEAD not in _step5(text)
    )


def _rules_a_passing_isolation_run(text: str) -> bool:
    paragraph = _paragraph(text)
    return _is_placed_in_step2(text) and all(clause(paragraph) for clause in _CLAUSES)


def test_step2_rules_a_timeout_that_passes_in_isolation():
    assert _rules_a_passing_isolation_run(_execute())


@pytest.mark.parametrize("clause", _CLAUSES, ids=lambda c: c.__name__.lstrip("_"))
def test_each_clause_holds_on_the_live_text(clause):
    assert clause(_paragraph(_execute()))


def test_the_rule_predicate_rejects_the_pre_edit_execute_md():
    pre = _execute_pre_edit(_execute())
    assert not _rules_a_passing_isolation_run(pre)
    assert not _is_placed_in_step2(pre)
    assert not any(clause(_paragraph(pre)) for clause in _CLAUSES)


@pytest.mark.parametrize(
    ("clause", "old", "new"),
    [
        # At step 5 a commit leaves the cache key as step 2 left it, so a cached run replays step 2's green.
        pytest.param(_isolation_run_is_the_same_run, "between the sweep and it, cache-defeated, with the test command",
                     "between the sweep and it, with the test command", id="cached"),
        pytest.param(_isolation_run_is_the_same_run, "with the test command and time bound the sweep gave that package",
                     "with a time bound of its own", id="raised-bound"),
        pytest.param(_isolation_run_is_the_same_run, "changing nothing between the sweep and it",
                     "after any fix the test needs", id="edited-tree"),
        # Retried until it passes, the isolation run clears a timeout that recurs.
        pytest.param(_isolation_run_is_the_same_run, "Run each isolation run once, on its own",
                     "Run each isolation run, on its own", id="retried"),
        pytest.param(_isolation_run_is_the_same_run, " or a second attempt", "", id="retry-proves"),
        # Beside another suite, build or isolation run, the contention comes back.
        pytest.param(_isolation_run_is_the_same_run, ", on its own (one package at a time, with no other suite or "
                     "build this run started still running),", ",", id="crowded-host"),
        # A `sweep-` stem is the shape gate.md's scoped backfill reads as a
        # second sweep's numbered capture.
        pytest.param(_captures_the_isolation_run, "there too as `isolation-<step>-<short sha>.log`",
                     "there too as `sweep-<step>-<short sha>.log`", id="sweep-stem"),
        pytest.param(_captures_the_isolation_run, "`isolation-backfill-<short sha>.log`",
                     "`sweep-backfill-<short sha>.log`", id="backfill-sweep-stem"),
        # Scratch is removed when the story advances; the record cites both captures after that.
        pytest.param(_captures_the_isolation_run, "Keep that sweep's capture in `evidence-<story_id>/`",
                     "Keep that sweep's capture in `.scratch-<story_id>/`", id="scratch-home"),
        pytest.param(_captures_the_isolation_run, ", a name already taken getting the next free number", "",
                     id="overwrites"),
        pytest.param(_keeps_the_isolation_stem_apart, "so it is never read as the numbered capture of a second sweep",
                     "so it may stand as the numbered capture of a second sweep", id="read-as-second-sweep"),
        pytest.param(_a_pass_leaves_the_step_green, "the timeout puts no red in that sweep",
                     "the timeout is still that sweep's red", id="still-red"),
        pytest.param(_a_pass_leaves_the_step_green, "and whose only reds were such timeouts is its step's green",
                     "and so run the same sweep once more", id="resweeps"),
        # A sweep with another red beside the timeouts is not green: that red takes its own route.
        pytest.param(_a_pass_leaves_the_step_green, " and whose only reds were such timeouts", "",
                     id="any-sweep-green"),
        # The singular wording leaves a sweep where contention timed out two packages red.
        pytest.param(_a_pass_leaves_the_step_green, "whose only reds were such timeouts", "whose only red it was",
                     id="one-timeout-only"),
        # A runner that stopped at the timeout left packages unrun: the sweep would read green over them.
        pytest.param(_a_pass_leaves_the_step_green, "a sweep that ran every task it scheduled and whose",
                     "a sweep whose", id="unrun-tasks"),
        # Left neither green nor red, an incomplete sweep has no route.
        pytest.param(_an_incomplete_sweep_runs_again, "is no green yet: before any isolation run, run it once more at "
                     "the same tree and scope, cache-defeated, with every task run, captured under the next free "
                     "number, and read that sweep instead;", "is no green;", id="unrun-no-route"),
        pytest.param(_an_incomplete_sweep_runs_again, " with every task run,", "", id="stops-again"),
        # Unlimited, the re-run would come before remediating a sweep a real red stopped.
        pytest.param(_an_incomplete_sweep_runs_again, " and whose only reds were timeouts", "", id="unrun-any-red"),
        # After the isolation runs, the first sweep's timeouts are isolated and logged for a sweep that is set aside.
        pytest.param(_an_incomplete_sweep_runs_again, "before any isolation run, ", "", id="isolates-first"),
        pytest.param(_an_incomplete_sweep_runs_again, "that re-run is no fix, so it counts toward neither of its two "
                     "fixes", "that re-run is one of its two fixes", id="spends-a-fix"),
        pytest.param(_the_marker_comes_from_that_sweep, "step 2 writes its marker from that sweep,",
                     "step 2 writes its marker from the isolation run,", id="marker-from-isolation"),
        pytest.param(_the_marker_comes_from_that_sweep, ", and a gate step that writes one after its sweep by its own "
                     "rule (`references/gate.md`: the backfill's step 3 once its sweep is green, a cap-only re-loop's "
                     "`scope=full` refresh) writes it from that sweep too", "", id="gate-steps-unruled"),
        pytest.param(_step5_commits_nothing, "at step 5 the marker stands, and step 5 commits nothing for it",
                     "at step 5 write a fresh marker and re-commit", id="step5-recommits"),
        pytest.param(_logs_a_timeout_line, "log one `timeout:` line", "log one `flaky:` line", id="flaky-prefix"),
        # Unconditional, the line would be owed by a timeout that fails in isolation too.
        pytest.param(_logs_a_timeout_line, "For each such pass, log one", "Log one", id="log-unconditional"),
        # One line for the whole sweep drops a package when several timed out.
        pytest.param(_logs_a_timeout_line, "For each such pass, log one", "For the sweep, log one",
                     id="one-line-per-sweep"),
        pytest.param(_logs_a_timeout_line, "the `HEAD` the sweep ran at, ", "", id="no-head"),
        pytest.param(_logs_a_timeout_line, "the sweep's capture and the isolation run's capture",
                     "the isolation run's capture", id="one-capture"),
        pytest.param(_owes_no_flake_record, "owes no `flaky:` line of its own and no row to",
                     "owes a `flaky:` line and a `sweep` row to", id="ledger-row"),
        pytest.param(_a_failing_isolation_run_is_a_red, "the timeout is that sweep's red",
                     "the timeout is no red", id="failing-is-green"),
        pytest.param(_in_order, _PASS_SENTENCE_HEAD, "When that package then passes alone, the timeout puts no red",
                     id="pass-unstated"),
        pytest.param(_in_order, " When that package fails in isolation too, the timeout is that sweep's red, and "
                     "takes its step's route.", "", id="fail-unstated"),
    ],
)
def test_each_clause_rejects_its_mutant(clause, old, new):
    paragraph = _flat(_paragraph(_execute()))
    assert paragraph.count(old) == 1
    mutant = paragraph.replace(old, new, 1)
    assert mutant != paragraph
    assert clause(paragraph)
    assert not clause(mutant)


def test_the_order_rejects_the_log_line_after_the_fail_sentence():
    """Moved after the fail sentence, the log line reads as owed by either
    outcome of the isolation run."""
    paragraph = _flat(_paragraph(_execute()))
    start = paragraph.index(_LOG_SENTENCE_HEAD)
    end = paragraph.index(" " + _UNRUN_SENTENCE_HEAD, start)
    log_sentence = paragraph[start:end]
    mutant = paragraph.replace(" " + log_sentence, "", 1) + " " + log_sentence
    assert mutant != paragraph and mutant.count(_LOG_SENTENCE_HEAD) == 1
    assert _in_order(paragraph)
    assert not _in_order(mutant)


def test_the_placement_rejects_a_copy_in_step5():
    """The rule lives once, in step 2: a copy in step 5 is a second source of
    truth for the same case."""
    live = _execute()
    pointer = "\n5. **Re-verify on the committed HEAD.**"
    mutant = live.replace(pointer, pointer + " " + _PASS_SENTENCE_HEAD + ".", 1)
    assert mutant != live
    assert _is_placed_in_step2(live)
    assert not _is_placed_in_step2(mutant)


# --- the gate steps the paragraph names still exist ----------------------------------


def _gate_names_the_marker_steps(gate: str) -> bool:
    """The backfill's step 3 and the cap-only re-loop's `scope=full` refresh,
    which the paragraph sends to "that sweep" for their marker. Read on the
    flattened text, so a reflow of gate.md changes nothing."""
    flat = _flat(gate)
    return _GATE_BACKFILL_STEP3 in flat and _GATE_CAP_ONLY_REFRESH in flat


def test_gate_md_still_has_the_marker_steps_the_paragraph_names():
    assert _gate_names_the_marker_steps(_gate())


@pytest.mark.parametrize("dropped", [_GATE_BACKFILL_STEP3, _GATE_CAP_ONLY_REFRESH], ids=["backfill-step3", "cap-only"])
def test_the_gate_check_rejects_a_dropped_step(dropped):
    gate = _flat(_gate())
    assert gate.count(dropped) == 1
    mutant = gate.replace(dropped, "", 1)
    assert _gate_names_the_marker_steps(gate)
    assert not _gate_names_the_marker_steps(mutant)


def _loaded_line(text: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(_LOADED_HEAD))


def test_the_touched_line_has_no_em_dash_left():
    assert _EM_DASH not in _loaded_line(_execute())


def test_the_em_dash_check_rejects_the_pre_edit_line():
    assert _EM_DASH in _loaded_line(_execute_pre_edit(_execute()))
