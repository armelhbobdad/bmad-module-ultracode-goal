#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""CI-deterministic tests for the per-story process driver.

`drive_epic.py` spawns one `claude -p` per story so each story's context dies
with the process that held it. Everything it decides, it decides from two
sources it does not own: the rollup parsed out of sprint-status.yaml, and the
terminal `run-result.json` the spawned session wrote. So the whole contract is
about what it does when one of those two is missing, lying, or unchanged - and
every test here is written so that it fails for its OWN reason:

  - a spawn that leaves no readable result STOPS (fail-closed): the test proves
    a second spawn never happens, so a driver that assumed success reds here
  - `blocked` STOPS and the reason reaches both the summary and stdout
  - `complete` WITHOUT the story advancing STOPS (the anti-spin rule): the test
    pins the spawn count at exactly one, which is the number a spinning driver
    would exceed on its very next lap
  - `complete` WITH the story advancing continues, and the second story is a
    DIFFERENT story than the first
  - the stale-terminal delete happens BEFORE the spawn: a stale `complete` is
    seeded, and the fake session records what it saw at spawn time from INSIDE
    the spawn. Both halves have to hold - the recorded flag says the file was
    gone, and the drive's verdict says the stale bytes were never read as this
    spawn's result
  - the session's EXIT CODE decides nothing, proven in both directions: a
    non-zero exit over a real terminal keeps driving, a zero exit over no
    terminal still stops
  - a stale terminal that SURVIVES the delete stops before the spawn. The
    success-path tests cannot see this one - drop the guard and they stay green
  - JSON that parses but is not an object is no terminal, not a shape to probe
  - a session that outruns `--session-timeout` is a non-terminal, never an
    advance, and the ceiling is asserted to reach the spawn seam (0 as "none")
  - `--profile light` and `--skill-command` reach the spawned prompt; production
    contributes nothing to it, because it is the skill's own default
  - a `--impl-artifacts` that does not itself hold sprint-status.yaml is refused
    BEFORE the first spawn, with a twin proving the guard stays quiet on the
    correct invocation
  - `bypassPermissions` is refused without `--allow-full-autonomy` and accepted
    with it; an out-of-vocabulary `--permission-mode` or `--profile` is refused
  - `--dry-run` spawns nothing AND deletes nothing (it is the one path where the
    driver's single sanctioned write must not fire either)
  - `--limit` bounds SPAWNS, not stories: the fake advances every time, so a
    driver that ignored the bound would run the Epic out

Each of the four guards added after the first review round was mutation-checked:
disabling the stale-delete halt, the non-dict guard, the exit-code neutrality,
or the impl-artifacts match each turns this suite red.

NOTHING HERE SPAWNS `claude`. The subprocess seam is the module-level `spawn`,
monkeypatched to a `FakeSession` that plays a scripted terminal. A test that
actually launched a session would be non-deterministic, slow, and would need a
real BMAD project on disk.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_drive_epic.py -v
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "drive_epic.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


drive_epic = _load("drive_epic", SCRIPT)
envelope = _load("headless_envelope", HERE.parent / "headless_envelope.py")

EPIC = "epic-7"
STORY_A = "7-1-alpha"
STORY_B = "7-2-beta"
STORY_C = "7-3-gamma"
DONE_STORY = "7-0-prelude"


# --- the synthetic project --------------------------------------------------


def write_sprint_status(impl: Path, statuses: dict[str, str]) -> None:
    """Write the flat `development_status:` map `build_rollup` reads.

    Rewritten in place by the fake session when a story advances, exactly as
    Stage 5's `advance` route does - `bmad-dev-story` leaves a passing story at
    `review`, so `done` is the run's own write (`references/gate.md`), and it is
    the write this driver's progress check reads. The driver re-reads this file
    rather than trusting the envelope, so the file has to be the thing that moves.
    """
    lines = ["development_status:", "  epic-7: in-progress"]
    lines += [f"  {key}: {value}" for key, value in statuses.items()]
    impl.mkdir(parents=True, exist_ok=True)
    (impl / "sprint-status.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path) -> dict:
    """A project root with an impl-artifacts dir carrying sprint-status.yaml."""
    root = tmp_path / "repo"
    impl = root / "_bmad-output" / "impl"
    write_sprint_status(impl, {DONE_STORY: "done", STORY_A: "ready-for-dev", STORY_B: "backlog"})
    return {"root": root, "impl": impl, "result": impl / envelope.RESULT_FILENAME}


class FakeSession:
    """A stand-in for one `claude -p` process, playing a scripted terminal.

    Each entry of `script` is `(envelope_or_None, story_to_mark_done_or_None)`.
    The last entry repeats, so a test that wants "always advances" supplies one.

    `code` is the exit status every scripted session returns. It exists because
    the driver documents that the exit code decides NOTHING - the terminal file
    does - and a knob no test turns cannot prove that.
    """

    SPIN_CAP = 8

    def __init__(
        self,
        project: dict,
        script: list[tuple[dict | None, str | None]],
        *,
        code: int | None = 0,
        spin_cap: int | None = None,
    ):
        self.project = project
        self.script = list(script)
        self.code = code
        # A driver that lost its anti-spin rule would call this forever. The cap
        # converts that regression into a NAMED failure instead of a CI job that
        # hangs until somebody kills it - verified: with the rule removed the
        # spin test times out, with the cap it fails on this line.
        self.spin_cap = self.SPIN_CAP if spin_cap is None else spin_cap
        self.calls: list[list[str]] = []
        self.cwds: list[Path] = []
        # Recorded from INSIDE the spawn: whether the pinned terminal file was
        # on disk at the moment this session started. The stale-delete test
        # reads this and nothing else.
        self.result_present_at_spawn: list[bool] = []
        # The wall-clock ceiling the driver handed each spawn, so a test can pin
        # that the flag reaches the seam rather than being parsed and dropped.
        self.timeouts: list[int | None] = []

    def __call__(self, command: list[str], cwd: Path, timeout: int | None = None) -> int | None:
        if len(self.calls) >= self.spin_cap:
            raise AssertionError(
                f"the driver spawned {len(self.calls) + 1} sessions against a cap of "
                f"{self.spin_cap}: it is spinning, not driving"
            )
        self.calls.append(list(command))
        self.cwds.append(Path(cwd))
        self.timeouts.append(timeout)
        self.result_present_at_spawn.append(self.project["result"].exists())

        step = self.script[0] if len(self.script) == 1 else self.script.pop(0)
        payload, advance = step

        if advance:
            statuses = current_statuses(self.project["impl"])
            statuses[advance] = "done"
            write_sprint_status(self.project["impl"], statuses)
        if payload is not None:
            self.project["impl"].mkdir(parents=True, exist_ok=True)
            self.project["result"].write_text(json.dumps(payload), encoding="utf-8")
        return self.code


def current_statuses(impl: Path) -> dict[str, str]:
    """The story rows currently in sprint-status.yaml, in file order."""
    text = (impl / "sprint-status.yaml").read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for raw in text.splitlines()[1:]:
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        if key and not key.startswith("epic-"):
            out[key] = value.strip()
    return out


def complete_envelope() -> dict:
    return {
        "status": "complete",
        "skill": "ultracode-goal",
        "decision_log": "/tmp/.decision-log.md",
        "report": None,
        "deferred_work": None,
    }


def blocked_envelope(reason: str) -> dict:
    return {
        "status": "blocked",
        "skill": "ultracode-goal",
        "decision_log": "/tmp/.decision-log.md",
        "report": None,
        "deferred_work": None,
        "reason": reason,
    }


def never_spawn(reason: str):
    """A spawn seam that fails the test if it is ever reached.

    Every refusal path shares this: the assertion that matters is not what the
    driver printed, it is that no session was started at all.
    """

    def _seam(command, cwd, timeout=None):
        pytest.fail(reason)

    return _seam


def run_drive(project: dict, monkeypatch, fake, **kwargs) -> dict:
    monkeypatch.setattr(drive_epic, "spawn", fake)
    return drive_epic.drive(
        epic=EPIC,
        project_root=project["root"],
        impl_artifacts=project["impl"],
        **kwargs,
    )


# --- fail-closed on the terminal --------------------------------------------


def test_missing_result_file_stops_the_drive(project, monkeypatch, capsys):
    """No terminal was observed, so no terminal is assumed. One spawn, then stop."""
    fake = FakeSession(project, [(None, None)])
    summary = run_drive(project, monkeypatch, fake)

    assert summary["stopped_because"] == drive_epic.STOP_NO_TERMINAL
    assert len(fake.calls) == 1, "a driver that assumed success would have spawned again"
    assert summary["driven"] == [STORY_A]
    assert summary["advanced"] == []
    assert drive_epic.STOP_NO_TERMINAL in capsys.readouterr().out


def test_unparseable_result_file_stops_the_drive(project, monkeypatch):
    """Garbage at the pinned path is 'no terminal', never a tolerated shape."""

    def fake(command, cwd, timeout=None):
        project["result"].parent.mkdir(parents=True, exist_ok=True)
        project["result"].write_text("{not json", encoding="utf-8")
        return 0

    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC, project_root=project["root"], impl_artifacts=project["impl"]
    )
    assert summary["stopped_because"] == drive_epic.STOP_NO_TERMINAL


def test_blocked_status_stops_and_surfaces_the_reason(project, monkeypatch, capsys):
    reason = "secret ANTHROPIC_KEY unresolvable in headless"
    fake = FakeSession(project, [(blocked_envelope(reason), None)])
    summary = run_drive(project, monkeypatch, fake)

    assert summary["stopped_because"] == drive_epic.STOP_BLOCKED
    assert reason in (summary["detail"] or "")
    assert reason in capsys.readouterr().out
    assert len(fake.calls) == 1


def test_unrecognised_status_stops(project, monkeypatch):
    """There is no third status value; a fourth is not quietly treated as one."""
    odd = dict(complete_envelope())
    odd["status"] = "partial-complete"
    fake = FakeSession(project, [(odd, None)])
    summary = run_drive(project, monkeypatch, fake)

    assert summary["stopped_because"] == drive_epic.STOP_UNKNOWN_STATUS
    assert len(fake.calls) == 1


# --- the anti-spin rule ------------------------------------------------------


def test_complete_without_advancing_stops(project, monkeypatch, capsys):
    """A complete envelope over an unchanged sprint plan is not progress.

    The spawn count is the assertion that bites: the same command against the
    same state would loop forever, so anything above one here is the spin.
    """
    fake = FakeSession(project, [(complete_envelope(), None)], spin_cap=3)
    summary = run_drive(project, monkeypatch, fake)

    assert summary["stopped_because"] == drive_epic.STOP_NO_PROGRESS
    assert len(fake.calls) == 1, "a driver without the anti-spin rule would loop"
    assert summary["driven"] == [STORY_A]
    assert summary["advanced"] == []
    assert "ready-for-dev" in (summary["detail"] or "")
    assert drive_epic.STOP_NO_PROGRESS in capsys.readouterr().out


def test_complete_with_advance_continues_to_the_next_story(project, monkeypatch):
    """Two pending stories, both advancing: two spawns, then a clean all-done."""
    fake = FakeSession(
        project,
        [(complete_envelope(), STORY_A), (complete_envelope(), STORY_B)],
    )
    summary = run_drive(project, monkeypatch, fake)

    assert summary["stopped_because"] == drive_epic.STOP_ALL_DONE
    assert summary["driven"] == [STORY_A, STORY_B]
    assert summary["advanced"] == [STORY_A, STORY_B]
    assert summary["skipped_already_done"] == [DONE_STORY]
    assert len(fake.calls) == 2


def test_already_done_stories_are_never_driven(project, monkeypatch):
    fake = FakeSession(project, [(complete_envelope(), STORY_A), (complete_envelope(), STORY_B)])
    summary = run_drive(project, monkeypatch, fake)
    assert DONE_STORY not in summary["driven"]
    assert DONE_STORY in summary["skipped_already_done"]


# --- the stale-terminal delete ----------------------------------------------


def test_stale_result_is_deleted_before_the_spawn(project, monkeypatch):
    """Seeded stale `complete`, observed from inside the spawn, and not read.

    Two independent halves. The recorded flag proves the delete ran BEFORE the
    process started. The verdict proves the stale bytes never stood in for this
    spawn's result: the fake writes nothing, so the only way to reach anything
    but `no-terminal` is to have read somebody else's terminal.
    """
    project["impl"].mkdir(parents=True, exist_ok=True)
    project["result"].write_text(json.dumps(complete_envelope()), encoding="utf-8")

    fake = FakeSession(project, [(None, None)])
    summary = run_drive(project, monkeypatch, fake)

    assert fake.result_present_at_spawn == [False], "the stale terminal survived into the spawn"
    assert summary["stopped_because"] == drive_epic.STOP_NO_TERMINAL
    assert summary["advanced"] == []


def test_the_delete_is_the_only_write_the_driver_makes(project, monkeypatch):
    """A whole drive leaves the tree byte-identical, minus the cleared terminal."""
    project["impl"].mkdir(parents=True, exist_ok=True)
    project["result"].write_text(json.dumps(complete_envelope()), encoding="utf-8")
    others = {
        path: path.read_bytes()
        for path in sorted(project["root"].rglob("*"))
        if path.is_file() and path != project["result"]
    }

    fake = FakeSession(project, [(None, None)])
    run_drive(project, monkeypatch, fake)

    assert not project["result"].exists()
    assert {path: path.read_bytes() for path in others} == others
    assert sorted(p for p in project["root"].rglob("*") if p.is_file()) == sorted(others)


# --- the command the driver builds ------------------------------------------


def test_command_carries_the_work_bound_and_no_invented_flags(project, monkeypatch):
    fake = FakeSession(project, [(complete_envelope(), STORY_A), (complete_envelope(), STORY_B)])
    run_drive(project, monkeypatch, fake)

    command = fake.calls[0]
    assert command[0] == drive_epic.DEFAULT_CLAUDE_BIN
    assert command[1] == "-p"
    assert command[2] == f"/ultracode-goal {EPIC} -H --max-stories 1"
    assert "--output-format" in command and command[command.index("--output-format") + 1] == "json"
    assert command[command.index("--permission-mode") + 1] == drive_epic.DEFAULT_PERMISSION_MODE
    # Claude Code 2.1.220 defines no such flag; the turn ceiling is the skill's.
    assert "--max-turns" not in command
    assert fake.cwds[0] == project["root"]


def test_terminal_filename_comes_from_the_envelope_module():
    """The pinned name has ONE owner; a second spelling is a drift waiting."""
    source = SCRIPT.read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]  # exclude the module docstring
    assert "headless_envelope.RESULT_FILENAME" in body
    assert envelope.RESULT_FILENAME not in body


