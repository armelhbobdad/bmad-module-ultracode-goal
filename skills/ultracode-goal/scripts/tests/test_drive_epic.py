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


def _git(repo: Path, *args: str) -> str:
    """Run git against a fixture repo, immune to the developer's own config.

    `-c commit.gpgsign=false` is not optional: a contributor with a global
    `commit.gpgsign=true` (or a `gpg.format=ssh` with no key reachable in CI)
    gets a signing failure on every fixture commit, and the whole git-backed
    half of this file ERRORS rather than fails - on their machine only. This
    repo has shipped that class of CI-portability defect before.
    """
    import subprocess

    proc = subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
    )
    return proc.stdout.strip()


@pytest.fixture
def git_project(tmp_path: Path) -> dict:
    """A project whose root is a REAL git repo, with one commit.

    The plain `project` fixture is not a repo, so the post-stop triage correctly
    finds git unreadable and refuses to retry. That is the right fail-closed
    default and it is pinned by its own test, but every retry behaviour needs a
    tree the triage can actually read.
    """
    root = tmp_path / "repo"
    impl = root / "_bmad-output" / "impl"
    write_sprint_status(impl, {DONE_STORY: "done", STORY_A: "ready-for-dev", STORY_B: "backlog"})
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    # Real projects gitignore the run artifacts, and the triage excludes them
    # from its safety judgment either way (the driver deletes run-result.json
    # itself, so a tracked one would dirty the tree on every single lap).
    (root / ".gitignore").write_text("_bmad-output/\n", encoding="utf-8")
    _git(root, "add", ".gitignore")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "seed.txt")
    _git(root, "commit", "-qm", "seed")
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
        dirty: bool = False,
        commit: bool = False,
        intent_to_add: bool = False,
    ):
        self.project = project
        self.script = list(script)
        self.code = code
        # What this session leaves behind in the TREE, which is what the
        # post-stop triage reads and what the retry decision turns on.
        self.dirty = dirty
        self.commit = commit
        self.intent_to_add = intent_to_add
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

        root = self.project["root"]
        if self.dirty:
            (root / "half_written.rs").write_text("fn incomplete() {\n", encoding="utf-8")
        if self.intent_to_add:
            (root / "rescue_me.rs").write_text("fn precious() {}\n", encoding="utf-8")
            _git(root, "add", "-N", "rescue_me.rs")
        if self.commit:
            (root / "landed.rs").write_text("fn landed() {}\n", encoding="utf-8")
            _git(root, "add", "landed.rs")
            _git(root, "commit", "-qm", "the story's work")

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


def test_undecodable_bytes_at_the_pinned_path_are_no_terminal(project, monkeypatch):
    """`read_result` promises "unreadable" lands on None; UnicodeDecodeError is unreadable.

    It is a ValueError, not an OSError, so an OSError-only guard let it raise
    straight out of the drive - no summary line, no `driven`/`advanced` account,
    a traceback instead of the fail-closed stop every other malformed terminal
    gets. Reachable rather than theoretical: the adapter serializes with
    `ensure_ascii=False`, so a real terminal can carry multi-byte UTF-8, and
    this driver SIGKILLs a session that outran its ceiling - possibly partway
    through that write. These are the trailing bytes of a truncated one.
    """

    def fake(command, cwd, timeout=None):
        project["result"].parent.mkdir(parents=True, exist_ok=True)
        project["result"].write_bytes(b'{"status": "compl\xc3')
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


def test_the_kill_signal_is_resolved_once_and_never_named_directly():
    """SIGKILL is POSIX-only, and CI runs Windows.

    The first cut of the timeout reached for `signal.SIGKILL` at the call site
    and died on Windows with AttributeError at the exact moment it was trying to
    clean up a wedged session - the one place a crash is least affordable. The
    constant resolves it once, at import, with a fallback; this pins that no
    later edit quietly reintroduces the direct reference.
    """
    body = SCRIPT.read_text(encoding="utf-8").split('"""', 2)[-1]
    assert "signal.SIGKILL" not in body, (
        "signal.SIGKILL does not exist on Windows; use _KILL_SIGNAL"
    )
    assert drive_epic._KILL_SIGNAL in (
        getattr(signal, "SIGKILL", None),
        signal.SIGTERM,
    )


