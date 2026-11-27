#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for a prescribed finding on a production signal that did not fail.

Under `--profile production`, `gate_eval.py` downgrades an `advance` to `reloop`
when one production signal fails, and the other can pass beside it: an NFR
assessment can read `FAIL` while the test review scores 80 or more and does not
say `Block`, or the other way round. gate.md's paragraph "A downgrade the
story's own AC prescribes is not a re-loop" read only the failed signal's
findings against the story's acceptance criteria. The passing signal's findings
then went to the generalize step with the rest of the re-loop's findings, where
one that an AC prescribes could get a `class:` line and a fix that breaks the
AC.

The paragraph now ends, directly after its "the next gate takes this paragraph
if the downgrade still stands." sentence, on one more sentence: a signal that
did not fail can carry a prescribed finding too, its findings are read against
the criteria as well, and each prescribed one is named in that entry (the
re-loop's `.decision-log.md` entry the sentence before it names), gets no
`class:` line and stays unfixed; only a failed signal's findings count toward
the `ac-amendment-needed` escalation, so the sentence adds no stop. It rides
the paragraph's key, a downgrade with no gate FAIL, and sets none of its own.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against gate.md without the sentence (gate.md as v8.1.1 shipped it) and
one-clause mutants it must reject. The sentence is pinned whole and in place,
not the paragraph around it, which `test_gate_ac_prescribed_downgrade_prose.py`
pins clause by clause. The case the sentence covers is checked against
`gate_eval.py` itself (one signal failed, the other did not, and the reasons
name only the failed one), and its facts about TEA against the tracked
reference skill under `skf-skills/tea-testarch/` (the installed TEA skills
under `.claude/skills/` are not tracked, so no test reads them): a test review
scoring 80 or more can still deduct for a MEDIUM or LOW finding and waives
none for the story's context, and an NFR assessment rates a criterion
`CONCERNS` without blocking.

Stated limits: this is a presence proof over prose. It shows the instruction is
in the file, not that a conductor obeys it or that TEA behaves as its reference
says. The paragraph lists the findings behind a failure (each violation a
failed test review deducts for, each criterion a failed NFR assessment rates
`FAIL`) and the sentence does not list a passing signal's, so no test pins
which entries of a passing NFR assessment are its findings. The tracked
reference states how TEA rolls a domain's status up from its findings, not how
it rolls the Overall Status up from the domains, so no test shows that an
assessment whose Overall Status is not `FAIL` rates no criterion `FAIL`.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
GATE = (_SKILL_ROOT / "references" / "gate.md").read_text(encoding="utf-8")

_HEAD = "**A downgrade the story's own AC prescribes is not a re-loop.**"
_RED_BACKFILL_HEAD = "**A red backfill sweep and the `gate-gap:` lines take this route their own way.**"
# The paragraph's key, which the existing pin checks too: a downgrade, with no gate FAIL.
_KEY = (
    "On a `reloop` whose `reasons` hold `production signal failed; advance downgraded to reloop` (a PASS or "
    "WAIVED gate, with no gate FAIL)"
)
# The reading the new sentence does "as well": the failed signal's, before the generalize step.
_FAILED_READ = "against the story's acceptance criteria before the generalize step above starts"
# The escalation's condition, over the signals that failed and no other.
_ESCALATION = (
    "When every production signal that failed was read and has findings behind its failure, and every one of "
    "those findings is prescribed"
)
# The entry "that entry" names: the re-loop's, from the sentence the new one follows.
_ENTRY = "name the prescribed findings in this re-loop's `.decision-log.md` entry"
_STILL_STANDS = "and the next gate takes this paragraph if the downgrade still stands."

_OPENER = "A signal that did not fail can carry a prescribed finding too"
# Which entries of a signal that did not fail are its findings, in the paragraph's own form for a failed one.
_WHICH = (
    " (each violation a test review that did not fail deducts for, each criterion an NFR assessment that did not "
    "fail rates `CONCERNS`):"
)
_READ = _OPENER + _WHICH + " its findings are read against the criteria as well"
_UNFIXED = ", and each prescribed one is named in that entry, gets no `class:` line and stays unfixed;"
_NO_STOP = " only a failed signal's findings count toward the escalation above."
_SENTENCE = _READ + _UNFIXED + _NO_STOP


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _raw_paragraph(gate: str) -> str:
    """The paragraph as the file holds it, its two-space indent included, or ''."""
    if gate.count(_HEAD) != 1:
        return ""
    start = gate.index(_HEAD) - 2
    end = gate.find("\n\n", start)
    return gate[start : end if end != -1 else len(gate)]


def _paragraph(gate: str = GATE) -> str:
    return _flat(_raw_paragraph(gate)).strip()


def _added(paragraph: str) -> str:
    """The sentence directly after the "still stands." one, or '' when none follows it in the paragraph."""
    if paragraph.count(_STILL_STANDS) != 1:
        return ""
    rest = paragraph.split(_STILL_STANDS, 1)[1].lstrip()
    found = re.match(r".*?\.(?= |$)", rest)
    return found.group(0) if found else ""


def _without_the_sentence(gate: str = GATE) -> str:
    """gate.md before the edit: the paragraph ends on its "still stands." sentence."""
    assert gate.count(" " + _SENTENCE) == 1, "the live text must hold the sentence once"
    return gate.replace(" " + _SENTENCE, "", 1)


def _mutant(old: str, new: str) -> str:
    """The flat paragraph with one clause changed."""
    paragraph = _paragraph()
    assert paragraph.count(old) == 1, "the mutant must change the one clause it names"
    return paragraph.replace(old, new, 1)


def _gate_mutant(old: str, new: str) -> str:
    assert GATE.count(old) == 1, "the mutant must change the one place it names"
    return GATE.replace(old, new, 1)


# --- the sentence sits at the end of the paragraph, after the "still stands." one ---


def _reloop_bullet(gate: str) -> str:
    start = gate.find("- **`reloop`**")
    end = gate.find("- **`escalate`**", start)
    return gate[start:end] if -1 not in (start, end) else ""


def _placed(gate: str) -> bool:
    """The sentence is in the paragraph, indented under the reloop bullet, directly after the "still stands."
    sentence: after the escalation it says it adds nothing to and after the re-loop entry "that entry" names,
    and in no other place of the file."""
    paragraph = _paragraph(gate)
    if not paragraph or _flat(gate).count(_OPENER) != 1:
        return False
    if not _added(paragraph).startswith(_OPENER):
        return False
    reloop = _reloop_bullet(gate)
    return bool(
        _raw_paragraph(gate) in reloop
        # Indented under the bullet, not a bullet of its own.
        and "\n\n  " + _HEAD in reloop
        and reloop.index(_HEAD) < reloop.index(_RED_BACKFILL_HEAD)
        and paragraph.index(_ESCALATION) < paragraph.index(_ENTRY) < paragraph.index(_OPENER)
    )


def test_the_sentence_ends_the_paragraph_after_the_still_stands_sentence():
    assert _placed(GATE)
    # As the file holds it: the sentence follows "still stands." on the paragraph's one line, and the paragraph
    # ends on it, before the blank line that opens the red-backfill paragraph.
    assert _raw_paragraph(GATE).endswith(_STILL_STANDS + " " + _SENTENCE)


def test_placement_predicate_rejects_the_text_without_the_sentence():
    assert not _placed(_without_the_sentence())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # A paragraph of its own after this one: "that entry" and "the escalation above" then point at nothing.
        pytest.param(" " + _SENTENCE, "\n\n  " + _SENTENCE, id="own-paragraph"),
        # A sentence put between: "that entry" could then name another entry.
        pytest.param(" " + _SENTENCE, " The next gate reads them again. " + _SENTENCE, id="sentence-between"),
        # The paragraph moved out of the reloop bullet, the sentence with it.
        pytest.param("\n\n  " + _HEAD, "\n\n- " + _HEAD, id="paragraph-top-level"),
    ],
)
def test_placement_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _placed(_gate_mutant(old, new))


