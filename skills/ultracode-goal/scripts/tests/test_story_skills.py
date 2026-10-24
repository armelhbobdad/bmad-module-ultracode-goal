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
- neither invokes or names BMAD's shim ids outside its attribution, and every
  local file either one points at ships with it;
- a decomposed child, which has no story file, reaches `ucg-dev-story` as an
  explicit input (its key, the parent's story file, the ACs it claims, and on
  a re-loop the findings that sent it back) that writes no story file, meets
  no step or checklist item only a story file can meet, and moves only the
  child's row.

Run: uv run --with pytest pytest scripts/tests/test_story_skills.py
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[3]
CREATE = SKILLS / "ucg-create-story"
DEV = SKILLS / "ucg-dev-story"
EXECUTE = SKILLS / "ultracode-goal" / "references" / "execute.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(path: Path) -> str:
    return re.sub(r"\s+", " ", _text(path))


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


def test_create_story_description_names_every_skill_that_delegates_to_it():
    # ucg-formalize runs it to fill a story gap, cold as well as inside a run,
    # so a description scoped to an UltraCode Goal run turned that call away.
    found = re.search(r'^description: "(.*)"$', _text(CREATE / "SKILL.md"), re.M)
    assert found is not None
    description = found.group(1)
    assert "ultracode-goal" in description and "ucg-formalize" in description, description
    assert "outside an UltraCode Goal run" not in description, description


def test_every_local_file_the_story_skills_point_at_ships():
    # The checklist told every story creation to load `./workflow.md`, which
    # this copy never shipped: its variables live in SKILL.md. LICENSE.md
    # records that change, so it names the file.
    for skill in (CREATE, DEV):
        for path in skill.glob("*.md"):
            if path.name == "LICENSE.md":
                continue
            text = _text(path)
            for name in re.findall(r"`\./([\w./-]+)`", text):
                assert (skill / name).is_file(), (skill.name, path.name, name)
            assert "workflow.md" not in text, (skill.name, path.name)


_CHILD_INPUTS = ("story_key", "parent_story_path", "claimed_acs")


def _section(text: str, heading: str) -> str:
    at = text.find(heading)
    assert at != -1, f"{heading!r} is gone"
    end = text.find(" ## ", at + len(heading))
    return text[at : end if end != -1 else len(text)]


def test_dev_story_takes_a_decomposed_child_input():
    # execute.md's sizing conventions: a child has no story file and must never
    # get one, the parent's story file is never edited and is read for the AC
    # text only, and the parent's row stays `done`. Before this input existed
    # the skill looked for `{{story_key}}.md` and halted, or took the parent's
    # file and wrote its tasks and its row.
    text = _flat(DEV / "SKILL.md")
    section = _section(text, "## Decomposed Child")
    for name in _CHILD_INPUTS:
        assert f"`{{{{{name}}}}}`:" in section, name
    for rule in (
        "for the claimed ACs' text and its Dev Notes only",
        "Its tasks and its other ACs are the parent's",
        "Never edit the parent's file and never create `{{story_key}}.md`",
        "Skip every write to a story file",
        "Implement the claimed ACs only",
        "sets development_status[{{story_key}}] to `in-progress` and step 9 sets it to `review`",
        "The parent's row stays `done`",
        "Never edit the parent's file to fix one",
    ):
        assert rule in section, rule
    # Step 1 routes a child before it reads a story path or looks for a file
    # named for the key, and keeps the key it was given.
    step1 = text[text.find('<step n="1"') : text.find('<step n="2"')]
    child = step1.find('<check if="{{parent_story_path}} is provided">')
    assert child != -1, "step 1 has no route for a decomposed child"
    assert child < step1.find('<check if="{{story_path}} is provided">')
    assert child < step1.find("{{story_key}}.md")
    assert "Keep {{story_key}} as given" in step1
    # Step 4 moves a child's row from whatever status it holds, which is not
    # `ready-for-dev`: ucg-create-story, the writer of that status, never runs
    # for a child.
    step4 = text[text.find('<step n="4"') : text.find('<step n="5"')]
    assert "({{parent_story_path}} is provided AND {{current_status}} != 'in-progress')" in step4


def test_execute_hands_ucg_dev_story_the_child_input():
    text = _flat(EXECUTE)
    at = text.find("**For a decomposed child row, skip `ucg-create-story` entirely**")
    assert at != -1, "execute.md step 1's decomposed-child rule moved"
    window = text[at : at + 1600]
    assert "Hand `ucg-dev-story` the child's input in place of a story path" in window
    for name in _CHILD_INPUTS:
        assert f"`{name}`" in window, name
    assert 'Its "Decomposed Child" section' in window
    assert "## Decomposed Child" in _text(DEV / "SKILL.md")
    assert "never a `ucg-create-story` run for the child" in window


