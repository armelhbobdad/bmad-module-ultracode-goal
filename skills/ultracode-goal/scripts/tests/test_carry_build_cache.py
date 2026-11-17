#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""carry_build_cache.py: the gate worktree's build folders, carried across its rebuild.

#240: the gate's rebuild (`git worktree remove --force`, then `git worktree
add`) deleted every ignored folder the worktree held, Cargo's `target` among
them, so each story paid two cold builds. The script moves each build folder
into a stash in the story's scratch folder before the removal and back to the
same path after the add. These tests run it as the gate does, `out`, a
replaced worktree, then `back`, and pin what it never carries: a test-result
cache, a folder reached through a link, a path outside the worktree or the
stash, and the run results a mutant's run left in a Cargo build folder. Its
`drop` mode deletes what the stash holds when the story escalates instead.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "carry_build_cache.py"
_TAG = "Signature: 8a477f597d28d172789f06886806bc55\n"


def _run(*args: str) -> tuple[int, dict | None, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    out = json.loads(proc.stdout) if proc.stdout.strip() else None
    return proc.returncode, out, proc.stderr


def _cargo_target(folder: Path, artifact: str = "libdemo.rlib") -> None:
    """A Cargo build folder: its two markers and one build artifact."""
    (folder / "debug" / "deps").mkdir(parents=True)
    (folder / "CACHEDIR.TAG").write_text(_TAG, encoding="utf-8")
    (folder / ".rustc_info.json").write_text('{"rustc_fingerprint": 1}\n', encoding="utf-8")
    (folder / "debug" / "deps" / artifact).write_text("built\n", encoding="utf-8")


def _worktree(root: Path) -> Path:
    """A gate worktree as `git worktree add` leaves it: tracked files and a `.git` file."""
    root.mkdir(parents=True)
    (root / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    (root / "src-tauri" / "src").mkdir(parents=True)
    (root / "src-tauri" / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    (root / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    return root


@pytest.fixture
def gate(tmp_path: Path) -> tuple[Path, Path, Path]:
    """The main tree, the gate worktree a mutation pass built in, and the
    story's stash, all under the implementation artifacts folder."""
    main = tmp_path / "main"
    artifacts = main / "_bmad-output" / "implementation-artifacts"
    worktree = _worktree(artifacts / ".gate-worktree-1-2")
    _cargo_target(worktree / "target")
    _cargo_target(worktree / "src-tauri" / "target", "libapp.rlib")
    # Run results a mutant's run wrote: never carried.
    (worktree / "target" / "criterion" / "bench").mkdir(parents=True)
    (worktree / "target" / "nextest" / "default").mkdir(parents=True)
    (worktree / "target" / "tarpaulin").mkdir()
    (worktree / "target" / "llvm-cov-target").mkdir()
    (worktree / "target" / "llvm-cov-target" / "demo-1.profraw").write_text("raw\n", encoding="utf-8")
    (worktree / "target" / "llvm-cov").mkdir()
    (worktree / "target" / "tmp" / "it").mkdir(parents=True)  # CARGO_TARGET_TMPDIR, never cleaned by Cargo
    (worktree / "target" / "debug" / "demo.profdata").write_text("merged\n", encoding="utf-8")
    # A test-result cache: a cache folder, but no Cargo build folder.
    (worktree / ".pytest_cache" / "v" / "cache").mkdir(parents=True)
    (worktree / ".pytest_cache" / "CACHEDIR.TAG").write_text(_TAG, encoding="utf-8")
    (worktree / ".pytest_cache" / "v" / "cache" / "lastfailed").write_text("{}\n", encoding="utf-8")
    # The main tree's own build folder, reached from the worktree through its
    # linked dependency folder: never moved.
    _cargo_target(main / "node_modules" / "native" / "target")
    stash = artifacts / ".scratch-1-2" / "gate-build"
    return main, worktree, stash


def _rebuild(worktree: Path) -> None:
    """`git worktree remove --force` then `git worktree add`: every file the
    worktree held is gone, and the tracked ones come back."""
    shutil.rmtree(worktree)
    _worktree(worktree)


def test_out_then_back_puts_each_build_folder_at_its_path_with_its_contents(gate):
    _, worktree, stash = gate
    code, out, err = _run("out", "--worktree", str(worktree), "--stash", str(stash))
    assert code == 0, err
    assert out["mode"] == "out"
    assert out["carried"] == ["src-tauri/target", "target"]
    assert out["failed"] == [] and out["skipped"] == []
    assert not (worktree / "target").exists() and not (worktree / "src-tauri" / "target").exists()
    assert (stash / "target" / "debug" / "deps" / "libdemo.rlib").is_file()
    assert (stash / ".gitignore").read_text(encoding="utf-8") == "*\n"

    _rebuild(worktree)
    code, back, err = _run("back", "--worktree", str(worktree), "--stash", str(stash))
    assert code == 0, err
    assert back["mode"] == "back"
    assert back["carried"] == ["src-tauri/target", "target"]
    assert (worktree / "target" / "debug" / "deps" / "libdemo.rlib").read_text(encoding="utf-8") == "built\n"
    assert (worktree / "src-tauri" / "target" / "debug" / "deps" / "libapp.rlib").is_file()
    assert (worktree / "target" / "CACHEDIR.TAG").is_file()
    assert (worktree / "target" / ".rustc_info.json").is_file()
    # The stash keeps only its ignore file once everything went back.
    assert sorted(p.name for p in stash.iterdir()) == [".gitignore"]


def test_out_deletes_the_run_results_and_carries_no_test_result_cache(gate):
    _, worktree, stash = gate
    code, out, _ = _run("out", "--worktree", str(worktree), "--stash", str(stash))
    assert code == 0
    assert out["cleared"] == [
        "target/criterion",
        "target/nextest",
        "target/tarpaulin",
        "target/llvm-cov",
        "target/tmp",
        "target/debug/demo.profdata",
        "target/llvm-cov-target/demo-1.profraw",
    ]
    for name in ("criterion", "nextest", "tarpaulin", "llvm-cov", "tmp"):
        assert not (stash / "target" / name).exists()
    assert not (stash / "target" / "llvm-cov-target" / "demo-1.profraw").exists()
    assert not (stash / "target" / "debug" / "demo.profdata").exists()
    assert (stash / "target" / "debug" / "deps" / "libdemo.rlib").is_file()
    # The pytest cache stays in the worktree, to be deleted with it.
    assert (worktree / ".pytest_cache" / "v" / "cache" / "lastfailed").is_file()
    assert not (stash / ".pytest_cache").exists()


def test_a_folder_reached_through_a_link_never_moves(gate, tmp_path):
    main, worktree, stash = gate
    try:
        os.symlink(main / "node_modules", worktree / "node_modules", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available here")
    code, out, _ = _run("out", "--worktree", str(worktree), "--stash", str(stash))
    assert code == 0
    assert "node_modules/native/target" not in out["carried"]
    code, out, _ = _run(
        "out", "--worktree", str(worktree), "--stash", str(stash), "--dir", "node_modules/native/target"
    )
    assert code == 0
    assert out["skipped"] == [{"path": "node_modules/native/target", "reason": "link"}]
    assert (main / "node_modules" / "native" / "target" / "debug" / "deps" / "libdemo.rlib").is_file()


def test_a_linked_build_folder_never_moves(tmp_path):
    worktree = _worktree(tmp_path / "wt")
    real = tmp_path / "elsewhere" / "target"
    _cargo_target(real)
    try:
        os.symlink(real, worktree / "target", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available here")
    stash = tmp_path / "stash"
    code, out, _ = _run("out", "--worktree", str(worktree), "--stash", str(stash), "--dir", "target")
    assert code == 0
    assert out["carried"] == [] and out["skipped"] == [{"path": "target", "reason": "link"}]
    assert (real / "debug" / "deps" / "libdemo.rlib").is_file()


@pytest.mark.parametrize("cache", [".pytest_cache", ".turbo", ".nx/cache", "node_modules/.cache/turbo"])
def test_a_named_test_result_cache_is_never_carried(tmp_path, cache):
    worktree = _worktree(tmp_path / "wt")
    (worktree / cache).mkdir(parents=True)
    stash = tmp_path / "stash"
    code, out, _ = _run("out", "--worktree", str(worktree), "--stash", str(stash), "--dir", cache)
    assert code == 0
    assert out["skipped"] == [{"path": cache, "reason": "test-result-cache"}]
    assert (worktree / cache).is_dir() and not stash.exists()


def test_a_named_folder_of_another_toolchain_is_carried_instead(tmp_path):
    worktree = _worktree(tmp_path / "wt")
    _cargo_target(worktree / "target")
    (worktree / "build" / "classes").mkdir(parents=True)
    (worktree / "build" / "classes" / "App.class").write_text("cafebabe\n", encoding="utf-8")
    stash = tmp_path / "stash"
    code, out, _ = _run("out", "--worktree", str(worktree), "--stash", str(stash), "--dir", "build")
    assert code == 0
    # Given a `--dir`, nothing is discovered.
    assert out["carried"] == ["build"]
    assert (worktree / "target").is_dir()
    _rebuild(worktree)
    code, back, _ = _run("back", "--worktree", str(worktree), "--stash", str(stash), "--dir", "build")
    assert code == 0 and back["carried"] == ["build"]
    assert (worktree / "build" / "classes" / "App.class").is_file()


def test_out_leaves_a_stash_a_dead_session_left_alone(gate):
    _, worktree, stash = gate
    _cargo_target(stash / "target", "libolder.rlib")
    code, out, _ = _run("out", "--worktree", str(worktree), "--stash", str(stash))
    assert code == 0
    assert out["carried"] == ["src-tauri/target"]
    assert out["skipped"] == [{"path": "target", "reason": "exists"}]
    assert (stash / "target" / "debug" / "deps" / "libolder.rlib").is_file()
    assert not (stash / "target" / "debug" / "deps" / "libdemo.rlib").exists()


def test_back_skips_a_taken_path_and_a_missing_parent_and_leaves_them_stashed(gate):
    _, worktree, stash = gate
    _run("out", "--worktree", str(worktree), "--stash", str(stash))
    _rebuild(worktree)
    shutil.rmtree(worktree / "src-tauri")  # the commit under assessment has no src-tauri
    (worktree / "target").mkdir()  # a tracked folder of that name
    code, back, _ = _run("back", "--worktree", str(worktree), "--stash", str(stash))
    assert code == 0
    assert back["carried"] == []
    assert back["skipped"] == [
        {"path": "src-tauri/target", "reason": "parent-missing"},
        {"path": "target", "reason": "exists"},
    ]
    assert (stash / "target" / "debug" / "deps" / "libdemo.rlib").is_file()
    assert (stash / "src-tauri" / "target" / "debug" / "deps" / "libapp.rlib").is_file()


def test_back_with_no_stash_carries_nothing(tmp_path):
    worktree = _worktree(tmp_path / "wt")
    code, back, err = _run("back", "--worktree", str(worktree), "--stash", str(tmp_path / "none"))
    assert code == 0, err
    assert back == {"mode": "back", "carried": [], "cleared": [], "skipped": [], "failed": []}


def test_a_worktree_with_no_build_folder_makes_no_stash(tmp_path):
    worktree = _worktree(tmp_path / "wt")
    stash = tmp_path / "stash"
    code, out, _ = _run("out", "--worktree", str(worktree), "--stash", str(stash))
    assert code == 0 and out["carried"] == []
    assert not stash.exists()


def test_the_walk_skips_nested_trees_and_other_caches(tmp_path):
    worktree = _worktree(tmp_path / "wt")
    _cargo_target(worktree / "vendor" / "sub" / "target")
    (worktree / "vendor" / "sub" / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    _cargo_target(worktree / ".venv" / "target")
    (worktree / ".venv" / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    # Cargo's markers inside another cache are never reached.
    (worktree / ".mypy_cache").mkdir()
    (worktree / ".mypy_cache" / "CACHEDIR.TAG").write_text(_TAG, encoding="utf-8")
    _cargo_target(worktree / ".mypy_cache" / "target")
    # A folder named `target` that is no build folder is not carried.
    (worktree / "packages" / "target").mkdir(parents=True)
    _cargo_target(worktree / "crates" / "a" / "target")
    stash = tmp_path / "stash"
    code, out, _ = _run("out", "--worktree", str(worktree), "--stash", str(stash))
    assert code == 0
    assert out["carried"] == ["crates/a/target"]


def test_a_failed_move_leaves_the_folder_in_the_worktree(gate):
    _, worktree, stash = gate
    stash.parent.mkdir(parents=True)
    stash.mkdir()
    # A file where the stash needs a folder makes the move fail.
    (stash / "src-tauri").write_text("not a folder\n", encoding="utf-8")
    code, out, _ = _run("out", "--worktree", str(worktree), "--stash", str(stash))
    assert code == 1
    assert [f["path"] for f in out["failed"]] == ["src-tauri/target"]
    assert out["carried"] == ["target"]
    assert (worktree / "src-tauri" / "target" / "debug" / "deps" / "libapp.rlib").is_file()


@pytest.mark.parametrize("bad", ["../outside", ".", "/abs/target"])
def test_a_dir_outside_the_worktree_is_refused(tmp_path, bad):
    worktree = _worktree(tmp_path / "wt")
    code, out, err = _run("out", "--worktree", str(worktree), "--stash", str(tmp_path / "stash"), "--dir", bad)
    assert code == 2 and out is None
    assert "inside the worktree" in err


def test_a_stash_inside_the_worktree_is_refused(tmp_path):
    worktree = _worktree(tmp_path / "wt")
    code, out, err = _run("out", "--worktree", str(worktree), "--stash", str(worktree / "stash"))
    assert code == 2 and out is None
    assert "must not hold each other" in err


def test_a_missing_worktree_is_refused(tmp_path):
    code, out, err = _run("out", "--worktree", str(tmp_path / "gone"), "--stash", str(tmp_path / "stash"))
    assert code == 2 and out is None
    assert "not a folder" in err


_LOCKABLE = os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() != 0


@pytest.mark.skipif(not _LOCKABLE, reason="needs POSIX permissions and a user other than root")
@pytest.mark.parametrize("locked", ["criterion/bench", "llvm-cov-target"])
def test_a_run_result_that_cannot_be_deleted_keeps_the_folder_out_of_the_stash(tmp_path, locked):
    worktree = _worktree(tmp_path / "wt")
    _cargo_target(worktree / "target")
    folder = worktree / "target" / locked
    folder.mkdir(parents=True)
    (folder / ("demo-1.profraw" if locked == "llvm-cov-target" else "estimates.json")).write_text(
        "x\n", encoding="utf-8"
    )
    stash = tmp_path / "stash"
    os.chmod(folder, 0o555)
    try:
        code, out, _ = _run("out", "--worktree", str(worktree), "--stash", str(stash))
    finally:
        os.chmod(folder, 0o755)
    assert code == 1
    assert [f["path"] for f in out["failed"]] == ["target"]
    assert out["carried"] == []
    assert (worktree / "target" / "debug" / "deps" / "libdemo.rlib").is_file()
    assert not stash.exists() or not any(stash.iterdir())


def test_back_through_a_link_in_the_new_worktree_moves_nothing(tmp_path):
    worktree = _worktree(tmp_path / "wt")
    _cargo_target(worktree / "src-tauri" / "target")
    stash = tmp_path / "stash"
    code, out, _ = _run("out", "--worktree", str(worktree), "--stash", str(stash))
    assert code == 0 and out["carried"] == ["src-tauri/target"]
    _rebuild(worktree)
    shutil.rmtree(worktree / "src-tauri")
    main = tmp_path / "main" / "src-tauri"
    main.mkdir(parents=True)
    try:
        os.symlink(main, worktree / "src-tauri", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available here")
    code, back, _ = _run("back", "--worktree", str(worktree), "--stash", str(stash))
    assert code == 0
    assert back["carried"] == []
    assert back["skipped"] == [{"path": "src-tauri/target", "reason": "link"}]
    assert (stash / "src-tauri" / "target" / "debug" / "deps" / "libdemo.rlib").is_file()
    assert not (main / "target").exists()


def test_a_stash_that_is_a_file_is_refused(tmp_path):
    worktree = _worktree(tmp_path / "wt")
    stash = tmp_path / "stash"
    stash.write_text("not a folder\n", encoding="utf-8")
    for args in (("out", "--worktree", str(worktree)), ("back", "--worktree", str(worktree)), ("drop",)):
        code, out, err = _run(*args, "--stash", str(stash))
        assert code == 2 and out is None, args
        assert "not a folder" in err


def test_drop_deletes_every_folder_the_stash_holds(gate):
    _, worktree, stash = gate
    _run("out", "--worktree", str(worktree), "--stash", str(stash))
    code, out, err = _run("drop", "--stash", str(stash))
    assert code == 0, err
    assert out == {"mode": "drop", "carried": [], "cleared": ["src-tauri", "target"], "skipped": [], "failed": []}
    assert sorted(p.name for p in stash.iterdir()) == [".gitignore"]


def test_drop_never_deletes_through_a_link(tmp_path):
    stash = tmp_path / "stash"
    _cargo_target(stash / "target")
    elsewhere = tmp_path / "main"
    _cargo_target(elsewhere / "target")
    try:
        os.symlink(elsewhere / "target", stash / "linked", target_is_directory=True)
        os.symlink(elsewhere, stash / "target" / "debug" / "inner", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available here")
    code, out, _ = _run("drop", "--stash", str(stash))
    assert code == 0
    assert out["cleared"] == ["target"]
    assert out["skipped"] == [{"path": "linked", "reason": "link"}]
    # What the links point at is untouched.
    assert (elsewhere / "target" / "debug" / "deps" / "libdemo.rlib").is_file()
    assert not (stash / "target").exists()


def test_drop_with_no_stash_deletes_nothing(tmp_path):
    code, out, err = _run("drop", "--stash", str(tmp_path / "none"))
    assert code == 0, err
    assert out == {"mode": "drop", "carried": [], "cleared": [], "skipped": [], "failed": []}


def test_drop_takes_the_stash_alone_and_out_needs_a_worktree(tmp_path):
    worktree = _worktree(tmp_path / "wt")
    code, out, err = _run("drop", "--worktree", str(worktree), "--stash", str(tmp_path / "stash"))
    assert code == 2 and out is None and "--stash alone" in err
    code, out, err = _run("out", "--stash", str(tmp_path / "stash"))
    assert code == 2 and out is None and "needs --worktree" in err


def test_a_mode_is_required(tmp_path):
    worktree = _worktree(tmp_path / "wt")
    code, out, _ = _run("--worktree", str(worktree), "--stash", str(tmp_path / "stash"))
    assert code == 2 and out is None


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_stash_is_invisible_to_a_status_read_of_the_tree_that_holds_it(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    worktree = _worktree(tmp_path / "wt")
    _cargo_target(worktree / "target")
    scratch = repo / "_bmad-output" / "implementation-artifacts" / ".scratch-1-2"
    code, _, err = _run("out", "--worktree", str(worktree), "--stash", str(scratch / "gate-build"))
    assert code == 0, err
    (scratch / "sweep.sh").write_text("true\n", encoding="utf-8")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "sweep.sh" in status
    assert "gate-build" not in status
