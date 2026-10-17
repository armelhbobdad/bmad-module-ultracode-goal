#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""The step-3 answers reach the readiness verdict (`formalize_check.py --scan`).

The kernel flags judgment candidates; the step-3 subagent confirms or clears
each into `reds` or `concerns`. Before `--scan`, nothing carried that answer
back, so the kernel read `blocked` on any Epic where it flagged a candidate,
however the candidate was judged, and the hard gate's "`ready` and only
`ready`" clause could not be met. These tests pin:

- each candidate's line-free `id` (`<kind>:<bare path>:<digest>`), which
  survives an edit above the candidate and a re-spacing of its line, and
  changes when the line is reworded, for a story candidate and a TEA one
  alike; two candidates on one line (two undeclared ids cited) get two ids;
- `--scan`: a candidate a red or a concern answers by its `candidate` id AND
  its `source` is judged (`judged_candidates`, with `judged_as`) and stops
  setting judgment_required, so `ready` is reachable; an unanswered one keeps
  `blocked`; an entry naming no candidate's id, or the right id at another
  source, judges nothing; two candidates on the same text share an id and
  are told apart by source; a pair both lists name reads as `red`;
- fail-closed reading: a missing or unparseable scan, or one red_ids.py
  refuses (no `reds` list, a red with no string `kind`, `source` or
  `decision_needed`), judges nothing and says `read: false`, and the kernel
  reads a scan exactly when red_ids.py accepts it; `-` reads stdin and a
  relative path resolves against the project root;
- the headless adapter names a confirmed candidate as a blocker at a `ready`
  verdict too, before any unanswered one;
- the docs: preflight step 2 closes on a re-run of the kernel and step 3 is
  seeded from it, carries `candidate` in its contract and re-runs the kernel
  with `--scan`; step 4 reads that re-run's verdict; ucg-formalize maps the
  re-run verdict and rejects an unanswered candidate.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_formalize_scan_answers.py -v
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS / "formalize_check.py"
RED_IDS = SCRIPTS / "red_ids.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "formalize" / "unclassified_signal_epic"
SKILL_ROOT = SCRIPTS.parent
PREFLIGHT = SKILL_ROOT / "references" / "preflight.md"
UCG_FORMALIZE = SKILL_ROOT.parent / "ucg-formalize" / "SKILL.md"
STORY = Path("impl-artifacts") / "4-1-signal.md"


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(FIXTURE, root)
    return root


def _run(root: Path, *extra: str, stdin: str | None = None) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--epic",
            "4",
            "--project-root",
            str(root),
            "--planning-artifacts",
            str(root / "planning-artifacts"),
            "--impl-artifacts",
            str(root / "impl-artifacts"),
            "--tea-config",
            str(root / "tea" / "config.yaml"),
            *extra,
        ],
        capture_output=True,
        text=True,
        input=stdin,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _write_scan(tmp_path: Path, scan: object) -> Path:
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(scan), encoding="utf-8")
    return path


def _concern(candidate: str | None, source: str = str(STORY) + ":15") -> dict:
    entry = {"source": source, "note": "cosmetic"}
    if candidate is not None:
        entry["candidate"] = candidate
    return entry


def _red(candidate: str, source: str = str(STORY) + ":15") -> dict:
    return {
        "source": source,
        "kind": "undecided-product",
        "decision_needed": "decide it",
        "evidence": "the line",
        "candidate": candidate,
    }


def test_the_fixture_is_blocked_on_one_candidate_alone(tmp_path):
    # The starting point the scan has to move: no mechanical gap, one candidate.
    out = _run(_project(tmp_path))
    assert out["verdict"] == "blocked"
    assert out["mechanical_budget"] == 0
    assert len(out["judgment_candidates"]) == 1
    assert out["judged_candidates"] == []
    assert out["scan"] is None


