#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Mechanical preflight for an UltraCode-Goal epic run.

Plumbing ONLY. This script parses tool versions, inspects git state, checks
file/directory existence, and reads TEA config flags. It reports mechanical
facts plus a `budget` count of mechanical blockers. It does NOT decide whether
to intervene, remediate, or block on semantic grounds — that judgment lives in
references/preflight.md (the LLM). The "auto-remediation then hard-gate"
posture (decision D2') is the LLM's to run; this script only tells it what is
mechanically true right now.

What counts as a mechanical blocker (each adds 1 to `budget`):
  - the Claude Code primitives needed for an unattended run are below the
    minimum versions the run depends on (`/goal`, dynamic workflows, auto memory),
  - the test framework is not scaffolded (no playwright/cypress/jest config),
  - the working tree is dirty (a per-green-story commit needs a clean base),
  - the current branch is a protected branch (the epic must run on its own branch).

`green` is true iff `budget == 0`. A green preflight means there is nothing
MECHANICAL left to clear; the LLM still owns the true-RED hard gate
(undecided architecture/product, unresolvable secrets), which this script
cannot and does not evaluate.

Severity is advisory metadata for the LLM, not a gate. `remediable` flags
blockers the remediation pass can plausibly auto-clear (e.g. scaffold the
framework, branch off, commit/stash) vs. ones that need a human (none here are
inherently un-remediable; true-RED items never reach this script).

Version gates (from the grounded constraints in .decision-log.md):
  /goal >= 2.1.139, dynamic workflows >= 2.1.154, auto memory >= 2.1.59.

Output: JSON to stdout. Exit 0 whenever a payload is produced (a non-green
preflight is a valid result, not an error). Exit 2 is reserved for invocation
errors where no useful payload can be produced.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Minimum Claude Code versions the unattended run depends on.
MIN_GOAL = (2, 1, 139)
MIN_WORKFLOWS = (2, 1, 154)
MIN_AUTOMEMORY = (2, 1, 59)

# Filenames that signal a scaffolded test framework (playwright / cypress / jest).
FRAMEWORK_MARKERS = (
    "playwright.config.ts",
    "playwright.config.js",
    "playwright.config.mjs",
    "cypress.config.ts",
    "cypress.config.js",
    "cypress.config.mjs",
    "cypress.json",
    "jest.config.ts",
    "jest.config.js",
    "vitest.config.ts",
    "vitest.config.js",
)

# TEA test-artifact subdirectories the gates write into (relative to test_artifacts root).
TEA_ARTIFACT_DIRS = ("test-design", "test-reviews", "traceability")

# TEA config flags worth surfacing to the LLM verbatim (mechanical read, no interpretation).
TEA_FLAG_KEYS = (
    "test_execution_mode",
    "tea_execution_mode",
    "test_framework",
    "test_stack_type",
    "ci_platform",
    "risk_threshold",
    "tea_browser_automation",
    "tea_capability_probe",
    "test_artifacts",
)

# Default protected branches when the caller doesn't override (mirrors customize.toml).
DEFAULT_PROTECTED = ("main", "master")


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a command, returning (returncode, stdout, stderr). 127 if not found."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def _parse_semver(text: str) -> tuple[int, int, int] | None:
    """Extract the first dotted three-part version from text."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    if not match:
        return None
    return tuple(int(g) for g in match.groups())  # type: ignore[return-value]


def _cc_version() -> tuple[str | None, tuple[int, int, int] | None]:
    """Best-effort read of the installed Claude Code version."""
    code, out, _ = _run(["claude", "--version"])
    if code != 0:
        return None, None
    return out, _parse_semver(out)


def _meets(version: tuple[int, int, int] | None, minimum: tuple[int, int, int]) -> bool:
    return version is not None and version >= minimum


def _git(args: list[str], project_root: Path) -> tuple[int, str]:
    code, out, _ = _run(["git", *args], cwd=project_root)
    return code, out


def _git_branch(project_root: Path) -> str | None:
    code, out = _git(["rev-parse", "--abbrev-ref", "HEAD"], project_root)
    if code != 0 or not out:
        return None
    return out


def _git_clean(project_root: Path) -> bool | None:
    code, out = _git(["status", "--porcelain"], project_root)
    if code != 0:
        return None
    return out == ""


def _read_toml_or_yaml_flags(tea_config: Path) -> dict:
    """Read flat key: value scalars from the TEA config.

    The TEA config is YAML in practice. To stay stdlib-only we parse the flat
    `key: value` scalar lines we care about ourselves (no nesting is needed for
    these flags). If `tomllib` ever applies (a .toml config) we try that first.
    """
    if not tea_config.is_file():
        return {}
    text = tea_config.read_text(encoding="utf-8", errors="replace")

    if tea_config.suffix.lower() == ".toml":
        try:
            import tomllib

            data = tomllib.loads(text)
            return {k: data[k] for k in TEA_FLAG_KEYS if k in data}
        except Exception:
            pass

    flags: dict = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key not in TEA_FLAG_KEYS:
            continue
        value = value.strip().strip('"').strip("'")
        if value.lower() in ("true", "false"):
            flags[key] = value.lower() == "true"
        else:
            flags[key] = value
    return flags


def _tea_artifacts_root(project_root: Path, tea_flags: dict) -> Path:
    """Resolve the test_artifacts root, honoring a tea-config override if present."""
    configured = tea_flags.get("test_artifacts")
    if isinstance(configured, str) and configured:
        resolved = configured.replace("{project-root}", str(project_root))
        path = Path(resolved)
        return path if path.is_absolute() else (project_root / path)
    return project_root / "_bmad-output" / "test-artifacts"


def _framework_present(project_root: Path) -> bool:
    """A framework config at the project root signals a scaffolded test framework."""
    for marker in FRAMEWORK_MARKERS:
        if (project_root / marker).is_file():
            return True
    return False


def _test_artifacts_dirs(artifacts_root: Path) -> dict:
    """Map each TEA artifact subdir to whether it exists."""
    return {name: (artifacts_root / name).is_dir() for name in TEA_ARTIFACT_DIRS}


def _sprint_status_present(project_root: Path, impl_artifacts: Path) -> bool:
    """sprint-status.yaml controls test-design's System/Epic prompt (must exist to auto-run).

    BMad writes it under the output tree; search the common locations rather
    than hardcoding one path that may drift between installs.
    """
    candidates = [
        impl_artifacts / "sprint-status.yaml",
        project_root / "_bmad-output" / "sprint-status.yaml",
    ]
    for path in candidates:
        if path.is_file():
            return True
    # Fall back to a bounded glob under the output tree.
    output = project_root / "_bmad-output"
    if output.is_dir():
        for hit in output.rglob("sprint-status.yaml"):
            if hit.is_file():
                return True
    return False


def _project_context_count(project_root: Path) -> int:
    """Count project-context.md files (the persistent-facts source)."""
    return sum(1 for _ in project_root.rglob("project-context.md"))


def build_report(
    project_root: Path,
    epic: str,
    tea_config: Path,
    impl_artifacts: Path,
    protected_branches: tuple[str, ...],
) -> dict:
    cc_raw, cc_ver = _cc_version()
    goal_ok = _meets(cc_ver, MIN_GOAL)
    workflows_ok = _meets(cc_ver, MIN_WORKFLOWS)
    automemory_ok = _meets(cc_ver, MIN_AUTOMEMORY)

    git_branch = _git_branch(project_root)
    git_clean = _git_clean(project_root)

    tea_flags = _read_toml_or_yaml_flags(tea_config)
    artifacts_root = _tea_artifacts_root(project_root, tea_flags)

    framework_present = _framework_present(project_root)
    test_artifacts_dirs = _test_artifacts_dirs(artifacts_root)
    sprint_status_present = _sprint_status_present(project_root, impl_artifacts)
    project_context_count = _project_context_count(project_root)

    checks = {
        "cc_version": cc_raw,
        "goal_ok": goal_ok,
        "workflows_ok": workflows_ok,
        "automemory_ok": automemory_ok,
        "git_branch": git_branch,
        "git_clean": git_clean,
        "framework_present": framework_present,
        "test_artifacts_dirs": test_artifacts_dirs,
        "sprint_status_present": sprint_status_present,
        "project_context_count": project_context_count,
        "tea_flags": tea_flags,
    }

    blockers: list[dict] = []

    # --- Mechanical blockers (each counts toward the budget) ---

    # Primitive versions: any one being below minimum blocks the unattended run.
    if not (goal_ok and workflows_ok and automemory_ok):
        below = []
        if not goal_ok:
            below.append("/goal>=%d.%d.%d" % MIN_GOAL)
        if not workflows_ok:
            below.append("workflows>=%d.%d.%d" % MIN_WORKFLOWS)
        if not automemory_ok:
            below.append("auto-memory>=%d.%d.%d" % MIN_AUTOMEMORY)
        detail = (
            "Claude Code %s is below the minimum for: %s"
            % (cc_raw or "(version unreadable)", ", ".join(below))
        )
        blockers.append(
            {
                "id": "cc_version",
                "kind": "version",
                "severity": "high",
                "detail": detail,
                # The script can't upgrade the host; the LLM prompts the user.
                "remediable": False,
            }
        )

    if not framework_present:
        blockers.append(
            {
                "id": "framework_present",
                "kind": "framework",
                "severity": "medium",
                "detail": "No test framework config found at project root "
                "(playwright/cypress/jest/vitest). ATDD halts without one.",
                # Remediation pass scaffolds via bmad-testarch-framework.
                "remediable": True,
            }
        )

    if git_clean is False:
        blockers.append(
            {
                "id": "git_clean",
                "kind": "git",
                "severity": "medium",
                "detail": "Working tree is dirty; a per-green-story commit needs a clean base.",
                "remediable": True,
            }
        )
    elif git_clean is None:
        blockers.append(
            {
                "id": "git_repo",
                "kind": "git",
                "severity": "high",
                "detail": "git status failed; project-root may not be a git repository.",
                "remediable": False,
            }
        )

    if git_branch is not None and git_branch in protected_branches:
        blockers.append(
            {
                "id": "git_branch",
                "kind": "git",
                "severity": "medium",
                "detail": "On protected branch '%s'; the epic must run on its own branch."
                % git_branch,
                "remediable": True,
            }
        )

    budget = len(blockers)
    return {
        "green": budget == 0,
        "budget": budget,
        "blockers": blockers,
        "checks": checks,
    }


def _resolve(path_arg: str, project_root: Path) -> Path:
    """Expand a possible {project-root} token and resolve relative to project_root."""
    resolved = path_arg.replace("{project-root}", str(project_root))
    path = Path(resolved)
    return path if path.is_absolute() else (project_root / path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mechanical preflight for an UltraCode-Goal epic run."
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--epic", required=True)
    parser.add_argument("--tea-config", required=True)
    parser.add_argument("--impl-artifacts", required=True)
    parser.add_argument(
        "--protected-branch",
        action="append",
        default=None,
        help="Protected branch name; repeatable. Defaults to main, master.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).expanduser()
    if not project_root.is_dir():
        print(
            json.dumps({"error": "project-root not found: %s" % project_root}),
            file=sys.stderr,
        )
        return 2

    project_root = project_root.resolve()
    tea_config = _resolve(args.tea_config, project_root)
    impl_artifacts = _resolve(args.impl_artifacts, project_root)
    protected = tuple(args.protected_branch) if args.protected_branch else DEFAULT_PROTECTED

    report = build_report(
        project_root=project_root,
        epic=args.epic,
        tea_config=tea_config,
        impl_artifacts=impl_artifacts,
        protected_branches=protected,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
