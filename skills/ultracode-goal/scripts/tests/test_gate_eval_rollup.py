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
- one `done` row owes no gate: a decomposed parent on its split record
  (`.split-<key>.json` beside sprint-status.yaml, written by story_sizing.py
  --record) naming children each of which is another story row of the epic,
  with no chain of records back to it and no gate artifact of its own (one
  `--story <key>` would read). Its children's gates count in its place, and
  nothing but the record is read as a split.

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


SIZING = SCRIPTS / "story_sizing.py"


def _story(root: Path, *names: str) -> None:
    """Story files beside sprint-status.yaml, which the roll-up never reads."""
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Story {name}\n", encoding="utf-8")


def _split(root: Path, parent: str, *children: str) -> None:
    """The split record story_sizing.py --record writes beside sprint-status.yaml."""
    (root / f".split-{parent}.json").write_text(
        json.dumps({"parent": parent, "children": list(children)}), encoding="utf-8"
    )


def _read_through(out: dict, key: str) -> str | None:
    return next(
        (r for r in out["reasons"] if r.startswith(f"story {key}: a decomposed parent, split into ")),
        None,
    )


def _refused(out: dict, key: str) -> bool:
    return f"story {key}: gate_status NOT_EVALUATED - a done row with no resolvable gate artifact of its own" in out["reasons"]


def test_a_decomposed_parent_is_read_through_its_children(tmp_path: Path) -> None:
    """execute.md's decomposition conventions set the parent `done` and move its
    contract into child rows, and nothing ever gates it. Refusing it escalated
    every Epic that was ever split; on its split record, its children carry
    its gate."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1a", "PASS")
    _gate(trace, "7-1b", "CONCERNS")
    _gate(trace, "7-2", "PASS")
    _split(tmp_path, "7-1", "7-1a", "7-1b")
    sprint = _sprint(
        tmp_path, {"7-1a": "done", "7-1b": "done", "7-1": "done", "7-2": "done"}
    )
    out = _run(trace, sprint)
    assert out["gate_status"] == "CONCERNS", out["reasons"]
    assert out["verdict"] == "defer"
    assert set(out.keys()) == _CONTRACT_KEYS, "rollup must not grow the JSON shape"
    assert (
        "story 7-1: a decomposed parent, split into 7-1a, 7-1b (.split-7-1.json); "
        "it owes no gate of its own, and theirs count in its place"
    ) in out["reasons"]
    assert not any(r.startswith("story 7-1: gate_status") for r in out["reasons"])
    assert not any(r.startswith("story 7-1: story 7-1 has no") for r in out["reasons"]), (
        "a parent read through its children carries no resolver record"
    )
    assert (
        "roll-up over 4 stories (1 decomposed parent read through its children): "
        "worst gate_status CONCERNS"
    ) in out["reasons"]


def test_two_decomposed_parents_are_counted_in_the_summary(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    for story in ("7-1a", "7-1b", "7-2a"):
        _gate(trace, story, "PASS")
    _split(tmp_path, "7-1", "7-1a", "7-1b")
    _split(tmp_path, "7-2", "7-2a")
    sprint = _sprint(
        tmp_path,
        {"7-1a": "done", "7-1b": "done", "7-1": "done", "7-2a": "done", "7-2": "done"},
    )
    out = _run(trace, sprint)
    assert out["gate_status"] == "PASS", out["reasons"]
    assert (
        "roll-up over 5 stories (2 decomposed parents read through their children): "
        "worst gate_status PASS"
    ) in out["reasons"]


def test_slugged_keys_are_read_by_their_sprint_status_key(tmp_path: Path) -> None:
    """The shape a consumer's project shipped: `95-0-a-i/ii/iii` above the
    `95-0-a` parent, every key carrying its title slug, the record named for
    the parent's key byte for byte."""
    trace = tmp_path / "trace"
    children = ("7-0-a-i-the-spine", "7-0-a-ii-the-inputs", "7-0-a-iii-the-gate")
    for story in children:
        _gate(trace, story, "PASS")
    _split(tmp_path, "7-0-a-audit-the-substrate", *children)
    rows = {story: "done" for story in children}
    rows["7-0-a-audit-the-substrate"] = "done"
    out = _run(trace, _sprint(tmp_path, rows))
    assert out["gate_status"] == "PASS", out["reasons"]
    reason = _read_through(out, "7-0-a-audit-the-substrate")
    assert reason is not None and ", ".join(children) in reason, out["reasons"]


