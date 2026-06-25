#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Decide an Epic/story verdict from TEA's deterministic quality gate.

Completion truth for ultracode-goal: this script reads TEA's gate artifact and
maps the gate_status to a verdict. It NEVER re-derives the TEA thresholds
(P0=100%, P1>=90%, overall>=80%) — those are decided upstream by the trace
workflow and written into the artifact; here we read gate_status as given.

Verdict mapping (gate_status -> verdict):
    PASS | WAIVED  -> advance
    CONCERNS       -> defer
    FAIL           -> reloop
    NOT_EVALUATED  -> escalate

Profile:
    light       -> the trace gate is the whole decision.
    production  -> additionally AND two signals; any failure downgrades an
                   otherwise-advance verdict to reloop (never below — a CONCERNS
                   stays defer, a FAIL stays reloop):
                     - nfr-assessment.md  : Overall Status != FAIL
                     - test-review.md     : Quality Score >= 80 AND
                                            Recommendation != Block

Artifact resolution:
    Read gate-decision.json (the slim file). Its name is resolved from the trace
    report markdown frontmatter when it records one, else defaults to
    <trace-output>/gate-decision.json. The slim file is only written by TEA when
    the run is gate-eligible AND the decision is PASS/CONCERNS/FAIL/WAIVED, so
    its ABSENCE is normal, not an error: fall back to the always-written
    e2e-trace-summary.json and read its gate fields. When even the summary
    carries no gate fields (not gate-eligible), gate_status is NOT_EVALUATED.

    --story (multi-story shared dir): when many stories write per-story-named
    trace reports + gate decisions into ONE shared <trace-output>, an unscoped
    glob would resolve the first/oldest report's gate (the bug --story fixes).
    Pass --story <id> and resolution is scoped to that story's artifacts: the
    trace report whose filename carries the id (then its frontmatter hint), else
    a conventionally-named gate-decision-<id>.json / e2e-trace-summary-<id>.json.
    Matching is on id components (11-6 == 11.6 == 11_6) anchored to the stem's
    trailing components, so epic id 1 resolves trace-1 (never child story 1-1)
    and 11-6 is never confused with 1-11-6. With no per-story artifact found it
    falls back to the unscoped resolution, so a single-story dir is unchanged.

    python3 gate_eval.py --trace-output DIR --profile production --story 11-6 \
        --nfr DIR/nfr-assessment.md --test-review DIR/test-review.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GATE_VERDICT = {
    "PASS": "advance",
    "WAIVED": "advance",
    "CONCERNS": "defer",
    "FAIL": "reloop",
    "NOT_EVALUATED": "escalate",
}

# Frontmatter keys a trace report may use to point at its slim gate file.
_FRONTMATTER_GATE_KEYS = ("gateDecisionFile", "gateDecisionPath", "gate_decision_path")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _frontmatter(text: str) -> dict[str, str]:
    """Parse the leading ``---`` YAML frontmatter as flat key: value scalars.

    Stdlib-only: we only need top-level string scalars (the gate-file hint), so
    a line scan is sufficient and avoids a yaml dependency.
    """
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    out: dict[str, str] = {}
    for line in match.group(1).splitlines():
        kv = re.match(r"^([A-Za-z_][\w]*):\s*(.*)$", line)
        if not kv:
            continue
        value = kv.group(2).strip().strip("'\"")
        out[kv.group(1)] = value
    return out


def _story_variants(story: str | None) -> list[str]:
    """Separator-insensitive variants of a story id for filename matching.

    A story id like ``11-6`` is written into per-story artifact names with any of
    ``-`` / ``.`` / ``_`` as the separator depending on the producing tool; treat
    them as equal so ``--story 11-6`` matches ``trace-11.6.md`` and
    ``gate-decision-11_6.json`` alike. Order is stable and de-duplicated.
    """
    if not story or not story.strip():
        return []
    parts = re.split(r"[-._]", story.strip())
    variants = [sep.join(parts) for sep in ("-", ".", "_")]
    variants.append(story.strip())
    return list(dict.fromkeys(v for v in variants if v))


