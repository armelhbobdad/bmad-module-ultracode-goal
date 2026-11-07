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
- `--artifacts-root` (repeatable): a name absent from the project root that
  exists under a given folder is read there, `ignored` only when every folder
  that holds it ignores it or lies outside the work tree; a name that exists
  from the project root, or under no folder, keeps its reading, and with no
  folder given the output is the one before the flag;
- `--tea-config` (#199): TEA's test-artifacts root, resolved from the config
  by preflight_check.py's own functions (a `{project-root}` in the path or the
  value, a relative or commented value, a missing file), is read as one more
  folder, so a bare `atdd-checklist-<story_id>.md` under an ignored root is
  `ignored` and under a tracked one stays in `not_in_diff`;
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
import shutil
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


def _case_insensitive(folder: Path) -> bool:
    probe = folder / "case-probe"
    probe.write_text("x", encoding="utf-8")
    try:
        return (folder / "CASE-PROBE").exists()
    finally:
        probe.unlink()


def test_a_real_path_named_in_another_case_matches_where_the_filesystem_ignores_case(repo):
    # #160 item 7: on Windows (and macOS by default) `Src/Guard.py` and the
    # staged `src/guard.py` are one file, and exists() says yes to both, so the
    # exact-match rule read the named path as not in the diff.
    if not _case_insensitive(repo):
        pytest.skip("needs a case-insensitive filesystem (the Windows leg runs it)")
    _stage(repo, "src/guard.py")
    out = cc.check("edit `Src/Guard.py`", repo)
    assert out["named"] == ["Src/Guard.py"]
    assert out["not_in_diff"] == []


def test_the_index_spelling_matches_after_a_case_only_rename(repo):
    # A case-only rename made without `git mv` leaves the index's spelling
    # (`docs/README.md`) and the work tree's (`docs/readme.md`) apart, and a
    # text may use either; both name the staged file.
    if not _case_insensitive(repo):
        pytest.skip("needs a case-insensitive filesystem (the Windows leg runs it)")
    (repo / "docs").mkdir()
    _stage(repo, "docs/README.md")
    os.rename(repo / "docs" / "README.md", repo / "docs" / "readme.md")
    for named in ("docs/readme.md", "docs/README.md"):
        assert cc.check(f"edit `{named}`", repo)["not_in_diff"] == [], named


def test_case_is_read_from_the_filesystem_itself(repo):
    _stage(repo, "src/guard.py")
    path = repo / "src" / "guard.py"
    assert cc._ignores_case(path, repo) is _case_insensitive(repo)
    assert cc._ignores_case(repo / "src", repo) is _case_insensitive(repo)
    # A segment with no letter is judged by the nearest one that has some.
    (repo / "docs" / "2024").mkdir(parents=True)
    assert cc._ignores_case(repo / "docs" / "2024", repo) is _case_insensitive(repo)
    # Nothing at or above the project root is probed: it can be another filesystem.
    (repo / "2025").mkdir()
    assert cc._ignores_case(repo / "2025", repo) is False
    # Nor a path that leaves the project through `..`.
    shared = repo.parent / "Shared"
    shared.mkdir()
    (shared / "x.md").write_text("x\n", encoding="utf-8")
    assert cc._ignores_case(repo / ".." / "Shared" / "x.md", repo) is False


def test_a_digits_only_segment_named_in_another_case_matches(repo):
    # `Docs/2024` names the staged `docs/2024/notes.md` where case is ignored:
    # the probe swaps `docs`, since `2024` has no case to swap.
    if not _case_insensitive(repo):
        pytest.skip("needs a case-insensitive filesystem (the Windows leg runs it)")
    (repo / "docs" / "2024").mkdir(parents=True)
    _stage(repo, "docs/2024/notes.md")
    assert cc.check("see `Docs/2024/`", repo)["not_in_diff"] == []


def test_a_real_path_named_in_another_case_stays_unmatched_where_case_counts(repo):
    # On a case-sensitive filesystem `Src/Guard.py` is another path, which does
    # not exist, so it matches loosely by its segments, and case still counts.
    if _case_insensitive(repo):
        pytest.skip("needs a case-sensitive filesystem")
    _stage(repo, "src/guard.py")
    assert cc.check("edit `Src/Guard.py`", repo)["not_in_diff"] == ["Src/Guard.py"]


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


# --- --artifacts-root: names a record writes from its own folders (#195) ------
#
# A record cites its scratch, evidence and run-folder files by the folder's own
# path (`sweep.sh`, `red-phase/INDEX.md`), which git was asked about from the
# project root, so every one landed in `not_in_diff` (71 entries on one record).
# Each test below is one row of the spec's matrix, and each holds 4.1.0's
# reading, with no root given, beside it.

_IMPL = "_bmad-output/implementation-artifacts"


def _ignore(repo: Path, *patterns: str) -> None:
    (repo / ".gitignore").write_text("".join(p + "\n" for p in patterns), encoding="utf-8")
    _git(repo, "add", ".gitignore")


def _artifact(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("captured\n", encoding="utf-8")
    return path


def test_a_bare_name_under_an_ignored_root_is_ignored(repo):
    _ignore(repo, "_bmad-output/")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "sweep.sh")
    _stage(repo, "src/guard.py")
    message = "ran sweep.sh against src/guard.py"
    # 4.1.0: a bare name absent at the root was never asked about.
    assert cc.check(message, repo)["not_in_diff"] == ["sweep.sh"]
    out = cc.check(message, repo, [repo / _IMPL, scratch])
    assert out["ignored"] == ["sweep.sh"]
    assert out["not_in_diff"] == [] and out["clean"] is True


def test_a_slash_name_under_an_ignored_root_is_ignored(repo):
    _ignore(repo, "_bmad-output/")
    evidence = repo / _IMPL / "evidence-4-1"
    _artifact(evidence, "red-phase/INDEX.md")
    message = "the red phase is captured in red-phase/INDEX.md"
    # 4.1.0: git was asked about `red-phase/INDEX.md` at the root, which no rule covers.
    assert cc.check(message, repo)["not_in_diff"] == ["red-phase/INDEX.md"]
    out = cc.check(message, repo, [repo / _IMPL, evidence])
    assert out["ignored"] == ["red-phase/INDEX.md"]
    assert out["not_in_diff"] == []


def test_a_name_under_a_root_no_rule_covers_stays_a_claim(repo):
    # A tracked artifact tree: the file could be committed, so naming it is a claim.
    evidence = repo / _IMPL / "evidence-4-1"
    _artifact(evidence, "red-phase.txt")
    out = cc.check("captured in red-phase.txt", repo, [repo / _IMPL, evidence])
    assert out["not_in_diff"] == ["red-phase.txt"]
    assert out["ignored"] == []


def test_a_tracked_file_under_an_ignored_root_stays_a_claim(repo):
    impl = repo / _IMPL
    _artifact(impl, "4-1-login.md")
    _git(repo, "add", _IMPL + "/4-1-login.md")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "story")
    _ignore(repo, "_bmad-output/")
    out = cc.check("updated 4-1-login.md", repo, [impl])
    assert out["not_in_diff"] == ["4-1-login.md"]
    assert out["ignored"] == []


@pytest.mark.parametrize("other", ["not-ignored", "tracked"])
def test_a_name_under_two_roots_is_ignored_only_when_every_holder_is(repo, other):
    scratch = repo / _IMPL / ".scratch-4-1"
    notes = repo / "notes"
    _artifact(scratch, "sweep.sh")
    _ignore(repo, "_bmad-output/")
    # Twin: the ignored copy alone reads ignored.
    assert cc.check("ran sweep.sh", repo, [scratch, notes])["ignored"] == ["sweep.sh"]
    _artifact(notes, "sweep.sh")
    if other == "tracked":
        _git(repo, "add", "notes/sweep.sh")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "notes")
        _ignore(repo, "_bmad-output/", "notes/")
    # Either copy is a file the text may mean, and one of them a commit can carry.
    out = cc.check("ran sweep.sh", repo, [scratch, notes])
    assert out["not_in_diff"] == ["sweep.sh"]
    assert out["ignored"] == []


