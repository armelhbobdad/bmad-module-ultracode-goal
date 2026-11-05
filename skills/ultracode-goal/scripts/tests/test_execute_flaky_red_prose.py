#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for a red the story's changes do not explain (issue #213).

Every red route of a wide sweep assumed the red was the story's own, so a
nondeterministic failure in a test file the story never touched had one written
route: remediate, write a fresh marker and re-commit. When the story's code
needed no change there was nothing to stage, and the guard refuses a commit
whose staged index is empty, so step 5 could not close; at the gate's backfill
the same red read as a defect in the story's code and cost a re-loop.

`references/execute.md` step 2 now carries the rule for every wide sweep (its
own, step 5's, and each sweep the gate runs as step 5 runs it): a non-timeout
red qualifies only when its test file is in neither `git diff --name-only` from
the baseline nor `git status --porcelain --untracked-files=all`, its failure
names no path those list and the output shows the cause inside that test, never
state another test left behind. It gets one cache-defeated re-run of the same
sweep at the same tree and scope; no red in that second sweep is the step's
green, with a `flaky:` decision-log line, a `sweep` ledger row and nothing
edited or committed, and any red in it is a red. Step 5 and the gate's backfill
step 2 point at it, and the ledger schema lists the `sweep` source.

Its review (#213) added: `--no-renames`, so the diff lists both sides of a
rename; the `flaky:` line says the story's uncommitted changes sit on the
`HEAD` both sweeps ran at at step 2; the ledger row names its `story`,
`reason`, `suggested_action` and `status`; step 2 is named as the step that
writes the marker; a timeout in the second sweep takes the loaded-machine
paragraph first; gate.md's cap-only re-loop appends nothing to the ledger save
that `sweep` row; and the evidence commit stages any `sweep` row the story's
sweeps appended, which no commit of the story carries.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text with the #213 wording removed (the pre-edit text) and against
a one-clause mutant it must reject. Stated limit: this is a presence proof over
prose. It shows the instruction is in the file, not that an executor obeys it.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_GATE = _SKILL_ROOT / "references" / "gate.md"
_HOW_IT_WORKS = _REPO / "docs" / "how-it-works.md"

_HEAD = "**A red the story's changes do not explain is not yet a red either.**"
_LOADED_HEAD = "**A wide sweep is also a loaded machine.**"
_RED_MEANS = "A red means the story is **not** done:"
_STEP5_POINTER = (
    "A red step 2 reads as not yet a red (a timeout on a loaded machine, or a red the story's changes do not "
    "explain) is read that way here too: a red the story's changes do not explain whose second sweep shows no red "
    "leaves this step green, with nothing committed."
)
_GATE_POINTER = (
    "A red `references/execute.md` step 2 reads as not yet a red (a timeout on a loaded machine, or a red the "
    "story's changes do not explain) is read that way here first. That step's second sweep for a red the story's "
    "changes do not explain is no fix, so it counts toward neither of the two fixes below, and when it shows no red, "
    "this sweep is green."
)
_GATE_FIXES = "A red that a change to the backfilled test files alone fixes"
_SWEEP_SOURCE = (
    ", `sweep` (a non-critical finding: a case outside the story's changes that went red in one sweep and green in "
    "the next at the same tree, `references/execute.md` step 2)"
)
_CAP_ONLY_CARVE_OUT = (
    " save the deferred-work `sweep` row its re-sweep owes for a red the story's changes do not explain "
    "(`references/execute.md` step 2)"
)
_EVIDENCE_SWEEP_ROW = (
    ", and any `sweep` row this story's sweeps appended (`references/execute.md` step 2) is tracked state no "
    "commit of the story carries, since those stage only its source and test paths"
)
_EVIDENCE_HEAD = "**Commit the gate's evidence before the next story starts.**"
_EVIDENCE_STAGING = "While `.current-story` still names this story, stage those of these paths"
_INVARIANT = (
    "Only non-gate-blocking work (CONCERNS, non-critical findings, parked decisions, and the rows open `gate-gap:` "
    "lines become) is allowed onto the ledger"
)
_DOCS_CLAUSE = (
    ", except that a red in a case outside the story's changes, whose cause shows inside that test, and that a "
    "second sweep at the same commit does not repeat, is logged as flaky and parked on the ledger, with nothing "
    "committed"
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
    """Step 5 alone, bounded at its own blank line, as the other step-5 pins
    bound it: no `6. ` follows it to stop at."""
    start = text.index("\n5. **Re-verify on the committed HEAD.**")
    return text[start : text.index("\n\n", start)]


def _paragraph(text: str) -> str:
    """The rule's paragraph, from its bold head to the blank line after it."""
    if _HEAD not in text:
        return ""
    start = text.index(_HEAD)
    end = text.find("\n\n", start)
    return text[start:] if end == -1 else text[start:end]


def _backfill_step2(gate: str) -> str:
    start = gate.index("\n2. With them staged")
    return gate[start : gate.index("\n3. Once the sweep is green", start)]


def _source_line(gate: str) -> str:
    return next(line for line in gate.splitlines() if line.startswith("- `source` ∈"))


def _reloop_bullet(gate: str) -> str:
    start = gate.index("- **`reloop`**")
    return gate[start : gate.index("- **`escalate`**", start)]


def _evidence_commit_opening(gate: str) -> str:
    """The evidence commit's paragraph up to its staging sentence: the list of
    what that commit stages."""
    start = gate.index(_EVIDENCE_HEAD)
    return gate[start : gate.index(_EVIDENCE_STAGING, start)]


# --- the pre-edit text: the live text with the #213 wording taken out ----------


def _execute_pre_edit(text: str) -> str:
    """execute.md as it stood before #213: no paragraph after the loaded-machine
    one, and no pointer in step 5."""
    paragraph = _paragraph(text)
    text = text.replace(paragraph + "\n\n", "", 1)
    return text.replace(_STEP5_POINTER + " ", "", 1)


def _gate_pre_edit(gate: str) -> str:
    return (
        gate.replace(_GATE_POINTER + " ", "", 1)
        .replace(_SWEEP_SOURCE, "", 1)
        .replace(_CAP_ONLY_CARVE_OUT, "", 1)
        .replace(_EVIDENCE_SWEEP_ROW, "", 1)
    )


def test_the_pre_edit_text_is_a_real_reconstruction():
    """The twins below must red for the right reason: the reconstruction removes
    exactly the #213 wording and leaves both files otherwise whole."""
    live, gate = _execute(), _gate()
    pre, gate_pre = _execute_pre_edit(live), _gate_pre_edit(gate)
    assert _HEAD not in pre and _STEP5_POINTER not in pre
    assert len(live) - len(pre) == len(_paragraph(live)) + 2 + len(_STEP5_POINTER) + 1
    # The loaded-machine paragraph is followed again by the capture rule.
    loaded = pre.index(_LOADED_HEAD)
    assert pre[pre.index("\n\n", loaded) + 2 :].startswith("**Capture, then slice: never pipe a long command")
    assert "denies the story's own second commit" in _step2(pre)
    assert _RED_MEANS in _step5(pre)
    assert _GATE_POINTER not in gate_pre and "`sweep`" not in _source_line(gate_pre)
    assert len(gate) - len(gate_pre) == (
        len(_GATE_POINTER) + 1 + len(_SWEEP_SOURCE) + len(_CAP_ONLY_CARVE_OUT) + len(_EVIDENCE_SWEEP_ROW)
    )
    assert _source_line(gate_pre).endswith("`decision` (parked decision).")
    assert "writing no `class:` lines, appending nothing to the ledger, and skipping" in _reloop_bullet(gate_pre)
    assert _evidence_commit_opening(gate_pre).endswith("are tracked state written after Execute's commit-at-green. ")


# --- execute.md step 2: the rule -----------------------------------------------


def _is_placed_in_step2(text: str) -> bool:
    """Once in the file, inside step 2's slice, right after the loaded-machine
    paragraph, and not in step 5."""
    if text.count(_HEAD) != 1 or _LOADED_HEAD not in text:
        return False
    loaded = text.index(_LOADED_HEAD)
    after_loaded = text[text.index("\n\n", loaded) + 2 :]
    return bool(_HEAD in _step2(text) and _HEAD not in _step5(text) and after_loaded.startswith(_HEAD))


def _binds_every_wide_sweep(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(
        "In any wide sweep this file or `references/gate.md` runs (this step's, step 5's, and each sweep the gate "
        "runs as step 5 runs it)" in flat
        and "a failing case that is not a timeout (the paragraph above rules a timeout)" in flat
    )


def _qualifies_only_outside_the_changes(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(
        "is not yet this story's red when all three of these hold" in flat
        and "its test file appears in neither `git diff --name-only --no-renames <the sha in .baseline-<story_id>>` "
        "(which lists both sides of a rename) nor `git status --porcelain --untracked-files=all`" in flat
        and "its captured failure names no path either command lists" in flat
        and "the output shows the failure's cause inside that test" in flat
    )


def _excludes_state_left_behind(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(
        "A failure that shows state another test left behind (the order the cases ran in, a shared fixture, a "
        "leftover file or port) does not qualify" in flat
        and "since this story's own tests can leave that state" in flat
    )


def _resweeps_once(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(
        "keep that sweep's capture, change nothing, and run the same sweep once more at the same tree and scope, "
        "cache-defeated, captured under the next free number" in flat
        and "Running the case alone does not answer it" in flat
    )


def _records_the_flake(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(
        "When that second sweep shows no red at all, it is the step's green" in flat
        and re.search(r"log a `flaky:` line in `\.decision-log\.md` naming the case, its file, the `HEAD` both "
                      r"sweeps ran at \(at step 2 the story's changes are uncommitted: they sit on that `HEAD`, "
                      r"untouched between the two sweeps\), the cause the output shows and both captures", flat)
        and "append a row for the case to `{workflow.deferred_work_path}`, worded as a non-critical finding" in flat
        and "edit, skip or retry-wrap nothing in that file, which is not this story's to change" in flat
    )


def _names_the_ledger_row(paragraph: str) -> bool:
    """Every column of the schema's row but its `id`, which the schema mints."""
    return (
        "worded as a non-critical finding (`references/gate.md`, \"Deferred-work ledger schema\"), with `source` "
        "`sweep`, `severity` `med`, `story` this story's id, a `reason` naming the case, its file and both captures, "
        "a `suggested_action` to fix the test outside this Epic's stories, and `status` `open`;"
    ) in _flat(paragraph)


def _keeps_the_marker_and_commits_nothing(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(
        "Step 2 then writes its marker from that second sweep" in flat
        and "At step 5 nothing has changed, so commit nothing" in flat
        and "the marker stands as it does after a green first try" in flat
    )


_TIMEOUT_SENTENCE = (
    "A timeout in the second sweep still takes the paragraph above first, as a timeout in any wide sweep does, "
    "before it is read as that sweep's red."
)
_SECOND_RED_SENTENCE = (
    "Any red in the second sweep, in that case or in another, is a red, and takes its step's route."
)


def _a_second_sweep_timeout_is_read_first(paragraph: str) -> bool:
    """The loaded-machine paragraph still rules a timeout in the second sweep,
    before the next sentence reads any red there as a red."""
    flat = _flat(paragraph)
    return bool(
        _TIMEOUT_SENTENCE in flat
        and "Any red in the second sweep" in flat
        and flat.index(_TIMEOUT_SENTENCE) < flat.index("Any red in the second sweep")
    )


def _a_second_red_is_a_red(paragraph: str) -> bool:
    return "Any red in the second sweep, in that case or in another, is a red, and takes its step's route" in _flat(
        paragraph
    )


_CLAUSES = (
    _binds_every_wide_sweep,
    _qualifies_only_outside_the_changes,
    _excludes_state_left_behind,
    _resweeps_once,
    _records_the_flake,
    _names_the_ledger_row,
    _keeps_the_marker_and_commits_nothing,
    _a_second_sweep_timeout_is_read_first,
    _a_second_red_is_a_red,
)


def _rules_the_unexplained_red(text: str) -> bool:
    paragraph = _paragraph(text)
    return _is_placed_in_step2(text) and all(clause(paragraph) for clause in _CLAUSES)


def test_step2_rules_a_red_the_storys_changes_do_not_explain():
    assert _rules_the_unexplained_red(_execute())


def test_the_rule_predicate_rejects_the_pre_edit_execute_md():
    pre = _execute_pre_edit(_execute())
    assert not _rules_the_unexplained_red(pre)
    assert not _is_placed_in_step2(pre)
    assert not any(clause(_paragraph(pre)) for clause in _CLAUSES)


@pytest.mark.parametrize(
    ("clause", "old", "new"),
    [
        # Bound to step 5 alone, as the issue asked, it leaves the gate's backfill
        # reading the same red as a defect in the story's code.
        pytest.param(_binds_every_wide_sweep, "(this step's, step 5's, and each sweep the gate runs as step 5 runs it)",
                     "(step 5's)", id="step5-only"),
        pytest.param(_binds_every_wide_sweep, "a failing case that is not a timeout (the paragraph above rules a "
                     "timeout)", "a failing case", id="takes-timeouts"),
        # Outside the diff alone lets through a cross-package regression the story caused.
        pytest.param(_qualifies_only_outside_the_changes, " nor `git status --porcelain --untracked-files=all`", "",
                     id="no-untracked"),
        # The pre-review wording: a rename listed only its new path, so a test the
        # story renamed away from read as one outside its changes.
        pytest.param(_qualifies_only_outside_the_changes,
                     "`git diff --name-only --no-renames <the sha in .baseline-<story_id>>` (which lists both sides of "
                     "a rename)", "`git diff --name-only <the sha in .baseline-<story_id>>`", id="rename-one-side"),
        pytest.param(_qualifies_only_outside_the_changes, " --no-renames", "", id="no-renames-dropped"),
        pytest.param(_qualifies_only_outside_the_changes, "its captured failure names no path either command lists; ",
                     "", id="names-a-changed-path"),
        pytest.param(_qualifies_only_outside_the_changes, "the output shows the failure's cause inside that test",
                     "the case passes when run alone", id="cause-not-shown"),
        pytest.param(_excludes_state_left_behind, "(the order the cases ran in, a shared fixture, a leftover file or "
                     "port) does not qualify", "(a shared fixture) does not qualify", id="order-qualifies"),
        pytest.param(_excludes_state_left_behind, "A failure that shows state another test left behind",
                     "A failure that shows no state another test left behind", id="state-qualifies"),
        pytest.param(_resweeps_once, "run the same sweep once more at the same tree and scope",
                     "run the failing case alone until it passes", id="isolated-rerun"),
        pytest.param(_resweeps_once, "run the same sweep once more at the same tree and scope, cache-defeated,",
                     "run the same sweep once more at the same tree and scope,", id="cached-resweep"),
        pytest.param(_resweeps_once, "Running the case alone does not answer it",
                     "Running the case alone answers it too", id="alone-answers"),
        pytest.param(_records_the_flake, "log a `flaky:` line in `.decision-log.md`", "log a line",
                     id="no-flaky-line"),
        # The pre-review wording: at step 2 a `HEAD` alone does not identify the
        # uncommitted tree both sweeps ran on.
        pytest.param(_records_the_flake, "the `HEAD` both sweeps ran at (at step 2 the story's changes are "
                     "uncommitted: they sit on that `HEAD`, untouched between the two sweeps),",
                     "the `HEAD` both sweeps ran at,", id="head-alone"),
        pytest.param(_records_the_flake, "untouched between the two sweeps", "edited between the two sweeps",
                     id="tree-moved"),
        pytest.param(_records_the_flake, ", worded as a non-critical finding (", " (", id="not-non-critical"),
        pytest.param(_records_the_flake, "edit, skip or retry-wrap nothing in that file",
                     "fix the test in the story's range", id="edits-the-file"),
        pytest.param(_names_the_ledger_row, "with `source` `sweep`, `severity` `med`",
                     "with `source` `gate`, `severity` `low`", id="wrong-ledger-row"),
        # The pre-review wording, which named two of the row's columns.
        pytest.param(_names_the_ledger_row, "(`references/gate.md`, \"Deferred-work ledger schema\"), with `source` "
                     "`sweep`, `severity` `med`, `story` this story's id, a `reason` naming the case, its file and both "
                     "captures, a `suggested_action` to fix the test outside this Epic's stories, and `status` `open`",
                     "with `source` `sweep` and `severity` `med` (`references/gate.md`, \"Deferred-work ledger "
                     "schema\")", id="columns-unnamed"),
        pytest.param(_names_the_ledger_row, "`story` this story's id, ", "", id="no-story"),
        pytest.param(_names_the_ledger_row, " and both captures, a `suggested_action`", ", a `suggested_action`",
                     id="reason-without-captures"),
        pytest.param(_names_the_ledger_row, "to fix the test outside this Epic's stories",
                     "to fix the test in the next story", id="fix-inside-the-epic"),
        pytest.param(_names_the_ledger_row, ", and `status` `open`", "", id="no-status"),
        pytest.param(_keeps_the_marker_and_commits_nothing, "At step 5 nothing has changed, so commit nothing",
                     "At step 5, re-commit as for any red", id="recommits"),
        pytest.param(_keeps_the_marker_and_commits_nothing, "the marker stands as it does after a green first try",
                     "write a fresh marker from the second sweep", id="fresh-marker"),
        # The pre-review wording, ambiguous in a paragraph that binds step 2,
        # step 5 and the gate's sweeps.
        pytest.param(_keeps_the_marker_and_commits_nothing, "Step 2 then writes its marker",
                     "This step then writes its marker", id="this-step"),
        # The pre-review wording: no sentence for a timeout in the second sweep.
        pytest.param(_a_second_sweep_timeout_is_read_first, "A timeout in the second sweep still takes the paragraph "
                     "above first, as a timeout in any wide sweep does, before it is read as that sweep's red. ", "",
                     id="second-sweep-timeout-unruled"),
        pytest.param(_a_second_sweep_timeout_is_read_first, "still takes the paragraph above first",
                     "is that sweep's red, and skips the paragraph above", id="timeout-is-a-red"),
        pytest.param(_a_second_sweep_timeout_is_read_first, _TIMEOUT_SENTENCE + " " + _SECOND_RED_SENTENCE,
                     _SECOND_RED_SENTENCE + " " + _TIMEOUT_SENTENCE, id="timeout-after-the-red-route"),
        pytest.param(_a_second_red_is_a_red, "Any red in the second sweep, in that case or in another, is a red",
                     "A red in the same case in the second sweep is a red", id="other-case-unruled"),
        pytest.param(_a_second_red_is_a_red, "and takes its step's route", "and takes a third sweep",
                     id="third-sweep"),
    ],
)
def test_each_rule_clause_rejects_its_one_clause_mutant(clause, old, new):
    paragraph = _flat(_paragraph(_execute()))
    assert paragraph.count(old) == 1, "the mutant must change the one clause it names"
    mutant = paragraph.replace(old, new)
    assert mutant != paragraph, "the mutant must actually change the text"
    assert clause(paragraph)
    assert not clause(mutant)


@pytest.mark.parametrize(
    "where",
    [
        pytest.param("step5", id="into-step5"),
        pytest.param("heartbeat", id="into-a-later-section"),
        pytest.param("before-loaded", id="before-the-loaded-machine-paragraph"),
    ],
)
def test_the_rule_is_anchored_to_step2_after_the_loaded_machine_paragraph(where):
    """Locality twin: the paragraph moved out of place must red, not only the
    paragraph removed."""
    live = _execute()
    paragraph = _paragraph(live)
    pre = _execute_pre_edit(live)
    if where == "step5":
        step5 = _step5(pre)
        mutant = pre.replace(step5, step5 + " " + paragraph, 1)
    elif where == "heartbeat":
        mutant = pre.replace("## Run-status heartbeat", f"{paragraph}\n\n## Run-status heartbeat", 1)
    else:
        mutant = pre.replace(_LOADED_HEAD, f"{paragraph}\n\n{_LOADED_HEAD}", 1)
    assert mutant != pre and _HEAD in mutant
    assert not _is_placed_in_step2(mutant)
    # The clauses still read, so only the placement check catches the move.
    assert all(clause(_paragraph(mutant)) for clause in _CLAUSES)


# --- execute.md step 5: the pointer ---------------------------------------------


def _step5_reads_it_first(text: str) -> bool:
    step5 = _step5(text)
    return bool(
        _STEP5_POINTER in step5
        and _RED_MEANS in step5
        and step5.index(_STEP5_POINTER) < step5.index(_RED_MEANS)
        and _STEP5_POINTER not in _step2(text)
    )


def test_step5_reads_the_unexplained_red_before_its_red_route():
    assert _step5_reads_it_first(_execute())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_STEP5_POINTER + " ", "", id="pre-edit"),
        pytest.param("leaves this step green, with nothing committed.",
                     "leaves this step green once it is re-committed.", id="recommits"),
        pytest.param("is read that way here too", "is a red here", id="red-here"),
        # After the red route, a reader has already remediated by the time it reads the pointer.
        pytest.param(_STEP5_POINTER + " " + _RED_MEANS, _RED_MEANS + " " + _STEP5_POINTER, id="after-red-route"),
    ],
)
def test_the_step5_pointer_predicate_rejects_its_mutants(old, new):
    live = _execute()
    assert live.count(old) == 1, "the mutant must change the one clause it names"
    mutant = live.replace(old, new, 1)
    assert mutant != live, "the mutant must actually change the text"
    assert not _step5_reads_it_first(mutant)


def test_step5_keeps_its_red_route_and_baseline_rule():
    """The pointer goes before the red route without rewording it."""
    step5 = _step5(_execute())
    assert (
        "A red means the story is **not** done: remediate, write a fresh `.tests-ran-<story_id>` marker, and "
        "re-commit (amend or a follow-up within the story boundary) until the committed HEAD is green" in step5
    )
    assert "**copied, never re-derived from `git rev-parse HEAD`**" in step5
    assert "\u2014" not in step5, "the touched line holds no em dash"


# --- gate.md: the backfill pointer and the ledger source ------------------------


def _backfill_reads_it_first(gate: str) -> bool:
    step = _backfill_step2(gate)
    return bool(
        _GATE_POINTER in step
        and _GATE_FIXES in step
        and step.index(_GATE_POINTER) < step.index(_GATE_FIXES)
        and "is fixed there, staged, and re-run, at most twice in this backfill" in step
    )


def test_the_backfill_sweep_reads_the_unexplained_red_first():
    assert _backfill_reads_it_first(_gate())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_GATE_POINTER + " ", "", id="pre-edit"),
        # Charged against the fix budget, a flake spends one of the backfill's two fixes.
        pytest.param("is no fix, so it counts toward neither of the two fixes below",
                     "counts as one of the two fixes below", id="counts-as-a-fix"),
        pytest.param("and when it shows no red, this sweep is green.", "and it is fixed there.", id="not-green"),
        pytest.param(_GATE_POINTER + " " + _GATE_FIXES, _GATE_FIXES + " " + _GATE_POINTER, id="after-the-fixes"),
    ],
)
def test_the_backfill_pointer_predicate_rejects_its_mutants(old, new):
    gate = _gate()
    assert gate.count(old) == 1, "the mutant must change the one clause it names"
    mutant = gate.replace(old, new, 1)
    assert mutant != gate, "the mutant must actually change the text"
    assert not _backfill_reads_it_first(mutant)


def _ledger_takes_a_sweep_row(gate: str) -> bool:
    """The `sweep` source is a non-critical finding, so the INVARIANT's list of
    what may reach the ledger holds unchanged."""
    return bool(_SWEEP_SOURCE.lstrip(", ") in _source_line(gate) and _INVARIANT in _flat(gate))


def test_the_ledger_schema_lists_the_sweep_source():
    assert _ledger_takes_a_sweep_row(_gate())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_SWEEP_SOURCE, "", id="pre-edit"),
        pytest.param("`sweep` (a non-critical finding: a case", "`sweep` (a case", id="not-non-critical"),
    ],
)
def test_the_ledger_predicate_rejects_its_mutants(old, new):
    gate = _gate()
    assert gate.count(old) == 1, "the mutant must change the one clause it names"
    mutant = gate.replace(old, new, 1)
    assert mutant != gate, "the mutant must actually change the text"
    assert not _ledger_takes_a_sweep_row(mutant)


