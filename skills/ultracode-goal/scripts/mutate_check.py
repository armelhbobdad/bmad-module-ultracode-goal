#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Drive a table of mutations against a green baseline, and prove each one red.

The module's anti-vacuity discipline says a guard is non-vacuous only under
mutation. Every run used to hand-roll the harness for that into scratch space
(and delete it at story end, so the next story hand-rolled it again). This is
the tracked form: a table in, a ledger out, with the properties the hand-rolled
versions kept losing built in as refusals rather than reminders.

Table (JSON array; every key a string, all five required, ``note`` optional):

    [{"file": "src/guard.py",
      "anchor": "if depth > MAX_DEPTH:",
      "replacement": "if False:",
      "command": "npx turbo run test --force --filter=guard",
      "expect_red": "test_depth_guard_fires",
      "note": "AC-3 twin"}]

Per row, in order: assert the anchor occurs EXACTLY once (0 occurrences is
reported distinctly as STALE - the formatter-reflow signature - and more than
one as NOT UNIQUE, because a duplicated anchor mutates a different site than it
reports); back the file up; apply; run the command; classify; restore from the
backup and verify the restore BYTE-IDENTICAL. Before any row: run every
distinct command once and refuse the whole table unless all are green, because
a mutation over a red baseline proves nothing. Each write, the mutation and
the restore alike, leaves the file's mtime in a later whole second than it
had: CPython reuses cached bytecode whose recorded source mtime (in whole
seconds) and size match, so a same-size mutation and its restore written
within one second would otherwise run each other's bytecode.

Classification, per row:

  - GREEN            the command stayed green: the mutation SURVIVED. This is
                     the output that matters - a guard that cannot fail - so
                     the ledger leads with these.
  - KILLED           red, the expected case named in the output, and exactly
                     one failure counted.
  - KILLED+others    red and named, but more than one case failed (or the
                     count could not be parsed): the kill stands, the extra
                     reds are surfaced rather than silently absorbed.
  - MISATTRIBUTED    red, but the output's own count says 0 failed (checked
                     first: a collection or harness error, so no test the row
                     names went red), or the expected case never appears
                     beside a failure token: something failed, and it was not
                     the observer this row claims to test. The name must sit
                     on a line that speaks of failure, because verbose
                     reporters echo PASSING names.
  - STALE / NOT UNIQUE / UNDECODABLE  the anchor (or the file) did not hold;
                     nothing was mutated for the row.

Node's test runner is read in its two default reporters. The spec reporter
(the default even when the output is captured, since Node 23) marks a failed
test with U+2716 and a passed one with U+2714, and ends with a summary line
`fail N` behind U+2139. The TAP reporter (the default for captured output
before Node 23) writes `not ok`, `ok N` for a pass and `# fail N`. jest names
a failed test on the line U+25CF heads, the only such line under its default
reporter (several test files, no --verbose) and its agent reporter (which
jest picks under Claude Code); --verbose adds U+2715 (U+00D7 on Windows).
vitest marks a failed test with U+00D7.

