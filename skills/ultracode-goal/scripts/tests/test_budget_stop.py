#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Exercise the budget Stop hook via the real stdin/stdout contract.

Invariant under test: an overrun NEVER blocks the stop (no decision:"block");
it writes an escalation marker and surfaces a systemMessage, exit 0.

Also pins the hook to turns only: the token path is gone from the source and
inert at runtime, the stage references no longer interpolate a token ceiling,
and the config key that named it is deprecated in place rather than removed."""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "budget_stop.py"
_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_CUSTOMIZE = _SKILL_ROOT / "customize.toml"
_STABILITY = _REPO_ROOT / "docs" / "_internal" / "STABILITY.md"
_CHANGELOG = _REPO_ROOT / "CHANGELOG.md"

_STAGES = ("preflight", "execute", "finalize", "gate")


def _stage_text(stage: str) -> str:
    return (_SKILL_ROOT / "references" / f"{stage}.md").read_text(encoding="utf-8")


def _preflight_step5(text: str) -> str:
    start = text.index("## 5. Arm the environment")
    try:
        end = text.index("### Launch briefing", start)
    except ValueError:
        end = len(text)
    return text[start:end]


def _unreleased_block(changelog: str) -> str:
    start = changelog.index("## [Unreleased]")
    nxt = changelog.find("\n## [", start + 1)
    return changelog[start:] if nxt == -1 else changelog[start:nxt]


def _run(event: dict, cwd: Path, env_extra: dict) -> tuple[int, dict | None]:
    env = {**os.environ, **env_extra}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )
    out = json.loads(proc.stdout) if proc.stdout.strip() else None
    return proc.returncode, out


def test_under_budget_proceeds_silently(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    impl.mkdir()
    code, out = _run(
        {"hook_event_name": "Stop", "cwd": str(tmp_path)},
        tmp_path,
        {
            "ULTRACODE_IMPL_ARTIFACTS": str(impl),
            "ULTRACODE_STORY_ID": "S1",
            "ULTRACODE_MAX_TURNS": "3",
        },
    )
    assert code == 0
    assert out is None
    state = json.loads((impl / ".budget-S1.json").read_text())
    assert state["turns"] == 1


def test_turn_overrun_escalates_but_proceeds(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    impl.mkdir()
    env = {
        "ULTRACODE_IMPL_ARTIFACTS": str(impl),
        "ULTRACODE_STORY_ID": "S1",
        "ULTRACODE_MAX_TURNS": "2",
    }
    _run({"hook_event_name": "Stop", "cwd": str(tmp_path)}, tmp_path, env)
    code, out = _run({"hook_event_name": "Stop", "cwd": str(tmp_path)}, tmp_path, env)

    assert code == 0  # the stop proceeds; the hook never blocks
    assert out is not None
    assert "block" not in out  # critical: not a Stop-block decision
    # the line above tests dict KEYS, so it cannot see a {"decision": "block"}
    # value; the advisory guarantee needs the emitted payload checked too
    assert out.get("decision") != "block"
    assert "block" not in json.dumps(out)
    assert "systemMessage" in out
    assert (impl / ".escalation-S1.md").is_file()


def test_overrun_marker_and_message_defer_to_the_gate(tmp_path: Path) -> None:
    # The hook cannot know the gate's verdict, so neither its marker nor its
    # message may declare the story escalated: a story that then advances at
    # its gate gets a sizing note instead.
    impl = tmp_path / "impl"
    impl.mkdir()
    env = {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "ULTRACODE_STORY_ID": "S1", "ULTRACODE_MAX_TURNS": "1"}
    code, out = _run({"hook_event_name": "Stop", "cwd": str(tmp_path)}, tmp_path, env)

    assert code == 0 and out is not None
    message = out["systemMessage"]
    assert "It escalates if its gate does not advance it" in message
    assert "sizing note" in message
    assert "Stop and escalate this story" not in message
    marker = (impl / ".escalation-S1.md").read_text(encoding="utf-8")
    assert "Unless this story advances at its gate" in marker
    assert "this is a sizing note, not an escalation" in marker
    assert "stops this story and escalates" not in marker


def _no_story_env(impl: Path, max_turns: str = "1") -> dict:
    # ULTRACODE_STORY_ID is set empty rather than left out, because _run merges
    # the host environment and a host value must not satisfy the case.
    return {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "ULTRACODE_STORY_ID": "", "ULTRACODE_MAX_TURNS": max_turns}


def test_a_whitespace_story_id_falls_through_to_the_marker(tmp_path: Path) -> None:
    """A blank-but-set ULTRACODE_STORY_ID is no story id: with no marker nothing
    is counted, and with a marker the marker's story is."""
    impl = tmp_path / "impl"
    impl.mkdir()
    env = {**_no_story_env(impl, "25"), "ULTRACODE_STORY_ID": "   "}
    _run({"hook_event_name": "Stop", "cwd": str(tmp_path)}, tmp_path, env)
    assert list(impl.iterdir()) == []
    (impl / ".current-story").write_text("S1\n", encoding="utf-8")
    _run({"hook_event_name": "Stop", "cwd": str(tmp_path)}, tmp_path, env)
    assert json.loads((impl / ".budget-S1.json").read_text())["turns"] == 1