def test_every_signal_that_stops_the_driver_is_forwarded(tmp_path):
    """SIGINT alone left SIGTERM and SIGHUP orphaning the session.

    `start_new_session` detaches the spawn, and `--session-timeout` is enforced
    only by the driver's own `proc.wait`, so a signal that kills the driver and
    is not forwarded leaves a `claude` session running under `acceptEdits` with
    no wall clock at all - the overnight-ssh-drops case. SIGHUP is POSIX-only,
    so the tuple is resolved by name for the same reason `_KILL_SIGNAL` is.
    """
    names = {s.name for s in drive_epic._FORWARDED_SIGNALS}
    assert {"SIGINT", "SIGTERM"} <= names
    if hasattr(signal, "SIGHUP"):
        assert "SIGHUP" in names

    body = SCRIPT.read_text(encoding="utf-8").split('"""', 2)[-1]
    assert "signal.SIGHUP" not in body, (
        "signal.SIGHUP does not exist on Windows; resolve it by name"
    )


def test_a_forwarded_signal_stops_the_drive_instead_of_spawning_the_next_story(
    project, monkeypatch, capsys
):
    """Forwarding kills the session; this is what stops the DRIVE.

    The regression this pins is worse than the bug it replaced. A handler that
    merely forwards and returns leaves the driver alive: `wait()` resumes, the
    terminal the dying session had ALREADY written reads as an ordinary
    `complete`, the story shows `done`, and the loop spawns the next story - so
    `kill <driver>` would start a fresh unattended session under `acceptEdits`.
    The spawn count is the assertion that bites.
    """

    def fake(command, cwd, timeout=None):
        # Exactly the ordering finalize.md prescribes: the session writes its
        # terminal and advances the row, and is only then killed mid-teardown.
        project["impl"].mkdir(parents=True, exist_ok=True)
        project["result"].write_text(json.dumps(complete_envelope()), encoding="utf-8")
        statuses = current_statuses(project["impl"])
        statuses[STORY_A] = "done"
        write_sprint_status(project["impl"], statuses)
        setattr(drive_epic, "_STOPPED_BY_SIGNAL", signal.SIGTERM)
        return -15

    monkeypatch.setattr(drive_epic, "spawn", fake)
    monkeypatch.setattr(drive_epic, "_STOPPED_BY_SIGNAL", None)
    summary = drive_epic.drive(
        epic=EPIC, project_root=project["root"], impl_artifacts=project["impl"]
    )

    assert summary["stopped_because"] == drive_epic.STOP_SIGNALLED
    assert summary["driven"] == [STORY_A]
    assert summary["advanced"] == [], "a signalled stop must not bank the kill as progress"
    assert drive_epic.STOP_SIGNALLED in capsys.readouterr().out
    assert drive_epic.STOP_SIGNALLED not in drive_epic.CLEAN_STOPS


