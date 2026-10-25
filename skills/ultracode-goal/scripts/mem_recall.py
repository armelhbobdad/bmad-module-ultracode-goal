#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Cross-Session Recall read path for ultracode-goal: latch, filter, unlatch.

Advisory-only, voice-never-vote, fail-closed, OFF by default. Nothing here ever
touches the gate/completion path. This script writes the machine latch the
PreToolUse guard reads, turns this repo's prior run records in the local run
store (cross_session_recall_store) into a small, deterministic, defanged
advisory set the skill MAY surface, and removes the latch when the run ends.
It makes no MCP call and reads no stdin.

Subcommands
-----------
latch --store <value>
    Latch v2, written at Stage 1. Checks the cross_session_recall knob, that
    the store value is set, the repo fingerprint, and that
    ``<store>/<fingerprint-dir>/runs`` can be created and written (mkstemp,
    then unlink; a store root the probe creates gets its ``.gitignore`` holding
    ``*``). Writes ``{latch_version: 2, run_id, backend, store_ok, recall,
    store, fingerprint, created_at}`` to ``<impl-artifacts>/.mem-state.json``
    atomically, replacing a latch another run left there. ``--recall on`` with
    an unset store is red and prints ``NOTE recall-store-unset`` naming the
    key. A run_id that fails the shared check exits 2 before anything is
    written. Prints ``{"latch": <the state written>, "notes": [...],
    "reason": str|null}``.

filter --store <value> [--epic <id>]
    Reads this repo's ``runs/*.jsonl`` through the store module, which
    validates each record on its own (unparseable or wrong shape: invalid;
    newer schema_version: cross_schema; another fingerprint: foreign). Only the
    survivors feed recurrence and horizon immunity, stale records still
    counting. The fingerprint alone decides foreign, so worktrees and clones of
    one repo read each other's records. An explicit adapter types each record
    (id is the run_id, a title line built from epic, gate_status and verdict).
    Ranking: this Epic first, then recurring, then created_at_epoch clamped to
    now (descending), then run_id (ascending). It works whatever the latch
    says: gating is the guard's job.

unlatch --run-id <run_id>
    Removes the latch only when its run_id is this one. Another run's latch,
    an unreadable one and an absent one are left as they are. Prints one JSON
    line ``{"removed": bool, "reason": str}`` and exits 0; bad arguments, a
    malformed run_id included, exit 2 and remove nothing. Every terminal of a
    run (Finalize, a preflight STOP, the headless envelope path) calls it, and
    it is the only way the prose removes a latch.

The claude-mem forms are gone: ``selftest``, the latch flags ``--probe``,
``--claude-mem-absent`` and ``--tool-form``, a latch or filter without
``--store``, and filter's ``--probe`` and ``--project``. Each exits 2 with one
line on stderr naming its replacement.

Recurrence: a signature recurs when it spans at least two distinct run_ids
and its class is not "other". Horizon immunity counts the same distinct
run_ids but not the class: a record carrying a signature that two or more
runs recorded, of class "other" too, is immune to the horizon.

Determinism: a total-order sort; future epochs are clamped to --now-epoch for
ranking only (never dropped); byte/codepoint caps are boundary-safe; identical
input yields byte-identical output.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from typing import NoReturn

from lib import mem_common as mc

_PROG = "mem_recall.py"


