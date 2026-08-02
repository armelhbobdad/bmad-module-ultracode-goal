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
    assert "ULTRACODE_MAX_TURNS={workflow.max_turns_per_story}" in step5

    # the re-loop-becomes-escalate rule is one of the two real bounds; it stays
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
    deprecated = changelog[changelog.index("### Deprecated"):]
    nxt = deprecated.find("\n### ", 1)
    deprecated = deprecated if nxt == -1 else deprecated[:nxt]
    assert "story_token_budget" in deprecated
    assert "max_turns_per_story" in deprecated
