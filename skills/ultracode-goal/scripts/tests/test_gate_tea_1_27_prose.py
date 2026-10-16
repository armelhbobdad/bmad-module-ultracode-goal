"""Prose contract over the gate on TEA 1.27.2: trace on any stack, the per-story
paths trace has to be told to write, the gate's evidence commit, and the epic row.

A real `--light` run on a pytest library showed each one. TEA's trace ran and
authored the gate on that non-web stack, which the references said it could
not. It wrote fixed, flat paths and ignored `trace_output`, and the run reached
the gate only because the conductor improvised per-story names. Nothing said
when the post-gate `done` sync and gate files were committed, and nothing ever
moved the epic row, which the run report then told the operator a
retrospective would close.

Each predicate is checked against the live reference; the ones that could pass
on prose that merely mentions the topic are also checked, as their anti-vacuous
twins, against the pre-edit wording or a single-clause mutant they must reject.
Stdlib + pytest only.
"""

import re
from pathlib import Path

_REFS = Path(__file__).resolve().parents[2] / "references"


def _read(name: str) -> str:
    return (_REFS / name).read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i : text.index(end, i)]


# --- trace runs on any stack ------------------------------------------------

_RETIRED_TRACE_CLAIM = "cannot run on a non-web stack"


def _trace_first_everywhere(opener: str) -> bool:
    return bool(
        re.search(r"On TEA 1\.27\.2, `bmad-testarch-trace` runs on any stack", opener)
        and re.search(r"run it first on every stack", opener)
        and re.search(r"fallback for when trace halts or cannot run", opener)
    )


def _nonweb_opener() -> str:
    section = _between(_read("gate.md"), "## Non-web stack", "\n**`trace-<id>.md`**")
    return section


def test_nonweb_section_runs_trace_first_and_is_only_a_fallback():
    assert _trace_first_everywhere(_nonweb_opener())


def test_trace_predicate_rejects_the_pre_edit_opener():
    pre_edit = (
        "## Non-web stack (web-only TEA chain): author the deterministic trace "
        "artifacts\n\nWhen the module's TEA chain is web-only, `bmad-testarch-trace` "
        "cannot run on a non-web stack and so cannot emit the binding gate decision."
    )
    assert not _trace_first_everywhere(pre_edit)


def test_the_retired_trace_claim_stays_out():
    for name in ("gate.md", "define-done.md", "preflight.md"):
        assert _RETIRED_TRACE_CLAIM not in _read(name), name
    assert "the automate→trace pair at the gate" not in _read("define-done.md")
    assert "land deterministically" not in _read("preflight.md")


def test_define_done_names_trace_as_stack_agnostic():
    assert re.search(r"neither is trace, which runs on any stack too", _read("define-done.md"))


# --- the per-story paths trace writes ---------------------------------------


def _names_per_story_paths(para: str) -> bool:
    return bool(
        re.search(r"does not read `trace_output`", para)
        and "`trace-<story_id>.md`" in para
        and "`gateDecisionFile: gate-decision-<story_id>.json`" in para
        and "`e2e-trace-summary-<story_id>.json`" in para
        and re.search(r"sprint-status key copied verbatim", para)
        and re.search(r"provenance stays `tea` only while TEA's own steps computed", para)
    )


def _naming_paragraph() -> str:
    return _between(_read("gate.md"), "**Name the per-story paths trace writes", "\nProduction:")


def test_gate_names_the_per_story_paths_trace_must_write():
    assert _names_per_story_paths(_naming_paragraph())


def test_naming_predicate_rejects_a_paragraph_without_provenance_limit():
    mutant = _naming_paragraph().replace(
        "the provenance stays `tea` only while TEA's own steps computed the content", ""
    )
    assert mutant != _naming_paragraph(), "the mutant must actually change the text"
    assert not _names_per_story_paths(mutant)


def test_preflight_points_at_the_naming_step():
    assert re.search(
        r"On TEA 1\.27\.2 trace does not read `trace_output`", _read("preflight.md")
    )


