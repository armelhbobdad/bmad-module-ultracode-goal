#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""The single headless-envelope adapter.

`build_headless_envelope` adapts a blocker source — either an ordered blocker list
or `formalize_check.py`'s formalize verdict object — into the ONE canonical five-key
headless envelope (status, skill, decision_log, report, deferred_work) plus the
conditional `reason`, exactly the shape the preflight step-4 block and the
ucg-formalize SKILL.md block document. The formalize verdict stays a SEPARATE
script-layer object — it is never nested into the envelope (two-layer
separation). A formalize RED therefore routes through the IDENTICAL channel as a
semantic-scan RED; no formalize-specific key, no formalize-specific status.

`reason` is POSITIONAL: the one-line rendering of `blockers[0]` (the caller-supplied
order; reds carry no severity field), flattened to a single physical line. Every
formalize RED is also written to the run's `.decision-log.md`, so a headless
block is never silent and the one-line reason reconstructs to its full finding. An
empty blocker list cannot make a block silent either: it is a fail-closed signal in
its own right, so the adapter substitutes an explicit no-recorded-blocker blocker
rather than emitting a blocked envelope whose `reason` is the empty string.

Both terminal shapes also land on disk at `<impl-artifacts>/run-result.json`, so an
automator reads a file instead of scraping the transcript. `render_envelope` is the
ONE serialization: the string it returns is what the file holds and what the run
emits on stdout, so the two are byte-identical by construction rather than by
convention. The write is best-effort: it never raises, because a terminal emit that
died on an unwritable directory would convert a clean exit into a crash.

Stdlib-only. Fail-closed (mirroring gate_eval.py `nfr_status is None -> failing`):
a missing / unparseable formalize verdict is treated as a blocking signal, never neutral.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SKILL = "ultracode-goal"
# The five always-present canonical keys; `reason` is the conditional sixth.
CANONICAL_KEYS = ("status", "skill", "decision_log", "report", "deferred_work")
# Path-pinned and overwrite-in-place, exactly like run-status.json.
RESULT_FILENAME = "run-result.json"


def _one_line(blocker: dict) -> str:
    """Render a blocker {source, decision_needed} as ONE physical line (no newline)."""
    source = str(blocker.get("source", "")).strip()
    decision = str(blocker.get("decision_needed", "")).strip()
    text = f"{source} - {decision}" if source and decision else (source or decision)
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip()


def fr5_blockers(verdict: object) -> list[dict]:
    """Extract an ordered blocker list from a formalize verdict — fail-closed.

    A missing / non-dict / unparseable verdict, or one whose ``verdict`` is not the
    terminal ``ready``, is a BLOCKING signal: blocked when ``verdict == 'blocked'``
    (its judgment_candidates are the reds) or on an unreadable verdict. ``ready`` and
    ``remediable`` (with no reds) yield no blockers.
    """
    if not isinstance(verdict, dict):
        return [{"source": "formalize", "decision_needed": "formalize verdict unreadable or absent", "kind": "unreadable"}]
    v = verdict.get("verdict")
    if v == "blocked":
        cands = verdict.get("judgment_candidates") or []
        blockers = [
            {
                "source": c.get("source", ""),
                "decision_needed": c.get("why_machine_cannot_decide") or c.get("decision_needed", ""),
                "kind": c.get("kind", ""),
            }
            for c in cands
        ]
        # A blocked verdict with no candidates is still a block (fail-closed).
        return blockers or [{"source": "formalize", "decision_needed": "formalize verdict is blocked", "kind": "blocked"}]
    if v not in ("ready", "remediable"):
        return [{"source": "formalize", "decision_needed": "formalize verdict is unreadable or missing", "kind": "unreadable"}]
    return []