def test_a_decomposed_parent_never_masks_its_children(tmp_path: Path) -> None:
    """Read through, not waved through: a child's FAIL is the epic's, and a
    child with no gate of its own still refuses the roll-up."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1a", "FAIL")
    _gate(trace, "7-2", "PASS")
    _split(tmp_path, "7-1", "7-1a", "7-1b")
    rows = {"7-1a": "done", "7-1b": "done", "7-1": "done", "7-2": "done"}
    out = _run(trace, _sprint(tmp_path, rows))
    assert out["gate_status"] == "NOT_EVALUATED", out["reasons"]
    assert _refused(out, "7-1b"), out["reasons"]
    _gate(trace, "7-1b", "PASS")
    out = _run(trace, _sprint(tmp_path, rows))
    assert out["gate_status"] == "FAIL", out["reasons"]
    assert out["verdict"] == "reloop"


def test_without_a_record_no_shape_reads_as_a_split(tmp_path: Path) -> None:
    """Nothing but the record is evidence of a split. Each layout here waived a
    never-gated row's gate under an earlier reading of the row's id, place or
    story files: the conventions' own shape with no record, a lettered story
    placed above a hand-finished row, and that story with its file named the
    way bmad-build names a spec. Each now refuses, with a pointer at the record."""
    layouts = {
        "conventions": (["7-1"], {"7-1a": "done", "7-1b": "done", "7-1": "done"}, ("7-1a", "7-1b"), "7-1"),
        "placed": (
            ["7-1-the-login.md", "7-2a-the-prereq.md", "7-2-the-dashboard.md"],
            {"7-1-the-login": "done", "7-2a-the-prereq": "done", "7-2-the-dashboard": "done"},
            ("7-1-the-login", "7-2a-the-prereq"),
            "7-2-the-dashboard",
        ),
        "spec-named": (
            ["7-1-the-login.md", "spec-7-2a-the-prereq.md", "7-2-the-dashboard.md"],
            {"7-1-the-login": "done", "7-2a-the-prereq": "done", "7-2-the-dashboard": "done"},
            ("7-1-the-login", "7-2a-the-prereq"),
            "7-2-the-dashboard",
        ),
    }
    for name, (files, rows, gated, ungated) in layouts.items():
        base = tmp_path / name
        base.mkdir()
        trace = base / "trace"
        for story in gated:
            _gate(trace, story, "PASS")
        _story(base, *[f if f.endswith(".md") else f + ".md" for f in files])
        out = _run(trace, _sprint(base, rows))
        assert out["gate_status"] == "NOT_EVALUATED", (name, out["reasons"])
        assert _refused(out, ungated), (name, out["reasons"])
        assert _read_through(out, ungated) is None, (name, out["reasons"])
        assert any(
            r.startswith(f"story {ungated}: rows above it extend its id (")
            and f"story_sizing.py --parent {ungated} --record" in r
            for r in out["reasons"]
        ), (name, out["reasons"])


def test_the_record_is_read_by_the_rows_exact_key(tmp_path: Path) -> None:
    """A record under the bare id is not the slugged row's, and one in the
    trace directory is not beside sprint-status.yaml."""
    for name, where, parent in (
        ("bare-id", "", "7-1"),
        ("trace-dir", "trace", "7-1-the-login"),
    ):
        base = tmp_path / name
        base.mkdir()
        trace = base / "trace"
        _gate(trace, "7-1a", "PASS")
        _split(base / where if where else base, parent, "7-1a")
        out = _run(trace, _sprint(base, {"7-1a": "done", "7-1-the-login": "done"}))
        assert out["gate_status"] == "NOT_EVALUATED", (name, out["reasons"])
        assert _refused(out, "7-1-the-login"), (name, out["reasons"])


def test_the_record_decides_whatever_the_rows_order(tmp_path: Path) -> None:
    """The driver needs children above the parent; the gate reads the record."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1a", "PASS")
    _split(tmp_path, "7-1", "7-1a")
    out = _run(trace, _sprint(tmp_path, {"7-1": "done", "7-1a": "done"}))
    assert out["gate_status"] == "PASS", out["reasons"]
    assert _read_through(out, "7-1") is not None


