#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""operator_owed.py: is a gate FAIL one only operator evidence can change?

The field case: a story whose every test was green failed its gate at P1 75%,
because one acceptance criterion carried a half only a person could measure (a
Windows release build) as prose, TEA counted the whole AC PARTIAL, and the gate
routed the FAIL to a re-loop no fix could ever satisfy. Define-Done now splits
that half into its own AC tagged `**Gate-ability:** operator-evidence`, and gate.md asks
this script, on every FAIL, whether only such ACs are open. `owed: true`
becomes an `operator-evidence-owed` escalation, which `drive_epic.py` reports
as a handoff, so a wrong `true` would dress a real failure as routine. Every
closed direction is therefore pinned here:

- owed only when the gate reads FAIL over a full instrument (no delta, a
  scope=full sweep, and in production NFR and test-review that pass the AND);
- the trace report is the story's own `trace-<id>.md`, and its
  `tempCoverageMatrixPath` names an absolute, PHASE_1_COMPLETE matrix whose
  counts, requirement recount and commit agree with the story's own summary;
- every open requirement is `AC-<n>` and the story tags AC `<n>.`
  operator-evidence and nothing else, inside its one `## Acceptance Criteria`
  section; a plain `operator` tag is work the dev agent builds, never owed;
- a live record that failed is a finding, never owed evidence; a stale one is
  still owed;
- anything unreadable gives false.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_operator_owed.py -v
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS / "operator_owed.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


owed_mod = _load("operator_owed", SCRIPT)

STORY = "96-0-g-the-landing"
SHA = "a14e48a79010dd124366db59af51d8586e85ab33"
PRIORITIES = ("P0", "P1", "P2", "P3")

# Five P0 and four P1 criteria covered, and the split operator half (AC 10) open.
CLEAN = [(f"AC-{n}", "P0", "FULL") for n in range(1, 6)] + [
    (f"AC-{n}", "P1", "FULL") for n in range(6, 10)
] + [("AC-10", "P1", "NONE")]

AC_TEMPLATE = """{n}. **Criterion {n}.**
   **Verification:** case-{n}.test.ts.
   **Anti-vacuous twin:** remove the guard and case-{n} goes red.
   **Gate-ability:** {tag}.
"""


def story_text(tags: dict[int, str], extra: str = "") -> str:
    body = "\n".join(AC_TEMPLATE.format(n=n, tag=tag) for n, tag in sorted(tags.items()))
    return f"# Story {STORY}\n\n## Acceptance Criteria\n\n{body}\n{extra}## Tasks\n\n- [ ] Task 1 (AC: 1)\n"


SPLIT_TAGS = {n: "ci-machine" for n in range(1, 10)} | {10: "operator-evidence"}


def breakdown(reqs: list[tuple[str, str, str]], pct_key: str) -> dict:
    out = {}
    for p in PRIORITIES:
        total = sum(1 for _, prio, _ in reqs if prio == p)
        covered = sum(1 for _, prio, cov in reqs if prio == p and cov == "FULL")
        out[p] = {"total": total, "covered": covered, pct_key: round(covered / total * 100) if total else 100}
    return out


