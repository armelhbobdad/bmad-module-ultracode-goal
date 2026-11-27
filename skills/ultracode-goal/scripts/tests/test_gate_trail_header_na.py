#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Contract for what the gate trail's header says an `n/a` cell means.

`gate_trail.py` writes `gate-trail.md` at finalize, and its header tells the
reader how to read the cells below it. In 8.1.1 the header said only "A cell
whose source artifact was absent or unreadable reads `n/a`", while the script
also renders `n/a` from a source it did read: an empty cell, or a column the
source's table does not carry, such as a result cell the acceptance checklist
left empty, or every result cell of a checklist whose table has no result
column. A reader who trusted the header took every such `n/a` for a missing
file. `docs/how-it-works.md` already said both. (One such case, a checklist
with no test column the trail reads, has carried a line of its own in the
story's section since 8.1.1; the cases above carry none, so the header is all
that explains them.)

The header's sentence now reads: "A cell whose source artifact was absent or
unreadable reads `n/a`, and so can one whose source was read, when the cell is
empty or its table has no such column." The comment on the script's `NA`
constant says the same.

The trail is rendered from the production fixture under
`fixtures/gate_trail/`, through the script's command line as finalize runs it,
and the predicate is checked on that header and, as its anti-vacuous twin, on
headers rendered by one-statement mutants of the script (the 8.1.1 sentence
among them). The condition the header gives is checked word for word against
the user doc's, the `NA` comment against the header's two conditions, and the
claim itself against trails rendered from a checklist that leaves a result
cell empty and from one whose table has no result column, beside a twin whose
cells are all filled, each with no line of its own to explain the `n/a`.
Stated limit: this shows what the header says and that the cases it names
occur; the script's other `n/a` cases are `test_gate_trail.py`'s to prove.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
_SCRIPT = _SCRIPTS / "gate_trail.py"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gate_trail"
_REPO = _SCRIPTS.parents[2]
HOW_IT_WORKS = (_REPO / "docs" / "how-it-works.md").read_text(encoding="utf-8")

_STORIES = ["7-1", "7-2", "7-3", "7-4"]

_VERDICTS = "It renders the gate's verdicts; it never forms one."
_ABSENT = "A cell whose source artifact was absent or unreadable reads `n/a`"
_READ = ", and so can one whose source was read, "
_CONDITION = "when the cell is empty or its table has no such column."
_SENTENCE = _VERDICTS + " " + _ABSENT + _READ + _CONDITION

# The script's statement that writes the sentence, as it spells it, and the
# 8.1.1 statement it replaced.
_STATEMENT = (
    '        f"was absent or unreadable reads `{NA}`, and so can one whose source was read, when the "\n'
    '        "cell is empty or its table has no such column.",\n'
)
_PRE_EDIT_STATEMENT = '        f"was absent or unreadable reads `{NA}`.",\n'


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _header(trail: str) -> str:
    """The trail above its first story section."""
    end = trail.find("\n## ")
    return trail[: end if end != -1 else len(trail)]


def _header_says_a_read_source_can_render_na(trail: str) -> bool:
    """The header holds the sentence, as one paragraph of its own, directly
    after the paragraph that names the trail's sources."""
    paragraphs = [_flat(part).strip() for part in _header(trail).split("\n\n")]
    if _SENTENCE not in paragraphs:
        return False
    at = paragraphs.index(_SENTENCE)
    return at > 0 and paragraphs[at - 1].startswith("Synthesized at finalize from the artifacts this run already wrote")