def test_a_record_naming_a_row_the_epic_lacks_is_not_read(tmp_path: Path) -> None:
    """Every child the record names must be another story row of this epic:
    a missing row, a row of another epic, or the parent itself means the
    record is not the split sprint-status shows."""
    for name, children in (
        ("missing", ("7-1a", "7-1c")),
        ("other-epic", ("7-1a", "17-1a")),
        ("itself", ("7-1a", "7-1")),
    ):
        base = tmp_path / name
        base.mkdir()
        trace = base / "trace"
        _gate(trace, "7-1a", "PASS")
        _gate(trace, "17-1a", "PASS")
        _split(base, "7-1", *children)
        out = _run(trace, _sprint(base, {"7-1a": "done", "7-1": "done", "17-1a": "done"}))
        assert out["gate_status"] == "NOT_EVALUATED", (name, out["reasons"])
        assert _refused(out, "7-1"), (name, out["reasons"])
        stray = children[1]
        assert (
            f"story 7-1: .split-7-1.json names {stray}, not another story row of "
            "epic 7, so it is not read"
        ) in out["reasons"], (name, out["reasons"])


def test_a_malformed_record_is_not_read(tmp_path: Path) -> None:
    for name, content in {
        "not-json": "{",
        "array": json.dumps(["7-1a"]),
        "other-parent": json.dumps({"parent": "7-2", "children": ["7-1a"]}),
        "no-children": json.dumps({"parent": "7-1"}),
        "empty-children": json.dumps({"parent": "7-1", "children": []}),
        "children-not-a-list": json.dumps({"parent": "7-1", "children": "7-1a"}),
        "child-not-a-string": json.dumps({"parent": "7-1", "children": ["7-1a", 3]}),
        "child-empty": json.dumps({"parent": "7-1", "children": ["7-1a", ""]}),
        "no-parent": json.dumps({"children": ["7-1a"]}),
    }.items():
        base = tmp_path / name
        base.mkdir()
        trace = base / "trace"
        _gate(trace, "7-1a", "PASS")
        (base / ".split-7-1.json").write_text(content, encoding="utf-8")
        out = _run(trace, _sprint(base, {"7-1a": "done", "7-1": "done"}))
        assert out["gate_status"] == "NOT_EVALUATED", (name, out["reasons"])
        assert (
            "story 7-1: .split-7-1.json is not a split record of 7-1 (parent and "
            "children), so it is not read"
        ) in out["reasons"], (name, out["reasons"])
        assert _refused(out, "7-1"), name


