#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Deterministic fingerprint + seen-cache plumbing for the ultracode-goal health check.

Plumbing ONLY. This script computes the dedup fingerprint for a health-check
finding and manages the machine-local seen-cache. It does NO network, NO `gh`,
and makes NO submit/queue/route decisions — that judgment lives in
references/health-check.md (the LLM). Here we only guarantee a byte-stable
fingerprint and a crash-proof cache.

The fingerprint is install-mode-invariant: the `step_file` component is ALWAYS
the source-repo form `skills/ultracode-goal/references/{stage}.md` regardless of
where the skill is installed, so the same defect dedups to the same key across a
dev checkout and an installed `_bmad/` tree.

    fp = "fp-" + sha1("{severity}|ultracode-goal/{stage}|"
                      "skills/ultracode-goal/references/{stage}.md|{section-slug}")[:7]

Subcommands:
  fingerprint --severity S --stage T --section-slug SLUG
      Validate S against the 3 severities and T against the 6 stages; validate
      SLUG against ^[a-z0-9]+(-[a-z0-9]+)*$. Emit {"fp": ..., "tuple": ...}.
  seen --fp FP --cache PATH
      Validate FP. Missing/empty/corrupt cache -> {"seen": false, "record": null}
      (never crash). Found -> {"seen": true, "record": {...}}.
  record --fp FP --cache PATH --issue-url URL --action A --date YYYY-MM-DD
      Validate FP + action. Create parent dirs. Merge-write (preserve other fps),
      atomic via temp file + os.replace. Emit {"written": true, "fp": FP}.

Output: JSON to stdout. Errors are JSON to stdout with exit code 1. A successful
payload exits 0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

SEVERITIES = ("bug", "friction", "gap")
STAGES = (
    "ingest-and-scope",
    "preflight",
    "define-done",
    "execute",
    "gate",
    "finalize",
)
ACTIONS = ("created", "reacted", "commented", "queued")

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FP_RE = re.compile(r"^fp-[0-9a-f]{7}$")


def _fail(message: str) -> int:
    print(json.dumps({"error": message}))
    return 1


def _compute_fp(severity: str, stage: str, slug: str) -> tuple[str, str]:
    """Return (fp, tuple_string). The tuple string is the exact sha1 input."""
    step_file = f"skills/ultracode-goal/references/{stage}.md"
    tuple_str = f"{severity}|ultracode-goal/{stage}|{step_file}|{slug}"
    digest = hashlib.sha1(tuple_str.encode("utf-8")).hexdigest()[:7]
    return f"fp-{digest}", tuple_str


def cmd_fingerprint(args: argparse.Namespace) -> int:
    if args.severity not in SEVERITIES:
        return _fail(
            "invalid severity %r; expected one of %s"
            % (args.severity, ", ".join(SEVERITIES))
        )
    if args.stage not in STAGES:
        return _fail(
            "invalid stage %r; expected one of %s" % (args.stage, ", ".join(STAGES))
        )
    if not SLUG_RE.match(args.section_slug):
        return _fail(
            "invalid section-slug %r; expected kebab-case ^[a-z0-9]+(-[a-z0-9]+)*$"
            % args.section_slug
        )

    fp, tuple_str = _compute_fp(args.severity, args.stage, args.section_slug)
    print(json.dumps({"fp": fp, "tuple": tuple_str}))
    return 0


def _load_cache(cache: Path) -> dict:
    """Read the seen-cache as a dict. Missing/empty/corrupt -> {} (never raises)."""
    try:
        # errors="replace" so raw non-UTF-8 garbage decodes to junk text rather
        # than raising at the read stage; the json.loads below then rejects it.
        text = cache.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return {}
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def cmd_seen(args: argparse.Namespace) -> int:
    if not FP_RE.match(args.fp):
        return _fail("invalid fp %r; expected ^fp-[0-9a-f]{7}$" % args.fp)

    cache = Path(args.cache).expanduser()
    data = _load_cache(cache)
    record = data.get(args.fp)
    if isinstance(record, dict):
        print(json.dumps({"seen": True, "record": record}))
    else:
        print(json.dumps({"seen": False, "record": None}))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    if not FP_RE.match(args.fp):
        return _fail("invalid fp %r; expected ^fp-[0-9a-f]{7}$" % args.fp)
    if args.action not in ACTIONS:
        return _fail(
            "invalid action %r; expected one of %s"
            % (args.action, ", ".join(ACTIONS))
        )

    cache = Path(args.cache).expanduser()
    cache.parent.mkdir(parents=True, exist_ok=True)

    # Merge: preserve every other fp; a corrupt/empty cache is treated as empty.
    data = _load_cache(cache)
    data[args.fp] = {
        "issue_url": args.issue_url,
        "action": args.action,
        "date": args.date,
    }

    # Atomic write: temp file in the same dir, then os.replace.
    fd, tmp_name = tempfile.mkstemp(dir=str(cache.parent), prefix=".hc-seen-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, str(cache))
    except OSError as exc:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        return _fail("could not write cache %s: %s" % (cache, exc))

    print(json.dumps({"written": True, "fp": args.fp}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fingerprint + seen-cache plumbing for the ultracode-goal health check."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fp_parser = sub.add_parser("fingerprint", help="Compute the dedup fingerprint.")
    fp_parser.add_argument("--severity", required=True)
    fp_parser.add_argument("--stage", required=True)
    fp_parser.add_argument("--section-slug", required=True, dest="section_slug")
    fp_parser.set_defaults(func=cmd_fingerprint)

    seen_parser = sub.add_parser("seen", help="Check the seen-cache for a fingerprint.")
    seen_parser.add_argument("--fp", required=True)
    seen_parser.add_argument("--cache", required=True)
    seen_parser.set_defaults(func=cmd_seen)

    rec_parser = sub.add_parser("record", help="Record a fingerprint outcome to the cache.")
    rec_parser.add_argument("--fp", required=True)
    rec_parser.add_argument("--cache", required=True)
    rec_parser.add_argument("--issue-url", required=True, dest="issue_url")
    rec_parser.add_argument("--action", required=True)
    rec_parser.add_argument("--date", required=True)
    rec_parser.set_defaults(func=cmd_record)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
