#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contracts for the shipped mutation runner's obligation and the
heartbeat/stall sidecars.

mutate_check.py's behaviour is pinned by test_mutate_check.py; these tests pin
the INSTRUCTION side: that execute.md orders the shipped runner used (instead
of the hand-rolled scratch harness every run re-invented), that the twin
contract binds BEFORE the gate, and that the heartbeat/stall sidecars exist
with their observability-only standing. Dropping any of that leaves the
scripts shipped and dead."""

from __future__ import annotations

import re
from pathlib import Path

EXECUTE = (Path(__file__).resolve().parents[2] / "references" / "execute.md").read_text(
    encoding="utf-8"
)


# --- the mutation runner obligation --------------------------------------------


def test_shipped_runner_is_ordered_not_offered():
    assert "scripts/mutate_check.py --table" in EXECUTE
    assert re.search(r"use it instead of\s+.?hand-rolling", EXECUTE), (
        "the runner must displace the scratch harness, not sit beside it"
    )


def test_twin_contract_binds_before_the_gate():
    assert re.search(
        r"Every guard or assertion this story adds or changes appears as a\s+.?table row "
        r"with an attributable red BEFORE the gate runs",
        EXECUTE,
    )


def test_ledger_is_a_story_artifact_not_scratch():
    assert re.search(r"ledger is a story artifact the\s+.?reviewers read", EXECUTE)
    assert re.search(r"scratch dies at\s+.?story end", EXECUTE)
    # Name-pinned per story, with a reachable consumer - an unpinned artifact
    # in this module is an artifact nothing resolves.
    assert "mutation-ledger-<story_id>.md" in EXECUTE
    assert re.search(r"step-3\s+.?test-review context", EXECUTE)


def test_runner_properties_named_as_refusals():
    for phrase in (
        "green-baseline precheck",
        "formatter-reflow signature",
        "byte-identical restore verification",
        "leads with GREEN survivors",
    ):
        assert phrase in EXECUTE, phrase
    assert re.search(r"cannot defeat the task-runner cache for you", EXECUTE)


# The parenthetical #212 added to the table sentence, and the rule its review 2
# added to it: mutate_check.py refuses a blank file, anchor, command or
# expect_red with exit 2, and an author learns that here, not from the refusal.
_NON_BLANK_RULE = "; the other four keys must be non-blank"
_DELETION_ROW = (
    " (an empty `replacement` deletes the anchor, the plainest mutation of a guard clause"
    + _NON_BLANK_RULE
    + ")"
)


def _table_sentence_allows_a_deletion_row(text: str) -> bool:
    """Said on the table's own sentence, where an author learns the row shape."""
    return bool(
        re.search(
            r"drives a JSON table of `\{file, anchor, replacement, command, expect_red\}` rows\s+"
            r"\(an empty `replacement` deletes the anchor\b",
            text,
        )
    )


def _table_sentence_requires_the_other_keys_non_blank(text: str) -> bool:
    """In the same parenthetical: blank, not only empty, since only whitespace
    is refused too."""
    return bool(
        re.search(
            r"drives a JSON table of `\{file, anchor, replacement, command, expect_red\}` rows\s+"
            r"\(an empty `replacement` deletes the anchor\b[^()]*;"
            r"\s+the other four keys must be\s+non-blank\)",
            text,
        )
    )


def test_table_sentence_says_an_empty_replacement_deletes_the_anchor():
    assert _table_sentence_allows_a_deletion_row(EXECUTE)
    # Twin: the sentence as it stood before #212.
    assert _DELETION_ROW in EXECUTE
    assert not _table_sentence_allows_a_deletion_row(EXECUTE.replace(_DELETION_ROW, ""))


def test_table_sentence_says_the_other_four_keys_must_be_non_blank():
    assert _table_sentence_requires_the_other_keys_non_blank(EXECUTE)
    # Twin: the parenthetical as #212 first wrote it, without the rule.
    assert _NON_BLANK_RULE in EXECUTE
    assert not _table_sentence_requires_the_other_keys_non_blank(EXECUTE.replace(_NON_BLANK_RULE, ""))
    # Twin: the rule before review 2, when only an empty key was refused.
    assert not _table_sentence_requires_the_other_keys_non_blank(
        EXECUTE.replace(_NON_BLANK_RULE, "; the other four keys must be non-empty")
    )


# --- the heartbeat sidecar and stall marker ------------------------------------


def test_heartbeat_appends_at_every_step_boundary():
    assert ".heartbeat-<story_id>" in EXECUTE
    assert re.search(r"step 0 through step 5, plus gate start and gate end", EXECUTE)
    # The guard-inert one-command form is stated, or a run re-derives an
    # appender through command substitution and gets refused.
    assert re.search(r'date -u "\+step-2 %FT%TZ" >>', EXECUTE)


def test_heartbeat_is_observability_only():
    assert re.search(r"never\s+.?gate evidence, is read by no guard", EXECUTE)
    # Purged at arming like .budget-*, or a prior run's gap fires this run's
    # stall rule; and "the heartbeat" must stay bound to run-status.json for
    # every pre-existing use of the word.
    assert re.search(r"purged at fresh-run arming exactly as `\.budget-\*`", EXECUTE)
    assert re.search(r"with no qualifier still means `run-status\.json`", EXECUTE)


def test_resume_routing_reaches_the_stall_check():
    """The rule cannot live only in the observability section: the resume
    paragraphs are what a resuming session actually follows."""
    assert re.search(r"\*\*A resume owes the stall check first\.\*\*", EXECUTE)
    resume_pos = EXECUTE.index("A resume owes the stall check first")
    sweep_pos = EXECUTE.index("The re-assertion sweep is one script call")
    assert resume_pos < sweep_pos


def test_heartbeat_append_is_allowlisted():
    """The 8-per-story append must not hit the permission layer headless."""
    toml = (Path(__file__).resolve().parents[2] / "customize.toml").read_text(encoding="utf-8")
    assert '"date"' in toml.split("allowlist_commands", 1)[1].splitlines()[0]


def test_purge_families_include_the_sidecars():
    preflight = (
        Path(__file__).resolve().parents[2] / "references" / "preflight.md"
    ).read_text(encoding="utf-8")
    assert ".heartbeat-*" in preflight
    assert ".stall-*" in preflight
    assert "Those five dot-prefixed families only" in preflight


def test_stall_marker_written_on_resume_after_a_gap():
    assert ".stall-<story_id>" in EXECUTE
    assert re.search(r"exceeds 30 minutes", EXECUTE)
    assert re.search(r"`unknown` otherwise", EXECUTE), (
        "unknown must be a legal cause, or the marker silently never gets written"
    )
    assert re.search(r"before driving anything", EXECUTE)


def test_sidecars_survive_finalize():
    assert re.search(r"Leave\s+.?both sidecars in place at story end", EXECUTE)
    assert re.search(r"active\s+.?versus idle time", EXECUTE)
