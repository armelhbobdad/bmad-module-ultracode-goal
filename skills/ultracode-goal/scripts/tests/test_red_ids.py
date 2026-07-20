"""Unit tests for red_ids.py, the deterministic RED identity layer.

The id is a join key between two surfaces that never share a session: preflight
mints it during the semantic scan, and `/ucg-resolve` records an operator's answer
against it days later. Two rounds of specifying that key in prose each shipped a
deadlock, and a first code version then shipped a fail-open, so the behaviours
pinned here are the ones that actually went wrong:

  - two findings of the same `kind` in one artifact never share an id (one answer
    must not clear a decision nobody made);
  - an answered decision restated unchanged stays suppressed, even if it moved
    within the file;
  - a reworded decision gets a NEW id and is asked again -- recognition is exact
    and never guesses, because every proxy for "is this the same decision" can
    swallow a brand-new one;
  - a tombstone never adopts a different decision, and a blank `decision_needed`
    is refused rather than digested to a constant (the two fail-open regressions);
  - the failure posture is asymmetric: an unreadable override suppresses nothing,
    while any malformed registry writes nothing.

Stdlib + pytest only.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import red_ids  # noqa: E402


def _red(kind, source, decision, evidence="quoted line"):
    return {"source": source, "kind": kind, "decision_needed": decision, "evidence": evidence}


def _write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


# --- minting ------------------------------------------------------------------
def test_id_excludes_the_line_number():
    a = red_ids.mint_id("undecided-product", "docs/prd.md:42", "Pick a session length")
    b = red_ids.mint_id("undecided-product", "docs/prd.md:1180", "Pick a session length")
    assert a == b, "an edit above the finding must not change its id"
    assert ":42" not in a and ":1180" not in a


def test_a_colon_bearing_path_keeps_everything_but_the_line():
    assert red_ids.bare_path("C:/repo/prd.md:42") == "C:/repo/prd.md"
    assert red_ids.bare_path("docs/prd.md") == "docs/prd.md"


def test_same_kind_and_path_but_different_decisions_do_not_collide():
    # The fail-open the digest component exists to prevent.
    a = red_ids.mint_id("undecided-product", "docs/prd.md:10", "Do sessions expire at 30 days?")
    b = red_ids.mint_id("undecided-product", "docs/prd.md:90", "Which payment provider ships first?")
    assert a != b


def test_rewrapping_or_renormalizing_the_same_decision_is_the_same_id():
    a = red_ids.mint_id("contradiction", "prd.md:1", "Pick  one\n  storage  backend")
    b = red_ids.mint_id("contradiction", "prd.md:1", "Pick one storage backend")
    assert a == b, "whitespace must not be identity"


# --- recognition is exact, and never guesses ----------------------------------
def test_the_same_decision_restated_identically_keeps_its_id():
    was = red_ids.mint_id("undecided-product", "prd.md:5", "Decide session expiry")
    out = red_ids.reconcile([_red("undecided-product", "prd.md:900", "Decide session expiry")])
    assert out[0]["id"] == was, "a finding that only moved must keep its id"


def test_a_reworded_decision_gets_a_new_id_and_is_asked_again():
    # The deliberate trade: recognition is exact, so a reword fails CLOSED.
    was = red_ids.mint_id("undecided-product", "prd.md:5", "Decide session expiry")
    out = red_ids.reconcile([_red("undecided-product", "prd.md:5", "Session expiry: 30 vs 90 days")])
    assert out[0]["id"] != was


def test_only_a_textually_identical_decision_shares_an_id():
    out = red_ids.reconcile([
        _red("contradiction", "adr.md:3", "Pick one storage backend"),
        _red("contradiction", "adr.md:9", "Pick one storage backend"),
        _red("contradiction", "adr.md:40", "Pick one queue backend"),
    ])
    assert out[0]["id"] == out[1]["id"], "the same decision reported twice is one decision"
    assert out[2]["id"] != out[0]["id"], "a different decision must never share the id"


def test_a_blank_decision_is_refused_rather_than_digested_to_a_constant(tmp_path):
    # FAIL-OPEN REGRESSION: an absent or blank `decision_needed` digests to the
    # CONSTANT sha256(""), collapsing every distinct decision in one artifact onto
    # a single id, so one close would suppress all of them.
    for bad in ({}, {"decision_needed": ""}, {"decision_needed": "   "}, {"decision_needed": None}):
        red = {**_red("undecided-product", "prd.md:5", "x"), **bad}
        if "decision_needed" not in bad:
            red.pop("decision_needed")
        with pytest.raises(red_ids.RedIdError):
            red_ids.apply([red], tmp_path)


def test_the_blank_decision_guard_covers_the_from_sidecar_path(tmp_path):
    # ANTI-VACUOUS TWIN: --from-sidecar never passes through the scan reader, so
    # validating only there would leave this path open.
    _write(tmp_path / ".preflight-reds.json",
           {"reds": [{"id": "undecided-product:prd.md:e3b0c44298fc", "source": "prd.md:5",
                      "kind": "undecided-product", "decision_needed": "", "evidence": "e"}],
            "resolved": []})
    assert red_ids.main(["--from-sidecar", "--impl-artifacts", str(tmp_path)]) == 2


def test_a_malformed_sidecar_field_fails_closed_rather_than_reading_empty(tmp_path):
    # FAIL-OPEN REGRESSION: coercing a wrong-typed `reds` to [] reads as "nothing
    # pending" and the next write would replace the registry with that emptiness,
    # discarding REDs nobody answered.
    sidecar = tmp_path / ".preflight-reds.json"
    for bad in ({"reds": {}}, {"reds": "none"}, {"reds": [1, 2]}, {"reds": [], "resolved": "x"}):
        _write(sidecar, bad)
        with pytest.raises(red_ids.RedIdError):
            red_ids.apply([_red("undecided-product", "prd.md:5", "Undecided")], tmp_path)
        assert json.loads(sidecar.read_text(encoding="utf-8")) == bad, "must not be rewritten"


# --- the override -------------------------------------------------------------
def test_close_then_rescan_stays_suppressed(tmp_path):
    impl = tmp_path
    first = red_ids.apply([_red("undecided-product", "prd.md:5", "Decide session expiry")], impl)
    _write(impl / ".preflight-reds.json", first)
    the_id = first["reds"][0]["id"]

    _write(impl / ".decisions.json", {"decisions": [{"id": the_id, "answer": "30 days", "action": "close"}]})

    # Re-detected at a different line, restated unchanged.
    second = red_ids.apply([_red("undecided-product", "prd.md:11", "Decide session expiry")], impl)
    assert second["reds"] == [], "an answered decision must not be asked again"
    assert any(t["id"] == the_id for t in second["resolved"]), "the close must leave a tombstone"


def test_a_close_survives_repeated_rescans(tmp_path):
    impl = tmp_path
    first = red_ids.apply([_red("contradiction", "prd.md:5", "Pick one storage backend")], impl)
    _write(impl / ".preflight-reds.json", first)
    the_id = first["reds"][0]["id"]
    _write(impl / ".decisions.json", {"decisions": [{"id": the_id, "action": "close", "answer": "postgres"}]})

    for _ in range(3):
        out = red_ids.apply([_red("contradiction", "prd.md:5", "Pick one storage backend")], impl)
        _write(impl / ".preflight-reds.json", out)
        assert out["reds"] == [], "an unchanged decision stays suppressed across rescans"
        assert [t["id"] for t in out["resolved"]] == [the_id], "and its tombstone is not duplicated"


def test_a_tombstone_never_adopts_a_different_decision(tmp_path):
    # THE FAIL-OPEN REGRESSION TEST. A cardinality-based pairing let a closed
    # decision's tombstone swallow a brand-new one at the same (kind, path): the
    # operator was never shown it and the hard gate opened on a question nobody
    # decided. Worse, the tombstone was re-added every run, so one close poisoned
    # that (kind, path) permanently.
    impl = tmp_path
    first = red_ids.apply([_red("undecided-product", "prd.md:5", "Decide session expiry")], impl)
    _write(impl / ".preflight-reds.json", first)
    _write(impl / ".decisions.json",
           {"decisions": [{"id": first["reds"][0]["id"], "action": "close", "answer": "30 days"}]})
    closed = red_ids.apply([_red("undecided-product", "prd.md:5", "Decide session expiry")], impl)
    _write(impl / ".preflight-reds.json", closed)
    assert closed["reds"] == [] and len(closed["resolved"]) == 1

    # A genuinely new decision arrives at the SAME (kind, path), as the only
    # candidate -- the exact shape that used to be silently suppressed.
    fresh = red_ids.apply([_red("undecided-product", "prd.md:400", "Which payment provider ships first")], impl)
    assert len(fresh["reds"]) == 1, (
        "a never-answered decision must never inherit a closed decision's id: "
        "suppressing it opens the hard gate on a question nobody decided"
    )
    assert "payment" in fresh["reds"][0]["decision_needed"]


def test_two_findings_at_one_key_keep_distinct_ids_across_scans(tmp_path):
    impl = tmp_path
    reds = [
        _red("undecided-product", "prd.md:5", "Decide session expiry"),
        _red("undecided-product", "prd.md:80", "Decide which payment provider ships first"),
    ]
    first = red_ids.apply(reds, impl)
    _write(impl / ".preflight-reds.json", first)
    ids = [r["id"] for r in first["reds"]]
    assert len(set(ids)) == 2, "two decisions must never share an id"

    _write(impl / ".decisions.json", {"decisions": [{"id": ids[0], "action": "close", "answer": "30 days"}]})
    second = red_ids.apply(reds, impl)
    assert [r["id"] for r in second["reds"]] == [ids[1]], (
        "closing one must clear exactly one, and the other keeps its id"
    )


def test_a_defer_does_not_suppress(tmp_path):
    impl = tmp_path
    first = red_ids.apply([_red("undecided-product", "prd.md:5", "Undecided thing")], impl)
    _write(impl / ".preflight-reds.json", first)
    _write(impl / ".decisions.json",
           {"decisions": [{"id": first["reds"][0]["id"], "action": "defer", "answer": "later"}]})
    second = red_ids.apply([_red("undecided-product", "prd.md:5", "Undecided thing")], impl)
    assert len(second["reds"]) == 1, "a parked decision still blocks"


def test_a_stale_answer_cannot_pre_authorize_a_finding_not_yet_made(tmp_path):
    impl = tmp_path
    _write(impl / ".decisions.json", {"decisions": [{"id": "undecided-product:other.md:ffffffffffff",
                                                     "action": "close", "answer": "x"}]})
    out = red_ids.apply([_red("undecided-product", "prd.md:5", "Undecided")], impl)
    assert len(out["reds"]) == 1, "an override naming no present RED must be ignored"


# --- failure posture ----------------------------------------------------------
def test_unreadable_decisions_file_suppresses_nothing(tmp_path):
    impl = tmp_path
    (impl / ".decisions.json").write_text("{ this is not json", encoding="utf-8")
    out = red_ids.apply([_red("undecided-product", "prd.md:5", "Undecided")], impl)
    assert len(out["reds"]) == 1, "a suppression file that cannot be read is not a suppression"


def test_unreadable_sidecar_is_a_hard_error_and_writes_nothing(tmp_path):
    impl = tmp_path
    sidecar = impl / ".preflight-reds.json"
    sidecar.write_text("{ corrupt", encoding="utf-8")
    with pytest.raises(red_ids.RedIdError):
        red_ids.apply([_red("undecided-product", "prd.md:5", "Undecided")], impl)
    assert sidecar.read_text(encoding="utf-8") == "{ corrupt", "the registry must not be clobbered"


def test_missing_sidecar_is_a_clean_first_run(tmp_path):
    out = red_ids.apply([_red("undecided-product", "prd.md:5", "Undecided")], tmp_path)
    assert len(out["reds"]) == 1 and out["resolved"] == []


def test_written_reds_carry_the_four_scan_fields_plus_the_id(tmp_path):
    out = red_ids.apply([_red("undecided-product", "prd.md:5", "Undecided")], tmp_path)
    assert set(out["reds"][0]) == {"id", *red_ids.RED_FIELDS}


# --- cli ----------------------------------------------------------------------
def test_cli_writes_the_sidecar_and_echoes_it(tmp_path, capsys):
    scan = tmp_path / "scan.json"
    _write(scan, {"reds": [_red("undecided-product", "prd.md:5", "Undecided")], "concerns": []})
    rc = red_ids.main(["--scan", str(scan), "--impl-artifacts", str(tmp_path)])
    assert rc == 0
    written = json.loads((tmp_path / ".preflight-reds.json").read_text(encoding="utf-8"))
    assert written == json.loads(capsys.readouterr().out)


def test_cli_dry_run_writes_nothing(tmp_path):
    scan = tmp_path / "scan.json"
    _write(scan, {"reds": [_red("undecided-product", "prd.md:5", "Undecided")]})
    assert red_ids.main(["--scan", str(scan), "--impl-artifacts", str(tmp_path), "--dry-run"]) == 0
    assert not (tmp_path / ".preflight-reds.json").exists()


def test_cli_from_sidecar_applies_a_close_without_a_new_scan(tmp_path):
    scan = tmp_path / "scan.json"
    _write(scan, {"reds": [_red("undecided-product", "prd.md:5", "Undecided")]})
    red_ids.main(["--scan", str(scan), "--impl-artifacts", str(tmp_path)])
    the_id = json.loads((tmp_path / ".preflight-reds.json").read_text(encoding="utf-8"))["reds"][0]["id"]
    _write(tmp_path / ".decisions.json", {"decisions": [{"id": the_id, "action": "close", "answer": "done"}]})

    assert red_ids.main(["--from-sidecar", "--impl-artifacts", str(tmp_path)]) == 0
    after = json.loads((tmp_path / ".preflight-reds.json").read_text(encoding="utf-8"))
    assert after["reds"] == [], "the closed red is cleared"
    assert [t["id"] for t in after["resolved"]] == [the_id], "and leaves its tombstone"


def test_cli_mint_one_is_stable_and_touches_nothing(tmp_path, capsys):
    args = ["--mint-one", "budget-overrun", "impl/.escalation-3-1.md:4", "Re-scope, split, or hand off story 3-1"]
    assert red_ids.main(args) == 0
    first = capsys.readouterr().out.strip()
    assert red_ids.main(args) == 0
    assert capsys.readouterr().out.strip() == first, "the same item must mint the same id"
    assert first == red_ids.mint_id(
        "budget-overrun", "impl/.escalation-3-1.md:4", "Re-scope, split, or hand off story 3-1"
    )
    assert list(tmp_path.iterdir()) == [], "--mint-one must write nothing"


def test_cli_requires_exactly_one_input_mode(tmp_path):
    with pytest.raises(SystemExit):
        red_ids.main(["--impl-artifacts", str(tmp_path)])


def test_cli_rejects_a_malformed_scan(tmp_path, capsys):
    scan = tmp_path / "scan.json"
    _write(scan, {"reds": [{"kind": "undecided-product"}]})  # no source
    assert red_ids.main(["--scan", str(scan), "--impl-artifacts", str(tmp_path)]) == 2
    assert "error" in capsys.readouterr().err
