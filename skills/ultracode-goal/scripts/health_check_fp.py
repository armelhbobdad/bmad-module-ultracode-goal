#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Deterministic fingerprint + seen-cache plumbing for the ultracode-goal health check.

Plumbing ONLY. This script computes the dedup fingerprints of a health-check
finding, reads the machine-local seen-cache into a verdict (asking GitHub for
a recorded issue's state through `gh`, bounded), and merge-writes a record
under a lock. It makes NO submit/queue/route decisions: that judgment lives in
references/health-check.md (the LLM), as do the severity, the section slug and
the defect key it hashes.

The fingerprint is install-mode-invariant: the `step_file` component is ALWAYS
the source-repo form `skills/ultracode-goal/references/{stage}.md` regardless of
where the skill is installed, so the same defect dedups to the same key across a
dev checkout and an installed `_bmad/` tree.

    fp        = "fp-" + sha1("{severity}|ultracode-goal/{stage}|"
                             "skills/ultracode-goal/references/{stage}.md|"
                             "{section-slug}|{defect-key}")[:7]
    legacy_fp = the same hash without "|{defect-key}": the section fingerprint,
                which every defect of one severity in one section shares, and
                the fingerprint versions without the defect key filed under

Subcommands:
  fingerprint --severity S --stage T --section-slug SLUG --defect-key KEY
      Validate S against the 3 severities and T against the 6 stages, SLUG as
      kebab-case (^[a-z0-9]+(-[a-z0-9]+)*$) and KEY as one to four kebab-case
      words (^[a-z0-9]+(-[a-z0-9]+){0,3}$). Emit {"fp", "legacy_fp", "tuple"},
      where `tuple` is the exact sha1 input of `fp`.
  seen --fp FP --legacy-fp FP --cache PATH
      Validate both fingerprints. Emit {"seen": B, "status": S, "record": R,
      "matched_on": M}. The record under --fp decides; only when the cache has
      no --fp key does the record under --legacy-fp decide (M is "fp",
      "legacy_fp", or null when neither is there). On the record found, the
      first branch that matches gives the status:
        1. no record under either fingerprint: unseen
        2. action `resolved`: regression
        3. action created, reacted or commented with an issue_url: the
           issue's own state decides, read with
           `gh issue view <issue_url> --json state,stateReason`, stopped after
           10 seconds (GH_TIMEOUT_SEC) with every process it started. CLOSED
           with stateReason COMPLETED, or MERGED (a resolving pull request), is
           regression; every other answer (OPEN, a NOT_PLANNED close) and every
           failure (no gh, the time limit, a non-zero exit, output that is not
           that JSON) is handled. gh runs only for an issue_url that starts
           with https:// and holds no whitespace (any other value is handled
           without a call), is never one found in the current folder, and
           never runs through a shell.
        4. one of those three actions with no issue_url: handled
        5. no action, any other action (an old `queued` included), or a
           record that is not an object: unrecognized
      A record found only under --legacy-fp may be another defect's, so
      handled becomes unseen (a legacy record never suppresses) and
      regression becomes possible-regression; unrecognized stays.
      `seen` is the SUPPRESSION verdict, true for handled alone: every
      uncertain verdict reports. Missing/empty/corrupt cache -> unseen.
  record --fp FP --cache PATH --issue-url URL --action A --date YYYY-MM-DD
         [--regression]
      Validate FP; A is created, reacted or commented with an https:// URL
      holding no whitespace, or resolved with such a URL or an empty one; the
      date is a real YYYY-MM-DD date. Set the --fp key alone to
      {"issue_url", "action", "date"} and keep every other key. A
      `defect_slug` the replaced record carries is carried over. A `resolved`
      record is never downgraded: without --regression, any other action
      leaves it as it is and emits "written": false (exit 0). The read, merge
      and write hold an OS lock on <cache>.lock (fcntl.flock, or
      msvcrt.locking on Windows), waited on for up to 10 seconds
      (LOCK_WAIT_SEC); the lock file is never deleted. The new file is
      written beside the cache, synced to disk and renamed over it. A cache
      that exists and is not a JSON object is first renamed to
      <cache>.corrupt-<UTC YYYYMMDDTHHMMSSZ> (then -2, -3 in the same second),
      so its records can be repaired by hand; when that rename fails, nothing
      is written. Emit {"written": B, "fp": FP, "record": <what the cache now
      holds under FP>, "set_aside": <the renamed corrupt cache> | null}.
  version --project-root PATH --skill-root PATH
      Resolve the module version off a deterministic first-hit-wins probe ladder
      and emit {"version": "<resolved>", "source": "<which probe hit>"} — or
      {"version": null, "source": "N/A"} when nothing hits. A probe that exists
      but is unreadable/malformed (bad JSON, missing key, empty string) falls
      through to the next rung — it never crashes. The ladder is:
        1. <project-root>/_bmad/ucg/VERSION   (plain text)  -> "_bmad/ucg/VERSION"
        2. <skill-root>/VERSION               (plain text)  -> "{skill-root}/VERSION"
        3. <project-root>/.claude-plugin/marketplace.json    JSON plugins[0].version
                                                            -> "marketplace.json"
        4. <project-root>/package.json         JSON version  -> "package.json"