def test_a_stop_with_no_story_writes_nothing(tmp_path: Path) -> None:
    """Before the first story's step 0 (hooks armed, no story set yet) a Stop is
    no story's turn.
    It used to book the turn to a made-up story and write `.budget-unknown.json`,
    which nothing reads and which kept preflight's clean-tree check red."""
    impl = tmp_path / "impl"
    impl.mkdir()
    code, out = _run({"hook_event_name": "Stop", "cwd": str(tmp_path)}, tmp_path, _no_story_env(impl))
    assert code == 0
    assert out is None, "a ceiling of 1 would have printed the overrun for a counted turn"
    assert list(impl.iterdir()) == []


def test_a_current_story_marker_is_still_counted(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / ".current-story").write_text("S1\n", encoding="utf-8")
    code, _ = _run({"hook_event_name": "Stop", "cwd": str(tmp_path)}, tmp_path, _no_story_env(impl, "5"))
    assert code == 0
    assert json.loads((impl / ".budget-S1.json").read_text())["turns"] == 1


def test_a_stop_with_no_story_leaves_a_story_counter_alone(tmp_path: Path) -> None:
    """A resume inherits each story's counter; a Stop with no story set must not
    touch one, or a story could evade or exhaust its ceiling by accident."""
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / ".budget-S1.json").write_text(json.dumps({"turns": 5}), encoding="utf-8")
    _run({"hook_event_name": "Stop", "cwd": str(tmp_path)}, tmp_path, _no_story_env(impl, "25"))
    assert json.loads((impl / ".budget-S1.json").read_text()) == {"turns": 5}
    assert not (impl / ".budget-unknown.json").exists()


def test_an_empty_story_marker_still_counts_against_unknown(tmp_path: Path) -> None:
    """An empty marker may hide a story in flight, so its turns still count."""
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / ".current-story").write_text("", encoding="utf-8")
    _run({"hook_event_name": "Stop", "cwd": str(tmp_path)}, tmp_path, _no_story_env(impl, "25"))
    assert json.loads((impl / ".budget-unknown.json").read_text())["turns"] == 1


def test_a_story_marker_that_is_not_utf8_still_counts_against_unknown(tmp_path: Path) -> None:
    """A marker holding bytes that are not UTF-8 raised out of the hook, which
    exited 1 before it counted the turn, so the ceiling could not see it. It
    counts as an unreadable marker does now."""
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / ".current-story").write_bytes(b"\xff\xfeS1\n")
    code, out = _run({"hook_event_name": "Stop", "cwd": str(tmp_path)}, tmp_path, _no_story_env(impl, "25"))
    assert code == 0
    assert out is None
    assert json.loads((impl / ".budget-unknown.json").read_text())["turns"] == 1


