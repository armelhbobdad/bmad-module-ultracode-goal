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

import pytest

HOOK =Path(__file__).resolve().parents[1] / "hooks" / "budget_stop.py"
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


# --- #186: bad input never ends the hook on an error --------------------------
# Claude Code ignores `onFailure` on Stop, so a budget hook that exits 1 is a
# hook error and nothing more: the stop proceeds, and the turn it should have
# counted is lost. These inputs each raised out of the hook before it counted.


def _run_raw(
    stdin: str | bytes, cwd: Path, env_extra: dict, timeout: float | None = None
) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_extra}
    data = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
    return subprocess.run(
        [sys.executable, str(HOOK)], input=data, cwd=cwd, capture_output=True, env=env, timeout=timeout
    )


def _turns(impl: Path, story: str) -> int:
    return json.loads((impl / f".budget-{story}.json").read_text(encoding="utf-8"))["turns"]


@pytest.mark.parametrize(
    "stdin,shown",
    [
        pytest.param("[1, 2]", "not an object", id="array"),
        pytest.param('"Stop"', "not an object", id="string"),
        pytest.param("7", "not an object", id="number"),
        pytest.param("null", "not an object", id="null"),
        pytest.param("[" * 100_000, "RecursionError", id="nested-past-what-python-reads"),
        pytest.param("{not json", "not JSON", id="not-json"),
        pytest.param(b"\xff\xfe{}", "not JSON", id="not-utf8"),
    ],
)
def test_an_event_it_cannot_read_still_counts_the_turn(tmp_path: Path, stdin: str | bytes, shown: str) -> None:
    """The env names the state dir and the story, so the turn is counted
    without the event, and stderr says what was read past."""
    impl = tmp_path / "impl"
    impl.mkdir()
    env = {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "ULTRACODE_STORY_ID": "S1", "ULTRACODE_MAX_TURNS": "25"}
    proc = _run_raw(stdin, tmp_path, env)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == b""
    assert _turns(impl, "S1") == 1
    stderr = proc.stderr.decode("utf-8", "replace")
    assert stderr.startswith("budget_stop: ") and shown in stderr, stderr
    assert "Traceback" not in stderr


def test_an_event_it_cannot_read_with_no_state_dir_exits_zero(tmp_path: Path) -> None:
    """With no event cwd and no ULTRACODE_IMPL_ARTIFACTS there is nowhere to
    count: exit 0, as for any Stop with no state dir."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("ULTRACODE_")}
    proc = subprocess.run([sys.executable, str(HOOK)], input=b"[]", cwd=tmp_path, capture_output=True, env=env)
    assert proc.returncode == 0, proc.stderr
    assert list(tmp_path.iterdir()) == []


def test_a_cwd_that_is_not_a_string_reads_as_no_cwd(tmp_path: Path) -> None:
    impl = tmp_path / "impl"
    impl.mkdir()
    env = {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "ULTRACODE_STORY_ID": "S1"}
    proc = _run_raw(json.dumps({"hook_event_name": "Stop", "cwd": 7}), tmp_path, env)
    assert proc.returncode == 0, proc.stderr
    assert _turns(impl, "S1") == 1


def test_a_story_pointer_holding_a_nul_counts_against_unknown(tmp_path: Path) -> None:
    """No file name holds a NUL byte, so the counter could not be written and
    the hook raised. Such a pointer names no story it can count, so the turn
    counts against `unknown`, as an unreadable pointer's does."""
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / ".current-story").write_bytes(b"S1\x00x\n")
    proc = _run_raw(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)}), tmp_path, _no_story_env(impl, "25"))
    assert proc.returncode == 0, proc.stderr
    assert _turns(impl, "unknown") == 1
    assert "NUL" in proc.stderr.decode("utf-8", "replace")


def test_a_nul_story_at_its_ceiling_still_exits_zero(tmp_path: Path) -> None:
    """The overrun path writes a marker named after the story too."""
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / ".current-story").write_bytes(b"S1\x00x\n")
    proc = _run_raw(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)}), tmp_path, _no_story_env(impl, "1"))
    assert proc.returncode == 0, proc.stderr
    assert (impl / ".escalation-unknown.md").is_file()
    assert "systemMessage" in json.loads(proc.stdout)