Output: JSON to stdout. Errors are JSON to stdout with exit code 1 (operational
failure, a value that breaks its rule, or a record that could not take the lock,
set a corrupt cache aside or write); argparse usage errors exit 2. A successful
payload exits 0.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

SEVERITIES = ("bug", "friction", "gap")
STAGES = (
    "ingest-and-scope",
    "preflight",
    "define-done",
    "execute",
    "gate",
    "finalize",
)
ACTIONS = ("created", "reacted", "commented", "resolved")

# Which recorded actions SUPPRESS a later sighting of the same fingerprint.
# Deliberately a literal tuple and NOT `ACTIONS` minus `resolved`: a disposition
# added later then defaults to NOT suppressing until it is opted in here, and a
# missing or unrecognized action (a hand-edited cache, an old `queued` record,
# or one written by a newer module) does not suppress either. That is the
# fail-closed direction for a health check: a duplicate report is closed by the
# dedup Action, while a silenced regression is caught by nothing. When in
# doubt, report.
SUPPRESSING_ACTIONS = ("created", "reacted", "commented")
RESOLVED = "resolved"

# Each rule is matched with fullmatch, so a value ending in a newline fails it.
SLUG_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
DEFECT_KEY_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+){0,3}")
FP_RE = re.compile(r"fp-[0-9a-f]{7}")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
URL_PREFIX = "https://"

GH_TIMEOUT_SEC = 10.0
KILL_WAIT_SEC = 2.0  # each wait once the time limit stops gh: SIGTERM or taskkill, then the child
LOCK_WAIT_SEC = 10.0
_LOCK_POLL_MIN_SEC = 0.01
_LOCK_POLL_MAX_SEC = 0.2
CORRUPT_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
# Windows refuses to rename over a file another process has open (a `seen`
# reading the cache, a virus scanner); the rename is retried for this long.
_IS_WINDOWS = os.name == "nt"
_REPLACE_WAIT_SECONDS = 5.0
_REPLACE_POLL_SECONDS = 0.02


class _WriteError(Exception):
    """record could not read the cache, set a corrupt one aside or write it."""


class _LockBusy(Exception):
    """Another record call held <cache>.lock for the whole wait."""


def _fail(message: str) -> int:
    print(json.dumps({"error": message}))
    return 1


def _sha7(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:7]


def _compute_fp(severity: str, stage: str, slug: str, defect_key: str) -> tuple[str, str, str]:
    """Return (fp, legacy_fp, tuple_string). The tuple string is fp's exact sha1 input."""
    step_file = f"skills/ultracode-goal/references/{stage}.md"
    legacy = f"{severity}|ultracode-goal/{stage}|{step_file}|{slug}"
    keyed = f"{legacy}|{defect_key}"
    return f"fp-{_sha7(keyed)}", f"fp-{_sha7(legacy)}", keyed


