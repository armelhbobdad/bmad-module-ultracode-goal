#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for the four permanent JUDGMENT floor classes in formalize_check.py.

These cover the four permanent hard-block detections — vacuous AC, leaked TEA
artifact, orphaned never-green index, invented NFR threshold — plus the no-dark-
pass catch-all, over the committed fixture corpus under
tests/fixtures/floor/. Each defect fixture has a sound/resolved TWIN that must NOT
fire the detection: the twin is the anti-vacuous proof that the check keys on the
DEFECT (a tautology / a wrong-location TEA file / a dangling citation / a missing
source) and not on the mere presence of an AC / a TEA file / a citation / a
number.

Floor pin: the two never-machine-clearable classes (vacuous_ac,
invented_nfr_threshold) are emitted ONLY as judgment_candidates. The grep/source
assertion in test_floor_classes_carry_frozen_remediable_literals is intentionally
MUTATION-SENSITIVE: flipping either kind to remediable=True or routing it into
mechanical_gaps must FAIL this test — it pins the human-authored frozen-literal
classification (the preflight_check.py:411-457 convention) so a JUDGMENT-floor
class can never be silently re-tagged auto-remediable.

Mirrors test_preflight_check.py / test_formalize_check.py: the
importlib.util.spec_from_file_location loader, subprocess runs for the exit-code
lane, fixtures under tests/fixtures/floor/.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_formalize_check_floor.py -v
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "formalize_check.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "floor"

# The four named floor-class kinds + the reserved catch-all sentinel.
NAMED_FLOOR_KINDS = frozenset(
    {"vacuous_ac", "leaked_tea_artifact", "orphaned_index", "invented_nfr_threshold"}
)

# Which Epic id each floor fixture's sprint-status declares.
EPIC_OF = {
    "all_clean": "7",
    "vacuous_ac": "8",
    "vacuous_ac_sound": "8",
    "leaked_tea": "9",
    "leaked_tea_clean": "9",
    "orphaned_index": "10",
    "orphaned_index_resolved": "10",
    "invented_threshold": "11",
    "sourced_threshold": "11",
    "unclassified_signal": "12",
    "unclassified_signal_removed": "12",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("formalize_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


fc = _load_module()

_SOURCE_RE = re.compile(r".+:\d+")
_PATH_OR_SOURCE_RE = re.compile(r".+(:\d+)?$")


def _fixture_dir(name: str) -> Path:
    return FIXTURES / name


def _run_cli(name: str, epic: str | None = None) -> subprocess.CompletedProcess:
    """Run formalize_check.py over a floor fixture as a subprocess (exit-0 lane)."""
    root = _fixture_dir(name)
    if epic is None:
        epic = EPIC_OF[name]
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--epic",
            epic,
            "--project-root",
            str(root),
            "--planning-artifacts",
            str(root / "planning-artifacts"),
            "--impl-artifacts",
            str(root / "impl-artifacts"),
            "--tea-config",
            str(root / "tea" / "config.yaml"),
        ],
        capture_output=True,
        text=True,
    )


def _verdict(name: str, epic: str | None = None) -> dict:
    proc = _run_cli(name, epic)
    # Exit-code lane: exit 0 on any produced payload (a non-ready verdict is
    # a valid result, not an invocation error).
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --- vacuous_ac -> JUDGMENT, blocked ----------------------------------------


def test_vacuous_ac_emits_judgment_blocked():
    out = _verdict("vacuous_ac")

    assert out["verdict"] == "blocked"
    assert out["judgment_required"] is True

    vac = [c for c in out["judgment_candidates"] if c["kind"] == "vacuous_ac"]
    assert len(vac) == 1
    assert _SOURCE_RE.match(vac[0]["source"]), vac[0]["source"]
    assert vac[0]["why_machine_cannot_decide"].strip()

    # The vacuous-AC source never appears as a mechanical_gap (NEVER remediable).
    vac_source = vac[0]["source"]
    assert not any(g["source"] == vac_source for g in out["mechanical_gaps"])
    assert all(g["kind"] != "vacuous_ac" for g in out["mechanical_gaps"])


def test_vacuous_ac_sound_is_not_flagged():
    # Anti-vacuous twin: the SAME story with the vacuous AC replaced by a
    # deterministic machine-checkable AC fires ZERO vacuous_ac candidates and is
    # not blocked on that class — proving the detection keys on the tautological
    # DEFECT, not on the presence of any AC.
    out = _verdict("vacuous_ac_sound")
    assert [c for c in out["judgment_candidates"] if c["kind"] == "vacuous_ac"] == []
    # The sound twin carries named-verification + an anti-vacuous twin, so it is
    # fully READY — assert == "ready" (not merely != "blocked"), so a mutation that
    # introduced a NEW medium gap (verdict "remediable") cannot false-green this.
    assert out["verdict"] == "ready"


# --- leaked_tea_artifact -> MECHANICAL move ---------------------------------