class Project:
    """A trace dir, a story file, the gate signals and TEA's matrix, all in tmp_path."""

    def __init__(self, root: Path, reqs=CLEAN, tags=SPLIT_TAGS, live=(), gate="FAIL"):
        self.root = root
        self.trace = root / "trace"
        self.impl = root / "impl"
        self.scratch = root / "scratch"
        for d in (self.trace, self.impl, self.scratch):
            d.mkdir(parents=True, exist_ok=True)
        self.matrix_path = self.scratch / "tea-trace-coverage-matrix.json"
        self.matrix = {
            "phase": "PHASE_1_COMPLETE",
            "source_sha": SHA,
            "requirements": [
                {"id": rid, "priority": prio, "coverage": cov, "gaps": [f"{rid} gap"]}
                for rid, prio, cov in reqs
            ],
            "coverage_statistics": {"priority_breakdown": breakdown(list(reqs), "percentage")},
            "live_records": [dict(r) for r in live],
        }
        self.summary = {
            "source_sha": SHA,
            "coverage": {"priority_breakdown": breakdown(list(reqs), "pct")},
        }
        self.gate = {"gate_status": gate, "p0_status": "MET", "p1_status": "NOT_MET", "overall_status": "MET"}
        self.frontmatter = {
            "workflowType": "testarch-trace",
            "gateDecisionFile": f"gate-decision-{STORY}.json",
            "tempCoverageMatrixPath": f"'{self.matrix_path}'",
        }
        self.story_file = root / f"{STORY}.md"
        self.story = story_text(tags)
        self.nfr = self.trace / f"nfr-assessment-{STORY}.md"
        self.nfr_text = "# NFR\n\n**Overall Status:** CONCERNS\n"
        self.review = self.trace / f"test-review-{STORY}.md"
        self.review_text = "# Review\n\n**Quality Score**: 84/100\n**Recommendation**: Approve with Comments\n"
        self.tests_ran = self.impl / f".tests-ran-{STORY}"
        self.tests_ran_text = f"baseline={SHA}\nscope=full\n"

    def write(self) -> "Project":
        self.matrix_path.write_text(json.dumps(self.matrix), encoding="utf-8")
        (self.trace / f"e2e-trace-summary-{STORY}.json").write_text(json.dumps(self.summary), encoding="utf-8")
        (self.trace / f"gate-decision-{STORY}.json").write_text(json.dumps(self.gate), encoding="utf-8")
        fm = "\n".join(f"{k}: {v}" for k, v in self.frontmatter.items())
        (self.trace / f"trace-{STORY}.md").write_text(f"---\n{fm}\n---\n\nbody\n", encoding="utf-8")
        self.story_file.write_text(self.story, encoding="utf-8")
        self.nfr.write_text(self.nfr_text, encoding="utf-8")
        self.review.write_text(self.review_text, encoding="utf-8")
        self.tests_ran.write_text(self.tests_ran_text, encoding="utf-8")
        return self

    def argv(self, profile: str = "production", **extra: str) -> list[str]:
        argv = [
            "--trace-output", str(self.trace),
            "--story", STORY,
            "--story-file", str(self.story_file),
            "--profile", profile,
            "--tests-ran", str(self.tests_ran),
        ]
        if profile == "production":
            argv += ["--nfr", str(self.nfr), "--test-review", str(self.review)]
        for flag, value in extra.items():
            argv += [f"--{flag.replace('_', '-')}", value]
        return argv


def run(argv: list[str]) -> dict:
    return owed_mod.evaluate(owed_mod.build_parser().parse_args(argv))


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return Project(tmp_path)


# --- the one shape that is owed -----------------------------------------------


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_only_an_open_operator_ac_is_owed(project):
    project.write()
    before = _tree(project.root)
    result = run(project.argv())
    assert result["owed"] is True, result["reasons"]
    assert result["open"] == result["operator"] == ["AC-10"]
    assert result["assessed_commit"] == SHA
    assert result["evidence"] == {"AC-10": "none"}
    assert set(result) == {"owed", "open", "operator", "evidence", "assessed_commit", "reasons"}
    assert _tree(project.root) == before, "the check must read, never write"


def test_main_prints_the_json_and_exits_zero(project, capsys):
    project.write()
    assert owed_mod.main(project.argv()) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["owed"] is True


def test_a_missing_required_argument_is_a_usage_error(project):
    argv = project.write().argv()
    cut = argv.index("--story-file")
    with pytest.raises(SystemExit) as exc:
        owed_mod.main(argv[:cut] + argv[cut + 2 :])
    assert exc.value.code == 2


# --- open criteria a re-loop can change ---------------------------------------


def test_a_ci_machine_ac_also_open_is_not_owed(tmp_path):
    reqs = [(rid, prio, "PARTIAL" if rid == "AC-4" else cov) for rid, prio, cov in CLEAN]
    project = Project(tmp_path, reqs=reqs).write()
    result = run(project.argv())
    assert result["owed"] is False
    assert result["open"] == ["AC-4", "AC-10"]
    assert result["operator"] == ["AC-10"]
    assert any(r.startswith("AC-4 is open") for r in result["reasons"]), result["reasons"]


