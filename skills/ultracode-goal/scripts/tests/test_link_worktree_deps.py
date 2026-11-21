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
their folders for an offline install, linking nothing before it, and runs that
install itself with `--install`, only into the gate's own worktree: no
allowlist entry runs a package manager, since a rule would also let the
install run in the main tree.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "link_worktree_deps.py"


def _run(*args: str, env: dict | None = None) -> tuple[int, dict | None, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "cp1252", **(env or {})},
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
        "--project-root", str(main), "--worktree", str(worktree), "--install",
        "--impl-artifacts", str(worktree.parent), "--link-workspace",
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

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree))

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


# --- #253: `--install`, the one way the gate installs ---------------------------------
#
# A prefix allow rule such as `Bash(npm ci --offline:*)` also lets an unattended run aim the
# install at another folder, the main tree included, where `npm ci` empties and rebuilds
# `node_modules` and runs lifecycle scripts. So the script runs the install itself, only into
# the gate's own worktree, and these tests run it against a fake package manager on PATH.

_needs_git_and_posix = pytest.mark.skipif(
    os.name == "nt" or shutil.which("git") is None,
    reason="a real git worktree and a fake package manager that is a shebang script",
)

_FAKE_PM = """#!{python}
import json, os, sys
from pathlib import Path
with open(os.environ["EX_FAKE_PM_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({{"argv": [Path(sys.argv[0]).name, *sys.argv[1:]], "cwd": os.getcwd()}}) + "\\n")
if os.environ.get("EX_FAKE_PM_EXIT", "0") != "0":
    print("ex-fake: resolving", flush=True)
    print("error: --offline: ex-left is not in the cache", file=sys.stderr)
    print("npm error A complete log of this run can be found in: /ex/_logs/debug-0.log", file=sys.stderr)
    sys.exit(int(os.environ["EX_FAKE_PM_EXIT"]))
for rel in os.environ.get("EX_FAKE_PM_MAKES", "node_modules").split(","):
    (Path(sys.argv[-1]) / rel / "ex-installed").mkdir(parents=True, exist_ok=True)
"""

# The argument list `--install` runs for each lockfile, the folder appended.
_EXPECTED = {
    "package-lock.json": ["npm", "ci", "--offline", "--prefix"],
    "npm-shrinkwrap.json": ["npm", "ci", "--offline", "--prefix"],
    "bun.lock": ["bun", "install", "--frozen-lockfile", "--offline", "--cwd"],
    "bun.lockb": ["bun", "install", "--frozen-lockfile", "--offline", "--cwd"],
    "pnpm-lock.yaml": ["pnpm", "install", "--offline", "--frozen-lockfile", "--dir"],
}