@pytest.mark.skipif(
    os.name != "posix",
    reason=(
        "os.kill on Windows does not deliver a signal - it calls TerminateProcess, "
        "which kills the test runner outright instead of invoking the handler. The "
        "forwarder is a POSIX mechanism (see _terminate's killpg fallback)."
    ),
)
def test_a_real_signal_sets_the_flag_and_kills_the_session(tmp_path, monkeypatch):
    """Pins the PRODUCER half against a real signal, not a hand-set global.

    Without this, deleting the two lines in `_forward` that set the flag leaves
    the whole suite green - and re-lands the regression the flag exists to stop
    (session killed, its already-written terminal read as a clean completion,
    next story spawned). The consumer test hand-sets the global, so it cannot
    catch that. A real signal is deterministic here and costs under a second.
    """
    monkeypatch.setattr(drive_epic, "_STOPPED_BY_SIGNAL", None)

    import threading

    timer = threading.Timer(0.4, lambda: os.kill(os.getpid(), signal.SIGTERM))
    timer.start()
    try:
        code = drive_epic.spawn(
            [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, timeout=None
        )
    finally:
        timer.cancel()

    assert drive_epic._STOPPED_BY_SIGNAL == signal.SIGTERM, (
        "_forward must record the signal; without it the drive banks the kill as progress"
    )
    assert code == -signal.SIGTERM, "the forwarded signal must reach the session's group"


def test_the_signal_flag_does_not_leak_between_drives(project, monkeypatch):
    """A stale flag from a previous drive would stop the next one on spawn 1."""
    monkeypatch.setattr(drive_epic, "_STOPPED_BY_SIGNAL", signal.SIGTERM)
    fake = FakeSession(project, [(complete_envelope(), STORY_A)])
    summary = run_drive(project, monkeypatch, fake)
    assert summary["stopped_because"] != drive_epic.STOP_SIGNALLED


def test_an_inherited_sig_ign_is_not_clobbered(tmp_path):
    """`nohup` ignores SIGHUP so a long drive survives a dropped terminal.

    Installing the forwarder over that would revoke the immunity for the
    duration of every spawn, i.e. for almost the whole drive.
    """
    if not hasattr(signal, "SIGHUP"):  # pragma: no cover - POSIX-only check
        return
    previous = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        drive_epic.spawn([sys.executable, "-c", "raise SystemExit(0)"], tmp_path)
        assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
    finally:
        signal.signal(signal.SIGHUP, previous)


def test_forwarded_handlers_are_restored_after_a_spawn(tmp_path):
    """The driver borrows the process's handlers; it must hand them back.

    Installing three and restoring one would leave the operator's own SIGTERM
    and SIGHUP dispositions pointing at a forwarder for a process that has
    already exited, for the rest of the drive.
    """
    before = {sig: signal.getsignal(sig) for sig in drive_epic._FORWARDED_SIGNALS}
    drive_epic.spawn([sys.executable, "-c", "raise SystemExit(0)"], tmp_path)
    assert {sig: signal.getsignal(sig) for sig in drive_epic._FORWARDED_SIGNALS} == before


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
                os.kill(int(pidfile.read_text()), drive_epic._KILL_SIGNAL)


# --- The in-flight abort: retry, but only over a tree that is safe -----------
#
# A `claude -p` killed by the API layer exits non-zero having written no
# terminal, so it lands on `no-terminal`, NOT on `signalled` (that branch fires
# only when a signal reached the DRIVER). Measured live before this suite was
# written: driving a fake spawn that exits 1 without writing a result produces
# `stopped_because == "no-terminal"` and leaves `_STOPPED_BY_SIGNAL` None.


def test_an_abort_over_a_clean_unmoved_tree_is_retried_and_lands(git_project, monkeypatch):
    """Nothing landed, so the same story is safe to re-spawn - and it works.

    This is the whole measured shape: eleven of twenty-two spawns in one session
    died in flight, and every row that was retried landed on a later attempt
    against identical state with no change of method. The operator was the retry
    loop eight times.
    """
    fake = FakeSession(
        git_project,
        [
            (None, None),  # dies in flight, writes no terminal
            (complete_envelope(), STORY_A),  # the retry lands
            (complete_envelope(), STORY_B),
        ],
        code=1,
    )
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC, project_root=git_project["root"], impl_artifacts=git_project["impl"]
    )

    assert summary["stopped_because"] == drive_epic.STOP_ALL_DONE
    assert summary["advanced"] == [STORY_A, STORY_B]
    # Three spawns, but only two stories driven: the retry is the SAME story.
    assert len(fake.calls) == 3
    assert summary["driven"] == [STORY_A, STORY_B]


def test_an_abort_over_a_dirty_tree_is_never_retried(git_project, capsys, monkeypatch):
    """A retry across a dirty tree is how already-green work gets destroyed."""
    fake = FakeSession(git_project, [(None, None)], code=1, dirty=True)
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC, project_root=git_project["root"], impl_artifacts=git_project["impl"]
    )

    assert summary["stopped_because"] == drive_epic.STOP_NO_TERMINAL
    assert len(fake.calls) == 1, "a dirty tree must not be re-spawned over"
    assert "not retried" in (summary["detail"] or "")
    out = capsys.readouterr().out
    assert "tree DIRTY" in out
    assert "do NOT re-drive over this tree" in out


