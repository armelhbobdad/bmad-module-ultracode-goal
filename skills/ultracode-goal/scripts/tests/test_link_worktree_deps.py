#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""link_worktree_deps.py: the gate's dependency links, made without `ln`.

#160 item 4: the gate linked `node_modules` into its measurement worktree with
`ln -s`, which neither `acceptEdits` nor the run's allowlist lets through, so
an unattended gate could have it refused. The script runs under `uv run`.

#253: in a workspace monorepo the package manager writes each of the repo's
own packages into those folders as a relative link, and through a folder linked
whole that link resolves to the main tree's package, so a cross-package
mutation in the worktree read GREEN. The script now finds such links and leaves
their folders for an offline install, linking nothing before it.
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
    (worktree / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    stale = main / "_bmad-output" / "implementation-artifacts" / ".gate-worktree-1-1"
    _package(stale, "node_modules")
    (stale / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
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
    assert out == {"linked": ["vendor"], "skipped": [], "failed": [], "workspace": []}
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


# --- #253: workspace links --------------------------------------------------------


def _link(root: Path, rel: str, target: str) -> None:
    """A link at root/rel with the target text given, relative as a package manager writes one."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target.replace("/", os.sep), path, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available here")


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path]:
    """A workspace main tree (packages/sb-util, apps/ex-web, a lockfile) and a worktree of it."""
    main = tmp_path / "main"
    worktree = main / "_bmad-output" / "implementation-artifacts" / ".gate-worktree-61-3"
    for tree in (main, worktree):
        (tree / "packages" / "sb-util").mkdir(parents=True)
        (tree / "packages" / "sb-util" / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
        (tree / "apps" / "ex-web").mkdir(parents=True)
        (tree / "bun.lock").write_text("{}\n", encoding="utf-8")
    (worktree / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    _package(main, "node_modules")
    _package(main, "packages/sb-util/node_modules")
    return main, worktree


# Where each package manager writes a workspace link, and the link it writes:
# (the folder that holds it, the link, its target).
_LAYOUTS = {
    "top level": ("node_modules", "node_modules/sb-util", "../packages/sb-util"),
    "@scope": ("node_modules", "node_modules/@ex/sb-util", "../../packages/sb-util"),
    "bun store peer": (
        "node_modules",
        "node_modules/.bun/ex-plugin@1.0.0+abc/node_modules/@ex/sb-util",
        "../../../../../packages/sb-util",
    ),
    "bun store hoist": ("node_modules", "node_modules/.bun/node_modules/@ex/sb-util", "../../../../packages/sb-util"),
    "pnpm store peer": (
        "node_modules",
        "node_modules/.pnpm/ex-plugin@1.0.0_@ex+sb-util@packages+sb-util/node_modules/@ex/sb-util",
        "../../../../../packages/sb-util",
    ),
    "pnpm store hoist": (
        "node_modules", "node_modules/.pnpm/node_modules/@ex/sb-util", "../../../../packages/sb-util"
    ),
    "nested app folder": (
        "apps/ex-web/node_modules", "apps/ex-web/node_modules/@ex/sb-util", "../../../../packages/sb-util"
    ),
}


@pytest.mark.parametrize("layout", sorted(_LAYOUTS))
def test_a_folder_holding_a_workspace_link_is_left_for_the_install(workspace, layout: str) -> None:
    main, worktree = workspace
    holder, link, target = _LAYOUTS[layout]
    _link(main, link, target)
    assert os.path.realpath(main / link) == os.path.realpath(main / "packages" / "sb-util")

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))

    assert code == 0, err
    assert out["linked"] == []
    assert out["failed"] == []
    held_back = {"node_modules", "packages/sb-util/node_modules"} - {holder}
    assert {entry["path"]: entry["reason"] for entry in out["skipped"]} == {
        holder: "workspace",
        **{rel: "install-first" for rel in held_back},
    }
    assert out["workspace"] == [
        {"path": holder, "lockfiles": ["bun.lock"], "links": [{"path": link, "to": "packages/sb-util"}]}
    ]
    for entry in out["skipped"]:
        assert not os.path.lexists(worktree / entry["path"]), entry


def test_links_into_node_modules_or_out_of_the_root_are_not_workspace_links(workspace, tmp_path) -> None:
    """bun's and pnpm's links into their own store, and a link to a folder
    outside the project, resolve the same from either tree: the folder is
    linked whole, as before."""
    main, worktree = workspace
    _package(main, "node_modules/.bun/ex-left@1.0.0/node_modules")
    _link(main, "packages/sb-util/node_modules/ex-left", "../../../node_modules/.bun/ex-left@1.0.0/node_modules/left-pad")
    _link(main, "node_modules/ex-left", ".bun/ex-left@1.0.0/node_modules/left-pad")
    (tmp_path / "ex-outside").mkdir()
    _link(main, "node_modules/ex-outside", str(tmp_path / "ex-outside"))

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))

    assert code == 0, err
    assert out == {
        "linked": ["node_modules", "packages/sb-util/node_modules"],
        "skipped": [],
        "failed": [],
        "workspace": [],
    }
    for rel in out["linked"]:
        assert os.path.realpath(worktree / rel) == os.path.realpath(main / rel)


def test_installed_links_only_the_folders_the_install_did_not_make(workspace) -> None:
    main, worktree = workspace
    _link(main, "node_modules/@ex/sb-util", "../../packages/sb-util")
    _package(main, "apps/ex-web/node_modules")
    _link(main, "apps/ex-web/node_modules/@ex/sb-util", "../../../../packages/sb-util")
    _package(main, "tools/ex-standalone/node_modules")
    (worktree / "tools" / "ex-standalone").mkdir(parents=True)
    # The install made the root's folder and sb-util's, and none for the app.
    (worktree / "node_modules").mkdir()
    (worktree / "packages" / "sb-util" / "node_modules").mkdir()

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree), "--installed")

    assert code == 0, err
    assert out["linked"] == ["tools/ex-standalone/node_modules"]
    assert out["skipped"] == [
        {"path": "apps/ex-web/node_modules", "reason": "workspace"},
        {"path": "node_modules", "reason": "exists"},
        {"path": "packages/sb-util/node_modules", "reason": "exists"},
    ]
    assert out["failed"] == []
    assert [entry["path"] for entry in out["workspace"]] == ["apps/ex-web/node_modules", "node_modules"]
    assert not os.path.lexists(worktree / "apps" / "ex-web" / "node_modules")
    assert not (worktree / "node_modules").is_symlink()
    assert os.path.realpath(worktree / "tools" / "ex-standalone" / "node_modules") == os.path.realpath(
        main / "tools" / "ex-standalone" / "node_modules"
    )


def test_link_workspace_links_every_folder_whole_and_still_names_them(workspace) -> None:
    """The fallback when no offline install can serve: the folders are linked
    as before, and `workspace` still names what the worktree now reads from
    the main tree."""
    main, worktree = workspace
    _link(main, "node_modules/@ex/sb-util", "../../packages/sb-util")

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree), "--link-workspace")

    assert code == 0, err
    assert out["linked"] == ["node_modules", "packages/sb-util/node_modules"]
    assert out["skipped"] == [] and out["failed"] == []
    assert out["workspace"] == [
        {
            "path": "node_modules",
            "lockfiles": ["bun.lock"],
            "links": [{"path": "node_modules/@ex/sb-util", "to": "packages/sb-util"}],
        }
    ]
    assert os.path.realpath(worktree / "node_modules" / "@ex" / "sb-util") == os.path.realpath(
        main / "packages" / "sb-util"
    )


def test_the_two_modes_exclude_each_other(workspace) -> None:
    main, worktree = workspace

    code, out, err = _run(
        "--project-root", str(main), "--worktree", str(worktree), "--installed", "--link-workspace"
    )

    assert code == 2
    assert out is None
    assert "not allowed with argument" in err


def test_a_folder_the_worktree_already_links_fails_before_an_install(workspace) -> None:
    """An install writes through a linked folder into the main tree (npm's
    removed the main tree's package through one), so a link already there,
    from a gate that linked before this check, is a failure to fix first."""
    main, worktree = workspace
    _link(main, "node_modules/@ex/sb-util", "../../packages/sb-util")
    _link(worktree, "packages/sb-util/node_modules", str(main / "packages" / "sb-util" / "node_modules"))

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))

    assert code == 1, err
    assert [entry["path"] for entry in out["failed"]] == ["packages/sb-util/node_modules"]
    assert "write through it into the main tree" in out["failed"][0]["error"]
    assert out["linked"] == []


def test_a_holder_the_commit_lacks_holds_nothing_back(workspace) -> None:
    """A folder whose package the commit does not have gets no install, so
    it neither appears under `workspace` nor holds the others back."""
    main, worktree = workspace
    _package(main, "apps/ex-old/node_modules")
    _link(main, "apps/ex-old/node_modules/@ex/sb-util", "../../../../packages/sb-util")

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))

    assert code == 0, err
    assert out["workspace"] == []
    assert out["linked"] == ["node_modules", "packages/sb-util/node_modules"]
    assert out["skipped"] == [{"path": "apps/ex-old/node_modules", "reason": "parent-missing"}]


def test_a_named_folder_may_link_into_itself(workspace) -> None:
    """A `--dir` folder's own links (a `bin` link to a package it holds)
    resolve inside it, not to the repo's own packages."""
    main, worktree = workspace
    _package(main, "vendor")
    _link(main, "vendor/bin-link", "left-pad")

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree), "--dir", "vendor")

    assert code == 0, err
    assert out == {"linked": ["vendor"], "skipped": [], "failed": [], "workspace": []}


def test_the_lockfiles_are_read_from_the_nearest_folder_of_the_worktree(workspace) -> None:
    main, worktree = workspace
    (worktree / "bun.lock").unlink()
    (worktree / "package-lock.json").write_text("{}\n", encoding="utf-8")
    (worktree / "pnpm-lock.yaml").write_text("{}\n", encoding="utf-8")
    _package(main, "apps/ex-web/node_modules")
    _link(main, "apps/ex-web/node_modules/@ex/sb-util", "../../../../packages/sb-util")

    def lockfiles() -> list[str]:
        code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))
        assert code == 0, err
        assert [entry["path"] for entry in out["workspace"]] == ["apps/ex-web/node_modules"]
        return out["workspace"][0]["lockfiles"]

    assert lockfiles() == ["package-lock.json", "pnpm-lock.yaml"]
    (worktree / "apps" / "ex-web" / "bun.lock").write_text("{}\n", encoding="utf-8")
    assert lockfiles() == ["apps/ex-web/bun.lock"]
    for lockfile in ("package-lock.json", "pnpm-lock.yaml", "apps/ex-web/bun.lock"):
        (worktree / lockfile).unlink()
    assert lockfiles() == []


