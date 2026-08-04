#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""`gate_eval.py --rollup`: the epic verdict as a computation, not a summary.

The epic-level gate used to rest on a single epic-named artifact whose content
was, on the hand-authored path, prose the run wrote about itself. `--rollup`
replaces that with a fail-closed aggregate over the per-story record:

- the story set is read from sprint-status.yaml, never a caller-typed list —
  a story omitted from a typed list would simply not be aggregated, which is
  the fabrication channel the flag exists to close;
- the aggregate is the WORST per-story gate_status;
- five refusals, all NOT_EVALUATED -> escalate: unreadable sprint-status, an
  epic with no stories, any story not `done`, a multi-story epic in a
  generically-named trace dir (one shared artifact cannot decide N stories),
  and any `done` story whose own gate artifact does not resolve (a `done` row
  nothing gated is surfaced, not papered over).

The flag is additive: unchanged invocations return unchanged verdicts, and the
printed JSON's key set is exactly the shape STABILITY.md enumerates — the
per-story detail rides in `reasons`, whose wording is explicitly
non-contractual.

Run: uv run --with pytest pytest scripts/tests/test_gate_eval_rollup.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS / "gate_eval.py"

# The consumable key set (docs/_internal/STABILITY.md). --rollup must not grow it.
_CONTRACT_KEYS = {
    "verdict",
    "gate_status",
    "p0_status",
    "p1_status",
    "overall_status",
    "nfr_status",
    "review_score",
    "epic_level",
    "reasons",
}


def _sprint(tmp_path: Path, rows: dict[str, str]) -> Path:
    lines = ["development_status:"]
    lines += [f"  {key}: {status}" for key, status in rows.items()]
    path = tmp_path / "sprint-status.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _gate(trace: Path, story: str, status: str) -> None:
    trace.mkdir(exist_ok=True)
    (trace / f"trace-{story}.md").write_text(
        f"---\nworkflowType: testarch-trace\ngateDecisionFile: gate-decision-{story}.json\n---\n",
        encoding="utf-8",
    )
    (trace / f"gate-decision-{story}.json").write_text(
        json.dumps(
            {
                "gate_status": status,
                "p0_status": "MET",
                "p1_status": "MET",
                "overall_status": "MET",
            }
        ),
        encoding="utf-8",
    )


def _run(
    trace: Path, sprint: Path, epic: str = "7", *extra: str, expect_code: int = 0
) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--trace-output",
            str(trace),
            "--profile",
            "production",
            "--story",
            epic,
            "--epic-level",
            "--rollup",
            "--sprint-status",
            str(sprint),
            *extra,
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == expect_code, proc.stderr or proc.stdout
    return json.loads(proc.stdout)


