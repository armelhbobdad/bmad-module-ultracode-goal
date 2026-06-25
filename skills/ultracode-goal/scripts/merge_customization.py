#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tomli-w"]
# ///
"""Install-time merge of a UCG-awareness fragment into a BMad customize target.

Lands a fragment's flat ``persistent_facts`` string facts into a target
customization TOML (e.g. ``_bmad/custom/bmad-prd.toml``) using a stamp-scoped
anti-zombie strip-then-reappend, mirroring ``merge_help_csv.py``:

  - the strip (``_strip_ucg_rows``) is the anti-zombie filter — every existing
    ``persistent_facts`` string carrying a ``[ucg:<id>]`` marker is removed
    before the fragment's items are re-appended, so re-install converges
    byte-stable and stale UCG rows never persist;
  - one ``[ucg]`` stamp table (``managed``/``version``/``block``/
    ``installed_at``) plus an ``item_hashes`` manifest of UCG-owned content
    hashes is (re)written under it.

The landing channel is the NESTED ``workflow.persistent_facts`` path, because
every real BMad customize target nests ``persistent_facts`` under a
``[workflow]`` table (verified: ``.claude/skills/{bmad-prd,bmad-architecture,
bmad-create-epics-and-stories,bmad-create-story}/customize.toml``). The runtime
``deep_merge`` only lands an overlay's items in
``resolved['workflow']['persistent_facts']`` when the overlay nests them under
``[workflow]`` too; writing a TOP-LEVEL ``persistent_facts`` key would be a
dark write the live resolve silently ignores. The ``[ucg]`` stamp + manifest
stay TOP-LEVEL of the overlay — that is UCG bookkeeping the live resolve never
reads, and the tool finds its own stamp top-level.

The runtime ``deep_merge`` engine is IMPORTED from
``_bmad/scripts/resolve_customization.py`` (never reimplemented). Because
``persistent_facts`` is a flat STRING array, that engine can only APPEND
(``_merge_arrays`` keys-merges only dict items with ``code``/``id``); therefore
idempotency, anti-zombie, uninstall and conflict are owned ENTIRELY by this
tool's strip-then-reappend — ``deep_merge`` is the appender the strip
compensates for, never the enforcer.

Pre-merge shape probe (three branches):
  - target absent or empty ``{}`` → FRESH install: seed ``[workflow]`` with
    ``persistent_facts`` and merge (NOT a schema-mismatch);
  - target non-empty but does not expose ``workflow.persistent_facts`` (no
    ``[workflow]`` table, or ``[workflow]`` present but no ``persistent_facts``
    key under it) → fail-loud ``schema-mismatch`` SKIP, write nothing — never a
    dark write;
  - target exposes ``workflow.persistent_facts`` → merge.

Conflict detection: a UCG-stamped row whose content-hash no longer
matches the manifest is LEFT in place and reported in ``conflicts``, never
clobbered. Non-``[ucg:``-marked human rows are always preserved.

Exit codes (the merge-family lane, NOT the gate_eval lane):
  0 = success / skip / conflict
  1 = validation error (unparseable --target or --fragment TOML)
  2 = missing engine dependency (resolve_customization.py absent)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

import tomli_w

# The single universal sanctioned landing channel the live customize schema
# exposes, nested under the [workflow] table in every real target. The
# fragment declares persistent_facts top-level; the tool lands it at
# workflow.persistent_facts so the live deep_merge actually resolves it.
WORKFLOW_KEY = "workflow"
CHANNEL = "persistent_facts"

# The per-directive identity marker embedded in each UCG-owned fact string,
# e.g. "...steer the author. [ucg:bmad-prd-01]". A stable prefix the naive
# strip can find without parsing the whole sentence.
UCG_MARKER = re.compile(r"\[ucg:([a-z0-9-]+-\d+)\]")

STAMP_KEY = "ucg"
MANIFEST_KEY = "item_hashes"


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Stamp-scoped strip-then-reappend of a UCG-awareness fragment's "
            "persistent_facts into a BMad customize target, with a pre-merge "
            "shape probe and conflict detection."
        )
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Path to the target customize TOML (e.g. _bmad/custom/bmad-prd.toml).",
    )
    parser.add_argument(
        "--fragment",
        help="Path to the UCG-awareness fragment TOML to merge (omit with --remove).",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Uninstall: strip only [ucg:<id>]-marked rows and the [ucg] table.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress to stderr.",
    )
    return parser.parse_args()


def _content_hash(text: str) -> str:
    """Stable content hash of a fact string (full string incl. its marker)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _marker_id(text: str) -> str | None:
    """The single [ucg:<id>] id embedded in a fact string, or None."""
    found = UCG_MARKER.findall(text)
    return found[0] if found else None


