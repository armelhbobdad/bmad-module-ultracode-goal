#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""claim_check.py: the paths a commit message names that the staged diff skips.

The field case: a commit message recorded a file's edit as landed when the
script making the edit had died on its first assertion, so the diff for that
path was empty. A reviewer found it by diffing the file. This pins:

- what counts as a named path (a file name with a common extension, a
  well-known extensionless name, a known dotfile, a token with a `/` that ends
  with one or exists in the tree or the index), and what does not (`and/or`,
  `Node.js`, a URL, an e-mail address, a version, a glob, `$VAR`, `#123`);
- the `:line`, `:L12`, `#L12` and `::test` suffixes are dropped, `\\` reads as
  `/`, an absolute path under the root is made relative, and `--flag=x` and
  `old→new` are split;
- matching: a path that exists must match exactly or as a directory holding a
  staged path (a root `README.md` is not `docs/README.md`); one that exists
  nowhere matches by trailing segments or as a directory anywhere; both sides
  of a rename; a staged deletion; a non-ASCII name;
- the exit codes, and `-` for stdin;
- execute.md step 4 runs it between staging and the commit, and the
  documented command is not a git write the PreToolUse guard would gate.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_claim_check.py -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS / "claim_check.py"
EXECUTE = SCRIPTS.parent / "references" / "execute.md"
GUARD = SCRIPTS / "hooks" / "guard_pretooluse.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cc = _load("claim_check", SCRIPT)


@pytest.fixture(autouse=True)
def _hermetic_git(monkeypatch, tmp_path):
    for var in [v for v in os.environ if v.startswith("GIT_")]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    # Only the excludes file: turning the system config off would also drop a
    # Windows host's core.autocrlf (see test_preflight_check's _no_host_ignores).
    empty = tmp_path / "no-excludes"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.excludesFile")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(empty))


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for rel in ("src/guard.py", "src/fixture.ts", "tests/test_guard.py", "skills/ucg-formalize/SKILL.md", "old.py"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x = 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "add", ".")
    _git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base")
    return root


def _stage(repo: Path, rel: str, text: str = "x = 2\n") -> None:
    (repo / rel).write_text(text, encoding="utf-8")
    _git(repo, "add", rel)


def test_a_message_naming_only_staged_paths_is_clean(repo):
    _stage(repo, "src/guard.py")
    out = cc.check("fix(guard): tighten `src/guard.py`", repo)
    assert out == {"named": ["src/guard.py"], "staged": ["src/guard.py"], "not_in_diff": [], "clean": True}


def test_the_field_case_a_named_edit_that_never_landed(repo):
    # The message says the narrowing landed in fixture.ts; the diff touches
    # only the guard.
    _stage(repo, "src/guard.py")
    out = cc.check("fix: narrow the scan in `fixture.ts` and src/guard.py", repo)
    assert out["not_in_diff"] == ["fixture.ts"]
    assert out["clean"] is False


def test_matching_by_directory_trailing_segments_and_suffixes(repo):
    _stage(repo, "src/guard.py")
    _stage(repo, "tests/test_guard.py")
    message = "Touches src/, guard.py, `tests/test_guard.py::test_depth` and src/guard.py:12."
    out = cc.check(message, repo)
    assert out["named"] == ["src/", "guard.py", "tests/test_guard.py", "src/guard.py"]
    assert out["not_in_diff"] == []


def test_a_real_path_must_match_exactly(repo):
    # A root README.md exists, so a staged docs/README.md is not the one named.
    (repo / "README.md").write_text("root\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "README.md").write_text("docs\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "readmes")
    _stage(repo, "docs/README.md", "docs v2\n")
    out = cc.check("update README.md and docs/README.md", repo)
    assert out["not_in_diff"] == ["README.md"]


def test_a_path_that_exists_nowhere_matches_loosely(repo):
    # A trailing segment or a mid-path directory names a staged file.
    _stage(repo, "src/guard.py")
    out = cc.check("edit guard.py under src/ via `src/guard.py`; see hooks/", repo)
    assert "guard.py" in out["named"]
    assert out["not_in_diff"] == ["hooks/"]
    (repo / "skills" / "x" / "scripts" / "hooks").mkdir(parents=True)
    (repo / "skills" / "x" / "scripts" / "hooks" / "g.py").write_text("g\n", encoding="utf-8")
    _git(repo, "add", "skills/x/scripts/hooks/g.py")
    assert cc.check("touch scripts/hooks/", repo)["not_in_diff"] == []


def test_a_non_ascii_name_matches(repo):
    _stage(repo, "src/caf\u00e9.py", "x = 3\n")
    out = cc.check("edit src/caf\u00e9.py", repo)
    assert out["staged"] == ["src/caf\u00e9.py"]
    assert out["not_in_diff"] == []


def test_normalized_spellings_of_a_path(repo):
    _stage(repo, "src/guard.py")
    _stage(repo, "src/fixture.ts")
    root = str(repo.resolve())
    message = (
        "Edit src\\guard.py#L10, %s/src/guard.py:L12, --out=src/fixture.ts, "
        "`src/fixture.ts:12-14`, old.py\u2192src/guard.py" % root
    )
    out = cc.check(message, repo)
    assert out["named"] == ["src/guard.py", "src/fixture.ts", "old.py"]
    assert out["not_in_diff"] == ["old.py"]


def test_a_backticked_path_with_a_space_stays_whole(repo):
    (repo / "docs").mkdir()
    _stage(repo, "docs/my file.md", "m\n")
    out = cc.check("add `docs/my file.md`", repo)
    assert out["named"] == ["docs/my file.md"]
    assert out["not_in_diff"] == []