def test_token_env_vars_are_inert(tmp_path: Path) -> None:
    """A conductor that still injects the old token vars changes nothing.

    Same drive as the pre-deprecation token-overrun case: a budget of 100 with
    150 spent this turn, well under the turn ceiling. The hook must ignore both
    vars, stay silent, and write no escalation marker."""
    impl = tmp_path / "impl"
    impl.mkdir()
    code, out = _run(
        {"hook_event_name": "Stop", "cwd": str(tmp_path)},
        tmp_path,
        {
            "ULTRACODE_IMPL_ARTIFACTS": str(impl),
            "ULTRACODE_STORY_ID": "S2",
            "ULTRACODE_MAX_TURNS": "999",
            "ULTRACODE_TOKEN_BUDGET": "100",
            "ULTRACODE_TURN_TOKENS": "150",
        },
    )
    assert code == 0
    assert out is None
    assert not (impl / ".escalation-S2.md").exists()
    # positive control: the hook did run and did count the turn
    assert json.loads((impl / ".budget-S2.json").read_text())["turns"] == 1


def test_token_accumulation_removed_from_hook_source() -> None:
    """No token path remains in the hook, live or dormant."""
    src = HOOK.read_text(encoding="utf-8")
    assert "ULTRACODE_TURN_TOKENS" not in src
    assert "ULTRACODE_TOKEN_BUDGET" not in src
    assert "DEFAULT_TOKEN_BUDGET" not in src
    assert re.search(r"""\[\s*["']tokens["']\s*\]\s*\+=""", src) is None
    # positive control: this really is the hook source, not an empty read
    assert "ULTRACODE_MAX_TURNS" in src and 'state["turns"] += 1' in src


def test_hook_docstring_documents_turns_only_bound() -> None:
    """The module docstring states the three real layers and claims no other."""
    doc = ast.get_docstring(ast.parse(HOOK.read_text(encoding="utf-8"))) or ""
    assert doc, "the hook must keep its module docstring"

    lower = doc.lower()
    goal_clause = lower.index("/goal")
    reloop = lower.index("re-loop budget")
    recorder = lower.index("recorder")
    assert goal_clause < reloop < recorder, (
        "the docstring must state the bound in order of authority: the /goal "
        "turn clause, then the gate re-loop budget, then this hook as recorder"
    )
    assert "stop after n turns" in lower
    assert "max_turns_per_story" in doc
    assert "advisory" in lower and "never blocks" in lower

    # and it must not re-advertise a ceiling this layer cannot enforce
    assert "token" not in lower


def test_stage_references_drop_token_budget_ceiling() -> None:
    """No stage file interpolates the deprecated key as an enforceable ceiling."""
    for stage in _STAGES:
        text = _stage_text(stage)
        assert "story_token_budget" not in text, (
            f"{stage}.md still interpolates a token ceiling that cannot fire"
        )
        # positive control: a real read of a real stage file, not empty text
        assert "{workflow.max_turns_per_story}" in text, (
            f"{stage}.md must still name the turn budget that replaced it"
        )

    step5 = _preflight_step5(_stage_text("preflight"))
    assert "ULTRACODE_TOKEN_BUDGET" not in step5, (
        "preflight must not inject a token budget into the hook env"
    )
    assert "1_500_000" not in step5, (
        "and must not re-advertise the ceiling via the fallback literal"
    )
    # positive control on the slice itself
    assert "ULTRACODE_MAX_TURNS='{workflow.max_turns_per_story}'" in step5

    # the re-loop-becomes-escalate rule is what the conductor checks the count against; it stays
    gate = _stage_text("gate")
    assert "treat it as `escalate` instead" in gate
    assert "If the re-loop would exceed `{workflow.max_turns_per_story}`" in gate


