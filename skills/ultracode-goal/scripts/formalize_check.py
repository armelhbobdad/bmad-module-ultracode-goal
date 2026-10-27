#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Mechanical readiness kernel for the /ucg-formalize gate.

PLUMBING ONLY. This script resolves an Epic's planning/impl/TEA artifact set the
way references/ingest-and-scope.md Stage 1 does, reads mechanical FACTS off the
artifacts on disk, and emits the readiness verdict JSON. It computes the
ten-key `checks` fact map, counts per-finding `mechanical_gaps[]` (each carrying
a HUMAN-AUTHORED `remediable` boolean literal frozen at the emission site, the
preflight_check.py convention), flags `judgment_candidates[]`, and maps the pair
to a verdict. It NEVER decides a judgment gap — that read belongs to the LLM at
the SKILL/preflight layer; this script only tells it what is mechanically
true on disk so one readiness definition serves both the standalone
command and the preflight clause.

FAIL-CLOSED CONTRACT (deliberate — do not "relax", mirrors gate_eval.py's
`nfr_status is None -> treated as failing` posture): every artifact
open is wrapped; a missing / unparseable / ambiguous artifact records a FAILING
gap (or a false `checks` value) and is NEVER treated as a neutral/null pass. Any
signal the kernel can DETECT but has no human-authored classification for
defaults to a JUDGMENT candidate (the no-dark-pass catch-all) — never a
silent pass, never an auto-remediable mechanical gap.

The two coverage ratios (`ac_machine_checkable_ratio`, `gate_ability_tag_coverage`)
are REPORTING values only. `mechanical_budget` is a per-item COUNT
(`len(mechanical_gaps)`), NEVER a ratio-vs-cutoff comparison — so NO numeric
threshold constant exists anywhere in this file.

Verdict mapping:
    mechanical_budget == 0 and no judgment candidate owed     -> ready
    gaps all remediable and no judgment candidate owed        -> remediable
    any judgment candidate owed / any non-remediable
    mechanical gap / any unreadable artifact                  -> blocked

A judgment candidate is owed until the step-3 scan answers it: with
`--scan`, a candidate a red or a concern names by its id and source moves to
`judged_candidates` and stops counting. Without `--scan` every candidate is
owed.

Output: a single JSON object to stdout, serialized with sort_keys for
byte-stable output and carrying NO timestamp/uuid (so a re-run over the same
unchanged artifacts is byte-identical). Exit 0 whenever a payload is
produced (a non-ready verdict is a valid result, not an error). Exit 2 is
reserved for an invocation error where no useful payload can be produced (a
missing/empty required flag), the gate_eval.py invocation lane.

This is the KERNEL only. It emits the rich readiness verdict; the five-key headless
envelope is NOT this script's surface. The four permanent floor
classes are seeded as fixtures elsewhere; this script builds the kernel they
run over.

    uv run formalize_check.py --epic <id> --project-root <p> \
        --planning-artifacts <p> --impl-artifacts <p> --tea-config <p> \
        [--story <key> ...] [--scan <the step-3 scan object, or - for stdin>]

The in-scope stories are the Epic's not-`done` rows (ingest-and-scope.md Stage 1
rule 3), or, with `--story` (repeatable), the named ones among them: the
operator-scoped subset Stage 1 recorded. The per-story and per-AC checks read
only those stories' files, plus the done parent's file a decomposed child's
criteria come from, and `story_keys_uncovered` counts only those keys. A
`--story` key that names no not-`done` story row of the Epic is a
non-remediable gap, and when no `--story` key names one those checks read no
story file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import NamedTuple

# The story-status vocabulary BMad's sprint-planning writes into
# sprint-status.yaml; "done" stories are out of scope (in-scope = not-yet-done,
# ingest-and-scope.md Stage 1 rule 3).
STORY_STATUSES = ("done", "in-progress", "ready-for-dev", "review", "backlog")

# Filenames (case-insensitive substrings) that mark a PRD / ADR-architecture doc
# under the planning-artifacts root. Presence + parseability only (reader,
# never a second evaluator).
PRD_MARKERS = ("prd",)
ADR_MARKERS = ("architecture", "adr")

# TEA artifact filename markers — a test-design / trace / test-review /
# nfr-assessment file. Used to detect a leaked artifact sitting under the
# impl/source tree instead of the trace_output root.
TEA_ARTIFACT_MARKERS = (
    "test-design",
    "trace",
    "traceability",
    "test-review",
    "nfr-assessment",
    "gate-decision",
    "e2e-trace-summary",
)

# A token shaped like a verification artifact reference: a *Verification:* line,
# a pytest path, a test file, a "Test:" pointer. The named-verification check
# keys on the presence of such a pointer in an AC block.
_NAMED_VERIFICATION_RE = re.compile(
    r"\*?\*?(?:Verification|Test)\*?\*?\s*[:\-]|"
    r"\b\w[\w./-]*::\w|"
    r"\b\w[\w./-]*\.py\b|"
    r"\bpytest\b",
    re.IGNORECASE,
)

# An anti-vacuous twin marker: a "twin" / "anti-vacuous" / "mutation" clause that
# proves the assertion is load-bearing.
_ANTI_VACUOUS_RE = re.compile(
    r"anti-vacuous|\btwin\b|\bmutation\b|negative case|must FAIL",
    re.IGNORECASE,
)

# A gate-ability tag the AC/story carries (ci-machine / ci-deterministic /
# operator / Split:). Reporting-only coverage.
_GATE_ABILITY_RE = re.compile(
    r"gate[\s_-]?abilit|\bci-machine\b|\bci-deterministic\b|\bSplit\b",
    re.IGNORECASE,
)

# A machine-checkable AC reads off a deterministic, mechanically observable
# condition (an exit code, an exact equality, a JSON key, a count). A prose /
# non-deterministic AC ("clear", "intuitive", "reasonable") is NOT machine
# checkable. Reporting-only ratio.
_MACHINE_CHECKABLE_RE = re.compile(
    r"exit\s*code|returncode|==|exactly|\bJSON\b|\bcount\b|asserts?\b|"
    r"byte-identical|matches\s+r?['\"]|grep\b|set\(",
    re.IGNORECASE,
)

# Prose adjectives that mark a NON-deterministic / non-machine-checkable AC.
_PROSE_HEDGE_RE = re.compile(
    r"\bclear\b|\bintuitive\b|\breasonable\b|\bappropriate\b|\bgraceful\b|"
    r"\buser-friendly\b|\beasy\b|\bsensible\b|\bnice\b",
    re.IGNORECASE,
)

# An NFR threshold is a bare number with a unit (ms, s, %, rps, MB) in an
# NFR/threshold context. It is "unsourced" when the same line carries no
# citation (no path:line, no http, no FR/ADR id) and is not explicitly marked
# UNKNOWN / CONCERNS / deferred.
_NFR_NUMBER_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|s|%|rps|qps|MB|GB|KB|seconds?|minutes?)\b",
    re.IGNORECASE,
)
_SOURCE_CITATION_RE = re.compile(
    r"\b\w[\w./-]*:\d+\b|https?://|\b(?:FR|NFR|ADR|AD|INV|R)-?\d+\b|"
    r"UNKNOWN|CONCERNS|deferred|TBD",
    re.IGNORECASE,
)

# A vacuous AC asserts a condition that holds no matter what the code does — a
# tautology (assert True / 1 == 1 / x == x), a "passes regardless of"/"always
# passes" claim, or an assertion with no observable subject. It is the first
# permanent JUDGMENT floor class: the kernel can DETECT the tautological SHAPE but
# cannot decide what the AC SHOULD assert instead, so it is NEVER auto-remediable.
# Keys on the vacuous SHAPE, never on mere presence
# of an assertion (the vacuous_ac_sound twin carries a real deterministic AC and
# must not fire).
_VACUOUS_AC_RE = re.compile(
    r"\bassert\s+True\b|"
    r"\bassert\s+1\s*==\s*1\b|"
    r"\bassert\s+(\w+)\s*==\s*\1\b|"
    r"passes?\s+(?:no\s+matter|regardless\s+of|whatever|always)\b|"
    r"\balways\s+passes\b|"
    r"\bno\s+matter\s+what\s+the\s+code\b|"
    r"\btautolog",
    re.IGNORECASE,
)

# A citation token: an AC/trace row pointing at a verification artifact, a story,
# or an FR/NFR id that must be DECLARED somewhere in the resolved set. Captures
# the dangling reference token for the orphaned-index finding detail. Keys on an
# explicit `traces:`/`Covers:`/`verifies:` index row so a plain prose mention is
# not a citation (the orphaned_index_resolved twin declares the cited id and must
# not fire).
_INDEX_CITATION_RE = re.compile(
    r"(?:traces?|covers?|verifies|verified\s+by|index)\s*[:\-]\s*"
    r"([\w][\w./:-]*(?:\s*,\s*[\w][\w./:-]*)*)",
    re.IGNORECASE,
)