def cmd_fingerprint(args: argparse.Namespace) -> int:
    if args.severity not in SEVERITIES:
        return _fail(
            "invalid severity %r; expected one of %s"
            % (args.severity, ", ".join(SEVERITIES))
        )
    if args.stage not in STAGES:
        return _fail(
            "invalid stage %r; expected one of %s" % (args.stage, ", ".join(STAGES))
        )
    if not SLUG_RE.fullmatch(args.section_slug):
        return _fail(
            "invalid section-slug %r; expected kebab-case ^[a-z0-9]+(-[a-z0-9]+)*$"
            % args.section_slug
        )
    if not DEFECT_KEY_RE.fullmatch(args.defect_key):
        return _fail(
            "invalid defect-key %r; expected one to four kebab-case words "
            "^[a-z0-9]+(-[a-z0-9]+){0,3}$" % args.defect_key
        )

    fp, legacy_fp, tuple_str = _compute_fp(
        args.severity, args.stage, args.section_slug, args.defect_key
    )
    print(json.dumps({"fp": fp, "legacy_fp": legacy_fp, "tuple": tuple_str}))
    return 0


# --- the cache ---------------------------------------------------------------


def _parse(raw: bytes) -> dict | None:
    """The cache object in raw bytes: {} for an empty file, None when it is not a JSON object."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):  # RecursionError: nested past the parser's depth
        return None
    return data if isinstance(data, dict) else None


def _load_cache(cache: Path) -> dict:
    """Read the seen-cache as a dict. Missing/empty/unreadable/corrupt -> {} (never raises)."""
    try:
        raw = cache.read_bytes()
    except OSError:
        return {}
    return _parse(raw) or {}


# --- the issue-state check -----------------------------------------------------


def _resolve_outside_cwd(command: str) -> str | None:
    """shutil.which, refusing a resolution into the current folder.

    shutil.which on Windows searches the current folder ahead of PATH, and a
    `.` or empty PATH entry does the same on POSIX. The current folder is the
    user's project, which this module does not control, so a `gh` planted
    there reads as no gh. Returns an absolute path, or None.
    """
    resolved = shutil.which(command)
    if resolved is None:
        return None
    resolved = os.path.abspath(resolved)
    here = os.path.normcase(os.path.realpath(os.getcwd()))
    if os.path.normcase(os.path.realpath(os.path.dirname(resolved))) == here:
        return None
    return resolved


def _child_env() -> dict:
    """os.environ with gh's prompts and update notice turned off."""
    env = dict(os.environ)
    env["GH_PROMPT_DISABLED"] = "1"
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    return env


def _stop(proc: subprocess.Popen, windows: bool = _IS_WINDOWS) -> None:
    """Stop proc and everything it started once the time limit runs out.

    POSIX sends SIGTERM to its process group, then SIGKILL to whatever is
    left; Windows runs taskkill /F /T on its tree.
    """
    try:
        if windows:
            taskkill = _resolve_outside_cwd("taskkill")
            if taskkill:
                subprocess.run(
                    [taskkill, "/F", "/T", "/PID", str(proc.pid)],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=KILL_WAIT_SEC,
                    check=False,
                )
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=KILL_WAIT_SEC)
            except subprocess.TimeoutExpired:
                pass
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    try:
        proc.wait(timeout=KILL_WAIT_SEC)
    except subprocess.TimeoutExpired:
        pass


def _run(argv: list[str], timeout: float) -> tuple[int | None, bytes, bytes]:
    """Run argv with no stdin and no shell; (returncode, stdout, stderr).

    returncode is None when the time limit stopped the call. The call gets a
    process group (a POSIX session) of its own, so _stop reaches all it
    started, and its output goes to temporary files, not pipes, so a child it
    left behind cannot hold a read open. Raises OSError or ValueError when
    argv cannot start.
    """
    kwargs: dict = {}
    if _IS_WINDOWS:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=err_f,
            env=_child_env(),
            **kwargs,
        )
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop(proc)
            returncode = None
        out_f.seek(0)
        err_f.seek(0)
        return returncode, out_f.read(), err_f.read()