def test_an_abort_after_a_commit_is_never_retried_and_says_so(git_project, capsys, monkeypatch):
    """Clean tree with HEAD ADVANCED means the work committed.

    This is the $24 case: the drive had already committed and died in close-out,
    so the only thing missing was a status flip, and the driver reported it as a
    failure. Re-driving it would redo a delivered story.
    """
    fake = FakeSession(git_project, [(None, None)], code=1, commit=True)
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC, project_root=git_project["root"], impl_artifacts=git_project["impl"]
    )

    assert summary["stopped_because"] == drive_epic.STOP_NO_TERMINAL
    assert len(fake.calls) == 1
    out = capsys.readouterr().out
    assert "tree CLEAN and HEAD ADVANCED" in out
    assert "only close-out is missing" in out
    assert "Do NOT re-drive this story" in out


def test_the_retry_budget_is_capped_and_the_cap_surfaces(git_project, monkeypatch):
    """Three consecutive deaths needed an operator; the cap is what says so."""
    fake = FakeSession(git_project, [(None, None)], code=1)
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC,
        project_root=git_project["root"],
        impl_artifacts=git_project["impl"],
        max_abort_retries=2,
    )

    assert summary["stopped_because"] == drive_epic.STOP_NO_TERMINAL
    assert len(fake.calls) == 3, "the original attempt plus exactly two retries"
    assert "2 retry attempt(s)" in (summary["detail"] or "")


def test_max_abort_retries_zero_restores_stop_on_first_abort(git_project, monkeypatch):
    fake = FakeSession(git_project, [(None, None)], code=1)
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC,
        project_root=git_project["root"],
        impl_artifacts=git_project["impl"],
        max_abort_retries=0,
    )

    assert summary["stopped_because"] == drive_epic.STOP_NO_TERMINAL
    assert len(fake.calls) == 1


def test_the_retry_budget_is_per_story_not_per_drive(git_project, monkeypatch):
    """A budget spent on one row must not leave the next unable to survive."""
    fake = FakeSession(
        git_project,
        [
            (None, None),                     # story A dies
            (complete_envelope(), STORY_A),   # A's retry lands
            (None, None),                     # story B dies
            (complete_envelope(), STORY_B),   # B's retry lands, on B's OWN budget
        ],
        code=1,
    )
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC,
        project_root=git_project["root"],
        impl_artifacts=git_project["impl"],
        max_abort_retries=1,
    )

    assert summary["stopped_because"] == drive_epic.STOP_ALL_DONE
    assert summary["advanced"] == [STORY_A, STORY_B]
    assert len(fake.calls) == 4


def test_no_git_means_no_retry(project, monkeypatch):
    """Fail-closed: without git the triage cannot establish a safe tree."""
    fake = FakeSession(project, [(None, None)], code=1)
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC, project_root=project["root"], impl_artifacts=project["impl"]
    )

    assert summary["stopped_because"] == drive_epic.STOP_NO_TERMINAL
    assert len(fake.calls) == 1


def test_a_blocked_stop_also_prints_the_triage(git_project, capsys, monkeypatch):
    """The triage attaches to EVERY non-clean stop, not only the retryable one.

    Attaching it selectively is how a killed spawn's state went unreported in
    the first place.
    """
    fake = FakeSession(git_project, [(blocked_envelope("a story escalated"), None)])
    monkeypatch.setattr(drive_epic, "spawn", fake)
    drive_epic.drive(
        epic=EPIC, project_root=git_project["root"], impl_artifacts=git_project["impl"]
    )

    assert "triage:" in capsys.readouterr().out


# --- The intent-to-add hazard, in code rather than an operator's memory ------


