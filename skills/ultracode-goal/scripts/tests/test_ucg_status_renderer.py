#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""CI-deterministic tests for the read-only run-status renderer and its skill.

`status_render.py` is the read side over a run's own artifacts: it collects the
heartbeat snapshot, the decision-log tail, the deferred-work ledger, the
escalation files and the runs index, and renders them. It has authority over
nothing, so its whole contract is about what it does NOT do - it must not write,
must not spawn, must not crash on a partial run, and must not label a
model-maintained field as machine-derived.

The tests pin those, in the order they can actually break:

  - the provenance label is EXCLUSIVE (set-equality both ways, so neither
    labeling everything nor labeling nothing satisfies it)
  - the render is read-only (bytes + mtimes unchanged, and a source-level check
    that keys on the write call itself, proven against a one-line writing variant)
  - the runs index discriminates terminal from live on the run report, not on
    folder existence
  - an absent / partial / empty / unknown-key snapshot degrades to `n/a` at exit
    0, while a malformed INVOCATION still exits 2 - the fail-soft-on-sources,
    fail-closed-on-invocation split `gate_trail.py` already draws
  - an unpromoted crash residual renders as unpromoted, and a promoted one does not
  - the optional diff-viewer affordance is confined to stdout
  - the skill is registered end to end (13-column CSV row, unique menu code, and
    `validate-skills.js` actually reading this new nested path)

PATH DISCIPLINE, and it is load-bearing. Every renderer invocation here pins
PATH explicitly, because the viewer probe consults the ambient PATH and the
viewer IS installed on some developer machines (verified: it is present on at
least one, contrary to the assumption that it exists nowhere). A test that let
the ambient PATH through would render the affordance on one machine and not on
another, and the list-equality below would pass or fail by accident of who ran
it. `_clean_path()` strips exactly the directories that carry the viewer and
keeps the rest, so the probe's own dependency (`which`) stays resolvable.

STATED BOUND on the viewer half: the "present" case is proven with a STUB
executable written into tmp_path and prepended to PATH, never a real install.
That proves the probe is consulted and that the affordance reaches stdout and
nothing else. It does NOT prove a real `hunk show <sha>` renders a usable diff.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_ucg_status_renderer.py -v
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "status_render.py"
FIXTURES = HERE / "fixtures" / "ucg_status"

REPO_ROOT = HERE.parents[3]  # skills/ultracode-goal/scripts/tests -> repo root
SKILL_DIR = REPO_ROOT / "skills" / "ucg-status"
SKILL_MD = SKILL_DIR / "SKILL.md"
HELP_CSV = REPO_ROOT / "skills" / "ultracode-goal" / "assets" / "module-help.csv"
VALIDATE_SKILLS = REPO_ROOT / "tools" / "validate-skills.js"

MACHINE = "[machine-derived]"
UNPROMOTED = "escalation (unpromoted: session ended before Execute promoted it)"
VIEWER = "hunk"

MODULE_COLUMN = "UltraCode Goal"
CSV_COLUMNS = 13


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


envelope = _load("headless_envelope", HERE.parent / "headless_envelope.py")


# --- invocation helpers -----------------------------------------------------


def _clean_path() -> str:
    """The ambient PATH with every directory carrying the viewer removed.

    Not a hardcoded `/usr/bin:/bin`: the probe shells out to `which`, so the
    stripped PATH still has to resolve it wherever this runs.
    """
    kept = [
        entry
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry and not (Path(entry) / VIEWER).exists()
    ]
    return os.pathsep.join(kept)


def _stub_viewer(tmp_path: Path) -> Path:
    """A stub viewer executable in its own dir, for prepending to PATH."""
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / VIEWER
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    return bin_dir


