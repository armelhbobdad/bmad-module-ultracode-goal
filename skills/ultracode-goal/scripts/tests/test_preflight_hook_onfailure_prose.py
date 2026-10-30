#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""The guard is armed to refuse a tool call when it fails, and only the guard.

Claude Code reads a hook that cannot start, exits with a code other than 0 or
2, or times out as no objection, so the tool call runs unchecked. From 2.1.295
a command hook item that carries `"onFailure": "block"` makes each of those a
refusal instead. Nothing in UCG writes the hook entries: the conductor writes
them by following references/preflight.md step 5's Hooks bullet, so the
setting exists exactly as far as that bullet spells it. These checks pin:

- the item templates in the Hooks bullet: the guard's carries
  `"onFailure": "block"` beside `"type"` and `"command"`, and the Stop budget
  hook's carries no `onFailure` (Claude Code ignores it on Stop, and the
  budget hook never blocks by design);
- what the setting does, its exact lower-case value (another value drops the
  whole item, so no guard runs), and its cost under the all-tools matcher;
- the no-write equality list and the assertion naming it, so a 3.x arming
  without it is rewritten rather than kept;
- the resume route in execute.md for a run a 3.x release armed: re-merge
  through the Hooks bullet alone, replace never append, purge nothing, then
  assert again;
- the sentence that said a crashing hook lets the command through, restated;
- the step-1 checks list against the keys build_report emits.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_preflight_hook_onfailure_prose.py -v
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REFERENCES = SCRIPTS.parent / "references"
PREFLIGHT = REFERENCES / "preflight.md"
EXECUTE = REFERENCES / "execute.md"
PREFLIGHT_CHECK = SCRIPTS / "preflight_check.py"
REPO_ROOT = SCRIPTS.parents[2]
SECURITY = REPO_ROOT / "SECURITY.md"
TROUBLESHOOTING = REPO_ROOT / "docs" / "troubleshooting.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _hooks_bullet(text: str | None = None) -> str:
    text = _read(PREFLIGHT) if text is None else text
    start = text.index("- **Hooks.**")
    end = text.index("\n- **Allowlist.**", start)
    return text[start:end]


# An inline code span holding one hook item, as the bullet writes it.
_ITEM = re.compile(r'`(\{"type": "command".*?\})`')


def _items(bullet: str) -> dict[str, dict]:
    """The hook item templates in the bullet, keyed by the script each runs."""
    found: dict[str, dict] = {}
    for raw in _ITEM.findall(bullet):
        item = json.loads(raw)
        for script in ("guard_pretooluse.py", "budget_stop.py"):
            if script in item["command"]:
                assert script not in found, f"two templates for {script}"
                found[script] = item
    return found


def _arms_only_the_guard_with_block(bullet: str) -> bool:
    """The guard template carries exactly "block"; the Stop template none."""
    items = _items(bullet)
    guard, budget = items.get("guard_pretooluse.py"), items.get("budget_stop.py")
    if guard is None or budget is None:
        return False
    return guard.get("onFailure") == "block" and guard.get("type") == "command" and "onFailure" not in budget


# --- the item templates ------------------------------------------------------


def test_the_hooks_bullet_writes_the_guard_item_with_on_failure_block():
    items = _items(_hooks_bullet())
    guard = items["guard_pretooluse.py"]
    assert guard == {
        "type": "command",
        "command": "<env> uv run {skill-root}/scripts/hooks/guard_pretooluse.py",
        "onFailure": "block",
    }
    assert _arms_only_the_guard_with_block(_hooks_bullet())


def test_the_hooks_bullet_writes_the_stop_item_without_on_failure():
    budget = _items(_hooks_bullet())["budget_stop.py"]
    assert budget == {"type": "command", "command": "<env> uv run {skill-root}/scripts/hooks/budget_stop.py"}
    flat = _flat(_hooks_bullet())
    assert "the budget hook's item carries no `onFailure` key" in flat
    assert "The Stop budget hook carries no `onFailure`: Claude Code ignores the key on `Stop`" in flat
    assert "the budget hook never blocks a stop by design" in flat


