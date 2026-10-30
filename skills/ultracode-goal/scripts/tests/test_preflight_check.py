#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for preflight_check.py.

Covers the green-vs-blockers contract: a fully-prepared tree returns green with
budget 0, and each mechanical fault (stale primitive versions, missing test
framework, missing story skills, missing TEA skills for the run's profile,
dirty tree, protected branch, broken git)
surfaces exactly the expected blocker and increments the budget. Also covers TEA-flag parsing
(YAML scalars) and the CLI exit codes.

The `claude --version` shell-out is monkeypatched so version-gate behavior is
deterministic regardless of the host. git is exercised against real temp repos.

Run: uv run -m pytest   (from the scripts/ directory, or point pytest at this file)
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
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


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch) -> Path:
    """Point the home directory at an empty temp dir, so a skill the host
    happens to have under ~/.claude/skills cannot satisfy a case (HOME on
    POSIX, USERPROFILE on Windows: Path.home() reads whichever applies), and
    drop a host CLAUDE_CONFIG_DIR, which would relocate that directory."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return home


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


STORY_SKILLS = ("ucg-create-story", "ucg-dev-story")

# The TEA skills each profile delegates to, written out here rather than read
# from the script, so a change to either set has to change this contract too.
TEA_PRODUCTION = (
    "bmad-testarch-framework",
    "bmad-testarch-ci",
    "bmad-testarch-test-design",
    "bmad-testarch-atdd",
    "bmad-testarch-automate",
    "bmad-testarch-test-review",
    "bmad-testarch-nfr",
    "bmad-testarch-trace",
)
TEA_LIGHT = ("bmad-testarch-framework", "bmad-testarch-test-design", "bmad-testarch-trace")
TEA_BY_PROFILE = {"production": TEA_PRODUCTION, "light": TEA_LIGHT}


def _seed_skills(skills_dir: Path, ids=STORY_SKILLS) -> None:
    for skill_id in ids:
        (skills_dir / skill_id).mkdir(parents=True, exist_ok=True)
        (skills_dir / skill_id / "SKILL.md").write_text(
            f"---\nname: {skill_id}\n---\n", encoding="utf-8"
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

    # The story skills the run delegates to, where UCG's installer copies
    # them for Claude Code, and the TEA 1.27.x skills BMAD's installer puts
    # beside them.
    _seed_skills(root / ".claude" / "skills")
    _seed_skills(root / ".claude" / "skills", ids=TEA_PRODUCTION)

    # Commit all scaffolding so the green-path tree is genuinely clean.
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "scaffold")

    return root


def _report(
    project: Path,
    monkeypatch,
    version="2.1.301",
    protected=("main", "master"),
    profile="production",
):
    """Build a report with a controlled cc version."""
    parsed = pf._parse_semver(version) if version else None
    monkeypatch.setattr(pf, "_cc_version", lambda: (version, parsed))
    return pf.build_report(
        project_root=project.resolve(),
        epic="7",
        tea_config=project / "_bmad" / "tea" / "config.yaml",
        impl_artifacts=project / "_bmad-output" / "implementation-artifacts",
        protected_branches=protected,
        profile=profile,
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
    assert checks["hook_onfailure_ok"] is True
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
    "version,expect_goal,expect_wf,expect_am,expect_hf",
    [
        ("2.1.301", True, True, True, True),      # all above minimums
        ("2.1.295", True, True, True, True),      # exactly the hook onFailure min
        ("2.1.294", True, True, True, False),     # one below it: no onFailure yet
        ("2.1.200", True, True, True, False),     # above the old 2.1.154 floor, still below
        ("2.1.154", True, True, True, False),     # exactly workflows min
        ("2.1.139", True, False, True, False),    # exactly /goal min; below workflows
        ("2.1.59", False, False, True, False),    # exactly auto-memory min; below others
        ("2.1.0", False, False, False, False),    # below everything
        ("2.2.0", True, True, True, True),        # a later minor
    ],
)
def test_version_flags(project, monkeypatch, version, expect_goal, expect_wf, expect_am, expect_hf):
    report = _report(project, monkeypatch, version=version)
    checks = report["checks"]
    assert checks["goal_ok"] is expect_goal
    assert checks["workflows_ok"] is expect_wf
    assert checks["automemory_ok"] is expect_am
    assert checks["hook_onfailure_ok"] is expect_hf
    # Any flag below its minimum is the one cc_version blocker, and nothing else is.
    every = expect_goal and expect_wf and expect_am and expect_hf
    assert ("cc_version" in _blocker_ids(report)) is (not every)
    assert report["green"] is every


def test_below_the_hook_onfailure_minimum_alone_names_that_primitive(project, monkeypatch):
    """2.1.294 has /goal, workflows and auto memory, and drops the hook setting
    `"onFailure": "block"` silently, so a guard that crashes there lets the
    call through. The blocker names that primitive and no other."""
    report = _report(project, monkeypatch, version="2.1.294")
    blocker = next(b for b in report["blockers"] if b["id"] == "cc_version")
    assert blocker["detail"] == "Claude Code 2.1.294 is below the minimum for: hook-onFailure>=2.1.295"
    assert blocker["remediable"] is False
    assert report["budget"] == 1


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


def test_framework_kind_reports_js_config_for_playwright(project, monkeypatch):
    # The green fixture scaffolds playwright.config.ts.
    checks = _report(project, monkeypatch)["checks"]
    assert checks["framework_present"] is True
    assert checks["framework_kind"] == "js-config"


def test_pytest_ini_counts_as_a_framework(project, monkeypatch):
    (project / "playwright.config.ts").unlink()
    (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    report = _report(project, monkeypatch)
    assert report["checks"]["framework_present"] is True
    assert report["checks"]["framework_kind"] == "pytest"
    assert "framework_present" not in _blocker_ids(report)


def test_root_conftest_counts_as_pytest(project, monkeypatch):
    (project / "playwright.config.ts").unlink()
    (project / "conftest.py").write_text("# fixtures\n", encoding="utf-8")
    checks = _report(project, monkeypatch)["checks"]
    assert checks["framework_present"] is True
    assert checks["framework_kind"] == "pytest"


def test_pyproject_pytest_table_counts_as_pytest(project, monkeypatch):
    (project / "playwright.config.ts").unlink()
    (project / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "-q"\n', encoding="utf-8"
    )
    assert _report(project, monkeypatch)["checks"]["framework_kind"] == "pytest"


def test_real_npm_test_script_counts_as_a_framework(project, monkeypatch):
    (project / "playwright.config.ts").unlink()
    (project / "package.json").write_text(
        json.dumps({"scripts": {"test": "uv run pytest && node test/cli.js"}}),
        encoding="utf-8",
    )
    report = _report(project, monkeypatch)
    assert report["checks"]["framework_present"] is True
    assert report["checks"]["framework_kind"] == "npm-test"
    assert "framework_present" not in _blocker_ids(report)


def test_npm_init_placeholder_test_script_does_not_count(project, monkeypatch):
    (project / "playwright.config.ts").unlink()
    (project / "package.json").write_text(
        json.dumps({"scripts": {"test": 'echo "Error: no test specified" && exit 1'}}),
        encoding="utf-8",
    )
    report = _report(project, monkeypatch)
    assert report["checks"]["framework_present"] is False
    assert report["checks"]["framework_kind"] is None
    assert "framework_present" in _blocker_ids(report)


def test_no_harness_at_all_reports_kind_none(project, monkeypatch):
    (project / "playwright.config.ts").unlink()
    report = _report(project, monkeypatch)
    assert report["checks"]["framework_present"] is False
    assert report["checks"]["framework_kind"] is None
    assert "framework_present" in _blocker_ids(report)


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


def _unborn_project(tmp_path: Path, branch: str, *, hide_scaffold: bool) -> Path:
    """The green-ready scaffold in a fresh `git init` with nothing committed.

    `hide_scaffold` lists every path in `.git/info/exclude`, so the tree reads
    clean and the case cannot ride on `git_clean`: an unborn HEAD has to stop
    the run on its own.
    """
    root = tmp_path / "unborn"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "symbolic-ref", "HEAD", f"refs/heads/{branch}")
    (root / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    tea = root / "_bmad" / "tea"
    tea.mkdir(parents=True)
    (tea / "config.yaml").write_text("test_framework: auto\n", encoding="utf-8")
    impl = root / "_bmad-output" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "sprint-status.yaml").write_text("development_status:\n  epic-7: backlog\n", encoding="utf-8")
    _seed_skills(root / ".claude" / "skills")
    _seed_skills(root / ".claude" / "skills", ids=TEA_PRODUCTION)
    if hide_scaffold:
        (root / ".git" / "info").mkdir(parents=True, exist_ok=True)
        (root / ".git" / "info" / "exclude").write_text("*\n", encoding="utf-8")
    return root


def test_unborn_protected_branch_raises_the_branch_and_unborn_blockers(tmp_path, monkeypatch):
    root = _unborn_project(tmp_path, "main", hide_scaffold=True)
    report = _report(root, monkeypatch)
    ids = _blocker_ids(report)
    assert report["checks"]["git_unborn"] is True
    assert report["checks"]["git_branch"] == "main"
    assert report["checks"]["git_clean"] is True
    assert {"git_unborn", "git_branch"} <= ids
    unborn = next(b for b in report["blockers"] if b["id"] == "git_unborn")
    assert unborn["remediable"] is False
    assert "'main'" in unborn["detail"]
    assert report["green"] is False


def test_unborn_epic_branch_raises_the_unborn_blocker_only(tmp_path, monkeypatch):
    root = _unborn_project(tmp_path, "ultracode/epic-7", hide_scaffold=True)
    report = _report(root, monkeypatch)
    ids = _blocker_ids(report)
    assert report["checks"]["git_branch"] == "ultracode/epic-7"
    assert "git_unborn" in ids
    assert "git_branch" not in ids
    assert report["green"] is False
    # The baseline belongs on the protected base, never on the unborn Epic
    # branch, where it would become that branch's root with nothing under it.
    detail = next(b for b in report["blockers"] if b["id"] == "git_unborn")["detail"]
    assert "`git symbolic-ref HEAD refs/heads/main`" in detail
    assert "never commit the baseline on an Epic branch" in detail


def test_dirty_unborn_repo_raises_unborn_and_clean(tmp_path, monkeypatch):
    root = _unborn_project(tmp_path, "main", hide_scaffold=False)
    ids = _blocker_ids(_report(root, monkeypatch))
    assert {"git_unborn", "git_clean", "git_branch"} <= ids


def test_committed_repo_is_not_unborn(project, monkeypatch):
    report = _report(project, monkeypatch)
    assert report["checks"]["git_unborn"] is False
    assert "git_unborn" not in _blocker_ids(report)


def test_non_git_dir_is_a_blocker(tmp_path, monkeypatch):
    bare = tmp_path / "plain"
    bare.mkdir()
    (bare / "_bmad" / "tea").mkdir(parents=True)
    (bare / "_bmad" / "tea" / "config.yaml").write_text("test_framework: auto\n", encoding="utf-8")
    (bare / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    monkeypatch.setattr(pf, "_cc_version", lambda: ("2.1.301", (2, 1, 301)))
    report = pf.build_report(
        project_root=bare.resolve(),
        epic="7",
        tea_config=bare / "_bmad" / "tea" / "config.yaml",
        impl_artifacts=bare / "impl",
        protected_branches=("main", "master"),
    )
    assert "git_repo" in _blocker_ids(report)
    assert report["checks"]["git_clean"] is None
    # Outside a repository the unborn probe exits 128, not 1: no unborn
    # blocker rides along with git_repo.
    assert report["checks"]["git_unborn"] is False
    assert "git_unborn" not in _blocker_ids(report)


def test_multiple_blockers_accumulate_budget(project, monkeypatch):
    (project / "playwright.config.ts").unlink()
    (project / "scratch.txt").write_text("dirty\n", encoding="utf-8")
    report = _report(project, monkeypatch, version="2.1.0")
    ids = _blocker_ids(report)
    assert {"cc_version", "framework_present", "git_clean"} <= ids
    assert report["budget"] == len(report["blockers"]) >= 3
    assert report["green"] is False


# --- Story skills -----------------------------------------------------------
# The run delegates story creation and implementation to ucg-create-story and
# ucg-dev-story, which UCG's installer copies beside the ultracode-goal skill.
# A partial or older UCG install lacks them, and their absence has to stop the
# launch rather than surface mid-run.


def _skills_blocker(report: dict) -> dict:
    hits = [b for b in report["blockers"] if b["id"] == "story_skills"]
    assert len(hits) == 1, report["blockers"]
    return hits[0]


def test_missing_story_skill_is_a_non_remediable_blocker(project, monkeypatch):
    shutil.rmtree(project / ".claude" / "skills" / "ucg-dev-story")
    report = _report(project, monkeypatch)
    blocker = _skills_blocker(report)
    assert blocker["kind"] == "dependency"
    assert blocker["severity"] == "high"
    # The remediation pass cannot install the skills; the operator does.
    assert blocker["remediable"] is False
    # Only the missing skill is named as missing.
    assert blocker["detail"].startswith("UCG story skill(s) not installed: ucg-dev-story.")
    assert report["checks"]["story_skills"] == {
        "ucg-create-story": True,
        "ucg-dev-story": False,
    }
    assert report["green"] is False
    assert report["budget"] == len(report["blockers"])


def test_present_story_skills_raise_no_blocker(project, monkeypatch):
    # Anti-vacuous twin of the case above: the same tree with both skills in
    # place carries no story_skills blocker.
    report = _report(project, monkeypatch)
    assert "story_skills" not in _blocker_ids(report)
    assert report["checks"]["story_skills"] == {
        "ucg-create-story": True,
        "ucg-dev-story": True,
    }


def test_a_skill_dir_without_skill_md_is_not_installed(project, monkeypatch):
    (project / ".claude" / "skills" / "ucg-create-story" / "SKILL.md").unlink()
    blocker = _skills_blocker(_report(project, monkeypatch))
    assert blocker["detail"].startswith("UCG story skill(s) not installed: ucg-create-story.")


def test_a_personal_skill_counts_as_installed(project, monkeypatch, _isolated_home):
    shutil.rmtree(project / ".claude" / "skills" / "ucg-dev-story")
    _seed_skills(_isolated_home / ".claude" / "skills", ids=("ucg-dev-story",))
    report = _report(project, monkeypatch)
    assert "story_skills" not in _blocker_ids(report)
    assert report["checks"]["story_skills"]["ucg-dev-story"] is True


def test_a_relocated_config_dir_replaces_the_personal_root(
    project, monkeypatch, tmp_path, _isolated_home
):
    # With CLAUDE_CONFIG_DIR set, Claude Code keeps its home-directory files
    # there, so a skill under it counts and one left in ~/.claude does not.
    shutil.rmtree(project / ".claude" / "skills" / "ucg-dev-story")
    config = tmp_path / "claude-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    _seed_skills(_isolated_home / ".claude" / "skills", ids=("ucg-dev-story",))
    assert _report(project, monkeypatch)["checks"]["story_skills"]["ucg-dev-story"] is False
    _seed_skills(config / "skills", ids=("ucg-dev-story",))
    report = _report(project, monkeypatch)
    assert "story_skills" not in _blocker_ids(report)


def test_an_unexpandable_config_dir_still_returns_a_report(project, monkeypatch):
    # Claude Code takes CLAUDE_CONFIG_DIR as given; expanding a ~user this
    # machine does not have would raise and lose the whole payload.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "~nosuchuser_zz/claude")
    shutil.rmtree(project / ".claude" / "skills" / "ucg-dev-story")
    report = _report(project, monkeypatch)
    assert report["checks"]["story_skills"]["ucg-dev-story"] is False
    assert "~nosuchuser_zz" in _skills_blocker(report)["detail"]


@pytest.mark.skipif(
    sys.platform == "win32" or not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="needs POSIX permissions enforced for a non-root user",
)
def test_an_untraversable_personal_root_still_reports_the_blocker(
    project, monkeypatch, _isolated_home
):
    shutil.rmtree(project / ".claude" / "skills" / "ucg-dev-story")
    locked = _isolated_home / ".claude"
    locked.mkdir()
    locked.chmod(0)
    try:
        report = _report(project, monkeypatch)
    finally:
        locked.chmod(0o755)
    assert report["checks"]["story_skills"]["ucg-dev-story"] is False
    assert _skills_blocker(report)["remediable"] is False


def test_missing_story_skills_name_the_ucg_reinstall(project, monkeypatch):
    shutil.rmtree(project / ".claude" / "skills")
    report = _report(project, monkeypatch)
    detail = _skills_blocker(report)["detail"]
    assert detail.startswith("UCG story skill(s) not installed: ucg-create-story, ucg-dev-story.")
    assert "`npx bmad-module-ultracode-goal update`" in detail
    # The deprecated BMAD shims the skills were adapted from are no fix.
    assert "--shims" not in detail
    assert "\n" not in detail  # headless `reason` flattens the first blocker to one line


def test_bmad_shims_do_not_stand_in_for_the_ucg_story_skills(project, monkeypatch):
    # Twin of the present-skills case: BMAD's own bmad-create-story and
    # bmad-dev-story (installed with --shims) in place of UCG's two skills
    # still leave the run without the skills it delegates to.
    for skill_id in STORY_SKILLS:
        shutil.rmtree(project / ".claude" / "skills" / skill_id)
    _seed_skills(project / ".claude" / "skills", ids=("bmad-create-story", "bmad-dev-story"))
    report = _report(project, monkeypatch)
    assert _skills_blocker(report)["remediable"] is False
    assert report["checks"]["story_skills"] == {"ucg-create-story": False, "ucg-dev-story": False}


# --- TEA skills -------------------------------------------------------------
# The run delegates test design, ATDD, review and the gate to TEA's
# bmad-testarch-* skills, which TEA 1.27.x installs and TEA 3.0 renamed to
# bmad-tea-*. A missing one has to stop the launch, not escalate mid-run, and
# the light profile needs fewer of them than production.

_SUPPORTED = "UCG supports BMAD 6 with TEA 1.27.x"
# Only TEA 3.0 renamed the skills, so finding the new names says 3.0 or later.
# TEA 2.x moved to BMAD 7's module format but kept the bmad-testarch-* names.
_RENAMED = "that looks like TEA 3.0 or later, which renamed these skills and which UCG does not support yet"


def _tea_blocker(report: dict) -> dict:
    hits = [b for b in report["blockers"] if b["id"] == "tea_skills"]
    assert len(hits) == 1, report["blockers"]
    return hits[0]


def _remove_skills(project: Path, ids) -> None:
    for skill_id in ids:
        shutil.rmtree(project / ".claude" / "skills" / skill_id)


@pytest.mark.parametrize("profile", ["production", "light"])
def test_present_tea_skills_raise_no_blocker(project, monkeypatch, profile):
    report = _report(project, monkeypatch, profile=profile)
    assert report["green"] is True
    assert "tea_skills" not in _blocker_ids(report)
    # The check reports exactly the profile's skills, in delegation order.
    assert report["checks"]["tea_skills"] == {s: True for s in TEA_BY_PROFILE[profile]}
    assert list(report["checks"]["tea_skills"]) == list(TEA_BY_PROFILE[profile])


@pytest.mark.parametrize(
    "profile,skill_id",
    [(p, s) for p, skills in TEA_BY_PROFILE.items() for s in skills],
)
def test_one_missing_tea_skill_is_a_non_remediable_blocker(project, monkeypatch, profile, skill_id):
    _remove_skills(project, [skill_id])
    report = _report(project, monkeypatch, profile=profile)
    blocker = _tea_blocker(report)
    assert blocker["kind"] == "dependency"
    assert blocker["severity"] == "high"
    # The run cannot install TEA, and no other skill writes what TEA writes.
    assert blocker["remediable"] is False
    # Only the missing skill is named as missing.
    assert blocker["detail"].startswith(
        "TEA skill(s) the %s profile delegates to not installed: %s." % (profile, skill_id)
    )
    assert _SUPPORTED in blocker["detail"]
    assert _RENAMED not in blocker["detail"]
    assert "TEA 2.0" not in blocker["detail"]
    assert "\n" not in blocker["detail"]  # headless `reason` flattens a blocker to one line
    assert report["checks"]["tea_skills"][skill_id] is False
    assert sum(not v for v in report["checks"]["tea_skills"].values()) == 1
    assert report["green"] is False
    assert report["budget"] == len(report["blockers"])


def test_light_does_not_require_the_production_only_tea_skills(project, monkeypatch):
    # The light profile skips ci, ATDD, automate, test-review and NFR, so a
    # project without them can run under --light, and not under production.
    production_only = [s for s in TEA_PRODUCTION if s not in TEA_LIGHT]
    assert len(production_only) == 5
    _remove_skills(project, production_only)
    light = _report(project, monkeypatch, profile="light")
    assert "tea_skills" not in _blocker_ids(light)
    production = _report(project, monkeypatch, profile="production")
    assert _tea_blocker(production)["detail"].startswith(
        "TEA skill(s) the production profile delegates to not installed: %s."
        % ", ".join(production_only)
    )


def test_tea_absent_entirely_names_every_skill_and_the_fix(project, monkeypatch):
    _remove_skills(project, TEA_PRODUCTION)
    for profile, skills in TEA_BY_PROFILE.items():
        report = _report(project, monkeypatch, profile=profile)
        detail = _tea_blocker(report)["detail"]
        assert detail.startswith(
            "TEA skill(s) the %s profile delegates to not installed: %s."
            % (profile, ", ".join(skills))
        )
        assert report["checks"]["tea_skills"] == {s: False for s in skills}
        assert _SUPPORTED in detail
        assert "`npx bmad-method install`, module `tea`" in detail
        # Only BMAD Method 6.12.2 and later pin TEA at 1.27.2; an older BMAD 6
        # installer takes the newest TEA tag.
        assert "with BMAD Method 6.12.2 or later" in detail
        assert "an older BMAD 6 installer can pick a later TEA" in detail
        assert "the run never installs TEA itself" in detail
        assert _RENAMED not in detail
        # The story skills are a separate blocker, still satisfied here.
        assert "story_skills" not in _blocker_ids(report)


@pytest.mark.parametrize("profile", ["production", "light"])
def test_renamed_tea_skills_read_as_tea_3_or_later(project, monkeypatch, profile):
    # TEA 3.0 publishes the skills UCG calls as bmad-tea-*, so a project on it
    # has those and none of the bmad-testarch-* names.
    _remove_skills(project, TEA_PRODUCTION)
    renamed = ("bmad-tea-atdd", "bmad-tea-trace", "bmad-tea-test-design")
    _seed_skills(project / ".claude" / "skills", ids=renamed)
    report = _report(project, monkeypatch, profile=profile)
    blocker = _tea_blocker(report)
    detail = blocker["detail"]
    assert detail.startswith(
        "TEA skill(s) the %s profile delegates to not installed: %s."
        % (profile, ", ".join(TEA_BY_PROFILE[profile]))
    )
    assert "Found %s instead: %s." % (", ".join(sorted(renamed)), _RENAMED) in detail
    assert _SUPPORTED in detail
    assert blocker["remediable"] is False
    assert "\n" not in detail


def test_renamed_tea_skills_in_the_personal_root_are_named(project, monkeypatch, _isolated_home):
    _remove_skills(project, TEA_PRODUCTION)
    _seed_skills(_isolated_home / ".claude" / "skills", ids=("bmad-tea-trace",))
    detail = _tea_blocker(_report(project, monkeypatch, profile="light"))["detail"]
    assert "Found bmad-tea-trace instead: %s." % _RENAMED in detail


def test_tea_1_27_agent_skills_alone_are_not_read_as_the_rename(project, monkeypatch):
    # Anti-vacuous twin of the rename case: TEA 1.27.x's own bmad-tea agent and
    # bmad-teach-me-testing share the prefix up to "bmad-tea" but are not the
    # renamed skills, and a bmad-tea-* directory without SKILL.md is no skill.
    _remove_skills(project, TEA_PRODUCTION)
    _seed_skills(project / ".claude" / "skills", ids=("bmad-tea", "bmad-teach-me-testing"))
    (project / ".claude" / "skills" / "bmad-tea-atdd").mkdir()
    detail = _tea_blocker(_report(project, monkeypatch))["detail"]
    assert _RENAMED not in detail
    assert "Found " not in detail


def test_the_tea_skill_sets_cover_every_delegate_the_prose_names():
    # The skill and its stage references are where the run's delegates are
    # named. A new bmad-testarch-* delegate there must reach the check too, and
    # light must stay a subset of production.
    import re

    skill_root = SCRIPT.parent.parent
    texts = [skill_root / "SKILL.md", *sorted((skill_root / "references").glob("*.md"))]
    named = set()
    for path in texts:
        named |= set(re.findall(r"bmad-testarch-[a-z]+(?:-[a-z]+)*", path.read_text(encoding="utf-8")))
    assert named == set(TEA_PRODUCTION)
    assert pf.TEA_SKILLS == {"production": TEA_PRODUCTION, "light": TEA_LIGHT}
    assert set(TEA_LIGHT) < set(TEA_PRODUCTION)


def test_cli_profile_picks_the_tea_skills(project):
    _remove_skills(project, [s for s in TEA_PRODUCTION if s not in TEA_LIGHT])
    base = [
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
    ]
    results = {}
    for profile in (None, "production", "light"):
        argv = base + (["--profile", profile] if profile else [])
        proc = subprocess.run(argv, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        results[profile] = json.loads(proc.stdout)
    # Production is the default, as it is the run's.
    assert results[None]["checks"]["tea_skills"] == results["production"]["checks"]["tea_skills"]
    assert "tea_skills" in _blocker_ids(results["production"])
    assert "tea_skills" not in _blocker_ids(results["light"])
    assert list(results["light"]["checks"]["tea_skills"]) == list(TEA_LIGHT)
    bad = subprocess.run(base + ["--profile", "fast"], capture_output=True, text=True)
    assert bad.returncode == 2
    assert "--profile" in bad.stderr


# --- TEA flag parsing -------------------------------------------------------


def test_tea_flags_parsed_from_yaml(project, monkeypatch):
    flags = _report(project, monkeypatch)["checks"]["tea_flags"]
    assert flags["tea_execution_mode"] == "auto"
    assert flags["risk_threshold"] == "p1"
    assert flags["tea_capability_probe"] is True  # bool coerced
    assert flags["test_artifacts"] == "{project-root}/_bmad-output/test-artifacts"


def test_tea_flags_empty_when_config_absent(project, monkeypatch):
    missing = project / "_bmad" / "tea" / "nope.yaml"
    parsed = pf._parse_semver("2.1.301")
    monkeypatch.setattr(pf, "_cc_version", lambda: ("2.1.301", parsed))
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


def test_cli_normal_mode_requires_epic_and_tea_config(tmp_path):
    # Regression: outside rollup mode, --epic and --tea-config stay required and
    # argparse's "the following arguments are required" error / exit 2 is kept.
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(tmp_path),
            "--impl-artifacts",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "the following arguments are required" in proc.stderr
    assert "--epic" in proc.stderr
    assert "--tea-config" in proc.stderr


# --- Rollup mode ------------------------------------------------------------


def _write_sprint_status(impl_artifacts: Path, body: str) -> None:
    impl_artifacts.mkdir(parents=True, exist_ok=True)
    (impl_artifacts / "sprint-status.yaml").write_text(body, encoding="utf-8")


# A multi-epic sprint-status.yaml in BMad's shape: a flat development_status map
# of story rows (e.g. 1-1-foo: done) alongside epic / retrospective / BUG
# bookkeeping rows that must NOT be counted as stories.
MULTI_EPIC_SPRINT_STATUS = (
    "generated: 2026-06-04\n"
    "development_status:\n"
    "  # Epic 1 — fully done\n"
    "  epic-1: done\n"
    "  1-1-foundation: done\n"
    "  1-2-ingestion: done\n"
    "  epic-1-retrospective: done\n"
    "\n"
    "  # Epic 2 — in flight\n"
    "  epic-2: in-progress\n"
    "  2-1-traversal: done\n"
    "  2-2-detection: in-progress  # actively worked\n"
    "  2-3-display: ready-for-dev\n"
    '  BUG-001-something: done\n'
    "  epic-2-retrospective: optional\n"
    "\n"
    "  # Epic 3 — not started\n"
    "  epic-3: backlog\n"
    "  3-1-delete: backlog\n"
    "  3-2-modify: review\n"
)


def test_rollup_multi_epic_counts_and_flags(tmp_path):
    impl = tmp_path / "_bmad-output" / "implementation-artifacts"
    _write_sprint_status(impl, MULTI_EPIC_SPRINT_STATUS)

    rollup = pf.build_rollup(project_root=tmp_path.resolve(), impl_artifacts=impl)

    assert rollup["sprint_status_present"] is True
    by_id = {e["epic"]: e for e in rollup["epics"]}
    assert set(by_id) == {"1", "2", "3"}

    # Epic 1: two stories, all done. epic-1 / retrospective rows are NOT stories.
    e1 = by_id["1"]
    assert e1["story_count"] == 2
    assert e1["counts"] == {
        "done": 2,
        "in-progress": 0,
        "ready-for-dev": 0,
        "review": 0,
        "backlog": 0,
    }
    assert [s["id"] for s in e1["stories"]] == ["1-1-foundation", "1-2-ingestion"]
    assert e1["all_done"] is True

    # Epic 2: three stories (the BUG row is excluded), mixed statuses.
    e2 = by_id["2"]
    assert e2["story_count"] == 3
    assert e2["counts"] == {
        "done": 1,
        "in-progress": 1,
        "ready-for-dev": 1,
        "review": 0,
        "backlog": 0,
    }
    assert {s["id"] for s in e2["stories"]} == {
        "2-1-traversal",
        "2-2-detection",
        "2-3-display",
    }
    assert e2["all_done"] is False

    # Epic 3: backlog + review, none done.
    e3 = by_id["3"]
    assert e3["story_count"] == 2
    assert e3["counts"]["backlog"] == 1
    assert e3["counts"]["review"] == 1
    assert e3["all_done"] is False


def test_rollup_absent_sprint_status_is_empty_not_error(tmp_path):
    rollup = pf.build_rollup(
        project_root=tmp_path.resolve(),
        impl_artifacts=tmp_path / "_bmad-output" / "implementation-artifacts",
    )
    assert rollup == {"sprint_status_present": False, "epics": []}


def test_cli_rollup_emits_json_and_exit_zero(tmp_path):
    impl = tmp_path / "_bmad-output" / "implementation-artifacts"
    _write_sprint_status(impl, MULTI_EPIC_SPRINT_STATUS)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--rollup",
            "--project-root",
            str(tmp_path),
            "--impl-artifacts",
            str(impl),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["sprint_status_present"] is True
    assert {e["epic"] for e in payload["epics"]} == {"1", "2", "3"}


def test_cli_rollup_absent_sprint_status_exit_zero(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--rollup",
            "--project-root",
            str(tmp_path),
            "--impl-artifacts",
            str(tmp_path / "nope"),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"sprint_status_present": False, "epics": []}


def test_cli_rollup_ignores_epic_and_tea_config_requirement(tmp_path):
    # Regression: rollup mode does not require --epic / --tea-config, even
    # though normal mode does. Omitting them must still produce a payload.
    impl = tmp_path / "_bmad-output" / "implementation-artifacts"
    _write_sprint_status(impl, MULTI_EPIC_SPRINT_STATUS)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--rollup",
            "--project-root",
            str(tmp_path),
            "--impl-artifacts",
            str(impl),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "required" not in proc.stderr
    assert json.loads(proc.stdout)["sprint_status_present"] is True


def test_rollup_finds_sprint_status_via_glob_fallback(tmp_path):
    # The locator falls back to a bounded glob under _bmad-output when the file
    # is not at either primary candidate path; rollup must reuse that.
    nested = tmp_path / "_bmad-output" / "nested" / "deeper"
    _write_sprint_status(nested, "development_status:\n  4-1-thing: done\n")
    rollup = pf.build_rollup(
        project_root=tmp_path.resolve(),
        impl_artifacts=tmp_path / "does-not-exist",
    )
    assert rollup["sprint_status_present"] is True
    assert [e["epic"] for e in rollup["epics"]] == ["4"]
    assert rollup["epics"][0]["all_done"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# --- tea-config inline comments ---------------------------------------------
#
# A hand-written tea config routinely annotates its keys. The scalar reader did
# not strip the comment, so `test_artifacts` resolved to a directory whose name
# carried the comment text: `ULTRACODE_TEST_ARTIFACTS` pointed nowhere, the
# guard's un-skip proof found no checklist to read and enforced nothing, and
# preflight still reported green. An inert control, not a cosmetic parse bug.


def test_tea_scalar_drops_an_inline_comment(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "test_artifacts: _bmad-output/test-artifacts  # where TEA writes\n"
        "tea_execution_mode: sequential  # TEA's parallelism mode\n",
        encoding="utf-8",
    )

    flags = pf._read_toml_or_yaml_flags(cfg)

    assert flags["test_artifacts"] == "_bmad-output/test-artifacts"
    assert flags["tea_execution_mode"] == "sequential"
    assert pf._tea_artifacts_root(tmp_path, flags) == (
        tmp_path / "_bmad-output" / "test-artifacts"
    )


# --- impl_artifacts_tracked: a reported fact, never a blocker -----------------


@pytest.fixture
def _no_host_ignores(monkeypatch, tmp_path):
    """Keep the host's global and system ignore rules out of these cases.

    Only `core.excludesFile` is overridden, pointed at an empty file. Turning
    the system config off instead also drops a Windows host's `core.autocrlf`,
    and the CRLF files Python writes there then read as modified whenever git
    re-checks content, which made the clean-tree assertion flaky.
    """
    empty = tmp_path / "no-excludes"
    empty.write_text("", encoding="utf-8")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.excludesFile")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(empty))


def _commit_gitignore(project: Path, rules: str) -> None:
    (project / ".gitignore").write_text(rules, encoding="utf-8")
    _git(project, "add", ".gitignore")
    _git(project, "commit", "-q", "-m", "ignore rules")


def test_impl_artifacts_are_tracked_when_no_rule_ignores_them(project, monkeypatch, _no_host_ignores):
    report = _report(project, monkeypatch)
    assert report["checks"]["impl_artifacts_tracked"] is True


def test_a_negated_rule_keeps_the_artifact_tree_tracked(project, monkeypatch, _no_host_ignores):
    _commit_gitignore(project, "_bmad-output/*\n!_bmad-output/implementation-artifacts/\n")
    assert _report(project, monkeypatch)["checks"]["impl_artifacts_tracked"] is True


def test_an_artifact_tree_outside_git_reads_as_untracked(project, tmp_path, _no_host_ignores):
    # git refuses both paths (exit 128), and neither tree is in git: the same
    # hazard as an ignored one, so not the unknown `null`.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = project / "_bmad-output" / "linked-artifacts"
    link.symlink_to(elsewhere, target_is_directory=True)
    assert pf._impl_artifacts_tracked(project.resolve(), link) is False
    assert pf._impl_artifacts_tracked(project.resolve(), elsewhere) is False


def test_a_gitignored_artifact_tree_is_reported_and_never_blocks(project, monkeypatch, _no_host_ignores):
    # A project that keeps its BMAD output out of git on purpose: the branch
    # then undoes the code only, which the briefing says, but the run is ready.
    _commit_gitignore(project, "_bmad-output/\n")
    report = _report(project, monkeypatch)
    assert report["checks"]["impl_artifacts_tracked"] is False
    assert report["green"] is True, report["blockers"]
    assert report["budget"] == 0


def test_git_reads_the_probe_path_itself_on_every_platform(project, monkeypatch, _no_host_ignores):
    # #160 item 8: exit 128 (git could not read the path) reads as untracked,
    # the same as exit 0 (ignored), so the ignored-tree case cannot tell a
    # Windows path git rejected from a rule that matched. Pin git's own answer.
    _commit_gitignore(project, "_bmad-output/\n")
    calls = []
    real_git = pf._git

    def recording_git(args, root):
        code, out = real_git(args, root)
        calls.append((args, code))
        return code, out

    monkeypatch.setattr(pf, "_git", recording_git)
    impl = project.resolve() / "_bmad-output" / "implementation-artifacts"
    assert pf._impl_artifacts_tracked(project.resolve(), impl) is False
    assert [code for args, code in calls if args[0] == "check-ignore"] == [0]


def test_impl_artifacts_tracked_is_null_only_with_no_repository(tmp_path, _no_host_ignores):
    outside = tmp_path / "no-repo"
    outside.mkdir()
    assert pf._impl_artifacts_tracked(outside, outside / "impl") is None


def test_tea_scalar_without_a_comment_is_unchanged(tmp_path):
    """Control: the strip must not alter an un-annotated value."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("test_artifacts: _bmad-output/test-artifacts\n", encoding="utf-8")

    flags = pf._read_toml_or_yaml_flags(cfg)

    assert flags["test_artifacts"] == "_bmad-output/test-artifacts"


def test_tea_scalar_keeps_a_hash_inside_a_quoted_value(tmp_path):
    """A `#` that is part of the value survives.

    YAML starts a comment only at a WHITESPACE-preceded `#`, so the strip is
    anchored on that rather than on a bare `split('#')` -- which would have
    truncated a legitimate path.
    """
    cfg = tmp_path / "config.yaml"
    cfg.write_text('test_artifacts: "out/sharp#1"  # annotated\n', encoding="utf-8")

    flags = pf._read_toml_or_yaml_flags(cfg)

    assert flags["test_artifacts"] == "out/sharp#1"