# --- the gate's evidence commit ----------------------------------------------


def _evidence_commit() -> str:
    return _between(
        _read("gate.md"),
        "**Commit the gate's evidence before the next story starts.**",
        "When **every story of the Epic is `done`**",
    )


def _commits_on_the_existing_marker(para: str) -> bool:
    return bool(
        re.search(r"before the next story's step 0", para)
        and re.search(r"reuse that marker as it stands and never rewrite it", para)
        and re.search(r"refresh `\.commit-<story_id>` from `HEAD`", para)
        and re.search(r"never forced in with `git add -f`", para)
        and re.search(r"if nothing is staged, make no commit", para)
        and re.search(r"A resume that finds an advanced story's evidence still uncommitted", para)
        and re.search(r"For the story whose advance makes every story `done`", para)
    )


def test_gate_commits_its_evidence_inside_the_story_boundary():
    assert _commits_on_the_existing_marker(_evidence_commit())


def test_evidence_commit_predicate_rejects_a_fresh_marker():
    """Writing a fresh marker for a commit no test run backs is a forged marker."""
    mutant = _evidence_commit().replace(
        "reuse that marker as it stands and never rewrite it for this commit",
        "write a fresh tests-ran marker for this commit",
    )
    assert not _commits_on_the_existing_marker(mutant)


def test_execute_names_the_evidence_commit():
    assert re.search(
        r"one implementation commit per green story; the gate's evidence commit follows",
        _read("execute.md"),
    )


def test_finalize_states_the_range_rule_the_script_uses():
    assert re.search(
        r"ends at its own `\.commit-<story_id>` when that marker names a commit",
        _read("finalize.md"),
    )


# --- the epic row ------------------------------------------------------------


def _syncs_the_epic_row(gate: str) -> bool:
    return bool(
        re.search(r"move the Epic's own `epic-<id>` row from `backlog` to `in-progress`", gate)
        and re.search(
            r"When the Epic-level gate returns `advance`, or `defer` \(whose route advances anyway\), "
            r"set the `epic-<id>` row to `done`",
            gate,
        )
        and re.search(r"Never write it on any other route", gate)
    )


def test_gate_syncs_the_epic_row():
    assert _syncs_the_epic_row(_read("gate.md"))


def test_epic_row_predicate_rejects_an_unbounded_done_write():
    mutant = _read("gate.md").replace("Never write it on any other route", "")
    assert not _syncs_the_epic_row(mutant)


def test_finalize_never_promises_the_retrospective_closes_the_row():
    finalize = _read("finalize.md")
    assert re.search(r"never tell the operator `bmad-retrospective` will close the row", finalize)


# --- the non-web deliverables when TEA authored the trace --------------------


def test_provenance_item_names_both_values():
    item = next(
        line for line in _read("gate.md").splitlines() if line.startswith("5. **`gate-provenance:`")
    )
    assert "`gate-provenance: hand-authored` where item 1 applied" in item
    assert "`tea` where trace ran" in item


def test_red_count_never_edits_a_tea_authored_report():
    assert re.search(
        r"Where TEA authored the trace report, record them beside the captured output of item 3",
        _read("gate.md"),
    )


def test_a_story_is_never_isolated_into_a_fresh_trace_dir():
    gate = _read("gate.md")
    assert "isolate the current story's" not in gate
    assert re.search(r"Never isolate a story into a fresh directory instead", gate)


def test_a_resume_meets_the_owed_evidence_commit_before_the_next_baseline():
    """A resume enters Execute before Stage 5 is loaded, so gate.md's resume rule
    alone is read too late: execute.md has to carry the check itself."""
    execute = _read("execute.md")
    assert re.search(
        r"Before the next story's step 0, also check whether the last advanced story's gate evidence is still uncommitted",
        execute,
    )
    assert re.search(r"after the advance route's evidence commit when one is owed", execute)