def _is_ucg_row(text: str) -> bool:
    return _marker_id(text) is not None


def _strip_ucg_rows(facts: list, keep_ids: set[str] | None = None) -> list:
    """Anti-zombie filter mirroring merge_help_csv.py:filter_rows.

    Remove every persistent_facts string carrying a [ucg:<id>] marker, except
    those whose id is in ``keep_ids`` (conflicted hand-edits, left in place).
    Non-string items and non-UCG human rows are always preserved.
    """
    keep_ids = keep_ids or set()
    kept = []
    for item in facts:
        if isinstance(item, str):
            marker = _marker_id(item)
            if marker is not None and marker not in keep_ids:
                continue
        kept.append(item)
    return kept


def _channel_exposed(data: dict) -> bool:
    """True iff the target exposes the nested workflow.persistent_facts channel
    (a [workflow] table carrying a persistent_facts key).
    """
    workflow = data.get(WORKFLOW_KEY)
    return isinstance(workflow, dict) and CHANNEL in workflow


def _get_channel(data: dict) -> list:
    """Return workflow.persistent_facts as a list (empty when absent)."""
    workflow = data.get(WORKFLOW_KEY)
    if not isinstance(workflow, dict):
        return []
    facts = workflow.get(CHANNEL)
    return list(facts) if isinstance(facts, list) else []


def _set_channel(data: dict, facts: list) -> None:
    """Write workflow.persistent_facts, creating the [workflow] table if needed
    (fresh-seed path). Mutates ``data`` in place.
    """
    workflow = data.get(WORKFLOW_KEY)
    if not isinstance(workflow, dict):
        workflow = {}
        data[WORKFLOW_KEY] = workflow
    workflow[CHANNEL] = facts


def _load_toml(path: Path) -> dict:
    """Parse a TOML file; raises tomllib.TOMLDecodeError on malformed input."""
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _resolve_deep_merge(target_path: Path, verbose: bool):
    """Guarded import of deep_merge from the engine at
    ``<project>/_bmad/scripts/resolve_customization.py`` relative to --target
    (which lives under ``_bmad/custom/``). Never define it locally.

    Returns the imported callable, or None when the engine is absent — the
    caller then takes the documented exit-2 missing-dep path.
    """
    # --target == .../_bmad/custom/<name>.toml ; engine == .../_bmad/scripts/.
    custom_dir = target_path.resolve().parent  # _bmad/custom
    engine_dir = custom_dir.parent / "scripts"  # _bmad/scripts
    if str(engine_dir) not in sys.path:
        sys.path.insert(0, str(engine_dir))
    try:
        from resolve_customization import deep_merge  # noqa: WPS433 (guarded)
    except ImportError:
        if verbose:
            print(f"resolve_customization not importable from {engine_dir}", file=sys.stderr)
        return None
    return deep_merge


def _emit(result: dict) -> None:
    print(json.dumps(result, indent=2))