def _render_cli(tmp_path: Path) -> str:
    """The production fixture's trail, written by the script's command line."""
    root = tmp_path / "production"
    shutil.copytree(_FIXTURES / "production", root)
    run_dir = tmp_path / "run"
    cmd = [sys.executable, str(_SCRIPT), "--run-dir", str(run_dir), "--profile", "production", "--epic", "7"]
    for story in _STORIES:
        cmd += ["--story", story]
    cmd += [
        "--impl-artifacts", str(root / "impl-artifacts"),
        "--trace-output", str(root / "test-artifacts" / "traceability"),
        "--test-artifacts", str(root / "test-artifacts"),
        "--decision-log", str(root / "decision-log.md"),
        "--repo", str(tmp_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return (run_dir / "gate-trail.md").read_text(encoding="utf-8")


def _load_live():
    spec = importlib.util.spec_from_file_location("gate_trail_header_na_live", _SCRIPT)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _mutant(old: str, new: str) -> types.ModuleType:
    """gate_trail.py with one statement replaced, loaded as a module of its own."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert source.count(old) == 1, f"the mutated statement moved: {old!r}"
    module = types.ModuleType("gate_trail_header_na_mutant")
    module.__file__ = str(_SCRIPT)
    exec(compile(source.replace(old, new), str(_SCRIPT), "exec"), module.__dict__)  # noqa: S102
    return module


def _render_in_process(trail_module, tmp_path: Path) -> str:
    """The production fixture's trail, rendered by `trail_module` in process."""
    root = tmp_path / "production"
    shutil.copytree(_FIXTURES / "production", root)
    return trail_module.render(
        _STORIES,
        epic="7",
        profile="production",
        impl_artifacts=root / "impl-artifacts",
        test_artifacts=root / "test-artifacts",
        trace_output=root / "test-artifacts" / "traceability",
        decision_log=root / "decision-log.md",
        repo=tmp_path,
    )


def test_the_trail_header_says_a_read_source_can_render_na(tmp_path):
    assert _header_says_a_read_source_can_render_na(_render_cli(tmp_path))


def test_the_in_process_render_writes_the_same_header(tmp_path):
    """The twins below render in process; the live module there writes the
    header the command line writes, so a twin's header differs only by its
    mutation."""
    cli = _header(_render_cli(tmp_path / "cli"))
    assert _header(_render_in_process(_load_live(), tmp_path / "live")) == cli


def test_header_predicate_rejects_the_pre_edit_header(tmp_path):
    trail = _render_in_process(_mutant(_STATEMENT, _PRE_EDIT_STATEMENT), tmp_path)
    assert _ABSENT + "." in _flat(_header(trail))
    assert not _header_says_a_read_source_can_render_na(trail)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("when the cell is empty or its table has no such column.", "when the cell is empty.",
                     id="empty-cell-only"),
        pytest.param("when the cell is empty or its table has no such column.",
                     "when its table has no such column.", id="missing-column-only"),
        pytest.param("and so can one whose source was read,", "and never one whose source was read,",
                     id="never-a-read-source"),
        pytest.param("was absent or unreadable reads", "was absent reads", id="unreadable-dropped"),
    ],
)
def test_header_predicate_rejects_a_one_clause_mutant(tmp_path, old, new):
    statement = _STATEMENT.replace(old, new, 1) if old in _STATEMENT else None
    if statement is None:
        # The clause spans the statement's two string literals.
        joined = _STATEMENT.replace('when the "\n        "cell', "when the cell")
        assert old in joined, old
        statement = joined.replace(old, new, 1)
    assert statement != _STATEMENT
    trail = _render_in_process(_mutant(_STATEMENT, statement), tmp_path)
    assert not _header_says_a_read_source_can_render_na(trail)


def test_header_predicate_rejects_the_header_without_the_n_a_sentence(tmp_path):
    module = _mutant(
        '        "It renders the gate\'s verdicts; it never forms one. A cell whose source artifact "\n' + _STATEMENT,
        '        "It renders the gate\'s verdicts; it never forms one.",\n',
    )
    trail = _render_in_process(module, tmp_path)
    assert _VERDICTS in _flat(_header(trail))
    assert not _header_says_a_read_source_can_render_na(trail)


def test_header_predicate_rejects_the_sentence_moved_below_the_story_count(tmp_path):
    """The sentence as a paragraph of its own after the profile and story
    lines, away from the paragraph that names the sources it speaks of."""
    module = _mutant(
        '        "It renders the gate\'s verdicts; it never forms one. A cell whose source artifact "\n'
        + _STATEMENT
        + '        "",\n        f"- Profile: {profile}",\n        f"- Stories: {len(stories)}",\n',
        '        f"- Profile: {profile}",\n        f"- Stories: {len(stories)}",\n        "",\n'
        '        "It renders the gate\'s verdicts; it never forms one. A cell whose source artifact "\n'
        + _STATEMENT,
    )
    trail = _render_in_process(module, tmp_path)
    assert _SENTENCE in _flat(_header(trail))
    assert not _header_says_a_read_source_can_render_na(trail)


# --- the condition is the user doc's ----------------------------------------------

_DOC_OPENER = "A source it did read can still leave a cell `n/a`, "


