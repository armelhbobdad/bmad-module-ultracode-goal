#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Deterministic fingerprint, seen-cache and queue plumbing for the ultracode-goal health check.

Plumbing ONLY. This script computes the dedup fingerprints of a health-check
finding (turning a section heading into its slug and a defect name into its
key) with the issue title and the machine-read top of the issue body, reads
the machine-local seen-cache into a verdict (asking GitHub for a recorded
issue's state through `gh`, bounded) with the line a regression's body opens
with, merge-writes a record under a lock, and writes a drafted body into the
local queue under a free name with the commands that submit it. It
makes NO submit/queue/route decision: that judgment lives in
references/health-check.md (the LLM), as do the severity, the section and the
defect name it is given.

The fingerprint is install-mode-invariant: the `step_file` component is ALWAYS
the source-repo form `skills/ultracode-goal/references/{stage}.md` regardless of
where the skill is installed, so the same defect dedups to the same key across a
dev checkout and an installed `_bmad/` tree.

    fp        = "fp-" + sha1("{severity}|ultracode-goal/{stage}|"
                             "skills/ultracode-goal/references/{stage}.md|"
                             "{section-slug}|{defect-key}")[:7]
    legacy_fp = the same hash without "|{defect-key}": the section fingerprint,
                which every defect of one severity in one section shares, and
                the fingerprint versions without the defect key filed under

Subcommands:
  fingerprint --severity S --stage T
              (--section-slug SLUG | --stdin) (--defect-key KEY | --stdin)
      Validate S against the 3 severities and T against the 7 stages (the six
      run stages and `health-check`, the health check's own). The
      section comes from --section-slug or from `section_heading` in the JSON
      object --stdin reads, never both; the defect from --defect-key or from
      that object's `defect_name`, never both. Without --stdin both flags are
      required (an argparse usage error, exit 2); with it, a pair given twice
      or not at all, a key other than those two and `short_description`, or
      a value that is not a non-empty string exits 1. The two flags stay for
      tests and old calls: --section-slug skips the check that the heading is
      one of the stage file's own, and without --stdin the flags print a null
      title, regression_title and body_header.
        section_heading: must equal, after its leading `#`s, the text of an
          ATX heading line of references/{T}.md beside this script (outside
          fenced code and the frontmatter). Its slug: drop the leading `#`s and
          a leading numbering token (`1b.`, `5a-ii.`, `4-headless.`),
          lower-case, turn each run of characters that are not ASCII letters or
          digits into `-`, and trim hyphens.
        defect_name: drop surrounding whitespace, backticks and quotes, keep
          its last path component (after `/` or `\\`), drop a trailing `:N`,
          `:N-M` or `:N:M` line suffix, a known file extension
          (KNOWN_EXTENSIONS) and then leading dashes and underscores; split at
          whitespace, `_`, `-`, `.` and each lower-case letter followed by an
          upper-case one; drop each character that is not an ASCII letter or
          digit; lower-case; keep the last four words, joined by `-`. A name
          that yields no word exits 1.
        short_description: optional; the issue title's description. It
          exits 1 when it holds a backtick, `$`, a double quote, a backslash,
          `!` or a character that is not printable (a tab, a line break, NUL,
          U+2028 and the like), since the title goes on a command line inside
          double quotes, or when it makes regression_title longer than 256
          characters (TITLE_MAX, GitHub's limit); surrounding whitespace is
          dropped.
      A given SLUG must be kebab-case (^[a-z0-9]+(-[a-z0-9]+)*$) and a given
      KEY one to four kebab-case words (^[a-z0-9]+(-[a-z0-9]+){0,3}$). Emit
      {"fp", "legacy_fp", "tuple", "section_slug", "defect_key", "title",
      "regression_title", "body_header"}, where `tuple` is the exact sha1
      input of `fp` and, with a short_description D (all three null
      without one):
        title:            [health-check][S][fp] ultracode-goal/T: D
        regression_title: [health-check][S][fp] ultracode-goal/T: REGRESSION: D
        body_header:      the machine-read top of the issue body, the
          `## Workflow`, `## Step File`, `## Section`, `## Severity`,
          `## Fingerprint` (`fp` alone on its line, then the line
          "Section fingerprint: `legacy_fp`") and `## Defect Key` sections,
          each value in backticks, ending in a newline.
      The JSON is printed in UTF-8, a non-ASCII character as itself.
  seen --fp FP --legacy-fp FP --cache PATH [--repo REPO]
      Validate both fingerprints, and REPO as [HOST/]OWNER/REPO (exit 1).
      Emit {"seen": B, "status": S, "record": R, "matched_on": M,
      "opening_line": L}. With --repo, a record with an empty or no
      issue_url, or that is not an object, names no repository and counts as
      without --repo; any other record whose issue_url is not a string under
      https://github.com/OWNER/REPO/ (https://HOST/OWNER/REPO/ for a REPO that
      names a host), compared in any letter case, counts as no record, under
      either fingerprint: another repository's issue, a URL that is not
      https:// or one that is not a string alike. The record under --fp
      decides; only when the cache has no --fp key does the record under
      --legacy-fp decide (M is "fp", "legacy_fp", or null when neither is
      there). On the record found, the first branch that matches gives the
      status:
        1. no record under either fingerprint: unseen
        2. action `resolved`: regression
        3. action created, reacted or commented with an issue_url: the
           issue's own state decides, read with
           `gh issue view <issue_url> --json state,stateReason`, stopped after
           10 seconds (GH_TIMEOUT_SEC) with every process it started. CLOSED
           with stateReason COMPLETED, or MERGED (a resolving pull request), is
           regression; every other answer (OPEN, a NOT_PLANNED close) and every
           failure (no gh, the time limit, a non-zero exit, output that is not
           that JSON) is handled. gh runs only for an issue_url that starts
           with https:// and holds no whitespace (any other value is handled
           without a call), is never one found in the current folder, and
           never runs through a shell.
        4. one of those three actions with no issue_url: handled
        5. no action, any other action (an old `queued` included), or a
           record that is not an object: unrecognized
      A record found only under --legacy-fp may be another defect's, so
      handled becomes unseen (a legacy record never suppresses) and
      regression becomes possible-regression; unrecognized stays.
      `seen` is the SUPPRESSION verdict, true for handled alone: every
      uncertain verdict reports. Missing/empty/corrupt cache -> unseen.
      L is the line that opens the issue body, null for unseen, handled and
      unrecognized; U is the record's issue_url when it starts with https://
      and holds no whitespace, D its date when that has the YYYY-MM-DD shape
      (else "on an unrecorded date"), and P, after a possible-regression,
      ": that report's fingerprint has no defect key, so it may be another
      defect in this section". From a `resolved` record, whose date is the
      fix's:
        regression, with U:           Regression of U (resolved D).
        regression, without:          Regression of a previously resolved
                                      local finding (resolved D).
        possible-regression, with U:  Possibly a regression of U (resolved D)P.
        possible-regression, without: Possibly a regression of a previously
                                      resolved local finding in this section
                                      (resolved D).
      From branch 3, whose record dates the report, not the fix:
        a completed close:            Regression of U, closed as completed
                                      since its report on D. (Possibly a
                                      regression ... D P. after a legacy record)
        a merge:                      the same with "merged" for "closed as
                                      completed".
  record --fp FP --cache PATH --issue-url URL --action A --date YYYY-MM-DD
         [--regression]
      Validate FP; A is created, reacted or commented with an https:// URL
      holding no whitespace, or resolved with such a URL or an empty one; the
      date is a real YYYY-MM-DD date. Set the --fp key alone to
      {"issue_url", "action", "date"} and keep every other key. A
      `defect_slug` the replaced record carries is carried over. A `resolved`
      record is never downgraded: without --regression, any other action
      leaves it as it is and emits "written": false (exit 0). The read, merge
      and write hold an OS lock on <cache>.lock (fcntl.flock, or
      msvcrt.locking on Windows), waited on for up to 10 seconds
      (LOCK_WAIT_SEC); the lock file is never deleted. The new file is
      written beside the cache, synced to disk and renamed over it. A cache
      that exists and is not a JSON object is first renamed to
      <cache>.corrupt-<UTC YYYYMMDDTHHMMSSZ> (then -2, -3 in the same second),
      so its records can be repaired by hand; when that rename fails, nothing
      is written. Emit {"written": B, "fp": FP, "record": <what the cache now
      holds under FP>, "set_aside": <the renamed corrupt cache> | null}.
  version --project-root PATH
      The version of the UltraCode Goal this script belongs to, never the
      user's project's: emit {"version": V, "source": S}, or {"version": null,
      "source": "N/A"} when no rung gives one (exit 0). UCG's own root is the
      folder three levels above this script's (UCG_ROOT: a checkout's or a
      plugin's root), and there is none when the script sits fewer than four
      folders deep. The first rung that gives a non-empty version wins; a file
      that is missing, unreadable or malformed, or that names another package,
      falls through to the next:
        1. UCG_ROOT/.claude-plugin/marketplace.json: the version of its
           `plugins` entry named bmad-module-ultracode-goal (PACKAGE_NAME)
                                       -> ".claude-plugin/marketplace.json"
        2. UCG_ROOT/package.json, when its name is PACKAGE_NAME: its version
                                       -> "package.json"
        3. <project-root>/_bmad/ucg/VERSION, which only UCG's CLI installer
           writes, for the copy it installs under .claude/skills/, which has
           no root of its own (plain text)
                                       -> "_bmad/ucg/VERSION"
      UCG's root comes first, so a stale _bmad/ucg/VERSION never masks it.
  queue --queue-dir DIR --body-file F --title TITLE --repo REPO
      Read F (a missing or unreadable F exits 1 and creates nothing). F
      opens with the body_header `fingerprint` prints (after a UTF-8 BOM and
      at most one opening line and a blank line, its line endings LF or
      CRLF), from which the stage T, the severity S and the fingerprint FP
      are read. Each of these exits 1 and creates nothing: F opening with no
      such header; a TITLE that does not start with
      `[health-check][S][FP] ultracode-goal/T: `
      (the title `fingerprint` printed for another finding), is longer than
      TITLE_MAX or holds a character `fingerprint` refuses in a description;
      a REPO that is not [HOST/]OWNER/REPO. Create DIR when absent and write
      F's bytes, unchanged and with no frontmatter, to
      DIR/hc-ultracode-goal-{T}-{UTC YYYYMMDD-HHmmss}.md, opened with
      O_CREAT|O_EXCL so no file is ever overwritten: a taken name gets -2, -3
      and so on before `.md`. Emit {"path": P, "commands": [L, C, B]}, P
      being the absolute path written and L, C and B the commands that submit
      it: the label create and the create, run in that order (a failed L, the
      label there already or no push access, is no error), and B, the create
      without labels, for a reporter without push access to run alone:
        L: gh label create --repo REPO FP --color ededed
             --description 'Health-check fingerprint dedup key'
        C: gh issue create --repo REPO --title TITLE
             --label health-check,workflow-improvement,S,FP --body-file P
        B: gh issue create --repo REPO --title TITLE --body-file P
      each on one line, every argument quoted for a POSIX shell
      (shlex.quote), so a space or a quote in TITLE or P reaches gh as
      written, and `--repo` right after the subcommand, so an allow rule
      scoped to the repository matches. The JSON is printed in UTF-8, a
      non-ASCII character as itself.

Output: JSON to stdout. Errors are JSON to stdout with exit code 1 (operational
failure, a value that breaks its rule, or a record that could not take the lock,
set a corrupt cache aside or write); argparse usage errors exit 2. A successful
payload exits 0.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

SEVERITIES = ("bug", "friction", "gap")
STAGES = (
    "ingest-and-scope",
    "preflight",
    "define-done",
    "execute",
    "gate",
    "finalize",
    # The health check's own stage reference, for a defect in its own
    # instructions (references/health-check.md routes it to the local queue only).
    "health-check",
)
ACTIONS = ("created", "reacted", "commented", "resolved")

# Which recorded actions SUPPRESS a later sighting of the same fingerprint.
# Deliberately a literal tuple and NOT `ACTIONS` minus `resolved`: a disposition
# added later then defaults to NOT suppressing until it is opted in here, and a
# missing or unrecognized action (a hand-edited cache, an old `queued` record,
# or one written by a newer module) does not suppress either. That is the
# fail-closed direction for a health check: a duplicate report is closed by the
# dedup Action, while a silenced regression is caught by nothing. When in
# doubt, report.
SUPPRESSING_ACTIONS = ("created", "reacted", "commented")
RESOLVED = "resolved"

# Each rule is matched with fullmatch, so a value ending in a newline fails it.
SLUG_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
DEFECT_KEY_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+){0,3}")
FP_RE = re.compile(r"fp-[0-9a-f]{7}")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
URL_PREFIX = "https://"