# --- invocation ---------------------------------------------------------------


def _cli(project: dict, *extra: str) -> list[str]:
    return [
        "--epic",
        EPIC,
        "--project-root",
        str(project["root"]),
        "--impl-artifacts",
        str(project["impl"]),
        *extra,
    ]


def test_bypass_permissions_is_refused_without_allow_full_autonomy(project, monkeypatch, capsys):
    monkeypatch.setattr(drive_epic, "spawn", never_spawn("refused invocation still spawned"))
    with pytest.raises(SystemExit) as exc:
        drive_epic.main(_cli(project, "--permission-mode", "bypassPermissions"))

    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--allow-full-autonomy" in err
    assert "unattended" in err


def test_bypass_permissions_is_allowed_with_allow_full_autonomy(project, monkeypatch, capsys):
    monkeypatch.setattr(drive_epic, "spawn", never_spawn("--dry-run must spawn nothing"))
    code = drive_epic.main(
        _cli(project, "--permission-mode", "bypassPermissions", "--allow-full-autonomy", "--dry-run")
    )

    assert code == 0
    assert "--permission-mode bypassPermissions" in capsys.readouterr().out


def test_out_of_vocabulary_permission_mode_is_refused(project, monkeypatch, capsys):
    monkeypatch.setattr(drive_epic, "spawn", never_spawn("refused invocation still spawned"))
    with pytest.raises(SystemExit) as exc:
        drive_epic.main(_cli(project, "--permission-mode", "yolo"))

    assert exc.value.code == 2
    assert "acceptEdits" in capsys.readouterr().err