def test_a_decomposed_parent_with_its_own_gate_is_read_like_any_story(
    tmp_path: Path,
) -> None:
    """A gate of its own is a record, and the roll-up keeps every record."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1a", "PASS")
    _gate(trace, "7-1", "FAIL")
    _split(tmp_path, "7-1", "7-1a")
    sprint = _sprint(tmp_path, {"7-1a": "done", "7-1": "done"})
    out = _run(trace, sprint)
    assert out["gate_status"] == "FAIL", out["reasons"]
    assert "story 7-1: gate_status FAIL" in out["reasons"]
    assert not any("decomposed parent" in r for r in out["reasons"])


def _owned_case(base: Path, name: str, content: str = "x\n") -> dict:
    """7-1-the-login split into 7-1a, on its record, plus one more trace-dir file.

    `base` is a fresh directory per case, numbered rather than named after the
    file, so names that differ only in case never share one on a filesystem
    that ignores case.
    """
    base.mkdir()
    trace = base / "trace"
    _gate(trace, "7-1a-the-first", "PASS")
    target = trace / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _split(base, "7-1-the-login", "7-1a-the-first")
    return _run(trace, _sprint(base, {"7-1a-the-first": "done", "7-1-the-login": "done"}))


_TRACE_REPORT = "---\nworkflowType: testarch-trace\n---\n"


def test_each_gate_artifact_of_the_parents_own_still_refuses(tmp_path: Path) -> None:
    """A gate artifact the per-story resolver finds as the parent's own (a
    declared trace report named for its key, under any prefix, separator or
    leading dot; its gate decision; its trace summary) means it was gated on
    its own, so it must resolve like any story, whatever its record says."""
    hinted = "---\nworkflowType: testarch-trace\ngateDecisionFile: archive/gate-decision-7-1-the-login.json\n---\n"
    cases = {
        "trace-7-1-the-login.md": _TRACE_REPORT,
        "trace-7_1_the_login.md": _TRACE_REPORT,
        "Trace-Final-7-1-the-login.md": _TRACE_REPORT,
        "atdd-trace-7-1-the-login.md": _TRACE_REPORT,
        ".trace-7-1-the-login.md": hinted,
        "gate-decision-7-1-the-login.json": "{",
        "gate-decision-7.1.the.login.json": "{",
        "e2e-trace-summary-7-1-the-login.json": "{}",
        "e2e-trace-summary-7_1_the_login.json": "{}",
    }
    for index, (name, content) in enumerate(cases.items()):
        base = tmp_path / f"case-{index}"
        out = _owned_case(base, name, content)
        assert out["gate_status"] == "NOT_EVALUATED", (name, out["reasons"])
        assert (
            "story 7-1-the-login: a decomposed parent (7-1a-the-first), but %s in "
            "%s is a gate artifact of its own, so its own gate must resolve"
            % (name, base / "trace")
        ) in out["reasons"], (name, out["reasons"])
        assert _refused(out, "7-1-the-login"), (name, "an owned parent is then read like any story")
        assert not any("rows above it extend its id" in r for r in out["reasons"]), name
        assert not any("read through" in r for r in out["reasons"]), name
    out = _owned_case(tmp_path / "hint", ".trace-7-1-the-login.md", hinted)
    assert any(
        r.startswith("story 7-1-the-login: .trace-7-1-the-login.md hints at ") for r in out["reasons"]
    ), ("the refused hint is surfaced like any story's", out["reasons"])


def test_no_pointer_for_a_row_with_a_gate_artifact_of_its_own(tmp_path: Path) -> None:
    """The pointer names the record as the way out, which it is not for a row
    that has a gate of its own: a record would still leave that gate to
    resolve."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1a", "PASS")
    (trace / "trace-7-1.md").write_text(_TRACE_REPORT, encoding="utf-8")
    out = _run(trace, _sprint(tmp_path, {"7-1a": "done", "7-1": "done"}))
    assert out["gate_status"] == "NOT_EVALUATED", out["reasons"]
    assert _refused(out, "7-1"), out["reasons"]
    assert not any("rows above it extend its id" in r for r in out["reasons"]), out["reasons"]


def test_files_the_resolver_never_reads_as_the_parents_are_no_gate(tmp_path: Path) -> None:
    """The identity is the key, as for every per-story gate: the parent's
    story file, its ATDD checklist (Define-Done writes one before Execute
    sizes the row), notes, NFR and review files, a report that does not
    declare itself a trace report, one under the bare id of a slugged key,
    one in a subdirectory, and a gate decision not named `.json` are not its
    gate, so its record is read."""
    cases = {
        "atdd-checklist-7-1-the-login.md": "x\n",
        "7-1-the-login.md": "# Story 7-1\n",
        "notes-7-1-the-login.md": "x\n",
        "nfr-assessment-7-1-the-login.md": "x\n",
        "test-review-7-1-the-login.md": "x\n",
        "trace-7-1-the-login.md": "x\n",
        "trace-7-1.md": _TRACE_REPORT,
        "archive/trace-7-1-the-login.md": _TRACE_REPORT,
        "gate-decision-7-1-the-login.yaml": "gate_status: FAIL\n",
    }
    for index, (name, content) in enumerate(cases.items()):
        out = _owned_case(tmp_path / f"case-{index}", name, content)
        assert out["gate_status"] == "PASS", (name, out["reasons"])
        assert _read_through(out, "7-1-the-login") is not None, (name, out["reasons"])