@pytest.mark.parametrize("source", ["pointer", "env"])
@pytest.mark.parametrize(
    "story",
    [
        pytest.param("x/../../../escaped", id="dotdot"),
        pytest.param("/../../escaped-abs", id="leading-slash"),
        pytest.param("1/2", id="slash"),
        pytest.param("x\\..\\..\\..\\escaped", id="backslash"),
    ],
)
def test_a_story_id_holding_a_path_separator_counts_against_unknown(tmp_path: Path, story: str, source: str) -> None:
    """The counter and the turn-ceiling marker are named after the story id
    inside the state dir, so an id holding a separator named them in another
    folder: `x/../../../escaped` wrote `<project>/escaped.json`, and
    `<project>/escaped.md` at the ceiling (a backslash does so on Windows).
    Such an id names no story it can count, so the turn counts against
    `unknown`, as a NUL's does, and nothing is written anywhere else."""
    project = tmp_path / "proj"
    impl = project / "_bmad-output" / "implementation-artifacts"
    impl.mkdir(parents=True)
    env = _no_story_env(impl, "1")
    if source == "pointer":
        (impl / ".current-story").write_text(story + "\n", encoding="utf-8")
    else:
        env["ULTRACODE_STORY_ID"] = story
    before = set(tmp_path.rglob("*"))
    proc = _run_raw(json.dumps({"hook_event_name": "Stop", "cwd": str(project)}), project, env)
    assert proc.returncode == 0, proc.stderr
    assert set(tmp_path.rglob("*")) - before == {impl / ".budget-unknown.json", impl / ".escalation-unknown.md"}
    assert _turns(impl, "unknown") == 1
    assert "separator" in proc.stderr.decode("utf-8", "replace")


# A file name holds at most 255 bytes (NAME_MAX on Linux and macOS), and the
# longest name the hook writes is the turn-ceiling marker's, 15 bytes more
# than the story id: `.escalation-<id>.md`.
_LONGEST_ID_BYTES = 255 - len(".escalation-.md")


@pytest.mark.parametrize("source", ["pointer", "env"])
@pytest.mark.parametrize(
    "story",
    [
        pytest.param("1-1-" + "a" * 246, id="250-bytes"),
        pytest.param("1-1-" + "a" * (_LONGEST_ID_BYTES - 3), id="one-byte-past-the-marker"),
        pytest.param("1-1-" + "é" * 119, id="121-characters-242-bytes"),
    ],
)
def test_a_story_id_too_long_for_a_file_name_counts_against_unknown(tmp_path: Path, story: str, source: str) -> None:
    """The counter and the marker are named after the story id, and an id
    too long for either name was never counted: the counter could not be read
    or written (ENAMETOOLONG), every turn was lost with a note on stderr, and
    the ceiling never fired. Such an id names no story it can count, as a
    NUL's or a separator's does, so the turn counts against `unknown`. The
    length is the file system's, in bytes, not in characters."""
    assert len(os.fsencode(f".escalation-{story}.md")) > 255
    impl = tmp_path / "impl"
    impl.mkdir()
    env = _no_story_env(impl, "1")
    if source == "pointer":
        (impl / ".current-story").write_text(story + "\n", encoding="utf-8")
    else:
        env["ULTRACODE_STORY_ID"] = story
    proc = _run_raw(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)}), tmp_path, env)
    assert proc.returncode == 0, proc.stderr
    assert _turns(impl, "unknown") == 1
    assert (impl / ".escalation-unknown.md").is_file()
    assert "systemMessage" in json.loads(proc.stdout)
    assert "too long for a file name" in proc.stderr.decode("utf-8", "replace")


@pytest.mark.skipif(
    sys.platform == "win32", reason="a 255-character name passes the 260-character path limit Windows may keep"
)
def test_the_longest_story_id_a_marker_name_holds_counts_as_itself(tmp_path: Path) -> None:
    """The twin at the bound: an id whose marker name is 255 bytes long is
    counted against itself, and its marker is written at the ceiling."""
    story = "1-1-" + "a" * (_LONGEST_ID_BYTES - 4)
    assert len(os.fsencode(f".escalation-{story}.md")) == 255
    impl = tmp_path / "impl"
    impl.mkdir()
    env = {**_no_story_env(impl, "1"), "ULTRACODE_STORY_ID": story}
    proc = _run_raw(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)}), tmp_path, env)
    assert proc.returncode == 0, proc.stderr
    assert _turns(impl, story) == 1
    assert (impl / f".escalation-{story}.md").is_file()
    assert not (impl / ".budget-unknown.json").exists()


