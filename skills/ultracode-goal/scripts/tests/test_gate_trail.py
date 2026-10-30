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
GATE = SCRIPTS.parent / "references" / "gate.md"

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


def _log_with_verdict(tmp_path: Path, heading_id: str, verdict: str) -> Path:
    """A decision log carrying one story heading and one fenced verdict block."""
    log = tmp_path / f"decision-log-{heading_id}.md"
    log.write_text(
        f"# Decision log\n\n### Story {heading_id} - some prose title\n\n```json\n"
        + json.dumps({"story": heading_id, "verdict": verdict})
        + "\n```\n",
        encoding="utf-8",
    )
    return log


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


def test_a_recorded_verdict_without_a_gate_artifact_is_not_rendered(tmp_path):
    """A decision-log verdict is honoured only when the story's gate artifact resolved.

    Measured on a real epic: a story with a `.baseline-<id>` from an earlier
    invocation but no resolvable per-story gate artifact fell through to the
    decision-log verdict and rendered `advance` beside `Gate artifact: n/a` —
    while `gate_eval.py` on the same story returns NOT_EVALUATED -> escalate.
    The trail must not out-vote the gate in the gate's own column: no artifact,
    no rendered verdict, and the source line says why.
    """
    root = copy_fixture("production", tmp_path)
    log = root / "decision-log.md"
    log.write_text(
        log.read_text(encoding="utf-8")
        + "\n### Story 7-5 - recorded but artifact-less\n\n```json\n"
        + json.dumps({"story": "7-5", "gate_status": "PASS", "verdict": "advance"})
        + "\n```\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="production",
        # 7-5 has no trace report and no gate file in the fixture.
        stories=[*PRODUCTION_STORIES, "7-5"],
        impl_artifacts=root / "impl-artifacts",
        trace_output=root / "test-artifacts" / "traceability",
        decision_log=log,
        repo=tmp_path,
    )
    text = (run_dir / "gate-trail.md").read_text(encoding="utf-8")
    body = section(text, "7-5")

    assert {row[3] for row in rows(body)} == {"n/a"}
    assert "advance" not in body
    assert "no gate artifact resolved" in body
    # A story whose artifact DID resolve still renders its verdict normally.
    assert {row[3] for row in rows(section(text, "7-1"))} == {"advance"}


def test_alphanumeric_sibling_ids_do_not_share_one_recorded_verdict(tmp_path):
    """One driven story's verdict must not bleed onto undriven siblings.

    The recorded-verdict map used to be keyed by `numeric_prefix`, which keeps
    only the LEADING numeric components — so `92-0a`, `92-3b` and `92-7f` all
    collapsed to the bucket `92` and every sibling in the `--story` list rendered
    whatever verdict the log last recorded. Measured against a real epic's
    artifacts: 63 of 76 stories rendered a `defer` that only one of them had
    actually reached.

    The `92-8` control matters. Its second component IS numeric, so it never
    collided and always rendered correctly — which is why the defect read as
    "sometimes" and was twice diagnosed wrongly.
    """
    stories = ["92-0a-alpha", "92-3b-beta", "92-7f-gamma", "92-8-numeric"]
    recorded = gate_trail.recorded_verdicts(_log_with_verdict(tmp_path, "92-3b", "defer"))

    assert recorded == {"92-3b": "defer"}, "the heading id is keyed verbatim"
    resolved = gate_trail.resolve_recorded_verdicts(recorded, stories)
    assert resolved == {"92-3b-beta": "defer"}, "exactly the story that was driven"


def test_a_heading_matching_every_story_records_none_of_them(tmp_path):
    """An epic-wide heading names no single story, so no story inherits it.

    This is the uniqueness rule doing its job: rendering `## Story 92`'s verdict
    on all of 92's children is the fabrication the trail's `n/a` promise forbids.
    """
    stories = ["92-1-one", "92-2-two", "92-3-three"]
    recorded = gate_trail.recorded_verdicts(_log_with_verdict(tmp_path, "92", "advance"))

    assert recorded == {"92": "advance"}
    assert gate_trail.resolve_recorded_verdicts(recorded, stories) == {}


def test_a_short_heading_id_still_matches_its_full_slugged_story(tmp_path):
    """Headings carry the short id; `--story` carries the full slug.

    A real log writes `### Story 92-0a - the five confirmed defects` while the
    trail is invoked with `92-0a-the-five-confirmed-defects`. Requiring equality
    would blank the verdict column on every real run, which is the failure mode
    the obvious "key it by the full id" fix would have introduced.
    """
    recorded = gate_trail.recorded_verdicts(_log_with_verdict(tmp_path, "92-0a", "defer"))
    resolved = gate_trail.resolve_recorded_verdicts(
        recorded, ["92-0a-the-five-confirmed-defects"]
    )
    assert resolved == {"92-0a-the-five-confirmed-defects": "defer"}


def test_gate_artifact_resolves_for_an_alphanumeric_story_id(tmp_path):
    """The trail resolves the same gate file `gate_eval.py` resolves.

    `gate_status_for` scoped by `numeric_prefix`, so `92-3b-…` truncated to `92`,
    nothing in a per-story directory is named `92`, and the cell read
    `Gate artifact: n/a` for a file sitting right there under its correct name.
    Reported at least six times across one epic. The assertion that matters is
    the AGREEMENT: both readers, same directory, same id, same file.

    NO TRACE REPORT HERE, DELIBERATELY. Every prior sighting was worked around by
    authoring `trace-<id>.md` with a `gateDecisionFile:` hint, and that hint
    rescues resolution even under the truncated scope — so a fixture carrying one
    reproduces the workaround, not the defect. The story's own slim gate file,
    standing alone, is the case that failed.
    """
    trace = tmp_path / "traceability"
    trace.mkdir()
    story = "92-3b-the-minting-primitives-secrets-and-escrow"
    (trace / f"gate-decision-{story}.json").write_text(
        json.dumps({"gate_status": "CONCERNS"}), encoding="utf-8"
    )

    status, source = gate_trail.gate_status_for(trace, story)
    assert (status, source) == ("CONCERNS", f"gate-decision-{story}.json")

    reasons: list[str] = []
    assert gate_eval.load_gate(trace, reasons, story)["gate_status"] == "CONCERNS"
    assert any(f"gate-decision-{story}.json" in r for r in reasons)


def test_a_story_with_its_own_gate_never_renders_a_neighbours_status(tmp_path):
    """The truncated scope did not only under-report; it could report a PASS.

    With the scope collapsed to the bare epic number, `_resolve_gate_file` matched
    nothing by id and fell through to the FIRST sorted trace report's hint - a
    neighbour's. `belongs()` then accepted it anyway, because `own_trace` is true
    whenever this story has any matching `.md` in the directory, which disarms
    the very narrowing whose docstring promises to stop "an unevaluated story
    with someone else's verdict - silently green".

    So a CONCERNS story rendered its neighbour's PASS. That is the direction that
    matters: a spurious PASS is the verdict nobody re-reads.
    """
    trace = tmp_path / "traceability"
    trace.mkdir()
    for story, status in (
        ("92-1a-the-neighbour-story", "PASS"),
        ("92-9a-the-rehearsal-constant", "CONCERNS"),
    ):
        (trace / f"trace-{story}.md").write_text(
            f"---\nworkflowType: testarch-trace\ngateDecisionFile: gate-decision-{story}.json\n---\n# t\n",
            encoding="utf-8",
        )
        (trace / f"gate-decision-{story}.json").write_text(
            json.dumps({"gate_status": status}), encoding="utf-8"
        )

    status, source = gate_trail.gate_status_for(trace, "92-9a-the-rehearsal-constant")
    assert (status, source) == (
        "CONCERNS",
        "gate-decision-92-9a-the-rehearsal-constant.json",
    )
    # The oracle is agreement with the reader that actually decides.
    reasons: list[str] = []
    assert (
        gate_eval.load_gate(trace, reasons, "92-9a-the-rehearsal-constant")["gate_status"]
        == status
    )


