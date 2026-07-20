#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Deterministic identity for preflight REDs, and the resolved-RED override.

A blocked run is unblocked by matching an operator's recorded answer back to the
finding it answers. That match is by `id` only, so the id is a join key shared by
two surfaces that never run in the same session: preflight mints it during the
semantic scan, and `/ucg-resolve` records an answer against it hours or days
later. Minting it from prose made it a value two independent model invocations had
to agree on by hand, and they cannot. This module is the fix -- it owns the
derivation and the override, so the id is computed one way, by code.

The identity rules, all of them mechanical:

  - An id is `<kind>:<bare artifact path>:<digest>`, where `<digest>` is the first
    12 hex characters of the SHA-256 of the whitespace-normalized
    `decision_needed`. Line numbers are excluded: `source` arrives as
    `<path>:<line>`, and a line-bearing id would evaporate the moment anyone
    edited above the finding, taking the operator's answer with it.
  - The digest is what makes the id UNIQUE. One artifact routinely carries several
    findings of the same `kind`, and on `kind` plus path alone they would collide,
    so one answer would clear every decision sharing the id -- a fail-open at a
    hard gate.
  - Recognition of a decision already on record is EXACT: the same decision stated
    the same way digests to the same id, so an answer recorded against it still
    matches. A reword mints a NEW id and the decision is asked again.
  - That last point is a deliberate refusal, not a gap. Judging whether a reworded
    finding is "the same decision" is a judgment, not a computation, and every
    mechanical proxy for it -- pairing on `(kind, path)` when one candidate
    remains, or scoring text similarity -- can silently adopt a brand-new decision
    into an answered one's identity, suppressing a question nobody answered and
    opening the hard gate on it. A repeated question costs an operator one answer;
    a swallowed one costs the run its whole reason for stopping. This fails CLOSED
    and never guesses.
  - Closed ids are kept as `resolved` tombstones. They are an audit record, not
    part of matching: because ids are derived, a closed decision restated
    unchanged re-derives to its own id and is suppressed with no lookup. The
    record is what lets a reader see which decisions were settled, rather than
    inferring it from an absence.

The override then drops every red whose id an operator closed. It is deliberately
asymmetric about failure: an unreadable `.decisions.json` suppresses nothing (a
suppression file that cannot be read is not a suppression), while an unreadable
`.preflight-reds.json` is a hard error that writes nothing, because overwriting
the identity registry would strand every answer already recorded against it.

Stdlib only. This module forms no verdict and reads no artifact corpus: it decides
identity and suppression, and leaves every judgment to the prompt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

DIGEST_LEN = 12
SIDECAR_NAME = ".preflight-reds.json"
RED_FIELDS = ("source", "kind", "decision_needed", "evidence")


class RedIdError(RuntimeError):
    """A fail-closed condition: nothing is written and the caller must stop."""


