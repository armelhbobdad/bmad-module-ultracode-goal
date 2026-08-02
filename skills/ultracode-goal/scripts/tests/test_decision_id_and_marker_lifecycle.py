"""Prose-contract tests for RED identity and run-marker lifecycle.

A blocked run is unblocked by matching an operator's recorded answer back to the
finding it answers. That match is by `id` only, so the identity rules and the
lifecycle of the files carrying them are load-bearing. These tests pin what a
quality scan found missing, each one guarding a defect that shipped green:

  - neither surface derives an id by hand: both call `scripts/red_ids.py`, because
    a join key two model invocations must agree on by hand is one they will
    eventually disagree on (+ twin: no hand-executable recipe may survive in the
    prose for a reader to follow instead);
  - `ucg-resolve` READS the stored id for a preflight RED and applies a close
    through the same script, so a second writer cannot strand the id an answer is
    keyed to;
  - `defer` is re-presented on a later pass, and only `close` suppresses, so a
    parked decision cannot deadlock the run;
  - `.decisions.json` is merged read-modify-write, not overwritten;
  - the turn counter is purged when arming a fresh run but NOT on resume, and is
    reset when an operator closes a `budget-overrun`;
  - a headless run clears a prior `run-result.json`, so presence means this run
    reached a terminal.

Cross-file assertions locate rules by CONTENT, never by hardcoded line number.
Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_INGEST = _SKILL_ROOT / "references" / "ingest-and-scope.md"
_PARENT_SKILL = _SKILL_ROOT / "SKILL.md"
_RESOLVE = _SKILL_ROOT.parent / "ucg-resolve" / "SKILL.md"
_STATUS = _SKILL_ROOT.parent / "ucg-status" / "SKILL.md"


def _preflight() -> str:
    return _PREFLIGHT.read_text(encoding="utf-8")


def _resolve() -> str:
    return _RESOLVE.read_text(encoding="utf-8")


def _canon(text: str) -> str:
    return " ".join(text.split())


# --- identity is owned by code, not by prose ----------------------------------
def test_both_surfaces_delegate_id_derivation_to_the_script():
    # The id is a join key between two sessions that never overlap. Two rounds of
    # prose specifying it by hand each shipped a deadlock, in opposite directions,
    # so the rule is now that neither surface derives one.
    for name, text in (("preflight.md", _preflight()), ("ucg-resolve", _resolve())):
        assert "red_ids.py" in text, f"{name} must call the id layer"
    assert re.search(r"[Dd]o not mint, compare, or edit an id by hand", _preflight()), (
        "preflight must forbid hand-minting outright"
    )
    assert re.search(r"[Nn]ever derive an id by hand", _resolve()), (
        "ucg-resolve must forbid hand-deriving outright"
    )


def test_no_hand_executable_id_recipe_survives_in_prose():
    # ANTI-VACUOUS TWIN: naming the script is not enough if a step-by-step recipe
    # is still sitting there for a reader to follow instead.
    for name, text in (("preflight.md", _preflight()), ("ucg-resolve", _resolve())):
        canon = _canon(text)
        assert not re.search(r"first \d+ characters of[^.]{0,40}decision_needed", canon), (
            f"{name} still carries a hand-executable slug recipe; the id must come from "
            "the script, or two sessions will derive it differently"
        )
        assert "collapsed to a single" not in canon, (
            f"{name} still spells out a character transform for the id"
        )


def test_the_sidecar_records_closed_ids_without_claiming_they_drive_matching():
    text = _canon(_preflight())
    assert "`resolved`" in text, "the sidecar must carry the closed-id list"
    assert re.search(r"audit record rather than part of the matching", text), (
        "the closed-id list must be described as a record, not as the mechanism that "
        "recognizes a decision: ids are derived, so recognition needs no lookup, and "
        "implying otherwise sends a reader looking for machinery that is not there"
    )
    assert re.search(r"re-derives to its own id", text), (
        "the prose must say how a closed decision is recognized on a rescan"
    )


def test_resolve_reads_the_persisted_id_for_preflight_reds():
    text = _canon(_resolve())
    assert re.search(r"read the `id` off the sidecar entry\W+never re-derive it", text, re.IGNORECASE), (
        "ucg-resolve must READ the stored id for preflight REDs"
    )
    assert re.search(r"hard-capped at four fields and cannot carry one", text), (
        "ucg-resolve must justify the one derived case by the sidecar's field cap"
    )


def test_close_applies_the_override_through_the_id_layer():
    text = _canon(_resolve())
    assert re.search(r"--from-sidecar", text), (
        "a close must re-apply the override through the script; a second writer "
        "hand-editing the registry is how an id an answer is keyed to goes missing"
    )


# --- defer must not deadlock --------------------------------------------------
def test_no_reopen_rule_is_scoped_to_close():
    # Whitespace-canonicalized, and bounded by word count rather than by the first
    # period: `.decisions.json` carries periods, so a `[^.]*` bound stops short.
    text = " ".join(_resolve().split())
    m = re.search(r"Do not re-open an item\b(?:\s+\S+){0,20}", text)
    assert m, "the no-re-open rule must be present"
    assert "`close`" in m.group(0), (
        "the no-re-open rule must be scoped to `close`; unscoped, a deferred item is "
        "never re-presented while preflight keeps blocking on it, deadlocking the run"
    )


def test_defer_is_explicitly_re_presented():
    assert re.search(r"Present it again", _resolve()), (
        "ucg-resolve must say a deferred item is presented again on a later pass"
    )


# --- the answer record must survive a second pass -----------------------------
def test_decisions_json_is_merged_not_overwritten():
    text = _resolve()
    assert re.search(r"read-modify-write", text, re.IGNORECASE), (
        "`.decisions.json` must be specified read-modify-write; a whole-document write "
        "erases every answer an earlier pass recorded"
    )
    assert re.search(r"keyed by `id`|merge this pass's answers", text, re.IGNORECASE)


def test_unparseable_decisions_file_fails_closed_with_a_stated_exit():
    text = _resolve()
    assert re.search(r"stop\s*[-—]*\s*do not overwrite\s*it", text, re.IGNORECASE), (
        "an unreadable answer record must not be overwritten"
    )
    assert "corrupt-" in text, (
        "the fail-closed stop must name the operator's way out, or it is a dead end "
        "on the only surface that can unblock the run"
    )


# --- turn-counter lifecycle ---------------------------------------------------
def test_arming_purges_the_turn_counter_but_resume_does_not():
    text = _preflight()
    m = re.search(r"- \*\*Purge stale run markers\.\*\*.*?(?=\n- \*\*)", text, re.DOTALL)
    assert m, "the arming purge bullet must be present"
    block = m.group(0)
    assert ".budget-*" in block, (
        "arming must purge a stale turn counter, or a fresh run escalates on its first "
        "Stop event before doing any work"
    )
    # ANTI-VACUOUS TWIN: purging it on resume would let a story evade its ceiling
    # by stopping and resuming, so the carve-out is as load-bearing as the purge.
    assert re.search(r"On a resume, purge nothing", block), (
        "the purge must carve out resume, or the turn ceiling becomes unenforceable"
    )


def test_closing_a_budget_overrun_resets_the_counter_inside_the_close_bullet():
    text = _resolve()
    m = re.search(r"- \*\*`close`\*\*.*?(?=\n- \*\*`|\n\n)", text, re.DOTALL)
    assert m, "the close disposition bullet must be present"
    block = m.group(0)
    assert ".budget-<story_id>.json" in block, (
        "the counter reset must live INSIDE the close bullet: a paragraph separated by a "
        "blank line falls outside every assertion that guards this disposition"
    )


# --- run-result.json lifecycle ------------------------------------------------
def test_headless_clears_a_prior_run_result():
    assert re.search(r"delete any existing .*run-result\.json", _INGEST.read_text(encoding="utf-8"), re.IGNORECASE), (
        "a headless run must clear a prior result, or its presence means only that SOME "
        "run once terminated"
    )


def test_the_clear_is_bound_to_scalar_resolution_not_to_stage_one():
    text = _INGEST.read_text(encoding="utf-8")
    assert re.search(r"resolution of the scalar.*?not arrival at this stage", text, re.IGNORECASE | re.DOTALL), (
        "the trigger must be scalar resolution; bound to Stage 1 it never fires on the "
        "resume routes that re-enter at Stage 2 or Execute"
    )
    assert re.search(r"run-result\.json", _PARENT_SKILL.read_text(encoding="utf-8")), (
        "the parent Resume paragraph must carry the same clearing rule"
    )


# --- status: a declared scalar must actually be threaded ----------------------
def test_status_invocation_passes_the_declared_ledger_scalar():
    text = _STATUS.read_text(encoding="utf-8")
    m = re.search(r"uv run \{ucg-root\}/scripts/status_render\.py[^\n]*", text)
    assert m, "the renderer invocation must be present"
    assert "--deferred-work" in m.group(0), (
        "Conventions tells the agent to resolve `deferred_work_path` and to stop if it "
        "cannot; an invocation that drops it makes the override silently no-op"
    )