def test_gate_artifact_resolves_when_the_trace_report_carries_a_hint(tmp_path):
    """The hint path that every field workaround relied on still resolves."""
    trace = tmp_path / "traceability"
    trace.mkdir()
    story = "92-3b-the-minting-primitives-secrets-and-escrow"
    (trace / f"trace-{story}.md").write_text(
        f"---\nworkflowType: testarch-trace\ngateDecisionFile: gate-decision-{story}.json\n---\n# t\n",
        encoding="utf-8",
    )
    (trace / f"gate-decision-{story}.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )
    assert gate_trail.gate_status_for(trace, story) == (
        "PASS",
        f"gate-decision-{story}.json",
    )


def test_trace_report_is_the_declared_one_not_the_alphabetical_first(tmp_path):
    """`nfr-assessment-<id>.md` sorts first and is not the trace report.

    `references/gate.md`'s non-web-stack path puts `nfr-assessment-`,
    `test-review-` and `trace-` files for one story in one directory. Selecting
    the first sorted id-match returned the NFR file, which carries no
    `gateDecisionFile` hint, so no gate resolved and the per-AC table vanished.
    """
    trace = tmp_path / "traceability"
    trace.mkdir()
    story = "92-3b-the-minting"
    (trace / f"nfr-assessment-{story}.md").write_text(
        "# NFR\n\n**Overall Status:** CONCERNS\n", encoding="utf-8"
    )
    (trace / f"test-review-{story}.md").write_text("# Review\n", encoding="utf-8")
    (trace / f"trace-{story}.md").write_text(
        f"---\nworkflowType: testarch-trace\ngateDecisionFile: gate-decision-{story}.json\n---\n# t\n",
        encoding="utf-8",
    )
    (trace / f"gate-decision-{story}.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )

    assert gate_trail.trace_report_path(trace, story).name == f"trace-{story}.md"
    assert gate_trail.gate_status_for(trace, story)[0] == "PASS"


def test_generic_named_single_story_dir_resolves_its_gate(tmp_path):
    """The documented isolate-into-a-fresh-dir workaround must actually work.

    `references/gate.md` sanctions isolating one story's artifacts under the
    generic names `trace.md` / `gate-decision.json`, and `gate_eval.py` resolves
    them. The trail rejected the resolved file afterwards, because a generic stem
    matches no story id - so the workaround recovered nothing and a third
    sighting reported byte-equal output to the un-worked-around render.
    """
    trace = tmp_path / "isolated"
    trace.mkdir()
    (trace / "trace.md").write_text(
        "---\nworkflowType: testarch-trace\ngateDecisionFile: gate-decision.json\n---\n# t\n",
        encoding="utf-8",
    )
    (trace / "gate-decision.json").write_text(
        json.dumps({"gate_status": "CONCERNS"}), encoding="utf-8"
    )
    assert gate_trail.gate_status_for(trace, "92-9a-the-rehearsal-constant") == (
        "CONCERNS",
        "gate-decision.json",
    )


def test_a_shared_generic_summary_is_not_inherited_by_an_undriven_story(tmp_path):
    """The generic-name allowance must not fire in a per-story directory.

    `e2e-trace-summary.json` is written unconditionally and carries no story id.
    Accepting a generic name on the filename alone therefore hands its status to
    every story in the directory that wrote nothing - which is the exact
    fail-open the id-keying fixes exist to close, re-entering through the door
    opened for the isolated-directory workaround.

    The oracle is AGREEMENT: `gate_eval.py` fails closed for this story, so the
    trail must render `n/a`, not the summary's PASS.
    """
    trace = tmp_path / "traceability"
    trace.mkdir()
    (trace / "trace-92-1.md").write_text(
        "---\nworkflowType: testarch-trace\ngateDecisionFile: gate-decision-92-1.json\n---\n# t\n",
        encoding="utf-8",
    )
    (trace / "gate-decision-92-1.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )
    (trace / "e2e-trace-summary.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )

    assert gate_trail.gate_status_for(trace, "92-2-never-driven") == (None, None)
    reasons: list[str] = []
    assert gate_eval.load_gate(trace, reasons, "92-2-never-driven")["gate_status"] == "NOT_EVALUATED"
    # The story that DID write artifacts still resolves its own.
    assert gate_trail.gate_status_for(trace, "92-1")[1] == "gate-decision-92-1.json"


def test_a_scopes_summary_fallback_never_preempts_another_scopes_gate_file(tmp_path):
    """Every scope's gate file is tried before any scope's summary.

    Resolving each scope completely in turn let the FULL id's summary fallback
    answer first: `_resolve_gate_file` found nothing under `4-1-some-slug`, the
    same iteration fell to the epic-wide `e2e-trace-summary.json`, and the story's
    own `gate-decision-4-1.json` - reachable under the numeric prefix - was never
    read. CONCERNS rendered as PASS, which is a downgrade in the unsafe direction.
    """
    trace = tmp_path / "traceability"
    trace.mkdir()
    (trace / "trace-4-1.md").write_text(
        "---\nworkflowType: testarch-trace\ngateDecisionFile: gate-decision-4-1.json\n---\n# t\n",
        encoding="utf-8",
    )
    (trace / "gate-decision-4-1.json").write_text(
        json.dumps({"gate_status": "CONCERNS"}), encoding="utf-8"
    )
    (trace / "e2e-trace-summary.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )

    assert gate_trail.gate_status_for(trace, "4-1-some-slug") == (
        "CONCERNS",
        "gate-decision-4-1.json",
    )


def test_reports_declaring_no_workflow_type_keep_sorted_first(tmp_path):
    """The workflowType preference must not resolve NOTHING for an old dir."""
    trace = tmp_path / "traceability"
    trace.mkdir()
    (trace / "trace-4-1.md").write_text("# plain trace report, no frontmatter\n", encoding="utf-8")
    assert gate_trail.trace_report_path(trace, "4-1").name == "trace-4-1.md"


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


# TEA-authored trace reports, in the two shapes a real 1.27.2 run wrote. TEA's
# template defines no single matrix table, so the parser has to find the
# criterion-keyed table that names a planned test, and must never mistake TEA's
# gate-threshold tables (`| Criterion | Threshold | Actual | Status |`) for
# acceptance criteria.
_TEA_THRESHOLDS = """
| Criterion             | Threshold | Actual | Status  |
| --------------------- | --------- | ------ | ------- |
| P0 Coverage           | 100%      | 100%   | ✅ PASS |
| P1 Coverage           | 90%       | 100%   | ✅ PASS |
"""

_TEA_DESIGN_FIRST = (
    """
| AC | FRs | Test design ID | Priority | Risk links (test design) |
| -- | --- | -------------- | -------- | ------------------------ |
| AC1 | FR1 | 1.1-UNIT-001 | P0 | R-001 (6) |
| AC2 | FR2 | 1.1-UNIT-002 | P0 | R-001 (6) |

| Criterion | Description | Priority | Test ID | Test (node) | File:Line | Level | Cases | Result | Coverage |
| --------- | ----------- | -------- | ------- | ----------- | --------- | ----- | ----- | ------ | -------- |
| AC1 (FR1) | example | P0 | 1.1-UNIT-001 | `test_prd_example` | tests/test_core.py:8 | unit | 1 | 1/1 passed | FULL |
| AC2 (FR2) | folding | P0 | 1.1-UNIT-002 | `test_accents_fold` | tests/test_core.py:20 | unit | 3 | 3/3 passed | FULL |
"""
    + _TEA_THRESHOLDS
)

_TEA_MATRIX_FIRST = (
    """
| Criterion | Description | Priority | Test ID | Test file:line | Level | Pytest items (passed) | Coverage |
| --------- | ----------- | -------- | ------- | -------------- | ----- | --------------------- | -------- |
| AC1 | prints the slug | P1 | 1.2-INT-001 | `tests/test_cli.py:22` | integration | 4/4 | FULL ✅ |
| AC2 | empty slug | P1 | 1.2-INT-002 | `tests/test_cli.py:35` | integration | 3/3 | FULL ✅ |
"""
    + _TEA_THRESHOLDS
    + """
| AC | FRs | Test design ID | Priority | Risk links (test design) |
| -- | --- | -------------- | -------- | ------------------------ |
| AC1 | FR7 | 1.2-INT-001 | P1 | R-004 (4) |
"""
)


def test_tea_report_with_a_design_table_first_reads_the_matrix():
    rows_ = gate_trail.criterion_rows(_TEA_DESIGN_FIRST, prefer_tested=True)
    assert rows_ == [
        ("AC1 (FR1)", "`test_prd_example`", "1/1 passed"),
        ("AC2 (FR2)", "`test_accents_fold`", "3/3 passed"),
    ]


def test_tea_report_with_the_matrix_first_reads_tea_column_names():
    """`Test file:line` is the planned test, and with no `Result` header the
    pass count (`Pytest items (passed)`) is the result, never the coverage."""
    rows_ = gate_trail.criterion_rows(_TEA_MATRIX_FIRST, prefer_tested=True)
    assert rows_ == [
        ("AC1", "`tests/test_cli.py:22`", "4/4"),
        ("AC2", "`tests/test_cli.py:35`", "3/3"),
    ]


def test_no_test_column_anywhere_falls_back_and_never_reads_thresholds():
    """With no planned-test column anywhere, the trail must not render a gate
    threshold as a criterion with a PASS beside it."""
    design_only = _TEA_DESIGN_FIRST.split("| Criterion | Description")[0] + _TEA_THRESHOLDS
    for prefer_tested in (False, True):
        rows_ = gate_trail.criterion_rows(design_only, prefer_tested=prefer_tested)
        assert rows_ == [("AC1", "n/a", "n/a"), ("AC2", "n/a", "n/a")]


def test_a_report_with_only_threshold_tables_yields_no_criteria():
    assert gate_trail.criterion_rows(_TEA_THRESHOLDS, prefer_tested=True) == []


def test_tea_columns_are_picked_by_name_not_position():
    """Swap `Test ID` and `Test (node)`, and `Result` and `Coverage`: the same
    columns must be picked, the test node over the bare id and the result over
    the coverage status."""
    swapped = (
        "| Criterion | Test (node) | Test ID | Coverage | Result |\n"
        "| --------- | ----------- | ------- | -------- | ------ |\n"
        "| AC1 | `test_prd_example` | 1.1-UNIT-001 | FULL | 1/1 passed |\n"
    )
    assert gate_trail.criterion_rows(swapped, prefer_tested=True) == [
        ("AC1", "`test_prd_example`", "1/1 passed")
    ]


# Production acceptance checklists keep "the first criterion-keyed table wins":
# their first such table is the AC table, and later tables are inventories or
# case lists. Both shapes below are real checklists the tested-table preference
# misread when it applied to checklists too.
_CHECKLIST_WITH_INVENTORY = """
| AC | Pri | Risk ids | Level | Acceptance test file(s) |
|----|-----|----------|-------|--------------------------|
| 1. org context carried | P1 | DATA-03 | schema-source | `org-context.test.ts` |

| # | File | Tests | Level | ACs |
|---|------|-------|-------|-----|
| 1 | `org-context.test.ts` | 7 | schema-source | 1 |
"""

_CHECKLIST_WITH_CASE_TABLES = """
| AC | Claim | Priority | Planned assertion | Where |
|---|---|---|---|---|
| 1 | both schemes registered | **P0** | repo scan + twin | G1.1, G1.2 |

| id | Test | Pri | RED because |
|---|---|---|---|
| G1.1 | the repo scan returns zero violations | **P0** | the scanner does not exist |
"""


def test_a_checklist_keeps_its_ac_table_over_an_inventory():
    assert gate_trail.criterion_rows(_CHECKLIST_WITH_INVENTORY) == [
        ("1. org context carried", "n/a", "n/a")
    ]


def test_a_checklist_keeps_its_ac_table_over_a_case_table():
    assert gate_trail.criterion_rows(_CHECKLIST_WITH_CASE_TABLES) == [("1", "n/a", "n/a")]


def test_a_trace_never_lets_a_case_list_or_inventory_replace_its_ac_table():
    """The fail-open: an AC table with no recognised test column, followed by a
    case list marked PASS, rendered the case ids as criteria and dropped the AC."""
    case_list = (
        "| AC | Claim |\n| -- | ----- |\n| AC1 | import | \n| AC2 | fold |\n| AC3 | untested |\n\n"
        "| ID | Test | Status |\n| -- | ---- | ------ |\n"
        "| T1 | test_import | PASS |\n| T2 | test_fold | PASS |\n"
    )
    rows_ = gate_trail.criterion_rows(case_list, prefer_tested=True)
    assert [row[0] for row in rows_] == ["AC1", "AC2", "AC3"]
    assert gate_trail.criterion_rows(_CHECKLIST_WITH_INVENTORY, prefer_tested=True) == [
        ("1. org context carried", "n/a", "n/a")
    ]


def _tea_atdd_ac_table() -> str:
    """TEA 1.27.2's ATDD checklist AC table, as its template writes it. The ids
    are built rather than spelled, so this file carries no planning-style id."""
    rows = "".join(
        f"| AC-{n} | supplied/generated | criterion {n} |\n" for n in (1, 2, 3)
    )
    return (
        "| ID   | ID source          | Acceptance criterion     |\n"
        "| ---- | ------------------ | ------------------------ |\n" + rows
    )


def test_tea_atdd_checklist_ac_table_is_read_in_both_modes():
    """Its first criterion-like header is `ID`, which alone is ambiguous: the
    table's keys are all its criterion-like headers, `Acceptance criterion` too."""
    for prefer_tested in (False, True):
        rows_ = gate_trail.criterion_rows(_tea_atdd_ac_table(), prefer_tested=prefer_tested)
        assert [row[0] for row in rows_] == [f"AC-{n}" for n in (1, 2, 3)]


def test_tea_atdd_ac_table_is_not_replaced_by_a_following_case_list():
    case_list = "\n| ID | Test | Status |\n| -- | ---- | ------ |\n| T1 | test_login | PASS |\n"
    for prefer_tested in (False, True):
        rows_ = gate_trail.criterion_rows(_tea_atdd_ac_table() + case_list, prefer_tested=prefer_tested)
        assert [row[0] for row in rows_] == [f"AC-{n}" for n in (1, 2, 3)]


def test_a_case_list_never_stands_in_for_a_skipped_criterion_table():
    """`| Criterion | Description | Priority |` names no test, so it is set aside;
    a following `| ID | Test | Status |` case list must not take its place."""
    text = (
        "| Criterion | Description | Priority |\n| --------- | ----------- | -------- |\n"
        "| AC1 | import | P0 |\n| AC2 | fold | P1 |\n\n"
        "| ID | Test | Status |\n| -- | ---- | ------ |\n| T1 | test_import | PASS |\n"
    )
    for prefer_tested in (False, True):
        rows_ = gate_trail.criterion_rows(text, prefer_tested=prefer_tested)
        assert all(not row[0].startswith("T") for row in rows_), rows_


def test_coverage_standing_in_for_a_result_is_labelled():
    text = (
        "| Criterion | Test file:line | Coverage |\n| --------- | -------------- | -------- |\n"
        "| AC1 | `tests/test_cli.py:22` | FULL |\n"
    )
    assert gate_trail.criterion_rows(text, prefer_tested=True) == [
        ("AC1", "`tests/test_cli.py:22`", "coverage: FULL")
    ]


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


def _commit_range_repo(tmp_path):
    """A three-commit repo plus an impl-artifacts dir, for the range tests below."""
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
    return repo, impl, shas


def test_a_story_that_committed_is_not_rendered_as_having_committed_nothing(tmp_path):
    """The `.commit-<story>` marker closes a story's range without a neighbour.

    THE DEFECT THIS PINS, observed in the field: story 9-1 committed, and the
    NEXT story's baseline marker was residue anchored at 9-1's own head sha. The
    range end was inferred from that neighbour, so it collapsed to `X..X` and the
    trail rendered `(no commits in range)` for a story with a commit sitting in
    the log. Inference from baselines alone could not tell that apart from a story
    that legitimately committed nothing, which is why the end sha is now recorded
    by the step that makes the commit instead of guessed afterwards.
    """
    repo, impl, shas = _commit_range_repo(tmp_path)
    (impl / ".baseline-9-1").write_text(shas[0] + "\n", encoding="utf-8")
    # residue: the later story is anchored at 9-1's OWN head, collapsing 9-1's
    # inferred range to shas[2]..shas[2]
    (impl / ".baseline-9-2").write_text(shas[2] + "\n", encoding="utf-8")
    (impl / ".commit-9-1").write_text(shas[2] + "\n", encoding="utf-8")

    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="light",
        stories=["9-1", "9-2"],
        impl_artifacts=impl,
        repo=repo,
        epic="9",
    )
    cell = rows(section((run_dir / "gate-trail.md").read_text(encoding="utf-8"), "9-1"))[0][4]

    assert "no commits in range" not in cell, cell
    assert shas[1][:7] in cell and shas[2][:7] in cell, cell
    assert shas[0][:7] not in cell, "the baseline is the range start, not a story commit"


def test_a_story_that_really_committed_nothing_still_says_so(tmp_path):
    """The marker must not manufacture commits for a story that made none.

    An escalated story leaves a baseline (step 0 writes it before any
    implementation) and no `.commit-` marker, because step 4 never ran. It falls
    back to the old inference and still reports an empty range - the observation
    the commit cell is documented to make, and the false-positive direction the
    previous comment refused to trade for.
    """
    repo, impl, shas = _commit_range_repo(tmp_path)
    (impl / ".baseline-9-1").write_text(shas[2] + "\n", encoding="utf-8")

    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="light",
        stories=["9-1"],
        impl_artifacts=impl,
        repo=repo,
        epic="9",
    )
    cell = rows(section((run_dir / "gate-trail.md").read_text(encoding="utf-8"), "9-1"))[0][4]

    assert "no commits in range" in cell, cell


def test_execute_orders_the_end_sha_marker_to_be_written_and_refreshed():
    """The reader is only correct if the step that commits actually writes it.

    `.commit-<story>` is the one step-0-family marker whose rule is refresh
    rather than keep, so both halves have to be ordered: written at step 4, and
    rewritten at step 5 after an amend or a remediation re-commit. A reader
    pointed at a marker nobody writes silently falls back forever.
    """
    execute = (SCRIPTS.parent / "references" / "execute.md").read_text(encoding="utf-8")

    assert ".commit-<story_id>" in execute
    assert execute.count(".commit-<story_id>") >= 2, "step 4 writes it; step 5 must refresh it"
    assert re.search(r"refreshed, not preserved", execute), (
        "the refresh rule must be stated, or a reader keeps a stale end sha after an amend"
    )


# ---------------------------------------------------------------------------
# The story list is an argument, not a source: fail-soft does not cover it.
# ---------------------------------------------------------------------------


def test_zero_stories_is_refused_and_nothing_is_written(tmp_path):
    # The fail-open this closes: naming no story used to exit 0 and write a
    # well-formed trail of zero sections - an evidence artifact that traces
    # nothing, which the stage then names in the run report as delivered
    # evidence. Refusal must happen before anything lands on disk.
    run_dir = tmp_path / "run"
    proc = run_trail(run_dir=run_dir, profile="light", stories=[], expect_ok=False)

    assert proc.returncode == 2
    assert "--story" in proc.stderr
    assert not (run_dir / "gate-trail.md").exists()
    # Refused up front, so not even the run folder is created.
    assert not run_dir.exists()


def test_blank_story_id_is_refused(tmp_path):
    # The same error wearing a value: a blank id otherwise renders an anonymous
    # section of nothing but `n/a`, which reads as a story that was gated and
    # came back empty rather than one that was never named.
    run_dir = tmp_path / "run"
    proc = run_trail(run_dir=run_dir, profile="light", stories=[""], expect_ok=False)

    assert proc.returncode == 2
    assert "--story values must be non-empty story ids" in proc.stderr
    assert not (run_dir / "gate-trail.md").exists()


def test_one_story_still_renders(tmp_path):
    # Anti-vacuous twin: the guard keys on the EMPTY/blank list and nothing
    # else, so the ordinary single-story invocation is untouched.
    run_dir = tmp_path / "run"
    # repo is pinned to tmp_path so the commit-range lookup can never shell out
    # against the runner's CWD; hermetic by construction, not by the accident of
    # --impl-artifacts being absent.
    proc = run_trail(run_dir=run_dir, profile="light", stories=["4-1"], repo=tmp_path)

    assert proc.returncode == 0
    assert (run_dir / "gate-trail.md").exists()


def test_finalize_states_the_story_ids_are_required():
    """The stage must say the ids are required and that refusal is not a halt.

    Without this the section reads as best-effort: it sits under a paragraph
    promising every source is optional, so a conductor can reasonably take the
    whole invocation as fail-soft.
    """
    text = FINALIZE.read_text(encoding="utf-8")
    match = re.search(r"^## Gate trail\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, "finalize.md has no `## Gate trail` section"
    body = match.group(1)

    assert "required" in body.lower(), "the section must state the story ids are required"
    # The refusal must be classified, or a hard exit at the SECOND of finalize's
    # sections reads as an escalation and strands every step after it.
    assert "invocation error" in body.lower()
    assert "not a gate verdict" in body.lower()
    assert re.search(r"continue through the remaining finalize steps", body, re.I), (
        "the section must tell the conductor to finish the remaining finalize steps"
    )


# ---------------------------------------------------------------------------
# House rules: the shipped surfaces describe behavior, never a plan identifier.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        SCRIPT,
        FINALIZE,
        Path(__file__),
        # The resolution property file builds artifact fixtures with a criterion
        # table, which is exactly where an `AC-<n>` reaches a shipped surface by
        # habit. It was in the list of files that could drift before it was in
        # the list of files this checks.
        Path(__file__).resolve().parent / "test_artifact_resolution_property.py",
    ],
)
def test_shipped_surfaces_cite_no_plan_identifiers(path: Path):
    text = path.read_text(encoding="utf-8")
    if path == Path(__file__):
        # This test names the patterns it forbids; skip its own definition lines.
        text = text.split("# House rules:")[0]
    for pattern in (r"\bFR-\d", r"\bAD-\d", r"\bNFR-\d", r"\bOQ-\d", r"\bINV-\d", r"\bAC-\d"):
        assert not re.search(pattern, text), f"{path.name} cites {pattern}"


# ---------------------------------------------------------------------------
# The two remaining ways `belongs()` could be disarmed, both of which handed an
# undriven story somebody else's PASS.
# ---------------------------------------------------------------------------


def _declared_trace(trace: Path, story: str) -> None:
    (trace / f"trace-{story}.md").write_text(
        "---\nworkflowType: testarch-trace\n"
        f"gateDecisionFile: gate-decision-{story}.json\n---\n# t\n",
        encoding="utf-8",
    )


def _slim(trace: Path, story: str, status: str) -> None:
    (trace / f"gate-decision-{story}.json").write_text(
        json.dumps({"gate_status": status}), encoding="utf-8"
    )


def test_alphanumeric_child_story_never_inherits_the_epic_rollups_pass(tmp_path):
    """`numeric_prefix('92-7f-never-driven')` is `92` — the EPIC id, not a shorter
    spelling of the story.

    The epic roll-up writes `trace-92.md` / `gate-decision-92.json` into the same
    shared directory, so the truncated scope matched a real artifact set and a
    story nobody ever drove rendered the epic's PASS as its own verdict.
    """
    trace = tmp_path / "traceability"
    trace.mkdir()
    # the epic roll-up, PASS
    _declared_trace(trace, "92")
    _slim(trace, "92", "PASS")
    # a genuinely driven sibling, so the directory is per-story-named
    _declared_trace(trace, "92-1a")
    _slim(trace, "92-1a", "CONCERNS")

    status, source = gate_trail.gate_status_for(trace, "92-7f-never-driven")

    assert (status, source) == (None, None), (
        "an undriven child story resolved %r from %r" % (status, source)
    )


def test_the_epic_rollup_still_resolves_its_own_gate(tmp_path):
    """Control for the test above. Narrowing the prefix scope must not make the
    epic's own roll-up unresolvable — without this, the assertion above would
    also pass on a build that simply stopped resolving anything."""
    trace = tmp_path / "traceability"
    trace.mkdir()
    _declared_trace(trace, "92")
    _slim(trace, "92", "PASS")
    _declared_trace(trace, "92-1a")
    _slim(trace, "92-1a", "CONCERNS")

    assert gate_trail.gate_status_for(trace, "92") == ("PASS", "gate-decision-92.json")
    assert gate_trail.gate_status_for(trace, "92-1a") == (
        "CONCERNS",
        "gate-decision-92-1a.json",
    )


def test_slug_suffixed_story_still_resolves_through_the_prefix_fallback(tmp_path):
    """The fallback the prefix scope exists FOR must survive the narrowing.

    `4-1-some-slug` keeps a complete `<epic>-<story>` prefix, so it still resolves
    `gate-decision-4-1.json`. This is the case the scope was added for.
    """
    trace = tmp_path / "traceability"
    trace.mkdir()
    _declared_trace(trace, "4-1")
    _slim(trace, "4-1", "PASS")

    assert gate_trail.gate_status_for(trace, "4-1-some-slug") == (
        "PASS",
        "gate-decision-4-1.json",
    )


def test_a_story_with_only_an_nfr_file_does_not_claim_a_trace_report(tmp_path):
    """`own_trace` disarms `belongs()` entirely, so it must mean what it says.

    `references/gate.md` ORDERS the non-web author to write `nfr-assessment-<id>.md`
    into this same directory. Computed from any id-matching `*.md`, `own_trace`
    was true for a story that produced only that file — and the always-written
    `e2e-trace-summary.json` was then accepted as its gate.
    """
    trace = tmp_path / "traceability"
    trace.mkdir()
    (trace / "e2e-trace-summary.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )
    # a driven sibling, so the directory is not the isolated single-story shape
    _declared_trace(trace, "92-1a")
    _slim(trace, "92-1a", "CONCERNS")
    # the undriven story wrote ONLY its NFR file - no workflowType frontmatter
    (trace / "nfr-assessment-92-7f.md").write_text(
        "# NFR\n\n**Overall Status:** PASS\n", encoding="utf-8"
    )

    status, source = gate_trail.gate_status_for(trace, "92-7f")

    assert (status, source) == (None, None), (
        "a story with only an NFR file resolved %r from %r" % (status, source)
    )


def test_a_trace_report_does_not_buy_a_story_the_shared_summarys_verdict(tmp_path):
    """A DECLARED trace report is not a gate artifact, and does not reach the shared summary.

    THIS TEST PREVIOUSLY ASSERTED THE OPPOSITE, as a control proving a narrowing
    had removed only the NFR-only case "and not the mechanism". The mechanism was
    the defect. `gate_status_for` reaches `e2e-trace-summary.json` through
    `gate_eval._resolve_summary_file`, which bypasses `gate_eval.load_gate` - and
    `load_gate` REFUSES this exact read, in a per-story-named directory, with a
    comment naming it "the neighbour's-verdict fail-open wearing a different
    filename". So the two readers disagreed about one file, which this module's
    own `gate_status_for` docstring calls a defect, and the disagreement ran in
    the dangerous direction: measured on this very fixture, `gate_eval` returned
    `escalate` for 92-7f while the rendered trail printed `advance`.

    The directory here is the reason. It holds 92-1a's per-story artifacts too,
    so `e2e-trace-summary.json` is the run-wide file and provably not 92-7f's
    alone - and 92-7f, which wrote no gate artifact, would otherwise outrank
    92-1a, which wrote its own CONCERNS. The isolated all-generic directory,
    where a generic summary DOES belong to the one story being driven, is
    unaffected and keeps its own test.
    """
    trace = tmp_path / "traceability"
    trace.mkdir()
    (trace / "e2e-trace-summary.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )
    _declared_trace(trace, "92-1a")
    _slim(trace, "92-1a", "CONCERNS")
    # this story DID write a declared trace report, but no slim gate file
    (trace / "trace-92-7f.md").write_text(
        "---\nworkflowType: testarch-trace\n---\n# t\n", encoding="utf-8"
    )

    status, source = gate_trail.gate_status_for(trace, "92-7f")

    assert (status, source) == (None, None), (
        "a story with a trace report but no gate artifact resolved %r from %r" % (status, source)
    )

    # The two readers now agree about this file, which is the whole point.
    reasons: list[str] = []
    assert gate_eval.load_gate(trace, reasons, "92-7f")["gate_status"] == "NOT_EVALUATED", reasons


# ---------------------------------------------------------------------------
# A story the run escalated renders `escalate`, never the verdict it escalated
# from. The `escalate` route stops after logging `gate_eval.py`'s `reloop` (a
# FAIL only operator evidence can change, or a re-loop past the turn ceiling),
# and FAIL maps to `reloop` too.
# ---------------------------------------------------------------------------


def _sidecar(impl: Path, story: str, kind: str) -> Path:
    path = impl / f"escalation-{story}.json"
    path.write_text(
        json.dumps(
            {
                "source": f"trace-{story}.md",
                "kind": kind,
                "decision_needed": "record the live result the criterion owes",
                "evidence": "no record exists",
            }
        ),
        encoding="utf-8",
    )
    return path


def _sprint(impl: Path, rows_by_key: dict[str, str]) -> None:
    (impl / "sprint-status.yaml").write_text(
        "development_status:\n" + "".join(f"  {k}: {v}\n" for k, v in rows_by_key.items()),
        encoding="utf-8",
    )


def _escalation_trail(tmp_path: Path, root: Path, stories: list[str]) -> str:
    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="production",
        stories=stories,
        impl_artifacts=root / "impl-artifacts",
        trace_output=root / "test-artifacts" / "traceability",
        decision_log=root / "decision-log.md",
        repo=tmp_path,
    )
    return (run_dir / "gate-trail.md").read_text(encoding="utf-8")


def _source_line(body: str) -> str:
    return next(ln for ln in body.splitlines() if ln.startswith("- Verdict source:"))


def test_an_open_operator_evidence_escalation_renders_escalate_not_reloop(tmp_path):
    """Measured on a real run: every row of a story that escalated
    `operator-evidence-owed` read `reloop`, telling the reader it owed a code fix
    when it owed only an operator's record."""
    root = copy_fixture("production", tmp_path)
    impl = root / "impl-artifacts"
    _sidecar(impl, "7-2", "operator-evidence-owed")
    _sprint(impl, {"7-1": "done", "7-2": "review", "7-3": "review", "7-4": "review"})
    log = root / "decision-log.md"
    log.write_text(
        log.read_text(encoding="utf-8")
        + "\n### Story 7-2: gate\n\n```json\n"
        + json.dumps({"verdict": "reloop", "gate_status": "FAIL", "reasons": ["gate_status FAIL -> reloop"]})
        + "\n```\n",
        encoding="utf-8",
    )
    text = _escalation_trail(tmp_path, root, PRODUCTION_STORIES)
    body = section(text, "7-2")
    assert {row[3] for row in rows(body)} == {"escalate"}
    assert _source_line(body) == (
        "- Verdict source: the open escalation `escalation-7-2.json` (kind `operator-evidence-owed`)"
    )
    assert "reloop" not in body
    assert {row[3] for row in rows(section(text, "7-1"))} == {"advance"}


def test_an_open_escalation_with_no_gate_artifact_renders_escalate(tmp_path):
    """`gate_eval.py` returns NOT_EVALUATED -> escalate for a story with no gate
    artifact, so an open escalation there reads `escalate` too, never `n/a`, and
    a verdict the log records for it still does not reach the cell."""
    root = copy_fixture("production", tmp_path)
    impl = root / "impl-artifacts"
    _sidecar(impl, "7-5", "budget-overrun")
    _sprint(impl, {"7-5": "in-progress"})
    log = root / "decision-log.md"
    log.write_text(
        log.read_text(encoding="utf-8")
        + "\n### Story 7-5: gate\n\n```json\n"
        + json.dumps({"verdict": "advance", "gate_status": "PASS"})
        + "\n```\n",
        encoding="utf-8",
    )
    text = _escalation_trail(tmp_path, root, [*PRODUCTION_STORIES, "7-5"])
    body = section(text, "7-5")
    assert {row[3] for row in rows(body)} == {"escalate"}
    assert _source_line(body) == (
        "- Verdict source: the open escalation `escalation-7-5.json` (kind `budget-overrun`), "
        "and no gate artifact resolved for this story"
    )
    assert "Gate artifact: n/a" in body


def test_an_unreadable_sidecar_is_an_open_escalation(tmp_path):
    """Read as a resume reads it: something escalated, and nothing on disk says it
    was answered."""
    root = copy_fixture("production", tmp_path)
    impl = root / "impl-artifacts"
    (impl / "escalation-7-2.json").write_text("{not json", encoding="utf-8")
    text = _escalation_trail(tmp_path, root, PRODUCTION_STORIES)
    body = section(text, "7-2")
    assert {row[3] for row in rows(body)} == {"escalate"}
    assert "(kind `unreadable`)" in _source_line(body)


@pytest.mark.parametrize("row", ["done", None], ids=["done-row", "no-sprint-status"])
def test_an_open_evidence_commit_rejected_escalation_keeps_advance_and_is_named(tmp_path, row):
    """The advance route writes this kind after the story advanced: only the
    evidence commit is owed, so the cell keeps `advance` and the source line
    names the escalation. Keyed on the kind, not on the row, so an unreadable
    sprint-status still keeps it green."""
    root = copy_fixture("production", tmp_path)
    impl = root / "impl-artifacts"
    _sidecar(impl, "7-1", "evidence-commit-rejected")
    if row is not None:
        _sprint(impl, {"7-1": row, "7-2": "review", "7-3": "review", "7-4": "review"})
    text = _escalation_trail(tmp_path, root, PRODUCTION_STORIES)
    body = section(text, "7-1")
    assert {cells[3] for cells in rows(body)} == {"advance"}
    assert _source_line(body) == (
        "- Verdict source: the gate artifact's status, mapped by the gate's own table; the "
        "escalation `escalation-7-1.json` (kind `evidence-commit-rejected`) is still open, and "
        "owes the evidence commit, not a verdict"
    )


def test_an_open_evidence_commit_rejected_escalation_keeps_a_defer(tmp_path):
    """Guard (passes before the fix too): the `defer` route advances anyway, so
    its evidence commit can be rejected as well, and the cell keeps `defer`,
    as finalize.md says, not `advance`."""
    root = copy_fixture("production", tmp_path)
    impl = root / "impl-artifacts"
    gate = root / "test-artifacts" / "traceability" / "gate-decision-7-1.json"
    gate.write_text(json.dumps({**json.loads(gate.read_text(encoding="utf-8")), "gate_status": "CONCERNS"}))
    (root / "decision-log.md").write_text(
        "# Decision log\n\n### Story 7-1: gate\n\n"
        + _fenced({"verdict": "defer", "gate_status": "CONCERNS", "reasons": ["gate_status CONCERNS -> defer"]}),
        encoding="utf-8",
    )
    _sidecar(impl, "7-1", "evidence-commit-rejected")
    _sprint(impl, {"7-1": "done", "7-2": "review", "7-3": "review", "7-4": "review"})
    body = section(_escalation_trail(tmp_path, root, PRODUCTION_STORIES), "7-1")
    assert {cells[3] for cells in rows(body)} == {"defer"}
    assert _source_line(body) == (
        "- Verdict source: recorded in the decision log; the escalation `escalation-7-1.json` "
        "(kind `evidence-commit-rejected`) is still open, and owes the evidence commit, not a verdict"
    )


def test_a_done_story_ignores_a_leftover_sidecar(tmp_path):
    """A `done` row advanced, so a sidecar an older run left beside it is residue,
    not where the story stopped. Measured on a real project: five `done` stories
    whose gates resolve sat beside open sidecars."""
    root = copy_fixture("production", tmp_path)
    impl = root / "impl-artifacts"
    _sidecar(impl, "7-2", "budget-overrun")
    _sprint(impl, {"7-1": "done", "7-2": "done", "7-3": "review", "7-4": "review"})
    text = _escalation_trail(tmp_path, root, PRODUCTION_STORIES)
    body = section(text, "7-2")
    assert {row[3] for row in rows(body)} == {"reloop"}
    assert "escalation-7-2.json" not in body


def test_a_closed_or_handoff_sidecar_is_not_an_open_escalation(tmp_path):
    """Read as a resume reads it: a closed id is an answered decision's residue,
    and a handoff hands work over rather than escalating a verdict."""
    sys.path.insert(0, str(SCRIPTS))
    import red_ids  # noqa: PLC0415

    root = copy_fixture("production", tmp_path)
    impl = root / "impl-artifacts"
    closed = _sidecar(impl, "7-2", "budget-overrun")
    data = json.loads(closed.read_text(encoding="utf-8"))
    (impl / ".decisions.json").write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "id": red_ids.mint_id(data["kind"], data["source"], data["decision_needed"]),
                        "action": "close",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _sidecar(impl, "7-4", "story-decomposed")
    _sprint(impl, {"7-1": "done", "7-2": "review", "7-3": "review", "7-4": "review"})
    text = _escalation_trail(tmp_path, root, PRODUCTION_STORIES)
    assert {row[3] for row in rows(section(text, "7-2"))} == {"reloop"}
    assert "escalation-" not in text


def test_a_story_heading_never_lends_a_later_storys_verdict(tmp_path):
    """The FIRST verdict object under a story heading is the story's own.

    A heading's span runs to the next heading the reader matches, and a log whose
    later stories are headed without the word `Story` puts their verdicts in the
    earlier story's span. Measured on a real epic: taking the LAST object there
    rendered one story `advance` on a later story's gate, where its own was
    `defer`.
    """
    log = tmp_path / "decision-log.md"
    log.write_text(
        "# Decision log\n\n### Story 7-1 - first\n\n```json\n"
        + json.dumps({"verdict": "defer", "gate_status": "CONCERNS"})
        + "\n```\n\n## Session 2\n\n### 7-2 - a later story, headed without the word\n\n```json\n"
        + json.dumps({"verdict": "advance", "gate_status": "PASS"})
        + "\n```\n",
        encoding="utf-8",
    )
    recorded = gate_trail.resolve_recorded_verdicts(gate_trail.recorded_verdicts(log), ["7-1", "7-2"])
    assert recorded == {"7-1": "defer"}


# ---------------------------------------------------------------------------
# Under the prescribed heading, the trail shows the story's own latest verdict
# object: not an earlier cycle's, and not the Epic-level roll-up's. A real
# project's conductor logged `gate_eval.py`'s result inline in backticks in five
# of seven gate cycles of one epic, which gate.md's "Record the full verdict
# JSON" allows, and a reader of fenced objects alone kept the cycle before.
# ---------------------------------------------------------------------------


def _fenced(payload: dict) -> str:
    return "```json\n" + json.dumps(payload) + "\n```\n\n"


def _inline(payload: dict) -> str:
    """`gate_eval.py`'s result as that project's log holds it: inside a sentence,
    wrapped mid-string."""
    raw = json.dumps(payload).replace("gate_status PASS", "gate_status\nPASS")
    return f"**gate_eval.py (production):** `{raw}`. `gate-provenance: tea`.\n\n"


_PASS = {"verdict": "advance", "gate_status": "PASS", "epic_level": False, "reasons": ["gate_status PASS -> advance"]}
_FAIL = {"verdict": "reloop", "gate_status": "FAIL", "epic_level": False, "reasons": ["gate_status FAIL -> reloop"]}


def _trail_over(tmp_path: Path, log_text: str, story: str = "7-1") -> str:
    """One story of the production fixture (7-1's gate file reads PASS, 7-2's
    FAIL) under `log_text`."""
    root = copy_fixture("production", tmp_path)
    log = root / "decision-log.md"
    log.write_text(log_text, encoding="utf-8")
    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="production",
        stories=[story],
        impl_artifacts=root / "impl-artifacts",
        trace_output=root / "test-artifacts" / "traceability",
        decision_log=log,
        repo=tmp_path,
    )
    return section((run_dir / "gate-trail.md").read_text(encoding="utf-8"), story)


def test_a_later_cycle_logged_inline_replaces_the_earlier_cycles_verdict(tmp_path):
    """Measured on a real epic: cycle 1 fenced its `reloop`, cycles 2 and 3
    logged theirs inline, and cycle 3 advanced. Every row read cycle 1's
    `reloop` once the prescribed heading stood before each cycle."""
    heading = "### Story 7-1: gate\n\n"
    body = _trail_over(
        tmp_path,
        "# Decision log\n\n" + heading + _fenced(_FAIL) + heading + _inline(_FAIL) + heading + _inline(_PASS),
    )
    assert {row[3] for row in rows(body)} == {"advance"}
    assert _source_line(body) == "- Verdict source: recorded in the decision log"


def test_an_inline_downgrade_is_the_verdict_shown(tmp_path):
    """The case the heading was prescribed for: a `PASS` the production signals
    downgraded to `reloop` must not read `advance` because it was logged
    inline."""
    downgraded = {"verdict": "reloop", "gate_status": "PASS", "nfr_status": "FAIL", "reasons": ["nfr FAIL"]}
    body = _trail_over(tmp_path, "# Decision log\n\n### Story 7-1: gate\n\n" + _inline(downgraded))
    assert {row[3] for row in rows(body)} == {"reloop"}
    assert _source_line(body) == "- Verdict source: recorded in the decision log"


@pytest.mark.parametrize(
    ("own", "shown", "source"),
    [
        (_inline(_PASS), "advance", "recorded in the decision log"),
        ("Gate: PASS, verdict advance.\n\n", "advance", "the gate artifact's status, mapped by the gate's own table"),
    ],
    ids=["own-verdict-inline", "own-verdict-as-prose"],
)
def test_the_epic_level_rollup_is_never_a_storys_verdict(tmp_path, own, shown, source):
    """The Epic-level gate runs after the last story's cycle under no story
    heading, so its fenced roll-up falls in that story's entries."""
    rollup = {"verdict": "defer", "gate_status": "CONCERNS", "epic_level": True, "reasons": ["roll-up"]}
    body = _trail_over(
        tmp_path,
        "# Decision log\n\n### Story 7-1: gate\n\n" + own + "### Stage 5: Epic-level gate\n\n" + _fenced(rollup),
    )
    assert {row[3] for row in rows(body)} == {shown}
    assert _source_line(body) == f"- Verdict source: {source}"


def test_a_later_cycle_with_no_readable_verdict_drops_the_earlier_one(tmp_path):
    """A later `### Story <key>: gate` heading is a later cycle: with no verdict
    object under it, the trail falls back to the gate file rather than show the
    earlier cycle's verdict as the story's. Twin of
    `test_a_later_heading_that_is_no_gate_cycle_keeps_the_recorded_verdict`:
    a reader that never drops reds here, one that drops on every heading there."""
    body = _trail_over(
        tmp_path,
        "# Decision log\n\n### Story 7-1: gate\n\n"
        + _fenced(_FAIL)
        + "### Story 7-1: gate\n\nGate: PASS, verdict advance.\n",
    )
    assert {row[3] for row in rows(body)} == {"advance"}
    assert _source_line(body) == "- Verdict source: the gate artifact's status, mapped by the gate's own table"


_DOWNGRADED = {
    "verdict": "reloop",
    "gate_status": "PASS",
    "nfr_status": "FAIL",
    "epic_level": False,
    "reasons": ["gate read from gate-decision-7-1.json", "nfr overallStatus is FAIL", "advance downgraded to reloop"],
}
_CAPPED = {
    "verdict": "reloop",
    "gate_status": "PASS",
    "sweep_scope": "scoped",
    "epic_level": False,
    "reasons": ["gate read from gate-decision-7-1.json", "sweep scope scoped: verdict capped at reloop"],
}


@pytest.mark.parametrize("recorded", [_DOWNGRADED, _CAPPED], ids=["nfr-downgrade", "sweep-cap"])
@pytest.mark.parametrize(
    "later",
    [
        "### Story 7-1: re-loop 1\n\nWork bound reached (--max-stories 1): carried over 7-1.\n",
        "### Story 7-1 re-loop 1 step 0\n\nRe-anchored on the baseline.\n",
        "#### Story 7-1 - what the re-loop owes\n\n- NFR R-001\n",
    ],
    ids=["re-loop-heading", "step-0-heading", "owed-note-heading"],
)
def test_a_later_heading_that_is_no_gate_cycle_keeps_the_recorded_verdict(tmp_path, recorded, later):
    """Only a later `### Story <key>: gate` heading is a later cycle. A re-loop's
    own heading for the same key, with no verdict object under it, dropped the
    downgraded or capped `reloop` before it, and the trail showed 7-1's `PASS`
    gate file mapped to `advance` for a story that had not advanced."""
    body = _trail_over(tmp_path, "# Decision log\n\n### Story 7-1: gate\n\n" + _fenced(recorded) + later)
    assert {row[3] for row in rows(body)} == {"reloop"}
    assert _source_line(body) == "- Verdict source: recorded in the decision log"


def test_a_later_heading_that_is_no_gate_cycle_replaces_the_verdict_with_its_own(tmp_path):
    """Guard (passes before the fix too): a heading of another shape still ends
    the cycle's entries, so a verdict object under it is the story's latest
    verdict, as gate.md says."""
    body = _trail_over(
        tmp_path,
        "# Decision log\n\n### Story 7-1: gate\n\n"
        + _fenced(_PASS)
        + "### Story 7-1: re-gate after the NFR fix\n\n"
        + _fenced(_DOWNGRADED),
    )
    assert {row[3] for row in rows(body)} == {"reloop"}
    assert _source_line(body) == "- Verdict source: recorded in the decision log"


def test_an_unchanged_later_cycle_still_reads_its_own_fenced_verdict(tmp_path):
    """Control: a log in the shape gate.md prescribes reads the last cycle."""
    heading = "### Story 7-1: gate\n\n"
    body = _trail_over(tmp_path, "# Decision log\n\n" + heading + _fenced(_PASS) + heading + _fenced(_FAIL))
    assert {row[3] for row in rows(body)} == {"reloop"}


def _read_from(gate_file: str, payload: dict) -> dict:
    return {**payload, "reasons": [f"gate read from {gate_file}", *payload["reasons"]]}


def test_a_verdict_naming_another_storys_gate_file_is_not_this_storys(tmp_path):
    """Measured on a real epic: a planning note headed `### Story 92-3b` opened a
    span nine thousand lines long, whose first verdict objects were two later
    stories' gates (`gate read from gate-decision-92-8d-...json`), and the trail
    showed one of them as the story's. 7-2's own gate file reads FAIL."""
    body = _trail_over(
        tmp_path,
        "# Decision log\n\n### Story 7-2 - scope notes before the drafting pass\n\nNotes only.\n\n"
        "### Stage 5: Gate, 7-8\n\nVerdict JSON:\n"
        + _inline(_read_from("gate-decision-7-8-...json", _PASS)).replace("gate read from ", "gate read from\n")
        + "### Stage 5: Gate, 7-9\n\n"
        + _fenced(_read_from("gate-decision-7-9-a-later-story.json", _PASS)),
        story="7-2",
    )
    assert {row[3] for row in rows(body)} == {"reloop"}
    assert _source_line(body) == "- Verdict source: the gate artifact's status, mapped by the gate's own table"


@pytest.mark.parametrize(
    "gate_file",
    ["gate-decision-7-1.json", "gate-decision-7-1-a-slug.json", "gate-decision.json", "gate-decision-...json"],
)
def test_a_verdict_naming_the_storys_own_gate_file_is_read(tmp_path, gate_file):
    """Control: the story's own file, short or slugged, and a file that names
    no story (generic, or its id elided), leave the object the story's."""
    downgraded = {**_FAIL, "verdict": "reloop", "gate_status": "PASS"}
    body = _trail_over(tmp_path, "# Decision log\n\n### Story 7-1: gate\n\n" + _fenced(_read_from(gate_file, downgraded)))
    assert {row[3] for row in rows(body)} == {"reloop"}
    assert _source_line(body) == "- Verdict source: recorded in the decision log"


# ---------------------------------------------------------------------------
# A letter-prefixed sprint key (`lp-0-1-...`) names a story as a numeric one
# does, while a heading that only starts with the word `Story` stays prose.
# ---------------------------------------------------------------------------


def test_a_letter_prefixed_key_under_the_prescribed_heading_is_read(tmp_path):
    log = tmp_path / "decision-log.md"
    log.write_text(
        "# Decision log\n\n### Story 7-1: gate\n\n"
        + _fenced(_PASS)
        + "### Story lp-7-2-a-letter-key: gate\n\n"
        + _fenced(_FAIL),
        encoding="utf-8",
    )
    assert gate_trail.recorded_verdicts(log) == {"7-1": "advance", "lp-7-2-a-letter-key": "reloop"}


def test_a_heading_naming_a_listed_letter_key_is_read(tmp_path):
    """Read only when sprint-status lists the key: unlisted, the same heading is
    prose, and its verdict stays in the previous story's entries."""
    log = tmp_path / "decision-log.md"
    log.write_text(
        "# Decision log\n\n### Story 7-1 - a numeric key\n\nGate notes only.\n\n"
        "### Story lp-7-2-a-letter-key - a letter key\n\n" + _fenced(_FAIL),
        encoding="utf-8",
    )
    assert gate_trail.recorded_verdicts(log, {"7-1", "lp-7-2-a-letter-key"}) == {"lp-7-2-a-letter-key": "reloop"}
    assert gate_trail.recorded_verdicts(log) == {"7-1": "reloop"}


def test_the_render_reads_letter_keys_from_sprint_status(tmp_path):
    """End to end. A listed key's heading is read as its story's, and the keys
    come from sprint-status.yaml, not from `--story` alone: the heading of a
    story the invocation does not render still ends the entries of the story
    before it, whose own gate logged no verdict object."""
    trace = tmp_path / "traceability"
    trace.mkdir()
    impl = tmp_path / "impl"
    impl.mkdir()
    first, second, third, fourth = (f"lp-7-{n}-story-{n}" for n in range(1, 5))
    for story in (first, third):
        (trace / f"gate-decision-{story}.json").write_text(json.dumps({"gate_status": "PASS"}), encoding="utf-8")
    _sprint(impl, {key: "done" for key in (first, second, third, fourth)})
    log = tmp_path / "decision-log.md"
    log.write_text(
        f"# Decision log\n\n### Story {first} - downgraded at its gate\n\n"
        + _fenced({**_PASS, "verdict": "reloop", "nfr_status": "FAIL"})
        + f"### Story {third} - its gate logged as prose\n\nGate: PASS, verdict advance.\n\n"
        f"### Story {fourth} - not rendered by this invocation\n\n" + _fenced(_FAIL),
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_trail(
        run_dir=run_dir,
        profile="production",
        stories=[first, third],
        impl_artifacts=impl,
        trace_output=trace,
        decision_log=log,
        repo=tmp_path,
    )
    text = (run_dir / "gate-trail.md").read_text(encoding="utf-8")
    assert {row[3] for row in rows(section(text, first))} == {"reloop"}
    assert _source_line(section(text, first)) == "- Verdict source: recorded in the decision log"
    assert {row[3] for row in rows(section(text, third))} == {"advance"}
    assert _source_line(section(text, third)) == (
        "- Verdict source: the gate artifact's status, mapped by the gate's own table"
    )


@pytest.mark.parametrize(
    "prose",
    [
        "### Story committed and re-verified",
        "### Story ORDER: one deviation from the named sequence, and why",
        "#### Story lp-7-2-a-letter-key: gate",
        "### Story line ranges in `epics.md` (for the drafting pass)",
    ],
)
def test_a_prose_heading_ends_no_storys_entries(tmp_path, prose):
    """Headings a real project's logs hold under the word `Story`. Between a
    story's heading and its verdict, each leaves the verdict the story's. The
    third is the prescribed heading at another level, for a key sprint-status
    does not list."""
    log = tmp_path / "decision-log.md"
    log.write_text(
        "# Decision log\n\n### Story 7-1: gate\n\n" + prose + "\n\n" + _fenced(_FAIL),
        encoding="utf-8",
    )
    assert gate_trail.recorded_verdicts(log, {"7-1"}) == {"7-1": "reloop"}


def _finalize_escalation_failures(text: str) -> list[str]:
    match = re.search(r"^## Gate trail\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, "finalize.md has no `## Gate trail` section"
    body = match.group(1)
    clauses = (
        "A story whose escalation is still open (`escalation-<story_id>.json` on disk, neither "
        "closed nor a handoff, beside a `sprint-status.yaml` row that is not `done`) reads "
        "`escalate` instead, gate artifact or not",
        "because the `escalate` route stops after logging the verdict it escalated from",
        "an `evidence-commit-rejected` escalation `/ucg-resolve` has not closed keeps the verdict the "
        "story advanced on (`advance`, or `defer`), whatever its row reads, and is named on its "
        "verdict-source line",
    )
    return [clause for clause in clauses if clause not in body]


def test_finalize_says_an_open_escalation_reads_escalate():
    assert _finalize_escalation_failures(FINALIZE.read_text(encoding="utf-8")) == []


def test_the_finalize_pin_reds_on_an_evidence_clause_that_names_advance_alone():
    """Twin: the clause as it read when it named `advance` alone, though the
    `defer` route advances too and its evidence commit can be rejected."""
    text = FINALIZE.read_text(encoding="utf-8")
    old = text.replace(
        "an `evidence-commit-rejected` escalation `/ucg-resolve` has not closed keeps the verdict the "
        "story advanced on (`advance`, or `defer`), whatever its row reads,",
        "an open `evidence-commit-rejected` escalation keeps the story's `advance`",
    )
    assert old != text
    assert len(_finalize_escalation_failures(old)) == 1


def test_the_finalize_pin_reds_without_the_sentence():
    """Twin: the same check over finalize.md with the sentence cut out."""
    text = FINALIZE.read_text(encoding="utf-8")
    start = text.index("A story whose escalation is still open")
    end = text.index("The production AND ran once", start)
    assert len(_finalize_escalation_failures(text[:start] + text[end:])) == 3


# ---------------------------------------------------------------------------
# The heading the trail reads a recorded verdict under is one gate.md has the
# run write. No reference named it before, and a real project's logs matched
# the reader's heading in none of 118 headings of one epic, so the reader found
# no recorded verdict at all.
# ---------------------------------------------------------------------------

_HEADING_RULE = "**Head each gate cycle's entries with the story's key.**"


def _run_the_gate(text: str) -> str:
    start = text.index("## Run the gate")
    return text[start : text.index("## Route on the verdict", start)]


def _heading_paragraph(text: str) -> str | None:
    return next((p for p in _run_the_gate(text).split("\n\n") if p.startswith(_HEADING_RULE)), None)


def _prescribed_heading(text: str) -> str | None:
    """The heading gate.md's "Run the gate" has the run write before a cycle."""
    paragraph = _heading_paragraph(text)
    if paragraph is None:
        return None
    match = re.search(r"write the heading `(#{2,4} [^`]*<story_id>[^`]*)`", paragraph)
    return match.group(1) if match else None


def _log_in_the_prescribed_shape(template: str, path: Path) -> Path:
    """Three stories logged as gate.md prescribes: a re-looped story's two
    cycles, with Execute's entries between them, then a story whose red backfill
    sweep re-looped it, then a letter-prefixed key, then the epic roll-up, which
    takes no story heading. The stories' own section headings are the shape a
    real project's logs use."""
    first, second, third = "7-2-the-slugged-key", "7-3-another-key", "lp-7-4-a-letter-key"

    def fence(payload: dict) -> str:
        return "```json\n" + json.dumps(payload) + "\n```\n\n"

    path.write_text(
        "# Decision log\n\n## Session 1\n\n### 7-2-the-slugged-key (story 1 of 3)\n\n"
        + template.replace("<story_id>", first)
        + "\n\ngate-automate: abc1234\n\n"
        + fence({"verdict": "reloop", "gate_status": "FAIL", "reasons": ["FAIL"]})
        + "#### Route: reloop\n\n#### Step 0 (re-loop)\n\n"
        + template.replace("<story_id>", first)
        + "\n\n"
        + fence({"verdict": "advance", "gate_status": "PASS", "reasons": []})
        + "### 7-3-another-key (story 2 of 3)\n\n"
        + template.replace("<story_id>", second)
        + "\n\n"
        + fence({"verdict": "reloop", "reasons": ["the backfill sweep went red"]})
        + "### lp-7-4-a-letter-key (story 3 of 3)\n\n"
        + template.replace("<story_id>", third)
        + "\n\n"
        + fence({"verdict": "defer", "gate_status": "CONCERNS", "reasons": []})
        + "### Stage 5: Epic-level gate\n\n"
        + fence({"verdict": "advance", "gate_status": "PASS", "epic_level": True}),
        encoding="utf-8",
    )
    return path


def _heading_rule_failures(text: str, tmp_path: Path) -> list[str]:
    template = _prescribed_heading(text)
    if template is None:
        return ["gate.md names no heading to write before a gate cycle"]
    failures = []
    log = _log_in_the_prescribed_shape(template, tmp_path / "prescribed-log.md")
    stories = ["7-2-the-slugged-key", "7-3-another-key", "lp-7-4-a-letter-key"]
    # No sprint-status keys: the prescribed shape alone names the letter key.
    recorded = gate_trail.resolve_recorded_verdicts(gate_trail.recorded_verdicts(log), stories)
    if recorded != {"7-2-the-slugged-key": "advance", "7-3-another-key": "reloop", "lp-7-4-a-letter-key": "defer"}:
        failures.append(f"the trail reads {recorded} from a log in the prescribed shape")
    paragraph = _heading_paragraph(text)
    for clause in (
        "with `<story_id>` the sprint-status key copied verbatim",
        "Write it again before each later cycle of the story, a re-gate included.",
        "Under it, log the cycle's verdict JSON as a fenced JSON object on lines of its own",
        "fenced or inline in backticks, and never from one carrying `\"epic_level\": true`, the Epic-level "
        "gate's roll-up",
        "or from one whose `reasons` say it read another story's gate file",
        "one whose id is a key `sprint-status.yaml` lists, so a prose heading such as `### Story order` ends none",
        "A later heading in this shape for the story replaces what an earlier one's entries recorded, even "
        "when no verdict object follows it",
        "A later heading of another shape for the story (`### Story <story_id>: re-loop 1`) is no cycle: it "
        "replaces that verdict only with a verdict object of its own",
        "never an earlier cycle's verdict",
        "never a position such as `Story 2 of 5`",
    ):
        if clause not in paragraph:
            failures.append(f"the rule does not say {clause!r}")
    return failures


def test_gate_prescribes_the_story_heading_the_trail_reads(tmp_path):
    text = GATE.read_text(encoding="utf-8")
    assert _prescribed_heading(text) == "### Story <story_id>: gate"
    assert _heading_rule_failures(text, tmp_path) == []


def test_the_heading_pin_reds_when_the_rule_is_removed_or_reshaped(tmp_path):
    """Twin: the same check reds on gate.md without the rule, and on a rule whose
    heading drops the word `Story`, the shape a real project's logs used."""
    text = GATE.read_text(encoding="utf-8")
    removed = text.replace(_heading_paragraph(text) + "\n\n", "")
    assert _heading_rule_failures(removed, tmp_path) == [
        "gate.md names no heading to write before a gate cycle"
    ]
    reshaped = text.replace("`### Story <story_id>: gate`", "`### <story_id>: gate`")
    failures = _heading_rule_failures(reshaped, tmp_path)
    assert len(failures) == 1 and failures[0].startswith("the trail reads {}"), failures


def test_the_heading_pin_reds_on_a_heading_only_a_numeric_key_survives(tmp_path):
    """Twin: without its `: gate` tail, the heading still names a numeric key,
    but a letter-prefixed key sprint-status is not asked for reads as prose."""
    text = GATE.read_text(encoding="utf-8")
    reshaped = text.replace("`### Story <story_id>: gate`", "`### Story <story_id>`")
    failures = _heading_rule_failures(reshaped, tmp_path)
    assert failures == [
        "the trail reads {'7-2-the-slugged-key': 'advance', '7-3-another-key': 'reloop'} "
        "from a log in the prescribed shape"
    ], failures


@pytest.mark.parametrize(
    "sentence",
    [
        "Under it, log the cycle's verdict JSON as a fenced JSON object on lines of its own, as a red "
        "backfill sweep logs its re-loop. ",
        "`scripts/gate_trail.py` reads the verdict the run acted on from the first JSON object carrying "
        "`verdict` after such a heading, ",
        "The heading's entries run to the next heading the trail reads as a story's: ",
        "A later heading in this shape for the story replaces what an earlier one's entries recorded, ",
        "A later heading of another shape for the story (`### Story <story_id>: re-loop 1`) is no cycle: ",
    ],
)
def test_the_heading_pin_reds_without_each_reader_sentence(tmp_path, sentence):
    """Twin: each sentence that tells the conductor how the trail reads its log
    is pinned; cutting one reds the pin."""
    text = GATE.read_text(encoding="utf-8")
    paragraph = _heading_paragraph(text)
    start = paragraph.index(sentence)
    end = paragraph.find(". ", start + len(sentence) - 2)
    cut = paragraph[:start] + paragraph[end + 2 :]
    assert cut != paragraph
    failures = _heading_rule_failures(text.replace(paragraph, cut), tmp_path)
    assert failures and all(f.startswith("the rule does not say") for f in failures), failures


# ---------------------------------------------------------------------------
# The release notes. A change fragment becomes the CHANGELOG, so the two the
# trail's fixes added say what it reads, and what it read before, no more.
# ---------------------------------------------------------------------------

_CHANGES = SCRIPTS.parents[2] / "changes"
_FRAGMENT_CLAUSES = {
    "gate-story-heading.yaml": (
        # Main read any `Story` heading with a digit-led id, at levels 2 to 4.
        "the trail found no recorded verdict for a story whose verdict JSON stood under no heading of its own "
        "reading `Story` and then an id starting with a digit",
        "A later `### Story <story_id>: gate` heading for the same story replaces what an earlier one recorded",
        "Any other later heading for the story, such as `### Story <story_id>: re-loop 1`, is no gate cycle, and "
        "replaces that verdict only with a verdict object of its own.",
    ),
    "gate-trail-open-escalation.yaml": (
        "keeps the verdict the story advanced on (`advance`, or `defer`), whatever its row reads",
    ),
}


def _fragment_failures(name: str, text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text)
    return [clause for clause in _FRAGMENT_CLAUSES[name] if clause not in flat]


@pytest.mark.parametrize("name", sorted(_FRAGMENT_CLAUSES))
def test_the_trail_fragments_say_what_the_trail_reads(name):
    assert _fragment_failures(name, (_CHANGES / name).read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("name", "claim", "replaced"),
    [
        (
            "gate-story-heading.yaml",
            "the trail found no recorded verdict for a story whose verdict JSON stood under no heading of its own "
            "reading `Story` and then an id starting with a digit",
            "a log whose stories were headed any other way gave the trail no recorded verdict at all",
        ),
        (
            "gate-story-heading.yaml",
            "A later `### Story <story_id>: gate` heading for the same story",
            "A later cycle's heading for the same story",
        ),
        (
            "gate-trail-open-escalation.yaml",
            "keeps the verdict the story advanced on (`advance`, or `defer`), whatever its row reads",
            "keeps the story's `advance`",
        ),
    ],
    ids=["no-verdict-before", "drop-on-gate-heading", "evidence-keeps-defer"],
)
def test_the_fragment_pin_reds_on_the_claim_it_replaced(name, claim, replaced):
    """Twin: each fragment with the claim it carried before reds the pin."""
    text = (_CHANGES / name).read_text(encoding="utf-8")
    assert claim in text
    assert _fragment_failures(name, text.replace(claim, replaced))