def _append_to_log(decision_log: str, lines: list[str]) -> None:
    Path(decision_log).parent.mkdir(parents=True, exist_ok=True)
    with open(decision_log, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _append_line_to_log(decision_log: str, line: str) -> None:
    _append_to_log(decision_log, ["", line])


def _append_blockers_to_log(decision_log: str, blockers: list[dict]) -> None:
    """Write the full formalize/semantic blockers (source:line + decision_needed) to the log."""
    lines = ["", "## Headless blocked envelope - full blocker list", ""]
    for b in blockers:
        lines.append(f"- {b.get('source', '')} :: {b.get('decision_needed', '')}")
    _append_to_log(decision_log, lines)


def render_envelope(envelope: dict) -> str:
    """The ONE serialization of an envelope.

    Whatever goes to stdout and whatever goes into ``run-result.json`` is THIS string,
    produced once and handed to both sinks. Serializing twice with independently-chosen
    ``json.dumps`` kwargs is the divergence this single function exists to prevent.
    No trailing newline: the file holds exactly the emitted bytes and nothing more.
    """
    return json.dumps(envelope, ensure_ascii=False)


def _resolved_impl_artifacts(impl_artifacts) -> Path | None:
    """The impl-artifacts dir, or None when it has not resolved yet.

    A block that fires before the config resolves (no BMAD project, so no
    ``customize.toml`` scalar to resolve) has nowhere to put the file. None, empty, and
    a still-unsubstituted ``{...}`` placeholder are all that same unresolved case.
    """
    if impl_artifacts is None:
        return None
    text = str(impl_artifacts).strip()
    if not text or ("{" in text and "}" in text):
        return None
    return Path(text)


def write_run_result(text: str, impl_artifacts, decision_log: str | None = None) -> Path | None:
    """Write the serialized envelope to ``<impl-artifacts>/run-result.json``.

    Returns the path written, or None when impl-artifacts has not resolved (the
    pre-resolution block, whose stdout envelope is the sole output) or when the write
    failed. **Never raises**: a failed write is logged and the run still emits, because
    a terminal emit that crashed on an unwritable directory is strictly worse than one
    that only reached stdout.
    """
    target_dir = _resolved_impl_artifacts(impl_artifacts)
    if target_dir is None:
        return None
    path = target_dir / RESULT_FILENAME
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        if decision_log:
            try:
                _append_line_to_log(decision_log, f"WARN run-result-write-failed :: {path} :: {exc}")
            except OSError:
                pass  # the log is unwritable too; the stdout emit still stands
        return None
    return path


def build_headless_envelope(
    source,
    decision_log,
    *,
    write_log: bool = True,
    impl_artifacts=None,
    report=None,
    deferred_work=None,
) -> dict:
    """Adapt a blocker source into the canonical BLOCKED envelope.

    THIS IS THE BLOCKED ADAPTER. Its complete sibling is
    :func:`build_complete_envelope`, and the name here is historical - see the
    :data:`build_blocked_envelope` alias below, which is what new callers should
    read for.

    ``source`` is either an ordered list of blocker dicts (each {source, decision_needed})
    or a formalize verdict dict (adapted via :func:`fr5_blockers`). Returns exactly the five
    canonical keys plus ``reason`` (the one-line rendering of ``blockers[0]``).

    ``report`` / ``deferred_work`` are optional because a blocked exit is not
    always artifact-less. A run that ESCALATED reached Stage 6 and produced a run
    report and a gate trail, so hard-coding them to ``None`` under-reported what
    was on disk for the one run most worth reading. They stay ``None`` when the
    block happened before those artifacts existed, which is the earlier block
    points' case.

    When ``impl_artifacts`` resolves, the same bytes are also written to
    ``run-result.json`` there.
    """
    # Refuse a complete-shaped mapping BEFORE any side effect. Handed one, the
    # fail-closed branch below reads no blockers from it, SYNTHESISES one, and
    # then (a) appends a fabricated "formalize verdict is unreadable or missing"
    # line to the decision log and (b) writes a `blocked` run-result.json over a
    # successful run - corrupting the two artifacts an automator and a resume
    # read, silently and with no exception. Observed in the field. Raising is
    # right even though the emit path is otherwise never-raise: this is a caller
    # error, and the alternative is a wrong answer written to disk.
    if isinstance(source, dict) and str(source.get("status", "")).strip() == "complete":
        raise ValueError(
            "build_headless_envelope is the BLOCKED adapter; a complete-shaped "
            "mapping belongs in build_complete_envelope"
        )
    blockers = source if isinstance(source, list) else fr5_blockers(source)
    decision_log = str(decision_log)
    if not blockers:
        # Fail-closed: a blocked envelope always carries a cause. An empty blocker list
        # is itself the anomaly worth naming, not a licence to emit an empty `reason`
        # and write nothing to the log.
        blockers = [
            {
                "source": "headless",
                "decision_needed": "blocked with no recorded blocker",
                "kind": "unreadable",
            }
        ]
    reason = _one_line(blockers[0])
    if write_log:
        _append_blockers_to_log(decision_log, blockers)
    envelope = {
        "status": "blocked",
        "skill": SKILL,
        "decision_log": decision_log,
        "report": str(report) if report else None,
        "deferred_work": str(deferred_work) if deferred_work else None,
        "reason": reason,
    }
    write_run_result(render_envelope(envelope), impl_artifacts, decision_log)
    return envelope


# The name this adapter should have had. `build_headless_envelope` reads as the
# adapter for headless generally, which is how a complete-shaped mapping came to
# be handed to the blocked one.
build_blocked_envelope = build_headless_envelope


def build_complete_envelope(decision_log, *, report=None, deferred_work=None, impl_artifacts=None) -> dict:
    """Build the canonical COMPLETE envelope: exactly the five canonical keys.

    ``reason`` is not in this dict at all. It is the conditional sixth key of a BLOCKED
    exit, so a complete emit omits it rather than carrying it as ``null`` — a caller must
    read `reason` only when `status` is `blocked`. ``report`` / ``deferred_work`` stay
    ``null`` when that artifact was not produced, so the five are KeyError-safe.
    """
    envelope = {
        "status": "complete",
        "skill": SKILL,
        "decision_log": str(decision_log),
        "report": str(report) if report else None,
        "deferred_work": str(deferred_work) if deferred_work else None,
    }
    write_run_result(render_envelope(envelope), impl_artifacts, envelope["decision_log"])
    return envelope
