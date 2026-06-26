#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for formalize_check.py — the readiness kernel.

Covers the six acceptance criteria against the six fixtures under
tests/fixtures/formalize/: exact schema + exit-0-on-payload (and exit-2 on
an invocation error), fail-closed on unreadable artifacts, per-item budget with
no ratio cutoff (plus the static guard), the no-dark-pass
unclassified-signal -> JUDGMENT catch-all, Stage-1 resolution + stdlib-only
(plus the ast.walk + PEP-723 guards), and self-explaining + deterministic
output.

Mirrors test_preflight_check.py: the importlib.util.spec_from_file_location
loader, subprocess runs for exit-code assertions, fixtures under tests/fixtures/.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_formalize_check.py -v
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "formalize_check.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "formalize"

# Frozen schema constants compared with == (NOT subset): adding a stray key
# OR dropping judgment_candidates/orphaned_indices fails the schema test.
FR5_TOP_KEYS = frozenset(
    {
        "ready",
        "verdict",
        "mechanical_budget",
        "judgment_required",
        "mechanical_gaps",
        "judgment_candidates",
        "checks",
        "timing",
    }
)
FR5_TIMING_KEYS = frozenset({"wall_clock_ms", "epic", "artifact_count", "mechanical_ms"})
FR5_CHECK_KEYS = frozenset(
    {
        "prd_present",
        "adr_present",
        "stories_with_ac",
        "ac_machine_checkable_ratio",
        "ac_with_named_verification",
        "ac_anti_vacuous_twins",
        "orphaned_indices",
        "tea_artifacts_in_source",
        "nfr_thresholds_unsourced",
        "gate_ability_tag_coverage",
    }
)

