#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Say whether TEA's trace still scores an AC the operator moved out of the story.

An `operator-evidence-owed` escalation can close on the operator's written move
of an AC out of the story: its numbered item leaves `## Acceptance Criteria`
for a section of its own, and its number is retired. TEA's trace has no status
for a moved criterion. It scores every criterion it resolves, from the story,
the epic, the PRD or the test design, so an AC that left the story's list can
still be a row of its coverage matrix, scored NONE, and that row fails the
gate, or holds it at CONCERNS, over work the story no longer owes.
`references/gate.md` runs this check on every gate cycle after a move, once
trace has written its files and before `gate_eval.py` runs, whatever the gate
status and in either profile. Only a pass lets the gate run; a row or an
unreadable matrix escalates `operator-evidence-owed` again, never a re-loop.

gate_eval.py is not changed and no verdict is added. The matrix is read through
operator_owed.read_matrix, with the same cross-checks: the story's own
`trace-<id>.md`, an absolute `tempCoverageMatrixPath` naming a PHASE_1_COMPLETE
matrix whose P0-P3 counts and requirement recount agree with the story's own
`e2e-trace-summary-<id>.json`, a summary that names the commit it measured
(`source_sha`), and a matrix `source_sha`, when the matrix has one, naming the
same commit. This script then requires that commit to be `--commit`, the
commit under assessment, so a previous gate's trace files never read as this
one's, and every requirement id to be a string. Anything it cannot read is a
refusal (FAIL-CLOSED).

