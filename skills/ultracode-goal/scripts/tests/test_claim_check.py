#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""claim_check.py: the paths a commit message names that the staged diff skips.

The field case: a story record and a commit message both said a file's edit
had landed when the script making the edit had died on its first assertion,
so the diff for that file was empty. Only the record named the file, which is
why `--message` repeats. This pins:

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
  of a rename; a staged deletion; a non-ASCII name; a project root below the
  git top level, named from either;
- the exit codes, `-` for stdin, and several `--message` texts read as one;
  stdin and the JSON are UTF-8 whatever the console's code page, and a staged
  name that is not UTF-8 still prints;
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
    assert out == {"named": ["src/guard.py"], "staged": ["src/guard.py"], "not_in_diff": [], "ignored": [], "clean": True}


def test_a_named_edit_that_never_landed(repo):
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


def test_a_lone_slash_is_not_the_project_root(repo):
    # Prose such as "a token that holds a `/`" must not name the root itself.
    assert cc.check("a token that holds a `/` or a // pair", repo)["named"] == []


def test_a_rename_and_a_deletion_match_by_either_name(repo):
    _git(repo, "mv", "old.py", "src/new.py")
    _git(repo, "rm", "-q", "src/fixture.ts")
    out = cc.check("Move `old.py` to `src/new.py`, drop src/fixture.ts", repo)
    assert out["not_in_diff"] == []


@pytest.fixture
def subdir_project(tmp_path: Path) -> Path:
    """A project root one folder below the repository's top level, as a
    BMAD install into a monorepo's `app/` folder leaves it."""
    top = tmp_path / "mono"
    for rel in ("README.md", "app/README.md", "app/src/a.py", "app/src/b.py", "other/c.py"):
        (top / rel).parent.mkdir(parents=True, exist_ok=True)
        (top / rel).write_text("x = 1\n", encoding="utf-8")
    _git(top, "init", "-q")
    _git(top, "config", "user.email", "t@example.com")
    _git(top, "config", "user.name", "t")
    _git(top, "add", ".")
    _git(top, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base")
    return top / "app"


def test_a_project_root_below_the_top_level_reads_names_from_it(subdir_project):
    # git names a staged path from the top level (`app/src/a.py`); a text
    # names it from the project root (`src/a.py`), as execute.md's command
    # passes `--project-root {project-root}`.
    app = subdir_project
    _stage(app, "src/a.py")
    out = cc.check("feat: change src/a.py", app)
    assert out == {"named": ["src/a.py"], "staged": ["app/src/a.py"], "not_in_diff": [], "ignored": [], "clean": True}
    # The top-level form, an absolute path and the folder name it as well.
    assert cc.check("feat: change app/src/a.py", app)["clean"] is True
    assert cc.check("feat: change %s/src/a.py under src/" % app.resolve().as_posix(), app)["clean"] is True
    # An edit that did not land is still listed, in either form.
    out = cc.check("feat: change src/a.py, src/b.py and app/src/b.py", app)
    assert out["not_in_diff"] == ["src/b.py", "app/src/b.py"]
    # A real path under the project root is read there: the top level's
    # staged README.md is not the project's own.
    _stage(app.parent, "README.md", "top v2\n")
    assert cc.check("docs: update README.md", app)["not_in_diff"] == ["README.md"]
    _stage(app, "README.md", "app v2\n")
    assert cc.check("docs: update README.md", app)["not_in_diff"] == []


def test_a_project_root_below_the_top_level_ignores_diff_relative(subdir_project):
    # With diff.relative set, git would name the staged paths from the cwd
    # and drop the ones outside it; the check reads them from the top level
    # whatever the config says.
    app = subdir_project
    _git(app.parent, "config", "diff.relative", "true")
    _stage(app, "src/a.py")
    _stage(app.parent, "other/c.py")
    out = cc.check("feat: change src/a.py and app/src/a.py", app)
    assert out["staged"] == ["app/src/a.py", "other/c.py"]
    assert out["clean"] is True


@pytest.mark.skipif(os.name != "posix", reason="a file name that is not UTF-8 needs bytes in argv")
def test_a_staged_name_that_is_not_utf8_still_prints_json(repo):
    # git stores the bytes it was given; this one is Latin-1. Read back as a
    # lone surrogate, it crashed the UTF-8 print with exit 1 and no JSON.
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"], cwd=repo, input=b"x\n", capture_output=True, check=True
    ).stdout.decode().strip()
    subprocess.run(
        [b"git", b"update-index", b"--add", b"--cacheinfo", b"100644", blob.encode(), b"caf\xe9.txt"],
        cwd=repo, check=True, capture_output=True,
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--message", "-", "--project-root", str(repo)],
        input=b"edit src/guard.py", capture_output=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.decode("utf-8"))
    # The JSON escape names the same bytes git holds.
    assert out["staged"] == ["caf\udce9.txt"]
    assert os.fsencode(out["staged"][0]) == b"caf\xe9.txt"
    assert out["not_in_diff"] == ["src/guard.py"]


