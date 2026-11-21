#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract: what the gate asks trace to score for a decomposed child (issue #249).

A decomposed child has no story file of its own. Its criteria are the parent ACs
its sprint-status row claims, written in the parent's story file, which every
sibling shares. `references/gate.md`'s trace delegation ("Name the per-story
paths trace writes, in either profile.") listed what the conductor may ask of
trace and said "Ask for nothing beyond" that list, which named neither the
parent's story file nor the claimed ids. Trace then had no rule limiting it to
the claim, so the siblings' ACs could be scored as uncovered and fail or hold
the child's gate over work it does not owe.

The paragraph now says it, inside what "those names" covers: for a decomposed
child, the parent's story file is the file trace reads the child's criteria
from, the claimed parent AC ids are the only criteria trace scores, and the
siblings' ACs are no row of the child's coverage matrix and no part of its
scores.

The predicate checks what the clause says, anywhere in the naming paragraph,
not its exact words or where it sits. Each property is shown to matter by a
one-clause mutant it rejects, and the clause moved out of the naming paragraph
is rejected too. Stated limit: a presence proof over prose; it shows the
instruction is in the file, not that a conductor obeys it.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_GATE = Path(__file__).resolve().parents[2] / "references" / "gate.md"
_NAMING_HEAD = "**Name the per-story paths trace writes, in either profile.**"
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*(\"])")


def _read() -> str:
    return _GATE.read_text(encoding="utf-8")


def _paragraph(text: str, head: str) -> str:
    """The paragraph that opens with `head`, to the blank line after it, flattened."""
    if head not in text:
        return ""
    start = text.index(head)
    end = text.find("\n\n", start)
    return " ".join((text[start:] if end == -1 else text[start:end]).split())


def _child_clause(paragraph: str) -> str:
    """Every sentence naming a decomposed child, each with the sentence after it."""
    sentences = _SENTENCE.split(paragraph)
    picked: list[str] = []
    for i, sentence in enumerate(sentences):
        if re.search(r"\bdecomposed child", sentence, re.I):
            picked.extend(sentences[i : i + 2])
    return " ".join(picked)


_PROPERTIES = {
    "names a decomposed child": lambda c: bool(re.search(r"\bdecomposed child", c, re.I)),
    "names the parent's story file as the criteria source": lambda c: bool(
        re.search(r"\bparent'?s story file\b", c, re.I) and re.search(r"\bcriteria\b|\bACs?\b", c)
    ),
    "takes the ids the child's row claims": lambda c: bool(
        re.search(r"\b(AC ids?|ACs?|criteria)\b[^.]{0,80}\b(row|sprint-status)\b[^.]{0,40}\bclaim", c, re.I)
        or re.search(r"\bclaimed\b[^.]{0,40}\b(AC ids?|ACs?|criteria)\b", c, re.I)
    ),
    "scores only the claimed ids": lambda c: bool(
        re.search(r"\bonly\b[^.]{0,40}\b(criteria|ACs?|ids?)\b[^.]{0,40}\bscor", c, re.I)
        or re.search(r"\bscor\w*\s+only\b", c, re.I)
    ),
    "leaves the siblings' ACs out of the matrix and the scores": lambda c: bool(
        re.search(
            r"\bsibling[^.]*?\b(none|not|no|never|neither|excluded|left out)\b[^.]*?"
            r"\b(coverage matrix|matrix|scor\w*)\b",
            c,
            re.I,
        )
    ),
}


def _unmet(paragraph: str) -> list[str]:
    clause = _child_clause(paragraph)
    return sorted(name for name, check in _PROPERTIES.items() if not check(clause))


def test_the_trace_delegation_scopes_a_decomposed_child_to_its_claimed_acs():
    paragraph = _paragraph(_read(), _NAMING_HEAD)
    assert paragraph, "the naming paragraph is gone"
    assert _unmet(paragraph) == []
    # It sits where the paragraph's own list can cover it: the paragraph still
    # bounds what trace is asked for, so the clause has to be in that paragraph.
    assert "Ask for nothing beyond those names" in paragraph


def test_the_paragraph_without_the_clause_meets_none_of_it():
    """The paragraph as it stood before the fix names no child at all."""
    paragraph = _paragraph(_read(), _NAMING_HEAD)
    clause = " ".join(s for s in _SENTENCE.split(paragraph) if re.search(r"\bdecomposed child", s, re.I))
    before = paragraph.replace(" " + clause, "")
    assert before != paragraph
    assert _unmet(before) == sorted(_PROPERTIES)


@pytest.mark.parametrize(
    ("old", "new", "lost"),
    [
        pytest.param(
            "its parent's story file", "the epic file", "names the parent's story file as the criteria source",
            id="criteria-elsewhere",
        ),
        pytest.param(
            "the parent AC ids the child's sprint-status row claims", "the parent's ACs",
            "takes the ids the child's row claims", id="whole-parent-list",
        ),
        pytest.param(
            "as the only criteria trace scores", "as criteria trace may score", "scores only the claimed ids",
            id="scope-not-bounded",
        ),
        pytest.param(
            "none of them is a row of the child's coverage matrix or a part of any of its scores",
            "trace reads them as context",
            "leaves the siblings' ACs out of the matrix and the scores", id="siblings-scored",
        ),
        pytest.param("For a decomposed child", "For a split story", "names a decomposed child", id="child-unnamed"),
    ],
)
def test_each_property_rejects_its_one_clause_mutant(old, new, lost):
    paragraph = _paragraph(_read(), _NAMING_HEAD)
    assert paragraph.count(old) == 1, "the mutant must change the one clause it names"
    mutant = paragraph.replace(old, new)
    assert lost in _unmet(mutant)


def test_the_clause_outside_the_naming_paragraph_does_not_count():
    """Locality twin: the same sentence in another paragraph of the gate is not
    part of the list trace may be asked for."""
    text = _read()
    paragraph = _paragraph(text, _NAMING_HEAD)
    clause = " ".join(s for s in _SENTENCE.split(paragraph) if re.search(r"\bdecomposed child", s, re.I))
    raw = text[text.index(_NAMING_HEAD) : text.index("\n\n", text.index(_NAMING_HEAD))]
    assert clause in raw
    moved_out = text.replace(" " + clause, "", 1).replace(
        "## Route on the verdict\n\n", "## Route on the verdict\n\n" + clause + "\n\n", 1
    )
    assert clause in moved_out
    # The clause itself still meets every property where it now stands, so only
    # reading the naming paragraph, and nothing else in the file, rejects it.
    assert _unmet(_paragraph(moved_out, clause[:40])) == []
    assert _unmet(_paragraph(moved_out, _NAMING_HEAD)) == sorted(_PROPERTIES)