# A reference token that LOOKS like a story / FR / verification id worth resolving
# against the declared set (story keys, FR/NFR ids, test::node pointers). A bare
# English word is not an index token.
_INDEX_TOKEN_RE = re.compile(
    r"^(?:(?:FR|NFR|ADR|AD|INV|R)-?\d+|"
    r"\d+-\d+[\w-]*|"
    r"[\w./-]+::[\w-]+|"
    r"[\w./-]+\.py(?:::[\w-]+)?|"
    r"STORY-[\w-]+|VER-[\w-]+)$",
    re.IGNORECASE,
)

# A check-shaped condition that signals a detectable-but-unclassified anomaly the
# kernel must NOT silently pass (the no-dark-pass catch-all). A story / AC line
# may opt a fixture into this lane with an explicit, machine-detectable marker
# the kernel has no human-authored classification for.
_UNCLASSIFIED_SIGNAL_RE = re.compile(r"UCG-UNCLASSIFIED-SIGNAL", re.IGNORECASE)

# The reserved catch-all sentinel kind.
UNCLASSIFIED_KIND = "unclassified_signal"

# The two permanent JUDGMENT-floor classes that are NEVER machine-clearable:
# a vacuous AC the kernel cannot rewrite, and an invented NFR threshold
# the kernel cannot source. This is the human-authored frozen classification (the
# preflight_check.py:411-457 `remediable` literal convention, here as a
# never-remediable allow-list): these kinds are emitted ONLY as judgment
# candidates and carry NO `remediable=True` path anywhere in this file. Authored
# as single-quoted string literals so the source-grep pins the
# floor classification and a mutation re-tagging either as remediable is caught.
NEVER_REMEDIABLE_JUDGMENT_KINDS = frozenset({'vacuous_ac', 'invented_nfr_threshold'})


def _safe_read_text(path: Path) -> str | None:
    """Read a file as UTF-8. Return None on ANY failure (missing/unreadable).

    None is the fail-closed sentinel: the caller treats it as a FAILING signal,
    never as an empty-but-ok read (mirrors gate_eval.py's file-not-found lane).
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        # ValueError covers UnicodeDecodeError (a non-UTF-8/binary artifact):
        # an unparseable file is a FAILING read, never a neutral empty one.
        return None


def _resolve(path_arg: str, project_root: Path) -> Path:
    """Expand a {project-root} token and resolve relative to project_root.

    Stage-1 paths already contain project-root (ingest-and-scope.md:13) — the
    token expansion never re-prefixes an already-absolute path.
    """
    resolved = path_arg.replace("{project-root}", str(project_root))
    path = Path(resolved)
    return path if path.is_absolute() else (project_root / path)


def _rel(path: Path, project_root: Path) -> str:
    """Project-relative display path for a `source` field (deterministic)."""
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


# --- sprint-status parse (the rollup SHAPE from preflight_check.py) ----------


def _locate_sprint_status(impl_artifacts: Path) -> Path | None:
    """sprint-status.yaml under the impl-artifacts root (Stage 1 authority)."""
    candidate = impl_artifacts / "sprint-status.yaml"
    return candidate if candidate.is_file() else None


def _parse_development_status(text: str) -> dict[str, str]:
    """Hand-parse the flat `key: status` scalars under `development_status:`.

    Mirrors preflight_check.py's stdlib-only YAML read (flat scalar lines): a
    single `development_status:` map of `name: status` entries, trailing inline
    comments and surrounding quotes stripped, returned in file order.
    """
    entries: dict[str, str] = {}
    in_block = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not in_block:
            if stripped.rstrip().rstrip(":") == "development_status" and stripped.endswith(":"):
                in_block = True
            continue
        if raw[:1] not in (" ", "\t"):
            break
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip().strip('"').strip("'")
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        if key and value:
            entries[key] = value
    return entries


def _epic_id_of(story_key: str) -> str | None:
    match = re.match(r"^(\d+)", story_key)
    return match.group(1) if match else None


def _is_story_key(key: str) -> bool:
    """True for per-story rows; False for epic/retrospective/bug rows."""
    if _epic_id_of(key) is None:
        return False
    # epic-N / epic-N-retrospective / BUG-... rows are bookkeeping, not stories.
    return not key.lower().startswith(("epic-", "bug-"))


def _not_done_story_keys(text: str, epic: str) -> list[str]:
    """The Epic's not-yet-done story keys (in-scope, Stage 1 rule 3)."""
    entries = _parse_development_status(text)
    keys: list[str] = []
    for key, status in entries.items():
        if not _is_story_key(key):
            continue
        if _epic_id_of(key) != str(epic):
            continue
        if status == "done":
            continue
        keys.append(key)
    return keys


# --- planning artifact resolution -------------------------------------------


def _find_marked_file(root: Path, markers: tuple[str, ...]) -> Path | None:
    """First markdown file under `root` whose name carries a marker substring.

    Deterministic: sorted traversal. Resolution honors the per-root flag — a
    file under the WRONG root is never found (the wrong_root twin).
    """
    if not root.is_dir():
        return None
    try:
        candidates = sorted(p for p in root.rglob("*.md") if p.is_file())
    except OSError:
        return None
    for path in candidates:
        name = path.name.lower()
        if any(marker in name for marker in markers):
            return path
    return None


def _present_and_readable(path: Path | None) -> bool:
    """True iff the file exists AND parses (non-empty read). Fail-closed."""
    if path is None:
        return False
    text = _safe_read_text(path)
    return bool(text and text.strip())


# --- story / AC scan ---------------------------------------------------------


def _story_files(impl_artifacts: Path, epic: str, story_keys: list[str]) -> list[Path]:
    """Every story file of the Epic under impl-artifacts, `done` ones included.

    Stories for an Epic share its number prefix (ingest-and-scope.md:16), and a
    file starting with one of `story_keys` counts too. Sorted for determinism.
    The coverage check reads all of them, since a done parent's file covers its
    decomposed children, and so does the declared-id set. Which of them the
    per-story checks read is `_in_scope_story_files`'s call.
    """
    if not impl_artifacts.is_dir():
        return []
    try:
        all_md = sorted(p for p in impl_artifacts.rglob("*.md") if p.is_file())
    except OSError:
        return []
    prefix = f"{epic}-"
    files: list[Path] = []
    for path in all_md:
        name = path.name.lower()
        if name.startswith("sprint-status"):
            continue
        if name.startswith(prefix) or any(name.startswith(f"{k.lower()}") for k in story_keys):
            files.append(path)
    return files


# The id part of a story key or a story file's name: the Epic number, the
# story number (which may carry letters, `2a`), then any child segments a
# decomposition added: a single letter or a roman numeral up to x, and, after
# one of those, a number (`94-7-b-1`).
_EPIC_SEGMENT = re.compile(r"^\d+$")
_STORY_SEGMENT = re.compile(r"^\d+[a-z]*$")
_CHILD_SEGMENT = re.compile(r"^(?:[a-z]|i{1,3}|iv|vi{0,3}|ix|x)$")
_NUMBERED_CHILD_SEGMENT = re.compile(r"^\d+$")


def _story_stem(name: str) -> str | None:
    """The id stem of a story key or file name, or None for an alpha-keyed one.

    `95-0-a-i-the-scanner-spine` gives `95-0-a-i`, `94-2a-the-thing` gives
    `94-2a`, `2-4-kebab-title.md` and `2-4.md` both give `2-4`. A file name is
    cut at its first `.` or `_` first, so `1-1_draft.md` gives `1-1`. A title
    word that is itself a single letter or a roman numeral reads as a child
    segment (`2-4-a-new-thing` gives `2-4-a`). A story file named after its
    full key gives the same stem. A file named otherwise for such a key (a
    bare number, or a retitled slug) has a shorter stem: given the
    sprint-status rows, with the key's row and no row of that stem, the key
    reads as a child of that file whose parent row the split removed, and
    `checks.decomposed_children` lists it with no parent row (define-done.md
    renames such a file after its key); without them it reads uncovered. A
    parent whose title starts that way (`5-1-i-o-layer` gives `5-1-i-o`)
    never covers its decomposed children, which fails closed.
    """
    base = re.split(r"[._]", name.lower(), maxsplit=1)[0]
    parts = base.split("-")
    if len(parts) < 2 or not (_EPIC_SEGMENT.match(parts[0]) and _STORY_SEGMENT.match(parts[1])):
        return None
    stem = parts[:2]
    for part in parts[2:]:
        lettered_parent = len(stem) > 2 and _CHILD_SEGMENT.match(stem[-1])
        if not (_CHILD_SEGMENT.match(part) or (lettered_parent and _NUMBERED_CHILD_SEGMENT.match(part))):
            break
        stem.append(part)
    return "-".join(stem)


def _parent_stem(stem: str) -> str | None:
    """The stem one level up: `95-0-a-i` to `95-0-a`, `92-7f` to `92-7`, `7-1` to None."""
    parts = stem.split("-")
    if len(parts) > 2:
        return "-".join(parts[:-1])
    lettered = re.match(r"^(\d+)[a-z]+$", parts[1])
    return "%s-%s" % (parts[0], lettered.group(1)) if lettered else None