def test_dry_run_spawns_nothing_and_deletes_nothing(project, monkeypatch, capsys):
    project["impl"].mkdir(parents=True, exist_ok=True)
    project["result"].write_text(json.dumps(complete_envelope()), encoding="utf-8")
    monkeypatch.setattr(drive_epic, "spawn", never_spawn("--dry-run must spawn nothing"))

    code = drive_epic.main(_cli(project, "--dry-run"))
    out = capsys.readouterr().out

    assert code == 0
    assert project["result"].exists(), "a dry run must not fire the one write either"
    assert out.count("would run:") == 2  # the two not-done stories
    assert "/ultracode-goal epic-7 -H --max-stories 1" in out


def test_limit_bounds_the_number_of_spawns(project, monkeypatch, capsys):
    """Three pending, an always-advancing session, --limit 2: exactly two spawns."""
    write_sprint_status(
        project["impl"],
        {DONE_STORY: "done", STORY_A: "ready-for-dev", STORY_B: "backlog", STORY_C: "backlog"},
    )
    spawned: list[list[str]] = []

    def fake(command, cwd, timeout=None):
        spawned.append(list(command))
        statuses = current_statuses(project["impl"])
        for key, value in statuses.items():
            if value != "done":
                statuses[key] = "done"
                break
        write_sprint_status(project["impl"], statuses)
        project["result"].write_text(json.dumps(complete_envelope()), encoding="utf-8")
        return 0

    monkeypatch.setattr(drive_epic, "spawn", fake)
    code = drive_epic.main(_cli(project, "--limit", "2"))

    assert len(spawned) == 2, "the bound counts spawns, not stories"
    assert code == 0
    assert drive_epic.STOP_LIMIT in capsys.readouterr().out


