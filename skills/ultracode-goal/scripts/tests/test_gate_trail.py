#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for gate_trail.py, the per-story evidence trail written at finalize.

Run: uv run --with pytest pytest scripts/tests/test_gate_trail.py

Two halves share this module because the behavior has two halves: the script
that synthesizes the trail, and the finalize reference that mandates the step and
pins where the file lands. Deleting either one has to red something here.

The fixtures are the oracle. A full production finalize cannot be reproduced in
CI (this repository runs the light profile), so the production path is proven
against a hand-built fixture run folder, and the light path against fixtures that
carry the exact shape a hand-authored trace report really has - including one
whose coverage table drops the house split column, which is what makes
"parse by header name" a testable claim rather than an intention.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS / "gate_trail.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gate_trail"
FINALIZE = SCRIPTS.parent / "references" / "finalize.md"

PRODUCTION_STORIES = ["7-1", "7-2", "7-3", "7-4"]
LIGHT_STORIES = ["2-4", "2-6"]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


gate_trail = _load("gate_trail", SCRIPT)
# The very module the trail defers its verdict mapping to: comparing against this
# object is what makes "the verdict cell is the gate's own map" a byte-level claim.
gate_eval = gate_trail.gate_eval


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def copy_fixture(name: str, tmp_path: Path) -> Path:
    """Copy a fixture run into tmp_path.

    Tests never read the fixtures in place, and never read a run's real output
    directory: the shipped fixtures are the only inputs, so the suite stays green
    on a clean checkout.
    """
    root = tmp_path / name
    shutil.copytree(FIXTURES / name, root)
    return root


def run_trail(
    *,
    run_dir: Path,
    profile: str,
    stories: list[str],
    impl_artifacts: Path | None = None,
    trace_output: Path | None = None,
    test_artifacts: Path | None = None,
    decision_log: Path | None = None,
    repo: Path | None = None,
    epic: str = "7",
    extra: list[str] | None = None,
    expect_ok: bool = True,
) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--run-dir",
        str(run_dir),
        "--profile",
        profile,
        "--epic",
        epic,
    ]
    for story in stories:
        cmd += ["--story", story]
    if impl_artifacts is not None:
        cmd += ["--impl-artifacts", str(impl_artifacts)]
    if trace_output is not None:
        cmd += ["--trace-output", str(trace_output)]
    if test_artifacts is not None:
        cmd += ["--test-artifacts", str(test_artifacts)]
    if decision_log is not None:
        cmd += ["--decision-log", str(decision_log)]
    if repo is not None:
        cmd += ["--repo", str(repo)]
    cmd += extra or []
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if expect_ok:
        assert proc.returncode == 0, proc.stderr
    return proc


def production_trail(tmp_path: Path) -> str:
    root = copy_fixture("production", tmp_path)
    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="production",
        stories=PRODUCTION_STORIES,
        impl_artifacts=root / "impl-artifacts",
        trace_output=root / "test-artifacts" / "traceability",
        test_artifacts=root / "test-artifacts",
        decision_log=root / "decision-log.md",
        repo=tmp_path,
    )
    return (run_dir / "gate-trail.md").read_text(encoding="utf-8")


def light_trail(tmp_path: Path) -> str:
    root = copy_fixture("light", tmp_path)
    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="light",
        stories=LIGHT_STORIES,
        impl_artifacts=root / "impl-artifacts",
        trace_output=root / "test-artifacts" / "traceability",
        test_artifacts=root / "test-artifacts",
        decision_log=root / "decision-log.md",
        repo=tmp_path,
        epic="2",
    )
    return (run_dir / "gate-trail.md").read_text(encoding="utf-8")