# The stage references a section_heading is looked up in: the skill's own
# references/ folder, beside scripts/, wherever the skill is installed.
REFERENCES_DIR = Path(__file__).resolve().parent.parent / "references"
# The root of the UltraCode Goal this script belongs to, a checkout's or a plugin's: the folder above skills/, three
# levels above this script's. None when the script sits fewer than four folders deep. `version` reads it at call time,
# so a test can point it elsewhere.
_PARENTS = Path(__file__).resolve().parents
UCG_ROOT = _PARENTS[3] if len(_PARENTS) > 3 else None
# The name UCG's package.json and its marketplace's plugin entry carry: a file at UCG_ROOT that names another package
# (the user's project, when UCG_ROOT is not UCG's) gives no version.
PACKAGE_NAME = "bmad-module-ultracode-goal"
# An ATX heading line: up to three spaces, one to six `#`, then its text.
_HEADING_LINE_RE = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*")
# The optional closing sequence of an ATX heading (`## Title ##`).
_HEADING_CLOSE_RE = re.compile(r"(?:^|[ \t]+)#+$")
# A fence line opens or closes a fenced code block, whose `#` lines are no headings.
_FENCE_RE = re.compile(r" {0,3}(`{3,}|~{3,})")
# A leading numbering token: `1.`, `1b.`, `0.5.`, `5a-ii.`, `4-headless.`.
_NUMBERING_RE = re.compile(r"[0-9][0-9A-Za-z]*(?:[.-][0-9A-Za-z]+)*\.\s+")
_NOT_SLUG_RE = re.compile(r"[^a-z0-9]+")