def test_a_name_that_exists_from_the_project_root_keeps_its_root_reading(repo):
    _ignore(repo, "_bmad-output/")
    (repo / "README.md").write_text("readme\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "readme")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "README.md")
    _artifact(scratch, "src/fixture.ts")
    message = "see README.md and src/fixture.ts"
    out = cc.check(message, repo, [scratch])
    assert out["not_in_diff"] == ["README.md", "src/fixture.ts"]
    assert out["ignored"] == []
    assert out == cc.check(message, repo)


def test_a_name_that_exists_under_no_root_keeps_its_root_reading(repo):
    # Each root's ignore rule would cover the name, were it read there; it
    # exists nowhere, so it could be any file of that name.
    _ignore(repo, "_bmad-output/")
    impl = repo / _IMPL
    scratch = impl / ".scratch-4-1"
    scratch.mkdir(parents=True)
    message = "ran missing.sh and wrote red-phase/missing.md"
    out = cc.check(message, repo, [impl, scratch])
    assert out["not_in_diff"] == ["missing.sh", "red-phase/missing.md"]
    assert out["ignored"] == []
    assert out == cc.check(message, repo)


def test_a_name_under_a_root_outside_the_work_tree_is_ignored(repo, tmp_path):
    outside = tmp_path / "elsewhere" / "implementation-artifacts"
    _artifact(outside, "red-phase.txt")
    message = "captured in red-phase.txt"
    assert cc.check(message, repo)["not_in_diff"] == ["red-phase.txt"]
    out = cc.check(message, repo, [outside])
    assert out["ignored"] == ["red-phase.txt"]
    assert out["not_in_diff"] == []


def test_outside_is_read_from_the_top_level_not_the_project_root(subdir_project):
    # `other/` is outside the project root `app/` but inside the work tree, so
    # git is asked about it, and no rule covers it.
    top = subdir_project.parent
    _artifact(top / "other", "sweep.sh")
    out = cc.check("ran sweep.sh", subdir_project, [top / "other"])
    assert out["not_in_diff"] == ["sweep.sh"]
    (top / ".gitignore").write_text("other/\n", encoding="utf-8")
    _git(top, "add", ".gitignore")
    out = cc.check("ran sweep.sh", subdir_project, [top / "other"])
    assert out["ignored"] == ["sweep.sh"]


# A folder's copy never hides a name that can mean a file of the tree itself.


@pytest.mark.parametrize("state", ["tracked", "untracked"])
@pytest.mark.parametrize("name", ["guard.py", "hooks/guard.py"])
def test_a_name_a_deeper_tree_file_could_be_keeps_its_root_reading(repo, state, name):
    # The record means `src/hooks/guard.py`, unstaged; a scratch copy of the
    # same name must not turn the claim into `ignored` with `clean: true`.
    _ignore(repo, "_bmad-output/")
    _artifact(repo, "src/hooks/guard.py")
    if state == "tracked":
        _git(repo, "add", "src/hooks/guard.py")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "hooks")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, name)
    message = f"edited {name}"
    out = cc.check(message, repo, [repo / _IMPL, scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == [name] and out["clean"] is False


def test_a_tracked_file_deleted_in_the_work_tree_keeps_its_root_reading(repo):
    # The deletion is unstaged: the index still holds `old.py`, though the work
    # tree does not.
    _ignore(repo, "_bmad-output/")
    (repo / "old.py").unlink()
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "old.py")
    message = "removed old.py"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == ["old.py"]


def test_a_tree_file_the_commit_never_wrote_keeps_its_root_reading(repo):
    # The commit claims `src/new_helper.ts` and never wrote it; its only copy
    # is the prototype in scratch, and `src/` exists from the project root.
    _ignore(repo, "_bmad-output/")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "src/new_helper.ts")
    message = "adds src/new_helper.ts"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == ["src/new_helper.ts"]


# The copy's own folder holds no tree file: a capture beside the copy, the
# files of a held folder, or a tracked sibling must not send the name back to
# the project root's reading (an ignore rule anchored there).
_BESIDE = {
    "alone": ("coverage/summary.json", "/coverage/", ("coverage/summary.json",), False),
    "sibling": ("coverage/summary.json", "/coverage/", ("coverage/summary.json", "coverage/lcov.info"), False),
    "folder": ("coverage/html/", "/coverage/", ("coverage/html/index.html", "coverage/html/app.js"), False),
    "tracked sibling": ("reports/summary.md", "/reports/", ("reports/summary.md", "reports/other.md"), True),
}


def _held_beside(project: Path, git_root: Path, case: str) -> None:
    name, rule, rels, tracked = _BESIDE[case]
    evidence = project / _IMPL / "evidence-4-1"
    for rel in rels:
        _artifact(evidence, rel)
    if tracked:
        _commit(git_root, *((evidence / rel).relative_to(git_root).as_posix() for rel in rels))
    (project / ".gitignore").write_text(rule + "\n", encoding="utf-8")
    _git(project, "add", ".gitignore")
    message = f"see {name}"
    assert cc.check(message, project)["ignored"] == [name]
    out = cc.check(message, project, [project / _IMPL, evidence])
    assert out["not_in_diff"] == [name]
    assert out["ignored"] == []


@pytest.mark.parametrize("case", list(_BESIDE))
def test_a_held_name_is_not_read_from_the_project_root(repo, case):
    # `/coverage/` ignores `coverage/summary.json` from the project root, but
    # the copy the record means sits in a tracked artifacts tree, where no rule
    # covers it: the root reading must not stand in for the copy's.
    _held_beside(repo, repo, case)


def test_a_name_that_climbs_out_of_its_root_keeps_its_root_reading(repo, tmp_path):
    # Read under the scratch root, the name leaves it, and the work tree, for a
    # file that exists there; a `..` name is never read under a root.
    _ignore(repo, "_bmad-output/")
    scratch = repo / _IMPL / ".scratch-4-1"
    (scratch / "red-phase").mkdir(parents=True)
    (tmp_path / "x.md").write_text("outside\n", encoding="utf-8")
    name = "red-phase/../../../../../x.md"
    assert (scratch / name).resolve() == (tmp_path / "x.md").resolve()
    message = f"see {name}"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == [name]


def test_a_held_folder_name_under_an_ignored_root_is_ignored(repo):
    _ignore(repo, "_bmad-output/")
    evidence = repo / _IMPL / "evidence-4-1"
    _artifact(evidence, "red-phase/INDEX.md")
    message = "the captures are in red-phase/"
    assert cc.check(message, repo)["not_in_diff"] == ["red-phase/"]
    out = cc.check(message, repo, [evidence])
    assert out["ignored"] == ["red-phase/"]
    assert out["not_in_diff"] == []


def test_a_link_in_an_ignored_root_is_read_where_it_points(repo):
    # The link sits in ignored scratch, but the file it names is tracked: the
    # commit can carry an edit to it.
    _ignore(repo, "_bmad-output/")
    scratch = repo / _IMPL / ".scratch-4-1"
    scratch.mkdir(parents=True)
    try:
        (scratch / "notes.md").symlink_to(repo / "src" / "guard.py")
    except OSError:
        pytest.skip("this platform cannot create a symlink here")
    out = cc.check("edited notes.md", repo, [scratch])
    assert out["not_in_diff"] == ["notes.md"]
    assert out["ignored"] == []


def test_a_link_to_a_tracked_file_of_its_name_is_read_where_it_points(repo):
    # The link's target is the copy the name reads, not a tree file beside it:
    # read as one, the name would fall back to `/hooks/`, which ignores it from
    # the project root, though the commit can carry an edit to the target.
    _ignore(repo, "_bmad-output/", "/hooks/")
    _artifact(repo, "src/hooks/guard.py")
    _commit(repo, "src/hooks/guard.py")
    scratch = repo / _IMPL / ".scratch-4-1"
    (scratch / "hooks").mkdir(parents=True)
    try:
        (scratch / "hooks" / "guard.py").symlink_to(repo / "src" / "hooks" / "guard.py")
    except OSError:
        pytest.skip("this platform cannot create a symlink here")
    message = "edited hooks/guard.py"
    assert cc.check(message, repo)["ignored"] == ["hooks/guard.py"]
    out = cc.check(message, repo, [scratch])
    assert out["not_in_diff"] == ["hooks/guard.py"]
    assert out["ignored"] == []