# Each step action that reads or writes a story file, as a decomposed child
# must never meet it: under a guard that leaves a child out.
_NOT_A_CHILD = "{{parent_story_path}} is not provided"
_STORY_FILE_ONLY = (
    "Identify first incomplete task (unchecked [ ]) in Tasks/Subtasks",
    'Check if "Senior Developer Review (AI)" section exists in the story file',
    "Document technical approach and decisions in Dev Agent Record",
    "ONLY THEN mark the task (and subtasks) checkbox with [x]",
    "Add Change Log entry",
    "Save the story file",
    "Verify ALL tasks and subtasks are marked [x]",
    'Update the story Status to: "review"',
    "Validate definition-of-done checklist with essential requirements",
    "Prepare a concise summary in Dev Agent Record",
    "Provide the story file path and current status",
)


def _guard_of(workflow: str, at: int) -> str:
    """The `if` of the innermost <check> still open at `at`, or of the
    <action> that holds `at`; '' when nothing guards it."""
    opened: list[str] = []
    for tag in re.finditer(r'<(/?)(check|action)\b([^>]*)>', workflow[:at]):
        closing, kind, attrs = tag.groups()
        if closing:
            if opened and opened[-1][0] == kind:
                opened.pop()
            continue
        if attrs.rstrip().endswith("/"):
            continue
        found = re.search(r'if="([^"]*)"', attrs)
        opened.append((kind, found.group(1) if found else ""))
    for _, condition in reversed(opened):
        if condition:
            return condition
    return ""


def test_a_decomposed_child_meets_no_story_file_step():
    # A child has no story file: the parent's file holds its criteria, and the
    # parent's tasks, review section and Status are the parent's. Before, step
    # 1 jumped to step 9 when the parent's tasks were all checked, step 3 read
    # the parent's review section, and steps 8 to 10 saved a story file, set
    # its Status and validated its Change Log, so a child either wrote the
    # parent's file or halted on a definition of done it could never meet.
    text = _flat(DEV / "SKILL.md")
    workflow = text[text.index("<workflow>") :]
    for action in _STORY_FILE_ONLY:
        at = workflow.find(action)
        assert at != -1, action
        assert workflow.count(action) == 1, action
        assert _NOT_A_CHILD in _guard_of(workflow, at), action
    step1 = workflow[workflow.find('<step n="1"') : workflow.find('<step n="2"')]
    task_check = step1[step1.find('<anchor id="task_check" />') :]
    assert "Take the ACs in {{claimed_acs}}, in the order given, as the work list" in task_check
    step3 = workflow[workflow.find('<step n="3"') : workflow.find('<step n="4"')]
    child = step3.find('<check if="{{parent_story_path}} is provided">')
    assert child != -1 and child < step3.find("Senior Developer Review")
    assert "Set review_continuation = true when {{review_findings}} is given" in step3
    section = _section(text, "## Decomposed Child")
    assert "`{{review_findings}}`:" in section
    assert "do not apply: mark them N/A, never failed" in section


def test_the_dev_story_checklist_reads_a_decomposed_child():
    checklist = _text(DEV / "checklist.md")
    target = re.search(r"^validation-target: '(.*)'$", checklist, re.M)
    assert target is not None
    assert "{{claimed_acs}}" in target.group(1) and "{{parent_story_path}}" in target.group(1)
    flat = re.sub(r"\s+", " ", checklist)
    note = flat[flat.index("**A decomposed child**") :]
    note = note[: note.index(" ## ")]
    for item in ("Change Log Updated", "Story Structure Compliance", "Story Status Updated"):
        assert f"**{item}**" in note, item
    assert "N/A" in note
    # The description promises a story set to review, which a child never has.
    found = re.search(r'^description: "(.*)"$', _text(DEV / "SKILL.md"), re.M)
    assert found is not None
    assert "decomposed child" in found.group(1), found.group(1)


def test_execute_hands_a_child_its_findings_and_checks_its_notes():
    text = _flat(EXECUTE)
    at = text.find("**For a decomposed child row, skip `ucg-create-story` entirely**")
    window = text[at : at + 2400]
    # On a re-loop the gate's reasons and the review findings reach the child
    # as an input: no review can write them into a story file it does not have.
    assert "On a re-loop, also hand it `review_findings`" in window
    # Its File List and notes, given in ucg-dev-story's step 10 summary, are the
    # record the claim check reads: an empty notes file checked nothing.
    claims = text[text.index("**Check the record's claims before the commit.**") :]
    claims = claims[: claims.index("```")]
    assert "an empty file when it added none, as for a decomposed child with no record" not in claims
    assert "for a decomposed child, which has no record, the File List and completion notes" in claims