def test_limit_below_one_is_refused(project):
    with pytest.raises(SystemExit) as exc:
        drive_epic.main(_cli(project, "--limit", "0"))
    assert exc.value.code == 2


# --- repo-shaped stops --------------------------------------------------------


def test_absent_sprint_status_stops_without_spawning(tmp_path, monkeypatch):
    monkeypatch.setattr(drive_epic, "spawn", never_spawn("nothing to drive, yet it spawned"))
    summary = drive_epic.drive(
        epic=EPIC, project_root=tmp_path / "repo", impl_artifacts=tmp_path / "repo" / "impl"
    )
    assert summary["stopped_because"] == drive_epic.STOP_NO_SPRINT_STATUS
    assert summary["driven"] == []


def test_unknown_epic_stops_without_spawning(project, monkeypatch):
    monkeypatch.setattr(drive_epic, "spawn", never_spawn("unknown epic, yet it spawned"))
    summary = drive_epic.drive(
        epic="epic-42", project_root=project["root"], impl_artifacts=project["impl"]
    )
    assert summary["stopped_because"] == drive_epic.STOP_EPIC_NOT_FOUND


def test_epic_id_accepts_both_spellings():
    assert drive_epic.normalise_epic("epic-7") == "7"
    assert drive_epic.normalise_epic("7") == "7"
    assert drive_epic.normalise_epic("epic-st-5") is None


