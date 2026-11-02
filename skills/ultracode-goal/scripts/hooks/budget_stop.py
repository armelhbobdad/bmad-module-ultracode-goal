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
An empty or unreadable marker (one that is not UTF-8 included) still counts
against "unknown", because a story may be in flight behind it, and so does a
story id that holds a NUL byte, which no counter's file name can, or a slash
or a backslash, which would name the counter and the turn-ceiling marker in
another folder (outside the state dir, with `..` steps after it), or bytes
that are not UTF-8 (an ULTRACODE_STORY_ID's), which the marker's text cannot
hold, or a character the file system's encoding cannot spell, or that is too
long for a file name: the marker's name, the longer of the two, would pass
255 bytes. An id whose marker's whole path would pass the longest path the
system takes counts against "unknown" too, when unknown's marker path does
not; the system says so with ENAMETOOLONG, or on Windows with error 206, and
where it answers otherwise (Windows may say the path is not found), the turn
counts against the story and the marker's write says on stderr why it failed.

The hook reads and writes only a regular file at the counter's and the
marker's names. It opens the counter without following a symlink at its name
or waiting on a FIFO there, and writes each through a new file in the state
dir renamed onto the name, so neither write goes through a link put there.
Where it cannot make or rename that file (a state dir it may change files in
but not add names to, or a path the new file's longer name takes past the
system's longest), it writes into the file at the name instead, opened the
same way, and only into a regular file that no other name links to. A
name that holds a symlink, a FIFO, a folder or any other file that is not a
regular one is left as it is and said on stderr: at the counter's, the turn
counts against "unknown" (and goes uncounted when unknown's counter holds one
too); at the marker's, no marker is written, and the overrun message says so.

The hook exits 0 whatever it is given. Claude Code ignores `onFailure` on
Stop, so a budget hook that exited 1 would only print a hook error, and the
turn it should have counted would be lost. A Stop event that is not a JSON
object, or that is nested past what Python reads, reads as no event: the
injected ULTRACODE_* values still name the state dir and the story, so the
turn is counted. Each such read-past is said on stderr, which Claude Code
shows in its debug output, and any other error ends the hook with exit 0 and
its name on stderr.

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

import errno
import json
import os
import stat
import sys
from pathlib import Path
from typing import NoReturn

DEFAULT_MAX_TURNS = 25

# The longest file name, in bytes: NAME_MAX on Linux and macOS. Windows takes
# 255 UTF-16 units, so a name within 255 UTF-8 bytes fits there too.
_NAME_MAX = 255

# Open the counter without following a symlink at its name or waiting on a
# FIFO there, where the system has the flags (Windows has neither, nor FIFOs,
# and _regular_or_absent turns a link away first).
_READ_FLAGS = (
    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
)
# Create the new file a write goes through, refusing any file already there.
_CREATE_FLAGS = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
)
# Open the file at a name to write into it where no new file can be made
# beside it: create it if absent, but follow no symlink at the name and do
# not wait on a FIFO there, as the read does.
_IN_PLACE_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_BINARY", 0)
)
# Windows's ERROR_FILENAME_EXCED_RANGE: a path longer than it takes.
_WINDOWS_PATH_TOO_LONG = 206


class _NotRegular(Exception):
    """A name holds a symlink or a file that is not a regular one."""


def _warn(message: str) -> None:
    """Say on stderr what the hook read past, and go on."""
    print(f"budget_stop: {message}", file=sys.stderr)