def main() -> None:
    args = parse_args()
    verbose = args.verbose
    target_path = Path(args.target)

    # --- Guarded engine import. Even --remove honors the
    # contract: the merge family always proves the engine is present, so an
    # absent engine is the exit-2 missing-dep signal regardless of operation.
    deep_merge = _resolve_deep_merge(target_path, verbose)
    if deep_merge is None:
        print(
            "warning: resolve_customization.py (deep_merge engine) not found; "
            "writing nothing. Install BMAD's customization layer first.",
            file=sys.stderr,
        )
        sys.exit(2)

    # --- Single read of the target (no TOCTOU between probe and write).
    target_existed = target_path.exists()
    original_bytes = target_path.read_bytes() if target_existed else b""
    try:
        target_data = tomllib.loads(original_bytes.decode("utf-8")) if target_existed else {}
    except tomllib.TOMLDecodeError as error:
        print(f"Error: unparseable target TOML {target_path}: {error}", file=sys.stderr)
        sys.exit(1)

    # ----------------------------------------------------------------- remove
    if args.remove:
        _do_remove(target_path, target_data, target_existed, verbose)
        return

    # ------------------------------------------------------------------ merge
    if not args.fragment:
        print("Error: --fragment is required unless --remove is given", file=sys.stderr)
        sys.exit(1)

    fragment_path = Path(args.fragment)
    if not fragment_path.exists():
        print(f"Error: fragment not found at {fragment_path}", file=sys.stderr)
        sys.exit(1)
    try:
        fragment_data = _load_toml(fragment_path)
    except tomllib.TOMLDecodeError as error:
        print(f"Error: unparseable fragment TOML {fragment_path}: {error}", file=sys.stderr)
        sys.exit(1)

    # The fragment authors persistent_facts at TOP LEVEL; the
    # tool re-homes those items into the target's nested workflow channel.
    fragment_facts = fragment_data.get(CHANNEL, [])
    fragment_stamp = fragment_data.get(STAMP_KEY, {})

    # --- Pre-merge shape probe, three branches:
    #   1. absent/empty target  -> FRESH install: seed [workflow] and merge;
    #   2. non-empty but no workflow.persistent_facts -> schema-mismatch SKIP;
    #   3. exposes workflow.persistent_facts -> merge.
    is_fresh = not target_existed or not target_data
    if not is_fresh and not _channel_exposed(target_data):
        result = {
            "status": "skipped",
            "skipped": "schema-mismatch",
            "channel": f"{WORKFLOW_KEY}.{CHANNEL}",
            "target_path": str(target_path.resolve()),
            "rows_removed": 0,
            "rows_added": 0,
            "conflicts": [],
        }
        _emit(result)
        sys.exit(0)

    existing_facts = _get_channel(target_data)
    prior_stamp = target_data.get(STAMP_KEY, {})
    prior_manifest = {}
    if isinstance(prior_stamp, dict):
        prior_manifest = dict(prior_stamp.get(MANIFEST_KEY, {}) or {})

    # --- Conflict detection: a stamped row whose content-hash no longer
    # matches the manifest was hand-edited. Leave it in place (keep its id),
    # report the id, and do NOT re-append the fragment's version over it.
    conflicts: list[str] = []
    for item in existing_facts:
        if not isinstance(item, str):
            continue
        marker = _marker_id(item)
        if marker is None:
            continue  # human row, never a conflict
        recorded = prior_manifest.get(marker)
        if recorded is not None and recorded != _content_hash(item):
            conflicts.append(marker)
    conflicts = sorted(set(conflicts))
    conflict_set = set(conflicts)

    # --- Anti-zombie strip: remove every UCG-marked row EXCEPT the conflicted
    # ones we are leaving verbatim. Human rows pass through untouched.
    rows_before = sum(1 for item in existing_facts if isinstance(item, str) and _is_ucg_row(item))
    stripped_facts = _strip_ucg_rows(existing_facts, keep_ids=conflict_set)
    rows_removed = rows_before - len(conflict_set)

    # --- Re-append the fragment's items (each carrying its embedded marker),
    # skipping any id we are leaving as a conflicted hand-edit. The flat
    # string array is what the imported deep_merge engine would itself APPEND
    # (resolve_customization.py:_merge_arrays); we drive it explicitly so the
    # idempotency comes from the strip above, not from the appender.
    appended: list[str] = []
    manifest: dict[str, str] = {}
    for fact in fragment_facts:
        if not isinstance(fact, str):
            continue
        marker = _marker_id(fact)
        if marker is None:
            continue
        if marker in conflict_set:
            # Preserve the human's hand-edit; record its (edited) hash so a
            # subsequent unchanged run sees no further conflict drift.
            for item in stripped_facts:
                if isinstance(item, str) and _marker_id(item) == marker:
                    manifest[marker] = _content_hash(item)
                    break
            continue
        appended.append(fact)
        manifest[marker] = _content_hash(fact)

    # Carry forward manifest hashes for conflicted rows already present but not
    # in the fragment (defensive; normally all conflicts are fragment ids).
    for marker in conflict_set:
        if marker not in manifest:
            for item in stripped_facts:
                if isinstance(item, str) and _marker_id(item) == marker:
                    manifest[marker] = _content_hash(item)
                    break

    merged_facts = stripped_facts + appended
    rows_added = len(appended)

    # --- Reconstruct the output dict deterministically: drive deep_merge for
    # the channel array (proving the engine is wired), then write exactly one
    # refreshed [ucg] stamp + manifest. Rebuilding from human content + a
    # fixed-order UCG block is what makes re-serialization byte-stable.
    # The channel lands NESTED at workflow.persistent_facts (seeding [workflow]
    # on a fresh target); the stamp + manifest stay top-level.
    merged = dict(target_data)
    if isinstance(merged.get(WORKFLOW_KEY), dict):
        merged[WORKFLOW_KEY] = dict(merged[WORKFLOW_KEY])  # don't mutate the read
    # engine append over empty base == identity (proves the engine is wired):
    _set_channel(merged, deep_merge([], merged_facts))

    stamp = {
        "managed": True,
        "version": str(fragment_stamp.get("version", "")),
        "block": str(fragment_stamp.get("block", "ucg-awareness")),
        "installed_at": str(fragment_stamp.get("installed_at", "")),
        MANIFEST_KEY: {mid: manifest[mid] for mid in sorted(manifest)},
    }
    merged[STAMP_KEY] = stamp

    new_bytes = tomli_w.dumps(merged).encode("utf-8")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(new_bytes)

    result = {
        "status": "conflict" if conflicts else "success",
        "target_path": str(target_path.resolve()),
        "target_existed": target_existed,
        "rows_removed": rows_removed,
        "rows_added": rows_added,
        "skipped": None,
        "conflicts": conflicts,
    }
    if verbose:
        print(
            f"stripped {rows_removed} UCG rows, appended {rows_added}, "
            f"conflicts={conflicts}",
            file=sys.stderr,
        )
    _emit(result)
    sys.exit(0)