# --- A link or a special file at the counter's or the marker's name ----------
# The hook read and wrote its counter and its marker by name, following a
# symlink there, so one to a file outside the state dir had that file's
# contents replaced (by `{"turns": 1}`, or by the marker text at the ceiling),
# and a FIFO there kept it waiting until Claude Code's hook timeout, with the
# turn uncounted. It reads and writes neither through such a name now.


def _make_special(kind: str, at: Path, target: Path) -> None:
    """Put a symlink to target, a FIFO or a folder at `at`, or skip where the
    system cannot make one."""
    if kind == "symlink":
        try:
            os.symlink(target, at)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"cannot create a symlink here: {exc}")
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("this system has no FIFOs")
        os.mkfifo(at)
    else:
        at.mkdir()


def _is_kind(kind: str, path: Path) -> bool:
    if kind == "symlink":
        return path.is_symlink()
    if kind == "fifo":
        return path.is_fifo()
    return path.is_dir() and not path.is_symlink()


_SPECIAL_KINDS = pytest.mark.parametrize("kind", ["symlink", "fifo", "folder"])


@pytest.fixture
def victim(tmp_path: Path) -> Path:
    """A file outside the state dir that a link at a counter's or a marker's
    name points to: its contents must survive the hook."""
    path = tmp_path / "outside" / "victim.txt"
    path.parent.mkdir()
    path.write_text("keep me\nline 2\n", encoding="utf-8")
    return path


def _leftovers(impl: Path) -> list[str]:
    """Temporary files the hook left in the state dir."""
    return sorted(path.name for path in impl.iterdir() if path.name.endswith(".tmp"))


@_SPECIAL_KINDS
def test_a_counter_name_holding_a_link_or_a_special_file_counts_against_unknown(
    tmp_path: Path, victim: Path, kind: str
) -> None:
    """The counter's name holds a symlink, a FIFO or a folder: the hook reads
    nothing through it and writes nothing through it, leaves it as it is, and
    counts the turn against `unknown`, as for a story id that names no counter
    it can use. stderr says why. It never waits on the FIFO."""
    project = tmp_path / "proj"
    impl = project / "_bmad-output" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / ".current-story").write_text("1-1-login\n", encoding="utf-8")
    counter = impl / ".budget-1-1-login.json"
    _make_special(kind, counter, victim)
    event = json.dumps({"hook_event_name": "Stop", "cwd": str(project)})
    proc = _run_raw(event, project, _no_story_env(impl, "1"), timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert victim.read_text(encoding="utf-8") == "keep me\nline 2\n"
    assert _is_kind(kind, counter)
    assert _turns(impl, "unknown") == 1
    assert (impl / ".escalation-unknown.md").is_file()
    assert not (impl / ".escalation-1-1-login.md").exists()
    assert "systemMessage" in json.loads(proc.stdout)
    stderr = proc.stderr.decode("utf-8", "replace")
    assert ".budget-1-1-login.json is a symlink or not a regular file" in stderr, stderr
    assert "against unknown" in stderr
    assert _leftovers(impl) == []


@_SPECIAL_KINDS
def test_a_marker_name_holding_a_link_or_a_special_file_is_not_written_through(
    tmp_path: Path, victim: Path, kind: str
) -> None:
    """At the ceiling, the marker's name holds a symlink, a FIFO or a folder:
    the turn is counted, the overrun message still goes out, and the hook
    writes no marker through that name and leaves it as it is. The message
    then says no marker was written, rather than that one was."""
    impl = tmp_path / "impl"
    impl.mkdir()
    marker = impl / ".escalation-S1.md"
    _make_special(kind, marker, victim)
    env = {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "ULTRACODE_STORY_ID": "S1", "ULTRACODE_MAX_TURNS": "1"}
    proc = _run_raw(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)}), tmp_path, env, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert victim.read_text(encoding="utf-8") == "keep me\nline 2\n"
    assert _is_kind(kind, marker)
    assert _turns(impl, "S1") == 1
    message = json.loads(proc.stdout)["systemMessage"]
    assert "reached its turn ceiling" in message
    assert "Marker written" not in message
    assert f"No marker was written at {marker}" in message
    assert ".escalation-S1.md is a symlink or not a regular file" in proc.stderr.decode("utf-8", "replace")
    assert _leftovers(impl) == []