def _read_event() -> dict:
    """The Stop event, or {} for one that is absent or cannot be read as a JSON object."""
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except (ValueError, RecursionError) as exc:
        # ValueError covers JSON that does not parse and stdin that is not
        # text; RecursionError, JSON nested past what Python reads.
        _warn(f"the Stop event is not JSON it can read ({type(exc).__name__}); reading it as no event")
        return {}
    if not isinstance(event, dict):
        _warn(f"the Stop event is a JSON {type(event).__name__}, not an object; reading it as no event")
        return {}
    return event


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
    if not sid and impl is not None:
        marker = impl / ".current-story"
        if not marker.is_file():
            return None
        # A marker that is not UTF-8 is unreadable too: raising here would
        # end the hook before it counted the turn.
        try:
            sid = marker.read_text(encoding="utf-8").strip() or "unknown"
        except (OSError, UnicodeDecodeError):
            return "unknown"
    if "\0" in sid:
        # Neither the counter nor the marker could be named after it.
        _warn("the story id holds a NUL byte, which no file name can; counting the turn against unknown")
        return "unknown"
    if "/" in sid or "\\" in sid:
        # The counter and the marker are named after it inside impl, and a
        # separator would put them in another folder: with `..` steps after
        # it, outside impl. A backslash is a separator on Windows only, but
        # no story id holds one, so it counts the same way everywhere.
        _warn(
            "the story id holds a path separator, which would name its counter in another folder; "
            "counting the turn against unknown"
        )
        return "unknown"
    if not sid:
        return None
    try:
        sid.encode("utf-8")
    except UnicodeEncodeError:
        # An ULTRACODE_STORY_ID holding bytes that are not UTF-8 decodes to
        # surrogates: its counter could be named, but the marker's UTF-8 text
        # could not hold the id, so the ceiling never wrote one.
        _warn(
            "the story id holds bytes that are not UTF-8, which its turn-ceiling marker cannot hold; "
            "counting the turn against unknown"
        )
        return "unknown"
    try:
        name_bytes = len(os.fsencode(f".escalation-{sid}.md"))
    except UnicodeError:
        _warn(
            "the story id holds a character the file system's encoding cannot spell, so no counter "
            "can be named after it; counting the turn against unknown"
        )
        return "unknown"
    if name_bytes > _NAME_MAX:
        # The marker's name is two bytes longer than the counter's, so an id
        # that fits it fits both. Past it, the marker could not be written,
        # and two bytes further the counter could not be read or written.
        _warn(
            f"the story id is too long for a file name: its turn-ceiling marker's name would pass "
            f"{_NAME_MAX} bytes; counting the turn against unknown"
        )
        return "unknown"
    if (
        impl is not None
        and _path_too_long(impl / f".escalation-{sid}.md")
        and not _path_too_long(impl / ".escalation-unknown.md")
    ):
        # The same for the whole path, when unknown's marker still fits: a
        # shorter id than "unknown" would gain nothing from it.
        _warn(
            "the path of the story's turn-ceiling marker would pass the longest path the system takes; "
            "counting the turn against unknown"
        )
        return "unknown"
    return sid


def _path_too_long(path: Path) -> bool:
    """Whether the system refuses path as longer than it takes: ENAMETOOLONG,
    or Windows's "filename or extension is too long". Any other answer, no
    such file included, is False."""
    try:
        os.lstat(path)
    except OSError as exc:
        return exc.errno == errno.ENAMETOOLONG or getattr(exc, "winerror", None) == _WINDOWS_PATH_TOO_LONG
    except ValueError:
        return False
    return False


def _regular_or_absent(path: Path) -> bool:
    """Whether path names a regular file or nothing; False for a symlink, a
    FIFO, a folder or any other file, which the hook neither reads nor writes
    through. An error that says neither (no access, say) is left to the read
    or the write to report."""
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except (OSError, ValueError):  # nothing there (FileNotFoundError) included
        return True


def _read_text(path: Path) -> str:
    """The UTF-8 text of the regular file at path, opened without following a
    symlink at its name or waiting on a FIFO there; _NotRegular for any other
    file, FileNotFoundError for none."""
    fd = os.open(path, _READ_FLAGS)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise _NotRegular(path.name)
        chunks = []
        while chunk := os.read(fd, 65536):
            chunks.append(chunk)
    finally:
        os.close(fd)
    return b"".join(chunks).decode("utf-8")


def _write_text(path: Path, text: str) -> None:
    """Write text to path through a new file in its folder, renamed onto the
    name: whatever sits at the name is replaced, never written through. The
    new file's name starts with `.budget-` and ends in `.tmp`, so preflight's
    purge of `.budget-*` takes one a crash left behind.

    Where that fails (a folder the hook may change files in but not add names
    to, or a path the new file's longer name takes past the longest the
    system takes), it writes into the file at the name instead, through
    _write_in_place, and raises the first error when that fails too."""
    data = text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_through_new_file(path, data)
    except OSError as exc:
        try:
            _write_in_place(path, data)
        except (OSError, _NotRegular):
            raise exc from None


