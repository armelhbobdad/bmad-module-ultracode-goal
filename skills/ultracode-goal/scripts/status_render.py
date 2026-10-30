#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Render what a run is doing, out of the files that run already produced.

This is the READ side over the spine's own artifacts. It answers "what is this
run doing right now" from eight sources and nothing else:

    | what              | source                                            |
    | heartbeat         | <impl-artifacts>/run-status.json                  |
    | decision log tail | the run folder's .decision-log.md                 |
    | ledger            | the deferred-work ledger                          |
    | escalations       | .escalation-<story>.md and escalation-<story>.json|
    | advanced stories  | <impl-artifacts>/sprint-status.yaml `done` rows   |
    | evidence owed     | <impl-artifacts>/.evidence-owed-<story>           |
    | re-gate owed      | <impl-artifacts>/.regate-<story>                  |
    | runs index        | the runs root's per-run folders                   |

STRICTLY READ-ONLY. It starts no run, attaches to no session, and opens no file
for output. The processes it starts are read-only and serve the optional
diff-viewer affordance below: the `which` probe, and, only when the viewer is
present and the repository reads, one `git log` per story listing the commits in
its range (through `gate_trail._git_log`). Their results reach stdout only and
are never recorded anywhere. Everything else is a read. That property is what
makes this safe to run against a LIVE run: a status read that touched the
artifacts would be a status read that changed the thing it reports on.

PROVENANCE LABELS. Two rendered fields are copied verbatim out of machine
output - the gate's own reason strings, and the turn counter the Stop hook
maintains. Both are suffixed `[machine-derived]`, and nothing else is. The
label carries information only because it is exclusive: label every row and it
says nothing, label none and a reader cannot tell a counted number from a
narrated one.