def test_extensionless_names_and_dotfiles(repo):
    _stage(repo, "Dockerfile", "FROM x\n")
    (repo / ".env").write_text("A=1\n", encoding="utf-8")
    out = cc.check("update Dockerfile and .env, not .prettierrc", repo)
    # .env exists, so it is a path; .prettierrc exists nowhere and is prose.
    assert out["named"] == ["Dockerfile", ".env"]
    assert out["not_in_diff"] == [".env"]


def test_an_at_sign_in_a_path_is_kept(repo):
    (repo / "packages" / "@acme" / "ui").mkdir(parents=True)
    _stage(repo, "packages/@acme/ui/button.tsx", "b\n")
    out = cc.check("style packages/@acme/ui/button.tsx; ask ops@team.sh", repo)
    # ops@team.sh has an extension-like ending: only the e-mail rule keeps it out.
    assert out["named"] == ["packages/@acme/ui/button.tsx"]


def test_a_slash_token_counts_only_when_it_is_a_path(repo):
    _stage(repo, "src/guard.py")
    message = (
        "Read and/or write, pass/fail, 1/2 of v2.3.0, e.g. see https://example.com/a.py "
        "on Node.js; `*.py` globs, $HOME/x.py, #123, -v; skills/ucg-formalize holds it; new/dir/ next.\n\n"
        "Co-Authored-By: Someone <noreply@example.com>"
    )
    out = cc.check(message, repo)
    # An existing directory and a trailing-slash token are paths; the rest are prose.
    assert out["named"] == ["skills/ucg-formalize", "new/dir/"]
    assert out["not_in_diff"] == ["skills/ucg-formalize", "new/dir/"]


def test_a_rename_and_a_deletion_match_by_either_name(repo):
    _git(repo, "mv", "old.py", "src/new.py")
    _git(repo, "rm", "-q", "src/fixture.ts")
    out = cc.check("Move `old.py` to `src/new.py`, drop src/fixture.ts", repo)
    assert out["not_in_diff"] == []


def test_the_cli_reports_json_and_reads_stdin(repo):
    _stage(repo, "src/guard.py")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--message", "-", "--project-root", str(repo)],
        input="edit src/fixture.ts",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["not_in_diff"] == ["src/fixture.ts"]


def test_the_cli_exits_2_when_it_cannot_run(repo, tmp_path):
    missing = subprocess.run(
        [sys.executable, str(SCRIPT), "--message", str(tmp_path / "none.txt"), "--project-root", str(repo)],
        capture_output=True, text=True, timeout=60,
    )
    assert missing.returncode == 2
    message = tmp_path / "m.txt"
    message.write_text("edit src/guard.py", encoding="utf-8")
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    no_repo = subprocess.run(
        [sys.executable, str(SCRIPT), "--message", str(message), "--project-root", str(outside)],
        capture_output=True, text=True, timeout=60,
    )
    assert no_repo.returncode == 2
    assert "not a git work tree" in no_repo.stderr


# --- execute.md step 4 --------------------------------------------------------


def _claim_paragraph() -> tuple[str, str]:
    text = EXECUTE.read_text(encoding="utf-8")
    start = text.index("**Check the record's claims before the commit.**")
    end = text.index("\n5. **Re-verify on the committed HEAD.**", start)
    step4 = text.rfind("\n4. **Commit at green**", 0, start)
    assert step4 != -1 and text.find("\n5. ", step4, start) == -1, "the check sits inside step 4"
    return text[start:end], text


def test_step4_runs_the_check_between_staging_and_the_commit():
    paragraph, _ = _claim_paragraph()
    assert "between the staging call and the commit call" in paragraph
    assert "uv run {skill-root}/scripts/claim_check.py --message {workflow.implementation_artifacts}/.scratch-<story_id>/message.txt --project-root {project-root}" in paragraph
    assert "stage the path if this commit should change it, or reword the message" in paragraph
    # The judgment half: the diff's own new claims.
    assert "the usual fix is to weaken the sentence, not to strengthen the code" in paragraph
    # Bounded: one pass, evidence already produced, no new run.
    assert "make one pass over the claims the diff itself adds" in paragraph
    assert "start no new run to back a sentence" in paragraph
    # A sentence softened in a staged file must reach the commit.
    assert "Re-stage every file this pass edited, in its own `git add` call" in paragraph
    assert "Run the same check before any re-commit or amend step 5 makes." in paragraph


def test_the_documented_command_is_not_a_git_write():
    # The check runs between two guarded calls; it must not itself be one.
    paragraph, _ = _claim_paragraph()
    commands = [line for line in paragraph.splitlines() if line.startswith("uv run ")]
    assert len(commands) == 1 and "claim_check.py" in commands[0]
    # Resolved under a project whose path holds the word `git`, the shape the
    # guard's fail-closed scan reads most suspiciously.
    resolved = (
        commands[0]
        .replace("{skill-root}", "/home/u/git/proj/.claude/skills/ultracode-goal")
        .replace("{workflow.implementation_artifacts}", "/home/u/git/proj/_bmad-output/implementation-artifacts")
        .replace("<story_id>", "4-1")
        .replace("{project-root}", "/home/u/git/proj")
    )
    guard = _load("guard_pretooluse", GUARD)
    assert guard._git_writes(resolved) == set()
    # The message file's name keeps the commit verb out of the command entirely.
    assert "commit" not in resolved
