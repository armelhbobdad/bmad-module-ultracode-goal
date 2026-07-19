#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Synthesize the per-story evidence trail a finished Epic leaves behind.

Writes `gate-trail.md` into the run folder (a peer of `run-report.md` and
`.decision-log.md`) so a reader can audit a green Epic without re-running it.
Each in-scope story gets a section whose table traces five columns:

    acceptance criterion -> planned test -> result -> gate verdict -> commit

PURE SYNTHESIS. Every cell is read out of an artifact the run already wrote;
this script forms no judgment of its own and produces no verdict:

    | column                | production source        | light source            |
    | acceptance criterion  | acceptance checklist     | trace report coverage   |
    | planned test          | acceptance checklist     | trace report coverage   |
    | result                | acceptance checklist     | trace report coverage   |
    | gate verdict          | the recorded verdict, else gate_status mapped   |
    |                       | through gate_eval.GATE_VERDICT                  |
    | commit                | git log over the story's baseline range         |

The verdict cell is `gate_eval.GATE_VERDICT[gate_status]` and nothing else. An
unrecognized gate_status is rendered verbatim rather than re-classified, and the
production AND is NEVER re-applied here: it already ran when the gate decided,
and re-running it at finalize would be a second, later judgment. When the run
recorded its own verdict for a story (a fenced JSON object carrying a `verdict`
key under that story's heading in `.decision-log.md`), that recorded verdict
wins over the mapped one, because it is what the run actually acted on -
including any downgrade the gate applied at decision time.

FAIL-SOFT. Every source is optional. A missing, short or unparseable file
renders `n/a` in its cell and the synthesis continues. This is the opposite of
`gate_eval.py`, which fails closed, and the asymmetry is deliberate: the gate has
authority and must not advance on evidence it could not read, while this report
has none - failing closed here would turn a reporting bug into a blocked run.

That covers the SOURCES, not the invocation. The story list is an argument, not
an artifact to be read: with no ids this script would write a well-formed
document carrying no sections at all, an evidence trail that traces nothing and
that the stage then names in the run report as delivered evidence. So the ids
are refused up front - exit 2, nothing written - which is the invocation-error
lane `--run-dir` and `--profile` already occupy, and costs a re-issued command
rather than a run.

Gate-artifact resolution is imported from `gate_eval.py` rather than
re-implemented, so the trail always describes the same file that decided.

    python3 gate_trail.py --run-dir DIR --impl-artifacts DIR --trace-output DIR \
        --profile light --story 4-1 --story 4-2
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_eval  # noqa: E402  (sibling script, path set above)

OUTPUT_NAME = "gate-trail.md"

# The five columns this trail exists to trace. Every rendered row carries all
# five: drop one and the trail stops being an audit trail.
COLUMNS = (
    "Acceptance criterion",
    "Planned test",
    "Result",
    "Gate verdict",
    "Commit",
)

# Rendered in any cell whose source artifact is absent or unreadable.
NA = "n/a"

# Column headers are matched by NAME, never by position: the house trace table
# carries an extra split column that a future trace author may drop, and a
# positional parser would then read the wrong column as the planned test.
_AC_HEADERS = {"ac", "acs", "ac #", "id", "criterion", "criteria", "acceptance criterion"}
_TEST_HEADERS = {"verification", "planned test", "planned tests", "test", "tests", "named verification"}
_RESULT_HEADERS = {"status", "result", "outcome"}

_STORY_HEADING = re.compile(r"^#{2,4}\s+story\s+([0-9][\w.\-]*)", re.IGNORECASE | re.MULTILINE)
_JSON_FENCE = re.compile(r"```(?:json)?\s*\n(\{.*?\})\s*\n```", re.DOTALL)


# --------------------------------------------------------------------------
# fail-soft reads
# --------------------------------------------------------------------------


def read_text(path: Path | None) -> str | None:
    """Return a file's text, or None when it is absent or unreadable.

    The fail-soft boundary for every source this script reads. Removing it turns
    a missing artifact into a raised error instead of an `n/a` cell.
    """
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def read_json(path: Path | None) -> dict | None:
    """Return a JSON object from a file, or None when absent or unparseable."""
    text = read_text(path)
    if text is None:
        return None
    try:
        loaded = json.loads(text)
    except (ValueError, TypeError):
        return None
    return loaded if isinstance(loaded, dict) else None


# --------------------------------------------------------------------------
# markdown table parsing (by header name)
# --------------------------------------------------------------------------


def _cells(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [c.strip() for c in stripped.split("|")]


def _is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:|-]*-[\s:|-]*\|?", line.strip())) and "-" in line


def _normalize_header(cell: str) -> str:
    return cell.strip().strip("*`_").strip().lower()


def _tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """Every pipe table in the text as (headers, rows)."""
    out: list[tuple[list[str], list[list[str]]]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines) - 1:
        line = lines[index]
        if line.strip().startswith("|") and _is_separator(lines[index + 1]):
            headers = [_normalize_header(c) for c in _cells(line)]
            rows: list[list[str]] = []
            cursor = index + 2
            while cursor < len(lines) and lines[cursor].strip().startswith("|"):
                rows.append(_cells(lines[cursor]))
                cursor += 1
            out.append((headers, rows))
            index = cursor
            continue
        index += 1
    return out


def criterion_rows(text: str | None) -> list[tuple[str, str, str]]:
    """Extract (criterion, planned test, result) triples from a markdown table.

    The first table carrying a recognizable criterion column wins. Columns are
    located by header name; any column the table does not carry renders `n/a`.
    """
    if not text:
        return []
    for headers, rows in _tables(text):
        try:
            ac_at = next(i for i, h in enumerate(headers) if h in _AC_HEADERS)
        except StopIteration:
            continue
        test_at = next((i for i, h in enumerate(headers) if h in _TEST_HEADERS), None)
        result_at = next((i for i, h in enumerate(headers) if h in _RESULT_HEADERS), None)

        def pick(row: list[str], at: int | None) -> str:
            if at is None or at >= len(row):
                return NA
            return row[at].strip() or NA

        extracted: list[tuple[str, str, str]] = []
        for row in rows:
            if ac_at >= len(row):
                continue
            criterion = row[ac_at].strip()
            if not criterion:
                continue
            extracted.append((criterion, pick(row, test_at), pick(row, result_at)))
        if extracted:
            return extracted
    return []


# --------------------------------------------------------------------------
# per-story sources
# --------------------------------------------------------------------------


def numeric_prefix(story: str) -> str:
    """The leading numeric components of a story id (`4-1-some-slug` -> `4-1`)."""
    parts = [p for p in re.split(r"[-._]", (story or "").strip()) if p]
    lead = []
    for part in parts:
        if not part.isdigit():
            break
        lead.append(part)
    return "-".join(lead)


def checklist_path(test_artifacts: Path | None, story: str) -> Path | None:
    """The story's acceptance checklist, which exists in production runs only."""
    if test_artifacts is None:
        return None
    return test_artifacts / f"atdd-checklist-{story}.md"


def trace_report_path(trace_output: Path | None, story: str) -> Path | None:
    """The story's trace report, matched by id components the way the gate does."""
    if trace_output is None or not trace_output.is_dir():
        return None
    candidates = [
        report
        for report in sorted(trace_output.glob("*.md"))
        if gate_eval._stem_matches_story(report.stem, story)
        or gate_eval._stem_matches_story(report.stem, numeric_prefix(story) or story)
    ]
    return candidates[0] if candidates else None


def gate_status_for(trace_output: Path | None, story: str) -> tuple[str | None, str | None]:
    """Return (gate_status, source filename) for a story, or (None, None).

    Resolution is delegated to the gate's own resolver so the trail can never
    describe a different file than the one that decided. A gate artifact that is
    absent yields None - the cell renders `n/a` rather than being classified.

    One narrowing on top of that resolver, and it is load-bearing. In a shared
    directory holding many stories' artifacts, the resolver's last-resort
    fallback is an unscoped one: for a story that wrote no artifacts at all it
    can hand back a DIFFERENT story's gate file, which would render an
    unevaluated story with someone else's verdict - silently green. So a
    resolved artifact is only accepted when it is named for this story, or when
    this story has its own trace report in the directory (a single-story
    directory, or a report that hints at the file by name). Anything else is
    read as absent.
    """
    if trace_output is None or not trace_output.is_dir():
        return None, None
    scope = numeric_prefix(story) or story
    own_trace = trace_report_path(trace_output, story) is not None

    def belongs(path: Path) -> bool:
        return own_trace or gate_eval._stem_matches_story(path.stem, scope)

    # The resolver itself returns None when this story is absent from a
    # per-story-named directory; that is already "absent", so it skips the read.
    gate_file = gate_eval._resolve_gate_file(trace_output, scope)
    if gate_file is not None and belongs(gate_file):
        slim = read_json(gate_file)
        if slim is not None and slim.get("gate_status"):
            return str(slim["gate_status"]).strip(), gate_file.name

    summary_file = gate_eval._resolve_summary_file(trace_output, scope)
    if belongs(summary_file):
        summary = read_json(summary_file)
        if summary is not None and summary.get("gate_status"):
            return str(summary["gate_status"]).strip(), summary_file.name
    return None, None


def verdict_for(gate_status: str | None, recorded: str | None) -> str:
    """The verdict cell: recorded if the run wrote one, else the gate's own map.

    Never re-derived and never re-judged - an unrecognized gate_status renders
    verbatim instead of being defaulted into a classification this script would
    then own.
    """
    if recorded:
        return recorded
    if not gate_status:
        return NA
    return gate_eval.GATE_VERDICT.get(gate_status.upper(), gate_status)


def recorded_verdicts(decision_log: Path | None) -> dict[str, str]:
    """Verdicts the run recorded per story in its decision log.

    A story heading followed by a fenced JSON object carrying a `verdict` key is
    read as the verdict the run acted on. Prose headings without such a block
    contribute nothing, which is the common case.
    """
    text = read_text(decision_log)
    if not text:
        return {}
    out: dict[str, str] = {}
    matches = list(_STORY_HEADING.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        span = text[match.end() : end]
        for fence in _JSON_FENCE.finditer(span):
            try:
                payload = json.loads(fence.group(1))
            except (ValueError, TypeError):
                continue
            if isinstance(payload, dict) and payload.get("verdict"):
                out[numeric_prefix(match.group(1)) or match.group(1)] = str(payload["verdict"])
                break
    return out


def baseline_sha(impl_artifacts: Path | None, story: str) -> str | None:
    """The story's recorded baseline commit, or None when it was never written."""
    if impl_artifacts is None:
        return None
    text = read_text(impl_artifacts / f".baseline-{story}")
    if not text:
        return None
    for line in text.splitlines():
        match = re.search(r"\b([0-9a-f]{7,40})\b", line.strip(), re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _git_log(repo: Path, start: str, end: str) -> list[str] | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "log", "--format=%h", f"{start}..{end}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def commit_cell(repo: Path, start: str | None, end: str | None) -> str:
    """The commits a story's baseline range contains.

    A story with no recorded baseline renders `n/a`. A readable but empty range
    is reported as such and nothing more: an observation for the reader, never a
    verdict and never a denial.
    """
    if not start:
        return NA
    end_ref = end or "HEAD"
    span = f"`{start[:7]}..{end[:7] if end else 'HEAD'}`"
    shas = _git_log(repo, start, end_ref)
    if shas is None:
        return span
    if not shas:
        return f"{span} (no commits in range)"
    return ", ".join(f"`{sha}`" for sha in shas)


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _escape(cell: str) -> str:
    return cell.replace("|", "\\|").strip() or NA


def story_section(
    story: str,
    *,
    profile: str,
    impl_artifacts: Path | None,
    test_artifacts: Path | None,
    trace_output: Path | None,
    repo: Path,
    recorded: dict[str, str],
    range_end: str | None,
) -> str:
    checklist = checklist_path(test_artifacts, story) if profile == "production" else None
    checklist_text = read_text(checklist)
    trace = trace_report_path(trace_output, story)
    trace_text = read_text(trace)

    rows = criterion_rows(checklist_text)
    criteria_source = checklist.name if (rows and checklist is not None) else None
    if not rows:
        rows = criterion_rows(trace_text)
        criteria_source = trace.name if (rows and trace is not None) else criteria_source

    gate_status, gate_source = gate_status_for(trace_output, story)
    verdict = verdict_for(gate_status, recorded.get(numeric_prefix(story) or story))
    start = baseline_sha(impl_artifacts, story)
    commits = commit_cell(repo, start, range_end)

    lines = [f"## Story {story}", ""]
    lines.append(f"- Criteria and planned tests: {criteria_source or NA}")
    lines.append(f"- Gate artifact: {gate_source or NA} (gate status `{gate_status or NA}`)")
    lines.append(
        "- Verdict source: recorded in the decision log"
        if recorded.get(numeric_prefix(story) or story)
        else "- Verdict source: the gate artifact's status, mapped by the gate's own table"
    )
    lines.append(f"- Baseline: `{start}`" if start else f"- Baseline: {NA}")
    lines.append("")
    lines.append(_row(list(COLUMNS)))
    lines.append(_row(["---"] * len(COLUMNS)))
    if not rows:
        lines.append(_row([NA, NA, NA, _escape(verdict), commits]))
    else:
        for criterion, planned, result in rows:
            lines.append(
                _row(
                    [
                        _escape(criterion),
                        _escape(planned),
                        _escape(result),
                        _escape(verdict),
                        commits,
                    ]
                )
            )
    lines.append("")
    return "\n".join(lines)


def render(
    stories: list[str],
    *,
    epic: str,
    profile: str,
    impl_artifacts: Path | None,
    test_artifacts: Path | None,
    trace_output: Path | None,
    decision_log: Path | None,
    repo: Path,
) -> str:
    recorded = recorded_verdicts(decision_log)
    baselines = {story: baseline_sha(impl_artifacts, story) for story in stories}

    header = [
        f"# Gate trail: Epic {epic}",
        "",
        "Synthesized at finalize from the artifacts this run already wrote: the per-story "
        "acceptance checklist (production runs), the trace report, the gate decision file, "
        "the decision log and the recorded baseline commits.",
        "",
        "It renders the gate's verdicts; it never forms one. A cell whose source artifact "
        f"was absent or unreadable reads `{NA}`.",
        "",
        f"- Profile: {profile}",
        f"- Stories: {len(stories)}",
        "",
    ]

    sections = []
    for index, story in enumerate(stories):
        # The range end is the next story's baseline (its start is this story's
        # end), and HEAD for the last story in sprint order.
        range_end = None
        for later in stories[index + 1 :]:
            if baselines.get(later):
                range_end = baselines[later]
                break
        sections.append(
            story_section(
                story,
                profile=profile,
                impl_artifacts=impl_artifacts,
                test_artifacts=test_artifacts,
                trace_output=trace_output,
                repo=repo,
                recorded=recorded,
                range_end=range_end,
            )
        )
    return "\n".join(header + sections).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Synthesize the per-story evidence trail into the run folder."
    )
    parser.add_argument("--run-dir", required=True, help="The run folder; the trail is written here.")
    parser.add_argument("--profile", required=True, choices=["light", "production"])
    parser.add_argument(
        "--story",
        action="append",
        default=[],
        dest="stories",
        required=True,
        help="A story id, repeatable, in sprint order. At least one is required.",
    )
    parser.add_argument("--impl-artifacts", help="Directory holding the recorded baselines.")
    parser.add_argument("--trace-output", help="Directory holding the trace and gate artifacts.")
    parser.add_argument(
        "--test-artifacts",
        help="Test-artifacts root holding the acceptance checklists. "
        "Defaults to the parent of --trace-output.",
    )
    parser.add_argument(
        "--decision-log",
        help="Path to this run's decision log. Defaults to .decision-log.md in the run folder.",
    )
    parser.add_argument("--epic", help="Epic id for the heading. Defaults to the run folder name.")
    parser.add_argument("--repo", default=".", help="Repository root for the commit range.")
    args = parser.parse_args(argv)

    # The same invocation-error lane, for the same error wearing a value.
    # `required=True` catches "no ids at all"; a blank id otherwise renders an
    # anonymous `## Story ` section of nothing but `n/a` - a story that reads as
    # gated and empty rather than as never named.
    if any(not story.strip() for story in args.stories):
        parser.error("--story values must be non-empty story ids")

    run_dir = Path(args.run_dir)
    trace_output = Path(args.trace_output) if args.trace_output else None
    if args.test_artifacts:
        test_artifacts: Path | None = Path(args.test_artifacts)
    else:
        test_artifacts = trace_output.parent if trace_output else None
    decision_log = Path(args.decision_log) if args.decision_log else run_dir / ".decision-log.md"
    epic = args.epic or re.sub(r"^epic-", "", run_dir.name) or run_dir.name

    text = render(
        list(args.stories),
        epic=epic,
        profile=args.profile,
        impl_artifacts=Path(args.impl_artifacts) if args.impl_artifacts else None,
        test_artifacts=test_artifacts,
        trace_output=trace_output,
        decision_log=decision_log,
        repo=Path(args.repo),
    )

    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / OUTPUT_NAME
    out.write_text(text, encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
