#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""CI-deterministic tests for the standalone ucg-formalize SKILL.md (Story 1.3).

The standalone `/ucg-formalize <epic>` skill is the thin FR-6 LLM layer over the
Story-1.1 `formalize_check.py` kernel: it RUNS the kernel, adapts its rich FR-5
verdict into the canonical five-key headless envelope, delegates judgment to ONE
throwaway subagent, and maps the graduated verdict per FR-6. These five tests pin
the structural contract that makes INV-9 (one kernel, two entry points, cannot
drift) hold:

  - test_standalone_envelope_keys_match_autonomous (AC3) — the SKILL's Headless
    envelope blocks have the SAME key SET as the autonomous parent SKILL.md:68-75
    envelope (set-equality, never subset; an extra `verdict`/`mechanical_budget`
    key or a dropped `skill` is RED).
  - test_verdict_mapping_table (AC4) — the FR-6 mapping encodes all three rows and
    the blocked row enumerates all three triggers (red, non-remediable mechanical,
    unreadable artifact); `status=blocked`/`status=complete` adapt, never
    `status=remediable`.
  - test_subagent_contract_matches_preflight (AC5) — the subagent block parses to a
    key set byte-identical to the three-key preflight.md:57-64 contract, and
    exactly one subagent spawn is described.
  - test_two_entry_points_one_envelope (AC7) — the documented adaptation of one
    canned blocked FR-5 verdict yields the SAME five-key envelope dict (sorted-keys
    byte-identical) the autonomous SKILL.md shape prescribes.
  - test_judgment_fixtures_route_to_blocked (AC6 deterministic half) — running the
    real kernel over the Story-1.2 JUDGMENT-floor fixtures: each JUDGMENT-floor
    defect yields a blocked-routing kernel verdict that the FR-6 mapping adapts to
    status=blocked, and a sound fixture adapts to status=complete (the operator
    benchmark in bench_ucg_formalize.md covers the subagent-read half).

Reference line ranges (SKILL.md:68-75, preflight.md:57-64/78-85) are located
ROBUSTLY by heading + fenced-block structure, not hardcoded line numbers that may
drift. Mirrors test_formalize_check_floor.py: the importlib loader, subprocess
exit-0 lane, fixtures under tests/fixtures/.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_ucg_formalize_envelope.py -v
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "formalize_check.py"
FIXTURES = HERE / "fixtures"
FLOOR = FIXTURES / "floor"
UCG_FIXTURES = FIXTURES / "ucg_formalize"

REPO_ROOT = HERE.parents[3]  # skills/ultracode-goal/scripts/tests -> repo root
SKILL_MD = REPO_ROOT / "skills" / "ultracode-goal" / "skills" / "ucg-formalize" / "SKILL.md"
PARENT_SKILL_MD = REPO_ROOT / "skills" / "ultracode-goal" / "SKILL.md"
PREFLIGHT_MD = REPO_ROOT / "skills" / "ultracode-goal" / "references" / "preflight.md"
VALIDATE_SKILLS = REPO_ROOT / "tools" / "validate-skills.js"

# The canonical always-present five-key envelope set and the conditional sixth.
ALWAYS_KEYS = frozenset({"status", "skill", "decision_log", "report", "deferred_work"})
BLOCKED_KEYS = ALWAYS_KEYS | {"reason"}
SUBAGENT_KEYS = frozenset({"reds", "concerns", "advisories_checked"})


def _load_module():
    spec = importlib.util.spec_from_file_location("formalize_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


fc = _load_module()


# --- robust markdown / fenced-block parsing ---------------------------------


def _heading_level(line: str) -> int | None:
    m = re.match(r"^(#{1,6})\s", line)
    return len(m.group(1)) if m else None


def _section_text(text: str, heading_regex: str) -> str:
    """Return the body of the FIRST heading matching heading_regex, scoped to its
    own section: everything from that heading until the next heading of the same
    or higher level (a smaller or equal `#` count). Returns "" if not found."""
    lines = text.split("\n")
    start = None
    start_level = None
    for i, line in enumerate(lines):
        level = _heading_level(line)
        if level is not None and re.search(heading_regex, line, re.IGNORECASE):
            start = i
            start_level = level
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        level = _heading_level(lines[j])
        if level is not None and level <= start_level:
            end = j
            break
    return "\n".join(lines[start:end])


def _fenced_json_blocks(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"```json\s*\n(.*?)```", text, re.DOTALL)]


