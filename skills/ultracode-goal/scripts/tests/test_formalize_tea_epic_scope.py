"""formalize_check.py reads the checked Epic's own TEA files, where TEA writes them.

TEA 1.27.2 writes an Epic's plan as `{test_artifacts}/test-design-epic-{epic_num}.md`
and one `{test_artifacts}/nfr-assessment.md`, beside its system-level
`test-design-architecture.md` and `test-design-qa.md` and its progress and
validation files. The TEA-reader once read the first file under `trace_output`
whose name held `test-design`, whatever Epic it belonged to, and owed an NFR
assessment whenever it found one (issue #201). These tests pin: the root
preflight resolves, the Epic's own plan only (every copy, in any folder below
the root), TEA's own risk-table headers, an NFR assessment read only when it
names an in-scope story, and none ever owed.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "formalize_check.py"

RISK = "| Risk ID | Category | P | I | Score | Mitigation |\n|--|--|--|--|--|--|\n"
SCORED = RISK + "| T-1 | TECH | 2 | 2 | 4 | x |\n"
BLANK = RISK + "| T-1 | TECH | 3 | 2 |  | x |\n"
NFR = "Overall Status: PASS\n\n| Category | Status | Threshold | Evidence |\n|--|--|--|--|\n| latency | PASS | 200ms | bench.py:3 |\n"
NFR_UNKNOWN = "Overall Status: CONCERNS\n\n| Category | Status | Threshold | Evidence |\n|--|--|--|--|\n| latency | PASS | UNKNOWN | bench.py:3 |\n"
TA = "test_artifacts: {project-root}/ta\n"
INSTALLER = 'test_artifacts: "{project-root}/ta"\ntrace_output: ta/traceability\n'
TEA_KINDS = {
    "blank_pxi_score", "unreadable_tea_artifact", "missing_nfr_assessment", "leaked_tea_artifact",
    "risk_score_conflict", "invented_nfr_threshold", "nfr_pass_on_unknown", "nfr_pass_without_evidence",
    "nfr_overall_status_unreadable",
}
STORY = "# Story 1.1\n\n## Acceptance Criteria\n\n1. Given a user, when they log in, then they see the dashboard (verified by test_login.py).\n"


def _project(root: Path, files: dict[str, str | bytes], config: str | None = TA, impl: str = "impl-artifacts") -> Path:
    for folder in ("planning-artifacts", impl):
        (root / folder).mkdir(parents=True, exist_ok=True)
    if config is not None:
        (root / "tea").mkdir(parents=True, exist_ok=True)
        (root / "tea" / "config.yaml").write_text(config, encoding="utf-8")
    (root / "planning-artifacts" / "prd-x.md").write_text("# PRD\n", encoding="utf-8")
    (root / "planning-artifacts" / "architecture-x.md").write_text("# Architecture\n", encoding="utf-8")
    (root / impl / "sprint-status.yaml").write_text(
        "development_status:\n  epic-1: in-progress\n  1-0-old: done\n  1-1-login: backlog\n"
        "  epic-9: done\n  9-1-y: done\n  epic-10: in-progress\n  10-1-z: backlog\n",
        encoding="utf-8",
    )
    (root / impl / "1-1-login.md").write_text(STORY, encoding="utf-8")
    (root / impl / "10-1-z.md").write_text(STORY, encoding="utf-8")
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(body, encoding="utf-8")
    return root


def _run(root: Path, epic: str = "1", impl: str = "impl-artifacts", stories: tuple[str, ...] = ()) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--epic", epic, "--project-root", str(root),
         "--planning-artifacts", str(root / "planning-artifacts"), "--impl-artifacts", str(root / impl),
         "--tea-config", str(root / "tea" / "config.yaml"), *(a for s in stories for a in ("--story", s))],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _tea(out: dict) -> list[tuple[str, str]]:
    """The TEA findings, gaps then candidates, as (kind, source with `/`)."""
    items = out["mechanical_gaps"] + out["judgment_candidates"]
    return [(i["kind"], i["source"].replace("\\", "/")) for i in items if i["kind"] in TEA_KINDS]


_ROWS = [
    ("installer-own-blank", INSTALLER, {"ta/test-design-epic-1.md": BLANK}, [("blank_pxi_score", "ta/test-design-epic-1.md:3")]),
    ("none", TA, {}, []),
    ("epic-9-scored", TA, {"ta/test-design-epic-9.md": SCORED}, []),
    ("epic-9-blank", TA, {"ta/test-design-epic-9.md": BLANK}, []),
    ("own-blank-nfr", TA, {"ta/test-design-epic-1.md": BLANK, "ta/nfr-assessment.md": NFR},
     [("blank_pxi_score", "ta/test-design-epic-1.md:3")]),
    ("epic-0-sorts-first", TA,
     {"ta/test-design-epic-0.md": SCORED, "ta/test-design-epic-1.md": BLANK, "ta/nfr-assessment.md": NFR},
     [("blank_pxi_score", "ta/test-design-epic-1.md:3")]),
    ("architecture-sorts-first", TA,
     {"ta/test-design-architecture.md": BLANK, "ta/test-design-epic-1.md": BLANK, "ta/nfr-assessment.md": NFR},
     [("blank_pxi_score", "ta/test-design-epic-1.md:3")]),
]


@pytest.mark.parametrize(("config", "files", "expected"), [r[1:] for r in _ROWS], ids=[r[0] for r in _ROWS])
def test_the_issue_rows(tmp_path, config, files, expected):
    out = _run(_project(tmp_path, files, config))
    assert _tea(out) == expected
    assert out["verdict"] == "remediable", out["mechanical_gaps"]


@pytest.mark.parametrize("config", [None, "test_framework: pytest\n"], ids=["no-config", "neither-key"])
def test_the_default_root_is_read(tmp_path, config):
    files = {"_bmad-output/test-artifacts/test-design-epic-1.md": BLANK}
    out = _run(_project(tmp_path, files, config))
    assert _tea(out) == [("blank_pxi_score", "_bmad-output/test-artifacts/test-design-epic-1.md:3")]


_NOT_THE_EPICS = (
    "ta/test-design-epic-10.md", "ta/test-design-epic-11.md", "ta/test-design-epic-1-2.md",
    "ta/test-design-epic-01.md", "ta/test-design-epic-1-old.md", "ta/test-design-architecture.md",
    "ta/test-design-qa.md", "ta/test-design-progress-epic-1.md", "ta/test-design-progress.md",
    "ta/test-design-validation-report-epic-1-20261104.md", "ta/test-design/proj-handoff.md",
    "ta/test-design-epic-cross-session-recall-local-store.md",
)


def test_only_the_epics_own_plan_is_read(tmp_path):
    files = {rel: BLANK + "\nLatency budget: 200 ms.\n" for rel in _NOT_THE_EPICS}
    out = _run(_project(tmp_path / "p", files))
    assert _tea(out) == []
    empty = _run(_project(tmp_path / "e", {}))
    assert out["timing"]["artifact_count"] == empty["timing"]["artifact_count"]
    # The same tree read for Epic 10 reads its plan alone.
    assert _tea(_run(tmp_path / "p", epic="10")) == [
        ("blank_pxi_score", "ta/test-design-epic-10.md:3"),
        ("invented_nfr_threshold", "ta/test-design-epic-10.md:5"),
    ]


def test_every_copy_below_the_root_is_read(tmp_path):
    files = {rel: BLANK for rel in ("ta/test-design-epic-1.md", "ta/test-design/test-design-epic-1.md",
                                    "ta/traceability/test-design-epic-1.md")}
    out = _run(_project(tmp_path, files, INSTALLER))
    assert _tea(out) == [
        ("blank_pxi_score", "ta/test-design/test-design-epic-1.md:3"),
        ("blank_pxi_score", "ta/test-design-epic-1.md:3"),
        ("blank_pxi_score", "ta/traceability/test-design-epic-1.md:3"),
    ]


def test_the_name_is_compared_without_case(tmp_path):
    out = _run(_project(tmp_path, {"ta/Test-Design-Epic-1.MD": BLANK}))
    assert _tea(out) == [("blank_pxi_score", "ta/Test-Design-Epic-1.MD:3")]


def test_an_unreadable_plan_is_a_failing_gap(tmp_path):
    out = _run(_project(tmp_path, {"ta/test-design-epic-1.md": b"\xff\xfe risk \x80\n"}))
    assert _tea(out) == [("unreadable_tea_artifact", "ta/test-design-epic-1.md")]
    assert out["verdict"] == "blocked"


def test_a_missing_nfr_assessment_is_no_gap(tmp_path):
    out = _run(_project(tmp_path, {"ta/test-design-epic-1.md": SCORED}))
    assert _tea(out) == []
    assert out["verdict"] == "remediable"


_STORY_LINES = [
    ("story-1-1", "**Story:** 1-1\n", True),
    ("story-1.1", "**Story:** 1.1\n", True),
    ("story-id-key", "story_id: '1-1-login'\n", True),
    ("other-epic", "**Story:** 9-1\n", False),
    ("done-story", "**Story:** 1-0\n", False),
    ("epic-only", "**Story:** 1\n", False),
    ("neighbour", "**Story:** 1-10\n", False),
    ("placeholder", "**Story:** {STORY_ID} (if applicable)\n", False),
    ("no-line", "", False),
]


@pytest.mark.parametrize(("line", "read"), [s[1:] for s in _STORY_LINES], ids=[s[0] for s in _STORY_LINES])
def test_an_nfr_assessment_is_read_only_when_it_names_an_in_scope_story(tmp_path, line, read):
    files = {"ta/test-design-epic-1.md": SCORED, "ta/nfr-assessment.md": line + NFR_UNKNOWN}
    found = _tea(_run(_project(tmp_path, files)))
    row = 5 + (1 if line else 0)
    assert found == ([("nfr_pass_on_unknown", "ta/nfr-assessment.md:%d" % row)] if read else [])


def test_an_nfr_assessment_is_read_against_the_story_scope(tmp_path):
    # Two open stories; `--story 1-1-login` drives only the first, so an
    # assessment of the second raises nothing, and one of the first still does.
    root = _project(tmp_path, {"ta/test-design-epic-1.md": SCORED, "ta/nfr-assessment.md": "**Story:** 1-2\n" + NFR_UNKNOWN})
    status = root / "impl-artifacts" / "sprint-status.yaml"
    status.write_text(status.read_text(encoding="utf-8").replace(
        "  1-1-login: backlog\n", "  1-1-login: backlog\n  1-2-signup: backlog\n"), encoding="utf-8")
    (root / "impl-artifacts" / "1-2-signup.md").write_text(STORY, encoding="utf-8")
    assert _tea(_run(root)) == [("nfr_pass_on_unknown", "ta/nfr-assessment.md:6")]
    assert _tea(_run(root, stories=("1-1-login",))) == []
    (root / "ta" / "nfr-assessment.md").write_text("**Story:** 1-1\n" + NFR_UNKNOWN, encoding="utf-8")
    assert _tea(_run(root, stories=("1-1-login",))) == [("nfr_pass_on_unknown", "ta/nfr-assessment.md:6")]


def test_an_unreadable_nfr_assessment_beside_the_plan_is_a_failing_gap(tmp_path):
    files = {"ta/test-design-epic-1.md": SCORED, "ta/nfr-assessment.md": b"**Story:** 1-1\n| note | caf\xe9 |\n"}
    out = _run(_project(tmp_path, files))
    assert _tea(out) == [("unreadable_tea_artifact", "ta/nfr-assessment.md")]
    assert out["verdict"] == "blocked"
    # Without the Epic's plan no assessment is read, so it raises nothing.
    other = _run(_project(tmp_path / "other", {"ta/test-design-epic-9.md": SCORED, "ta/nfr-assessment.md": files["ta/nfr-assessment.md"]}))
    assert _tea(other) == []


def test_no_nfr_assessment_is_read_without_the_epics_plan(tmp_path):
    files = {"ta/test-design-epic-9.md": SCORED, "ta/nfr-assessment.md": "**Story:** 1-1\n" + NFR_UNKNOWN}
    assert _tea(_run(_project(tmp_path, files))) == []


TEA_TABLE = (
    "### High-Priority Risks\n\n"
    "| Risk ID | Category | Description | Probability | Impact | Score | Mitigation |\n"
    "| --- | --- | --- | ---: | ---: | ---: | --- |\n"
    "| R-01 | SEC | a | 3 | 2 |  | m |\n"
    "| R-02 | TECH | b | 2 | 2 | **5** | m |\n"
)


def test_teas_own_risk_table_headers_are_read(tmp_path):
    out = _run(_project(tmp_path, {"ta/test-design-epic-1.md": TEA_TABLE}))
    assert _tea(out) == [("blank_pxi_score", "ta/test-design-epic-1.md:5"),
                         ("risk_score_conflict", "ta/test-design-epic-1.md:6")]
    assert [g["recomputed"] for g in out["mechanical_gaps"] if g["kind"] == "blank_pxi_score"] == [6]


def test_backticks_and_bold_are_stripped_from_cells_and_headers(tmp_path):
    plan = (
        "| Risk ID | Category | Description | **Probability** | `Impact` | **Score** | Mitigation |\n"
        "| --- | --- | --- | ---: | ---: | ---: | --- |\n"
        "| R-01 | SEC | a | `3` | `2` | `5` | m |\n"
        "| R-02 | TECH | b | **2** | **3** |  | m |\n"
    )
    out = _run(_project(tmp_path, {"ta/test-design-epic-1.md": plan}))
    assert _tea(out) == [("blank_pxi_score", "ta/test-design-epic-1.md:4"),
                         ("risk_score_conflict", "ta/test-design-epic-1.md:3")]


# GFM makes a row's outer pipes optional: a row that drops one stays in its table.
_PIPELESS = [
    ("no-trailing-pipe-p-i",
     "| Risk ID | Category | P | I | Score | Mitigation |\n|---|---|---|---|---|---|\n"
     "| R-1 | TECH | 2 | 2 | 4 | x\n| R-2 | SEC | 3 | 2 |  | y |\n| R-3 | OPS | 3 | 3 | 6 | z |\n"),
    ("no-trailing-pipe-tea",
     "| Risk ID | Category | Description | Probability | Impact | Score | Mitigation |\n| --- | --- | --- | --- | --- | --- | --- |\n"
     "| R-1 | TECH | a | 2 | 2 | 4 | x\n| R-2 | SEC | b | 3 | 2 |  | y |\n| R-3 | OPS | c | 3 | 3 | 6 | z |\n"),
    ("no-outer-pipes",
     "Risk ID | Category | P | I | Score | Mitigation\n---|---|---|---|---|---\n"
     "R-1 | TECH | 2 | 2 | 4 | x\nR-2 | SEC | 3 | 2 |  | y\nR-3 | OPS | 3 | 3 | 6 | z\n"),
]


@pytest.mark.parametrize("plan", [p[1] for p in _PIPELESS], ids=[p[0] for p in _PIPELESS])
def test_a_row_without_outer_pipes_stays_in_its_table(tmp_path, plan):
    out = _run(_project(tmp_path, {"ta/test-design-epic-1.md": plan}))
    assert _tea(out) == [("blank_pxi_score", "ta/test-design-epic-1.md:4"),
                         ("risk_score_conflict", "ta/test-design-epic-1.md:5")]


def test_each_table_is_read_under_its_own_header(tmp_path):
    plan = SCORED + "\n## Effort\n\n| Priority | Count | Hours | Days | Total | Notes |\n|--|--|--|--|--|--|\n" \
        "| P0 | 3 | 2 | 1 | 7 | x |\n| P1 | 4 | 5 | 2 |  | y |\n"
    assert _tea(_run(_project(tmp_path, {"ta/test-design-epic-1.md": plan}))) == []


def test_a_set_trace_output_inside_impl_artifacts_is_no_leak(tmp_path):
    files = {"impl-artifacts/traceability/trace-1-1.md": "# trace\n"}
    out = _run(_project(tmp_path / "set", files, TA + "trace_output: impl-artifacts/traceability\n"))
    assert _tea(out) == []
    out = _run(_project(tmp_path / "unset", files, TA))
    assert _tea(out) == [("leaked_tea_artifact", "impl-artifacts/traceability/trace-1-1.md")]


def test_the_default_root_inside_impl_artifacts_is_no_leak(tmp_path):
    files = {"_bmad-output/test-artifacts/trace-1-1.md": "# trace\n", "_bmad-output/stray/trace-1-1.md": "# trace\n"}
    out = _run(_project(tmp_path, files, None, impl="_bmad-output"), impl="_bmad-output")
    assert _tea(out) == [("leaked_tea_artifact", "_bmad-output/stray/trace-1-1.md")]