def test_a_candidate_id_is_line_free_and_survives_an_edit_above_it(tmp_path):
    root = _project(tmp_path)
    before = _run(root)["judgment_candidates"][0]
    # The kernel reports paths with the platform separator, in the id as in `source`.
    assert re.fullmatch(r"unclassified_signal:%s:[0-9a-f]{12}" % re.escape(str(STORY)), before["id"])
    story = root / STORY
    story.write_text("A line added above everything.\n" + story.read_text(encoding="utf-8"), encoding="utf-8")
    after = _run(root)["judgment_candidates"][0]
    assert after["source"] != before["source"]
    assert after["id"] == before["id"]


def test_a_concern_that_answers_the_candidate_reaches_ready(tmp_path):
    root = _project(tmp_path)
    candidate = _run(root)["judgment_candidates"][0]
    out = _run(root, "--scan", str(_write_scan(tmp_path, {"reds": [], "concerns": [_concern(candidate["id"])]})))
    assert out["verdict"] == "ready"
    assert out["ready"] is True
    assert out["judgment_required"] is False
    assert out["judgment_candidates"] == []
    assert out["judged_candidates"] == [{**candidate, "judged_as": "concern"}]
    assert out["scan"]["read"] is True
    assert out["scan"]["answered"] == 1


def test_a_confirmed_candidate_is_judged_as_red(tmp_path):
    # Confirmed, it is a RED the hard gate's reds stream reads: the kernel no
    # longer owes a judgment on it, and the gate still blocks on the red.
    root = _project(tmp_path)
    candidate = _run(root)["judgment_candidates"][0]
    out = _run(root, "--scan", str(_write_scan(tmp_path, {"reds": [_red(candidate["id"])], "concerns": []})))
    assert out["judged_candidates"][0]["judged_as"] == "red"
    assert out["judgment_required"] is False
    # The kernel reads `ready`: the red blocks through the reds stream, which
    # red_ids.py computes from this same scan, not through the kernel verdict.
    assert out["verdict"] == "ready"


def test_an_id_both_lists_name_reads_as_red(tmp_path):
    root = _project(tmp_path)
    cid = _run(root)["judgment_candidates"][0]["id"]
    out = _run(root, "--scan", str(_write_scan(tmp_path, {"reds": [_red(cid)], "concerns": [_concern(cid)]})))
    assert out["judged_candidates"][0]["judged_as"] == "red"


def test_an_unanswered_candidate_keeps_the_verdict_blocked(tmp_path):
    root = _project(tmp_path)
    # A concern at the candidate's very line, but with no id: a source alone is no answer.
    out = _run(root, "--scan", str(_write_scan(tmp_path, {"reds": [], "concerns": [_concern(None)]})))
    assert out["verdict"] == "blocked"
    assert len(out["judgment_candidates"]) == 1
    assert out["judged_candidates"] == []
    assert out["scan"] == {"path": str(tmp_path / "scan.json"), "read": True, "answered": 0}


def test_an_entry_naming_no_candidate_judges_nothing(tmp_path):
    root = _project(tmp_path)
    scan = {"reds": [], "concerns": [_concern("unclassified_signal:impl-artifacts/4-1-signal.md:000000000000")]}
    out = _run(root, "--scan", str(_write_scan(tmp_path, scan)))
    assert out["verdict"] == "blocked"
    assert out["judged_candidates"] == []


def test_the_right_id_at_another_source_judges_nothing(tmp_path):
    # The id names the text, the source names the place: an answer seeded from
    # a run whose lines have since moved names a source the candidate no longer
    # has, and it must not judge the candidate now at the line it named.
    root = _project(tmp_path)
    cid = _run(root)["judgment_candidates"][0]["id"]
    scan = {"reds": [], "concerns": [_concern(cid, source=str(STORY) + ":16")]}
    out = _run(root, "--scan", str(_write_scan(tmp_path, scan)))
    assert out["verdict"] == "blocked"
    assert out["judged_candidates"] == []