# The file extensions a defect name drops: `gate_eval.py` names the script `gate-eval`.
KNOWN_EXTENSIONS = (
    ".py", ".md", ".json", ".yaml", ".yml", ".toml", ".js", ".cjs", ".mjs", ".ts", ".sh", ".csv", ".txt",
)
_PATH_SEP_RE = re.compile(r"[/\\]")
_LINE_SUFFIX_RE = re.compile(r":[0-9]+(?:[-:][0-9]+)?$")
# What a name copied from Markdown or a log may be wrapped in.
_NAME_WRAPPERS = "`'\""
_NAME_SPLIT_RE = re.compile(r"[\s_.-]+")
_CASE_BOUNDARY_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_NOT_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")
DEFECT_KEY_WORDS = 4
STDIN_KEYS = ("section_heading", "defect_name", "short_description")
# What a title may not hold besides a character that is not printable (a tab, a line break, NUL, U+2028): it goes
# on a command line inside double quotes, where each of these is special (`!` to an interactive shell's history).
TITLE_UNSAFE = "`$\"\\!"
# GitHub refuses an issue title longer than this many characters.
TITLE_MAX = 256
# The record date an opening line names when the record holds no YYYY-MM-DD date.
UNRECORDED_DATE = "on an unrecorded date"

QUEUE_STAMP_FORMAT = "%Y%m%d-%H%M%S"
# What every health-check issue is filed with besides its severity and fingerprint labels, and the fp-* label's
# look as the health check creates it (the dedup Action creates it the same way).
ISSUE_LABELS = ("health-check", "workflow-improvement")
FP_LABEL_COLOR = "ededed"
FP_LABEL_DESCRIPTION = "Health-check fingerprint dedup key"
# The start of a draft: at most one opening line (a regression's) and a blank line, then the body_header
# `fingerprint` prints, its line endings LF or CRLF.
_DRAFT_HEADER_RE = re.compile(
    r"(?:[^\r\n]+\r?\n\r?\n)?"
    r"## Workflow\r?\n`ultracode-goal/(?P<stage>" + "|".join(STAGES) + r")`\r?\n\r?\n"
    r"## Step File\r?\n`skills/ultracode-goal/references/(?P=stage)\.md`\r?\n\r?\n"
    r"## Section\r?\n`[^`\r\n]+`\r?\n\r?\n"
    r"## Severity\r?\n`(?P<severity>" + "|".join(SEVERITIES) + r")`\r?\n\r?\n"
    r"## Fingerprint\r?\n`(?P<fp>fp-[0-9a-f]{7})`\r?\n\r?\n"
    r"Section fingerprint: `fp-[0-9a-f]{7}`\r?\n\r?\n"
    r"## Defect Key\r?\n`[^`\r\n]+`(?:\r?\n|\Z)"
)
# A repository as gh takes it: [HOST/]OWNER/REPO.
REPO_RE = re.compile(r"(?:[A-Za-z0-9][A-Za-z0-9.-]*/)?[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+")

GH_TIMEOUT_SEC = 10.0
KILL_WAIT_SEC = 2.0  # each wait once the time limit stops gh: SIGTERM or taskkill, then the child
LOCK_WAIT_SEC = 10.0
_LOCK_POLL_MIN_SEC = 0.01
_LOCK_POLL_MAX_SEC = 0.2
CORRUPT_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
# Windows refuses to rename over a file another process has open (a `seen`
# reading the cache, a virus scanner); the rename is retried for this long.
_IS_WINDOWS = os.name == "nt"
_REPLACE_WAIT_SECONDS = 5.0
_REPLACE_POLL_SECONDS = 0.02


class _WriteError(Exception):
    """record could not read the cache, set a corrupt one aside or write it."""


class _LockBusy(Exception):
    """Another record call held <cache>.lock for the whole wait."""


def _fail(message: str) -> int:
    print(json.dumps({"error": message}))
    return 1


def _repo_error(repo: str) -> str | None:
    """The rule a --repo value breaks, or None: gh takes [HOST/]OWNER/REPO."""
    if REPO_RE.fullmatch(repo):
        return None
    return "invalid repo %r; expected [HOST/]OWNER/REPO" % repo


def _sha7(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:7]


def _compute_fp(severity: str, stage: str, slug: str, defect_key: str) -> tuple[str, str, str]:
    """Return (fp, legacy_fp, tuple_string). The tuple string is fp's exact sha1 input."""
    step_file = f"skills/ultracode-goal/references/{stage}.md"
    legacy = f"{severity}|ultracode-goal/{stage}|{step_file}|{slug}"
    keyed = f"{legacy}|{defect_key}"
    return f"fp-{_sha7(keyed)}", f"fp-{_sha7(legacy)}", keyed


def _heading_text(text: str) -> str:
    """A heading's text: no leading `#`s, no ATX closing sequence, single spaces."""
    text = text.strip().lstrip("#")
    text = _HEADING_CLOSE_RE.sub("", text.strip())
    return " ".join(text.split())


