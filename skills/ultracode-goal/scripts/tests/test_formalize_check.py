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
import shutil
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
        "judged_candidates",
        "scan",
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
        "decomposed_children",
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
        "hashlib",
        "json",
        "re",
        "sys",
        "time",
        "tomllib",
        "unicodedata",
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
    # Determinism holds for everything EXCEPT the `timing` block, whose
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


# --- measurement protocol: timing block + no time-based block --------------

INJECTED_MS = 50
# time.sleep() can wake EARLY by up to the OS timer granularity (~16 ms on
# Windows); the injected-delay lower bound subtracts that slack so it stays a
# real anti-constant proof (a hardcoded/raw-non-delta reads ~0, nowhere near
# this floor) without flaking on a coarse-timer runner.
SLEEP_SLACK_MS = 16
INJECTED_FLOOR_MS = INJECTED_MS - SLEEP_SLACK_MS


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
    # with EXACTLY the four provenance keys and numeric deltas.
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
    assert slowed["timing"]["mechanical_ms"] >= INJECTED_FLOOR_MS
    assert slowed["timing"]["wall_clock_ms"] >= slowed["timing"]["mechanical_ms"]


def test_no_time_based_block(monkeypatch):
    args = _build_args("ready_epic", "1")
    monkeypatch.setattr(fc, "_mechanical_hook", lambda: time.sleep(INJECTED_MS / 1000))
    out = fc.build_verdict(**args)
    # An over-budget mechanical half returns the SAME verdict it would at any speed.
    assert out["verdict"] == "ready"
    assert out["ready"] is True
    assert out["timing"]["wall_clock_ms"] >= INJECTED_FLOOR_MS
    # The CLI exit lane is unchanged by a slow run (exit 0 on any payload).
    assert _run_cli("ready_epic").returncode == 0
    # Static: no authored duration cutoff / ceiling / timeout anywhere in the kernel.
    src = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(
        r"timeout|ceiling|deadline|max_(ms|seconds|wall)|>\s*[0-9]+\s*#\s*(ms|sec)", src, re.IGNORECASE
    ), "the kernel must author no wall-clock cutoff"


# --- empty in-scope story set must not read ready ---------------------------

STORY_BODY = """# Story 7-1: Kernel

## Acceptance Criteria

1. Running `pytest tests/test_kernel.py::test_reads_config` exits 0, and the
   anti-vacuous twin `test_reads_config_missing_reds` fails when the config is
   removed. gate-ability: mechanical.
"""


def _mini_project(tmp_path, with_story: bool):
    """A minimal Epic-7 project whose ONLY variable is whether a story exists.

    Everything else the kernel reads is present and readable, so the empty story
    set is the sole difference between the two runs.
    """
    root = tmp_path / ("with_story" if with_story else "no_story")
    planning = root / "planning-artifacts"
    impl = root / "impl-artifacts"
    planning.mkdir(parents=True)
    impl.mkdir(parents=True)
    (planning / "prd-fixture.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture-fixture.md").write_text("# Architecture\n", encoding="utf-8")
    (impl / "sprint-status.yaml").write_text(
        "generated: fixture\ndevelopment_status:\n  epic-7: in-progress\n  7-1-kernel: backlog\n",
        encoding="utf-8",
    )
    if with_story:
        (impl / "7-1-kernel.md").write_text(STORY_BODY, encoding="utf-8")
    return root


def _run_project(root: Path) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--epic",
            "7",
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
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_zero_in_scope_stories_is_remediable_not_ready(tmp_path):
    # The fail-open this closes: with no story files, every per-story and per-AC
    # check iterates nothing, so the Epic used to score a clean zero-gap `ready`
    # vacuously — the exact verdict the launch gate treats as go.
    out = _run_project(_mini_project(tmp_path, with_story=False))

    assert out["verdict"] == "remediable"
    assert out["ready"] is False
    assert out["checks"]["stories_with_ac"] == 0

    gaps = [g for g in out["mechanical_gaps"] if g["kind"] == "no_in_scope_stories"]
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["severity"] == "high"
    # Remediable: the create-story scaffold generates the missing story files.
    assert gap["remediable"] is True
    assert "7" in gap["detail"]
    assert "impl-artifacts" in gap["detail"]
    assert "impl-artifacts" in gap["source"]

    # It counts toward the budget exactly like every other gap (not special-cased
    # out of it), which is what moves the verdict off `ready`.
    assert out["mechanical_budget"] == len(out["mechanical_gaps"])
    assert out["mechanical_budget"] >= 1


def test_non_empty_story_set_emits_no_empty_set_gap(tmp_path):
    # Anti-vacuous twin (data): the SAME project with one story file present
    # fires ZERO no_in_scope_stories gaps — proving the gap keys on the EMPTY
    # story set and not merely on running the kernel over this project shape.
    out = _run_project(_mini_project(tmp_path, with_story=True))

    assert all(g["kind"] != "no_in_scope_stories" for g in out["mechanical_gaps"])
    assert out["checks"]["stories_with_ac"] == 1


_EMPTY_STORY_SET_GUARD = "    if not story_paths:\n"


