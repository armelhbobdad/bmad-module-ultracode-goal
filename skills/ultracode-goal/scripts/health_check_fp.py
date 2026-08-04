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
      Validate FP. Emit {"seen": B, "status": S, "record": R}, where `seen` is
      the SUPPRESSION verdict and not mere cache presence:
        unseen        {"seen": false, "status": "unseen",       "record": null}
        handled       {"seen": true,  "status": "handled",      "record": {...}}
        regression    {"seen": false, "status": "regression",   "record": {...}}
        unrecognized  {"seen": false, "status": "unrecognized", "record": {...}}
      A record whose action is in SUPPRESSING_ACTIONS suppresses; a `resolved`
      record does NOT, because a fresh sighting of a fixed defect is a
      regression, not a duplicate. The record is still returned in that case so
      the caller can link the original rather than file it as a first sighting.
      An action this version does not know cannot be confirmed handled, so it
      does not suppress either. Missing/empty/corrupt cache -> unseen (no crash).
  record --fp FP --cache PATH --issue-url URL --action A --date YYYY-MM-DD
      Validate FP + action. Create parent dirs. Merge-write (preserve other fps),
      atomic via temp file + os.replace. Emit {"written": true, "fp": FP}.
  version --project-root PATH --skill-root PATH
      Resolve the module version off a deterministic first-hit-wins probe ladder
      and emit {"version": "<resolved>", "source": "<which probe hit>"} — or
      {"version": null, "source": "N/A"} when nothing hits. A probe that exists
      but is unreadable/malformed (bad JSON, missing key, empty string) falls
      through to the next rung — it never crashes. The ladder is:
        1. <project-root>/_bmad/ucg/VERSION   (plain text)  -> "_bmad/ucg/VERSION"
        2. <skill-root>/VERSION               (plain text)  -> "{skill-root}/VERSION"
        3. <project-root>/.claude-plugin/marketplace.json    JSON plugins[0].version
                                                            -> "marketplace.json"
        4. <project-root>/package.json         JSON version  -> "package.json"

Output: JSON to stdout. Errors are JSON to stdout with exit code 1 (operational
failure); argparse usage errors exit 2. A successful payload exits 0.
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
ACTIONS = ("created", "reacted", "commented", "queued", "resolved")

# Which recorded actions SUPPRESS a later sighting of the same fingerprint.
# Deliberately a literal tuple and NOT `ACTIONS` minus `resolved`: a disposition
# added later then defaults to NOT suppressing until it is opted in here, and a
# missing or unrecognized action (a hand-edited cache, or one written by a newer
# module) does not suppress either. That is the fail-closed direction for a
# health check: a duplicate report is closed by the dedup Action, while a
# silenced regression is caught by nothing. When in doubt, report.
SUPPRESSING_ACTIONS = ("created", "reacted", "commented", "queued")

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


def _prior_filing(queue_path: Path, fp: str) -> dict | None:
    """The queued filing that carries this fingerprint, or None.

    Searched so the handled branch can compare DEFECTS without a manual
    retrieval step: the queue dir first, then its resolved/ subfolder (a
    resolved filing is still the recorded prior for a collision judgement).
    Identity is the frontmatter/underscored fingerprint line or the fp in the
    filename - never a body-wide substring, which would match filings that
    merely DISCUSS the fp. Fail-soft: an unreadable dir or file contributes
    nothing; this helper informs a judgement and never blocks one.
    """
    fp_line = re.compile(
        r"^(?:fingerprint|fp):\s*`?%s`?\s*$" % re.escape(fp), re.MULTILINE
    )
    for base in (queue_path, queue_path / "resolved"):
        try:
            entries = sorted(base.iterdir())
        except OSError:
            continue
        for path in entries:
            if not path.is_file() or path.suffix != ".md":
                continue
            named = fp in path.name
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            head = "\n".join(text.splitlines()[:40])
            if not named and not fp_line.search(head):
                continue
            title = next(
                (ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("# ")),
                None,
            )
            slug_match = re.search(r"^defect_slug:\s*([a-z0-9-]+)\s*$", head, re.MULTILINE)
            return {
                "path": str(path),
                "title": title,
                "defect_slug": slug_match.group(1) if slug_match else None,
            }
    return None


