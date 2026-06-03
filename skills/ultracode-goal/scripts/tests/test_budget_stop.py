#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Exercise the budget Stop hook via the real stdin/stdout contract.

Invariant under test: an overrun NEVER blocks the stop (no decision:"block");
it writes an escalation marker and surfaces a systemMessage, exit 0."""

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "budget_stop.py"


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
    assert "systemMessage" in out
    assert (impl / ".escalation-S1.md").is_file()


def test_token_overrun_escalates(tmp_path: Path) -> None:
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
    assert out is not None and "systemMessage" in out
    assert (impl / ".escalation-S2.md").is_file()