def gh_issue_state(issue_url: str, timeout: float | None = None) -> dict | None:
    """`gh issue view <issue_url> --json state,stateReason`: its JSON object, or None on any failure."""
    exe = _resolve_outside_cwd("gh")
    if exe is None:
        return None
    limit = GH_TIMEOUT_SEC if timeout is None else timeout
    try:
        returncode, out, _err = _run(
            [exe, "issue", "view", issue_url, "--json", "state,stateReason"], limit
        )
    except (OSError, ValueError):
        return None
    if returncode != 0:
        return None
    try:
        answer = json.loads(out.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    if not isinstance(answer, dict) or not isinstance(answer.get("state"), str):
        return None
    return answer


def _gh_url(value) -> bool:
    """An issue_url gh may be given: https://, no whitespace (so never a flag)."""
    return (
        isinstance(value, str)
        and value.startswith(URL_PREFIX)
        and not any(ch.isspace() for ch in value)
    )


def _issue_verdict(issue_url) -> str:
    """Branch 3: regression for a completed close or a merge, handled for anything else."""
    if not _gh_url(issue_url):
        return "handled"
    answer = gh_issue_state(issue_url)
    if answer is None:
        return "handled"
    state = answer["state"].upper()
    reason = answer.get("stateReason")
    reason = reason.upper() if isinstance(reason, str) else ""
    if (state == "CLOSED" and reason == "COMPLETED") or state == "MERGED":
        return "regression"
    return "handled"


def _verdict(record) -> str:
    """Branches 2 to 5 on a record that exists."""
    if not isinstance(record, dict):
        return "unrecognized"
    action = record.get("action")
    if action == RESOLVED:
        # Fixed and closed out, so a fresh sighting is a REGRESSION, not a
        # duplicate. The record rides along so the caller can link the original.
        return "regression"
    if action in SUPPRESSING_ACTIONS:
        if record.get("issue_url") in (None, ""):
            return "handled"
        return _issue_verdict(record.get("issue_url"))
    # Absent or unrecognized: we cannot confirm this was handled, so report.
    return "unrecognized"


def cmd_seen(args: argparse.Namespace) -> int:
    if not FP_RE.fullmatch(args.fp):
        return _fail("invalid fp %r; expected ^fp-[0-9a-f]{7}$" % args.fp)
    if not FP_RE.fullmatch(args.legacy_fp):
        return _fail("invalid legacy-fp %r; expected ^fp-[0-9a-f]{7}$" % args.legacy_fp)

    data = _load_cache(Path(args.cache).expanduser())
    if args.fp in data:
        record = data[args.fp]
        status = _verdict(record)
        matched_on = "fp"
    elif args.legacy_fp in data:
        record = data[args.legacy_fp]
        # A section fingerprint may be another defect's: it never suppresses,
        # and a fix it records is only possibly this defect's.
        status = _verdict(record)
        status = {"handled": "unseen", "regression": "possible-regression"}.get(status, status)
        matched_on = "legacy_fp"
    else:
        record = None
        status = "unseen"
        matched_on = None

    print(
        json.dumps(
            {
                "seen": status == "handled",
                "status": status,
                "record": record,
                "matched_on": matched_on,
            }
        )
    )
    return 0


# --- record --------------------------------------------------------------------


def _record_error(fp: str, action: str, issue_url: str, day: str) -> str | None:
    """The rule the record arguments break, or None."""
    if not FP_RE.fullmatch(fp):
        return "invalid fp %r; expected ^fp-[0-9a-f]{7}$" % fp
    if action not in ACTIONS:
        return "invalid action %r; expected one of %s" % (action, ", ".join(ACTIONS))
    if action == RESOLVED:
        if issue_url != "" and not _gh_url(issue_url):
            return (
                "invalid issue-url %r; a resolved record takes an empty URL or one "
                "that starts with %s and holds no whitespace" % (issue_url, URL_PREFIX)
            )
    elif not _gh_url(issue_url):
        return "invalid issue-url %r; expected one that starts with %s and holds no whitespace" % (
            issue_url,
            URL_PREFIX,
        )
    try:
        if not DATE_RE.fullmatch(day):
            raise ValueError
        date.fromisoformat(day)
    except ValueError:
        return "invalid date %r; expected a real date as YYYY-MM-DD" % day
    return None


def _lock_busy(exc: OSError) -> bool:
    return exc.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK, errno.EDEADLK)