def test_leaked_tea_artifact_is_mechanical_move():
    out = _verdict("leaked_tea")

    assert out["checks"]["tea_artifacts_in_source"]  # truthy / non-zero

    leaked = [
        g for g in out["mechanical_gaps"] if g["kind"] == "leaked_tea_artifact"
    ]
    assert len(leaked) == 1
    assert leaked[0]["remediable"] is True
    assert _PATH_OR_SOURCE_RE.match(leaked[0]["source"]), leaked[0]["source"]

    # That same source never appears in judgment_candidates (a MOVE is mechanical).
    leaked_source = leaked[0]["source"]
    assert not any(c["source"] == leaked_source for c in out["judgment_candidates"])


def test_correctly_placed_tea_artifact_is_not_flagged():
    # Anti-vacuous twin: the identical TEA artifact placed correctly under the
    # trace_output root yields a falsy tea_artifacts_in_source and zero leaked
    # gaps — proving the check keys on the WRONG LOCATION (path classification),
    # not on the mere presence of a TEA file.
    out = _verdict("leaked_tea_clean")
    assert not out["checks"]["tea_artifacts_in_source"]
    assert [
        g for g in out["mechanical_gaps"] if g["kind"] == "leaked_tea_artifact"
    ] == []


def test_leaked_tea_excludes_ucg_impl_artifacts(tmp_path):
    """Regression: a UCG story-note or run-sentinel
    whose filename merely carries a TEA marker token (because the STORY SLUG does) is
    NOT a leaked TEA artifact — only a genuine TEA output is flagged. Skipping these is
    load-bearing: they live under impl-artifacts by design, so flagging one would
    deadlock the budget==0 launch gate (the only clearing action, a MOVE, misfiles it).
    Exercises all three identity-exclusion branches; the genuine leak stays flagged.
    """
    impl = tmp_path / "impl-artifacts"
    impl.mkdir()
    # (1) story-note: <epic>-<story>-<slug>.md whose slug carries "test-design"
    (impl / "2-7-tea-shaping-test-design-nfr.md").write_text(
        "---\nstory_id: 2-7\nauthored_by: ultracode-goal run epic-2\n---\n# note\n",
        encoding="utf-8",
    )
    # (2) run sentinels: dotfiles whose name carries "test-design"
    (impl / ".tests-ran-2-7-test-design-nfr").write_text("ran\n", encoding="utf-8")
    (impl / ".budget-2-7-test-design.json").write_text("{}\n", encoding="utf-8")
    # (3) UCG-authored note NOT matching the N-N- prefix but carrying "trace" — caught
    #     by the authored_by frontmatter identity check
    (impl / "epic-2-trace-notes.md").write_text(
        "---\nauthored_by: ultracode-goal\n---\n# retro trace\n", encoding="utf-8"
    )
    # genuine leaked TEA artifact — must STILL be flagged (anti-vacuous: the narrowing
    # did not disable the detector)
    (impl / "test-design-9-1.md").write_text("# Test Design\n", encoding="utf-8")

    leaked = {p.name for p in fc._leaked_tea_artifacts(impl, None)}
    assert leaked == {"test-design-9-1.md"}, leaked


# --- orphaned never-green index ---------------------------------------------


def test_orphaned_index_is_caught():
    out = _verdict("orphaned_index")

    assert out["checks"]["orphaned_indices"] >= 1
    assert out["verdict"] != "ready"

    # Exactly one finding (across mechanical_gaps + judgment_candidates) names the
    # seeded dangling id in its detail/why, and carries a source.
    findings = out["mechanical_gaps"] + out["judgment_candidates"]
    naming = [
        f
        for f in findings
        if "10-9-ghost-story"
        in (f.get("detail", "") + f.get("why_machine_cannot_decide", ""))
    ]
    assert len(naming) == 1, naming
    assert naming[0].get("source")


def test_resolved_index_is_not_flagged():
    # Anti-vacuous twin: the same cited id IS declared by a real story/test in the
    # set -> orphaned_indices == 0 and zero orphaned-index findings — proving the
    # check resolves references against the actual declared set, not flagging
    # every citation.
    out = _verdict("orphaned_index_resolved")
    assert out["checks"]["orphaned_indices"] == 0
    findings = out["mechanical_gaps"] + out["judgment_candidates"]
    assert [f for f in findings if f["kind"] == "orphaned_index"] == []


# --- invented_nfr_threshold hard-blocks -------------------------------------


def test_invented_nfr_threshold_hard_blocks():
    out = _verdict("invented_threshold")

    assert out["checks"]["nfr_thresholds_unsourced"] >= 1

    inv = [
        c
        for c in out["judgment_candidates"]
        if c["kind"] == "invented_nfr_threshold"
    ]
    assert len(inv) == 1
    assert _SOURCE_RE.match(inv[0]["source"]), inv[0]["source"]
    assert "source" in inv[0]["why_machine_cannot_decide"].lower()
    assert out["verdict"] == "blocked"

    # The invented-threshold class can never be machine-cleared.
    assert all(
        g["kind"] != "invented_nfr_threshold" for g in out["mechanical_gaps"]
    )