def test_story_token_budget_deprecated_in_place() -> None:
    """The key stays accepted and no-op, and the contract surfaces say so."""
    customize = _CUSTOMIZE.read_text(encoding="utf-8")
    assert re.search(r"^story_token_budget\s*=\s*1500000\s*$", customize, re.M), (
        "removing or renaming the key is a contract break; it stays assigned"
    )
    lines = customize.splitlines()
    idx = next(i for i, l in enumerate(lines) if l.startswith("story_token_budget"))
    preceding = []
    while idx > 0 and lines[idx - 1].lstrip().startswith("#"):
        idx -= 1
        preceding.insert(0, lines[idx])
    comment = "\n".join(preceding)
    assert "DEPRECATED" in comment and "max_turns_per_story" in comment, (
        "the shipped key must carry a deprecation comment pointing at its replacement"
    )

    stability = _STABILITY.read_text(encoding="utf-8")
    workflow_section = stability[stability.index("### The `[workflow]` customize.toml keys"):]
    workflow_section = workflow_section[: workflow_section.index("\n### ")]
    assert "`story_token_budget`" in workflow_section, (
        "the key stays enumerated in the supported override surface"
    )
    assert "deprecated" in workflow_section.lower()
    assert "no-op" in workflow_section.lower()

    # The note must be IN the changelog, not necessarily under [Unreleased].
    # It shipped in 1.0.0 and now sits under that release, which is where a
    # reader looks for what 1.0.0 deprecated. Asserting [Unreleased] only held
    # while that block was never drained between releases - the entry had simply
    # never been filed to the version it went out in.
    changelog = _CHANGELOG.read_text(encoding="utf-8")
    assert "### Deprecated" in changelog, (
        "a [workflow] key gets a deprecation note in the changelog before changing"
    )
    # More than one release can carry a "### Deprecated" section (the --parallel
    # retirement added one), so scan them all for THE story_token_budget note,
    # which names its replacement.
    sections = []
    idx = 0
    while (idx := changelog.find("### Deprecated", idx)) != -1:
        nxt = changelog.find("\n### ", idx + 1)
        sections.append(changelog[idx:] if nxt == -1 else changelog[idx:nxt])
        idx += 1
    assert any(
        "story_token_budget" in s and "max_turns_per_story" in s for s in sections
    ), "no Deprecated section names story_token_budget with its replacement"


def test_a_stop_waiting_on_background_work_still_counts(tmp_path: Path) -> None:
    """The count is responses: a Stop that ends a wait counts like any other.

    The hook cannot tell an acknowledgement from work (its input has no tool
    calls), so it must not skip a Stop because work is still in flight or the
    final text is short: that would let a story that keeps a task running spend
    responses the ceiling never sees."""
    env = {"ULTRACODE_IMPL_ARTIFACTS": str(tmp_path), "ULTRACODE_STORY_ID": "s1", "ULTRACODE_MAX_TURNS": "25"}
    waiting = {
        "hook_event_name": "Stop",
        "cwd": str(tmp_path),
        "stop_hook_active": False,
        "last_assistant_message": "The sweep is still running.",
        "background_tasks": [{"id": "t1", "type": "shell", "status": "running", "description": "full sweep"}],
        "session_crons": [],
    }
    for n, event in enumerate(
        (waiting, {**waiting, "last_assistant_message": ""}, {**waiting, "background_tasks": []}), start=1
    ):
        code, out = _run(event, tmp_path, env)
        assert code == 0 and out is None
        assert json.loads((tmp_path / ".budget-s1.json").read_text())["turns"] == n


def test_hook_docstring_says_why_a_waiting_stop_counts() -> None:
    doc = ast.get_docstring(ast.parse(HOOK.read_text(encoding="utf-8"))) or ""
    lower = " ".join(doc.lower().split())
    assert "only acknowledged a background task's notification" in lower
    assert "cannot tell waiting from work" in lower
