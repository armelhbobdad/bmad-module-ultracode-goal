#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Cross-Session Recall write path for ultracode-goal (D12) — build/spill/drain.

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
    mean no locking is ever needed.

drain
    Scan ALL mem-outbox.*.jsonl: expire entries past TTL (tombstones),
    dead-letter entries that have failed >=3 times, and report the rest as
    replayable while incrementing their attempt counters in place. Original
    spill stamps are preserved verbatim.
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

import mem_common as mc

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


def _count_deferred(deferred_path: Path | None, epic: str) -> int:
    """Count '- ' list items under this epic's heading in a deferred ledger.

    The heading is any markdown heading line whose text contains the epic id. We
    count '- ' bullet lines until the next heading of the same-or-shallower
    level. Absent file or no matching heading -> 0.
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
    count = 0
    epic_token = str(epic).strip()

    for line in lines:
        m = heading_re.match(line)
        if m:
            level = len(m.group(1))
            heading_text = m.group(2)
            if in_section and level <= section_level:
                # A sibling or shallower heading ends our section.
                in_section = False
            if not in_section and epic_token and epic_token in heading_text:
                in_section = True
                section_level = level
            continue
        if in_section and line.lstrip().startswith("- "):
            count += 1
    return count


def cmd_build(args: argparse.Namespace) -> int:
    gate_status = (args.gate_status or "").strip().upper()
    if gate_status == "NOT_EVALUATED":
        print(json.dumps({"skip": True, "reason": "gate NOT_EVALUATED; no payload written"}))
        return 0

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


def cmd_spill(args: argparse.Namespace) -> int:
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
    p_drain.set_defaults(func=cmd_drain)

    args = parser.parse_args(argv)

    if getattr(args, "command", None) == "drain" and args.now_epoch is None:
        import time

        args.now_epoch = int(time.time() * 1000)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