def _force_utf8_stdio() -> None:
    """Pin stdin/stdout/stderr to UTF-8.

    Windows consoles default to a legacy codepage (cp1252), which cannot
    encode the multibyte content this script legitimately emits (titles pass
    through with ensure_ascii=False), so json output would crash with
    UnicodeEncodeError. The output contract is UTF-8 everywhere.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _invalid_run_id(run_id: str) -> str:
    return f"invalid run_id {run_id!r}: expected epic-<id>-<YYYYMMDD>T<HHMMSS>Z"


# ---------------------------------------------------------------------------
# Recurrence
# ---------------------------------------------------------------------------


def _recurrence_from_payloads(payloads: Iterable[dict]) -> tuple[dict, dict[str, int]]:
    """The recurrence rule over run records (each carrying ``run_id`` and
    ``signatures``): the store records that survived the invalid, foreign and
    cross-schema drops.

    A signature recurs iff it spans >=2 DISTINCT run_ids AND its class !=
    "other". Returns (recurrence_by_sig, run_id_counts): recurrence_by_sig
    maps sig -> {"sig","class","count","run_ids":[sorted]} for the signatures
    that qualify, and run_id_counts maps every sig to its distinct run_id
    count, for the horizon-immunity check.
    """
    # sig -> {"class": str, "run_ids": set[str]}
    accum: dict[str, dict] = {}
    for payload in payloads:
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            continue
        signatures = payload.get("signatures")
        if not isinstance(signatures, list):
            continue
        for sig_entry in signatures:
            if not isinstance(sig_entry, dict):
                continue
            sig = sig_entry.get("sig")
            cls = mc.canonical_class(sig_entry.get("class"))
            if not isinstance(sig, str) or not sig:
                continue
            bucket = accum.setdefault(sig, {"class": cls, "run_ids": set()})
            bucket["run_ids"].add(run_id)
            # Keep the first non-"other" class we saw; class is per-signature.
            if bucket["class"] == "other" and cls != "other":
                bucket["class"] = cls

    recurrence: dict[str, dict] = {}
    run_id_counts: dict[str, int] = {}
    for sig, bucket in accum.items():
        run_ids = bucket["run_ids"]
        run_id_counts[sig] = len(run_ids)
        if len(run_ids) >= 2 and bucket["class"] != "other":
            recurrence[sig] = {
                "sig": sig,
                "class": bucket["class"],
                "count": len(run_ids),
                "run_ids": sorted(run_ids),
            }
    return recurrence, run_id_counts


def _byte_clamp(text: str, max_bytes: int) -> str:
    """Clamp a string so its UTF-8 encoding is <= max_bytes, on a codepoint
    boundary (never splitting a multibyte char)."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes]
    # Back off to the last complete codepoint.
    return truncated.decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# filter --store: the local run store
# ---------------------------------------------------------------------------


def _store_signatures(record: dict) -> list[str]:
    """The non-empty signatures of a validated store record."""
    return [entry["sig"] for entry in record["signatures"] if entry["sig"]]


def _store_text(text: str, per_record_bytes: int) -> str:
    """Defang one free-text field of a store record before it reaches the model.

    Redacted and neutralized like any untrusted text (a run file is a plain
    file anyone can edit), then clamped to ``per_record_bytes`` on a codepoint
    boundary.
    """
    return _byte_clamp(mc.neutralize(mc.redact(text)), per_record_bytes)


def _store_title_phrase(record: dict, per_record_bytes: int) -> str:
    """The adapter's title line, the field the per-record byte cap clamps.

    Built from the record's epic, gate_status and verdict, then defanged by
    _store_text.
    """
    line = (
        f"UCG run epic {record['epic']}: gate {record['gate_status']}, "
        f"verdict {record['verdict']}"
    )
    return _store_text(line, per_record_bytes)


def _type_store_record(record: dict, recurrence: dict, per_record_bytes: int) -> dict:
    """The explicit adapter from a store record to the filter's typed shape.

    id is the run_id (already checked by the store module's validator), kind
    the record's kind, epoch its created_at_epoch, and project is display only
    (never compared). Every free-text field is defanged by _store_text.
    """
    return {
        "id": record["run_id"],
        "kind": _store_text(record["kind"], per_record_bytes),
        "epoch": record["created_at_epoch"],
        "project": _store_text(record["project"], per_record_bytes),
        "title_noun_phrase": _store_title_phrase(record, per_record_bytes),
        "recurring": any(sig in recurrence for sig in _store_signatures(record)),
    }


def _store_recurrence_entry(entry: dict, per_record_bytes: int) -> dict:
    """A recurrence entry for the output, its free-text ``sig`` defanged.

    ``class`` is already one of the TAXONOMY classes, ``count`` an int and
    ``run_ids`` checked run_ids. Matching used the raw sig; only the printed
    copy changes, and a signature ``write`` computed (12 hex characters) is
    left as it is.
    """
    return {**entry, "sig": _store_text(entry["sig"], per_record_bytes)}


