#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Link the main tree's dependency folders into a gate's measurement worktree.

A worktree carries tracked files only, so `node_modules` and its kin are
absent there, and the gate (references/gate.md) links each one in from the
main tree. A bare `ln -s` is not among the commands Claude Code's
`acceptEdits` mode runs without asking (`mkdir`, `touch`, `rm`, `rmdir`, `mv`,
`cp`, `sed`), nor on the run's allowlist, so an unattended gate under
drive_epic's default mode would have it refused. This script runs under
`uv run`, which the allowlist covers, and makes the links itself.

Which folders. Every `node_modules` folder in the main tree, the root's and
the nested ones (a workspace package's), but never one inside another
`node_modules`: linking the outer one carries it. The walk does not enter
`.git`, `__pycache__`, a repository or worktree nested in the tree (a folder
holding a `.git`: the gate worktrees under the implementation artifacts
folder, an agent worktree, a submodule, whose files the gate's worktree does
not check out), a Python virtual environment
(a folder holding `pyvenv.cfg`) or a cache folder (one holding `CACHEDIR.TAG`,
such as Cargo's `target`). None holds the project's own dependencies, and some
are large. A folder is judged by what it holds, not by its name, so a
workspace package named `target` or a JavaScript action under `.github/` is
still walked.
`--dir` names a folder to link instead, relative to the project root, for a
dependency folder of another name (`vendor`); repeat it for several. Given
any `--dir`, nothing is discovered.

Workspace links. A workspace package manager writes each of the repo's own
packages into these folders as a relative link
(`node_modules/@ex/sb-util -> ../../packages/sb-util`), and bun and pnpm write
a registry package's peer on one of them inside their store
(`node_modules/.bun/<pkg>/node_modules/@ex/sb-util`, and `.pnpm/` alike).
Through a folder linked whole, such a link resolves against the main tree's
folder, so a run in the worktree loads the main tree's copy of the package,
uncommitted edits and build output included. So before it links anything the
script reads each folder whose parent the worktree has: a workspace link is a
link (or a junction) whose real path is the project root (the root package) or
lies inside it, outside every `node_modules` folder and outside the folder
itself. It reads the folder's entries and each `@scope`'s, and the same for
`.bun/node_modules`, `.pnpm/node_modules` and each `.bun/<pkg>/node_modules`
and `.pnpm/<pkg>/node_modules`, and nothing deeper, so a large folder stays
quick. A workspace package a package manager copies in rather than links
(pnpm's injected dependencies) leaves no link to find, and the scan does not
see it. A folder that holds a workspace link is never linked: the gate gives the worktree an
offline install instead. An install writes through a linked folder into the
main tree (npm's and pnpm's do), so when any folder holds one, the call links
nothing at all and holds every other folder back (`install-first`), and it
fails a folder the worktree already holds as a link, which the install would
write through. Once the install has run, the same call with `--installed`
links whole each folder the worktree still lacks, never one that holds a
workspace link. When no install can serve, the same call with
`--link-workspace` links every folder whole, those included, as before: the
gate then reads the main tree's copy of each package such a link points to.

How each link is made. A directory symlink to the main tree's folder, at the
same relative path in the worktree. On Windows, where a symlink needs a
privilege or Developer Mode, a directory junction instead, which needs
neither. A folder whose parent the worktree does not have (the commit under
assessment has no such package) is skipped, and so is a path the worktree
already holds (a link a resumed gate made, a folder the install made, or a
tracked folder of that name).

Usage:
    uv run link_worktree_deps.py --project-root <main tree> --worktree <path>
        [--dir <relpath> ...] [--installed | --link-workspace]

Output: JSON on stdout, `{"linked": [...], "skipped": [{"path", "reason"}],
"failed": [{"path", "error"}], "workspace": [{"path", "lockfiles",
"links": [{"path", "to"}]}]}`, paths relative to the project root with `/`
separators (`lockfiles` relative to the worktree's root, the same paths);
`reason` is `parent-missing`, `exists`, `workspace` (a folder that holds a
workspace link, left for the install) or `install-first` (any other folder,
held back until the install has run). `workspace` lists each folder whose
parent the worktree has that holds a workspace link, with each link and the
folder it resolves to (`to`), and the lockfiles (`package-lock.json`,
`npm-shrinkwrap.json`, `bun.lock`, `bun.lockb`, `pnpm-lock.yaml`,
`yarn.lock`) in the nearest folder of the worktree, at or above that folder's
parent, that holds any, `[]` when none does. Exit 0 when every link was made
or skipped, 1 when any failed, and 2 when the project root or the worktree is
not a folder, or a `--dir` is absolute or leaves the project root.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

DEPENDENCY_DIR = "node_modules"
# Folders the walk never enters, by name.
_UNWALKED = frozenset({".git", "__pycache__"})
# A folder holding one of these is another repository or worktree (`.git`), a
# Python virtual environment, or a cache (the Cache Directory Tagging spec).
_UNWALKED_MARKERS = frozenset({".git", "pyvenv.cfg", "CACHEDIR.TAG"})
# The store a package manager keeps inside `node_modules`: each package in it
# has a `node_modules` of its own that holds its dependencies, peers included,
# and the store's own `node_modules` holds the hoisted ones.
_STORES = frozenset({".bun", ".pnpm"})
# The reparse tag of a Windows junction (`stat.IO_REPARSE_TAG_MOUNT_POINT`).
_MOUNT_POINT = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)
# The lockfiles `workspace` reports, in this order, so the gate can tell which offline install
# serves a folder: npm's two, bun's two, pnpm's, and yarn's, which no install the gate gives reads.
LOCKFILES = (
    "package-lock.json",
    "npm-shrinkwrap.json",
    "bun.lock",
    "bun.lockb",
    "pnpm-lock.yaml",
    "yarn.lock",
)


def discover(project_root: Path) -> list[str]:
    """Every `node_modules` folder under project_root, outermost only, sorted.

    The gate's own worktree, like every git worktree, holds a `.git` file, so
    the marker check skips it with the other nested trees.
    """
    found: list[str] = []
    for current, dirs, files in os.walk(project_root):
        if current != str(project_root) and any(
            marker in dirs or marker in files for marker in _UNWALKED_MARKERS
        ):
            dirs[:] = []  # a nested repository or worktree, a virtual environment, a cache
            continue
        kept = []
        for name in dirs:
            if name == DEPENDENCY_DIR:
                found.append(Path(os.path.relpath(os.path.join(current, name), project_root)).as_posix())
            elif name not in _UNWALKED:
                kept.append(name)
        dirs[:] = kept
    return sorted(found)


def _is_link(path: str) -> bool:
    """A symlink, or on Windows a junction, which `islink` does not report and npm makes.

    Read from the reparse tag, which Python 3.11 has (`isjunction` came in 3.12).
    """
    if os.path.islink(path):
        return True
    if os.name != "nt":
        return False
    try:
        return getattr(os.lstat(path), "st_reparse_tag", 0) == _MOUNT_POINT
    except OSError:
        return False


def _entry_is_link(entry: os.DirEntry) -> bool:
    """The same test on a listed entry, read from the listing where the system gives the type."""
    if entry.is_symlink():
        return True
    return os.name == "nt" and _is_link(entry.path)


def _entry_is_folder(entry: os.DirEntry) -> bool:
    try:
        return not _entry_is_link(entry) and entry.is_dir(follow_symlinks=False)
    except OSError:
        return False


def _listing(folder: str) -> list[os.DirEntry]:
    try:
        with os.scandir(folder) as entries:
            return list(entries)
    except OSError:
        return []


def _entries(folder: str) -> list[os.DirEntry]:
    """The entries of one `node_modules`-shaped folder, each `@scope`'s included."""
    found = []
    for entry in _listing(folder):
        found.append(entry)
        if entry.name.startswith("@") and _entry_is_folder(entry):
            found.extend(_listing(entry.path))
    return found


def _scanned(folder: str) -> list[os.DirEntry]:
    """Every entry the workspace scan reads: the folder's, and its stores' packages'."""
    found = []
    for entry in _entries(folder):
        found.append(entry)
        if entry.name not in _STORES or not _entry_is_folder(entry):
            continue
        for package in _listing(entry.path):
            if not _entry_is_folder(package):
                continue
            if package.name == DEPENDENCY_DIR:
                found.extend(_entries(package.path))
                continue
            inner = os.path.join(package.path, DEPENDENCY_DIR)
            if not _is_link(inner) and os.path.isdir(inner):
                found.extend(_entries(inner))
    return found


def _resolve(path: str, folders: dict[str, str], hops: int = 0) -> str:
    """`os.path.realpath(path)`, with each folder's real path computed once.

    A store's thousands of links share a few folders, and `realpath` walks
    every component of every one, so a large store took seconds. A folder's
    real path holds no link, so a relative target's leading `..` steps up from
    it as written; anything else goes to `realpath`.
    """
    parent, name = os.path.split(path)
    real_parent = folders.get(parent)
    if real_parent is None:
        real_parent = folders[parent] = os.path.realpath(parent)
    full = os.path.join(real_parent, name)
    if not os.path.islink(full):
        # A plain file or folder, or a Windows junction, which only `realpath` follows.
        return os.path.realpath(full) if _is_link(full) else full
    target = os.readlink(full)
    if hops >= 40 or os.path.isabs(target) or os.path.splitdrive(target)[0]:
        return os.path.realpath(full)
    if os.altsep:
        target = target.replace(os.altsep, os.sep)
    parts = [part for part in target.split(os.sep) if part not in ("", os.curdir)]
    base, index = real_parent, 0
    while index < len(parts) and parts[index] == os.pardir:
        base, index = os.path.dirname(base), index + 1
    rest = parts[index:]
    if not rest or os.pardir in rest:
        return os.path.realpath(full)
    return _resolve(os.path.join(base, *rest), folders, hops + 1)


def workspace_links(project_root: Path, rel: str) -> list[dict]:
    """The links in project_root/rel that resolve to the repo's own tracked files.

    A link counts when its real path is project_root itself (the root
    package) or lies inside it, outside every `node_modules` folder and
    outside the scanned folder itself: a workspace package, which a package
    manager links in relatively, so that through a folder linked whole it
    resolves to the main tree's copy.
    """
    root = str(project_root).rstrip(os.sep)
    inside = root + os.sep
    folder = os.path.join(root, rel)
    own = (os.path.normpath(folder) + os.sep, os.path.realpath(folder) + os.sep)
    nested = os.sep + DEPENDENCY_DIR + os.sep
    links = []
    folders: dict[str, str] = {}
    for entry in _scanned(str(project_root / rel)):
        if not _entry_is_link(entry):
            continue
        try:
            real = _resolve(entry.path, folders)
        except OSError:  # a link that changed or vanished during the scan
            real = os.path.realpath(entry.path)
        if real == root:
            to = "."
        elif not real.startswith(inside) or (real + os.sep).startswith(own):
            continue
        elif nested in os.sep + real[len(inside):] + os.sep:
            continue
        else:
            to = Path(real[len(inside):]).as_posix()
        links.append({"path": Path(os.path.relpath(entry.path, root)).as_posix(), "to": to})
    return sorted(links, key=lambda link: link["path"])


def lockfiles(worktree: Path, rel: str) -> list[str]:
    """The lockfiles in the nearest folder of the worktree, at or above rel's parent, that holds any."""
    folder = (worktree / rel).parent
    while folder == worktree or worktree in folder.parents:
        found = [name for name in LOCKFILES if (folder / name).is_file()]
        if found:
            return [Path(os.path.relpath(folder / name, worktree)).as_posix() for name in found]
        folder = folder.parent
    return []


def _link(target: Path, link: Path) -> None:
    """A directory symlink, or on Windows a junction when the symlink is refused."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        import _winapi  # noqa: PLC0415  (Windows only)

        _winapi.CreateJunction(str(target), str(link))


_WRITES_THROUGH = (
    "the worktree already holds this path as a link to a dependency folder, and the "
    "offline install would write through it into the main tree: replace the worktree "
    "as the gate's rebuild does (its build folders carried out and back) and run this "
    "call before anything else links into it"
)


def link_all(project_root: Path, worktree: Path, rel_dirs: list[str], mode: str = "default") -> dict:
    """Link each folder whole, holding back the ones an offline install has to make.

    mode is `default` (no install has run yet), `installed` (it has) or
    `link-workspace` (no install can serve, so link every folder whole).
    """
    linked: list[str] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    workspace: list[dict] = []
    held: set[str] = set()
    for rel in rel_dirs:
        if not (worktree / rel).parent.is_dir():
            continue
        links = workspace_links(project_root, rel)
        if links:
            held.add(rel)
            workspace.append({"path": rel, "lockfiles": lockfiles(worktree, rel), "links": links})
    hold_all = bool(held) and mode == "default"
    for rel in rel_dirs:
        target = project_root / rel
        link = worktree / rel
        if not link.parent.is_dir():
            skipped.append({"path": rel, "reason": "parent-missing"})
            continue
        if os.path.lexists(link):
            if hold_all and _is_link(str(link)):
                failed.append({"path": rel, "error": _WRITES_THROUGH})
            else:
                skipped.append({"path": rel, "reason": "exists"})
            continue
        if rel in held and mode != "link-workspace":
            skipped.append({"path": rel, "reason": "workspace"})
            continue
        if hold_all:
            skipped.append({"path": rel, "reason": "install-first"})
            continue
        try:
            _link(target.resolve(), link)
        except OSError as exc:
            failed.append({"path": rel, "error": str(exc)})
            continue
        linked.append(rel)
    return {"linked": linked, "skipped": skipped, "failed": failed, "workspace": workspace}


def _relative_dir(raw: str, project_root: Path) -> str | None:
    """`raw` as a `/` path relative to project_root, or None when it leaves it."""
    if os.path.isabs(raw) or Path(raw).drive:
        return None
    full = os.path.normpath(os.path.join(project_root, raw))
    rel = os.path.relpath(full, project_root)
    if rel == os.curdir or rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return None
    return Path(rel).as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Link the main tree's dependency folders into a gate's measurement worktree."
    )
    parser.add_argument("--project-root", required=True, help="the main tree")
    parser.add_argument("--worktree", required=True, help="the gate's measurement worktree")
    parser.add_argument(
        "--dir",
        action="append",
        default=[],
        help="a folder to link, relative to the project root; repeat for several "
        "(default: every node_modules folder)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--installed",
        action="store_true",
        help="the worktree has had its offline install: link whole each folder it still "
        "lacks, never one that holds a workspace link",
    )
    mode.add_argument(
        "--link-workspace",
        action="store_true",
        help="no install can serve: link every folder whole, one that holds a workspace "
        "link included, so a run reads the main tree's copy of each workspace package",
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    project_root = Path(args.project_root).resolve()
    worktree = Path(args.worktree).resolve()
    for name, folder in (("project root", project_root), ("worktree", worktree)):
        if not folder.is_dir():
            print(json.dumps({"error": f"the {name} is not a folder: {folder}"}), file=sys.stderr)
            return 2
    if args.dir:
        rel_dirs = []
        for raw in args.dir:
            rel = _relative_dir(raw, project_root)
            if rel is None:
                print(
                    json.dumps({"error": f"--dir must be a folder inside the project root: {raw}"}),
                    file=sys.stderr,
                )
                return 2
            rel_dirs.append(rel)
    else:
        rel_dirs = discover(project_root)
    mode_name = "installed" if args.installed else "link-workspace" if args.link_workspace else "default"
    result = link_all(project_root, worktree, rel_dirs, mode_name)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