def test_an_operator_ac_covered_live_beside_a_unit_only_ci_ac_is_not_owed(tmp_path):
    """The trap a union of TEA's recommendation lists falls into.

    TEA lists an AC covered only by live evidence among its recommendations,
    and leaves a P1 UNIT-ONLY criterion out of them, so reading the
    recommendations would call this story operator-owed. The matrix says AC-10
    is FULL and AC-7, a ci-machine AC, is the open one.
    """
    reqs = [
        (rid, prio, "UNIT-ONLY" if rid == "AC-7" else "FULL" if rid == "AC-10" else cov)
        for rid, prio, cov in CLEAN
    ]
    live = [{"id": f"{STORY}-LIVE-001", "requirement_id": "AC-10", "disposition": "counted"}]
    project = Project(tmp_path, reqs=reqs, live=live).write()
    result = run(project.argv())
    assert result["owed"] is False
    assert result["open"] == ["AC-7"]
    assert result["operator"] == []


def test_the_real_run_shape_is_not_owed(tmp_path):
    """The cycle-1 matrix of the field case, before any split: three ACs open.

    AC-4 was a real test gap and AC-2 needed a ruling, so the re-loop route was
    right for this one, and no AC is tagged operator-evidence.
    """
    open_ids = {"AC-2": "PARTIAL", "AC-4": "PARTIAL", "AC-9": "PARTIAL"}
    reqs = [(rid, prio, open_ids.get(rid, cov)) for rid, prio, cov in CLEAN if rid != "AC-10"]
    tags = {n: "ci-machine" for n in range(1, 10) if n != 2}
    project = Project(tmp_path, reqs=reqs, tags=tags).write()
    result = run(project.argv())
    assert result["owed"] is False
    assert result["open"] == ["AC-2", "AC-4", "AC-9"]
    assert result["operator"] == []


def test_a_fail_with_no_open_criterion_is_not_owed(tmp_path):
    reqs = [(rid, prio, "FULL") for rid, prio, _ in CLEAN]
    project = Project(tmp_path, reqs=reqs).write()
    result = run(project.argv())
    assert result["owed"] is False
    assert result["open"] == []


# --- the story's tag is read narrowly -------------------------------------------


@pytest.mark.parametrize(
    "story",
    [
        pytest.param(story_text(SPLIT_TAGS | {10: "partly-operator"}), id="unsplit-partly-operator"),
        pytest.param(story_text(SPLIT_TAGS | {10: "operator"}), id="plain-operator"),
        pytest.param(story_text(SPLIT_TAGS | {10: "Operator-evidence"}), id="tag-not-exactly-operator-evidence"),
        pytest.param(
            story_text(SPLIT_TAGS).replace(
                "**Gate-ability:** operator-evidence.",
                "**Gate-ability:** operator-evidence.\n   **Gate-ability:** ci-machine.",
            ),
            id="mixed-tags",
        ),
        pytest.param(
            story_text({n: t for n, t in SPLIT_TAGS.items() if n != 10})
            + "\n10. **Operator half.**\n   **Gate-ability:** operator-evidence.\n",
            id="tag-outside-the-ac-section",
        ),
        pytest.param(
            story_text(SPLIT_TAGS, extra="10. **A second AC 10.**\n   **Gate-ability:** operator-evidence.\n\n"),
            id="ac-numbered-twice",
        ),
        pytest.param(
            story_text(SPLIT_TAGS) + "\n## Acceptance Criteria\n\n1. **Again.**\n",
            id="two-ac-sections",
        ),
        pytest.param(story_text(SPLIT_TAGS).replace("## Acceptance Criteria", "## Criteria"), id="no-ac-section"),
        pytest.param(
            story_text(SPLIT_TAGS).replace("10. **Criterion 10.**", "   10. **Criterion 10.**"),
            id="indented-item-is-not-an-ac",
        ),
    ],
)
def test_an_ac_the_story_does_not_tag_operator_evidence_alone_is_not_owed(project, story):
    project.story = story
    project.write()
    result = run(project.argv())
    assert result["owed"] is False
    assert result["operator"] == []