def _cap_only_reloop_owes_its_sweep_row(gate: str) -> bool:
    """A cap-only re-loop re-runs the full sweep, which execute.md step 2 binds,
    so "appending nothing to the ledger" carves out the `sweep` row it can owe."""
    bullet = _reloop_bullet(gate)
    return bool(
        "**A cap-only re-loop skips the ceremony.**" in bullet
        and "writing no `class:` lines, appending nothing to the ledger" + _CAP_ONLY_CARVE_OUT
        + ", and skipping `bmad-correct-course` entirely" in bullet
    )


def test_the_cap_only_reloop_carves_out_the_sweep_row():
    assert _cap_only_reloop_owes_its_sweep_row(_gate())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The pre-review wording, which forbade the row execute.md step 2 owes.
        pytest.param(_CAP_ONLY_CARVE_OUT, "", id="pre-edit"),
        pytest.param("save the deferred-work `sweep` row its re-sweep owes",
                     "not even the deferred-work `sweep` row its re-sweep owes", id="row-forbidden"),
        pytest.param("(`references/execute.md` step 2), and skipping `bmad-correct-course`",
                     ", and skipping `bmad-correct-course`", id="no-pointer"),
    ],
)
def test_the_cap_only_predicate_rejects_its_mutants(old, new):
    gate = _gate()
    assert gate.count(old) == 1, "the mutant must change the one clause it names"
    mutant = gate.replace(old, new, 1)
    assert mutant != gate, "the mutant must actually change the text"
    assert not _cap_only_reloop_owes_its_sweep_row(mutant)