def _stage_headings(stage_file: Path) -> list[str]:
    """The text of every ATX heading line of stage_file, outside its frontmatter and fenced code.

    Raises OSError when the file cannot be read.
    """
    lines = stage_file.read_text(encoding="utf-8-sig").splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    headings = []
    fence = None
    for line in lines[start:]:
        run = _FENCE_RE.match(line)
        if fence is not None:
            # Only a run of the same character, at least as long and alone on its line, closes it.
            closes = run and run.group(1)[0] == fence[0] and len(run.group(1)) >= len(fence)
            if closes and not line.strip().strip(fence[0]):
                fence = None
            continue
        if run:
            fence = run.group(1)
        elif _HEADING_LINE_RE.fullmatch(line):
            headings.append(_heading_text(line))
    return headings


def section_slug(heading: str) -> str:
    """The slug rule: no leading `#`s or numbering token, lower-case, one `-` per run of other characters."""
    text = _heading_text(heading)
    numbering = _NUMBERING_RE.match(text)
    if numbering:
        text = text[numbering.end():]
    return _NOT_SLUG_RE.sub("-", text.lower()).strip("-")


def defect_key(name: str) -> str:
    """The defect-key rule; an empty string when the name yields no word."""
    text = name.strip().strip(_NAME_WRAPPERS).strip()  # `gate_eval.py`, in backticks or quotes
    text = _PATH_SEP_RE.split(text)[-1]  # `scripts/gate_eval.py` names `gate_eval.py`
    text = _LINE_SUFFIX_RE.sub("", text)  # `gate_eval.py:42`, `:42-50` and `:42:7` name it too
    for ext in KNOWN_EXTENSIONS:
        if text.lower().endswith(ext) and len(text) > len(ext):
            text = text[: -len(ext)]
            break
    text = text.lstrip("-_")
    words = []
    for part in _NAME_SPLIT_RE.split(text):
        for piece in _CASE_BOUNDARY_RE.split(part):
            word = _NOT_ALNUM_RE.sub("", piece).lower()
            if word:
                words.append(word)
    return "-".join(words[-DEFECT_KEY_WORDS:])


def _title_unsafe(text: str) -> bool:
    """True when text holds a character a title on a command line may not: TITLE_UNSAFE, or one not printable."""
    return any(ch in TITLE_UNSAFE or not ch.isprintable() for ch in text)


def _read_stdin_names() -> tuple[dict | None, str | None]:
    """The JSON object --stdin reads, or the rule it breaks.

    Read as UTF-8 bytes, so a heading's non-ASCII character survives whatever
    the locale is.
    """
    raw = getattr(sys.stdin, "buffer", None)
    try:
        text = raw.read().decode("utf-8-sig") if raw is not None else sys.stdin.read()
        data = json.loads(text)
    except (OSError, ValueError, RecursionError):  # UnicodeDecodeError is a ValueError
        return None, "--stdin did not read a JSON object"
    if not isinstance(data, dict):
        return None, "--stdin did not read a JSON object"
    unknown = sorted(set(data) - set(STDIN_KEYS))
    if unknown:
        return None, "unknown --stdin key(s) %s; expected only %s and %s" % (
            ", ".join(map(repr, unknown)),
            ", ".join(STDIN_KEYS[:-1]),
            STDIN_KEYS[-1],
        )
    for key, value in data.items():
        if not isinstance(value, str) or not value.strip():
            return None, "--stdin %s must be a non-empty string" % key
    if _title_unsafe(data.get("short_description", "")):
        return None, (
            "--stdin short_description %r holds a backtick, `$`, double quote, backslash, `!` or a character that is "
            "not printable (a tab or a line break included); the title goes on a command line, so it may hold none"
            % data["short_description"]
        )
    return data, None


def _one_of(flag: str, flag_value: str | None, key: str, names: dict) -> str | None:
    """The rule a section or defect pair breaks: given twice, or not at all."""
    if flag_value is not None and key in names:
        return "give %s or a --stdin %s, not both" % (flag, key)
    if flag_value is None and key not in names:
        return "give %s or a --stdin %s" % (flag, key)
    return None


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

    names: dict = {}
    if args.stdin:
        names, problem = _read_stdin_names()
        if problem:
            return _fail(problem)
        problem = _one_of("--section-slug", args.section_slug, "section_heading", names) or _one_of(
            "--defect-key", args.defect_key, "defect_name", names
        )
        if problem:
            return _fail(problem)

    slug = args.section_slug
    if "section_heading" in names:
        heading = names["section_heading"]
        stage_file = REFERENCES_DIR / f"{args.stage}.md"
        try:
            headings = _stage_headings(stage_file)
        except (OSError, UnicodeDecodeError) as exc:
            return _fail("could not read %s: %s" % (stage_file, exc))
        if _heading_text(heading) not in headings:
            return _fail(
                "section_heading %r is no heading of references/%s.md; copy a heading line of that file"
                % (heading, args.stage)
            )
        slug = section_slug(heading)
        if not slug:
            return _fail("section_heading %r yields no slug" % heading)
    elif not SLUG_RE.fullmatch(slug):
        return _fail(
            "invalid section-slug %r; expected kebab-case ^[a-z0-9]+(-[a-z0-9]+)*$" % slug
        )

    key = args.defect_key
    if "defect_name" in names:
        key = defect_key(names["defect_name"])
        if not key:
            return _fail("defect_name %r yields no word" % names["defect_name"])
    elif not DEFECT_KEY_RE.fullmatch(key):
        return _fail(
            "invalid defect-key %r; expected one to four kebab-case words "
            "^[a-z0-9]+(-[a-z0-9]+){0,3}$" % key
        )

    fp, legacy_fp, tuple_str = _compute_fp(args.severity, args.stage, slug, key)
    title = regression_title = header = None
    if "short_description" in names:
        description = names["short_description"].strip()
        prefix = f"[health-check][{args.severity}][{fp}] ultracode-goal/{args.stage}: "
        title = prefix + description
        regression_title = prefix + "REGRESSION: " + description
        if len(regression_title) > TITLE_MAX:
            return _fail(
                "short_description makes the regression title %d characters long; GitHub takes at most %d, so "
                "shorten it by %d" % (len(regression_title), TITLE_MAX, len(regression_title) - TITLE_MAX)
            )
        header = body_header(args.severity, args.stage, slug, key, fp, legacy_fp)
    _print_utf8(
        {
            "fp": fp,
            "legacy_fp": legacy_fp,
            "tuple": tuple_str,
            "section_slug": slug,
            "defect_key": key,
            "title": title,
            "regression_title": regression_title,
            "body_header": header,
        }
    )
    return 0