def test_a_root_spelled_through_a_link_is_inside_the_work_tree(repo, tmp_path):
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(repo, target_is_directory=True)
    except OSError:
        pytest.skip("this platform cannot create a directory symlink here")
    top = repo.resolve()
    assert cc._in_tree(alias / "a" / "x.md", top) == top / "a" / "x.md"
    assert cc._in_tree(tmp_path / "elsewhere" / "x.md", top) is None


def _commit(repo: Path, *rels: str) -> None:
    _git(repo, "add", *rels)
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "add")


def test_a_slash_name_whose_folder_the_tree_holds_keeps_its_root_reading(repo):
    # Never written, and named by its trailing folder: `src/hooks/` holds a
    # tracked file, so the scratch prototype must not hide the claim.
    _ignore(repo, "_bmad-output/")
    _artifact(repo, "src/hooks/guard.py")
    _commit(repo, "src/hooks/guard.py")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "hooks/new_guard.py")
    message = "adds hooks/new_guard.py"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == ["hooks/new_guard.py"]


@pytest.mark.parametrize("case", ["hooks", "legacy"])
def test_a_folder_name_the_tree_holds_keeps_its_root_reading(repo, case):
    # `hooks/` is a folder of a tracked file; `legacy/` is a tracked folder
    # deleted in the work tree, its deletion unstaged.
    _ignore(repo, "_bmad-output/")
    if case == "hooks":
        _artifact(repo, "src/hooks/guard.py")
        _commit(repo, "src/hooks/guard.py")
    else:
        _artifact(repo, "legacy/a.py")
        _commit(repo, "legacy/a.py")
        (repo / "legacy" / "a.py").unlink()
        (repo / "legacy").rmdir()
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, f"{case}/notes.md")
    message = f"see {case}/"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == [f"{case}/"]


@pytest.mark.parametrize("project", ["repo", "subdir_project"])
def test_a_slash_name_under_a_project_root_folder_keeps_its_root_reading(request, project):
    # `src/` exists from the project root, `src/new/` does not; below the top
    # level, `src/` exists under `app/` only.
    root = request.getfixturevalue(project)
    _ignore(root, "_bmad-output/")
    scratch = root / _IMPL / ".scratch-4-1"
    _artifact(scratch, "src/new/helper.ts")
    message = "adds src/new/helper.ts"
    out = cc.check(message, root, [scratch])
    assert out == cc.check(message, root)
    assert out["not_in_diff"] == ["src/new/helper.ts"]


@pytest.mark.parametrize("name", ["hooks/sub/new.py", "hooks/sub/"])
def test_a_name_whose_folder_part_spans_two_folders_keeps_its_root_reading(repo, name):
    # `pkg/hooks/sub/` holds a tracked file, so `hooks/sub` names its folders.
    _ignore(repo, "_bmad-output/")
    _artifact(repo, "pkg/hooks/sub/x.py")
    _commit(repo, "pkg/hooks/sub/x.py")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "hooks/sub/new.py")
    message = f"see {name}"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == [name]


@pytest.mark.parametrize("name", ["hooks//guard.py", "hooks/./guard.py"])
def test_a_name_with_an_empty_or_dot_segment_keeps_its_root_reading(repo, name):
    # pathlib would read either as `hooks/guard.py` under the root, and the
    # tree lookup as written, so the scratch copy would hide the tracked file.
    _ignore(repo, "_bmad-output/")
    _artifact(repo, "src/hooks/guard.py")
    _commit(repo, "src/hooks/guard.py")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "hooks/guard.py")
    message = f"edited {name}"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == [name]


@pytest.mark.parametrize("contents", ["empty", "ignored-only"])
def test_a_folder_at_the_project_root_keeps_its_root_reading(repo, contents):
    # git lists neither folder, so only the folder's own existence says the
    # name can mean it.
    _ignore(repo, "_bmad-output/", "*.bin")
    (repo / "cache").mkdir()
    if contents == "ignored-only":
        (repo / "cache" / "blob.bin").write_bytes(b"\0")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "cache/notes.md")
    message = "cleared cache/"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == ["cache/"]


def test_an_ignored_file_at_the_project_root_keeps_its_root_reading(repo):
    # The root file is ignored and its copy sits under a folder no rule covers.
    _ignore(repo, "/notes.txt")
    (repo / "notes.txt").write_text("root\n", encoding="utf-8")
    evidence = repo / _IMPL / "evidence-4-1"
    _artifact(evidence, "notes.txt")
    message = "see notes.txt"
    out = cc.check(message, repo, [evidence])
    assert out == cc.check(message, repo)
    assert out["ignored"] == ["notes.txt"]


@pytest.mark.parametrize("fails", ["_listed", "_toplevel"])
def test_a_tree_git_cannot_read_keeps_every_root_reading(repo, monkeypatch, fails):
    _ignore(repo, "_bmad-output/", "notes/")
    _artifact(repo, "src/hooks/guard.py")
    _commit(repo, "src/hooks/guard.py")
    scratch = repo / _IMPL / ".scratch-4-1"
    for rel in ("sweep.sh", "guard.py", "notes/x.md"):
        _artifact(scratch, rel)
    message = "ran sweep.sh on guard.py, notes in notes/x.md"
    expected = cc.check(message, repo)
    monkeypatch.setattr(cc, fails, lambda project_root: None)
    out = cc.check(message, repo, [scratch])
    assert out == expected
    assert out["not_in_diff"] == ["sweep.sh", "guard.py"]
    assert out["ignored"] == ["notes/x.md"]


# BMAD below the top level (a monorepo's `app/`): the tree outside the project
# root is the tree too.


def _app_scratch(app: Path) -> Path:
    (app / ".gitignore").write_text("_bmad-output/\n", encoding="utf-8")
    _git(app, "add", ".gitignore")
    return app / _IMPL / ".scratch-4-1"


@pytest.mark.parametrize(("rel", "tracked"), [("tools/lint.py", True), ("tools/new_check.py", False)])
def test_a_name_a_top_level_file_could_be_keeps_its_root_reading(subdir_project, rel, tracked):
    app, top = subdir_project, subdir_project.parent
    _artifact(top, rel)
    if tracked:
        _commit(top, rel)
    scratch = _app_scratch(app)
    name = rel.rsplit("/", 1)[1]
    _artifact(scratch, name)
    message = f"ran {name}"
    out = cc.check(message, app, [app / _IMPL, scratch])
    assert out == cc.check(message, app)
    assert out["not_in_diff"] == [name]


def test_a_slash_name_under_a_top_level_folder_keeps_its_root_reading(subdir_project):
    # `.github/` exists from the top level only, and holds no file of that path.
    app, top = subdir_project, subdir_project.parent
    _artifact(top, ".github/CODEOWNERS")
    _commit(top, ".github/CODEOWNERS")
    scratch = _app_scratch(app)
    _artifact(scratch, ".github/workflows/ci.yml")
    message = "adds .github/workflows/ci.yml"
    out = cc.check(message, app, [scratch])
    assert out == cc.check(message, app)
    assert out["not_in_diff"] == [".github/workflows/ci.yml"]


@pytest.mark.parametrize("case", list(_BESIDE))
def test_a_held_name_below_the_top_level_is_read_from_its_own_copy(subdir_project, case):
    # `app/.gitignore`'s anchored rule ignores the name from the project root;
    # the copy the record means sits in app's tracked artifacts tree.
    _held_beside(subdir_project, subdir_project.parent, case)


@pytest.mark.parametrize("case", ["tracked", "untracked", "outside"])
def test_a_link_in_an_artifacts_root_is_read_where_it_sits_too(repo, tmp_path, case):
    # A run folder tracked in part, whose own `.gitignore` ignores the run
    # folders: git keeps and commits a link at its own path, so a claim about
    # the link is one whatever its target is (an ignored scratch file, or a
    # file outside the work tree).
    impl = repo / _IMPL
    scratch, evidence = impl / ".scratch-1-2", impl / "evidence-1-2"
    _artifact(scratch, "draft.md")
    _artifact(scratch, "draft2.md")
    evidence.mkdir()
    (impl / ".gitignore").write_text(".scratch-*/\nevidence-*/\n", encoding="utf-8")
    name = {"tracked": "current.md", "untracked": "latest.md", "outside": "team-notes.md"}[case]
    target = {"outside": str(_artifact(tmp_path / "outside", "notes.md"))}.get(case, ".scratch-1-2/draft.md")
    try:
        (impl / name).symlink_to(target)
    except OSError:
        pytest.skip("this platform cannot create a symlink here")
    if case == "tracked":
        _commit(repo, f"{_IMPL}/.gitignore", f"{_IMPL}/{name}")
        # Retargeted, and the change left unstaged.
        (impl / name).unlink()
        (impl / name).symlink_to(".scratch-1-2/draft2.md")
    message = f"updated {name}"
    out = cc.check(message, repo, [impl, scratch, evidence])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == [name]