def _try_lock(fd: int) -> None:
    """Take an exclusive lock on fd without waiting; OSError when it is held."""
    if _IS_WINDOWS:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fd: int) -> None:
    try:
        if _IS_WINDOWS:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass  # closing the file releases it too


def _acquire(lock: Path, wait: float) -> int:
    """Open <cache>.lock and lock it, waiting up to `wait` seconds with backoff.

    The OS drops the lock when the holder dies, so a lock left by a killed
    call never needs clearing, and the file is never deleted, which avoids
    races on unlink. Raises _LockBusy at the end of the wait, OSError when the
    file cannot be opened or locked.
    """
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    deadline = time.monotonic() + wait
    delay = _LOCK_POLL_MIN_SEC
    while True:
        try:
            _try_lock(fd)
            return fd
        except OSError as exc:
            left = deadline - time.monotonic()
            if not _lock_busy(exc) or left <= 0:
                os.close(fd)
                if _lock_busy(exc):
                    raise _LockBusy() from None
                raise
        time.sleep(min(delay, left))
        delay = min(delay * 2, _LOCK_POLL_MAX_SEC)


def _release(fd: int) -> None:
    _unlock(fd)
    try:
        os.close(fd)
    except OSError:
        pass


def _replace(src: Path | str, dst: Path | str) -> None:
    """os.replace, retried on Windows while another process has dst open."""
    deadline = time.monotonic() + _REPLACE_WAIT_SECONDS
    while True:
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not _IS_WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(_REPLACE_POLL_SECONDS)


def _atomic_write(cache: Path, content: str) -> None:
    """Temp file beside the cache, synced to disk, then renamed over it."""
    fd, tmp_name = tempfile.mkstemp(dir=str(cache.parent), prefix=".hc-seen-", suffix=".tmp")
    try:
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        _replace(tmp_name, cache)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _corrupt_stamp() -> str:
    return datetime.now(timezone.utc).strftime(CORRUPT_STAMP_FORMAT)


def _set_aside(cache: Path) -> Path:
    """Rename a corrupt cache to <cache>.corrupt-<UTC stamp>, never over an earlier one."""
    stamp = _corrupt_stamp()
    aside = cache.with_name(f"{cache.name}.corrupt-{stamp}")
    n = 2
    while os.path.lexists(aside):
        aside = cache.with_name(f"{cache.name}.corrupt-{stamp}-{n}")
        n += 1
    _replace(cache, aside)
    return aside


