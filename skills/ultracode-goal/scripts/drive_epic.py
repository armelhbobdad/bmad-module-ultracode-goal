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

FAIL-CLOSED AT EVERY DECISION, and there are six of them:

  | after a spawn                            | driver does           |
  | a forwarded signal reached the driver    | STOP (`signalled`)    |
  | the session outran `--session-timeout`   | KILL it, STOP         |
  | no result file, or it will not parse     | RETRY once or twice,  |
  |                                          | else STOP (`no-terminal`)|
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

THE ONE RETRY, AND WHY IT IS ONLY THIS ONE. A `claude -p` subprocess can be
terminated in flight by the API layer; the child exits non-zero having written
no terminal, so it lands on `no-terminal`, NOT on `signalled` - that branch
fires only when a signal reached the DRIVER, which is a person interrupting.
Measured across one 22-spawn session: eleven such deaths, at 4 / 6 / 14 / 20 /
53 / 80 / 95 / 154 / 175 / 222 turns. No turn-count pattern, no story pattern,
and the same row landing on the next attempt against identical state. There is
nothing to detect in advance and nothing to avoid, so the only useful response
is to try again - which an operator did eight times by hand, and which is the
only reason that epic advanced.

Every OTHER stop keeps its single-shot fail-closed behaviour, because each of
them means something specific that a second identical spawn cannot change.

POST-STOP TRIAGE, AND IT IS THE RETRY'S PRECONDITION rather than a convenience.
A killed spawn leaves wildly different states: a clean tree with HEAD advanced
means the work COMMITTED and only close-out is missing; a dirty tree may hold a
suite that is already green, or half a module worth reverting. The driver used
to report none of it, so an unattended loop discarded the first kind and would
re-spawn over the second. Every non-clean stop now prints a triage block, and a
retry is taken ONLY on the one reading that means nothing landed (clean tree,
HEAD unmoved). It reports and never decides: committing another session's
unfinished work needs judgment about whether the SUBJECT is complete, not merely
whether it compiles.

The triage is read-only git (`status`, `rev-parse`), so the read-only property
above is unchanged. It calls out intent-to-add paths BY NAME, because such an
entry carries a BLANK index column and `A` in the worktree column, so the
obvious `^A ` match - which reads the index column - misses every one of them,
and `git checkout -- <path>` then truncates one to zero bytes and exits 0.

The status read is `--porcelain -z`, and that is not cosmetic. Without `-z` git
C-QUOTES any path holding a space or a non-ASCII byte, so a file named
`a -> b.txt` arrives quoted and splits on its own arrow, and `café.rs` arrives
as octal escapes. Both then name a file that does not exist, inside the very
warning that tells an operator which files to back up before reverting. Under
`-z` nothing is quoted and the bytes are the path.

An UNREADABLE pre-spawn HEAD (an unborn HEAD: `git init` with no commit yet) is
its own reading, never "nothing landed". Folding it into "unmoved" let a session
make a project's first-ever commit, die before its terminal, and be re-driven
over work already on disk.

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
        [--max-abort-retries N] [--limit N] [--dry-run] [--claude-bin PATH]

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
from typing import Any, TextIO

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

# How many times one story may be re-spawned after a spawn died leaving no
# terminal. Two, because two was sufficient for every case measured across a
# 22-spawn session; the one row that died three times running needed an operator,
# and a cap is what surfaces that rather than hiding it behind an eleventh
# attempt. 0 disables the retry and restores the stop-on-first-abort behaviour.
#
# The bound is per STORY and it is small on purpose. A retry is only ever taken
# over a tree the triage found clean with HEAD unmoved, so it cannot destroy
# work, but a generous cap would still let a genuinely broken invocation - a bad
# `--skill-command`, a missing binary - burn N sessions before saying so.
DEFAULT_MAX_ABORT_RETRIES = 2

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
STOP_SIGNALLED = "signalled"

