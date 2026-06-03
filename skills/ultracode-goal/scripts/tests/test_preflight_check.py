#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for preflight_check.py.

Covers the green-vs-blockers contract: a fully-prepared tree returns green with
budget 0, and each mechanical fault (stale primitive versions, missing test
framework, dirty tree, protected branch, broken git) surfaces exactly the
expected blocker and increments the budget. Also covers TEA-flag parsing
(YAML scalars) and the CLI exit codes.

The `claude --version` shell-out is monkeypatched so version-gate behavior is
deterministic regardless of the host. git is exercised against real temp repos.

Run: uv run -m pytest   (from the scripts/ directory, or point pytest at this file)
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "preflight_check.py"

# git env vars that, if inherited from the host (e.g. a git hook context), would
# point every `git` invocation below at the live repo instead of the temp repos
# these tests create — making the fixtures depend on the runner's git state.
_GIT_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
)


@pytest.fixture(autouse=True)
def _hermetic_git_env(monkeypatch):
    """Scrub inherited GIT_* env so git runs against the temp repos, not the host."""
    for var in _GIT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/")


def _load_module():
    spec = importlib.util.spec_from_file_location("preflight_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


pf = _load_module()


# --- Fixtures: a synthesized, git-backed project tree ----------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A green-ready project: git repo on a feature branch, clean, framework + dirs + config."""
    root = tmp_path / "proj"
    root.mkdir()

    # git repo on a non-protected branch with a clean tree.
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    _git(root, "checkout", "-q", "-b", "ultracode/epic-7")

    # Scaffolded test framework.
    (root / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")

    # TEA config (YAML) + the artifact dirs it points at.
    tea = root / "_bmad" / "tea"
    tea.mkdir(parents=True)
    (tea / "config.yaml").write_text(
        "test_artifacts: \"{project-root}/_bmad-output/test-artifacts\"\n"
        "tea_execution_mode: auto\n"
        "test_framework: auto\n"
        "ci_platform: auto\n"
        "risk_threshold: p1\n"
        "tea_capability_probe: true\n",
        encoding="utf-8",
    )
    artifacts = root / "_bmad-output" / "test-artifacts"
    for sub in ("test-design", "test-reviews", "traceability"):
        (artifacts / sub).mkdir(parents=True)

    # sprint-status.yaml + a project-context.md.
    impl = root / "_bmad-output" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "sprint-status.yaml").write_text("development_status:\n  epic-7: backlog\n", encoding="utf-8")
    (root / "project-context.md").write_text("# ctx\n", encoding="utf-8")

    # Commit all scaffolding so the green-path tree is genuinely clean.
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "scaffold")

    return root


def _report(project: Path, monkeypatch, version="2.1.200", protected=("main", "master")):
    """Build a report with a controlled cc version."""
    parsed = pf._parse_semver(version) if version else None
    monkeypatch.setattr(pf, "_cc_version", lambda: (version, parsed))
    return pf.build_report(
        project_root=project.resolve(),
        epic="7",
        tea_config=project / "_bmad" / "tea" / "config.yaml",
        impl_artifacts=project / "_bmad-output" / "implementation-artifacts",
        protected_branches=protected,
    )


def _blocker_ids(report: dict) -> set[str]:
    return {b["id"] for b in report["blockers"]}


# --- Green path -------------------------------------------------------------


def test_green_when_fully_prepared(project, monkeypatch):
    report = _report(project, monkeypatch)
    assert report["green"] is True
    assert report["budget"] == 0
    assert report["blockers"] == []


def test_green_report_checks_are_populated(project, monkeypatch):
    checks = _report(project, monkeypatch)["checks"]
    assert checks["goal_ok"] and checks["workflows_ok"] and checks["automemory_ok"]
    assert checks["git_branch"] == "ultracode/epic-7"
    assert checks["git_clean"] is True
    assert checks["framework_present"] is True
    assert checks["sprint_status_present"] is True
    assert checks["project_context_count"] == 1
    assert checks["test_artifacts_dirs"] == {
        "test-design": True,
        "test-reviews": True,
        "traceability": True,
    }


def test_green_invariant_budget_equals_blocker_count(project, monkeypatch):
    report = _report(project, monkeypatch)
    assert report["budget"] == len(report["blockers"])
    assert report["green"] is (report["budget"] == 0)


# --- Version gate -----------------------------------------------------------


@pytest.mark.parametrize(
    "version,expect_goal,expect_wf,expect_am",
    [
        ("2.1.200", True, True, True),     # all above minimums
        ("2.1.139", True, False, True),    # exactly /goal min; below workflows
        ("2.1.154", True, True, True),     # exactly workflows min
        ("2.1.59", False, False, True),    # exactly auto-memory min; below others
        ("2.1.0", False, False, False),    # below everything
    ],
)
def test_version_flags(project, monkeypatch, version, expect_goal, expect_wf, expect_am):
    checks = _report(project, monkeypatch, version=version)["checks"]
    assert checks["goal_ok"] is expect_goal
    assert checks["workflows_ok"] is expect_wf
    assert checks["automemory_ok"] is expect_am


