#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Preflight states its conditional rules as conditional.

Three rules in references/preflight.md read as unconditional and were not:

- the TEA-mode step read as a config write (`tea_execution_mode: create`),
  where `tea_execution_mode` is TEA's parallelism setting and Create is the
  choice made at each TEA invocation;
- "the branch is the real undo" holds only when git tracks the artifact tree.
  On a gitignored one the branch undoes the code alone, `git_clean` says
  nothing about what the pass wrote there, and an acceptance criterion that
  reads a file there at test time fails in CI;
- the stale-hook disarm binds a remediation commit only, so a pass that makes
  no commit need not disarm, and a refused disarm it did not need is no stop.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_preflight_conditional_wording.py -v
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
PREFLIGHT = SCRIPTS.parent / "references" / "preflight.md"
PREFLIGHT_CHECK = SCRIPTS / "preflight_check.py"
GUARD = SCRIPTS / "hooks" / "guard_pretooluse.py"


def _text() -> str:
    return PREFLIGHT.read_text(encoding="utf-8")


def _section(heading: str, stop: str = "\n## ") -> str:
    text = _text()
    start = text.index(heading)
    end = text.find(stop, start + len(heading))
    return text[start : end if end != -1 else len(text)]


def _bullet(section: str, prefix: str) -> str:
    hits = [line for line in section.splitlines() if line.startswith(prefix)]
    assert len(hits) == 1, (prefix, len(hits))
    return hits[0]


# --- TEA mode -----------------------------------------------------------------


def test_tea_mode_is_chosen_at_each_invocation_not_written_to_config():
    bullet = _bullet(_section("## 2. Auto-remediation pass"), "- **TEA mode**")
    assert "invoke every TEA workflow this run in **Create** mode" in bullet
    assert "**not** a config value" in bullet
    assert "`auto`, `subagent`, `agent-team` or `sequential`" in bullet
    assert "never write `create` or any other mode word into it" in bullet
    # TEA normalizes a stray value to `auto`, so the step logs it and writes nothing.
    assert "TEA reads a value outside those four as `auto`" in bullet
    assert "log it, and leave the file alone" in bullet
    # The old wording that read as a write of `create` into the key is gone.
    assert "Set/confirm whatever the TEA config exposes" not in bullet


def test_the_script_no_longer_records_a_forced_create_check():
    text = PREFLIGHT_CHECK.read_text(encoding="utf-8")
    assert "forced-Create" not in text
    assert "create  # forced" not in text


# --- a gitignored artifact tree -----------------------------------------------


def test_step1_reports_impl_artifacts_tracked_as_a_fact_not_a_blocker():
    step1 = _section("## 1. Run the mechanical check", "\n## 1b.")
    assert "bmad_install, impl_artifacts_tracked}}" in step1
    assert "`impl_artifacts_tracked` is a reported fact, never a blocker" in step1
    assert "`null` only when there is no repository to ask" in step1


def test_step2_forbids_a_test_reading_an_ignored_path():
    step2 = _section("## 2. Auto-remediation pass")
    assert "**A gitignored artifact tree** (`impl_artifacts_tracked: false`)." in step2
    assert "`git_clean: true` says nothing about the story files this pass writes there" in step2
    assert "as a file a test reads at run time: the test would pass here and fail in CI" in step2
    # The rule binds the whole run, and Define-Done, where most ACs are written, points to it.
    assert "No acceptance criterion or test this run writes (this pass, Define-Done's story creation and ATDD, or Execute)" in step2
    define_done = (SCRIPTS.parent / "references" / "define-done.md").read_text(encoding="utf-8")
    assert "preflight's `impl_artifacts_tracked: false`), no acceptance criterion may have a test read a file" in define_done


def test_step5_and_the_briefing_say_what_the_branch_does_not_undo():
    step5 = _section("## 5. Arm the environment", "\n### Launch briefing")
    arm = _bullet(step5, "- **What the branch does not undo.**")
    assert "When step 1 reported `impl_artifacts_tracked: false`" in arm
    assert "deleting this branch undoes the code only" in arm
    briefing = _section("### Launch briefing", "\n## ")
    line = _bullet(briefing, "- **What the branch does not undo**")
    assert "(only when step 1 reported `impl_artifacts_tracked: false`)" in line
    assert "omit this line when the tree is tracked" in line
    # It sits right after the kill switch, the line the operator reads for the undo.
    bullets = [b for b in briefing.splitlines() if b.startswith("- ")]
    kill = next(i for i, b in enumerate(bullets) if b.startswith("- **Kill switch:**"))
    assert bullets[kill + 1] == line


# --- the stale-hook disarm ----------------------------------------------------


def test_the_disarm_binds_a_commit_only():
    step2 = _section("## 2. Auto-remediation pass")
    paragraph = next(p for p in step2.split("\n\n") if p.startswith("**When the disarm applies.**"))
    assert "the disarm is owed before the first commit this run makes ahead of step 5's Hooks bullet" in paragraph
    assert "or step 5's own dirty-tree resolve" in paragraph
    assert "On a tracked tree that commit is all but certain" in paragraph
    assert "skip the disarm and log why" in paragraph
    # A skipped disarm leaves stale entries, so step 5 must replace, never append.
    step5 = _section("## 5. Arm the environment", "\n### Launch briefing")
    assert "**Replace, never append.** When the merge writes, it first removes every inner item" in step5
    refused = next(p for p in step2.split("\n\n") if p.startswith("**A refused settings write.**"))
    assert "A refused write of a disarm the pass does not need (the paragraph above) is no stop" in refused
    # Every other refusal still stops.
    assert "Treat any other refusal of the write" in refused and "as a stop" in refused


def test_the_guard_acts_on_commit_and_push_alone():
    # The disarm paragraph's scope rests on this: if the guard ever gated another
    # git verb, a pass that only branches could hit a stale guard too.
    spec = importlib.util.spec_from_file_location("guard_pretooluse", GUARD)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    assert guard._WRITE_VERBS == frozenset({"commit", "push"})
    assert guard._git_writes("git checkout -b epic-4") == set()
    assert guard._git_writes("git commit -m x") == {"commit"}
