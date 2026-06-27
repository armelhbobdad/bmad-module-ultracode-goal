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
block is never silent and the one-line reason reconstructs to its full finding.

Stdlib-only. Fail-closed (mirroring gate_eval.py `nfr_status is None -> failing`):
a missing / unparseable formalize verdict is treated as a blocking signal, never neutral.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL = "ultracode-goal"
# The five always-present canonical keys; `reason` is the conditional sixth.
CANONICAL_KEYS = ("status", "skill", "decision_log", "report", "deferred_work")


def _one_line(blocker: dict) -> str:
    """Render a blocker {source, decision_needed} as ONE physical line (no newline)."""
    source = str(blocker.get("source", "")).strip()
    decision = str(blocker.get("decision_needed", "")).strip()
    text = f"{source} — {decision}" if source and decision else (source or decision)
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


def _append_blockers_to_log(decision_log: str, blockers: list[dict]) -> None:
    """Write the full formalize/semantic blockers (source:line + decision_needed) to the log."""
    lines = ["", "## Headless blocked envelope — full blocker list", ""]
    for b in blockers:
        lines.append(f"- {b.get('source', '')} :: {b.get('decision_needed', '')}")
    Path(decision_log).parent.mkdir(parents=True, exist_ok=True)
    with open(decision_log, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def build_headless_envelope(source, decision_log, *, write_log: bool = True) -> dict:
    """Adapt a blocker source into the canonical blocked envelope.

    ``source`` is either an ordered list of blocker dicts (each {source, decision_needed})
    or a formalize verdict dict (adapted via :func:`fr5_blockers`). Returns exactly the five
    canonical keys plus ``reason`` (the one-line rendering of ``blockers[0]``).
    """
    blockers = source if isinstance(source, list) else fr5_blockers(source)
    decision_log = str(decision_log)
    reason = _one_line(blockers[0]) if blockers else ""
    if write_log and blockers:
        _append_blockers_to_log(decision_log, blockers)
    return {
        "status": "blocked",
        "skill": SKILL,
        "decision_log": decision_log,
        "report": None,
        "deferred_work": None,
        "reason": reason,
    }
