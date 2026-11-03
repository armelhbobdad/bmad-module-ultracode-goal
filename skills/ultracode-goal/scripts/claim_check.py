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

A record names its own artifacts from the folder it keeps them in
(`sweep.sh`, `red-phase/INDEX.md`), not from the project root, so
`--artifacts-root` (repeatable) names such a folder: the run folder, the
story's scratch folder, its evidence folder. `--tea-config FILE` adds one
more, TEA's test-artifacts root, which holds the `atdd-checklist-<story_id>.md`
a record names bare. It is resolved from that TEA config as preflight
resolves it, with preflight_check.py's own reader, imported rather than
copied: `{project-root}` in FILE is substituted and a relative FILE is read
under the project root, then the root is the config's `test_artifacts` value,
an inline comment dropped, `{project-root}` substituted and a relative value
read under the project root, or `_bmad-output/test-artifacts` there when the
config names none or does not exist. A config file that cannot be read (a
permission error, say) adds no folder; a path that holds no file (a
directory, a dangling link) is read as no config. A named path that does not exist
from the project root but exists under one or more of those folders is read
there instead: it is `ignored` when each copy that holds it is either ignored
by git or outside the work tree (no commit can carry either), a link being a
copy both where it sits and at its target, and stays in `not_in_diff`
otherwise, a tracked copy included. A named path keeps its reading from the
project root when it exists there; when a path the index or the work tree
holds unignored, a folder git lists holding no such path (one directly under
a folder that holds listed files), a submodule's file or a staged name ends
with it, its own copies aside, or, outside the folder that holds a copy of
it, holds its first folder as a folder, in any case; when it holds a `/` and
its first segment exists from the project root or the top level; when it
holds an empty or `.` segment; when no folder holds it; or when git cannot
say where the work tree ends or what it holds. A file the commit claims and
never wrote, named bare, under a folder the tree does not hold, or under an
empty or ignored-only folder inside an untracked one (git lists only the
topmost untracked folder, `lib/` for `lib/plugins/`), cannot be told from an
artifact of that name, so a copy under one of the folders reads it as the
copy: execute.md's hunk pass, which looks for the hunk of each edit the texts
say the commit makes, is what catches it.

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
        [--artifacts-root <dir> ...] [--tea-config <file>]

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


def _ask(paths: list[str], project_root: Path) -> set[str]:
    """The paths `git check-ignore` reports, each asked about on its own when
    the batch ends at exit 128."""
    if not paths:
        return set()
    code, ignored = _check_ignore(paths, project_root)
    if code in (0, 1):
        return ignored
    found: set[str] = set()
    for path in paths:
        code, one = _check_ignore([path], project_root)
        if code == 0:
            found |= one
    return found