# The stops that mean "this invocation finished its work", i.e. exit 0. A
# signalled stop is deliberately NOT one: the operator interrupted the drive.
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
    except (OSError, ValueError):
        # ValueError covers UnicodeDecodeError, which is NOT an OSError and is
        # reachable rather than theoretical: the adapter serializes with
        # `ensure_ascii=False`, so a legitimate terminal can carry multi-byte
        # UTF-8, and this driver SIGKILLs a session that outran its ceiling -
        # possibly mid-write. A truncated multi-byte sequence read back here
        # would raise straight out of the drive, replacing the fail-closed
        # `no-terminal` stop this function documents with a traceback, at the
        # one moment the operator most needs the summary line.
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

# Every signal that stops the driver must be handed on, for the same reason the
# SIGINT forwarder exists: `start_new_session` detaches the session, so a signal
# that kills the driver reaches nothing else, and `--session-timeout` is enforced
# solely by the driver's own `proc.wait(timeout=...)` - it dies with the driver.
# SIGINT is the interactive kill switch; SIGTERM is a plain `kill`, a `timeout N`
# wrapper, systemd, or a cancelled CI job; SIGHUP is a closed terminal or a
# dropped ssh session, which is exactly how an overnight drive ends. Forwarding
# only the first leaves the other two orphaning a session that keeps committing
# under `acceptEdits` with no wall clock at all. Resolved by name, never
# referenced directly, because SIGHUP is POSIX-only (see `_KILL_SIGNAL`).
_FORWARDED_SIGNALS = tuple(
    sig
    for sig in (getattr(signal, name, None) for name in ("SIGINT", "SIGTERM", "SIGHUP"))
    if sig is not None
)

# Set by the forwarder, read by the drive loop. Forwarding alone kills the
# SESSION; this is what stops the DRIVE, and without it handling these signals
# is strictly worse than leaving them at their default disposition. The default
# terminated the driver outright. A handler that returns does not: the `wait()`
# the signal interrupted simply resumes (PEP 475), the terminal the dying
# session had already written reads as an ordinary completion, and the loop
# spawns the NEXT story - so `kill <driver>` would start a fresh unattended
# session under `acceptEdits` instead of ending the run.
_STOPPED_BY_SIGNAL: int | None = None


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
    driver's terminal process group, so a signal sent to the driver would not
    reach it - hence the forwarder, installed for every signal in
    `_FORWARDED_SIGNALS`. It hands each one on, leaving the operator's kill
    switch working exactly as it did before and, more importantly, making sure
    that whatever stops the driver also stops the session it was timing.
    """
    try:
        proc = subprocess.Popen(command, cwd=str(cwd), start_new_session=True)
    except (OSError, ValueError):
        # A missing or unusable binary. There is no terminal file either way, so
        # the caller's fail-closed read stops the drive on the next line.
        return 127

    def _forward(signum, _frame):
        global _STOPPED_BY_SIGNAL
        if _STOPPED_BY_SIGNAL is not None:
            # Asked twice. The first signal was forwarded and the session is
            # still up, so it is absorbing or ignoring that signal and the
            # polite path would leave the operator waiting out the remaining
            # ceiling - up to `DEFAULT_SESSION_TIMEOUT`, or forever under
            # `--session-timeout 0`. Escalate: hard-kill the whole group, then
            # let this signal take the driver at its default disposition, so
            # the second Ctrl-C (or `kill`) ends things the way an operator
            # expects. The group kill goes FIRST so dying here still cannot
            # orphan the session.
            _terminate(proc, _KILL_SIGNAL)
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
            return
        _STOPPED_BY_SIGNAL = signum
        _terminate(proc, signum)

    previous: list[tuple[int, Any]] = []
    for sig in _FORWARDED_SIGNALS:
        try:
            if signal.getsignal(sig) is signal.SIG_IGN:
                # Inherited SIG_IGN is a decision the environment already made -
                # `nohup` ignores SIGHUP precisely so a long drive survives a
                # dropped terminal. Installing over it would revoke that for the
                # duration of every spawn, i.e. for almost the whole drive.
                continue
            previous.append((sig, signal.signal(sig, _forward)))
        except (ValueError, OSError):  # pragma: no cover - not the main thread
            pass

    try:
        return proc.wait(timeout=timeout or None)
    except subprocess.TimeoutExpired:
        _terminate(proc, _KILL_SIGNAL)
        proc.wait()
        return None
    finally:
        for sig, handler in previous:
            if handler is not None:
                signal.signal(sig, handler)


# --------------------------------------------------------------------------
# the drive
# --------------------------------------------------------------------------


def _git_out(repo: Path, *args: str) -> str | None:
    """A git command's stdout, or None when git is absent or the call failed.

    Fail-soft on purpose: the triage below is a REPORT, and a report that
    crashed the driver would be worse than the silence it replaces.

    DECODED AS UTF-8 EXPLICITLY, not by the locale. `text=True` alone decodes
    with the platform's preferred encoding, which on Windows is a legacy code
    page (cp1252 on the CI runners), while git emits path bytes as UTF-8. A file
    named `café.rs` therefore came back mojibake there - which is the same defect
    class as the quoting bug this triage already had to fix: a warning naming a
    file that does not exist. `errors="replace"` keeps the fail-soft posture for
    a path that is genuinely not UTF-8, so an undecodable name degrades to a
    visibly mangled entry rather than raising mid-triage.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, ValueError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def head_sha(repo: Path) -> str | None:
    """The repo's current HEAD, or None when it cannot be read."""
    out = _git_out(repo, "rev-parse", "HEAD")
    return out.strip() if out and out.strip() else None


