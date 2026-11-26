#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract: define-done names the checklist column the gate trail reads (issue #284).

Stage 6's evidence trail (`scripts/gate_trail.py`) takes a production story's
planned tests from the first table of `atdd-checklist-<story_key>.md` keyed by
acceptance criterion, and only from a column whose header it knows. Define-done
step 2 asked ATDD for a checklist "mapping each AC to its planned test(s)" and
named no header, and TEA's own template gives its AC table no test column, so a
checklist that did map every criterion to its test, under a header of its own
such as `Primary red-phase leaf`, rendered `n/a` in every planned-test cell.

Now step 2 has ATDD keep the criteria in TEA's template table, never in a list,
and add a column headed `Planned test` to it, the first table keyed by AC. It
says what the trail renders otherwise: `n/a` with a note line for a header it
does not read, and no criteria from a list or a table keyed only by a bare
header, so, with no other table keyed by AC, the trace report's, with no note.
This file pins that paragraph and ties it to the reader: every header the step
names must be one the trail's own header list holds, every example of an unread
header must be one it does not hold, the bare headers it names must be the
trail's own, and the trail, given the step's template table with a column under
that header, must read both planned tests. So neither the prose nor the reader
can drift alone.

Each predicate has an anti-vacuous twin: the pre-edit step (the live text with
the paragraph taken out) and one-clause mutants must fail it, and the same table
under another header must read `n/a`. Stated limit: this is a presence proof
over prose. It shows the instruction is in the file, not that an ATDD run obeys
it.

`test_gate_trail.py` reads the step's headers through `_named_headers` here, so
the step's boundary is spelled once.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_DEFINE_DONE = _SKILL_ROOT / "references" / "define-done.md"
_GATE_TRAIL = _SKILL_ROOT / "scripts" / "gate_trail.py"

# The paragraph's bold lead, which the pre-edit mutant removes the paragraph by.
_LEAD = "   **Have it head the checklist's test column `Planned test`.**"
# A header TEA's own vocabulary suggests (it calls a scaffold a red-phase leaf)
# and the trail does not read.
_UNREAD_HEADER = "Primary red-phase leaf"
# The header row of the AC table TEA 1.27.2's ATDD checklist template writes.
_TEA_TEMPLATE = "| ID | ID source | Acceptance criterion |"


def _load_gate_trail():
    # A name of its own, so this load never replaces the module object another
    # trail test registered (and may be monkeypatching) under `gate_trail`.
    name = "gate_trail_for_define_done_header"
    spec = importlib.util.spec_from_file_location(name, _GATE_TRAIL)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


gate_trail = _load_gate_trail()

_ATDD_STEP = re.compile(
    r"^2\. \*\*`bmad-testarch-atdd`\*\*.*?(?=^\*\*In `--light`:\*\*|\Z)",
    re.MULTILINE | re.DOTALL,
)
# The table the step has ATDD keep the criteria in, as it quotes it.
_TEMPLATE = re.compile(r"in the table TEA's template gives them \(`(\|[^`]+\|)`\), never in a list,")
# Where the step puts the test column: in that table, the first keyed by AC.
_PLACE = re.compile(r"in a column headed `[^`]+` added to that table, the first table in the file keyed by AC\.")
# The examples of a header the trail does not read, and what it renders then.
_UNREAD = re.compile(
    r"when that table names them under a header it does not read \(((?:`[^`]+`)(?:, `[^`]+`)*)\), "
    r"or leaves them to a later table or a list, the trail renders `n/a` in every planned-test cell "
    r"of the story, with a note line that says so\."
)
# The bare headers the step says key no criteria table on their own.
_BARE = re.compile(
    r"A list of criteria, or a table keyed only by ((?:`[^`]+`)(?:(?:, | or )`[^`]+`)*) with no test column "
    r"the trail reads, gives the trail none of them: with no other table in the file keyed by AC, it takes "
    r"them from the trace report instead, with no note\."
)


def _text() -> str:
    return _DEFINE_DONE.read_text(encoding="utf-8")


def _atdd_step(text: str) -> str:
    """Step 2 of "Per Story", from its numbered item to the `--light` note."""
    match = _ATDD_STEP.search(text)
    return match.group(0) if match else ""


def _named_headers(text: str) -> list[str]:
    """Every column header step 2 names, as `column headed `<header>``."""
    return re.findall(r"column headed `([^`]+)`", _atdd_step(text))


def _quoted(pattern: re.Pattern[str], step: str) -> list[str]:
    """The backticked names in the pattern's first group, or none."""
    match = pattern.search(step)
    return re.findall(r"`([^`]+)`", match.group(1)) if match else []