def run_store_filter(args: argparse.Namespace) -> dict:
    """filter --store: read this repo's records from the store and filter them.

    The store module reads ``<store>/<fingerprint-dir>/runs/*.jsonl`` and
    validates each record on its own, so one bad file never stops the read.
    Recurrence and horizon immunity count only the survivors of the invalid,
    foreign and cross-schema drops (stale records still count). The
    fingerprint alone decides foreign. An unset store, or a cwd with no
    fingerprint, reads nothing and returns the empty result.
    """
    horizon_ms = args.horizon_days * 24 * 60 * 60 * 1000
    now_epoch = args.now_epoch
    fingerprint = mc.repo_fingerprint(args.cwd or ".").get("value")
    store = mc.resolve_store_root(args.store, project_root=args.project_root)
    records, read_dropped = mc.read_store([store], fingerprint)
    # run_id order, so nothing below depends on the order the files were read.
    records.sort(key=lambda record: record["run_id"])

    recurrence, run_id_counts = _recurrence_from_payloads(records)
    immune_sigs = {sig for sig, count in run_id_counts.items() if count >= 2}

    dropped = {
        "foreign": read_dropped[mc.RECORD_FOREIGN],
        "stale": 0,
        "cross_schema": read_dropped[mc.RECORD_CROSS_SCHEMA],
        "invalid": read_dropped[mc.RECORD_INVALID],
    }
    ranked: list[tuple[tuple, dict]] = []
    for record in records:
        age = now_epoch - record["created_at_epoch"]
        if age > horizon_ms and not any(
            sig in immune_sigs for sig in _store_signatures(record)
        ):
            dropped["stale"] += 1
            continue
        typed = _type_store_record(record, recurrence, args.per_record_bytes)
        # Total order: this Epic first, then recurring, then created_at_epoch
        # clamped to now (descending), then run_id (ascending). Future epochs
        # clamp for ranking only and are never dropped.
        key = (
            0 if args.epic is not None and record["epic"] == args.epic else 1,
            0 if typed["recurring"] else 1,
            -min(typed["epoch"], now_epoch),
            typed["id"],
        )
        ranked.append((key, typed))

    ranked.sort(key=lambda item: item[0])
    out = [typed for _key, typed in ranked][: args.max_records]
    # Whole-payload byte cap, lowest-ranked records trimmed first.
    while out and len(json.dumps(out, ensure_ascii=False).encode("utf-8")) > args.max_bytes:
        out.pop()

    return {
        "records": out,
        "recurrence": [
            _store_recurrence_entry(recurrence[sig], args.per_record_bytes)
            for sig in sorted(recurrence)
        ],
        "dropped": dropped,
        "empty": len(out) == 0,
    }


# ---------------------------------------------------------------------------
# latch, filter, unlatch
# ---------------------------------------------------------------------------


def cmd_latch(args: argparse.Namespace) -> int:
    """latch --store: measure and write latch v2. No probe, no stdin, no MCP call.

    A run_id that fails the shared check exits 2 before anything is written
    (no git call, no latch, no store root), as ``mem_observation.py write``
    does. Every other outcome writes the latch and exits 0; its colour is in
    the printed state, and ``reason`` says why it is red. The latch is kept
    out of git as well (mc.exclude_state), whatever its colour, and a latch git
    can still see adds ``NOTE recall-latch-visible`` to ``notes``.
    """
    if not mc.valid_run_id(args.run_id):
        print(json.dumps({"error": _invalid_run_id(args.run_id)}))
        return 2
    measure = mc.measure_latch_v2(
        run_id=args.run_id,
        recall=args.recall,
        store_value=args.store,
        cwd=args.cwd,
        project_root=args.project_root,
    )
    mc.write_state(args.impl_artifacts, measure.state)
    notes = measure.notes + mc.exclude_state(args.impl_artifacts)
    print(
        json.dumps(
            {"latch": measure.state, "notes": notes, "reason": measure.reason},
            sort_keys=True,
        )
    )
    return 0