def _print_utf8(payload: dict) -> None:
    """Print payload as JSON in UTF-8 whatever the locale, non-ASCII as itself: the title is used as printed."""
    text = json.dumps(payload, ensure_ascii=False) + "\n"
    out = getattr(sys.stdout, "buffer", None)
    if out is None:
        sys.stdout.write(text)
        return
    sys.stdout.flush()
    out.write(text.encode("utf-8"))
    out.flush()


def body_header(severity: str, stage: str, slug: str, key: str, fp: str, legacy_fp: str) -> str:
    """The machine-read top of an issue body: the sections the dedup Action and a maintainer's triage read."""
    return (
        f"## Workflow\n`ultracode-goal/{stage}`\n\n"
        f"## Step File\n`skills/ultracode-goal/references/{stage}.md`\n\n"
        f"## Section\n`{slug}`\n\n"
        f"## Severity\n`{severity}`\n\n"
        f"## Fingerprint\n`{fp}`\n\n"
        # At the start of a line of its own: the dedup Action's SECTION_RE reads it there.
        f"Section fingerprint: `{legacy_fp}`\n\n"
        f"## Defect Key\n`{key}`\n"
    )


# --- the cache ---------------------------------------------------------------


def _parse(raw: bytes) -> dict | None:
    """The cache object in raw bytes: {} for an empty file, None when it is not a JSON object."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):  # RecursionError: nested past the parser's depth
        return None
    return data if isinstance(data, dict) else None


def _load_cache(cache: Path) -> dict:
    """Read the seen-cache as a dict. Missing/empty/unreadable/corrupt -> {} (never raises)."""
    try:
        raw = cache.read_bytes()
    except OSError:
        return {}
    return _parse(raw) or {}


# --- the issue-state check -----------------------------------------------------


def _resolve_outside_cwd(command: str) -> str | None:
    """shutil.which, refusing a resolution into the current folder.

    shutil.which on Windows searches the current folder ahead of PATH, and a
    `.` or empty PATH entry does the same on POSIX. The current folder is the
    user's project, which this module does not control, so a `gh` planted
    there reads as no gh. Returns an absolute path, or None.
    """
    resolved = shutil.which(command)
    if resolved is None:
        return None
    resolved = os.path.abspath(resolved)
    here = os.path.normcase(os.path.realpath(os.getcwd()))
    if os.path.normcase(os.path.realpath(os.path.dirname(resolved))) == here:
        return None
    return resolved


def _child_env() -> dict:
    """os.environ with gh's prompts and update notice turned off."""
    env = dict(os.environ)
    env["GH_PROMPT_DISABLED"] = "1"
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    return env


def _stop(proc: subprocess.Popen, windows: bool = _IS_WINDOWS) -> None:
    """Stop proc and everything it started once the time limit runs out.

    POSIX sends SIGTERM to its process group, then SIGKILL to whatever is
    left; Windows runs taskkill /F /T on its tree.
    """
    try:
        if windows:
            taskkill = _resolve_outside_cwd("taskkill")
            if taskkill:
                try:
                    subprocess.run(
                        [taskkill, "/F", "/T", "/PID", str(proc.pid)],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        timeout=KILL_WAIT_SEC,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass  # proc itself is still killed below
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=KILL_WAIT_SEC)
            except subprocess.TimeoutExpired:
                pass
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    try:
        proc.wait(timeout=KILL_WAIT_SEC)
    except subprocess.TimeoutExpired:
        pass


def _run(argv: list[str], timeout: float) -> tuple[int | None, bytes, bytes]:
    """Run argv with no stdin and no shell; (returncode, stdout, stderr).

    returncode is None when the time limit stopped the call. The call gets a
    process group (a POSIX session) of its own, so _stop reaches all it
    started, and its output goes to temporary files, not pipes, so a child it
    left behind cannot hold a read open. Raises OSError or ValueError when
    argv cannot start.
    """
    kwargs: dict = {}
    if _IS_WINDOWS:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=err_f,
            env=_child_env(),
            **kwargs,
        )
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop(proc)
            returncode = None
        out_f.seek(0)
        err_f.seek(0)
        return returncode, out_f.read(), err_f.read()