def test_all_done_all_pass_rolls_up_to_advance(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    for story in ("7-1", "7-2", "7-3"):
        _gate(trace, story, "PASS")
    sprint = _sprint(tmp_path, {"7-1": "done", "7-2": "done", "7-3": "done"})
    out = _run(trace, sprint)
    assert out["gate_status"] == "PASS"
    assert out["verdict"] == "advance"
    assert out["epic_level"] is True
    assert set(out.keys()) == _CONTRACT_KEYS, "rollup must not grow the JSON shape"
    for story in ("7-1", "7-2", "7-3"):
        assert any(f"story {story}:" in r for r in out["reasons"])


def test_the_aggregate_is_the_worst_story_status(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _gate(trace, "7-1", "PASS")
    _gate(trace, "7-2", "CONCERNS")
    _gate(trace, "7-3", "WAIVED")
    sprint = _sprint(tmp_path, {"7-1": "done", "7-2": "done", "7-3": "done"})
    out = _run(trace, sprint)
    assert out["gate_status"] == "CONCERNS"
    assert out["verdict"] == "defer"


def test_a_fail_story_rolls_up_to_fail_and_reloop(tmp_path: Path) -> None:
    """FAIL outranks CONCERNS; the aggregate maps through the gate's own table."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1", "CONCERNS")
    _gate(trace, "7-2", "FAIL")
    _gate(trace, "7-3", "PASS")
    sprint = _sprint(tmp_path, {"7-1": "done", "7-2": "done", "7-3": "done"})
    out = _run(trace, sprint)
    assert out["gate_status"] == "FAIL"
    assert out["verdict"] == "reloop"


def test_a_generic_named_dir_refuses_a_multi_story_rollup(tmp_path: Path) -> None:
    """One shared artifact cannot decide N stories: without per-story naming
    the unscoped fallback would hand the same gate-decision.json to every
    story, and a one-artifact epic would advance with per-story reason lines
    the directory cannot support."""
    trace = tmp_path / "trace"
    trace.mkdir()
    (trace / "trace.md").write_text(
        "---\nworkflowType: testarch-trace\ngateDecisionFile: gate-decision.json\n---\n",
        encoding="utf-8",
    )
    (trace / "gate-decision.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )
    sprint = _sprint(tmp_path, {"7-1": "done", "7-2": "done"})
    out = _run(trace, sprint)
    assert out["gate_status"] == "NOT_EVALUATED"
    assert out["verdict"] == "escalate"
    assert any("not per-story-named" in r for r in out["reasons"])


def test_a_single_story_epic_may_live_in_a_generic_dir(tmp_path: Path) -> None:
    """gate_eval's documented isolated-dir rule survives: one story, one
    generically-named artifact set, resolved as that story's own."""
    trace = tmp_path / "trace"
    trace.mkdir()
    (trace / "trace.md").write_text(
        "---\nworkflowType: testarch-trace\ngateDecisionFile: gate-decision.json\n---\n",
        encoding="utf-8",
    )
    (trace / "gate-decision.json").write_text(
        json.dumps({"gate_status": "PASS"}), encoding="utf-8"
    )
    sprint = _sprint(tmp_path, {"7-1": "done"})
    out = _run(trace, sprint)
    assert out["gate_status"] == "PASS"
    assert out["verdict"] == "advance"


def test_a_failing_storys_resolution_record_is_surfaced(tmp_path: Path) -> None:
    """The aggregation must not drop the resolver's own record of which file
    decided a non-PASS story - the trail has to agree with the gate."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1", "PASS")
    _gate(trace, "7-2", "FAIL")
    sprint = _sprint(tmp_path, {"7-1": "done", "7-2": "done"})
    out = _run(trace, sprint)
    assert any(
        r.startswith("story 7-2: ") and "gate-decision-7-2.json" in r
        for r in out["reasons"]
    ), out["reasons"]


def test_a_sibling_map_after_development_status_is_not_swallowed(tmp_path: Path) -> None:
    """The block ends at the key's own indentation: a sibling map (an archive,
    say) must not inject phantom rows - a duplicate key there overwrote a real
    not-done row last-wins, which is a wrong-verdict channel, not a refusal."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1", "PASS")
    path = tmp_path / "sprint-status.yaml"
    path.write_text(
        "sprint:\n"
        "  development_status:\n"
        "    7-1: in-progress\n"
        "  archive:\n"
        "    7-1: done\n",
        encoding="utf-8",
    )
    out = _run(trace, path)
    assert out["gate_status"] == "NOT_EVALUATED"
    assert any("not done" in r for r in out["reasons"]), (
        "the archive's done row must not overwrite the real in-progress row"
    )


