#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""One definition of a recorded split, and the split record's writers and readers.

A decomposed parent is read through its children at the Epic-level roll-up
only on its split record (`.split-<parent key>.json`, written by
`story_sizing.py --record`). Three passages decide whether a split is
recorded (preflight's formalize gaps bullet, Define-Done step 1, and
`/ucg-formalize`'s remediation), and they must name the same three records,
or a child counted as split in one stage is scaffolded as a story in another.
The resume cursor and the story loop must pass over a `done` parent whose
split is recorded, since it never gets a gate verdict of its own.

Run: uv run --with pytest pytest scripts/tests/test_recorded_split_prose.py
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
REFS = SKILL / "references"
FORMALIZE = SKILL.parent / "ucg-formalize" / "SKILL.md"


def _flat(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


_RECORDS = (
    ".split-<parent key>.json",
    "the child's row cites the parent ACs it claims",
    "names the parent and the ACs each child claims",
)


def test_the_three_deciders_name_the_same_three_records() -> None:
    for path in (REFS / "preflight.md", REFS / "define-done.md", FORMALIZE):
        text = _flat(path)
        found = re.search(r"split is recorded (?:when|\()", text)
        assert found is not None, f"{path.name} no longer defines a recorded split"
        window = text[found.start() : found.start() + 600]
        for record in _RECORDS:
            assert record in window, f"{path.name}: the recorded-split definition lacks {record!r}"


def test_preflight_and_formalize_write_the_record_for_an_older_split() -> None:
    preflight = _flat(REFS / "preflight.md")
    assert "**Write the split record in this pass**" in preflight
    assert "the isolated track's own directory on a flag-only isolated track" in preflight, (
        "preflight must send the record where the Epic gate reads it on an isolated track"
    )
    assert "`parent_row` is `null`" in preflight
    formalize = _flat(FORMALIZE)
    assert "--record {workflow.implementation_artifacts}" in formalize
    for text, name in ((preflight, "preflight.md"), (formalize, "ucg-formalize")):
        assert "does not exit 0" in text and "exit 2" in text, (
            f"{name} must say what is logged when the record is not written"
        )


def test_gate_md_names_every_writer_of_the_record() -> None:
    text = _flat(REFS / "gate.md")
    assert "Execute's decomposition step writes it for every split it makes" in text
    assert "preflight's remediation pass writes it" in text
    assert "`/ucg-formalize` writes it for each such split its own remediation repairs" in text


def test_the_cursor_and_the_loop_pass_over_a_recorded_parent() -> None:
    text = _flat(REFS / "execute.md")
    at = text.find("**The cursor passes over a decomposed parent.**")
    assert at != -1, "the resume cursor's rule for a decomposed parent is gone"
    cursor = text[at : at + 1200]
    assert "pass over it and re-enter at the next story, and never drive it" in cursor
    for record in (".split-<key>.json", "cites the parent ACs it claims", "the ACs each child claims"):
        assert record in cursor, f"the cursor's recorded split lacks {record!r}"
    loop = re.search(r"For each in-scope story, in sprint order, run this loop \(([^)]*\([^)]*\)[^)]*|[^)]*)\)", text)
    assert loop is not None, "the story loop's opening sentence moved"
    assert "split is recorded" in loop.group(1), loop.group(1)
    assert "preflight step 2 set `done` as a container" in loop.group(1), loop.group(1)