def gh_issue_state(issue_url: str, timeout: float | None = None) -> dict | None:
    """`gh issue view <issue_url> --json state,stateReason`: its JSON object, or None on any failure."""
    exe = _resolve_outside_cwd("gh")
    if exe is None:
        return None
    limit = GH_TIMEOUT_SEC if timeout is None else timeout
    try:
        returncode, out, _err = _run(
            [exe, "issue", "view", issue_url, "--json", "state,stateReason"], limit
        )
    except (OSError, ValueError):
        return None
    if returncode != 0:
        return None
    try:
        answer = json.loads(out.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    if not isinstance(answer, dict) or not isinstance(answer.get("state"), str):
        return None
    return answer


def _gh_url(value) -> bool:
    """An issue_url gh may be given: https://, no whitespace (so never a flag)."""
    return (
        isinstance(value, str)
        and value.startswith(URL_PREFIX)
        and not any(ch.isspace() for ch in value)
    )


def _issue_verdict(issue_url) -> tuple[str, str | None]:
    """Branch 3: regression for a completed close ("closed") or a merge ("merged"), handled for anything else."""
    if not _gh_url(issue_url):
        return "handled", None
    answer = gh_issue_state(issue_url)
    if answer is None:
        return "handled", None
    state = answer["state"].upper()
    reason = answer.get("stateReason")
    reason = reason.upper() if isinstance(reason, str) else ""
    if state == "CLOSED" and reason == "COMPLETED":
        return "regression", "closed"
    if state == "MERGED":
        return "regression", "merged"
    return "handled", None


def _verdict(record) -> tuple[str, str | None]:
    """Branches 2 to 5 on a record that exists: the status, and for a regression how the fix is known."""
    if not isinstance(record, dict):
        return "unrecognized", None
    action = record.get("action")
    if action == RESOLVED:
        # Fixed and closed out, so a fresh sighting is a REGRESSION, not a
        # duplicate. The record rides along so the caller can link the original.
        return "regression", RESOLVED
    if action in SUPPRESSING_ACTIONS:
        if record.get("issue_url") in (None, ""):
            return "handled", None
        return _issue_verdict(record.get("issue_url"))
    # Absent or unrecognized: we cannot confirm this was handled, so report.
    return "unrecognized", None


def _issue_prefix(repo: str) -> str:
    """The start of every issue URL of repo: github.com's, or the host's when repo names one."""
    return f"{URL_PREFIX}{repo}/" if repo.count("/") == 2 else f"{URL_PREFIX}github.com/{repo}/"


def _in_repo(record, repo: str | None) -> bool:
    """Whether record may decide a verdict for repo.

    A record that is not an object, or whose issue_url is empty or missing, names no repository, so it decides as it
    always did. Any other issue_url must be a string under repo's issue prefix: another repository's record, or one
    whose URL is not https:// or not a string, neither suppresses this one's finding nor gives its body a line
    linking that issue.
    """
    if repo is None or not isinstance(record, dict):
        return True
    url = record.get("issue_url")
    if url is None or url == "":
        return True
    return isinstance(url, str) and url.lower().startswith(_issue_prefix(repo).lower())


def cmd_seen(args: argparse.Namespace) -> int:
    if not FP_RE.fullmatch(args.fp):
        return _fail("invalid fp %r; expected ^fp-[0-9a-f]{7}$" % args.fp)
    if not FP_RE.fullmatch(args.legacy_fp):
        return _fail("invalid legacy-fp %r; expected ^fp-[0-9a-f]{7}$" % args.legacy_fp)
    if args.repo is not None:
        problem = _repo_error(args.repo)
        if problem:
            return _fail(problem)

    loaded = _load_cache(Path(args.cache).expanduser())
    # A record of another repository's issue counts as no record, before anything reads it (gh included).
    data = {
        key: loaded[key] for key in (args.fp, args.legacy_fp) if key in loaded and _in_repo(loaded[key], args.repo)
    }
    fixed = None
    if args.fp in data:
        record = data[args.fp]
        status, fixed = _verdict(record)
        matched_on = "fp"
    elif args.legacy_fp in data:
        record = data[args.legacy_fp]
        # A section fingerprint may be another defect's: it never suppresses,
        # and a fix it records is only possibly this defect's.
        status, fixed = _verdict(record)
        status = {"handled": "unseen", "regression": "possible-regression"}.get(status, status)
        matched_on = "legacy_fp"
    else:
        record = None
        status = "unseen"
        matched_on = None

    print(
        json.dumps(
            {
                "seen": status == "handled",
                "status": status,
                "record": record,
                "matched_on": matched_on,
                "opening_line": opening_line(status, record, fixed),
            }
        )
    )
    return 0


def opening_line(status: str, record, fixed: str | None) -> str | None:
    """The line a regression's or a possible regression's issue body opens with; None for any other verdict.

    `fixed` is how the fix is known: RESOLVED (the record says so, and its date is the fix's), or "closed" or
    "merged" (the recorded issue's own state, and the record's date is only the day this machine reported it).
    """
    if status not in ("regression", "possible-regression") or not isinstance(record, dict):
        return None
    url = record.get("issue_url")
    day = record.get("date")
    dated = isinstance(day, str) and DATE_RE.fullmatch(day)
    possible = status == "possible-regression"
    lead = "Possibly a regression" if possible else "Regression"
    if fixed in ("closed", "merged"):
        how = "closed as completed" if fixed == "closed" else "merged"
        line = f"{lead} of {url}, {how} since its report " + (f"on {day}" if dated else UNRECORDED_DATE)
    else:
        resolved = f"(resolved {day if dated else UNRECORDED_DATE})"
        if not _gh_url(url):
            where = " in this section" if possible else ""
            return f"{lead} of a previously resolved local finding{where} {resolved}."
        line = f"{lead} of {url} {resolved}"
    if possible:
        return line + ": that report's fingerprint has no defect key, so it may be another defect in this section."
    return line + "."


# --- record --------------------------------------------------------------------


def _record_error(fp: str, action: str, issue_url: str, day: str) -> str | None:
    """The rule the record arguments break, or None."""
    if not FP_RE.fullmatch(fp):
        return "invalid fp %r; expected ^fp-[0-9a-f]{7}$" % fp
    if action not in ACTIONS:
        return "invalid action %r; expected one of %s" % (action, ", ".join(ACTIONS))
    if action == RESOLVED:
        if issue_url != "" and not _gh_url(issue_url):
            return (
                "invalid issue-url %r; a resolved record takes an empty URL or one "
                "that starts with %s and holds no whitespace" % (issue_url, URL_PREFIX)
            )
    elif not _gh_url(issue_url):
        return "invalid issue-url %r; expected one that starts with %s and holds no whitespace" % (
            issue_url,
            URL_PREFIX,
        )
    try:
        if not DATE_RE.fullmatch(day):
            raise ValueError
        date.fromisoformat(day)
    except ValueError:
        return "invalid date %r; expected a real date as YYYY-MM-DD" % day
    return None


def _lock_busy(exc: OSError) -> bool:
    return exc.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK, errno.EDEADLK)


def _try_lock(fd: int) -> None:
    """Take an exclusive lock on fd without waiting; OSError when it is held."""
    if _IS_WINDOWS:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fd: int) -> None:
    try:
        if _IS_WINDOWS:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass  # closing the file releases it too


def _acquire(lock: Path, wait: float) -> int:
    """Open <cache>.lock and lock it, waiting up to `wait` seconds with backoff.

    The OS drops the lock when the holder dies, so a lock left by a killed
    call never needs clearing, and the file is never deleted, which avoids
    races on unlink. Raises _LockBusy at the end of the wait, OSError when the
    file cannot be opened or locked.
    """
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    deadline = time.monotonic() + wait
    delay = _LOCK_POLL_MIN_SEC
    while True:
        try:
            _try_lock(fd)
            return fd
        except OSError as exc:
            left = deadline - time.monotonic()
            if not _lock_busy(exc) or left <= 0:
                os.close(fd)
                if _lock_busy(exc):
                    raise _LockBusy() from None
                raise
        time.sleep(min(delay, left))
        delay = min(delay * 2, _LOCK_POLL_MAX_SEC)


def _release(fd: int) -> None:
    _unlock(fd)
    try:
        os.close(fd)
    except OSError:
        pass


def _replace(src: Path | str, dst: Path | str) -> None:
    """os.replace, retried on Windows while another process has dst open."""
    deadline = time.monotonic() + _REPLACE_WAIT_SECONDS
    while True:
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not _IS_WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(_REPLACE_POLL_SECONDS)


