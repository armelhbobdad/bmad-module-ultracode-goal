#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Mechanical readiness kernel for the /ucg-formalize gate.

PLUMBING ONLY. This script resolves an Epic's planning/impl/TEA artifact set the
way references/ingest-and-scope.md Stage 1 does, reads mechanical FACTS off the
artifacts on disk, and emits the FR-5 readiness verdict JSON. It computes the
ten-key `checks` fact map, counts per-finding `mechanical_gaps[]` (each carrying
a HUMAN-AUTHORED `remediable` boolean literal frozen at the emission site, the
preflight_check.py convention), flags `judgment_candidates[]`, and maps the pair
to a verdict. It NEVER decides a judgment gap — that read belongs to the LLM at
the SKILL/preflight layer (AD-7); this script only tells it what is mechanically
true on disk (INV-3) so one readiness definition serves both the standalone
command and the preflight clause (INV-9).

FAIL-CLOSED CONTRACT (deliberate — do not "relax", mirrors gate_eval.py's
`nfr_status is None -> treated as failing` posture, INV-4/NFR-2): every artifact
open is wrapped; a missing / unparseable / ambiguous artifact records a FAILING
gap (or a false `checks` value) and is NEVER treated as a neutral/null pass. Any
signal the kernel can DETECT but has no human-authored classification for
defaults to a JUDGMENT candidate (AD-1's no-dark-pass catch-all) — never a
silent pass, never an auto-remediable mechanical gap.

The two coverage ratios (`ac_machine_checkable_ratio`, `gate_ability_tag_coverage`)
are REPORTING values only. `mechanical_budget` is a per-item COUNT
(`len(mechanical_gaps)`), NEVER a ratio-vs-cutoff comparison — so NO numeric
threshold constant exists anywhere in this file (AD-1).

Verdict mapping (FR-6):
    mechanical_budget == 0 and no judgment candidates        -> ready
    gaps all remediable and no judgment candidates            -> remediable
    any judgment candidate / any non-remediable mechanical
    gap / any unreadable artifact                             -> blocked

Output: a single JSON object to stdout, serialized with sort_keys for
byte-stable output and carrying NO timestamp/uuid (so a re-run over the same
unchanged artifacts is byte-identical, NFR-1). Exit 0 whenever a payload is
produced (a non-ready verdict is a valid result, not an error). Exit 2 is
reserved for an invocation error where no useful payload can be produced (a
missing/empty required flag), the gate_eval.py invocation lane.

This is the KERNEL only. It emits the rich FR-5 verdict; the five-key headless
envelope is NOT this script's surface (AD-7, Story 1.3). The four Epic-11 floor
classes are seeded as fixtures in Story 1.2; this story builds the kernel they
run over.

    uv run formalize_check.py --epic <id> --project-root <p> \
        --planning-artifacts <p> --impl-artifacts <p> --tea-config <p>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# The story-status vocabulary BMad's sprint-planning writes into
# sprint-status.yaml; "done" stories are out of scope (in-scope = not-yet-done,
# ingest-and-scope.md Stage 1 rule 3).
STORY_STATUSES = ("done", "in-progress", "ready-for-dev", "review", "backlog")

# Filenames (case-insensitive substrings) that mark a PRD / ADR-architecture doc
# under the planning-artifacts root. Presence + parseability only (AD-6: reader,
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

# A check-shaped condition that signals a detectable-but-unclassified anomaly the
# kernel must NOT silently pass (AD-1 no-dark-pass catch-all). A story / AC line
# may opt a fixture into this lane with an explicit, machine-detectable marker
# the kernel has no human-authored classification for.
_UNCLASSIFIED_SIGNAL_RE = re.compile(r"UCG-UNCLASSIFIED-SIGNAL", re.IGNORECASE)

# The reserved catch-all sentinel kind (Story 1.2 floor AC6 reuses this).
UNCLASSIFIED_KIND = "unclassified_signal"


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
    file under the WRONG root is never found (AC5 wrong_root twin).
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
    """Story files under impl-artifacts whose name shares the Epic prefix.

    Stories for an Epic share its number prefix (ingest-and-scope.md:16). Sorted
    for determinism. When the rollup named not-done keys, prefer files matching
    one of those keys; otherwise fall back to the Epic-prefix glob.
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


def _split_ac_blocks(text: str) -> list[tuple[int, str]]:
    """Split a story body into (start_line, block_text) per acceptance criterion.

    An AC starts at a numbered list item under an "Acceptance Criteria" heading
    (``1. ...``) and runs until the next numbered item or a new heading. Returns
    1-based start line numbers for the `<path:line>` source.
    """
    lines = text.splitlines()
    in_ac = False
    blocks: list[tuple[int, list[str]]] = []
    for idx, raw in enumerate(lines):
        stripped = raw.strip()
        if re.match(r"^#+\s", raw):
            if re.search(r"acceptance criteria", stripped, re.IGNORECASE):
                in_ac = True
                continue
            # A different heading ends the AC section.
            if in_ac:
                in_ac = False
            continue
        if not in_ac:
            continue
        if re.match(r"^\d+\.\s", stripped):
            blocks.append((idx + 1, [raw]))
        elif blocks:
            blocks[-1][1].append(raw)
    return [(line_no, "\n".join(body)) for line_no, body in blocks]


def _ac_is_machine_checkable(block: str) -> bool:
    """Reporting heuristic: a deterministic, mechanically observable condition."""
    if _PROSE_HEDGE_RE.search(block) and not _MACHINE_CHECKABLE_RE.search(block):
        return False
    return bool(_MACHINE_CHECKABLE_RE.search(block))


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


def _leaked_tea_artifacts(
    impl_artifacts: Path, trace_root: Path | None, project_root: Path
) -> list[Path]:
    """TEA-shaped artifacts found under the impl/source tree (the wrong root).

    A TEA artifact correctly placed under trace_root is NOT a leak; one under
    impl-artifacts (and outside trace_root) is (Story 1.2 floor AC2 keys on the
    WRONG LOCATION, not on mere presence of a TEA file).
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
        if trace_root is not None and trace_root in path.parents:
            continue
        leaked.append(path)
    return leaked


# --- verdict assembly --------------------------------------------------------


def build_verdict(
    epic: str,
    project_root: Path,
    planning_artifacts: Path,
    impl_artifacts: Path,
    tea_config: Path,
) -> dict:
    mechanical_gaps: list[dict] = []
    judgment_candidates: list[dict] = []

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
        story_keys = _not_done_story_keys(sprint_text, epic)

    # --- per-story / per-AC scan ---
    story_paths = _story_files(impl_artifacts, epic, story_keys)
    stories_with_ac = 0
    ac_total = 0
    ac_machine_checkable = 0
    ac_with_named_verification = 0
    ac_anti_vacuous_twins = 0
    stories_with_gate_tag = 0
    nfr_thresholds_unsourced = 0

    for story_path in story_paths:
        body = _safe_read_text(story_path)
        rel = _rel(story_path, project_root)
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
                        # derivable from the AC shape (AD-1 (a)).
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
            # -> JUDGMENT (never auto-remediated; FR-5 / Story 1.2 floor AC4).
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

            # No-dark-pass catch-all: a detectable check-shaped signal the kernel
            # has no human-authored classification for defaults to JUDGMENT
            # (AD-1, INV-6/INV-4).
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
    for story_path in story_paths:
        body = _safe_read_text(story_path)
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
    leaked = _leaked_tea_artifacts(impl_artifacts, trace_root, project_root)
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
                # A path MOVE is machine-derivable + meaning-preserving (AD-1).
                "remediable": True,
                "source": rel,
            }
        )

    # --- reporting ratios (NEVER compared to a cutoff) ---
    ac_machine_checkable_ratio = (
        (ac_machine_checkable / ac_total) if ac_total else 0.0
    )
    gate_ability_tag_coverage = (
        (stories_with_gate_tag / len(story_paths)) if story_paths else 0.0
    )

    checks = {
        "prd_present": prd_present,
        "adr_present": adr_present,
        "stories_with_ac": stories_with_ac,
        "ac_machine_checkable_ratio": ac_machine_checkable_ratio,
        "ac_with_named_verification": ac_with_named_verification,
        "ac_anti_vacuous_twins": ac_anti_vacuous_twins,
        "orphaned_indices": 0,
        "tea_artifacts_in_source": tea_artifacts_in_source,
        "nfr_thresholds_unsourced": nfr_thresholds_unsourced,
        "gate_ability_tag_coverage": gate_ability_tag_coverage,
    }

    mechanical_budget = len(mechanical_gaps)
    judgment_required = bool(judgment_candidates)

    non_remediable = any(not g["remediable"] for g in mechanical_gaps)
    if judgment_required or non_remediable:
        verdict = "blocked"
    elif mechanical_budget == 0:
        verdict = "ready"
    else:
        verdict = "remediable"
    ready = verdict == "ready"

    return {
        "ready": ready,
        "verdict": verdict,
        "mechanical_budget": mechanical_budget,
        "judgment_required": judgment_required,
        "mechanical_gaps": mechanical_gaps,
        "judgment_candidates": judgment_candidates,
        "checks": checks,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mechanical readiness kernel for the /ucg-formalize gate "
        "(emits the FR-5 verdict JSON)."
    )
    parser.add_argument("--epic")
    parser.add_argument("--project-root")
    parser.add_argument("--planning-artifacts")
    parser.add_argument("--impl-artifacts")
    parser.add_argument("--tea-config")
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
    )
    print(json.dumps(verdict, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