def _toplevel(project_root: Path) -> Path | None:
    """The work tree's top level, resolved, or None when git cannot name it."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=project_root, capture_output=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = proc.stdout.decode("utf-8", errors="surrogateescape").rstrip("\r\n")
    if proc.returncode != 0 or not out:
        return None
    try:
        return Path(out).resolve()
    except (OSError, RuntimeError):
        return None


def _in_tree(path: Path, top: Path) -> Path | None:
    """`path`, which is resolved, spelled from the top level when it lies inside
    the work tree; None when it lies outside.

    A folder above it that is the top level under another spelling (another
    case, on a filesystem that ignores case) counts as the top level.
    """
    if path.is_relative_to(top):
        return path
    for parent in path.parents:
        try:
            if os.path.samefile(parent, top):
                return top / path.relative_to(parent)
        except (OSError, ValueError):
            continue
    return None


def _holders(path: str, project_root: Path, roots: list[Path]) -> list[Path]:
    """Each artifacts root's copy of a named path that does not exist from the
    project root, resolved; empty when the project root has it, or no root does.

    Only a relative path that stays inside a root is resolved against one.
    """
    bare = path.rstrip("/")
    if not bare or bare.startswith("/") or re.match(r"^[A-Za-z]:/", bare):
        return []
    if bare == ".." or bare.startswith("../") or "/../" in bare or bare.endswith("/.."):
        return []
    if any(segment in ("", ".") for segment in bare.split("/")):
        # `hooks//guard.py` and `hooks/./guard.py` would be read as
        # `hooks/guard.py` here and as written against the tree.
        return []
    if (project_root / bare).exists():
        return []
    found: dict[str, Path] = {}
    for root in roots:
        candidate = root / bare
        try:
            if not candidate.exists():
                continue
            copies = [candidate.resolve()]
            if candidate.is_symlink():
                # git keeps and commits a link at its own path, so the link
                # where it sits is a copy as much as its target is.
                copies.append(candidate.parent.resolve() / candidate.name)
        except (OSError, RuntimeError):
            continue
        for copy in copies:
            found.setdefault(copy.as_posix(), copy)
    return list(found.values())


def _git_names(argv: list[str], cwd: Path) -> list[str] | None:
    """The NUL-separated names a git command prints, or None when it fails."""
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return [name for name in proc.stdout.decode("utf-8", errors="surrogateescape").split("\0") if name]


def _submodule_others(repo: Path, prefix: str = "") -> list[str] | None:
    """The untracked, unignored files of each checked-out submodule of `repo`
    (its mode 160000 entries), and the folders git lists there holding no
    listed file as `dir/`, recursively, named from the top level `prefix`
    stands for; None when git cannot list one."""
    entries = _git_names(["git", "ls-files", "-z", "-s"], repo)
    if entries is None:
        return None
    names: list[str] = []
    for entry in entries:
        meta, _, path = entry.partition("\t")
        if not meta.startswith("160000 ") or not (repo / path / ".git").exists():
            continue
        others = _git_names(["git", "ls-files", "-z", "--others", "--exclude-standard"], repo / path)
        folders = _git_names(["git", "ls-files", "-z", "--others", "--exclude-standard", "--directory"], repo / path)
        nested = _submodule_others(repo / path, prefix + path + "/")
        if others is None or folders is None or nested is None:
            return None
        names += [prefix + path + "/" + name for name in others]
        names += [prefix + path + "/" + name for name in folders if name.endswith("/")] + nested
    return names


def _listed(project_root: Path) -> list[str] | None:
    """Every path the index holds or the work tree holds unignored, across the
    whole work tree and its submodules' checkouts, and every folder git lists
    holding no such path (empty, or holding ignored files only) as `dir/`,
    named from the top level; None when git cannot list them. git lists only
    the topmost untracked folder, so an empty `lib/plugins/` inside an
    untracked `lib/` is listed as `lib/` alone."""
    top = _toplevel(project_root)
    if top is None:
        return None
    names: list[str] = []
    for argv in (
        ["git", "ls-files", "-z", "--full-name", "--cached", "--others", "--exclude-standard", "--", ":/"],
        # `--others` does not combine with `--recurse-submodules`.
        ["git", "ls-files", "-z", "--full-name", "--cached", "--recurse-submodules", "--", ":/"],
        ["git", "ls-files", "-z", "--full-name", "--others", "--exclude-standard", "--directory", "--", ":/"],
    ):
        listed = _git_names(argv, project_root)
        if listed is None:
            return None
        names += listed
    others = _submodule_others(top)
    return None if others is None else names + others


def _tree_names(held: dict[str, list[Path]], project_root: Path, top: Path, listed: list[str], roots: list[Path]) -> set[str]:
    """The held names that can mean a file of the tree itself, so a folder's
    copy must not hide the claim.

    A name can when it holds a `/` and its first segment exists from the
    project root or the top level (`src/new_helper.ts`, a file the commit
    claims and never wrote, beside a prototype in scratch), when a listed or
    staged path ends with it (`guard.py` for a tracked `src/hooks/guard.py`, a
    tracked file deleted in the work tree, an unignored new file), or when its
    first folder is a folder of one, anywhere in that path (`hooks/` or
    `hooks/sub/new.py` beside `src/hooks/x.py`, a top-level folder the index
    holds and the disk does not). A folder's own copy counts for nothing, and
    for the first-folder match neither does any listed path in the folder that
    holds it (the root plus the name's first folder, so a sibling
    `coverage/lcov.info` beside a held `coverage/summary.json`); a path that
    ends with the name protects it wherever it lies.

    The listing is read once: each path's trailing segments and folders are
    looked up among the held names, both sides casefolded, since a case-only
    rename made without `git mv` leaves the index's spelling listed alone
    where git ignores case.
    """
    found: set[str] = set()
    wanted: dict[str, tuple[set[str], tuple[str, ...]]] = {}
    by_suffix: dict[str, list[str]] = {}
    by_folder: dict[str, list[str]] = {}
    for path, holders in held.items():
        if not holders:
            continue
        bare = path.rstrip("/")
        first = bare.split("/", 1)[0]
        if "/" in bare and ((project_root / first).exists() or (top / first).exists()):
            found.add(path)
            continue
        spelled = (_in_tree(holder, top) for holder in holders)
        own = {copy.relative_to(top).as_posix() for copy in spelled if copy is not None}
        folders: set[str] = set()
        for root in roots:
            try:
                if not (root / bare).exists():
                    continue
                folder = _in_tree((root / first if "/" in bare else root).resolve(), top)
            except (OSError, RuntimeError):
                continue
            if folder is not None and folder != top:
                folders.add(folder.relative_to(top).as_posix() + "/")
        wanted[path] = (own, tuple(sorted(folders)))
        by_suffix.setdefault(bare.casefold(), []).append(path)
        by_folder.setdefault(first.casefold(), []).append(path)
    if not wanted:
        return found
    longest_suffix = max(key.count("/") for key in by_suffix) + 1
    for name in listed:
        folded = name.casefold()
        # A `dir/` entry ends with its last folder, and every segment of it
        # is a folder.
        segments = folded.rstrip("/").split("/")
        # A path that ends with the name protects it wherever it lies, its
        # own copies aside; one that only holds its first folder protects it
        # only outside the folder that holds a copy.
        ending: list[str] = []
        for i in range(max(0, len(segments) - longest_suffix), len(segments)):
            ending += by_suffix.get("/".join(segments[i:]), ())
        holding: list[str] = []
        for folder in segments if folded.endswith("/") else segments[:-1]:
            holding += by_folder.get(folder, ())
        entry = name.rstrip("/")
        for path in ending:
            if path not in found and entry not in wanted[path][0]:
                found.add(path)
        for path in holding:
            if path in found:
                continue
            own, inside = wanted[path]
            if entry not in own and not name.startswith(inside):
                found.add(path)
    return found


def ignored_paths(
    paths: list[str], project_root: Path, artifacts_roots: list[Path] | tuple = (), staged: list[str] | tuple = ()
) -> set[str]:
    """The paths an ignore rule covers. A tracked file is never reported as
    ignored, since git commits its edits whatever the rules say.

    git stops at the first path it cannot evaluate (beyond a symlink, say)
    with exit 128, so on that exit each path is asked about on its own, and
    one it cannot evaluate counts as not ignored.

    A path that exists under an artifacts root and not from the project root
    is asked about there, as an absolute path in `/` form, unless it can mean
    a file of the tree itself (`_tree_names`, which reads the listing and
    the `staged` names, from the top level, since a staged rename or deletion
    takes a folder out of the listing): it is ignored when each root's copy
    of it, a link both where it sits and at its target, is either ignored by
    git or outside the work tree.
    """
    roots = [Path(root) for root in artifacts_roots]
    held = {path: _holders(path, project_root, roots) for path in paths} if roots else {}
    top = None
    if any(held.values()):
        top = _toplevel(project_root)
        listed = _listed(project_root) if top is not None else None
        if top is None or listed is None:
            # Nothing says where the work tree ends or what it holds: read
            # every name from the project root.
            held = {}
        else:
            for path in _tree_names(held, project_root, top, [*listed, *staged], roots):
                held[path] = []
    found = _ask([p for p in paths if not held.get(p) and _askable(p, project_root)], project_root)
    if top is None or not any(held.values()):
        return found
    spelled = {holder: _in_tree(holder, top) for holders in held.values() for holder in holders}
    asked = _ask(sorted({p.as_posix() for p in spelled.values() if p is not None}), project_root)
    for path, holders in held.items():
        if holders and all(spelled[h] is None or spelled[h].as_posix() in asked for h in holders):
            found.add(path)
    return found


def check(message: str, project_root: Path, artifacts_roots: list[Path] | tuple = ()) -> dict | None:
    staged = staged_paths(project_root)
    if staged is None:
        return None
    prefix = project_prefix(project_root)
    named = named_paths(message, project_root, [*staged, *_project_relative(staged, prefix)])
    unmatched = [path for path in named if not _matches(path, staged, project_root, prefix)]
    ignored = ignored_paths(unmatched, project_root, artifacts_roots, staged)
    missing = [path for path in unmatched if path not in ignored]
    return {
        "named": named,
        "staged": staged,
        "not_in_diff": missing,
        "ignored": [path for path in unmatched if path in ignored],
        "clean": not missing,
    }


def _tea_root(tea_config: str, project_root: Path) -> Path | None:
    """TEA's test-artifacts root, which holds `atdd-checklist-<story_id>.md`,
    resolved from the TEA config `tea_config` names as preflight resolves it.

    preflight_check.py's own functions do the reading, imported here rather
    than copied, so the two never read one config apart: `_resolve` for the
    config path (`{project-root}` substituted, a relative path read under the
    project root), `_read_toml_or_yaml_flags` for its `test_artifacts` value
    (an inline comment dropped, a missing file read as no value), and
    `_tea_artifacts_root` for the root. None when the config is a file that
    cannot be read (a permission error, say), so no folder is added and each
    name keeps its reading; a path that holds no file (a directory, a dangling
    link) is read as no config, as preflight reads it.
    """
    scripts = str(Path(__file__).resolve().parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import preflight_check  # noqa: PLC0415  (sibling script, path set above)

    root = project_root.resolve()
    try:
        flags = preflight_check._read_toml_or_yaml_flags(preflight_check._resolve(tea_config, root))
    except OSError:
        return None
    return preflight_check._tea_artifacts_root(root, flags)


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
    parser.add_argument(
        "--artifacts-root",
        action="append",
        default=[],
        metavar="DIR",
        help="a folder the texts name artifacts from (the run folder, the story's scratch or evidence folder): "
        "a named path that exists there and not from the project root is read there; repeat for several",
    )
    parser.add_argument(
        "--tea-config",
        metavar="FILE",
        help="the TEA config ({project-root} is substituted): its test-artifacts root, resolved as preflight "
        "resolves it, is read as one more --artifacts-root, the folder that holds atdd-checklist-<story_id>.md",
    )
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
    roots = [Path(root) for root in args.artifacts_root]
    if args.tea_config is not None:
        tea_root = _tea_root(args.tea_config, Path(args.project_root))
        if tea_root is not None:
            roots.append(tea_root)
    result = check(message, Path(args.project_root), roots)
    if result is None:
        print(json.dumps({"error": "not a git work tree: %s" % args.project_root}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
