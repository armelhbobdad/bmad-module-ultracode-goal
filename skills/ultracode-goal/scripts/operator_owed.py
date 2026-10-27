#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Say whether a story's gate FAIL is one only operator evidence can change.

An acceptance criterion whose proof is a measurement only a person can make (a
release build CI cannot run, a judgment no test can decide) is split by
Define-Done into its own AC tagged `**Gate-ability:** operator`, proven by a
record in TEA's live verification results file. Until that record exists, TEA's
trace counts the AC as uncovered, and at P0 or P1 the gate reads FAIL. gate_eval
maps that FAIL to `reloop`, and no re-loop can produce the record: a real run
re-looped such a story with every test green. This script answers the one
question the conductor needs before it spends a re-loop: is every criterion TEA
holds open an operator AC still owed its evidence? `references/gate.md` routes
`owed: true` to an `operator-evidence-owed` escalation instead.

gate_eval.py is not changed and no verdict is added. This script imports its
readers, so the gate artifacts resolve here exactly as the gate resolved them.

FAIL-CLOSED. `owed` is true only when ALL of these hold, and anything this
script cannot read gives false, which leaves the re-loop route as it was:

  - the gate reads gate_status FAIL (gate_eval.load_gate, same resolution);
  - the gate was the full instrument: no `--cycle-profile delta`, and the
    sweep-scope AND (and, under `--profile production`, the NFR and test-review
    ANDs) would leave an advance an advance, so nothing a re-loop can change
    failed beside the coverage;
  - the story's trace report is exactly `trace-<story id>.md`, declares itself a
    trace report, and its frontmatter `tempCoverageMatrixPath` names (by an
    absolute path) TEA's Phase 1 coverage matrix, a JSON object whose `phase`
    is PHASE_1_COMPLETE;
  - that matrix is this gate's: its P0-P3 total and covered counts equal the
    story's own `e2e-trace-summary-<story id>.json`, its requirement list
    recounts to those numbers, and its `source_sha`, when it has one, names the
    summary's commit;
  - every requirement below FULL is `AC-<n>`, and AC `<n>.` under the story
    file's `## Acceptance Criteria` carries `**Gate-ability:** operator` and no
    other tag;
  - none of those ACs has a live record TEA classified `fail` or
    `contradicted`: a failed measurement is a finding, not owed evidence;
  - the summary names the commit it measured (`source_sha`), which is the
    commit the record must be made at.

TEA's own per-criterion classification is trusted as given, the same trust the
gate places in gate_status. The cross-checks catch a stale or foreign matrix,
not a criterion TEA classified wrongly.