def _atomic_write(cache: Path, content: str) -> None:
    """Temp file beside the cache, synced to disk, then renamed over it."""
    fd, tmp_name = tempfile.mkstemp(dir=str(cache.parent), prefix=".hc-seen-", suffix=".tmp")
    try:
        try:
            data = memoryview(content.encode("utf-8"))
            while data:
                data = data[os.write(fd, data):]  # os.write may write fewer bytes than asked
            os.fsync(fd)
        finally:
            os.close(fd)
        _replace(tmp_name, cache)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _corrupt_stamp() -> str:
    return datetime.now(timezone.utc).strftime(CORRUPT_STAMP_FORMAT)


def _set_aside(cache: Path) -> Path:
    """Rename a corrupt cache to <cache>.corrupt-<UTC stamp>, never over an earlier one."""
    stamp = _corrupt_stamp()
    aside = cache.with_name(f"{cache.name}.corrupt-{stamp}")
    n = 2
    while os.path.lexists(aside):
        aside = cache.with_name(f"{cache.name}.corrupt-{stamp}-{n}")
        n += 1
    _replace(cache, aside)
    return aside


def _merge(cache: Path, fp: str, new: dict, regression: bool) -> dict:
    """The read, merge and write; runs while the caller holds the lock."""
    set_aside = None
    try:
        raw = cache.read_bytes()
    except FileNotFoundError:
        data = {}
    except OSError as exc:
        raise _WriteError("could not read cache %s: %s" % (cache, exc)) from None
    else:
        data = _parse(raw)
        if data is None:
            try:
                set_aside = _set_aside(cache)
            except OSError as exc:
                raise _WriteError(
                    "could not set aside cache %s, which is not a JSON object: %s; "
                    "nothing was written" % (cache, exc)
                ) from None
            data = {}

    existing = data.get(fp)
    if isinstance(existing, dict):
        if existing.get("action") == RESOLVED and new["action"] != RESOLVED and not regression:
            # Never downgrade a fix: only an issue that tracks the recurrence
            # (--regression) replaces it, so suppression never comes back alone.
            return {"written": False, "fp": fp, "record": existing, "set_aside": None}
        if "defect_slug" in existing:
            # Written by an earlier version of this module; it rides along.
            new = {**new, "defect_slug": existing["defect_slug"]}
    data[fp] = new

    try:
        _atomic_write(cache, json.dumps(data, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        where = " (the corrupt cache was renamed to %s)" % set_aside if set_aside else ""
        raise _WriteError("could not write cache %s: %s%s" % (cache, exc, where)) from None
    return {
        "written": True,
        "fp": fp,
        "record": new,
        "set_aside": str(set_aside) if set_aside else None,
    }


def cmd_record(args: argparse.Namespace) -> int:
    problem = _record_error(args.fp, args.action, args.issue_url, args.date)
    if problem:
        return _fail(problem)

    cache = Path(args.cache).expanduser()
    new = {"issue_url": args.issue_url, "action": args.action, "date": args.date}
    lock = cache.with_name(cache.name + ".lock")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail("could not create %s: %s" % (cache.parent, exc))
    try:
        fd = _acquire(lock, LOCK_WAIT_SEC)
    except _LockBusy:
        return _fail(
            "%s stayed locked by another record call for %s seconds; nothing was written"
            % (lock, LOCK_WAIT_SEC)
        )
    except OSError as exc:
        return _fail("could not take %s: %s" % (lock, exc))
    try:
        result = _merge(cache, args.fp, new, args.regression)
    except _WriteError as exc:
        return _fail(str(exc))
    finally:
        _release(fd)

    print(json.dumps(result))
    return 0


def _read_plain_version(path: Path) -> str | None:
    """Read a plain-text VERSION file, a UTF-8 byte order mark dropped. Missing/unreadable/empty -> None."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except (FileNotFoundError, OSError):
        return None
    stripped = text.strip()
    return stripped or None


def _read_json(path: Path):
    """The JSON value in path; None when it is missing, unreadable or malformed."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except (FileNotFoundError, OSError):
        return None
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        return None


def _json_version(node) -> str | None:
    """The "version" of a JSON object, stripped; None when node is no object or that is no non-empty string."""
    version = node.get("version") if isinstance(node, dict) else None
    if not isinstance(version, str):
        return None
    return version.strip() or None


def _marketplace_version(root: Path) -> str | None:
    """The version of the plugin entry named PACKAGE_NAME in root's .claude-plugin/marketplace.json."""
    data = _read_json(root / ".claude-plugin" / "marketplace.json")
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, list):
        return None
    return _json_version(next((p for p in plugins if isinstance(p, dict) and p.get("name") == PACKAGE_NAME), None))


def _package_version(root: Path) -> str | None:
    """The version in root's package.json, when its name is PACKAGE_NAME."""
    data = _read_json(root / "package.json")
    if not isinstance(data, dict) or data.get("name") != PACKAGE_NAME:
        return None
    return _json_version(data)


def cmd_version(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).expanduser()
    root = UCG_ROOT

    # First hit wins: UCG's own root, then the version file only UCG's CLI installer writes. A rung whose file is
    # missing, malformed or another package's gives None and falls through to the next.
    ladder = []
    if root is not None:
        ladder += [
            (_marketplace_version(root), ".claude-plugin/marketplace.json"),
            (_package_version(root), "package.json"),
        ]
    ladder.append((_read_plain_version(project_root / "_bmad" / "ucg" / "VERSION"), "_bmad/ucg/VERSION"))

    for version, source in ladder:
        if version is not None:
            print(json.dumps({"version": version, "source": source}))
            return 0

    print(json.dumps({"version": None, "source": "N/A"}))
    return 0


# --- queue ---------------------------------------------------------------------


def _queue_stamp() -> str:
    return datetime.now(timezone.utc).strftime(QUEUE_STAMP_FORMAT)


def _create_new(queue_dir: Path, stem: str) -> tuple[int, Path]:
    """Open queue_dir/<stem>.md for writing, never over a file: <stem>-2.md, -3 and so on when taken.

    Raises OSError when a free name cannot be opened.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    target = queue_dir / f"{stem}.md"
    n = 2
    while True:
        try:
            return os.open(target, flags, 0o644), target
        except FileExistsError:
            target = queue_dir / f"{stem}-{n}.md"
            n += 1


def _draft_keys(body: bytes) -> tuple[str, str, str] | None:
    """The (stage, severity, fp) of the body_header a draft opens with, or None when it opens with none."""
    match = _DRAFT_HEADER_RE.match(body.decode("utf-8-sig", errors="replace"))
    return (match.group("stage"), match.group("severity"), match.group("fp")) if match else None


def submit_commands(repo: str, title: str, severity: str, fp: str, path: str) -> list[str]:
    """The label create, the create, and the create without labels that file a queued draft.

    Each argument is quoted for a POSIX shell, and `--repo` follows the subcommand, so an allow rule scoped to the
    repository (`gh issue create --repo OWNER/REPO`) matches.
    """

    def line(*argv: str) -> str:
        return " ".join(shlex.quote(arg) for arg in argv)

    label = line("gh", "label", "create", "--repo", repo, fp, "--color", FP_LABEL_COLOR,
                 "--description", FP_LABEL_DESCRIPTION)
    create = line("gh", "issue", "create", "--repo", repo, "--title", title,
                  "--label", ",".join((*ISSUE_LABELS, severity, fp)), "--body-file", path)
    bare = line("gh", "issue", "create", "--repo", repo, "--title", title, "--body-file", path)
    return [label, create, bare]


def cmd_queue(args: argparse.Namespace) -> int:
    body_file = Path(args.body_file).expanduser()
    try:
        body = body_file.read_bytes()
    except OSError as exc:
        return _fail("could not read body file %s: %s" % (body_file, exc))
    keys = _draft_keys(body)
    if keys is None:
        return _fail(
            "body file %s holds no body_header; open the draft with the body_header `fingerprint` printed"
            % body_file
        )
    stage, severity, fp = keys
    prefix = f"[health-check][{severity}][{fp}] ultracode-goal/{stage}: "
    if not args.title.startswith(prefix):
        return _fail(
            "title %r is not this draft's: the draft's body_header gives %s, %s and %s, so its title starts with %r"
            % (args.title, stage, severity, fp, prefix)
        )
    if len(args.title) > TITLE_MAX:
        return _fail("title is %d characters long; GitHub takes at most %d" % (len(args.title), TITLE_MAX))
    if _title_unsafe(args.title):
        return _fail(
            "title %r holds a backtick, `$`, double quote, backslash, `!` or a character that is not printable "
            "(a tab or a line break included)" % args.title
        )
    problem = _repo_error(args.repo)
    if problem:
        return _fail(problem)

    queue_dir = Path(args.queue_dir).expanduser()
    try:
        queue_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail("could not create %s: %s" % (queue_dir, exc))
    try:
        fd, target = _create_new(queue_dir, f"hc-ultracode-goal-{stage}-{_queue_stamp()}")
    except OSError as exc:
        return _fail("could not create a queue file in %s: %s" % (queue_dir, exc))
    try:
        try:
            data = memoryview(body)
            while data:
                data = data[os.write(fd, data):]  # os.write may write fewer bytes than asked
        finally:
            os.close(fd)
    except OSError as exc:
        try:
            os.unlink(target)
        except OSError:
            pass
        return _fail("could not write %s: %s" % (target, exc))

    path = os.path.abspath(target)
    _print_utf8({"path": path, "commands": submit_commands(args.repo, args.title, severity, fp, path)})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fingerprint, seen-cache and queue plumbing for the ultracode-goal health check."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fp_parser = sub.add_parser("fingerprint", help="Compute the dedup fingerprints.")
    fp_parser.add_argument("--severity", required=True)
    fp_parser.add_argument("--stage", required=True)
    fp_parser.add_argument(
        "--section-slug",
        dest="section_slug",
        help="The section's kebab-case slug, in place of a --stdin section_heading: it skips the check that the "
        "heading is one of the stage file's own. Without --stdin, title, regression_title and body_header print "
        "null.",
    )
    fp_parser.add_argument(
        "--defect-key",
        dest="defect_key",
        help="One to four kebab-case words naming the thing the fix would change, in place of a --stdin "
        "defect_name. Without --stdin, title, regression_title and body_header print null.",
    )
    fp_parser.add_argument(
        "--stdin",
        action="store_true",
        help='Read {"section_heading": ..., "defect_name": ..., "short_description": ...} from stdin: the '
        "first two in place of --section-slug and --defect-key respectively, the optional third for the "
        "issue title and body header.",
    )
    fp_parser.set_defaults(func=cmd_fingerprint)

    seen_parser = sub.add_parser("seen", help="The seen-cache verdict for a finding.")
    seen_parser.add_argument("--fp", required=True)
    seen_parser.add_argument("--legacy-fp", required=True, dest="legacy_fp")
    seen_parser.add_argument("--cache", required=True)
    seen_parser.add_argument(
        "--repo",
        help="The repository findings are filed on, [HOST/]OWNER/REPO: a record of an issue on another one counts "
        "as no record.",
    )
    seen_parser.set_defaults(func=cmd_seen)

    rec_parser = sub.add_parser("record", help="Record a fingerprint outcome to the cache.")
    rec_parser.add_argument("--fp", required=True)
    rec_parser.add_argument("--cache", required=True)
    rec_parser.add_argument("--issue-url", required=True, dest="issue_url")
    rec_parser.add_argument("--action", required=True)
    rec_parser.add_argument("--date", required=True)
    rec_parser.add_argument(
        "--regression",
        action="store_true",
        help="After a regression verdict: the issue tracks the recurrence, so it "
        "replaces a resolved record.",
    )
    rec_parser.set_defaults(func=cmd_record)

    ver_parser = sub.add_parser(
        "version", help="The version of the UltraCode Goal this script belongs to, never the user's project's."
    )
    ver_parser.add_argument(
        "--project-root", required=True, dest="project_root",
        help="The user's project: its _bmad/ucg/VERSION, which UCG's CLI installer writes, is the last rung.",
    )
    ver_parser.set_defaults(func=cmd_version)

    queue_parser = sub.add_parser(
        "queue", help="Write a drafted body into the local queue and print the commands that submit it."
    )
    queue_parser.add_argument("--queue-dir", required=True, dest="queue_dir")
    queue_parser.add_argument(
        "--body-file", required=True, dest="body_file",
        help="The draft, opening with the body_header `fingerprint` printed: the queue file is named after its stage.",
    )
    queue_parser.add_argument("--title", required=True, help="The issue title `fingerprint` printed for the draft.")
    queue_parser.add_argument("--repo", required=True, help="The repository the commands file the issue on.")
    queue_parser.set_defaults(func=cmd_queue)

    args = parser.parse_args(argv)
    if args.command == "fingerprint" and not args.stdin:
        # Without --stdin both flags stay required, as before --stdin existed.
        missing = [
            flag
            for flag, value in (("--section-slug", args.section_slug), ("--defect-key", args.defect_key))
            if value is None
        ]
        if missing:
            fp_parser.error(
                "the following arguments are required without --stdin: %s" % ", ".join(missing)
            )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