def _doc_and_header_agree(header: str, doc: str) -> bool:
    """The condition the header gives for an `n/a` from a source that was read
    is the user doc's, word for word."""
    flat_header, flat_doc = _flat(header), _flat(doc)
    at = flat_header.find(_READ)
    doc_at = flat_doc.find(_DOC_OPENER)
    if at == -1 or doc_at == -1:
        return False
    condition = flat_header[at + len(_READ) :].split(".", 1)[0] + "."
    return flat_doc[doc_at + len(_DOC_OPENER) :].startswith(condition) and condition == _CONDITION


def test_the_header_gives_the_user_doc_s_condition(tmp_path):
    assert _doc_and_header_agree(_header(_render_cli(tmp_path)), HOW_IT_WORKS)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_DOC_OPENER + _CONDITION, _DOC_OPENER + "when the cell is empty.", id="doc-drops-the-column"),
        pytest.param(_DOC_OPENER, "A source it did read never leaves a cell `n/a`. ", id="doc-denies-it"),
    ],
)
def test_agreement_predicate_rejects_a_doc_that_says_otherwise(tmp_path, old, new):
    flat_doc = _flat(HOW_IT_WORKS)
    assert flat_doc.count(_DOC_OPENER + _CONDITION) == 1
    doc = flat_doc.replace(old, new, 1)
    assert doc != flat_doc
    assert not _doc_and_header_agree(_header(_render_cli(tmp_path)), doc)


def test_agreement_predicate_rejects_the_pre_edit_header(tmp_path):
    trail = _render_in_process(_mutant(_STATEMENT, _PRE_EDIT_STATEMENT), tmp_path)
    assert not _doc_and_header_agree(_header(trail), HOW_IT_WORKS)


# --- the NA constant's comment gives the header's two conditions ------------------

_NA_LINE = 'NA = "n/a"\n'
_NA_COMMENT = (
    "Rendered in a cell whose source artifact is absent or unreadable, and in one a read source leaves empty or "
    "whose table has no such column."
)
# 8.1.1's comment, before the change.
_PRE_EDIT_NA_COMMENT = "# Rendered in any cell whose source artifact is absent or unreadable.\n"


def _na_comment(source: str) -> str:
    """The comment block directly above the `NA` constant, its `#` marks taken
    out, or "" when the line above the constant is no comment."""
    lines = source[: source.index(_NA_LINE)].splitlines()
    block: list[str] = []
    while lines and lines[-1].startswith("#"):
        block.insert(0, lines.pop().lstrip("#").strip())
    return " ".join(block)


def _na_comment_gives_both_conditions(source: str) -> bool:
    """The comment on `NA` says what the header says: absent or unreadable, and
    empty or a missing column from a source that was read."""
    return _flat(_na_comment(source)).strip() == _NA_COMMENT


def _script_source() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def _source_replaced(old: str, new: str) -> str:
    source = _script_source()
    assert source.count(old) == 1, old
    mutant = source.replace(old, new, 1)
    assert mutant != source, "the mutant must actually change the text"
    return mutant


def test_the_na_comment_gives_the_header_s_two_conditions():
    assert _na_comment_gives_both_conditions(_script_source())


def test_na_comment_predicate_rejects_the_pre_edit_comment_and_none():
    source = _script_source()
    comment = source[: source.index(_NA_LINE)].rsplit("\n\n", 1)[1]
    assert not _na_comment_gives_both_conditions(_source_replaced(comment, _PRE_EDIT_NA_COMMENT))
    assert not _na_comment_gives_both_conditions(_source_replaced(comment, ""))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("leaves empty or\n# whose table has no such column.", "leaves empty.", id="column-dropped"),
        pytest.param("a read source leaves empty or\n# whose table has no such column.",
                     "a read source's table has no such column.", id="empty-dropped"),
        pytest.param("is absent or unreadable,", "is absent,", id="unreadable-dropped"),
        pytest.param("and in one a read source", "and never in one a read source", id="never-a-read-source"),
        pytest.param("# whose table has no such column.\n" + _NA_LINE,
                     "# whose table has no such column.\n\n" + _NA_LINE, id="parted-from-the-constant"),
    ],
)
def test_na_comment_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _na_comment_gives_both_conditions(_source_replaced(old, new))


# --- the claim holds: a source that was read renders `n/a` ------------------------