def test_intent_to_add_is_read_off_the_columns_not_sniffed(tmp_path):
    """Built from REAL `git status --porcelain -z`, not hand-written strings.

    A hand-written fixture is what let two parsing bugs through: the arrow-split
    and the C-quoting. Both only appear in git's actual output, so the oracle has
    to be git. Every path here is one that exists on disk, and the assertion is
    that the function names exactly the hazardous ones - no more, no fewer.
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "base.txt")
    _git(root, "commit", "-qm", "seed")

    # The hazards: intent-to-add, including the names that defeat sniffing.
    # `a -> b.txt` is POSIX-only: Windows forbids `>` in a filename, so the file
    # cannot be created there at all. Its parsing is covered unconditionally by
    # test_an_arrow_in_a_filename_is_not_a_rename below.
    hazards = ["plain.rs", "has space.rs", "caf\u00e9.rs"]
    if os.name != "nt":
        hazards.append("a -> b.txt")
    for name in hazards:
        (root / name).write_text("precious\n", encoding="utf-8")
        _git(root, "add", "-N", name)
    # The safe neighbours: genuinely staged, modified, untracked, and a rename.
    (root / "staged.rs").write_text("x\n", encoding="utf-8")
    _git(root, "add", "staged.rs")
    (root / "base.txt").write_text("edited\n", encoding="utf-8")
    (root / "untracked.rs").write_text("x\n", encoding="utf-8")

    porcelain = drive_epic._git_out(
        root, "status", "--porcelain", "-z", "--untracked-files=all"
    )
    found = drive_epic.intent_to_add_paths(drive_epic.porcelain_entries(porcelain))

    assert sorted(found) == sorted(hazards)
    # Every name it reports is a file that actually exists - the property the
    # arrow-split and the octal escapes each broke.
    for name in found:
        assert (root / name).is_file(), f"{name!r} is not on disk"

    # And the CALLER must ask git for that shape. Asserting only against a
    # hand-passed -z string would leave post_stop_triage free to drop the flag.
    triage = drive_epic.post_stop_triage(root, drive_epic.head_sha(root))
    assert sorted(triage["intent_to_add"]) == sorted(found)
    for name in triage["intent_to_add"]:
        assert (root / name).is_file(), f"triage named {name!r}, which is not on disk"


def test_an_arrow_in_a_filename_is_not_a_rename():
    """A path whose NAME contains " -> " must not be split as a rename.

    Synthetic rather than git-produced, and that is sound HERE specifically:
    `-z` is NUL-delimited and never quotes, so this string is byte-for-byte what
    git emits. (A hand-written *line-based* fixture would not be sound - the
    C-quoting is exactly what the old parser got wrong.) It has to be synthetic
    because Windows forbids `>` in a filename, so the file cannot exist there,
    while the parsing bug is platform-independent.

    The pre-fix parser returned `b.txt`: a real, different, plausible file. The
    operator backs that up, sees the true hazard unflagged, reverts it, and git
    truncates it to zero bytes exiting 0.
    """
    payload = " A a -> b.txt\0 A plain.rs\0"
    entries = drive_epic.porcelain_entries(payload)
    assert entries == [(" ", "A", "a -> b.txt"), (" ", "A", "plain.rs")]
    assert drive_epic.intent_to_add_paths(entries) == ["a -> b.txt", "plain.rs"]


def test_a_rename_entry_does_not_shift_the_parse(tmp_path):
    """A rename carries a trailing origPath field; consuming it is required.

    Miss it and every entry after a rename is read one field out of step.
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "base.txt").write_text("b\n", encoding="utf-8")
    _git(root, "add", "base.txt")
    _git(root, "commit", "-qm", "seed")
    _git(root, "mv", "base.txt", "renamed.txt")
    (root / "zz_after.rs").write_text("x\n", encoding="utf-8")
    _git(root, "add", "-N", "zz_after.rs")

    entries = drive_epic.porcelain_entries(
        drive_epic._git_out(root, "status", "--porcelain", "-z", "--untracked-files=all")
    )
    paths = [p for _, _, p in entries]
    assert "renamed.txt" in paths
    assert "base.txt" not in paths, "the origPath field must be consumed, not re-parsed"
    assert drive_epic.intent_to_add_paths(entries) == ["zz_after.rs"]


def test_the_triage_names_intent_to_add_paths_with_the_truncation_warning(git_project, capsys, monkeypatch):
    fake = FakeSession(git_project, [(None, None)], code=1, intent_to_add=True)
    monkeypatch.setattr(drive_epic, "spawn", fake)
    drive_epic.drive(
        epic=EPIC, project_root=git_project["root"], impl_artifacts=git_project["impl"]
    )

    out = capsys.readouterr().out
    assert "intent-to-add: rescue_me.rs" in out
    assert "TRUNCATES these to zero bytes" in out