def _template(text: str) -> str:
    """The header row of the table step 2 has ATDD keep the criteria in."""
    match = _TEMPLATE.search(_atdd_step(text))
    return match.group(1) if match else ""


def _reads(header: str) -> bool:
    return gate_trail._normalize_header(header) in gate_trail._TEST_HEADER_PREFERENCE


def _names_a_header_the_trail_reads(text: str) -> bool:
    """True only when step 2 has ATDD keep the criteria in TEA's template table,
    never a list; names at least one test-column header, every one the trail
    reads, by file and test name, in that table, the first table keyed by AC;
    says the trail reads that table alone; gives examples of a header it does
    not read, none of which it reads, and says those render `n/a` with a note
    line; names the bare headers that give no criteria as the trail's own and
    says those criteria come from the trace report with no note; and says which
    criteria leave their cell empty."""
    step = _atdd_step(text)
    headers = _named_headers(text)
    unread = _quoted(_UNREAD, step)
    bare = _quoted(_BARE, step)
    return (
        _template(text) == _TEA_TEMPLATE
        and bool(headers)
        and all(_reads(header) for header in headers)
        and "planned test(s), by file and test name, in a column headed" in step
        and _PLACE.search(step) is not None
        and "reads a story's planned tests from that table alone, and only under a header it reads" in step
        and bool(unread)
        and not any(_reads(header) for header in unread)
        and {gate_trail._normalize_header(header) for header in bare} == set(gate_trail._AMBIGUOUS_AC_HEADERS)
        and "An AC with no scaffold (an operator-evidence AC, or a parent AC a decomposed child does not claim, "
        "both below) leaves its cell empty." in step
    )


def _without_the_paragraph(text: str) -> str:
    """The step as it stood before #284: the live text minus the paragraph."""
    start = text.index(_LEAD)
    end = text.index("\n\n", start) + 2
    return text[:start] + text[end:]


def _checklist(header: str, template: str) -> str:
    """The step's template AC table (its header row `template`) with one more
    column headed `header`, two rows. Ids are built, not spelled."""
    columns = [cell.strip() for cell in template.strip().strip("|").split("|")]

    def cell(column: str, n: int) -> str:
        return f"AC-{n}" if column in ("ID", "AC") else f"criterion {n}"

    rows = "".join(
        "| "
        + " | ".join(cell(column, n) for column in columns)
        + f" | `tests/acceptance/sb-{n}.spec.ts` -> `criterion {n} holds` |\n"
        for n in (1, 2)
    )
    return "## Acceptance Criteria\n\n" f"{template} {header} |\n" "|" + " -- |" * (len(columns) + 1) + "\n" + rows


# One clause of the paragraph each, as (what it reads, what the mutant reads).
_MUTANTS = {
    "an-unread-header": ("column headed `Planned test`", f"column headed `{_UNREAD_HEADER}`"),
    "no-first-table": (", the first table in the file keyed by AC", ""),
    "a-later-table-too": (
        "the first table in the file keyed by AC.",
        "the first table in the file keyed by AC or a later one.",
    ),
    "a-list-allowed": (", never in a list,", ","),
    "no-template-table": (" (`| ID | ID source | Acceptance criterion |`)", ""),
    "another-template-table": ("`| ID | ID source | Acceptance criterion |`", "`| AC | Acceptance criterion |`"),
    "no-file-and-test-name": ("by file and test name, ", ""),
    "any-table": ("from that table alone", "from any table"),
    "no-unread-examples": (
        "when that table names them under a header it does not read (`Primary red-phase leaf`, `Scaffold`), "
        "or leaves them to a later table or a list, the trail renders",
        "under that header, the trail renders",
    ),
    "a-read-example": ("`Primary red-phase leaf`, `Scaffold`", "`Primary red-phase leaf`, `Test`"),
    "no-note-line": (", with a note line that says so", ""),
    "no-n-a": (
        "the trail renders `n/a` in every planned-test cell",
        "the trail renders nothing in a planned-test cell",
    ),
    "a-bare-header-missing": ("`ID`, `Criterion` or `Criteria`", "`ID` or `Criterion`"),
    "a-note-on-the-trace": (
        "from the trace report instead, with no note.",
        "from the trace report instead, with a note line.",
    ),
    "no-trace-sentence": (
        "A list of criteria, or a table keyed only by `ID`, `Criterion` or `Criteria` with no test column "
        "the trail reads, gives the trail none of them: with no other table in the file keyed by AC, it "
        "takes them from the trace report instead, with no note. ",
        "",
    ),
    "no-other-table-condition": (" with no other table in the file keyed by AC,", ""),
    "one-kind-unscaffolded": (
        "(an operator-evidence AC, or a parent AC a decomposed child does not claim, both below)",
        "(an operator-evidence AC, below)",
    ),
    "no-empty-cell": (
        " An AC with no scaffold (an operator-evidence AC, or a parent AC a decomposed child does not claim, "
        "both below) leaves its cell empty.",
        "",
    ),
}


