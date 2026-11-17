#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Carry a gate worktree's build folders aside across its rebuild.

The gate (references/gate.md) replaces its measurement worktree with
`git worktree remove --force` and `git worktree add`, which deletes every
ignored folder the worktree held, Cargo's `target` among them, so each story
paid two cold builds. This script moves those build folders out of the
worktree into a stash right before the removal (`out`), and back to the same
paths right after the add (`back`). When the story escalates instead of
being gated again, `drop` deletes what the stash holds. It runs under
`uv run`, which the run's allowlist covers; a bare `mv` or `rm` is not on it.

Which folders. By default every Cargo build folder in the tree, outermost
only: a folder holding both `CACHEDIR.TAG` and `.rustc_info.json`, such as
the root's `target` or a Tauri app's `src-tauri/target`. A folder is judged by
what it holds, not by its name. The walk does not enter `.git`,
`node_modules`, a repository or worktree nested in the tree, a Python virtual
environment, any other cache folder (one holding `CACHEDIR.TAG` alone, such
as `.pytest_cache`) or a link. `--dir` names a build folder of another
toolchain instead, relative to the worktree; repeat it for several. Given any
`--dir`, nothing is discovered. Never carried: a test-result cache
(`.pytest_cache`, a turbo or nx cache), whose replayed results would stand in
for runs that never happened, a path reached through a link or a junction,
and a path that resolves outside the worktree or the stash.

How each folder moves. With `os.rename` only, to the same relative path, so a
tool that keys its cache on the folder's path finds it valid. A folder that
fails to move stays where it was: `out` leaves it in the worktree, which the
removal then deletes with it, so the next build is cold but never wrong.
Before `out` moves a Cargo build folder, it deletes the run results Cargo's
tools keep there (`criterion/`, `nextest/`, `tarpaulin/`, `llvm-cov/` and
`tmp/`, Cargo's `CARGO_TARGET_TMPDIR`, which Cargo never cleans, at its top
and at the top of every Cargo build folder inside it, such as
`llvm-cov-target`, and every `*.profraw` and `*.profdata` file in it), since
a mutant's run wrote them. Such a name is deleted only when it is a folder or
a link (the link itself); a plain file of that name stays. `out` clears
every folder it carries this way, a `--dir` one included, so a Cargo build
folder nested in another toolchain's folder loses its run results too. A folder whose run
results cannot all be deleted, an unreadable folder inside it included, is
not carried. `out` skips a folder the
stash already holds (`exists`), so nothing is merged. `back` skips a folder
whose parent the worktree does not have (`parent-missing`) or whose path the
worktree already holds (`exists`), and leaves it in the stash. The stash gets
a `.gitignore` holding `*` when `out` first creates it, so a status read of
the tree that holds it never lists its files. A stash `back` finds missing
holds nothing to carry.

How `drop` deletes. Every folder the stash holds, with everything in it,
never through a link: a link inside is deleted itself, never what it points
at, and a folder of the stash that is a link, or a stash that is one, is
skipped. The stash's `.gitignore` stays. A missing stash holds nothing to
delete; a stash it cannot reach (a parent folder it may not search) is
reported under `failed`. Since it deletes every folder it finds, `drop` refuses a stash that
is not a folder named `gate-build` holding the `.gitignore` reading `*` that
`out` writes, or one that holds a `.git`.

Usage:
    uv run carry_build_cache.py out --worktree <path> --stash <path> [--dir <relpath> ...]
    uv run carry_build_cache.py back --worktree <path> --stash <path> [--dir <relpath> ...]
    uv run carry_build_cache.py drop --stash <path>

Output: JSON on stdout, `{"mode", "carried": [...], "cleared": [...],
"skipped": [{"path", "reason"}], "failed": [{"path", "error"}]}`, paths
relative to the worktree (to the stash for `drop`) with `/` separators;
`cleared` lists the run results `out` deleted, or the folders `drop` deleted,
and `reason` is `missing`, `exists`, `parent-missing`, `link`, `outside`,
`not-a-folder` or `test-result-cache`. Exit 0 when every folder was carried,
deleted or skipped, 1 when any failed, and 2 when the call is wrong: the
worktree is missing or not a folder, the stash is not a folder (for `out` and
`back`, a stash that is a link included), the stash and the worktree overlap,
a `--dir` is absolute or leaves the worktree, or `drop` was given a folder
that is not a stash.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path