def test_the_json_is_utf8_whatever_the_console_code_page(repo):
    # A Windows pipe writes the ANSI code page (cp1252), which has no CJK.
    (repo / "docs").mkdir()
    _stage(repo, "docs/日本.md", "n\n")
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--message", "-", "--project-root", str(repo)],
        input="edit docs/日本.md".encode("utf-8"), capture_output=True, timeout=60, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.decode("utf-8"))
    assert out["staged"] == ["docs/日本.md"]
    assert out["clean"] is True


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


def test_the_story_notes_name_what_the_message_only_describes(repo, tmp_path):
    # The field shape: the message describes the edit by its content and names
    # no file; the record notes name the file. Read together, the missing hunk
    # shows up as a path the diff does not touch.
    _stage(repo, "src/guard.py")
    message = tmp_path / "message.txt"
    message.write_text("fix(guard): src/guard.py, and the override union now says it closes the raw path\n", encoding="utf-8")
    notes = tmp_path / "record-notes.md"
    notes.write_text("- narrowed the override paragraph in `src/fixture.ts`\n", encoding="utf-8")
    # The message alone reads clean: it names only the file the diff touches.
    assert cc.check(message.read_text(encoding="utf-8"), repo)["clean"] is True
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--message", str(message), "--message", str(notes), "--project-root", str(repo)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    # Both texts are read, the message first.
    assert out["named"] == ["src/guard.py", "src/fixture.ts"]
    assert out["not_in_diff"] == ["src/fixture.ts"]