def test_sourced_or_unknown_threshold_is_not_flagged():
    # Anti-vacuous twin: the same NFR with the threshold citing an upstream
    # path:line (or marked UNKNOWN) yields nfr_thresholds_unsourced == 0 and zero
    # invented candidates — proving the detector keys on the MISSING SOURCE, not
    # on the mere presence of a number.
    out = _verdict("sourced_threshold")
    assert out["checks"]["nfr_thresholds_unsourced"] == 0
    assert [
        c
        for c in out["judgment_candidates"]
        if c["kind"] == "invented_nfr_threshold"
    ] == []


# --- frozen human-authored remediable literals ------------------------------


def test_floor_classes_carry_frozen_remediable_literals():
    # (a) Over every fixture: each mechanical_gaps finding carries a 'remediable'
    # bool, and no judgment_candidate carries remediable==True (no auto-clear path
    # for a judgment defect).
    for name in EPIC_OF:
        out = _verdict(name)
        for gap in out["mechanical_gaps"]:
            assert "remediable" in gap
            assert isinstance(gap["remediable"], bool), (name, gap)
        for cand in out["judgment_candidates"]:
            assert cand.get("remediable") is not True, (name, cand)

    source = SCRIPT.read_text(encoding="utf-8")

    # (b) Source-level grep: the two never-clearable JUDGMENT-floor kinds are
    # present as literals in the script (rc == 0).
    grep = subprocess.run(
        ["grep", "-nE", r"'vacuous_ac'|'invented_nfr_threshold'", str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert grep.returncode == 0, "the two JUDGMENT-floor kind literals must exist"

    # And neither literal kind co-occurs with remediable=True in the same finding
    # constructor block — in EITHER quote style, so the assertion inspects the real
    # emission sites and not only the frozen allow-list declaration. We slice the
    # enclosing { ... } literal around every occurrence of the kind (single OR
    # double quoted) and assert it carries no remediable-true marker. A mutation
    # flipping vacuous_ac / invented_nfr_threshold to remediable=True (or moving it
    # into a mechanical_gaps constructor with "remediable": True) FAILS here —
    # this is the floor pin and is intentionally mutation-sensitive.
    floor_kind_re = re.compile(r"""['"](?:vacuous_ac|invented_nfr_threshold)['"]""")
    remediable_true_re = re.compile(r"""remediable['"]?\s*[:=]\s*True""")
    matched_any = False
    for match in floor_kind_re.finditer(source):
        matched_any = True
        start = source.rfind("{", 0, match.start())
        end = source.find("}", match.end())
        assert start != -1 and end != -1
        block = source[start : end + 1]
        assert not remediable_true_re.search(block), (
            "a JUDGMENT-floor kind co-occurs with remediable=True in a finding "
            "constructor block:\n%s" % block
        )
    assert matched_any, "expected the floor-kind literals to appear in source"


# --- no-dark-pass catch-all -------------------------------------------------


def test_unclassified_signal_defaults_to_judgment_no_dark_pass():
    out = _verdict("unclassified_signal")

    assert out["judgment_required"] is True
    assert out["verdict"] != "ready"

    cat = [
        c for c in out["judgment_candidates"] if c["kind"] == "unclassified_signal"
    ]
    assert len(cat) >= 1
    # The catch-all kind is OUTSIDE the four named classes (it is the reserved
    # sentinel, provably not a re-detected named class).
    assert all(c["kind"] not in NAMED_FLOOR_KINDS for c in cat)
    assert fc.UNCLASSIFIED_KIND == "unclassified_signal"
    assert fc.UNCLASSIFIED_KIND not in NAMED_FLOOR_KINDS

    # All four named checks are CLEAN for this fixture — so nothing but the
    # catch-all forces verdict != ready.
    assert out["checks"]["nfr_thresholds_unsourced"] == 0
    assert out["checks"]["orphaned_indices"] == 0
    assert not out["checks"]["tea_artifacts_in_source"]
    assert not [
        c for c in out["judgment_candidates"] if c["kind"] == "vacuous_ac"
    ]


def test_all_clean_fixture_is_ready():
    # Anti-vacuous twin (1): a fixture with no seeded defect of any class is ready
    # — proving the catch-all is not a vacuous always-block stub.
    out = _verdict("all_clean")
    assert out["verdict"] == "ready"
    assert out["judgment_required"] is False
    assert out["judgment_candidates"] == []
    assert out["mechanical_budget"] == 0


def test_unclassified_signal_removed_is_ready():
    # Anti-vacuous twin (2): a near-identical copy of the unclassified_signal
    # fixture with ONLY the detectable anomaly deleted (the classifier reaches
    # nothing) is ready — proving the catch-all keys on the unclassified SIGNAL
    # itself, not on the fixture's mere structure/layout.
    out = _verdict("unclassified_signal_removed")
    assert out["verdict"] == "ready"
    assert out["judgment_required"] is False
    assert [
        c for c in out["judgment_candidates"] if c["kind"] == "unclassified_signal"
    ] == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