@pytest.mark.parametrize(
    "present, listed",
    [
        *[((name,), [name]) for name in (
            "package-lock.json", "npm-shrinkwrap.json", "bun.lock", "bun.lockb", "pnpm-lock.yaml", "yarn.lock"
        )],
        # Two lockfiles: the gate installs for neither, and needs to see both.
        (("bun.lockb", "bun.lock"), ["bun.lock", "bun.lockb"]),
        (("yarn.lock", "package-lock.json"), ["package-lock.json", "yarn.lock"]),
    ],
)
def test_every_lockfile_name_is_reported(workspace, present: tuple[str, ...], listed: list[str]) -> None:
    main, worktree = workspace
    (worktree / "bun.lock").unlink()
    for name in present:
        (worktree / name).write_text("{}\n", encoding="utf-8")
    _link(main, "node_modules/@ex/sb-util", "../../packages/sb-util")

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))

    assert code == 0, err
    assert out["workspace"][0]["lockfiles"] == listed


def test_a_link_that_reaches_a_package_through_another_link_counts(workspace) -> None:
    """The scan follows a chain of links to its end, as Node does."""
    main, worktree = workspace
    _link(main, "node_modules/@ex/sb-util", "../../packages/sb-util")
    _link(main, "apps/ex-web/node_modules/@ex/sb-util", "../../../../node_modules/@ex/sb-util")

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree), "--installed")

    assert code == 0, err
    assert {entry["path"]: entry["links"] for entry in out["workspace"]} == {
        "apps/ex-web/node_modules": [{"path": "apps/ex-web/node_modules/@ex/sb-util", "to": "packages/sb-util"}],
        "node_modules": [{"path": "node_modules/@ex/sb-util", "to": "packages/sb-util"}],
    }
    assert not os.path.lexists(worktree / "apps" / "ex-web" / "node_modules")