def test_mutant_without_empty_story_set_gap_reads_ready(tmp_path):
    """Twin for test_zero_in_scope_stories_is_remediable_not_ready.

    Concrete mutation: neutralize the empty-story-set guard in build_verdict
    (`if not story_paths:` -> `if False:`) on a COPY of the script, so no gap is
    appended. The zero-story project then reports `ready` with mechanical_budget
    0 — the pre-fix fail-open — which reds the verdict/budget assertions in the
    named test above. If `remediable` survived this mutation, the guard would not
    be what produces it and the named test would prove nothing.
    """
    src = SCRIPT.read_text(encoding="utf-8")
    assert _EMPTY_STORY_SET_GUARD in src, "mutation anchor drifted out of formalize_check.py"
    mutant_dir = tmp_path / "src"
    mutant_dir.mkdir()
    mutant = mutant_dir / "mutant_formalize_check.py"
    mutant.write_text(src.replace(_EMPTY_STORY_SET_GUARD, "    if False:\n", 1), encoding="utf-8")

    root = _mini_project(tmp_path, with_story=False)
    proc = subprocess.run(
        [
            sys.executable, str(mutant), "--epic", "7",
            "--project-root", str(root),
            "--planning-artifacts", str(root / "planning-artifacts"),
            "--impl-artifacts", str(root / "impl-artifacts"),
            "--tea-config", str(root / "tea" / "config.yaml"),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    assert out["verdict"] == "ready"
    assert out["mechanical_budget"] == 0
    assert out["mechanical_gaps"] == []
    assert out["checks"]["stories_with_ac"] == 0


# ---------------------------------------------------------------------------
# The same empty-set fail-open, one level down: a story that HAS a file but
# declares no acceptance criteria.
# ---------------------------------------------------------------------------

# Three shapes a story file can take while asserting nothing. All three used to
# read `ready`: the per-AC loop iterates zero times, so no gap is appended.
AC_LESS_BODIES = {
    "empty_file": "",
    "heading_without_items": "# Story 7-1: Kernel\n\n## Acceptance Criteria\n",
    "prose_without_ac_section": (
        "# Story 7-1: Kernel\n\nAs an operator I want the kernel to read config.\n\n"
        "## Tasks\n\n- wire it up\n"
    ),
}


def _ac_less_project(tmp_path, shape: str):
    """The `_mini_project` shape with the story present but asserting nothing.

    Only the story BODY varies from the `with_story=True` fixture, so an
    AC-less story is the sole difference from a passing run.
    """
    root = _mini_project(tmp_path, with_story=True)
    (root / "impl-artifacts" / "7-1-kernel.md").write_text(
        AC_LESS_BODIES[shape], encoding="utf-8"
    )
    return root


@pytest.mark.parametrize("shape", sorted(AC_LESS_BODIES))
def test_story_without_ac_is_remediable_not_ready(tmp_path, shape):
    # The fail-open this closes: `no_in_scope_stories` keys on the story file
    # being ABSENT, but a file that exists and declares no AC iterates the
    # per-AC loop zero times just the same, scoring a clean zero-gap `ready`
    # with stories_with_ac 0 - the exact verdict the launch gate treats as go.
    out = _run_project(_ac_less_project(tmp_path, shape))

    assert out["verdict"] == "remediable"
    assert out["ready"] is False
    assert out["checks"]["stories_with_ac"] == 0

    gaps = [g for g in out["mechanical_gaps"] if g["kind"] == "story_without_ac"]
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["severity"] == "high"
    # Remediable: the create-story scaffold authors the AC section.
    assert gap["remediable"] is True
    assert "7-1-kernel.md" in gap["source"]

    # It counts toward the budget like every other gap, which is what moves the
    # verdict off `ready`.
    assert out["mechanical_budget"] == len(out["mechanical_gaps"])


def test_story_with_ac_emits_no_ac_less_gap(tmp_path):
    # Anti-vacuous twin (data): the SAME project whose story declares a real AC
    # fires ZERO story_without_ac gaps - proving the gap keys on the absent AC
    # set and not merely on running the kernel over this project shape.
    out = _run_project(_mini_project(tmp_path, with_story=True))

    assert all(g["kind"] != "story_without_ac" for g in out["mechanical_gaps"])
    assert out["checks"]["stories_with_ac"] == 1


def test_mutant_without_ac_less_gap_reads_ready(tmp_path):
    """Twin for test_story_without_ac_is_remediable_not_ready.

    Concrete mutation: neutralize the AC-less branch in build_verdict
    (`else:` -> `elif False:` on the `if ac_blocks:` arm) on a COPY of the
    script, so no gap is appended. The AC-less project then reports `ready`
    with mechanical_budget 0 - the pre-fix fail-open - which reds the
    verdict/budget assertions in the named test above.
    """
    src = SCRIPT.read_text(encoding="utf-8")
    anchor = "            stories_with_ac += 1\n        else:\n"
    assert anchor in src, "mutation anchor drifted out of formalize_check.py"
    mutant_dir = tmp_path / "src"
    mutant_dir.mkdir()
    mutant = mutant_dir / "mutant_formalize_check.py"
    mutant.write_text(
        src.replace(anchor, "            stories_with_ac += 1\n        elif False:\n", 1),
        encoding="utf-8",
    )

    root = _ac_less_project(tmp_path, "empty_file")
    proc = subprocess.run(
        [
            sys.executable, str(mutant), "--epic", "7",
            "--project-root", str(root),
            "--planning-artifacts", str(root / "planning-artifacts"),
            "--impl-artifacts", str(root / "impl-artifacts"),
            "--tea-config", str(root / "tea" / "config.yaml"),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    assert out["verdict"] == "ready"
    assert out["mechanical_budget"] == 0
    assert out["mechanical_gaps"] == []
    assert out["checks"]["stories_with_ac"] == 0


# ---------------------------------------------------------------------------
# The same empty-set fail-open one step FURTHER OUT: a PARTIALLY seeded Epic.
# The empty-set guard asks "are there zero story files?"; it never asks "do the
# files cover the in-scope keys?". Observed live at 7 of 8 story files, where the
# kernel returned a clean `ready` while one in-scope story had no file at all.
# ---------------------------------------------------------------------------

_KEYS = ("7-1-kernel", "7-2-adapter", "7-3-renderer")


def _story_body(key: str) -> str:
    return (
        f"# Story {key}\n\n## Acceptance Criteria\n\n"
        f"1. Running `pytest tests/test_{key.split('-')[-1]}.py::test_it` exits 0, and the\n"
        f"   anti-vacuous twin `test_it_missing_reds` fails when the config is removed.\n"
        f"   gate-ability: mechanical.\n"
    )


def _seeded_project(tmp_path, seeded: tuple[str, ...], label: str):
    """An Epic-7 project with THREE in-scope keys and a chosen subset seeded.

    The only variable across the tests below is which story files exist; the
    sprint-status always names all three, so coverage is the sole difference.
    """
    root = tmp_path / label
    planning = root / "planning-artifacts"
    impl = root / "impl-artifacts"
    planning.mkdir(parents=True)
    impl.mkdir(parents=True)
    (planning / "prd-fixture.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture-fixture.md").write_text("# Architecture\n", encoding="utf-8")
    (impl / "sprint-status.yaml").write_text(
        "generated: fixture\ndevelopment_status:\n  epic-7: in-progress\n"
        + "".join(f"  {k}: backlog\n" for k in _KEYS),
        encoding="utf-8",
    )
    for key in seeded:
        (impl / f"{key}.md").write_text(_story_body(key), encoding="utf-8")
    return root


def test_partially_seeded_story_set_is_remediable_not_ready(tmp_path):
    # The fail-open this closes, reproduced from the live sighting: SOME story
    # files resolve, so the empty-set guard stays silent, the per-story loop
    # iterates only over the stories that exist, and the Epic scores a clean
    # zero-gap `ready` while an in-scope story has no file and therefore no
    # acceptance criteria for the launch gate to read.
    out = _run_project(_seeded_project(tmp_path, _KEYS[:2], "partial"))

    assert out["verdict"] == "remediable"
    assert out["ready"] is False
    # The two seeded stories still scan normally: this is a COVERAGE gap, not a
    # claim that the resolved stories are bad.
    assert out["checks"]["stories_with_ac"] == 2

    gaps = [g for g in out["mechanical_gaps"] if g["kind"] == "story_keys_uncovered"]
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["severity"] == "high"
    # Remediable: the create-story scaffold generates the missing story files.
    assert gap["remediable"] is True
    # The detail NAMES the missing id, which is what makes the gap actionable
    # rather than merely true.
    assert "7-3-renderer" in gap["detail"]
    assert "7-1-kernel" not in gap["detail"]
    # No parent is involved, so the detail names none.
    assert "Below a done parent" not in gap["detail"]
    assert "7-2-adapter" not in gap["detail"]
    assert "1 of 3" in gap["detail"]

    # It counts toward the budget like every other gap, which is what moves the
    # verdict off `ready`.
    assert out["mechanical_budget"] == len(out["mechanical_gaps"])


def test_fully_seeded_story_set_emits_no_coverage_gap(tmp_path):
    # Anti-vacuous twin (data): the SAME project with all three story files
    # present fires ZERO coverage gaps, proving the gap keys on the UNCOVERED
    # key and not merely on running the kernel over this project shape.
    out = _run_project(_seeded_project(tmp_path, _KEYS, "full"))

    assert all(g["kind"] != "story_keys_uncovered" for g in out["mechanical_gaps"])
    assert out["checks"]["stories_with_ac"] == 3
    assert out["verdict"] == "ready"


def test_empty_story_set_reports_only_the_empty_set_gap(tmp_path):
    # Disjointness: with NO story files the pre-existing empty-set gap fires and
    # the coverage gap does NOT, so a zero-story Epic is reported once rather
    # than twice. Regression guard on the `if story_paths and uncovered` scope.
    out = _run_project(_seeded_project(tmp_path, (), "empty"))

    kinds = [g["kind"] for g in out["mechanical_gaps"]]
    assert "no_in_scope_stories" in kinds
    assert "story_keys_uncovered" not in kinds
    assert out["verdict"] == "remediable"


def test_epic_prefix_files_do_not_cover_unrelated_keys(tmp_path):
    # The crux of the matching rule. `_story_files` resolves ANY file starting
    # with the Epic prefix (`7-`), so a naive coverage check that merely counted
    # resolved files against the key count would call this Epic fully seeded: two
    # keys, two `7-` files. But `7-9-stray` is not one of the in-scope keys, and
    # `7-2-adapter` still has no file. Coverage must be per KEY, not a count.
    root = _seeded_project(tmp_path, ("7-1-kernel",), "stray")
    (root / "impl-artifacts" / "7-9-stray.md").write_text(_story_body("7-9-stray"), encoding="utf-8")

    out = _run_project(root)

    gaps = [g for g in out["mechanical_gaps"] if g["kind"] == "story_keys_uncovered"]
    assert len(gaps) == 1, "a prefix-sharing stray file must not vacuously cover a key"
    assert "7-2-adapter" in gaps[0]["detail"]
    assert "7-3-renderer" in gaps[0]["detail"]
    assert "2 of 3" in gaps[0]["detail"]


def test_number_only_filename_covers_its_key(tmp_path):
    """The permissive direction, and the false positive it exists to prevent.

    `ucg-create-story` writes `{story_key}.md` from whatever the operator
    supplied, so asking for story `7-2` yields `7-2.md` while sprint-planning's
    generated key is `7-2-adapter`. `_story_files` resolves that file via the
    Epic-prefix arm and the kernel reads and AC-grades it. A coverage rule keyed
    on the full slug would report an already-scanned file as missing and refuse
    to launch a genuinely seeded Epic - reporting `stories_with_ac: 3` and
    "3 of 3 resolve no story file" in the same payload.
    """
    root = _seeded_project(tmp_path, (), "number_only")
    impl = root / "impl-artifacts"
    for key in _KEYS:
        number = key.split("-")[0] + "-" + key.split("-")[1]
        (impl / f"{number}.md").write_text(_story_body(key), encoding="utf-8")

    out = _run_project(root)

    assert all(g["kind"] != "story_keys_uncovered" for g in out["mechanical_gaps"]), (
        "a number-only filename is the documented convention (stories share the "
        "Epic's NUMBER prefix); the slug is not a contract"
    )
    assert out["checks"]["stories_with_ac"] == 3
    assert out["verdict"] == "ready"


def test_higher_numbered_file_does_not_cover_a_lower_key(tmp_path):
    """The boundary, and the false NEGATIVE a bare prefix test would reintroduce.

    `"7-10-late.md".startswith("7-1")` is True, so an unanchored prefix rule
    lets a higher-numbered story vacuously cover a lower one. Story `7-1` would
    then reach an unattended launch with no file and no acceptance criteria,
    which is the exact fail-open this check exists to close.
    """
    root = tmp_path / "boundary"
    planning = root / "planning-artifacts"
    impl = root / "impl-artifacts"
    planning.mkdir(parents=True)
    impl.mkdir(parents=True)
    (planning / "prd-fixture.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture-fixture.md").write_text("# Architecture\n", encoding="utf-8")
    # Bare-numeric keys, the shape that makes the collision reachable.
    (impl / "sprint-status.yaml").write_text(
        "generated: fixture\ndevelopment_status:\n  epic-7: in-progress\n"
        "  7-1: backlog\n  7-10: backlog\n",
        encoding="utf-8",
    )
    # Only the HIGHER-numbered story is seeded.
    (impl / "7-10-late.md").write_text(_story_body("7-10-late"), encoding="utf-8")

    out = _run_project(root)

    gaps = [g for g in out["mechanical_gaps"] if g["kind"] == "story_keys_uncovered"]
    assert len(gaps) == 1, "7-10's file must not vacuously cover key 7-1"
    assert "7-1" in gaps[0]["detail"]
    assert "1 of 2" in gaps[0]["detail"]
    assert out["verdict"] == "remediable"


_COVERAGE_GUARD = "    if story_paths and uncovered:\n"


def test_mutant_without_coverage_gap_reads_ready(tmp_path):
    """Twin for test_partially_seeded_story_set_is_remediable_not_ready.

    Concrete mutation: neutralize the coverage guard in build_verdict
    (`if story_paths and uncovered:` -> `if False:`) on a COPY of the script, so
    no gap is appended. The partially seeded project then reports `ready` with
    mechanical_budget 0 - the exact pre-fix fail-open observed live at 7 of 8
    story files - which reds the verdict/budget assertions in the named test
    above. If `remediable` survived this mutation, the guard would not be what
    produces it and the named test would prove nothing.
    """
    src = SCRIPT.read_text(encoding="utf-8")
    assert _COVERAGE_GUARD in src, "mutation anchor drifted out of formalize_check.py"
    mutant_dir = tmp_path / "src"
    mutant_dir.mkdir()
    mutant = mutant_dir / "mutant_formalize_check.py"
    mutant.write_text(src.replace(_COVERAGE_GUARD, "    if False:\n", 1), encoding="utf-8")

    root = _seeded_project(tmp_path, _KEYS[:2], "partial_mutant")
    proc = subprocess.run(
        [
            sys.executable, str(mutant), "--epic", "7",
            "--project-root", str(root),
            "--planning-artifacts", str(root / "planning-artifacts"),
            "--impl-artifacts", str(root / "impl-artifacts"),
            "--tea-config", str(root / "tea" / "config.yaml"),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    assert out["verdict"] == "ready"
    assert out["mechanical_budget"] == 0
    assert out["mechanical_gaps"] == []
    # And the tell that made this dangerous: it looked healthy. Two stories
    # scanned green while a third in-scope story had no file at all.
    assert out["checks"]["stories_with_ac"] == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# --- present-but-unparsed sprint-status.yaml ---------------------------------
#
# `_safe_read_text` returns None only on OSError/decode failure, so an EMPTY or
# structurally unparseable rollup returns "" and takes the else-branch. The
# in-scope key set is then empty, which silences BOTH guards at once: story files
# still resolve through the epic-prefix glob so `no_in_scope_stories` never
# fires, and `story_keys_uncovered` is scoped `if story_paths and uncovered`
# against that empty set. The kernel returned `ready`, budget 0, on an Epic
# missing a story file.


def _seeded_epic(tmp_path: Path, sprint_body: str, drop_story: bool) -> Path:
    root = tmp_path / "proj"
    shutil.copytree(FIXTURES / "ready_epic", root)
    (root / "impl-artifacts" / "sprint-status.yaml").write_text(
        sprint_body, encoding="utf-8"
    )
    if drop_story:
        (root / "impl-artifacts" / "1-2-floor.md").unlink()
    return root


def _run_root(root: Path, epic: str = "1") -> dict:
    proc = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--epic", epic,
            "--project-root", str(root),
            "--planning-artifacts", str(root / "planning-artifacts"),
            "--impl-artifacts", str(root / "impl-artifacts"),
            "--tea-config", str(root / "tea" / "config.yaml"),
        ],
        capture_output=True, text=True,
    )
    return json.loads(proc.stdout)


_GOOD_ROLLUP = (
    "generated: fixture\ndevelopment_status:\n  epic-1: in-progress\n"
    "  1-1-kernel: ready-for-dev\n  1-2-floor: backlog\n"
)


def test_empty_sprint_status_does_not_score_a_vacuous_ready(tmp_path):
    """An Epic missing a story file must not reach `ready` on an empty rollup."""
    root = _seeded_epic(tmp_path, "", drop_story=True)

    result = _run_root(root)

    assert result["verdict"] != "ready", result.get("mechanical_gaps")
    ids = {g["id"] for g in result["mechanical_gaps"]}
    assert "sprint_status_unparsed" in ids, ids


def test_unparseable_sprint_status_is_flagged(tmp_path):
    """Structurally unparseable is the same fail-open as empty."""
    root = _seeded_epic(tmp_path, "!!! not a rollup !!!\n", drop_story=True)

    result = _run_root(root)

    assert result["verdict"] != "ready"
    assert "sprint_status_unparsed" in {g["id"] for g in result["mechanical_gaps"]}


def test_a_well_formed_rollup_still_reaches_ready(tmp_path):
    """Control: the guard must fire on the empty rollup and NOTHING else.

    Same tree, same story files, a parseable rollup -- still `ready`. Without
    this the assertions above would also pass on a build that had simply broken
    the kernel.
    """
    root = _seeded_epic(tmp_path, _GOOD_ROLLUP, drop_story=False)

    result = _run_root(root)

    assert "sprint_status_unparsed" not in {g["id"] for g in result["mechanical_gaps"]}
    assert result["verdict"] == "ready", result.get("mechanical_gaps")


def test_a_well_formed_rollup_still_catches_the_partial_seed(tmp_path):
    """Control on the other axis: with a parseable rollup the ORIGINAL guard
    still fires for the missing story, so the new gap is not masking it."""
    root = _seeded_epic(tmp_path, _GOOD_ROLLUP, drop_story=True)

    result = _run_root(root)

    ids = {g["id"] for g in result["mechanical_gaps"]}
    assert "story_keys_uncovered" in ids, ids
    assert result["verdict"] != "ready"


# --- a citation is not a declaration ----------------------------------------
#
# _collect_declared_ids harvested _FR_DECL_RE/_VER_DECL_RE over the ENTIRE story
# body, and the `traces:` row is part of that body -- so a cited id declared
# itself and could never be reported dangling. Every _INDEX_TOKEN_RE shape except
# the story key (`\d+-\d+...`) is also matched by one of those two declaration
# regexes, and the story key always takes the `regenerable` mechanical arm, which
# left the JUDGMENT arm unreachable.


def _epic_citing(tmp_path: Path, citation: str | None) -> Path:
    root = tmp_path / "proj"
    shutil.copytree(FIXTURES / "ready_epic", root)
    if citation is not None:
        story = root / "impl-artifacts" / "1-1-kernel.md"
        story.write_text(
            story.read_text(encoding="utf-8") + "\n" + citation + "\n", encoding="utf-8"
        )
    return root


@pytest.mark.parametrize(
    "citation",
    [
        "- traces: FR-99",
        "- traces: tests/test_ghost.py::test_never_written",
        "- traces: VER-GHOST-1",
        "- traces: STORY-GHOST",
    ],
)
def test_a_dangling_non_story_citation_reaches_the_judgment_arm(tmp_path, citation):
    """These four shapes used to self-declare and score a clean `ready`."""
    result = _run_root(_epic_citing(tmp_path, citation))

    assert result["verdict"] == "blocked", result
    assert result["judgment_required"] is True
    kinds = [c["kind"] for c in result["judgment_candidates"]]
    assert "orphaned_index" in kinds, result["judgment_candidates"]


def test_an_uncited_epic_is_still_ready(tmp_path):
    """Control: the harvest narrowing must not manufacture a finding."""
    result = _run_root(_epic_citing(tmp_path, None))

    assert result["verdict"] == "ready", result.get("mechanical_gaps")
    assert result["checks"]["orphaned_indices"] == 0


def test_a_citation_that_resolves_to_a_real_story_is_still_ready(tmp_path):
    """Control: a citation naming a story file that DOES exist still resolves.

    `1-2-floor` is a sibling story in this fixture, declared by its filename
    stem rather than by the citation row, so narrowing the harvest leaves it
    resolvable.
    """
    result = _run_root(_epic_citing(tmp_path, "- traces: 1-2-floor"))

    assert result["verdict"] == "ready", result.get("mechanical_gaps")
    assert result["checks"]["orphaned_indices"] == 0


def test_a_dangling_story_key_still_takes_the_mechanical_arm(tmp_path):
    """Control on the other arm: the regenerable shape is unchanged.

    A dangling story key is machine-regenerable, so it stays a `remediable`
    mechanical gap rather than becoming a judgment candidate -- proving the fix
    opened the judgment arm without collapsing the two arms together.
    """
    result = _run_root(_epic_citing(tmp_path, "- traces: 23-9-ghost-story"))

    assert result["verdict"] == "remediable", result
    assert any(g["id"].startswith("orphaned_index") for g in result["mechanical_gaps"])


# --- Acceptance criteria split at their own indent ----------------------------


def test_a_wrapped_line_starting_with_a_number_stays_in_its_ac():
    # The live sighting: the AC's prose wrapped so that "Recorded decision 1."
    # fell across a line break, and the continuation line began "1. ". Read as
    # a new AC, it cut the real AC in two, and the first half reported no
    # verification and no twin that it carried a few lines further down.
    body = (
        "# Story 7-1\n\n## Acceptance Criteria\n\n"
        "1. **The schema lands in one diff.** `packages/db/schema/x.surql` per Recorded decision\n"
        "   1. All four mechanisms land together: the file appended to the schema.\n"
        "   **Verification:** `pytest tests/test_schema.py::test_lands` exits 0.\n"
        "   **Anti-vacuous twin:** `test_schema_missing_reds` fails when the file is removed.\n"
        "2. Running `pytest tests/test_two.py::test_it` exits 0, and the twin `test_two_reds` fails.\n"
    )
    blocks = fc._split_ac_blocks(body)
    assert [line for line, _ in blocks] == [5, 9]
    first = blocks[0][1]
    assert "All four mechanisms" in first
    assert "**Verification:**" in first
    assert "**Anti-vacuous twin:**" in first


def test_a_nested_numbered_sub_list_belongs_to_its_ac():
    body = (
        "## Acceptance Criteria\n\n"
        "1. The CLI accepts three flags:\n"
        "   1. `--light`\n"
        "   2. `-H`\n"
        "2. The second criterion.\n"
    )
    blocks = fc._split_ac_blocks(body)
    assert len(blocks) == 2
    assert "`-H`" in blocks[0][1]
    assert blocks[1][1].startswith("2. The second criterion.")


def test_acs_written_at_an_indent_split_at_that_indent():
    # The first item sets the indent, so a list indented as a whole still splits.
    body = "## Acceptance Criteria\n\n  1. First.\n     1. wrapped, not an AC\n  2. Second.\n"
    blocks = fc._split_ac_blocks(body)
    assert [text.strip().split("\n")[0] for _, text in blocks] == ["1. First.", "2. Second."]


def test_an_item_left_of_the_first_items_text_opens_a_new_ac():
    # The CommonMark rule for a list item at the same level: right-aligned
    # numbering and an item that slipped one space each still open an AC.
    right_aligned = "## Acceptance Criteria\n\n" + "".join(f" {n}. AC {n}.\n" for n in range(1, 10)) + "10. AC 10.\n"
    assert len(fc._split_ac_blocks(right_aligned)) == 10
    slipped = "## Acceptance Criteria\n\n1. One.\n2. Two.\n 3. Three.\n"
    assert len(fc._split_ac_blocks(slipped)) == 3
    # A numbered list indented at the top of the section does not swallow the
    # column-0 ACs after it.
    indented_first = "## Acceptance Criteria\n\n  1. Indented.\n  2. Indented.\n1. Column 0.\n2. Column 0.\n"
    assert len(fc._split_ac_blocks(indented_first)) == 4


def test_a_tab_indented_wrapped_line_stays_in_its_ac():
    body = "## Acceptance Criteria\n\n1. The text wraps on a tab and\n\t1. continues here.\n2. Next.\n"
    blocks = fc._split_ac_blocks(body)
    assert len(blocks) == 2
    assert "continues here" in blocks[0][1]


def test_a_line_before_the_first_item_joins_no_earlier_ac():
    # Prose under a later AC heading, before its first item, used to be appended
    # to the previous section's last AC: that block then held lines it does not
    # span, and a candidate's line number counted from its start went wrong.
    body = (
        "## Acceptance Criteria\n\n1. First.\n\n## Notes\n\nA note.\n\n"
        "## Acceptance Criteria\n\nIntro prose before the list.\n\n1. Second.\n"
    )
    blocks = fc._split_ac_blocks(body)
    assert [line for line, _ in blocks] == [3, 13]
    assert "Intro prose" not in blocks[0][1]


def test_a_new_acceptance_criteria_heading_resets_the_indent():
    body = "## Acceptance Criteria\n\n  1. Indented.\n\n## Acceptance Criteria\n\n1. At column 0.\n2. Also.\n"
    assert len(fc._split_ac_blocks(body)) == 3


# --- Story-key coverage by id stem ---------------------------------------------


@pytest.mark.parametrize(
    ("name", "stem"),
    [
        ("95-0-a-i-the-scanner-spine", "95-0-a-i"),
        ("95-0-a-audit-the-guard-substrate.md", "95-0-a"),
        ("94-2a-the-thing.md", "94-2a"),
        ("92-7e-i-scan", "92-7e-i"),
        ("2-4-kebab-title", "2-4"),
        ("2-4.md", "2-4"),
        ("1-1_draft.md", "1-1"),
        ("1-10-foo.md", "1-10"),
        ("94-7-b-1-the-season-door", "94-7-b-1"),
        ("2-4-3-foo", "2-4"),
        ("lp-6-foo", None),
        ("epic-7", None),
    ],
)
def test_story_stem(name, stem):
    assert fc._story_stem(name) == stem


def test_a_child_key_is_not_covered_by_a_file_of_another_id():
    # Arm A of the filing: three children with no file of their own read
    # covered by their parent's file when only the first two numbers counted.
    # With no sprint rows nothing says the parent is a container, so its file
    # covers nothing but itself.
    keys = ["95-0-a-i-the-scanner-spine", "95-0-a-ii-the-turbo-inputs", "95-0-a-iii-the-cli-gate"]
    assert fc._uncovered_story_keys([Path("95-0-a-audit-the-guard-substrate.md")], keys) == keys
    # A true sibling's file covers nothing either, at any depth.
    assert fc._uncovered_story_keys([Path("95-0-a-ii-the-turbo-inputs.md")], ["95-0-a-i-the-scanner-spine"]) == [
        "95-0-a-i-the-scanner-spine"
    ]
    assert fc._uncovered_story_keys([Path("95-0-a-audit.md")], ["95-0-b-red-phase"]) == ["95-0-b-red-phase"]
    rows = {"94-7-b-1-the-season-door": "backlog", "94-7-b-2-the-other": "backlog"}
    assert fc._uncovered_story_keys([Path("94-7-b-2-the-other.md")], ["94-7-b-1-the-season-door"], rows) == [
        "94-7-b-1-the-season-door"
    ]


def test_a_letter_suffixed_key_is_covered_by_its_own_file():
    # Arm B of the filing: `94-2a` read uncovered against its own file.
    assert fc._uncovered_story_keys([Path("94-2a-the-thing.md")], ["94-2a-the-thing"]) == []


def test_a_higher_numbered_file_still_does_not_cover_a_lower_key():
    assert fc._uncovered_story_keys([Path("1-10-foo.md")], ["1-1-bar"]) == ["1-1-bar"]


def test_a_bare_number_file_still_covers_its_kebab_key():
    assert fc._uncovered_story_keys([Path("2-4.md")], ["2-4-kebab-title"]) == []


def test_a_decomposed_child_is_covered_by_its_done_parent_file():
    # execute.md: a decomposed child has no story file and must never get one;
    # the parent row is set to done and keeps the file the children cite.
    rows = {"95-0-a-i-the-scanner-spine": "backlog", "95-0-a-audit-the-guard-substrate": "done"}
    assert fc._uncovered_story_keys([Path("95-0-a-audit-the-guard-substrate.md")], ["95-0-a-i-the-scanner-spine"], rows) == []
    # A lettered child of a story number (92-7f of 92-7), through a level with no row (92-7e).
    rows = {"92-7f-the-departure": "backlog", "92-7e-i-the-scan": "backlog", "92-7-per-profile": "done"}
    files = [Path("92-7-per-profile.md")]
    assert fc._uncovered_story_keys(files, ["92-7f-the-departure", "92-7e-i-the-scan"], rows) == []
    # Every child is listed, each with the parent's file and row.
    assert fc._story_coverage(files, ["92-7f-the-departure", "92-7e-i-the-scan"], rows).children == [
        ("92-7f-the-departure", Path("92-7-per-profile.md"), "92-7-per-profile"),
        ("92-7e-i-the-scan", Path("92-7-per-profile.md"), "92-7-per-profile"),
    ]


def test_a_parent_that_is_not_done_covers_no_child():
    # Not a container yet: its file is its own story, not the children's text.
    # Each child sits above its parent's row, so the status alone decides.
    rows = {"92-7f-the-departure": "backlog", "92-7-per-profile": "in-progress"}
    assert fc._uncovered_story_keys([Path("92-7-per-profile.md")], ["92-7f-the-departure"], rows) == ["92-7f-the-departure"]
    # Stopped by an open parent, not placed below a done one.
    assert fc._story_coverage([Path("92-7-per-profile.md")], ["92-7f-the-departure"], rows).below_parent == {}
    # Nor does a done parent with no file of its own.
    rows = {"92-7f-the-departure": "backlog", "92-7-per-profile": "done"}
    assert fc._uncovered_story_keys([Path("92-6-other.md")], ["92-7f-the-departure"], rows) == ["92-7f-the-departure"]


def test_a_parent_whose_row_the_split_removed_still_covers_with_its_file():
    # A split that dropped the parent row instead of setting it done: the
    # parent's file is still the text its children cite.
    rows = {"94-8-a-the-first": "backlog", "94-8-b-the-second": "backlog"}
    files = [Path("94-8-season-learner.md")]
    assert fc._uncovered_story_keys(files, ["94-8-a-the-first", "94-8-b-the-second"], rows) == []


def test_a_parent_still_being_worked_stops_the_walk_even_under_a_done_grandparent():
    rows = {"92-7e-i-the-scan": "backlog", "92-7e-the-umbrella": "in-progress", "92-7-per-profile": "done"}
    files = [Path("92-7-per-profile.md")]
    assert fc._uncovered_story_keys(files, ["92-7e-i-the-scan"], rows) == ["92-7e-i-the-scan"]
    assert fc._story_coverage(files, ["92-7e-i-the-scan"], rows).below_parent == {}
    # The same tree with 92-7e set done is a container chain, and 92-7's file covers.
    rows["92-7e-the-umbrella"] = "done"
    assert fc._uncovered_story_keys(files, ["92-7e-i-the-scan"], rows) == []


def test_a_stem_shared_by_several_rows_is_done_only_when_every_row_is():
    # 92-7e-i and 92-7e-i-scan share the stem 92-7e-i; as a parent it is a
    # container only once both rows are done, whichever comes first in the file.
    files = [Path("92-7e-i-the-scan.md")]
    for rows in (
        {"92-7e-i-a-child": "backlog", "92-7e-i-the-scan": "done", "92-7e-i-scan": "in-progress"},
        {"92-7e-i-a-child": "backlog", "92-7e-i-scan": "in-progress", "92-7e-i-the-scan": "done"},
    ):
        assert fc._uncovered_story_keys(files, ["92-7e-i-a-child"], rows) == ["92-7e-i-a-child"]


def test_a_story_inserted_below_a_done_parent_row_is_reported():
    # sprint-planning writes rows in the order of the epics' story headings, so
    # a `Story 3.2a` added after 3.2 shipped lands below 3.2's row. A decomposed
    # child sits above its parent's row (execute.md), so the lettered key below
    # it is a story of its own, with no file yet.
    files = [Path("3-1-login.md"), Path("3-2-user-login.md"), Path("3-3-profile.md")]
    rows = {"3-1-login": "done", "3-2-user-login": "done", "3-2a-reset-password": "backlog", "3-3-profile": "backlog"}
    keys = ["3-2a-reset-password", "3-3-profile"]
    assert fc._uncovered_story_keys(files, keys, rows) == ["3-2a-reset-password"]
    coverage = fc._story_coverage(files, keys, rows)
    assert coverage.below_parent == {"3-2a-reset-password": "3-2-user-login"}
    assert coverage.children == []
    # The twin: the same row above its parent's is where a child sits, and it
    # reads as one.
    rows = {"3-1-login": "done", "3-2a-reset-password": "backlog", "3-2-user-login": "done", "3-3-profile": "backlog"}
    assert fc._uncovered_story_keys(files, keys, rows) == []
    coverage = fc._story_coverage(files, keys, rows)
    assert coverage.children == [("3-2a-reset-password", Path("3-2-user-login.md"), "3-2-user-login")]
    assert coverage.below_parent == {}


def test_the_order_is_read_against_the_parent_that_holds_the_file():
    # 3-2a-a walks past 3-2a, which has no row and no file, to 3-2's file: its
    # place is read against 3-2's row, not against the level it passed over.
    files = [Path("3-2-login.md")]
    rows = {"3-2-login": "done", "3-2a-a-reset-flow": "backlog"}
    coverage = fc._story_coverage(files, ["3-2a-a-reset-flow"], rows)
    assert coverage.uncovered == ["3-2a-a-reset-flow"]
    assert coverage.below_parent == {"3-2a-a-reset-flow": "3-2-login"}
    rows = {"3-2a-a-reset-flow": "backlog", "3-2-login": "done"}
    assert fc._story_coverage(files, ["3-2a-a-reset-flow"], rows).children == [
        ("3-2a-a-reset-flow", Path("3-2-login.md"), "3-2-login")
    ]


def test_a_child_must_sit_above_the_first_row_of_its_parents_stem():
    # 92-7e-i-the-scan and 92-7e-i-scan share the stem 92-7e-i: a child between
    # the two sits below the first, so it does not read as one.
    files = [Path("92-7e-i-the-scan.md")]
    rows = {"92-7e-i-the-scan": "done", "92-7e-i-a-child": "backlog", "92-7e-i-scan": "done"}
    assert fc._uncovered_story_keys(files, ["92-7e-i-a-child"], rows) == ["92-7e-i-a-child"]
    assert fc._story_coverage(files, ["92-7e-i-a-child"], rows).below_parent == {"92-7e-i-a-child": "92-7e-i-the-scan"}
    rows = {"92-7e-i-a-child": "backlog", "92-7e-i-the-scan": "done", "92-7e-i-scan": "done"}
    assert fc._story_coverage(files, ["92-7e-i-a-child"], rows).children == [
        ("92-7e-i-a-child", Path("92-7e-i-the-scan.md"), "92-7e-i-the-scan")
    ]


def test_a_parent_with_two_files_is_named_by_the_first():
    # Both files have the stem 3-2; the kernel passes them sorted, and the
    # first is the one the children's criteria are read from.
    files = [Path("3-2-user-login.md"), Path("3-2_draft.md")]
    rows = {"3-2a-reset-password": "backlog", "3-2-user-login": "done"}
    assert fc._story_coverage(files, ["3-2a-reset-password"], rows).children == [
        ("3-2a-reset-password", Path("3-2-user-login.md"), "3-2-user-login")
    ]


def test_a_key_with_no_row_is_covered_by_no_parent():
    # Without its row there is no place to compare, so only its own file covers it.
    files = [Path("92-7-per-profile.md")]
    for rows in ({"92-7-per-profile": "done"}, {"92-6-other": "done"}):
        coverage = fc._story_coverage(files, ["92-7f-the-departure"], rows)
        assert coverage.uncovered == ["92-7f-the-departure"]
        assert coverage.children == [] and coverage.below_parent == {}


def test_a_parent_whose_row_was_removed_is_listed_with_no_row():
    rows = {"94-8-a-the-first": "backlog"}
    files = [Path("94-7-other.md"), Path("94-8-season-learner.md")]
    coverage = fc._story_coverage(files, ["94-8-a-the-first"], rows)
    assert coverage.uncovered == []
    assert coverage.children == [("94-8-a-the-first", Path("94-8-season-learner.md"), None)]


def test_an_alpha_keyed_story_falls_back_to_the_whole_key():
    assert fc._uncovered_story_keys([Path("lp-6-foo.md")], ["lp-6-foo", "lp-7-bar"]) == ["lp-7-bar"]


def test_kernel_reads_a_done_parent_as_the_container_of_its_children(tmp_path):
    # End to end: the parent row is done and keeps its file, the child row is
    # in scope with no file of its own, and the readiness gate reports no gap.
    root = tmp_path / "decomposed"
    planning = root / "planning-artifacts"
    impl = root / "impl-artifacts"
    planning.mkdir(parents=True)
    impl.mkdir(parents=True)
    (planning / "prd-fixture.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture-fixture.md").write_text("# Architecture\n", encoding="utf-8")
    (impl / "sprint-status.yaml").write_text(
        "generated: fixture\ndevelopment_status:\n  epic-7: in-progress\n"
        "  7-1-a-i-the-first-child: backlog\n  7-1-a-umbrella: done\n",
        encoding="utf-8",
    )
    (impl / "7-1-a-umbrella.md").write_text(_story_body("7-1-a-umbrella"), encoding="utf-8")
    out = _run_project(root)
    assert all(g["kind"] != "story_keys_uncovered" for g in out["mechanical_gaps"]), out["mechanical_gaps"]
    # Reported, not gated on: the briefing names the keys read as children.
    assert out["checks"]["decomposed_children"] == [
        {"key": "7-1-a-i-the-first-child", "parent_file": "impl-artifacts/7-1-a-umbrella.md", "parent_row": "7-1-a-umbrella"}
    ]
    # The twin: the same project with the parent not yet done reports the child.
    (impl / "sprint-status.yaml").write_text(
        "generated: fixture\ndevelopment_status:\n  epic-7: in-progress\n"
        "  7-1-a-i-the-first-child: backlog\n  7-1-a-umbrella: in-progress\n",
        encoding="utf-8",
    )
    out = _run_project(root)
    gaps = [g for g in out["mechanical_gaps"] if g["kind"] == "story_keys_uncovered"]
    assert len(gaps) == 1 and "7-1-a-i-the-first-child" in gaps[0]["detail"]
    # Stopped by an open parent: the detail names no done parent's row.
    assert "Below a done parent" not in gaps[0]["detail"]
    # A split that removed the parent's row: the file still covers, with no row.
    (impl / "sprint-status.yaml").write_text(
        "generated: fixture\ndevelopment_status:\n  epic-7: in-progress\n  7-1-a-i-the-first-child: backlog\n",
        encoding="utf-8",
    )
    out = _run_project(root)
    assert out["checks"]["decomposed_children"] == [
        {"key": "7-1-a-i-the-first-child", "parent_file": "impl-artifacts/7-1-a-umbrella.md", "parent_row": None}
    ]


def test_kernel_reports_a_story_inserted_below_a_done_parent(tmp_path):
    # End to end: `Story 7.1a`, added after 7.1 shipped, sits below 7.1's done
    # row with no file. The gap names it, and says why no parent covered it.
    root = tmp_path / "inserted"
    planning = root / "planning-artifacts"
    impl = root / "impl-artifacts"
    planning.mkdir(parents=True)
    impl.mkdir(parents=True)
    (planning / "prd-fixture.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture-fixture.md").write_text("# Architecture\n", encoding="utf-8")
    (impl / "sprint-status.yaml").write_text(
        "generated: fixture\ndevelopment_status:\n  epic-7: in-progress\n"
        "  7-1-the-login: done\n  7-1a-reset-password: backlog\n  7-1b-audit: backlog\n",
        encoding="utf-8",
    )
    (impl / "7-1-the-login.md").write_text(_story_body("7-1-the-login"), encoding="utf-8")
    out = _run_project(root)
    gaps = [g for g in out["mechanical_gaps"] if g["kind"] == "story_keys_uncovered"]
    assert len(gaps) == 1, out["mechanical_gaps"]
    assert "Unresolved: 7-1a-reset-password, 7-1b-audit" in gaps[0]["detail"]
    # Each key below the done parent's row is named with that row.
    assert "7-1a-reset-password (parent row 7-1-the-login), 7-1b-audit (parent row 7-1-the-login)" in gaps[0]["detail"]
    assert gaps[0]["remediable"] is True
    assert out["checks"]["decomposed_children"] == []


def test_kernel_covers_a_lettered_story_whose_slug_carries_a_tea_word(tmp_path):
    # End to end: `7-1a-trace-export.md` is the story's own file, written from
    # the story template with no authored_by header. Read as a leaked TEA
    # artifact, its only clearing move archived it and left the key uncovered,
    # so the verdict could never reach ready.
    root = tmp_path / "lettered"
    planning = root / "planning-artifacts"
    impl = root / "impl-artifacts"
    planning.mkdir(parents=True)
    impl.mkdir(parents=True)
    (planning / "prd-fixture.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture-fixture.md").write_text("# Architecture\n", encoding="utf-8")
    (impl / "sprint-status.yaml").write_text(
        "generated: fixture\ndevelopment_status:\n  epic-7: in-progress\n"
        "  7-1-the-login: done\n  7-1a-trace-export: ready-for-dev\n",
        encoding="utf-8",
    )
    (impl / "7-1-the-login.md").write_text(_story_body("7-1-the-login"), encoding="utf-8")
    (impl / "7-1a-trace-export.md").write_text(_story_body("7-1a-trace-export"), encoding="utf-8")
    out = _run_project(root)
    kinds = [g["kind"] for g in out["mechanical_gaps"]]
    assert "leaked_tea_artifact" not in kinds, out["mechanical_gaps"]
    assert "story_keys_uncovered" not in kinds, out["mechanical_gaps"]
    assert not out["checks"]["tea_artifacts_in_source"]


def test_a_title_starting_with_a_letter_reads_its_bare_number_file_as_a_parent():
    # `2-4-a-new-login-page` has the stem 2-4-a, and the operator's `2-4.md`
    # the stem 2-4. With its row and no 2-4 row, the key reads as a child of a
    # parent whose row the split removed; the order cannot tell the two apart,
    # so the report lists it (define-done.md renames such a file after its key).
    files = [Path("2-4.md")]
    keys = ["2-4-a-new-login-page"]
    rows = {"2-1-setup": "done", "2-4-a-new-login-page": "ready-for-dev"}
    coverage = fc._story_coverage(files, keys, rows)
    assert coverage.uncovered == []
    assert coverage.children == [("2-4-a-new-login-page", Path("2-4.md"), None)]
    assert fc._story_coverage([Path("2-4-login-page.md")], keys, rows).children == [
        ("2-4-a-new-login-page", Path("2-4-login-page.md"), None)
    ]
    # Without the rows no parent covers anything, and the key reads uncovered.
    assert fc._story_coverage(files, keys).uncovered == keys
    # Named after its full key, the file is its own.
    assert fc._story_coverage([Path("2-4-a-new-login-page.md")], keys, rows) == fc._Coverage([], [], {})


def test_the_stem_docstring_says_what_a_bare_number_file_reads_as():
    doc = re.sub(r"\s+", " ", fc._story_stem.__doc__)
    assert "fails closed;" not in doc
    assert "reads as a child of that file whose parent row the split removed" in doc
    assert "without them it reads uncovered" in doc


def test_define_done_renames_a_story_file_the_kernel_read_as_a_parent():
    text = re.sub(r"\s+", " ", (SCRIPT.parent.parent / "references" / "define-done.md").read_text(encoding="utf-8"))
    start = text.index("**A decomposed child gets no story file.**")
    paragraph = text[start : text.index("On a project whose artifact tree git does not track", start)]
    assert "rename that file to `<key>.md`" in paragraph
    assert "the readiness check did read its criteria" in paragraph
    # The rename names its command, one `acceptEdits` runs without asking
    # (no allow rule covers a git move), and a file two listed keys share is a
    # parent's, so neither key takes it.
    assert "in one `mv <that file> <its folder>/<key>.md` call" in paragraph
    assert "no other key in the list names the same file" in paragraph
    assert "A file two listed keys name is a parent's, so rename it for neither." in paragraph


# --- the in-scope stories only ------------------------------------------------
#
# The per-story and per-AC checks read every `<epic>-*` file whatever its row's
# status, so a `done` story's criteria raised remediable gaps that kept the
# verdict off `ready` and judgment candidates that stayed owed, although `done`
# stories are out of scope (ingest-and-scope.md Stage 1 rule 3). And the kernel
# took no story filter, so an operator-scoped run could never tell it which
# stories it drives. Coverage and the declared ids still read every file.

# No named verification, no twin, and an unsourced threshold: two mechanical
# gaps and one invented_nfr_threshold judgment candidate.
_FLAWED_BODY = "# Story {key}\n\n## Acceptance Criteria\n\n1. The page answers within 300 ms.\n"


def _scoped_project(tmp_path: Path, rows: dict[str, str], bodies: dict[str, str]) -> Path:
    """An Epic-7 project with the given rows; `bodies` maps a key to its story text."""
    root = tmp_path / "scoped"
    planning = root / "planning-artifacts"
    impl = root / "impl-artifacts"
    planning.mkdir(parents=True)
    impl.mkdir(parents=True)
    (planning / "prd-fixture.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture-fixture.md").write_text("# Architecture\n", encoding="utf-8")
    (impl / "sprint-status.yaml").write_text(
        "generated: fixture\ndevelopment_status:\n  epic-7: in-progress\n"
        + "".join(f"  {key}: {status}\n" for key, status in rows.items()),
        encoding="utf-8",
    )
    for key, body in bodies.items():
        (impl / f"{key}.md").write_text(body.format(key=key), encoding="utf-8")
    return root


def _run_scoped(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--epic", "7",
            "--project-root", str(root),
            "--planning-artifacts", str(root / "planning-artifacts"),
            "--impl-artifacts", str(root / "impl-artifacts"),
            "--tea-config", str(root / "tea" / "config.yaml"),
            *extra,
        ],
        capture_output=True, text=True,
    )


def _scoped_verdict(root: Path, *extra: str) -> dict:
    proc = _run_scoped(root, *extra)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _finding_files(out: dict) -> set[str]:
    """The files every gap and every candidate points into, with `/` between
    parts: the kernel prints the platform's own separator."""
    sources = [g["source"] for g in out["mechanical_gaps"]] + [
        c["source"] for c in out["judgment_candidates"]
    ]
    return {source.split(":")[0].replace("\\", "/") for source in sources}


def test_a_done_storys_acceptance_criteria_raise_no_gap(tmp_path):
    rows = {"7-1-shipped": "done", "7-2-next": "backlog"}
    root = _scoped_project(tmp_path, rows, {"7-1-shipped": _FLAWED_BODY, "7-2-next": _story_body("7-2-next")})
    out = _scoped_verdict(root)
    assert out["verdict"] == "ready", out
    assert "impl-artifacts/7-1-shipped.md" not in _finding_files(out)
    assert out["checks"]["stories_with_ac"] == 1
    # Every file of the Epic is still read once.
    assert out["timing"]["artifact_count"] == 5


def test_the_same_story_not_done_still_raises_its_gaps(tmp_path):
    # The twin: the filter keys on the row's status, not on the file.
    rows = {"7-1-shipped": "review", "7-2-next": "backlog"}
    root = _scoped_project(tmp_path, rows, {"7-1-shipped": _FLAWED_BODY, "7-2-next": _story_body("7-2-next")})
    out = _scoped_verdict(root)
    assert out["verdict"] == "blocked"
    kinds = {g["kind"] for g in out["mechanical_gaps"]}
    assert {"ac_missing_named_verification", "ac_missing_anti_vacuous_twin"} <= kinds
    assert [c["kind"] for c in out["judgment_candidates"]] == ["invented_nfr_threshold"]
    assert out["checks"]["stories_with_ac"] == 2


def test_a_done_parents_file_is_still_read_for_its_child(tmp_path):
    # Not loosened: a decomposed child's criteria live in its done parent's file.
    rows = {"7-1-a-i-child": "backlog", "7-1-a-umbrella": "done"}
    out = _scoped_verdict(_scoped_project(tmp_path, rows, {"7-1-a-umbrella": _FLAWED_BODY}))
    assert "impl-artifacts/7-1-a-umbrella.md" in _finding_files(out)
    assert out["verdict"] == "blocked"


def test_a_citation_to_a_done_story_still_resolves(tmp_path):
    rows = {"7-1-shipped": "done", "7-2-next": "backlog"}
    bodies = {
        "7-1-shipped": _story_body("7-1-shipped"),
        "7-2-next": _story_body("7-2-next") + "   traces: 7-1-shipped\n",
    }
    out = _scoped_verdict(_scoped_project(tmp_path, rows, bodies))
    assert out["checks"]["orphaned_indices"] == 0
    assert out["verdict"] == "ready", out


def test_an_all_done_epic_still_reads_every_file(tmp_path):
    # No in-scope key: every file of the Epic is read, as before.
    out = _scoped_verdict(_scoped_project(tmp_path, {"7-1-shipped": "done"}, {"7-1-shipped": _FLAWED_BODY}))
    assert "impl-artifacts/7-1-shipped.md" in _finding_files(out)


_SCOPE_ROWS = {"7-1-kernel": "backlog", "7-2-adapter": "backlog", "7-3-renderer": "backlog"}


def _scope_bodies() -> dict[str, str]:
    """7-1 sound, 7-2 flawed, 7-3 with no story file."""
    return {"7-1-kernel": _story_body("7-1-kernel"), "7-2-adapter": _FLAWED_BODY}


def test_story_scopes_the_files_and_the_coverage(tmp_path):
    root = _scoped_project(tmp_path, _SCOPE_ROWS, _scope_bodies())
    whole = _scoped_verdict(root)
    assert any(g["kind"] == "story_keys_uncovered" for g in whole["mechanical_gaps"])
    assert "impl-artifacts/7-2-adapter.md" in _finding_files(whole)
    scoped = _scoped_verdict(root, "--story", "7-1-kernel")
    assert scoped["verdict"] == "ready", scoped
    assert scoped["mechanical_gaps"] == [] and scoped["judgment_candidates"] == []


def test_story_keeps_an_in_scope_storys_gaps_and_uncovered_key(tmp_path):
    root = _scoped_project(tmp_path, _SCOPE_ROWS, _scope_bodies())
    out = _scoped_verdict(root, "--story", "7-2-adapter", "--story", "7-3-renderer")
    gaps = {g["kind"]: g for g in out["mechanical_gaps"]}
    assert "1 of 2" in gaps["story_keys_uncovered"]["detail"]
    assert "Unresolved: 7-3-renderer" in gaps["story_keys_uncovered"]["detail"]
    assert "ac_missing_named_verification" in gaps
    assert [c["kind"] for c in out["judgment_candidates"]] == ["invented_nfr_threshold"]
    assert "impl-artifacts/7-1-kernel.md" not in _finding_files(out)


def test_story_naming_a_done_or_unknown_row_blocks(tmp_path):
    rows = dict(_SCOPE_ROWS, **{"7-0-shipped": "done"})
    root = _scoped_project(tmp_path, rows, dict(_scope_bodies(), **{"7-0-shipped": _story_body("7-0-shipped")}))
    for bad in ("7-0-shipped", "7-9-typo", "8-1-other-epic"):
        out = _scoped_verdict(root, "--story", "7-1-kernel", "--story", bad)
        gaps = [g for g in out["mechanical_gaps"] if g["kind"] == "story_not_in_scope"]
        assert len(gaps) == 1 and bad in gaps[0]["detail"], out["mechanical_gaps"]
        assert gaps[0]["remediable"] is False
        assert out["verdict"] == "blocked"
    # The twin: the same run naming only a not-done row reads ready.
    assert _scoped_verdict(root, "--story", "7-1-kernel")["verdict"] == "ready"


def test_story_naming_no_not_done_row_reads_no_story_file(tmp_path):
    # Not the all-done fallback: with every --story key invalid, reading every
    # file brought back the done story's gaps and candidates.
    rows = dict(_SCOPE_ROWS, **{"7-0-shipped": "done"})
    root = _scoped_project(tmp_path, rows, dict(_scope_bodies(), **{"7-0-shipped": _FLAWED_BODY}))
    for bad in (["7-0-shipped"], ["7-9-typo"], ["7-0"], ["8-1-other-epic"], ["7-9-typo", "7-0-shipped"]):
        out = _scoped_verdict(root, *(arg for key in bad for arg in ("--story", key)))
        assert [g["kind"] for g in out["mechanical_gaps"]] == ["story_not_in_scope"] * len(bad), out
        assert out["judgment_candidates"] == []
        assert _finding_files(out) == {"impl-artifacts/sprint-status.yaml"}
        assert out["checks"]["stories_with_ac"] == 0
        assert out["verdict"] == "blocked"


def test_story_naming_a_parent_set_done_reads_no_story_file(tmp_path):
    # A closing re-run that kept the key of a parent step 2 set done.
    rows = {"7-0-shipped": "done", "7-1-a-i-child": "backlog", "7-1-a-umbrella": "done", "7-2-next": "backlog"}
    bodies = {"7-0-shipped": _FLAWED_BODY, "7-1-a-umbrella": _story_body("7-1-a-umbrella"), "7-2-next": _story_body("7-2-next")}
    root = _scoped_project(tmp_path, rows, bodies)
    out = _scoped_verdict(root, "--story", "7-1-a-umbrella")
    assert [g["kind"] for g in out["mechanical_gaps"]] == ["story_not_in_scope"], out
    assert out["judgment_candidates"] == []
    # The twin: the swapped flags read the parent's file through its child.
    assert _scoped_verdict(root, "--story", "7-1-a-i-child")["verdict"] == "ready"


def test_story_on_an_all_done_epic_reads_no_story_file(tmp_path):
    # The every-file fallback is for a run with no --story only.
    root = _scoped_project(tmp_path, {"7-1-shipped": "done"}, {"7-1-shipped": _FLAWED_BODY})
    out = _scoped_verdict(root, "--story", "7-1-shipped")
    assert [g["kind"] for g in out["mechanical_gaps"]] == ["story_not_in_scope"], out
    assert "impl-artifacts/7-1-shipped.md" not in _finding_files(out)
    # The twin: no --story still reads the whole Epic.
    assert "impl-artifacts/7-1-shipped.md" in _finding_files(_scoped_verdict(root))


def test_a_blank_story_is_an_invocation_error(tmp_path):
    proc = _run_scoped(_scoped_project(tmp_path, _SCOPE_ROWS, _scope_bodies()), "--story", " ")
    assert proc.returncode == 2
    # The required-flag lane names it, as it names a blank --epic.
    assert "required and non-empty: --story" in proc.stderr


def test_story_reaches_ready_once_its_candidates_are_answered(tmp_path):
    bodies = dict(_scope_bodies(), **{"7-1-kernel": _story_body("7-1-kernel") + "   Renders within 300 ms.\n"})
    root = _scoped_project(tmp_path, _SCOPE_ROWS, bodies)
    first = _scoped_verdict(root, "--story", "7-1-kernel")
    assert first["verdict"] == "blocked" and len(first["judgment_candidates"]) == 1, first
    scan = tmp_path / "scan.json"
    concerns = [{"candidate": c["id"], "source": c["source"]} for c in first["judgment_candidates"]]
    scan.write_text(json.dumps({"reds": [], "concerns": concerns}), encoding="utf-8")
    out = _scoped_verdict(root, "--story", "7-1-kernel", "--scan", str(scan))
    assert out["verdict"] == "ready", out
