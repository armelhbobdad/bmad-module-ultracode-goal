#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for the gate worktree's build folders (issue #240).

The production gate replaces its measurement worktree once automate has
finished (`git worktree remove --force`, then `git worktree add`), and removes
it once the verdict is recorded. The removal deleted every ignored folder the
worktree held, Cargo's `target` among them, so a Rust or Tauri story paid two
cold builds of several minutes each, one at the first setup and one after the
rebuild, and each re-loop cycle paid again.

`references/gate.md` now has the gate carry the worktree's build folders out,
with `scripts/carry_build_cache.py out`, into a stash in the story's scratch
folder right before each removal after which the story is gated again (the
rebuild, the removal once a `reloop` verdict is recorded, and a resume's
removal of a dead session's worktree), and back with `back` right after every
`git worktree add`, before the dependency links. After an `escalate`,
`advance` or `defer` verdict it carries nothing, so the build folder goes with
the worktree as it always did. The script never carries a test-result cache, a
folder reached through a link or a path outside the worktree and the stash,
deletes the run results Cargo's tools keep in a build folder first, and leaves
a folder it cannot move to go with the worktree: the build is cold, never
wrong. The rebuild still discards every mutated source and copied test, and
the honesty line names each folder carried, skipped or failed.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text with the #240 wording taken out (the pre-edit text) and
against one-clause mutants it must reject. A replay runs the rebuild's steps,
in the order the rebuild paragraph lists them, against a worktree that holds a
Cargo build folder, with the real script: the live order keeps the folder and
the pre-edit order loses it. Stated limit: this is a presence proof over
prose. It shows the instruction is in the file, not that an executor obeys it.

Stdlib + pytest only.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_GATE = _SKILL_ROOT / "references" / "gate.md"
_SCRIPT = _SKILL_ROOT / "scripts" / "carry_build_cache.py"
_FRAGMENT = _REPO / "changes" / "gate-worktree-keeps-build-cache.yaml"
_ARCHITECTURE = _REPO / "docs" / "architecture.md"

_REBUILD_HEAD = "**Rebuild the worktree once automate has finished (production).**"
_CAVEAT_HEAD = "- **Dependency directories do not follow the commit.**"
_HONESTY_HEAD = "Record in `.decision-log.md`, once per gated story"

_OUT = "`uv run {skill-root}/scripts/carry_build_cache.py out --worktree <tmp-path> --stash <stash>`"
_WHEN_OUT = (
    "So carry the worktree's own across each replacement after which the story is gated again: right before the "
    "rebuild's `git worktree remove --force <tmp-path>`, the one once a `reloop` verdict is recorded, and a resume's "
    "of a dead session's worktree, run " + _OUT + ","
)
_WHEN_BACK = (
    "and right after every `git worktree add <tmp-path> <commit>`, before the links above, the same call with `back` "
    "in place of `out`."
)
_NOTHING_AFTER = (
    "Once an `escalate`, `advance` or `defer` verdict is recorded, carry nothing out: the build folder goes with the "
    "worktree, as it always has, so a story that stops holds no build of its own, and its re-gate builds cold."
)
_STASH = (
    "`<stash>` is `{workflow.implementation_artifacts}/.scratch-<story_id>/gate-build`, so the gate's build "
    "folders sit in the story's scratch folder (`references/execute.md`, step 0) while they are out of the "
    "worktree, and never pass to another story."
)
_NEVER_CARRIES = (
    "never a test-result cache (`.pytest_cache`, a turbo or nx cache), a folder reached through a link or a path "
    "outside the worktree and the stash"
)
_RUN_RESULTS = (
    "before it carries a Cargo folder out it deletes the run results Cargo's tools keep there (`criterion/`, "
    "`nextest/`, `tarpaulin/`, `*.profraw`), which a mutant's run wrote."
)
_COLD = "A folder it cannot move stays in the worktree and goes with it, so its next build is cold, never wrong."

# Each #240 edit as (pre-edit text, live text).
_REMOVAL = (
    "and a measurement surface holds nothing to preserve), then `git worktree prune`; a resume that finds a dead "
    "session's stale `.gate-worktree-<story_id>` removes it the same way before creating its own.",
    "and a measurement surface holds nothing to keep but the build folders the first caveat below carries out when "
    "the verdict is `reloop`), then `git worktree prune`; a resume that finds a dead session's stale "
    "`.gate-worktree-<story_id>` carries its build folders out and removes it the same way before creating its own.",
)
_CAVEAT = (
    "measure both once per repo before committing to one.",
    "measure both once per repo before committing to one. A build folder (Cargo's `target`) does not follow the "
    "commit either, and is never linked: two trees that build into one folder run each other's output as their own. "
    + _WHEN_OUT + " " + _WHEN_BACK + " " + _NOTHING_AFTER + " " + _STASH + " The script moves every Cargo build "
    "folder (`--dir <path>`, repeatable, names another toolchain's build folder instead) to the same path with a "
    "rename, " + _NEVER_CARRIES + ", and " + _RUN_RESULTS + " It prints what it carried, skipped and failed to move. "
    + _COLD,
)
_REBUILD_STEPS = (
    "replace the worktree instead of trusting it: remove it with `git worktree remove --force <tmp-path>`, add it "
    "again with `git worktree add <tmp-path> <commit>` at the commit under assessment (the backfill's commit when "
    "automate made one, per \"When automate backfills\" above), then link the dependency folders",
    "replace the worktree instead of trusting it: carry its build folders out with the `carry_build_cache.py` call "
    "the first caveat above gives, remove it with `git worktree remove --force <tmp-path>`, add it again with "
    "`git worktree add <tmp-path> <commit>` at the commit under assessment (the backfill's commit when automate made "
    "one, per \"When automate backfills\" above), carry them back with the same call's `back` form, then link the "
    "dependency folders",
)
_EXCEPTION = (
    "a command no allowlist entry covers.",
    "a command no allowlist entry covers. The build folders carried back are the one exception, and what a mutant's "
    "build left in them is an input the build tool checks, never a result it reads: every file the add writes is "
    "newer than anything built there before, so Cargo rebuilds each crate of the worktree from the commit's source "
    "and reuses only what no file of the worktree feeds, such as the registry's crates.",
)
_HONESTY = (
    "since a server the operator started can read as one the run left up.",
    "since a server the operator started can read as one the run left up. It also names each build folder "
    "`carry_build_cache.py` carried out or back, and each one it skipped, with the reason it printed, or failed to "
    "move.",
)
_EDITS = (_REMOVAL, _CAVEAT, _REBUILD_STEPS, _EXCEPTION, _HONESTY)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _paragraph(text: str, head: str) -> str:
    if head not in text:
        return ""
    start = text.index(head)
    end = text.find("\n", start)
    return text[start : end if end != -1 else len(text)]


def _pre_edit(text: str) -> str:
    for old, new in _EDITS:
        text = text.replace(new, old, 1)
    return text


def test_the_pre_edit_text_is_a_real_reconstruction():
    live = _read(_GATE)
    pre = _pre_edit(live)
    for old, new in _EDITS:
        assert live.count(new) == 1, new[:80]
        assert pre.count(old) == 1 and new not in pre, old[:80]
    assert "carry_build_cache" not in pre and "gate-build" not in pre
    assert len(live) - len(pre) == sum(len(new) - len(old) for old, new in _EDITS)


# --- the predicates -----------------------------------------------------------------


def _carries_before_each_regated_removal(text: str) -> bool:
    caveat = _flat(_paragraph(text, _CAVEAT_HEAD))
    return _WHEN_OUT in caveat and _WHEN_BACK in caveat and caveat.index(_WHEN_OUT) < caveat.index(_WHEN_BACK)


def _carries_nothing_after_a_final_verdict(text: str) -> bool:
    caveat = _flat(_paragraph(text, _CAVEAT_HEAD))
    return _NOTHING_AFTER in caveat and _REMOVAL[1] in _flat(text)


def _keeps_the_stash_in_scratch(text: str) -> bool:
    return _STASH in _flat(_paragraph(text, _CAVEAT_HEAD))


def _never_carries_what_a_run_left(text: str) -> bool:
    caveat = _flat(_paragraph(text, _CAVEAT_HEAD))
    return _NEVER_CARRIES in caveat and _RUN_RESULTS in caveat and _COLD in caveat


def _rebuild_carries_around_the_removal_and_the_add(text: str) -> bool:
    """Out, remove, add, back, then the links, in that order."""
    rebuild = _flat(_paragraph(text, _REBUILD_HEAD))
    steps = (
        "carry its build folders out with the `carry_build_cache.py` call",
        "remove it with `git worktree remove --force <tmp-path>`",
        "add it again with `git worktree add <tmp-path> <commit>`",
        "carry them back with the same call's `back` form",
        "then link the dependency folders with the same `link_worktree_deps.py` call",
    )
    if not all(step in rebuild for step in steps):
        return False
    indices = [rebuild.index(step) for step in steps]
    return indices == sorted(indices)


def _qualifies_what_the_rebuild_leaves(text: str) -> bool:
    return _EXCEPTION[1] in _flat(_paragraph(text, _REBUILD_HEAD))


def _honesty_line_names_the_folders(text: str) -> bool:
    return _HONESTY[1] in _flat(_paragraph(text, _HONESTY_HEAD))


_RULES = {
    "when-out-and-back": _carries_before_each_regated_removal,
    "nothing-after-a-final-verdict": _carries_nothing_after_a_final_verdict,
    "stash-in-scratch": _keeps_the_stash_in_scratch,
    "never-carries-a-run": _never_carries_what_a_run_left,
    "rebuild-order": _rebuild_carries_around_the_removal_and_the_add,
    "exception": _qualifies_what_the_rebuild_leaves,
    "honesty-line": _honesty_line_names_the_folders,
}


@pytest.mark.parametrize("rule", sorted(_RULES))
def test_each_rule_holds_and_is_absent_before_the_edit(rule):
    live = _read(_GATE)
    assert _RULES[rule](live)
    assert not _RULES[rule](_pre_edit(live))


# One-clause mutants, each of which drops or weakens one rule.
_MUTANTS = (
    ("when-out-and-back", "the one once a `reloop` verdict is recorded, and a resume's", "and a resume's"),
    ("when-out-and-back", ", and a resume's of a dead session's worktree, run", ", run"),
    ("when-out-and-back", "and right after every `git worktree add", "and right after the rebuild's `git worktree add"),
    ("when-out-and-back", "before the links above, the same call", "after the links above, the same call"),
    (
        "nothing-after-a-final-verdict",
        "carry nothing out: the build folder goes",
        "carry them out too: the build folder goes",
    ),
    ("nothing-after-a-final-verdict", "carries out when the verdict is `reloop`", "carries out whatever the verdict"),
    ("nothing-after-a-final-verdict", "carries its build folders out and removes it", "removes it"),
    ("stash-in-scratch", "/.scratch-<story_id>/gate-build`", "/.gate-build-<story_id>`"),
    ("stash-in-scratch", ", and never pass to another story.", ", and pass on to the next story."),
    ("never-carries-a-run", "never a test-result cache (`.pytest_cache`, a turbo or nx cache), ", ""),
    ("never-carries-a-run", "a folder reached through a link or a path", "a path"),
    ("never-carries-a-run", "(`criterion/`, `nextest/`, `tarpaulin/`, `*.profraw`)", "(`criterion/`)"),
    ("never-carries-a-run", "so its next build is cold, never wrong.", "so a copy of it is carried instead."),
    (
        "rebuild-order",
        "carry its build folders out with the `carry_build_cache.py` call the first caveat above gives, ",
        "",
    ),
    ("rebuild-order", "carry them back with the same call's `back` form, then link", "then link"),
    ("exception", "never a result it reads", "and a result it reads"),
    ("exception", "so Cargo rebuilds each crate of the worktree from the commit's source", "so Cargo reuses it"),
    ("honesty-line", "and each one it skipped, with the reason it printed, or failed to move.", "."),
)


@pytest.mark.parametrize(
    ("rule", "old", "new"), [pytest.param(*m, id=f"{m[0]}-{i}") for i, m in enumerate(_MUTANTS)]
)
def test_each_rule_rejects_a_one_clause_mutant(rule, old, new):
    live = _read(_GATE)
    assert live.count(old) == 1, old
    mutant = live.replace(old, new, 1)
    assert mutant != live, "the mutant must actually change the text"
    assert _RULES[rule](live) and not _RULES[rule](mutant)


def test_the_back_step_can_not_move_ahead_of_the_links():
    """Twin of the order: carrying back after the links would find a linked
    folder's path taken and leave a build folder in the stash."""
    live = _read(_GATE)
    back = "carry them back with the same call's `back` form, "
    links = "then link the dependency folders with the same `link_worktree_deps.py` call"
    mutant = live.replace(back, "", 1).replace(links, links + ", " + back.rstrip(", "), 1)
    assert mutant != live
    assert not _rebuild_carries_around_the_removal_and_the_add(mutant)


def test_the_caveats_stay_four_and_the_new_prose_breaks_no_house_rule():
    live = _read(_GATE)
    assert "Four caveats the setup owes" in live
    section = live[live.index("## Measure the commit, not the working tree") :]
    section = section[: section.index("\n**Rebuild the worktree")]
    assert len(re.findall(r"^- \*\*", section, re.MULTILINE)) == 4
    for _, new in _EDITS:
        assert chr(0x2014) not in new
        assert "owned" not in new
    # No new sentence names the scratch folder beside a verb that removes it.
    scratch = re.compile(r"\.scratch-(?:<[^>]+>|\*)|scratch (?:directory|folder|dir)\b", re.I)
    remove = re.compile(r"remov|delet|rm -|clean\w* up|discard|wip|eras|prun|purg|clear\w* (?:out|away)|drop", re.I)
    for _, new in _EDITS:
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z`*(\"-])", new):
            assert not (scratch.search(sentence) and remove.search(sentence)), sentence
    # No command the prose gives leads with an environment variable.
    assert not re.search(r"`[A-Z_]+=\S+ ", "".join(new for _, new in _EDITS))
    assert chr(0x2014) not in _read(_FRAGMENT)


# --- the script the prose names ------------------------------------------------------


def _help() -> str:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def test_the_prose_names_the_scripts_own_modes_and_flags():
    usage = _help()
    for word in ("out", "back", "--worktree", "--stash", "--dir"):
        assert word in usage, word
    caveat = _flat(_paragraph(_read(_GATE), _CAVEAT_HEAD))
    assert _OUT in caveat and "`--dir <path>`" in caveat


def test_the_script_has_its_line_in_the_architecture_layout():
    assert "── carry_build_cache.py " in _read(_ARCHITECTURE)


# --- the rebuild, replayed with the real script --------------------------------------


def _carry(mode: str, worktree: Path, stash: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), mode, "--worktree", str(worktree), "--stash", str(stash)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _add(worktree: Path) -> None:
    """`git worktree add`: the commit's tracked files, and nothing else."""
    (worktree / "src").mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    (worktree / "src" / "lib.rs").write_text("pub fn f() {}\n", encoding="utf-8")


def _replay_rebuild(gate: str, tmp_path: Path) -> tuple[bool, bool]:
    """Run the rebuild's steps in the order its paragraph lists them, on a
    worktree that holds a Cargo build folder and a mutated source file.
    Returns whether the build folder is back and whether the mutant is gone."""
    worktree = tmp_path / "impl" / ".gate-worktree-1-2"
    stash = tmp_path / "impl" / ".scratch-1-2" / "gate-build"
    _add(worktree)
    (worktree / "src" / "lib.rs").write_text("pub fn f() { panic!() }\n", encoding="utf-8")  # automate's mutant
    target = worktree / "target"
    (target / "debug").mkdir(parents=True)
    (target / "CACHEDIR.TAG").write_text("Signature: 8a477f597d28d172789f06886806bc55\n", encoding="utf-8")
    (target / ".rustc_info.json").write_text("{}\n", encoding="utf-8")
    (target / "debug" / "libdep.rlib").write_text("built\n", encoding="utf-8")

    rebuild = _flat(_paragraph(gate, _REBUILD_HEAD))
    actions = {
        "carry its build folders out": lambda: _carry("out", worktree, stash),
        "remove it with `git worktree remove --force <tmp-path>`": lambda: shutil.rmtree(worktree),
        "add it again with `git worktree add <tmp-path> <commit>`": lambda: _add(worktree),
        "carry them back": lambda: _carry("back", worktree, stash) if worktree.is_dir() else None,
    }
    for step in sorted((s for s in actions if s in rebuild), key=rebuild.index):
        actions[step]()
    restored = (worktree / "target" / "debug" / "libdep.rlib").is_file()
    clean = (worktree / "src" / "lib.rs").read_text(encoding="utf-8") == "pub fn f() {}\n"
    return restored, clean


def test_replay_the_rebuild_keeps_the_build_folder_and_drops_the_mutant(tmp_path):
    assert _replay_rebuild(_read(_GATE), tmp_path) == (True, True)


def test_replay_on_the_pre_edit_text_loses_the_build_folder(tmp_path):
    """The mutant twin: the field failure, read off the pre-edit sentences."""
    assert _replay_rebuild(_pre_edit(_read(_GATE)), tmp_path) == (False, True)


# --- the fragment ----------------------------------------------------------------------

_FRAGMENT_SAYS = (
    "type: changed",
    "scope: ultracode-goal",
    "issues: [240]",
    "`carry_build_cache.py`",
    "`.scratch-<story_id>/gate-build/`",
    "right before a `git worktree remove --force` after which the story is gated again",
    "the removal once a `reloop` verdict is recorded",
    "back to the same path right after every `git worktree add`",
    "After an `escalate`, `advance` or `defer` verdict nothing is carried",
    "never carries a test-result cache (`.pytest_cache`, a turbo or nx cache) or a folder reached through a link",
    "(`criterion/`, `nextest/`, `tarpaulin/`, `*.profraw`)",
    "a build is cold but never wrong",
    "Mutated sources and copied tests are still discarded",
    "the cache never passes from one story to the next",
)


def test_the_fragment_says_what_the_prose_does():
    fragment = _flat(_read(_FRAGMENT))
    assert [s for s in _FRAGMENT_SAYS if s not in fragment] == []


def test_the_scripts_header_matches_its_sibling():
    header = _read(_SCRIPT)
    assert header.startswith("#!/usr/bin/env -S uv run --script\n# /// script\n")
    assert '# requires-python = ">=3.11"' in header and "# dependencies = []" in header
    assert os.path.basename(_SCRIPT) == "carry_build_cache.py"
