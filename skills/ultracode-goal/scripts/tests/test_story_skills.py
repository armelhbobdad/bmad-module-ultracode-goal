#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""The story skills UCG ships in place of BMAD Method's deprecated shims.

`ucg-create-story` and `ucg-dev-story` are adapted from BMAD Method 6.12.4's
`bmad-create-story` and `bmad-dev-story`, which 6.12 made opt-in shims and v7
removes. The rest of a run reads what they leave behind, so these tests pin the
parts of their contract UCG's own stages depend on:

- the story file lands at `{implementation_artifacts}/{story_key}.md`, and the
  sprint-status row moves backlog -> ready-for-dev (create) and ready-for-dev ->
  in-progress -> review (dev), never to `done`, which only the gate writes;
- neither skill commits, push or otherwise, so the commit guard and Execute's
  commit-at-green order stay intact;
- each carries the MIT notice of the work it adapts, and loads config even where
  `_bmad/scripts/resolve_config.py` is absent;
- neither invokes or names BMAD's shim ids outside its attribution.

Run: uv run --with pytest pytest scripts/tests/test_story_skills.py
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[3]
CREATE = SKILLS / "ucg-create-story"
DEV = SKILLS / "ucg-dev-story"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# The only commit mentions the forks carry read history or capture HEAD; any
# other line naming a commit or a push is an instruction to make one.
_READ_ONLY_COMMIT_MENTION = re.compile(
    r"commit titles|recent commits|capture current commit into \{\{baseline_commit\}\}", re.I
)


def _commits(text: str) -> list[str]:
    """Lines that tell the agent to make a commit or push."""
    return [
        line
        for line in text.splitlines()
        if re.search(r"\b(commit\w*|push\w*)\b", _READ_ONLY_COMMIT_MENTION.sub("", line), re.I)
    ]


def test_each_skill_is_named_for_its_directory_and_attributed():
    for skill in (CREATE, DEV):
        text = _text(skill / "SKILL.md")
        assert re.search(r"^name: %s$" % skill.name, text, re.M), skill.name
        assert "lifecycle: shim" not in text
        assert "Deprecated: `bmad-build` is now the official implementation method" not in text
        assert "Copyright (c) 2025 BMad Code, LLC" in text
        license_text = _text(skill / "LICENSE.md")
        assert "Copyright (c) 2025 BMad Code, LLC" in license_text
        assert "The above copyright notice and this permission notice shall be included" in license_text


def test_create_story_writes_the_story_file_and_ready_for_dev():
    text = _text(CREATE / "SKILL.md")
    assert "`default_output_file` = `{implementation_artifacts}/{{story_key}}.md`" in text
    assert 'Update development_status[{{story_key}}] = "ready-for-dev"' in text
    assert '<action>Set story Status to: "ready-for-dev"</action>' in text


def test_dev_story_moves_in_progress_then_review_and_never_done():
    text = _text(DEV / "SKILL.md")
    assert 'Update the story in the sprint status report to = "in-progress"' in text
    assert 'Update development_status[{{story_key}}] = "review"' in text
    assert not re.search(r'development_status\[[^\]]*\]\s*=\s*"done"', text)


def test_neither_skill_commits():
    for skill in (CREATE, DEV):
        for path in skill.glob("*.md"):
            assert _commits(_text(path)) == [], path


def test_the_commit_detector_sees_a_commit_instruction():
    # Anti-vacuous twin: the instructions the fork must never carry are caught,
    # in command form and in plain prose, while its read-only mentions pass.
    assert _commits('<action>Run `git commit -m "story"` once tests pass</action>')
    assert _commits("<action>Commit all changes with a message naming the story</action>")
    assert _commits("<action>Push the branch</action>")
    assert _commits("<action>Finish by committing the story changes</action>")
    assert _commits("<action>Pushing the branch is the last step</action>")
    # A read-only phrase exempts only itself, never the rest of its line.
    assert _commits("<action>Check recent commits, then commit the story</action>")
    assert not _commits("<action>Get last 5 commit titles to understand recent work patterns</action>")
    assert not _commits("Run `git rev-parse HEAD` to capture current commit into {{baseline_commit}}")


def test_config_loads_without_resolve_config():
    for skill in (CREATE, DEV):
        text = _text(skill / "SKILL.md")
        assert "If that script is absent or fails, read the same keys from" in text, skill.name
        assert "`{project-root}/_bmad/bmm/config.yaml`" in text, skill.name


def test_customization_lands_in_the_workflow_persistent_facts_channel():
    # Installer Step 6b merges the opt-in awareness fragment for ucg-create-story
    # into this channel; ucg-dev-story keeps the same surface.
    for skill in (CREATE, DEV):
        workflow = tomllib.loads(_text(skill / "customize.toml"))["workflow"]
        assert workflow["persistent_facts"] == []
        assert workflow["on_complete"] == ""


def test_no_shim_id_outside_the_attribution():
    for skill in (CREATE, DEV):
        for path in skill.iterdir():
            if path.name == "LICENSE.md":
                continue
            for line in _text(path).splitlines():
                if "bmad-create-story" in line or "bmad-dev-story" in line:
                    assert line.startswith("<!-- Adapted for UltraCode Goal from BMAD Method"), (path, line)


def test_dev_story_points_back_to_ucg_create_story():
    text = _text(DEV / "SKILL.md")
    assert "Run `ucg-create-story` to create next story from epics" in text
    assert "validate-create-story" not in text
    assert "Run `ucg-dev-story` for optimized implementation" in _text(CREATE / "SKILL.md")


def test_the_customization_resolver_call_runs_on_bmad_6_10():
    # BMAD 6.10's resolve_customization.py takes --skill and --key only and
    # exits 2 on --project-root, so every call omits it, and on_complete has a
    # fallback to the block resolved on activation.
    for skill in (CREATE, DEV):
        text = _text(skill / "SKILL.md")
        calls = [line for line in text.splitlines() if "resolve_customization.py" in line]
        assert len(calls) == 2, (skill.name, calls)
        assert all("--project-root" not in line for line in calls), skill.name
        assert "take `on_complete` from the `workflow` block resolved on activation" in text, skill.name