@pytest.mark.parametrize("change", ["rename", "delete"])
def test_a_folder_a_staged_change_took_out_of_the_listing_keeps_its_root_reading(repo, change):
    # The commit moves or empties `lib/old/`, so the listing no longer holds
    # it; a new file the text claims there must not hide behind a scratch copy.
    _ignore(repo, "_bmad-output/")
    _artifact(repo, "lib/old/a.py")
    _commit(repo, "lib/old/a.py")
    if change == "rename":
        _git(repo, "mv", "lib/old", "lib/new")
    else:
        _git(repo, "rm", "-q", "lib/old/a.py")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "old/b.py")
    message = "adds old/b.py"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == ["old/b.py"]


def _add_submodule(repo: Path, tmp_path: Path) -> None:
    """A local submodule at `vendor/lib` tracking `vendored_helper.py`, with an
    untracked `draft_helper.py` in its checkout; skips where git cannot add one."""
    lib = tmp_path / "lib-src"
    _artifact(lib, "vendored_helper.py")
    _git(lib, "init", "-q")
    _git(lib, "config", "user.email", "t@example.com")
    _git(lib, "config", "user.name", "t")
    _commit(lib, "vendored_helper.py")
    proc = subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(lib), "vendor/lib"],
        cwd=repo, capture_output=True, timeout=60,
    )
    if proc.returncode != 0:
        pytest.skip("this git cannot add a local submodule here")
    _artifact(repo / "vendor" / "lib", "draft_helper.py")


@pytest.mark.parametrize("name", ["vendored_helper.py", "draft_helper.py"])
def test_a_submodule_file_keeps_its_root_reading(repo, tmp_path, name):
    # `vendored_helper.py` is tracked in the submodule; `draft_helper.py` is
    # an untracked, unignored file in its checkout.
    _add_submodule(repo, tmp_path)
    _ignore(repo, "_bmad-output/")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, name)
    message = f"patched {name}"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == [name]


def test_a_folder_holding_no_listed_file_in_a_submodule_keeps_its_root_reading(repo, tmp_path):
    # An empty `core/plugins/` in the submodule's checkout: its `--directory`
    # listing names the folder, as the superproject's does outside it.
    _add_submodule(repo, tmp_path)
    (repo / "vendor" / "lib" / "core" / "plugins").mkdir(parents=True)
    _ignore(repo, "_bmad-output/")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "core/plugins/new.py")
    message = "adds core/plugins/new.py"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == ["core/plugins/new.py"]


@pytest.mark.parametrize("contents", ["empty", "ignored-only"])
@pytest.mark.parametrize("project", ["repo", "subdir_project"])
def test_a_folder_holding_no_listed_file_keeps_its_root_reading(request, project, contents):
    # git lists a file in no folder that holds no listed file; `--directory`
    # lists the folder itself, here beside the tracked files of `src/`.
    root = request.getfixturevalue(project)
    _ignore(root, "_bmad-output/", "*.pyc")
    (root / "src" / "cache").mkdir(parents=True)
    if contents == "ignored-only":
        (root / "src" / "cache" / "mod.pyc").write_bytes(b"\0")
    scratch = root / _IMPL / ".scratch-4-1"
    _artifact(scratch, "cache/new.py")
    message = "adds cache/new.py"
    out = cc.check(message, root, [scratch])
    assert out == cc.check(message, root)
    assert out["not_in_diff"] == ["cache/new.py"]


def test_a_folder_inside_an_untracked_folder_is_the_stated_limit(repo):
    # Pinned so a change to it is deliberate: git lists only the topmost
    # untracked folder (`lib/`), so an empty `lib/plugins/` protects nothing,
    # and a claimed, never-written `plugins/new.py` reads as its scratch copy.
    # The hunk pass in execute.md is what catches it.
    _ignore(repo, "_bmad-output/")
    (repo / "lib" / "plugins").mkdir(parents=True)
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "plugins/new.py")
    message = "adds plugins/new.py"
    assert cc.check(message, repo)["not_in_diff"] == ["plugins/new.py"]
    out = cc.check(message, repo, [scratch])
    assert out["ignored"] == ["plugins/new.py"]
    assert out["not_in_diff"] == []


def test_a_listed_folder_in_the_copys_folder_that_ends_with_the_name_keeps_its_root_reading(repo):
    # The copy `cache/` is ignored where it sits; git lists the empty
    # `sub/cache/` beside it as `.../sub/cache/`, and the name can mean it, as
    # it could a listed file of that name.
    impl = repo / _IMPL
    _artifact(impl, "cache/x.md")
    _artifact(impl, "sub/real.md")
    _commit(repo, f"{_IMPL}/sub/real.md")
    (impl / "sub" / "cache").mkdir()
    (impl / ".gitignore").write_text("/cache/\n", encoding="utf-8")
    message = "cleared cache/"
    out = cc.check(message, repo, [impl])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == ["cache/"]


def test_a_committable_file_in_the_copys_folder_that_ends_with_the_name_keeps_its_root_reading(repo):
    # The copy `notes.md` is ignored where it sits, but `sub/notes.md` beside
    # it is a written, unstaged file a commit can carry, and the name can mean
    # it: a path that ends with the name protects it wherever it lies.
    impl = repo / _IMPL
    _artifact(impl, "notes.md")
    _artifact(impl, "sub/notes.md")
    (impl / ".gitignore").write_text("/notes.md\n", encoding="utf-8")
    message = "see notes.md"
    out = cc.check(message, repo, [impl])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == ["notes.md"]


def test_a_slash_name_whose_first_folder_the_tree_holds_keeps_its_root_reading(repo):
    # The tree holds `hooks/` but no `hooks/sub/`: from the project root only
    # the first folder is needed, so the tree needs no more either.
    _ignore(repo, "_bmad-output/")
    _artifact(repo, "src/hooks/x.py")
    _commit(repo, "src/hooks/x.py")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "hooks/sub/new.py")
    message = "adds hooks/sub/new.py"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == ["hooks/sub/new.py"]


@pytest.mark.parametrize("gone", ["moved", "deleted", "deleted on disk"])
@pytest.mark.parametrize("project", ["repo", "subdir_project"])
def test_a_top_level_folder_the_disk_lacks_keeps_its_root_reading(request, project, gone):
    # `tools/` is gone from the disk, moved or deleted by the commit or on
    # disk alone, but the index or the staged names still hold it.
    root = request.getfixturevalue(project)
    top = root if project == "repo" else root.parent
    _ignore(root, "_bmad-output/")
    _artifact(top, "tools/x.py")
    _commit(top, "tools/x.py")
    if gone == "moved":
        _git(top, "mv", "tools", "kit")
    elif gone == "deleted":
        _git(top, "rm", "-q", "-r", "tools")
    else:
        shutil.rmtree(top / "tools")
    scratch = root / _IMPL / ".scratch-4-1"
    _artifact(scratch, "tools/sub/new.py")
    message = "adds tools/sub/new.py"
    out = cc.check(message, root, [scratch])
    assert out == cc.check(message, root)
    assert out["not_in_diff"] == ["tools/sub/new.py"]


def test_a_case_only_rename_git_does_not_see_keeps_its_root_reading(repo):
    # With `core.ignorecase=true`, a rename made without `git mv` leaves only
    # the index's spelling listed.
    _ignore(repo, "_bmad-output/")
    _artifact(repo, "Docs/Guide.md")
    _commit(repo, "Docs/Guide.md")
    (repo / "Docs").rename(repo / "docs-tmp")
    (repo / "docs-tmp").rename(repo / "docs")
    (repo / "docs" / "Guide.md").rename(repo / "docs" / "guide.md")
    _git(repo, "config", "core.ignorecase", "true")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "guide.md")
    message = "edited guide.md"
    out = cc.check(message, repo, [scratch])
    assert out == cc.check(message, repo)
    assert out["not_in_diff"] == ["guide.md"]