def test_a_path_git_ignores_is_listed_apart(repo):
    # A ledger the record must cite lives under an ignored tree: no commit can
    # carry it, so it is not a claim the commit fails to make good.
    (repo / ".gitignore").write_text("_bmad-output/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _stage(repo, "src/guard.py")
    out = cc.check("see _bmad-output/implementation-artifacts/mutation-ledger-4-1.md and src/fixture.ts", repo)
    assert out["ignored"] == ["_bmad-output/implementation-artifacts/mutation-ledger-4-1.md"]
    assert out["not_in_diff"] == ["src/fixture.ts"]
    assert out["clean"] is False


def test_only_ignored_paths_left_read_clean(repo):
    (repo / ".gitignore").write_text("_bmad-output/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    out = cc.check("cites _bmad-output/implementation-artifacts/mutation-ledger-4-1.md", repo)
    assert out["not_in_diff"] == []
    assert out["ignored"] == ["_bmad-output/implementation-artifacts/mutation-ledger-4-1.md"]
    assert out["clean"] is True


def test_a_tracked_file_under_an_ignored_folder_is_not_ignored(repo):
    # git commits a tracked file's edits whatever the rules say.
    (repo / "out").mkdir()
    (repo / "out" / "kept.md").write_text("k\n", encoding="utf-8")
    _git(repo, "add", "out/kept.md")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "kept")
    (repo / ".gitignore").write_text("out/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    out = cc.check("edit out/kept.md", repo)
    assert out["ignored"] == []
    assert out["not_in_diff"] == ["out/kept.md"]


def test_a_path_git_cannot_evaluate_does_not_hide_an_ignored_one(repo, tmp_path):
    # git stops at the first path beyond a symlink (exit 128); the ledger after
    # it must still be found ignored.
    (repo / ".gitignore").write_text("_bmad-output/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    try:
        (repo / "link").symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("this platform cannot create a directory symlink here")
    message = "see link/file.md, ../other/x.md, /tmp/x.md, then _bmad-output/ledger.md"
    out = cc.check(message, repo)
    assert out["ignored"] == ["_bmad-output/ledger.md"]
    assert "link/file.md" in out["not_in_diff"]


def test_a_bare_name_that_exists_nowhere_is_not_asked_about(repo):
    # With `*.txt` ignored, readme.txt could be any file of that name: it stays a claim.
    (repo / ".gitignore").write_text("*.txt\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    out = cc.check("update readme.txt", repo)
    assert out["ignored"] == []
    assert out["not_in_diff"] == ["readme.txt"]


def test_an_unreadable_second_message_names_the_file(repo, tmp_path):
    message = tmp_path / "message.txt"
    message.write_text("edit src/guard.py", encoding="utf-8")
    # Not UTF-8: the decode error names no file by itself, unlike a missing one.
    notes = tmp_path / "record-notes.md"
    notes.write_bytes(b"\xff\xfe not utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--message", str(message), "--message", str(notes), "--project-root", str(repo)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 2
    assert str(notes) in json.loads(proc.stderr)["error"]


def test_stdin_can_be_read_only_once(repo):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--message", "-", "--message", "-", "--project-root", str(repo)],
        input="x", capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 2
    assert "only once" in proc.stderr


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
    assert (
        "uv run {skill-root}/scripts/claim_check.py --message {workflow.implementation_artifacts}/.scratch-<story_id>/message.txt"
        " --message {workflow.implementation_artifacts}/.scratch-<story_id>/record-notes.md --project-root {project-root}"
    ) in paragraph
    assert "and the story-record notes this cycle added" in paragraph
    assert "an empty file when the cycle added none" in paragraph
    # A decomposed child has no story record: its notes are the File List and
    # completion notes ucg-dev-story gives in its summary, so they are checked.
    assert "for a decomposed child, which has no record, the File List and completion notes" in paragraph
    assert "Reading either first if an earlier session left it" in paragraph
    # The three remedies, and the ignored list apart.
    assert "if the work tree shows no change there, the edit did not happen, so make it or remove the claim" in paragraph
    assert "are listed apart, in `ignored`" in paragraph
    # The loop ends: a deliberate mention stays listed and does not block it.
    assert "Run the check again until every path left in `not_in_diff` is one a text names on purpose and says so." in paragraph
    assert "correct the story record itself (not only its scratch copy)" in paragraph
    assert "stage it if this commit changed it" in paragraph
    # The judgment half: the diff's own new claims.
    assert "the usual fix is to weaken the sentence, not to strengthen the code" in paragraph
    # Bounded: one pass, evidence already produced, no new run.
    assert "make one pass over the claims the diff itself adds" in paragraph
    assert "start no new run to back a sentence" in paragraph
    # A sentence softened in a staged file must reach the commit.
    assert "Re-stage every file this pass edited, in its own `git add` call" in paragraph
    assert "Run the same check before any re-commit or amend step 5 makes." in paragraph
    # An edit described by its content still needs its hunk, and a forward
    # reference the commit makes false is found and corrected.
    assert "read `git diff --cached` once and find the hunk for each edit the message or the notes say this commit makes" in paragraph
    assert "a forward reference to what it lands" in paragraph
    # The search names the story id, so a comment that cites the story is found.
    assert 'Search the project\'s own files with the Grep tool, case-insensitive, for this story\'s id, "does not exist yet" and "owed by"' in paragraph
    assert "leaving out the installed skill, the run folder and this story's own record and tests" in paragraph
    assert "correct a hit only when it refers to what this commit lands" in paragraph
    assert "log it to `.decision-log.md` for that story instead" in paragraph


def test_execute_carries_the_ignored_tree_rule_for_a_resume():
    text = EXECUTE.read_text(encoding="utf-8")
    start = text.index("\n1. `ucg-create-story`")
    end = text.index("\n2. Run the tests, lint, and build", start)
    between = text[start:end]
    assert "**On a gitignored artifact tree** (`impl_artifacts_tracked: false`, which preflight step 1 reports" in between
    assert "a resumed session reads in its `--assert-armed` manifest's `checks`" in between
    assert "or any other path `git check-ignore` reports, at run time" in between


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