def test_placement_predicate_rejects_the_sentence_moved_elsewhere():
    without = _without_the_sentence()
    # Before the "Otherwise" sentence, ahead of the entry it names.
    before = without.replace("Otherwise the route above stands", _SENTENCE + " Otherwise the route above stands", 1)
    assert before != without and not _placed(before)
    # Into the red-backfill paragraph, after its last sentence.
    tail = "only the verdict or a red backfill sweep does."
    assert without.count(tail) == 1
    moved = without.replace(tail, tail + " " + _SENTENCE, 1)
    assert not _placed(moved)
    # Twice: in place and again in the red-backfill paragraph.
    assert not _placed(GATE.replace(tail, tail + " " + _SENTENCE, 1))


def _sentence_is_whole(gate: str) -> bool:
    return _added(_paragraph(gate)) == _SENTENCE


def test_the_sentence_holds_nothing_else():
    assert _sentence_is_whole(GATE)
    assert not _sentence_is_whole(_without_the_sentence())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("and stays unfixed;", "and stays unfixed unless a fix is cheap;", id="clause-added"),
        pytest.param("count toward the escalation above.", "count toward the escalation above, and the generalize "
                     "step reads the rest.", id="clause-appended"),
    ],
)
def test_whole_sentence_predicate_rejects_an_added_clause(old, new):
    assert not _sentence_is_whole(_gate_mutant(old, new))