def _do_remove(target_path: Path, target_data: dict, target_existed: bool, verbose: bool) -> None:
    """--remove: strip only [ucg:<id>]-marked rows from workflow.persistent_facts
    + delete the top-level [ucg] table, leaving every non-UCG item and human
    scalar/table byte-identical.

    TRUE no-op when there is nothing to remove: if the target carries neither a
    [ucg] stamp NOR any [ucg:<id>]-marked row, the file is NOT rewritten (bytes
    stay byte-identical, in==out), and an absent target is left absent (never
    created). 'Nothing to remove' is a clean success (exit 0, removed:0), per
    the merge exit-code lane (1=validation, 2=missing-dep only). A second
    consecutive --remove is therefore also a no-op.
    """
    existing_facts = _get_channel(target_data)
    rows_before = sum(1 for item in existing_facts if isinstance(item, str) and _is_ucg_row(item))
    has_stamp = isinstance(target_data.get(STAMP_KEY), dict)
    nothing_to_remove = rows_before == 0 and not has_stamp

    if nothing_to_remove:
        # Do NOT touch the file: no rewrite, no creation. Byte-identical no-op.
        if verbose:
            state = "absent" if not target_existed else "no UCG artifacts"
            print(f"--remove no-op: target has {state}; wrote nothing", file=sys.stderr)
        result = {
            "status": "success",
            "target_path": str(target_path.resolve()),
            "target_existed": target_existed,
            "rows_removed": 0,
            "rows_added": 0,
            "skipped": None,
            "conflicts": [],
        }
        _emit(result)
        sys.exit(0)

    merged = dict(target_data)
    if _channel_exposed(target_data):
        merged[WORKFLOW_KEY] = dict(merged[WORKFLOW_KEY])  # don't mutate the read
        _set_channel(merged, _strip_ucg_rows(existing_facts))
    merged.pop(STAMP_KEY, None)

    new_bytes = tomli_w.dumps(merged).encode("utf-8")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(new_bytes)

    result = {
        "status": "success",
        "target_path": str(target_path.resolve()),
        "target_existed": target_existed,
        "rows_removed": rows_before,
        "rows_added": 0,
        "skipped": None,
        "conflicts": [],
    }
    if verbose:
        print(f"removed {rows_before} UCG rows + [ucg] stamp", file=sys.stderr)
    _emit(result)
    sys.exit(0)


if __name__ == "__main__":
    main()