def test_a_link_loop_ends_the_scan_with_output(workspace) -> None:
    main, worktree = workspace
    _link(main, "node_modules/ex-loop-a", "ex-loop-b")
    _link(main, "node_modules/ex-loop-b", "ex-loop-a")

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))

    assert code == 0, err
    assert out["workspace"] == []
    assert out["linked"] == ["node_modules", "packages/sb-util/node_modules"]


def test_a_link_to_the_root_package_counts(workspace) -> None:
    """An app that depends on the root package gets a link to the project root itself."""
    main, worktree = workspace
    _link(main, "node_modules/ex-root", "..")

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))

    assert code == 0, err
    assert out["workspace"] == [
        {"path": "node_modules", "lockfiles": ["bun.lock"], "links": [{"path": "node_modules/ex-root", "to": "."}]}
    ]
    assert out["linked"] == []


def test_a_named_folder_that_is_itself_a_link_reads_its_own_links_as_its_own(workspace) -> None:
    """`vendor` links to a folder beside it: a link inside it that stays inside
    that folder resolves through the real path, and is still the folder's own."""
    main, worktree = workspace
    _package(main, ".vendor-real")
    _link(main, ".vendor-real/bin-link", "left-pad")
    _link(main, "vendor", ".vendor-real")

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree), "--dir", "vendor")

    assert code == 0, err
    assert out == {"linked": ["vendor"], "skipped": [], "failed": [], "workspace": []}


@pytest.mark.skipif(os.name != "nt", reason="junctions are a Windows link")
def test_a_junction_is_a_workspace_link_on_every_python(workspace) -> None:
    """npm and pnpm write a Windows workspace link as a junction, which
    `os.path.islink` does not report and Python 3.11 has no `isjunction` for."""
    import _winapi  # noqa: PLC0415  (Windows only)

    main, worktree = workspace
    (main / "node_modules" / "@ex").mkdir()
    _winapi.CreateJunction(str(main / "packages" / "sb-util"), str(main / "node_modules" / "@ex" / "sb-util"))
    _winapi.CreateJunction(
        str(main / "packages" / "sb-util" / "node_modules"), str(worktree / "packages" / "sb-util" / "node_modules")
    )

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))

    assert code == 1, err
    assert out["workspace"] == [
        {
            "path": "node_modules",
            "lockfiles": ["bun.lock"],
            "links": [{"path": "node_modules/@ex/sb-util", "to": "packages/sb-util"}],
        }
    ]
    assert [entry["path"] for entry in out["failed"]] == ["packages/sb-util/node_modules"]