def _evidence_commit_stages_the_sweep_row(gate: str) -> bool:
    """A `sweep` row step 2 appends comes before the story's commit, which
    stages only its source and test paths, so the evidence commit's list names
    it beside the gate's own ledger rows."""
    opening = _evidence_commit_opening(gate)
    return bool(
        "this gate's ledger rows and the decision log" in opening
        and "are tracked state written after Execute's commit-at-green" + _EVIDENCE_SWEEP_ROW + ". " in opening
    )


def test_the_evidence_commit_stages_the_sweep_row():
    assert _evidence_commit_stages_the_sweep_row(_gate())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The pre-review wording: "this gate's ledger rows" alone, so a row
        # execute.md appended stayed uncommitted.
        pytest.param(_EVIDENCE_SWEEP_ROW, "", id="pre-edit"),
        pytest.param("any `sweep` row this story's sweeps appended", "any `sweep` row this gate's sweeps appended",
                     id="gate-sweeps-only"),
        # Moved past the staging sentence, the row is named after the list the
        # commit stages from.
        pytest.param(_EVIDENCE_SWEEP_ROW + ". While `.current-story` still names this story, stage those of these "
                     "paths", ". While `.current-story` still names this story, stage those of these paths"
                     + _EVIDENCE_SWEEP_ROW, id="after-the-staging"),
    ],
)
def test_the_evidence_commit_predicate_rejects_its_mutants(old, new):
    gate = _gate()
    assert gate.count(old) == 1, "the mutant must change the one clause it names"
    mutant = gate.replace(old, new, 1)
    assert mutant != gate, "the mutant must actually change the text"
    assert not _evidence_commit_stages_the_sweep_row(mutant)


# --- docs/how-it-works.md: the Execute summary ----------------------------------


def _docs_park_the_flake(text: str) -> bool:
    flat = _flat(text)
    return bool(
        "a red here means the story is not done and must be remediated and re-committed before it advances"
        + _DOCS_CLAUSE + "." in flat
    )


def test_how_it_works_says_a_flake_is_parked_with_nothing_committed():
    assert _docs_park_the_flake(_HOW_IT_WORKS.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_DOCS_CLAUSE, "", id="pre-edit"),
        pytest.param("whose cause shows inside that test, ", "", id="any-cause"),
        pytest.param("parked on the ledger, with nothing committed", "parked on the ledger, then re-committed",
                     id="recommits"),
    ],
)
def test_the_docs_predicate_rejects_its_mutants(old, new):
    text = _HOW_IT_WORKS.read_text(encoding="utf-8")
    assert text.count(old) == 1, "the mutant must change the one clause it names"
    mutant = text.replace(old, new, 1)
    assert mutant != text, "the mutant must actually change the text"
    assert not _docs_park_the_flake(mutant)
