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
    and 11-6 is never confused with 1-11-6.

    With no per-story artifact found, what happens next depends on how the dir
    is NAMED — FAIL-CLOSED, deliberately. If any trace report or gate-decision
    file there is named for SOME story or epic (a trailing numeric id component
    in its stem), the dir is per-story-named and the requested story is genuinely
    absent: resolution fails closed to NOT_EVALUATED rather than handing back an
    unrelated story's gate. If every candidate is generically named (trace.md,
    gate-decision.json), the dir holds one story's artifacts and the unscoped
    resolution still applies, so a single-story dir is unchanged.

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


# The artifact-name prefixes this module writes. A stem that is EXACTLY one of
# these carries no id; a stem that is one of these followed by something starting
# with a digit is named for a story or an epic.
_ARTIFACT_PREFIXES = (
    ("gate", "decision"),
    ("e2e", "trace", "summary"),
    ("nfr", "assessment"),
    ("test", "review"),
    ("trace",),
    ("atdd", "checklist"),
)


def _has_trailing_id(stem: str) -> bool:
    """True iff a filename stem carries a story or epic id after its prefix.

    NOT "the last component is numeric". That was the original rule and it is
    wrong for every id this module actually produces once a story is split or
    slugged: ``trace-92-0a`` ends in ``0a`` and ``trace-5-8-some-slug`` ends in
    ``slug``, so both read as GENERIC. A directory full of them therefore
    reported itself as not-per-story-named, which switches OFF the fail-closed
    branch in :func:`_resolve_gate_file` - and an artifact-less story then
    resolved a neighbour's gate and advanced on it.

    Measured before the fix, in a directory holding only
    ``trace-92-0a-alpha.md`` + its PASS gate file: ``--story 92-7f-never-driven``
    returned ``PASS``. That story wrote nothing at all.

    The rule is now structural: match a known artifact prefix, then require the
    NEXT component to start with a digit. ``traceability-matrix`` is untouched
    (its first component is ``traceability``, not ``trace``), which keeps the
    documented unscoped fallback for a directory that names no story.
    """
    parts = [p for p in re.split(r"[-._]", stem) if p]
    if not parts:
        return False
    for prefix in _ARTIFACT_PREFIXES:
        if len(parts) > len(prefix) and tuple(parts[: len(prefix)]) == prefix:
            return parts[len(prefix)][:1].isdigit()
    return False


def _is_per_story_named(trace_output: Path) -> bool:
    """True iff any trace report / gate-decision file there is named for a story.

    Distinguishes a shared multi-story dir (where a story with no artifacts is
    genuinely absent) from the single-story dir whose generically-named files
    the unscoped fallback is documented to resolve.
    """
    candidates = list(trace_output.glob("*.md")) + list(trace_output.glob("gate-decision*.json"))
    return any(_has_trailing_id(p.stem) for p in candidates)


def _per_story_slim(trace_output: Path, story: str | None) -> Path | None:
    """The conventionally-named per-story slim gate file, when one exists."""
    for v in _story_variants(story):
        candidate = trace_output / f"gate-decision-{v}.json"
        if candidate.is_file():
            return candidate
    return None


# The `workflowType` values a trace report must declare. A report that declares
# neither is skipped by the hint loop, so it can carry no gate decision.
_TRACE_WORKFLOW_TYPES = ("testarch-trace", "trace")