def test_a_not_done_story_refuses_the_rollup(tmp_path: Path) -> None:
    """The roll-up's own trigger is every-story-done; early is refused, not
    answered — which is also how the partial-by-design exception is enforced
    mechanically if someone runs the roll-up against a deliberate subset."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1", "PASS")
    sprint = _sprint(tmp_path, {"7-1": "done", "7-2": "in-progress"})
    out = _run(trace, sprint)
    assert out["gate_status"] == "NOT_EVALUATED"
    assert out["verdict"] == "escalate"
    assert any("not done" in r and "7-2" in r for r in out["reasons"])


def test_a_done_story_with_no_artifacts_refuses_the_rollup(tmp_path: Path) -> None:
    """The done-without-gate-artifacts audit, made binding at the epic gate."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1", "PASS")
    # 7-2 is done in the sprint file but wrote nothing to the trace dir.
    sprint = _sprint(tmp_path, {"7-1": "done", "7-2": "done"})
    out = _run(trace, sprint)
    assert out["gate_status"] == "NOT_EVALUATED"
    assert out["verdict"] == "escalate"
    assert any(
        "7-2" in r and "no resolvable gate artifact" in r for r in out["reasons"]
    )


def test_unreadable_sprint_status_refuses(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _gate(trace, "7-1", "PASS")
    out = _run(trace, tmp_path / "missing.yaml")
    assert out["gate_status"] == "NOT_EVALUATED"
    assert out["verdict"] == "escalate"
    assert any("unreadable" in r for r in out["reasons"])


def test_an_epic_with_no_stories_refuses(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    trace.mkdir()
    sprint = _sprint(tmp_path, {"9-1": "done"})
    out = _run(trace, sprint, "7")
    assert out["gate_status"] == "NOT_EVALUATED"
    assert any("no stories for epic 7" in r for r in out["reasons"])


def test_story_grouping_is_numeric_prefix_exact(tmp_path: Path) -> None:
    """Epic 7 owns 7-1, never 17-1 or 70-1: grouping mirrors the rollup reader."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1", "PASS")
    _gate(trace, "17-1", "FAIL")
    sprint = _sprint(tmp_path, {"7-1": "done", "17-1": "done"})
    out = _run(trace, sprint)
    assert out["gate_status"] == "PASS"
    assert not any("17-1" in r for r in out["reasons"])


def test_rollup_requires_its_three_companions(tmp_path: Path) -> None:
    """--rollup without --epic-level / --story / --sprint-status is the
    invocation-error lane: exit 2, nothing evaluated."""
    trace = tmp_path / "trace"
    trace.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--trace-output",
            str(trace),
            "--profile",
            "production",
            "--rollup",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "--rollup" in proc.stderr


def test_a_partially_supplied_companion_set_is_refused(tmp_path: Path) -> None:
    """Each missing companion alone must refuse: an and-to-or mutant passes
    the all-absent case and dies here."""
    trace = tmp_path / "trace"
    trace.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--trace-output",
            str(trace),
            "--profile",
            "production",
            "--story",
            "7",
            "--epic-level",
            "--rollup",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "--sprint-status" in proc.stderr or "--rollup" in proc.stderr


def test_sprint_status_without_rollup_is_refused(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    trace.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--trace-output",
            str(trace),
            "--profile",
            "light",
            "--sprint-status",
            str(tmp_path / "s.yaml"),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "--sprint-status" in proc.stderr


def test_unchanged_epic_level_invocation_still_reads_the_epic_artifact(
    tmp_path: Path,
) -> None:
    """Additivity: without --rollup the file-based epic read is byte-identical
    in behavior — the epic's own artifact decides."""
    trace = tmp_path / "trace"
    _gate(trace, "7", "PASS")
    _gate(trace, "7-1", "FAIL")
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--trace-output",
            str(trace),
            "--profile",
            "production",
            "--story",
            "7",
            "--epic-level",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["gate_status"] == "PASS", "the epic artifact, not the rollup, decides"


def test_gate_md_documents_the_rollup_invocation() -> None:
    gate_md = (SCRIPTS.parent / "references" / "gate.md").read_text(encoding="utf-8")
    fenced = [ln.strip() for ln in gate_md.splitlines() if ln.strip().startswith("uv run ")]
    epic_cmd = next((ln for ln in fenced if "--epic-level" in ln), None)
    assert epic_cmd, "gate.md no longer shows an epic-level invocation"
    assert "--rollup" in epic_cmd and "--sprint-status" in epic_cmd
    assert "partial-by-design exception below binds `--rollup` unchanged" in gate_md
