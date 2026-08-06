#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Sizing arithmetic and parent-AC claim reconciliation for a story decomposition.

`references/execute.md` ("Sizing: a story too large to drive") asks for two
computations and, until this module, shipped neither:

  - the sizing ratio, which decides whether a row is implausible to drive; and
  - the claim map check, "every parent AC claimed exactly once", which the prose
    explicitly requires to be done **mechanically** rather than by eye.

Leaving the second in the prompt meant every decomposition improvised a parser.
One of those improvisations reported two false double-claims by matching the `1`
inside `REQ-1` -- a substring match where an identity match was needed. That is
the failure this module retires, and it retires it by construction: ids are
tokenized into whole tokens and compared for EQUALITY, never with `in`. `REQ-1`
and `1` are two different ids here, and no amount of shared characters makes
them the same one.

What stays in the prompt is the judgment the prose reserves: "implausible" is an
override in both directions, and which child owns which AC is an authoring
decision. This module computes the counts, the ratio and the exactly-once
reconciliation. It never decides the split.

Exit codes: 0 the claim map reconciles, 1 it does not (unclaimed, double-claimed
or unknown ids), 2 usage error. The JSON is written on 0 and 1 alike, because a
failing reconciliation is a result to read, not a crash.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# An id is a whole token: a `<word>-<number>` form (`AC-1`, `REQ-1`, `FR-2.1`) or
# a bare number (`1`). Anchored at both ends, so a token either IS an id or is
# rejected -- there is no partial match, which is what makes the `REQ-1` vs `1`
# confusion unrepresentable rather than merely unlikely.
_ID = re.compile(r"^(?:[A-Za-z][A-Za-z0-9_]*-\d+(?:\.\d+)*|\d+)$")

_SPLIT = re.compile(r"[,\s]+")


def parse_ids(raw: str, *, field: str) -> list[str]:
    """Split a comma/whitespace separated id list into validated whole tokens.

    Rejects a token that is not a well-formed id rather than silently dropping
    it: a typo'd id that vanished would read downstream as an AC nobody claimed,
    turning a usage error into a false reconciliation failure.
    """
    tokens = [t for t in _SPLIT.split(raw.strip()) if t]
    bad = [t for t in tokens if not _ID.match(t)]
    if bad:
        raise ValueError("%s: not well-formed ids: %s" % (field, ", ".join(bad)))
    return tokens


def _dedupe(ids: list[str]) -> tuple[list[str], list[str]]:
    """Preserve order, and report ids repeated WITHIN one list separately."""
    seen: dict[str, int] = {}
    for i in ids:
        seen[i] = seen.get(i, 0) + 1
    return list(seen), sorted(i for i, n in seen.items() if n > 1)


def reconcile(parent_acs: list[str], children: dict[str, list[str]]) -> dict:
    """Map each parent AC to the children claiming it, by token equality."""
    parent_unique, parent_dupes = _dedupe(parent_acs)
    parent_set = set(parent_unique)

    claims: dict[str, list[str]] = {ac: [] for ac in parent_unique}
    unknown: dict[str, list[str]] = {}
    for child, claimed in children.items():
        for ac in claimed:
            if ac in parent_set:
                if child not in claims[ac]:
                    claims[ac].append(child)
            else:
                unknown.setdefault(child, []).append(ac)

    unclaimed = [ac for ac in parent_unique if not claims[ac]]
    double = [ac for ac in parent_unique if len(claims[ac]) > 1]
    return {
        "claims": claims,
        "unclaimed": unclaimed,
        "double_claimed": double,
        "unknown_claims": unknown,
        "parent_ac_duplicates": parent_dupes,
        "exactly_once": not (unclaimed or double or unknown or parent_dupes),
    }


def size(ac_count: int, task_count: int, turn_ceiling: int | None) -> dict:
    """The first-pass implausibility test execute.md states.

    load = AC count + task count; implausible once load reaches roughly half the
    per-story turn ceiling. With no ceiling supplied the ratio is undecidable, so
    `implausible` is None -- never False, which would read as "checked, fine".
    """
    load = ac_count + task_count
    if not turn_ceiling:
        return {
            "ac_count": ac_count,
            "task_count": task_count,
            "turn_ceiling": None,
            "load": load,
            "ratio": None,
            "implausible": None,
        }
    return {
        "ac_count": ac_count,
        "task_count": task_count,
        "turn_ceiling": turn_ceiling,
        "load": load,
        "ratio": round(load / turn_ceiling, 4),
        "implausible": load >= turn_ceiling / 2,
    }


def _parse_child(spec: str) -> tuple[str, list[str]]:
    if "=" not in spec:
        raise ValueError("--child expects <row-id>=<ac,ac,...>, got: %s" % spec)
    row, _, claimed = spec.partition("=")
    row = row.strip()
    if not row:
        raise ValueError("--child is missing the row id: %s" % spec)
    return row, parse_ids(claimed, field="--child %s" % row)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Size a story row and reconcile a decomposition's parent-AC claim "
            "map. Every parent AC must be claimed exactly once."
        ),
        epilog=(
            "example: story_sizing.py --parent-acs 'AC-1,AC-2,REQ-1' "
            "--child '7-1a=AC-1,AC-2' --child '7-1b=REQ-1' --tasks 4 "
            "--turn-ceiling 25"
        ),
    )
    parser.add_argument(
        "--parent-acs",
        default="",
        help="the parent row's acceptance criteria ids, comma or space separated",
    )
    parser.add_argument(
        "--child",
        action="append",
        default=[],
        metavar="ROW=ACS",
        help="one child row and the parent ACs it claims; repeatable",
    )
    parser.add_argument("--tasks", type=int, default=0, help="task count on the row")
    parser.add_argument(
        "--turn-ceiling",
        type=int,
        default=None,
        help="{workflow.max_turns_per_story}; omit to skip the implausibility test",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        parent_acs = parse_ids(args.parent_acs, field="--parent-acs")
        children = dict(_parse_child(spec) for spec in args.child)
    except ValueError as exc:
        print("usage error: %s" % exc, file=sys.stderr)
        return 2

    result = size(len(set(parent_acs)), args.tasks, args.turn_ceiling)
    # Reconciliation only means something once a split exists. Sizing alone is
    # the pre-decomposition call, and it must not report a clean claim map it
    # never checked.
    result["reconciled"] = bool(children)
    result.update(reconcile(parent_acs, children) if children else {})

    print(json.dumps(result, indent=2, sort_keys=True))
    if children and not result["exactly_once"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
