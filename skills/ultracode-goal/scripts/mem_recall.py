#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Cross-Session Recall read path for ultracode-goal (D12) — latch + filter.

Advisory-only, voice-never-vote, fail-closed, OFF by default. Nothing here ever
touches the gate/completion path; this script only validates the claude-mem
capability contract, writes the machine latch the hook reads, and turns a raw
get_observations(ids) JSON array into a small, deterministic, defanged advisory
set the skill MAY surface.

Subcommands
-----------
latch
    Validate the capability contract against a probe (a get_observations JSON
    array) and write the state latch ONCE, atomically. Any uncertainty fails
    closed (claude_mem "absent" / schema_ok false). The latch is the ONLY writer
    of the state file; Stage 6 Finalize removes it.

filter
    Pure function over a probe array. Drops foreign / cross-schema / stale /
    invalid records, computes recurrence from records carrying our payload
    marker, types and defangs the survivors, and emits a byte-deterministic
    result. Works regardless of the latch state (gating is the hook's job).

selftest
    Report whether a probe satisfies the capability pin.

Capability pin (NOT a version pin): the read-fields we require are id:int,
project:str, title:str, created_at_epoch:int. UNKNOWN EXTRA FIELDS ARE
TOLERATED. An empty array is a valid present+schema_ok response.

Determinism: total-order sort (recurring desc, epoch-clamped-to-now desc, id
asc); future epochs are clamped to --now-epoch for ranking only (never dropped);
byte/codepoint caps are boundary-safe; identical input yields byte-identical
output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib import mem_common as mc


def _force_utf8_stdio() -> None:
    """Pin stdin/stdout/stderr to UTF-8.

    Windows consoles default to a legacy codepage (cp1252), which cannot
    encode the multibyte content this script legitimately emits (titles pass
    through with ensure_ascii=False) — json output would crash with
    UnicodeEncodeError. The probe/output contract is UTF-8 everywhere.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# Probe loading
# ---------------------------------------------------------------------------


def _load_probe_text(spec: str | None) -> str:
    """Read a probe spec: '-' or None means stdin; otherwise a file path."""
    if spec is None or spec == "-":
        return sys.stdin.read()
    return Path(spec).read_text(encoding="utf-8")


def _parse_probe(spec: str | None) -> tuple[list | None, str | None]:
    """Return (records, error). records is a list on success, else None+error."""
    try:
        text = _load_probe_text(spec)
    except OSError as exc:
        return None, f"could not read probe: {exc}"
    if not text.strip():
        # An explicitly empty probe is a valid empty array.
        return [], None
    try:
        data = json.loads(text)
    except ValueError as exc:
        return None, f"probe is not valid JSON: {exc}"
    if not isinstance(data, list):
        return None, "probe must be a JSON array of records"
    return data, None


# ---------------------------------------------------------------------------
# Capability pin
# ---------------------------------------------------------------------------

# The read-fields we depend on, with their required Python types. bool is
# excluded from int because in Python bool is a subclass of int and a True/False
# id is not a real record id.
_REQUIRED_READ_FIELDS = (
    ("id", int),
    ("project", str),
    ("title", str),
    ("created_at_epoch", int),
)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _record_satisfies_pin(record: object) -> bool:
    """True iff the record carries every required read-field with the right type."""
    if not isinstance(record, dict):
        return False
    for field, typ in _REQUIRED_READ_FIELDS:
        if field not in record:
            return False
        value = record[field]
        if typ is int:
            if not _is_int(value):
                return False
        elif not isinstance(value, typ):
            return False
    return True


def evaluate_contract(records: list) -> tuple[bool, list[str]]:
    """Check every record against the capability pin.

    Returns (contract_ok, problems). An empty list of records is contract_ok
    (claude-mem present, schema valid, simply no observations yet). Unknown
    extra fields never fail.
    """
    problems: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            problems.append(f"record[{index}] is not an object")
            continue
        for field, typ in _REQUIRED_READ_FIELDS:
            if field not in record:
                problems.append(f"record[{index}] missing required field {field!r}")
            else:
                value = record[field]
                ok = _is_int(value) if typ is int else isinstance(value, typ)
                if not ok:
                    problems.append(
                        f"record[{index}] field {field!r} has wrong type "
                        f"(expected {typ.__name__})"
                    )
    return (not problems), problems


# ---------------------------------------------------------------------------
# Embedded UCG payload parsing
# ---------------------------------------------------------------------------


def _carries_marker(record: dict) -> bool:
    """True if the record IS one of OUR run-summary payloads.

    Requires the marker in the text field — a title that merely starts with
    "UCG run" is not proof of ownership (a third-party record could carry that
    title), and treating it as ours would send payload extraction hunting for
    arbitrary JSON in foreign prose.
    """
    text = record.get("text")
    return isinstance(text, str) and mc.UCG_MARKER in text


def _extract_payload(record: dict) -> dict | None:
    """Pull our embedded JSON payload out of a record's text. Defensive.

    The text field is one human line, then the marker, then a fenced json block.
    We locate the first ``{`` after the marker and JSON-decode from there using a
    raw decoder so trailing fence characters do not break parsing. Never raises;
    returns None when nothing parseable is present.
    """
    text = record.get("text")
    if not isinstance(text, str):
        return None
    marker_at = text.find(mc.UCG_MARKER)
    if marker_at == -1:
        return None  # no marker -> not our payload; never scan from position 0
    brace_at = text.find("{", marker_at + len(mc.UCG_MARKER))
    if brace_at == -1:
        return None
    decoder = json.JSONDecoder()
    try:
        obj, _end = decoder.raw_decode(text[brace_at:])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _payload_schema_version(payload: dict) -> object:
    """Read the embedded schema_version (may be absent/garbage)."""
    return payload.get("schema_version")


# ---------------------------------------------------------------------------
# Recurrence — only from OUR payloads
# ---------------------------------------------------------------------------


def compute_recurrence(records: list) -> tuple[dict, dict[str, int]]:
    """Group signatures from UCG payloads; a signature recurs iff it spans >=2
    DISTINCT run_ids AND its class != "other".

    Returns (recurrence_by_sig, recurring_run_id_counts) where recurrence_by_sig
    maps sig -> {"sig","class","count","run_ids":[sorted]} for signatures that
    QUALIFY as recurring, and recurring_run_id_counts is the same sig -> distinct
    run_id count for the horizon-immunity check.
    """
    # sig -> {"class": str, "run_ids": set[str]}
    accum: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict) or not _carries_marker(record):
            continue
        payload = _extract_payload(record)
        if payload is None:
            continue
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


def _record_signatures(record: dict) -> list[str]:
    """Signatures declared by a record's embedded payload (empty if none)."""
    if not _carries_marker(record):
        return []
    payload = _extract_payload(record)
    if payload is None:
        return []
    signatures = payload.get("signatures")
    if not isinstance(signatures, list):
        return []
    out: list[str] = []
    for sig_entry in signatures:
        if isinstance(sig_entry, dict):
            sig = sig_entry.get("sig")
            if isinstance(sig, str) and sig:
                out.append(sig)
    return out


# ---------------------------------------------------------------------------
# Filtering + typing
# ---------------------------------------------------------------------------


def _byte_clamp(text: str, max_bytes: int) -> str:
    """Clamp a string so its UTF-8 encoding is <= max_bytes, on a codepoint
    boundary (never splitting a multibyte char)."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes]
    # Back off to the last complete codepoint.
    return truncated.decode("utf-8", errors="ignore")


def run_filter(records: list, args: argparse.Namespace) -> dict:
    """Apply the full filter pipeline and return the emit structure."""
    project = args.project
    horizon_ms = args.horizon_days * 24 * 60 * 60 * 1000
    now_epoch = args.now_epoch
    fingerprint = mc.repo_fingerprint(args.cwd or ".").get("value")

    # Recurrence (and per-sig distinct run_id counts) is computed across ALL
    # records up front so horizon immunity can reference it.
    recurrence, run_id_counts = compute_recurrence(records)
    immune_sigs = {sig for sig, count in run_id_counts.items() if count >= 2}

    dropped = {"foreign": 0, "stale": 0, "cross_schema": 0, "invalid": 0}
    survivors: list[dict] = []

    for record in records:
        # 1. invalid — missing required read fields / not an object.
        if not _record_satisfies_pin(record):
            dropped["invalid"] += 1
            continue

        is_ours = _carries_marker(record)

        # 2. foreign — project mismatch (when --project given); our own payloads
        #    additionally must match this repo's fingerprint.
        if project is not None and record["project"] != project:
            dropped["foreign"] += 1
            continue
        if is_ours:
            payload = _extract_payload(record)
            if payload is not None:
                payload_fp = payload.get("fingerprint")
                if (
                    fingerprint is not None
                    and isinstance(payload_fp, str)
                    and payload_fp != fingerprint
                ):
                    dropped["foreign"] += 1
                    continue

        # 3. cross_schema — OUR payloads whose embedded schema_version != 1.
        if is_ours:
            payload = _extract_payload(record)
            if payload is not None:
                version = _payload_schema_version(payload)
                if version != mc.UCG_SCHEMA_VERSION:
                    dropped["cross_schema"] += 1
                    continue

        # 4. stale — older than the horizon, UNLESS the record carries a
        #    signature that recurs across >=2 distinct run_ids (per-signal
        #    horizon immunity).
        epoch = record["created_at_epoch"]
        age = now_epoch - epoch
        if age > horizon_ms:
            record_sigs = _record_signatures(record)
            if not any(sig in immune_sigs for sig in record_sigs):
                dropped["stale"] += 1
                continue

        survivors.append(record)

    typed = [
        _type_record(record, now_epoch, recurrence, args.per_record_bytes)
        for record in survivors
    ]

    # Total-order deterministic sort. Future epochs clamp to now for ranking.
    def _sort_key(t: dict) -> tuple:
        clamped = min(t["epoch"], now_epoch)
        return (0 if t["recurring"] else 1, -clamped, t["id"])

    typed.sort(key=_sort_key)
    typed = typed[: args.max_records]

    # Whole-payload byte cap (codepoint-safe is moot at the JSON level; we cap
    # the record list deterministically by dropping lowest-ranked tails until the
    # serialized records fit). We keep it simple and stable: serialize and, if
    # over, trim from the end.
    while typed and len(json.dumps(typed, ensure_ascii=False).encode("utf-8")) > args.max_bytes:
        typed.pop()

    recurrence_list = [
        recurrence[sig] for sig in sorted(recurrence.keys())
    ]

    return {
        "records": typed,
        "recurrence": recurrence_list,
        "dropped": dropped,
        "empty": len(typed) == 0,
    }


def _type_record(
    record: dict, now_epoch: int, recurrence: dict, per_record_bytes: int
) -> dict:
    """Project a raw record into the small typed advisory shape (defanged)."""
    title = record.get("title")
    title_phrase = mc.neutralize(title if isinstance(title, str) else "")
    title_phrase = _byte_clamp(title_phrase, per_record_bytes)

    record_sigs = set(_record_signatures(record))
    recurring = any(sig in recurrence for sig in record_sigs)

    return {
        "id": record["id"],
        "kind": record.get("type") if isinstance(record.get("type"), str) else "",
        "epoch": record["created_at_epoch"],
        "project": record["project"],
        "title_noun_phrase": title_phrase,
        "recurring": recurring,
    }


# ---------------------------------------------------------------------------
# latch
# ---------------------------------------------------------------------------


def cmd_latch(args: argparse.Namespace) -> int:
    fingerprint = mc.repo_fingerprint(args.cwd or ".").get("value")

    if args.claude_mem_absent:
        claude_mem = "absent"
        schema_ok = False
    else:
        records, error = _parse_probe(args.probe)
        if error is not None or records is None:
            # Any uncertainty -> fail closed.
            claude_mem = "absent"
            schema_ok = False
        else:
            contract_ok, _problems = evaluate_contract(records)
            claude_mem = "present"
            schema_ok = bool(contract_ok)

    # recall is only meaningfully "on" when present + schema_ok + caller asked
    # for it AND we actually have a fingerprint to pin to.
    requested_on = args.recall == "on"
    recall = (
        "on"
        if (claude_mem == "present" and schema_ok and requested_on and fingerprint)
        else "off"
    )

    state = {
        "latch_version": mc.LATCH_VERSION,
        "run_id": args.run_id,
        "claude_mem": claude_mem,
        "schema_ok": schema_ok,
        "recall": recall,
        "tool_form": args.tool_form,
        "fingerprint": fingerprint,
        "created_at": mc.utc_now_iso(),
    }

    mc.write_state(args.impl_artifacts, state)
    print(json.dumps(state))
    return 0


# ---------------------------------------------------------------------------
# filter
# ---------------------------------------------------------------------------


def cmd_filter(args: argparse.Namespace) -> int:
    records, error = _parse_probe(args.probe)
    if error is not None or records is None:
        print(json.dumps({"error": error or "could not parse probe"}))
        return 1
    result = run_filter(records, args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------


def cmd_selftest(args: argparse.Namespace) -> int:
    records, error = _parse_probe(args.probe)
    if error is not None or records is None:
        print(json.dumps({"contract_ok": False, "problems": [error or "unparseable probe"]}))
        return 1
    contract_ok, problems = evaluate_contract(records)
    print(json.dumps({"contract_ok": contract_ok, "problems": problems}))
    return 0 if contract_ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Cross-Session Recall latch + filter for ultracode-goal."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_latch = sub.add_parser("latch", help="Validate the capability contract and write the state latch.")
    p_latch.add_argument("--impl-artifacts", required=True, dest="impl_artifacts")
    p_latch.add_argument("--run-id", required=True, dest="run_id")
    p_latch.add_argument("--recall", required=True, choices=["on", "off"])
    group = p_latch.add_mutually_exclusive_group(required=True)
    group.add_argument("--probe", help="get_observations JSON array (file path or '-').")
    group.add_argument("--claude-mem-absent", action="store_true", dest="claude_mem_absent")
    p_latch.add_argument("--tool-form", choices=["plugin", "bare"], default=None, dest="tool_form")
    p_latch.add_argument("--cwd", default=None)
    p_latch.set_defaults(func=cmd_latch, claude_mem_absent=False)

    p_filter = sub.add_parser("filter", help="Filter + type a probe array deterministically.")
    p_filter.add_argument("--impl-artifacts", required=True, dest="impl_artifacts")
    p_filter.add_argument("--probe", required=True, help="get_observations JSON array (file path or '-').")
    p_filter.add_argument("--project", default=None)
    p_filter.add_argument("--max-records", type=int, default=5, dest="max_records")
    p_filter.add_argument("--per-record-bytes", type=int, default=2048, dest="per_record_bytes")
    p_filter.add_argument("--max-bytes", type=int, default=8192, dest="max_bytes")
    p_filter.add_argument("--horizon-days", type=int, default=120, dest="horizon_days")
    p_filter.add_argument("--now-epoch", type=int, default=None, dest="now_epoch")
    p_filter.add_argument("--cwd", default=None)
    p_filter.set_defaults(func=cmd_filter)

    p_self = sub.add_parser("selftest", help="Report whether a probe satisfies the capability pin.")
    p_self.add_argument("--probe", default=None, help="get_observations JSON array (file path or '-').")
    p_self.set_defaults(func=cmd_selftest)

    args = parser.parse_args(argv)

    # Default now-epoch to the current wall clock (ms) when the caller did not
    # pin one. Pinning is what makes tests deterministic.
    if getattr(args, "command", None) == "filter" and args.now_epoch is None:
        import time

        args.now_epoch = int(time.time() * 1000)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
