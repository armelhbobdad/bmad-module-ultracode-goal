#!/usr/bin/env python3
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
a mutation over a red baseline proves nothing.

Classification, per row:

  - GREEN            the command stayed green: the mutation SURVIVED. This is
                     the output that matters - a guard that cannot fail - so
                     the ledger leads with these.
  - KILLED           red, the expected case named in the output, and exactly
                     one failure counted.
  - KILLED+others    red and named, but more than one case failed (or the
                     count could not be parsed): the kill stands, the extra
                     reds are surfaced rather than silently absorbed.
  - MISATTRIBUTED    red, but the expected case never appears beside a
                     failure token (or the output's own count says 0 failed):
                     something failed, and it was not the observer this row
                     claims to test. The name must sit on a line that speaks
                     of failure, because verbose reporters echo PASSING names.
  - STALE / NOT UNIQUE / UNDECODABLE  the anchor (or the file) did not hold;
                     nothing was mutated for the row.

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

# Failure-count shapes across the common runners (pytest, vitest/jest, mocha,
# cargo, go). First match wins; no match means the count is unparseable and the
# kill is reported without the exactly-one claim.
_FAIL_COUNT_RES = (
    re.compile(r"(\d+)\s+failed", re.IGNORECASE),
    re.compile(r"failures[:=]\s*(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s+failing", re.IGNORECASE),
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


def _fail_count(output: str) -> int | None:
    for pattern in _FAIL_COUNT_RES:
        match = pattern.search(output)
        if match:
            return int(match.group(1))
    return None


_FAIL_TOKEN_RE = re.compile(r"fail|error|not ok|assert|✗|✘", re.IGNORECASE)


def _named_in_failure_context(output: str, expect_red: str) -> bool:
    """True when the expected case is named on a line that speaks of failure.

    A whole-output substring match is defeated by any verbose reporter that
    echoes PASSING names (`pytest -v` prints every test), which made a wrongly
    attributed kill read as a clean one. So the name only counts on a line
    that also carries a failure token. Heuristic, and documented as one: a
    runner whose failure lines carry none of the tokens reads MISATTRIBUTED,
    which fails toward the honest side - a human looks.
    """
    return any(
        expect_red in line and _FAIL_TOKEN_RE.search(line)
        for line in output.splitlines()
    )


def _classify_red(output: str, expect_red: str) -> tuple[str, str, bool]:
    """(status, detail, is_finding) for a red run."""
    if not _named_in_failure_context(output, expect_red):
        return (
            "MISATTRIBUTED",
            f"red, but {expect_red!r} never appears beside a failure token - "
            "whatever failed, it was not the observer this row claims",
            True,
        )
    count = _fail_count(output)
    if count == 1:
        return "KILLED", f"exactly {expect_red!r} went red", False
    if count == 0:
        # A red exit whose own summary counts zero failures is a collection or
        # harness error wearing a red exit code, not the observer firing.
        return (
            "MISATTRIBUTED",
            "red, but the output's own count says 0 failed - a collection or "
            "harness error, not the observer",
            True,
        )
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

        target.write_bytes(text.replace(row["anchor"], row["replacement"], 1).encode("utf-8"))
        try:
            code, output = _run(row["command"], project_root)
        finally:
            # Restore is unconditional and verified, never assumed: an earlier
            # hand-rolled run in the field lost a file to its own cleanup. A
            # restore WRITE that fails is the tree-dirty case and must land in
            # the exit-2 refusal lane, not propagate as a traceback into the
            # findings exit code.
            try:
                target.write_bytes(original)
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
            status, detail, is_finding = _classify_red(output, row["expect_red"])
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
