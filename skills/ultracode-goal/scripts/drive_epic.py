#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Drive an Epic one story per PROCESS, so context dies with each story.

A single headless invocation drives every not-done story of an Epic in ONE
Claude Code session, and that session's context only grows: by the fifth story
it carries four stories of transcript it will never need again, and an operator
watching a long run ends up clearing and re-invoking by hand. This driver moves
that boundary into the process table. It spawns one `claude -p` per story, each
invoking the skill headless under the per-invocation work bound:

    <claude-bin> -p "<skill-command> <epic> [--light] -H --max-stories 1" \\
        --output-format json --permission-mode <mode>

The bound is a WORK bound, not a scope narrowing. The Epic's in-scope set is
still every not-done story (the headless contract in
`references/ingest-and-scope.md` rule 3 is unchanged); the invocation simply
stops early and the skill's own resume routing picks the rest up next time. So
the driver never has to tell a session WHICH story to take - it takes the first
one the sprint plan still owes, which is the same story the driver is watching.

THE `done` ROW IS A CONTRACT THIS SCRIPT DEPENDS ON, and it is worth naming
because nothing about it is incidental. The driver reads progress out of
sprint-status.yaml, and only Stage 5's `advance` route writes it there: the
orchestrated sub-skills leave a passing story at `review` (`bmad-dev-story`) or
at `in-progress` (`bmad-code-review`, whenever a non-critical finding was
deferred - and it does not run under `--light` at all). `references/gate.md`
therefore makes the `done` sync part of `advance` itself. If that instruction is
ever dropped, this script's anti-spin rule inverts from a safety net into a
guaranteed halt on the first healthy story, so the two move together.

STRICTLY READ-ONLY ON THE REPO, WITH EXACTLY ONE EXCEPTION. It edits no source,
stages nothing, commits nothing, and creates no artifact of its own. The one
thing it writes is a DELETE of `<impl-artifacts>/run-result.json` before each
spawn, and that delete is the mechanism described next. Everything the driver
knows about the repo it gets from `preflight_check.build_rollup` (a read of
sprint-status.yaml) and from that one result file. The spawned session is of
course not read-only - it is the thing doing the work - but the driver's own
hands stay off the tree, which is what makes it safe to point at a run in
flight.

THE STALE-TERMINAL DELETE IS LOAD-BEARING. `run-result.json` is path-pinned and
overwritten in place, but it is only ever WRITTEN at a terminal. A file left by
the previous story's session therefore sits at exactly the path this story's
result will land at, and reads as this story's result to anyone testing for
presence - which is precisely what the driver does. The skill clears it itself
on every headless entry, but that clear happens once its config scalar resolves,
so a session that died before that (a bad binary, a refused permission mode, a
kill) never reached it. Deleting immediately BEFORE the spawn is what makes
presence mean one thing and one thing only: *this* spawn reached a terminal. If
the delete fails and the file survives, the drive stops rather than reading it.

FAIL-CLOSED AT EVERY DECISION, and there are five of them:

  | after a spawn                            | driver does           |
  | the session outran `--session-timeout`   | KILL it, STOP         |
  | no result file, or it will not parse     | STOP (`no-terminal`)  |
  | `status` is `blocked`                    | STOP, surface `reason`|
  | `status` is neither `complete`/`blocked`  | STOP (`unknown-status`)|
  | `status` is `complete`, story not `done` | STOP (`no-progress`)  |

The last one is the anti-spin rule and it is the least obvious. A session that
emits `complete` without advancing its story has finished its work without
blocking and still left the sprint plan exactly where it found it. Continuing
would spawn the identical command against the identical state forever, burning
a session per lap and reporting progress the whole time. A drive that cannot
show the story moved is not a drive that should keep going. The advance is read
back out of sprint-status.yaml, not out of the envelope: the envelope says what
the session thinks it did, the sprint plan says what actually changed.