# --- a passing signal's findings are read against the criteria too --------------------


def _reads_a_passing_signal(paragraph: str) -> bool:
    """A signal that did not fail is read too, against the story's ACs, at the time the failed one is: before
    the generalize step, which "as well" ties it to."""
    sentence = _added(paragraph)
    return bool(
        sentence.startswith(_READ + ",")
        and _FAILED_READ in paragraph
        and paragraph.index(_FAILED_READ) < paragraph.index(sentence)
    )


def test_a_passing_signal_is_read_against_the_criteria():
    assert _reads_a_passing_signal(_paragraph())


def test_read_predicate_rejects_the_text_without_the_sentence():
    assert not _reads_a_passing_signal(_paragraph(_without_the_sentence()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("A signal that did not fail can carry", "A signal that failed can carry", id="failed-only"),
        pytest.param("can carry a prescribed finding too (", "carries no prescribed finding (", id="none-carried"),
        pytest.param("its findings are read against the criteria as well",
                     "its findings go to the generalize step", id="sent-to-generalize"),
        pytest.param("read against the criteria as well", "read against the criteria after the generalize step",
                     id="read-after-generalizing"),
        pytest.param("read against the criteria as well", "read against the review's own rules", id="read-elsewhere"),
        # The reading "as well" refers back to, moved after the generalize step.
        pytest.param(_FAILED_READ, "against the story's acceptance criteria after the generalize step",
                     id="first-read-after-generalizing"),
    ],
)
def test_read_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _reads_a_passing_signal(_mutant(old, new))


# --- a prescribed one is named in the re-loop's entry, gets no class: line, stays unfixed ---


def _leaves_a_prescribed_one_unfixed(paragraph: str) -> bool:
    """Each prescribed finding of a passing signal is named in the re-loop's `.decision-log.md` entry, the one
    the sentence before names, gets no `class:` line and is left unfixed."""
    sentence = _added(paragraph)
    return bool(
        _UNFIXED in sentence
        and sentence.index(_READ) < sentence.index(_UNFIXED)
        and _ENTRY in paragraph
        and paragraph.index(_ENTRY) < paragraph.index(sentence)
    )


def test_a_prescribed_finding_on_a_passing_signal_is_named_and_left_unfixed():
    assert _leaves_a_prescribed_one_unfixed(_paragraph())


def test_unfixed_predicate_rejects_the_text_without_the_sentence():
    assert not _leaves_a_prescribed_one_unfixed(_paragraph(_without_the_sentence()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("is named in that entry,", "is named in the deferred-work ledger,", id="named-off-the-entry"),
        pytest.param("each prescribed one is named in that entry, gets", "each prescribed one gets",
                     id="named-nowhere"),
        pytest.param("gets no `class:` line", "gets a `class:` line", id="class-line-written"),
        pytest.param("and stays unfixed;", "and is fixed;", id="fixed"),
        pytest.param("each prescribed one is named", "the first prescribed one is named", id="first-only"),
        # The entry "that entry" points back to, gone from the sentence before.
        pytest.param(_ENTRY, "name the prescribed findings in the escalation sidecar", id="entry-unnamed"),
    ],
)
def test_unfixed_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _leaves_a_prescribed_one_unfixed(_mutant(old, new))


# --- only a failed signal's findings count toward the escalation: no new stop ----------


def _adds_no_stop(paragraph: str) -> bool:
    """The sentence ends by keeping a passing signal's findings out of the escalation, and the escalation's
    condition still ranges over the signals that failed and no other, so a prescribed finding on a passing
    signal stops no story and an unprescribed one keeps none from its escalation."""
    sentence = _added(paragraph)
    return bool(
        sentence.endswith(";" + _NO_STOP)
        and _ESCALATION + ", no re-loop changes the verdict" in paragraph
        and paragraph.index(_ESCALATION) < paragraph.index(sentence)
        and "take `escalate` with `kind` `ac-amendment-needed`" in paragraph
    )


def test_only_a_failed_signal_counts_toward_the_escalation():
    assert _adds_no_stop(_paragraph())