Prints one JSON object and exits 0: `owed`, `open` (the requirement ids below
FULL), `operator` (the open ones owed operator evidence), `evidence` (each of
those ACs' live record dispositions, or `none`), `assessed_commit` and
`reasons`. An argument error exits 2.

    uv run operator_owed.py --trace-output DIR --story 11-6 \\
        --story-file STORY.md --profile production --nfr NFR.md \\
        --test-review REVIEW.md --tests-ran IMPL/.tests-ran-11-6
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_eval  # noqa: E402  (sibling script, path set above)

PRIORITIES = ("P0", "P1", "P2", "P3")

# TEA names an acceptance criterion requirement AC-<n>, numbered as the story
# numbers its ACs. Any other id shape is not mapped to a story AC at all.
_AC_ID = re.compile(r"^AC-(\d+)$")
_AC_SECTION = re.compile(r"^## Acceptance Criteria[ \t]*$(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
# A top-level numbered list item starts an AC; an indented one is inside it.
_AC_START = re.compile(r"^(\d+)\.\s")
_TAG = re.compile(r"\*\*Gate-ability:\*\*\s*`?([A-Za-z][A-Za-z-]*)`?")

# Live record dispositions that say the measurement was made and failed.
_REFUTED = ("fail", "contradicted")


def _own_artifact(trace_output: Path, name: str, story: str) -> Path | None:
    """The story's own artifact, found by its exact id, never by a shorter prefix of it.

    `name` carries a `{}` where the id goes. Only the separator spellings of the
    id itself are tried, so story `4-2-slug` never reads a sibling's `trace-4-2.md`.
    """
    for variant in gate_eval._story_variants(story):
        candidate = trace_output / name.format(variant)
        if candidate.is_file():
            return candidate
    return None


def _counts(breakdown: dict, priority: str) -> tuple[int, int]:
    """One priority's (total, covered); raises on anything that is not two ints."""
    entry = breakdown[priority]
    total, covered = entry["total"], entry["covered"]
    for value in (total, covered):
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{priority} count {value!r} is not an integer")
    return total, covered


def _same_commit(a: str, b: str) -> bool:
    """Two shas name one commit when the shorter is a prefix of the longer, as TEA compares them."""
    a, b = a.strip().lower(), b.strip().lower()
    if not a or not b:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return longer.startswith(shorter)


def operator_acs(story_text: str) -> set[int]:
    """The AC numbers the story's `## Acceptance Criteria` section tags operator.

    An AC counts only when its number starts exactly one top-level list item in
    the one such section, and every `**Gate-ability:**` tag inside it reads
    `operator`. A second section, a repeated number, an untagged AC or a mixed
    tag leaves the AC out, which keeps the re-loop route.
    """
    sections = _AC_SECTION.findall(story_text)
    if len(sections) != 1:
        return set()
    starts: dict[int, int] = {}
    tags: dict[int, set[str]] = {}
    current: int | None = None
    for line in sections[0].splitlines():
        start = _AC_START.match(line)
        if start:
            current = int(start.group(1))
            starts[current] = starts.get(current, 0) + 1
        if current is None:
            continue
        for tag in _TAG.findall(line):
            tags.setdefault(current, set()).add(tag)
    return {n for n, found in tags.items() if found == {"operator"} and starts.get(n) == 1}


def _gate_reads_owed(args: argparse.Namespace, reasons: list[str]) -> bool:
    """True when the gate's FAIL rests on coverage alone, with every other signal clean."""
    gate = gate_eval.load_gate(Path(args.trace_output), reasons, args.story)
    status = str(gate.get("gate_status") or "NOT_EVALUATED").upper()
    if status != "FAIL":
        reasons.append(f"gate_status {status} is not FAIL")
        return False
    if args.cycle_profile == "delta":
        reasons.append("a delta-profile gate is not the full instrument; run the full gate")
        return False
    signals: list[str] = []
    if gate_eval.apply_sweep_scope("advance", Path(args.tests_ran), signals)[0] != "advance":
        reasons.append("the sweep behind this gate was not scope=full, so a re-loop can change it")
        reasons.extend(signals)
        return False
    if args.profile == "production":
        nfr = Path(args.nfr) if args.nfr else None
        review = Path(args.test_review) if args.test_review else None
        if gate_eval.apply_production_and("advance", nfr, review, signals)[0] != "advance":
            reasons.append("a production signal failed, so a re-loop can change it")
            reasons.extend(signals)
            return False
    return True


def evaluate(args: argparse.Namespace) -> dict:
    reasons: list[str] = []
    out: dict = {
        "owed": False,
        "open": [],
        "operator": [],
        "evidence": {},
        "assessed_commit": None,
        "reasons": reasons,
    }
    if not _gate_reads_owed(args, reasons):
        return out

    trace_output = Path(args.trace_output)
    report = _own_artifact(trace_output, "trace-{}.md", args.story)
    if report is None or not gate_eval._declares_trace_report(report):
        reasons.append(f"no trace report named trace-{args.story}.md in {trace_output}")
        return out
    report_text = gate_eval._read_text(report)
    matrix_hint = gate_eval._frontmatter(report_text or "").get("tempCoverageMatrixPath", "")
    if not matrix_hint or not Path(matrix_hint).is_absolute():
        reasons.append(
            f"{report.name} names no absolute tempCoverageMatrixPath, so TEA's coverage matrix cannot be read"
        )
        return out
    matrix = gate_eval._read_json(Path(matrix_hint))
    if matrix is None or matrix.get("phase") != "PHASE_1_COMPLETE":
        reasons.append(f"{matrix_hint} is not a readable PHASE_1_COMPLETE coverage matrix")
        return out
    summary_path = _own_artifact(trace_output, "e2e-trace-summary-{}.json", args.story)
    summary = gate_eval._read_json(summary_path) if summary_path else None
    if summary is None:
        reasons.append(f"no readable e2e-trace-summary-{args.story}.json in {trace_output}")
        return out

    try:
        matrix_counts = {p: _counts(matrix["coverage_statistics"]["priority_breakdown"], p) for p in PRIORITIES}
        summary_counts = {p: _counts(summary["coverage"]["priority_breakdown"], p) for p in PRIORITIES}
        requirements = matrix["requirements"]
        if not isinstance(requirements, list) or not requirements:
            raise TypeError("requirements is not a non-empty list")
        if not all(isinstance(r, dict) for r in requirements):
            raise TypeError("a requirement is not an object")
        live_records = matrix.get("live_records", [])
        if not isinstance(live_records, list):
            raise TypeError("live_records is not a list")
    except (KeyError, TypeError) as exc:
        reasons.append(f"the coverage matrix or the summary lacks a coverage field ({exc})")
        return out
    stale = [p for p in PRIORITIES if matrix_counts[p] != summary_counts[p]]
    if stale:
        reasons.append(
            f"the matrix disagrees with {summary_path.name} on {', '.join(stale)}: it is not this gate's matrix"
        )
        return out
    recount = {
        p: (
            sum(1 for r in requirements if r.get("priority") == p),
            sum(1 for r in requirements if r.get("priority") == p and r.get("coverage") == "FULL"),
        )
        for p in PRIORITIES
    }
    if recount != matrix_counts:
        reasons.append("the matrix's requirements do not recount to its own priority breakdown")
        return out
    commit = summary.get("source_sha")
    if not isinstance(commit, str) or not commit.strip():
        reasons.append(f"{summary_path.name} names no source_sha, so no commit to record the evidence at")
        return out
    matrix_commit = matrix.get("source_sha")
    if isinstance(matrix_commit, str) and matrix_commit.strip() and not _same_commit(matrix_commit, commit):
        reasons.append(f"the matrix measured {matrix_commit}, not the summary's {commit}")
        return out
    story_text = gate_eval._read_text(Path(args.story_file))
    if story_text is None:
        reasons.append(f"story file {args.story_file} could not be read")
        return out

    tagged = operator_acs(story_text)
    dispositions: dict[str, list[str]] = {}
    for record in live_records:
        if isinstance(record, dict) and isinstance(record.get("requirement_id"), str):
            dispositions.setdefault(record["requirement_id"], []).append(str(record.get("disposition")))
    for requirement in requirements:
        if requirement.get("coverage") == "FULL":
            continue
        rid = str(requirement.get("id"))
        out["open"].append(rid)
        number = _AC_ID.match(rid)
        if not number or int(number.group(1)) not in tagged:
            reasons.append(
                f"{rid} is open ({requirement.get('coverage')}) and is not an AC the story "
                "tags **Gate-ability:** operator, so a re-loop can change it"
            )
            continue
        found = dispositions.get(rid, [])
        refuted = sorted({d for d in found if d in _REFUTED})
        if refuted:
            reasons.append(
                f"{rid}: its recorded evidence is {', '.join(refuted)}; that is a finding, not owed evidence"
            )
            continue
        out["operator"].append(rid)
        out["evidence"][rid] = ", ".join(sorted(set(found))) or "none"

    if not out["open"]:
        reasons.append("the gate reads FAIL but the matrix holds no criterion open")
        return out
    if out["open"] != out["operator"]:
        return out
    out["assessed_commit"] = commit.strip()
    out["owed"] = True
    reasons.append(
        f"only operator evidence is owed: {', '.join(out['operator'])}, at commit {out['assessed_commit']}"
    )
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Say whether a story's gate FAIL is one only operator evidence can change."
    )
    parser.add_argument("--trace-output", required=True, help="The trace directory the gate read.")
    parser.add_argument("--story", required=True, help="The story id, as the gate took it.")
    parser.add_argument("--story-file", required=True, help="PATH to the story file holding its ACs.")
    parser.add_argument("--profile", required=True, choices=["light", "production"])
    parser.add_argument("--tests-ran", required=True, help="PATH to the story's .tests-ran-<story_id> marker.")
    parser.add_argument("--nfr", help="PATH to the story's NFR assessment (production).")
    parser.add_argument("--test-review", help="PATH to the story's test review (production).")
    parser.add_argument("--cycle-profile", choices=["full", "delta"], help="Exactly as the gate took it.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(json.dumps(evaluate(args), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
