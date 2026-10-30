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
        (13, 5, 25, True),  # 13 criteria >= 12.5
        (12, 5, 25, False),  # 12 < 12.5, though criteria plus tasks is 17
        (1, 12, 25, False),  # criteria plus tasks is 13, over the old line
        (15, 0, 30, True),  # the line moves with the ceiling: 15 >= 15
        (14, 3, 30, False),  # 14 < 15, though criteria plus tasks is 17
    ],
)
def test_implausibility_threshold_is_half_the_turn_ceiling_in_criteria(ac, task, ceiling, expected) -> None:
    """Each row under the line carries tasks that would cross it if they were
    added, so the summed rule fails here as well as in the cases below."""
    assert mod.size(ac, task, ceiling)["implausible"] is expected


@pytest.mark.parametrize(
    ("ac", "task"),
    [
        (9, 7),  # criteria plus tasks 16: flagged before, a row driven whole in 6 turns
        (12, 13),  # however long the task list, 12 criteria stay under 12.5
    ],
)
def test_tasks_do_not_add_to_the_threshold(ac, task) -> None:
    """A task list is how the author sliced the work, and it lists steps every
    row pays (read the skills, run the gates). Added to the criteria it flagged
    most rows a real project then drove whole."""
    sized = mod.size(ac, task, 25)

    assert sized["implausible"] is False
    assert sized["task_count"] == task
    assert "load" not in sized


def test_the_ratio_is_criteria_over_the_ceiling() -> None:
    assert mod.size(13, 9, 25)["ratio"] == 0.52


def test_absent_ceiling_leaves_implausible_undecided_not_false() -> None:
    """`False` would read as "checked, fine" on a row nobody sized."""
    sized = mod.size(8, 8, None)

    assert sized["implausible"] is None
    assert sized["ratio"] is None
    assert sized["ac_count"] == 8
    assert sized["task_count"] == 8


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


def test_the_sizing_call_reads_the_criteria_and_reports_the_tasks() -> None:
    """The call execute.md runs before a split: 9 criteria and 7 tasks summed to
    16 and flagged a row that was then driven whole in 6 turns."""
    acs = ",".join("AC-%d" % n for n in range(1, 10))
    code, payload = _run("--parent-acs", acs, "--tasks", "7", "--turn-ceiling", "25")

    assert code == 0
    assert payload is not None
    assert payload["implausible"] is False
    assert payload["ratio"] == 0.36
    assert payload["task_count"] == 7
    assert "load" not in payload


def test_malformed_id_is_a_usage_error_not_a_dropped_token() -> None:
    """A dropped typo would surface as an AC nobody claimed: a false failure."""
    code, payload = _run("--parent-acs", "AC-1, oops!", "--child", "a=AC-1")

    assert code == 2
    assert payload is None


def test_child_without_an_equals_is_a_usage_error() -> None:
    code, _ = _run("--parent-acs", "AC-1", "--child", "a AC-1")

    assert code == 2


# ---------------------------------------------------------------------------
# The split record gate_eval.py --rollup reads a decomposed parent through.


def test_a_reconciled_split_writes_its_record(tmp_path: Path) -> None:
    code, payload = _run(
        "--parent", "7-1-the-login", "--record", str(tmp_path),
        "--parent-acs", "1 2 3", "--child", "7-1b=3", "--child", "7-1a=1,2",
    )

    record = tmp_path / ".split-7-1-the-login.json"
    assert code == 0
    assert payload is not None and payload["record"] == str(record)
    assert json.loads(record.read_text(encoding="utf-8")) == {
        "parent": "7-1-the-login",
        "children": ["7-1b", "7-1a"],
        "parent_acs": ["1", "2", "3"],
        "claims": {"7-1b": ["3"], "7-1a": ["1", "2"]},
    }, "the children keep the order given, which is the order of their rows"


def test_a_failing_split_writes_no_record_and_keeps_an_earlier_one(tmp_path: Path) -> None:
    """A record is evidence the claim map reconciled, so a failing run never
    writes one, and never overwrites the one a reconciling run left."""
    record = tmp_path / ".split-7-1.json"
    code, payload = _run("--parent", "7-1", "--record", str(tmp_path), "--parent-acs", "1 2", "--child", "7-1a=1")
    assert code == 1
    assert payload is not None and payload["record"] is None
    assert not record.exists()

    assert _run("--parent", "7-1", "--record", str(tmp_path), "--parent-acs", "1", "--child", "7-1a=1")[0] == 0
    before = record.read_text(encoding="utf-8")
    assert _run("--parent", "7-1", "--record", str(tmp_path), "--parent-acs", "1 2", "--child", "7-1a=1")[0] == 1
    assert record.read_text(encoding="utf-8") == before