def porcelain_entries(porcelain_z: str) -> list[tuple[str, str, str]]:
    """Parse `git status --porcelain -z` into (index_col, worktree_col, path).

    ``-z`` IS LOAD-BEARING, not a style choice. Without it git C-QUOTES any path
    carrying a space or a non-ASCII byte, so `a -> b.txt` arrives as
    ``" A \\"a -> b.txt\\""`` and `café.rs` as ``" A \\"caf\\\\303\\\\251.rs\\""``.
    Both were mis-read here: the first was split on its own ` -> ` and reported
    as `b.txt`, the second reported with its octal escapes intact. Each names a
    file that DOES NOT EXIST, inside the warning that tells an operator which
    files to back up before a destructive revert. Under ``-z`` git never quotes
    and the bytes are the path.

    Fields are NUL-separated. A rename or copy is followed by ONE extra field
    holding the original path, which is consumed here rather than mistaken for
    the next entry.
    """
    fields = porcelain_z.split("\0")
    out: list[tuple[str, str, str]] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if len(field) < 4:
            continue
        x, y, path = field[0], field[1], field[3:]
        if x in "RC" or y in "RC":
            index += 1  # the origPath field that trails a rename/copy
        if path:
            out.append((x, y, path))
    return out


def intent_to_add_paths(entries: list[tuple[str, str, str]]) -> list[str]:
    """Paths staged with `git add -N`, which `git checkout --` TRUNCATES.

    THE COLUMNS ARE THE POINT. An intent-to-add entry has a BLANK index column
    and ``A`` in the worktree column, so the obvious ``^A `` match - which reads
    the index column - misses every one of them. A `git checkout -- <path>`
    against one then rewrites it to ZERO BYTES and exits 0, silently, because
    the index entry it restores from is empty.

    Read off the parsed columns rather than sniffed out of the raw line, because
    every string-sniffing shortcut here has a filename that defeats it.

    This lives in code rather than in an operator's memory because it is a
    destructive-data hazard that fires exactly when someone is cleaning up after
    a crash, which is when they are least likely to be reading carefully.
    """
    return [path for x, y, path in entries if x == " " and y == "A"]


def _relative_to_repo(repo: Path, path: Path) -> str | None:
    """`path` as a repo-relative POSIX prefix, or None when it is outside."""
    try:
        rel = Path(os.path.relpath(Path(path).resolve(), Path(repo).resolve()))
    except (OSError, ValueError):
        return None
    text = rel.as_posix()
    return None if text == "." or text.startswith("..") else text