def test_no_stop_predicate_rejects_the_text_without_the_sentence():
    assert not _adds_no_stop(_paragraph(_without_the_sentence()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("only a failed signal's findings count", "every signal's findings count", id="every-signal"),
        pytest.param("; only a failed signal's findings count toward the escalation above.", ".", id="dropped"),
        pytest.param("; only a failed signal's findings count toward the escalation above.",
                     "; a prescribed one counts toward the escalation above.", id="passing-one-counts"),
        pytest.param("count toward the escalation above.", "count toward the re-loop above.", id="re-loop-only"),
        # The condition itself widened to every signal, a passing one included.
        pytest.param("When every production signal that failed was read", "When every production signal was read",
                     id="condition-over-every-signal"),
    ],
)
def test_no_stop_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _adds_no_stop(_mutant(old, new))


# --- the sentence rides the paragraph's key: a downgrade with no gate FAIL --------------


def _rides_the_downgrade_key(paragraph: str) -> bool:
    """The paragraph still opens on the downgrade with no gate FAIL, and the sentence names no verdict, gate
    status or cap of its own, so it reaches no re-loop the paragraph does not."""
    sentence = _added(paragraph)
    return bool(
        sentence
        and paragraph.startswith(_HEAD + " " + _KEY + ", take each production signal that failed")
        and not re.search(r"`(?:reloop|advance|defer|escalate)`|gate (?:FAIL|PASS)|gate_status|\bcap|re-loops?\b",
                          sentence)
    )


def test_the_sentence_keys_on_the_downgrade_with_no_gate_fail():
    assert _rides_the_downgrade_key(_paragraph())


def test_key_predicate_rejects_the_text_without_the_sentence():
    assert not _rides_the_downgrade_key(_paragraph(_without_the_sentence()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("(a PASS or WAIVED gate, with no gate FAIL)", "(a gate FAIL included)", id="gate-fail-too"),
        pytest.param("On a `reloop` whose `reasons` hold `production signal failed; advance downgraded to reloop`",
                     "On any `reloop`", id="any-reloop"),
        pytest.param(_OPENER, "On any `reloop`, " + _OPENER[0].lower() + _OPENER[1:], id="sentence-on-any-reloop"),
        pytest.param("count toward the escalation above.", "count toward the escalation above, on a gate FAIL too.",
                     id="sentence-on-a-gate-fail"),
        pytest.param("count toward the escalation above.", "count toward the escalation above, and a capped "
                     "re-loop reads them the same way.", id="sentence-on-a-cap"),
    ],
)
def test_key_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _rides_the_downgrade_key(_mutant(old, new))


# --- the case is the script's: one signal failed, the other did not ---------------------


