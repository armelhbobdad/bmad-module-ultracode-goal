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
  - no test framework is detected (no playwright/cypress/jest/vitest config,
    no pytest config/conftest.py, and no real package.json `test` script),
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

Rollup mode (`--rollup`): a separate, cheaper read used by Stage 1
(references/ingest-and-scope.md, "Resolve the Epic and its artifacts" step 1).
It parses ONLY sprint-status.yaml and emits a compact per-Epic story-status
summary so the LLM selects the target Epic from a small structured summary
instead of parsing raw YAML. None of the mechanical preflight checks run in
this mode; `--epic`, `--tea-config`, and `--protected-branch` are not required.
Absence of sprint-status.yaml is a reportable fact (sprint_status_present:
false, epics: []), not an error — rollup still exits 0.

  uv run preflight_check.py --rollup --project-root <path> --impl-artifacts <path>
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

# Root-level config filenames that signal a scaffolded JS/browser test framework
# (playwright / cypress / jest / vitest). Pytest and npm-driven harnesses are
# detected separately in _detect_framework — a config file is only one of the
# shapes a real test framework takes.
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

# The story-status vocabulary BMad's sprint-planning writes into
# sprint-status.yaml (see its sprint-status-template.yaml STATUS DEFINITIONS).
# Order here is the order counts are reported in the rollup; "done" first so the
# in-scope decision (not-yet-done) reads off the leading count.
STORY_STATUSES = ("done", "in-progress", "ready-for-dev", "review", "backlog")


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


# The npm-init placeholder `test` script ("...no test specified..."); not a real harness.
_NPM_TEST_PLACEHOLDER = "no test specified"


def _safe_read_text(path: Path) -> str:
    """Read a file as UTF-8, returning "" on any OS error (missing, unreadable)."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _pytest_present(project_root: Path) -> bool:
    """True when the project root carries a pytest config, conftest, or [pytest] table."""
    if (project_root / "pytest.ini").is_file():
        return True
    if (project_root / "conftest.py").is_file():
        return True
    tox = project_root / "tox.ini"
    if tox.is_file() and "[pytest]" in _safe_read_text(tox):
        return True
    setup_cfg = project_root / "setup.cfg"
    if setup_cfg.is_file() and "[tool:pytest]" in _safe_read_text(setup_cfg):
        return True
    pyproject = project_root / "pyproject.toml"
    if pyproject.is_file() and "[tool.pytest" in _safe_read_text(pyproject):
        return True
    return False


def _npm_test_script(project_root: Path) -> bool:
    """True when package.json has a real `test` script (not the npm-init placeholder)."""
    pkg = project_root / "package.json"
    if not pkg.is_file():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    scripts = data.get("scripts")
    script = scripts.get("test") if isinstance(scripts, dict) else None
    if not isinstance(script, str) or not script.strip():
        return False
    return _NPM_TEST_PLACEHOLDER not in script


def _detect_framework(project_root: Path) -> str | None:
    """Identify the project's test harness, returning its kind or None.

    Returns "js-config" (a scaffolded playwright/cypress/jest/vitest config),
    "pytest" (a pytest config or root conftest), or "npm-test" (a package.json
    with a real `test` script) — whichever is found first, in that order — and
    None when no harness is recognized.

    Detection is deliberately broad. The gate asks "does this project have a
    test framework the unattended run can target?", and a pytest or npm-driven
    harness answers yes just as a browser-E2E config does. A pure-Python or
    CLI/markdown module has no playwright.config, so flagging it
    "framework absent" was a false-positive no remediation could honestly
    clear — the blocker could only be satisfied by scaffolding an
    inappropriate browser harness. (Note: this answers *presence*, not
    *fitness* — TEA's ATDD/automate flow still assumes a browser/E2E stack;
    that fitness gap is tracked separately.)
    """
    for marker in FRAMEWORK_MARKERS:
        if (project_root / marker).is_file():
            return "js-config"
    if _pytest_present(project_root):
        return "pytest"
    if _npm_test_script(project_root):
        return "npm-test"
    return None


def _test_artifacts_dirs(artifacts_root: Path) -> dict:
    """Map each TEA artifact subdir to whether it exists."""
    return {name: (artifacts_root / name).is_dir() for name in TEA_ARTIFACT_DIRS}


def _locate_sprint_status(project_root: Path, impl_artifacts: Path) -> Path | None:
    """Return the path to sprint-status.yaml, or None if it is not found.

    BMad writes it under the output tree; search the common locations rather
    than hardcoding one path that may drift between installs.
    """
    candidates = [
        impl_artifacts / "sprint-status.yaml",
        project_root / "_bmad-output" / "sprint-status.yaml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    # Fall back to a bounded glob under the output tree.
    output = project_root / "_bmad-output"
    if output.is_dir():
        for hit in output.rglob("sprint-status.yaml"):
            if hit.is_file():
                return hit
    return None


def _sprint_status_present(project_root: Path, impl_artifacts: Path) -> bool:
    """sprint-status.yaml controls test-design's System/Epic prompt (must exist to auto-run)."""
    return _locate_sprint_status(project_root, impl_artifacts) is not None


