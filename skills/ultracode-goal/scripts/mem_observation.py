#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Cross-Session Recall write path for ultracode-goal — build/spill/drain.

Advisory-only, voice-never-vote, fail-closed, OFF by default. This script builds
the save_observation payload the skill MAY persist after a run, and provides a
crash-proof outbox (spill) + replayer (drain) so a transient claude-mem outage
during a run never blocks the run — the payload is parked and replayed later.

Subcommands
-----------
build
    Assemble a save_observation-ready {text,title,project} from run facts. Every
    free-text fragment is redacted; root-cause classes are constrained to the
    12-class TAXONOMY (unknown -> "other"). The structured payload travels inside
    the human-readable ``text`` field after our marker, because save_observation
    only accepts {text,title,project}. A NOT_EVALUATED gate is SKIPPED (no
    payload); WAIVED outcomes ARE written.

spill
    Append ONE JSON line to <impl>/mem-outbox.<run_id>.jsonl. Per-run-id files
    mean no locking is ever needed. A run_id holding a path separator or ``..``
    exits 2 before anything is written.

drain
    Scan ALL mem-outbox.*.jsonl: expire entries past TTL (tombstones),
    dead-letter entries that have failed >=3 times, and report the rest as
    replayable while incrementing their attempt counters in place. Original
    spill stamps are preserved verbatim.