def test_the_reporters_names_in_an_ignored_tree_are_ignored(repo):
    # #195's own names, each relative to the folder that holds it, in a
    # gitignored artifacts tree: none is a claim a commit can carry.
    _ignore(repo, "_bmad-output/")
    impl = repo / _IMPL
    scratch, evidence = impl / ".scratch-4-1", impl / "evidence-4-1"
    _artifact(scratch, "sweep.sh")
    _artifact(scratch, "mutation/table.json")
    _artifact(evidence, "red-phase/INDEX.md")
    message = "ran sweep.sh; rows in mutation/table.json; red phase in red-phase/INDEX.md and red-phase/"
    out = cc.check(message, repo, [impl, scratch, evidence])
    assert out["ignored"] == ["sweep.sh", "mutation/table.json", "red-phase/INDEX.md", "red-phase/"]
    assert out["not_in_diff"] == [] and out["clean"] is True


# Each listing `_listed` runs, by a flag only its command carries: the
# submodules' files, the folders, the index's entries, and the untracked files
# of a submodule's checkout.
_LISTINGS = {
    "submodules": lambda argv: "--recurse-submodules" in argv,
    "folders": lambda argv: "--directory" in argv,
    "entries": lambda argv: "-s" in argv,
    "submodule checkout": lambda argv: argv == ["git", "ls-files", "-z", "--others", "--exclude-standard"],
}


@pytest.mark.parametrize("listing", list(_LISTINGS))
def test_a_submodule_listing_that_fails_keeps_every_root_reading(repo, tmp_path, monkeypatch, listing):
    # The first listing alone would read `sweep.sh` under its root; with any
    # other listing failed, what the tree holds is unknown.
    if listing == "submodule checkout":
        _add_submodule(repo, tmp_path)
    _ignore(repo, "_bmad-output/")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "sweep.sh")
    message = "ran sweep.sh"
    expected = cc.check(message, repo)
    run = subprocess.run

    def fails_on_submodules(argv, *args, **kwargs):
        if _LISTINGS[listing](argv):
            return subprocess.CompletedProcess(argv, 128, b"", b"fatal: cannot list")
        return run(argv, *args, **kwargs)

    monkeypatch.setattr(cc.subprocess, "run", fails_on_submodules)
    out = cc.check(message, repo, [scratch])
    assert out == expected
    assert out["not_in_diff"] == ["sweep.sh"]


def test_with_no_root_the_reading_is_unchanged(repo):
    _ignore(repo, "_bmad-output/")
    scratch = repo / _IMPL / ".scratch-4-1"
    _artifact(scratch, "sweep.sh")
    _artifact(scratch, "red-phase/INDEX.md")
    message = "ran sweep.sh, see red-phase/INDEX.md and _bmad-output/implementation-artifacts/ledger.md"
    out = cc.check(message, repo)
    assert out == cc.check(message, repo, ())
    assert out["not_in_diff"] == ["sweep.sh", "red-phase/INDEX.md"]
    assert out["ignored"] == ["_bmad-output/implementation-artifacts/ledger.md"]


def test_the_cli_reads_each_artifacts_root_it_is_given(repo, tmp_path):
    # The reporter's shape: a record citing its run-folder, scratch and
    # evidence files by their own folders' paths, beside a real claim.
    _ignore(repo, "_bmad-output/")
    impl = repo / _IMPL
    scratch = impl / ".scratch-4-1"
    evidence = impl / "evidence-4-1"
    _artifact(impl, "mutation-ledger-4-1.md")
    _artifact(scratch, "sweep.sh")
    _artifact(evidence, "red-phase/INDEX.md")
    message = tmp_path / "message.txt"
    message.write_text(
        "ran sweep.sh; rows in mutation-ledger-4-1.md; red phase in red-phase/INDEX.md; edited src/fixture.ts\n",
        encoding="utf-8",
    )

    def run(*roots: str, cwd: Path | None = None) -> dict:
        argv = [sys.executable, str(SCRIPT), "--message", str(message), "--project-root", str(repo)]
        for root in roots:
            argv += ["--artifacts-root", root]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60, cwd=cwd)
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    out = run(str(impl), str(scratch), str(evidence))
    assert out["ignored"] == ["sweep.sh", "mutation-ledger-4-1.md", "red-phase/INDEX.md"]
    assert out["not_in_diff"] == ["src/fixture.ts"]
    # One root reads only the names it holds.
    assert run(str(scratch))["ignored"] == ["sweep.sh"]
    # A relative root is read from the working directory, as `--project-root` is.
    assert run(_IMPL + "/.scratch-4-1", cwd=repo)["ignored"] == ["sweep.sh"]
    # No root: 4.1.0's output.
    assert run()["not_in_diff"] == ["sweep.sh", "mutation-ledger-4-1.md", "red-phase/INDEX.md", "src/fixture.ts"]


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


# --- --tea-config: TEA's test-artifacts root (#199) ----------------------------
#
# A record names the story's ATDD checklist bare, `atdd-checklist-<story_id>.md`,
# and it lives in TEA's test-artifacts root, which none of the three folders
# step 4 names is. On a gitignored root the name sat in `not_in_diff`. The root
# is read as preflight reads it, by preflight_check.py's own functions.

pc = _load("preflight_check", SCRIPTS / "preflight_check.py")

_TEA = "_bmad-output/test-artifacts"
_CHECKLIST = "atdd-checklist-1-2.md"


def _tea_config(repo: Path, body: str | None, rel: str = "_bmad/tea/config.yaml") -> Path:
    path = repo / rel
    if body is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return path


def _preflight_root(config: str, repo: Path) -> Path:
    root = repo.resolve()
    return pc._tea_artifacts_root(root, pc._read_toml_or_yaml_flags(pc._resolve(config, root)))


def test_a_checklist_under_a_gitignored_tea_root_is_ignored(repo):
    _ignore(repo, "_bmad-output/")
    config = _tea_config(repo, 'test_artifacts: "{project-root}/_bmad-output/test-artifacts"\n')
    _artifact(repo / _TEA, _CHECKLIST)
    scratch = repo / _IMPL / ".scratch-1-2"
    _artifact(scratch, "sweep.sh")
    _stage(repo, "src/guard.py")
    message = f"ran sweep.sh; un-skipped every case {_CHECKLIST} lists; edited src/guard.py and src/fixture.ts"
    roots = [repo / _IMPL, scratch]
    before = cc.check(message, repo, roots)
    assert before["not_in_diff"] == [_CHECKLIST, "src/fixture.ts"]
    tea_root = cc._tea_root(str(config), repo)
    assert tea_root == (repo / _TEA).resolve()
    out = cc.check(message, repo, [*roots, tea_root])
    assert out["ignored"] == ["sweep.sh", _CHECKLIST]
    assert out["not_in_diff"] == ["src/fixture.ts"]
    # No other name's reading moves: only the checklist leaves `not_in_diff`.
    assert out["named"] == before["named"] and out["staged"] == before["staged"]
    assert before["ignored"] == ["sweep.sh"]
    # The checklist alone, with nothing else left: clean.
    assert cc.check(f"un-skipped every case {_CHECKLIST} lists", repo, [tea_root])["clean"] is True


def test_a_checklist_under_a_tracked_tea_root_stays_a_claim(repo):
    config = _tea_config(repo, "test_artifacts: _bmad-output/test-artifacts\n")
    _artifact(repo / _TEA, _CHECKLIST)
    _commit(repo, _TEA + "/" + _CHECKLIST)
    out = cc.check(f"updated {_CHECKLIST}", repo, [cc._tea_root(str(config), repo)])
    assert out["not_in_diff"] == [_CHECKLIST]
    assert out["ignored"] == []


# Each row: the config's text (None: no file), and the root preflight resolves.
_TEA_VALUES = {
    "relative, with an inline comment": ("test_artifacts: qa/art  # where TEA writes\n", "qa/art"),
    "a {project-root} value": ('test_artifacts: "{project-root}/qa/art"\n', "qa/art"),
    "a quoted relative value": ("test_artifacts: 'qa/art'\n", "qa/art"),
    "no test_artifacts key": ("tea_use_playwright_utils: true\n", _TEA),
    "an empty value": ("test_artifacts:\n", _TEA),
    "no config file": (None, _TEA),
}