def test_a_key_whose_title_starts_like_a_child_is_read_by_its_key(tmp_path: Path) -> None:
    """`7-1-a-new-flow` reads as id 7-1-a, but ownership asks the resolver,
    which matches the key: its own trace report counts, its child's does not."""
    for index, own in enumerate((False, True)):
        base = tmp_path / f"case-{index}"
        base.mkdir()
        trace = base / "trace"
        _gate(trace, "7-1a", "PASS")
        if own:
            (trace / "trace-7-1-a-new-flow.md").write_text(_TRACE_REPORT, encoding="utf-8")
        _split(base, "7-1-a-new-flow", "7-1a")
        out = _run(trace, _sprint(base, {"7-1a": "done", "7-1-a-new-flow": "done"}))
        assert out["gate_status"] == ("NOT_EVALUATED" if own else "PASS"), (own, out["reasons"])
        assert (_read_through(out, "7-1-a-new-flow") is None) is own, (own, out["reasons"])


def test_a_dotted_split_is_read_like_any_other(tmp_path: Path) -> None:
    """Dotted keys have no id stem, and their children's files are theirs."""
    trace = tmp_path / "trace"
    _gate(trace, "7.1.1", "PASS")
    _gate(trace, "7.1.2", "PASS")
    _split(tmp_path, "7.1", "7.1.1", "7.1.2")
    out = _run(trace, _sprint(tmp_path, {"7.1.1": "done", "7.1.2": "done", "7.1": "done"}))
    assert out["gate_status"] == "PASS", out["reasons"]
    assert _read_through(out, "7.1") is not None, out["reasons"]


def test_the_record_is_no_file_of_the_parents_own(tmp_path: Path) -> None:
    """When one directory holds sprint-status.yaml, the record, the parent's
    story file and the gates, neither the record nor the story file is read
    as a gate of the parent's own."""
    _gate(tmp_path, "7-1a-the-first", "PASS")
    _split(tmp_path, "7-1-the-login", "7-1a-the-first")
    _story(tmp_path, "7-1-the-login.md")
    out = _run(tmp_path, _sprint(tmp_path, {"7-1a-the-first": "done", "7-1-the-login": "done"}))
    assert out["gate_status"] == "PASS", out["reasons"]
    assert _read_through(out, "7-1-the-login") is not None, out["reasons"]


def test_a_parent_with_no_id_stem_owns_only_its_own_files(tmp_path: Path) -> None:
    """A key with no id stem is matched by the resolver's key rule like any
    other: `trace-7-x-spike-a` is its child's, not 7-x-spike's, so the
    recorded split is read through."""
    trace = tmp_path / "trace"
    _gate(trace, "7-x-spike-a", "PASS")
    _gate(trace, "7-2", "PASS")
    _split(tmp_path, "7-x-spike", "7-x-spike-a")
    rows = {"7-x-spike-a": "done", "7-x-spike": "done", "7-2": "done"}
    out = _run(trace, _sprint(tmp_path, rows))
    assert out["gate_status"] == "PASS", out["reasons"]
    assert _read_through(out, "7-x-spike") is not None, out["reasons"]