def test_exit_code_splits_finished_from_fail_closed(project, monkeypatch):
    """Exit 0 only for a finished invocation; every fail-closed stop is 1."""
    fake_ok = FakeSession(project, [(complete_envelope(), STORY_A), (complete_envelope(), STORY_B)])
    monkeypatch.setattr(drive_epic, "spawn", fake_ok)
    assert drive_epic.main(_cli(project)) == 0

    write_sprint_status(project["impl"], {DONE_STORY: "done", STORY_A: "ready-for-dev"})
    monkeypatch.setattr(drive_epic, "spawn", FakeSession(project, [(None, None)]))
    assert drive_epic.main(_cli(project)) == 1


# --- the session exit code decides nothing -----------------------------------


def test_a_nonzero_exit_does_not_stop_a_drive_that_reached_a_terminal(project, monkeypatch):
    """The terminal file decides, not the exit status - both directions.

    Without this the docstring's "the exit code is recorded and reported, but it
    decides nothing" is unpinned: a regression that short-circuits on a non-zero
    code passes every other test in this file, because no other test hands the
    driver a session that exits non-zero.
    """
    fake = FakeSession(
        project,
        [(complete_envelope(), STORY_A), (complete_envelope(), STORY_B)],
        code=3,
    )
    summary = run_drive(project, monkeypatch, fake)

    assert summary["stopped_because"] == drive_epic.STOP_ALL_DONE
    assert summary["advanced"] == [STORY_A, STORY_B], "a non-zero exit vetoed a real terminal"
    assert len(fake.calls) == 2

    # ...and the other direction, so neither half of the claim stands alone: a
    # CLEAN exit that wrote nothing is still not a terminal.
    write_sprint_status(project["impl"], {DONE_STORY: "done", STORY_A: "ready-for-dev"})
    clean_but_empty = FakeSession(project, [(None, None)], code=0)
    monkeypatch.setattr(drive_epic, "spawn", clean_but_empty)
    assert (
        drive_epic.drive(epic=EPIC, project_root=project["root"], impl_artifacts=project["impl"])[
            "stopped_because"
        ]
        == drive_epic.STOP_NO_TERMINAL
    )