def _in_scope_story_files(
    story_paths: list[Path], scope_keys: list[str], children: list[tuple[str, Path, str | None]]
) -> list[Path]:
    """The story files the per-story and per-AC checks read, in `story_paths` order.

    Each in-scope key's own file, matched on the id stem as `_story_coverage`
    matches it (the whole key for an alpha-keyed one), and the parent file each
    in-scope decomposed child's criteria come from (`children`). A `done`
    story's file is out of scope (ingest-and-scope.md Stage 1 rule 3), so its
    acceptance criteria raise no gap here. With no in-scope key at all (every
    row `done`, or no rollup to read), every file, as before. The caller never
    asks for that fallback when `--story` was given: a `--story` list that
    names no not-done row reads no file.
    """
    if not scope_keys:
        return list(story_paths)
    stems = {_story_stem(key) for key in scope_keys} - {None}
    alpha = [key.lower() for key in scope_keys if _story_stem(key) is None]
    parents = {parent for _, parent, _ in children}
    return [
        path
        for path in story_paths
        if path in parents
        or _story_stem(path.name) in stems
        or any(path.name.lower().startswith(key) for key in alpha)
    ]


def _uncovered_story_keys(
    story_paths: list[Path], story_keys: list[str], rows: dict[str, str] | None = None
) -> list[str]:
    """In-scope keys with no story file of their own, in `story_keys` order.

    `_story_coverage` decides it; this keeps only the uncovered keys.
    """
    return _story_coverage(story_paths, story_keys, rows).uncovered


class _Coverage(NamedTuple):
    """What `_story_coverage` found for the in-scope keys.

    `uncovered`: the keys with no file of their own and no parent that covers
    them, in `story_keys` order. `children`: the keys a parent's file covers,
    each as (key, the parent's file, the parent's row key or None when the
    split removed it). `below_parent`: the uncovered keys that a done parent's
    file would cover but whose row sits below that parent's row, each mapped to
    the parent's row key.
    """

    uncovered: list[str]
    children: list[tuple[str, Path, str | None]]
    below_parent: dict[str, str]


def _story_coverage(
    story_paths: list[Path], story_keys: list[str], rows: dict[str, str] | None = None
) -> _Coverage:
    """Which in-scope keys have a story file, and which a parent's file covers.

    A file covers a key when the two share the same id stem (`_story_stem`):
    the Epic number, the story number with any letters (`94-2a`), and every
    child segment a decomposition added (`95-0-a-i`). The stem, not the whole
    slug, because the slug is not a contract: `ucg-create-story` writes
    `{story_key}.md` from whatever the operator supplied, so an operator who
    asked for story `2-4` gets `2-4.md` while sprint-planning's generated key
    is `2-4-<kebab-title>`; both have the stem `2-4`. The full stem, not its
    first two numbers, because a shorter match lets a sibling cover a key: a
    child `95-0-a-i` with no file of its own would read covered by
    `95-0-a-audit.md`, and `95-0-b` by the same file. Comparing whole stems
    also keeps a HIGHER-numbered story from covering a lower one (`1-10` is
    not `1-1`).

    One more way a key is covered: by a decomposed parent. execute.md's
    decomposition conventions give a child row no story file ("the child has
    no story file and must never get one"), insert the child rows above the
    parent row, set the parent row to `done` once its children exist, and
    keep the parent's file as the text the children cite. So walking up from
    the key's stem (`95-0-a-i` to `95-0-a`, `92-7f` to `92-7`), a parent with
    a file covers the key when its row is `done` and the key's row sits above
    it, or when it has no row at all: a split that removed the parent's row
    instead of setting it `done` still leaves the parent's file as the text
    its children cite. The order is what tells a child from a story inserted
    later with a lettered key: sprint-planning writes rows in the order of the
    epics' story headings, so a `3-2a` added after `3-2` shipped lands below
    `3-2`'s row and stays uncovered, while every child sits above its parent.
    When several rows share the parent's stem, the key must sit above the
    first of them. A parent row that is not `done` stops the walk: a story
    still being worked is not a container. A level with no row and no file is
    passed over. `rows` is the sprint-status map (`key: status`) in file
    order; without it no parent covers anything, and neither does a parent of
    a key that has no row there.

    What the order cannot tell apart is a story inserted ABOVE a done parent's
    row, or a child whose parent row was removed: both read as children, and
    so does a story whose own file has a shorter stem than its key
    (`_story_stem`). So every key a parent covers is returned in `children`,
    for the report to show rather than to gate on.

    A key whose slug carries no story number (an alpha-keyed track) has no
    stem, so it falls back to the whole-key prefix rather than being silently
    treated as covered.
    """
    names = [p.name.lower() for p in story_paths]
    file_of_stem: dict[str, Path] = {}
    for path, name in zip(story_paths, names):
        stem = _story_stem(name)
        if stem and stem not in file_of_stem:
            file_of_stem[stem] = path
    row_status: dict[str, str] = {}
    # The first row of each stem, by position and key: a child sits above it.
    first_row: dict[str, tuple[int, str]] = {}
    position = {key: index for index, key in enumerate(rows or {})}
    for index, (key, status) in enumerate((rows or {}).items()):
        stem = _story_stem(key)
        # Several rows can share a stem (`92-7e-i`, `92-7e-i-scan`): done only
        # when every one of them is.
        if stem:
            row_status[stem] = status if row_status.get(stem, "done") == "done" else row_status[stem]
            first_row.setdefault(stem, (index, key))

    uncovered: list[str] = []
    children: list[tuple[str, Path, str | None]] = []
    below_parent: dict[str, str] = {}
    for key in story_keys:
        stem = _story_stem(key)
        if stem is None:
            low = key.lower()
            if not any(name.startswith(low) for name in names):
                uncovered.append(key)
            continue
        if stem in file_of_stem:
            continue
        parent = _parent_stem(stem) if rows is not None and key in position else None
        while parent is not None:
            status = row_status.get(parent)
            if status is not None and status != "done":
                parent = None
                break
            if parent in file_of_stem:
                break
            parent = _parent_stem(parent)
        if parent is None:
            uncovered.append(key)
        elif parent not in first_row:
            children.append((key, file_of_stem[parent], None))
        elif position[key] < first_row[parent][0]:
            children.append((key, file_of_stem[parent], first_row[parent][1]))
        else:
            uncovered.append(key)
            below_parent[key] = first_row[parent][1]
    return _Coverage(uncovered, children, below_parent)


def _split_ac_blocks(text: str) -> list[tuple[int, str]]:
    """Split a story body into (start_line, block_text) per acceptance criterion.

    An AC starts at a numbered list item under an "Acceptance Criteria" heading
    (``1. ...``) and runs until the next numbered item at the SAME indent or a
    new heading. Returns 1-based start line numbers for the `<path:line>`
    source.

    An item opens a new AC when it starts left of the first AC item's text,
    the CommonMark rule for a list item at the same level: its indent is less
    than the first item's indent plus its marker width (`1. ` is three). So a
    right-aligned ` 9.` before `10.` and an item that slipped one space still
    open their own AC. A wrapped line that happens to begin with a number
    (`   1. All four...` under an item's text) and a nested numbered sub-list
    start at or right of that text, so they stay part of the AC above them:
    reading either as a new AC splits one criterion in two, and the first half
    then reports a missing verification and a missing twin it does have.
    """
    lines = text.splitlines()
    in_ac = False
    # Where the first AC item's text starts: an item left of it opens a new AC.
    text_column: int | None = None
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] | None = None
    for idx, raw in enumerate(lines):
        stripped = raw.strip()
        if re.match(r"^#+\s", raw):
            # Any heading closes the open block: a block's lines are contiguous,
            # since each candidate's line number is counted from its start.
            current = None
            if re.search(r"acceptance criteria", stripped, re.IGNORECASE):
                in_ac = True
                text_column = None
                continue
            # A different heading ends the AC section.
            if in_ac:
                in_ac = False
            continue
        if not in_ac:
            continue
        item = re.match(r"^(\s*)(\d+\.\s)", raw.expandtabs(4))
        indent = len(item.group(1)) if item else None
        if item and (text_column is None or indent < text_column):
            if text_column is None:
                text_column = indent + len(item.group(2))
            current = [raw]
            blocks.append((idx + 1, current))
        elif current is not None:
            current.append(raw)
    return [(line_no, "\n".join(body)) for line_no, body in blocks]


def _ac_is_machine_checkable(block: str) -> bool:
    """Reporting heuristic: a deterministic, mechanically observable condition."""
    if _PROSE_HEDGE_RE.search(block) and not _MACHINE_CHECKABLE_RE.search(block):
        return False
    return bool(_MACHINE_CHECKABLE_RE.search(block))


# --- declared-id index (orphaned-index resolution) ---------------------------

# An id DECLARED by a story/test/PRD: an FR/NFR id, a story key, a test::node,
# a .py test file, or an explicit STORY-/VER- token. The orphaned-index check
# resolves every CITED index token against this declared set; a citation with no
# declaration is the dangling never-green reference.
_FR_DECL_RE = re.compile(r"\b((?:FR|NFR|ADR|AD|INV|R)-?\d+)\b", re.IGNORECASE)
_VER_DECL_RE = re.compile(
    r"\b([\w./-]+::[\w-]+|[\w./-]+\.py(?:::[\w-]+)?|STORY-[\w-]+|VER-[\w-]+)\b",
    re.IGNORECASE,
)


