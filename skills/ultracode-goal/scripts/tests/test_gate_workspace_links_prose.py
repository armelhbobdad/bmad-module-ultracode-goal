#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""gate.md: a dependency folder that holds a workspace link gets an offline install (#253).

In a workspace monorepo the gate linked each dependency folder whole into its
worktree, and the package manager's relative links to the repo's own packages
inside it resolved to the main tree's copy, so a cross-package mutation read
GREEN in the worktree. Measured with bun 1.4.2, npm 11.19.0 and pnpm 12.21.0:
the offline install of the lockfile's package manager makes every row commit
true, a peer's included, while an install run over a linked folder writes
through it into the main tree. The gate runs that install only through
`link_worktree_deps.py --install`, never as a command of its own: an allow
rule for one would match it by its start, in any folder, the main tree
included. These pins hold the procedure, its failure path and the places it is
recorded.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_GATE = _SKILL_ROOT / "references" / "gate.md"
_SCRIPT = _SKILL_ROOT / "scripts" / "link_worktree_deps.py"
_FRAGMENT = _REPO / "changes" / "gate-worktree-workspace-install.yaml"

_CAVEAT_HEAD = "- **Dependency directories do not follow the commit.**"
_CANNOT_RUN_HEAD = "- A row cannot run when it reads"
_REBUILD_HEAD = "**Rebuild the worktree once automate has finished (production).**"
_HONESTY_HEAD = "Record in `.decision-log.md`, once per gated story"