def post_stop_triage(repo: Path, head_before: str | None, run_artifacts: Path | None = None) -> dict:
    """Describe the tree a killed spawn left behind. REPORT, never decide.

    A spawn that dies mid-flight leaves one of several very different states and
    the right response differs for each: a clean tree with HEAD advanced means
    the work committed and only close-out is missing; a dirty tree may hold work
    that is already green, or a half-written module worth reverting. The driver
    used to say nothing at all, so an unattended loop discarded the first kind
    and re-spawned over the second.

    Deliberately does NOT auto-rescue. Committing another session's unfinished
    work needs judgment about whether the SUBJECT is complete, not merely whether
    it compiles, and that judgment is not the driver's. Reporting "tree clean,
    HEAD advanced, story not marked" already turns a lost session into a one-line
    fix, which is the whole of the available win.

    Read-only: `status` and `rev-parse` only. The driver's hands stay off the
    tree, which is the property that makes it safe to point at a run in flight.

    AN UNREADABLE `head_before` IS ITS OWN READING, never "nothing landed". The
    sample is taken before the spawn and fails on an unborn HEAD - a greenfield
    `git init` project with nothing committed yet, which is a shape this module
    is advertised to run on. Folding that into "unmoved" let a session commit the
    story's first-ever commit, die before its terminal, and be re-driven twice
    over work already on disk. Unknown is not unmoved.
    """
    # `-uall` because the default COLLAPSES an untracked directory to a single
    # `?? _bmad-output/` entry, which no per-file prefix test can match - so the
    # run-artifacts exclusion below silently missed the commonest case, and the
    # report named a directory where an operator needs the files.
    porcelain = _git_out(repo, "status", "--porcelain", "-z", "--untracked-files=all")
    head_after = head_sha(repo)
    triage = {
        "git_available": porcelain is not None and head_after is not None,
        "tree_clean": None,
        "head_before": head_before,
        "head_after": head_after,
        "head_moved": None,
        "dirty_paths": [],
        "run_artifact_paths": [],
        "intent_to_add": [],
        "reading": "unknown",
    }
    if porcelain is None or head_after is None:
        return triage

    # The RUN ARTIFACTS are not story work, and counting them as such would kill
    # the retry outright in any project that does not gitignore them. The driver
    # deletes the pinned terminal file there itself before every spawn, so if
    # that file is tracked the tree is dirty by the driver's own hand,
    # permanently and on every lap. Excluded from the safety judgment, still
    # listed in the report.
    ignored = _relative_to_repo(repo, run_artifacts) if run_artifacts is not None else None

    def is_run_artifact(path: str) -> bool:
        return bool(ignored) and (path == ignored or path.startswith(f"{ignored}/"))

    entries = porcelain_entries(porcelain)
    story_dirty = [(x, y, p) for x, y, p in entries if not is_run_artifact(p)]
    triage["tree_clean"] = not story_dirty
    triage["dirty_paths"] = [f"{x}{y} {p}" for x, y, p in story_dirty]
    triage["run_artifact_paths"] = [f"{x}{y} {p}" for x, y, p in entries if is_run_artifact(p)]
    triage["intent_to_add"] = [
        p for p in intent_to_add_paths(entries) if not is_run_artifact(p)
    ]
    if head_before is not None:
        triage["head_moved"] = head_before != head_after

    if head_before is None:
        # Unknown, and therefore not safe: see the docstring.
        triage["reading"] = "head-unknown"
    elif triage["tree_clean"] and triage["head_moved"]:
        triage["reading"] = "committed-close-out-missing"
    elif triage["tree_clean"]:
        triage["reading"] = "nothing-landed"
    else:
        triage["reading"] = "dirty-work-in-tree"
    return triage