def test_records_that_lead_back_to_their_parent_are_not_read(tmp_path: Path) -> None:
    """Two records naming each other, written by two reconciling runs, would
    leave out both rows and compute a PASS over no gate at all. A record
    whose chain of children returns to its parent is not read, so each row
    in the cycle is read like any story; a record pointing into the cycle
    from outside is still read, and the cycle's rows still refuse."""
    cases = {
        "pair": ({"7-1": ("7-1a",), "7-1a": ("7-1",)}, {"7-1": "done", "7-1a": "done"}, (), ()),
        "beside-a-gated-row": (
            {"7-1": ("7-2",), "7-2": ("7-1",)},
            {"7-1": "done", "7-2": "done", "7-3": "done"},
            ("7-3",),
            (),
        ),
        "fed-from-outside": (
            {"7-1": ("7-2",), "7-2": ("7-3",), "7-3": ("7-1",), "7-4": ("7-1",)},
            {"7-1": "done", "7-2": "done", "7-3": "done", "7-4": "done", "7-5": "done"},
            ("7-5",),
            ("7-4",),
        ),
    }
    for index, (name, (records, rows, gated, read)) in enumerate(cases.items()):
        base = tmp_path / f"case-{index}"
        base.mkdir()
        trace = base / "trace"
        trace.mkdir()
        (trace / "atdd-checklist-7-9.md").write_text("x\n", encoding="utf-8")
        for story in gated:
            _gate(trace, story, "PASS")
        for parent, children in records.items():
            _split(base, parent, *children)
        out = _run(trace, _sprint(base, rows))
        assert out["gate_status"] == "NOT_EVALUATED", (name, out["reasons"])
        assert out["verdict"] == "escalate", name
        for parent in records:
            if parent in read:
                assert _read_through(out, parent) is not None, (name, parent, out["reasons"])
            else:
                assert _read_through(out, parent) is None, (name, parent, out["reasons"])
                assert _refused(out, parent), (name, parent, out["reasons"])
    out_pair = _run(tmp_path / "case-0" / "trace", tmp_path / "case-0" / "sprint-status.yaml")
    assert (
        "story 7-1: its split record leads back to it (7-1 -> 7-1a -> 7-1), so it is not read"
    ) in out_pair["reasons"], out_pair["reasons"]
    assert (
        "story 7-1a: its split record leads back to it (7-1a -> 7-1 -> 7-1a), so it is not read"
    ) in out_pair["reasons"], out_pair["reasons"]


def test_a_childs_artifacts_are_not_the_parents(tmp_path: Path) -> None:
    """Ownership asks the resolver, which matches the full key: `trace-7-1a-...`
    and `gate-decision-7-1-a-...` are the children's files, not 7-1's."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1a-the-first", "PASS")
    _gate(trace, "7-1-a-the-second", "PASS")
    _split(tmp_path, "7-1-the-login", "7-1a-the-first", "7-1-a-the-second")
    sprint = _sprint(
        tmp_path,
        {"7-1a-the-first": "done", "7-1-a-the-second": "done", "7-1-the-login": "done"},
    )
    out = _run(trace, sprint)
    assert out["gate_status"] == "PASS", out["reasons"]


def test_nested_decomposed_parents_are_each_read_through(tmp_path: Path) -> None:
    """A child split again has its own record: both levels are read through."""
    trace = tmp_path / "trace"
    for story in ("7-1-a-i", "7-1-a-ii", "7-1-b"):
        _gate(trace, story, "PASS")
    _split(tmp_path, "7-1-a", "7-1-a-i", "7-1-a-ii")
    _split(tmp_path, "7-1", "7-1-a", "7-1-b")
    rows = {"7-1-a-i": "done", "7-1-a-ii": "done", "7-1-a": "done", "7-1-b": "done", "7-1": "done"}
    out = _run(trace, _sprint(tmp_path, rows))
    assert out["gate_status"] == "PASS", out["reasons"]
    assert _read_through(out, "7-1-a") is not None, out["reasons"]
    assert _read_through(out, "7-1") is not None, out["reasons"]
    assert (
        "roll-up over 5 stories (2 decomposed parents read through their children): "
        "worst gate_status PASS"
    ) in out["reasons"]


def test_an_ancestors_own_gate_is_not_a_nested_parents(tmp_path: Path) -> None:
    """7-1's own gate files have stem 7-1, not 7-1-a, so the nested parent
    7-1-a is still read through its child."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1-a-i", "PASS")
    _gate(trace, "7-1", "PASS")
    _split(tmp_path, "7-1-a", "7-1-a-i")
    rows = {"7-1-a-i": "done", "7-1-a": "done", "7-1": "done"}
    out = _run(trace, _sprint(tmp_path, rows))
    assert out["gate_status"] == "PASS", out["reasons"]
    assert _read_through(out, "7-1-a") is not None, out["reasons"]
    assert "story 7-1: gate_status PASS" in out["reasons"]