def test_stale_version_is_a_blocker(project, monkeypatch):
    report = _report(project, monkeypatch, version="2.1.0")
    assert "cc_version" in _blocker_ids(report)
    assert report["green"] is False
    blocker = next(b for b in report["blockers"] if b["id"] == "cc_version")
    assert blocker["remediable"] is False


def test_unreadable_version_is_a_blocker(project, monkeypatch):
    # `claude` not on PATH -> (None, None).
    monkeypatch.setattr(pf, "_cc_version", lambda: (None, None))
    report = pf.build_report(
        project_root=project.resolve(),
        epic="7",
        tea_config=project / "_bmad" / "tea" / "config.yaml",
        impl_artifacts=project / "_bmad-output" / "implementation-artifacts",
        protected_branches=("main", "master"),
    )
    assert "cc_version" in _blocker_ids(report)
    assert report["checks"]["cc_version"] is None


# --- Framework blocker ------------------------------------------------------


def test_missing_framework_is_a_remediable_blocker(project, monkeypatch):
    (project / "playwright.config.ts").unlink()
    report = _report(project, monkeypatch)
    assert "framework_present" in _blocker_ids(report)
    assert report["checks"]["framework_present"] is False
    blocker = next(b for b in report["blockers"] if b["id"] == "framework_present")
    assert blocker["remediable"] is True


# --- Git blockers -----------------------------------------------------------


def test_dirty_tree_is_a_blocker(project, monkeypatch):
    (project / "scratch.txt").write_text("uncommitted\n", encoding="utf-8")
    report = _report(project, monkeypatch)
    assert "git_clean" in _blocker_ids(report)
    assert report["checks"]["git_clean"] is False


def test_protected_branch_is_a_blocker(project, monkeypatch):
    _git(project, "checkout", "-q", "-b", "main")
    report = _report(project, monkeypatch)
    assert "git_branch" in _blocker_ids(report)
    assert report["checks"]["git_branch"] == "main"


def test_non_git_dir_is_a_blocker(tmp_path, monkeypatch):
    bare = tmp_path / "plain"
    bare.mkdir()
    (bare / "_bmad" / "tea").mkdir(parents=True)
    (bare / "_bmad" / "tea" / "config.yaml").write_text("test_framework: auto\n", encoding="utf-8")
    (bare / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    monkeypatch.setattr(pf, "_cc_version", lambda: ("2.1.200", (2, 1, 200)))
    report = pf.build_report(
        project_root=bare.resolve(),
        epic="7",
        tea_config=bare / "_bmad" / "tea" / "config.yaml",
        impl_artifacts=bare / "impl",
        protected_branches=("main", "master"),
    )
    assert "git_repo" in _blocker_ids(report)
    assert report["checks"]["git_clean"] is None


def test_multiple_blockers_accumulate_budget(project, monkeypatch):
    (project / "playwright.config.ts").unlink()
    (project / "scratch.txt").write_text("dirty\n", encoding="utf-8")
    report = _report(project, monkeypatch, version="2.1.0")
    ids = _blocker_ids(report)
    assert {"cc_version", "framework_present", "git_clean"} <= ids
    assert report["budget"] == len(report["blockers"]) >= 3
    assert report["green"] is False


# --- TEA flag parsing -------------------------------------------------------


def test_tea_flags_parsed_from_yaml(project, monkeypatch):
    flags = _report(project, monkeypatch)["checks"]["tea_flags"]
    assert flags["tea_execution_mode"] == "auto"
    assert flags["risk_threshold"] == "p1"
    assert flags["tea_capability_probe"] is True  # bool coerced
    assert flags["test_artifacts"] == "{project-root}/_bmad-output/test-artifacts"


def test_tea_flags_empty_when_config_absent(project, monkeypatch):
    missing = project / "_bmad" / "tea" / "nope.yaml"
    parsed = pf._parse_semver("2.1.200")
    monkeypatch.setattr(pf, "_cc_version", lambda: ("2.1.200", parsed))
    report = pf.build_report(
        project_root=project.resolve(),
        epic="7",
        tea_config=missing,
        impl_artifacts=project / "_bmad-output" / "implementation-artifacts",
        protected_branches=("main", "master"),
    )
    assert report["checks"]["tea_flags"] == {}


def test_tea_artifacts_root_honors_config_override(project, monkeypatch):
    # Point test_artifacts elsewhere; the default dirs should then read as absent.
    (project / "_bmad" / "tea" / "config.yaml").write_text(
        'test_artifacts: "{project-root}/elsewhere"\n', encoding="utf-8"
    )
    report = _report(project, monkeypatch)
    assert report["checks"]["test_artifacts_dirs"] == {
        "test-design": False,
        "test-reviews": False,
        "traceability": False,
    }


# --- CLI plumbing -----------------------------------------------------------


def test_cli_emits_json_and_exit_zero(project):
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--epic",
            "7",
            "--tea-config",
            "{project-root}/_bmad/tea/config.yaml",
            "--impl-artifacts",
            "{project-root}/_bmad-output/implementation-artifacts",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    for key in ("green", "budget", "blockers", "checks"):
        assert key in payload


def test_cli_missing_project_root_exits_two(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(tmp_path / "does-not-exist"),
            "--epic",
            "7",
            "--tea-config",
            "x.yaml",
            "--impl-artifacts",
            "y",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
