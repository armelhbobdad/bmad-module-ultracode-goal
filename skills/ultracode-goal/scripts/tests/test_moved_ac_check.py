#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""moved_ac_check.py: does TEA's trace still score an AC the operator moved out?

The field case (#222): an `operator-evidence-owed` escalation closed on the
operator's written move of an AC out of the story, and the re-gate still read
it. TEA's trace scores every criterion it resolves, with no status for a moved
one, so the AC was a NONE row of its matrix, the gate read FAIL, and
`operator_owed.py`, finding an open AC the story no longer tags, sent the story
to a re-loop with nothing to build. gate.md now runs this check after trace and
before `gate_eval.py` on every re-gate after a move, and escalates again on
anything but exit 0. A wrong exit 0 would let the gate score the moved AC, so
every closed direction is pinned here:

- exit 0 only when the matrix reads as this trace's and no row is a moved AC;
- exit 1 when an AC token anywhere in a row id names a moved AC (`AC-07`,
  `ac-7`, `AC7`, `AC 7`, `AC: 7`, `AC#7`, `AC.7`, a dash, `AC-7.1`, `AC-7_1`,
  `AC-7: login`, `AC-7/AC-8`, the story's own `96-0-AC-7`), naming each such
  row and where trace says it read its criteria, while `AC-70`, `AC-17` and a
  sibling story's `11-5-AC-7` name no moved AC;
- exit 2 when the report, the matrix or the summary cannot be read or do not
  agree, through operator_owed.read_matrix, whose FAIL-only route is untouched,
  when they measured a commit other than `--commit` (the summary's or the
  matrix's own), when a requirement id is not a string, and on any failure the
  check did not foresee, which still prints the JSON object;
- `--commit` only as a full sha, 40 or 64 hex digits, never `HEAD` or a
  prefix, which could match another commit's matrix;
- several `--moved`, each normalised and checked once; a malformed one is a
  usage error, which still prints the JSON object with its reason.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_moved_ac_check.py -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


check = _load("moved_ac_check")
owed = _load("operator_owed")

STORY = "96-0-g-the-landing"
SHA = "a14e48a79010dd124366db59af51d8586e85ab33"
PRIORITIES = ("P0", "P1", "P2", "P3")
ORACLE_SOURCES = ["_bmad-output/implementation-artifacts/96-0-g-the-landing.md", "_bmad-output/planning/epics.md"]

# AC 7 moved out of the story; AC 8 is an operator-evidence AC still owed.
WITHOUT_AC7 = [(f"AC-{n}", "P0", "FULL") for n in range(1, 7)] + [("AC-8", "P1", "NONE")]
WITH_AC7 = WITHOUT_AC7[:6] + [("AC-7", "P1", "NONE")] + WITHOUT_AC7[6:]


def _breakdown(reqs: list[tuple[str, str, str]]) -> dict:
    out = {}
    for p in PRIORITIES:
        total = sum(1 for _, prio, _ in reqs if prio == p)
        covered = sum(1 for _, prio, cov in reqs if prio == p and cov == "FULL")
        out[p] = {"total": total, "covered": covered}
    return out


class Trace:
    """The trace directory a re-gate's trace writes, and TEA's Phase 1 matrix beside it."""

    def __init__(self, root: Path, reqs=WITHOUT_AC7):
        self.trace = root / "trace"
        self.trace.mkdir(parents=True, exist_ok=True)
        self.matrix_path = root / "tmp" / "tea-trace-coverage-matrix-1.json"
        self.matrix_path.parent.mkdir(parents=True, exist_ok=True)
        self.matrix = {
            "phase": "PHASE_1_COMPLETE",
            "source_sha": SHA,
            "oracle": {"resolution_mode": "formal_requirements", "sources": list(ORACLE_SOURCES)},
            "requirements": [{"id": rid, "priority": prio, "coverage": cov} for rid, prio, cov in reqs],
            "coverage_statistics": {"priority_breakdown": _breakdown(list(reqs))},
            "live_records": [],
        }
        self.summary = {"source_sha": SHA, "coverage": {"priority_breakdown": _breakdown(list(reqs))}}
        self.frontmatter = {
            "workflowType": "testarch-trace",
            "gateDecisionFile": f"gate-decision-{STORY}.json",
            "tempCoverageMatrixPath": f"'{self.matrix_path}'",
        }

    def write(self) -> "Trace":
        self.matrix_path.write_text(json.dumps(self.matrix), encoding="utf-8")
        (self.trace / f"e2e-trace-summary-{STORY}.json").write_text(json.dumps(self.summary), encoding="utf-8")
        fm = "\n".join(f"{k}: {v}" for k, v in self.frontmatter.items())
        (self.trace / f"trace-{STORY}.md").write_text(f"---\n{fm}\n---\n\nbody\n", encoding="utf-8")
        return self

    def argv(self, *moved: str, commit: str = SHA) -> list[str]:
        argv = ["--trace-output", str(self.trace), "--story", STORY, "--commit", commit]
        for rid in moved:
            argv += ["--moved", rid]
        return argv


def run(argv: list[str]) -> tuple[int, dict]:
    return check.evaluate(check.build_parser().parse_args(argv))


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# --- the one shape that passes -------------------------------------------------


def test_a_matrix_with_no_row_for_the_moved_ac_passes(tmp_path):
    trace = Trace(tmp_path).write()
    before = _tree(tmp_path)
    code, out = run(trace.argv("AC-7"))
    assert code == 0, out["reasons"]
    assert out["rows"] == []
    assert out["moved"] == ["AC-7"]
    assert out["matrix"] == str(trace.matrix_path)
    assert out["oracle_sources"] == ORACLE_SOURCES
    assert out["assessed_commit"] == SHA
    assert set(out) == {"moved", "rows", "matrix", "oracle_sources", "assessed_commit", "reasons"}
    assert _tree(tmp_path) == before, "the check must read, never write"


def test_main_prints_the_json_and_exits_with_the_code(tmp_path, capsys):
    trace = Trace(tmp_path).write()
    assert check.main(trace.argv("AC-7")) == 0
    assert json.loads(capsys.readouterr().out)["rows"] == []
    trace = Trace(tmp_path, reqs=WITH_AC7).write()
    assert check.main(trace.argv("AC-7")) == 1
    assert [r["id"] for r in json.loads(capsys.readouterr().out)["rows"]] == ["AC-7"]


# --- a row that is a moved AC ----------------------------------------------------


def test_a_row_for_the_moved_ac_refuses_and_names_where_trace_read_it(tmp_path):
    """The field shape: the AC left the story's list, and trace scored it NONE anyway."""
    code, out = run(Trace(tmp_path, reqs=WITH_AC7).write().argv("AC-7"))
    assert code == 1
    assert out["rows"] == [{"id": "AC-7", "priority": "P1", "coverage": "NONE"}]
    assert out["oracle_sources"] == ORACLE_SOURCES
    assert any("AC-7" in r and "still scores" in r for r in out["reasons"])


def test_a_covered_row_for_the_moved_ac_refuses_too(tmp_path):
    """A FULL row still counts in every percentage the gate reads, so its
    coverage is no reason to pass."""
    reqs = WITHOUT_AC7[:6] + [("AC-7", "P1", "FULL")] + WITHOUT_AC7[6:]
    code, out = run(Trace(tmp_path, reqs=reqs).write().argv("AC-7"))
    assert code == 1 and out["rows"][0]["coverage"] == "FULL"


@pytest.mark.parametrize(
    "spelling",
    ["AC-07", "ac-7", " AC-7 ", "AC-7.1", "AC-7a", "AC-7-b", "ac-07.2", "AC7", "AC 7", "AC-7: login", "AC-7_1",
     "AC-7 (a)", "AC_7", "story AC-7", "AC: 7", "AC#7", "AC.7", "AC  7", "AC\u20137", "AC\u20147", "AC \u2014 7",
     "AC\u20107", "96-0-AC-7", STORY + "-AC-7"],
)
def test_another_spelling_of_the_moved_id_is_the_same_row(tmp_path, spelling):
    reqs = WITHOUT_AC7[:6] + [(spelling, "P1", "NONE")] + WITHOUT_AC7[6:]
    code, out = run(Trace(tmp_path, reqs=reqs).write().argv("AC-7"))
    assert code == 1
    assert out["rows"][0]["id"] == spelling.strip()


@pytest.mark.parametrize(
    "other",
    ["AC-70", "AC-17", "AC-71.1", "REQ-7", "7", "AC-", "AC-x7", "TRAC-7", "AC-070", "11-5-AC-7", "11-6-AC-7",
     "96-1-AC-7", "AC--7"],
)
def test_a_row_that_is_another_criterion_is_not_the_moved_ac(tmp_path, other):
    reqs = WITHOUT_AC7[:6] + [(other, "P1", "NONE")] + WITHOUT_AC7[6:]
    code, out = run(Trace(tmp_path, reqs=reqs).write().argv("AC-7"))
    assert code == 0, out["reasons"]


# --- several moved ACs ------------------------------------------------------------


def test_every_moved_ac_is_checked(tmp_path):
    reqs = WITHOUT_AC7[:3] + [("AC-9", "P2", "NONE")] + WITHOUT_AC7[3:]
    trace = Trace(tmp_path, reqs=reqs).write()
    code, out = run(trace.argv("AC-7", "AC-9"))
    assert code == 1
    assert [r["id"] for r in out["rows"]] == ["AC-9"]
    code, out = run(trace.argv("AC-7", "AC-10"))
    assert code == 0
    assert out["moved"] == ["AC-7", "AC-10"]


def test_two_rows_for_two_moved_acs_are_both_named(tmp_path):
    reqs = WITH_AC7 + [("AC-9", "P2", "NONE")]
    code, out = run(Trace(tmp_path, reqs=reqs).write().argv("AC-9", "AC-7", "AC-7"))
    assert code == 1
    assert out["moved"] == ["AC-7", "AC-9"]
    assert sorted(r["id"] for r in out["rows"]) == ["AC-7", "AC-9"]


@pytest.mark.parametrize("bad", ["7", "AC7", "AC-", "AC-7a", "AC-7,AC-9"])
def test_a_malformed_moved_id_is_a_usage_error_that_still_prints_json(tmp_path, bad, capsys):
    trace = Trace(tmp_path).write()
    with pytest.raises(SystemExit) as exc:
        check.main(trace.argv(bad))
    assert exc.value.code == 2
    printed = json.loads(capsys.readouterr().out)
    assert printed["rows"] == [] and printed["matrix"] is None
    assert any("usage error" in r and "AC-<n>" in r for r in printed["reasons"])


@pytest.mark.parametrize("spelling", ["ac-7", " AC-7 ", "AC-07", "Ac-007"])
def test_a_moved_id_is_normalised_and_listed_once(tmp_path, spelling):
    trace = Trace(tmp_path, reqs=WITH_AC7).write()
    code, out = run(trace.argv(spelling, "AC-7"))
    assert code == 1
    assert out["moved"] == ["AC-7"]
    assert [r["id"] for r in out["rows"]] == ["AC-7"]


@pytest.mark.parametrize("cut", ["--moved", "--commit"])
def test_a_missing_required_argument_is_a_usage_error(tmp_path, cut, capsys):
    argv = Trace(tmp_path).write().argv("AC-7")
    i = argv.index(cut)
    with pytest.raises(SystemExit) as exc:
        check.main(argv[:i] + argv[i + 2 :])
    assert exc.value.code == 2
    assert any(cut in r for r in json.loads(capsys.readouterr().out)["reasons"])


# --- the trace of another commit: a previous gate's files are not this one's -----


def test_trace_files_that_measured_another_commit_refuse(tmp_path):
    """A re-gate whose trace never wrote leaves the previous gate's files, which
    agree with each other and name the commit that gate measured."""
    trace = Trace(tmp_path, reqs=WITHOUT_AC7).write()
    code, out = run(trace.argv("AC-7", commit="0123456789abcdef0123456789abcdef01234567"))
    assert code == 2
    assert out["rows"] == [] and out["assessed_commit"] is None
    assert any("not the commit under assessment" in r for r in out["reasons"])


def test_a_summary_with_no_matrix_commit_is_still_checked_against_the_commit(tmp_path):
    trace = Trace(tmp_path)
    del trace.matrix["source_sha"]
    trace.write()
    assert run(trace.argv("AC-7"))[0] == 0
    assert run(trace.argv("AC-7", commit="0123456789abcdef0123456789abcdef01234567"))[0] == 2


def test_a_short_form_of_the_commit_under_assessment_is_refused(tmp_path, capsys):
    """A prefix could match another commit's matrix, so only the full sha passes;
    its case does not matter."""
    trace = Trace(tmp_path).write()
    with pytest.raises(SystemExit) as exc:
        check.main(trace.argv("AC-7", commit=SHA[:12]))
    assert exc.value.code == 2
    assert any("--commit" in r for r in json.loads(capsys.readouterr().out)["reasons"])
    assert run(trace.argv("AC-7", commit=SHA.upper()))[0] == 0


def test_a_matrix_commit_of_another_tail_refuses(tmp_path):
    """The summary names a 7-digit prefix of the commit under assessment, and the
    matrix a full sha with that prefix and another tail: the loader reads the two
    as one commit, so only the matrix's own comparison with `--commit` refuses."""
    trace = Trace(tmp_path)
    trace.summary["source_sha"] = SHA[:7]
    trace.matrix["source_sha"] = SHA[:7] + "f" * (len(SHA) - 7)
    assert trace.matrix["source_sha"] != SHA
    trace.write()
    code, out = run(trace.argv("AC-7"))
    assert code == 2
    assert any("not the commit under assessment" in r for r in out["reasons"])


@pytest.mark.parametrize(
    "commit", ["", "HEAD", "a", "abc12", "abcdef", "abcdef1", SHA[:12], SHA[:39], "g" * 40, "a" * 65, "main"]
)
def test_a_commit_that_is_not_a_full_or_short_sha_is_a_usage_error(tmp_path, commit, capsys):
    trace = Trace(tmp_path).write()
    with pytest.raises(SystemExit) as exc:
        check.main(trace.argv("AC-7", commit=commit))
    assert exc.value.code == 2
    printed = json.loads(capsys.readouterr().out)
    assert any("--commit" in r for r in printed["reasons"])


def test_a_failure_the_check_did_not_foresee_exits_2_and_keeps_what_it_read(tmp_path, capsys, monkeypatch):
    """Uncaught, a failure part way exited 1, the code that means a row was
    found, and printed nothing; the JSON keeps what the read had collected."""
    trace = Trace(tmp_path, reqs=WITH_AC7).write()

    def fail(rid: str, story: str) -> set[int]:
        raise RuntimeError("row reader broke")

    monkeypatch.setattr(check, "_named_numbers", fail)
    assert check.main(trace.argv("AC-7")) == 2
    printed = json.loads(capsys.readouterr().out)
    assert printed["rows"] == [] and printed["moved"] == ["AC-7"]
    assert printed["matrix"] == str(trace.matrix_path)
    assert printed["oracle_sources"] == ORACLE_SOURCES and printed["assessed_commit"] == SHA
    assert any("could not finish" in r and "row reader broke" in r for r in printed["reasons"])


def test_a_sibling_that_failed_to_import_exits_2_with_its_json(tmp_path, capsys, monkeypatch):
    trace = Trace(tmp_path).write()
    monkeypatch.setattr(check, "_IMPORT_ERROR", ImportError("no operator_owed"))
    assert check.main(trace.argv("AC-7")) == 2
    printed = json.loads(capsys.readouterr().out)
    assert printed["matrix"] is None and any("no operator_owed" in r for r in printed["reasons"])


def test_a_closed_pipe_exits_2_not_1(tmp_path, monkeypatch):
    trace = Trace(tmp_path, reqs=WITH_AC7).write()

    class Closed:
        def write(self, text: str) -> int:
            raise BrokenPipeError("the reader went away")

        def flush(self) -> None:
            raise BrokenPipeError("the reader went away")

    monkeypatch.setattr(sys, "stdout", Closed())
    assert check.main(trace.argv("AC-7")) == 2


def test_a_story_prefix_counts_only_for_this_story():
    assert check._named_numbers("11-5-AC-7", "11-6") == set()
    assert check._named_numbers("11-6-AC-7", "11-6") == {7}
    assert check._named_numbers("11-6-AC-7", "11-6-the-login-page") == {7}
    assert check._named_numbers("11-5-AC-7 / AC-8", "11-6") == {8}


def test_a_row_naming_two_acs_is_a_row_of_each(tmp_path):
    reqs = WITHOUT_AC7[:6] + [("AC-7/AC-8", "P1", "NONE")] + WITHOUT_AC7[6:]
    trace = Trace(tmp_path, reqs=reqs).write()
    assert [r["id"] for r in run(trace.argv("AC-8"))[1]["rows"]] == ["AC-7/AC-8", "AC-8"]
    assert [r["id"] for r in run(trace.argv("AC-7"))[1]["rows"]] == ["AC-7/AC-8"]


@pytest.mark.parametrize("rid", [7, None, ["AC-7"], {"id": "AC-7"}])
def test_a_requirement_id_that_is_not_a_string_refuses(tmp_path, rid):
    trace = Trace(tmp_path)
    trace.matrix["requirements"][0]["id"] = rid
    trace.write()
    code, out = run(trace.argv("AC-7"))
    assert code == 2
    assert any("not a string" in r for r in out["reasons"])


# --- a matrix that cannot be read or is not this trace's: fail closed --------------


def _matrix_missing(t: Trace) -> None:
    t.matrix_path.unlink()


def _matrix_not_json(t: Trace) -> None:
    t.matrix_path.write_text("{", encoding="utf-8")


def _phase_not_complete(t: Trace) -> None:
    t.matrix["phase"] = "PHASE_1_IN_PROGRESS"
    t.write()


def _relative_hint(t: Trace) -> None:
    t.frontmatter["tempCoverageMatrixPath"] = "tmp/tea-trace-coverage-matrix-1.json"
    t.write()


def _no_hint(t: Trace) -> None:
    del t.frontmatter["tempCoverageMatrixPath"]
    t.write()


def _summary_missing(t: Trace) -> None:
    (t.trace / f"e2e-trace-summary-{STORY}.json").unlink()


def _summary_disagrees(t: Trace) -> None:
    t.summary["coverage"]["priority_breakdown"]["P1"]["covered"] = 1
    t.write()


def _requirements_disagree(t: Trace) -> None:
    # The stats, and the summary they agree with, still count the moved AC's
    # row, but the list under them lost it: read off the list alone, the check
    # would pass a matrix whose numbers still score AC-7.
    t.matrix["coverage_statistics"]["priority_breakdown"] = _breakdown(WITH_AC7)
    t.summary["coverage"]["priority_breakdown"] = _breakdown(WITH_AC7)
    t.write()


def _another_commit(t: Trace) -> None:
    t.matrix["source_sha"] = "0123456789abcdef0123456789abcdef01234567"
    t.write()


def _report_missing(t: Trace) -> None:
    (t.trace / f"trace-{STORY}.md").unlink()


def _a_siblings_report_only(t: Trace) -> None:
    (t.trace / f"trace-{STORY}.md").rename(t.trace / "trace-96-0-g.md")


@pytest.mark.parametrize(
    "damage",
    [
        _matrix_missing,
        _matrix_not_json,
        _phase_not_complete,
        _relative_hint,
        _no_hint,
        _summary_missing,
        _summary_disagrees,
        _requirements_disagree,
        _another_commit,
        _report_missing,
        _a_siblings_report_only,
    ],
)
def test_an_unreadable_or_foreign_matrix_refuses(tmp_path, damage):
    trace = Trace(tmp_path).write()
    damage(trace)
    code, out = run(trace.argv("AC-7"))
    assert code == 2
    assert out["rows"] == [] and out["assessed_commit"] is None
    assert any("could not be read" in r for r in out["reasons"])


def test_an_unreadable_matrix_exits_2_from_main(tmp_path, capsys):
    trace = Trace(tmp_path).write()
    trace.matrix_path.unlink()
    assert check.main(trace.argv("AC-7")) == 2
    assert json.loads(capsys.readouterr().out)["matrix"] is None


# --- the shared reader, and the route it was taken from ----------------------------


def test_the_check_reads_the_matrix_through_operator_owed():
    """One reader, so the two scripts cannot disagree on which matrix is this gate's."""
    source = (SCRIPTS / "moved_ac_check.py").read_text(encoding="utf-8")
    assert "operator_owed.read_matrix(" in source
    assert "_read_json" not in source and "_frontmatter" not in source


def test_operator_owed_still_reads_a_matrix_only_after_a_fail(tmp_path):
    """The extraction moved the matrix read, not the FAIL-only route in front of it."""
    trace = Trace(tmp_path).write()
    reasons: list[str] = []
    assert owed.read_matrix(trace.trace, STORY, reasons) is not None and reasons == []
    source = (SCRIPTS / "operator_owed.py").read_text(encoding="utf-8")
    evaluate = source[source.index("def evaluate(") :]
    assert evaluate.index("_gate_reads_owed(args, reasons)") < evaluate.index("read_matrix(")