# --- the stale-terminal delete, when it FAILS --------------------------------


def test_a_terminal_that_survives_the_delete_stops_before_the_spawn(project, monkeypatch):
    """The halt the module docstring calls load-bearing, actually exercised.

    Every other stale-delete test drives the success path, so removing the guard
    entirely leaves them green. This one is the mutation's only detector: if the
    delete's failure were ignored, the stale bytes would stand in for this
    spawn's result and the drive would read somebody else's terminal.
    """
    project["impl"].mkdir(parents=True, exist_ok=True)
    project["result"].write_text(json.dumps(complete_envelope()), encoding="utf-8")
    monkeypatch.setattr(drive_epic, "clear_result", lambda impl_artifacts: False)
    monkeypatch.setattr(drive_epic, "spawn", never_spawn("spawned over a stale terminal"))

    summary = drive_epic.drive(
        epic=EPIC, project_root=project["root"], impl_artifacts=project["impl"]
    )

    assert summary["stopped_because"] == drive_epic.STOP_STALE_RESULT
    assert summary["driven"] == []


def test_clear_result_reports_failure_when_the_file_outlives_the_unlink(project, monkeypatch):
    """`clear_result` is False only when the file is still there afterwards."""
    project["impl"].mkdir(parents=True, exist_ok=True)
    project["result"].write_text("{}", encoding="utf-8")

    def refuse(self, *args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(Path, "unlink", refuse)
    assert drive_epic.clear_result(project["impl"]) is False
    assert project["result"].exists()

    # An already-absent file is success, even on the same refusing unlink.
    assert drive_epic.clear_result(project["impl"] / "nowhere") is True


# --- terminal shapes ----------------------------------------------------------


def test_json_that_is_not_an_object_is_no_terminal(project, monkeypatch):
    """A well-formed JSON array at the pinned path is not a five-key envelope.

    `read_result`'s docstring names this as a distinct case it collapses to
    None; without the test, dropping the isinstance guard turns it into an
    AttributeError mid-drive instead of a clean fail-closed stop.
    """

    def fake(command, cwd, timeout=None):
        project["result"].parent.mkdir(parents=True, exist_ok=True)
        project["result"].write_text(json.dumps(["complete"]), encoding="utf-8")
        return 0

    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC, project_root=project["root"], impl_artifacts=project["impl"]
    )
    assert summary["stopped_because"] == drive_epic.STOP_NO_TERMINAL


# --- the wall clock -----------------------------------------------------------


def test_a_session_that_outruns_the_ceiling_stops_the_drive(project, monkeypatch):
    """`spawn` returning None means "never finished", which is never a terminal."""
    fake = FakeSession(project, [(complete_envelope(), STORY_A)], code=None)
    summary = run_drive(project, monkeypatch, fake)

    assert summary["stopped_because"] == drive_epic.STOP_SESSION_TIMEOUT
    assert summary["driven"] == [STORY_A]
    assert summary["advanced"] == [], "a killed session must not count as an advance"
    assert len(fake.calls) == 1


def test_the_ceiling_reaches_the_spawn_seam(project, monkeypatch):
    """Parsed AND passed through - a flag the seam never sees bounds nothing."""
    fake = FakeSession(project, [(complete_envelope(), STORY_A), (complete_envelope(), STORY_B)])
    run_drive(project, monkeypatch, fake)
    assert fake.timeouts == [drive_epic.DEFAULT_SESSION_TIMEOUT] * 2

    write_sprint_status(project["impl"], {DONE_STORY: "done", STORY_A: "ready-for-dev"})
    fake = FakeSession(project, [(complete_envelope(), STORY_A)])
    monkeypatch.setattr(drive_epic, "spawn", fake)
    assert drive_epic.main(_cli(project, "--session-timeout", "45")) == 0
    assert fake.timeouts == [45]


