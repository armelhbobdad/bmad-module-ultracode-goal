#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contracts for the operator-evidence route.

A real story failed its gate with every test green: one acceptance criterion
held a half only a person could measure, TEA counted the whole AC PARTIAL, and
the gate routed the FAIL to a re-loop no fix could satisfy. The fix is mostly
instruction, which no script test reaches, so this file pins it where a run
reads it:

  - define-done.md splits the operator half into its own AC tagged
    `**Gate-ability:** operator-evidence`, retags in place only an AC that asks
    for nothing to be built or changed, and scaffolds every other AC only;
  - every surface keys the owed class on `operator-evidence`, and the plain
    `operator` tag keeps its meaning, work the dev agent builds;
  - gate.md names the live results file trace reads, asks `operator_owed.py`
    on every FAIL BEFORE the re-loop route, escalates with kind
    `operator-evidence-owed` on `owed: true`, keeps an AC whose counted record
    TEA still holds below FULL with the operator, naming the records counted,
    parks an owed AC on advance or defer without claiming a P2 or P3 one
    cannot fail the gate, and deletes the re-gate marker once a verdict is
    logged; an unread coverage matrix (`evaluated: false`) moves the cycle's
    trace files aside and escalates with an opening phrase of its own that
    ucg-resolve keys on, never re-loops, except a hand-authored FAIL or a
    decomposed child that claims no tagged AC, which keep the re-loop (#250);
  - execute.md names the kind as a live one, keeps it off ucg-dev-story's
    plate, says to get an AC narrowed before pinning a stated bound, and
    re-gates (never re-drives) a story whose escalation /ucg-resolve closed,
    taking step 5's red route when the re-measure is red;
  - ucg-resolve closes the escalation only with the records on disk, a partly
    recorded AC only on a record it does not already name or a written
    narrowing, and that close writes `.regate-<story_id>` and resets the
    story's turn counter;
  - finalize.md files it under the escalated route.

test_operator_owed.py pins the script; this pins the routing. The documented
command is also parsed with the script's own parser, so the two cannot drift.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import re
import shlex
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REFS = _SKILL_ROOT / "references"
GATE = (_REFS / "gate.md").read_text(encoding="utf-8")
DEFINE_DONE = (_REFS / "define-done.md").read_text(encoding="utf-8")
EXECUTE = (_REFS / "execute.md").read_text(encoding="utf-8")
FINALIZE = (_REFS / "finalize.md").read_text(encoding="utf-8")
RESOLVE = (_SKILL_ROOT.parent / "ucg-resolve" / "SKILL.md").read_text(encoding="utf-8")
_REPO_ROOT = _SKILL_ROOT.parents[1]
GATE_MODEL = (_REPO_ROOT / "docs" / "gate-model.md").read_text(encoding="utf-8")
HOW_IT_WORKS = (_REPO_ROOT / "docs" / "how-it-works.md").read_text(encoding="utf-8")
FRAGMENT = (_REPO_ROOT / "changes" / "gate-operator-evidence-owed.yaml").read_text(encoding="utf-8")
MOVED_FRAGMENT = (_REPO_ROOT / "changes" / "gate-moved-ac-regate.yaml").read_text(encoding="utf-8")

_EVIDENCE_TAG = "`**Gate-ability:** operator-evidence`"
_PLAIN_TAG = "`**Gate-ability:** operator`"

_ROUTE_BULLET = "- **A FAIL only operator evidence can change is not a re-loop.**"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start : end if end != -1 else len(text)]


def _operator_route() -> str:
    """The new bullet and its command, up to the reloop bullet it precedes."""
    start = GATE.index(_ROUTE_BULLET)
    return GATE[start : GATE.index("- **`reloop`**", start)]