def test_a_link_at_unknowns_counter_too_leaves_the_turn_uncounted(tmp_path: Path, victim: Path) -> None:
    """When `unknown`'s counter name holds a link as well, there is no counter
    left to count against: the hook writes nothing, says so, and exits 0."""
    impl = tmp_path / "impl"
    impl.mkdir()
    _make_special("symlink", impl / ".budget-S1.json", victim)
    _make_special("symlink", impl / ".budget-unknown.json", victim)
    env = {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "ULTRACODE_STORY_ID": "S1", "ULTRACODE_MAX_TURNS": "1"}
    proc = _run_raw(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)}), tmp_path, env, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == b""
    assert victim.read_text(encoding="utf-8") == "keep me\nline 2\n"
    assert sorted(path.name for path in impl.iterdir()) == [".budget-S1.json", ".budget-unknown.json"]
    assert "this turn is not counted" in proc.stderr.decode("utf-8", "replace")


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "mkfifo"), reason="needs O_NOFOLLOW and FIFOs (POSIX)"
)
def test_a_link_or_a_fifo_put_at_the_name_after_the_look_is_not_read_through(tmp_path: Path, victim: Path) -> None:
    """The hook looks at what a name holds before it opens it, and a link or
    a FIFO could be put there in between. The open itself follows no link at
    the name and does not wait on a FIFO, the type check after it refuses
    anything but a regular file, and a write goes through a new file renamed
    onto the name, which replaces a link there rather than writing through
    it."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("ucg_budget_stop_under_test", HOOK)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    link = tmp_path / "link.json"
    os.symlink(victim, link)
    with pytest.raises(OSError):
        hook._read_text(link)
    fifo = tmp_path / "fifo.json"
    os.mkfifo(fifo)
    with pytest.raises(hook._NotRegular):
        hook._read_text(fifo)
    assert hook._load_state(link) == {"turns": 0}
    hook._write_text(link, '{"turns": 1}')
    assert not link.is_symlink()
    assert link.read_text(encoding="utf-8") == '{"turns": 1}'
    assert victim.read_text(encoding="utf-8") == "keep me\nline 2\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["fifo.json", "link.json", "outside"]


def test_a_counter_is_replaced_whole_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    """The positive twin: a regular counter is read and rewritten through a
    temporary file renamed onto its name, which leaves nothing behind."""
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / ".budget-S1.json").write_text(json.dumps({"turns": 4}), encoding="utf-8")
    env = {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "ULTRACODE_STORY_ID": "S1", "ULTRACODE_MAX_TURNS": "5"}
    proc = _run_raw(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)}), tmp_path, env, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert _turns(impl, "S1") == 5
    assert (impl / ".escalation-S1.md").is_file()
    assert sorted(path.name for path in impl.iterdir()) == [".budget-S1.json", ".escalation-S1.md"]


@pytest.mark.parametrize(
    "state",
    [
        pytest.param("[3]", id="array"),
        pytest.param("[" * 100_000, id="nested-past-what-python-reads"),
        pytest.param('{"turns": 1e999}', id="infinite"),
        pytest.param('{"turns": null}', id="null"),
    ],
)
def test_a_counter_it_cannot_read_restarts_as_an_unparseable_one_does(tmp_path: Path, state: str) -> None:
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / ".budget-S1.json").write_text(state, encoding="utf-8")
    env = {"ULTRACODE_IMPL_ARTIFACTS": str(impl), "ULTRACODE_STORY_ID": "S1"}
    proc = _run_raw(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)}), tmp_path, env)
    assert proc.returncode == 0, proc.stderr
    assert _turns(impl, "S1") == 1


def test_the_docstring_says_bad_input_never_ends_the_hook() -> None:
    doc = " ".join(ast.get_docstring(ast.parse(HOOK.read_text(encoding="utf-8"))).split())
    assert "Claude Code ignores `onFailure` on Stop" in doc
    assert "exits 0 whatever it is given" in doc


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