def test_a_new_reconciled_split_replaces_the_record(tmp_path: Path) -> None:
    assert _run("--parent", "7-1", "--record", str(tmp_path), "--parent-acs", "1 2", "--child", "7-1a=1,2")[0] == 0
    assert _run(
        "--parent", "7-1", "--record", str(tmp_path), "--parent-acs", "1 2",
        "--child", "7-1a=1", "--child", "7-1b=2",
    )[0] == 0
    record = json.loads((tmp_path / ".split-7-1.json").read_text(encoding="utf-8"))
    assert record["children"] == ["7-1a", "7-1b"]


def test_without_the_record_flags_the_output_is_unchanged() -> None:
    code, payload = _run("--parent-acs", "1", "--child", "7-1a=1")
    assert code == 0
    assert payload is not None and "record" not in payload


@pytest.mark.parametrize(
    "argv",
    [
        ("--parent", "7-1", "--parent-acs", "1", "--child", "7-1a=1"),
        ("--record", "{dir}", "--parent-acs", "1", "--child", "7-1a=1"),
        ("--parent", "7-1", "--record", "{dir}", "--parent-acs", "1"),
        ("--parent", "7-1", "--record", "{dir}", "--parent-acs", "1", "--child", "7-1=1"),
        ("--parent", "  ", "--record", "{dir}", "--parent-acs", "1", "--child", "7-1a=1"),
        ("--parent", "../7-1", "--record", "{dir}", "--parent-acs", "1", "--child", "7-1a=1"),
        ("--parent", "..\\7-1", "--record", "{dir}", "--parent-acs", "1", "--child", "7-1a=1"),
        ("--parent", " 7-1a ", "--record", "{dir}", "--parent-acs", "1", "--child", "7-1a=1"),
        ("--parent", "7-1", "--record", "{dir}/missing", "--parent-acs", "1", "--child", "7-1a=1"),
        ("--parent", "7-1", "--record", "{dir}/a-file", "--parent-acs", "1", "--child", "7-1a=1"),
        ("--parent", "7-1", "--record", "{dir}", "--parent-acs", "", "--child", "7-1a=AC-1"),
        ("--parent", "7-1", "--record", "{dir}", "--parent-acs", "1", "--child", "7-1a=1", "--child", "7-1b="),
    ],
    ids=[
        "parent-alone", "record-alone", "no-child", "parent-is-a-child", "blank-parent",
        "parent-path", "parent-backslash-path", "padded-parent-is-a-child", "missing-dir",
        "record-is-a-file", "no-parent-acs", "child-claims-nothing",
    ],
)
def test_a_record_it_cannot_write_is_a_usage_error(tmp_path: Path, argv: tuple[str, ...]) -> None:
    """Refused before anything is computed, with the cause named, rather than
    left to fail at the write."""
    (tmp_path / "a-file").write_text("x\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *(a.replace("{dir}", str(tmp_path)) for a in argv)],
        capture_output=True, text=True,
    )

    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr.startswith("usage error: "), proc.stderr
    assert not list(tmp_path.glob(".split-*"))


def test_a_padded_parent_names_the_record_by_its_key(tmp_path: Path) -> None:
    code, payload = _run("--parent", " 7-1 ", "--record", str(tmp_path), "--parent-acs", "1", "--child", "7-1a=1")

    assert code == 0
    record = json.loads((tmp_path / ".split-7-1.json").read_text(encoding="utf-8"))
    assert record["parent"] == "7-1"


def test_a_child_given_twice_is_a_usage_error() -> None:
    """Merging two --child flags for one row kept the last claims and dropped
    the rest, so a double claim or an unknown id in the dropped ones left the
    check, and the split record written on it."""
    code, payload = _run(
        "--parent-acs", "AC-1,AC-2", "--child", "7-1a=AC-1,AC-2,AC-9", "--child", "7-1b=AC-2", "--child", "7-1a=AC-1",
    )

    assert code == 2
    assert payload is None


def test_a_record_that_cannot_be_written_is_exit_2_not_a_traceback(tmp_path: Path) -> None:
    (tmp_path / ".split-7-1.json").mkdir()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--parent", "7-1", "--record", str(tmp_path), "--parent-acs", "1", "--child", "7-1a=1"],
        capture_output=True, text=True,
    )

    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "cannot write the split record" in proc.stderr
    assert "Traceback" not in proc.stderr
    assert not (tmp_path / ".split-7-1.json.tmp").exists(), "the staged copy is cleaned up"


def test_a_failed_rewrite_leaves_the_earlier_record_whole(tmp_path: Path) -> None:
    """The record is written beside itself and moved into place, so a write
    that fails cannot leave a truncated record the roll-up then refuses."""
    record = tmp_path / ".split-7-1.json"
    assert _run("--parent", "7-1", "--record", str(tmp_path), "--parent-acs", "1 2", "--child", "7-1a=1,2")[0] == 0
    before = record.read_text(encoding="utf-8")
    (tmp_path / ".split-7-1.json.tmp").mkdir()

    code, payload = _run(
        "--parent", "7-1", "--record", str(tmp_path), "--parent-acs", "1 2", "--child", "7-1a=1", "--child", "7-1b=2",
    )

    assert code == 2
    assert payload is None
    assert record.read_text(encoding="utf-8") == before