def test_the_triage_never_writes_to_the_tree(git_project):
    """The driver's read-only property must survive the triage.

    Driven directly rather than through a drive, because the fake session writes
    to the tree on purpose - so a before/after around the whole drive would be
    measuring the fake, not the triage.
    """
    root = git_project["root"]
    (root / "half_written.rs").write_text("fn incomplete() {\n", encoding="utf-8")
    (root / "rescue_me.rs").write_text("fn precious() {}\n", encoding="utf-8")
    _git(root, "add", "-N", "rescue_me.rs")

    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    head_before = _git(root, "rev-parse", "HEAD")
    porcelain_before = _git(root, "status", "--porcelain")

    triage = drive_epic.post_stop_triage(root, head_before, git_project["impl"])
    drive_epic.render_triage(triage)

    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) == before
    assert _git(root, "rev-parse", "HEAD") == head_before
    assert _git(root, "status", "--porcelain") == porcelain_before
    # And the intent-to-add file still has its bytes.
    assert (root / "rescue_me.rs").read_text(encoding="utf-8") == "fn precious() {}\n"


def test_the_cli_exposes_max_abort_retries():
    parser_help = drive_epic.main.__doc__ or ""
    del parser_help  # the flag is asserted through argparse, not the docstring
    import io, contextlib as _c

    buf = io.StringIO()
    with _c.redirect_stdout(buf), pytest.raises(SystemExit):
        drive_epic.main(["--help"])
    text = buf.getvalue()
    assert "--max-abort-retries" in text
    assert "re-spawn over work in progress" in " ".join(text.split())


def test_run_artifacts_do_not_count_as_a_dirty_tree(git_project, monkeypatch):
    """The driver's own artifacts are not story work, and treating them as such
    would kill the retry outright in any project that tracks `_bmad-output/`.

    The driver DELETES the pinned terminal file before every single spawn, so a
    tracked one leaves the tree dirty by the driver's own hand, permanently and
    on every lap. Found by writing the retry tests against a repo that had no
    `.gitignore`: the retry never fired, and the reason was the driver's own
    footprint.
    """
    root = git_project["root"]
    # Track the run-artifacts dir, the case a real project usually gitignores.
    (root / ".gitignore").write_text("", encoding="utf-8")
    git_project["impl"].mkdir(parents=True, exist_ok=True)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "track the run artifacts")
    (git_project["impl"] / "run-result.json").write_text("{}", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "a terminal from a prior run")

    fake = FakeSession(
        git_project,
        [(None, None), (complete_envelope(), STORY_A), (complete_envelope(), STORY_B)],
        code=1,
    )
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC, project_root=root, impl_artifacts=git_project["impl"]
    )

    # The driver's delete of the tracked terminal made the tree dirty, and the
    # retry still fired because that path is the driver's, not the story's.
    assert summary["stopped_because"] == drive_epic.STOP_ALL_DONE
    assert len(fake.calls) == 3


def test_the_report_still_lists_run_artifacts_it_excluded(git_project):
    """Excluded from the JUDGMENT, never hidden from the operator."""
    root = git_project["root"]
    (git_project["impl"] / "stray.txt").write_text("x", encoding="utf-8")
    (root / ".gitignore").write_text("", encoding="utf-8")

    triage = drive_epic.post_stop_triage(
        root, _git(root, "rev-parse", "HEAD"), git_project["impl"]
    )
    assert triage["tree_clean"] is False, ".gitignore itself is a real dirty path"
    assert any("_bmad-output" in p for p in triage["run_artifact_paths"])
    assert not any("_bmad-output" in p for p in triage["dirty_paths"])


@pytest.fixture
def unborn_project(tmp_path: Path) -> dict:
    """A git repo with NO commits: a greenfield project, HEAD unborn.

    `git init` with nothing committed yet is a shape this module advertises
    itself as able to run on, and `git rev-parse HEAD` fails there.
    """
    root = tmp_path / "repo"
    impl = root / "_bmad-output" / "impl"
    write_sprint_status(impl, {DONE_STORY: "done", STORY_A: "ready-for-dev", STORY_B: "backlog"})
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    # NOT a .gitignore: an unborn HEAD has no commit to carry one, so a
    # .gitignore would sit untracked and make the tree dirty - which would make
    # every test below pass for the wrong reason (dirty-work-in-tree), never
    # reaching the head-unknown reading they exist to pin.
    exclude = root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text("_bmad-output/\n", encoding="utf-8")
    return {"root": root, "impl": impl, "result": impl / envelope.RESULT_FILENAME}