def cmd_filter(args: argparse.Namespace) -> int:
    result = run_store_filter(args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_unlatch(args: argparse.Namespace) -> int:
    """unlatch: remove this run's latch, and no other.

    A run_id that fails the shared check exits 2 before the latch is read, so
    a malformed value can never match, or remove, anything. Every other outcome
    exits 0 with ``{"removed": bool, "reason": str}`` (mc.remove_own_state):
    ``removed`` for this run's latch; ``absent``, ``foreign`` (another run_id,
    or none) and ``unreadable`` leave the latch path as it is, and
    ``remove-failed: <error>`` says the removal itself failed.
    """
    if not mc.valid_run_id(args.run_id):
        print(json.dumps({"error": _invalid_run_id(args.run_id)}))
        return 2
    removed, reason = mc.remove_own_state(args.impl_artifacts, args.run_id)
    print(json.dumps({"removed": removed, "reason": reason}, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# The removed claude-mem forms
# ---------------------------------------------------------------------------

# Subcommands the claude-mem backend needed, with what replaces each.
_REMOVED_COMMANDS = {
    "selftest": "use latch --store VALUE, which checks that the store can be written",
}


def _refuse_removed(form: str, hint: str) -> NoReturn:
    """Exit 2 on a removed claude-mem form, with one stderr line naming its replacement."""
    sys.stderr.write(f"{_PROG}: error: {form} was removed with the claude-mem backend; {hint}\n")
    sys.exit(2)


class _RemovedFlag(argparse.Action):
    """A removed claude-mem flag: hidden from the help, refused when given.

    It is still declared so that an exact match reaches it: undeclared,
    ``--project`` would pass as an abbreviation of ``--project-root``.
    """

    def __init__(self, option_strings, dest, *, form: str, hint: str, nargs="?", **kwargs):
        super().__init__(
            option_strings, dest, nargs=nargs, default=argparse.SUPPRESS, help=argparse.SUPPRESS, **kwargs
        )
        self.form = form
        self.hint = hint

    def __call__(self, parser, namespace, values, option_string=None):
        _refuse_removed(self.form, self.hint)


def _add_removed_flag(parser: argparse.ArgumentParser, flag: str, form: str, hint: str, *, nargs="?") -> None:
    parser.add_argument(flag, action=_RemovedFlag, form=form, hint=hint, nargs=nargs)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


_STORE_HELP = (
    "cross_session_recall_store value (the local run store root): a ~ path, an "
    "absolute path or a {project-root} path. A bare --store, an empty or blank "
    "value, an unresolved {...} token, a literal $VAR or %%VAR%% and a relative "
    "path count as unset. Required."
)
_PROJECT_ROOT_HELP = "Substituted for {project-root} in the --store value."


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="Cross-Session Recall latch, filter and unlatch for ultracode-goal.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_latch = sub.add_parser("latch", help="Check the store and write the state latch (latch v2).")
    p_latch.add_argument("--impl-artifacts", required=True, dest="impl_artifacts")
    p_latch.add_argument("--run-id", required=True, dest="run_id")
    p_latch.add_argument("--recall", required=True, choices=["on", "off"])
    p_latch.add_argument(
        "--store", nargs="?", const="", default=None,
        help=_STORE_HELP + " The latch runs the store's write probe.",
    )
    p_latch.add_argument("--project-root", default=None, dest="project_root", help=_PROJECT_ROOT_HELP)
    p_latch.add_argument("--cwd", default=None)
    _add_removed_flag(p_latch, "--probe", "latch --probe", "use latch --store VALUE, which takes no probe")
    _add_removed_flag(
        p_latch, "--claude-mem-absent", "latch --claude-mem-absent", "use latch --store VALUE", nargs=0,
    )
    _add_removed_flag(
        p_latch, "--tool-form", "latch --tool-form", "drop it: latch --store VALUE takes no tool form",
    )
    p_latch.set_defaults(func=cmd_latch)

    p_filter = sub.add_parser("filter", help="Read, filter and type this repo's records from the store.")
    p_filter.add_argument("--impl-artifacts", required=True, dest="impl_artifacts")
    p_filter.add_argument(
        "--store", nargs="?", const="", default=None,
        help=_STORE_HELP + " This repo's records are read from it.",
    )
    p_filter.add_argument("--epic", default=None, help="The current Epic, whose records rank first.")
    p_filter.add_argument("--project-root", default=None, dest="project_root", help=_PROJECT_ROOT_HELP)
    p_filter.add_argument("--max-records", type=int, default=5, dest="max_records")
    p_filter.add_argument("--per-record-bytes", type=int, default=2048, dest="per_record_bytes")
    p_filter.add_argument("--max-bytes", type=int, default=8192, dest="max_bytes")
    p_filter.add_argument("--horizon-days", type=int, default=120, dest="horizon_days")
    p_filter.add_argument("--now-epoch", type=int, default=None, dest="now_epoch")
    p_filter.add_argument("--cwd", default=None)
    _add_removed_flag(p_filter, "--probe", "filter --probe", "use filter --store VALUE, which reads the store")
    _add_removed_flag(
        p_filter, "--project", "filter --project",
        "drop it: filter --store VALUE tells this repo's records apart by fingerprint",
    )
    p_filter.set_defaults(func=cmd_filter)

    p_unlatch = sub.add_parser("unlatch", help="Remove the state latch when it is this run's.")
    p_unlatch.add_argument("--impl-artifacts", required=True, dest="impl_artifacts")
    p_unlatch.add_argument("--run-id", required=True, dest="run_id")
    p_unlatch.set_defaults(func=cmd_unlatch)
    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    arguments = sys.argv[1:] if argv is None else list(argv)
    if arguments and arguments[0] in _REMOVED_COMMANDS:
        _refuse_removed(arguments[0], _REMOVED_COMMANDS[arguments[0]])
    parser = _build_parser()
    args = parser.parse_args(arguments)
    if args.command in ("latch", "filter") and args.store is None:
        # The latch and filter without --store were the claude-mem ones.
        _refuse_removed(f"{args.command} without --store", f"use {args.command} --store VALUE")

    # Default now-epoch to the current wall clock (ms) when the caller did not
    # pin one. Pinning is what makes tests deterministic.
    if args.command == "filter" and args.now_epoch is None:
        import time

        args.now_epoch = int(time.time() * 1000)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