def _load_script():
    spec = importlib.util.spec_from_file_location("operator_owed", _SKILL_ROOT / "scripts" / "operator_owed.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# --- gate.md --------------------------------------------------------------------


def test_the_operator_route_comes_before_the_reloop_route():
    route = _section(GATE, "## Route on the verdict")
    assert route.count(_ROUTE_BULLET) == 1
    assert route.index(_ROUTE_BULLET) < route.index("- **`reloop`**"), (
        "the check must be met before the reloop route, or a FAIL is re-looped first"
    )
    # Locality: the reloop route's own slice (test_reloop_scope_prose.py) does not swallow it.
    reloop = GATE[GATE.index("- **`reloop`**") : GATE.index("- **`escalate`**")]
    assert "operator_owed.py" not in reloop


_ROUTE_CHECKS = {
    "runs on every FAIL": lambda s: "On every gate_status FAIL, first run" in s,
    "names the script": lambda s: "uv run {skill-root}/scripts/operator_owed.py" in s,
    "escalates with the kind on owed: true": lambda s: bool(
        re.search(r"On `owed: true`, take `escalate` with `kind` `operator-evidence-owed`", s)
    ),
    "names the commit and the file to record into": lambda s: "`assessed_commit`" in s
    and "the live results file to record into" in s,
    "names /ucg-resolve as the close": lambda s: "`/ucg-resolve` closes it" in s,
    "spends no re-loop and no correct-course": lambda s: "run no `bmad-correct-course`, spend no re-loop" in s,
    "commits nothing after the assessed commit": lambda s: "commit nothing after the assessed commit" in s,
    "keeps the reloop route on owed: false once evaluated": lambda s: (
        "On `evaluated: true` and `owed: false`, the `reloop` route below stands" in s
    ),
    "passes the cycle profile as the gate took it": lambda s: "pass `--cycle-profile` exactly as the gate took it" in s,
}


def test_the_operator_route_states_its_contract():
    route = _operator_route()
    unmet = sorted(name for name, check in _ROUTE_CHECKS.items() if not check(route))
    assert unmet == []
    # Twin: the same checks find nothing in the rest of the file.
    rest = GATE.replace(route, "")
    assert sorted(name for name, check in _ROUTE_CHECKS.items() if not check(rest)) == sorted(_ROUTE_CHECKS)


def test_the_documented_command_parses_with_the_scripts_own_parser():
    route = _operator_route()
    line = next(ln for ln in route.splitlines() if ln.startswith("uv run {skill-root}/scripts/operator_owed.py"))
    argv = shlex.split(re.sub(r"\{[^}]+\}|<[^>]+>", "x", line))[3:]
    args = _load_script().build_parser().parse_args(argv)
    assert args.profile == "production" and args.nfr and args.test_review and args.tests_ran


def test_the_escalate_bullet_names_the_case():
    bullet = next(ln for ln in GATE.splitlines() if ln.startswith("- **`escalate`**"))
    assert "a FAIL only operator evidence can change" in bullet


# --- an unread coverage matrix escalates, never re-loops (#250) -------------------

_UNREAD_OPENING = "The operator-evidence check could not read trace's coverage matrix"
_UNREAD_HEAD = "On `evaluated: false`, the story file tags an operator-evidence AC"

_UNREAD_CHECKS = {
    "routes evaluated: false before the reloop sentence": lambda s: (
        _UNREAD_HEAD in s
        and "On `evaluated: true` and `owed: false`" in s
        and s.index(_UNREAD_HEAD) < s.index("On `evaluated: true` and `owed: false`")
    ),
    "names what could not be read": lambda s: (
        "there is no trace report, or it names no absolute `tempCoverageMatrixPath`, the file it names is gone or "
        "unreadable, or the matrix or the summary is not this gate's, names no commit or measured another one" in s
    ),
    "keeps the hand-authored fallback's reloop": lambda s: (
        "Two such FAILs keep the `reloop` route below, as they did before the script could tell them apart" in s
        and "one in the hand-authored trace files (\"Non-web stack\" above), logged `gate-provenance: hand-authored`, "
        "which hold no coverage matrix by design" in s
    ),
    "keeps a decomposed child off a sibling's tag": lambda s: (
        "a decomposed child's when no parent AC its sprint-status row claims carries that tag, since a sibling's tag "
        "owes it nothing" in s
    ),
    "escalates with the kind": lambda s: "Otherwise take `escalate` with `kind` `operator-evidence-owed`." in s
    and "`source` is the trace report's path as moved aside (with no report, the gate decision's, or else the "
    "summary's), `evidence` is the script's last reason" in s,
    "moves the trace files aside before the sidecar": lambda s: (
        "Before you write its sidecar, move whichever of the story's `trace-<story_id>.md`, "
        "`gate-decision-<story_id>.json` and `e2e-trace-summary-<story_id>.json` exist aside, all in one step" in s
        and "so the re-gate its close owes runs trace again and never reads this cycle's report" in s
        and "a resume that finds them moved aside routes `gate-owed` as that paragraph says" in s
    ),
    "opens decision_needed with its own phrase": lambda s: f'`decision_needed` opens with "{_UNREAD_OPENING}"' in s,
    "names the run, the number, the commit and an earlier one": lambda s: (
        "then names this run's id, its number among this story's escalations with that opening" in s
        and "the commit under assessment as the assessed commit, in full as `git rev-parse` prints it" in s
        and "whether one of this story at this commit came before" in s
    ),
    "says what is wrong and what the close waits on": lambda s: (
        "why the matrix could not be read, whether one of this story at this commit came before, and what the close "
        "waits on: nothing for the first at that commit, whose re-gate runs trace again, and for a later one the "
        "operator's written word that trace can leave a coverage matrix the check can read there" in s
    ),
    "names the close": lambda s: "`/ucg-resolve` keys its close on that opening phrase. Log the script's" in s,
    "logs what the next one counts from": lambda s: (
        "Log the script's JSON and the `decision_needed` you write, since the next such escalation takes its number, "
        "and whether one came before at this commit, from the log." in s
    ),
    "spends no re-loop": lambda s: "Write no `class:` line, run no `bmad-correct-course`, spend no re-loop, since "
    "what kept the check from the matrix is the files trace left" in s,
    "commits nothing after the assessed commit": lambda s: (
        "commit nothing after the assessed commit, since the re-gate its close owes measures that commit" in s
    ),
}


def test_an_unread_matrix_escalates_rather_than_reloops():
    """The field case (#250): the trace report lost `tempCoverageMatrixPath`,
    `operator_owed.py` printed `owed: false` with nothing open, and the route
    re-looped a story whose only open criterion was evidence a person records.
    An unread matrix is now `evaluated: false`, which escalates with an opening
    phrase of its own, after moving the cycle's trace files aside so the
    re-gate really re-traces; only `evaluated: true`, a hand-authored FAIL and a
    decomposed child that claims no tagged AC keep the reloop route."""
    route = _norm(_operator_route())
    assert sorted(name for name, check in _UNREAD_CHECKS.items() if not check(route)) == []
    # Twin: the same checks find nothing in the rest of the file.
    rest = _norm(GATE.replace(_operator_route(), ""))
    assert sorted(name for name, check in _UNREAD_CHECKS.items() if not check(rest)) == sorted(_UNREAD_CHECKS)
    # Twin: the bullet as it stood on main, which re-looped every `owed: false`, meets none of them.
    new_end = "On `evaluated: true` and `owed: false`, the `reloop` route below stands; log the script's `reasons`."
    start, end = route.index(" " + _UNREAD_HEAD), route.index(new_end) + len(new_end)
    old_end = " On `owed: false`, the `reloop` route below stands; log the script's `reasons`."
    main = route[:start] + old_end + route[end:]
    assert _UNREAD_OPENING not in main and "`evaluated: false`" not in main
    assert sorted(name for name, check in _UNREAD_CHECKS.items() if not check(main)) == sorted(_UNREAD_CHECKS)


@pytest.mark.parametrize(
    ("old", "new", "lost"),
    [
        pytest.param(
            "Two such FAILs keep the `reloop` route below", "Two such FAILs escalate the same way",
            "keeps the hand-authored fallback's reloop", id="hand-authored-escalates",
        ),
        pytest.param(
            "a decomposed child's when no parent AC its sprint-status row claims carries that tag",
            "a decomposed child's when its parent's story file tags no AC",
            "keeps a decomposed child off a sibling's tag", id="child-judged-by-parent-file",
        ),
        pytest.param(
            "Before you write its sidecar, move whichever of", "Before you write its sidecar, keep whichever of",
            "moves the trace files aside before the sidecar", id="stale-report-kept",
        ),
        pytest.param(
            " (with no report, the gate decision's, or else the summary's)", "",
            "escalates with the kind", id="source-undefined-without-a-report",
        ),
        pytest.param(
            "Log the script's JSON and the `decision_needed` you write,", "Log the script's `reasons`,",
            "logs what the next one counts from", id="count-unrecorded",
        ),
        pytest.param(
            ", and what the close waits on: nothing for the first at that commit, whose re-gate runs trace again, and "
            "for a later one the operator's written word that trace can leave a coverage matrix the check can read "
            "there", "",
            "says what is wrong and what the close waits on", id="close-unexplained",
        ),
        pytest.param(
            ", and commit nothing after the assessed commit, since the re-gate its close owes measures that commit", "",
            "commits nothing after the assessed commit", id="commit-allowed",
        ),
    ],
)
def test_the_unread_matrix_pin_rejects_a_mutant(old, new, lost):
    route = _norm(_operator_route())
    assert route.count(old) == 1, "the mutant must change the one clause it names"
    mutant = route.replace(old, new)
    assert not _UNREAD_CHECKS[lost](mutant)


def test_the_escalate_bullet_names_the_unread_matrix():
    bullet = next(ln for ln in GATE.splitlines() if ln.startswith("- **`escalate`**"))
    case = "a FAIL whose operator-evidence check could not read trace's coverage matrix, `evaluated: false` above"
    assert case in bullet
    assert bullet.index("gate_status NOT_EVALUATED") < bullet.index(case) < bullet.index("budget exhausted")


def test_the_close_keys_on_the_phrase_the_gate_opens_with():
    """Cross-file: the opening phrase gate.md writes is the one `/ucg-resolve` keys on."""
    close = re.search(r"- \*\*`close`\*\*.*?(?=\n- \*\*`|\n\n)", RESOLVE, re.DOTALL)
    assert close is not None
    assert f'One that opens with "{_UNREAD_OPENING}"' in _norm(close.group(0))
    assert f'opens with "{_UNREAD_OPENING}"' in _norm(_operator_route())


def test_the_gate_model_doc_states_both_closes_and_the_reloops_it_keeps():
    """docs/gate-model.md describes the unread-matrix route as gate.md runs it:
    the move aside, the first close at once, a repeat only on the operator's
    written word, and the two FAILs that keep the re-loop."""
    model = _norm(GATE_MODEL)
    for clause in (
        "The gate moves that cycle's trace files aside first, so `/ucg-resolve` closes the first such escalation at a "
        "commit at once and its re-gate runs trace again",
        "and closes a later one at that commit only on the operator's written word that trace can leave a matrix the "
        "check can read there",
        "A hand-authored trace, which holds no matrix by design, keeps the re-loop, and so does a decomposed child "
        "none of whose claimed criteria carries the tag",
    ):
        assert clause in model, clause


def test_the_backfill_section_names_the_live_results_input():
    backfill = _section(GATE, "## Backfill the gate evidence")
    assert "**Operator evidence is a recorded live result, in either profile.**" in backfill
    assert "`live_results_input`" in backfill
    assert "`{workflow.trace_output_dir}/live-verification-results-<story_id>.json`" in backfill
    assert "Write no record the operator did not give you" in backfill
    assert "caps a requirement covered only this way at CONCERNS" in backfill


def test_an_owed_ac_is_parked_on_advance_and_defer():
    defer = next(ln for ln in GATE.splitlines() if ln.startswith("- **`defer`**"))
    assert "**On `advance` or `defer`, an operator-evidence AC still owed its evidence is parked too**" in defer
    assert "`source` `gate`" in defer
    advance = next(ln for ln in GATE.splitlines() if ln.startswith("- **`advance`**"))
    assert "an operator-evidence AC still owed its evidence is parked on the ledger first" in advance


def test_a_partly_recorded_ac_is_owed_on_advance_and_defer_too():
    """The FAIL route calls an AC TEA holds below FULL on counted records still
    owed. A PASS or CONCERNS gate that leaves such a P2 or P3 AC open must park
    its unrecorded part on the ledger, not read the counted record as enough."""
    defer = _norm(next(ln for ln in GATE.splitlines() if ln.startswith("- **`defer`**")))
    assert "or while TEA holds it below FULL with only the records it counted there" in defer
    assert "for a partly recorded AC, the ids of the records TEA counted and the part still owed" in defer
    # Twin: the test as first written read any counted `pass` record as enough.
    old = defer.replace(", or while TEA holds it below FULL with only the records it counted there", "")
    assert "or while TEA holds it below FULL" not in old


def test_parking_never_claims_a_p2_or_p3_criterion_cannot_fail_the_gate():
    """TEA fails a gate whose overall coverage is under 80%, and that counts P2 and P3.

    A split story with three covered ci-machine ACs and one uncovered P2
    operator-evidence AC is at 75%, a FAIL: the parking sentence may say such
    a criterion can leave the gate at PASS or CONCERNS, never that it cannot
    fail it, and a FAIL goes to the operator check, not to the ledger.
    """
    defer = _norm(next(ln for ln in GATE.splitlines() if ln.startswith("- **`defer`**")))
    assert "does not fail the gate over an uncovered P2 or P3" not in defer
    assert "an uncovered P2 or P3 criterion may leave the gate at PASS or CONCERNS" in defer
    assert "It still counts toward TEA's overall coverage, so it can also FAIL the gate" in defer
    assert "a FAIL goes to `operator_owed.py` (the next bullet), never to this ledger" in defer
    assert "does not fail the gate, at P2 or P3" not in _norm(FRAGMENT)
    assert "It still counts toward TEA's overall coverage, so it can also fail the gate" in _norm(FRAGMENT)


# --- define-done.md ---------------------------------------------------------------


def test_define_done_splits_the_operator_half_and_scaffolds_the_rest():
    step1 = DEFINE_DONE[DEFINE_DONE.index("1. **`ucg-create-story`**") : DEFINE_DONE.index("2. **`bmad-testarch-atdd`**")]
    assert "**A criterion with an operator half is split here.**" in step1
    assert _EVIDENCE_TAG in step1
    assert "recorded rather than gated" in step1, "the prose shape that held the field AC at PARTIAL is named"
    step2 = DEFINE_DONE[DEFINE_DONE.index("2. **`bmad-testarch-atdd`**") : DEFINE_DONE.index("**In `--light`:**")]
    assert "**An operator-evidence AC gets no red-phase scaffold**" in step2
    assert "scaffold every AC except the ones tagged `**Gate-ability:** operator-evidence`," in step2
    exit_condition = _section(DEFINE_DONE, "## Exit condition")
    assert "An operator-evidence AC needs no scaffold" in exit_condition


_RETAG_CHECKS = {
    "retags only an AC that builds or changes nothing": lambda s: (
        "only when it asks the dev agent to build or change nothing: its whole content is a "
        "measurement, run or observation a person makes and records" in s
    ),
    "tests for a change, not for who checks it": lambda s: (
        "The test is whether the AC asks for anything to be built or changed, not who can check it" in s
    ),
    "an AC asking for a change keeps its tag": lambda s: (
        "an AC that asks for a change (code, a comment, a doc, a ledger edit) keeps its tag "
        "even when only a person's read can check it" in s
    ),
}


def test_define_done_retags_in_place_only_an_ac_that_asks_for_no_change():
    """Who can check an AC does not decide its tag; whether it asks for a change does.

    AC 6 of a consumer project's story asks for comment fixes that only a reviewer's read can
    check. Retagged `operator-evidence`, Execute would have ucg-dev-story build
    nothing for it and the gate would route the unbuilt fixes to a person. It
    keeps its plain tag. AC 10, a checklist a person runs on a real build and
    records, asks for nothing to be built, and is the AC the retag is for.
    """
    step1 = _norm(
        DEFINE_DONE[DEFINE_DONE.index("1. **`ucg-create-story`**") : DEFINE_DONE.index("2. **`bmad-testarch-atdd`**")]
    )
    unmet = sorted(name for name, check in _RETAG_CHECKS.items() if not check(step1))
    assert unmet == []
    broad = (
        "is not split: retag it in place, keeping its number, with `**Gate-ability:** operator-evidence`, "
        "whatever tag it carried."
    )
    assert broad not in step1
    # Twin: the broad wording, which retagged by who can check the AC, meets none of the checks.
    old = (
        "An AC whose split names only such a part, with nothing a script or test can decide, " + broad
    )
    assert sorted(name for name, check in _RETAG_CHECKS.items() if not check(old)) == sorted(_RETAG_CHECKS)
    fragment = _norm(FRAGMENT)
    assert "A criterion that is wholly operator evidence is retagged" not in fragment
    assert (
        "A criterion that asks for nothing to be built or changed, whose whole content is a measurement, "
        "run or observation a person makes and records, is retagged `operator-evidence` in place." in fragment
    )
    assert (
        "A criterion that asks for a change (code, a comment, a doc, a ledger edit) keeps its tag even when "
        "only a person's read can check it." in fragment
    )


# --- execute.md, finalize.md, ucg-resolve -------------------------------------------


def test_execute_names_the_kind_and_the_two_story_loop_rules():
    sidecar = _section(EXECUTE, "### Escalation sidecar")
    assert "`operator-evidence-owed` is a live `kind` too" in sidecar
    loop = EXECUTE[EXECUTE.index("### The story loop") : EXECUTE.index("\n2. Run the tests")]
    assert "**An operator-evidence AC is not `ucg-dev-story`'s to satisfy.**" in loop
    rule = loop[loop.index("**An operator-evidence AC is not") :].split("\n\n")[0]
    assert f"When the story carries an AC tagged {_EVIDENCE_TAG}" in rule
    assert f"An AC tagged plain {_PLAIN_TAG} is not one: it is work `ucg-dev-story` builds" in rule
    stated = "**Get an AC narrowed in writing before committing a case that pins behaviour it forbids.**"
    assert stated in loop
    paragraph = loop[loop.index(stated) :].split("\n\n")[0]
    assert "escalate for it" in paragraph and "narrowed AC" in paragraph


def test_finalize_files_it_under_the_escalated_route():
    route = next(ln for ln in FINALIZE.splitlines() if ln.startswith("- **The terminal route this run took**"))
    assert "An `operator-evidence-owed` escalation takes the escalated route" in route
    assert "reached a Stage-5 verdict" in route


def test_ucg_resolve_closes_it_only_with_the_records_on_disk():
    close = re.search(r"- \*\*`close`\*\*.*?(?=\n- \*\*`|\n\n)", RESOLVE, re.DOTALL)
    assert close is not None
    text = _norm(close.group(0))
    assert "**Closing an `operator-evidence-owed` escalation needs the evidence on disk.**" in text
    assert "confirm a `status` `pass` record for every AC it lists, made at the commit it names" in text
    assert "Those are the story's `**Gate-ability:** operator-evidence` ACs" in text
    assert "a plain `operator` tag is work the dev agent builds, never evidence this close waits on" in text
    assert "If one is missing, say which and record `defer`" in text
    assert "This surface never writes a record itself" in text


# --- the owed class's tag ------------------------------------------------------------


_SENTENCE = re.compile(r"(?<=[.:;])\s+(?=[A-Z*`(])")


def test_every_surface_keys_the_owed_class_on_operator_evidence():
    """Stories UCG already wrote tag built work `operator` (a consumer project's story: code-comment fixes, a
    CLAUDE.md pin a script checks, ledger closures). A rule keyed on that tag would tell
    ucg-dev-story to build nothing for them and route their gaps to a person. So every
    surface that names the owed class names `operator-evidence`, and the plain tag appears
    only in a sentence that says it is work the dev agent builds.
    """
    surfaces = {
        "gate.md": GATE,
        "define-done.md": DEFINE_DONE,
        "execute.md": EXECUTE,
        "ucg-resolve": RESOLVE,
        "docs/gate-model.md": GATE_MODEL,
        "docs/how-it-works.md": HOW_IT_WORKS,
        "changes fragment": FRAGMENT,
        "moved-AC fragment": MOVED_FRAGMENT,
    }
    for name, text in surfaces.items():
        flat = _norm(text)
        assert _EVIDENCE_TAG in flat, name
        for sentence in _SENTENCE.split(flat):
            if _PLAIN_TAG in sentence:
                assert "builds" in sentence, (name, sentence)
    # Twin: the old wording, which keyed the class on the plain tag, fails the check.
    old = "An AC tagged `**Gate-ability:** operator` is proven only through TEA's live verification results."
    assert any(_PLAIN_TAG in s and "builds" not in s for s in _SENTENCE.split(old))


# --- the re-gate a closed escalation owes, and a record that covers part of an AC ---


def test_ucg_resolve_writes_the_regate_marker_and_resets_the_counter():
    """Without the marker the resume re-drove the closed story from step 0,
    where its grown turn count could escalate it and steps 1-4 could commit
    past the commit the operator's records were made at."""
    close = re.search(r"- \*\*`close`\*\*.*?(?=\n- \*\*`|\n\n)", RESOLVE, re.DOTALL)
    assert close is not None
    text = _norm(close.group(0))
    operator = text[text.index("**Closing an `operator-evidence-owed` escalation") :]
    assert "`{workflow.implementation_artifacts}/.regate-<story_id>`" in operator
    assert "`sha=` the assessed commit" in operator
    assert "`decision=` the id you closed" in operator
    assert "`{workflow.implementation_artifacts}/.budget-<story_id>.json`" in operator
    assert "routes the story `gate-owed`" in operator
    assert "There is no counter reset" not in RESOLVE


_FOURTH_CASE = "**A fourth case: a closed `operator-evidence-owed` story owes a re-gate, not a re-drive.**"


def test_execute_resume_rule_re_gates_a_closed_operator_evidence_story():
    assert EXECUTE.count(_FOURTH_CASE) == 1
    # In the resume rule: after the third case, before the story loop.
    assert EXECUTE.index("**A third case:") < EXECUTE.index(_FOURTH_CASE) < EXECUTE.index("## Default")
    paragraph = _norm(EXECUTE[EXECUTE.index(_FOURTH_CASE) :].split("\n\n")[0])
    for token in (
        "`{workflow.implementation_artifacts}/.regate-<story_id>`",
        "resets the story's turn counter",
        "the route is `gate-owed`",
        "skipping step 0's turn-ceiling read and steps 1 through 4",
        "Commit nothing before that gate",
        "A `stale` marker",
        "routes as if it were absent",
        "the gate deletes the marker once this story's verdict is logged",
    ):
        assert token in paragraph, token
    sweep = next(ln for ln in EXECUTE.splitlines() if ln.startswith("**The re-assertion sweep is one script call"))
    assert "the re-gate a closed `operator-evidence-owed` escalation owes" in sweep


def test_the_fourth_case_takes_step_5s_red_route_on_a_red_re_measure():
    """Step 5's red route is a remediation commit, so "commit nothing" holds only
    while the re-measure is green. On a red, the commit makes the records stale,
    and the re-gate at the new HEAD escalates again rather than counting them."""
    paragraph = _norm(EXECUTE[EXECUTE.index(_FOURTH_CASE) :].split("\n\n")[0])
    assert "Commit nothing before that gate while step 5's re-measure is green" in paragraph
    red = paragraph[paragraph.index("On a red, take step 5's red route") :]
    for token in (
        "remediate, write a fresh `.tests-ran-<story_id>` marker, re-commit",
        "moves `HEAD` past the assessed commit, so the records no longer count",
        "the `.regate-<story_id>` marker is stale",
        "the re-gate at the new `HEAD` escalates `operator-evidence-owed` again at the new commit",
    ):
        assert token in red, token
    step5 = next(ln for ln in EXECUTE.splitlines() if ln.startswith("5. **Re-verify on the committed HEAD.**"))
    assert "A red means the story is **not** done: remediate, write a fresh `.tests-ran-<story_id>` marker" in step5


def test_the_gate_deletes_the_regate_marker_once_the_verdict_is_logged():
    """Left on disk, a marker still naming HEAD would route the next resume to
    another re-gate of a story whose verdict already stands."""
    route = _norm(_section(GATE, "## Route on the verdict"))
    settle = "**A logged verdict settles an owed re-gate.**"
    removal = "delete `{workflow.implementation_artifacts}/.regate-<story_id>` if it exists"
    assert route.count(settle) == 1 and removal in route
    # After the record ("Run the gate", above), before every route that follows.
    assert route.index(settle) < route.index(removal) < route.index("- **`advance`**")
    assert "Once this story's verdict is recorded in `.decision-log.md`" in route
    assert "the resume re-gates that commit rather than re-driving the story" in _norm(_operator_route())


def test_a_counted_record_trace_holds_partial_stays_with_the_operator():
    """A record TEA counted that covers only part of the AC leaves the rest to
    the operator: no re-loop can record it, and narrowing the AC is the
    operator's written decision (execute.md: "no re-loop changes the AC")."""
    route = _norm(_operator_route())
    assert "already holds a `pass` record TEA counted at the assessed commit is still owed" in route
    assert (
        "For each AC in `partial`, `decision_needed` names the record ids TEA already counted, says they "
        "cover only part of the criterion, and asks the operator to record the rest or to narrow or move "
        "the AC in writing" in route
    )
    assert "the run takes the re-loop" not in route
    script = (_SKILL_ROOT / "scripts" / "operator_owed.py").read_text(encoding="utf-8")
    for name, text in {
        "gate.md": GATE,
        "docs/gate-model.md": GATE_MODEL,
        "changes fragment": FRAGMENT,
        "operator_owed.py": script,
    }.items():
        assert not re.search(r"correct-course`? narrows", _norm(text)), name
    assert "narrow the criterion through correct-course" not in _norm(script)
    for name, text in {"docs/gate-model.md": GATE_MODEL, "changes fragment": FRAGMENT}.items():
        assert "counted `pass` record" in text, name
        assert "is still owed: the record covers only part of" in _norm(text), name
    close = re.search(r"- \*\*`close`\*\*.*?(?=\n- \*\*`|\n\n)", RESOLVE, re.DOTALL)
    assert close is not None
    text = _norm(close.group(0))
    assert (
        "closes only on a `pass` record at that commit whose `id` is not among the ones the escalation "
        "names, or on the operator's written narrowing or move of the AC" in text
    )
    assert "the records already counted are not enough, since re-gating them changes nothing" in text