`bypassPermissions` IS REFUSED unless `--allow-full-autonomy` is also passed.
The default stays `acceptEdits`. This is a second flag rather than a warning
because of what the driver is: an unattended loop, so a bypassed session's
ability to run anything at all is not one prompt an operator declines, it is
every prompt in every story of the Epic, none of which anybody sees.

FLAG VOCABULARY IS PINNED, NOT INVENTED. Verified against Claude Code 2.1.220:
`--permission-mode` accepts exactly acceptEdits|auto|bypassPermissions|manual|
dontAsk|plan, `--output-format` accepts text|json|stream-json, and there is NO
`--max-turns` flag. The per-story turn ceiling is the skill's own
`{workflow.max_turns_per_story}`, enforced inside the `/goal` condition and the
`budget_stop.py` Stop hook; do not reach for a CLI flag that does not exist.
That ceiling counts TURNS, though, so it cannot bound a session wedged inside a
single tool call - hence `--session-timeout`, a wall clock the driver owns.

THE INVOCATION STRING IS NOT UNIVERSAL, so it is a flag rather than a constant.
`/ultracode-goal` is the form an npx/`ucg install` install produces, where the
skill lands in `.claude/skills/`. Installed from the plugin marketplace the same
skill answers to `/bmad-module-ultracode-goal:ultracode-goal`, and a bare
natural-language trigger works in neither `-p` context reliably. Pass
`--skill-command` when yours differs; the default is the install path the
module's own README documents.

THE PROFILE HAS TO BE PASSABLE for the driver to be usable at all on the stacks
most likely to want it. `references/preflight.md` steers a non-web module to
`--light`, because TEA's ATDD/automate chain assumes a browser stack - so a
driver that could only ever spawn the production default would be unable to
drive exactly those projects. `--profile light` prepends `--light` to the
spawned prompt. Nothing else is passed through: `--yes` is meaningless under
`-H`, and `--retro` would run a close-out retrospective once per STORY.