def test_two_candidates_on_the_same_text_are_told_apart_by_source(tmp_path):
    root = _project(tmp_path)
    story = root / STORY
    flagged = "   for: UCG-UNCLASSIFIED-SIGNAL on this load-bearing line.\n"
    story.write_text(
        story.read_text(encoding="utf-8")
        + "2. A second criterion, flagged on the same words:\n"
        + flagged
        + "   - *Verification:* pytest test asserts the second key set.\n"
        + "   - *Anti-vacuous twin:* AND a mutation dropping a key must FAIL the test.\n"
        + "   - *Split:* `ci-deterministic`\n",
        encoding="utf-8",
    )
    first, second = _run(root)["judgment_candidates"]
    assert first["id"] == second["id"]
    assert first["source"] != second["source"]
    one = _run(root, "--scan", str(_write_scan(tmp_path, {"reds": [], "concerns": [_concern(first["id"])]})))
    assert one["verdict"] == "blocked"
    assert [c["source"] for c in one["judged_candidates"]] == [first["source"]]
    assert [c["source"] for c in one["judgment_candidates"]] == [second["source"]]
    both = {"reds": [], "concerns": [_concern(first["id"]), _concern(second["id"], source=second["source"])]}
    assert _run(root, "--scan", str(_write_scan(tmp_path, both)))["verdict"] == "ready"


def test_a_reworded_line_changes_the_id_and_the_old_answer_judges_nothing(tmp_path):
    # The id is the stale-line guard: same source, different text, so an answer
    # the subagent gave to the old line must not judge the new one.
    root = _project(tmp_path)
    before = _run(root)["judgment_candidates"][0]
    story = root / STORY
    text = story.read_text(encoding="utf-8")
    old = "   for: UCG-UNCLASSIFIED-SIGNAL on this load-bearing line."
    story.write_text(text.replace(old, "   for: UCG-UNCLASSIFIED-SIGNAL on a line that now says something else."), encoding="utf-8")
    after = _run(root)["judgment_candidates"][0]
    assert after["source"] == before["source"]
    assert after["id"] != before["id"]
    out = _run(root, "--scan", str(_write_scan(tmp_path, {"reds": [], "concerns": [_concern(before["id"])]})))
    assert out["verdict"] == "blocked"
    assert out["judged_candidates"] == []


def test_two_candidates_on_one_line_get_two_ids(tmp_path):
    # An AC row citing two ids nobody declares flags each on the same line: one
    # answer must judge the one it names, never both.
    root = _project(tmp_path)
    story = root / STORY
    story.write_text(story.read_text(encoding="utf-8") + "   - traces: FR-901, FR-902\n", encoding="utf-8")
    orphans = [c for c in _run(root)["judgment_candidates"] if c["kind"] == "orphaned_index"]
    assert len(orphans) == 2
    assert orphans[0]["source"] == orphans[1]["source"]
    assert orphans[0]["id"] != orphans[1]["id"]
    assert "FR-901" in orphans[0]["why_machine_cannot_decide"]
    scan = {"reds": [], "concerns": [_concern(orphans[0]["id"], source=orphans[0]["source"])]}
    out = _run(root, "--scan", str(_write_scan(tmp_path, scan)))
    assert [c["id"] for c in out["judged_candidates"]] == [orphans[0]["id"]]
    assert orphans[1]["id"] in [c["id"] for c in out["judgment_candidates"]]


def test_a_re_spaced_line_keeps_its_id(tmp_path):
    root = _project(tmp_path)
    before = _run(root)["judgment_candidates"][0]
    story = root / STORY
    text = story.read_text(encoding="utf-8")
    old = "   for: UCG-UNCLASSIFIED-SIGNAL on this load-bearing line."
    assert text.count(old) == 1
    story.write_text(text.replace(old, "   for:   UCG-UNCLASSIFIED-SIGNAL  on this\tload-bearing line.  "), encoding="utf-8")
    after = _run(root)["judgment_candidates"][0]
    assert after["source"] == before["source"]
    assert after["id"] == before["id"]