def test_an_open_id_that_is_not_an_ac_is_not_owed(tmp_path):
    reqs = [("REQ-10" if rid == "AC-10" else rid, prio, cov) for rid, prio, cov in CLEAN]
    project = Project(tmp_path, reqs=reqs).write()
    result = run(project.argv())
    assert result["owed"] is False
    assert result["open"] == ["REQ-10"]


def test_operator_acs_reads_only_the_ac_section():
    text = story_text(SPLIT_TAGS)
    assert owed_mod.operator_acs(text) == {10}
    assert owed_mod.operator_acs(text.replace("operator-evidence.", "ci-machine.")) == set()
    assert owed_mod.operator_acs(text.replace("operator-evidence.", "operator.")) == set()


# --- a plain `operator` tag is built work, never owed evidence --------------------

# GMC 96-0-j's shape. Six ACs carry the older plain `operator` tag, for work the
# dev agent builds and a person or a script verifies (doc fixes, a CLAUDE.md pin,
# ledger closures, a checklist run on a real build). AC 7 is the pin, and its own
# verification is a machine check. Priorities as its test design set them.
J_PRIORITY = {n: "P0" for n in (1, 2, 3, 4, 10, 11, 12)} | {5: "P1", 13: "P1"} | {n: "P2" for n in (6, 7, 8, 9)}
J_TAGS = {n: "ci-machine" for n in (1, 2, 3, 4, 5, 11, 13)} | {n: "operator" for n in (6, 7, 8, 9, 10, 12)}
J_AC7 = """7. **The pin lands where the next session will read it.**
   **Verification:** `bun run check:claude-size` green; `check:no-emdash` green.
   **Gate-ability:** {tag}.
"""


def j_story(tags: dict[int, str]) -> str:
    text = story_text(tags)
    generic = AC_TEMPLATE.format(n=7, tag=tags[7])
    assert generic in text
    return text.replace(generic, J_AC7.format(tag=tags[7]))


def j_reqs(open_ids: dict[str, str]) -> list[tuple[str, str, str]]:
    return [(f"AC-{n}", J_PRIORITY[n], open_ids.get(f"AC-{n}", "FULL")) for n in sorted(J_PRIORITY)]


def test_a_plain_operator_ac_is_never_owed(tmp_path):
    """The review's run: four plain-operator ACs open, AC 7's gap a missing pin a script checks.

    Read as owed evidence, the story would stop for a person to record a result
    for work a re-loop builds. The plain tag keeps the re-loop for every one.
    """
    reqs = j_reqs({"AC-6": "PARTIAL", "AC-7": "NONE", "AC-10": "NONE", "AC-12": "NONE"})
    project = Project(tmp_path, reqs=reqs, tags=J_TAGS)
    project.story = j_story(J_TAGS)
    project.write()
    assert "`bun run check:claude-size` green" in project.story_file.read_text(encoding="utf-8")
    result = run(project.argv(profile="light"))
    assert result["owed"] is False
    assert result["open"] == ["AC-6", "AC-7", "AC-10", "AC-12"]
    assert result["operator"] == []
    assert result["assessed_commit"] is None
    for rid in result["open"]:
        assert any(
            r.startswith(f"{rid} is open") and "operator-evidence, so a re-loop can change it" in r
            for r in result["reasons"]
        ), (rid, result["reasons"])


def test_a_plain_operator_ac_open_beside_operator_evidence_ones_keeps_the_reloop(tmp_path):
    """Define-Done retags the two real live-result ACs; the pin stays plain and stays built work.

    While the pin is open the re-loop stands; once it is built, only the
    operator-evidence ACs are open and they are owed.
    """
    tags = J_TAGS | {10: "operator-evidence", 12: "operator-evidence"}
    project = Project(tmp_path, reqs=j_reqs({"AC-7": "NONE", "AC-10": "NONE", "AC-12": "NONE"}), tags=tags)
    project.story = j_story(tags)
    project.write()
    result = run(project.argv(profile="light"))
    assert result["owed"] is False
    assert result["open"] == ["AC-7", "AC-10", "AC-12"]
    assert result["operator"] == ["AC-10", "AC-12"]
    assert any(r.startswith("AC-7 is open") for r in result["reasons"]), result["reasons"]

    built = Project(tmp_path / "built", reqs=j_reqs({"AC-10": "NONE", "AC-12": "NONE"}), tags=tags)
    built.story = j_story(tags)
    built.write()
    result = run(built.argv(profile="light"))
    assert result["owed"] is True, result["reasons"]
    assert result["open"] == result["operator"] == ["AC-10", "AC-12"]