write
    Build the same payload as ``build`` (without the claude-mem wrapper), add
    ``created_at_epoch`` (integer UTC ms, stamped now) and ``project`` (the main
    worktree's directory name, display only), and create this run's file in the
    local store, ``<store>/<fingerprint-dir>/runs/<run_id>.jsonl``, through the
    immutable writer in lib/mem_common. A bad ``--run-id`` exits 2 before
    anything is touched. A replay prints ``skipped-existing`` and leaves the file
    byte-identical; a foreign or unparseable target is never touched and the
    entry is dead-lettered with ``NOTE mem-target-foreign``; an OSError spills
    the record to the outbox with ``WARN mem-write-deferred``.

drain --store
    The store mode of drain: replays each spilled record through the same
    write and removes it once it lands (or is ``skipped-existing``), counting
    ``attempts`` only on an OSError. A claude-mem era ``{text,title,project}``
    entry carrying the marker is converted into a store record BEFORE the TTL
    check, with ``attempts`` reset to 0, and if the store refuses it, it is
    requeued marked ``converted`` and never meets the TTL; one that cannot
    convert is dead-lettered with ``NOTE mem-legacy-unconvertible``. An entry
    whose ``run_id`` fails the check is dead-lettered with
    ``NOTE mem-run-id-invalid``, whatever its age, and the others still land.
    ``mem-outbox.dead.jsonl`` is never converted. Without ``--store``, drain
    keeps the contract above (and refuses ``--project-root`` and ``--cwd``).

``--store`` takes the cross_session_recall_store value: a ``~`` path, an
absolute path or a ``{project-root}`` path (substituted from
``--project-root``). An empty or blank value, a bare ``--store``, an
unresolved ``{...}`` token, a literal ``$VAR`` or ``%VAR%`` and a relative path
count as unset: ``NOTE recall-store-unset``, and nothing is written.

Every NOTE and WARN line write and the store drain produce goes to stdout, in
the ``notes`` list of the one JSON object they print.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import gate_trail  # sibling script; the ledger's table parser lives there
from lib import mem_common as mc

_DEAD_LETTER = "mem-outbox.dead.jsonl"
_MAX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def _parse_root_cause(spec: str) -> dict:
    """Parse a 'class=<taxonomy>,path=<artifact>' fragment into a signature.

    Unknown classes collapse to "other". Both halves are redacted (a secret can
    hide in a path). The signature is sha1(class|path|fingerprint)[:12], computed
    by the caller which holds the fingerprint.
    """
    fields = _parse_kv(spec)
    cls = mc.canonical_class(fields.get("class"))
    path = mc.redact(fields.get("path", ""))
    return {"class": cls, "path": path}


def _parse_kv(spec: str) -> dict[str, str]:
    """Parse 'k=v,k2=v2' into a dict. Values may contain '=' (split once)."""
    out: dict[str, str] = {}
    for chunk in spec.split(","):
        if not chunk:
            continue
        key, sep, value = chunk.partition("=")
        if not sep:
            continue
        out[key.strip()] = value.strip()
    return out


def _signature(cls: str, path: str, fingerprint: str | None) -> str:
    basis = f"{cls}|{path}|{fingerprint or ''}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _heading_names_epic(heading_text: str, epic_token: str) -> bool:
    """True iff the heading names THIS epic, matched as a whole token.

    A plain substring test made every epic a prefix of its own successors: epic
    `1` matched the heading "Epic 11", and `epic-1` matched "epic-10", so the
    count reported a neighbour's parked items as this run's. The digits and
    letters on either side are what distinguish them, so the boundary is
    alphanumeric rather than `\\b` - `\\b` would not fire between `-` and `1`,
    which is exactly where an `epic-1` token ends.
    """
    return bool(
        re.search(
            rf"(?<![0-9A-Za-z]){re.escape(epic_token)}(?![0-9A-Za-z])", heading_text
        )
    )


def _count_deferred(deferred_path: Path | None, epic: str) -> int:
    """Count this epic's parked items in a deferred-work ledger.

    The heading is any markdown heading line whose text contains the epic id; the
    section runs until the next heading of the same-or-shallower level. The
    ledger the run actually writes is a pipe TABLE (one row per parked item), so
    rows carrying a non-empty `id` cell are counted first, through the same
    parser `status_render.ledger_rows` reads the ledger with — a second format
    guess here is how the two readers drift apart. A hand-written section with no
    such table falls back to its '- ' bullets. Absent file or no matching
    heading -> 0.
    """
    if deferred_path is None or not deferred_path.is_file():
        return 0
    try:
        text = deferred_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0

    lines = text.splitlines()
    heading_re = re.compile(r"^(#{1,6})\s+(.*)$")
    in_section = False
    section_level = 0
    section: list[str] = []
    epic_token = str(epic).strip()

    for line in lines:
        m = heading_re.match(line)
        if m:
            level = len(m.group(1))
            heading_text = m.group(2)
            if in_section and level <= section_level:
                # A sibling or shallower heading ends our section.
                in_section = False
            if not in_section and epic_token and _heading_names_epic(heading_text, epic_token):
                in_section = True
                section_level = level
            if in_section:
                # Keep a blank in the heading's place so a nested heading can
                # never glue two adjacent tables into one.
                section.append("")
            continue
        if in_section:
            section.append(line)

    count = 0
    for headers, rows in gate_trail._tables("\n".join(section)):
        if "id" not in headers:
            continue
        id_at = headers.index("id")
        for row in rows:
            if id_at < len(row) and row[id_at].strip():
                count += 1
    if count:
        return count
    return sum(1 for line in section if line.lstrip().startswith("- "))


def _build_payload(args: argparse.Namespace, gate_status: str) -> dict:
    """The structured run payload: what build embeds and write stores.

    Shared by build (which wraps it in the claude-mem ``{text,title,project}``
    shape) and write (which adds ``created_at_epoch`` and ``project`` and stores
    it), so the two can never drift apart.
    """
    fingerprint = mc.repo_fingerprint(args.cwd or ".").get("value")

    signatures = []
    for raw in args.root_cause or []:
        parsed = _parse_root_cause(raw)
        sig = _signature(parsed["class"], parsed["path"], fingerprint)
        signatures.append({"class": parsed["class"], "path": parsed["path"], "sig": sig})

    advisories = []
    for raw in args.advisory or []:
        fields = _parse_kv(raw)
        sig = mc.redact(fields.get("sig", ""))
        recurred = fields.get("recurred", "unknown")
        if recurred not in ("yes", "no", "unknown"):
            recurred = "unknown"
        advisories.append({"sig": sig, "recurred": recurred})

    deferred_path = Path(args.deferred) if args.deferred else None
    deferred_count = _count_deferred(deferred_path, args.epic)

    valid_until = {
        "sha": args.valid_until_sha if args.valid_until_sha else None,
        "date": args.valid_until_date if args.valid_until_date else mc.utc_now_iso(),
    }

    verdict = mc.redact(args.verdict).strip() or "blocked"

    payload = {
        "ucg": 1,
        "schema_version": mc.UCG_SCHEMA_VERSION,
        "kind": "run-summary",
        "epic": str(args.epic),
        "run_id": args.run_id,
        "fingerprint": fingerprint,
        "gate_status": gate_status,
        "verdict": verdict,
        "valid_until": valid_until,
        "signatures": signatures,
        "deferred_count": deferred_count,
        "advisories": advisories,
    }
    return payload


def cmd_build(args: argparse.Namespace) -> int:
    gate_status = (args.gate_status or "").strip().upper()
    if gate_status == "NOT_EVALUATED":
        print(json.dumps({"skip": True, "reason": "gate NOT_EVALUATED; no payload written"}))
        return 0

    payload = _build_payload(args, gate_status)
    verdict = payload["verdict"]
    signatures = payload["signatures"]
    deferred_count = payload["deferred_count"]

    summary_line = mc.redact(
        f"UCG run for epic {args.epic}: gate {gate_status}, verdict {verdict}, "
        f"{len(signatures)} signature(s), {deferred_count} deferred."
    )
    fenced = "```json\n" + json.dumps(payload, sort_keys=True) + "\n```"
    text = f"{summary_line}\n{mc.UCG_MARKER}\n{fenced}"

    title = mc.redact(f"UCG run — epic {args.epic}: {verdict}")

    print(json.dumps({"text": text, "title": title, "project": args.project}))
    return 0


# ---------------------------------------------------------------------------
# spill
# ---------------------------------------------------------------------------


def _outbox_path(impl: Path, run_id: str) -> Path:
    return impl / f"mem-outbox.{run_id}.jsonl"


def _force_utf8_stdio() -> None:
    """Pin stdin/stdout/stderr to UTF-8.

    Windows consoles default to a legacy codepage (cp1252) that cannot encode
    the multibyte content build/spill legitimately carry (epic titles, root
    causes); the payload contract is UTF-8 on every stream.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _run_id_leaves_the_folder(run_id: str) -> bool:
    """True when ``mem-outbox.<run_id>.jsonl`` would name a path outside the
    artifacts folder: a ``/`` or ``\\`` separator, or ``..``.

    The full run_id check (mc.valid_run_id) guards write and drain --store.
    spill, which today's Finalize prose calls, refuses only these values, so a
    run_id of any other shape keeps working as before.
    """
    return "/" in run_id or "\\" in run_id or ".." in run_id


def cmd_spill(args: argparse.Namespace) -> int:
    if _run_id_leaves_the_folder(args.run_id):
        print(json.dumps({"error": f"run_id {args.run_id!r} would leave the outbox folder"}))
        return 2
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        print(json.dumps({"error": f"payload is not valid JSON: {exc}"}))
        return 1

    impl = Path(args.impl_artifacts)
    impl.mkdir(parents=True, exist_ok=True)
    path = _outbox_path(impl, args.run_id)

    entry = {
        "payload": payload,
        "attempts": 0,
        "spilled_at": mc.utc_now_iso(),
    }
    # Append one self-contained JSON line. Per-run-id file => no locking
    # needed; flush+fsync so a normal exit never leaves a buffered partial
    # line (a crash mid-write is absorbed by drain's tombstone handling).
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    print(json.dumps({"spilled": True, "file": str(path)}))
    return 0


# ---------------------------------------------------------------------------
# drain
# ---------------------------------------------------------------------------


def _parse_iso(stamp: object) -> datetime | None:
    if not isinstance(stamp, str) or not stamp:
        return None
    text = stamp.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _atomic_write_lines(path: Path, lines: list[str]) -> None:
    """Rewrite a jsonl file atomically (or remove it when empty)."""
    if not lines:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".mem-outbox-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")
        os.replace(tmp_name, str(path))
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _append_dead(impl: Path, entries: list[dict]) -> None:
    if not entries:
        return
    dead = impl / _DEAD_LETTER
    with dead.open("a", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def cmd_drain(args: argparse.Namespace) -> int:
    if args.store is not None:
        return _cmd_drain_store(args)
    impl = Path(args.impl_artifacts)
    ttl_ms = args.ttl_days * 24 * 60 * 60 * 1000
    now_dt = datetime.fromtimestamp(args.now_epoch / 1000, tz=timezone.utc)

    replayable: list[dict] = []
    tombstones = 0
    dead_lettered = 0

    if not impl.is_dir():
        print(json.dumps({"replayable": [], "tombstones": 0, "dead_lettered": 0}))
        return 0

    # Deterministic file order. Skip the dead-letter file itself.
    outboxes = sorted(
        p for p in impl.glob("mem-outbox.*.jsonl") if p.name != _DEAD_LETTER
    )

    for path in outboxes:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        kept_lines: list[str] = []
        dead_entries: list[dict] = []
        line_no = 0
        for raw_line in content.splitlines():
            if not raw_line.strip():
                continue
            line_no += 1
            try:
                entry = json.loads(raw_line)
            except ValueError:
                # Unparseable line: drop it as a tombstone (it can never replay).
                tombstones += 1
                continue
            if not isinstance(entry, dict):
                tombstones += 1
                continue

            spilled_dt = _parse_iso(entry.get("spilled_at"))
            attempts = entry.get("attempts")
            if not isinstance(attempts, int) or isinstance(attempts, bool):
                attempts = 0

            # TTL expiry (vs spilled_at) -> tombstone, dropped.
            if spilled_dt is not None:
                age_ms = (now_dt - spilled_dt).total_seconds() * 1000
                if age_ms > ttl_ms:
                    tombstones += 1
                    continue

            # Too many failures -> dead-letter (preserve original stamps).
            if attempts >= _MAX_ATTEMPTS:
                dead_entries.append(entry)
                dead_lettered += 1
                continue

            # Replayable: report it and bump attempts in place. Original
            # payload + spilled_at are preserved verbatim.
            replayable.append(
                {"file": str(path), "line_no": line_no, "payload": entry.get("payload")}
            )
            bumped = dict(entry)
            bumped["attempts"] = attempts + 1
            kept_lines.append(json.dumps(bumped, sort_keys=True))

        _append_dead(impl, dead_entries)
        _atomic_write_lines(path, kept_lines)

    print(
        json.dumps(
            {
                "replayable": replayable,
                "tombstones": tombstones,
                "dead_lettered": dead_lettered,
            },
            sort_keys=True,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# write (the local run store)
# ---------------------------------------------------------------------------

# Counts the store drain always reports, zero included.
_STORE_DRAIN_COUNTS = (
    "converted",
    "dead_lettered",
    "deferred",
    "legacy_unconvertible",
    "run_id_invalid",
    "skipped_existing",
    "target_foreign",
    "tombstones",
    "written",
)


def _iso_from_dt(moment: datetime) -> str:
    """The outbox's ``spilled_at`` format (the same as mc.utc_now_iso())."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _target_foreign_note(target: Path, where: str) -> str:
    return (
        f"{mc.NOTE_MEM_TARGET_FOREIGN}: {target} holds something other than this "
        f"run's record; it was left untouched and {where} was dead-lettered to {_DEAD_LETTER}"
    )


def _deferred_note(exc: OSError, outbox: str) -> str:
    return (
        f"{mc.WARN_MEM_WRITE_DEFERRED}: the store could not be written ({exc}); "
        f"the record stays in {outbox} for a later drain"
    )


def _dead_entry(entry: dict, token: str) -> dict:
    """A dead-letter line: the outbox entry as it stands, plus the NOTE token that sent it there."""
    dead = dict(entry)
    dead["note"] = token
    return dead


def _spill_entry(impl: Path, run_id: str, entry: dict) -> Path:
    """Append one entry to this run's outbox (the same line format spill writes)."""
    impl.mkdir(parents=True, exist_ok=True)
    path = _outbox_path(impl, run_id)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return path


def cmd_write(args: argparse.Namespace) -> int:
    # The run_id names the run file and the outbox, so it is checked before
    # anything else: no git call, no store root, no outbox, no dead-letter.
    if not mc.valid_run_id(args.run_id):
        print(json.dumps({"error": f"invalid run_id {args.run_id!r}: expected epic-<id>-<YYYYMMDD>T<HHMMSS>Z"}))
        return 2

    gate_status = (args.gate_status or "").strip().upper()
    if gate_status == "NOT_EVALUATED":
        print(json.dumps(
            {"status": "skip", "reason": "gate NOT_EVALUATED; no record written", "notes": []},
            sort_keys=True,
        ))
        return 0

    store = mc.resolve_store_root(args.store, project_root=args.project_root)
    if store is None:
        print(json.dumps(
            {"status": "store-unset", "notes": [mc.store_unset_note("no record was written")]},
            sort_keys=True,
        ))
        return 0

    cwd = args.cwd or "."
    created_at_epoch = mc.utc_now_epoch_ms()
    payload = _build_payload(args, gate_status)
    if mc.fingerprint_dir(payload["fingerprint"]) is None:
        # No commit yet (or not a git repo): the record could never name its
        # folder, now or on a later drain, so nothing is written or spilled.
        print(json.dumps(
            {"status": "no-fingerprint", "reason": "no repo fingerprint; no record written", "notes": []},
            sort_keys=True,
        ))
        return 0
    record = mc.store_record(
        payload,
        created_at_epoch=created_at_epoch,
        project=mc.main_worktree_name(cwd) or "",
    )

    impl = Path(args.impl_artifacts)
    try:
        result = mc.write_run_record(store, record)
    except ValueError as exc:
        print(json.dumps({"error": f"record not writable: {exc}"}))
        return 2
    except OSError as exc:
        entry = {"payload": record, "attempts": 0, "spilled_at": mc.utc_now_iso()}
        try:
            outbox = _spill_entry(impl, args.run_id, entry)
        except OSError as spill_exc:
            print(json.dumps({"error": f"store write failed ({exc}) and the spill failed: {spill_exc}"}))
            return 1
        print(json.dumps(
            {"status": "deferred", "outbox": str(outbox), "notes": [_deferred_note(exc, outbox.name)]},
            sort_keys=True,
        ))
        return 0

    if result.status == mc.WRITE_FOREIGN_TARGET:
        entry = {"payload": record, "attempts": 0, "spilled_at": mc.utc_now_iso()}
        try:
            impl.mkdir(parents=True, exist_ok=True)
            _append_dead(impl, [_dead_entry(entry, mc.NOTE_MEM_TARGET_FOREIGN)])
        except OSError as exc:
            print(json.dumps({"error": f"target is foreign and the dead-letter failed: {exc}"}))
            return 1
        print(json.dumps(
            {
                "status": result.status,
                "path": str(result.path),
                "dead_letter": str(impl / _DEAD_LETTER),
                "notes": [_target_foreign_note(result.path, "this run's entry")],
            },
            sort_keys=True,
        ))
        return 0

    print(json.dumps({"status": result.status, "path": str(result.path), "notes": []}, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# drain --store (replay into the local run store, legacy conversion)
# ---------------------------------------------------------------------------


def _unconvertible(where: str, what: str, entry: dict, counts: dict, notes: list[str]) -> tuple[str, dict]:
    """Dead-letter an entry that holds no record this version can write."""
    counts["legacy_unconvertible"] += 1
    counts["dead_lettered"] += 1
    notes.append(
        f"{mc.NOTE_MEM_LEGACY_UNCONVERTIBLE}: {where} {what}; it was dead-lettered to {_DEAD_LETTER}"
    )
    return "dead", _dead_entry(entry, mc.NOTE_MEM_LEGACY_UNCONVERTIBLE)


def _run_id_rejected(where: str, entry: dict, counts: dict, notes: list[str]) -> tuple[str, dict]:
    """Dead-letter an entry whose run_id fails the check; the others still land."""
    counts["run_id_invalid"] += 1
    counts["dead_lettered"] += 1
    notes.append(
        f"{mc.NOTE_MEM_RUN_ID_INVALID}: {where} names a run_id that fails the check; "
        f"it was dead-lettered to {_DEAD_LETTER}"
    )
    return "dead", _dead_entry(entry, mc.NOTE_MEM_RUN_ID_INVALID)


def _replay_into_store(
    store: Path, entry: dict, where: str, outbox_name: str, counts: dict, notes: list[str]
) -> tuple[str, dict | None]:
    """Write one spilled record through the store writer; decide the entry's fate.

    Returns ("drop", None) once it lands or is skipped-existing, ("dead", entry)
    for a foreign target, a record the writer refuses, or the third OSError,
    and ("keep", entry) to requeue it after an OSError. ``attempts`` moves only
    on an OSError.
    """
    record = entry["payload"]
    try:
        result = mc.write_run_record(store, record)
    except ValueError:
        # The writer refuses the record before touching the disk. The caller
        # validates first, so this is a backstop: a line that can never land
        # is dead-lettered at once rather than crashing every later drain.
        return _unconvertible(where, "is not a store record this version can write", entry, counts, notes)
    except OSError as exc:
        bumped = dict(entry)
        bumped["attempts"] = entry["attempts"] + 1
        if bumped["attempts"] >= _MAX_ATTEMPTS:
            counts["dead_lettered"] += 1
            return "dead", bumped
        counts["deferred"] += 1
        notes.append(_deferred_note(exc, outbox_name))
        return "keep", bumped
    if result.status == mc.WRITE_WRITTEN:
        counts["written"] += 1
        return "drop", None
    if result.status == mc.WRITE_SKIPPED_EXISTING:
        counts["skipped_existing"] += 1
        return "drop", None
    counts["target_foreign"] += 1
    counts["dead_lettered"] += 1
    notes.append(_target_foreign_note(result.path, where))
    return "dead", _dead_entry(entry, mc.NOTE_MEM_TARGET_FOREIGN)


def _run_id_invalid(payload: object) -> bool:
    """True when a payload names a run_id (any non-None value) that fails the check."""
    run_id = payload.get("run_id") if isinstance(payload, dict) else None
    return run_id is not None and not mc.valid_run_id(run_id)


def _drain_store_entry(
    entry: dict,
    *,
    store: Path,
    now_dt: datetime,
    ttl_ms: int,
    where: str,
    outbox_name: str,
    counts: dict,
    notes: list[str],
) -> tuple[str, dict | None]:
    """Decide one outbox entry in store mode: ("drop" | "keep" | "dead", entry).

    Order: a legacy entry is converted (or dead-lettered) before any TTL check;
    any other entry is first checked for a bad run_id, then for a record this
    version can write (both dead-lettered at once with their NOTE, whatever the
    entry's age or attempts), and only then meets the TTL and the attempt cap.
    """
    payload = entry.get("payload")
    attempts = entry.get("attempts")
    if not isinstance(attempts, int) or isinstance(attempts, bool):
        attempts = 0

    if mc.is_legacy_payload(payload):
        # A parked claude-mem era summary is old by construction, so it is
        # converted BEFORE the TTL check (a TTL-first drain would tombstone the
        # only history the upgrade carries over). Its attempts are reset to 0:
        # the old drain bumped them on every report, failed or not.
        legacy = dict(entry)
        legacy["attempts"] = 0
        if _run_id_invalid(mc.extract_payload(payload)):
            return _run_id_rejected(where, legacy, counts, notes)
        record = mc.legacy_payload_to_record(payload)
        if record is None:
            return _unconvertible(where, "could not be converted into a store record", legacy, counts, notes)
        counts["converted"] += 1
        # If the store refuses the write, the entry is requeued as the
        # converted record, marked ``converted`` so no later drain's TTL
        # tombstones it: the TTL is for deferred store writes, and this is the
        # only history the upgrade carries over. The attempt cap still applies,
        # and a dead-lettered entry is kept for inspection.
        spilled_at = entry.get("spilled_at")
        converted = {
            "payload": record,
            "attempts": 0,
            "spilled_at": spilled_at if isinstance(spilled_at, str) else _iso_from_dt(now_dt),
            "converted": True,
        }
        return _replay_into_store(store, converted, where, outbox_name, counts, notes)

    current = dict(entry)
    current["attempts"] = attempts
    if _run_id_invalid(payload):
        return _run_id_rejected(where, current, counts, notes)
    if mc.validate_record(payload) != mc.RECORD_OK:
        # Neither a legacy summary nor a store record this version can write:
        # something parked before the store existed that cannot convert.
        return _unconvertible(where, "is not a store record and could not be converted", current, counts, notes)

    # A deferred store write keeps the TTL; a converted legacy entry does not.
    spilled_dt = _parse_iso(entry.get("spilled_at"))
    if spilled_dt is not None and entry.get("converted") is not True:
        age_ms = (now_dt - spilled_dt).total_seconds() * 1000
        if age_ms > ttl_ms:
            counts["tombstones"] += 1
            return "drop", None

    if attempts >= _MAX_ATTEMPTS:
        counts["dead_lettered"] += 1
        return "dead", current

    return _replay_into_store(store, current, where, outbox_name, counts, notes)


def _print_store_drain(store: Path | None, counts: dict, notes: list[str]) -> None:
    print(json.dumps(
        {**counts, "notes": notes, "store": None if store is None else str(store)},
        sort_keys=True,
    ))


def _cmd_drain_store(args: argparse.Namespace) -> int:
    """drain --store: land every spilled record in the local run store."""
    impl = Path(args.impl_artifacts)
    counts = {key: 0 for key in _STORE_DRAIN_COUNTS}
    notes: list[str] = []

    store = mc.resolve_store_root(args.store, project_root=args.project_root)
    if store is None:
        # Nowhere to land anything: the outbox is left exactly as it is.
        notes.append(mc.store_unset_note("the outbox was left as it is"))
        _print_store_drain(None, counts, notes)
        return 0

    if not impl.is_dir():
        _print_store_drain(store, counts, notes)
        return 0

    ttl_ms = args.ttl_days * 24 * 60 * 60 * 1000
    now_dt = datetime.fromtimestamp(args.now_epoch / 1000, tz=timezone.utc)

    # Deterministic file order. The dead-letter file is never read: it stays
    # terminal and unconverted, kept for inspection.
    outboxes = sorted(
        p for p in impl.glob("mem-outbox.*.jsonl") if p.name != _DEAD_LETTER
    )

    for path in outboxes:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        kept_lines: list[str] = []
        dead_entries: list[dict] = []
        line_no = 0
        for raw_line in content.splitlines():
            if not raw_line.strip():
                continue
            line_no += 1
            try:
                entry = json.loads(raw_line)
            except ValueError:
                counts["tombstones"] += 1
                continue
            if not isinstance(entry, dict):
                counts["tombstones"] += 1
                continue

            action, outcome = _drain_store_entry(
                entry,
                store=store,
                now_dt=now_dt,
                ttl_ms=ttl_ms,
                where=f"{path.name} line {line_no}",
                outbox_name=path.name,
                counts=counts,
                notes=notes,
            )
            if action == "keep":
                kept_lines.append(json.dumps(outcome, sort_keys=True))
            elif action == "dead":
                dead_entries.append(outcome)

        _append_dead(impl, dead_entries)
        _atomic_write_lines(path, kept_lines)

    _print_store_drain(store, counts, notes)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Cross-Session Recall observation builder + outbox for ultracode-goal."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build a save_observation-ready payload.")
    p_build.add_argument("--impl-artifacts", required=True, dest="impl_artifacts")
    p_build.add_argument("--epic", required=True)
    p_build.add_argument("--run-id", required=True, dest="run_id")
    p_build.add_argument("--gate-status", required=True, dest="gate_status")
    p_build.add_argument("--verdict", required=True)
    p_build.add_argument("--project", required=True)
    p_build.add_argument("--deferred", default=None)
    p_build.add_argument("--root-cause", action="append", dest="root_cause", default=[])
    p_build.add_argument("--advisory", action="append", dest="advisory", default=[])
    p_build.add_argument("--cwd", default=None)
    p_build.add_argument("--valid-until-sha", default=None, dest="valid_until_sha")
    p_build.add_argument("--valid-until-date", default=None, dest="valid_until_date")
    p_build.set_defaults(func=cmd_build)

    p_spill = sub.add_parser("spill", help="Append a payload to the per-run outbox.")
    p_spill.add_argument("--impl-artifacts", required=True, dest="impl_artifacts")
    p_spill.add_argument("--run-id", required=True, dest="run_id")
    p_spill.set_defaults(func=cmd_spill)

    p_drain = sub.add_parser("drain", help="Replay/expire/dead-letter outbox entries.")
    p_drain.add_argument("--impl-artifacts", required=True, dest="impl_artifacts")
    p_drain.add_argument("--ttl-days", type=int, default=14, dest="ttl_days")
    p_drain.add_argument("--now-epoch", type=int, default=None, dest="now_epoch")
    p_drain.add_argument(
        "--store", nargs="?", const="", default=None,
        help="cross_session_recall_store value: land spilled records in the local store "
        "(a bare --store counts as unset).",
    )
    p_drain.add_argument("--project-root", default=None, dest="project_root")
    p_drain.add_argument("--cwd", default=None)
    p_drain.set_defaults(func=cmd_drain)

    p_write = sub.add_parser("write", help="Build this run's record and create its run file in the local store.")
    p_write.add_argument("--impl-artifacts", required=True, dest="impl_artifacts")
    p_write.add_argument(
        "--store", nargs="?", const="", required=True,
        help="cross_session_recall_store value (a bare --store counts as unset).",
    )
    p_write.add_argument("--project-root", default=None, dest="project_root")
    p_write.add_argument("--epic", required=True)
    p_write.add_argument("--run-id", required=True, dest="run_id")
    p_write.add_argument("--gate-status", required=True, dest="gate_status")
    p_write.add_argument("--verdict", required=True)
    p_write.add_argument("--deferred", default=None)
    p_write.add_argument("--root-cause", action="append", dest="root_cause", default=[])
    p_write.add_argument("--advisory", action="append", dest="advisory", default=[])
    p_write.add_argument("--cwd", default=None)
    p_write.add_argument("--valid-until-sha", default=None, dest="valid_until_sha")
    p_write.add_argument("--valid-until-date", default=None, dest="valid_until_date")
    p_write.set_defaults(func=cmd_write)

    args = parser.parse_args(argv)
    if args.command == "drain" and args.store is None:
        if args.project_root is not None or args.cwd is not None:
            parser.error("drain: --project-root and --cwd apply only with --store")

    if getattr(args, "command", None) == "drain" and args.now_epoch is None:
        import time

        args.now_epoch = int(time.time() * 1000)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