# The folder name the gate gives its stash; `drop` refuses any other.
STASH_NAME = "gate-build"
# Cargo writes both into every build folder it makes.
CARGO_MARKERS = ("CACHEDIR.TAG", ".rustc_info.json")
# What Cargo's tools leave in a build folder after a run: Criterion's
# baselines, nextest's archives and reports, tarpaulin's and cargo-llvm-cov's
# reports, the scratch folder Cargo gives integration tests and benches as
# `CARGO_TARGET_TMPDIR` and never cleans, and the coverage profiles of an
# instrumented run.
_RUN_RESULT_DIRS = ("criterion", "nextest", "tarpaulin", "llvm-cov", "tmp")
_RUN_RESULT_SUFFIXES = (".profraw", ".profdata")
# Folders the walk never enters, by name.
_UNWALKED = frozenset({".git", "node_modules", "__pycache__"})
# A folder holding one of these is another repository or worktree (`.git`), a
# Python virtual environment, or a cache (the Cache Directory Tagging spec).
_UNWALKED_MARKERS = frozenset({".git", "pyvenv.cfg", "CACHEDIR.TAG"})
# Caches that replay a test task's result instead of running it.
_RESULT_CACHE_NAMES = frozenset({".pytest_cache", ".turbo", ".nx"})
_RESULT_CACHE_UNDER_DOT_CACHE = frozenset({"turbo", "nx"})
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _is_link(path: str | Path) -> bool:
    """A symbolic link, or on Windows any reparse point, a junction included."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & _REPARSE_POINT)


def _reached_through_a_link(root: Path, rel: str) -> bool:
    """Whether any folder on the way from root to root/rel, rel included, is a link."""
    current = str(root)
    for part in Path(rel).parts:
        current = os.path.join(current, part)
        if _is_link(current):
            return True
    return False


def _common(a: str, b: str) -> str | None:
    """The longest common path of a and b, or None for paths with no common
    root (two Windows drives)."""
    try:
        return os.path.commonpath([a, b])
    except ValueError:
        return None


def _inside(path: Path, root: Path) -> bool:
    real, real_root = os.path.realpath(path), os.path.realpath(root)
    return real != real_root and _common(real, real_root) == real_root


def _is_cargo_folder(path: Path) -> bool:
    return all(os.path.isfile(path / marker) for marker in CARGO_MARKERS)


def _is_result_cache(rel: str) -> bool:
    parts = Path(rel).parts
    if any(part in _RESULT_CACHE_NAMES for part in parts):
        return True
    return any(
        parts[i] == ".cache" and parts[i + 1] in _RESULT_CACHE_UNDER_DOT_CACHE for i in range(len(parts) - 1)
    )


def discover(root: Path) -> list[str]:
    """Every Cargo build folder under root, outermost only, sorted."""
    found: list[str] = []
    for current, dirs, files in os.walk(root):
        here = Path(current)
        entries = set(dirs) | set(files)
        if current != str(root) and entries & _UNWALKED_MARKERS:
            if _is_cargo_folder(here):
                found.append(Path(os.path.relpath(current, root)).as_posix())
            dirs[:] = []  # a build folder, another cache, a nested repository or a virtual environment
            continue
        dirs[:] = [name for name in dirs if name not in _UNWALKED and not _is_link(here / name)]
    return sorted(found)


def _outermost(rels: list[str]) -> list[str]:
    """Each path once, without one that sits inside another of them."""
    kept: list[str] = []
    for rel in sorted(set(rels)):
        if not any(rel.startswith(outer + "/") for outer in kept):
            kept.append(rel)
    return kept


def _raise(error: OSError) -> None:
    """An `os.walk` onerror that stops the walk: a folder it cannot read is a
    folder it cannot clear."""
    raise error


def _delete_link(path: Path) -> None:
    try:
        os.unlink(path)
    except OSError:
        os.rmdir(path)  # a junction on Windows


def _delete_folder(path: Path) -> None:
    """Delete a folder with everything in it, or a link, which is deleted
    itself and never followed. Raises OSError on a failure."""
    if _is_link(path):
        _delete_link(path)
    else:
        shutil.rmtree(path)


def _clear_run_results(folder: Path, rel: str, cleared: list[str]) -> None:
    """Delete the run results Cargo's tools keep in folder and in every Cargo
    build folder inside it, adding each to cleared. A run-result name is
    deleted only when it is a folder or a link (the link itself, never what it
    points at); a plain file of that name stays. Raises OSError when one
    cannot be deleted or a folder in it cannot be read."""
    for current, dirs, files in os.walk(folder, onerror=_raise):
        here = Path(current)
        cargo = _is_cargo_folder(here)
        kept: list[str] = []
        for name in sorted(dirs):
            path = here / name
            if cargo and name in _RUN_RESULT_DIRS:
                _delete_folder(path)
                cleared.append(Path(rel, os.path.relpath(path, folder)).as_posix())
            elif not _is_link(path):
                kept.append(name)
        dirs[:] = kept
        for name in sorted(files):
            path = here / name
            if (cargo and name in _RUN_RESULT_DIRS and _is_link(path)) or name.endswith(_RUN_RESULT_SUFFIXES):
                if _is_link(path):
                    _delete_link(path)
                else:
                    os.unlink(path)
                cleared.append(Path(rel, os.path.relpath(path, folder)).as_posix())


def _prune_empty_parents(path: Path, root: Path) -> None:
    """Remove the folders between root and path that the move left empty."""
    parent = path.parent
    while parent != root and root in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent


def _make_stash(stash: Path) -> None:
    stash.mkdir(parents=True, exist_ok=True)
    ignore = stash / ".gitignore"
    if not os.path.exists(ignore):
        ignore.write_text("*\n", encoding="utf-8")


def _within(path: Path, root: Path) -> bool:
    """Whether path resolves to root or to a path inside it."""
    return os.path.realpath(path) == os.path.realpath(root) or _inside(path, root)


def carry(mode: str, worktree: Path, stash: Path, rel_dirs: list[str]) -> dict:
    """Move each folder in rel_dirs from the worktree to the stash (`out`) or
    from the stash to the worktree (`back`), at the same relative path."""
    source_root, target_root = (worktree, stash) if mode == "out" else (stash, worktree)
    carried: list[str] = []
    cleared: list[str] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    for rel in rel_dirs:
        source, target = source_root / rel, target_root / rel
        parent_rel = Path(rel).parent.as_posix()
        if _is_result_cache(rel):
            skipped.append({"path": rel, "reason": "test-result-cache"})
        elif not os.path.lexists(source):
            skipped.append({"path": rel, "reason": "missing"})
        elif _reached_through_a_link(source_root, rel) or (
            parent_rel != "." and _reached_through_a_link(target_root, parent_rel)
        ):
            skipped.append({"path": rel, "reason": "link"})
        elif not _inside(source, source_root):
            skipped.append({"path": rel, "reason": "outside"})
        elif not os.path.isdir(source):
            skipped.append({"path": rel, "reason": "not-a-folder"})
        elif mode == "back" and not os.path.isdir(target.parent):
            skipped.append({"path": rel, "reason": "parent-missing"})
        elif os.path.lexists(target):
            skipped.append({"path": rel, "reason": "exists"})
        elif not _within(target.parent, target_root):
            skipped.append({"path": rel, "reason": "outside"})
        else:
            try:
                if mode == "out":
                    # Every folder carried out, a `--dir` one included: the
                    # clearing finds each Cargo build folder inside it.
                    _clear_run_results(source, rel, cleared)
                    _make_stash(stash)
                    target.parent.mkdir(parents=True, exist_ok=True)
                os.rename(source, target)
            except OSError as exc:
                failed.append({"path": rel, "error": str(exc)})
                continue
            carried.append(rel)
            if mode == "back":
                _prune_empty_parents(source, stash)
    return {"mode": mode, "carried": carried, "cleared": cleared, "skipped": skipped, "failed": failed}


def drop(stash: Path) -> dict:
    """Delete every folder the stash holds, never through a link."""
    cleared: list[str] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    if _is_link(stash):
        skipped.append({"path": ".", "reason": "link"})
    elif os.path.isdir(stash):
        try:
            entries = sorted(os.listdir(stash))
        except OSError as exc:
            failed.append({"path": ".", "error": str(exc)})
            entries = []
        for entry in entries:
            path = stash / entry
            if _is_link(path):
                skipped.append({"path": entry, "reason": "link"})
            elif os.path.isdir(path):
                try:
                    shutil.rmtree(path)
                except OSError as exc:
                    failed.append({"path": entry, "error": str(exc)})
                    continue
                cleared.append(entry)
    return {"mode": "drop", "carried": [], "cleared": cleared, "skipped": skipped, "failed": failed}


def _relative_dir(raw: str, root: Path) -> str | None:
    """`raw` as a `/` path relative to root, or None when it leaves it."""
    if os.path.isabs(raw) or Path(raw).drive:
        return None
    full = os.path.normpath(os.path.join(root, raw))
    rel = os.path.relpath(full, root)
    if rel == os.curdir or rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return None
    return Path(rel).as_posix()


def _overlap(a: Path, b: Path) -> bool:
    real_a, real_b = os.path.realpath(a), os.path.realpath(b)
    common = _common(real_a, real_b)
    return common is not None and common in (real_a, real_b)


def _is_a_stash(stash: Path) -> str | None:
    """Why the folder `drop` was given is not a stash `out` made, or None:
    `drop` deletes every folder it holds, so a wrong path must never reach it."""
    if stash.name != STASH_NAME:
        return f"the stash must be a folder named {STASH_NAME}: {stash}"
    try:
        ignore = (stash / ".gitignore").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        ignore = None
    if ignore is None or ignore.rstrip("\r\n") != "*":
        return f"the stash holds no .gitignore reading * as out writes it: {stash}"
    if os.path.lexists(stash / ".git"):
        return f"the stash holds a .git, so it is a repository or a worktree: {stash}"
    return None


def _error(message: str) -> int:
    print(json.dumps({"error": message}), file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carry a gate worktree's build folders aside across its rebuild.")
    parser.add_argument(
        "mode",
        choices=("out", "back", "drop"),
        help="out: worktree to stash; back: stash to worktree; drop: delete what the stash holds",
    )
    parser.add_argument("--worktree", help="the gate's measurement worktree (out and back)")
    parser.add_argument("--stash", required=True, help="the folder that holds the build folders between the two")
    parser.add_argument(
        "--dir",
        action="append",
        default=[],
        help="a build folder to carry, relative to the worktree; repeat for several "
        "(default: every Cargo build folder)",
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    stash = Path(os.path.abspath(args.stash))
    if args.mode == "drop":
        if args.worktree or args.dir:
            return _error("drop takes --stash alone")
        try:
            os.lstat(stash)
        except FileNotFoundError:
            pass  # no stash: nothing to delete
        except OSError as exc:
            result = {"mode": "drop", "carried": [], "cleared": [], "skipped": [],
                      "failed": [{"path": ".", "error": str(exc)}]}
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1
        if os.path.lexists(stash) and not _is_link(stash):
            if not os.path.isdir(stash):
                return _error(f"the stash is not a folder: {stash}")
            reason = _is_a_stash(stash)
            if reason is not None:
                return _error(reason)
        result = drop(stash)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result["failed"] else 0
    if not args.worktree:
        return _error(f"{args.mode} needs --worktree")
    if _is_link(stash):
        return _error(f"the stash is a link: {stash}")
    if os.path.lexists(stash) and not os.path.isdir(stash):
        return _error(f"the stash is not a folder: {stash}")
    worktree = Path(os.path.abspath(args.worktree))
    if not os.path.isdir(worktree):
        return _error(f"the worktree is not a folder: {worktree}")
    if _overlap(worktree, stash):
        return _error(f"the stash and the worktree must not hold each other: {stash}")
    rel_dirs = []
    for raw in args.dir:
        rel = _relative_dir(raw, worktree)
        if rel is None:
            return _error(f"--dir must be a folder inside the worktree: {raw}")
        rel_dirs.append(rel)
    if not rel_dirs:
        root = worktree if args.mode == "out" else stash
        rel_dirs = discover(root) if os.path.isdir(root) else []
    result = carry(args.mode, worktree, stash, _outermost(rel_dirs))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