def test_an_unreadable_pre_spawn_head_is_never_read_as_nothing_landed(unborn_project, monkeypatch):
    """Unknown is not unmoved, and the difference costs paid sessions.

    `head_sha` returns None on an unborn HEAD. Folding that into "unmoved" let a
    session make the project's FIRST commit, die before writing its terminal, and
    be re-driven twice over work already on disk - the exact case the retry gate
    says must never be retried.
    """
    fake = FakeSession(unborn_project, [(None, None)], code=1, commit=True)
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC, project_root=unborn_project["root"], impl_artifacts=unborn_project["impl"]
    )

    assert summary["stopped_because"] == drive_epic.STOP_NO_TERMINAL
    assert len(fake.calls) == 1, "an unknown pre-spawn HEAD must not be retried over"
    # And the session really did commit, so a retry would have re-driven it.
    assert _git(unborn_project["root"], "rev-parse", "HEAD")


def test_the_head_unknown_reading_says_so_rather_than_claiming_unmoved(unborn_project):
    """The report must not print a sha as "UNMOVED" that HEAD never previously had."""
    (unborn_project["root"] / "landed.rs").write_text("fn landed() {}\n", encoding="utf-8")
    _git(unborn_project["root"], "add", "landed.rs")
    _git(unborn_project["root"], "commit", "-qm", "the story's first-ever commit")

    triage = drive_epic.post_stop_triage(unborn_project["root"], None, unborn_project["impl"])
    assert triage["reading"] == "head-unknown"
    assert triage["head_moved"] is None

    rendered = " ".join(drive_epic.render_triage(triage))
    assert "UNREADABLE" in rendered
    assert "UNMOVED" not in rendered, "unknown must not be reported as unmoved"
    assert "nothing landed" not in rendered


def test_limit_bounds_paid_spawns_including_retries(git_project, monkeypatch):
    """`--limit` is the operator's SPEND bound, so a retry consumes it.

    Bounding distinct stories instead would let `--limit N` start
    N*(1+max_abort_retries) sessions - here 2 stories under `--limit 2` could
    have spawned up to six.
    """
    fake = FakeSession(git_project, [(None, None)], code=1, spin_cap=10)
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC,
        project_root=git_project["root"],
        impl_artifacts=git_project["impl"],
        limit=2,
        max_abort_retries=5,
    )

    assert len(fake.calls) == 2, "two paid sessions, because --limit said two"
    assert summary["stopped_because"] == drive_epic.STOP_LIMIT


def test_the_spawn_index_counts_every_paid_session(git_project, monkeypatch, capsys):
    """A retry that reprinted `[1]` would undercount what the operator paid for."""
    fake = FakeSession(
        git_project, [(None, None), (complete_envelope(), STORY_A), (complete_envelope(), STORY_B)],
        code=1,
    )
    monkeypatch.setattr(drive_epic, "spawn", fake)
    drive_epic.drive(
        epic=EPIC, project_root=git_project["root"], impl_artifacts=git_project["impl"]
    )
    out = capsys.readouterr().out
    for index in ("[1]", "[2]", "[3]"):
        assert index in out, f"missing spawn index {index}"


def test_the_no_progress_stop_is_triaged_too(git_project, monkeypatch, capsys):
    """The anti-spin stop is where the tree matters MOST.

    A session that claimed `complete` while the sprint row stayed put is exactly
    the shape where the work may have committed and only the `done` sync is
    missing - the case an operator most needs told about.
    """
    fake = FakeSession(git_project, [(complete_envelope(), None)], commit=True)
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic=EPIC, project_root=git_project["root"], impl_artifacts=git_project["impl"]
    )

    assert summary["stopped_because"] == drive_epic.STOP_NO_PROGRESS
    out = capsys.readouterr().out
    assert "triage:" in out
    assert "HEAD ADVANCED" in out, "the commit the session made must be surfaced"


def test_pre_spawn_stops_carry_no_triage(project, monkeypatch):
    """Nothing ran on this lap, so there is no post-spawn tree to describe."""
    fake = FakeSession(project, [(complete_envelope(), STORY_A)])
    monkeypatch.setattr(drive_epic, "spawn", fake)
    summary = drive_epic.drive(
        epic="epic-999", project_root=project["root"], impl_artifacts=project["impl"]
    )
    assert summary["stopped_because"] == drive_epic.STOP_EPIC_NOT_FOUND
    assert len(fake.calls) == 0
