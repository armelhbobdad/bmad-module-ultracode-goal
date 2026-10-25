#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""link_worktree_deps.py: the gate's dependency links, made without `ln`.

#160 item 4: the gate linked `node_modules` into its measurement worktree with
`ln -s`, which neither `acceptEdits` nor the run's allowlist lets through, so
an unattended gate could have it refused. The script runs under `uv run`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "link_worktree_deps.py"


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


def _package(root: Path, rel: str) -> None:
    """A dependency folder holding one installed package."""
    pkg = root / rel / "left-pad"
    pkg.mkdir(parents=True)
    (pkg / "index.js").write_text("module.exports = 1\n", encoding="utf-8")


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path]:
    """A monorepo main tree and a worktree of a commit that lacks packages/b."""
    main = tmp_path / "main"
    _package(main, "node_modules")
    _package(main, "node_modules/left-pad/node_modules")  # nested inside: carried by the outer link
    _package(main, "packages/a/node_modules")
    _package(main, "packages/b/node_modules")
    (main / ".git").mkdir()
    _package(main, ".git/node_modules")
    worktree = main / "_bmad-output" / "implementation-artifacts" / ".gate-worktree-1-2"
    (worktree / "packages" / "a").mkdir(parents=True)
    stale = main / "_bmad-output" / "implementation-artifacts" / ".gate-worktree-1-1"
    _package(stale, "node_modules")
    _package(main, ".venv/lib/node_modules")
    (main / ".venv" / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    agent = main / ".claude" / "worktrees" / "agent-1"
    _package(agent, "node_modules")
    (agent / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    nested = main / "vendor" / "sub-repo"
    _package(nested, "node_modules")
    (nested / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    _package(main, "rust/target/debug/node_modules")
    (main / "rust" / "target" / "CACHEDIR.TAG").write_text(
        "Signature: 8a477f597d28d172789f06886806bc55\n", encoding="utf-8"
    )
    # Walked: a JavaScript action under a dot-folder, a package named `target`.
    _package(main, ".github/actions/deploy/node_modules")
    _package(main, "packages/target/node_modules")
    (worktree / ".github" / "actions" / "deploy").mkdir(parents=True)
    (worktree / "packages" / "target").mkdir(parents=True)
    return main, worktree


def test_every_outermost_node_modules_is_linked_and_resolves(trees) -> None:
    main, worktree = trees

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))

    assert code == 0, err
    assert out["linked"] == [
        ".github/actions/deploy/node_modules",
        "node_modules",
        "packages/a/node_modules",
        "packages/target/node_modules",
    ]
    assert out["skipped"] == [{"path": "packages/b/node_modules", "reason": "parent-missing"}]
    assert out["failed"] == []
    for rel in out["linked"]:
        assert (worktree / rel / "left-pad" / "index.js").read_text(encoding="utf-8") == (
            "module.exports = 1\n"
        )
        assert os.path.realpath(worktree / rel) == os.path.realpath(main / rel)
    assert not (main / "packages" / "b" / "node_modules").is_symlink()


def test_a_second_run_skips_the_links_it_made(trees) -> None:
    main, worktree = trees
    _run("--project-root", str(main), "--worktree", str(worktree))

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))

    assert code == 0, err
    assert out["linked"] == []
    assert {"path": "node_modules", "reason": "exists"} in out["skipped"]


def test_dir_names_the_folders_to_link_instead(trees) -> None:
    main, worktree = trees
    _package(main, "vendor")

    code, out, err = _run(
        "--project-root", str(main), "--worktree", str(worktree), "--dir", "vendor"
    )

    assert code == 0, err
    assert out == {"linked": ["vendor"], "skipped": [], "failed": []}
    assert (worktree / "vendor" / "left-pad" / "index.js").is_file()


@pytest.mark.parametrize("bad", ["../outside", ".", "/abs/vendor"])
def test_a_dir_outside_the_project_root_is_refused(trees, bad: str) -> None:
    main, worktree = trees

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree), "--dir", bad)

    assert code == 2
    assert out is None
    assert "inside the project root" in err
    assert not os.path.lexists(worktree / "node_modules")


def test_a_missing_worktree_is_refused(tmp_path: Path) -> None:
    main = tmp_path / "main"
    main.mkdir()

    code, out, err = _run("--project-root", str(main), "--worktree", str(tmp_path / "gone"))

    assert code == 2
    assert out is None
    assert "worktree is not a folder" in err