def _tea_files(root: Path, design_line: str, nfr_category: str) -> None:
    trace = root / "tea" / "traceability"
    (trace / "test-design-epic-4.md").write_text("# Test design\n\n%s\n" % design_line, encoding="utf-8")
    (trace / "nfr-assessment.md").write_text(
        "overallStatus: PASS\n\n| Category | Threshold | Status |\n|---|---|---|\n| %s | UNKNOWN | PASS |\n" % nfr_category,
        encoding="utf-8",
    )


def test_a_tea_candidate_carries_an_id_and_can_be_answered(tmp_path):
    root = _project(tmp_path)
    _tea_files(root, "Latency must stay under 200 ms at p95.", "Performance")
    candidates = {c["kind"]: c for c in _run(root)["judgment_candidates"]}
    nfr, design = candidates["nfr_pass_on_unknown"], candidates["invented_nfr_threshold"]
    nfr_rel = str(Path("tea") / "traceability" / "nfr-assessment.md")
    assert nfr["source"] == nfr_rel + ":5"
    assert design["source"] == str(Path("tea") / "traceability" / "test-design-epic-4.md") + ":3"
    assert re.fullmatch(r"nfr_pass_on_unknown:%s:[0-9a-f]{12}" % re.escape(nfr_rel), nfr["id"])
    scan = {"reds": [], "concerns": [_concern(c["id"], source=c["source"]) for c in candidates.values()]}
    out = _run(root, "--scan", str(_write_scan(tmp_path, scan)))
    assert out["judgment_candidates"] == []
    assert {c["kind"] for c in out["judged_candidates"]} == set(candidates)


def test_a_tea_candidate_id_reads_the_tea_line(tmp_path):
    # The TEA texts are registered for the digest: a reworded TEA line at the
    # same source must change the id, as a story line does.
    root = _project(tmp_path)
    _tea_files(root, "Latency must stay under 200 ms at p95.", "Performance")
    before = {c["kind"]: c for c in _run(root)["judgment_candidates"]}
    _tea_files(root, "Throughput must reach 500 rps at peak.", "Availability")
    after = {c["kind"]: c for c in _run(root)["judgment_candidates"]}
    for kind in ("nfr_pass_on_unknown", "invented_nfr_threshold"):
        assert after[kind]["source"] == before[kind]["source"], kind
        assert after[kind]["id"] != before[kind]["id"], kind


def test_a_scan_red_ids_refuses_judges_nothing(tmp_path):
    # red_ids.py refuses these scans and computes no reds, so the kernel must
    # not read `ready` over them either.
    root = _project(tmp_path)
    cid = _run(root)["judgment_candidates"][0]["id"]
    answer = _concern(cid)
    no_decision = {**_red("unrelated"), "decision_needed": "  "}
    no_kind = {k: v for k, v in _red("unrelated").items() if k != "kind"}
    for scan in (
        {"concerns": [answer]},
        {"reds": {}, "concerns": [answer]},
        {"reds": [no_decision], "concerns": [answer]},
        {"reds": [no_kind], "concerns": [answer]},
        {"reds": ["a red"], "concerns": [answer]},
        {"reds": [], "concerns": answer},
    ):
        out = _run(root, "--scan", str(_write_scan(tmp_path, scan)))
        assert out["verdict"] == "blocked", scan
        assert out["scan"]["read"] is False, scan
        assert out["judged_candidates"] == [], scan