@pytest.mark.parametrize("case", list(_TEA_VALUES))
def test_the_tea_root_resolves_as_preflight_resolves_it(repo, case):
    body, expected = _TEA_VALUES[case]
    config = _tea_config(repo, body)
    for spelled in (str(config), "{project-root}/_bmad/tea/config.yaml", "_bmad/tea/config.yaml"):
        root = cc._tea_root(spelled, repo)
        assert root == (repo / expected).resolve(), spelled
        assert root == _preflight_root(spelled, repo), spelled
    # The name a record cites is read there, the comment never part of the folder.
    _ignore(repo, "qa/", "_bmad-output/")
    _artifact(repo / expected, _CHECKLIST)
    assert cc.check(f"see {_CHECKLIST}", repo, [cc._tea_root(str(config), repo)])["ignored"] == [_CHECKLIST]


def test_an_absolute_tea_root_is_read_where_it_is(repo, tmp_path):
    elsewhere = tmp_path / "tea-out"
    config = _tea_config(repo, f"test_artifacts: {elsewhere.as_posix()}\n")
    assert cc._tea_root(str(config), repo) == elsewhere == _preflight_root(str(config), repo)
    # Outside the work tree: no commit can carry it.
    _artifact(elsewhere, _CHECKLIST)
    assert cc.check(f"see {_CHECKLIST}", repo, [elsewhere])["ignored"] == [_CHECKLIST]


def test_the_tea_root_is_preflights_own_reading_not_a_copy():
    source = SCRIPT.read_text(encoding="utf-8")
    # One reader: a copy drifts (formalize_check.py's once lost the inline-comment strip).
    for name in ("def _read_toml_or_yaml_flags", "def _strip_inline_comment", "def _tea_artifacts_root", "tomllib"):
        assert name not in source, name
    for call in ("_read_toml_or_yaml_flags(", "_tea_artifacts_root(", "_resolve("):
        assert "preflight_check." + call in source, call
    # Still stdlib-only, so `uv run` needs no environment for it.
    assert "# dependencies = []\n" in source
    # Imported lazily: a run without --tea-config never loads preflight_check.
    assert "\nimport preflight_check" not in source


def test_an_unreadable_tea_config_adds_no_root(repo, monkeypatch):
    config = _tea_config(repo, "test_artifacts: qa/art\n")
    assert cc._tea_root(str(config), repo) == (repo / "qa/art").resolve()
    loaded = sys.modules["preflight_check"]

    def unreadable(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(loaded, "_read_toml_or_yaml_flags", unreadable)
    assert cc._tea_root(str(config), repo) is None


def test_the_cli_runs_on_when_the_tea_config_cannot_be_read(repo, tmp_path, monkeypatch, capsys):
    # A root the reader would find, so a folder added would change the output.
    _ignore(repo, "qa/")
    config = _tea_config(repo, "test_artifacts: qa/art\n")
    _artifact(repo / "qa/art", _CHECKLIST)
    message = tmp_path / "message.txt"
    message.write_text(f"see {_CHECKLIST}; edited src/fixture.ts\n", encoding="utf-8")
    argv = ["--message", str(message), "--project-root", str(repo)]
    assert cc._tea_root(str(config), repo) is not None  # loads preflight_check
    assert cc.main(argv) == 0
    without = json.loads(capsys.readouterr().out)

    def unreadable(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(sys.modules["preflight_check"], "_read_toml_or_yaml_flags", unreadable)
    assert cc.main([*argv, "--tea-config", str(config)]) == 0
    assert json.loads(capsys.readouterr().out) == without
    assert without["not_in_diff"] == [_CHECKLIST, "src/fixture.ts"]


def test_the_cli_reads_the_tea_root_from_a_literal_project_root_path(repo, tmp_path):
    # execute.md's command as the conductor may run it: the default
    # `{workflow.tea_config_path}` still holds `{project-root}` unexpanded. The
    # root is not the default one, so only a config read through that path
    # finds it.
    _ignore(repo, "qa/", "_bmad-output/")
    _tea_config(repo, 'test_artifacts: "{project-root}/qa/tea-out"  # TEA output\n')
    _artifact(repo / "qa/tea-out", _CHECKLIST)
    message = tmp_path / "message.txt"
    message.write_text(f"un-skipped every case {_CHECKLIST} lists; edited src/fixture.ts\n", encoding="utf-8")

    def run(*extra: str, project_root: str | None = str(repo), cwd: Path | None = None) -> dict:
        argv = [sys.executable, str(SCRIPT), "--message", str(message)]
        if project_root is not None:
            argv += ["--project-root", project_root]
        proc = subprocess.run([*argv, *extra], capture_output=True, text=True, timeout=60, cwd=cwd)
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    literal = "{project-root}/_bmad/tea/config.yaml"
    out = run("--tea-config", literal)
    assert out["ignored"] == [_CHECKLIST]
    assert out["not_in_diff"] == ["src/fixture.ts"]
    # The default `--project-root`, the working directory, reads the same root,
    # and so does a relative one, `{project-root}` read as its absolute path.
    assert run("--tea-config", literal, project_root=None, cwd=repo)["ignored"] == [_CHECKLIST]
    assert run("--tea-config", literal, project_root=repo.name, cwd=repo.parent)["ignored"] == [_CHECKLIST]
    # With no flag: the reading before it.
    assert run()["not_in_diff"] == [_CHECKLIST, "src/fixture.ts"]
    # A missing config never errors: the default root is read instead.
    missing = "{project-root}/_bmad/tea/missing.yaml"
    assert run("--tea-config", missing)["not_in_diff"] == [_CHECKLIST, "src/fixture.ts"]
    _artifact(repo / _TEA, _CHECKLIST)
    assert run("--tea-config", missing)["ignored"] == [_CHECKLIST]


# --- execute.md step 4 --------------------------------------------------------


def _claim_paragraph() -> tuple[str, str]:
    text = EXECUTE.read_text(encoding="utf-8")
    start = text.index("**Check the record's claims before the commit.**")
    end = text.index("\n5. **Re-verify on the committed HEAD.**", start)
    step4 = text.rfind("\n4. **Commit at green**", 0, start)
    assert step4 != -1 and text.find("\n5. ", step4, start) == -1, "the check sits inside step 4"
    return text[start:end], text


# Step 4's closing sentence (#218): before an amend the check compares the
# texts with what the amend would commit, so a path HEAD already carries is not
# listed, and the hunk pass reads the amend's whole diff.
_AMEND_SENTENCE = (
    "Run the same check before any re-commit step 5 makes, and before an amend with `--amend` added, on every run "
    "for that amend, a reword's re-run included: it compares the texts with what the amend would commit (the index "
    "against `HEAD`'s first parent, or the empty tree at a root commit), so a path the amended commit already "
    "carries from `HEAD` stays out of `not_in_diff`, and for that amend the hunk pass reads "
    "`git diff --cached <base>`, with the `base` the check printed."
)
_AMEND_SENTENCE_PRE = "Run the same check before any re-commit or amend step 5 makes."


def _runs_the_amend_check(paragraph: str) -> bool:
    return bool(
        "before any re-commit step 5 makes" in paragraph
        and "before an amend with `--amend` added" in paragraph
        and "on every run for that amend, a reword's re-run included" in paragraph
        and "the index against `HEAD`'s first parent, or the empty tree at a root commit" in paragraph
        # `<base>` for every amend: neither a root commit nor a shallow
        # clone's oldest commit has a `HEAD~1`.
        and "for that amend the hunk pass reads `git diff --cached <base>`, with the `base` the check printed"
        in paragraph
        # The closing sentence, not a second command line: one `uv run` line.
        and sum(line.startswith("uv run ") for line in paragraph.splitlines()) == 1
        and paragraph.rstrip().endswith(_AMEND_SENTENCE)
    )


def test_step4_runs_the_check_with_amend_before_an_amend():
    paragraph, _ = _claim_paragraph()
    assert _runs_the_amend_check(paragraph)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_AMEND_SENTENCE, _AMEND_SENTENCE_PRE, id="pre-edit"),
        pytest.param(", and before an amend with `--amend` added", ", and before an amend", id="no-flag"),
        pytest.param(", a reword's re-run included", "", id="reword-plain"),
        pytest.param("`git diff --cached <base>`", "`git diff --cached`", id="hunk-pass-against-head"),
        # The round-1 wording: `HEAD~1`, which a shallow clone's oldest commit lacks.
        pytest.param("`git diff --cached <base>`, with the `base` the check printed",
                     "`git diff --cached HEAD~1` (at a root commit, `git diff --cached` with the `base` the check "
                     "printed)", id="head-1-with-a-root-case"),
        pytest.param(", with the `base` the check printed", "", id="base-unnamed"),
        pytest.param(_AMEND_SENTENCE, "", id="dropped"),
    ],
)
def test_the_amend_rule_rejects_its_mutants(old, new):
    paragraph, _ = _claim_paragraph()
    assert paragraph.count(old) == 1, "the mutant must change the one clause it names"
    mutant = paragraph.replace(old, new, 1)
    assert mutant != paragraph
    assert not _runs_the_amend_check(mutant)


