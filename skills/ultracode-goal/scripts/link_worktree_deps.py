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
see it. A folder that holds a workspace link is never linked: the worktree
gets an offline install instead. An install writes through a linked folder
into the main tree (npm's and pnpm's do), so when any folder holds one, the
call links nothing at all and holds every other folder back (`install-first`),
and it fails a folder the worktree already holds as a link, which the install
would write through. The same call with `--install` then runs that install
and links whole each folder the worktree still lacks, never one that holds a
workspace link. When no install can serve, the same call with
`--link-workspace` links every folder whole, those included, as before: the
gate then reads the main tree's copy of each package such a link points to.

The install. No allowlist entry runs a package manager, since a rule matches a
command by its start only and would let the same install run in any folder,
the main tree included, where npm's clean install empties and rebuilds
`node_modules` and every install runs lifecycle scripts. So
`--install` is the one way the gate installs, and it runs only into the gate's
own worktree. It refuses (exit 3, its reason under `refused`, nothing run or
linked) unless the worktree is one `git worktree list --porcelain` gives for
the project root, is not the main worktree or the project root, and is a
folder named `.gate-worktree-<story_id>` right inside `--impl-artifacts`,
where the gate builds it (references/gate.md); unless every folder under
`workspace` has exactly one lockfile, of npm, bun or pnpm (a `yarn.lock`, two
lockfiles or none are refused, so the gate takes its fallback); unless each
lockfile's folder resolves, through any link, inside the worktree; and unless
each dependency folder the install would write (each folder of the call at or
under that folder, and that folder's own `node_modules`) resolves inside the
worktree too, so none is a link into the main tree. Then it runs, once per
lockfile, in the worktree's copy of the lockfile's folder, as an argument
list with no shell, only the offline, frozen-lockfile form the lockfile
names: `npm ci --offline --prefix <folder>` for `package-lock.json` or
`npm-shrinkwrap.json`, `bun install --frozen-lockfile --offline --cwd
<folder>` for `bun.lock` or `bun.lockb`, and `pnpm install --offline
--frozen-lockfile --dir <folder>` for `pnpm-lock.yaml`. Each runs the
packages' lifecycle scripts, as the main tree's install did, so a workspace
package whose `prepare` builds its entry point gets it built from the
commit's source. When an install exits non-zero, or cannot start, it stops,
links nothing and exits 1.

How each link is made. A directory symlink to the main tree's folder, at the
same relative path in the worktree. On Windows, where a symlink needs a
privilege or Developer Mode, a directory junction instead, which needs
neither. A folder whose parent the worktree does not have (the commit under
assessment has no such package) is skipped, and so is a path the worktree
already holds (a link a resumed gate made, a folder the install made, or a
tracked folder of that name).

Usage:
    uv run link_worktree_deps.py --project-root <main tree> --worktree <path>
        [--dir <relpath> ...] [--install --impl-artifacts <path> | --link-workspace]

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
parent, that holds any, `[]` when none does. With `--install` it also prints
`installs`, one `{"lockfile", "command", "exit", "error"}` per install it ran
(`command` the argument list, `exit` null when it could not start, `error`
the last line it printed that names an error, npm's pointer to its log aside,
when it failed, `""` otherwise), and, when it
refused, `refused`, the reason. Exit 0 when every install ran and every link
was made or skipped, 1 when an install or a link failed, 2 when the project
root or the worktree is not a folder, a `--dir` is absolute or leaves the
project root, or `--install` comes without `--impl-artifacts`, and 3 when
`--install` refused.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
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
# The one install `--install` runs for each lockfile it serves, the folder appended: offline and
# frozen to the lockfile, so it installs only what the lockfile pins, from the local cache, or fails.
INSTALLS = {
    "package-lock.json": ("npm", "ci", "--offline", "--prefix"),
    "npm-shrinkwrap.json": ("npm", "ci", "--offline", "--prefix"),
    "bun.lock": ("bun", "install", "--frozen-lockfile", "--offline", "--cwd"),
    "bun.lockb": ("bun", "install", "--frozen-lockfile", "--offline", "--cwd"),
    "pnpm-lock.yaml": ("pnpm", "install", "--offline", "--frozen-lockfile", "--dir"),
}
# The name of the gate's worktree, right inside the implementation artifacts folder (gate.md).
GATE_WORKTREE_PREFIX = ".gate-worktree-"
# A line that names an error, and npm's last one, which only points to its log.
_ERROR_LINE = re.compile(r"\berror\b|\bERR[_!]", re.IGNORECASE)
_NPM_LOG_POINTER = "A complete log of this run can be found in"


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


def workspace_folders(project_root: Path, worktree: Path, rel_dirs: list[str]) -> list[dict]:
    """The `workspace` entries: each folder whose parent the worktree has that holds a workspace link."""
    workspace = []
    for rel in rel_dirs:
        if not (worktree / rel).parent.is_dir():
            continue
        links = workspace_links(project_root, rel)
        if links:
            workspace.append({"path": rel, "lockfiles": lockfiles(worktree, rel), "links": links})
    return workspace


def link_all(
    project_root: Path,
    worktree: Path,
    rel_dirs: list[str],
    mode: str = "default",
    workspace: list[dict] | None = None,
) -> dict:
    """Link each folder whole, holding back the ones an offline install has to make.

    mode is `default` (no install has run yet), `installed` (it has) or
    `link-workspace` (no install can serve, so link every folder whole).
    """
    linked: list[str] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    if workspace is None:
        workspace = workspace_folders(project_root, worktree, rel_dirs)
    held = {entry["path"] for entry in workspace}
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


def _same(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _inside(path: str | Path, folder: Path) -> bool:
    """Whether path resolves, through any link, to folder or inside it."""
    real = os.path.normcase(os.path.realpath(path))
    real_folder = os.path.normcase(os.path.realpath(folder))
    return real == real_folder or real.startswith(real_folder.rstrip(os.sep) + os.sep)


def _listed_worktrees(project_root: Path) -> tuple[list[str], str]:
    """The worktrees `git worktree list --porcelain` gives for project_root, main first, or why not."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "worktree", "list", "--porcelain"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        return [], f"git could not run: {exc}"
    if proc.returncode:
        lines = proc.stderr.strip().splitlines()
        return [], lines[-1] if lines else f"git worktree list exited {proc.returncode}"
    return [line[len("worktree ") :] for line in proc.stdout.splitlines() if line.startswith("worktree ")], ""


def not_the_gate_worktree(project_root: Path, worktree: Path, impl_artifacts: Path) -> str | None:
    """Why worktree is not the gate's own worktree of project_root, or None when it is."""
    if _same(worktree, project_root):
        return f"the worktree is the project root, the main tree: {worktree}"
    listed, error = _listed_worktrees(project_root)
    if error:
        return f"`git worktree list` cannot list the project root's worktrees: {error}"
    if listed and _same(worktree, listed[0]):
        return f"the worktree is the main worktree: {worktree}"
    if not any(_same(worktree, path) for path in listed):
        return f"the worktree is not one `git worktree list` gives for the project root: {worktree}"
    real = Path(os.path.realpath(worktree))
    if not (
        real.name.startswith(GATE_WORKTREE_PREFIX)
        and len(real.name) > len(GATE_WORKTREE_PREFIX)
        and _same(real.parent, impl_artifacts)
    ):
        return (
            f"the worktree is not `{GATE_WORKTREE_PREFIX}<story_id>` right inside the implementation "
            f"artifacts folder, where the gate builds it: {worktree}"
        )
    return None


def install_plan(
    worktree: Path, rel_dirs: list[str], workspace: list[dict]
) -> tuple[list[tuple[str, list[str]]], str | None]:
    """Each lockfile to install for, with its argument list, or why `--install` refuses.

    One install per lockfile, in the order `workspace` first names it.
    """
    plan: dict[str, list[str]] = {}
    for entry in workspace:
        names = [lockfile.rsplit("/", 1)[-1] for lockfile in entry["lockfiles"]]
        if len(names) != 1 or names[0] not in INSTALLS:
            found = ", ".join(entry["lockfiles"]) or "none"
            return [], (
                f"`{entry['path']}` holds a workspace link and its lockfiles are {found}: an offline "
                f"install runs only for exactly one of {', '.join(INSTALLS)}"
            )
        lockfile = entry["lockfiles"][0]
        if lockfile in plan:
            continue
        rel_folder = lockfile.rsplit("/", 1)[0] if "/" in lockfile else ""
        folder = worktree / rel_folder
        if not _inside(folder, worktree):
            return [], f"`{lockfile}`'s folder resolves outside the worktree: {os.path.realpath(folder)}"
        writes = [Path(rel_folder, DEPENDENCY_DIR).as_posix()] + [
            rel for rel in rel_dirs if not rel_folder or rel.startswith(rel_folder + "/")
        ]
        for rel in writes:
            if not _inside(worktree / rel, worktree):
                return [], (
                    f"`{rel}`, which the install of `{lockfile}` would write, resolves outside the worktree "
                    f"(into the main tree, or another folder), and the install would write through it: "
                    f"{os.path.realpath(worktree / rel)}"
                )
        plan[lockfile] = [*INSTALLS[lockfile.rsplit("/", 1)[-1]], os.path.realpath(folder)]
    return list(plan.items()), None


def _error_line(*outputs: str) -> str:
    """The last line that names an error (npm's pointer to its log aside), else the last line printed."""
    for output in outputs:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        named = [line for line in lines if _ERROR_LINE.search(line) and _NPM_LOG_POINTER not in line]
        if named:
            return named[-1]
    for output in outputs:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if lines:
            return lines[-1]
    return ""


def run_install(lockfile: str, command: list[str]) -> dict:
    """Run one install, its program found on PATH, as an argument list with no shell."""
    record = {"lockfile": lockfile, "command": command, "exit": None, "error": ""}
    program = shutil.which(command[0])
    if program is None:
        record["error"] = f"{command[0]} is not on PATH"
        return record
    try:
        proc = subprocess.run(
            [program, *command[1:]],
            cwd=command[-1],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        record["error"] = str(exc)
        return record
    record["exit"] = proc.returncode
    if proc.returncode:
        record["error"] = _error_line(proc.stderr, proc.stdout)
    return record


def install(
    project_root: Path, worktree: Path, impl_artifacts: Path, rel_dirs: list[str]
) -> tuple[dict, int]:
    """`--install`: the checks, each offline install, then the links the install did not make."""
    workspace = workspace_folders(project_root, worktree, rel_dirs)
    refused = not_the_gate_worktree(project_root, worktree, impl_artifacts)
    plan: list[tuple[str, list[str]]] = []
    if refused is None:
        plan, refused = install_plan(worktree, rel_dirs, workspace)
    if refused is not None:
        result = {"linked": [], "skipped": [], "failed": [], "workspace": workspace}
        return {**result, "installs": [], "refused": refused}, 3
    installs = []
    for lockfile, command in plan:
        installs.append(run_install(lockfile, command))
        if installs[-1]["exit"] != 0:
            result = {"linked": [], "skipped": [], "failed": [], "workspace": workspace}
            return {**result, "installs": installs}, 1
    result = link_all(project_root, worktree, rel_dirs, "installed", workspace)
    return {**result, "installs": installs}, 1 if result["failed"] else 0


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
        "--install",
        action="store_true",
        help="give the gate's worktree the offline, frozen-lockfile install each lockfile "
        "names, then link whole each folder it still lacks, never one that holds a "
        "workspace link; refused (exit 3) for any other worktree or lockfile",
    )
    mode.add_argument(
        "--link-workspace",
        action="store_true",
        help="no install can serve: link every folder whole, one that holds a workspace "
        "link included, so a run reads the main tree's copy of each workspace package",
    )
    parser.add_argument(
        "--impl-artifacts",
        help="with --install: the implementation artifacts folder, where the gate builds its worktree",
    )
    args = parser.parse_args(argv)
    if args.install and not args.impl_artifacts:
        parser.error("--install needs --impl-artifacts")
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
    if args.install:
        result, code = install(project_root, worktree, Path(args.impl_artifacts), rel_dirs)
    else:
        mode_name = "link-workspace" if args.link_workspace else "default"
        result = link_all(project_root, worktree, rel_dirs, mode_name)
        code = 1 if result["failed"] else 0
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