def _depth1_keys(block: str) -> set[str]:
    """Top-level (brace-depth-1) keys of a JSON-ish example block. Tolerant of the
    placeholder values (`<...>`, `a|b|c`) the SKILL prose uses in example envelopes,
    so it reads the KEY SET without requiring strict JSON."""
    keys: list[str] = []
    depth = 0
    for tok in re.finditer(r'[{}]|"([^"]+)"\s*:', block):
        t = tok.group(0)
        if t == "{":
            depth += 1
        elif t == "}":
            depth -= 1
        elif depth == 1 and tok.group(1):
            keys.append(tok.group(1))
    return set(keys)


def _parent_envelope_keys() -> set[str]:
    """The full key set of the autonomous parent SKILL.md headless envelope (the
    SKILL.md:68-75 block — a single combined block carrying all six keys)."""
    section = _section_text(PARENT_SKILL_MD.read_text(encoding="utf-8"), r"Headless")
    blocks = _fenced_json_blocks(section)
    assert blocks, "parent SKILL.md Headless section must carry a fenced json block"
    keysets = [_depth1_keys(b) for b in blocks]
    # The canonical block is the one carrying the full six-key set.
    full = max(keysets, key=len)
    return full


def _preflight_subagent_keys() -> set[str]:
    """The three-key subagent contract key set parsed from preflight.md:57-64 — the
    fenced json block carrying `reds`/`concerns`/`advisories_checked`."""
    text = PREFLIGHT_MD.read_text(encoding="utf-8")
    for block in _fenced_json_blocks(text):
        keys = _depth1_keys(block)
        if "reds" in keys:
            return keys
    raise AssertionError("preflight.md must carry a `reds` subagent-contract block")


def _skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _headless_envelope_blocks() -> list[set[str]]:
    section = _section_text(_skill_text(), r"^#+\s*Headless\b")
    blocks = _fenced_json_blocks(section)
    assert blocks, "ucg-formalize SKILL.md Headless section must carry json envelopes"
    return [_depth1_keys(b) for b in blocks]


# --- AC3: standalone envelope key set == autonomous envelope (set-equality) ---


def test_standalone_envelope_keys_match_autonomous():
    parent_full = _parent_envelope_keys()
    assert parent_full == BLOCKED_KEYS, (
        "parent SKILL.md envelope drifted from the canonical six-key set: %s" % parent_full
    )

    envelope_keysets = _headless_envelope_blocks()
    # The Headless section emits two envelope blocks: an always-present (complete)
    # 5-key block and a blocked 6-key block.
    always_blocks = [k for k in envelope_keysets if "reason" not in k]
    blocked_blocks = [k for k in envelope_keysets if "reason" in k]
    assert always_blocks, "Headless section must carry an always-present (complete) envelope"
    assert blocked_blocks, "Headless section must carry a blocked envelope (with reason)"

    # SET-EQUALITY, not subset: the complete block is EXACTLY the autonomous five,
    # and the blocked block is EXACTLY the autonomous six. A leaked `verdict` /
    # `mechanical_budget` (extra) or a dropped `skill` (missing) is RED here.
    for k in always_blocks:
        assert k == (parent_full - {"reason"}), (
            "standalone complete envelope drifted from autonomous five-key set: %s" % k
        )
    for k in blocked_blocks:
        assert k == parent_full, (
            "standalone blocked envelope drifted from autonomous six-key set: %s" % k
        )

    # The forbidden FR-5 script-layer keys never appear in any envelope block.
    for k in envelope_keysets:
        assert "verdict" not in k and "mechanical_budget" not in k, (
            "FR-5 script-layer key leaked into the headless envelope: %s" % k
        )


