#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contracts for gate-time isolation (measure the commit, not the working
tree) and the delta cycle profile's instruction side.

gate_eval.py's delta cap is pinned by test_gate_eval.py; these tests pin what
no script test can: that gate.md still orders assessors onto a worktree of the
commit under assessment (with the three caveats that were each a measured
failure when skipped), and that the delta profile's use is bounded by the
mechanical attribution fallback rather than judgment.
"""

from __future__ import annotations

import re
from pathlib import Path

REFS = Path(__file__).resolve().parents[2] / "references"
GATE = (REFS / "gate.md").read_text(encoding="utf-8")


def _worktree_section() -> str:
    start = GATE.index("## Measure the commit, not the working tree")
    return GATE[start : GATE.index("\n## ", start + 1)]


def _delta_paragraph() -> str:
    start = GATE.index("**The delta cycle profile")
    return GATE[start : GATE.index("\n\n", start)]


# --- the worktree isolation rule ----------------------------------------------


def test_assessors_measure_a_worktree_of_the_commit():
    section = _worktree_section()
    assert "`git worktree add <tmp-path> <commit>`" in section
    assert "`git worktree remove --force <tmp-path>`" in section
    assert re.search(r"binds every assessor that runs or times anything", section)


def test_worktree_caveat_dependency_dirs_prefer_symlink_over_node_path():
    """NODE_PATH is honoured by the CJS resolver only; an ESM gate set breaks
    silently under it. The preference itself is asserted, not just the factoid:
    a rewrite recommending NODE_PATH while keeping the factoid inverted-in-place
    passed the factoid-only version of this test."""
    section = _worktree_section()
    assert re.search(r"prefer the symlink over resolver environment variables", section)
    assert re.search(r"Node's ESM resolver ignores `NODE_PATH` \(it is honoured by the CJS resolver only\)", section)
    assert re.search(r"root \*and\* nested", section)


def test_worktree_caveat_untracked_inputs_enumerated():
    section = _worktree_section()
    assert re.search(r"enumerate what the declared gate commands actually read", section)
    assert re.search(r"measures a different harness", section)


def test_worktree_licenses_no_overlap():
    """Part B (build N+1 while N gates) is a separate decision with its own
    risk budget; this section must say the sequence is unchanged or it becomes
    the smuggling route for it."""
    section = _worktree_section()
    assert re.search(r"licenses no overlap", section)
    assert re.search(r"sequential spine is unchanged", section)


def test_worktree_honesty_line_in_decision_log():
    section = _worktree_section()
    assert re.search(r"whether the gate measured a worktree or the main tree", section)
    assert re.search(r"false claim about the evidence", section)


# --- the delta cycle profile (instruction side) --------------------------------


def test_delta_profile_bounded_by_mechanical_attribution_fallback():
    """Trigger AND consequent: an inverted fallback ("assign it to the likeliest
    dimension and proceed") satisfied the trigger-only version of this test."""
    para = _delta_paragraph()
    assert "`--cycle-profile delta`" in para
    assert re.search(r"caps the verdict at `reloop`", para)
    assert re.search(r"fallback is mechanical, not judgment", para)
    assert re.search(r"lacks a clean dimension attribution.*run the full gate", para, re.S)


def test_delta_profile_pairs_with_the_sweep_split():
    para = _delta_paragraph()
    assert re.search(r"mid-loop cycles ride `scope=scoped` sweeps and delta gates", para)
    assert re.search(r"advance-bound cycle runs the full sweep and the full gate", para)


def test_delta_profile_is_not_a_light_mode():
    """The exact policy sentence, not a satisfiable-by-inversion wildcard."""
    para = _delta_paragraph()
    assert "so the profile buys nothing there; omit it" in para


def test_delta_recheck_base_is_recorded_state():
    """The non-failing assessors' diff base must be computable from the record:
    the previous gate's assessed-commit line, with a missing line routing to
    the full gate rather than to a guessed base."""
    para = _delta_paragraph()
    assert re.search(r"previous gate's `assessed-commit` line", para)
    assert re.search(r"without that line[^.]*run the full gate", para)
    # And the Run-the-gate section actually orders that line written.
    assert re.search(r"log `assessed-commit: <sha>`", GATE)


def test_worktree_outputs_land_in_the_main_tree():
    """The fail-open this pins: an artifact written into the worktree dies with
    it, and the gate re-reads the previous cycle's same-named artifact as
    current (name-based resolution, no freshness check)."""
    section = _worktree_section()
    assert re.search(r"Their OUTPUTS go home", section)
    assert re.search(r"resolved to absolute paths against `\{project-root\}`", section)
    assert re.search(r"the main tree is the record", section)
    assert re.search(r"stale PASS advancing a story whose fresh assessment was never read", section)


def test_worktree_placement_and_teardown_are_pinned():
    section = _worktree_section()
    assert ".gate-worktree-<story_id>" in section
    assert "`git worktree remove --force <tmp-path>`" in section
    assert "`git worktree prune`" in section
    assert re.search(r"never an improvised repo-root directory", section)


def test_cap_only_carveout_names_both_caps_and_drops_the_flag():
    """A delta-cap-only reloop must reach the ceremony skip, and the re-gate
    must drop the flag or it caps again forever."""
    assert re.search(r"the sweep-scope cap, the delta-profile cap, or both", GATE)
    assert re.search(r"dropping\s+`--cycle-profile`", GATE)