def section(text: str, story: str) -> str:
    """The rendered section for one story."""
    match = re.search(
        rf"^## Story {re.escape(story)}\s*$(.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"no section for story {story} in:\n{text}"
    return match.group(1)


def rows(section_text: str) -> list[list[str]]:
    """The table's data rows, as lists of cells (header and rule excluded)."""
    table = [ln for ln in section_text.splitlines() if ln.strip().startswith("|")]
    assert len(table) >= 2, f"no table in section:\n{section_text}"
    out = []
    for line in table[2:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        out.append(cells)
    return out


def header_cells(section_text: str) -> list[str]:
    table = [ln for ln in section_text.splitlines() if ln.strip().startswith("|")]
    return [c.strip() for c in table[0].strip().strip("|").split("|")]


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# A finalized Epic produces the trail, as a peer of the run report, with all
# five columns.
# ---------------------------------------------------------------------------


def test_production_fixture_renders_all_five_columns(tmp_path):
    """Every story section traces criterion, planned test, result, verdict, commit.

    Drop any one of the five from the renderer's column constant and this reds on
    the missing header. It cannot pass against an absent or empty trail either:
    it reads the file the synthesizer wrote and requires one section per story
    with a populated table under each.
    """
    text = production_trail(tmp_path)

    assert len(re.findall(r"^## Story ", text, re.MULTILINE)) == len(PRODUCTION_STORIES)
    for story in PRODUCTION_STORIES:
        body = section(text, story)
        assert header_cells(body) == [
            "Acceptance criterion",
            "Planned test",
            "Result",
            "Gate verdict",
            "Commit",
        ]
        data = rows(body)
        assert data, f"story {story} rendered no rows"
        for row in data:
            assert len(row) == 5, row


def test_trail_is_written_as_peer_of_run_report_in_the_run_folder(tmp_path):
    """The artifact lands in the run folder, named gate-trail.md, and prints its path."""
    root = copy_fixture("production", tmp_path)
    run_dir = tmp_path / "run"
    (run_dir).mkdir()
    (run_dir / "run-report.md").write_text("# Run report\n", encoding="utf-8")

    proc = run_trail(
        run_dir=run_dir,
        profile="production",
        stories=PRODUCTION_STORIES,
        impl_artifacts=root / "impl-artifacts",
        trace_output=root / "test-artifacts" / "traceability",
        decision_log=root / "decision-log.md",
        repo=tmp_path,
    )

    written = run_dir / "gate-trail.md"
    assert written.is_file()
    assert proc.stdout.strip() == str(written)
    # The peer relationship is the point: same folder as the run report, and not
    # under the implementation-artifacts directory.
    assert written.parent == (run_dir / "run-report.md").parent
    assert not (root / "impl-artifacts" / "gate-trail.md").exists()


def test_finalize_mandates_gate_trail_peer_of_run_report():
    """The finalize reference mandates the step and pins where the file goes.

    Delete the section and this reds: the section regex finds nothing.
    """
    text = FINALIZE.read_text(encoding="utf-8")
    match = re.search(r"^## Gate trail\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, "finalize.md has no `## Gate trail` section"
    body = match.group(1)

    assert "gate-trail.md" in body
    assert "run-report.md" in body, "the section must pin the trail as a peer of the run report"
    assert "peer" in body.lower()
    assert "scripts/gate_trail.py" in body
    for column in ("acceptance criterion", "planned test", "result", "gate verdict", "commit"):
        assert column in body.lower(), f"the section does not name the {column} column"
    # Ordering: the trail is written after the run report and before the recall write.
    assert text.index("## Run report") < text.index("## Gate trail")
    assert text.index("## Gate trail") < text.index("## Cross-Session Recall write")
    # The health check stays the terminal action.
    assert text.index("## Gate trail") < text.index("## Workflow health check")


# ---------------------------------------------------------------------------
# Pure synthesis: no new judgment, no new verdict.
# ---------------------------------------------------------------------------


def test_verdict_cell_is_gate_eval_verdict_map(tmp_path):
    """Each verdict cell is byte-traceable to the gate's own status map.

    Comparison is against gate_eval.GATE_VERDICT itself, so replacing the lookup
    with any constant reds at least one story here.
    """
    text = production_trail(tmp_path)
    expected = {
        "7-1": gate_eval.GATE_VERDICT["PASS"],
        "7-2": gate_eval.GATE_VERDICT["FAIL"],
        "7-3": gate_eval.GATE_VERDICT["NOT_EVALUATED"],
    }
    for story, verdict in expected.items():
        cells = {row[3] for row in rows(section(text, story))}
        assert cells == {verdict}, f"story {story} rendered {cells}, expected {verdict}"


def test_unknown_gate_status_renders_verbatim(tmp_path):
    """An unrecognized gate status is shown as recorded, not re-classified.

    Defaulting the lookup (for instance to `escalate`) would be the synthesizer
    forming a classification of its own, and reds here.
    """
    text = production_trail(tmp_path)
    body = section(text, "7-4")
    assert "WOBBLE" not in gate_eval.GATE_VERDICT
    cells = {row[3] for row in rows(body)}
    assert cells == {"WOBBLE"}
    for verdict in gate_eval.GATE_VERDICT.values():
        assert verdict not in cells


def test_trail_never_reapplies_production_and(tmp_path, monkeypatch):
    """The production AND is not re-run at finalize: it already ran at the gate.

    Two independent alarms. First, the AND helper is replaced with a detonator:
    calling it at all fails the test. Second, the command line offers no way to
    hand this script the two signals the AND consumes, so it cannot be re-applied
    even by a caller.
    """
    called: list[str] = []

    def detonate(*args, **kwargs):
        called.append("apply_production_and")
        raise AssertionError("the trail re-applied the production AND")

    monkeypatch.setattr(gate_trail.gate_eval, "apply_production_and", detonate)

    root = copy_fixture("production", tmp_path)
    text = gate_trail.render(
        PRODUCTION_STORIES,
        epic="7",
        profile="production",
        impl_artifacts=root / "impl-artifacts",
        test_artifacts=root / "test-artifacts",
        trace_output=root / "test-artifacts" / "traceability",
        decision_log=root / "decision-log.md",
        repo=tmp_path,
    )

    assert called == []
    # The passing story stays advance. Re-running the AND here would find neither
    # signal file and, being fail-closed, would downgrade it to reloop.
    assert {row[3] for row in rows(section(text, "7-1"))} == {"advance"}

    for flag in ("--nfr", "--test-review"):
        proc = run_trail(
            run_dir=tmp_path / "rejected",
            profile="production",
            stories=["7-1"],
            extra=[flag, "whatever"],
            expect_ok=False,
        )
        assert proc.returncode != 0, f"{flag} must not be accepted by the trail"


# ---------------------------------------------------------------------------
# A story whose verdict was not advance is rendered as such.
# ---------------------------------------------------------------------------


def test_fail_fixture_renders_reloop_not_advance(tmp_path):
    text = production_trail(tmp_path)
    body = section(text, "7-2")
    cells = {row[3] for row in rows(body)}
    assert cells == {"reloop"}
    assert "advance" not in body
    assert "`FAIL`" in body, "the section must name the gate status it rendered from"


def test_not_evaluated_fixture_renders_escalate(tmp_path):
    text = production_trail(tmp_path)
    body = section(text, "7-3")
    cells = {row[3] for row in rows(body)}
    assert cells == {"escalate"}
    assert "advance" not in body


def test_a_story_with_no_gate_artifact_is_not_given_another_storys_verdict(tmp_path):
    """An unevaluated story renders n/a, never a neighbour's verdict.

    Found by running the synthesizer against a real multi-story artifact
    directory: a story that had written nothing yet was handed the first
    story's gate file by the shared resolver's unscoped fallback and rendered
    green. A story that was never gated must never look gated.
    """
    root = copy_fixture("production", tmp_path)
    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="production",
        # 7-5 has no trace report, no gate file and no baseline in the fixture.
        stories=[*PRODUCTION_STORIES, "7-5"],
        impl_artifacts=root / "impl-artifacts",
        trace_output=root / "test-artifacts" / "traceability",
        decision_log=root / "decision-log.md",
        repo=tmp_path,
    )
    text = (run_dir / "gate-trail.md").read_text(encoding="utf-8")
    body = section(text, "7-5")

    assert {row[3] for row in rows(body)} == {"n/a"}
    assert "advance" not in body
    for other in PRODUCTION_STORIES:
        assert f"gate-decision-{other}.json" not in body
    # The neighbours still resolve their own gates.
    assert {row[3] for row in rows(section(text, "7-1"))} == {"advance"}


def test_recorded_verdict_in_the_decision_log_wins_over_the_mapped_one(tmp_path):
    """A verdict the run recorded is what the trail renders.

    The gate's status map is the fallback, not an override: a run that recorded
    its own verdict (a downgrade, for instance) must not be re-rendered green by
    a later reading of the raw gate status.
    """
    root = copy_fixture("production", tmp_path)
    log = root / "decision-log.md"
    log.write_text(
        log.read_text(encoding="utf-8")
        + "\n### Story 7-1 - recorded verdict\n\n```json\n"
        + json.dumps({"story": "7-1", "gate_status": "PASS", "verdict": "reloop"})
        + "\n```\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="production",
        stories=PRODUCTION_STORIES,
        impl_artifacts=root / "impl-artifacts",
        trace_output=root / "test-artifacts" / "traceability",
        decision_log=log,
        repo=tmp_path,
    )
    text = (run_dir / "gate-trail.md").read_text(encoding="utf-8")
    assert {row[3] for row in rows(section(text, "7-1"))} == {"reloop"}
    # Unrecorded stories still come from the gate artifact.
    assert {row[3] for row in rows(section(text, "7-3"))} == {"escalate"}


# ---------------------------------------------------------------------------
# The light path: no acceptance checklist, and every source optional.
# ---------------------------------------------------------------------------


def test_light_story_section_from_trace_coverage_table(tmp_path):
    """With no acceptance checklist, the section is built from the trace report."""
    text = light_trail(tmp_path)
    body = section(text, "2-4")
    data = rows(body)

    assert [row[0] for row in data] == ["1", "2", "3", "4"]
    assert [row[1] for row in data] == [
        "`test_step4_has_four_and_clauses`",
        "`test_reds_unioned_not_new_authority`",
        "`test_formalize_clause_fail_closed`",
        "`test_clause_reuses_post_remediation_kernel`",
    ]
    assert {row[2] for row in data} == {"COVERED"}
    assert {row[3] for row in data} == {gate_eval.GATE_VERDICT["PASS"]}
    assert "trace-2-4.md" in body, "the section must name the artifact it synthesized from"


def test_light_trace_table_parsed_by_header_not_index(tmp_path):
    """A trace table without the house split column still yields the planned test.

    The fixture's columns are `AC | Verification | Status`, so a parser that
    indexes by position (the planned test is the third column in the house shape)
    reads the coverage status instead. Reading by header name is what keeps the
    planned-test cell correct.
    """
    fixture = (
        FIXTURES / "light" / "test-artifacts" / "traceability" / "trace-2-6.md"
    ).read_text(encoding="utf-8")
    header = next(ln for ln in fixture.splitlines() if ln.strip().startswith("| AC"))
    assert "Split" not in header, "the twin fixture must NOT carry the split column"

    text = light_trail(tmp_path)
    data = rows(section(text, "2-6"))
    assert [row[1] for row in data] == [
        "`test_ac1_same_line_conjunction`",
        "`test_ac2_exact_verdict_token`",
        "`test_ac3_single_bullet_scope_no_time_number`",
        "`test_ac4_cross_file_verdict_equality`",
    ]
    assert "COVERED" not in {row[1] for row in data}
    assert {row[2] for row in data} == {"COVERED"}


def test_light_profile_ignores_a_checklist_that_happens_to_exist(tmp_path):
    """The acceptance checklist is a production source only.

    A light run has none by design; if a stale one is lying around, the trace
    report - the light profile's actual oracle - still decides what is rendered.
    """
    root = copy_fixture("light", tmp_path)
    (root / "test-artifacts" / "atdd-checklist-2-4.md").write_text(
        "| AC | Planned test | Result |\n|---|---|---|\n| 99 | `stale_test` | STALE |\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="light",
        stories=["2-4"],
        impl_artifacts=root / "impl-artifacts",
        trace_output=root / "test-artifacts" / "traceability",
        test_artifacts=root / "test-artifacts",
        decision_log=root / "decision-log.md",
        repo=tmp_path,
        epic="2",
    )
    body = section((run_dir / "gate-trail.md").read_text(encoding="utf-8"), "2-4")
    assert "stale_test" not in body
    assert "`test_step4_has_four_and_clauses`" in body


def test_missing_source_renders_na_without_raising(tmp_path):
    """A story with every optional source missing renders, it does not fail.

    Strip the fail-soft read wrapper and the missing checklist and baseline
    propagate an OSError instead: the synthesizer raises where it should have
    rendered a cell, and this reds on the non-zero exit.
    """
    empty_impl = tmp_path / "impl-artifacts"
    empty_trace = tmp_path / "traceability"
    empty_impl.mkdir()
    empty_trace.mkdir()
    run_dir = tmp_path / "run"

    proc = run_trail(
        run_dir=run_dir,
        profile="production",
        stories=["9-9"],
        impl_artifacts=empty_impl,
        trace_output=empty_trace,
        decision_log=tmp_path / "nowhere" / "decision-log.md",
        repo=tmp_path,
        epic="9",
    )
    assert "Traceback" not in proc.stderr

    body = section((run_dir / "gate-trail.md").read_text(encoding="utf-8"), "9-9")
    data = rows(body)
    assert len(data) == 1
    assert data[0] == ["n/a", "n/a", "n/a", "n/a", "n/a"]


def test_missing_baseline_renders_na_commit_cell(tmp_path):
    """A story whose baseline was never recorded renders n/a for its commit.

    It must not abort the trail: the stories around it still render their own
    commit ranges.
    """
    text = production_trail(tmp_path)

    without_baseline = rows(section(text, "7-4"))
    assert {row[4] for row in without_baseline} == {"n/a"}

    with_baseline = rows(section(text, "7-1"))
    assert {row[4] for row in with_baseline} != {"n/a"}
    assert all(row[4].startswith("`") for row in with_baseline)


def test_commit_cell_lists_shas_from_the_recorded_baseline_range(tmp_path):
    """The commit column is the real git range between recorded baselines.

    The last story's range ends at HEAD, and a range with nothing in it is
    reported as such - an observation for the reader, never a verdict.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    shas = []
    for index in range(3):
        (repo / f"f{index}.txt").write_text(f"{index}\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"change {index}")
        shas.append(_git(repo, "rev-parse", "HEAD"))

    impl = tmp_path / "impl-artifacts"
    impl.mkdir()
    (impl / ".baseline-9-1").write_text(shas[0] + "\n", encoding="utf-8")
    (impl / ".baseline-9-2").write_text(shas[2] + "\n", encoding="utf-8")

    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="light",
        stories=["9-1", "9-2"],
        impl_artifacts=impl,
        repo=repo,
        epic="9",
    )
    text = (run_dir / "gate-trail.md").read_text(encoding="utf-8")

    first = rows(section(text, "9-1"))[0][4]
    assert shas[1][:7] in first and shas[2][:7] in first
    assert shas[0][:7] not in first, "the baseline itself is the range start, not a story commit"

    last = rows(section(text, "9-2"))[0][4]
    assert "no commits in range" in last


# ---------------------------------------------------------------------------
# House rules: the shipped surfaces describe behavior, never a plan identifier.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [SCRIPT, FINALIZE, Path(__file__)])
def test_shipped_surfaces_cite_no_plan_identifiers(path: Path):
    text = path.read_text(encoding="utf-8")
    if path == Path(__file__):
        # This test names the patterns it forbids; skip its own definition lines.
        text = text.split("# House rules:")[0]
    for pattern in (r"\bFR-\d", r"\bAD-\d", r"\bNFR-\d", r"\bOQ-\d", r"\bINV-\d", r"\bAC-\d"):
        assert not re.search(pattern, text), f"{path.name} cites {pattern}"
