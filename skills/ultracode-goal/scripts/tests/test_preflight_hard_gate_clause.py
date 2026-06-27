"""Step-4 fourth AND-clause: union formalize reds + verdict==ready.

Static prose-contract assertions over preflight.md '## 4. Hard gate': exactly four
co-equal AND-clauses, the formalize reds unioned into the existing no-RED clause (not
a new stop-authority), fail-closed on verdict!=ready, and single-kernel reuse of the
post-remediation verdict (no gate-time re-invocation). Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_BASELINE = Path(__file__).resolve().parent / "fixtures" / "preflight_step4_baseline_3clause.md"


def _step4(text: str | None = None) -> str:
    text = text if text is not None else _PREFLIGHT.read_text(encoding="utf-8")
    start = text.index("## 4. Hard gate")
    try:
        end = text.index("## 5.", start)
    except ValueError:
        end = len(text)
    return text[start:end]


def _launch_bullets(block: str) -> list[str]:
    seg = block[block.index("Launch only when ALL hold"):]
    seg = seg[: seg.index("If any fails")]
    return [ln for ln in seg.splitlines() if ln.startswith("- ")]


def test_step4_has_four_and_clauses():
    bullets = _launch_bullets(_step4())
    assert len(bullets) == 4, f"expected exactly 4 AND-clauses, got {len(bullets)}"
    formalize = [b for b in bullets if re.search(r"formalize_check\.py verdict.*ready", b, re.I)]
    assert len(formalize) == 1, "exactly one formalize verdict==ready clause"
    assert "mechanical_budget == 0" in formalize[0]
    assert re.search(r"no RED", formalize[0]), "fourth clause names both conjuncts"
    # anti-vacuous: the pre-edit 3-clause baseline has 3 bullets and no formalize clause
    base = _launch_bullets(_BASELINE.read_text(encoding="utf-8"))
    assert len(base) == 3
    assert not any(re.search(r"formalize_check\.py verdict.*ready", b, re.I) for b in base)


def test_reds_unioned_not_new_authority():
    s4 = _step4()
    assert re.search(r"no RED.*(formalize|union)|formalize.*reds.*union", s4, re.I | re.S), (
        "the no-RED clause must union in the formalize subagent reds"
    )
    time_block = r"\b(timeout|wall-clock|wall clock|time-based|elapsed|seconds? budget|over-budget.*(block|stop|abort))\b"
    assert not re.search(time_block, s4, re.I), "step-4 must add no time-based stop-authority"
    # anti-vacuous: a standalone time-based STOP bullet would trip the guard
    mutant = s4 + "\n- formalize wall-clock over budget => STOP"
    assert re.search(time_block, mutant, re.I)


def test_formalize_clause_fail_closed():
    s4 = _step4()
    alt1 = r"verdict.*(only|iff|exactly).*ready"
    alt2 = r"(not ready|non-ready|blocked|remediable|unreadable|absent|missing).*(fails|stop|does not launch|blocks)"
    assert re.search(alt1, s4, re.I) or re.search(alt2, s4, re.I), "formalize clause must be fail-closed"
    assert re.search(r"If any fails", s4) and "STOP" in s4, "existing fail-closed disposition must govern"
    # anti-vacuous: a permissive default-pass wording satisfies neither fail-closed arm
    permissive = "- launch unless formalize_check.py explicitly returned blocked"
    assert not (re.search(alt1, permissive, re.I) or re.search(alt2, permissive, re.I))


def test_clause_reuses_post_remediation_kernel():
    s4 = _step4()
    clause = next(b for b in _launch_bullets(s4) if "formalize_check.py" in b)
    assert re.search(r"post-remediation|re-?run|after remediation", clause, re.I)
    assert "formalize_check.py" in clause
    reinvoke = r"(invoke|run|spawn)\s+\S{0,20}formalize_check\.py"
    assert not re.search(reinvoke, s4, re.I), "must reuse the verdict, not re-invoke the kernel at the gate"
    # anti-vacuous: a gate-time re-invocation would trip the guard
    mutant = s4 + "\n- run formalize_check.py again at the gate"
    assert re.search(reinvoke, mutant, re.I)