_SUCH_A_CASE = (
    "Where a symlink cannot serve, an offline install from the package manager's shared store is the fallback, "
    "and a dependency folder that holds a workspace link is such a case."
)
_WHY = "through a folder linked whole such a link resolves to the MAIN tree's package"
_PEER = "bun and pnpm also write a registry package's peer on one of them inside their store"
_LINKS_NOTHING = "and then links no folder at all, skipping each other one as `install-first`"
_WRITES_THROUGH = "an install run over a linked folder writes through the link into the main tree"
_ALREADY_LINKED = (
    "For the same reason it fails, with exit 1, a folder the worktree already holds as a link: replace the "
    "worktree the way the rebuild below does and run the call again."
)
_CONFIG_FIRST = (
    "When it lists one, copy in any package-manager config the install reads that the commit does not carry (an "
    "untracked `.npmrc` or `bunfig.toml`, under the next caveat)"
)
_INSTALL_CALL = (
    "give the worktree an offline install with the same `link_worktree_deps.py` call and `--install "
    "--impl-artifacts {workflow.implementation_artifacts}` added, never with an install command of your own"
)
_NO_RULE = (
    "no allowlist entry covers one, since a rule matches a command by its start and would let the same install run "
    "in any folder, the main tree included"
)
_OFFLINE_FROZEN = (
    "The call runs, once per lockfile and in the worktree's copy of the lockfile's folder, the offline, "
    "frozen-lockfile install of the package manager the lockfile names"
)
_INSTALLS = (
    "npm's for `package-lock.json` or `npm-shrinkwrap.json`",
    "bun's for `bun.lock` or `bun.lockb`",
    "pnpm's for `pnpm-lock.yaml`",
)
_INSTALLED = "then links whole each folder the install did not make, never one that holds a workspace link"
_REPORTS = "prints each install's `command`, `exit` and last `error` line under `installs`"
_REFUSES = (
    "It refuses, with exit 3 and its reason under `refused`, any worktree but `<tmp-path>` (one `git worktree list` "
    "gives for the project root, not the main tree, at "
    "`{workflow.implementation_artifacts}/.gate-worktree-<story_id>`), a lockfile's folder or a dependency folder "
    "that resolves outside it, and a folder whose `lockfiles` is not exactly one of those five."
)
_SCRIPTS_RUN = "The install runs the packages' lifecycle scripts, as the main tree's install did"
_BUILT_HERE = (
    "is built in the worktree with the project's own build command before any run reads it, and never copied "
    "from the main tree"
)
_NEXT_CAVEAT = "the untracked inputs the next caveat copies in are the ones no build of the commit's source produces"
_DOWNLOADS = (
    "`--offline` keeps the package manager off the network, not a lifecycle script: one that downloads (a browser "
    "binary, say) uses its own cache or fails, and a failed install takes the path below."
)
_FAILS = (
    "When the `--install` call exits non-zero (it refused, or an install failed: a cache that lacks a package the "
    "lockfile pins, or a lockfile the offline install refuses) or is itself refused (a permission or sandbox denial)"
)
_NEVER_ONLINE = (
    "never install online: log the reason it printed (its `refused` line, or the failed install's `command` and "
    "`error`) in `.decision-log.md`"
)
_REPLACE = "replace the worktree the way the rebuild below does (carry its build folders out, remove it, add it again"
_LINK_WORKSPACE = "run the same call with `--link-workspace` added"
_UNMEASURABLE = (
    "so a mutation row whose mutated file lies in one of those packages, under a command that reaches that package "
    "by its name (another package's tests, or its own tests that import it by its name rather than by a relative "
    "path), cannot run"
)
_NO_SUCH_ROW = "tell automate to write no such row"
_ASSESSORS = "so it reports that run as unmeasured"
_OTHER_FOLDERS = "For any other folder a symlink may not serve, measure both once per repo before committing to one."
_ROW_RULE = (
    "A row whose mutated file lies in a workspace package that the worktree reads from the main tree, because its "
    "offline install could not serve, and whose command reaches that package by its name (another package's tests, "
    "or its own that import it by name), reads the same way"
)
_REBUILD = (
    "exactly as the first setup did: the same `--install` call when the call lists a `workspace` folder, or, when "
    "the first setup's install could not serve, the `--link-workspace` call with no second try at the install."
)
_HONESTY = (
    "It also names each folder `link_worktree_deps.py` listed under `workspace` and the offline install the "
    "worktree got for them, and, when no install could serve, the call's refusal or the install that failed and its "
    "last error line, "
    "each package the worktree then read from the main tree, and each mutation row and assessor run that left "
    "unmeasured."
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _line(text: str, head: str) -> str:
    """The one physical line that starts with head (each of these paragraphs is one line)."""
    return next((line for line in text.splitlines() if line.startswith(head)), "")


def _procedure_holds(text: str) -> bool:
    """The caveat says when a symlink cannot serve, what the script does, the `--install` call that
    runs the install and what it refuses, then the failure path, in that order."""
    caveat = _flat(_line(text, _CAVEAT_HEAD))
    steps = (
        _SUCH_A_CASE,
        _WHY,
        _LINKS_NOTHING,
        _WRITES_THROUGH,
        _ALREADY_LINKED,
        _CONFIG_FIRST,
        _INSTALL_CALL,
        _NO_RULE,
        _OFFLINE_FROZEN,
        *_INSTALLS,
        _INSTALLED,
        _REPORTS,
        _REFUSES,
        _SCRIPTS_RUN,
        _DOWNLOADS,
        _BUILT_HERE,
        _FAILS,
        _NEVER_ONLINE,
        _REPLACE,
        _LINK_WORKSPACE,
        _UNMEASURABLE,
        _NO_SUCH_ROW,
        _ASSESSORS,
        _OTHER_FOLDERS,
    )
    if not all(step in caveat for step in steps):
        return False
    indices = [caveat.index(step) for step in steps]
    return indices == sorted(indices) and _PEER in caveat and _NEXT_CAVEAT in caveat


def test_the_caveat_gives_the_install_and_its_failure_path_in_order():
    assert _procedure_holds(_read(_GATE))


@pytest.mark.parametrize(
    "old, new",
    [
        # The install named but run after the links, which writes through them.
        (_LINKS_NOTHING, "and then links every other folder whole"),
        # An online fallback, which the gate never takes.
        (_NEVER_ONLINE, "install online instead"),
        # A failed install that measures the main tree silently.
        (_UNMEASURABLE, "so every row still runs"),
        # The lifecycle scripts skipped, which leaves a built entry point missing.
        (_SCRIPTS_RUN, "The install runs with `--ignore-scripts`"),
        # A build output copied in from the main tree.
        (_BUILT_HERE, "is copied in from the main tree"),
        # One of the three measured installs dropped.
        (_INSTALLS[1], "bun's for `bun.lockb`"),
        # The links after the install left out, so the folders the install did not make stay missing.
        (_INSTALLED, "then stops"),
        # The install handed back to the conductor as a raw command, which an allow rule would let run anywhere.
        (_INSTALL_CALL, "give the worktree an offline install with `npm ci --offline --prefix <tmp-path>`"),
        # The refusals dropped, so a call aimed at the main tree would install there.
        (_REFUSES, "It installs into whatever worktree it is given."),
        # A refused call, which exits with no code, left with no next step.
        (" or is itself refused (a permission or sandbox denial)", ""),
        # The rule narrowed back to another package's tests: a package's own tests that import it by name
        # read the main tree's copy through the root link, unflagged.
        (_UNMEASURABLE, "so a mutation row whose mutated file lies in one of those packages, under a command that "
                        "runs another package's tests, cannot run"),
        # The untracked package-manager config copied in after the install, which lays the folders out without it.
        (_CONFIG_FIRST, "before copying anything in"),
    ],
)
def test_each_step_is_load_bearing(old, new):
    live = _read(_GATE)
    mutant = live.replace(old, new, 1)
    assert mutant != live
    assert not _procedure_holds(mutant)


def test_the_unmeasurable_row_reads_as_one_that_cannot_run():
    bullet = _flat(_line(_read(_GATE), _CANNOT_RUN_HEAD))
    assert _ROW_RULE in bullet
    assert "(\"Dependency directories do not follow the commit\", under \"Measure the commit, not the working tree\")" in (
        bullet[bullet.index(_ROW_RULE):]
    )
    # It follows the reused server's rule, which "the same way" points back to.
    assert bullet.index("A row whose command runs through a server the gate set reuses") < bullet.index(_ROW_RULE)


def test_the_rebuild_repeats_the_install_or_the_fallback():
    rebuild = _flat(_line(_read(_GATE), _REBUILD_HEAD))
    assert _REBUILD in rebuild
    assert rebuild.index("then link the dependency folders with the same `link_worktree_deps.py` call") < (
        rebuild.index(_REBUILD)
    )


def test_the_honesty_line_names_the_workspace_folders_and_what_went_unmeasured():
    assert _HONESTY in _flat(_line(_read(_GATE), _HONESTY_HEAD))


def test_the_caveats_stay_four_and_the_new_prose_holds_no_em_dash():
    live = _read(_GATE)
    assert "Four caveats the setup owes" in live
    section = live[live.index("## Measure the commit, not the working tree") :]
    section = section[: section.index("\n**Rebuild the worktree")]
    assert len(re.findall(r"^- \*\*", section, re.MULTILINE)) == 4
    for head in (_CAVEAT_HEAD, _CANNOT_RUN_HEAD, _REBUILD_HEAD, _HONESTY_HEAD):
        assert chr(0x2014) not in _line(live, head), head
    # No command the new prose gives leads with an environment variable.
    assert not re.search(r"`[A-Z_]+=\S+ ", _line(live, _CAVEAT_HEAD))


def test_every_flag_the_prose_names_is_the_scripts_own():
    usage = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout
    caveat = _line(_read(_GATE), _CAVEAT_HEAD)
    # Every flag of the script's call, and of a code span that is flags alone, but a package
    # manager's `--offline`, is one of this script's.
    spans = [
        span for span in re.findall(r"`([^`]+)`", caveat) if span.startswith("--") or "link_worktree_deps.py" in span
    ]
    flags = {flag for span in spans for flag in re.findall(r"(?:^|\s)(--[a-z-]+)", span)} - {"--offline"}
    assert {"--install", "--impl-artifacts", "--link-workspace", "--dir"} <= flags
    for flag in flags:
        assert re.search(rf"{re.escape(flag)}\b(?!-)", usage), flag
    script = _read(_SCRIPT)
    for word in ("`workspace`", "`install-first`", "`installs`", "`refused`", "exit 3"):
        assert word in script, word


def test_the_prose_names_no_install_for_the_conductor_to_run():
    """The script runs the install; a code span that gives one would hand it back to the
    conductor, which no allow rule should let run unasked."""
    install = re.compile(r"^(?:npm (?:ci|install|i|clean-install)|bun (?:install|i)|pnpm (?:install|i)|yarn)\b")
    for path in (_SKILL_ROOT / "references").glob("*.md"):
        for span in re.findall(r"`([^`]+)`", _read(path)):
            assert not install.match(span.strip()), (path.name, span)


def test_the_fragment_says_what_the_prose_does():
    fragment = _read(_FRAGMENT)
    assert "type: changed" in fragment and "scope: ultracode-goal" in fragment and "issues: [253]" in fragment
    for word in ("`workspace`", "`--install --impl-artifacts <path>`", "`installs`", "`--link-workspace`",
                 "`.decision-log.md`", "exit 3"):
        assert word in fragment, word
    assert "--installed" not in fragment
    assert "the default `allowlist_commands` is unchanged and no allow rule runs a package manager" in _flat(fragment)
    assert "reaches the mutated file's workspace package by its name" in _flat(fragment)
    assert chr(0x2014) not in fragment