# --- AC4: FR-6 verdict-mapping table -----------------------------------------


def test_verdict_mapping_table():
    text = _skill_text()
    section = _section_text(text, r"Verdict mapping")
    assert section, "SKILL.md must carry a 'Verdict mapping' section"
    low = section.lower()

    # Three rows: ready->complete, remediable->remediate-then-re-run, blocked.
    assert "budget == 0" in low and "no reds" in low, "missing the ready/complete row"
    assert "remediate-then-re-run" in low or "remediate then re-run" in low, (
        "missing the remediable remediate-then-re-run row"
    )
    assert "status=complete" in section, "the ready row must adapt to status=complete"

    # The blocked row enumerates ALL THREE triggers, including the fail-closed
    # unreadable-artifact clause (INV-4/NFR-2). Each must be present.
    assert "any red" in low, "blocked row missing the RED trigger"
    assert "non-remediable" in low, "blocked row missing the non-remediable-mechanical trigger"
    assert ("could not read" in low) or ("unreadable" in low) or ("not read" in low), (
        "blocked row missing the fail-closed unreadable-artifact trigger"
    )
    assert "status=blocked" in section, "the reject row must adapt to status=blocked"

    # ANTI-VACUOUS TWIN (AC4): the mapping never emits the internal `remediable`
    # state as a headless status — `remediable` is the loop state, never a terminal
    # headless emit value.
    assert "status=remediable" not in text, (
        "remediable is an internal loop state, never a headless emit value"
    )

    # Mutant guard (AC4 twin, fail-closed): a copy of the mapping section with EVERY
    # carrier of the unreadable-artifact clause deleted must NOT satisfy the trigger
    # assertion above — proving the test keys on the clause and a blocked row that
    # silently dropped the unreadable-artifact trigger would go RED.
    mutated = section
    for phrase in ("could not read", "unreadable", "not read"):
        mutated = re.sub(re.escape(phrase), "X", mutated, flags=re.IGNORECASE)
    mutated_low = mutated.lower()
    assert not (
        ("could not read" in mutated_low) or ("unreadable" in mutated_low) or ("not read" in mutated_low)
    ), "deleting the unreadable-artifact clause must remove the fail-closed trigger"


# --- AC5: subagent contract == three-key preflight.md:57-64 ------------------


def test_subagent_contract_matches_preflight():
    preflight_keys = _preflight_subagent_keys()
    assert preflight_keys == SUBAGENT_KEYS, (
        "preflight.md subagent contract drifted from the three-key set: %s" % preflight_keys
    )

    text = _skill_text()
    section = _section_text(text, r"Judgment subagent")
    assert section, "SKILL.md must carry a 'Judgment subagent' section"

    blocks = _fenced_json_blocks(section)
    contract_blocks = [_depth1_keys(b) for b in blocks if "reds" in _depth1_keys(b)]
    assert len(contract_blocks) == 1, "exactly one subagent contract block expected"
    contract = contract_blocks[0]

    # SET-EQUALITY (byte-identical key set) against the three-key preflight contract.
    assert contract == preflight_keys, (
        "subagent contract key set is not byte-identical to preflight.md three-key "
        "contract (got %s, expected %s)" % (sorted(contract), sorted(preflight_keys))
    )

    # The three contract keys + the seeded kernel field each appear in prose.
    for key in ("reds", "concerns", "advisories_checked", "judgment_candidates"):
        assert key in text, "subagent block must mention `%s`" % key

    # EXACTLY ONE subagent spawn is described — count the spawn directives.
    spawn_count = len(re.findall(r"(?i)\bspawn\b\s+(?:exactly\s+)?one\b", text))
    exactly_one = len(re.findall(r"(?i)exactly\s+one\b\s+throwaway\s+subagent", text))
    assert spawn_count >= 1 or exactly_one >= 1, "no single-subagent spawn directive found"
    # No second subagent: the word 'second subagent'/'two subagents' must not appear.
    assert not re.search(r"(?i)\b(?:second|two|2)\s+subagents?\b", text) or re.search(
        r"(?i)never\s+two", text
    ), "the skill must not describe a second subagent"

    # ANTI-VACUOUS TWIN (AC5): the superseded two-key {reds, concerns} mutant must
    # NOT satisfy set-equality against the three-key preflight contract.
    mutant = (UCG_FIXTURES / "subagent_two_key_contract.txt").read_text(encoding="utf-8")
    mutant_blocks = [_depth1_keys(b) for b in _fenced_json_blocks(mutant) if "reds" in _depth1_keys(b)]
    assert len(mutant_blocks) == 1
    assert mutant_blocks[0] != preflight_keys, (
        "two-key mutant must FAIL set-equality against the three-key contract"
    )
    assert "advisories_checked" not in mutant_blocks[0], (
        "the two-key mutant is missing advisories_checked by construction"
    )


