#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contracts for the generalize-to-class re-loop route and the sweep-scope
marker contract (writer side in execute.md, reader side in gate.md).

gate_eval.py enforces the scope cap mechanically and test_gate_eval.py pins
that; these tests pin the INSTRUCTION side, which no script test can reach:
that execute.md still tells a run to write scope=/packages= into the marker,
that gate.md still routes a re-loop through the generalize step and the class
ledger, and that the cap-only case is carved out of the ceremony. Deleting or
paraphrasing away any of those policies must red HERE while the script tests
stay green - dropping the writer side alone would live-lock every story at
reloop with the whole script suite passing.
"""

from __future__ import annotations

import re
from pathlib import Path

REFS = Path(__file__).resolve().parents[2] / "references"
GATE = (REFS / "gate.md").read_text(encoding="utf-8")
EXECUTE = (REFS / "execute.md").read_text(encoding="utf-8")


def _reloop_bullet() -> str:
    """The reloop route's own text, not the whole file - locality matters:
    prose that drifts into another section is prose a reader never meets at
    the moment the verdict routes."""
    start = GATE.index("- **`reloop`**")
    end = GATE.index("- **`escalate`**")
    assert start < end
    return GATE[start:end]


def _sweep_and_paragraph() -> str:
    start = GATE.index("**The sweep-scope AND")
    return GATE[start : GATE.index("\n\n", start)]


# --- gate.md: the generalize step ---------------------------------------------


def test_reloop_route_generalizes_before_fixing():
    bullet = _reloop_bullet()
    assert "**generalize before fixing.**" in bullet
    assert re.search(r"name, in ONE line, the defect CLASS", bullet)
    assert re.search(r"fix must close the CLASS", bullet)
    assert "Record one `class:` line per finding" in bullet


def test_reloop_route_names_the_epic_scoped_ledger_append_only():
    bullet = _reloop_bullet()
    # Both mentions carry the epic-scoped name: the evidence read and the append.
    assert bullet.count(".class-ledger-<epic_id>.md") == 2
    assert "**append-only**" in bullet
    assert re.search(r"named for the Epic", bullet), (
        "the ledger's epic scoping is load-bearing: an unscoped ledger grows "
        "across Epics forever and warns every Epic about every other's classes"
    )


def test_flat_score_tripwire_is_profile_scoped():
    bullet = _reloop_bullet()
    assert re.search(r"moved `review_score` by less than 3", bullet)
    # review_score is null on every --light evaluation (only the production AND
    # sets it), so the tripwire must name its light-profile trigger or it is
    # vacuous on exactly the runs this module's own epics use.
    assert re.search(r"under `--light` no review score exists", bullet)


def test_cap_only_reloop_skips_the_ceremony():
    bullet = _reloop_bullet()
    assert "**A cap-only re-loop skips the ceremony.**" in bullet
    assert re.search(r"writing no `class:` lines, appending nothing to the ledger", bullet)
    assert re.search(r"skipping `bmad-correct-course` entirely", bullet)
    assert re.search(r"do not count toward the flat-score tripwire", bullet)


def test_step1_reads_the_ledger():
    assert ".class-ledger-<epic_id>.md" in EXECUTE
    assert re.search(r"a re-loop pre-booked", EXECUTE), (
        "step 1 must read the ledger into the dev/review context, or the "
        "cross-story recurrence the ledger exists to close stays open"
    )


# --- gate.md: the sweep-scope AND (reader side) --------------------------------


def test_sweep_scope_and_paragraph_pins_the_cap():
    para = _sweep_and_paragraph()
    assert re.search(r"capped at `reloop`", para)
    assert re.search(r"the cap moves `defer` too", para)
    assert re.search(
        r"missing marker, a marker with no `scope=` line, or a value the reader does not recognise",
        para,
    )
    assert re.search(r"`--epic-level` refuses the flag outright", para)
    assert re.search(r"a drift to fix, not a laxer mode to use", para)


def test_every_per_story_invocation_carries_tests_ran():
    """Three per-story invocation sites: the production command, the light
    command, and the non-web hand-authored path's inline invocation. A fourth
    per-story invocation added without the flag will not red this count - but
    dropping the flag from any of the three will."""
    assert (
        GATE.count("--tests-ran {workflow.implementation_artifacts}/.tests-ran-<story_id>")
        >= 3
    )


# --- execute.md: the writer side ----------------------------------------------


def test_step2_writes_scope_and_packages_lines():
    assert re.search(r"`scope=<full\|scoped>` naming which sweep form this green run was", EXECUTE)
    assert re.search(
        r"`packages=<the resolved package list>` copied from the runner's own printout, never hand-typed",
        EXECUTE,
    )


def test_reloop_may_scope_paragraph_present_and_bounded():
    assert (
        "**A re-loop iteration may scope the sweep; the cycle that expects to advance owes the full one.**"
        in EXECUTE
    )
    assert "**Print the resolved package list**" in EXECUTE
    # The baseline ref is the story's own end marker, not a free choice.
    assert re.search(r"\.commit-<story_id>`, the previous cycle's end marker", EXECUTE)
    assert re.search(r"refuses to advance a story off a `scope=scoped` marker", EXECUTE)


def test_step4_hook_rejection_restates_scope_lines():
    assert re.search(r"`scope=`/`packages=` re-stated for what the re-run actually was", EXECUTE)


def test_step5_fresh_marker_restates_scope():
    assert re.search(r"The fresh marker also re-states `scope=`", EXECUTE)


def test_gate_owed_resume_rewrites_the_marker_at_full_scope():
    assert re.search(r"\*\*even on a green first try\*\*", EXECUTE)
    assert re.search(r"the gate reads the marker THIS session leaves behind", EXECUTE)
