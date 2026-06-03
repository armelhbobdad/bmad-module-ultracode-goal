#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""UltraCode-Goal budget Stop hook (Claude Code hook).

Belt-and-suspenders to the in-/goal-condition "stop after N turns" clause:
counts Stop events (turns) and accumulated tokens for the current story against
max_turns_per_story / story_token_budget. On overrun it writes an escalation
marker and surfaces a clear message, then LETS THE STOP PROCEED.

KNOWN LIMITATION: a Stop hook fires only when Claude is *already* trying to stop.
It cannot interrupt a /goal condition mid-turn — it can record the overrun and
warn, but the budget ceiling is ultimately advisory at this layer. The hard
runaway guard is the gate_eval re-loop budget plus the /goal stop-after-N clause;
this hook is the third, defensive layer.

Hook contract (reads one JSON object on stdin):
  in : {session_id, cwd, hook_event_name:"Stop", ...}
  out: exit 0. We never set decision:"block" (we WANT the stop to proceed);
       on overrun we emit {systemMessage, suppressOutput:false} so the user
       sees the escalation. JSON is best-effort; absence is also valid.

State + config (env wins so the conductor injects per-story values):
  ULTRACODE_IMPL_ARTIFACTS    state dir; default <cwd>/_bmad-output/implementation-artifacts
  ULTRACODE_STORY_ID          current story id; else <impl>/.current-story
  ULTRACODE_MAX_TURNS         int; default 25
  ULTRACODE_TOKEN_BUDGET      int; default 1500000
  ULTRACODE_TURN_TOKENS       int tokens to add this turn (optional; 0 if unknown)

State file: <impl>/.budget-<story>.json  {turns:int, tokens:int}
Escalation marker: <impl>/.escalation-<story>.md
"""

import json
import os
import sys
from pathlib import Path

DEFAULT_MAX_TURNS = 25
DEFAULT_TOKEN_BUDGET = 1_500_000


def _read_event() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _emit(message: str | None) -> None:
    """Exit 0 and let the stop proceed; surface a message only on overrun."""
    if message:
        print(json.dumps({"systemMessage": message, "suppressOutput": False}))
    sys.exit(0)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _impl_artifacts(cwd: str | None) -> Path | None:
    env = os.environ.get("ULTRACODE_IMPL_ARTIFACTS")
    if env:
        return Path(env)
    if cwd:
        return Path(cwd) / "_bmad-output" / "implementation-artifacts"
    return None


def _current_story(impl: Path | None) -> str:
    sid = os.environ.get("ULTRACODE_STORY_ID")
    if sid:
        return sid.strip()
    if impl is not None:
        marker = impl / ".current-story"
        if marker.is_file():
            try:
                return marker.read_text(encoding="utf-8").strip() or "unknown"
            except OSError:
                return "unknown"
    return "unknown"


def _load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "turns": int(data.get("turns", 0)),
            "tokens": int(data.get("tokens", 0)),
        }
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return {"turns": 0, "tokens": 0}


def _save_state(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass  # state best-effort; never crash a Stop hook


def main() -> None:
    event = _read_event()
    cwd = event.get("cwd")
    impl = _impl_artifacts(cwd)

    if impl is None:
        _emit(None)  # nowhere to keep state; proceed silently

    story = _current_story(impl)
    max_turns = _int_env("ULTRACODE_MAX_TURNS", DEFAULT_MAX_TURNS)
    token_budget = _int_env("ULTRACODE_TOKEN_BUDGET", DEFAULT_TOKEN_BUDGET)
    turn_tokens = _int_env("ULTRACODE_TURN_TOKENS", 0)

    state_path = impl / f".budget-{story}.json"
    state = _load_state(state_path)
    state["turns"] += 1
    state["tokens"] += max(turn_tokens, 0)
    _save_state(state_path, state)

    over_turns = state["turns"] >= max_turns
    over_tokens = token_budget > 0 and state["tokens"] >= token_budget
    if not (over_turns or over_tokens):
        _emit(None)

    breached = []
    if over_turns:
        breached.append(f"turns {state['turns']}/{max_turns}")
    if over_tokens:
        breached.append(f"tokens {state['tokens']}/{token_budget}")
    detail = "; ".join(breached)

    marker = impl / f".escalation-{story}.md"
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            f"# Budget escalation — story {story}\n\n"
            f"Story budget exceeded ({detail}). UltraCode-Goal stops this story "
            f"and escalates: re-scope, split, or hand off. A Stop hook cannot "
            f"interrupt a /goal condition mid-turn, so treat this as advisory — "
            f"the deterministic guard is the gate_eval re-loop budget.\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    _emit(
        f"UltraCode-Goal budget exceeded for story {story} ({detail}). "
        f"Escalation marker written to {marker}. Stop and escalate this story; "
        f"do not keep re-looping."
    )


if __name__ == "__main__":
    main()