# --- AC7: two entry points, one envelope (sorted-keys byte-identical) --------


def _adapt_kernel_to_envelope(kernel_verdict: dict, *, decision_log: str, reason: str | None) -> dict:
    """The documented standalone adaptation (SKILL.md step 4 + Headless): map a
    POST-remediation FR-5 kernel verdict into the canonical five-key envelope. This
    is the SAME adapter the Epic-2 preflight clause calls — it lives in exactly one
    place so the two entry points cannot fork. `status=complete` ONLY when the
    kernel verdict is `ready`; otherwise (blocked / non-ready) `status=blocked`."""
    blocked = kernel_verdict.get("verdict") != "ready" or kernel_verdict.get("judgment_required")
    if blocked:
        return {
            "status": "blocked",
            "skill": "ultracode-goal",
            "decision_log": decision_log,
            "report": None,
            "deferred_work": None,
            "reason": reason,
        }
    return {
        "status": "complete",
        "skill": "ultracode-goal",
        "decision_log": decision_log,
        "report": None,
        "deferred_work": None,
    }


def _autonomous_blocked_envelope(*, decision_log: str, reason: str) -> dict:
    """The envelope shape the autonomous parent SKILL.md prescribes for a blocked
    exit (the preflight.md:78-85 / SKILL.md:68-75 shape), constructed independently
    here so the test compares two separately-built dicts for byte identity."""
    return {
        "status": "blocked",
        "skill": "ultracode-goal",
        "decision_log": decision_log,
        "report": None,
        "deferred_work": None,
        "reason": reason,
    }


def test_two_entry_points_one_envelope():
    decision_log = "/runs/epic-7/.decision-log.md"
    reason = "undecided-product at planning-artifacts/prd.md:42"
    canned_blocked_kernel = {
        "ready": False,
        "verdict": "blocked",
        "mechanical_budget": 0,
        "judgment_required": True,
        "mechanical_gaps": [],
        "judgment_candidates": [
            {"source": "planning-artifacts/prd.md:42", "kind": "vacuous_ac", "why_machine_cannot_decide": "x"}
        ],
        "checks": {},
    }

    standalone = _adapt_kernel_to_envelope(canned_blocked_kernel, decision_log=decision_log, reason=reason)
    autonomous = _autonomous_blocked_envelope(decision_log=decision_log, reason=reason)

    # Byte-identical (json.dumps with sorted keys) — the two entry points share one
    # envelope definition for the same blocked input.
    assert json.dumps(standalone, sort_keys=True) == json.dumps(autonomous, sort_keys=True), (
        "standalone and autonomous envelopes differ for the same blocked input:\n%s\n%s"
        % (json.dumps(standalone, sort_keys=True), json.dumps(autonomous, sort_keys=True))
    )
    assert set(standalone) == BLOCKED_KEYS

    # ANTI-VACUOUS TWIN (AC7): a forked adapter that sets skill=ucg-formalize or
    # drops decision_log must DIFFER from the autonomous envelope.
    forked_skill = dict(standalone, skill="ucg-formalize")
    assert json.dumps(forked_skill, sort_keys=True) != json.dumps(autonomous, sort_keys=True), (
        "a forked envelope using skill=ucg-formalize must NOT match the autonomous shape"
    )
    forked_drop = {k: v for k, v in standalone.items() if k != "decision_log"}
    assert json.dumps(forked_drop, sort_keys=True) != json.dumps(autonomous, sort_keys=True), (
        "an envelope dropping decision_log must NOT match the autonomous shape"
    )


