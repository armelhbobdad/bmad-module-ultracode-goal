#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""UltraCode-Goal turn-budget Stop hook (Claude Code hook).

Counts Stop events (turns) for the current story against max_turns_per_story.
On overrun it writes its turn-ceiling marker and surfaces a clear message, then
LETS THE STOP PROCEED. The conductor promotes that marker to a budget-overrun
escalation only when the story's gate escalates it on this count; a story
that advances gets a sizing note instead (references/execute.md).

Turns are the only thing counted here: this layer sees one event per stop and
no usage totals, so any other ceiling could never fire and none is claimed.

A runaway story is bounded by three layers, in order of authority:
  1. the "…or stop after N turns" clause inside a /goal condition, but only
     when an operator started a /goal whose own condition carries one, and then
     it bounds the session rather than the story: the conductor has no way to
     start a /goal itself, so in most sessions this layer is absent;
  2. the gate's re-loop budget: before each re-loop the conductor reads the
     turn count this hook keeps, and a reloop that would exceed
     max_turns_per_story becomes an escalate. That count advances once per
     Stop, so it cannot see re-loops spent inside a single response;
  3. this hook, as RECORDER. A Stop hook fires only when Claude is *already*
     trying to stop, so it cannot interrupt a /goal condition mid-turn. It
     records the overrun and warns; it is advisory end to end and never blocks.

A Stop with no current story at all (no ULTRACODE_STORY_ID and no
.current-story marker, as before a project's first story's step 0 once the
hooks are armed) is not a story's turn: nothing is counted and nothing is
written, so the hook never leaves a stray .budget-unknown.json in the tree.
An empty or unreadable marker still counts against "unknown", because a
story may be in flight behind it.

Every other Stop counts, including one that ends a response that only
acknowledged a background task's notification. The Stop input carries the
response's final text and the tasks still in flight, not its tool calls, and
the transcript may not hold the final message yet, so the hook cannot tell
waiting from work and does not try: skipping a Stop on a guess would let a
story that keeps a task running spend responses the ceiling never sees.
Execute keeps waits few instead (references/execute.md, "Waiting spends
turns").

Hook contract (reads one JSON object on stdin):
  in : {session_id, cwd, hook_event_name:"Stop", ...}
  out: exit 0. We never set decision:"block" (we WANT the stop to proceed);
       on overrun we emit {systemMessage, suppressOutput:false} so the user
       sees the overrun. JSON is best-effort; absence is also valid.

State + config (env wins so the conductor injects per-story values):
  ULTRACODE_IMPL_ARTIFACTS    state dir; default <cwd>/_bmad-output/implementation-artifacts
  ULTRACODE_STORY_ID          current story id; else <impl>/.current-story
  ULTRACODE_MAX_TURNS         int; default 25

Any other ULTRACODE_* variable a conductor still injects is ignored here.

State file: <impl>/.budget-<story>.json  {turns:int}
Turn-ceiling marker: <impl>/.escalation-<story>.md
"""

import json
import os
import sys
from pathlib import Path
from typing import NoReturn

DEFAULT_MAX_TURNS = 25


def _read_event() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _emit(message: str | None) -> NoReturn:
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


def _current_story(impl: Path | None) -> str | None:
    """The current story id, "unknown" for an unusable marker, None for none at all."""
    sid = (os.environ.get("ULTRACODE_STORY_ID") or "").strip()
    if sid:
        return sid
    if impl is not None:
        marker = impl / ".current-story"
        if marker.is_file():
            try:
                return marker.read_text(encoding="utf-8").strip() or "unknown"
            except OSError:
                return "unknown"
    return None


def _load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"turns": int(data.get("turns", 0))}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return {"turns": 0}


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
    if story is None:
        _emit(None)  # no story yet: not a story's turn to count
    max_turns = _int_env("ULTRACODE_MAX_TURNS", DEFAULT_MAX_TURNS)

    state_path = impl / f".budget-{story}.json"
    state = _load_state(state_path)
    state["turns"] += 1
    _save_state(state_path, state)

    if state["turns"] < max_turns:
        _emit(None)

    detail = f"turns {state['turns']}/{max_turns}"

    marker = impl / f".escalation-{story}.md"
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            f"# Turn ceiling reached: story {story}\n\n"
            f"Story turn ceiling reached ({detail}). Unless this story advances at "
            f"its gate, UltraCode-Goal escalates it: re-scope, split, or hand off. "
            f"If it advances, this is a sizing note, not an escalation. A Stop hook "
            f"cannot interrupt a session mid-turn, so this marker is a record: the "
            f"conductor's checks against this count, at a resume and before each "
            f"re-loop, are what stop the story.\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    _emit(
        f"UltraCode-Goal: story {story} reached its turn ceiling ({detail}). "
        f"Marker written to {marker}. It escalates if its gate does not advance it; "
        f"if the gate advances it, the overrun becomes a sizing note."
    )


if __name__ == "__main__":
    main()