_STORY = "61-1-sample-story"
# The bullet lines every story section carries, whatever its cells read.
_STANDARD_BULLETS = ["Criteria and planned tests", "Gate artifact", "Verdict source", "Baseline"]


def _checklist(headers: list[str], rows: list[list[str]]) -> str:
    """A TEA-shaped acceptance checklist whose criteria table has `headers` and
    `rows`."""
    head = "| " + " | ".join(headers) + " |"
    rule = "|" + "|".join(" --- " for _ in headers) + "|"
    body = "".join("| " + " | ".join(row) + " |\n" for row in rows)
    return f"---\nworkflowType: 'testarch-atdd'\n---\n\n# ATDD Checklist\n\n## Acceptance Criteria\n\n{head}\n{rule}\n{body}"


def _criteria(planned: bool, result: list[str] | None) -> str:
    """Two criteria, with a `Planned test` column when `planned`, and a
    `Result` column holding `result` when it is given."""
    headers = ["ID", "ID source", "Acceptance criterion"]
    headers += ["Planned test"] if planned else []
    headers += ["Result"] if result is not None else []
    rows = []
    for n in (1, 2):
        row = [f"AC-{n}", "supplied", f"criterion {n}"]
        row += [f"`tests/acceptance/sample-{n}.spec.ts`"] if planned else []
        row += [result[n - 1]] if result is not None else []
        rows.append(row)
    return _checklist(headers, rows)


def _rendered(tmp_path: Path, checklist: str) -> tuple[list[str], list[str], list[str]]:
    """The story section's bullet names, and its planned-test and result
    cells, rendered from `checklist` alone."""
    test_artifacts = tmp_path / "test-artifacts"
    trace = test_artifacts / "traceability"
    impl = tmp_path / "impl-artifacts"
    trace.mkdir(parents=True)
    impl.mkdir()
    (test_artifacts / f"atdd-checklist-{_STORY}.md").write_text(checklist, encoding="utf-8")
    trail = _load_live().render(
        [_STORY], epic="61", profile="production", impl_artifacts=impl, test_artifacts=test_artifacts,
        trace_output=trace, decision_log=None, repo=tmp_path,
    )
    assert _header_says_a_read_source_can_render_na(trail)
    lines = trail.splitlines()
    assert f"- Criteria and planned tests: atdd-checklist-{_STORY}.md" in lines
    bullets = [line[2:].split(":", 1)[0] for line in lines if line.startswith("- ")][2:]
    cells = [line.strip().strip("|").split("|") for line in lines if line.startswith("| ")][2:]
    return bullets, [row[1].strip() for row in cells], [row[2].strip() for row in cells]


def test_a_result_cell_the_checklist_left_empty_renders_na_with_no_line_of_its_own(tmp_path):
    bullets, planned, result = _rendered(tmp_path, _criteria(True, ["PASS", ""]))
    assert result == ["PASS", "n/a"]
    assert "n/a" not in planned
    assert bullets == _STANDARD_BULLETS


def test_a_checklist_with_no_result_column_renders_na_with_no_line_of_its_own(tmp_path):
    bullets, planned, result = _rendered(tmp_path, _criteria(True, None))
    assert result == ["n/a", "n/a"]
    assert "n/a" not in planned
    assert bullets == _STANDARD_BULLETS


def test_the_same_checklist_filled_renders_no_na(tmp_path):
    """Twin: with every cell filled the same checklist renders no `n/a` in
    those columns, so the ones above come from the empty cell and the missing
    column, not from a file the trail could not read."""
    bullets, planned, result = _rendered(tmp_path, _criteria(True, ["PASS", "FAIL"]))
    assert result == ["PASS", "FAIL"]
    assert planned == ["`tests/acceptance/sample-1.spec.ts`", "`tests/acceptance/sample-2.spec.ts`"]
    assert bullets == _STANDARD_BULLETS


def test_a_checklist_with_no_test_column_has_a_line_of_its_own(tmp_path):
    """The one read-source case 8.1.1 already explained in the story's section:
    a checklist with no test column the trail reads. It renders `n/a` in every
    planned-test cell and adds a `- Planned tests:` line, which the cases above
    do not."""
    bullets, planned, _ = _rendered(tmp_path, _criteria(False, ["PASS", "PASS"]))
    assert planned == ["n/a", "n/a"]
    assert bullets == _STANDARD_BULLETS[:1] + ["Planned tests"] + _STANDARD_BULLETS[1:]
