"""Story 2.3 — step-3 second hypothesis stream: seed formalize judgment_candidates.

Doc-shape assertions over preflight.md '## 3.' — the seed rides the EXISTING single
throwaway subagent (no second subagent), keeps the three-key return contract, preserves
the zero-net-conductor-context discipline, and keeps the script-flags / subagent-decides
boundary with a fail-closed default. Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"

_SECTION_RE = re.compile(r"^## 3\..*?(?=^## )", re.MULTILINE | re.DOTALL)


def _section() -> str:
    m = _SECTION_RE.search(_PREFLIGHT.read_text(encoding="utf-8"))
    assert m is not None, "step-3 section not found"
    return m.group(0)


def test_step3_seeds_formalize_candidates_single_subagent():
    section = _section()
    assert "judgment_candidates" in section
    assert "instead of scanning blind" in section
    assert re.search(r"(one|single) (throwaway )?subagent", section), "single-subagent spawn missing"
    low = section.lower()
    assert "second subagent" not in low and "another subagent" not in low, "no second subagent allowed"


def test_step3_contract_is_three_key():
    section = _section()
    fence = re.search(r"```json\s*(.*?)```", section, re.DOTALL)
    assert fence is not None, "step-3 json contract fence missing"
    body = fence.group(1)
    top_keys = set(re.findall(r'"([a-z_]+)"\s*:', body))
    # top-level keys of the returned object are exactly the three-key set
    assert {"reds", "concerns", "advisories_checked"} <= top_keys
    assert top_keys & {"reds", "concerns", "advisories_checked"} == {"reds", "concerns", "advisories_checked"}
    assert "formalize_candidates" not in top_keys and "formalize_verdict" not in top_keys
    for k in ("source", "kind", "decision_needed", "evidence"):
        assert k in body, f"reds[] entry must carry {k!r}"


def test_step3_zero_net_conductor_context():
    section = _section()
    assert "ONLY this object" in section or "no prose" in section
    assert re.search(r"discarded|stays in (its|the) discarded", section)
    assert re.search(r"source:?line|source:\s*line|candidate .*list", section, re.IGNORECASE)
    assert not re.search(
        r"paste[^.\n]{0,40}(corpus|full text|artifact bod|whole (file|artifact))",
        section,
        re.IGNORECASE,
    ), "must not instruct pasting full artifact bodies into the conductor prompt"


def test_step3_script_flags_subagent_decides():
    section = _section()
    # (a) confirm/clear verb structurally co-located with the candidate term
    assert re.search(
        r"(confirm|verify|clear)[^.\n]{0,80}(judgment_candidate|candidate)"
        r"|(judgment_candidate|candidate)[^.\n]{0,80}(confirm|verify|clear)",
        section,
        re.IGNORECASE,
    ), "confirm/clear instruction must be co-located with the candidate term"
    # (b) does not auto-promote a candidate to RED without the subagent
    assert not re.search(r"automatically (a |an )?red", section, re.IGNORECASE)
    assert not re.search(r"script[^.\n]{0,40}decides", section, re.IGNORECASE)
    # (c) fail-closed default present
    assert re.search(
        r"default(s)? to (red|judgment)|cannot (confirm|clear|decide)[^.\n]{0,60}(red|judgment)",
        section,
        re.IGNORECASE,
    ), "fail-closed default (candidate → RED/JUDGMENT) missing"
