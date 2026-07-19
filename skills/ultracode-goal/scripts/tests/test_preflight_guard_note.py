"""Prose contract over the commit/push guard note in preflight.md.

The note is what an operator reads to predict whether a command will be denied,
so it has to describe the guard the repo actually ships: anchored on the
segment's leading token, taken after assignments and known exec wrappers are
stripped. The anti-vacuous pole is a verbatim snapshot of the pre-edit bullet
(`fixtures/preflight_guard_note_baseline_anywhere.md`), which described a
matches-anywhere scan; both predicates below must REJECT it, or they would be
satisfied by any prose that merely mentions the guard. Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_BASELINE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "preflight_guard_note_baseline_anywhere.md"
)

_NOTE_PREFIX = "- **The commit/push guard"

# The false-positive id this note is the fix for. It is a pull-request id, not a
# planning id, so it is safe to cite in a shipped doc.
_FP_ID = "fp-7ac2643"

# Ids that must never reach a shipped doc.
_PLAN_ID = re.compile(r"\b(?:FR|AD|AC|NFR|INV)-\d+\b")


def _guard_note(text: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith(_NOTE_PREFIX):
            return line
    raise AssertionError("the commit/push guard note is missing")


def _live_note() -> str:
    return _guard_note(_PREFLIGHT.read_text(encoding="utf-8"))


def _baseline_note() -> str:
    return _guard_note(_BASELINE.read_text(encoding="utf-8"))


def _describes_anchored_stripped(note: str) -> bool:
    """True only for prose that states the anchor AND the strip that precedes it."""
    anchored = re.search(r"leading\s+\*{0,2}token", note, re.I)
    stripped = re.search(r"strip", note, re.I) and re.search(
        r"VAR=val|assignment", note, re.I
    )
    still_anywhere = re.search(
        r"string-matches the verb|does not parse the command", note, re.I
    )
    return bool(anchored and stripped and not still_anywhere)


def _carries_fp_id_and_no_plan_ids(note: str) -> bool:
    return _FP_ID in note and _PLAN_ID.search(note) is None


def test_guard_note_describes_anchored_stripped_behavior():
    note = _live_note()
    assert _describes_anchored_stripped(note)
    # the behavior an operator most needs predicted, in both directions
    assert re.search(r"echo", note, re.I), "the allowed shape must be named"
    assert re.search(r"sudo git commit|FOO=bar git commit", note), (
        "the still-denied prefixed shapes must be named"
    )
    assert re.search(r"residual", note, re.I), "the allow-on-unknown residual is stated"
    # surviving facts the rewrite must not drop
    assert "{workflow.protected_branches}" in note
    assert "commit-only" in note and "push" in note
    assert "execute.md step 4" in note
    # anti-vacuous: the pre-edit bullet describes a matches-anywhere scan
    assert not _describes_anchored_stripped(_baseline_note())


def test_guard_note_carries_fp_id_and_no_plan_ids():
    assert _carries_fp_id_and_no_plan_ids(_live_note())
    # anti-vacuous: the pre-edit bullet carries no such id
    assert not _carries_fp_id_and_no_plan_ids(_baseline_note())
    # ...and the predicate's second conjunct is discriminating on its own. The
    # probe below is a synthetic id-shaped string, never a citation of a real one.
    assert not _carries_fp_id_and_no_plan_ids(_live_note() + " (see FR-0)")