def test_the_amend_rule_rejects_a_second_command_line():
    """Twin: the flag written as a second fenced `uv run` line instead of in
    the closing sentence."""
    paragraph, _ = _claim_paragraph()
    line = next(line for line in paragraph.splitlines() if line.startswith("uv run "))
    mutant = paragraph.replace(line, line + "\n" + line + " --amend", 1)
    assert not _runs_the_amend_check(mutant)


def test_step4_runs_the_check_between_staging_and_the_commit():
    paragraph, _ = _claim_paragraph()
    assert "between the staging call and the commit call" in paragraph
    assert (
        "uv run {skill-root}/scripts/claim_check.py --message {workflow.implementation_artifacts}/.scratch-<story_id>/message.txt"
        " --message {workflow.implementation_artifacts}/.scratch-<story_id>/record-notes.md --project-root {project-root}"
        " --artifacts-root {workflow.implementation_artifacts}"
        " --artifacts-root {workflow.implementation_artifacts}/.scratch-<story_id>"
        " --artifacts-root {workflow.implementation_artifacts}/evidence-<story_id>"
        " --tea-config {workflow.tea_config_path}\n"
    ) in paragraph
    # The record's own names are read in its folders, and no folder hides a
    # claim. The fourth is TEA's, where `atdd-checklist-<story_id>.md` lives (#199).
    assert (
        "so the command names three folders with `--artifacts-root` (the run folder, this story's scratch folder and "
        "its evidence folder) and a fourth with `--tea-config`, the TEA test-artifacts root that holds "
        "`atdd-checklist-<story_id>.md`, resolved from the TEA config as preflight resolves it "
        "(`scripts/preflight_check.py`, `_tea_artifacts_root`), and such a name is read there: one that does not "
        "exist from `{project-root}` but exists "
        "in one of them lands in `ignored` when each copy that holds it is either ignored by git or outside the work "
        "tree, and in `not_in_diff` otherwise; one that exists from `{project-root}`, that a file the tree holds could "
        "be, or that is in none of them, is read from `{project-root}` as before."
    ) in paragraph
    # The boundary: a claimed, never-written file reads as a same-named copy,
    # and the hunk pass is what catches it.
    assert (
        "A file this commit claims and never wrote, named bare, under a folder the tree does not hold, or under an "
        "empty or ignored-only folder inside an untracked one (git lists only the topmost untracked folder), cannot be "
        "told from an artifact of that name, so a copy in one of the folders reads it as the copy: the hunk pass below, "
        "which finds the hunk for each edit the message or the notes say this commit makes, is what catches it."
    ) in paragraph
    # On a tracked artifact tree such a name stays listed, and is still never staged.
    assert (
        "A path under this story's `.scratch-<story_id>/` or `evidence-<story_id>/` is never staged, since both folders "
        "stay untracked: the record names it on purpose, as its own evidence, and it may stay listed."
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
    # Before an amend the check runs with `--amend` (#218), on every run for it.
    assert _AMEND_SENTENCE in paragraph
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
        .replace("{workflow.tea_config_path}", "/home/u/git/proj/_bmad/tea/config.yaml")
        .replace("<story_id>", "4-1")
        .replace("{project-root}", "/home/u/git/proj")
    )
    guard = _load("guard_pretooluse", GUARD)
    assert guard._git_writes(resolved) == set()
    # Before an amend the same line runs with `--amend` added (#218): still no
    # git write the guard would gate.
    assert guard._git_writes(resolved + " --amend") == set()
    # The message file's name keeps the commit verb out of the command entirely.
    assert "commit" not in resolved


# --- `--amend` (#218): compare with what an amend of HEAD would commit --------
#
# Step 5 amends the story's commit, and step 4's claim check before it read the
# staged diff alone: every path the amended commit already carried from HEAD
# landed in `not_in_diff`, and the rule for that list would have the conductor
# strip true claims. With `--amend` the index is compared with HEAD's first
# parent (the empty tree when HEAD has none), which is the list git's own
# `commit --dry-run --amend` shows.


def _git_text(repo: Path, *args: str, stdin: bytes | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, input=stdin)
    return proc.stdout.decode("utf-8").strip()


def _amend_oracle(repo: Path) -> list[str]:
    """The paths `git commit --amend` would commit, as git's own dry run lists
    them: each entry whose index column says it is staged against HEAD's first
    parent. Rename detection off, so a rename lists both names."""
    proc = subprocess.run(
        ["git", "-c", "status.renames=false", "commit", "--dry-run", "--amend", "--porcelain", "-z"],
        cwd=repo,
        capture_output=True,
    )
    entries = [entry for entry in proc.stdout.decode("utf-8").split("\0") if entry]
    return sorted(entry[3:] for entry in entries if entry[0] not in " ?!")


def _the_218_case(repo: Path) -> str:
    """Step 4 committed the guard and its test; step 5 stages a fixture for an
    amend, and the message names all three."""
    _stage(repo, "src/guard.py")
    _stage(repo, "tests/test_guard.py")
    _commit(repo, "src/guard.py", "tests/test_guard.py")
    _stage(repo, "src/fixture.ts")
    return "fix(guard): tighten `src/guard.py`, cover it in `tests/test_guard.py`, add `src/fixture.ts`"


def test_an_amend_reads_the_paths_head_already_carries(repo):
    message = _the_218_case(repo)
    plain = cc.check(message, repo)
    # The reported failure, which the plain check still gives: right before a
    # commit that adds to HEAD, wrong before an amend.
    assert plain["not_in_diff"] == ["src/guard.py", "tests/test_guard.py"]
    assert "base" not in plain
    amended = cc.check(message, repo, amend=True)
    assert amended["clean"] is True and amended["not_in_diff"] == []
    assert amended["staged"] == ["src/fixture.ts", "src/guard.py", "tests/test_guard.py"]
    assert amended["base"] == _git_text(repo, "rev-parse", "HEAD~1")
    # A message-only amend, nothing staged, still carries HEAD's paths.
    _git(repo, "reset", "-q", "--", "src/fixture.ts")
    out = cc.check("fix(guard): tighten `src/guard.py` and `tests/test_guard.py`", repo, amend=True)
    assert out["staged"] == ["src/guard.py", "tests/test_guard.py"] and out["clean"] is True


def test_mutant_head_base_lists_what_head_carries(repo, monkeypatch):
    """Twin: an amend compared with HEAD itself is the plain staged diff, and
    the #218 assertion above reds."""
    message = _the_218_case(repo)
    monkeypatch.setattr(cc, "amend_base", lambda project_root: "HEAD")
    out = cc.check(message, repo, amend=True)
    assert out["not_in_diff"] == ["src/guard.py", "tests/test_guard.py"]


def test_mutant_ignored_flag_lists_what_head_carries(repo, monkeypatch):
    """Twin: a base resolved but never handed to the diff."""
    message = _the_218_case(repo)
    unbased = cc.staged_paths
    monkeypatch.setattr(cc, "staged_paths", lambda project_root, base=None: unbased(project_root))
    out = cc.check(message, repo, amend=True)
    assert out["not_in_diff"] == ["src/guard.py", "tests/test_guard.py"]


def _plain(repo: Path) -> None:
    _stage(repo, "src/guard.py")
    _commit(repo, "src/guard.py")
    _stage(repo, "src/fixture.ts")
    # A mark the amend leaves out, as a commit does.
    (repo / "src/marked.ts").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-N", "--", "src/marked.ts")


def _rename(repo: Path) -> None:
    _git(repo, "mv", "old.py", "src/new.py")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "move")
    _stage(repo, "src/fixture.ts")