def test_zero_disables_the_ceiling_and_a_negative_is_refused(project, monkeypatch):
    write_sprint_status(project["impl"], {DONE_STORY: "done", STORY_A: "ready-for-dev"})
    fake = FakeSession(project, [(complete_envelope(), STORY_A)])
    monkeypatch.setattr(drive_epic, "spawn", fake)
    assert drive_epic.main(_cli(project, "--session-timeout", "0")) == 0
    assert fake.timeouts == [None], "0 must reach the seam as no ceiling, not as 0 seconds"

    with pytest.raises(SystemExit) as exc:
        drive_epic.main(_cli(project, "--session-timeout", "-1"))
    assert exc.value.code == 2


# --- what the spawned prompt can say ------------------------------------------


def test_the_light_profile_reaches_the_spawned_prompt(project, monkeypatch):
    """A driver that cannot say --light cannot drive a non-web stack at all."""
    fake = FakeSession(project, [(complete_envelope(), STORY_A), (complete_envelope(), STORY_B)])
    summary = run_drive(project, monkeypatch, fake, profile=drive_epic.PROFILE_LIGHT)

    assert summary["stopped_because"] == drive_epic.STOP_ALL_DONE
    assert fake.calls[0][2] == f"/ultracode-goal {EPIC} --light -H --max-stories 1"


def test_production_is_the_default_and_adds_nothing_to_the_prompt(project, monkeypatch):
    fake = FakeSession(project, [(complete_envelope(), STORY_A), (complete_envelope(), STORY_B)])
    run_drive(project, monkeypatch, fake)
    assert "--light" not in fake.calls[0][2]
    assert "--production" not in fake.calls[0][2], "production is the skill's default, not a flag"


def test_the_skill_command_is_overridable_for_a_plugin_install(project, monkeypatch):
    """A marketplace install namespaces the skill; a hardcoded slash form misses it."""
    namespaced = "/bmad-module-ultracode-goal:ultracode-goal"
    fake = FakeSession(project, [(complete_envelope(), STORY_A), (complete_envelope(), STORY_B)])
    run_drive(project, monkeypatch, fake, skill_command=namespaced)

    assert fake.calls[0][2] == f"{namespaced} {EPIC} -H --max-stories 1"


def test_an_unknown_profile_is_refused(project, monkeypatch):
    monkeypatch.setattr(drive_epic, "spawn", never_spawn("refused, yet it spawned"))
    with pytest.raises(SystemExit) as exc:
        drive_epic.main(_cli(project, "--profile", "turbo"))
    assert exc.value.code == 2


# --- the two reads must agree on one directory --------------------------------


def test_impl_artifacts_without_sprint_status_stops_without_spawning(project, monkeypatch):
    """The rollup searches; the terminal path does not. A split costs a session.

    `build_rollup` falls back to an rglob under `_bmad-output`, so a wrong
    `--impl-artifacts` still resolves a full rollup - while `result_path` stays
    pinned to the argv dir, where nothing will ever be written. Caught before
    the spawn, this is a usage error; caught after, it is a burned session
    reported as the session's own `no-terminal` failure.
    """
    elsewhere = project["root"] / "_bmad-output" / "not-impl"
    elsewhere.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(drive_epic, "spawn", never_spawn("spawned on a split path"))

    summary = drive_epic.drive(
        epic=EPIC, project_root=project["root"], impl_artifacts=elsewhere
    )

    assert summary["stopped_because"] == drive_epic.STOP_SPRINT_STATUS_ELSEWHERE
    assert summary["driven"] == []
    assert str(project["impl"]) in (summary["detail"] or "")



# --- argparse actually reaches drive() ----------------------------------------