def render_triage(triage: dict) -> list[str]:
    """The triage block's lines, in the order an operator needs to read them."""
    if not triage.get("git_available"):
        return ["triage: git unreadable here, so the tree state is unknown"]

    reading = triage["reading"]
    lines: list[str] = []
    if reading == "head-unknown":
        lines.append(
            "triage: HEAD before the spawn was UNREADABLE (an unborn HEAD, or git "
            f"declined), so whether anything landed cannot be told. Tree is "
            f"{'clean' if triage['tree_clean'] else 'DIRTY'} at "
            f"{(triage['head_after'] or '?')[:7]}. Inspect before re-driving; not retried."
        )
    elif reading == "committed-close-out-missing":
        lines.append(
            "triage: tree CLEAN and HEAD ADVANCED "
            f"({(triage['head_before'] or '?')[:7]} -> {(triage['head_after'] or '?')[:7]}) "
            "- the work committed and only close-out is missing; verify the subject, "
            "then set the sprint row to done. Do NOT re-drive this story."
        )
    elif reading == "nothing-landed":
        lines.append(
            "triage: tree CLEAN and HEAD UNMOVED "
            f"({(triage['head_after'] or '?')[:7]}) - nothing landed; this story is safe to re-drive."
        )
    else:
        lines.append(
            f"triage: tree DIRTY, {len(triage['dirty_paths'])} path(s), HEAD "
            + ("ADVANCED" if triage["head_moved"] else "UNMOVED")
            + f" ({(triage['head_after'] or '?')[:7]}) - the spawn may have left work that is "
            "already green. Run the project's build-and-pass command before deciding, and do "
            "NOT re-drive over this tree."
        )
        for path in triage["dirty_paths"][:20]:
            lines.append(f"  dirty: {path}")
        if len(triage["dirty_paths"]) > 20:
            lines.append(f"  dirty: ... and {len(triage['dirty_paths']) - 20} more")

    if triage["intent_to_add"]:
        lines.append(
            f"  DANGER: {len(triage['intent_to_add'])} intent-to-add path(s) below. "
            "`git checkout -- <path>` TRUNCATES these to zero bytes and exits 0. "
            "Back them up and verify the copies before reverting anything."
        )
        for path in triage["intent_to_add"]:
            lines.append(f"  intent-to-add: {path}")
    return lines


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
    max_abort_retries: int = DEFAULT_MAX_ABORT_RETRIES,
    out: TextIO | None = None,
) -> dict:
    """Spawn one session per not-done story until something says stop.

    Returns the summary dict the CLI prints and the tests assert on, so a caller
    reads a structure rather than scraping the progress lines.
    """
    stream = sys.stdout if out is None else out

    global _STOPPED_BY_SIGNAL
    _STOPPED_BY_SIGNAL = None

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
    retry_target: str | None = None
    attempts_spent = 0
    # Every `claude -p` this invocation started, retries included. `driven` is
    # the distinct stories taken on; the two diverge the moment a retry fires.
    spawns_run = 0
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

        # Counted in SPAWNS, not distinct stories. A retry is a paid `claude -p`
        # session like any other, so bounding `len(driven)` - which a retry pops
        # back down - would let `--limit N` spend up to N*(1+max_abort_retries)
        # sessions. `--limit` is the operator's spend bound; it counts what runs.
        if limit is not None and spawns_run >= limit:
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
        # Per STORY, not per drive: a retry budget spent on one row must not
        # leave the next row unable to survive its own first abort.
        if target != retry_target:
            retry_target = target
            attempts_spent = 0

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

        head_before = head_sha(project_root)
        spawns_run += 1
        say(f"[{spawns_run}] {target} - spawning: {shlex.join(command)}")
        code = spawn(command, project_root, session_timeout)
        driven.append(target)

        def stop(because: str, detail: str) -> dict:
            """Stop, but describe the tree first.

            Every POST-SPAWN stop routes through here so the triage cannot be
            attached to some exits and forgotten on others - which is how a
            killed spawn's already-green work went unreported in the first place.
            The pre-spawn stops (no sprint status, epic not found, a stale
            terminal that survived its delete) deliberately do not: nothing has
            run on this lap, so there is no post-spawn tree to describe.
            """
            say(f"stopped: {because} - {detail}")
            for line in render_triage(post_stop_triage(project_root, head_before, impl_artifacts)):
                say(line)
            return _summary(
                epic_key=epic_key,
                driven=driven,
                advanced=advanced,
                skipped=skipped,
                stopped_because=because,
                detail=detail,
            )

        if _STOPPED_BY_SIGNAL is not None:
            # Checked BEFORE the terminal is read, because a session killed by
            # the forwarded signal may already have written a perfectly good
            # `complete` envelope. Reading it first would advance the story and
            # start the next spawn - turning the operator's stop request into a
            # new unattended session.
            try:
                name = signal.Signals(_STOPPED_BY_SIGNAL).name
            except ValueError:  # pragma: no cover - a signum outside the enum
                name = str(_STOPPED_BY_SIGNAL)
            return stop(STOP_SIGNALLED, f"{target}: {name} received, session terminated")

        if code is None:
            return stop(
                STOP_SESSION_TIMEOUT,
                f"{target}: no exit within {session_timeout}s, session killed",
            )

        result = read_result(impl_artifacts)
        if result is None:
            # A spawn that DIED IN FLIGHT lands here, not on `signalled`. The
            # signal branch above fires only when a signal reached the DRIVER;
            # an API-level abort of the `claude -p` subprocess kills the child,
            # which exits non-zero having written no terminal. Measured: eleven
            # of twenty-two spawns in one session, at 4 / 6 / 14 / 20 / 53 / 80 /
            # 95 / 154 / 175 / 222 turns - no turn-count pattern, no story
            # pattern, and the same row succeeding on the next attempt against
            # identical state. There is nothing to detect in advance and nothing
            # to avoid, so the only available response is to try again.
            #
            # BOUNDED, AND ONLY OVER A TREE THAT IS SAFE TO RE-SPAWN OVER. A
            # retry across a dirty tree is how work that was already green gets
            # destroyed, so the triage is the precondition, not a nicety: retry
            # only when the tree is clean AND HEAD has not moved, which is the
            # one reading that means nothing landed. A clean tree with HEAD
            # ADVANCED is the opposite case - the work committed and only
            # close-out is missing - and re-driving it would redo a delivered
            # story.
            triage = post_stop_triage(project_root, head_before, impl_artifacts)
            retryable = triage["reading"] == "nothing-landed"
            if retryable and attempts_spent < max_abort_retries:
                attempts_spent += 1
                say(
                    f"{target}: exit {code}, no terminal written - tree clean and HEAD "
                    f"unmoved, so nothing landed; retrying "
                    f"({attempts_spent} of {max_abort_retries})"
                )
                driven.pop()  # the retry is the same story, not a second one
                continue
            detail = f"{target}: exit {code}, no readable {headless_envelope.RESULT_FILENAME}"
            if attempts_spent:
                detail += f" (after {attempts_spent} retry attempt(s))"
            elif not retryable:
                detail += " (not retried: the tree is not in a safe re-spawn state)"
            return stop(STOP_NO_TERMINAL, detail)

        status = result.get("status")
        if status == STATUS_BLOCKED:
            reason = str(result.get("reason") or "").strip() or "(no reason recorded)"
            return stop(STOP_BLOCKED, f"{target}: {reason}")

        if status != STATUS_COMPLETE:
            return stop(STOP_UNKNOWN_STATUS, f"{target}: unrecognised status {status!r}")

        rollup = preflight_check.build_rollup(project_root, impl_artifacts)
        stories = epic_stories(rollup, epic_key) or []
        now = status_of(stories, target)
        if now != DONE:
            # Triaged like every other post-spawn stop, and this is the one where
            # the tree matters most: a session that claimed `complete` while the
            # sprint row stayed put is exactly the shape where the work may have
            # committed and only the `done` sync is missing.
            return stop(
                STOP_NO_PROGRESS, f"{target}: complete envelope, sprint status still {now!r}"
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
        "--max-abort-retries",
        type=int,
        default=DEFAULT_MAX_ABORT_RETRIES,
        help=(
            f"How many times to re-spawn one story after a spawn died leaving no "
            f"terminal (default {DEFAULT_MAX_ABORT_RETRIES}). A retry is taken ONLY "
            f"when the post-stop triage finds the tree clean and HEAD unmoved, so it "
            f"can never re-spawn over work in progress. 0 disables it."
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
        max_abort_retries=max(0, args.max_abort_retries),
    )
    print(render_summary(summary))
    return 0 if summary["stopped_because"] in CLEAN_STOPS else 1


if __name__ == "__main__":
    sys.exit(main())
