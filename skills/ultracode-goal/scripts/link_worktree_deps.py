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
`.git`, `__pycache__`, a gate worktree (`.gate-worktree-*`, under the
implementation artifacts folder), a repository or worktree nested in the tree
(a folder holding a `.git`, such as an agent worktree or a submodule, whose
files the gate's worktree does not check out), a Python virtual environment
(a folder holding `pyvenv.cfg`) or a cache folder (one holding `CACHEDIR.TAG`,
such as Cargo's `target`). None holds the project's own dependencies, and some
are large. A folder is judged by what it holds, not by its name, so a
workspace package named `target` or a JavaScript action under `.github/` is
still walked.
`--dir` names a folder to link instead, relative to the project root, for a
dependency folder of another name (`vendor`); repeat it for several. Given
any `--dir`, nothing is discovered.

How each link is made. A directory symlink to the main tree's folder, at the
same relative path in the worktree. On Windows, where a symlink needs a
privilege or Developer Mode, a directory junction instead, which needs
neither. A folder whose parent the worktree does not have (the commit under
assessment has no such package) is skipped, and so is a path the worktree
already holds (a link a resumed gate made, or a tracked folder of that name).

Usage:
    uv run link_worktree_deps.py --project-root <main tree> --worktree <path> [--dir <relpath> ...]

Output: JSON on stdout, `{"linked": [...], "skipped": [{"path", "reason"}],
"failed": [{"path", "error"}]}`, paths relative to the project root with `/`
separators; `reason` is `parent-missing` or `exists`. Exit 0 when every link
was made or skipped, 1 when any failed, and 2 when the project root or the
worktree is not a folder, or a `--dir` is absolute or leaves the project root.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEPENDENCY_DIR = "node_modules"
_GATE_WORKTREE_PREFIX = ".gate-worktree-"
# Folders the walk never enters, by name.
_UNWALKED = frozenset({".git", "__pycache__"})
# A folder holding one of these is another repository or worktree (`.git`), a
# Python virtual environment, or a cache (the Cache Directory Tagging spec).
_UNWALKED_MARKERS = frozenset({".git", "pyvenv.cfg", "CACHEDIR.TAG"})


def discover(project_root: Path, worktree: Path) -> list[str]:
    """Every `node_modules` folder under project_root, outermost only, sorted.

    Paths are compared as os.walk spells them under the resolved project root,
    so the worktree is skipped by one string comparison, with no realpath call
    per folder.
    """
    skip = os.path.normcase(str(worktree))
    found: list[str] = []
    for current, dirs, files in os.walk(project_root):
        if current != str(project_root) and _UNWALKED_MARKERS.intersection((*dirs, *files)):
            dirs[:] = []  # a nested repository, a virtual environment or a cache
            continue
        kept = []
        for name in dirs:
            full = os.path.join(current, name)
            if name == DEPENDENCY_DIR:
                found.append(Path(os.path.relpath(full, project_root)).as_posix())
            elif not (
                name in _UNWALKED
                or name.startswith(_GATE_WORKTREE_PREFIX)
                or os.path.normcase(full) == skip
            ):
                kept.append(name)
        dirs[:] = kept
    return sorted(found)


def _link(target: Path, link: Path) -> None:
    """A directory symlink, or on Windows a junction when the symlink is refused."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        import _winapi  # noqa: PLC0415  (Windows only)

        _winapi.CreateJunction(str(target), str(link))


def link_all(project_root: Path, worktree: Path, rel_dirs: list[str]) -> dict:
    linked: list[str] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    for rel in rel_dirs:
        target = project_root / rel
        link = worktree / rel
        if not link.parent.is_dir():
            skipped.append({"path": rel, "reason": "parent-missing"})
            continue
        if os.path.lexists(link):
            skipped.append({"path": rel, "reason": "exists"})
            continue
        try:
            _link(target.resolve(), link)
        except OSError as exc:
            failed.append({"path": rel, "error": str(exc)})
            continue
        linked.append(rel)
    return {"linked": linked, "skipped": skipped, "failed": failed}


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
        rel_dirs = discover(project_root, worktree)
    result = link_all(project_root, worktree, rel_dirs)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