def _norm_id(token: str) -> str:
    """Canonicalize an id token for set membership (case + dash-insensitive)."""
    return token.strip().lower().replace("-", "").rstrip(".")


def _collect_declared_ids(
    story_bodies: dict[str, str], story_keys: list[str], prd_text: str | None
) -> set[str]:
    """The set of ids any story / test / PRD in the resolved set DECLARES.

    Sources: the not-done story keys themselves, every story-key-shaped filename
    stem, every FR/NFR/ADR id mentioned anywhere in a story or the PRD, and every
    test::node / .py / STORY- / VER- pointer named in a story body. The
    orphaned-index check resolves citations against THIS set (the
    orphaned_index_resolved twin declares its cited id here and so does not fire).
    """
    declared: set[str] = set()
    for key in story_keys:
        declared.add(_norm_id(key))
    for rel, body in story_bodies.items():
        # The story file stem (e.g. 1-2-floor) is a declared story id.
        stem = Path(rel).stem
        declared.add(_norm_id(stem))
        # A CITATION is not a DECLARATION. Harvesting over the whole body meant
        # the `traces:` row was itself scanned, so `- traces: FR-99` declared
        # FR-99 and then resolved against it: every _INDEX_TOKEN_RE shape except
        # the story key (`\d+-\d+…`) is also matched by _FR_DECL_RE or
        # _VER_DECL_RE, so a dangling `path::node`, `*.py`, `STORY-*`, `VER-*`
        # or FR/NFR/ADR/AD/INV/R citation could never be reported orphaned.
        # Only the story-key shape survived — and that shape always takes the
        # `regenerable` mechanical arm, which left the JUDGMENT arm dead code.
        # Prose and `Verification:` mentions still declare; the citation row no
        # longer declares the thing it is citing.
        declaring = "\n".join(
            line for line in body.splitlines() if not _INDEX_CITATION_RE.search(line)
        )
        for match in _FR_DECL_RE.finditer(declaring):
            declared.add(_norm_id(match.group(1)))
        for match in _VER_DECL_RE.finditer(declaring):
            declared.add(_norm_id(match.group(1)))
    if prd_text:
        for match in _FR_DECL_RE.finditer(prd_text):
            declared.add(_norm_id(match.group(1)))
    return declared


def _cited_index_tokens(block: str) -> list[str]:
    """The index-citation tokens an AC/trace row declares it TRACES/COVERS.

    Only an explicit `traces:`/`covers:`/`verifies:`/`index:` row counts (not a
    prose mention), and only tokens shaped like a story/FR/verification id are
    returned (a bare English word is dropped). Keeps the check keyed on a real
    dangling INDEX reference, not on every citation.
    """
    tokens: list[str] = []
    for match in _INDEX_CITATION_RE.finditer(block):
        for raw in match.group(1).split(","):
            tok = raw.strip()
            if tok and _INDEX_TOKEN_RE.match(tok):
                tokens.append(tok)
    return tokens


# --- TEA artifact location ---------------------------------------------------


def _tea_trace_output_root(tea_config: Path, project_root: Path) -> Path | None:
    """Resolve the trace_output root from the TEA config (the leak-check anchor).

    Reads the flat `trace_output:` (or `test_artifacts:`) scalar. TOML configs
    go through stdlib tomllib (read-only). Fail-closed: an unreadable config
    yields None and the leak check treats every TEA-shaped artifact under
    impl/source as a candidate signal.
    """
    text = _safe_read_text(tea_config)
    if text is None:
        return None

    value: str | None = None
    if tea_config.suffix.lower() == ".toml":
        try:
            import tomllib

            data = tomllib.loads(text)
            raw = data.get("trace_output") or data.get("test_artifacts")
            value = raw if isinstance(raw, str) else None
        except Exception:
            value = None
    if value is None:
        for key in ("trace_output", "test_artifacts"):
            match = re.search(rf"^\s*{key}\s*:\s*(.+)$", text, re.MULTILINE)
            if match:
                value = match.group(1).strip().strip('"').strip("'")
                break
    if not value:
        return None
    resolved = value.replace("{project-root}", str(project_root))
    path = Path(resolved)
    return path if path.is_absolute() else (project_root / path)


# UCG's own impl-artifact bookkeeping is NOT a TEA artifact, even when its filename
# carries a TEA marker token because the STORY SLUG does (e.g. a story-note
# "2-7-...-test-design-nfr.md", or a ".tests-ran-<story>" / ".budget-<story>"
# sentinel for that story). The leak check must skip these: relocating one is a
# misfile, and (because they live under impl-artifacts BY DESIGN) moving it would
# be the only thing that clears the gate, so a "leave it in place" disposition would
# deadlock the budget==0 launch gate. Identity decides, not the marker substring.
# The story number may carry letters (`3-2a-trace-export.md`), as _STORY_SEGMENT
# reads it: archiving a lettered story's own file leaves its key uncovered.
_UCG_STORY_NOTE_RE = re.compile(r"^\d+-\d+[a-z]*-")


def _is_ucg_impl_artifact(path: Path, name: str) -> bool:
    """True for a UCG-owned impl-artifact (run sentinel / story note), which is never
    a leaked TEA artifact. ``name`` is the lowercased filename."""
    if name.startswith("."):
        return True  # run sentinels: .tests-ran-<story>, .budget-<story>
    if _UCG_STORY_NOTE_RE.match(name):
        return True  # story notes: <epic>-<story>-<slug>.md, <story> as 2 or 2a
    if name.endswith(".md"):
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:600]
        except OSError:
            return False
        if "authored_by: ultracode-goal" in head:
            return True  # UCG-authored note whose name does not match the prefix rule
    return False


def _leaked_tea_artifacts(
    impl_artifacts: Path, trace_root: Path | None
) -> list[Path]:
    """TEA-shaped artifacts found under the impl/source tree (the wrong root).

    A TEA artifact correctly placed under trace_root is NOT a leak; one under
    impl-artifacts (and outside trace_root) is (the check keys on the
    WRONG LOCATION, not on mere presence of a TEA file). UCG's own story notes /
    run sentinels are excluded even when their filename carries a marker token
    (see _is_ucg_impl_artifact).
    """
    if not impl_artifacts.is_dir():
        return []
    try:
        all_files = sorted(p for p in impl_artifacts.rglob("*") if p.is_file())
    except OSError:
        return []
    leaked: list[Path] = []
    for path in all_files:
        name = path.name.lower()
        if not any(marker in name for marker in TEA_ARTIFACT_MARKERS):
            continue
        if _is_ucg_impl_artifact(path, name):
            continue
        if trace_root is not None and trace_root in path.parents:
            continue
        leaked.append(path)
    return leaked


# --- TEA-reader: read TEA's emitted fields, NEVER originate them ---------------
# formalize stays a READER of the TEA test-design risk matrix + nfr-assessment.md
# located under the trace_output root; it verifies presence/parseability and
# value->source-or-UNKNOWN provenance, recomputes ONLY a blank P×I score cell when
# both P and I are stated (provenance arithmetic), and never originates an NFR
# threshold, a P0-P3 percentage, a Quality Score, or an overallStatus.

_OVERALL_STATUS_RE = re.compile(
    r"(?:Overall\s+Status|overallStatus)[*:_\s]*[`*]*\s*(PASS|CONCERNS|FAIL|NOT_ASSESSED)",
    re.IGNORECASE,
)


def _find_under(root: Path | None, marker: str) -> Path | None:
    """First readable file under ``root`` whose name carries ``marker`` (lowercased)."""
    if root is None or not root.is_dir():
        return None
    try:
        for path in sorted(root.rglob("*")):
            if path.is_file() and marker in path.name.lower():
                return path
    except OSError:
        return None
    return None


def _table_rows(text: str):
    """Yield (line_no, [cells]) for each markdown table row (``| a | b | …|``)."""
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 3:
            yield line_no, [cell.strip() for cell in stripped.strip("|").split("|")]