def test_the_pointer_names_every_extension_above_the_first_row_of_the_id(
    tmp_path: Path,
) -> None:
    """The pointer is a reason line only. It names grandchildren too, stops at
    the first row of the id, and names nothing that extends another id
    (`7-10` and `7-2a` are not 7-1's)."""
    trace = tmp_path / "trace"
    for story in ("7-1-a-i", "7-10", "7-2a", "7-1b", "7-3a", "7-3"):
        _gate(trace, story, "PASS")
    rows = {
        "7-1-a-i": "done",
        "7-10": "done",
        "7-2a": "done",
        "7-1-the-login": "done",
        "7-1b": "done",
        "7-1-the-logout": "done",
        "7-2": "done",
        "7-3a": "done",
        "7-3": "done",
    }
    out = _run(trace, _sprint(tmp_path, rows))
    pointers = [r for r in out["reasons"] if "rows above it extend its id" in r]
    assert any(r.startswith("story 7-1-the-login: rows above it extend its id (7-1-a-i) ") for r in pointers), pointers
    assert any(r.startswith("story 7-2: rows above it extend its id (7-2a) ") for r in pointers), pointers
    assert any(r.startswith("story 7-1-the-logout: rows above it extend its id (7-1-a-i) ") for r in pointers), (
        "the logout row shares id 7-1, so it reads from the id's first row; 7-1b below it is not named"
    )
    assert not any("7-1b" in r for r in pointers), pointers
    assert not any(r.startswith("story 7-3:") for r in pointers), (
        "7-3 has a gate of its own, so it owes no pointer"
    )
    assert len(pointers) == 3, pointers


def test_keys_with_no_id_stem_neither_crash_nor_split(tmp_path: Path) -> None:
    """A dotted key and a key with no story number are story rows the readers
    accept; they have no id stem, so an ungated one gets no pointer, and the
    roll-up reads them as plain stories beside a real split."""
    trace = tmp_path / "trace"
    for story in ("7.1", "7-x-spike", "7-2a"):
        _gate(trace, story, "PASS")
    _split(tmp_path, "7-2", "7-2a")
    sprint = _sprint(
        tmp_path,
        {"7-2a": "done", "7-y-notes": "done", "7.1": "done", "7-x-spike": "done", "7-2": "done"},
    )
    out = _run(trace, sprint)
    assert out["gate_status"] == "NOT_EVALUATED", out["reasons"]
    assert _refused(out, "7-y-notes"), out["reasons"]
    assert not any(r.startswith("story 7-y-notes: rows above") for r in out["reasons"])
    assert _read_through(out, "7-2") is not None, out["reasons"]


def test_story_sizing_writes_the_record_the_roll_up_reads(tmp_path: Path) -> None:
    """End to end: the reconciling story_sizing.py run writes the record, and a
    failing one writes none, so its parent still refuses."""
    trace = tmp_path / "trace"
    _gate(trace, "7-1a", "PASS")
    _gate(trace, "7-1b", "PASS")
    rows = {"7-1a": "done", "7-1b": "done", "7-1": "done"}

    def size(*claims: str) -> int:
        argv = [sys.executable, str(SIZING), "--parent", "7-1", "--record", str(tmp_path), "--parent-acs", "1 2 3"]
        for claim in claims:
            argv += ["--child", claim]
        return subprocess.run(argv, capture_output=True, text=True).returncode

    assert size("7-1a=1,2", "7-1b=2") == 1
    assert not (tmp_path / ".split-7-1.json").exists()
    out = _run(trace, _sprint(tmp_path, rows))
    assert out["gate_status"] == "NOT_EVALUATED", out["reasons"]

    assert size("7-1a=1,2", "7-1b=3") == 0
    out = _run(trace, _sprint(tmp_path, rows))
    assert out["gate_status"] == "PASS", out["reasons"]
    assert (
        "story 7-1: a decomposed parent, split into 7-1a, 7-1b (.split-7-1.json); "
        "it owes no gate of its own, and theirs count in its place"
    ) in out["reasons"]


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