@pytest.mark.parametrize(
    "old,new",
    [
        pytest.param('guard_pretooluse.py", "onFailure": "block"}', 'guard_pretooluse.py"}', id="guard-without-it"),
        pytest.param('guard_pretooluse.py", "onFailure": "block"}', 'guard_pretooluse.py", "onFailure": "Block"}', id="wrong-case"),
        pytest.param(
            'guard_pretooluse.py", "onFailure": "block"}', 'guard_pretooluse.py", "onFailure": "continue"}', id="continue"
        ),
        pytest.param('budget_stop.py"}', 'budget_stop.py", "onFailure": "block"}', id="on-stop-too"),
    ],
)
def test_the_template_predicate_rejects_a_drifted_template(old: str, new: str):
    """Twin: the predicate is not vacuous. Each mutant of the live bullet is
    a way the arming could drift: the 3.x item, a value Claude Code drops the
    item for, the value that lets a crash through, and the key on Stop."""
    live = _hooks_bullet()
    assert live.count(old) == 1, old
    mutant = live.replace(old, new)
    assert not _arms_only_the_guard_with_block(mutant)


def test_the_template_sits_in_the_hooks_bullet_not_merely_in_the_file():
    """Locality: the conductor arms from this bullet, so the template must be
    there and nowhere it would be read as a second, different shape."""
    text = _read(PREFLIGHT)
    bullet = _hooks_bullet(text)
    assert text.count('"onFailure": "block"}') == bullet.count('"onFailure": "block"}') == 1


# --- what the setting does, and what it costs --------------------------------


def test_the_bullet_says_what_the_setting_does_and_without_it():
    flat = _flat(_hooks_bullet())
    for clause in (
        "Claude Code refuses the tool call when the guard cannot start (`uv` missing from `PATH`, say), "
        "crashes, exits with a code other than 0 or 2, or times out.",
        "Without it each of those lets the call run unchecked",
        "Claude Code honors the key from 2.1.295, the minimum step 1's `cc_version` check enforces",
        'Write the value exactly `"block"`, in lower case',
        "so a mistyped one leaves no guard at all",
    ):
        assert clause in flat, clause


def test_the_bullet_states_the_cost_and_the_fix_made_outside_the_session():
    flat = _flat(_hooks_bullet())
    assert "A guard that cannot run refuses every tool call, Read and Edit included" in flat
    assert "the fix is made outside the session: put `uv` back on `PATH`" in flat
    assert "remove the guard item from `.claude/settings.local.json` by hand as SECURITY.md describes" in flat


def test_the_no_write_comparison_and_the_assertion_name_the_setting():
    """Without it in the equality list, a 3.x arming reads as matching and is
    kept instead of rewritten; without it in the assertion, nothing checks it."""
    flat = _flat(_hooks_bullet())
    no_write = flat[flat.index("A merge that would change nothing makes no write") :]
    no_write = no_write[: no_write.index("assert instead of writing")]
    assert "the guard item's `\"onFailure\": \"block\"`" in no_write
    assert "every guard item carries `\"onFailure\": \"block\"`" in flat
    assert "(branch, both hooks under their own events, matcher form, the guard's `onFailure`, injected env," in flat


def test_the_crash_sentence_states_the_new_behaviour():
    preflight = _flat(_read(PREFLIGHT))
    security = _flat(_read(SECURITY))
    assert "a hook that crashes makes no decision" not in preflight.lower()
    assert "a hook that crashes makes no decision" not in security.lower()
    assert (
        "What it cannot catch itself (an interpreter or `uv` that cannot start, a timeout) Claude Code refuses, "
        "under the guard item's `\"onFailure\": \"block\"` above" in preflight
    )
    assert "preflight arms the guard's hook item with `\"onFailure\": \"block\"`" in security
    assert "a guard that cannot run refuses every tool call, Read and Edit included" in security