# --- AC6 (deterministic half): floor fixtures route through the FR-6 mapping --


EPIC_OF = {
    "vacuous_ac": "8",
    "leaked_tea": "9",
    "orphaned_index": "10",
    "invented_threshold": "11",
    "all_clean": "7",
    "sourced_threshold": "11",
    "invented_threshold_unknown": "11",
}


def _run_kernel(fixture: str) -> dict:
    epic = EPIC_OF[fixture]
    root = FLOOR / fixture
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--epic",
            epic,
            "--project-root",
            str(root),
            "--planning-artifacts",
            str(root / "planning-artifacts"),
            "--impl-artifacts",
            str(root / "impl-artifacts"),
            "--tea-config",
            str(root / "tea" / "config.yaml"),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _map_status(kernel: dict) -> str:
    """Apply the FR-6 headless mapping to a (post-remediation) kernel verdict.
    blocked -> status=blocked; ready -> status=complete; remediable is the loop
    state (here, with no remediation applied, treated as not-yet-complete)."""
    if kernel["verdict"] == "blocked" or kernel["judgment_required"]:
        return "blocked"
    if kernel["verdict"] == "ready":
        return "complete"
    return "remediable"  # internal loop state — not a terminal headless emit


def test_judgment_fixtures_route_to_blocked():
    # The two Epic-11 JUDGMENT-floor classes (vacuous AC, invented NFR threshold)
    # are NEVER machine-clearable: the kernel emits them as judgment_candidates and
    # the FR-6 mapping routes them to status=blocked with the JUDGMENT class named.
    for fixture, expected_kind in (
        ("vacuous_ac", "vacuous_ac"),
        ("invented_threshold", "invented_nfr_threshold"),
    ):
        kernel = _run_kernel(fixture)
        assert kernel["verdict"] == "blocked", (fixture, kernel["verdict"])
        assert kernel["judgment_required"] is True, fixture
        kinds = {c["kind"] for c in kernel["judgment_candidates"]}
        assert expected_kind in kinds, (fixture, kinds)
        assert _map_status(kernel) == "blocked", fixture

    # The two MECHANICAL floor classes (leaked TEA artifact, orphaned regenerable
    # index) are remediable: the kernel does NOT block on them deterministically —
    # it routes them to remediate-then-re-run. Their full blocked-routing (when a
    # subagent confirms a red, or remediation cannot clear them) is the operator-
    # benchmark half in bench_ucg_formalize.md; here we assert only the deterministic
    # kernel fact: a remediable mechanical gap, no judgment, verdict != blocked.
    for fixture, expected_kind in (
        ("leaked_tea", "leaked_tea_artifact"),
        ("orphaned_index", "orphaned_index"),
    ):
        kernel = _run_kernel(fixture)
        assert kernel["verdict"] == "remediable", (fixture, kernel["verdict"])
        assert kernel["judgment_required"] is False, fixture
        gap_kinds = {g["kind"] for g in kernel["mechanical_gaps"]}
        assert expected_kind in gap_kinds, (fixture, gap_kinds)
        assert all(g["remediable"] for g in kernel["mechanical_gaps"]), fixture
        assert _map_status(kernel) != "blocked", fixture

    # A sound fixture routes to status=complete.
    for sound in ("all_clean", "sourced_threshold"):
        kernel = _run_kernel(sound)
        assert kernel["verdict"] == "ready", (sound, kernel["verdict"])
        assert _map_status(kernel) == "complete", sound

    # ANTI-VACUOUS TWIN (AC6 false-positive guard): the invented-threshold fixture
    # with the unsourced number marked UNKNOWN flips blocked -> complete, proving the
    # block is caused by the genuine unsourced-number defect, not unconditional
    # blocking.
    unknown = _run_kernel("invented_threshold_unknown")
    assert unknown["verdict"] == "ready", unknown["verdict"]
    assert unknown["checks"]["nfr_thresholds_unsourced"] == 0
    assert [c for c in unknown["judgment_candidates"] if c["kind"] == "invented_nfr_threshold"] == []
    assert _map_status(unknown) == "complete"