# --- live records -------------------------------------------------------------


@pytest.mark.parametrize(
    ("disposition", "owed"),
    [("fail", False), ("contradicted", False), ("stale", True), ("blocked", True)],
)
def test_a_failed_record_is_a_finding_and_a_stale_one_is_still_owed(tmp_path, disposition, owed):
    live = [{"id": f"{STORY}-LIVE-001", "requirement_id": "AC-10", "disposition": disposition}]
    project = Project(tmp_path, live=live).write()
    result = run(project.argv())
    assert result["owed"] is owed, result["reasons"]
    if owed:
        assert result["evidence"] == {"AC-10": disposition}
    else:
        assert result["operator"] == []
        assert any(disposition in r for r in result["reasons"])


# --- the gate must be the full instrument, failing on coverage alone -------------


@pytest.mark.parametrize("status", ["PASS", "WAIVED", "CONCERNS", "NOT_EVALUATED"])
def test_a_gate_that_is_not_fail_is_not_owed(tmp_path, status):
    project = Project(tmp_path, gate=status).write()
    result = run(project.argv())
    assert result["owed"] is False
    assert result["open"] == []


def test_a_story_with_no_gate_decision_is_not_owed(project):
    project.write()
    (project.trace / f"gate-decision-{STORY}.json").unlink()
    (project.trace / f"e2e-trace-summary-{STORY}.json").write_text("{}", encoding="utf-8")
    assert run(project.argv())["owed"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: setattr(p, "nfr_text", "**Overall Status:** FAIL\n"), id="nfr-fail"),
        pytest.param(lambda p: setattr(p, "nfr_text", "**Overall Status:** NOT_ASSESSED\n"), id="nfr-not-assessed"),
        pytest.param(
            lambda p: setattr(p, "review_text", "**Quality Score**: 74/100\n**Recommendation**: Approve\n"),
            id="review-score-74",
        ),
        pytest.param(
            lambda p: setattr(p, "review_text", "**Quality Score**: 91/100\n**Recommendation**: Block\n"),
            id="review-block-at-91",
        ),
    ],
)
def test_a_failing_production_signal_is_not_owed(project, mutate):
    mutate(project)
    project.write()
    result = run(project.argv())
    assert result["owed"] is False
    assert any("production signal" in r for r in result["reasons"])


def test_an_omitted_production_signal_is_not_owed(project):
    argv = project.write().argv()
    cut = argv.index("--nfr")
    assert run(argv[:cut] + argv[cut + 2 :])["owed"] is False


def test_light_reads_no_production_signal(project):
    project.nfr_text = "**Overall Status:** FAIL\n"
    project.write()
    assert run(project.argv())["owed"] is False
    assert run(project.argv(profile="light"))["owed"] is True


@pytest.mark.parametrize(
    "marker",
    [
        pytest.param(f"baseline={SHA}\nscope=scoped\npackages=a\n", id="scoped"),
        pytest.param(f"baseline={SHA}\n", id="no-scope-line"),
        pytest.param(None, id="missing-marker"),
    ],
)
def test_a_sweep_that_was_not_full_is_not_owed(project, marker):
    project.write()
    if marker is None:
        project.tests_ran.unlink()
    else:
        project.tests_ran.write_text(marker, encoding="utf-8")
    assert run(project.argv())["owed"] is False


def test_a_delta_gate_is_not_owed(project):
    project.write()
    assert run(project.argv(cycle_profile="delta"))["owed"] is False
    assert run(project.argv(cycle_profile="full"))["owed"] is True


# --- TEA's matrix must be this gate's, and readable ------------------------------


def _drop_matrix_hint(p: Project) -> None:
    del p.frontmatter["tempCoverageMatrixPath"]