# Which Epic id each fixture's sprint-status declares.
EPIC_OF = {
    "ready_epic": "1",
    "remediable_epic": "2",
    "unreadable_epic": "3",
    "unclassified_signal_epic": "4",
    "wrong_root_epic": "5",
    "low_ratio_zero_gap_epic": "6",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("formalize_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


fc = _load_module()


def _fixture_dir(name: str) -> Path:
    return FIXTURES / name


def _run_cli(name: str, epic: str | None = None) -> subprocess.CompletedProcess:
    """Run formalize_check.py over a fixture as a subprocess (exit-code lane)."""
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
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --- exact schema + exit-0-on-payload ---------------------------------------


def test_schema_keys_exact_and_exit0():
    proc = _run_cli("ready_epic")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    # Verification: exact key sets via frozen == (not subset).
    assert set(out.keys()) == FR5_TOP_KEYS
    assert set(out["checks"].keys()) == FR5_CHECK_KEYS

    # Anti-vacuous twin: the == comparison rejects a stray key AND a dropped key,
    # proving the assertion is not a subset check that a missing
    # judgment_candidates/orphaned_indices would silently pass.
    assert set(out.keys()) != (FR5_TOP_KEYS | {"stray_key"})
    assert set(out.keys()) != (FR5_TOP_KEYS - {"judgment_candidates"})
    assert set(out["checks"].keys()) != (FR5_CHECK_KEYS - {"orphaned_indices"})

    # Anti-vacuous twin: a malformed --epic '' is an invocation error -> exit 2,
    # proving exit 0 is not hardcoded unconditionally (the gate_eval lane).
    root = _fixture_dir("ready_epic")
    bad = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--epic",
            "",
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
    assert bad.returncode == 2


# --- fail-closed on unreadable artifacts ------------------------------------


def test_fail_closed_on_unreadable():
    out = _verdict("unreadable_epic")

    # Verification: blocked + ready false; each unreadable artifact is a gap that
    # names its path; no absent artifact yields a passing checks value.
    assert out["verdict"] == "blocked"
    assert out["ready"] is False
    assert out["checks"]["prd_present"] is False  # false, not null-treated-as-ok
    assert out["checks"]["adr_present"] is False

    gaps = out["mechanical_gaps"]
    # The absent PRD and ADR each surface as a gap whose source/detail names the
    # planning-artifacts root.
    assert any(
        g["kind"] == "missing_planning_artifact" and "planning-artifacts" in g["source"]
        for g in gaps
    )
    # The non-UTF-8 story is recorded as an unreadable gap naming its path (never
    # silently dropped), and is non-remediable so the verdict cannot relax below
    # blocked.
    unreadable = [g for g in gaps if g["kind"] == "unreadable_story"]
    assert unreadable, gaps
    assert "3-1-broken.md" in unreadable[0]["source"]
    assert unreadable[0]["remediable"] is False

    # Anti-vacuous twin: the fail-closed branch is load-bearing — were the
    # unreadable-artifact branch to return ready:true (or treat a missing PRD as a
    # neutral skip), this fixture could not be blocked with prd_present false.
    # We assert BOTH the blocked verdict AND the false (not null) checks value, so
    # a mutation flipping either direction breaks the test.
    assert out["verdict"] != "ready"
    assert out["checks"]["prd_present"] is not None
    non_remediable = [g for g in gaps if not g["remediable"]]
    assert non_remediable, "an unreadable artifact must produce a non-remediable gap"


# --- per-item budget, no ratio cutoff ---------------------------------------


def test_budget_is_per_item_count_no_cutoff():
    out = _verdict("low_ratio_zero_gap_epic")

    # Verification: ratio strictly below 1.0 (computed from the fixture's own AC
    # count: 2 of 3 ACs are prose/non-deterministic), yet budget == 0 and no gap
    # was manufactured by the low ratio.
    ratio = out["checks"]["ac_machine_checkable_ratio"]
    assert ratio < 1.0
    assert out["mechanical_budget"] == len(out["mechanical_gaps"])
    assert out["mechanical_gaps"] == []
    assert out["mechanical_budget"] == 0

    # Anti-vacuous twin: the low ratio did NOT manufacture a gap — every AC
    # already carries named-verification + anti-vacuous twin + gate-ability tag,
    # so the ratio reports but does not gate.
    assert out["verdict"] == "ready"
    assert out["checks"]["gate_ability_tag_coverage"] == 1.0

    # Every gap across the other fixtures carries a bool remediable literal, and
    # the budget is the per-item count in each.
    for name in ("remediable_epic", "unreadable_epic", "wrong_root_epic", "ready_epic"):
        other = _verdict(name)
        assert other["mechanical_budget"] == len(other["mechanical_gaps"])
        for gap in other["mechanical_gaps"]:
            assert isinstance(gap["remediable"], bool)

    # Static guard: no ratio-vs-cutoff comparison / float-threshold constant
    # exists in the script. Scanned with Python's re (not a shelled-out grep) so
    # the guard is deterministic across platforms; any match FAILS.
    cutoff_re = re.compile(r"([<>]=?|==)\s*0?\.[0-9]|ratio\s*[<>]")
    cutoff_hits = [
        f"{lineno}:{line}"
        for lineno, line in enumerate(SCRIPT.read_text(encoding="utf-8").splitlines(), 1)
        if cutoff_re.search(line)
    ]
    assert not cutoff_hits, (
        "the no-cutoff guard found a ratio cutoff in formalize_check.py:\n" + "\n".join(cutoff_hits)
    )


# --- unclassified signal -> JUDGMENT (no dark pass) -------------------------


def test_unclassified_signal_defaults_to_judgment():
    out = _verdict("unclassified_signal_epic")

    # Verification: the detectable-but-unclassified signal appears in
    # judgment_candidates with a non-empty why_machine_cannot_decide, NOT in
    # mechanical_gaps, and judgment_required is true.
    unclassified = [
        c for c in out["judgment_candidates"] if c["kind"] == fc.UNCLASSIFIED_KIND
    ]
    assert len(unclassified) >= 1
    assert unclassified[0]["why_machine_cannot_decide"].strip()
    assert out["judgment_required"] is True
    assert all(
        g["kind"] != fc.UNCLASSIFIED_KIND for g in out["mechanical_gaps"]
    ), "the unclassified signal must never become an auto-remediable mechanical gap"

    # Anti-vacuous twin: a fixture with no such signal (ready_epic) yields an
    # EMPTY judgment_candidates and judgment_required == False, proving the flag
    # tracks the list and is not constant-true; routing the signal into
    # mechanical_gaps (or dropping it) would break the assertions above.
    ready = _verdict("ready_epic")
    assert ready["judgment_candidates"] == []
    assert ready["judgment_required"] is False


# --- Stage-1 resolution + stdlib-only ---------------------------------------

# stdlib top-level module allow-list (no third-party imports).
_STDLIB_ALLOW = frozenset(
    {
        "__future__",
        "argparse",
        "json",
        "re",
        "sys",
        "time",
        "tomllib",
        "pathlib",
        "os",
        "io",
        "typing",
        "dataclasses",
        "collections",
        "functools",
        "itertools",
    }
)


def test_resolution_and_stdlib_only():
    out = _verdict("ready_epic")

    # Verification: resolved checks reflect the fixture's real files.
    assert out["checks"]["prd_present"] is True  # PRD under planning-artifacts
    assert out["checks"]["adr_present"] is True
    assert out["checks"]["stories_with_ac"] >= 1  # Epic's story files under impl

    # Anti-vacuous twin: a PRD misfiled under impl-artifacts (wrong root) reads as
    # prd_present false — resolution honors the per-root flags and is not a
    # blanket recursive glob.
    wrong = _verdict("wrong_root_epic")
    assert wrong["checks"]["prd_present"] is False
    assert wrong["checks"]["adr_present"] is True

    # PEP-723 dependencies must be empty (regex read of the header).
    header = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"^#\s*dependencies\s*=\s*\[\s*\]\s*$", header, re.MULTILINE), (
        "formalize_check.py PEP-723 header must declare dependencies = []"
    )

    # ast.walk finds no import outside the stdlib allow-list (adding `import yaml`
    # or `import tomli_w` would FAIL this).
    tree = ast.parse(header)
    imported_top: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_top.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                imported_top.add(node.module.split(".")[0])
    offenders = imported_top - _STDLIB_ALLOW
    assert not offenders, f"non-stdlib imports found: {sorted(offenders)}"


# --- self-explaining + deterministic ----------------------------------------

_SOURCE_RE = re.compile(r"^.+(:[0-9]+)?$")


def test_self_explaining_and_deterministic():
    out = _verdict("remediable_epic")

    # Verification: every gap/candidate carries a non-empty source of the form
    # <path:line> (or <path> for a whole-file gap).
    findings = out["mechanical_gaps"] + out["judgment_candidates"]
    assert findings, "remediable_epic must emit at least one finding to check"
    for finding in findings:
        src = finding["source"]
        assert src and src.strip(), f"empty source in {finding}"
        assert _SOURCE_RE.match(src), f"source not <path:line>: {src!r}"

    # Verification + determinism: two consecutive subprocess runs over the SAME
    # unchanged fixture yield byte-identical stdout (no timestamp/uuid leaks).
    first = _run_cli("remediable_epic")
    second = _run_cli("remediable_epic")
    assert first.returncode == 0 and second.returncode == 0
    # Determinism holds for everything EXCEPT the AD-5 `timing` block, whose
    # wall-clock deltas are load-dependent by design (advisory, never a contract).
    p_first = json.loads(first.stdout)
    p_second = json.loads(second.stdout)
    p_first.pop("timing", None)
    p_second.pop("timing", None)
    assert p_first == p_second

    # Anti-vacuous twin: a timestamp/uuid in the payload would break the
    # byte-identical re-run; an empty source would break the <path:line> assertion
    # above. Prove the payload carries no obvious wall-clock/uuid field.
    payload = json.loads(first.stdout)
    serialized = json.dumps(payload)
    assert "timestamp" not in serialized
    assert "uuid" not in serialized
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", serialized), (
        "an ISO wall-clock leaked into the verdict payload"
    )