def _write_in_place(path: Path, data: bytes) -> None:
    """Write data into the file at path, or into a new one there, opened
    without following a symlink at its name or waiting on a FIFO there. It
    writes only into a regular file no other name links to (a hard link to a
    file outside the state dir, say), raising _NotRegular for any other, and
    truncates it only once fstat has shown that."""
    fd = os.open(path, _IN_PLACE_FLAGS, 0o666)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise _NotRegular(path.name)
        os.ftruncate(fd, 0)
        while data:
            data = data[os.write(fd, data) :]
    finally:
        os.close(fd)


def _write_through_new_file(path: Path, data: bytes) -> None:
    temp = path.parent / f".budget-{os.getpid()}-{os.urandom(4).hex()}.tmp"
    fd = os.open(temp, _CREATE_FLAGS, 0o666)
    try:
        try:
            while data:
                data = data[os.write(fd, data) :]
        finally:
            os.close(fd)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _load_state(path: Path) -> dict:
    try:
        data = json.loads(_read_text(path))
        return {"turns": int(data.get("turns", 0))}
    except FileNotFoundError:
        return {"turns": 0}
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, RecursionError, _NotRegular) as exc:
        # Not a count it can read (not JSON, not an object, nested past what
        # Python reads, an infinite or absent number, or a link or a FIFO put
        # at the name since _regular_or_absent looked): it restarts at 0.
        _warn(f"{path.name} is not a count it can read ({type(exc).__name__}); counting from 0")
        return {"turns": 0}


def _save_state(path: Path, state: dict) -> None:
    try:
        _write_text(path, json.dumps(state))
    except (OSError, ValueError) as exc:
        _warn(f"could not write {path.name} ({type(exc).__name__}); this turn is not counted")


def _not_regular_note(path: Path, outcome: str) -> None:
    _warn(f"{path.name} is a symlink or not a regular file, which it neither reads nor writes through; {outcome}")


def main() -> None:
    event = _read_event()
    cwd = event.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        _warn(f"the Stop event's cwd is a JSON {type(cwd).__name__}, not a string; reading it as no cwd")
        cwd = None
    impl = _impl_artifacts(cwd)

    if impl is None:
        _emit(None)  # nowhere to keep state; proceed silently

    story = _current_story(impl)
    if story is None:
        _emit(None)  # no story yet: not a story's turn to count
    max_turns = _int_env("ULTRACODE_MAX_TURNS", DEFAULT_MAX_TURNS)

    state_path = impl / f".budget-{story}.json"
    if story != "unknown" and not _regular_or_absent(state_path):
        _not_regular_note(state_path, "counting the turn against unknown")
        story = "unknown"
        state_path = impl / f".budget-{story}.json"
    if not _regular_or_absent(state_path):
        _not_regular_note(state_path, "this turn is not counted")
        _emit(None)
    state = _load_state(state_path)
    state["turns"] += 1
    _save_state(state_path, state)

    if state["turns"] < max_turns:
        _emit(None)

    detail = f"turns {state['turns']}/{max_turns}"

    marker = impl / f".escalation-{story}.md"
    written = False
    if not _regular_or_absent(marker):
        _not_regular_note(marker, "no marker is written")
    else:
        try:
            _write_text(
                marker,
                f"# Turn ceiling reached: story {story}\n\n"
                f"Story turn ceiling reached ({detail}). Unless this story advances at "
                f"its gate, UltraCode-Goal escalates it: re-scope, split, or hand off. "
                f"If it advances, this is a sizing note, not an escalation. A Stop hook "
                f"cannot interrupt a session mid-turn, so this marker is a record: the "
                f"conductor's checks against this count, at a resume and before each "
                f"re-loop, are what stop the story.\n",
            )
            written = True
        except (OSError, ValueError) as exc:
            _warn(f"could not write {marker.name} ({type(exc).__name__})")

    where = f"Marker written to {marker}." if written else f"No marker was written at {marker}: stderr says why."
    _emit(
        f"UltraCode-Goal: story {story} reached its turn ceiling ({detail}). "
        f"{where} It escalates if its gate does not advance it; "
        f"if the gate advances it, the overrun becomes a sizing note."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001  (exit 1 here is a lost turn and a hook error, nothing more)
        _warn(f"stopped on {type(exc).__name__}: {exc}; the stop proceeds")
        sys.exit(0)
