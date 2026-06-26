"""Story 2.8 — measurement-protocol doc-shape (AC-2/AC-4/AC-5), tracked files only.

The AD-5 wall-clock-ceiling SOURCE lives in the gitignored planning docs
(architecture deferred-fork + PRD NFR-7); those are verified manually at authoring
time and recorded in the run's .decision-log.md, NOT CI-gated here — the Epic-1
CI-portability rule forbids a test depending on a gitignored path. CI asserts only
the tracked surface: the SKILL/preflight measurement prose and the absence of any
authored ceiling number / time-cutoff. The timing-block behavior + no-time-based-block
are covered in test_formalize_check.py (in-process, monkeypatched delay). Stdlib + pytest.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_FORMALIZE_SKILL = _SKILL_ROOT / "skills" / "ucg-formalize" / "SKILL.md"
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_KERNEL = _SKILL_ROOT / "scripts" / "formalize_check.py"

_CEILING_NUMBER = r"ceiling.*=.*[0-9]+ *(ms|s|min)|budget.*[0-9]+ *(ms|seconds|minutes)"
_TIME_CUTOFF = r"timeout|ceiling|deadline|max_(ms|seconds|wall)"


def test_ac2_measurement_protocol_documented():
    skill = _FORMALIZE_SKILL.read_text(encoding="utf-8")
    assert re.search(r"mechanical_ms|end_to_end_ms|wall_clock_ms|artifact_count", skill)
    assert re.search(r"AD-5|NFR-9", skill), "the block must cite AD-5/NFR-9 as its channel authority"
    # no new telemetry sink prose (NFR-9 existing channel only)
    assert not re.search(r"telemetry|metrics-endpoint|POST .*timing|new (sink|channel)", skill)
    # threaded into preflight step-1b
    pre = _PREFLIGHT.read_text(encoding="utf-8")
    assert re.search(r"formalize.*duration|wall_clock_ms.*decision-log|measurement protocol", pre, re.I)
    # anti-vacuous: a stale block dropping the AD-5/NFR-9 citation would fail the channel assertion
    assert not re.search(r"AD-5|NFR-9", "a measurement note with no channel authority")


def test_ac4_no_authored_ceiling_number():
    skill = _FORMALIZE_SKILL.read_text(encoding="utf-8")
    kernel = _KERNEL.read_text(encoding="utf-8")
    assert not re.search(_CEILING_NUMBER, skill), "no authored wall-clock ceiling number in the SKILL"
    assert not re.search(_TIME_CUTOFF, kernel, re.IGNORECASE), "no time cutoff/ceiling in the kernel"
    # anti-vacuous: a guessed ceiling like 'ceiling = 30s' trips the doc-lint
    assert re.search(_CEILING_NUMBER, "wall-clock ceiling = 30s")


def test_ac5_no_measurement_only_spawn():
    skill = _FORMALIZE_SKILL.read_text(encoding="utf-8")
    assert not re.search(r"second subagent|new subagent|additional prompt", skill)
    # anti-vacuous: a dedicated timing subagent would surface here
    assert re.search(r"second subagent", "spawn a second subagent to time it")