The spawned session's own output is inherited, not captured - the `-p
--output-format json` result object prints straight through, and the driver's
own lines all carry the `ucg-drive:` prefix so the two are separable by eye and
by grep. Capturing would buy a tidier log at the cost of hiding the only thing
an operator has to diagnose a session that died.

    python3 drive_epic.py --epic <id> --impl-artifacts DIR \\
        [--project-root DIR] [--profile production|light] \\
        [--permission-mode MODE] [--allow-full-autonomy] \\
        [--session-timeout SECONDS] [--skill-command CMD] \\
        [--limit N] [--dry-run] [--claude-bin PATH]

Exit 0 when the invocation finished its work (the Epic has no not-done story
left, or `--limit` was reached, or it was a dry run), 1 on any fail-closed stop,
2 on an invocation error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from typing import TextIO

sys.path.insert(0, str(Path(__file__).resolve().parent))

import headless_envelope  # noqa: E402  (sibling script, path set above)
import preflight_check  # noqa: E402  (sibling script, path set above)

# Every driver-authored line carries this, so the spawned session's inherited
# output and the drive's own account of itself stay separable.
PREFIX = "ucg-drive"

# The work bound handed to each session. One story per process is the whole
# point of this script; it is a constant rather than a flag so that "--limit 3"
# can only ever mean three PROCESSES, never one process doing three stories.
STORIES_PER_SESSION = 1

DEFAULT_CLAUDE_BIN = "claude"
DEFAULT_PERMISSION_MODE = "acceptEdits"
BYPASS_MODE = "bypassPermissions"

# The slash form an npx / `ucg install` install answers to. Overridable because a
# marketplace install namespaces it; see the module docstring.
DEFAULT_SKILL_COMMAND = "/ultracode-goal"

# The skill's own two profiles. `production` is its default, so it adds nothing
# to the prompt; `light` is the one that has to be said out loud.
PROFILE_PRODUCTION = "production"
PROFILE_LIGHT = "light"
PROFILES = (PROFILE_PRODUCTION, PROFILE_LIGHT)

# Wall-clock ceiling on ONE session, in seconds. Sized for the FIRST spawn, not
# the typical one: every spawn is a cold `-p` invocation, so spawn 1 carries
# Stages 1-3 before it reaches a story at all - preflight remediation, and under
# production a TEA test-design plus an ATDD pass for EVERY in-scope story, since
# `--max-stories` bounds stories DRIVEN, not the Epic-wide define-done that
# precedes them. Later spawns re-enter at Execute and are much cheaper. Two hours
# covers that front-loaded lap and is still finite, which is the property that
# matters for an unattended loop. 0 disables the ceiling for anyone who would
# rather babysit than risk a false kill on a slow first story.
DEFAULT_SESSION_TIMEOUT = 7200

# Verified against Claude Code 2.1.220. Validated here rather than left to the
# CLI so a typo costs one exit-2 line instead of N spawned sessions that each
# die on their own usage error.
PERMISSION_MODES = ("acceptEdits", "auto", BYPASS_MODE, "manual", "dontAsk", "plan")
OUTPUT_FORMAT = "json"

# The status values the envelope contract defines. There is no third one, and a
# driver that invented tolerance for a fourth would be guessing at a terminal.
STATUS_COMPLETE = "complete"
STATUS_BLOCKED = "blocked"

DONE = "done"

# Why the drive stopped. The first three are a finished invocation; the rest are
# fail-closed halts and each names its own cause.
STOP_ALL_DONE = "all-done"
STOP_LIMIT = "limit-reached"
STOP_DRY_RUN = "dry-run"
STOP_NO_SPRINT_STATUS = "no-sprint-status"
STOP_EPIC_NOT_FOUND = "epic-not-found"
STOP_SPRINT_STATUS_ELSEWHERE = "sprint-status-elsewhere"
STOP_STALE_RESULT = "stale-result"
STOP_SESSION_TIMEOUT = "session-timeout"
STOP_NO_TERMINAL = "no-terminal"
STOP_BLOCKED = "blocked"
STOP_UNKNOWN_STATUS = "unknown-status"
STOP_NO_PROGRESS = "no-progress"

# The stops that mean "this invocation finished its work", i.e. exit 0.
CLEAN_STOPS = frozenset({STOP_ALL_DONE, STOP_LIMIT, STOP_DRY_RUN})

# `build_rollup` keys epics by their bare numeric prefix (`7`), because that is
# how sprint-status.yaml keys stories (`7-3-...`). An operator types `epic-7`.
# Both resolve here; an alpha-keyed track (`epic-st-5`) resolves to nothing,
# which is the same limit `references/ingest-and-scope.md` documents for every
# other number-keyed reader in the module.
EPIC_KEY_PATTERN = re.compile(r"^(?:epic[-_ ]?)?(\d+)")


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------


def normalise_epic(epic: str) -> str | None:
    """The bare numeric epic key `build_rollup` groups by, or None."""
    match = EPIC_KEY_PATTERN.match(str(epic).strip().lower())
    return match.group(1) if match else None


def epic_stories(rollup: dict, epic_key: str) -> list[dict] | None:
    """The Epic's story rows in sprint-status order, or None when it is absent.

    Order matters: the driver takes the FIRST not-done row each lap and that has
    to be the same story the skill's own in-scope ordering reaches first, or the
    driver would be watching one story while the session drove another.
    `build_rollup` preserves file order, so this is that order.
    """
    for entry in rollup.get("epics") or []:
        if str(entry.get("epic")) == epic_key:
            rows = entry.get("stories") or []
            return [row for row in rows if isinstance(row, dict)]
    return None


def status_of(stories: list[dict], story_id: str) -> str | None:
    """One story's rollup status, or None when the row is not there."""
    for row in stories:
        if row.get("id") == story_id:
            status = row.get("status")
            return str(status) if status is not None else None
    return None


def pending_ids(stories: list[dict]) -> list[str]:
    """The not-`done` story ids, in sprint-status order."""
    return [str(row.get("id")) for row in stories if row.get("status") != DONE and row.get("id")]


def done_ids(stories: list[dict]) -> list[str]:
    """The already-`done` story ids, in sprint-status order."""
    return [str(row.get("id")) for row in stories if row.get("status") == DONE and row.get("id")]


def result_path(impl_artifacts: Path) -> Path:
    """The pinned terminal path. The filename comes from the envelope module.

    Never hardcoded here: the adapter owns that name, and a second spelling of
    it is a drift waiting to happen between the writer and this reader.
    """
    return Path(impl_artifacts) / headless_envelope.RESULT_FILENAME


def read_result(impl_artifacts: Path) -> dict | None:
    """The terminal envelope this spawn wrote, or None.

    Absent, unreadable, not JSON, and JSON-that-is-not-an-object all land on
    None together, because they mean the same thing to the caller: no terminal
    was observed. Distinguishing them would invite a branch that treats one of
    them as success.
    """
    try:
        text = result_path(impl_artifacts).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        loaded = json.loads(text)
    except (ValueError, TypeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def clear_result(impl_artifacts: Path) -> bool:
    """Delete the pinned terminal file. True once it is gone.

    The one write this script performs. An already-absent file is success (that
    is the state being aimed at). A file that survives the delete is a FAILURE
    the caller must stop on: presence would no longer mean "this spawn reached a
    terminal", and every decision downstream reads presence.
    """
    path = result_path(impl_artifacts)
    try:
        path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return not path.exists()
    return not path.exists()


# --------------------------------------------------------------------------
# the spawn seam
# --------------------------------------------------------------------------


def build_prompt(
    epic: str,
    skill_command: str = DEFAULT_SKILL_COMMAND,
    profile: str = PROFILE_PRODUCTION,
) -> str:
    """The headless invocation one session runs, bounded to one story.

    `production` contributes nothing because it is the skill's own default, so
    the prompt says only what would otherwise be untrue.
    """
    flags = "-H" if profile != PROFILE_LIGHT else "--light -H"
    return f"{skill_command} {epic} {flags} --max-stories {STORIES_PER_SESSION}"


def build_command(
    claude_bin: str,
    epic: str,
    permission_mode: str,
    skill_command: str = DEFAULT_SKILL_COMMAND,
    profile: str = PROFILE_PRODUCTION,
) -> list[str]:
    """The exact argv of one spawn. Only flags Claude Code actually defines."""
    return [
        claude_bin,
        "-p",
        build_prompt(epic, skill_command, profile),
        "--output-format",
        OUTPUT_FORMAT,
        "--permission-mode",
        permission_mode,
    ]


# The hardest signal this platform has. SIGKILL is POSIX-only - Windows has no
# such name, and reaching for it there is an AttributeError at the exact moment
# the driver is trying to clean up a wedged session.
_KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)


def _terminate(proc: subprocess.Popen, sig: int) -> None:
    """Signal the whole session, not just the process that named it.

    A wedged session is almost never the `claude` process itself - it is the
    thing `claude` is waiting on, a Bash tool call that will not return. Killing
    only the direct child reaps the one process that was already idle and leaves
    the one still writing to the repo, reparented and invisible, while the next
    spawn starts against a tree something else is mutating. `start_new_session`
    in `spawn` puts the session in a process group of its own precisely so this
    can address the group. Falls back to the single process where there are no
    process groups to address (Windows), which is the best available there.
    """
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), sig)
        else:  # pragma: no cover - POSIX is the supported platform
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        # Already gone, or not ours to signal. Either way there is nothing left
        # to do, and a driver that raised here would turn a handled timeout into
        # a crash.
        pass


def spawn(command: list[str], cwd: Path, timeout: int | None = None) -> int | None:
    """Run one session and return its exit code, or None if it outran `timeout`.

    stdout/stderr are INHERITED, not captured: the session's own result object
    is the operator's only window into a spawn that went wrong, and buffering it
    to print later loses it entirely if the driver itself is killed.

    The exit code is recorded and reported, but it decides nothing. The terminal
    file does. A session can exit non-zero having written a perfectly good
    blocked envelope, and one can exit zero having written nothing at all.

    `None` is the one return that decides something, and it is not an exit code
    at all: it says this session never finished, so nothing it may have left on
    disk describes a terminal.

    This is `Popen` rather than the tidier `subprocess.run` for one reason:
    `run`'s timeout handling kills the direct child ONLY, which is the wrong
    process (see `_terminate`). Owning the wait is what buys the group kill.
    The cost of `start_new_session` is that the session no longer shares the
    driver's terminal process group, so a Ctrl-C at the driver would not reach
    it - hence the SIGINT forwarder, which hands the interrupt on and leaves the
    operator's kill switch working exactly as it did before.
    """
    try:
        proc = subprocess.Popen(command, cwd=str(cwd), start_new_session=True)
    except (OSError, ValueError):
        # A missing or unusable binary. There is no terminal file either way, so
        # the caller's fail-closed read stops the drive on the next line.
        return 127

    def _forward(signum, _frame):  # pragma: no cover - needs a real interrupt
        _terminate(proc, signum)

    try:
        previous = signal.signal(signal.SIGINT, _forward)
    except ValueError:  # pragma: no cover - not the main thread
        previous = None

    try:
        return proc.wait(timeout=timeout or None)
    except subprocess.TimeoutExpired:
        _terminate(proc, _KILL_SIGNAL)
        proc.wait()
        return None
    finally:
        if previous is not None:
            signal.signal(signal.SIGINT, previous)


# --------------------------------------------------------------------------
# the drive
# --------------------------------------------------------------------------


def _summary(
    *,
    epic_key: str | None,
    driven: list[str],
    advanced: list[str],
    skipped: list[str],
    stopped_because: str,
    detail: str | None = None,
) -> dict:
    return {
        "epic": epic_key,
        "driven": list(driven),
        "advanced": list(advanced),
        "skipped_already_done": list(skipped),
        "stopped_because": stopped_because,
        "detail": detail,
    }


def drive(
    *,
    epic: str,
    project_root: Path,
    impl_artifacts: Path,
    permission_mode: str = DEFAULT_PERMISSION_MODE,
    profile: str = PROFILE_PRODUCTION,
    skill_command: str = DEFAULT_SKILL_COMMAND,
    session_timeout: int | None = DEFAULT_SESSION_TIMEOUT,
    limit: int | None = None,
    claude_bin: str = DEFAULT_CLAUDE_BIN,
    dry_run: bool = False,
    out: TextIO | None = None,
) -> dict:
    """Spawn one session per not-done story until something says stop.

    Returns the summary dict the CLI prints and the tests assert on, so a caller
    reads a structure rather than scraping the progress lines.
    """
    stream = sys.stdout if out is None else out

    def say(line: str) -> None:
        print(f"{PREFIX}: {line}", file=stream)

    project_root = Path(project_root)
    impl_artifacts = Path(impl_artifacts)

    epic_key = normalise_epic(epic)
    rollup = preflight_check.build_rollup(project_root, impl_artifacts)

    if not rollup.get("sprint_status_present"):
        say(f"stopped: {STOP_NO_SPRINT_STATUS} - no sprint-status.yaml under {impl_artifacts}")
        return _summary(
            epic_key=epic_key,
            driven=[],
            advanced=[],
            skipped=[],
            stopped_because=STOP_NO_SPRINT_STATUS,
            detail=f"no sprint-status.yaml reachable from {impl_artifacts}",
        )

    # `build_rollup` finds sprint-status.yaml by SEARCH: `--impl-artifacts` first,
    # then `_bmad-output/`, then an rglob under it. The terminal read does no
    # searching at all - `result_path` is `--impl-artifacts` exactly. So a typo'd
    # or stale `--impl-artifacts` still yields a perfectly populated rollup, and
    # the mismatch only surfaces after a full real session has been spawned and
    # blamed for a `no-terminal` the driver caused. Refuse up front instead.
    #
    # STATED BOUND, because the stronger property is not the one being checked:
    # the session writes its terminal to the config-resolved
    # `{workflow.implementation_artifacts}`, which the driver never reads and
    # cannot see. This guard proves only that `--impl-artifacts` is the directory
    # the sprint plan lives in. That catches the operator error worth catching -
    # naming the wrong directory - but an override that moves the config scalar
    # away from the sprint plan's directory is still a `no-terminal` after one
    # burned session, and closing THAT would mean resolving the customize.toml
    # chain here, i.e. a second implementation of the skill's own config
    # resolution, which is a worse trade than the failure it prevents.
    located = preflight_check._locate_sprint_status(project_root, impl_artifacts)
    if located is not None and located.parent.resolve() != impl_artifacts.resolve():
        detail = (
            f"sprint-status.yaml is in {located.parent}, not the --impl-artifacts "
            f"dir {impl_artifacts}; point --impl-artifacts at the former"
        )
        say(f"stopped: {STOP_SPRINT_STATUS_ELSEWHERE} - {detail}")
        return _summary(
            epic_key=epic_key,
            driven=[],
            advanced=[],
            skipped=[],
            stopped_because=STOP_SPRINT_STATUS_ELSEWHERE,
            detail=detail,
        )

    stories = epic_stories(rollup, epic_key) if epic_key else None
    # `epic_key is None` is redundant with `not stories` at RUNTIME (a None key
    # yields None stories two lines up), and it is stated anyway so the narrowing
    # is explicit rather than incidental: everything below this block reads
    # `epic_key` as a `str`, and without this the only thing keeping that true is
    # a chain a later edit could break with no gate to catch it. This module runs
    # no Python typechecker, so the reader is the gate.
    if epic_key is None or not stories:
        say(f"stopped: {STOP_EPIC_NOT_FOUND} - {epic!r} matches no epic in sprint-status.yaml")
        return _summary(
            epic_key=epic_key,
            driven=[],
            advanced=[],
            skipped=[],
            stopped_because=STOP_EPIC_NOT_FOUND,
            detail=f"{epic!r} matches no epic in sprint-status.yaml",
        )

    skipped = done_ids(stories)
    driven: list[str] = []
    advanced: list[str] = []
    command = build_command(claude_bin, epic, permission_mode, skill_command, profile)

    say(
        f"epic {epic} ({len(pending_ids(stories))} not done, "
        f"{len(skipped)} already done) - {profile} profile, mode {permission_mode}"
    )

    if dry_run:
        planned = pending_ids(stories)
        if limit is not None:
            planned = planned[:limit]
        for position, story_id in enumerate(planned, start=1):
            say(f"[{position}/{len(planned)}] {story_id} would run: {shlex.join(command)}")
        say(f"dry run: {len(planned)} spawn(s) planned, none started")
        return _summary(
            epic_key=epic_key,
            driven=[],
            advanced=[],
            skipped=skipped,
            stopped_because=STOP_DRY_RUN,
            detail=f"{len(planned)} spawn(s) planned",
        )

    while True:
        pending = pending_ids(stories)
        if not pending:
            say(f"stopped: {STOP_ALL_DONE} - every story of epic {epic} is done")
            return _summary(
                epic_key=epic_key,
                driven=driven,
                advanced=advanced,
                skipped=skipped,
                stopped_because=STOP_ALL_DONE,
            )

        if limit is not None and len(driven) >= limit:
            say(f"stopped: {STOP_LIMIT} - {limit} spawn(s) run, {len(pending)} story(ies) left")
            return _summary(
                epic_key=epic_key,
                driven=driven,
                advanced=advanced,
                skipped=skipped,
                stopped_because=STOP_LIMIT,
                detail=f"{len(pending)} story(ies) still not done",
            )

        target = pending[0]

        if not clear_result(impl_artifacts):
            say(f"stopped: {STOP_STALE_RESULT} - could not delete {result_path(impl_artifacts)}")
            return _summary(
                epic_key=epic_key,
                driven=driven,
                advanced=advanced,
                skipped=skipped,
                stopped_because=STOP_STALE_RESULT,
                detail=f"could not delete {result_path(impl_artifacts)}",
            )

        say(f"[{len(driven) + 1}] {target} - spawning: {shlex.join(command)}")
        code = spawn(command, project_root, session_timeout)
        driven.append(target)

        if code is None:
            detail = f"{target}: no exit within {session_timeout}s, session killed"
            say(f"stopped: {STOP_SESSION_TIMEOUT} - {detail}")
            return _summary(
                epic_key=epic_key,
                driven=driven,
                advanced=advanced,
                skipped=skipped,
                stopped_because=STOP_SESSION_TIMEOUT,
                detail=detail,
            )

        result = read_result(impl_artifacts)
        if result is None:
            say(f"stopped: {STOP_NO_TERMINAL} - {target} exited {code} leaving no readable result")
            return _summary(
                epic_key=epic_key,
                driven=driven,
                advanced=advanced,
                skipped=skipped,
                stopped_because=STOP_NO_TERMINAL,
                detail=f"{target}: exit {code}, no readable {headless_envelope.RESULT_FILENAME}",
            )

        status = result.get("status")
        if status == STATUS_BLOCKED:
            reason = str(result.get("reason") or "").strip() or "(no reason recorded)"
            say(f"stopped: {STOP_BLOCKED} - {target}: {reason}")
            return _summary(
                epic_key=epic_key,
                driven=driven,
                advanced=advanced,
                skipped=skipped,
                stopped_because=STOP_BLOCKED,
                detail=f"{target}: {reason}",
            )

        if status != STATUS_COMPLETE:
            say(f"stopped: {STOP_UNKNOWN_STATUS} - {target} reported status {status!r}")
            return _summary(
                epic_key=epic_key,
                driven=driven,
                advanced=advanced,
                skipped=skipped,
                stopped_because=STOP_UNKNOWN_STATUS,
                detail=f"{target}: unrecognised status {status!r}",
            )

        rollup = preflight_check.build_rollup(project_root, impl_artifacts)
        stories = epic_stories(rollup, epic_key) or []
        now = status_of(stories, target)
        if now != DONE:
            say(f"stopped: {STOP_NO_PROGRESS} - {target} reported complete but is {now!r}")
            return _summary(
                epic_key=epic_key,
                driven=driven,
                advanced=advanced,
                skipped=skipped,
                stopped_because=STOP_NO_PROGRESS,
                detail=f"{target}: complete envelope, sprint status still {now!r}",
            )

        advanced.append(target)
        say(f"[{len(driven)}] {target} - complete, now done (exit {code})")


def render_summary(summary: dict) -> str:
    """The one closing line. Always printed, whatever the drive did."""
    detail = summary.get("detail")
    tail = f" ({detail})" if detail else ""
    return (
        f"{PREFIX}: summary - driven {len(summary['driven'])}, "
        f"advanced {len(summary['advanced'])}, "
        f"skipped-already-done {len(summary['skipped_already_done'])}, "
        f"stopped because: {summary['stopped_because']}{tail}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Drive an Epic one story per claude -p process, so each story's "
            "context dies with the process that held it."
        )
    )
    parser.add_argument("--epic", required=True, help="Epic id, e.g. 7 or epic-7.")
    parser.add_argument(
        "--project-root",
        default=".",
        help="Repository root. Each session is spawned with this as its cwd.",
    )
    parser.add_argument(
        "--impl-artifacts",
        required=True,
        help=(
            "The run's implementation-artifacts dir: where sprint-status.yaml is "
            "read from and where the terminal result file lands."
        ),
    )
    parser.add_argument(
        "--profile",
        default=PROFILE_PRODUCTION,
        choices=list(PROFILES),
        help=(
            f"The skill's gate profile (default {PROFILE_PRODUCTION}). "
            f"'{PROFILE_LIGHT}' prepends --light, which is what a non-web stack needs."
        ),
    )
    parser.add_argument(
        "--skill-command",
        default=DEFAULT_SKILL_COMMAND,
        help=(
            f"How this install addresses the skill (default {DEFAULT_SKILL_COMMAND}). "
            "A plugin-marketplace install namespaces it as "
            "/bmad-module-ultracode-goal:ultracode-goal."
        ),
    )
    parser.add_argument(
        "--session-timeout",
        type=int,
        default=DEFAULT_SESSION_TIMEOUT,
        help=(
            f"Seconds one session may run before it is killed and the drive stops "
            f"(default {DEFAULT_SESSION_TIMEOUT}). 0 disables the ceiling."
        ),
    )
    parser.add_argument(
        "--permission-mode",
        default=DEFAULT_PERMISSION_MODE,
        help=f"One of {'|'.join(PERMISSION_MODES)} (default {DEFAULT_PERMISSION_MODE}).",
    )
    parser.add_argument(
        "--allow-full-autonomy",
        action="store_true",
        help="Required alongside --permission-mode bypassPermissions. Nothing else uses it.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after this many spawns. Default: unbounded (drive to the end of the Epic).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the exact command each spawn would run, start none of them, delete nothing.",
    )
    parser.add_argument(
        "--claude-bin",
        default=DEFAULT_CLAUDE_BIN,
        help=f"The Claude Code binary to spawn (default {DEFAULT_CLAUDE_BIN}).",
    )
    args = parser.parse_args(argv)

    if args.permission_mode not in PERMISSION_MODES:
        parser.error(
            f"--permission-mode must be one of {', '.join(PERMISSION_MODES)}; "
            f"got {args.permission_mode!r}. These are the values Claude Code 2.1.220 "
            "accepts; the driver does not pass through anything else."
        )

    if args.permission_mode == BYPASS_MODE and not args.allow_full_autonomy:
        parser.error(
            f"--permission-mode {BYPASS_MODE} also requires --allow-full-autonomy. "
            "This driver spawns unattended sessions in a loop, so bypassing permissions "
            "does not skip one prompt an operator would have declined - it lets every "
            "session of every story run anything at all with nobody watching. Pass "
            "--allow-full-autonomy to say that is what you meant, or stay on "
            f"--permission-mode {DEFAULT_PERMISSION_MODE}."
        )

    if not args.skill_command.startswith("/") or args.skill_command.strip() != args.skill_command:
        parser.error(
            f"--skill-command must be a slash command with no surrounding whitespace; got "
            f"{args.skill_command!r}. Anything else is not rejected by Claude Code, it is run as "
            "free-form prompt text - so the session does whatever that sentence suggests instead "
            "of invoking the skill, and the driver waits out the whole ceiling for a terminal "
            "nothing will write."
        )

    if args.limit is not None and args.limit < 1:
        parser.error(f"--limit must be at least 1; got {args.limit}.")

    if args.session_timeout < 0:
        parser.error(
            f"--session-timeout must be 0 (no ceiling) or more; got {args.session_timeout}."
        )

    summary = drive(
        epic=args.epic,
        project_root=Path(args.project_root),
        impl_artifacts=Path(args.impl_artifacts),
        permission_mode=args.permission_mode,
        profile=args.profile,
        skill_command=args.skill_command,
        session_timeout=args.session_timeout or None,
        limit=args.limit,
        claude_bin=args.claude_bin,
        dry_run=args.dry_run,
    )
    print(render_summary(summary))
    return 0 if summary["stopped_because"] in CLEAN_STOPS else 1


if __name__ == "__main__":
    sys.exit(main())