def _scan_test_design(text: str, rel: str) -> tuple[list[dict], list[dict]]:
    """Risk-matrix P×I provenance: blank-cell recompute (mechanical) vs disagreement
    (judgment), plus an unsourced NFR threshold (judgment). Reader-only, blank-cell-only."""
    gaps: list[dict] = []
    candidates: list[dict] = []
    cols: dict[str, int] | None = None
    for _, cells in _table_rows(text):
        lower = [c.lower() for c in cells]
        if "p" in lower and "i" in lower and any("score" in c for c in lower):
            cols = {
                "P": lower.index("p"),
                "I": lower.index("i"),
                "Score": next(idx for idx, c in enumerate(lower) if "score" in c),
            }
            break
    if cols is not None:
        header_seen = False
        for line_no, cells in _table_rows(text):
            lower = [c.lower() for c in cells]
            if not header_seen:
                header_seen = "p" in lower and "i" in lower and any("score" in c for c in lower)
                continue
            if all(set(c) <= set("-: ") for c in cells):  # separator row
                continue
            if max(cols.values()) >= len(cells):
                continue
            p, i, score = cells[cols["P"]], cells[cols["I"]], cells[cols["Score"]]
            if not (p.isdigit() and i.isdigit()):
                continue
            product = int(p) * int(i)
            if score == "":
                gaps.append({
                    "id": "blank_pxi_score:%s:%d" % (rel, line_no),
                    "kind": "blank_pxi_score",
                    "severity": "low",
                    "detail": "Blank P×I score with stated P=%s, I=%s -> recompute %d" % (p, i, product),
                    "remediable": True,
                    "source": "%s:%d" % (rel, line_no),
                    "recomputed": product,
                })
            elif score.isdigit() and int(score) != product:
                candidates.append({
                    "source": "%s:%d" % (rel, line_no),
                    "kind": "risk_score_conflict",
                    "why_machine_cannot_decide": "stated risk score %s conflicts with stated P,I "
                    "(%s×%s=%d); requires TEA reconciliation" % (score, p, i, product),
                })
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _NFR_NUMBER_RE.search(line) and not _SOURCE_CITATION_RE.search(line):
            candidates.append({
                "source": "%s:%d" % (rel, line_no),
                "kind": "invented_nfr_threshold",
                "why_machine_cannot_decide": "NFR threshold number with no cited source and not marked "
                "UNKNOWN; the kernel reads thresholds, it never invents the value",
            })
    return gaps, candidates


def _scan_nfr_assessment(text: str, rel: str) -> list[dict]:
    """Read TEA's per-category PASS rows; flag PASS-on-UNKNOWN and PASS-without-evidence
    as judgment_candidates. overallStatus is READ via the gate_eval recognizer, never
    re-derived or overwritten."""
    candidates: list[dict] = []
    # READ TEA's overallStatus via the same recognizer gate_eval.py uses;
    # the kernel never re-derives or emits it. A present-but-unreadable assessment
    # (no parseable overallStatus at all) is itself a JUDGMENT a human must resolve.
    overall = _OVERALL_STATUS_RE.search(text)
    if overall is None:
        candidates.append({
            "source": "%s:1" % rel,
            "kind": "nfr_overall_status_unreadable",
            "why_machine_cannot_decide": "nfr-assessment has no parseable overallStatus "
            "(PASS/CONCERNS/FAIL/NOT_ASSESSED); the kernel reads this field, it never originates it",
        })
    for line_no, cells in _table_rows(text):
        if not any(cell.strip().upper() == "PASS" for cell in cells):
            continue
        row = " | ".join(cells)
        if any("unknown" in cell.lower() for cell in cells):
            candidates.append({
                "source": "%s:%d" % (rel, line_no),
                "kind": "nfr_pass_on_unknown",
                "why_machine_cannot_decide": "category asserted PASS on an UNKNOWN threshold; "
                "UNKNOWN routes to CONCERNS, never PASS",
            })
        elif not _SOURCE_CITATION_RE.search(row):
            candidates.append({
                "source": "%s:%d" % (rel, line_no),
                "kind": "nfr_pass_without_evidence",
                "why_machine_cannot_decide": "category asserted PASS with no named evidence source",
            })
    return candidates


# --- timing seam (measurement protocol) -------------------------------------
# A no-op marker at the start of the mechanical half. Production never overrides
# it; a test monkeypatches it to inject a known delay so `mechanical_ms` is
# asserted against a deterministic monotonic-DELTA lower bound (defeating any
# hardcoded constant or raw unsubtracted clock read). Timing is measured AFTER the
# verdict is decided and never alters it — there is NO duration-vs-literal compare
# and NO code path that blocks/escalates/downgrades a verdict on elapsed time
# (the wall-clock budget is UNKNOWN, measured never guessed,
# and set only from a first real run — no number is authored here).
def _mechanical_hook() -> None:
    return None


# --- verdict assembly --------------------------------------------------------


# --- judgment candidate identity and the step-3 answers ----------------------

# The digest length red_ids.py uses for a RED's id.
_CANDIDATE_DIGEST_LEN = 12