def test_the_kernel_reads_a_reds_list_exactly_when_red_ids_accepts_it(tmp_path):
    # The two read one scan: if the kernel judged candidates from a scan red_ids.py
    # refuses, it could read `ready` while the reds stream was never computed.
    # (`concerns` is left out: red_ids.py never reads it, and the kernel refusing
    # a non-list one only keeps the verdict `blocked`.)
    root = _project(tmp_path)
    cid = _run(root)["judgment_candidates"][0]["id"]
    answer = _concern(cid)
    red = _red("unrelated")
    scans = [
        {"reds": [], "concerns": [answer]},
        {"reds": [red], "concerns": [answer]},
        {"concerns": [answer]},
        {"reds": {}, "concerns": [answer]},
        {"reds": ["a red"], "concerns": [answer]},
    ]
    for field, bad in (("kind", 1), ("kind", True), ("kind", " "), ("source", ["x"]), ("source", {"a": 1}),
                       ("source", ""), ("decision_needed", 7), ("decision_needed", " "), ("decision_needed", None)):
        scans.append({"reds": [{**red, field: bad}], "concerns": [answer]})
    scans.append({"reds": [{k: v for k, v in red.items() if k != "kind"}], "concerns": [answer]})
    for field in ("decision_needed", "evidence"):
        scans.append({"reds": [{**red, field: "pick \ud800 one"}], "concerns": [answer]})
    impl = tmp_path / "red-ids-impl"
    impl.mkdir()
    for scan in scans:
        path = _write_scan(tmp_path, scan)
        proc = subprocess.run(
            [sys.executable, str(RED_IDS), "--scan", str(path), "--impl-artifacts", str(impl), "--dry-run"],
            capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode in (0, 2), (scan, proc.stderr)
        out = _run(root, "--scan", str(path))
        assert out["scan"]["read"] is (proc.returncode == 0), scan
        assert (out["verdict"] == "ready") is (proc.returncode == 0), scan


def _envelope_module():
    spec = importlib.util.spec_from_file_location("headless_envelope", SCRIPTS / "headless_envelope.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_adapter_names_a_confirmed_candidate_first_at_any_verdict(tmp_path):
    env = _envelope_module()
    root = _project(tmp_path)
    candidate = _run(root)["judgment_candidates"][0]
    ready = _run(root, "--scan", str(_write_scan(tmp_path, {"reds": [_red(candidate["id"])], "concerns": []})))
    assert ready["verdict"] == "ready"
    blockers = env.fr5_blockers(ready)
    assert [b["source"] for b in blockers] == [candidate["source"]]
    assert blockers[0]["kind"] == candidate["kind"]
    # Confirmed first, then the unanswered ones, on a blocked verdict.
    blocked = {**ready, "verdict": "blocked", "judgment_candidates": [{**candidate, "source": "other.md:1"}]}
    assert [b["source"] for b in env.fr5_blockers(blocked)] == [candidate["source"], "other.md:1"]
    # A cleared candidate is no blocker, and an unreadable verdict reads as one.
    cleared = _run(root, "--scan", str(_write_scan(tmp_path, {"reds": [], "concerns": [_concern(candidate["id"])]})))
    assert env.fr5_blockers(cleared) == []
    assert env.fr5_blockers({**ready, "verdict": "maybe"})[0]["kind"] == "unreadable"


def test_a_relative_scan_path_resolves_against_the_project_root(tmp_path):
    root = _project(tmp_path)
    cid = _run(root)["judgment_candidates"][0]["id"]
    (root / "impl-artifacts" / ".preflight-scan-x.json").write_text(
        json.dumps({"reds": [], "concerns": [_concern(cid)]}), encoding="utf-8"
    )
    out = _run(root, "--scan", "impl-artifacts/.preflight-scan-x.json")
    assert out["verdict"] == "ready"
    assert out["scan"]["path"] == str(root / "impl-artifacts" / ".preflight-scan-x.json")


def test_a_scan_that_cannot_be_read_judges_nothing(tmp_path):
    root = _project(tmp_path)
    cid = _run(root)["judgment_candidates"][0]["id"]
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    listed = _write_scan(tmp_path, [{"candidate": cid}])
    for path in (tmp_path / "missing.json", broken, listed):
        out = _run(root, "--scan", str(path))
        assert out["verdict"] == "blocked", path
        assert out["scan"] == {"path": str(path), "read": False, "answered": 0}, path


def test_the_scan_can_come_on_stdin(tmp_path):
    root = _project(tmp_path)
    cid = _run(root)["judgment_candidates"][0]["id"]
    out = _run(root, "--scan", "-", stdin=json.dumps({"reds": [], "concerns": [_concern(cid)]}))
    assert out["verdict"] == "ready"
    assert out["scan"]["path"] == "-"


# --- the docs that drive the scan --------------------------------------------


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = text.find("\n## ", start + len(heading))
    return text[start : nxt if nxt != -1 else len(text)]


def test_preflight_step2_closes_on_a_kernel_rerun_that_seeds_step3():
    text = PREFLIGHT.read_text(encoding="utf-8")
    step2 = _section(text, "## 2. Auto-remediation pass")
    assert "Then run step 1b's command again too, unchanged" in step2
    assert "Step 3 is seeded from this closing run, not from step 1b's." in step2
    # The loop iterates and is bounded.
    assert "fold it in the same way, once, and run both commands one more time, still within this pass" in step2
    assert "(its closing re-run included), never a separate remediation pass" in step2
    step3 = _section(text, "## 3. Semantic intervention scan")
    assert "(from step 2's closing re-run of step 1b's command" in step3
    assert "its `source:line`, copied as given, in `source`" in step3


def test_preflight_step3_fails_the_gate_on_a_refused_scan():
    step3 = _section(PREFLIGHT.read_text(encoding="utf-8"), "## 3. Semantic intervention scan")
    assert "**A non-zero exit fails the gate.**" in step3
    assert "which is not the same as an empty one" in step3
    step4 = _section(PREFLIGHT.read_text(encoding="utf-8"), "## 4. Hard gate")
    assert "a stream `red_ids.py` never computed (a non-zero exit) fails this clause" in step4


def test_preflight_step3_seeds_ids_and_reruns_the_kernel_with_the_scan():
    step3 = _section(PREFLIGHT.read_text(encoding="utf-8"), "## 3. Semantic intervention scan")
    assert "each candidate's `id`, `source:line` and `why_machine_cannot_decide`" in step3
    assert "The answers match on that pair, never on `source` alone" in step3
    assert "Record each seeded candidate the subagent cleared there too" in step3
    fence = re.search(r"```json\n(.*?)```", step3, re.DOTALL).group(1)
    assert fence.count('"candidate"') == 2, "both reds and concerns entries carry the answered candidate id"
    assert "run step 1b's command again, unchanged, with `--scan " in step3
    assert ".preflight-scan-<run-id>.json` appended" in step3
    assert "This re-run's verdict, not step 1b's, is the one the step-4 hard gate reads." in step3


def test_preflight_step4_reads_the_post_scan_verdict():
    step4 = _section(PREFLIGHT.read_text(encoding="utf-8"), "## 4. Hard gate")
    clause = next(line for line in step4.splitlines() if "formalize_check.py verdict" in line)
    assert "post-scan formalize_check.py verdict is `ready`" in clause
    assert "every judgment candidate answered" in clause
    assert "step 3's kernel re-run on the answered scan" in clause


def test_ucg_formalize_maps_the_rerun_verdict_and_rejects_an_unanswered_candidate():
    text = UCG_FORMALIZE.read_text(encoding="utf-8")
    step3 = _section(text, "## 3. Judgment subagent")
    assert "--scan -" in step3
    # The degraded inline read still runs the id layer and the re-run.
    assert "Then run the id layer and the kernel re-run above on it" in step3
    mapping = _section(text, "## 4. Verdict mapping")
    assert (
        "| re-run kernel `verdict == ready` (`mechanical_budget == 0`, every judgment candidate answered)"
        " AND no reds | accept | `status=complete` |"
    ) in mapping
    # The unanswered-candidate row holds whatever the budget: with remediable gaps
    # left it is not the remediate row (that one needs verdict remediable).
    assert "no scan entry answered, whatever the budget | reject | `status=blocked` |" in mapping
    assert "| re-run kernel verdict unreadable, absent, or none of" in mapping
    assert "re-run the kernel with the same scan object (`--scan -`; the judgment pass is not spawned again)" in mapping
    assert "then judgment candidates no scan entry answered" in mapping
    assert "with a judgment candidate no scan entry answered" in mapping
    # The old row that rejected an Epic whose every candidate was cleared is gone.
    assert "because the subagent cleared every flagged candidate into `concerns`" not in mapping