def _merge(cache: Path, fp: str, new: dict, regression: bool) -> dict:
    """The read, merge and write; runs while the caller holds the lock."""
    set_aside = None
    try:
        raw = cache.read_bytes()
    except FileNotFoundError:
        data = {}
    except OSError as exc:
        raise _WriteError("could not read cache %s: %s" % (cache, exc)) from None
    else:
        data = _parse(raw)
        if data is None:
            try:
                set_aside = _set_aside(cache)
            except OSError as exc:
                raise _WriteError(
                    "could not set aside cache %s, which is not a JSON object: %s; "
                    "nothing was written" % (cache, exc)
                ) from None
            data = {}

    existing = data.get(fp)
    if isinstance(existing, dict):
        if existing.get("action") == RESOLVED and new["action"] != RESOLVED and not regression:
            # Never downgrade a fix: only an issue that tracks the recurrence
            # (--regression) replaces it, so suppression never comes back alone.
            return {"written": False, "fp": fp, "record": existing, "set_aside": None}
        if "defect_slug" in existing:
            # Written by an earlier version of this module; it rides along.
            new = {**new, "defect_slug": existing["defect_slug"]}
    data[fp] = new

    try:
        _atomic_write(cache, json.dumps(data, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        where = " (the corrupt cache was renamed to %s)" % set_aside if set_aside else ""
        raise _WriteError("could not write cache %s: %s%s" % (cache, exc, where)) from None
    return {
        "written": True,
        "fp": fp,
        "record": new,
        "set_aside": str(set_aside) if set_aside else None,
    }


def cmd_record(args: argparse.Namespace) -> int:
    problem = _record_error(args.fp, args.action, args.issue_url, args.date)
    if problem:
        return _fail(problem)

    cache = Path(args.cache).expanduser()
    new = {"issue_url": args.issue_url, "action": args.action, "date": args.date}
    lock = cache.with_name(cache.name + ".lock")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail("could not create %s: %s" % (cache.parent, exc))
    try:
        fd = _acquire(lock, LOCK_WAIT_SEC)
    except _LockBusy:
        return _fail(
            "%s stayed locked by another record call for %s seconds; nothing was written"
            % (lock, LOCK_WAIT_SEC)
        )
    except OSError as exc:
        return _fail("could not take %s: %s" % (lock, exc))
    try:
        result = _merge(cache, args.fp, new, args.regression)
    except _WriteError as exc:
        return _fail(str(exc))
    finally:
        _release(fd)

    print(json.dumps(result))
    return 0


def _read_plain_version(path: Path) -> str | None:
    """Read a plain-text VERSION file. Missing/unreadable/empty -> None."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return None
    stripped = text.strip()
    return stripped or None


def _read_json_version(path: Path, *keys) -> str | None:
    """Read a JSON file and walk `keys` (str=dict key, int=list index).

    Missing file, malformed JSON, a missing/typed-wrong key, or an empty/
    non-string resolved value all yield None so the caller falls through.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return None
    try:
        node = json.loads(text)
    except ValueError:
        return None
    for key in keys:
        if isinstance(key, int):
            if not isinstance(node, list) or not (-len(node) <= key < len(node)):
                return None
            node = node[key]
        else:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
    if not isinstance(node, str):
        return None
    stripped = node.strip()
    return stripped or None


def cmd_version(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).expanduser()
    skill_root = Path(args.skill_root).expanduser()

    # First-hit-wins probe ladder. Each rung that exists-but-is-malformed
    # returns None and falls through to the next.
    ladder = (
        (_read_plain_version(project_root / "_bmad" / "ucg" / "VERSION"), "_bmad/ucg/VERSION"),
        (_read_plain_version(skill_root / "VERSION"), f"{skill_root}/VERSION"),
        (
            _read_json_version(
                project_root / ".claude-plugin" / "marketplace.json",
                "plugins",
                0,
                "version",
            ),
            "marketplace.json",
        ),
        (_read_json_version(project_root / "package.json", "version"), "package.json"),
    )

    for version, source in ladder:
        if version is not None:
            print(json.dumps({"version": version, "source": source}))
            return 0

    print(json.dumps({"version": None, "source": "N/A"}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fingerprint + seen-cache plumbing for the ultracode-goal health check."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fp_parser = sub.add_parser("fingerprint", help="Compute the dedup fingerprints.")
    fp_parser.add_argument("--severity", required=True)
    fp_parser.add_argument("--stage", required=True)
    fp_parser.add_argument("--section-slug", required=True, dest="section_slug")
    fp_parser.add_argument(
        "--defect-key",
        required=True,
        dest="defect_key",
        help="One to four kebab-case words naming the thing the fix would change.",
    )
    fp_parser.set_defaults(func=cmd_fingerprint)

    seen_parser = sub.add_parser("seen", help="The seen-cache verdict for a finding.")
    seen_parser.add_argument("--fp", required=True)
    seen_parser.add_argument("--legacy-fp", required=True, dest="legacy_fp")
    seen_parser.add_argument("--cache", required=True)
    seen_parser.set_defaults(func=cmd_seen)

    rec_parser = sub.add_parser("record", help="Record a fingerprint outcome to the cache.")
    rec_parser.add_argument("--fp", required=True)
    rec_parser.add_argument("--cache", required=True)
    rec_parser.add_argument("--issue-url", required=True, dest="issue_url")
    rec_parser.add_argument("--action", required=True)
    rec_parser.add_argument("--date", required=True)
    rec_parser.add_argument(
        "--regression",
        action="store_true",
        help="After a regression verdict: the issue tracks the recurrence, so it "
        "replaces a resolved record.",
    )
    rec_parser.set_defaults(func=cmd_record)

    ver_parser = sub.add_parser("version", help="Resolve the module version off the probe ladder.")
    ver_parser.add_argument("--project-root", required=True, dest="project_root")
    ver_parser.add_argument("--skill-root", required=True, dest="skill_root")
    ver_parser.set_defaults(func=cmd_version)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