A row is a moved AC's when an AC token anywhere in its id names a number
`--moved` names: `AC` not preceded by a letter or digit, then optional blanks
around at most one `-`, `_`, `:`, `#`, `.` or dash (U+2010 to U+2015), then the
number, not followed by another digit, in any case and with leading zeros
(`AC-7`, `AC7`, `AC 7`, `AC: 7`, `AC#7`, `AC.7`, `AC-7.1`, `AC-7: login` are AC
7's; `AC-7/AC-8` names both; `AC-70` and `AC-17` name neither). A token that a
story-key-like prefix (`<digits>-<digits>...-`) directly precedes counts only
when that prefix is `--story`, or the run of digit groups `--story` opens with:
`11-5-AC-7` is a sibling story's AC 7, never this one's. `--moved` takes
`AC-<n>` stripped, in any case and with leading zeros, and each AC once;
`--commit` takes the full sha `git rev-parse` prints, 40 or 64 hex digits, and
never a prefix, which could match another commit's matrix. Prints one JSON object, a usage error or a failure the
check did not foresee included: `moved` (the ids asked about, as `AC-<n>`),
`rows` (each matrix row that is a moved AC: its `id`, `priority` and
`coverage`), `matrix` (the matrix path, or null), `oracle_sources` (the matrix's
`oracle.sources`, where trace says it read its criteria, or an empty list),
`assessed_commit` and `reasons`.

Exit 0: no row is a moved AC. Exit 1: a row is. Exit 2: the trace files could
not be read, are not this trace's or measured another commit, an argument
error, or any other failure of the check.

    uv run moved_ac_check.py --trace-output DIR --story 11-6 --commit SHA \\
        --moved AC-7 [--moved AC-9 ...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# A failed import is reported by main() as a refusal with its JSON, never as an
# exit 1, the code that means a row was found.
try:
    import operator_owed  # noqa: E402  (sibling script, path set above)
except Exception as _exc:  # noqa: BLE001
    operator_owed = None
    _IMPORT_ERROR: Exception | None = _exc
else:
    _IMPORT_ERROR = None

# A moved id as `--moved` takes it; an AC token anywhere in a matrix row id,
# with a story-key-like prefix right before it when there is one; and a full
# commit id as git prints one (never a ref name such as `HEAD`, never a prefix).
_MOVED = re.compile(r"^AC-0*(\d+)$", re.IGNORECASE)
_AC_TOKEN = re.compile(
    r"(?:(?<![A-Za-z0-9])(?P<key>\d+(?:-\d+)+)-)?(?<![A-Za-z0-9])AC\s*[-_:#.\u2010-\u2015]?\s*0*(?P<n>\d+)(?![0-9])",
    re.IGNORECASE,
)
_STORY_DIGITS = re.compile(r"^\d+(?:-\d+)*")
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

NO_ROW, ROW, UNREADABLE = 0, 1, 2


def _empty(moved: list[str], reasons: list[str]) -> dict:
    return {
        "moved": moved,
        "rows": [],
        "matrix": None,
        "oracle_sources": [],
        "assessed_commit": None,
        "reasons": reasons,
    }


def _moved_id(value: str) -> str:
    match = _MOVED.match(value.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"{value!r} is not an AC id of the form AC-<n>")
    return f"AC-{int(match.group(1))}"


def _commit_id(value: str) -> str:
    sha = value.strip().lower()
    if not _COMMIT.match(sha):
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a full commit id of 40 or 64 hex digits; pass the sha git rev-parse prints"
        )
    return sha


def _named_numbers(rid: str, story: str) -> set[int]:
    """The AC numbers a row id names for this story: a token a story-key-like
    prefix precedes counts only when that prefix is the story's own."""
    own = {story.strip().lower()}
    digits = _STORY_DIGITS.match(story.strip())
    if digits:
        own.add(digits.group(0))
    return {
        int(token.group("n"))
        for token in _AC_TOKEN.finditer(rid)
        if token.group("key") is None or token.group("key").lower() in own
    }


class _Parser(argparse.ArgumentParser):
    """An argument error still prints the one JSON object, with the error as its reason."""

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(json.dumps(_empty([], [f"usage error: {message}"]), indent=2))
        raise SystemExit(UNREADABLE)


def _moved_of(args: argparse.Namespace) -> list[int]:
    return sorted({int(rid[len("AC-") :]) for rid in args.moved})


def evaluate(args: argparse.Namespace, out: dict | None = None) -> tuple[int, dict]:
    """The exit code and the JSON object, filled into `out` as the read goes, so
    a failure part way leaves what was already read in it."""
    numbers = _moved_of(args)
    if out is None:
        out = _empty([f"AC-{n}" for n in numbers], [])
    reasons = out["reasons"]
    moved = out["moved"]
    trace = operator_owed.read_matrix(Path(args.trace_output), args.story, reasons)
    if trace is None:
        reasons.append("trace's coverage matrix could not be read, so no moved AC is shown to be out of it")
        return UNREADABLE, out
    measured = [trace.commit]
    matrix_commit = trace.matrix.get("source_sha")
    if isinstance(matrix_commit, str) and matrix_commit.strip():
        measured.append(matrix_commit)
    stale = [sha.strip() for sha in measured if not operator_owed._same_commit(sha, args.commit)]
    if stale:
        reasons.append(
            f"the trace files measured {', '.join(sorted(set(stale)))}, not the commit under assessment "
            f"{args.commit}: they are not this gate's trace"
        )
        return UNREADABLE, out
    ids = [requirement.get("id") for requirement in trace.requirements]
    if not all(isinstance(rid, str) for rid in ids):
        reasons.append("a requirement id in the coverage matrix is not a string, so it cannot be read as an AC's")
        return UNREADABLE, out
    out["matrix"] = str(trace.path)
    out["assessed_commit"] = trace.commit.strip()
    oracle = trace.matrix.get("oracle")
    sources = oracle.get("sources") if isinstance(oracle, dict) else None
    out["oracle_sources"] = sources if isinstance(sources, list) else []
    for requirement, rid in zip(trace.requirements, ids):
        if _named_numbers(rid, args.story) & set(numbers):
            out["rows"].append(
                {"id": rid.strip(), "priority": requirement.get("priority"), "coverage": requirement.get("coverage")}
            )
    if out["rows"]:
        for row in out["rows"]:
            reasons.append(
                f"{row['id']} is a row of {trace.path} ({row['priority']}, {row['coverage']}): trace still "
                "scores an AC the operator moved out of the story"
            )
        return ROW, out
    reasons.append(f"no row of {trace.path} is {', '.join(moved)}")
    return NO_ROW, out


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Say whether TEA's trace still scores an AC the operator moved out of the story.")
    parser.add_argument("--trace-output", required=True, help="The trace directory the gate's trace wrote to.")
    parser.add_argument("--story", required=True, help="The story id, as the gate takes it.")
    parser.add_argument(
        "--commit", required=True, type=_commit_id, help="The full sha of the commit under assessment, as git prints it."
    )
    parser.add_argument(
        "--moved",
        required=True,
        action="append",
        type=_moved_id,
        help="An AC the move retired, as AC-<n>; repeat it for each.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = _empty([f"AC-{n}" for n in _moved_of(args)], [])
    code = UNREADABLE
    try:
        if _IMPORT_ERROR is not None:
            raise _IMPORT_ERROR
        code, _ = evaluate(args, out)
    except Exception as exc:  # noqa: BLE001  (any failure refuses; exit 1 would read as a row)
        out["rows"] = []
        out["reasons"].append(f"the check could not finish, so no moved AC is shown to be out of the matrix: {exc!r}")
        code = UNREADABLE
    try:
        print(json.dumps(out, indent=2))
    except Exception as exc:  # noqa: BLE001  (a closed pipe or an unprintable object still refuses)
        try:
            print(f"moved_ac_check.py could not print its result: {exc!r}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
        return UNREADABLE
    return code


if __name__ == "__main__":
    sys.exit(main())