def _summary_disagrees(p: Project) -> None:
    p.summary["coverage"]["priority_breakdown"]["P1"]["covered"] = 5


def _requirements_disagree(p: Project) -> None:
    # The stats still agree with the summary, but the list under them lost a
    # P1 criterion, so only the operator AC reads open in what is left.
    del p.matrix["requirements"][8]


def _matrix_of_another_commit(p: Project) -> None:
    p.matrix["source_sha"] = "0123456789abcdef0123456789abcdef01234567"


def _no_source_sha(p: Project) -> None:
    del p.summary["source_sha"]


def _empty_source_sha(p: Project) -> None:
    # Blank on both sides, so only the summary's own check can refuse it.
    p.summary["source_sha"] = "  "
    p.matrix["source_sha"] = ""


def _phase_not_complete(p: Project) -> None:
    p.matrix["phase"] = "PHASE_1_IN_PROGRESS"


def _no_coverage_statistics(p: Project) -> None:
    del p.matrix["coverage_statistics"]


def _string_count(p: Project) -> None:
    p.summary["coverage"]["priority_breakdown"]["P0"]["total"] = "5"


def _live_records_not_a_list(p: Project) -> None:
    p.matrix["live_records"] = {"AC-10": "stale"}


def _report_not_a_trace_report(p: Project) -> None:
    del p.frontmatter["workflowType"]


@pytest.mark.parametrize(
    "mutate",
    [
        _drop_matrix_hint,
        _summary_disagrees,
        _requirements_disagree,
        _matrix_of_another_commit,
        _no_source_sha,
        _empty_source_sha,
        _phase_not_complete,
        _no_coverage_statistics,
        _string_count,
        _live_records_not_a_list,
        _report_not_a_trace_report,
    ],
)
def test_a_matrix_or_summary_that_is_not_this_gates_is_not_owed(project, mutate):
    mutate(project)
    project.write()
    result = run(project.argv())
    assert result["owed"] is False
    assert result["assessed_commit"] is None


def test_a_relative_matrix_path_is_not_followed(project, monkeypatch):
    """A relative path would resolve against whatever directory the script runs in.

    Run from the directory where it does name the real matrix, so the refusal
    is the absolute-path rule's and not a missing file's.
    """
    project.frontmatter["tempCoverageMatrixPath"] = "scratch/tea-trace-coverage-matrix.json"
    project.write()
    monkeypatch.chdir(project.root)
    assert Path("scratch/tea-trace-coverage-matrix.json").is_file()
    result = run(project.argv())
    assert result["owed"] is False
    assert any("absolute tempCoverageMatrixPath" in r for r in result["reasons"])


@pytest.mark.parametrize(
    "damage",
    [
        pytest.param(lambda p: p.matrix_path.unlink(), id="matrix-missing"),
        pytest.param(lambda p: p.matrix_path.write_text("[]", encoding="utf-8"), id="matrix-not-an-object"),
        pytest.param(lambda p: p.matrix_path.write_text("{", encoding="utf-8"), id="matrix-not-json"),
        pytest.param(lambda p: (p.trace / f"e2e-trace-summary-{STORY}.json").unlink(), id="summary-missing"),
        pytest.param(lambda p: p.story_file.unlink(), id="story-file-missing"),
        pytest.param(lambda p: (p.trace / f"trace-{STORY}.md").unlink(), id="trace-report-missing"),
    ],
)
def test_an_unreadable_input_is_not_owed(project, damage):
    project.write()
    damage(project)
    result = run(project.argv())
    assert result["owed"] is False


def test_a_shorter_ids_trace_report_is_never_read(project):
    """Resolution is by the exact story id: a sibling's `trace-<prefix>.md` is not this story's."""
    project.write()
    own = project.trace / f"trace-{STORY}.md"
    sibling = project.trace / "trace-96-0-g.md"
    own.rename(sibling)
    result = run(project.argv())
    assert result["owed"] is False
    assert any(f"trace-{STORY}.md" in r for r in result["reasons"])
    # The same report under the story's own name is owed, so the name alone decided it.
    sibling.rename(own)
    assert run(project.argv())["owed"] is True