# --- identity ----------------------------------------------------------------
def normalize(text: str) -> str:
    """Collapse a decision statement to its comparable form.

    NFC so visually identical text digests identically, and whitespace collapsed
    so a re-wrap of the same sentence is the same sentence.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def digest_of(decision_needed: str) -> str:
    return hashlib.sha256(normalize(decision_needed).encode("utf-8")).hexdigest()[:DIGEST_LEN]


def bare_path(source: str) -> str:
    """`<path>:<line>` -> `<path>`.

    Only a trailing all-digit segment is stripped: a path may legitimately contain
    a colon, and a line number is the only suffix the scan contract appends.
    """
    return re.sub(r":\d+$", "", (source or "").strip())


def mint_id(kind: str, source: str, decision_needed: str) -> str:
    return f"{(kind or '').strip()}:{bare_path(source)}:{digest_of(decision_needed)}"


def key_of(entry: dict[str, Any]) -> tuple[str, str]:
    return ((entry.get("kind") or "").strip(), bare_path(entry.get("source") or entry.get("path") or ""))


# --- derivation --------------------------------------------------------------
def reconcile(fresh: list[dict]) -> list[dict]:
    """Give each red its id.

    There is no lookup here, and that is the point. The id is a pure function of
    the decision -- `(kind, bare path, digest of decision_needed)` -- so a decision
    already on record re-derives to the id it already had, with nothing to match
    against and nothing to get wrong. Recognition is a property of the derivation
    rather than a step that can pair the wrong things.

    The exactness is a deliberate refusal. Judging whether a REWORDED finding is
    "the same decision" is a judgment, and both mechanical proxies for it fail in
    the direction this gate cannot afford. Pairing on `(kind, path)` when one
    candidate remains silently adopts a brand-new, never-answered decision into a
    closed one's identity: the operator is never shown it and the hard gate opens
    on it. Scoring text similarity moves the same guess behind a threshold. So a
    reword mints a new id and the decision is asked again, costing one repeated
    question, where the alternative loses a decision nobody made.

    Two reds sharing an id therefore means exactly one thing: they state the same
    decision, in the same words, in the same artifact. That is the same decision
    reported twice, and one answer settling both is correct.
    """
    return [
        {**red, "id": mint_id(red.get("kind", ""), red.get("source", ""), red.get("decision_needed", ""))}
        for red in fresh
    ]


# --- override -----------------------------------------------------------------
def closed_ids(decisions_path: Path) -> set[str]:
    """Ids an operator closed. Unreadable or malformed suppresses nothing."""
    try:
        data = json.loads(decisions_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if not isinstance(data, dict) or not isinstance(data.get("decisions"), list):
        return set()
    return {
        d["id"]
        for d in data["decisions"]
        if isinstance(d, dict) and d.get("action") == "close" and isinstance(d.get("id"), str)
    }


def load_sidecar(path: Path) -> tuple[list[dict], list[dict]]:
    """Existing pending reds and tombstones. A corrupt registry is fail-closed.

    Fail-closed means EVERY malformed shape raises, not just an unparseable file.
    Quietly coercing a wrong-typed `reds` to an empty list would read as "nothing
    is pending" and let the next write replace the registry with that emptiness,
    silently discarding REDs nobody has answered -- the same fail-open as a bad
    suppression, arrived at through a type confusion.
    """
    if not path.exists():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RedIdError(
            f"{path} is unreadable ({exc}); refusing to overwrite the id registry, "
            "because every answer already recorded is keyed to the ids it holds"
        ) from exc
    if not isinstance(data, dict):
        raise RedIdError(f"{path} is not a JSON object; refusing to overwrite the id registry")

    out: list[list[dict]] = []
    for field in ("reds", "resolved"):
        value = data.get(field, [])
        if not isinstance(value, list) or not all(isinstance(entry, dict) for entry in value):
            raise RedIdError(
                f"{path} has a malformed `{field}`: expected a list of objects. Refusing to "
                "overwrite the id registry, because treating it as empty would discard every "
                "decision it holds"
            )
        out.append(value)
    return out[0], out[1]


def validate_reds(reds: list[dict]) -> None:
    """Every red must carry the three fields the id is minted from.

    `decision_needed` is the load-bearing one: it is what the digest is taken
    from, so an absent or blank value digests to a CONSTANT and the id collapses
    to `kind` plus path -- exactly the collision the digest exists to prevent.
    Every distinct decision in one artifact would then share an id, and one close
    would suppress all of them, opening the hard gate on questions nobody
    answered. Both entry paths validate, because `--from-sidecar` never passes
    through the scan reader.
    """
    for red in reds:
        if not isinstance(red, dict) or not (red.get("kind") and red.get("source")):
            raise RedIdError("every red must be an object carrying `kind` and `source`")
        decision = red.get("decision_needed")
        if not isinstance(decision, str) or not normalize(decision):
            raise RedIdError(
                "every red must carry a non-empty string `decision_needed`: the id's digest "
                "is minted from it, and without it two distinct decisions collapse onto one "
                "id and a single answer suppresses both"
            )


def apply(scan_reds: list[dict], impl: Path) -> dict[str, Any]:
    """Validate, mint ids, drop closed reds, and return the sidecar to write."""
    sidecar = impl / SIDECAR_NAME
    tombstones = load_sidecar(sidecar)[1]
    validate_reds(scan_reds)
    reconciled = reconcile(scan_reds)

    closed = closed_ids(impl / ".decisions.json")
    surviving = [r for r in reconciled if r["id"] not in closed]

    # `resolved` is the audit trail of what has been decided, not part of matching:
    # ids are derived, so a closed decision restated unchanged re-derives to its own
    # id and the override suppresses it with no lookup. Keeping the record is what
    # lets an operator (and /ucg-status) see which decisions were settled and when
    # a question stopped being asked, rather than inferring it from an absence.
    keep = {t["id"]: t for t in tombstones if t.get("id")}
    for red in reconciled:
        if red["id"] in closed:
            kind, path = key_of(red)
            keep[red["id"]] = {"id": red["id"], "kind": kind, "path": path}
    return {
        "reds": [{"id": r["id"], **{f: r.get(f, "") for f in RED_FIELDS}} for r in surviving],
        "resolved": sorted(keep.values(), key=lambda t: t["id"]),
    }


# --- cli ----------------------------------------------------------------------
def _read_scan(path: str) -> list[dict]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise RedIdError(f"scan input is not valid JSON: {exc}") from exc
    reds = data.get("reds") if isinstance(data, dict) else None
    if not isinstance(reds, list):
        raise RedIdError('scan input must be an object carrying a "reds" list')
    validate_reds(reds)
    return reds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mint stable RED ids, inherit them across rescans, and apply the resolved-RED override.",
    )
    parser.add_argument("--scan", help="the subagent scan object, or - for stdin")
    parser.add_argument(
        "--from-sidecar",
        action="store_true",
        help="re-apply the override to the reds already on disk, with no new scan "
        "(how /ucg-resolve makes a close take effect without inventing a scan)",
    )
    parser.add_argument(
        "--mint-one",
        nargs=3,
        metavar=("KIND", "SOURCE", "DECISION_NEEDED"),
        help="print the id for a single item and exit, touching no file (how /ucg-resolve "
        "keys a typed escalation sidecar, whose four-field shape cannot carry an id)",
    )
    parser.add_argument("--impl-artifacts", help="the resolved implementation-artifacts dir")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the outcome without writing the sidecar",
    )
    args = parser.parse_args(argv)

    if args.mint_one:
        print(mint_id(args.mint_one[0], args.mint_one[1], args.mint_one[2]))
        return 0

    if not args.impl_artifacts:
        parser.error("--impl-artifacts is required unless --mint-one is used")
    if bool(args.scan) == bool(args.from_sidecar):
        parser.error("pass exactly one of --scan or --from-sidecar")

    try:
        impl = Path(args.impl_artifacts)
        # --from-sidecar feeds the stored reds back through the same path, so a
        # close is applied by the one component that owns these ids rather than by
        # a second writer hand-editing the file.
        scan = load_sidecar(impl / SIDECAR_NAME)[0] if args.from_sidecar else _read_scan(args.scan)
        result = apply(scan, impl)
    except RedIdError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2

    if not args.dry_run:
        impl.mkdir(parents=True, exist_ok=True)
        (impl / SIDECAR_NAME).write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