def _parse_development_status(text: str) -> dict[str, str]:
    """Hand-parse the flat `key: status` scalars under `development_status:`.

    Mirrors how this script already reads YAML (flat scalar lines, stdlib-only).
    sprint-status.yaml is a single `development_status:` map of one-key-per-line
    `name: status` entries (story keys like `1-1-foo`, epic rows like `epic-1`,
    retrospective and BUG rows). Trailing `# ...` comments and surrounding
    quotes are stripped. Returns the map in file order.
    """
    entries: dict[str, str] = {}
    in_block = False
    for raw in text.splitlines():
        # The map is one top-level key; detect entering/leaving its body by
        # indentation rather than tracking nesting (the file is flat).
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not in_block:
            if stripped.rstrip().rstrip(":") == "development_status" and stripped.endswith(":"):
                in_block = True
            continue
        # Inside the block: a non-indented line ends it.
        if raw[:1] not in (" ", "\t"):
            break
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip().strip('"').strip("'")
        # Drop trailing inline comment, then quotes/whitespace.
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        if key and value:
            entries[key] = value
    return entries


def _epic_id_of(story_key: str) -> str | None:
    """Epic id = the number prefix before the first separator (`-` or `.`).

    `1-1-user-authentication` -> "1", `2.3` -> "2". Non-story rows that carry no
    leading number (none in practice) map to None and are skipped by the caller.
    """
    match = re.match(r"^(\d+)", story_key)
    return match.group(1) if match else None


def _is_story_key(key: str) -> bool:
    """True for per-story rows; False for epic/retrospective/bug bookkeeping rows.

    Story keys begin with the epic number prefix (`1-1-...`, `2.3`). The
    `epic-N`, `epic-N-retrospective`, and `BUG-...` rows are not stories and must
    not be counted toward an Epic's story totals.
    """
    return _epic_id_of(key) is not None


def build_rollup(project_root: Path, impl_artifacts: Path) -> dict:
    """Compact per-Epic story-status summary parsed from sprint-status.yaml.

    Stage 1 selects the target Epic from this summary and computes in-scope as
    the stories whose status is not `done`. Absence of the file is reported, not
    raised.
    """
    sprint_status = _locate_sprint_status(project_root, impl_artifacts)
    if sprint_status is None:
        return {"sprint_status_present": False, "epics": []}

    text = sprint_status.read_text(encoding="utf-8", errors="replace")
    entries = _parse_development_status(text)

    # Group story rows by epic prefix, preserving first-seen epic order.
    epics: dict[str, list[dict]] = {}
    for key, status in entries.items():
        if not _is_story_key(key):
            continue
        epic_id = _epic_id_of(key)
        assert epic_id is not None  # _is_story_key guarantees this
        epics.setdefault(epic_id, []).append({"id": key, "status": status})

    rollup_epics: list[dict] = []
    for epic_id, stories in epics.items():
        counts = {name: 0 for name in STORY_STATUSES}
        for story in stories:
            if story["status"] in counts:
                counts[story["status"]] += 1
        rollup_epics.append(
            {
                "epic": epic_id,
                "story_count": len(stories),
                "counts": counts,
                "stories": stories,
                "all_done": all(s["status"] == "done" for s in stories),
            }
        )

    return {"sprint_status_present": True, "epics": rollup_epics}


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

    framework_kind = _detect_framework(project_root)
    framework_present = framework_kind is not None
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
        "framework_kind": framework_kind,
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
                "detail": "No test framework detected at project root "
                "(looked for a playwright/cypress/jest/vitest config, a pytest "
                "config or conftest.py, or a package.json `test` script). "
                "ATDD halts without one.",
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
        description="Mechanical preflight for an UltraCode-Goal epic run "
        "(use --rollup for the Stage 1 per-Epic story-status summary)."
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument(
        "--rollup",
        action="store_true",
        help="Emit only the per-Epic story-status summary parsed from "
        "sprint-status.yaml (Stage 1 scope selection). When set, --epic, "
        "--tea-config, and --protected-branch are not required and the "
        "mechanical preflight checks do not run.",
    )
    # Required only in the normal (non-rollup) mode; validated manually below so
    # rollup mode can omit them. --impl-artifacts is required in both modes.
    parser.add_argument("--epic")
    parser.add_argument("--tea-config")
    parser.add_argument("--impl-artifacts", required=True)
    parser.add_argument(
        "--protected-branch",
        action="append",
        default=None,
        help="Protected branch name; repeatable. Defaults to main, master.",
    )
    args = parser.parse_args(argv)

    # Preserve the normal-mode contract: --epic and --tea-config are required
    # unless --rollup is in effect. parser.error() reproduces argparse's usage
    # line + "error:" message and exits 2, exactly as required=True did.
    if not args.rollup:
        missing = [
            name
            for name, value in (("--epic", args.epic), ("--tea-config", args.tea_config))
            if value is None
        ]
        if missing:
            parser.error(
                "the following arguments are required: %s" % ", ".join(missing)
            )

    project_root = Path(args.project_root).expanduser()
    if not project_root.is_dir():
        print(
            json.dumps({"error": "project-root not found: %s" % project_root}),
            file=sys.stderr,
        )
        return 2

    project_root = project_root.resolve()
    impl_artifacts = _resolve(args.impl_artifacts, project_root)

    if args.rollup:
        rollup = build_rollup(project_root=project_root, impl_artifacts=impl_artifacts)
        print(json.dumps(rollup, indent=2))
        return 0

    tea_config = _resolve(args.tea_config, project_root)
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