def _merge(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "side")
    _stage(repo, "src/fixture.ts")
    _commit(repo, "src/fixture.ts")
    _git(repo, "checkout", "-q", "-")
    _stage(repo, "src/guard.py")
    _commit(repo, "src/guard.py")
    _git(repo, "-c", "commit.gpgsign=false", "merge", "-q", "--no-ff", "-m", "merge", "side")
    _stage(repo, "tests/test_guard.py")


def _root(repo: Path) -> None:
    _stage(repo, "src/guard.py")


@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        pytest.param(_plain, ["src/fixture.ts", "src/guard.py"], id="plain"),
        pytest.param(_rename, ["old.py", "src/fixture.ts", "src/new.py"], id="rename"),
        # The first parent: the side branch's file is what the merge brought in.
        pytest.param(_merge, ["src/fixture.ts", "tests/test_guard.py"], id="merge"),
        # No parent: the amend commits the whole index.
        pytest.param(_root, ["old.py", "skills/ucg-formalize/SKILL.md", "src/fixture.ts", "src/guard.py",
                             "tests/test_guard.py"], id="root"),
    ],
)
def test_the_amend_list_is_what_git_amend_commits(repo, shape, expected):
    shape(repo)
    out = cc.check("x", repo, amend=True)
    assert out["staged"] == expected
    assert out["staged"] == _amend_oracle(repo)


def test_an_amend_leaves_a_mark_out(repo):
    """An intent-to-add entry (Execute step 2's mark, #217) is in neither an
    amend nor the list, so a text that names it still lists it."""
    _plain(repo)
    out = cc.check("adds `src/marked.ts` and `src/fixture.ts`", repo, amend=True)
    assert "src/marked.ts" not in out["staged"]
    assert out["not_in_diff"] == ["src/marked.ts"]


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_a_root_amend_compares_with_the_repositorys_own_empty_tree(tmp_path, object_format):
    root = tmp_path / "repo"
    root.mkdir()
    if subprocess.run(["git", "init", "-q", f"--object-format={object_format}"], cwd=root,
                      capture_output=True).returncode != 0:
        pytest.skip(f"this git cannot make a {object_format} repository")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit(root, "a.py")
    _stage(root, "a.py")
    out = cc.check("changes a.py", root, amend=True)
    empty_tree = _git_text(root, "hash-object", "-t", "tree", "--stdin", stdin=b"")
    assert out["base"] == empty_tree
    assert len(empty_tree) == {"sha1": 40, "sha256": 64}[object_format]
    assert out["staged"] == ["a.py"] and out["clean"] is True


def test_an_unborn_head_has_nothing_to_amend(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "a.py")
    message = tmp_path / "message.txt"
    message.write_text("adds a.py", encoding="utf-8")
    argv = [sys.executable, str(SCRIPT), "--message", str(message), "--project-root", str(root)]
    proc = subprocess.run([*argv, "--amend"], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2
    assert "nothing to amend" in json.loads(proc.stderr)["error"]
    # The plain check still runs there: the staged diff of a first commit.
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["staged"] == ["a.py"]
    with pytest.raises(cc.NothingToAmend):
        cc.check("adds a.py", root, amend=True)


def test_a_failed_parent_probe_is_not_read_as_a_root_commit(repo, tmp_path, capsys, monkeypatch):
    """`rev-parse --verify -q HEAD~1` exiting other than 0 or 1 (a timeout, a
    git that cannot read the repository) while HEAD resolves is no root
    commit: the empty tree would read every index path as carried and the
    check as clean."""
    message_text = _the_218_case(repo)
    asked = cc._rev_parse

    def failing_parent(project_root, rev):
        return (128, "") if rev == "HEAD~1" else asked(project_root, rev)

    monkeypatch.setattr(cc, "_rev_parse", failing_parent)
    assert cc.check(message_text, repo, amend=True) is None
    message = tmp_path / "message.txt"
    message.write_text(message_text, encoding="utf-8")
    assert cc.main(["--message", str(message), "--project-root", str(repo), "--amend"]) == 2
    assert "not a git work tree" in json.loads(capsys.readouterr().err)["error"]


def test_a_head_whose_commit_object_is_missing_gets_no_empty_tree(repo, tmp_path, capsys):
    """`HEAD~1` exits 1 there, as at a root commit, and plain `HEAD` still
    resolves from the ref; `HEAD^{commit}` reads the object and does not, so
    the check reads it as nothing to amend, never as a root commit."""
    message_text = _the_218_case(repo)
    head = _git_text(repo, "rev-parse", "HEAD")
    obj = repo / ".git" / "objects" / head[:2] / head[2:]
    obj.chmod(0o644)  # git writes objects read-only, which Windows will not unlink
    obj.unlink()
    assert subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD~1"], cwd=repo).returncode == 1
    assert subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=repo, capture_output=True).returncode == 0
    with pytest.raises(cc.NothingToAmend):
        cc.amend_base(repo)
    message = tmp_path / "message.txt"
    message.write_text(message_text, encoding="utf-8")
    assert cc.main(["--message", str(message), "--project-root", str(repo), "--amend"]) == 2
    assert "nothing to amend" in json.loads(capsys.readouterr().err)["error"]


def test_mutant_plain_head_probe_reads_a_missing_commit_as_a_root(repo, monkeypatch):
    """Twin: with the second probe on plain `HEAD`, which resolves from the
    ref, the missing commit reads as a root commit and the empty tree is the
    base."""
    _the_218_case(repo)
    head = _git_text(repo, "rev-parse", "HEAD")
    obj = repo / ".git" / "objects" / head[:2] / head[2:]
    obj.chmod(0o644)
    obj.unlink()
    asked = cc._rev_parse
    monkeypatch.setattr(
        cc, "_rev_parse", lambda root, rev: asked(root, "HEAD" if rev == "HEAD^{commit}" else rev)
    )
    empty_tree = _git_text(repo, "hash-object", "-t", "tree", "--stdin", stdin=b"")
    assert cc.amend_base(repo) == empty_tree


def test_an_amend_outside_a_work_tree_is_still_not_a_git_work_tree(tmp_path):
    message = tmp_path / "message.txt"
    message.write_text("adds a.py", encoding="utf-8")
    nowhere = tmp_path / "plain-folder"
    nowhere.mkdir()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--message", str(message), "--project-root", str(nowhere), "--amend"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 2
    assert "not a git work tree" in json.loads(proc.stderr)["error"]


def test_base_is_printed_only_with_the_flag(repo, tmp_path, capsys):
    message = tmp_path / "message.txt"
    message.write_text(_the_218_case(repo), encoding="utf-8")
    argv = ["--message", str(message), "--project-root", str(repo)]
    assert cc.main(argv) == 0
    plain = json.loads(capsys.readouterr().out)
    assert list(plain) == ["named", "staged", "not_in_diff", "ignored", "clean"]
    assert cc.main([*argv, "--amend"]) == 0
    amended = json.loads(capsys.readouterr().out)
    assert list(amended) == ["named", "staged", "not_in_diff", "ignored", "clean", "base"]
    assert amended["clean"] is True and plain["clean"] is False


def test_mutant_cli_dropping_the_flag_prints_the_plain_result(repo, tmp_path, capsys, monkeypatch):
    """Twin: a `--amend` the CLI parses and never hands to the check."""
    message = tmp_path / "message.txt"
    message.write_text(_the_218_case(repo), encoding="utf-8")
    checked = cc.check
    monkeypatch.setattr(cc, "check", lambda text, root, roots=(), amend=False: checked(text, root, roots))
    assert cc.main(["--message", str(message), "--project-root", str(repo), "--amend"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "base" not in out and out["not_in_diff"] == ["src/guard.py", "tests/test_guard.py"]


def test_an_amend_below_the_top_level_names_paths_from_it(subdir_project):
    app = subdir_project
    _stage(app, "src/a.py")
    _commit(app, "src/a.py")
    _stage(app, "src/b.py")
    message = "feat: change src/a.py and src/b.py"
    assert cc.check(message, app)["not_in_diff"] == ["src/a.py"]
    out = cc.check(message, app, amend=True)
    assert out["staged"] == ["app/src/a.py", "app/src/b.py"]
    assert out["clean"] is True
    assert out["base"] == _git_text(app, "rev-parse", "HEAD~1")