def _declares_trace_report(report: Path) -> bool:
    """True iff this markdown file declares itself a trace report.

    Unreadable counts as NOT a trace report: the file could contribute no hint
    either way, and this predicate gates a fail-closed branch, so the safe
    answer is the one that keeps the branch reachable.
    """
    try:
        fm = _frontmatter(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return False
    return fm.get("workflowType") in _TRACE_WORKFLOW_TYPES


def _resolve_gate_file(trace_output: Path, story: str | None = None) -> Path | None:
    """Locate the slim gate-decision file, honoring a trace-report hint.

    With ``story`` set, scope resolution to that story's artifacts so a single
    shared multi-story ``trace_output`` does not resolve the first/oldest
    story's gate. Returns ``None`` when the story matches nothing in a
    per-story-named dir — the story is genuinely absent, and taking the unscoped
    fallback there would return a DIFFERENT story's gate as this story's
    verdict. A generically-named dir keeps the documented unscoped fallback.
    """
    reports = sorted(trace_output.glob("*.md"))
    scoped_slim = _per_story_slim(trace_output, story)
    if story and story.strip():
        # A markdown file merely NAMED for this story is not a trace report, and
        # letting one count here suppresses the fail-closed branch below.
        # `references/gate.md` tells the non-web author to write
        # `nfr-assessment-<id>.md` and `test-review-<id>.md` into this same
        # directory, and both match `_stem_matches_story`. So a story that
        # produced its NFR and review but never authored its trace pair looked
        # "present": `scoped` was non-empty, the fail-closed return was skipped,
        # neither file carries a `gateDecisionFile` hint, and resolution fell
        # through to the UNSCOPED `gate-decision.json` / `e2e-trace-summary.json`
        # - handing an artifact-less story a PASS. Measured: the same directory
        # with the NFR named `nfr-assessment.md` fails closed, and with it named
        # `nfr-assessment-1-2.md` returns PASS.
        #
        # Declared trace reports only, therefore - the same predicate the hint
        # loop below already applies before honoring a hint, and the same one
        # `gate_trail.py` applies when it picks a story's trace report. A file
        # that would contribute no hint must not buy the story a pass out of the
        # fail-closed branch either.
        scoped = [
            r
            for r in reports
            if _stem_matches_story(r.stem, story) and _declares_trace_report(r)
        ]
        if scoped:
            reports = scoped
        elif scoped_slim is not None:
            # This story wrote no trace report but DID write its own slim gate
            # file. Falling through here would leave ``reports`` as every report
            # in the directory and let the hint loop below return a NEIGHBOUR's
            # gate — observed handing an unrelated epic's PASS back as this
            # story's verdict. The story's own file wins, before any hint is read.
            return scoped_slim
        elif _is_per_story_named(trace_output):
            return None
    for report in reports:
        try:
            fm = _frontmatter(report.read_text(encoding="utf-8"))
        except OSError:
            continue
        if fm.get("workflowType") not in _TRACE_WORKFLOW_TYPES:
            continue
        for key in _FRONTMATTER_GATE_KEYS:
            hint = fm.get(key)
            if hint:
                hinted = Path(hint)
                return hinted if hinted.is_absolute() else trace_output / hinted
    # No frontmatter hint. With a story in scope, prefer the conventionally-named
    # per-story slim file before the shared default so the shared dir resolves
    # the right story even when no trace report points at it.
    if scoped_slim is not None:
        return scoped_slim
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
    if gate_file is None:
        # Fail-closed: the dir names its artifacts per story and none is this
        # story's, so there is nothing to read. Do NOT fall back to the unscoped
        # read — it would report a neighbouring story's gate as this one's.
        reasons.append(
            f"story {story} has no trace report or gate decision in {trace_output}; "
            "the directory is named per story, so no unscoped fallback was taken"
        )
        return {
            "gate_status": "NOT_EVALUATED",
            "p0_status": None,
            "p1_status": None,
            "overall_status": None,
        }

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

    AN OMITTED PATH IS FAILING TOO, and that is the same rule rather than a new
    one. A ``None`` path used to be skipped in silence: the signal's AND simply
    did not run, the field rendered ``null``, and the verdict was computed
    WITHOUT it. So the fail-closed contract covered a signal that was unreadable
    but not a signal that was never asked for, and forgetting a flag bought a
    higher verdict than supplying a failing artifact would have. A ``null`` beside
    ``--profile production`` also reads as "the artifact is missing or malformed",
    which is the opposite of what it meant. The epic roll-up genuinely has no
    aggregate to AND - TEA writes both artifacts per story - so it says so with
    ``--epic-level`` instead of by omission.
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
    else:
        reasons.append(
            "--nfr not supplied on a per-story production gate; treated as failing "
            "(pass --nfr, or --epic-level if this is the epic roll-up)"
        )
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
    else:
        reasons.append(
            "--test-review not supplied on a per-story production gate; treated as failing "
            "(pass --test-review, or --epic-level if this is the epic roll-up)"
        )
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
        if getattr(args, "epic_level", False):
            # The epic roll-up is a pure trace read. TEA produces NFR and
            # test-review PER STORY, so there is no aggregate to AND, and every
            # story already ANDed its own signals before reaching `done`.
            # Declared, never inferred from an absent flag - that is the whole
            # point of the flag.
            reasons.append(
                "epic-level roll-up: production ANDs not applied "
                "(TEA writes nfr and test-review per story, not per epic)"
            )
        else:
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
        # Machine-readable, because the `reasons` wording explicitly is not
        # (docs/_internal/STABILITY.md). Without this key a consumer cannot tell
        # an advance that ANDed both production signals from one that skipped
        # them, and `nfr_status: null` alone does not say which.
        "epic_level": bool(getattr(args, "epic_level", False)),
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
    parser.add_argument(
        "--epic-level",
        action="store_true",
        help="This is the epic roll-up, not a story gate: skip the production "
        "NFR/test-review ANDs, which TEA writes per story and never per epic. "
        "Without it, --profile production requires both --nfr and --test-review.",
    )
    args = parser.parse_args(argv)

    # Mutually exclusive by meaning: --epic-level asserts there is no aggregate to
    # AND, so supplying one anyway is a contradiction, and the flag would win
    # silently - discarding a FAILING artifact the caller explicitly named.
    # `references/gate.md` already calls the hybrid the mirror mistake; this is
    # the invocation-error lane a missing --story already occupies.
    if args.epic_level and (args.nfr or args.test_review):
        parser.error(
            "--epic-level asserts there is no epic-level aggregate to AND, so it "
            "cannot be combined with --nfr/--test-review; drop the flag for a "
            "per-story gate, or drop the paths for the epic roll-up"
        )

    result = evaluate(args)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
