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
    `**Gate-ability:** operator-evidence` and scaffolds every other AC only;
  - every surface keys the owed class on `operator-evidence`, and the plain
    `operator` tag keeps its meaning, work the dev agent builds;
  - gate.md names the live results file trace reads, asks `operator_owed.py`
    on every FAIL BEFORE the re-loop route, escalates with kind
    `operator-evidence-owed` on `owed: true`, sends an AC whose counted record
    TEA still holds below FULL to the re-loop, parks an owed AC on advance or
    defer without claiming a P2 or P3 one cannot fail the gate, and deletes the
    re-gate marker once a verdict is logged;
  - execute.md names the kind as a live one, keeps it off ucg-dev-story's
    plate, says to get an AC narrowed before pinning a stated bound, and
    re-gates (never re-drives) a story whose escalation /ucg-resolve closed;
  - ucg-resolve closes the escalation only with the records on disk, and that
    close writes `.regate-<story_id>` and resets the story's turn counter;
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
    "keeps the reloop route on owed: false": lambda s: "On `owed: false`, the `reloop` route below stands" in s,
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
    """Stories UCG already wrote tag built work `operator` (GMC 96-0-j: code-comment fixes, a
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


def test_a_counted_record_trace_holds_partial_takes_the_reloop():
    route = _norm(_operator_route())
    assert "already holds a `pass` record TEA counted at the assessed commit is not owed" in route
    assert "the run takes the re-loop, and its `bmad-correct-course` narrows the AC" in route