The failure count is read from each run's summary line: Node's `fail N`, the
`Tests` line of jest and vitest, and pytest's last line, where a test's setup
or teardown `error` counts as a failure too. jest's `Test Suites` line and
vitest's `Test Files` line count files, a test file that failed to load among
them, so once a `Tests` line was read neither is: a test file jest or vitest
cannot load runs no test. Node's test runner reports a test file whose process
failed as a failed test of its own, named after the file and located at the
file's line 1, column 1. That test does not count when the file could not
load, which Node shows by printing the error that stopped it, or when the
row's own test was reported, since that test then ran to its end: a file whose
tests pass and whose process then exits non-zero reads 0 failed, a harness
error. A process that exits or crashes during a test (a `process.exit` the
mutant reaches, a heap the test fills) reports neither that test nor such an
error, so while the row's test is not reported the file's test counts, and the
row reads as a kill, as a pytest test whose process dies does. A file Node
interrupts, as a `timeout` around the command does, is counted as cancelled,
not failed, so nothing is taken off for it. An error collecting a test module
or a test class does not count either: pytest names it with an `ERROR
collecting <path>` header and a short summary line `ERROR <path>` with no `::`
test id (a directory's path when a conftest.py in it fails to import) or
`ERROR <path>::<Class>`, an id whose last part starts with a capital letter and
that holds no parameters' `[...]`, and no test there ran. The path can hold a
space. Nor does a conftest.py that pytest loads before it collects and
cannot import: it writes `ImportError while loading conftest '<path>'.` and
stops, with no summary, before any test runs. So a mutant that breaks a module
such a file imports (a dropped colon, say) reads 0 failed rather than a kill.
When the output holds several summaries, as a command that runs two suites or
two runners does, their counts are added, and the collection errors of each
pytest run are taken off its own stats line only.

A count in another shape (mocha's `N failing`, cargo's `N failed`) is read
only when no summary counted a failure and no `-qq` run listed a failed test,
and never from a line inside pytest's report, from the first rule of its own
sections (ERRORS, FAILURES, PASSES, the warnings, the short summary and the
rest, or a `!` rule) to its stats line: a test's traceback, message or
captured output there can quote any count, such as a `0 failed` a test prints.
Any other `=` rule, such as a banner a script prints before cargo runs, opens
no report.

A failure word inside the expected name never counts: a test named "fails
when ..." supplies its own. A line never counts as a failure line when it
reports a pass or only names a test: one that starts with a pass mark
(U+2714, U+2713 as jest and vitest print it, U+221A as jest prints it on
Windows, or TAP's `ok N`) or with U+25B6 (spec) or `# Subtest:` (TAP), a
pytest line that reports `PASSED` or holds only a test id, a source line
quoted in a jest or vitest code frame, or a line of pytest's PASSES section.
Colour codes and a task runner's line prefix (turbo's `<package>:<task>: `,
pnpm's `<package dir> <script>: `) are removed before any line is read.

Exit code: 0 when every row KILLED (with or without +others); 1 when any row
is GREEN, MISATTRIBUTED, STALE, NOT UNIQUE or UNDECODABLE (each is a finding
about the suite or the table); 2 on a refusal - invalid table, red baseline, or a
restore that did not verify byte-identical (the one failure mode that leaves
the tree dirty, so it aborts the run rather than annotating it).

The task-runner cache rule binds the table's ``command`` verbatim: an
unchanged task hash replays the pre-mutation green, so every mutation
"survives" with zero failing cases. Defeat the cache in the command itself
(``--force`` and friends); this runner cannot do it for you.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

REQUIRED_KEYS = ("file", "anchor", "replacement", "command", "expect_red")


def _refuse(message: str) -> "SystemExit":
    """Exit 2, the refusal lane. `raise SystemExit(str)` would exit 1 and be
    indistinguishable from a findings run; the docstring promises 2."""
    print(f"REFUSED: {message}", file=sys.stderr)
    return SystemExit(2)


def _terminated(signum, _frame):
    raise SystemExit(128 + signum)


def _install_signal_unwind() -> None:
    """Convert termination signals into SystemExit so `finally` restores run.

    SIGTERM's default disposition kills the interpreter WITHOUT unwinding, so
    the finally block that restores a mutated file never executes - and TERM
    is the exact kill a harness timeout delivers mid-command. SIGKILL cannot
    be caught: after any abnormal end, `git status` before trusting the tree.
    """
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _terminated)
        except (ValueError, OSError):
            continue

# The summary lines that count one run's failed tests, each a whole line of
# its own, so a "3 failed" quoted inside an assertion message cannot win:
# Node's `fail N` behind U+2139 (spec reporter) or `#` (TAP), the `Tests:`
# line of jest and the `Tests` line of vitest (which reads `no tests` when no
# test file loaded), and pytest's last line, with or without its `=` rule. A
# run prints one, `fail 0` included for Node, so the counts of every summary
# are added: a command that runs a passing suite first, or one runner and then
# another, does not read 0 failed.
_NODE_FAIL_SUMMARY_RE = re.compile(r"^[ \t]*(?:ℹ|#)[ \t]*fail[ \t]+(\d+)[ \t]*$", re.IGNORECASE)
_TESTS_SUMMARY_RE = re.compile(r"^\s*Tests:?\s+(.*?(?:\b\d+ total|\(\d+\))|no tests)\s*$")
# jest's `Test Suites:` line and vitest's `Test Files` line, above their
# `Tests` line, count test files, and a file that failed to load counts as a
# failed one: `Test Suites: 1 failed, 1 passed` beside `Tests: 1 passed`. Once
# a `Tests` line was read, the count the fallback shapes below would take from
# that line is no test's failure, so neither line is read for one.
_FILES_SUMMARY_RE = re.compile(r"^\s*Test (?:Suites:|Files\s)")
# pytest 9 counts passed subtests apart, `2 subtests passed`, in the same line
# (a failed subtest counts in `failed`).
_PYTEST_SUMMARY_RE = re.compile(r"^=*\s*((?:\d+ (?:subtests )?\w+, )*\d+ (?:subtests )?\w+) in [\d.]+s\b.*$")
_SUMMARY_FAILED_RE = re.compile(r"\b(\d+) failed\b")
# pytest counts a test whose fixture raised as an `error`, not a failure, and
# never prints "0 failed": without these, every setup error read 0 failed.
_PYTEST_ERRORS_RE = re.compile(r"\b(\d+) errors?\b")
# An error collecting a module is counted in the same `error` total, but no
# test in that module ran, so it is no failure. pytest heads it `ERROR
# collecting <path>` in its ERRORS section and lists it in the short summary as
# `ERROR <path>`, a path with no `::` test id after it (a setup error's line
# carries one). The path is a module's, or a directory's when a conftest.py in
# it, which pytest loads while it collects, fails to import, and it can hold a
# space. A class pytest cannot collect (a parametrize `ids` function that
# raised, say) is listed as `ERROR <path>::<Class>`, and no test in it ran
# either: an id whose last part starts with a capital letter names a class, as
# pytest's default `Test*` and PEP 8 name one, while a test's id ends at a
# function, which they name in lower case. That line is read only from the short
# summary's own header to its end (the stats line, or the next `=` or `!`
# rule): a failing fixture's captured output, printed above it, can hold a line
# such as `ERROR bound-not-enforced`, and read anywhere it took the row's own
# setup-error kill off the count. An entry can run over several lines (pytest
# prints each one's whole message under `-vv` or when `CI` is set, and under
# xdist a collection error's message is its traceback), so the section does
# not end at the first line that opens no entry, and inside it only a token
# shaped like a path pytest collected counts: one ending in `.py`, one with a
# path separator, or a name that exists under the project root (`ERROR sub`,
# a top-level directory whose conftest.py failed). A skip reason or a kill's
# message that runs over lines can hold `ERROR connection-refused`. Without
# xdist the run also stops with `Interrupted: N error(s) during collection`;
# under xdist it does not, and the other modules still run. Under `-qq` with
# xdist pytest prints neither that line nor a stats line, so a short summary
# that lists collection errors and no test (no `FAILED` entry, no `ERROR` entry
# with a test's `::` id) means no test failed. Only a test's id carries its
# parameters' `[...]`, whose text can hold `::` and a capital letter of its own
# (`test_x[App::Models::User]`), so an id that holds one never names a class.
_PYTEST_COLLECTING_RE = re.compile(r"^_+ ERROR collecting (.+?) _+$")
_PYTEST_SHORT_HEADER_RE = re.compile(r"^=+ short test summary info =+$")
_PYTEST_SECTION_END_RE = re.compile(r"^(?:=+ .+ =+|!+ .+ !+)$")
# pytest's report opens at the first of its own sections, each a rule that
# names it: those that quote a test's traceback, message or captured output
# (ERRORS, FAILURES and XFAILURES, PASSES and XPASSES, the warnings), the
# durations and the short summary. pytest alone prints a `!` rule (`Interrupted:
# N errors during collection`, `stopping after N failures`). Any other `=` rule
# opens nothing: a task runner's banner, or `=== fixtures seeded ===` that a
# passing Node test prints, is no sign that pytest ran.
_PYTEST_REPORT_OPEN_RE = re.compile(
    r"^(?:=+ (?:ERRORS|X?FAILURES|X?PASSES|warnings summary(?: \(final\))?|slowest (?:\d+ )?durations"
    r"|short test summary info) =+|!+ .+ !+)$"
)
# A short summary entry: its outcome, its path up to a `::` id or the ` - `
# before its message, and the id.
_PYTEST_SHORT_ENTRY_RE = re.compile(r"^(FAILED|ERROR) ((?:(?!::| - ).)+)((?:::(?:(?! - ).)+)?)(?: - .*)?$")
# One command can run pytest twice. A run ends at its stats line, and a `-qq`
# run, which prints none, where the next run opens: at `test session starts`,
# at an ERRORS, FAILURES or short summary rule after its own short summary,
# since pytest prints each of those before its short summary, or at a progress
# line (`..F  [100%]`), which a `-q` run prints before its report.
_PYTEST_REPORT_RE = re.compile(r"^=+ (?:ERRORS|FAILURES|short test summary info) =+$")
_PYTEST_SESSION_RE = re.compile(r"^=+ test session starts =+$")
_PYTEST_PROGRESS_RE = re.compile(r"^[.,FEsxXuy-]+\s*\[\s*(?:\d+%|\d+/\d+)\]\s*$")
_PYTEST_INTERRUPTED_RE = re.compile(r"Interrupted: (\d+) errors? during collection")
# A conftest.py pytest loads before it collects (the rootdir's, say) that fails
# to import, whatever it raised, stops pytest before any test runs, under xdist
# too: it writes this line and the error, and exits 4 with no summary and no
# `ERROR collecting` line.
_PYTEST_CONFTEST_RE = re.compile(r"^ImportError while loading conftest '.+'\.$")
# A module the root conftest names in `pytest_plugins`, or a plugin pytest loads
# at startup, that fails to import is not wrapped as a conftest error: pytest
# dies with a bare traceback through its config setup and exit 1, before any
# test runs.
_PYTEST_STARTUP_CRASH_RE = re.compile(
    r'^\s*File ".*[/\\]_pytest[/\\]config[/\\]__init__\.py", line \d+, in _prepareconfig$'
)

# Node's test runner runs each test file in a process of its own. When that
# process fails (the file cannot load, its process exits non-zero after its
# tests ran, or it dies during a test), Node reports a failed test of its own,
# counted in `fail N`, and names it after the file: U+2716 and the path in the
# spec reporter, `not ok N - <path>` in TAP, the path relative to the directory
# node ran in (absolute on Node 20). A test of the file's own is located
# wherever it is declared, so only the runner's test is located at the file's
# line 1, column 1: `test at <path>:1:1` directly above it in the spec
# reporter's list of failing tests, `location: '<path>:1:1'` in its TAP block.
_NODE_FAILED_TEST_RE = re.compile(r"^\s*(?:✖|not ok \d+ -) (.+?)(?: \([\d.]+m?s\))?\s*$")
_NODE_PASSED_TEST_RE = re.compile(r"^\s*ok \d+\b")
_NODE_SPEC_AT_RE = re.compile(r"^\s*test at (.+):1:1\s*$")
_NODE_TAP_LOCATION_RE = re.compile(r"^\s*location: '(.+):1:1'\s*$")
# A test Node reports as it ends, passed, failed or skipped: U+2714, U+2716 or
# U+FE63 in the spec reporter, `ok N -` or `not ok N -` in TAP. A process that
# dies during a test reports neither that test nor, unless they ended well
# before it, the file's other tests.
_NODE_REPORTED_TEST_RE = re.compile(r"^\s*(?:✔|✖|﹣|(?:not )?ok \d+ -) (.+?)(?: \([\d.]+m?s\))?(?: # .*)?\s*$")
# A test file that cannot load (a syntax error, a module it cannot find, a
# throw or a failed assert at its top level) dies of an uncaught error, which
# Node prints ending with a line that names its own version (behind `#` in
# TAP). A process that exits or crashes during a test prints no such line.
_NODE_LOAD_ERROR_RE = re.compile(r"^\s*(?:#\s*)?Node\.js v\d+\.\d+\.\d+\s*$")
# A test file Node interrupted, as a `timeout` around the command makes it:
# listed under `Interrupted while running:` as `⚠ <path> (<path>:1:1)`, and
# counted under `cancelled`, not in `fail N`, though its runner's test is also
# reported failed.
_NODE_INTERRUPTED_RE = re.compile(r"^\s*⚠ (.+?) \((.+):1:1\)\s*$")

# Failure-count shapes across the other common runners (mocha, cargo, and any
# runner whose summary is not one of the above). First match wins; no match
# means the count is unparseable and the kill is reported without the
# exactly-one claim. `[ \t]` keeps a digit that ends one line from pairing
# with a FAILED that opens the next. None is read inside pytest's report.
_FAIL_COUNT_RES = (
    re.compile(r"(\d+)[ \t]+failed", re.IGNORECASE),
    re.compile(r"failures[:=][ \t]*(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)[ \t]+failing", re.IGNORECASE),
)


def _load_table(path: Path) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _refuse(f"table {path} unreadable or not JSON: {exc}")
    if not isinstance(raw, list) or not raw:
        raise _refuse(f"table {path} must be a non-empty JSON array of rows")
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise _refuse(f"row {index} is not an object")
        for key in REQUIRED_KEYS:
            if not isinstance(row.get(key), str) or not row[key]:
                raise _refuse(f"row {index} is missing required string key {key!r}")
        if row["anchor"] == row["replacement"]:
            raise _refuse(
                f"row {index} anchor and replacement are identical - "
                "that mutation mutates nothing"
            )
    return raw


_NS = 1_000_000_000


def _write_later(path: Path, data: bytes) -> None:
    """Write data, leaving the file's mtime in a later whole second than before.

    CPython (and pytest's assertion rewriting) reuses cached bytecode whose
    recorded source mtime, in whole seconds, and size match the file, so two
    same-size versions of one module written within one second run each
    other's bytecode. The mtime only ever moves forward, never back to the
    original's: tools that rebuild what is newer than its output (make,
    cargo) would keep a build of the mutation otherwise.
    """
    try:
        before = path.stat().st_mtime_ns // _NS
    except OSError:
        # Gone (the command deleted it): the write below recreates it.
        before = None
    path.write_bytes(data)
    try:
        stat = path.stat()
        if before is not None and stat.st_mtime_ns // _NS <= before:
            os.utime(path, ns=(stat.st_atime_ns, (before + 1) * _NS))
    except OSError:
        # The content is written; only the cache protection is lost.
        pass


def _run(command: str, cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        # utf-8 + replace, never the strict locale codec: a failing assertion
        # that dumps raw bytes must classify as a red, not crash the run - and
        # on Windows the locale default (cp1252) also mojibakes the very names
        # attribution matches on.
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except (OSError, ValueError):
        return False


def _collected_path(token: str, root: Path | None) -> bool:
    """Whether a short summary entry's path names what pytest collected. A
    path that holds a space counts only when it is there: a line of a message
    that runs over lines can open with `ERROR` and words."""
    if " " in token:
        return root is not None and _exists(root / token)
    if token.endswith(".py") or "/" in token or "\\" in token:
        return True
    return root is not None and _exists(root / token)


def _names_a_class(test_id: str) -> bool:
    """Whether a short summary entry's `::` id ends at a class: its last part
    starts with a capital letter, and it holds no parameters' `[...]`, which
    only a test's id carries and whose text can hold `::` itself
    (`test_x[App::Models::User]`)."""
    if "[" in test_id:
        return False
    last = test_id.rsplit("::", 1)[-1]
    return bool(last) and last[0].isupper()


def _collection_errors(lines: list[str], root: Path | None = None) -> tuple[int, bool, bool, bool]:
    """How many of one pytest run's counted errors were errors collecting a
    module, a directory or a class, whether no test failed (pytest stopped at
    them, or at a conftest.py or a startup plugin it could not load, before
    running any test, or its short summary lists collection errors and no
    test), whether the lines hold pytest's output at all, and whether its
    short summary lists a test that failed or errored."""
    headers = sum(1 for line in lines if _PYTEST_COLLECTING_RE.match(line))
    short = 0
    interrupted = 0
    stopped = False
    seen = headers > 0
    in_summary = False
    tests_listed = False
    for line in lines:
        if _PYTEST_SHORT_HEADER_RE.match(line):
            in_summary = seen = True
            continue
        if _PYTEST_SUMMARY_RE.match(line) or _PYTEST_REPORT_RE.match(line):
            seen = True
        if in_summary and (_PYTEST_SUMMARY_RE.match(line) or _PYTEST_SECTION_END_RE.match(line)):
            in_summary = False
        if in_summary:
            entry = _PYTEST_SHORT_ENTRY_RE.match(line)
            if entry and _collected_path(entry.group(2), root):
                outcome, test_id = entry.group(1), entry.group(3)
                if outcome == "ERROR" and (not test_id or _names_a_class(test_id)):
                    short += 1
                elif test_id:
                    tests_listed = True
        halt = _PYTEST_INTERRUPTED_RE.search(line)
        if halt:
            interrupted += int(halt.group(1))
            stopped = seen = True
        if _PYTEST_CONFTEST_RE.match(line) or _PYTEST_STARTUP_CRASH_RE.match(line):
            stopped = seen = True
    if short and not tests_listed:
        stopped = True
    return max(headers, short, interrupted), stopped, seen, tests_listed


def _same_file(name: str, location: str) -> bool:
    """Whether a test's name and a location's path name one file: equal, or
    one ends with the other after a separator (Node 20 names a file by its
    absolute path, and TAP doubles each backslash in both)."""
    name, location = (re.sub(r"[\\/]+", "/", path) for path in (name, location))
    return name == location or name.endswith("/" + location) or location.endswith("/" + name)


def _node_file_failures(lines: list[str], expect_red: str | None = None) -> int:
    """How many of the failed tests Node's `fail N` counts are the runner's own
    and no test's failure. The runner's test for a file whose process failed is
    named after the file and located at its line 1, column 1. It is no test's
    failure when the file could not load, one for each load error Node printed,
    or, all of them, when the row's own test was reported: that test ran to its
    end, so a process that failed did so outside it, as one that exits non-zero
    after its tests pass does. Otherwise a process died during a test, before
    Node reported the row's test, and its runner's test is that test's
    failure. A file Node interrupted is counted as cancelled, not in `fail N`,
    so it is never taken off."""
    files: set[str] = set()
    interrupted: set[str] = set()
    reported: set[str] = set()
    load_errors = 0
    spec_at = None
    tap_failed = None
    for line in lines:
        failed = _NODE_FAILED_TEST_RE.match(line)
        if failed:
            if spec_at is not None and _same_file(failed.group(1), spec_at):
                files.add(failed.group(1))
            tap_failed = failed.group(1)
        elif _NODE_PASSED_TEST_RE.match(line):
            tap_failed = None
        location = _NODE_TAP_LOCATION_RE.match(line)
        if location:
            if tap_failed is not None and _same_file(tap_failed, location.group(1)):
                files.add(tap_failed)
            tap_failed = None
        test = _NODE_REPORTED_TEST_RE.match(line)
        if test:
            reported.add(test.group(1))
        stopped = _NODE_INTERRUPTED_RE.match(line)
        if stopped and _same_file(stopped.group(1), stopped.group(2)):
            interrupted.add(stopped.group(1))
        if _NODE_LOAD_ERROR_RE.match(line):
            load_errors += 1
        # The spec reporter's location line sits directly above its test.
        at = _NODE_SPEC_AT_RE.match(line)
        spec_at = at.group(1) if at else None
    counted = len(files - interrupted)
    if expect_red and any(expect_red in name for name in reported - files):
        return counted
    return min(counted, load_errors)


def _fail_count(lines: list[str], root: Path | None = None, expect_red: str | None = None) -> int | None:
    summed: int | None = None
    others: list[str] = []
    tests_read = False
    # Inside pytest's report, from its first section rule to its stats line,
    # every line is a test's traceback, message or captured output, which can
    # quote any count, so none is read for another runner's count.
    in_report = False
    # Taken off Node's summaries, once in all.
    node_files = _node_file_failures(lines, expect_red)
    # The current pytest run's lines. Its collection errors are taken off its
    # own stats line only: a command that runs pytest twice, with flags that
    # print different signs of them, does not pool the two runs' counts.
    run: list[str] = []
    run_reported = False
    unsummarised: list[tuple[bool, bool]] = []

    def close_run() -> None:
        _, stopped, seen, listed = _collection_errors(run, root)
        if seen:
            unsummarised.append((stopped, listed))

    for line in lines:
        session = _PYTEST_SESSION_RE.match(line)
        if session or (run_reported and (_PYTEST_REPORT_RE.match(line) or _PYTEST_PROGRESS_RE.match(line))):
            # A run that printed no stats line (`-qq`) ends where the next opens.
            close_run()
            run, run_reported = [], False
            in_report = False
        run.append(line)
        run_reported = run_reported or bool(_PYTEST_SHORT_HEADER_RE.match(line))
        node = _NODE_FAIL_SUMMARY_RE.match(line)
        tests = _TESTS_SUMMARY_RE.match(line)
        pytest_summary = None if tests else _PYTEST_SUMMARY_RE.match(line)
        summary = tests or pytest_summary
        if not pytest_summary and _PYTEST_REPORT_OPEN_RE.match(line):
            in_report = True
        if node:
            count = int(node.group(1))
            uncounted = min(count, node_files)
            node_files -= uncounted
            count -= uncounted
        elif summary:
            failed = _SUMMARY_FAILED_RE.search(summary.group(1))
            count = int(failed.group(1)) if failed else 0
            tests_read = tests_read or bool(tests)
            if pytest_summary:
                in_report = False
                collection = _collection_errors(run, root)[0]
                errors = sum(int(n) for n in _PYTEST_ERRORS_RE.findall(summary.group(1)))
                count += errors - min(errors, collection)
                run, run_reported = [], False
        else:
            if not in_report:
                others.append(line)
            continue
        summed = (summed or 0) + count
    close_run()
    if summed:
        return summed
    # A pytest run that printed no stats line (`-qq` prints none, and a
    # conftest's or a startup plugin's failure none at all) counted none of
    # the tests its short summary lists as failed, so the count is not known,
    # whatever count another runner printed beside it (`0 failed` included).
    if any(listed for _, listed in unsummarised):
        return None
    # No summary counted a failure: another runner in the same command may
    # have printed its count in a shape not listed above. A `Tests` line has
    # counted the tests jest or vitest ran, so the files line beside it counts
    # none of them.
    if tests_read:
        others = [line for line in others if not _FILES_SUMMARY_RE.match(line)]
    for pattern in _FAIL_COUNT_RES:
        for line in others:
            match = pattern.search(line)
            if match:
                return int(match.group(1))
    # Every such run stopped at a collection error, or at a conftest.py or a
    # startup plugin it could not load, before any test ran, or listed only
    # collection errors: no test failed.
    if summed is None and unsummarised and all(stopped for stopped, _ in unsummarised):
        return 0
    return summed


# U+2716 is the failure mark of Node's spec reporter, U+2715 jest's, and
# U+00D7 vitest's (and jest's on Windows); U+2717 and U+2718 are the crosses
# other runners print. U+25CF heads each failed test's block in jest's
# output, the only line that names it under jest's default reporter (several
# test files, no --verbose) and its agent reporter.
_FAIL_TOKEN_RE = re.compile(r"fail|error|not ok|assert|✖|✕|×|✗|✘|●", re.IGNORECASE)

# Lines that name a test without reporting its failure. U+2714 (Node's spec
# reporter), U+2713 (jest, vitest), U+221A (jest on Windows) and TAP's `ok N`
# lead a line for a PASSING test, and U+25B6 (spec) and `# Subtest:` (TAP)
# only open a suite or a test.
_PASS_LINE_RE = re.compile(r"^\s*(?:✔|✓|√|▶|ok\s+\d+\b|#\s*Subtest:)")

# pytest's PASSED lines: `-v` puts the outcome after the test id, with an
# optional progress percentage, xdist's `-v` puts it after the worker and the
# percentage, and `-rA` leads its summary line with it.
_PYTEST_PASSED_RE = re.compile(
    r"^\s*(?:\[gw\d+\]\s*(?:\[\s*\d+%\]\s*)?)?PASSED\s|\sPASSED(?:\s+\[\s*\d+%\])?\s*$"
)

# A bare pytest test id: xdist's `-v` prints one when a test starts, before
# any outcome.
_PYTEST_STARTED_RE = re.compile(r"^\s*\S+\.py::\S+\s*$")

# A source line quoted in a code frame, which jest (`  5 | ...`, `> 5 | ...`)
# and vitest (`  5| ...`) print around each failed assertion: it quotes the
# neighbouring tests' declarations, whatever their outcome.
_CODE_FRAME_RE = re.compile(r"^\s*>?\s*\d+\s*\|")

# A pytest section rule, such as `=== PASSES ===`. The PASSES section, which
# `-rA` prints for each passing test that wrote output, holds only passing
# tests, each under a header that names it.
_PYTEST_SECTION_RE = re.compile(r"^=+ (.+?) =+$")

# A task runner's prefix on each line of a task's output: turbo writes
# `<package>:<task>: ` and pnpm's recursive run `<package dir> <script>: `.
# Removed, a pass mark behind it leads the line again and a summary behind it
# is a whole line again.
_TASK_PREFIX_RE = re.compile(
    r"^(?:[\w@.-]+(?:/[\w@.-]+)*:[\w.:-]+|[\w@.-]*(?:/[\w@.-]+)+ [\w.:-]+): "
)

# Colour codes a runner emits when FORCE_COLOR is set or it thinks it has a
# terminal. Left in, they sit between a line's start and its mark.
_ANSI_SGR_RE = re.compile(r"\x1b\[[0-9;]*m")


def _output_lines(output: str) -> list[str]:
    """The output's lines without colour codes or a task runner's prefix."""
    return [
        _TASK_PREFIX_RE.sub("", line, count=1)
        for line in _ANSI_SGR_RE.sub("", output).splitlines()
    ]


def _named_in_failure_context(lines: list[str], expect_red: str) -> bool:
    """True when the expected case is named on a line that speaks of failure.

    A whole-output substring match is defeated by any verbose reporter that
    echoes PASSING names (`pytest -v` prints every test), which made a wrongly
    attributed kill read as a clean one. So the name only counts on a line
    that also carries a failure token outside the name itself (a test named
    "fails when ..." supplies its own), and never on a line a reporter marks
    passed, a bare test id, a code-frame line or a line of pytest's PASSES
    section. Heuristic, and documented as one: a runner whose failure lines
    carry none of the tokens reads MISATTRIBUTED, which fails toward the
    honest side - a human looks.
    """
    in_passes = False
    for line in lines:
        section = _PYTEST_SECTION_RE.match(line)
        if section:
            in_passes = section.group(1) == "PASSES"
            continue
        if (
            in_passes
            or expect_red not in line
            or _PASS_LINE_RE.match(line)
            or _PYTEST_PASSED_RE.search(line)
            or _PYTEST_STARTED_RE.match(line)
            or _CODE_FRAME_RE.match(line)
        ):
            continue
        if _FAIL_TOKEN_RE.search(line.replace(expect_red, " ")):
            return True
    return False


def _classify_red(output: str, expect_red: str, root: Path | None = None) -> tuple[str, str, bool]:
    """(status, detail, is_finding) for a red run. `root` is the directory the
    command ran in, so a bare name in pytest's short summary can be checked."""
    lines = _output_lines(output)
    count = _fail_count(lines, root, expect_red)
    if count == 0:
        # A red exit whose own summary counts zero failures is a collection or
        # harness error wearing a red exit code, not the observer firing. It
        # is read before the name: a collection error never names the test, and
        # read as a missing name it looked like some other test's kill.
        return (
            "MISATTRIBUTED",
            "red, but the output's own count says 0 failed - a collection or "
            "harness error, not the observer",
            True,
        )
    if not _named_in_failure_context(lines, expect_red):
        return (
            "MISATTRIBUTED",
            f"red, but {expect_red!r} never appears beside a failure token - "
            "whatever failed, it was not the observer this row claims",
            True,
        )
    if count == 1:
        return "KILLED", f"exactly {expect_red!r} went red", False
    if count is None:
        return "KILLED+others", f"{expect_red!r} went red; failure count unparseable", False
    return "KILLED+others", f"{expect_red!r} went red among {count} failures", False


def run_table(table: list[dict], project_root: Path) -> tuple[list[dict], int]:
    """Execute the table; return (ledger rows, exit code)."""
    # Baseline first, each distinct command once, in first-appearance order.
    seen: list[str] = []
    for row in table:
        if row["command"] not in seen:
            seen.append(row["command"])
    for command in seen:
        code, output = _run(command, project_root)
        if code != 0:
            raise _refuse(
                "baseline is not green for command "
                f"{command!r} (exit {code}) - a mutation over a red baseline "
                f"proves nothing. Last lines:\n{output[-2000:]}"
            )

    rows: list[dict] = []
    findings = False
    for index, row in enumerate(table):
        target = project_root / row["file"]
        entry = {
            "index": index,
            "file": row["file"],
            "expect_red": row["expect_red"],
            "note": row.get("note", ""),
            "restore": "n/a",
        }
        try:
            original = target.read_bytes()
        except OSError as exc:
            entry.update(status="STALE", detail=f"file unreadable: {exc}")
            rows.append(entry)
            findings = True
            continue
        try:
            text = original.decode("utf-8")
        except UnicodeDecodeError as exc:
            entry.update(status="UNDECODABLE", detail=f"file is not UTF-8: {exc}")
            rows.append(entry)
            findings = True
            continue
        occurrences = text.count(row["anchor"])
        if occurrences != 1:
            entry.update(
                status="STALE" if occurrences == 0 else "NOT UNIQUE",
                detail=(
                    f"anchor occurs {occurrences} times - "
                    + (
                        "0 is the formatter-reflow signature; re-derive the anchor"
                        if occurrences == 0
                        else "a duplicated anchor mutates a different site than it reports"
                    )
                ),
            )
            rows.append(entry)
            findings = True
            continue

        _write_later(target, text.replace(row["anchor"], row["replacement"], 1).encode("utf-8"))
        try:
            code, output = _run(row["command"], project_root)
        finally:
            # Restore is unconditional and verified, never assumed: an earlier
            # hand-rolled run in the field lost a file to its own cleanup. A
            # restore WRITE that fails is the tree-dirty case and must land in
            # the exit-2 refusal lane, not propagate as a traceback into the
            # findings exit code.
            try:
                _write_later(target, original)
            except OSError as exc:
                raise _refuse(
                    f"restore of {row['file']} FAILED ({exc}) - the tree still "
                    "carries the mutation; fix the tree before trusting "
                    "anything else this run printed"
                ) from exc
        if target.read_bytes() != original:
            raise _refuse(
                f"restore of {row['file']} did not verify byte-identical - "
                "the tree is dirty; fix that before trusting anything else this run printed"
            )
        entry["restore"] = "verified"

        if code == 0:
            entry.update(
                status="GREEN",
                detail="the mutation SURVIVED: nothing in the suite can tell - this is a finding",
            )
            findings = True
        else:
            status, detail, is_finding = _classify_red(output, row["expect_red"], project_root)
            entry.update(status=status, detail=detail)
            findings = findings or is_finding
        rows.append(entry)

    return rows, 1 if findings else 0


_LEDGER_ORDER = {"GREEN": 0, "MISATTRIBUTED": 1, "STALE": 2, "NOT UNIQUE": 2, "UNDECODABLE": 2}


def render_ledger(rows: list[dict]) -> str:
    """The generated markdown ledger, GREEN survivors first."""
    ordered = sorted(rows, key=lambda r: (_LEDGER_ORDER.get(r["status"], 9), r["index"]))
    greens = sum(1 for r in rows if r["status"] == "GREEN")
    killed = sum(1 for r in rows if r["status"].startswith("KILLED"))
    lines = [
        "# Mutation ledger",
        "",
        f"{len(rows)} rows: {greens} GREEN (survived), {killed} killed, "
        f"{len(rows) - greens - killed} not applied.",
        "",
        "| # | status | file | expected red | detail | restore | note |",
        "|---|--------|------|--------------|--------|---------|------|",
    ]
    for r in ordered:
        lines.append(
            f"| {r['index']} | {r['status']} | `{r['file']}` | `{r['expect_red']}` "
            f"| {r['detail']} | {r['restore']} | {r['note']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a mutation table against a green baseline; ledger out, greens first."
    )
    parser.add_argument("--table", required=True, help="PATH to the JSON mutation table.")
    parser.add_argument(
        "--project-root",
        default=".",
        help="Directory row file paths resolve against and commands run in (default: cwd).",
    )
    parser.add_argument(
        "--output",
        help="Also write the markdown ledger to this PATH (it always prints to stdout).",
    )
    args = parser.parse_args(argv)

    _install_signal_unwind()
    table = _load_table(Path(args.table))
    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        raise _refuse(f"project root {project_root} is not a directory")

    rows, exit_code = run_table(table, project_root)
    ledger = render_ledger(rows)
    print(ledger)
    if args.output:
        Path(args.output).write_text(ledger, encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