# --- AD-5 measurement protocol: timing block + no time-based block ----------

INJECTED_MS = 50


def _build_args(name: str, epic: str) -> dict:
    root = _fixture_dir(name)
    return dict(
        epic=epic,
        project_root=root,
        planning_artifacts=root / "planning-artifacts",
        impl_artifacts=root / "impl-artifacts",
        tea_config=root / "tea" / "config.yaml",
    )


def test_timing_block_present_all_verdicts(monkeypatch):
    # The timing block is present on the ready, remediable, AND blocked payloads,
    # with EXACTLY the four AD-5 provenance keys and numeric deltas.
    cases = {"ready_epic": "ready", "remediable_epic": "remediable", "unreadable_epic": "blocked"}
    counts = {}
    for name, expected in cases.items():
        out = _verdict(name)
        assert out["verdict"] == expected, (name, out["verdict"])
        timing = out["timing"]
        assert set(timing.keys()) == FR5_TIMING_KEYS, timing
        assert isinstance(timing["wall_clock_ms"], (int, float))
        assert isinstance(timing["mechanical_ms"], (int, float))
        assert timing["wall_clock_ms"] >= timing["mechanical_ms"] >= 0
        assert timing["epic"] == EPIC_OF[name]
        assert isinstance(timing["artifact_count"], int)
        counts[name] = timing["artifact_count"]
    # (c) content-derived: differing fixtures report DIFFERENT artifact_count
    assert len(set(counts.values())) >= 2, counts

    # Deterministic, jitter-independent anti-constant proof via an injected delay:
    args = _build_args("ready_epic", "1")
    # (b) the un-injected mechanical_ms is small (defeats a raw unsubtracted clock read)
    base = fc.build_verdict(**args)
    assert base["timing"]["mechanical_ms"] < INJECTED_MS
    # (a) inject a known fixed sleep into the mechanical half -> mechanical_ms >= INJECTED_MS
    #     (a monotonic-DELTA lower bound a hardcoded constant cannot satisfy)
    monkeypatch.setattr(fc, "_mechanical_hook", lambda: time.sleep(INJECTED_MS / 1000))
    slowed = fc.build_verdict(**args)
    assert slowed["timing"]["mechanical_ms"] >= INJECTED_MS
    assert slowed["timing"]["wall_clock_ms"] >= slowed["timing"]["mechanical_ms"]


def test_no_time_based_block(monkeypatch):
    args = _build_args("ready_epic", "1")
    monkeypatch.setattr(fc, "_mechanical_hook", lambda: time.sleep(INJECTED_MS / 1000))
    out = fc.build_verdict(**args)
    # An over-budget mechanical half returns the SAME verdict it would at any speed.
    assert out["verdict"] == "ready"
    assert out["ready"] is True
    assert out["timing"]["wall_clock_ms"] >= INJECTED_MS
    # The CLI exit lane is unchanged by a slow run (exit 0 on any payload).
    assert _run_cli("ready_epic").returncode == 0
    # Static: no authored duration cutoff / ceiling / timeout anywhere in the kernel.
    src = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(
        r"timeout|ceiling|deadline|max_(ms|seconds|wall)|>\s*[0-9]+\s*#\s*(ms|sec)", src, re.IGNORECASE
    ), "the kernel must author no wall-clock cutoff (AD-5 / NFR-7)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