def _load_gate_eval():
    spec = importlib.util.spec_from_file_location(
        "gate_eval_prescribed_on_passed", _SKILL_ROOT / "scripts" / "gate_eval.py"
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_DOWNGRADE = "production signal failed; advance downgraded to reloop"


def _and(gate_eval, folder: Path, score: int, recommendation: str, status: str):
    """The production AND on an otherwise-advance verdict, with TEA's labelled lines."""
    review = folder / f"test-review-61-1-sample-story-{score}.md"
    review.write_text(f"**Quality Score**: {score}/100\n**Recommendation**: {recommendation}\n", encoding="utf-8")
    nfr = folder / f"nfr-assessment-61-1-sample-story-{status.lower()}.md"
    nfr.write_text(f"# NFR Assessment\n\n**Overall Status:** {status}\n", encoding="utf-8")
    reasons: list[str] = []
    return gate_eval.apply_production_and("advance", nfr, review, reasons), reasons


def test_gate_eval_downgrades_with_one_signal_passing_and_names_only_the_failed_one(tmp_path: Path):
    """The paragraph's key is the reason `gate_eval.py` prints, and the sentence's case is real: the NFR
    assessment fails while the review scores 80 or more, or the review fails while the NFR assessment reads
    `CONCERNS`, and the reasons name the failed signal and not the passing one."""
    assert _DOWNGRADE in _KEY
    # The paragraph's failed signal, so a signal that did not fail is a review at 80 or more with no `Block`, or
    # an NFR assessment that is not `FAIL`.
    assert "(a test-review score below 80, a `Block`, an NFR `FAIL`)" in _paragraph()
    gate_eval = _load_gate_eval()
    for score in (80, 85):
        verdict, reasons = _and(gate_eval, tmp_path, score, "Approve with Comments", "FAIL")
        assert verdict == ("reloop", "FAIL", score)
        assert _DOWNGRADE in reasons and "nfr overallStatus is FAIL" in reasons
        assert not [reason for reason in reasons if reason.startswith("test-review")]
    verdict, reasons = _and(gate_eval, tmp_path, 74, "Request Changes", "CONCERNS")
    assert verdict == ("reloop", "CONCERNS", 74)
    assert _DOWNGRADE in reasons and "test-review score 74 < 80" in reasons
    assert not [reason for reason in reasons if reason.startswith("nfr")]
    # Twins: a review at 79 fails beside the NFR one, so neither signal passed; and with neither failing the
    # verdict stays `advance`, the paragraph is not taken and the sentence has no re-loop to act in.
    verdict, reasons = _and(gate_eval, tmp_path, 79, "Request Changes", "FAIL")
    assert verdict == ("reloop", "FAIL", 79) and "test-review score 79 < 80" in reasons
    verdict, reasons = _and(gate_eval, tmp_path, 85, "Approve with Comments", "CONCERNS")
    assert verdict == ("advance", "CONCERNS", 85) and _DOWNGRADE not in reasons


# --- the facts about TEA the sentence rests on -----------------------------------------


def _tea_reference() -> Path:
    """The tracked reference skill for the TEA version this module targets."""
    group = _REPO / "skf-skills" / "tea-testarch"
    active = group / "active"
    version = active.resolve().name if active.is_dir() else active.read_text(encoding="utf-8").strip()
    return group / version / "tea-testarch"


_REVIEW_REF = _flat((_tea_reference() / "references" / "pattern-test-review.md").read_text(encoding="utf-8"))
_NFR_REF = _flat((_tea_reference() / "references" / "pattern-nfr.md").read_text(encoding="utf-8"))


def _caps(review: str) -> dict[str, int]:
    """The score each severity caps a review at, or {} when the reference states none."""
    found = re.search(r"Severity caps: CRITICAL ≤ (\d+), HIGH ≤ (\d+), MEDIUM ≤ (\d+), LOW ≤ (\d+)\.", review)
    return dict(zip(("CRITICAL", "HIGH", "MEDIUM", "LOW"), map(int, found.groups()))) if found else {}


def _a_passing_review_can_list_findings(review: str) -> bool:
    """A review scoring 80 or more carries no CRITICAL or HIGH finding (each caps the score below 80) but still
    deducts for a MEDIUM or LOW one, and TEA waives no violation for the story's context, so a finding an AC
    prescribes can stand in a review that did not fail."""
    caps = _caps(review)
    return bool(
        caps
        and caps["CRITICAL"] < 80
        and caps["HIGH"] < 80
        and max(caps["MEDIUM"], caps["LOW"]) >= 80
        and "CRITICAL −10, HIGH −5, MEDIUM −2, LOW −1" in review
        and "remaining MEDIUM/LOW with score ≥ 70 → Approve with Comments" in review
        and "Context cannot waive violations (`Context Waivers Applied` stays 0)" in review
    )


def test_a_test_review_that_did_not_fail_can_still_list_findings():
    assert _a_passing_review_can_list_findings(_REVIEW_REF)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # Every severity failing the review: a review at 80 or more would then list no finding.
        pytest.param("MEDIUM ≤ 89, LOW ≤ 99", "MEDIUM ≤ 79, LOW ≤ 79", id="every-severity-fails"),
        pytest.param("MEDIUM −2, LOW −1", "MEDIUM 0, LOW 0", id="no-deduction-below-high"),
        pytest.param("Context cannot waive violations", "Context can waive violations", id="context-waives"),
    ],
)
def test_passing_review_predicate_rejects_a_one_clause_mutant(old, new):
    assert _REVIEW_REF.count(old) == 1
    assert not _a_passing_review_can_list_findings(_REVIEW_REF.replace(old, new))


def _a_passing_nfr_can_list_findings(nfr: str) -> bool:
    """TEA rates a criterion `CONCERNS` without blocking, and a domain's status is its worst finding, so a
    domain that is not `FAIL` holds no `FAIL` finding but can hold `CONCERNS` ones."""
    return bool(
        "| `CONCERNS` | Partial or weak; does not block but needs follow-up" in nfr
        and "| `FAIL` | Not implemented or threshold breached" in nfr
        and "Domain status = worst finding (FAIL > CONCERNS > PASS)" in nfr
    )


def test_an_nfr_assessment_that_did_not_fail_can_rate_a_criterion_concerns():
    # The stated limit: the reference gives no roll-up of the Overall Status from the domains, so no test here
    # shows that an Overall Status other than `FAIL` rates no criterion `FAIL`.
    assert _a_passing_nfr_can_list_findings(_NFR_REF)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("does not block but needs follow-up", "blocks", id="concerns-blocks"),
        pytest.param("Domain status = worst finding", "Domain status = first finding", id="first-finding"),
    ],
)
def test_passing_nfr_predicate_rejects_a_one_clause_mutant(old, new):
    assert _NFR_REF.count(old) == 1
    assert not _a_passing_nfr_can_list_findings(_NFR_REF.replace(old, new))