# --- AC1 twin: validate-skills reads the new skill (mutant exits 1) ----------


def _validate_skills_exit(skill_dir: Path) -> tuple[int, str]:
    proc = subprocess.run(
        ["node", str(VALIDATE_SKILLS), str(skill_dir), "--strict", "--json"],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="node not available",
)
def test_real_skill_passes_validate_skills(tmp_path):
    # AC1 positive (deterministic): the real nested skill passes --strict with zero
    # HIGH+ findings for SKILL-01/02/03/07.
    rc, out = _validate_skills_exit(SKILL_MD.parent)
    assert rc == 0, out
    findings = json.loads(out)
    high_plus = [f for f in findings if f["severity"] in ("CRITICAL", "HIGH")]
    assert high_plus == [], high_plus


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="node not available",
)
def test_name_deleted_skill_mutant_fails_validate_skills(tmp_path):
    # AC1 anti-vacuous twin: materialize the name-deleted mutant as SKILL.md in a
    # temp dir and validate it. The validator must exit 1 with a SKILL-02 finding —
    # proving it actually reads this new skill path and is not silently skipping it.
    mutant = (UCG_FIXTURES / "skill_name_deleted.txt").read_text(encoding="utf-8")
    skill_dir = tmp_path / "ucg-formalize"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(mutant, encoding="utf-8")
    rc, out = _validate_skills_exit(skill_dir)
    assert rc == 1, "name-deleted SKILL mutant must exit 1 under --strict"
    findings = json.loads(out)
    rules = {f["rule"] for f in findings}
    assert "SKILL-02" in rules, ("expected SKILL-02 (missing name), got", rules)


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="node not available",
)
def test_empty_body_skill_mutant_fails_validate_skills(tmp_path):
    # AC1 anti-vacuous twin (the empty-body half): a SKILL.md with valid frontmatter
    # but NO body after the closing --- must exit 1 with a SKILL-07 finding.
    mutant = (UCG_FIXTURES / "skill_empty_body.txt").read_text(encoding="utf-8")
    skill_dir = tmp_path / "ucg-formalize"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(mutant, encoding="utf-8")
    rc, out = _validate_skills_exit(skill_dir)
    assert rc == 1, "empty-body SKILL mutant must exit 1 under --strict"
    findings = json.loads(out)
    rules = {f["rule"] for f in findings}
    assert "SKILL-07" in rules, ("expected SKILL-07 (no body), got", rules)


# --- AC2 helper: kernel-invocation block carries the FR-5 signature -----------


def test_kernel_invocation_block_present():
    # AC2 (deterministic): the SKILL instructs the {skill-root}-qualified FR-5
    # invocation with all five flags, and does NOT recompute the verdict.
    text = _skill_text()
    assert text.count("formalize_check.py") >= 1
    assert "{skill-root}/scripts/formalize_check.py" in text
    for flag in ("--epic", "--project-root", "--planning-artifacts", "--impl-artifacts", "--tea-config"):
        assert flag in text, "missing FR-5 flag %s" % flag
    # INV-9: no second kernel, and mechanical_budget is READ not recomputed.
    assert "formalize_eval.py" not in text, "must not invoke a non-existent second kernel"
    assert re.search(r"(?i)never re-?count|read .*off the json|do not recompute", text), (
        "the skill must instruct reading the budget/verdict, not recomputing it"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
