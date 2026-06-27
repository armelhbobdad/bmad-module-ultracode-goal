"""Headless blocked envelope: route a formalize RED through the canonical JSON.

(1) Schema parity: the preflight step-4 blocked block and the SKILL.md master block carry
the same five canonical keys (+ conditional reason); no formalize-prefixed key. (2) The
build_headless_envelope adapter routes a formalize RED through the IDENTICAL channel as a
semantic-scan RED, with the formalize verdict never nested. (3) reason is positional blockers[0],
one physical line. (4) the formalize RED is logged. (5) one envelope definition tree-wide.
Stdlib + pytest only.
"""

import importlib.util
import json
import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_SKILL_MD = _SKILL_ROOT / "SKILL.md"
_HELPER = _SKILL_ROOT / "scripts" / "headless_envelope.py"

CANONICAL = {"status", "skill", "decision_log", "report", "deferred_work"}
STATUS_ENUM = {"complete", "blocked", "complete|blocked"}


def _load_helper():
    spec = importlib.util.spec_from_file_location("headless_envelope", _HELPER)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


he = _load_helper()


def _json_blocks(text: str) -> list[str]:
    return re.findall(r"```json\s*(.*?)```", text, re.DOTALL)


def _parse(block: str):
    try:
        return json.loads(block)
    except json.JSONDecodeError:
        return None


def _first_block_after(text: str, heading: str) -> dict:
    after = text[text.index(heading):]
    blocks = _json_blocks(after)
    for b in blocks:
        d = _parse(b)
        if isinstance(d, dict) and "status" in d:
            return d
    raise AssertionError(f"no status-bearing json block after {heading!r}")


def _canonical_block(text: str) -> dict:
    for b in _json_blocks(text):
        d = _parse(b)
        if isinstance(d, dict) and (set(d) - {"reason"}) == CANONICAL:
            return d
    raise AssertionError("no canonical envelope block found")


# Case 1 ---------------------------------------------------------------------
def test_preflight_blocked_block_has_exact_canonical_keys():
    pre = _first_block_after(_PREFLIGHT.read_text(encoding="utf-8"), "## 4. Hard gate")
    skill = _canonical_block(_SKILL_MD.read_text(encoding="utf-8"))
    assert set(pre.keys()) == CANONICAL | {"reason"}
    assert (set(pre) - {"reason"}) == (set(skill) - {"reason"}) == CANONICAL
    assert not any("formalize" in k for k in pre), "no formalize-prefixed key on the headless surface"


# Case 2 ---------------------------------------------------------------------
def test_formalize_red_routes_through_blocked_envelope(tmp_path):
    log = tmp_path / "dl.md"
    fr5 = {
        "verdict": "blocked",
        "mechanical_gaps": [],
        "judgment_candidates": [
            {"source": "prd.md:42", "kind": "undecided-architecture", "why_machine_cannot_decide": "choose store"}
        ],
        "checks": {},
    }
    env = he.build_headless_envelope(fr5, str(log))
    assert env == {
        "status": "blocked",
        "skill": "ultracode-goal",
        "decision_log": str(log),
        "report": None,
        "deferred_work": None,
        "reason": he._one_line({"source": "prd.md:42", "decision_needed": "choose store"}),
    }
    assert all(v is not fr5 and v != fr5 for v in env.values()), "the formalize verdict must never be an envelope value"

    # anti-vacuous: a SEMANTIC-SCAN red with identical content yields the byte-identical envelope
    sem = [{"source": "prd.md:42", "decision_needed": "choose store", "kind": "undecided-architecture"}]
    env2 = he.build_headless_envelope(sem, str(log))
    assert env2 == env, "formalize and semantic-scan reds share one channel"


# Case 3 ---------------------------------------------------------------------
def test_reason_is_first_red_one_line(tmp_path):
    log = str(tmp_path / "dl.md")
    sem = {"source": "prd.md:10", "decision_needed": "pick auth", "kind": "undecided-product"}
    formal = {"source": "arch.md:7", "decision_needed": "pick store", "kind": "undecided-architecture"}
    assert he.build_headless_envelope([sem, formal], log)["reason"] == he._one_line(sem)
    assert he.build_headless_envelope([formal, sem], log)["reason"] == he._one_line(formal)
    assert he.build_headless_envelope([formal], log)["reason"] == he._one_line(formal)
    # one physical line even from a multi-line decision_needed
    multi = {"source": "x.md:1", "decision_needed": "line1\nline2\nline3"}
    reason = he.build_headless_envelope([multi], log)["reason"]
    assert "\n" not in reason and "line1" in reason and "line3" in reason


# Case 4 ---------------------------------------------------------------------
def test_blocked_envelope_logs_formalize_red(tmp_path):
    log = tmp_path / "dl.md"
    red = {"source": "epic.md:99", "decision_needed": "resolve the undecided NFR threshold"}
    env = he.build_headless_envelope([red], str(log))
    assert env["decision_log"] == str(log)
    assert log.exists()
    body = log.read_text(encoding="utf-8")
    assert "epic.md:99" in body and "resolve the undecided NFR threshold" in body


# Case 5 ---------------------------------------------------------------------
def test_single_envelope_definition():
    canon_keysets = []
    statuses = []
    for md in _SKILL_ROOT.rglob("*.md"):
        if ".analysis" in md.parts:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # deliberate non-UTF8 / unreadable fixtures are not envelope docs
        for block in _json_blocks(text):
            d = _parse(block)
            if not isinstance(d, dict):
                continue
            if (set(d) - {"reason"}) == CANONICAL:
                canon_keysets.append(frozenset(set(d) - {"reason"}))
            if "status" in d:
                statuses.append(d["status"])
    assert canon_keysets, "expected at least one canonical envelope block"
    assert len(set(canon_keysets)) == 1, "all canonical envelope blocks must share one key set"
    for s in statuses:
        assert s in STATUS_ENUM, f"non-canonical headless status string: {s!r}"