def test_define_done_names_a_header_the_trail_reads():
    assert _names_a_header_the_trail_reads(_text()), (
        "define-done step 2 must have ATDD keep the criteria in TEA's template table and head its test "
        "column with a header gate_trail.py reads, and say what the trail renders otherwise"
    )


def test_the_header_predicate_rejects_the_old_step():
    """Twin: the pre-edit step fails."""
    text = _text()
    assert _LEAD in text, "the paragraph's lead moved; update _LEAD"
    pre_edit = _without_the_paragraph(text)
    assert _LEAD not in pre_edit
    assert not _names_a_header_the_trail_reads(pre_edit), "the pre-edit step named no header"


@pytest.mark.parametrize("mutant", sorted(_MUTANTS))
def test_the_header_predicate_rejects_each_one_clause_mutant(mutant):
    """Twin: each clause is load-bearing, so the live text with that clause
    removed or changed fails."""
    old, new = _MUTANTS[mutant]
    text = _text()
    assert text.count(old) == 1, f"the mutated clause moved: {old!r}"
    assert not _names_a_header_the_trail_reads(text.replace(old, new)), mutant


def test_the_header_define_done_names_yields_the_planned_tests():
    """The prose tied to the reader: the step's template table with a column
    under each header step 2 names yields both planned tests."""
    template = _template(_text())
    headers = _named_headers(_text())
    assert template and headers
    for header in headers:
        rows = gate_trail.criterion_rows(_checklist(header, template))
        assert [row[0] for row in rows] == [f"AC-{n}" for n in (1, 2)]
        assert [row[1] for row in rows] == [
            f"`tests/acceptance/sb-{n}.spec.ts` -> `criterion {n} holds`" for n in (1, 2)
        ], header


def test_another_header_yields_no_planned_test():
    """Twin: TEA's table under a header the trail does not read gives `n/a`."""
    rows = gate_trail.criterion_rows(_checklist(_UNREAD_HEADER, _TEA_TEMPLATE))
    assert [row[0] for row in rows] == [f"AC-{n}" for n in (1, 2)]
    assert [row[1] for row in rows] == ["n/a", "n/a"]


def test_a_list_or_a_bare_keyed_table_gives_the_trail_no_criteria():
    """The prose tied to the reader: a checklist that lists its criteria, or
    keys its table only by a bare header the step names, with an unread test
    column, gives `criterion_rows` nothing, so the trail goes to the trace
    report."""
    bare = _quoted(_BARE, _atdd_step(_text()))
    assert bare
    listed = "## Acceptance Criteria\n\n" + "".join(f"{n}. criterion {n}\n" for n in (1, 2))
    assert gate_trail.criterion_rows(listed) == []
    for header in bare:
        assert gate_trail.criterion_rows(_bare_table(header, _UNREAD_HEADER)) == [], header


def test_a_bare_keyed_table_with_a_column_the_trail_reads_gives_criteria():
    """Twin: a table keyed by each bare header the trail holds, with its test
    column headed as the step asks, gives the criteria, so the empty result
    above is the test header's doing."""
    assert gate_trail._AMBIGUOUS_AC_HEADERS
    for header in sorted(gate_trail._AMBIGUOUS_AC_HEADERS):
        rows = gate_trail.criterion_rows(_bare_table(header, "Planned test"))
        assert [row[0] for row in rows] == [f"AC-{n}" for n in (1, 2)], header


def test_a_later_table_keyed_by_ac_gives_the_criteria_a_bare_keyed_one_does_not():
    """The step's condition tied to the reader: after a bare-keyed table the
    trail skips, a later table keyed by AC gives the criteria, so the trace
    report is reached only with no other table keyed by AC."""
    later = "\n| AC | Planned test |\n| -- | -- |\n" + "".join(f"| AC-{n} | `p{n}` |\n" for n in (1, 2))
    for header in sorted(gate_trail._AMBIGUOUS_AC_HEADERS):
        rows = gate_trail.criterion_rows(_bare_table(header, _UNREAD_HEADER) + later)
        assert rows == [(f"AC-{n}", f"`p{n}`", "n/a") for n in (1, 2)], header


def _bare_table(key: str, test_header: str) -> str:
    rows = "".join(f"| AC-{n} | `t{n}` |\n" for n in (1, 2))
    return f"| {key} | {test_header} |\n| -- | -- |\n" + rows
