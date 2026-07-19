"""Execute step 0: the per-story baseline SHA marker.

Static prose-contract assertions over execute.md's sequential spine: step 0 writes
`.baseline-<story_id>` from `git rev-parse HEAD` as exactly one newline-terminated
line holding the full 40-hex SHA, before any implementation; and the resume clause
re-reads that marker rather than rebuilding it. The pre-edit step-0 bullet and
resume clause are kept verbatim under fixtures/ as the anti-vacuous twins (mirroring
how fixtures/preflight_step4_baseline_3clause.md is used in
test_preflight_hard_gate_clause.py). Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_PRE_EDIT_STEP0 = _FIXTURES / "execute_step0_baseline_no_sha.md"
_PRE_EDIT_RESUME = _FIXTURES / "execute_resume_clause_no_baseline.md"


def _step0(text: str | None = None) -> str:
    """Slice the numbered step-0 bullet out of the sequential-spine loop."""
    text = text if text is not None else _EXECUTE.read_text(encoding="utf-8")
    start = text.index("\n0. ")
    try:
        end = text.index("\n1. ", start)
    except ValueError:
        end = len(text)
    return text[start:end]


def _resume_clause(text: str | None = None) -> str:
    text = text if text is not None else _EXECUTE.read_text(encoding="utf-8")
    hits = [ln for ln in text.splitlines() if ln.startswith("**On resume,")]
    assert len(hits) == 1, f"expected exactly one resume clause, got {len(hits)}"
    return hits[0]


# The step-0 format contract, one named check per bound property, so the twin can
# assert that *every* one of them reds on the pre-edit bullet (not just that it raised).
_STEP0_CHECKS = {
    "names the .baseline-<story_id> marker": lambda b: ".baseline-<story_id>" in b,
    "names git rev-parse HEAD": lambda b: "git rev-parse HEAD" in b,
    "pins the full 40-hex SHA": lambda b: bool(re.search(r"full 40-hex", b, re.I)),
    "pins one newline-terminated line": lambda b: bool(
        re.search(r"exactly one newline-terminated line", b, re.I)
    ),
    "orders the write before any implementation": lambda b: bool(
        re.search(r"before any implementation", b, re.I)
    ),
}


def _unmet(bullet: str) -> list[str]:
    return sorted(name for name, check in _STEP0_CHECKS.items() if not check(bullet))


def _reassert_covers_baseline(clause: str) -> bool:
    """True iff the clause's re-assert (do not rebuild) set includes the baseline marker."""
    idx = clause.lower().find("re-assert (do not rebuild)")
    if idx == -1:
        return False
    seg = clause[idx:]
    return all(
        re.search(p, seg, re.I)
        for p in (r"epic branch", r"\bhooks\b", r"allowlist", r"baseline")
    )


def test_step0_writes_full_sha_baseline_marker():
    bullet = _step0()
    assert _unmet(bullet) == [], f"step 0 does not pin: {_unmet(bullet)}"
    # the pre-existing step-0 semantics must survive the extension
    assert ".current-story" in bullet and "ULTRACODE_STORY_ID" in bullet
    # the bound format is stated as a contract: --short is called out as a breakage
    assert re.search(r"--short", bullet), "step 0 must rule out an abbreviated SHA"


def test_resume_rereads_baseline_marker_not_rebuilt():
    clause = _resume_clause()
    assert _reassert_covers_baseline(clause), (
        "the baseline marker must join the Epic branch, hooks and allowlist in the "
        "re-assert (do not rebuild) set"
    )
    assert re.search(r"re-?read", clause, re.I) and re.search(
        r"never regenerate|not regenerate|do not regenerate", clause, re.I
    ), "resume must re-read, never regenerate, the marker"
    # step 0 states the absent -> write / present -> read-and-keep discriminator
    bullet = _step0()
    assert re.search(r"is absent, write it now", bullet, re.I), "absent -> write"
    assert re.search(
        r"already present.*resume.*read it and keep it", bullet, re.I | re.S
    ), "present -> read and keep"
    assert re.search(r"never overwrite it", bullet, re.I)


def test_pre_edit_resume_clause_fixture_lacks_baseline():
    """Twin: the verbatim pre-edit resume clause must FAIL the re-assert-set check."""
    pre_edit = _resume_clause(_PRE_EDIT_RESUME.read_text(encoding="utf-8"))
    assert not _reassert_covers_baseline(pre_edit), (
        "the pre-edit resume clause names only the Epic branch, hooks and allowlist; "
        "if it passes, the re-assert-set check above is vacuous"
    )
    # and it is a real resume clause, not an empty/garbled file
    assert "re-assert (do not rebuild)" in pre_edit
    assert all(t in pre_edit.lower() for t in ("epic branch", "hooks", "allowlist"))


def test_pre_edit_step0_fixture_fails_baseline_assertions():
    """Twin: with the step-0 baseline write absent, every format assertion reds."""
    pre_edit = _step0(_PRE_EDIT_STEP0.read_text(encoding="utf-8"))
    assert _unmet(pre_edit) == sorted(_STEP0_CHECKS), (
        "the pre-edit step-0 bullet must fail every baseline assertion; "
        f"it already satisfies {sorted(set(_STEP0_CHECKS) - set(_unmet(pre_edit)))}"
    )


def test_pre_edit_fixture_differs_only_by_baseline_sentence():
    """Twin integrity: the fixture reds for the missing baseline write, nothing else."""
    raw = _PRE_EDIT_STEP0.read_text(encoding="utf-8")
    assert len([ln for ln in raw.splitlines() if ln.startswith("0. ")]) == 1, (
        "fixture must slice to exactly one step-0 bullet"
    )
    pre_edit = _step0(raw)
    # the .current-story / ULTRACODE_STORY_ID clause is carried verbatim from the
    # shipped bullet, so an emptied or truncated fixture fails here
    shipped = _step0()
    clause = (
        "write the story id to `{workflow.implementation_artifacts}/.current-story` "
        "(or export `ULTRACODE_STORY_ID=<story_id>` for the run). The guard reads the "
        "story id from `ULTRACODE_STORY_ID`, falling back to that `.current-story` "
        "file — without one set, it cannot find the marker and denies every commit."
    )
    assert clause in pre_edit, "fixture lost the verbatim .current-story clause"
    assert clause in shipped, "shipped step 0 dropped the pre-existing marker semantics"