def _git(repo: Path, *args: str) -> str:
    """git against a fixture repo, immune to the developer's own config."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
        capture_output=True,
        check=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
    )
    return proc.stdout.strip()


class Gate:
    """A workspace repo, its gate worktree, and a fake npm, bun and pnpm on PATH."""

    def __init__(self, tmp_path: Path, lockfiles: tuple[str, ...]) -> None:
        self.tmp = tmp_path
        self.main = tmp_path / "main"
        self.impl = self.main / "_bmad-output" / "implementation-artifacts"
        for rel in ("packages/sb-util/index.js", "apps/ex-web/index.js", "tools/ex-standalone/index.js"):
            (self.main / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.main / rel).write_text("module.exports = 1\n", encoding="utf-8")
        for lockfile in lockfiles:
            (self.main / lockfile).parent.mkdir(parents=True, exist_ok=True)
            (self.main / lockfile).write_text("{}\n", encoding="utf-8")
        (self.main / ".gitignore").write_text("node_modules\n_bmad-output\n", encoding="utf-8")
        _git(self.main, "init", "-q")
        _git(self.main, "add", "-A")
        _git(self.main, "-c", "user.email=ex@example.invalid", "-c", "user.name=ex", "commit", "-q", "-m", "ex")
        # The main tree's install: a workspace link in the root's folder, plain packages elsewhere.
        _package(self.main, "node_modules")
        _link(self.main, "node_modules/@ex/sb-util", "../../packages/sb-util")
        _package(self.main, "packages/sb-util/node_modules")
        _package(self.main, "tools/ex-standalone/node_modules")
        self.worktree = self.add_worktree(self.impl / ".gate-worktree-61-3")
        self.real = os.path.realpath(self.worktree)
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        for name in ("npm", "bun", "pnpm"):
            fake = self.bin / name
            fake.write_text(_FAKE_PM.format(python=sys.executable), encoding="utf-8")
            fake.chmod(0o755)
        self.log = tmp_path / "pm.log"
        self.env = {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"], "EX_FAKE_PM_LOG": str(self.log)}

    def add_worktree(self, path: Path) -> Path:
        _git(self.main, "worktree", "add", "-q", "--detach", str(path), "HEAD")
        return path

    def install(self, worktree: Path | None = None, **env: str) -> tuple[int, dict | None, str]:
        return _run(
            "--project-root", str(self.main), "--worktree", str(worktree or self.worktree),
            "--install", "--impl-artifacts", str(self.impl), env={**self.env, **env},
        )

    def calls(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def refused(self, worktree: Path | None = None) -> str:
        """Run `--install`, assert it refused before running or linking anything, and give its reason."""
        code, out, err = self.install(worktree)
        assert code == 3, (code, out, err)
        assert out["installs"] == [] and out["linked"] == [] and out["failed"] == []
        assert self.calls() == [], "a package manager ran"
        assert not os.path.lexists(self.worktree / "node_modules")
        return out["refused"]


@pytest.fixture
def gate(tmp_path: Path):
    def make(*lockfiles: str) -> Gate:
        return Gate(tmp_path, lockfiles or ("bun.lock",))

    return make


@_needs_git_and_posix
@pytest.mark.parametrize("lockfile", sorted(_EXPECTED))
def test_install_runs_the_lockfiles_offline_frozen_install_then_links_what_it_did_not_make(gate, lockfile) -> None:
    g = gate(lockfile)

    code, out, err = g.install(EX_FAKE_PM_MAKES="node_modules,packages/sb-util/node_modules")

    assert code == 0, err
    command = [*_EXPECTED[lockfile], g.real]
    assert out["installs"] == [{"lockfile": lockfile, "command": command, "exit": 0, "error": ""}]
    assert "refused" not in out
    assert g.calls() == [{"argv": command, "cwd": g.real}]
    # The install made the root's folder and sb-util's; the standalone tool's is linked whole.
    assert out["linked"] == ["tools/ex-standalone/node_modules"]
    assert out["skipped"] == [
        {"path": "node_modules", "reason": "exists"},
        {"path": "packages/sb-util/node_modules", "reason": "exists"},
    ]
    assert out["failed"] == []
    assert [entry["path"] for entry in out["workspace"]] == ["node_modules"]
    assert not (g.worktree / "node_modules").is_symlink()
    assert (g.worktree / "node_modules" / "ex-installed").is_dir()
    assert not (g.main / "node_modules" / "ex-installed").exists()
    assert os.path.realpath(g.worktree / "tools" / "ex-standalone" / "node_modules") == os.path.realpath(
        g.main / "tools" / "ex-standalone" / "node_modules"
    )


@_needs_git_and_posix
def test_install_runs_once_per_lockfile_in_its_own_folder_and_never_links_a_holder_it_did_not_make(gate) -> None:
    g = gate("package-lock.json", "apps/ex-web/bun.lock")
    _package(g.main, "apps/ex-web/node_modules")
    _link(g.main, "apps/ex-web/node_modules/@ex/sb-util", "../../../../packages/sb-util")
    _link(g.main, "node_modules/@ex/ex-web", "../../apps/ex-web")

    code, out, err = g.install(EX_FAKE_PM_MAKES="ex-made")

    assert code == 0, err
    assert [(entry["path"], entry["lockfiles"]) for entry in out["workspace"]] == [
        ("apps/ex-web/node_modules", ["apps/ex-web/bun.lock"]),
        ("node_modules", ["package-lock.json"]),
    ]
    assert [call["argv"] for call in g.calls()] == [
        [*_EXPECTED["bun.lock"], os.path.join(g.real, "apps", "ex-web")],
        [*_EXPECTED["package-lock.json"], g.real],
    ]
    assert [install["lockfile"] for install in out["installs"]] == ["apps/ex-web/bun.lock", "package-lock.json"]
    # The fake made neither holder: they stay unlinked, the others are linked whole.
    assert out["linked"] == ["packages/sb-util/node_modules", "tools/ex-standalone/node_modules"]
    assert {entry["path"]: entry["reason"] for entry in out["skipped"]} == {
        "apps/ex-web/node_modules": "workspace",
        "node_modules": "workspace",
    }
    assert not os.path.lexists(g.worktree / "node_modules")


@_needs_git_and_posix
def test_a_failed_install_links_nothing_and_reports_its_last_error_line(gate) -> None:
    g = gate("package-lock.json")

    code, out, err = g.install(EX_FAKE_PM_EXIT="1")

    assert code == 1, err
    assert out["installs"] == [
        {
            "lockfile": "package-lock.json",
            "command": [*_EXPECTED["package-lock.json"], g.real],
            "exit": 1,
            "error": "error: --offline: ex-left is not in the cache",
        }
    ]
    assert out["linked"] == [] and out["skipped"] == [] and out["failed"] == []
    assert [entry["path"] for entry in out["workspace"]] == ["node_modules"]
    for rel in ("node_modules", "packages/sb-util/node_modules", "tools/ex-standalone/node_modules"):
        assert not os.path.lexists(g.worktree / rel), rel


@_needs_git_and_posix
def test_a_package_manager_missing_from_path_fails_the_install(gate) -> None:
    g = gate("pnpm-lock.yaml")
    (g.bin / "pnpm").unlink()
    only_git = g.tmp / "only-git"
    only_git.mkdir()
    (only_git / "git").symlink_to(shutil.which("git"))

    code, out, err = g.install(PATH=f"{only_git}{os.pathsep}{g.bin}")

    assert code == 1, err
    assert out["installs"] == [
        {
            "lockfile": "pnpm-lock.yaml",
            "command": [*_EXPECTED["pnpm-lock.yaml"], g.real],
            "exit": None,
            "error": "pnpm is not on PATH",
        }
    ]
    assert out["linked"] == []


@_needs_git_and_posix
def test_install_refuses_the_main_tree(gate) -> None:
    g = gate()

    assert "main tree" in g.refused(g.main)
    assert not (g.main / "node_modules" / "ex-installed").exists()


@_needs_git_and_posix
@pytest.mark.parametrize("where", ["outside the artifacts folder", "another name in it"])
def test_install_refuses_a_worktree_where_the_gate_does_not_build_one(gate, where) -> None:
    g = gate()
    if where == "outside the artifacts folder":
        path = g.add_worktree(g.tmp / "ex-elsewhere" / ".gate-worktree-61-3")
    else:
        path = g.add_worktree(g.impl / "ex-agent-61-3")

    assert "where the gate builds it" in g.refused(path)
    assert not os.path.lexists(path / "node_modules")


@_needs_git_and_posix
def test_install_refuses_a_folder_that_is_not_a_worktree_of_the_project(gate) -> None:
    g = gate()
    path = g.impl / ".gate-worktree-61-4"
    path.mkdir()
    (path / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    (path / "bun.lock").write_text("{}\n", encoding="utf-8")

    assert "not one `git worktree list` gives" in g.refused(path)
    assert not os.path.lexists(path / "node_modules")


@_needs_git_and_posix
def test_install_refuses_a_lockfile_folder_that_escapes_the_worktree_by_a_link(gate) -> None:
    g = gate("apps/ex-web/bun.lock")
    _package(g.main, "apps/ex-web/node_modules")
    _link(g.main, "apps/ex-web/node_modules/@ex/sb-util", "../../../../packages/sb-util")
    shutil.rmtree(g.worktree / "apps" / "ex-web")
    _link(g.worktree, "apps/ex-web", str(g.main / "apps" / "ex-web"))

    reason = g.refused()

    assert "`apps/ex-web/bun.lock`'s folder resolves outside the worktree" in reason
    assert not (g.main / "apps" / "ex-web" / "node_modules" / "ex-installed").exists()


@_needs_git_and_posix
def test_install_refuses_a_dependency_folder_linked_into_the_main_tree(gate) -> None:
    g = gate()
    _link(g.worktree, "packages/sb-util/node_modules", str(g.main / "packages" / "sb-util" / "node_modules"))

    reason = g.refused()

    assert "`packages/sb-util/node_modules`" in reason and "resolves outside the worktree" in reason


@_needs_git_and_posix
@pytest.mark.parametrize(
    "lockfiles",
    [("yarn.lock",), ("bun.lock", "bun.lockb"), ("package-lock.json", "pnpm-lock.yaml"), ()],
    ids=["yarn", "both of bun's", "npm's and pnpm's", "none"],
)
def test_install_refuses_any_other_lockfile_shape(gate, lockfiles) -> None:
    g = gate("ex-placeholder.txt")
    for name in lockfiles:
        (g.worktree / name).write_text("{}\n", encoding="utf-8")

    reason = g.refused()

    assert "`node_modules` holds a workspace link and its lockfiles are " in reason
    assert f"are {', '.join(sorted(lockfiles)) or 'none'}:" in reason
    assert "runs only for exactly one of" in reason


def test_install_needs_the_artifacts_folder(workspace) -> None:
    main, worktree = workspace

    code, out, err = _run("--project-root", str(main), "--worktree", str(worktree), "--install")

    assert code == 2
    assert out is None
    assert "--install needs --impl-artifacts" in err