def _stem_matches_story(stem: str, story: str) -> bool:
    """True iff a filename stem's trailing id-components equal the story's.

    Components are the maximal ``[-._]``-separated runs (so ``11-6`` == ``11.6``
    == ``11_6``). The story's components must be a suffix of the stem's, AND the
    stem component immediately preceding that suffix (if any) must be
    non-numeric — a filename prefix like ``trace`` / ``gate-decision`` qualifies,
    a longer numeric id does not. This keeps epic id ``1`` (matches ``trace-1``,
    not child story ``trace-1-1``) apart from story ``1-1``, and story ``11-6``
    apart from ``1-11-6``. Component matching also rejects ``trace-211`` for id
    ``11`` (``211`` != ``11``).
    """
    story_parts = [p for p in re.split(r"[-._]", story.strip()) if p]
    stem_parts = [p for p in re.split(r"[-._]", stem) if p]
    if not story_parts or len(story_parts) > len(stem_parts):
        return False
    cut = len(stem_parts) - len(story_parts)
    if stem_parts[cut:] != story_parts:
        return False
    return cut == 0 or not stem_parts[cut - 1].isdigit()


def _resolve_gate_file(trace_output: Path, story: str | None = None) -> Path:
    """Locate the slim gate-decision file, honoring a trace-report hint.

    With ``story`` set, scope resolution to that story's artifacts so a single
    shared multi-story ``trace_output`` does not resolve the first/oldest
    story's gate. Falls back to the unscoped resolution when no per-story
    artifact is found, so a single-story dir behaves exactly as before.
    """
    reports = sorted(trace_output.glob("*.md"))
    if story and story.strip():
        scoped = [r for r in reports if _stem_matches_story(r.stem, story)]
        if scoped:
            reports = scoped
    for report in reports:
        try:
            fm = _frontmatter(report.read_text(encoding="utf-8"))
        except OSError:
            continue
        if fm.get("workflowType") not in ("testarch-trace", "trace"):
            continue
        for key in _FRONTMATTER_GATE_KEYS:
            hint = fm.get(key)
            if hint:
                hinted = Path(hint)
                return hinted if hinted.is_absolute() else trace_output / hinted
    # No frontmatter hint. With a story in scope, prefer the conventionally-named
    # per-story slim file before the shared default so the shared dir resolves
    # the right story even when no trace report points at it.
    for v in _story_variants(story):
        candidate = trace_output / f"gate-decision-{v}.json"
        if candidate.is_file():
            return candidate
    return trace_output / "gate-decision.json"


def _gate_fields_from_summary(summary: dict) -> dict:
    """Lift gate fields from e2e-trace-summary.json.

    The summary only carries gate_status / gate_criteria when the run was
    gate-eligible; otherwise those keys are absent and the gate is NOT_EVALUATED.
    """
    criteria = summary.get("gate_criteria") or {}
    return {
        "gate_status": summary.get("gate_status", "NOT_EVALUATED"),
        "p0_status": criteria.get("p0_status"),
        "p1_status": criteria.get("p1_status"),
        "overall_status": criteria.get("overall_status"),
    }


def _resolve_summary_file(trace_output: Path, story: str | None) -> Path:
    """The summary fallback path, preferring a per-story summary when one exists."""
    for v in _story_variants(story):
        candidate = trace_output / f"e2e-trace-summary-{v}.json"
        if candidate.is_file():
            return candidate
    return trace_output / "e2e-trace-summary.json"


def load_gate(trace_output: Path, reasons: list[str], story: str | None = None) -> dict:
    """Return normalized gate fields, preferring the slim file, else the summary."""
    gate_file = _resolve_gate_file(trace_output, story)
    if gate_file.is_file():
        slim = _read_json(gate_file)
        reasons.append(f"gate read from {gate_file.name}")
        return {
            "gate_status": slim.get("gate_status", "NOT_EVALUATED"),
            "p0_status": slim.get("p0_status"),
            "p1_status": slim.get("p1_status"),
            "overall_status": slim.get("overall_status"),
        }

    summary_file = _resolve_summary_file(trace_output, story)
    if summary_file.is_file():
        reasons.append(
            f"{gate_file.name} absent; gate read from {summary_file.name} (not a failure)"
        )
        return _gate_fields_from_summary(_read_json(summary_file))

    reasons.append(
        f"neither {gate_file.name} nor e2e-trace-summary.json present in {trace_output}"
    )
    return {
        "gate_status": "NOT_EVALUATED",
        "p0_status": None,
        "p1_status": None,
        "overall_status": None,
    }


def _scan_nfr_overall_status(text: str) -> str | None:
    """Read the NFR audit's Overall Status (PASS | CONCERNS | FAIL)."""
    match = re.search(
        r"(?:Overall\s+Status|overallStatus)[*:_\s]*[`*]*\s*(PASS|CONCERNS|FAIL|NOT_ASSESSED)",
        text,
        re.IGNORECASE,
    )
    return match.group(1).upper() if match else None


