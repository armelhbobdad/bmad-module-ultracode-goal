#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""List the paths a commit message names that the staged diff does not touch.

A commit message that says a path changed, when the commit leaves that path
alone, is a claim about the tree that needs no judgment to refute. The field
case: a story record and a commit message both said a file's edit had landed
after the script making the edit had died on its first assertion, so the diff
for that file was empty. Only the story record named the file; the message
described the edit by its content. So `--message` repeats: pass the commit
message and the story-record notes this cycle added, and every path either
names is checked. An edit described only by its content names no path, and
no script finds it; execute.md's judgment pass looks for its hunk instead.
A named path git ignores (a ledger the record cites, a file under a gitignored
artifact tree) is reported apart, in `ignored`: no commit can carry it, so it
is no claim the commit can make good. Only a relative path inside the tree
that holds a `/` or exists there is asked about: a bare name that exists
nowhere could be any file of that name, and stays in `not_in_diff`.

This reads the texts, collects the paths they name, and compares them with
`git diff --cached --name-only --no-renames -z` (a rename lists both names,
so a message naming either one matches; `-z` keeps a non-ASCII name
unquoted). git names a staged path from the repository's top level, and a
text names one from the project root, so when the project root is a folder
below the top level (a BMAD install in a monorepo's `app/`), `src/a.py` and
`app/src/a.py` both name a staged `app/src/a.py`.

Matching. A named path that exists in the work tree or the index must match a
staged path exactly, or be a directory holding one: `README.md` does not match
a staged `docs/README.md` when a root `README.md` exists, and below the top
level it does not match the top level's `README.md` when the project root
holds one. On a filesystem that ignores case (Windows, macOS by default), the
match ignores case too, so `Src/Guard.py` names a staged `src/guard.py`. A named path that exists nowhere matches by its trailing segments
or as a directory anywhere in a staged path, so `guard.py` or `hooks/` still
match `src/hooks/guard.py`.

The output is a list to resolve before the commit, not a verdict. For each
path: stage it if this commit changed it; if the work tree shows no change
there, the edit did not happen, so make it or remove the claim; or reword the
text when it says this commit changed a file it did not. A text may name an
unchanged file on purpose ("the guard in X already does this"); the list
makes sure that is a choice, and such a path stays listed.
Extraction is a heuristic and can miss a path or read one that is not meant.

What counts as a named path, after a `:line`, `:L12`, `#L12` or `::test`
suffix is dropped, a `\\` is read as `/`, an absolute path under the project
root is made relative, and a `--flag=` or `old→new` is split:
  - a file name with a common source or document extension, alone or under
    directories (`fixture.ts`, `src/guard.py`, `` `docs/my file.md` ``);
  - a well-known name with no extension (`Dockerfile`, `Makefile`), or a
    dotfile that exists in the tree or the index (`.env`);
  - a token holding a `/` that ends with one (`src/hooks/`), or that exists
    in the work tree or among the staged paths (`skills/ucg-formalize`).
So `and/or`, `pass/fail`, `Node.js`, a URL, an e-mail address, a version
string, an issue reference or a token holding a glob or a `$` is not a path.

Usage:
    uv run claim_check.py --message <file, or - for stdin> [--message <file> ...] [--project-root <dir>]

Output: JSON on stdout, `{"named": [...], "staged": [...], "not_in_diff":
[...], "ignored": [...], "clean": bool}`, where `clean` means `not_in_diff`
is empty and `staged` lists paths from the top level, as git does. Stdin and
the JSON are UTF-8 whatever the console's code page, and a staged name that
is not UTF-8 is written as its `\\udcXX` escape, which a JSON reader reads
back as the name git holds. Several `--message` files are read as one text,
in order. Exit 0 whenever it ran (a non-empty `not_in_diff` is a result, not
an error); exit 2 when a message file cannot be read, when `-` (stdin) is
given more than once, or when the project root is not a git work tree.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EXTENSIONS = frozenset(
    "py pyi ts tsx js jsx mjs cjs mts cts md mdx json jsonc yaml yml toml sh bash zsh "
    "rs go java kt kts rb php cs c h cc cpp hpp swift css scss sass less html htm vue "
    "svelte astro sql surql graphql proto txt cfg ini env lock csv xml".split()
)
# Names with no extension that are files in practice.
BARE_NAMES = frozenset(
    "Dockerfile Containerfile Makefile Justfile Procfile Gemfile Rakefile Brewfile "
    "Vagrantfile Jenkinsfile LICENSE CODEOWNERS".split()
)
# Product names spelled like a file name.
PROSE_NAMES = frozenset(
    "node.js next.js nuxt.js vue.js react.js express.js three.js chart.js d3.js "
    "deno.js ember.js backbone.js".split()
)
# Backticks, quotes, brackets and list punctuation separate tokens.
_TOKEN = re.compile(r"[^\s`'\"()\[\]{}<>,;]+")
_BACKTICKED = re.compile(r"`([^`\n]+)`")
_EMAIL = re.compile(r"^[^/@\s]+@[^/@\s]+\.[A-Za-z]{2,}$")


def _clean(token: str, root: str) -> str:
    token = token.replace("\\", "/")
    if "=" in token:
        token = token.rsplit("=", 1)[-1]
    # Sentence punctuation first, so `src/a.py:12.` still sheds its line number.
    token = token.split("::", 1)[0].rstrip(".:!?")
    token = re.sub(r"(?:#L\d+(?:-L?\d+)?|:L?\d+(?:-L?\d+)?)$", "", token).rstrip(".:!?")
    if root and token.startswith(root + "/"):
        token = token[len(root) + 1 :]
    return token[2:] if token.startswith("./") else token


def _has_extension(token: str) -> bool:
    stem, dot, ext = token.rstrip("/").rsplit("/", 1)[-1].rpartition(".")
    return bool(dot and stem and ext.lower() in EXTENSIONS)


def _known(bare: str, project_root: Path, staged: set[str]) -> bool:
    """Whether the path is in the work tree or the index, as itself or as a directory."""
    return (project_root / bare).exists() or any(p == bare or p.startswith(bare + "/") for p in staged)


def _is_path(token: str, project_root: Path, staged: set[str]) -> bool:
    if not token or "://" in token or _EMAIL.match(token) or re.search(r"[*?$]", token):
        return False
    if token.startswith(("-", "#")) or token.lower() in PROSE_NAMES:
        return False
    name = token.rstrip("/").rsplit("/", 1)[-1]
    if _has_extension(token) or name in BARE_NAMES:
        return True
    if re.fullmatch(r"\.[\w.-]+", name):
        return _known(token.strip("/"), project_root, staged)
    if "/" not in token:
        return False
    bare = token.strip("/")
    if not bare:
        # A lone `/` (or `//`) would resolve to the project root itself.
        return False
    if token.endswith("/") and len(bare) > 1:
        return True
    return _known(bare, project_root, staged)


def named_paths(message: str, project_root: Path, staged: list[str]) -> list[str]:
    """Every path the message names, in first-seen order, without duplicates.

    A backticked span holding a space is tried whole first, so `docs/my file.md`
    survives; when it is a path, its words are not read again one by one.
    """
    seen: dict[str, None] = {}
    staged_set = set(staged)
    # POSIX form: a message's backslash is read as `/` before the prefix is compared.
    root = project_root.resolve().as_posix()

    def spaced_span(match: re.Match) -> str:
        span = match.group(1).strip()
        if " " in span:
            token = _clean(span, root)
            if _is_path(token, project_root, staged_set):
                seen.setdefault(token, None)
                return " "
        return " %s " % span

    rest = _BACKTICKED.sub(spaced_span, message)
    for raw in _TOKEN.findall(rest):
        for part in raw.split("\u2192"):
            token = _clean(part, root)
            if _is_path(token, project_root, staged_set):
                seen.setdefault(token, None)
    return list(seen)


def _project_relative(staged: list[str], prefix: str) -> list[str]:
    """The staged paths under the project root, named from it.

    `prefix` is the project root's folder below the top level (`app/`), empty
    at the top level, where git's names are already the project's.
    """
    if not prefix:
        return staged
    return [path[len(prefix) :] for path in staged if path.startswith(prefix)]


def _ignores_case(path: Path, project_root: Path) -> bool:
    """Whether the filesystem holding `path`, which exists, ignores case.

    True when the same path with one segment's case swapped is the same file,
    as on Windows and on macOS by default. The last segment below the project
    root that holds a letter is swapped (`docs` for `docs/2024`); the root and
    the folders above it, which can sit on another filesystem, are never
    probed. A path with no such segment, or one that cannot be checked, reads
    as case-sensitive, which keeps the exact match.
    """
    root = project_root.resolve()
    try:
        path = path.resolve()
    except (OSError, RuntimeError):
        return False
    if not path.is_relative_to(root):
        return False  # `../x` names a path outside the project
    for current in (path, *path.parents):
        if current == root:
            return False
        swapped = current.name.swapcase()
        if swapped == current.name:
            continue
        try:
            return os.path.samefile(current, current.with_name(swapped))
        except (OSError, ValueError):
            return False
    return False


def _matches(named: str, staged: list[str], project_root: Path, prefix: str = "") -> bool:
    bare = named.strip("/")
    local = _project_relative(staged, prefix)
    if any(path == bare or path.startswith(bare + "/") for path in local):
        return True
    if _known(bare, project_root, set(local)):
        # It names a real path: only that path, or a file under it, will do.
        # Where the filesystem ignores case, any spelling of it does, the work
        # tree's and the index's alike (they differ after a case-only rename
        # made without `git mv`).
        full = project_root / bare
        if not (full.exists() and _ignores_case(full, project_root)):
            return False
        folded = bare.casefold()
        return any(
            path.casefold() == folded or path.casefold().startswith(folded + "/") for path in local
        )
    if prefix and any(path == bare or path.startswith(bare + "/") for path in staged):
        # Named from the top level (`app/src/a.py`).
        return True
    return any(path.endswith("/" + bare) or ("/" + bare + "/") in ("/" + path) for path in staged)


def project_prefix(project_root: Path) -> str:
    """The project root's folder below the git top level (`app/`), or ""."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-prefix"], cwd=project_root, capture_output=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", errors="surrogateescape").rstrip("\r\n")


def staged_paths(project_root: Path) -> list[str] | None:
    try:
        proc = subprocess.run(
            # From the top level even where diff.relative would name them from the cwd.
            ["git", "-c", "diff.relative=false", "diff", "--cached", "--name-only", "--no-renames", "-z"],
            cwd=project_root,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return [name for name in proc.stdout.decode("utf-8", errors="surrogateescape").split("\0") if name]


def _askable(path: str, project_root: Path) -> bool:
    """Whether `git check-ignore` can say something true about the path."""
    bare = path.rstrip("/")
    if not bare or bare.startswith("/") or re.match(r"^[A-Za-z]:/", bare):
        return False
    if bare == ".." or bare.startswith("../") or "/../" in bare:
        return False
    return "/" in bare or (project_root / bare).exists()


def _check_ignore(paths: list[str], project_root: Path) -> tuple[int, set[str]]:
    try:
        proc = subprocess.run(
            ["git", "check-ignore", "-z", "--stdin"],
            cwd=project_root,
            input=("\0".join(p.rstrip("/") for p in paths) + "\0").encode("utf-8", errors="surrogateescape"),
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 128, set()
    out = set(proc.stdout.decode("utf-8", errors="surrogateescape").split("\0"))
    return proc.returncode, {p for p in paths if p.rstrip("/") in out}


def ignored_paths(paths: list[str], project_root: Path) -> set[str]:
    """The paths an ignore rule covers. A tracked file is never reported as
    ignored, since git commits its edits whatever the rules say.

    git stops at the first path it cannot evaluate (beyond a symlink, say)
    with exit 128, so on that exit each path is asked about on its own, and
    one it cannot evaluate counts as not ignored.
    """
    askable = [p for p in paths if _askable(p, project_root)]
    if not askable:
        return set()
    code, ignored = _check_ignore(askable, project_root)
    if code in (0, 1):
        return ignored
    found: set[str] = set()
    for path in askable:
        code, one = _check_ignore([path], project_root)
        if code == 0:
            found |= one
    return found


def check(message: str, project_root: Path) -> dict | None:
    staged = staged_paths(project_root)
    if staged is None:
        return None
    prefix = project_prefix(project_root)
    named = named_paths(message, project_root, [*staged, *_project_relative(staged, prefix)])
    unmatched = [path for path in named if not _matches(path, staged, project_root, prefix)]
    ignored = ignored_paths(unmatched, project_root)
    missing = [path for path in unmatched if path not in ignored]
    return {
        "named": named,
        "staged": staged,
        "not_in_diff": missing,
        "ignored": [path for path in unmatched if path in ignored],
        "clean": not missing,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List the paths a commit message names that the staged diff does not touch."
    )
    parser.add_argument(
        "--message",
        action="append",
        required=True,
        help="a text whose path claims to check (the commit message, the story-record notes this "
        "cycle added); repeat for several, - for stdin once",
    )
    parser.add_argument("--project-root", default=".", help="the git work tree (default: the cwd)")
    args = parser.parse_args(argv)
    if args.message.count("-") > 1:
        parser.error("stdin (-) can be read only once")
    # A Windows pipe reads and writes the ANSI code page, which has no CJK, and
    # git hands back a name that is not UTF-8 as lone surrogates, which UTF-8
    # cannot encode: such a name is written as its \udcXX escape.
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    texts = []
    try:
        for source in args.message:
            texts.append(sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        print(json.dumps({"error": "cannot read the message %s: %s" % (source, exc)}), file=sys.stderr)
        return 2
    message = "\n\n".join(texts)
    result = check(message, Path(args.project_root))
    if result is None:
        print(json.dumps({"error": "not a git work tree: %s" % args.project_root}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