FAIL-SOFT ON SOURCES, FAIL-CLOSED ON INVOCATION. This borrows the split
`gate_trail.py` already draws, for the same reason. Every source is optional: an
absent, empty or unparseable file renders `n/a` and the render continues, because
a status read has no authority and failing closed here would turn a reporting gap
into a dead end. The invocation is not a source - a missing --impl-artifacts is
refused up front (exit 2, nothing rendered), because a render rooted at a
directory nobody named would describe some other run, or no run, while looking
exactly like a real answer.

    python3 status_render.py --impl-artifacts DIR [--deferred-work FILE] \
        [--run-dir DIR] [--runs-root DIR] [--repo DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_trail  # noqa: E402  (sibling script, path set above)
import preflight_check  # noqa: E402  (sibling script, path set above)

# Rendered wherever a source was absent, empty or unreadable.
NA = "n/a"

# The exclusive provenance suffix. Only the gate's copied reason strings and the
# hook-maintained turn counter carry it.
MACHINE = "[machine-derived]"

# A raw Stop-hook marker with no typed sidecar beside it, for a story that has
# not advanced. Either its gate has not ruled yet (Execute promotes the marker
# only when the gate escalates the story on its turn count), or the session
# died before Execute promoted it. Either way it may be a pending escalation.
UNPROMOTED = "escalation (unpromoted: no gate verdict yet, or the session ended before Execute promoted it)"

# The same raw marker for a story whose gate advanced it. Execute never promotes
# that one: the gate decided completion, and the overrun is a sizing note in the
# decision log, so nothing is pending and it is not listed as an escalation.
CEILING_NOTE = "turn ceiling reached; the story advanced at its gate, so this is a sizing note and nothing is pending"

# The other thin record: the typed sidecar IS on disk but is empty or does not
# parse, so there is nothing to render out of it. Distinct from UNPROMOTED
# because the typed file was written - two of the three escalation routes write
# it with no raw marker beside it - so "never promoted" would be a false account
# of a run that promoted just fine and then wrote badly.
UNREADABLE = "escalation (typed record present but unreadable)"

# An advanced story whose gate evidence commit a repo commit hook rejected. The
# gate escalates it as `evidence-commit-rejected` and leaves
# `.evidence-owed-<story>`, listing the paths it left staged, until a resume
# makes the commit, or finds the paths committed already (by the operator, or by
# a run that stopped between its commit and the marker's removal) and removes it
# without one. `/ucg-resolve` deletes the sidecar when it closes the escalation
# and leaves the marker, so from then on the marker is the one sign the commit
# was owed, and drive_epic.py stops `evidence-owed` on it rather than
# `all-done`. The render reads no git, so the line says what the marker held
# when it was written and both ways a resume settles it, never that the paths
# are still staged.
EVIDENCE_OWED = (
    "gate evidence commit owed when its marker was written, after a commit hook rejected it: "
    "a resume makes the commit, or removes the marker when it finds the paths committed already"
)

# A story whose `operator-evidence-owed` escalation `/ucg-resolve` closed. The
# close deletes the sidecar and writes `.regate-<story>`, holding `sha=` the
# assessed commit and `decision=` the closed id, and the gate deletes the marker
# once the story's next verdict is logged. Until then the heartbeat still shows
# the verdict that escalated the story, nothing renders under escalations, and
# the marker is the one sign the story still owes a gate.
REGATE_OWED = "re-gate owed: its operator-evidence-owed escalation was closed, and no gate verdict was logged since"

# The typed sidecar's four fields, rendered in this order.
SIDECAR_FIELDS = ("kind", "source", "decision_needed", "evidence")

# The optional diff viewer. Absent, nothing about it is rendered and the render
# is otherwise unchanged; present, each story that recorded a baseline commit
# gains a copy-paste line per commit in its range. It is an affordance, never a
# dependency.
VIEWER = "hunk"
MAX_VIEWER_LINES = 10


# --------------------------------------------------------------------------
# fail-soft reads
# --------------------------------------------------------------------------


def read_text(path: Path | None) -> str | None:
    """A file's text, or None when it is absent or unreadable."""
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def read_status(path: Path) -> dict | None:
    """The heartbeat snapshot as a dict, or None when there is no usable one.

    "Absent" and "present but empty" land here together on purpose. A zero-byte
    or `{}` heartbeat is what a run that crashed mid-write leaves behind, and it
    has to reach the same `n/a` path as a file that was never written - not a
    decode error. Only a file that is genuinely missing gets the distinct "no
    run" line, because that one means something different: no run has started.
    """
    text = read_text(path)
    if text is None or not text.strip():
        return None
    try:
        loaded = json.loads(text)
    except (ValueError, TypeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def field(status: dict | None, key: str) -> str:
    """One scalar heartbeat field, rendered, or `n/a`.

    Every field is optional. The heartbeat is overwritten in place at each spine
    step, so a partial snapshot is a real state and not a corrupt one - a reader
    that required a key would fail on a run that is simply early.
    """
    if not status:
        return NA
    value = status.get(key)
    if value is None or value == "":
        return NA
    return str(value)


# --------------------------------------------------------------------------
# derived rows
# --------------------------------------------------------------------------


def story_entries(status: dict | None) -> list[dict]:
    """The per-story entries, or an empty list when the snapshot carries none."""
    if not status:
        return []
    entries = status.get("stories")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def current_phase(status: dict | None) -> str:
    """Where the spine has the CURRENT story.

    Derived, not stored: the snapshot carries a phase per story entry and the id
    of the story it is on, so the current phase is the one belonging to that id.
    """
    if not status:
        return NA
    current = status.get("story")
    for entry in story_entries(status):
        if current and entry.get("story") == current:
            phase = entry.get("phase")
            if phase:
                return str(phase)
    return NA


def reason_lines(status: dict | None) -> list[str]:
    """The gate's reason strings, one rendered line each, all labeled.

    Copied across unedited from the gate result the spine last read. An absent
    or empty list renders one `n/a` line that keeps the label, because the field
    is machine-derived whether or not it currently holds a value.
    """
    reasons = (status or {}).get("last_reasons")
    if not isinstance(reasons, list) or not reasons:
        return [f"- Last reason: {NA} {MACHINE}"]
    return [f"- Last reason: {reason} {MACHINE}" for reason in reasons]


def budget_line(status: dict | None) -> str:
    """The turn counter, labeled. Read off the snapshot, never recomputed."""
    budget = (status or {}).get("budget_used")
    if not isinstance(budget, dict):
        return f"- Budget used: {NA} {MACHINE}"
    turns = budget.get("turns")
    ceiling = budget.get("max_turns")
    if turns is None and ceiling is None:
        return f"- Budget used: {NA} {MACHINE}"
    return (
        f"- Budget used: {NA if turns is None else turns} of "
        f"{NA if ceiling is None else ceiling} turns {MACHINE}"
    )


def ledger_rows(ledger: Path | None) -> list[dict]:
    """Every row of the deferred-work ledger, across all of its tables.

    The ledger accumulates one table per run, so a reader that stopped at the
    first table would silently drop every earlier run's parked work. Columns are
    located by header NAME, reusing the trail's parser, so a ledger that grows a
    column does not shift the values under a positional read.
    """
    text = read_text(ledger)
    if not text:
        return []
    rows: list[dict] = []
    for headers, raw_rows in gate_trail._tables(text):
        if "id" not in headers:
            continue
        for raw in raw_rows:
            row = {
                header: raw[index].strip()
                for index, header in enumerate(headers)
                if index < len(raw)
            }
            if row.get("id"):
                rows.append(row)
    return rows


def escalations(impl: Path) -> list[tuple[str, dict | None, Path]]:
    """Every escalation on disk, as (story, typed payload or None, marker path).

    Two files can carry one escalation: the raw marker the Stop hook writes, and
    the typed sidecar Execute promotes it into. The typed one wins where both
    exist. Where only the raw one does, the escalation is real but never got
    typed - which is a different thing to report, not a thing to hide.
    """
    found: dict[str, tuple[dict | None, Path]] = {}
    for marker in sorted(impl.glob(".escalation-*.md")):
        story = marker.name[len(".escalation-") : -len(".md")]
        if story:
            found[story] = (None, marker)
    for sidecar in sorted(impl.glob("escalation-*.json")):
        story = sidecar.name[len("escalation-") : -len(".json")]
        if not story:
            continue
        text = read_text(sidecar)
        payload: dict | None = None
        if text:
            try:
                loaded = json.loads(text)
            except (ValueError, TypeError):
                loaded = None
            if isinstance(loaded, dict):
                payload = loaded
        # An unreadable sidecar is not a promotion: the typed file exists but
        # says nothing, so fall back to whatever marker is on disk rather than
        # rendering an escalation with no content.
        if payload is None and story in found:
            continue
        found[story] = (payload, found.get(story, (None, sidecar))[1])
    return [(story, payload, path) for story, (payload, path) in sorted(found.items())]


def done_stories(impl: Path) -> set[str]:
    """Story keys whose `sprint-status.yaml` row reads `done`.

    The gate's advance route writes `done` for every story it advances, and the
    row outlives the heartbeat: `run-status.json` lists in-scope stories only, so
    a later invocation's snapshot no longer carries a story an earlier one
    advanced. Read with preflight's own block-scoped parser, so both agree.
    """
    text = read_text(impl / "sprint-status.yaml")
    if not text:
        return set()
    statuses = preflight_check._parse_development_status(text)
    return {key for key, value in statuses.items() if value == "done"}


def advanced_stories(status: dict | None, impl: Path) -> set[str]:
    """Stories the gate advanced: by this snapshot's verdict, or by a `done` row."""
    return {
        str(entry.get("story"))
        for entry in story_entries(status)
        if entry.get("story") and entry.get("verdict") in ("advance", "defer")
    } | done_stories(impl)


def ceiling_note_only(impl: Path, story: str, advanced: set[str]) -> bool:
    """True for an advanced story with the hook's raw marker and no typed sidecar."""
    return (
        story in advanced
        and (impl / f".escalation-{story}.md").is_file()
        and not (impl / f"escalation-{story}.json").exists()
    )


def owed_notes(impl: Path) -> dict[str, list[str]]:
    """Each story a marker says still owes work, with one line per marker.

    Both markers outlive the escalation that wrote them, so once `/ucg-resolve`
    has deleted its sidecar each is the one sign on disk that the story is not
    finished. The line names the marker and what it holds: for
    `.evidence-owed-<story>` the paths the gate left staged when it wrote it, one
    per line in the file, and for `.regate-<story>` its `sha=` and `decision=`
    values. An empty
    or unreadable marker still renders, with `n/a` for what it would have named.
    """
    owed: dict[str, list[str]] = {}
    for marker in sorted(impl.glob(".evidence-owed-*")):
        story = marker.name[len(".evidence-owed-") :]
        if not story or not marker.is_file():
            continue
        paths = [line.strip() for line in (read_text(marker) or "").splitlines() if line.strip()]
        owed.setdefault(story, []).append(f"{EVIDENCE_OWED} (`{marker.name}`: {', '.join(paths) or NA})")
    for marker in sorted(impl.glob(".regate-*")):
        story = marker.name[len(".regate-") :]
        if not story or not marker.is_file():
            continue
        # Read as preflight_check._regate_of reads it, without the git call that
        # tells a marker naming HEAD from a stale one.
        text = read_text(marker) or ""
        values = []
        for key in ("sha", "decision"):
            match = re.search(r"^%s=(.*)$" % key, text, re.MULTILINE)
            value = match.group(1).strip() if match else ""
            values.append(f"{key}={value or NA}")
        owed.setdefault(story, []).append(f"{REGATE_OWED} (`{marker.name}`: {', '.join(values)})")
    return owed


def known_runs(runs_root: Path | None) -> list[tuple[str, str]]:
    """Every run folder under the runs root, as (name, status).

    A folder counts as a run when it holds a decision log - that is the file the
    spine writes first and keeps writing, so it is the one marker present for
    every run at every stage. A run is `terminal` once it holds its run report
    and `live` until then; the report is written at finalize and nowhere else,
    which is exactly the distinction a reader wants. Sibling folders that are
    not runs (the queue directory, say) carry no decision log and are not runs
    to list.
    """
    if runs_root is None or not runs_root.is_dir():
        return []
    rows: list[tuple[str, str]] = []
    for folder in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        if not (folder / ".decision-log.md").is_file():
            continue
        state = "terminal" if (folder / "run-report.md").is_file() else "live"
        rows.append((folder.name, state))
    return rows


def decision_tail(run_dir: Path | None, lines: int = 12) -> list[str]:
    """The tail of the run's decision log - the run's own account of itself."""
    if run_dir is None:
        return []
    text = read_text(run_dir / ".decision-log.md")
    if not text:
        return []
    kept = [line.rstrip() for line in text.splitlines() if line.strip()]
    return kept[-lines:]


def viewer_available() -> bool:
    """Whether the optional diff viewer is on PATH.

    A probe, and only a probe: the answer changes what stdout carries and
    nothing else. It is never written to an artifact, because a run whose
    recorded evidence depended on which tools the reader happened to have
    installed would no longer be reproducible from the run itself.
    """
    try:
        probe = subprocess.run(
            ["which", VIEWER],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return False
    return probe.returncode == 0


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def render_runs_index(runs_root: Path | None) -> list[str]:
    rows = known_runs(runs_root)
    out = ["## Runs", ""]
    if not rows:
        out.append(f"- {NA}")
    else:
        for name, state in rows:
            out.append(f"- {name}: {state}")
    out.append("")
    return out


def render(
    *,
    impl: Path,
    run_dir: Path | None,
    runs_root: Path | None,
    ledger: Path,
    viewer: bool,
    repo: Path | None = None,
) -> str:
    """The whole render. Assembled once, printed once, written nowhere."""
    status_path = impl / "run-status.json"
    lines: list[str] = []

    if not status_path.exists():
        # The distinct case, and the only one that gets its own opening line: no
        # run has started here. Still a successful read - the answer "nothing is
        # running" is an answer, not a failure - so the runs index below still
        # renders and tells the reader which runs DO exist.
        lines.append(f"no run: {status_path} not found")
        lines.append("")
        lines.extend(render_runs_index(runs_root))
        return "\n".join(lines).rstrip() + "\n"

    status = read_status(status_path)

    lines.extend(
        [
            "# Run status",
            "",
            f"- Epic: {field(status, 'epic')}",
            f"- Story: {field(status, 'story')}",
            f"- Position: {field(status, 'index')} of {field(status, 'total')}",
            f"- Phase: {current_phase(status)}",
            f"- Last verdict: {field(status, 'last_verdict')}",
        ]
    )
    lines.extend(reason_lines(status))
    lines.append(budget_line(status))
    lines.extend(
        [
            f"- Re-loops this run: {field(status, 'reloop_count')}",
            f"- Profile: {field(status, 'profile')}",
            f"- Updated: {field(status, 'updated')}",
            "",
        ]
    )

    # Stories.
    lines.extend(["## Stories", ""])
    entries = story_entries(status)
    advanced = advanced_stories(status, impl)
    # An advanced story a later invocation's heartbeat no longer lists still
    # gets its note, on a line of its own after the listed stories.
    listed = {str(entry.get("story")) for entry in entries}
    unlisted_notes = [
        f"- {story}: {CEILING_NOTE} (`{marker.name}`)"
        for marker in sorted(impl.glob(".escalation-*.md"))
        if (story := marker.name[len(".escalation-") : -len(".md")])
        and story not in listed
        and ceiling_note_only(impl, story, advanced)
    ]
    # A story that still owes its gate evidence commit, or a re-gate, says so
    # the same way: on its row, or on a line of its own when it is not listed.
    owed = owed_notes(impl)
    unlisted_notes += [
        f"- {story}: {note}" for story, notes in sorted(owed.items()) if story not in listed for note in notes
    ]
    if not entries and not unlisted_notes:
        lines.append(f"- {NA}")
    for entry in entries:
        story = str(entry.get("story") or NA)
        lines.append(
            f"- {story}: phase={entry.get('phase') or NA} "
            f"verdict={entry.get('verdict') or NA} "
            f"attempts={entry.get('dev_attempts') if entry.get('dev_attempts') is not None else NA} "
            f"re-loops={entry.get('reloop_count') if entry.get('reloop_count') is not None else NA}"
        )
        if ceiling_note_only(impl, story, advanced):
            lines.append(f"  - {CEILING_NOTE} (`.escalation-{story}.md`)")
        lines.extend(f"  - {note}" for note in owed.get(story, []))
        sha = gate_trail.baseline_sha(impl, story)
        if sha:
            lines.append(f"  - baseline `{sha}`")
            if viewer:
                # The affordance has to point at THIS story's diff. The baseline
                # is the commit that preceded the story's work, so showing it
                # renders the previous story's diff - silently, since it is a
                # real diff from the same repo. The end commit `.commit-<story>`
                # records is the gate's evidence commit once one was made, which
                # holds the trace files and not the code, so where the repo is
                # readable every commit in the story's range gets its own line.
                # Only where no end commit was recorded is the anchor the sole
                # sha there is to hand the reader.
                # A range longer than a story ever needs (a baseline that is not
                # an ancestor of the end commit, say) falls back to one line
                # rather than printing hundreds.
                end = gate_trail.commit_sha(impl, story)
                in_range = gate_trail._git_log(repo, sha, end) if (repo and end) else None
                if in_range and len(in_range) > MAX_VIEWER_LINES:
                    in_range = None
                for commit in reversed(in_range or [end or sha]):
                    lines.append(f"  - {VIEWER} show {commit}")
    lines.extend(unlisted_notes)
    lines.append("")

    # Escalations.
    lines.extend(["## Escalations", ""])
    # An advanced story's raw turn-ceiling marker is a sizing note, shown on its
    # story row above, not a pending escalation.
    pending = [
        (story, payload, path)
        for story, payload, path in escalations(impl)
        if not ceiling_note_only(impl, story, advanced)
    ]
    if not pending:
        lines.append(f"- {NA}")
    for story, payload, path in pending:
        lines.append(f"### {story}")
        lines.append("")
        if payload is None:
            # Two different states arrive with no payload, and the path is the
            # discriminator: the Stop hook's raw marker means the escalation was
            # never promoted, while a typed sidecar that would not parse means
            # the record is there and cannot be read. Report what was observed.
            lines.append(f"- {UNREADABLE if path.suffix == '.json' else UNPROMOTED}")
            lines.append(f"- source: {path.name}")
        else:
            for key in SIDECAR_FIELDS:
                value = payload.get(key)
                lines.append(f"- {key}: {value if value else NA}")
        lines.append("")

    # Deferred work.
    lines.extend(["## Deferred work", ""])
    rows = ledger_rows(ledger)
    if not rows:
        lines.append(f"- {NA}")
    for row in rows:
        lines.append(
            f"- {row.get('id')} [{row.get('status') or NA}] "
            f"severity={row.get('severity') or NA} story={row.get('story') or NA}: "
            f"{row.get('reason') or NA}"
        )
    lines.append("")

    # Decision log tail.
    tail = decision_tail(run_dir)
    lines.extend(["## Decision log tail", ""])
    if not tail:
        lines.append(f"- {NA}")
    for line in tail:
        lines.append(f"    {line}")
    lines.append("")

    lines.extend(render_runs_index(runs_root))
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a run's current state from the artifacts it already produced."
    )
    parser.add_argument(
        "--impl-artifacts",
        required=True,
        help="Directory holding run-status.json, the escalation files and the baselines.",
    )
    parser.add_argument("--run-dir", help="This run's folder, holding its .decision-log.md.")
    parser.add_argument(
        "--runs-root",
        help="Directory holding the per-run folders. Defaults to <repo>/_bmad-output/ultracode-goal.",
    )
    parser.add_argument(
        "--deferred-work",
        help="The deferred-work ledger. Defaults to deferred-work.md in --impl-artifacts.",
    )
    parser.add_argument("--repo", default=".", help="Repository root, used to default --runs-root.")
    args = parser.parse_args(argv)

    impl = Path(args.impl_artifacts)
    repo = Path(args.repo)
    run_dir = Path(args.run_dir) if args.run_dir else None
    if args.runs_root:
        runs_root: Path | None = Path(args.runs_root)
    else:
        runs_root = repo / "_bmad-output" / "ultracode-goal"
    ledger = Path(args.deferred_work) if args.deferred_work else impl / "deferred-work.md"

    print(
        render(
            impl=impl,
            run_dir=run_dir,
            runs_root=runs_root,
            ledger=ledger,
            viewer=viewer_available(),
            repo=repo,
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