def _scan_review_score(text: str) -> int | None:
    """Read the test-review Quality Score (``{score}/100``)."""
    match = re.search(r"(?:Quality\s+Score|score)[*:_\s]*[`*]*\s*(\d{1,3})\s*/\s*100", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _scan_review_recommendation(text: str) -> str | None:
    """Read the test-review Recommendation (Approve / ... / Block)."""
    match = re.search(
        r"Recommendation[*:_\s]*[`*]*\s*"
        r"(Approve with Comments|Approve|Request Changes|Block)",
        text,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def apply_production_and(
    verdict: str,
    nfr_path: Path | None,
    review_path: Path | None,
    reasons: list[str],
) -> tuple[str, str | None, int | None]:
    """AND the production signals; downgrade an advance to reloop on any failure.

    Returns (verdict, nfr_status, review_score). The downgrade floor is reloop:
    only an otherwise-advance verdict moves; defer/reloop/escalate are unchanged.

    FAIL-CLOSED CONTRACT (deliberate — do not "relax"): a missing file or a
    field the scanners below cannot parse is treated as a *failing* signal, not
    a neutral/absent one (see the ``nfr_status is None`` / ``review_score is None``
    / file-not-found branches). TEA prose-format drift therefore degrades to a
    conservative reloop rather than a silent false-advance. The conservative
    direction is intentional: we would rather re-loop a green story than advance
    a story whose evidence we could not actually read.
    """
    nfr_status: str | None = None
    review_score: int | None = None
    failed = False

    if nfr_path is not None and nfr_path.is_file():
        nfr_status = _scan_nfr_overall_status(nfr_path.read_text(encoding="utf-8"))
        if nfr_status == "FAIL":
            reasons.append("nfr overallStatus is FAIL")
            failed = True
        elif nfr_status is None:
            reasons.append(f"nfr Overall Status not found in {nfr_path.name}; treated as failing")
            failed = True
    elif nfr_path is not None:
        reasons.append(f"nfr file {nfr_path} not found; treated as failing")
        failed = True

    if review_path is not None and review_path.is_file():
        review_text = review_path.read_text(encoding="utf-8")
        review_score = _scan_review_score(review_text)
        recommendation = _scan_review_recommendation(review_text)
        if review_score is None:
            reasons.append(f"test-review score not found in {review_path.name}; treated as failing")
            failed = True
        elif review_score < 80:
            reasons.append(f"test-review score {review_score} < 80")
            failed = True
        if recommendation is not None and recommendation.lower() == "block":
            reasons.append("test-review recommendation is Block")
            failed = True
    elif review_path is not None:
        reasons.append(f"test-review file {review_path} not found; treated as failing")
        failed = True

    if failed and verdict == "advance":
        reasons.append("production signal failed; advance downgraded to reloop")
        verdict = "reloop"

    return verdict, nfr_status, review_score


def evaluate(args: argparse.Namespace) -> dict:
    reasons: list[str] = []
    trace_output = Path(args.trace_output)

    gate = load_gate(trace_output, reasons, getattr(args, "story", None))
    gate_status = (gate["gate_status"] or "NOT_EVALUATED").upper()
    verdict = GATE_VERDICT.get(gate_status, "escalate")
    if gate_status not in GATE_VERDICT:
        reasons.append(f"unrecognized gate_status {gate_status!r}; escalating")
    else:
        reasons.append(f"gate_status {gate_status} -> {verdict}")

    nfr_status: str | None = None
    review_score: int | None = None
    if args.profile == "production":
        nfr_path = Path(args.nfr) if args.nfr else None
        review_path = Path(args.test_review) if args.test_review else None
        verdict, nfr_status, review_score = apply_production_and(
            verdict, nfr_path, review_path, reasons
        )

    return {
        "verdict": verdict,
        "gate_status": gate_status,
        "p0_status": gate["p0_status"],
        "p1_status": gate["p1_status"],
        "overall_status": gate["overall_status"],
        "nfr_status": nfr_status,
        "review_score": review_score,
        "reasons": reasons,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the TEA quality gate into a verdict.")
    parser.add_argument("--trace-output", required=True, help="Directory holding the trace gate artifacts.")
    parser.add_argument("--profile", required=True, choices=["light", "production"])
    parser.add_argument(
        "--story",
        help="Current story id; scopes gate-file resolution to that story's "
        "artifacts in a shared multi-story trace dir. Omit for a single-story dir.",
    )
    parser.add_argument("--nfr", help="Path to nfr-assessment.md (production only).")
    parser.add_argument("--test-review", help="Path to test-review.md (production only).")
    args = parser.parse_args(argv)

    result = evaluate(args)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
