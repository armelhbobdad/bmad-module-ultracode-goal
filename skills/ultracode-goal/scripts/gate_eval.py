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
    is NAMED — FAIL-CLOSED, deliberately. If any artifact there is named for SOME
    story or epic (a known artifact prefix followed by a component starting with
    a digit), the dir is per-story-named and the requested story is genuinely
    absent: resolution fails closed to NOT_EVALUATED rather than handing back an
    unrelated story's gate. If every candidate is generically named (trace.md,
    gate-decision.json), the dir holds one story's artifacts and the unscoped
    resolution still applies, so a single-story dir is unchanged. One exception,
    because the story is not absent: a story that wrote its own
    e2e-trace-summary-<id>.json is PRESENT, and resolution names its own slim
    path so the summary fallback below reads that file rather than the shared one.

    THE FRONTMATTER HINT IS BOUNDED. A `gateDecisionFile` must name a file
    directly inside <trace-output> — not a subdirectory, not a `..` path, not an
    absolute path elsewhere on disk — and, with --story in scope, must either
    carry that story's id or carry no id at all in a directory holding no OTHER
    story's artifacts. A hint that fails either test is skipped rather than
    followed; resolution continues to the story's own conventionally-named file
    and then to the fail-closed rule above. Following one verbatim let a story
    advance on a neighbour's gate, and on files outside the directory entirely.

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
#
# `traceability-matrix` is in this table and the `("trace",)` entry does NOT
# cover it: the components are `traceability` / `matrix`. `bmad-testarch-trace`'s
# `default_output_file` is the BARE `traceability-matrix.md` (verified in its
# workflow.yaml), so both spellings matter and they matter in opposite
# directions:
#
#   - bare `traceability-matrix.md` must read as GENERIC, which is what makes
#     TEA's own untouched output the sanctioned isolated single-story directory.
#     Listing the prefix is what puts it in `gate_trail.GENERIC_ARTIFACT_STEMS`,
#     which is derived from this table - without it the trail rendered `n/a` for
#     a file the gate read as PASS.
#   - `traceability-matrix-<id>.md`, the per-story spelling a run produces when
#     it names TEA's report per story in a shared directory, must read as NAMED.
#     It did not: `_has_trailing_id` returned False, so a directory of them read
#     as generic, the fail-closed branch switched off for the whole directory,
#     and never-driven stories resolved a neighbour's PASS.
#
# Both follow from one rule, which is why the entry is a prefix and not a special
# case: these entries carry an id only when a component FOLLOWS the prefix.
_ARTIFACT_PREFIXES = (
    ("gate", "decision"),
    ("e2e", "trace", "summary"),
    ("nfr", "assessment"),
    ("test", "review"),
    ("traceability", "matrix"),
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
    NEXT component to start with a digit. A stem that is EXACTLY a prefix carries
    no id and stays GENERIC, which keeps the documented unscoped fallback for a
    directory that names no story - so bare ``traceability-matrix.md`` is generic
    while ``traceability-matrix-<id>.md`` is named for a story. That pair is
    listed explicitly in the table because the ``("trace",)`` entry does NOT
    cover it: the components are ``traceability`` / ``matrix``, so every
    per-story file from a TEA build using its own default report filename read
    as generic, and the whole directory with it.
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

    The glob is EVERY md and json here, not `*.md` plus `gate-decision*.json`.
    The narrower pair was blind to a directory whose per-story artifacts are
    spelled `e2e-trace-summary-<id>.json`: nothing matched, the directory read as
    generic, the fail-closed branch switched off, and a never-driven story
    resolved the shared roll-up `e2e-trace-summary.json` as its own PASS.
    `gate_trail._only_generic_artifacts`, which decides the same question from
    the other side, has always globbed both; the two now see one directory.
    """
    candidates = list(trace_output.glob("*.md")) + list(trace_output.glob("*.json"))
    return any(_has_trailing_id(p.stem) for p in candidates)


def _per_story_slim(trace_output: Path, story: str | None) -> Path | None:
    """The conventionally-named per-story slim gate file, when one exists."""
    for v in _story_variants(story):
        candidate = trace_output / f"gate-decision-{v}.json"
        if candidate.is_file():
            return candidate
    return None


def _owns_a_per_story_summary(trace_output: Path, story: str | None) -> bool:
    """True iff this story wrote its own ``e2e-trace-summary-<id>.json`` here.

    The fail-closed branches below mean "this story is absent from a directory
    that names its artifacts per story". That is FALSE when the story wrote its
    own per-story summary, and reading it as absent was a liveness regression
    rather than a safety win: the summary is the ALWAYS-written artifact, so a
    story whose run was not gate-eligible has that file and nothing else, and
    refusing it reports NOT_EVALUATED for a story whose own evidence is sitting
    in the directory.

    Deliberately narrower than "owns any file here". `references/gate.md` has the
    non-web author write `nfr-assessment-<id>.md` and `test-review-<id>.md` into
    this same directory, and neither carries a gate decision - a story with only
    those must still fail closed, which is a behaviour with its own test. The
    slim file is not checked either, because every caller has already returned on
    it (`scoped_slim`) before reaching here.
    """
    if not story or not story.strip():
        return False
    return any(
        (trace_output / f"e2e-trace-summary-{v}.json").is_file() for v in _story_variants(story)
    )


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


def _holds_another_storys_artifact(trace_output: Path, story: str) -> bool:
    """True iff some artifact here is named for a story OTHER than this one.

    The question a GENERIC filename raises is not "does this directory name
    anything per story" but "could this unnamed file be someone else's". Those
    differ on exactly the shape `references/gate.md` tells an operator to build:
    isolate one story's artifacts into a fresh directory. A TEA build that names
    the trace report per story but the gate decision generically produces
    `trace-<id>.md` + `gate-decision.json` there, which IS per-story-named and
    holds no other story - so the generic gate file provably belongs to the one
    story being gated, and refusing it escalates a story with a real PASS.
    """
    candidates = list(trace_output.glob("*.md")) + list(trace_output.glob("*.json"))
    return any(
        _has_trailing_id(p.stem) and not _stem_matches_story(p.stem, story) for p in candidates
    )


def _hinted_gate_file(trace_output: Path, hint: str, story: str | None) -> Path | None:
    """The file a ``gateDecisionFile`` hint names, or None when it must not be followed.

    A hint is a string inside a trace report, and the report is written by the
    same run whose completion it is evidence for. It was previously followed
    verbatim, with no name check and no containment check at all, so three
    distinct shapes each handed a story a PASS it did not own: a hint naming a
    NEIGHBOUR's ``gate-decision-<other>.json``, a relative hint escaping the
    artifact directory (``../other-epic/gate-decision.json``), and an ABSOLUTE
    hint naming any path on disk. All three were measured returning
    ``PASS -> advance`` for a story that owned no gate decision.

    Two conditions now, and both are the artifact-resolution property rather than
    new policy:

    - CONTAINMENT. The file must sit directly in ``trace_output``. ``--trace-output``
      is the boundary the caller drew around this run's evidence; a gate read from
      outside it is not this run's gate. Absolute hints stay legal, but only when
      they resolve back inside that directory.
    - OWNERSHIP. With a story in scope, a hinted file that carries an id must
      carry THIS story's id. A hinted file carrying NO id is accepted only when
      the directory holds no OTHER story's artifacts, which is the isolated
      single-story directory `references/gate.md` tells an operator to build -
      there the unnamed file provably belongs to the one story being gated. The
      test is "is anyone else here", not "is anything here named": keying on the
      latter escalated a story whose TEA build named its trace report per story
      and its gate decision generically, which is a shape that workflow produces.

    Returning None means "do not follow this hint". The caller still prefers the
    story's OWN ``gate-decision-<id>.json`` when one exists - that artifact is
    named for this story, so it is not a file nobody pointed at - but it resolves
    NOTHING else afterwards. A refused hint is not a missing hint: the run named
    a file and this reader declined it, so falling on to the next candidate can
    RAISE the verdict, and it did (a refused FAIL became an advance off the
    story's own summary). See the ``refused_hint`` latch in the caller.
    """
    hinted = Path(hint)
    candidate = hinted if hinted.is_absolute() else trace_output / hinted
    try:
        resolved = candidate.resolve()
        inside = resolved.relative_to(trace_output.resolve())
    except (ValueError, OSError):
        return None
    # Exactly one component: a plain filename sitting directly in the directory.
    # Testing `inside.parent != Path(".")` instead let a hint of `.` or `""`
    # through, because both resolve to the DIRECTORY, whose relative form is `.`
    # and whose parent is also `.` - so resolution returned the artifact
    # directory itself as the gate file.
    if len(inside.parts) != 1:
        return None
    if story and story.strip():
        if _has_trailing_id(resolved.stem):
            return candidate if _stem_matches_story(resolved.stem, story) else None
        return None if _holds_another_storys_artifact(trace_output, story) else candidate
    return candidate


def _resolve_gate_file(
    trace_output: Path, story: str | None = None, notes: list[str] | None = None
) -> Path | None:
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
    refused_hint = False
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
        elif _is_per_story_named(trace_output) and not _owns_a_per_story_summary(
            trace_output, story
        ):
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
                hinted = _hinted_gate_file(trace_output, hint, story)
                if hinted is not None:
                    return hinted
                # A hint that names another story's file, or a path outside the
                # artifact directory, is not followed and is not fatal either:
                # fall through to this story's own conventionally-named file and,
                # failing that, to the fail-closed branch below.
                #
                # It is RECORDED, though. Refusing a hint and then resolving some
                # other file changes which artifact decided, and a reader who
                # cannot see that happened has no way to tell a gate read from
                # the intended file from one read from the fallback - which can
                # carry a different verdict.
                if notes is not None:
                    notes.append(
                        f"{report.name} hints at {hint!r}, which is not a file this story owns "
                        f"inside {trace_output}; the hint was not followed"
                    )
                refused_hint = True
                break
    # No frontmatter hint. With a story in scope, prefer the conventionally-named
    # per-story slim file before the shared default so the shared dir resolves
    # the right story even when no trace report points at it.
    if scoped_slim is not None:
        return scoped_slim
    if refused_hint:
        # A REFUSED HINT IS NOT A MISSING HINT. The run pointed at a specific
        # file and this reader declined to read it, so every remaining candidate
        # below is a file nobody pointed at. Resolving one anyway does not merely
        # lose information, it can RAISE the verdict: measured, a subdirectory
        # hint carrying FAIL was refused and the story then advanced on its own
        # summary's PASS, and an unscoped run whose hinted CONCERNS was refused
        # advanced on the generic summary. Both read as ordinary successful
        # resolutions in the log, because the fallback names a real file.
        #
        # The story's OWN slim file is the one exception, and it is already
        # returned above: that artifact is named for this story, so it is not a
        # file nobody pointed at. Everything after this line is.
        return None
    if story and _is_per_story_named(trace_output) and _owns_a_per_story_summary(trace_output, story):
        # THIS STORY IS PRESENT, but its only gate-bearing artifact is its own
        # summary. Falling through to the shared `gate-decision.json` below would
        # hand it the RUN-WIDE verdict: measured, a story whose own summary said
        # CONCERNS came back PASS -> advance off the generic file. Name this
        # story's own conventional slim path instead. It does not exist (a slim
        # file that did exist was returned as `scoped_slim` long before here), so
        # `load_gate` falls through to `_resolve_summary_file`, which resolves the
        # per-story summary this branch exists for.
        return trace_output / f"gate-decision-{story}.json"
    if story and _is_per_story_named(trace_output):
        # The SAME fail-closed rule as the branch above, applied to the last
        # resort. That `return None` is guarded by `elif`, so it is reachable
        # only when `scoped` is EMPTY — a story that authored a DECLARED trace
        # report but no resolvable gate file (no `gateDecisionFile` hint, and no
        # per-story slim file) skipped it entirely and landed here, where the
        # unscoped `gate-decision.json` is a NEIGHBOUR's, or the epic roll-up's,
        # verdict. Having written a trace report must not buy a story a pass out
        # of the fail-closed lane that a story with no artifacts at all gets.
        #
        # A story that wrote its OWN per-story summary is not in that lane: it
        # is present, its evidence is here, and `load_gate` reads that summary
        # one step below. Falling closed on it reported NOT_EVALUATED for a story
        # whose only artifact is the always-written one.
        return None
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
    gate_file = _resolve_gate_file(trace_output, story, reasons)
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
    if (
        story
        and summary_file.name == "e2e-trace-summary.json"
        and _is_per_story_named(trace_output)
    ):
        # The summary fallback is the same unscoped read, one file along. In a
        # per-story-named directory the GENERIC summary belongs to no story in
        # particular and is written for the whole run, so handing it back as
        # this story's gate is the neighbour's-verdict fail-open wearing a
        # different filename. A per-story-named summary is still honored above.
        reasons.append(
            f"story {story} has no per-story gate decision or summary in {trace_output}; "
            "the directory is named per story, so the shared e2e-trace-summary.json "
            "was not read as this story's gate"
        )
        return {
            "gate_status": "NOT_EVALUATED",
            "p0_status": None,
            "p1_status": None,
            "overall_status": None,
        }
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
        elif nfr_status == "NOT_ASSESSED":
            # NOT_ASSESSED is in the scanner's alternation, so it parses cleanly
            # and never reached the `is None` branch below: it read as "present
            # and not FAIL" and PASSED the AND. But it is the NFR audit saying
            # the NFRs were never evaluated - strictly weaker evidence than a
            # file this reader cannot parse, which already fails closed two
            # branches down. Advancing a story on it inverted the contract.
            reasons.append(
                f"nfr Overall Status is NOT_ASSESSED in {nfr_path.name}; "
                "treated as failing (the NFRs were never evaluated)"
            )
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
    parser.add_argument(
        "--nfr",
        help="PATH to the story's nfr-assessment markdown (production only) — a file "
        "path, never a status word. The file must carry a literal "
        "'**Overall Status:** <PASS|CONCERNS|FAIL|NOT_ASSESSED>' line; a value "
        "passed here instead of a path is read as a missing file and treated as "
        "failing.",
    )
    parser.add_argument(
        "--test-review",
        help="PATH to the story's test-review markdown (production only) — a file "
        "path, never a score. The file must carry '**Quality Score**: N/100' "
        "(the /100 denominator is required) and a '**Recommendation**:' line; a "
        "value passed here instead of a path is read as a missing file and "
        "treated as failing.",
    )
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