def test_every_flag_main_parses_reaches_the_drive(project, monkeypatch):
    """The passthrough itself, not just the behaviour behind it.

    Asserting a flag's effect through `drive(...)` proves the effect and nothing
    about `main`. Verified by mutation: replacing `profile=args.profile`,
    `skill_command=args.skill_command` or `claude_bin=args.claude_bin` with the
    module default left every other test in this file green, because none of
    them reach argparse at all.
    """
    seen: dict = {}

    def record(**kwargs):
        seen.update(kwargs)
        return _summary_stub()

    def _summary_stub() -> dict:
        return {
            "epic": "7",
            "driven": [],
            "advanced": [],
            "skipped_already_done": [],
            "stopped_because": drive_epic.STOP_DRY_RUN,
            "detail": None,
        }

    monkeypatch.setattr(drive_epic, "drive", record)
    code = drive_epic.main(
        _cli(
            project,
            "--profile",
            "light",
            "--skill-command",
            "/bmad-module-ultracode-goal:ultracode-goal",
            "--session-timeout",
            "99",
            "--claude-bin",
            "/opt/claude",
            "--limit",
            "2",
            "--permission-mode",
            "dontAsk",
            "--dry-run",
        )
    )

    assert code == 0
    assert seen["profile"] == "light"
    assert seen["skill_command"] == "/bmad-module-ultracode-goal:ultracode-goal"
    assert seen["session_timeout"] == 99
    assert seen["claude_bin"] == "/opt/claude"
    assert seen["limit"] == 2
    assert seen["permission_mode"] == "dontAsk"
    assert seen["dry_run"] is True


@pytest.mark.parametrize("bad", ["", "ultracode-goal", " /ultracode-goal"])
def test_a_skill_command_that_is_not_a_slash_command_is_refused(project, monkeypatch, bad):
    """Free-form text is not rejected by Claude Code; it is RUN. So reject it here."""
    monkeypatch.setattr(drive_epic, "spawn", never_spawn("refused, yet it spawned"))
    with pytest.raises(SystemExit) as exc:
        drive_epic.main(_cli(project, "--skill-command", bad))
    assert exc.value.code == 2


# --- the real subprocess seam -------------------------------------------------
#
# Everything above replaces `spawn`. These four run the real body, because the
# ceiling it enforces is the one thing no fake can stand in for: mutating
# `except subprocess.TimeoutExpired: return None` to `return 124`, or gutting
# the function entirely, left the rest of this file green.


REAL = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")


def test_the_real_spawn_returns_the_child_exit_code(tmp_path):
    assert drive_epic.spawn([sys.executable, "-c", "raise SystemExit(3)"], tmp_path) == 3


def test_the_real_spawn_reports_an_unusable_binary_instead_of_raising(tmp_path):
    """A bad `--claude-bin` must reach the caller's fail-closed read, not a traceback."""
    assert drive_epic.spawn([str(tmp_path / "no-such-binary")], tmp_path) == 127


def test_the_real_spawn_returns_none_when_the_child_outruns_the_ceiling(tmp_path):
    assert drive_epic.spawn([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, 1) is None


@REAL
def test_the_ceiling_kills_the_whole_session_not_just_the_process_it_named(tmp_path):
    """The kill has to reach the grandchild, because that is what wedges.

    A session is almost never stuck in the `claude` process itself - it is stuck
    waiting on a tool call. `subprocess.run`'s own timeout handling kills the
    direct child only, so the tool call survives, reparented, still writing to
    the repo while the next spawn starts. This is the test that forces
    `start_new_session` plus the process-group kill: without them the ticker
    below keeps growing after the driver has declared the session dead.
    """
    ticker = tmp_path / "ticker"
    pidfile = tmp_path / "grandchild.pid"
    grandchild = (
        "import os, time, pathlib; "
        f"pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); "
        f"p = pathlib.Path({str(ticker)!r}); p.write_text('');\n"
        "while True:\n"
        "    p.write_text(p.read_text() + 'x'); time.sleep(0.05)"
    )
    parent = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}]); "
        "time.sleep(60)"
    )

    try:
        assert drive_epic.spawn([sys.executable, "-c", parent], tmp_path, 1) is None

        # The grandchild had ~1s to start and tick before the kill landed.
        assert ticker.exists(), "the grandchild never started; the test proves nothing"
        settled = ticker.read_text()
        time.sleep(0.75)  # ~15 more ticks if it survived
        assert ticker.read_text() == settled, (
            "the grandchild outlived the session kill: the timeout reaped the process it "
            "named and left the one still writing to the tree"
        )
    finally:
        if pidfile.exists():
            with contextlib.suppress(ValueError, OSError):
                os.kill(int(pidfile.read_text()), signal.SIGKILL)