def test_troubleshooting_names_the_message_and_the_recovery():
    text = _read(TROUBLESHOOTING)
    section = text[text.index("## Every tool call is refused") :]
    section = _flat(section[: section.index("\n## ", 1)])
    assert 'blocking because onFailure is "block"' in section
    assert "`guard_pretooluse.py`" in section
    assert "Fix it from outside the session" in section
    assert 'REF["See: Every tool call is refused"]' in text


# --- the resume route --------------------------------------------------------

_ROUTE_HEAD = "**A hooks reason is fixed in place, not by a return to Stage 2.**"


def _resume_route(text: str | None = None) -> str:
    text = _read(EXECUTE) if text is None else text
    return next(p for p in text.split("\n\n") if p.startswith(_ROUTE_HEAD))


def _routes_a_3x_arming(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return all(
        clause in flat
        for clause in (
            'the guard not armed with `"onFailure": "block"`',
            "apply `references/preflight.md` step 5's **Hooks** bullet alone",
            "(replace, never append)",
            "every run armed by UCG 3.x or earlier carries",
            "Purge nothing",
            "Run none of preflight's checks, remediation or launch gate",
            "Then run the same `--assert-armed` call again, and drive the story only once it exits 0.",
        )
    )


def test_execute_gives_a_3x_arming_a_re_merge_route_on_resume():
    assert _routes_a_3x_arming(_resume_route())


@pytest.mark.parametrize(
    "clause",
    [
        "(replace, never append)",
        "Purge nothing",
        "Then run the same `--assert-armed` call again, and drive the story only once it exits 0.",
    ],
)
def test_the_route_predicate_rejects_a_dropped_clause(clause: str):
    paragraph = _resume_route()
    assert clause in paragraph
    assert not _routes_a_3x_arming(paragraph.replace(clause, ""))


def test_the_route_follows_the_sweep_and_the_precondition_points_at_it():
    """It sits right after the sweep that produces its reasons, and the
    precondition list that sends hooks 'to Stage 2' names it."""
    text = _read(EXECUTE)
    paragraphs = text.split("\n\n")
    index = next(i for i, p in enumerate(paragraphs) if p.startswith(_ROUTE_HEAD))
    assert paragraphs[index - 1].startswith("**The re-assertion sweep is one script call")
    preconditions = next(p for p in paragraphs if p.startswith("Preconditions (asserted, not assumed)"))
    assert "(on a resume, the hooks by re-merging them through Stage 2's step 5 **Hooks** bullet alone" in preconditions


def test_the_preflight_bullet_hands_a_resume_to_that_route():
    flat = _flat(_hooks_bullet())
    assert (
        "a resume, which never reaches this stage, re-merges through this bullet when its `--assert-armed` "
        "names the missing key (`references/execute.md`, the re-assertion sweep)" in flat
    )


def test_the_assert_armed_reason_names_the_same_route():
    """The conductor reads the reason first: it names the bullet and the rules."""
    spec = importlib.util.spec_from_file_location("preflight_check_onfailure", PREFLIGHT_CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reason = module._on_failure_reason([None])
    assert "(found: missing)" in reason
    assert "Re-merge the hooks as preflight.md step 5's Hooks bullet says" in reason
    assert "replace, never append; on a resume purge nothing" in reason


# --- the step-1 checks list ----------------------------------------------------


def test_step1_lists_every_check_key_build_report_emits(tmp_path: Path):
    """preflight.md step 1 spells the `checks` keys; the new version flag is one."""
    text = _read(PREFLIGHT)
    block = text[text.index(" checks: {") : text.index("}}", text.index(" checks: {"))]
    listed = {key.strip() for key in block.split("{", 1)[1].replace("\n", " ").split(",")}
    proc = subprocess.run(
        [
            sys.executable,
            str(PREFLIGHT_CHECK),
            "--project-root",
            str(tmp_path),
            "--epic",
            "1",
            "--tea-config",
            str(tmp_path / "tea.yaml"),
            "--impl-artifacts",
            str(tmp_path / "impl"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.stdout, proc.stderr
    emitted = set(json.loads(proc.stdout)["checks"])
    assert "hook_onfailure_ok" in listed
    assert listed == emitted
