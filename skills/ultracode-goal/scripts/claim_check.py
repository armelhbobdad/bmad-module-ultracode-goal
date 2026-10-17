#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""List the paths a commit message names that the staged diff does not touch.

A commit message that says a path changed, when the commit leaves that path
alone, is a claim about the tree that needs no judgment to refute. The field
case: a message recorded a file's edit as landed after the script making the
edit had died on its first assertion, so nothing in it ran and the diff for
that path was empty. This reads the message, collects the paths it names, and
compares them with `git diff --cached --name-only --no-renames -z` (a rename
lists both names, so a message naming either one matches; `-z` keeps a
non-ASCII name unquoted).

Matching. A named path that exists in the work tree or the index must match a
staged path exactly, or be a directory holding one: `README.md` does not match
a staged `docs/README.md` when a root `README.md` exists. A named path that
exists nowhere matches by its trailing segments or as a directory anywhere in
a staged path, so `guard.py` or `hooks/` still match `src/hooks/guard.py`.

The output is a list to resolve before the commit, not a verdict: stage the
path if this commit should change it, or reword the message so it does not
claim this commit changed it. A message may name an unchanged file on purpose
("the guard in X already does this"); the list makes sure that is a choice.
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
    uv run claim_check.py --message <file, or - for stdin> [--project-root <dir>]

Output: JSON on stdout, `{"named": [...], "staged": [...], "not_in_diff":
[...], "clean": bool}`. Exit 0 whenever it ran (a non-empty `not_in_diff` is
a result, not an error); exit 2 when the message cannot be read or the
project root is not a git work tree.
"""

from __future__ import annotations

import argparse
import json
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
    if token.endswith("/") and len(token.strip("/")) > 1:
        return True
    return _known(token.strip("/"), project_root, staged)


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


def _matches(named: str, staged: list[str], project_root: Path) -> bool:
    bare = named.strip("/")
    if any(path == bare or path.startswith(bare + "/") for path in staged):
        return True
    if _known(bare, project_root, set(staged)):
        # It names a real path: only that path, or a file under it, will do.
        return False
    return any(path.endswith("/" + bare) or ("/" + bare + "/") in ("/" + path) for path in staged)


def staged_paths(project_root: Path) -> list[str] | None:
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--no-renames", "-z"],
            cwd=project_root,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return [name for name in proc.stdout.decode("utf-8", errors="surrogateescape").split("\0") if name]


def check(message: str, project_root: Path) -> dict | None:
    staged = staged_paths(project_root)
    if staged is None:
        return None
    named = named_paths(message, project_root, staged)
    missing = [path for path in named if not _matches(path, staged, project_root)]
    return {"named": named, "staged": staged, "not_in_diff": missing, "clean": not missing}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List the paths a commit message names that the staged diff does not touch."
    )
    parser.add_argument("--message", required=True, help="the commit message file, or - for stdin")
    parser.add_argument("--project-root", default=".", help="the git work tree (default: the cwd)")
    args = parser.parse_args(argv)
    try:
        message = sys.stdin.read() if args.message == "-" else Path(args.message).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(json.dumps({"error": "cannot read the message: %s" % exc}), file=sys.stderr)
        return 2
    result = check(message, Path(args.project_root))
    if result is None:
        print(json.dumps({"error": "not a git work tree: %s" % args.project_root}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
