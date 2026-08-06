#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Tests for scripts/story_sizing.py.

The centre of gravity is the substring bug the module exists to retire: a
hand-rolled parser improvised for the claim map on a real run reported two false
double-claims by matching the `1` inside `REQ-1`. Every id here is compared as a
whole token, so that confusion is unrepresentable rather than merely unlikely --
and `test_req_1_does_not_collide_with_bare_1` is the fixture that pins it.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "story_sizing.py"


def _load():
    spec = importlib.util.spec_from_file_location("story_sizing", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load()


def _run(*argv: str) -> tuple[int, dict | None]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *argv], capture_output=True, text=True
    )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:
        return proc.returncode, None


# ---------------------------------------------------------------------------
# The bug this module retires.


def test_req_1_does_not_collide_with_bare_1() -> None:
    """`REQ-1`, `AC-1` and `1` are three distinct ids, not one seen three times.

    The improvised parser matched `1` as a substring of `REQ-1` and reported two
    false double-claims. Token equality makes that impossible.
    """
    result = mod.reconcile(
        ["AC-1", "REQ-1", "1"],
        {"7-1a": ["AC-1"], "7-1b": ["REQ-1"], "7-1c": ["1"]},
    )

    assert result["double_claimed"] == []
    assert result["unclaimed"] == []
    assert result["exactly_once"] is True
    assert result["claims"] == {"AC-1": ["7-1a"], "REQ-1": ["7-1b"], "1": ["7-1c"]}


def test_substring_matching_would_have_failed_this_fixture() -> None:
    """Twin: the rejected implementation, shown failing the fixture above.

    Without this the test above could pass for any reason at all; this pins that
    it passes BECAUSE the match is by equality.
    """
    parent = ["AC-1", "REQ-1", "1"]
    children = {"7-1a": ["AC-1"], "7-1b": ["REQ-1"], "7-1c": ["1"]}

    substring_claims = {
        ac: [row for row, claimed in children.items() if any(ac in c for c in claimed)]
        for ac in parent
    }

    assert len(substring_claims["1"]) == 3, (
        "the substring reading sees bare `1` inside AC-1 and REQ-1 too, which is "
        "exactly the two false double-claims observed on the real run"
    )
    assert mod.reconcile(parent, children)["double_claimed"] == []


# ---------------------------------------------------------------------------
# Reconciliation.


def test_unclaimed_and_double_claimed_are_both_reported() -> None:
    result = mod.reconcile(["AC-1", "AC-2", "AC-3"], {"a": ["AC-1", "AC-2"], "b": ["AC-2"]})

    assert result["unclaimed"] == ["AC-3"]
    assert result["double_claimed"] == ["AC-2"]
    assert result["exactly_once"] is False


def test_a_child_claiming_an_ac_the_parent_does_not_own_is_unknown_not_ignored() -> None:
    """Silently dropping it would read as a clean split over a fabricated AC."""
    result = mod.reconcile(["AC-1"], {"a": ["AC-1"], "b": ["AC-9"]})

    assert result["unknown_claims"] == {"b": ["AC-9"]}
    assert result["exactly_once"] is False


def test_one_child_claiming_the_same_ac_twice_is_not_a_double_claim() -> None:
    """Two children is a double claim; one child repeating itself is a typo."""
    result = mod.reconcile(["AC-1", "AC-2"], {"a": ["AC-1", "AC-1"], "b": ["AC-2"]})

    assert result["double_claimed"] == []
    assert result["claims"]["AC-1"] == ["a"]
    assert result["exactly_once"] is True


def test_duplicate_ids_in_the_parent_list_are_reported() -> None:
    """A parent list that already repeats an id cannot be claimed exactly once."""
    result = mod.reconcile(["AC-1", "AC-1"], {"a": ["AC-1"]})

    assert result["parent_ac_duplicates"] == ["AC-1"]
    assert result["exactly_once"] is False


# ---------------------------------------------------------------------------
# Sizing.


@pytest.mark.parametrize(
    ("ac", "task", "ceiling", "expected"),
    [
        (10, 3, 25, True),  # load 13 >= 12.5
        (6, 6, 25, False),  # load 12 < 12.5
        (1, 1, 25, False),
    ],
)
def test_implausibility_threshold_is_half_the_turn_ceiling(ac, task, ceiling, expected) -> None:
    assert mod.size(ac, task, ceiling)["implausible"] is expected


def test_absent_ceiling_leaves_implausible_undecided_not_false() -> None:
    """`False` would read as "checked, fine" on a row nobody sized."""
    sized = mod.size(8, 8, None)

    assert sized["implausible"] is None
    assert sized["ratio"] is None
    assert sized["load"] == 16


# ---------------------------------------------------------------------------
# CLI contract.


def test_cli_exits_1_on_a_failing_reconciliation_but_still_emits_json() -> None:
    """A failing claim map is a result to read, not a crash."""
    code, payload = _run("--parent-acs", "AC-1,AC-2", "--child", "a=AC-1")

    assert code == 1
    assert payload is not None
    assert payload["unclaimed"] == ["AC-2"]


def test_cli_exits_0_on_a_clean_reconciliation() -> None:
    code, payload = _run("--parent-acs", "AC-1", "--child", "a=AC-1")

    assert code == 0
    assert payload is not None and payload["exactly_once"] is True


def test_sizing_alone_does_not_claim_a_reconciliation_it_never_ran() -> None:
    """The pre-decomposition call has no children, so it reports none checked."""
    code, payload = _run("--parent-acs", "AC-1,AC-2", "--tasks", "3", "--turn-ceiling", "25")

    assert code == 0
    assert payload is not None
    assert payload["reconciled"] is False
    assert "exactly_once" not in payload


def test_malformed_id_is_a_usage_error_not_a_dropped_token() -> None:
    """A dropped typo would surface as an AC nobody claimed: a false failure."""
    code, payload = _run("--parent-acs", "AC-1, oops!", "--child", "a=AC-1")

    assert code == 2
    assert payload is None


def test_child_without_an_equals_is_a_usage_error() -> None:
    code, _ = _run("--parent-acs", "AC-1", "--child", "a AC-1")

    assert code == 2