def cmd_seen(args: argparse.Namespace) -> int:
    if not FP_RE.match(args.fp):
        return _fail("invalid fp %r; expected ^fp-[0-9a-f]{7}$" % args.fp)

    cache = Path(args.cache).expanduser()
    data = _load_cache(cache)
    record = data.get(args.fp)

    queue_path = getattr(args, "queue_path", None)
    prior = _prior_filing(Path(queue_path).expanduser(), args.fp) if queue_path else None

    if not isinstance(record, dict):
        print(
            json.dumps(
                {"seen": False, "status": "unseen", "record": None, "prior": prior}
            )
        )
        return 0

    action = record.get("action")
    if action in SUPPRESSING_ACTIONS:
        status = "handled"
    elif action == "resolved":
        # Fixed and closed out, so a fresh sighting is a REGRESSION, not a
        # duplicate. The record rides along so the caller can link the original.
        status = "regression"
    else:
        # Absent or unrecognized: we cannot confirm this was handled, so report.
        status = "unrecognized"

    print(
        json.dumps(
            {
                "seen": status == "handled",
                "status": status,
                "record": record,
                # The recorded prior filing, so the handled branch's mandated
                # same-defect comparison starts from the text instead of from a
                # retrieval step. Informational: it never changes the status.
                "prior": prior,
            }
        )
    )
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    if not FP_RE.match(args.fp):
        return _fail("invalid fp %r; expected ^fp-[0-9a-f]{7}$" % args.fp)
    if getattr(args, "defect_slug", None) and not SLUG_RE.match(args.defect_slug):
        return _fail(
            "invalid defect-slug %r; expected kebab-case ^[a-z0-9]+(-[a-z0-9]+)*$"
            % args.defect_slug
        )
    if args.action not in ACTIONS:
        return _fail(
            "invalid action %r; expected one of %s"
            % (args.action, ", ".join(ACTIONS))
        )

    cache = Path(args.cache).expanduser()
    cache.parent.mkdir(parents=True, exist_ok=True)

    # Merge: preserve every other fp; a corrupt/empty cache is treated as empty.
    data = _load_cache(cache)
    record = {
        "issue_url": args.issue_url,
        "action": args.action,
        "date": args.date,
    }
    # Additive, informational only: names WHICH defect this record is about,
    # so a REGRESSION title can be defect-accurate under a colliding fp. It
    # never keys suppression - that judgement stays with the handled branch's
    # mandated prior-text comparison (references/health-check.md).
    if getattr(args, "defect_slug", None):
        record["defect_slug"] = args.defect_slug
    data[args.fp] = record

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


def _read_plain_version(path: Path) -> str | None:
    """Read a plain-text VERSION file. Missing/unreadable/empty -> None."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return None
    stripped = text.strip()
    return stripped or None


def _read_json_version(path: Path, *keys) -> str | None:
    """Read a JSON file and walk `keys` (str=dict key, int=list index).

    Missing file, malformed JSON, a missing/typed-wrong key, or an empty/
    non-string resolved value all yield None so the caller falls through.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return None
    try:
        node = json.loads(text)
    except ValueError:
        return None
    for key in keys:
        if isinstance(key, int):
            if not isinstance(node, list) or not (-len(node) <= key < len(node)):
                return None
            node = node[key]
        else:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
    if not isinstance(node, str):
        return None
    stripped = node.strip()
    return stripped or None


def cmd_version(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).expanduser()
    skill_root = Path(args.skill_root).expanduser()

    # First-hit-wins probe ladder. Each rung that exists-but-is-malformed
    # returns None and falls through to the next.
    ladder = (
        (_read_plain_version(project_root / "_bmad" / "ucg" / "VERSION"), "_bmad/ucg/VERSION"),
        (_read_plain_version(skill_root / "VERSION"), f"{skill_root}/VERSION"),
        (
            _read_json_version(
                project_root / ".claude-plugin" / "marketplace.json",
                "plugins",
                0,
                "version",
            ),
            "marketplace.json",
        ),
        (_read_json_version(project_root / "package.json", "version"), "package.json"),
    )

    for version, source in ladder:
        if version is not None:
            print(json.dumps({"version": version, "source": source}))
            return 0

    print(json.dumps({"version": None, "source": "N/A"}))
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
    seen_parser.add_argument(
        "--queue-path",
        dest="queue_path",
        help="Local queue dir; when given, the output's `prior` carries the "
        "recorded filing (path, title, defect_slug) for this fp from the dir "
        "or its resolved/ subfolder, so the handled branch's same-defect "
        "comparison starts from text instead of a retrieval step.",
    )
    seen_parser.set_defaults(func=cmd_seen)

    rec_parser = sub.add_parser("record", help="Record a fingerprint outcome to the cache.")
    rec_parser.add_argument("--fp", required=True)
    rec_parser.add_argument("--cache", required=True)
    rec_parser.add_argument("--issue-url", required=True, dest="issue_url")
    rec_parser.add_argument("--action", required=True)
    rec_parser.add_argument("--date", required=True)
    rec_parser.add_argument(
        "--defect-slug",
        dest="defect_slug",
        help="Optional kebab-case name for WHICH defect this record is about "
        "(informational; never keys suppression). Makes a later REGRESSION "
        "title defect-accurate under a colliding fp.",
    )
    rec_parser.set_defaults(func=cmd_record)

    ver_parser = sub.add_parser("version", help="Resolve the module version off the probe ladder.")
    ver_parser.add_argument("--project-root", required=True, dest="project_root")
    ver_parser.add_argument("--skill-root", required=True, dest="skill_root")
    ver_parser.set_defaults(func=cmd_version)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