def _normalize_text(text: str) -> str:
    """NFC, whitespace collapsed: re-spacing one line keeps its text (a reflow
    that moves words across lines does not)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def _candidate_id(candidate: dict, texts_by_rel: dict[str, str]) -> str:
    """A judgment candidate's line-free id: `<kind>:<bare path>:<digest>`.

    The digest is the first 12 hex characters of the SHA-256 of the flagged
    line's normalized text and the candidate's normalized
    `why_machine_cannot_decide`, the recipe red_ids.py uses for a RED (which
    digests the decision instead). The line text is what makes the id confirm
    that the line at the candidate's source still reads as it did when the
    candidate was seeded. The reason tells apart two candidates of one kind on
    one line, such as an AC row citing two ids nobody declares: each names its
    own token. The line NUMBER is left out, so the id alone cannot tell apart
    two candidates of one kind on the same text in one file, and an answer
    must carry the candidate's `source` too (`_answers`).
    """
    kind, source = candidate["kind"], candidate["source"]
    path, _, line = source.rpartition(":")
    text = ""
    if line.isdigit() and path:
        lines = (texts_by_rel.get(path) or "").splitlines()
        number = int(line)
        if 1 <= number <= len(lines):
            text = lines[number - 1]
    else:
        path = source
    reason = _normalize_text(str(candidate.get("why_machine_cannot_decide") or ""))
    digest = hashlib.sha256(("%s\n%s" % (_normalize_text(text), reason)).encode("utf-8")).hexdigest()
    return "%s:%s:%s" % (kind, path, digest[:_CANDIDATE_DIGEST_LEN])


def _read_scan(scan: str | None) -> tuple[dict | None, dict | None]:
    """(the step-3 scan object, the `scan` report) for `--scan`, or (None, None).

    `-` reads stdin. An unreadable or unparseable scan, or one not in the
    shape red_ids.py accepts (`_well_formed_scan`), answers nothing: every candidate stays unjudged and the verdict
    stays `blocked`, and the report says the scan was not read. A scan that
    cannot be read is not an answer.
    """
    if scan is None:
        return None, None
    try:
        text = sys.stdin.read() if scan == "-" else Path(scan).read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, UnicodeDecodeError, ValueError):
        return None, {"path": scan, "read": False, "answered": 0}
    if not _well_formed_scan(data):
        return None, {"path": scan, "read": False, "answered": 0}
    return data, {"path": scan, "read": True, "answered": 0}


def _well_formed_scan(data: object) -> bool:
    """Whether the scan is one red_ids.py accepts, with concerns that can be read.

    An object carrying a `reds` list whose every red is an object with a
    non-blank string `kind`, `source` and `decision_needed`, all of it text
    UTF-8 can encode: red_ids.py refuses
    anything else, and then the reds stream the hard gate reads is not
    computed, so a scan it refuses must not judge a candidate here either, or
    the kernel would say `ready` over reds no one minted. `concerns`, when
    present, must be a list of objects; red_ids.py never reads it, and a
    refusal here only keeps the verdict `blocked`.
    """
    if not isinstance(data, dict) or not isinstance(data.get("reds"), list):
        return False
    for red in data["reds"]:
        if not isinstance(red, dict):
            return False
        for field in ("kind", "source", "decision_needed"):
            value = red.get(field)
            if not isinstance(value, str) or not _normalize_text(value):
                return False
        # red_ids.py writes each red as UTF-8; a lone surrogate it cannot encode.
        try:
            json.dumps(red, ensure_ascii=False).encode("utf-8")
        except UnicodeEncodeError:
            return False
    concerns = data.get("concerns", [])
    return isinstance(concerns, list) and all(isinstance(entry, dict) for entry in concerns)


def _answers(scan: dict | None) -> dict[tuple[str, str], str]:
    """`{(candidate id, source): "red" | "concern"}` from the scan's entries.

    A seeded candidate is answered by the entry that carries its id in
    `candidate` and its `source` as given. Both, because each covers a way the
    other alone would judge the wrong line: the source tells apart two
    candidates whose flagged lines and reasons read the same (they share an id), and the
    id makes sure the line at that source still holds the text the subagent
    judged (an edit between the seeding and this run moves lines, and a source
    alone would then name another line). A pair both lists name reads as
    `red`: a confirmation is never outweighed by a clearing.
    """
    answers: dict[tuple[str, str], str] = {}
    if not scan:
        return answers
    for field, verdict in (("concerns", "concern"), ("reds", "red")):
        for entry in scan.get(field) or []:
            candidate, source = entry.get("candidate"), entry.get("source")
            if isinstance(candidate, str) and isinstance(source, str) and candidate.strip() and source.strip():
                answers[(candidate.strip(), source.strip())] = verdict
    return answers


def build_verdict(
    epic: str,
    project_root: Path,
    planning_artifacts: Path,
    impl_artifacts: Path,
    tea_config: Path,
    scan: str | None = None,
    stories: list[str] | None = None,
) -> dict:
    mechanical_gaps: list[dict] = []
    judgment_candidates: list[dict] = []
    # The text of every file a candidate can point into, by the relative path
    # its `source` names: the line its id digests.
    texts_by_rel: dict[str, str] = {}

    # timing: monotonic samples at entry and at the mechanical-half start.
    _entry_ns = time.monotonic_ns()
    _mech_start_ns = time.monotonic_ns()
    _mechanical_hook()
    nfr_path: Path | None = None

    # --- PRD / ADR presence (planning-artifacts root, fail-closed) ---
    prd_path = _find_marked_file(planning_artifacts, PRD_MARKERS)
    adr_path = _find_marked_file(planning_artifacts, ADR_MARKERS)
    prd_present = _present_and_readable(prd_path)
    adr_present = _present_and_readable(adr_path)

    if not prd_present:
        mechanical_gaps.append(
            {
                "id": "prd_absent",
                "kind": "missing_planning_artifact",
                "severity": "high",
                "detail": "PRD not found or unreadable under planning-artifacts: %s"
                % _rel(planning_artifacts, project_root),
                # A regenerable stub is machine-derivable (bmad-create-prd); the
                # CONTENT decision is a separate judgment the SKILL layer makes.
                "remediable": True,
                "source": _rel(planning_artifacts, project_root),
            }
        )
    if not adr_present:
        mechanical_gaps.append(
            {
                "id": "adr_absent",
                "kind": "missing_planning_artifact",
                "severity": "high",
                "detail": "ADR/architecture not found or unreadable under "
                "planning-artifacts: %s" % _rel(planning_artifacts, project_root),
                "remediable": True,
                "source": _rel(planning_artifacts, project_root),
            }
        )

    # --- sprint-status + in-scope stories (fail-closed) ---
    sprint_status = _locate_sprint_status(impl_artifacts)
    sprint_text = _safe_read_text(sprint_status) if sprint_status else None
    # The sprint-status rows (`key: status`): the uncovered-key check reads
    # them for decomposed parents, which are `done` and keep the story file.
    rows: dict[str, str] = {}
    if sprint_status is None or sprint_text is None:
        story_keys: list[str] = []
        mechanical_gaps.append(
            {
                "id": "sprint_status_absent",
                "kind": "missing_impl_artifact",
                "severity": "high",
                "detail": "sprint-status.yaml not found or unreadable under "
                "impl-artifacts: %s" % _rel(impl_artifacts, project_root),
                # bmad-sprint-planning regenerates the rollup deterministically.
                "remediable": True,
                "source": _rel(impl_artifacts / "sprint-status.yaml", project_root),
            }
        )
    else:
        # PRESENT-BUT-UNPARSED is its own fail-open, distinct from absent.
        # `_safe_read_text` returns None only on OSError/decode failure, so an
        # EMPTY or structurally unparseable rollup returns "" and lands here.
        # `_not_done_story_keys` then yields an empty in-scope set, which
        # silences BOTH guards below at once: story files still resolve through
        # the epic-prefix glob so `no_in_scope_stories` never fires, and
        # `story_keys_uncovered` is scoped `if story_paths and uncovered` with
        # `uncovered` computed against that empty set. The kernel returned
        # `ready` with `mechanical_budget: 0` on an Epic missing a story file —
        # the exact partial-seed fail-open `story_keys_uncovered` exists to
        # close. A rollup with rows for other epics, or a legitimately all-done
        # Epic, still parses non-empty, so neither pays for this.
        if not _parse_development_status(sprint_text):
            mechanical_gaps.append(
                {
                    "id": "sprint_status_unparsed",
                    "kind": "missing_impl_artifact",
                    "severity": "high",
                    "detail": "sprint-status.yaml is present but yields no "
                    "development_status rows, so the in-scope story set is empty "
                    "and every per-story check below would pass vacuously: %s"
                    % _rel(impl_artifacts / "sprint-status.yaml", project_root),
                    # bmad-sprint-planning regenerates the rollup deterministically.
                    "remediable": True,
                    "source": _rel(impl_artifacts / "sprint-status.yaml", project_root),
                }
            )
        story_keys = _not_done_story_keys(sprint_text, epic)
        rows = {
            key: status
            for key, status in _parse_development_status(sprint_text).items()
            if _epic_id_of(key) == str(epic)
        }

    # The in-scope keys: every not-done story row, or the operator-scoped
    # subset `--story` names. A named key that is not a not-done story row of
    # this Epic (a typo, another Epic's row, a done row) is not silently
    # dropped: the verdict would then cover less than the run drives.
    scope_keys = story_keys
    if stories is not None:
        requested = list(dict.fromkeys(key.strip() for key in stories))
        scope_keys = [key for key in story_keys if key in requested]
        for key in requested:
            if key in story_keys:
                continue
            mechanical_gaps.append(
                {
                    "id": "story_not_in_scope:%s" % key,
                    "kind": "story_not_in_scope",
                    "severity": "high",
                    "detail": "--story %s names no not-done story row of Epic %s in sprint-status.yaml: %s"
                    % (key, epic, _rel(impl_artifacts / "sprint-status.yaml", project_root)),
                    # The invocation names the scope; only the caller can
                    # correct it.
                    "remediable": False,
                    "source": _rel(impl_artifacts / "sprint-status.yaml", project_root),
                }
            )

    # --- per-story / per-AC scan ---
    story_paths = _story_files(impl_artifacts, epic, story_keys)

    # An EMPTY in-scope story set is a fail-open, not a pass: every per-story and
    # per-AC check below iterates nothing, so an Epic whose story files do not
    # exist would otherwise score a clean zero-gap `ready` vacuously. Count it as
    # a gap like any other so the verdict is `remediable` instead.
    if not story_paths:
        mechanical_gaps.append(
            {
                "id": "no_in_scope_stories",
                "kind": "no_in_scope_stories",
                "severity": "high",
                "detail": "No in-scope story files found for Epic %s under "
                "impl-artifacts: %s" % (epic, _rel(impl_artifacts, project_root)),
                # The create-story scaffold generates the missing story files.
                "remediable": True,
                "source": _rel(impl_artifacts, project_root),
            }
        )

    # The SAME fail-open one step further out: the guard above asks "are there
    # zero story files?", never "do the files COVER the in-scope keys?". A
    # PARTIALLY seeded Epic - a create-story pass that died halfway, or story
    # files authored for most of the sprint but not all - resolves a non-empty
    # story set, iterates the per-story checks over only the stories that exist,
    # and scores a clean zero-gap `ready`. The uncovered story then passes the
    # launch gate with no file: Stage 3 writes its acceptance criteria, but no
    # per-AC check below ever reads them, because a resumed session does not
    # re-run this kernel, so they reach Execute unchecked.
    #
    # Scoped deliberately so the two guards stay disjoint and neither
    # double-reports: this one fires only when SOME story files resolved (the
    # zero case is already the gap above) and only when the rollup actually named
    # keys (with no keys there is nothing to compare against, and inventing a gap
    # from an unknown denominator would block legitimate runs).
    coverage = _story_coverage(story_paths, scope_keys, rows)
    uncovered = coverage.uncovered
    if story_paths and uncovered:
        detail = "Epic %s is partially seeded: %d of %d in-scope stories resolve no story file under impl-artifacts: %s. Unresolved: %s" % (
            epic,
            len(uncovered),
            len(scope_keys),
            _rel(impl_artifacts, project_root),
            ", ".join(uncovered),
        )
        if coverage.below_parent:
            # A done parent's file would cover these but for their place: a
            # decomposed child sits above its parent's row, so each is a story
            # inserted later, or a child whose row is out of place.
            detail += ". Below a done parent's row, where the decomposition conventions never put a child: %s" % ", ".join(
                "%s (parent row %s)" % (key, parent) for key, parent in coverage.below_parent.items()
            )
        mechanical_gaps.append(
            {
                "id": "story_keys_uncovered",
                "kind": "story_keys_uncovered",
                "severity": "high",
                "detail": detail,
                # The create-story scaffold generates the missing story files,
                # exactly as it does for the empty set. A decomposed child
                # above its done parent's row never reaches this list: its
                # parent's file covers it.
                "remediable": True,
                "source": _rel(impl_artifacts, project_root),
            }
        )

    # The files the per-story checks below read: in-scope stories only. A
    # `--story` list that names no not-done row reads none: its
    # `story_not_in_scope` gaps already block, and falling back to every file
    # would bring back the done stories' gaps and candidates.
    if scope_keys or stories is None:
        scan_paths = _in_scope_story_files(story_paths, scope_keys, coverage.children)
    else:
        scan_paths = []

    stories_with_ac = 0
    ac_total = 0
    ac_machine_checkable = 0
    ac_with_named_verification = 0
    ac_anti_vacuous_twins = 0
    stories_with_gate_tag = 0
    nfr_thresholds_unsourced = 0
    orphaned_indices = 0

    # Pre-pass: read every story body once and build the DECLARED-id set the
    # orphaned-index check resolves citations against (story keys, story-file
    # stems, FR/NFR ids, test::node pointers in any story + the PRD). A citation
    # to an id absent from this set is the dangling never-green reference. The
    # main loop and whole-story catch-all below REUSE these
    # reads (story_reads), so a story's declared ids and its readability verdict
    # always come from the SAME read — closing the TOCTOU window where the
    # pre-pass could see a file a later read cannot and over-populate declared_ids.
    story_reads: dict[Path, str | None] = {
        story_path: _safe_read_text(story_path) for story_path in story_paths
    }
    story_bodies: dict[str, str] = {
        _rel(story_path, project_root): body
        for story_path, body in story_reads.items()
        if body is not None
    }
    prd_text = _safe_read_text(prd_path) if prd_path is not None else None
    declared_ids = _collect_declared_ids(story_bodies, story_keys, prd_text)

    for story_path in scan_paths:
        body = story_reads[story_path]
        rel = _rel(story_path, project_root)
        if body is not None:
            texts_by_rel[rel] = body
        if body is None:
            mechanical_gaps.append(
                {
                    "id": "story_unreadable:%s" % rel,
                    "kind": "unreadable_story",
                    "severity": "high",
                    "detail": "Story file unreadable: %s" % rel,
                    # An unreadable file is not machine-fixable from its own
                    # (unreadable) content.
                    "remediable": False,
                    "source": rel,
                }
            )
            continue

        if _GATE_ABILITY_RE.search(body):
            stories_with_gate_tag += 1

        ac_blocks = _split_ac_blocks(body)
        if ac_blocks:
            stories_with_ac += 1
        else:
            # The SAME empty-set fail-open as `no_in_scope_stories`, one level
            # down: that guard keys on the story file being absent, but a story
            # file that EXISTS and declares no AC iterates this per-AC loop zero
            # times too, so it contributes no gap and the Epic reads a clean
            # `ready` with stories_with_ac 0 - the verdict the launch gate treats
            # as go. A story with nothing to verify cannot be formally ready, so
            # count it as a gap like any other. This is also the landing zone of
            # the other guard's own remediation: the create-story scaffold that
            # clears `no_in_scope_stories` writes story files, and a stub it
            # leaves AC-less would otherwise flip remediable straight to ready.
            mechanical_gaps.append(
                {
                    "id": "story_without_ac:%s" % rel,
                    "kind": "story_without_ac",
                    "severity": "high",
                    "detail": "Story declares no acceptance criteria: %s" % rel,
                    # The create-story scaffold authors the AC section.
                    "remediable": True,
                    "source": rel,
                }
            )

        for line_no, block in ac_blocks:
            ac_total += 1
            src = "%s:%d" % (rel, line_no)

            if _ac_is_machine_checkable(block):
                ac_machine_checkable += 1

            has_named = bool(_NAMED_VERIFICATION_RE.search(block))
            has_twin = bool(_ANTI_VACUOUS_RE.search(block))
            if has_named:
                ac_with_named_verification += 1
            if has_twin:
                ac_anti_vacuous_twins += 1

            if not has_named:
                mechanical_gaps.append(
                    {
                        "id": "ac_missing_named_verification:%s" % src,
                        "kind": "ac_missing_named_verification",
                        "severity": "medium",
                        "detail": "AC has no named verification artifact: %s" % src,
                        # The canonical named-verification scaffold is machine-
                        # derivable from the AC shape.
                        "remediable": True,
                        "source": src,
                    }
                )
            if not has_twin:
                mechanical_gaps.append(
                    {
                        "id": "ac_missing_anti_vacuous_twin:%s" % src,
                        "kind": "ac_missing_anti_vacuous_twin",
                        "severity": "medium",
                        "detail": "AC has no anti-vacuous twin: %s" % src,
                        "remediable": True,
                        "source": src,
                    }
                )

            # Unsourced NFR threshold: a bare number+unit with no citation on the
            # same AC line is a number whose benchmark the kernel CANNOT decide
            # -> JUDGMENT (never auto-remediated).
            for nfr_line_no, nfr_line in enumerate(block.splitlines(), start=line_no):
                if _NFR_NUMBER_RE.search(nfr_line) and not _SOURCE_CITATION_RE.search(nfr_line):
                    nfr_thresholds_unsourced += 1
                    judgment_candidates.append(
                        {
                            "source": "%s:%d" % (rel, nfr_line_no),
                            "kind": "invented_nfr_threshold",
                            "why_machine_cannot_decide": "Numeric threshold "
                            "carries no cited source and is not marked "
                            "UNKNOWN/CONCERNS/deferred; the kernel cannot invent "
                            "a benchmark for it.",
                        }
                    )

            # Vacuous AC (permanent floor class 1): an assertion that holds no
            # matter what the code does (a tautology / "passes regardless"). The
            # kernel detects the vacuous SHAPE but cannot decide what the AC
            # SHOULD assert instead -> JUDGMENT, NEVER auto-remediable. Emitted
            # ONLY as a judgment_candidate (frozen: no remediable
            # path for this kind anywhere in this file).
            for vac_line_no, vac_line in enumerate(block.splitlines(), start=line_no):
                if _VACUOUS_AC_RE.search(vac_line):
                    judgment_candidates.append(
                        {
                            "source": "%s:%d" % (rel, vac_line_no),
                            "kind": "vacuous_ac",
                            "why_machine_cannot_decide": "Acceptance criterion "
                            "asserts a tautology that passes regardless of the "
                            "code under test; the kernel cannot decide what the "
                            "AC should assert instead.",
                        }
                    )

            # Orphaned never-green index (permanent floor class 3): an AC/trace row
            # CITES a verification/story/FR id that no story or test in the
            # resolved set DECLARES, so it can never go green. A regenerable
            # story/AC is a MECHANICAL gap (remediable: True via ucg-create-story);
            # an un-regenerable reference defaults to JUDGMENT (fail-closed). The
            # dangling token is carried verbatim in the detail.
            for orph_line_no, orph_line in enumerate(block.splitlines(), start=line_no):
                for token in _cited_index_tokens(orph_line):
                    if _norm_id(token) in declared_ids:
                        continue
                    orphaned_indices += 1
                    osrc = "%s:%d" % (rel, orph_line_no)
                    # A story/AC reference (an N-M story key) is regenerable from
                    # canonical scaffold -> MECHANICAL move; any other dangling
                    # index reference is un-regenerable -> JUDGMENT (default).
                    regenerable = bool(re.match(r"^\d+-\d+", token))
                    if regenerable:
                        mechanical_gaps.append(
                            {
                                "id": "orphaned_index:%s" % osrc,
                                "kind": "orphaned_index",
                                "severity": "high",
                                "detail": "AC/trace row cites a story/AC id no "
                                "story or test declares: %s" % token,
                                # A missing-but-regenerable story/AC stub is
                                # machine-derivable (ucg-create-story).
                                "remediable": True,
                                "source": osrc,
                            }
                        )
                    else:
                        judgment_candidates.append(
                            {
                                "source": osrc,
                                "kind": "orphaned_index",
                                "why_machine_cannot_decide": "AC/trace row cites "
                                "a verification/FR id no story or test declares "
                                "(%s); the kernel cannot decide what it should "
                                "resolve to." % token,
                            }
                        )

            # No-dark-pass catch-all: a detectable check-shaped signal the kernel
            # has no human-authored classification for defaults to JUDGMENT.
            for sig_line_no, sig_line in enumerate(block.splitlines(), start=line_no):
                if _UNCLASSIFIED_SIGNAL_RE.search(sig_line):
                    judgment_candidates.append(
                        {
                            "source": "%s:%d" % (rel, sig_line_no),
                            "kind": UNCLASSIFIED_KIND,
                            "why_machine_cannot_decide": "Detectable signal has "
                            "no human-authored mechanical classification; "
                            "defaults to judgment (no dark-pass).",
                        }
                    )

    # --- whole-story-level catch-all + gate-tag absence (reporting + judgment) ---
    for story_path in scan_paths:
        body = story_reads[story_path]
        if body is None:
            continue
        rel = _rel(story_path, project_root)
        # A story carrying the unclassified marker OUTSIDE an AC block still must
        # not dark-pass.
        for line_no, line in enumerate(body.splitlines(), start=1):
            if _UNCLASSIFIED_SIGNAL_RE.search(line):
                src = "%s:%d" % (rel, line_no)
                if not any(c["source"] == src for c in judgment_candidates):
                    judgment_candidates.append(
                        {
                            "source": src,
                            "kind": UNCLASSIFIED_KIND,
                            "why_machine_cannot_decide": "Detectable signal has "
                            "no human-authored mechanical classification; "
                            "defaults to judgment (no dark-pass).",
                        }
                    )

    # --- TEA leak check (location classification, reader-only) ---
    trace_root = _tea_trace_output_root(tea_config, project_root)
    leaked = _leaked_tea_artifacts(impl_artifacts, trace_root)
    tea_artifacts_in_source = len(leaked)
    for path in leaked:
        rel = _rel(path, project_root)
        mechanical_gaps.append(
            {
                "id": "leaked_tea_artifact:%s" % rel,
                "kind": "leaked_tea_artifact",
                "severity": "medium",
                "detail": "TEA artifact under the source/impl tree instead of "
                "the trace_output root: %s" % rel,
                # A path MOVE is machine-derivable + meaning-preserving.
                "remediable": True,
                "source": rel,
            }
        )

    # --- TEA-reader: read TEA's emitted fields under the trace_output root ---
    # Fires ONLY when a test-design artifact is located under trace_root (a TEA run is
    # in progress); otherwise no TEA artifact is read and nothing is added. With a
    # test-design present, an nfr-assessment is EXPECTED — a missing/unreadable one is
    # a FAILING signal (fail-closed), never neutral.
    test_design_path = _find_under(trace_root, "test-design")
    if test_design_path is not None and trace_root is not None:
        td_rel = _rel(test_design_path, project_root)
        td_text = _safe_read_text(test_design_path)
        if td_text is None:
            mechanical_gaps.append({
                "id": "test_design_unreadable:%s" % td_rel,
                "kind": "unreadable_tea_artifact",
                "severity": "high",
                "detail": "test-design artifact unreadable: %s" % td_rel,
                "remediable": False,
                "source": td_rel,
            })
        else:
            texts_by_rel[td_rel] = td_text
            td_gaps, td_candidates = _scan_test_design(td_text, td_rel)
            mechanical_gaps.extend(td_gaps)
            judgment_candidates.extend(td_candidates)

        nfr_path = _find_under(trace_root, "nfr-assessment")
        nfr_text = _safe_read_text(nfr_path) if nfr_path is not None else None
        if nfr_text is None:
            nfr_rel = (
                _rel(nfr_path, project_root) if nfr_path is not None
                else _rel(trace_root / "nfr-assessment.md", project_root)
            )
            mechanical_gaps.append({
                "id": "nfr_assessment_absent",
                "kind": "missing_nfr_assessment",
                "severity": "high",
                "detail": "nfr-assessment.md absent or unreadable under trace_output: %s" % nfr_rel,
                # Fail-closed (mirroring gate_eval.py nfr_status is None -> failing):
                # an absent/unreadable nfr assessment is a FAILING gap, never neutral.
                "remediable": False,
                "source": nfr_rel,
            })
        else:
            texts_by_rel[_rel(nfr_path, project_root)] = nfr_text
            judgment_candidates.extend(_scan_nfr_assessment(nfr_text, _rel(nfr_path, project_root)))

    # --- reporting ratios (NEVER compared to a cutoff) ---
    ac_machine_checkable_ratio = (
        (ac_machine_checkable / ac_total) if ac_total else 0.0
    )
    gate_ability_tag_coverage = (
        (stories_with_gate_tag / len(scan_paths)) if scan_paths else 0.0
    )

    checks = {
        "prd_present": prd_present,
        "adr_present": adr_present,
        "stories_with_ac": stories_with_ac,
        "ac_machine_checkable_ratio": ac_machine_checkable_ratio,
        "ac_with_named_verification": ac_with_named_verification,
        "ac_anti_vacuous_twins": ac_anti_vacuous_twins,
        "orphaned_indices": orphaned_indices,
        "tea_artifacts_in_source": tea_artifacts_in_source,
        "nfr_thresholds_unsourced": nfr_thresholds_unsourced,
        "gate_ability_tag_coverage": gate_ability_tag_coverage,
        # The keys a parent's story file covers, read as decomposed children:
        # reported, never gated on, since a story inserted above a done
        # parent's row reads the same way.
        "decomposed_children": [
            # POSIX on every platform: Define-Done opens it, and a test compares it.
            {"key": key, "parent_file": Path(_rel(parent_file, project_root)).as_posix(), "parent_row": parent_row}
            for key, parent_file, parent_row in coverage.children
        ],
    }

    # timing: close the mechanical-half window BEFORE the verdict is derived,
    # so the verdict can never depend on elapsed time.
    _mech_end_ns = time.monotonic_ns()

    mechanical_budget = len(mechanical_gaps)

    # Every candidate carries its line-free id, and a candidate the step-3 scan
    # answered (`--scan`: a red or a concern carrying its id and source) is judged: it no
    # longer sets judgment_required. A confirmed one is a RED the hard gate's
    # reds stream reads, and a cleared one is a concern, so neither is a
    # judgment still owed. With no scan, or one that cannot be read, nothing is
    # judged, and the verdict stays `blocked` while any candidate stands.
    for candidate in judgment_candidates:
        candidate["id"] = _candidate_id(candidate, texts_by_rel)
    scan_object, scan_report = _read_scan(scan)
    answers = _answers(scan_object)
    judged_candidates = [
        {**candidate, "judged_as": answers[(candidate["id"], candidate["source"])]}
        for candidate in judgment_candidates
        if (candidate["id"], candidate["source"]) in answers
    ]
    judgment_candidates = [
        candidate for candidate in judgment_candidates if (candidate["id"], candidate["source"]) not in answers
    ]
    if scan_report is not None:
        scan_report["answered"] = len(judged_candidates)
    judgment_required = bool(judgment_candidates)

    non_remediable = any(not g["remediable"] for g in mechanical_gaps)
    if judgment_required or non_remediable:
        verdict = "blocked"
    elif mechanical_budget == 0:
        verdict = "ready"
    else:
        verdict = "remediable"
    ready = verdict == "ready"

    # provenance: artifact_count is the cardinality of the readiness resolver's
    # located, readable artifact set — content-derived and deterministic for a
    # given fixture. timing keys are present on every payload (ready/remediable/
    # blocked alike); the verdict never gates the timing record.
    artifact_count = (
        (1 if _present_and_readable(prd_path) else 0)
        + (1 if _present_and_readable(adr_path) else 0)
        + (1 if (sprint_status is not None and sprint_text is not None) else 0)
        + sum(1 for body in story_reads.values() if body is not None)
        + (1 if test_design_path is not None else 0)
        + (1 if nfr_path is not None else 0)
    )
    _exit_ns = time.monotonic_ns()
    timing = {
        "wall_clock_ms": (_exit_ns - _entry_ns) / 1e6,
        "epic": epic,
        "artifact_count": artifact_count,
        "mechanical_ms": (_mech_end_ns - _mech_start_ns) / 1e6,
    }

    return {
        "ready": ready,
        "verdict": verdict,
        "mechanical_budget": mechanical_budget,
        "judgment_required": judgment_required,
        "mechanical_gaps": mechanical_gaps,
        "judgment_candidates": judgment_candidates,
        "judged_candidates": judged_candidates,
        "scan": scan_report,
        "checks": checks,
        "timing": timing,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mechanical readiness kernel for the /ucg-formalize gate "
        "(emits the readiness verdict JSON)."
    )
    parser.add_argument("--epic")
    parser.add_argument("--project-root")
    parser.add_argument("--planning-artifacts")
    parser.add_argument("--impl-artifacts")
    parser.add_argument("--tea-config")
    parser.add_argument(
        "--scan",
        help="The step-3 scan object (a file, or - for stdin; a relative path "
        "resolves against --project-root). A judgment candidate a red or a concern "
        "answers by its id in `candidate` and its `source` is judged and stops "
        "setting judgment_required; an unreadable scan, or one red_ids.py refuses, "
        "judges nothing.",
    )
    parser.add_argument(
        "--story",
        action="append",
        help="An in-scope story key, as its sprint-status row spells it (repeatable): "
        "the operator-scoped subset. Without it every not-done story of the Epic is in "
        "scope. A key that names no not-done story row of the Epic is a non-remediable gap.",
    )
    args = parser.parse_args(argv)

    # Invocation-error lane (exit 2): any required flag missing OR empty. argparse
    # exits 2 with a usage line, exactly as gate_eval.py's required=True does.
    required = (
        ("--epic", args.epic),
        ("--project-root", args.project_root),
        ("--planning-artifacts", args.planning_artifacts),
        ("--impl-artifacts", args.impl_artifacts),
        ("--tea-config", args.tea_config),
    )
    missing = [name for name, value in required if value is None or value.strip() == ""]
    if args.story is not None and any(value.strip() == "" for value in args.story):
        missing.append("--story")
    if missing:
        parser.error("the following arguments are required and non-empty: %s" % ", ".join(missing))
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    project_root = Path(args.project_root).expanduser()
    if not project_root.is_dir():
        print(
            json.dumps({"error": "project-root not found: %s" % project_root}),
            file=sys.stderr,
        )
        return 2
    project_root = project_root.resolve()

    planning_artifacts = _resolve(args.planning_artifacts, project_root)
    impl_artifacts = _resolve(args.impl_artifacts, project_root)
    tea_config = _resolve(args.tea_config, project_root)

    verdict = build_verdict(
        epic=args.epic,
        project_root=project_root,
        planning_artifacts=planning_artifacts,
        impl_artifacts=impl_artifacts,
        tea_config=tea_config,
        scan=args.scan if args.scan in (None, "-") else str(_resolve(args.scan, project_root)),
        stories=args.story,
    )
    print(json.dumps(verdict, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