def _run(args: list[str], *, viewer_dir: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    clean = _clean_path()
    env["PATH"] = f"{viewer_dir}{os.pathsep}{clean}" if viewer_dir else clean
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _render_full(tmp_path: Path, *, viewer_dir: Path | None = None) -> str:
    run = _run(
        [
            "--impl-artifacts",
            str(FIXTURES / "full_run" / "impl"),
            "--run-dir",
            str(FIXTURES / "full_run" / "run"),
            "--runs-root",
            str(FIXTURES / "runs_root"),
            "--repo",
            str(tmp_path),
        ],
        viewer_dir=viewer_dir,
    )
    assert run.returncode == 0, run.stderr
    return run.stdout


# --- render parsing helpers -------------------------------------------------


def _labeled(render: str) -> set[str]:
    """Every rendered line carrying the provenance suffix."""
    return {line.strip() for line in render.splitlines() if line.strip().endswith(MACHINE)}


def _expected_labeled(status: dict) -> set[str]:
    """The lines that MAY carry the suffix, built from the snapshot itself."""
    budget = status["budget_used"]
    return {f"- Last reason: {reason} {MACHINE}" for reason in status["last_reasons"]} | {
        f"- Budget used: {budget['turns']} of {budget['max_turns']} turns {MACHINE}"
    }


def _index_rows(render: str) -> list[tuple[str, str]]:
    section = render.split("## Runs")[-1]
    rows = []
    for line in section.splitlines():
        match = re.fullmatch(r"- ([^:]+): (terminal|live)", line.strip())
        if match:
            rows.append((match.group(1), match.group(2)))
    return rows


def _escalation_block(render: str, story: str) -> str:
    """One escalation's rendered block, from its heading to the next one."""
    section = render.split("## Escalations", 1)[-1].split("## Deferred work", 1)[0]
    blocks = re.split(r"^### ", section, flags=re.MULTILINE)[1:]
    for block in blocks:
        if block.splitlines()[0].strip() == story:
            return block
    raise AssertionError(f"no rendered escalation block for {story!r}")


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# --- the read-only source assertion -----------------------------------------


def read_only_violations(src: str) -> list[str]:
    """Every way a module source could write or spawn, as findings.

    Keys on the CALLS, not on any property of the file as a whole, so the same
    helper can be handed a variant that differs by one added write and must
    report it. The single permitted spawn is the viewer probe.
    """
    found: list[str] = []
    if re.search(r"""\bopen\s*\([^)]*["'][rbt+]*[wax]""", src):
        found.append("open() in a write/append mode")
    for call in ("write_text", "write_bytes", "writelines", "mkdir", "touch", "unlink"):
        if re.search(rf"\.{call}\s*\(", src):
            found.append(call)
    sites = [m.start() for m in re.finditer(r"\bsubprocess\.\w+\s*\(", src)]
    if len(sites) != 1:
        found.append(f"{len(sites)} subprocess call sites (expected exactly the viewer probe)")
    else:
        window = src[sites[0] : sites[0] + 240]
        if '"which"' not in window or "VIEWER" not in window:
            found.append("the single subprocess call site is not the viewer probe")
    return found


# --- provenance labels are exclusive ----------------------------------------


def test_full_snapshot_renders_all_sm3_rows_with_provenance_labels(tmp_path):
    render = _render_full(tmp_path)
    status = json.loads((FIXTURES / "full_run" / "impl" / "run-status.json").read_text())

    # The five items a status read exists to answer, each with a real value.
    assert "- Phase: gated" in render
    assert "- Last verdict: advance" in render
    for reason in status["last_reasons"]:
        assert reason in render, f"gate reason not rendered: {reason}"
    assert "### beta" in render, "the pending escalation is not rendered"
    for row_id in ("d1", "d2"):
        assert re.search(rf"^- {row_id} \[", render, re.MULTILINE), f"ledger row {row_id} missing"

    # SET-EQUALITY: the labeled lines are EXACTLY the gate reasons and the turn
    # counter. An extra labeled row (over-labeling) and a dropped one
    # (under-labeling) are both RED here.
    assert _labeled(render) == _expected_labeled(status)


def test_provenance_label_is_exclusive(tmp_path):
    # Anti-vacuous twin, from the other side. The mutation the AC guards against
    # is dropping the suffix everywhere; this pins the opposite mutation -
    # labeling a model-maintained field too. `story` is the clearest case: it is
    # the spine's own narration of where it is, not a copied machine value.
    render = _render_full(tmp_path)
    status = json.loads((FIXTURES / "full_run" / "impl" / "run-status.json").read_text())
    expected = _expected_labeled(status)

    story_lines = [l for l in render.splitlines() if l.startswith("- Story: ")]
    assert len(story_lines) == 1
    assert not story_lines[0].endswith(MACHINE), "the story row must not be labeled"

    over_labeled = "\n".join(
        f"{line} {MACHINE}" if line.startswith("- Story: ") else line for line in render.splitlines()
    )
    assert _labeled(over_labeled) != expected, (
        "labeling a model-maintained field must FAIL the set-equality - otherwise "
        "labeling everything would satisfy the AC while carrying no provenance"
    )

    # And the under-labeling mutant: strip the suffix everywhere.
    bare = render.replace(f" {MACHINE}", "")
    assert _labeled(bare) != expected
    assert _labeled(bare) == set()


# --- read-only ---------------------------------------------------------------


def test_render_is_read_only_and_spawns_nothing(tmp_path):
    run_dir = tmp_path / "fixture-copy"
    shutil.copytree(FIXTURES / "full_run", run_dir)
    before = _snapshot(run_dir)

    result = _run(
        [
            "--impl-artifacts",
            str(run_dir / "impl"),
            "--run-dir",
            str(run_dir / "run"),
            "--runs-root",
            str(FIXTURES / "runs_root"),
            "--repo",
            str(tmp_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "a populated run must render something"

    # Bytes AND mtimes, for every file: a rewrite with identical content would
    # still move the mtime.
    assert _snapshot(run_dir) == before, "the render mutated its own inputs"

    # Source level: no write call, and exactly one spawn - the viewer probe.
    assert read_only_violations(SCRIPT.read_text(encoding="utf-8")) == []


def test_writing_variant_fixture_fails_read_only_assertion():
    # Anti-vacuous twin: the same helper, over the shipped module plus exactly
    # one memoizing write - the obvious "harmless" cache. It must FAIL, which is
    # what proves the assertion keys on the write call rather than on some
    # unrelated property of the file.
    shipped = SCRIPT.read_text(encoding="utf-8")
    variant = (FIXTURES / "status_render_writes.py.txt").read_text(encoding="utf-8")

    # The fixture is the shipped module plus ONE line. Pinned, so the fixture
    # cannot silently rot into a stale copy that proves nothing about the module
    # actually shipping today.
    shipped_lines, variant_lines = shipped.splitlines(), variant.splitlines()
    assert len(variant_lines) == len(shipped_lines) + 1, (
        "regenerate status_render_writes.py.txt: it must be the shipped module "
        "plus exactly one added write line"
    )
    added = [l for l in variant_lines if l not in shipped_lines]
    assert len(added) == 1 and "write_text" in added[0], added

    violations = read_only_violations(variant)
    assert "write_text" in violations, violations
    assert read_only_violations(shipped) == [], "the shipped module must stay clean"


# --- runs index --------------------------------------------------------------


def test_runs_index_lists_known_runs_with_status(tmp_path):
    result = _run(
        [
            "--impl-artifacts",
            str(tmp_path / "empty"),
            "--runs-root",
            str(FIXTURES / "runs_root"),
            "--repo",
            str(tmp_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    # LIST equality: the third folder carries no decision log, so it is not a
    # run and its appearance anywhere in the index is RED.
    assert _index_rows(result.stdout) == [("epic-a", "terminal"), ("epic-b", "live")]
    assert "epic-c" not in result.stdout


def test_runs_index_status_discriminates_on_run_report(tmp_path):
    # Anti-vacuous twin: the equality above cannot catch a renderer that hardcodes
    # `terminal`, because a genuinely terminal run renders identically under both.
    # Removing the run report must flip that row to `live`.
    runs_root = tmp_path / "runs"
    shutil.copytree(FIXTURES / "runs_root", runs_root)
    (runs_root / "epic-a" / "run-report.md").unlink()

    result = _run(
        [
            "--impl-artifacts",
            str(tmp_path / "empty"),
            "--runs-root",
            str(runs_root),
            "--repo",
            str(tmp_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert _index_rows(result.stdout) == [("epic-a", "live"), ("epic-b", "live")]

    # The fixture itself is untouched: its report is still there.
    assert (FIXTURES / "runs_root" / "epic-a" / "run-report.md").is_file()


# --- degrade, never crash ----------------------------------------------------


def test_absent_and_partial_status_degrade_not_crash(tmp_path):
    # (a) no heartbeat at all: exit 0, and the distinct opening line.
    empty = tmp_path / "impl"
    empty.mkdir()
    absent = _run(["--impl-artifacts", str(empty), "--repo", str(tmp_path)])
    assert absent.returncode == 0, absent.stderr
    assert absent.stdout.splitlines()[0] == f"no run: {empty / 'run-status.json'} not found"

    # (b) a heartbeat carrying only the two earliest keys: every field the spine
    # has not written yet renders `n/a`, at exit 0.
    partial = _run(
        [
            "--impl-artifacts",
            str(FIXTURES / "partial_status"),
            "--runs-root",
            str(FIXTURES / "runs_root"),
            "--repo",
            str(tmp_path),
        ]
    )
    assert partial.returncode == 0, partial.stderr
    assert "- Epic: sample" in partial.stdout
    assert "- Last verdict: n/a" in partial.stdout
    assert f"- Last reason: n/a {MACHINE}" in partial.stdout
    assert f"- Budget used: n/a {MACHINE}" in partial.stdout

    # (b') "absent" is not "present-but-empty": a zero-byte heartbeat is what a
    # run that died mid-write leaves, and it must reach the same `n/a` path
    # rather than a decode error.
    zero_byte = FIXTURES / "empty_status" / "run-status.json"
    assert zero_byte.stat().st_size == 0
    empty_file = _run(
        [
            "--impl-artifacts",
            str(FIXTURES / "empty_status"),
            "--runs-root",
            str(FIXTURES / "runs_root"),
            "--repo",
            str(tmp_path),
        ]
    )
    assert empty_file.returncode == 0, empty_file.stderr
    assert "- Epic: n/a" in empty_file.stdout
    assert "- Last verdict: n/a" in empty_file.stdout

    # (c) an unrecognized key is neither rendered nor fatal.
    unknown_dir = tmp_path / "unknown"
    unknown_dir.mkdir()
    (unknown_dir / "run-status.json").write_text(
        json.dumps({"epic": "sample", "story": "alpha", "quantum_flux": "surprise"}),
        encoding="utf-8",
    )
    unknown = _run(
        ["--impl-artifacts", str(unknown_dir), "--runs-root", str(FIXTURES / "runs_root"), "--repo", str(tmp_path)]
    )
    assert unknown.returncode == 0, unknown.stderr
    assert "quantum_flux" not in unknown.stdout
    assert "surprise" not in unknown.stdout
    assert "- Epic: sample" in unknown.stdout


def test_malformed_invocation_still_exits_2():
    # Anti-vacuous twin: case (a) above is satisfiable by a renderer that exits 0
    # unconditionally and prints nothing. This pins the other side of the split
    # `gate_trail.py` draws - an absent SOURCE is fail-soft, a malformed
    # INVOCATION is not - so those zeroes are attributable to source-absence
    # handling and not to a blanket try/except.
    result = _run([])
    assert result.returncode == 2
    assert result.stdout.strip() == "", "a refused invocation must render nothing"
    assert "usage" in result.stderr.lower()
    assert "--impl-artifacts" in result.stderr


# --- escalations: promoted vs crash residual ---------------------------------


def _escalation_render(tmp_path: Path) -> str:
    result = _run(
        [
            "--impl-artifacts",
            str(FIXTURES / "escalations"),
            "--runs-root",
            str(FIXTURES / "runs_root"),
            "--repo",
            str(tmp_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_unpromoted_escalation_md_renders_as_unpromoted(tmp_path):
    # The unpromoted fixture is copied verbatim from a real budget-overrun marker
    # a session left behind, so this is the shape that actually occurs.
    render = _escalation_render(tmp_path)
    assert render.count(UNPROMOTED) == 1, "the unpromoted literal must render exactly once"

    block = _escalation_block(render, "chore-empty-set-fail-opens")
    assert UNPROMOTED in block, "the literal must attach to the unpromoted story, not another"
    assert ".escalation-chore-empty-set-fail-opens.md" in block


def test_promoted_escalation_does_not_render_unpromoted(tmp_path):
    # Paired negative in the same fixture set. The naive implementation - glob
    # every `.escalation-*.md` and label them all - satisfies the positive half
    # and must FAIL here, since this story's marker DOES have its typed sidecar.
    render = _escalation_render(tmp_path)
    block = _escalation_block(render, "delta")
    assert UNPROMOTED not in block, "a promoted escalation must not read as unpromoted"
    # It renders from the typed sidecar instead.
    sidecar = json.loads((FIXTURES / "escalations" / "escalation-delta.json").read_text())
    for key in ("kind", "decision_needed", "evidence"):
        assert sidecar[key] in block, f"promoted block missing {key}"
    assert (FIXTURES / "escalations" / ".escalation-delta.md").is_file(), (
        "the raw marker stays on disk; it is never consumed by promotion"
    )


# --- the optional viewer affordance ------------------------------------------


def test_hunk_absent_and_present_differ_only_by_hunk_lines(tmp_path):
    """The affordance appears only when the probe finds the viewer.

    BOUND: "present" is a STUB executable on PATH, never a real install. This
    proves the probe is consulted and that its effect is confined to stdout; it
    does NOT prove a real `hunk show <sha>` renders a usable diff.
    """
    with_viewer = _render_full(tmp_path, viewer_dir=_stub_viewer(tmp_path)).splitlines()
    without = _render_full(tmp_path).splitlines()

    # LIST equality: strip the affordance lines and the two renders are the same
    # document. A renderer that emitted the line unconditionally would put
    # `hunk ` lines in `without` and fail here.
    assert [line for line in with_viewer if f"{VIEWER} " not in line] == without

    viewer_lines = [line for line in with_viewer if f"{VIEWER} " in line]
    committed = [line for line in without if line.strip().startswith("- baseline `")]
    assert committed, "the fixture must carry at least one committed story row"
    assert len(viewer_lines) == len(committed), "one affordance line per committed story row"
    for line in viewer_lines:
        assert re.fullmatch(rf"\s+- {VIEWER} show [0-9a-f]{{7,40}}", line), line


def test_hunk_presence_leaves_gate_artifacts_and_envelope_identical(tmp_path):
    # The second mutation the list-equality above cannot catch: threading the
    # probe result into an ARTIFACT (recording it into the heartbeat, say). The
    # affordance must reach stdout and nothing else, so a run's recorded evidence
    # never depends on which tools the reader happened to have installed.
    run_dir = tmp_path / "fixture-copy"
    shutil.copytree(FIXTURES / "full_run", run_dir)

    gate_artifacts = [run_dir / "trace" / "gate-decision-beta.json", run_dir / "trace" / "trace-beta.md"]
    for artifact in gate_artifacts:
        assert artifact.is_file(), artifact

    blockers = [{"source": "impl/.escalation-beta.md", "decision_needed": "re-scope, split, or hand off"}]
    log = run_dir / "run" / ".decision-log.md"

    before_artifacts = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in gate_artifacts}
    before_envelope = envelope.build_headless_envelope(blockers, log, write_log=False)

    result = _run(
        [
            "--impl-artifacts",
            str(run_dir / "impl"),
            "--run-dir",
            str(run_dir / "run"),
            "--runs-root",
            str(FIXTURES / "runs_root"),
            "--repo",
            str(tmp_path),
        ],
        viewer_dir=_stub_viewer(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert f"{VIEWER} show" in result.stdout, "the with-viewer render must carry the affordance"

    after_artifacts = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in gate_artifacts}
    after_envelope = envelope.build_headless_envelope(blockers, log, write_log=False)

    assert after_artifacts == before_artifacts, "a viewer-present render moved a gate artifact"
    assert json.dumps(after_envelope, sort_keys=True) == json.dumps(before_envelope, sort_keys=True)


# --- registration -------------------------------------------------------------


def _csv_rows() -> list[list[str]]:
    with HELP_CSV.open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def _node_missing() -> bool:
    return subprocess.run(["node", "--version"], capture_output=True).returncode != 0


def _validate_skills(skill_dir: Path) -> tuple[int, str]:
    proc = subprocess.run(
        ["node", str(VALIDATE_SKILLS), str(skill_dir), "--strict", "--json"],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout


@pytest.mark.skipif(_node_missing(), reason="node not available")
def test_skill_registered_in_help_csv_and_passes_validate_skills():
    rows = _csv_rows()
    header, data = rows[0], [r for r in rows[1:] if r]
    assert len(header) == CSV_COLUMNS

    module_rows = [r for r in data if r[0] == MODULE_COLUMN]
    assert len(module_rows) == 4, [r[1] for r in module_rows]

    status_rows = [r for r in module_rows if r[1] == "ucg-status"]
    assert len(status_rows) == 1, "exactly one ucg-status row"
    assert len(status_rows[0]) == CSV_COLUMNS, len(status_rows[0])

    menu_codes = [r[3] for r in module_rows]
    assert len(set(menu_codes)) == len(menu_codes), menu_codes

    # Columns 0-3 must stay comma-free: the installer's uniqueness check splits
    # the raw line naively, so a comma earlier in the row silently moves the
    # menu-code slot.
    for row in module_rows:
        for column in row[:4]:
            assert "," not in column, (row[1], column)

    # No authored _meta row: the installer assembles that one.
    assert not [r for r in data if len(r) > 1 and r[1] == "_meta"]

    # The skill dir passes --strict with zero HIGH+.
    rc, out = _validate_skills(SKILL_DIR)
    assert rc == 0, out
    high_plus = [f for f in json.loads(out) if f["severity"] in ("CRITICAL", "HIGH")]
    assert high_plus == [], high_plus

    # The description clause is asserted directly: it is MEDIUM, so --strict's
    # exit code alone would not cover it.
    text = SKILL_MD.read_text(encoding="utf-8")
    description = re.search(r"^description:\s*(.+?)\n(?:\w+:|---)", text, re.MULTILINE | re.DOTALL)
    assert description, "SKILL.md must carry a description"
    body = description.group(1)
    assert len(body) <= 1024, len(body)
    assert re.search(r"use\s+when\b", body, re.IGNORECASE), body

    # The renderer is invoked through the PARENT skill root - the one thing a
    # nested skill gets wrong by default.
    assert "{ucg-root}/scripts/status_render.py" in text


@pytest.mark.skipif(_node_missing(), reason="node not available")
def test_name_mismatch_skill_mutant_fails_validate_skills(tmp_path):
    # Anti-vacuous twin: the single most likely slip when copying a sibling
    # skill as the template is a `name` that no longer matches its directory.
    # The validator must catch it here, which also proves it actually reads this
    # new nested path rather than silently skipping it.
    mutant = (FIXTURES / "skill_name_mismatch.txt").read_text(encoding="utf-8")
    skill_dir = tmp_path / "ucg-status"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(mutant, encoding="utf-8")

    rc, out = _validate_skills(skill_dir)
    assert rc == 1, "a name/directory mismatch must exit 1 under --strict"
    rules = {f["rule"] for f in json.loads(out)}
    assert "SKILL-05" in rules, ("expected SKILL-05 (name != directory), got", rules)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
