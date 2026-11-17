#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for a backfilled test that reads source text (issue #239).

Where no test runner could execute the code a P0 gap sat in (a constructor
that needs a live host-framework object), automate backfilled a test that read
that code's source file and asserted on its spelling. Every mutant of the
spelled line changed the text the test read, so each row read `KILLED`, and
`references/gate.md` read that as the gap closed: no `gate-gap:` line was
logged, nothing reached the ledger, and the runtime behaviour reached the
verdict unmeasured.

gate.md now says that such a test measures the spelling only. A test reads
source text when it does not execute the code under its gap and reads that
code's text instead (a file read, `include_str!`, a `?raw` import, an AST or a
snapshot of the source). Automate's summary says beside each test whether it
executes the code, and the conductor also reads each backfilled test before
staging: one whose text names the gap's `file` beside a read form reads source
text, whatever the summary says. The test is still committed, and the
behaviour gets an `unmeasured` `gate-gap:` line naming the test and what could
execute the code, which each pass logs afresh at its own commit until a test
that executes the code kills every row behind it. A row in a file such a test
reads counts as killed only as `KILLED` or `KILLED+others` with an
`expect_red` naming a test that executes the code; any other reading there,
`MISATTRIBUTED` included, reads as `GREEN` does and gets the second run. No
pass writes a second test that reads source text for that behaviour, and on
`advance` or `defer` the line becomes the `med` ledger row every open line
becomes, naming the test and what could execute the code. `gate_eval.py`,
`mutate_check.py`'s statuses, the INVARIANT, the ledger's columns and the
escalation kinds are unchanged.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text with the #239 wording taken out (the pre-edit text) and
against one-clause mutants it must reject. A locality twin moves the new
paragraph out of the backfill section. Real `mutate_check.py` runs on a small
project show the reading: the spelled row reads `KILLED` and the gate now
reads it as no kill, and a row whose executing `expect_red` stays green while
the spelling test fails reads `MISATTRIBUTED` and no kill either. A replay on
gate.md's own sentences shows the behaviour line carried at its own commit with
no second spelling test, and the pre-edit text closing the gap. Stated limit:
this is a presence proof over prose. It shows the instruction is in the file,
not that an executor obeys it.

Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_GATE = _SKILL_ROOT / "references" / "gate.md"
_GATE_MODEL = _REPO / "docs" / "gate-model.md"
_FRAGMENT = _REPO / "changes" / "gate-source-reading-backfill.yaml"
_MUTATE_CHECK = _SKILL_ROOT / "scripts" / "mutate_check.py"

_HEAD = "**A test that reads the source measures only its spelling.**"
_CITED = '"A test that reads the source measures only its spelling"'
_CONFIRM_END = (
    "Like an `unmeasured` line, an `unkilled` line is not a finding, and it never changes the route the verdict "
    "takes."
)
_SUMMARY_HEAD = "**Automate's summary records its rows.**"
_KILLED_FIRST = (
    "- A row reads killed when it is `KILLED`, `KILLED+others`, or `MISATTRIBUTED` with the detail that its "
    "`expect_red` never appears beside a failure token."
)

# The new paragraph's rules, as sentences or clauses of it.
_DEFINES = (
    "A test reads source text when it does not execute the code under its gap and reads that code's text, for "
    "example by a file read, an `include_str!` or `include_bytes!`, a `?raw` import, Python's `inspect.getsource` "
    "or JavaScript's `fn.toString()`, or an AST or a snapshot of the source."
)
_SPELLING = "yet nothing has executed the behaviour: its kills measure the spelling and nothing else."
_SUMMARY_FIRST = "Automate's summary says beside each test it backfilled whether the test executes the code"
_BEFORE_STAGING = "before step 1 of \"When automate backfills\" stages anything, read each test the summary names too"
_READ_FORM = (
    "a test whose text names the `file` of its gap's rows beside a read form reads source text, whatever the summary "
    "says of it, and so does one that reads the gap's code by its object without naming the file, as Python's "
    "`inspect.getsource` or JavaScript's `Function.prototype.toString` (`String(fn)`, `fn.toString()`) does. The read "
    "forms include, among others, `open(`, `read_text`, `read_to_string`, `fs::read`, "
    "`include_str!`, `include_bytes!`, `readFile` and `readFileSync` (Node's `fs` or `fs.promises`), Go's "
    "`os.ReadFile`, a `?raw` import and a parse of the source."
)
_COMMIT_AND_LOG = (
    "Commit such a test with the backfill like any other, and log an `unmeasured` `gate-gap:` line for the behaviour "
    "under its gap, naming the test and what could execute the code (a mock of the runtime, a real build)."
)
_NEVER_CLOSES = (
    "so no test that reads source text, the backfilled one or a later one, ever closes that line: it closes only when "
    "a test that executes the code kills every row behind it"
)
_NO_LATER_SPELLING = "and no later pass writes another test that reads source text for it."
_NAMES_APART = (
    "`scripts/mutate_check.py` finds a row's `expect_red` anywhere on a failure line, a test's file path or its suite "
    "or class title included, so a test that reads source text and fails can make a row read `KILLED` for a test that "
    "executes the code whose name sits inside its own name, its file path or its title: when you delegate automate, "
    "tell it to name each test that executes such code so that no test that reads source text has a name, a file "
    "path or a suite or class title that contains it."
)

# Each #239 edit outside the new paragraph as (pre-edit text, live text).
_NO_SECOND = (
    "A gap behind an open `unkilled` line already has its test, so no pass writes it another while its rows can run "
    "(\"A backfill is confirmed in the pass that writes it\" below).",
    "A gap behind an open `unkilled` line already has its test, so no pass writes it another while its rows can run "
    "(\"A backfill is confirmed in the pass that writes it\" below). The behaviour under a gap whose rows only a test "
    "that reads source text has killed already has that test, so no pass writes it another test that reads source "
    "text: only a test that executes the code can measure it (" + _CITED + " below).",
)
_SUMMARY_SAYS = (
    "or behind an open `gate-gap:` line it re-ran and leaves open, so a later cycle can re-run them.",
    "or behind an open `gate-gap:` line it re-ran and leaves open, so a later cycle can re-run them. Tell it, too, to "
    "say beside each test it backfilled, and beside each test a row it ran names as its `expect_red`, whether that "
    "test executes the code under its gap or reads that code's source text, and for one that reads it, what could "
    "execute the code (" + _CITED + " above).",
)
_LOG_ONE = (
    "beside any line step 1 of \"When automate backfills\" logs for a test that was never written.",
    "beside any line step 1 of \"When automate backfills\" logs for a test that was never written. Log one, too, for "
    "the behaviour under each gap whose rows only a test that reads source text has killed (" + _CITED + " above).",
)
_FIELDS = (
    "An owned line ends with its `owned-by` marker (\"An owned `gate-gap:` line is not this story's to close\" below).",
    "An owned line ends with its `owned-by` marker (\"An owned `gate-gap:` line is not this story's to close\" "
    "below). A line for that behaviour says `unmeasured` in place of the summary, and also names the test that reads "
    "the source and what could execute the code, in place of an `unkilled` line for the same gap.",
)
_ROW_RULE = (
    "and a test a re-loop added under a name other than the row's `expect_red` reads `MISATTRIBUTED` that way.",
    "and a test a re-loop added under a name other than the row's `expect_red` reads `MISATTRIBUTED` that way. Where "
    "a test that reads source text reads the row's `file` (" + _CITED + " above), the row reads killed only when it "
    "is `KILLED` or `KILLED+others` and its `expect_red` names a test that executes the code, a name that is no part "
    "of the name, the file path or the suite or class title of a test that reads source text: any other row there, a "
    "`MISATTRIBUTED` one included, reads as a row that reads `GREEN` does, and automate makes its second run too "
    "(the next bullet), so when you delegate it, tell it to.",
)
_AFRESH = (
    "or `unkilled`, naming its test, while a test backfilled for the gap has not killed its rows.",
    "or `unkilled`, naming its test, while a test backfilled for the gap has not killed its rows. A line for the "
    "behaviour a test that reads source text left unmeasured closes only when a test that executes the code kills "
    "every row behind it (" + _CITED + " above), and until then each pass logs it afresh, naming this commit, "
    "`unmeasured`, that test and what could execute the code, whatever its rows read.",
)
_LEDGER_ROW = (
    "An owned line's row also names its owner and the ruling in `reason`, and its `suggested_action` names the owner.",
    "An owned line's row also names its owner and the ruling in `reason`, and its `suggested_action` names the owner. "
    "The row of a line for the behaviour a test that reads source text left unmeasured names that test in `reason`, "
    "and its `suggested_action` names what could execute the code.",
)
_SOURCE_ITEM = (
    "a risk on a P0 criterion it left unmeasured, a gap whose rows could not run, a backfilled test",
    "a risk on a P0 criterion it left unmeasured, a gap whose rows could not run, the behaviour under a gap whose "
    "rows only a test that reads source text killed, a backfilled test",
)
_EDITS = (_NO_SECOND, _SUMMARY_SAYS, _LOG_ONE, _FIELDS, _ROW_RULE, _AFRESH, _LEDGER_ROW, _SOURCE_ITEM)

_ROW_RULE_CORE = (
    "the row reads killed only when it is `KILLED` or `KILLED+others` and its `expect_red` names a test that executes "
    "the code, a name that is no part of the name, the file path or the suite or class title of a test that reads "
    "source text"
)
_ROW_RULE_SECOND_RUN = "reads as a row that reads `GREEN` does, and automate makes its second run too (the next bullet)"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _paragraph(text: str, head: str = _HEAD) -> str:
    if head not in text:
        return ""
    start = text.index(head)
    end = text.find("\n\n", start)
    return text[start : end if end != -1 else len(text)]


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start : end if end != -1 else len(text)]


def _killed_bullet(text: str) -> str:
    return next((line for line in text.splitlines() if line.startswith("- A row reads killed when it is")), "")


def _pre_edit(text: str) -> str:
    paragraph = _paragraph(text)
    if paragraph:
        text = text.replace(paragraph + "\n\n", "", 1)
    for old, new in _EDITS:
        text = text.replace(new, old, 1)
    return text


def test_the_pre_edit_text_is_a_real_reconstruction():
    live = _read(_GATE)
    pre = _pre_edit(live)
    for old, new in _EDITS:
        assert live.count(new) == 1, new[:80]
        assert pre.count(old) == 1 and new not in pre, old[:80]
    assert _HEAD not in pre and _CITED not in pre
    assert "reads source text" not in pre and "reads the source" not in pre
    assert len(live) - len(pre) == len(_paragraph(live)) + 2 + sum(len(new) - len(old) for old, new in _EDITS)
    # The confirmation paragraph is followed again by the summary paragraph.
    assert _CONFIRM_END + "\n\n" + _SUMMARY_HEAD in pre


# --- the new paragraph -------------------------------------------------------------


def _is_placed_after_the_confirmation(text: str) -> bool:
    """Once in the file, in the backfill section, right after the paragraph
    that confirms a backfill and before the one that records its rows."""
    if text.count(_HEAD) != 1:
        return False
    paragraph = _paragraph(text)
    return bool(
        _CONFIRM_END + "\n\n" + paragraph + "\n\n" + _SUMMARY_HEAD in text
        and _HEAD in _section(text, "## Backfill the gate evidence (production only)")
    )


def _defines_a_source_reading_test(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return _DEFINES in flat and _SPELLING in flat


def _reads_each_backfilled_test(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(
        _SUMMARY_FIRST in flat
        and _BEFORE_STAGING in flat
        and _READ_FORM in flat
        and flat.index(_SUMMARY_FIRST) < flat.index(_BEFORE_STAGING) < flat.index(_READ_FORM)
    )


def _commits_it_and_logs_the_behaviour(paragraph: str) -> bool:
    return _COMMIT_AND_LOG in _flat(paragraph)


def _never_closes_by_spelling(paragraph: str) -> bool:
    return _NEVER_CLOSES in _flat(paragraph)


def _names_executing_tests_apart(paragraph: str) -> bool:
    """`mutate_check.py` matches `expect_red` as a substring of a failure line,
    so an executing test named inside a spelling test's name could never count."""
    return _NAMES_APART in _flat(paragraph)


def _writes_no_second_spelling_test(text: str) -> bool:
    flat = _flat(text)
    return _NO_SECOND[1] in flat and _NO_LATER_SPELLING in _flat(_paragraph(text))


def _counts_only_an_executing_kill(text: str) -> bool:
    """The killed bullet keeps its first sentence, which the delta tests read
    as the bullet's statuses, and adds the rule after it."""
    bullet = _flat(_killed_bullet(text))
    return bool(
        bullet.startswith(_KILLED_FIRST)
        and _ROW_RULE[1] in bullet
        and _ROW_RULE_CORE in bullet
        and _ROW_RULE_SECOND_RUN in bullet
    )


def _summary_says_how_each_test_observes(text: str) -> bool:
    return _SUMMARY_SAYS[1] in _flat(_paragraph(text, _SUMMARY_HEAD))


def _logs_a_line_for_the_behaviour(text: str) -> bool:
    paragraph = _flat(_paragraph(text, "**A reported gap stays open until a later pass measures it closed.**"))
    return _LOG_ONE[1] in paragraph and _FIELDS[1] in paragraph


def _logs_it_afresh_until_executed(text: str) -> bool:
    return _AFRESH[1] in _flat(text)


def _parks_it_naming_test_and_executor(text: str) -> bool:
    flat = _flat(text)
    ledger = next((line for line in text.splitlines() if line.startswith("- `source` ∈")), "")
    return _LEDGER_ROW[1] in flat and _SOURCE_ITEM[1] in ledger


def test_the_paragraph_sits_right_after_the_confirmation():
    assert _is_placed_after_the_confirmation(_read(_GATE))


def test_locality_twin_rejects_the_paragraph_moved_out_of_the_backfill_section():
    live = _read(_GATE)
    paragraph = _paragraph(live)
    moved = live.replace(paragraph + "\n\n", "", 1)
    moved = moved.replace("## Run the gate\n", "## Run the gate\n\n" + paragraph + "\n", 1)
    assert moved != live
    assert not _is_placed_after_the_confirmation(moved)
    # Every rule still reads in the moved text: only the placement fails.
    assert _defines_a_source_reading_test(_paragraph(moved))


_PARAGRAPH_RULES = {
    "defines": _defines_a_source_reading_test,
    "reads-each-test": _reads_each_backfilled_test,
    "commits-and-logs": _commits_it_and_logs_the_behaviour,
    "never-closes": _never_closes_by_spelling,
    "names-apart": _names_executing_tests_apart,
}


@pytest.mark.parametrize("rule", sorted(_PARAGRAPH_RULES))
def test_each_rule_of_the_paragraph_holds_and_is_absent_before_the_edit(rule):
    predicate = _PARAGRAPH_RULES[rule]
    live = _read(_GATE)
    assert predicate(_paragraph(live))
    assert not predicate(_paragraph(_pre_edit(live)))


_GATE_RULES = {
    "no-second-test": _writes_no_second_spelling_test,
    "executing-kill": _counts_only_an_executing_kill,
    "summary-says": _summary_says_how_each_test_observes,
    "logs-a-line": _logs_a_line_for_the_behaviour,
    "afresh": _logs_it_afresh_until_executed,
    "ledger": _parks_it_naming_test_and_executor,
}


@pytest.mark.parametrize("rule", sorted(_GATE_RULES))
def test_each_rule_of_the_gate_holds_and_is_absent_before_the_edit(rule):
    predicate = _GATE_RULES[rule]
    live = _read(_GATE)
    assert predicate(live)
    assert not predicate(_pre_edit(live))


# One-clause mutants, each of which drops or weakens one rule.
_MUTANTS = (
    ("defines", "a file read, an `include_str!` or `include_bytes!`, a `?raw` import, Python's", "a file read, or"),
    ("defines", "reads that code's text, for example by a file read,", "reads that code's text, by a file read"),
    ("defines", "when it does not execute the code under its gap and reads", "when it reads"),
    ("defines", "its kills measure the spelling and nothing else", "its kills close the gap"),
    (
        "reads-each-test",
        "reads source text, whatever the summary says of it, and so does",
        "reads source text unless the summary says it executes the code, and so does",
    ),
    (
        "reads-each-test",
        ", and so does one that reads the gap's code by its object without naming the file, as Python's "
        "`inspect.getsource` or JavaScript's `Function.prototype.toString` (`String(fn)`, `fn.toString()`) does.",
        ".",
    ),
    ("reads-each-test", "The read forms include, among others,", "The read forms are"),
    ("reads-each-test", "`read_to_string`, `fs::read`, `include_str!`, `include_bytes!`,", "`include_str!`,"),
    ("reads-each-test", "Go's `os.ReadFile`, ", ""),
    ("reads-each-test", "stages anything, read each test the summary names too", "stages anything, trust the summary"),
    (
        "commits-and-logs",
        "and log an `unmeasured` `gate-gap:` line for the behaviour",
        "and log nothing for the behaviour",
    ),
    ("commits-and-logs", "Commit such a test with the backfill like any other", "Leave such a test unstaged"),
    ("never-closes", "ever closes that line: it closes only when", "ever closes that line alone: it closes when"),
    (
        "names-apart",
        "so that no test that reads source text has a name, a file path or a suite or class title that contains it.",
        "however it likes.",
    ),
    ("names-apart", "anywhere on a failure line, a test's file path or its suite or class title included,", "by name,"),
    (
        "names-apart",
        "has a name, a file path or a suite or class title that contains it.",
        "has a name that contains it.",
    ),
    ("reads-each-test", " or JavaScript's `Function.prototype.toString` (`String(fn)`, `fn.toString()`)", ""),
    ("no-second-test", "so no pass writes it another test that reads source text", "so a pass may write it another"),
    ("no-second-test", "and no later pass writes another test that reads source text for it.", "."),
    (
        "executing-kill",
        "only when it is `KILLED` or `KILLED+others` and its",
        "only when it is `KILLED`, `KILLED+others` or `MISATTRIBUTED` and its",
    ),
    ("executing-kill", ", a name that is no part of the name, the file path or the suite or class title of", ", of"),
    ("executing-kill", "no part of the name, the file path or the suite or class title of", "no part of the name of"),
    ("executing-kill", "and automate makes its second run too (the next bullet)", "and automate makes no second run"),
    ("summary-says", "and beside each test a row it ran names as its `expect_red`, ", ""),
    ("summary-says", "and for one that reads it, what could execute the code", "and nothing else"),
    ("logs-a-line", "Log one, too, for the behaviour under each gap", "Log none for the behaviour under each gap"),
    ("logs-a-line", ", and also names the test that reads the source and what could execute the code,", ","),
    ("logs-a-line", ", in place of an `unkilled` line for the same gap.", "."),
    ("afresh", "each pass logs it afresh, naming this commit, `unmeasured`,", "each pass copies it,"),
    (
        "afresh",
        "left unmeasured closes only when a test that executes the code kills",
        "left unmeasured closes when any test kills",
    ),
    (
        "ledger",
        "names that test in `reason`, and its `suggested_action` names what could execute the code",
        "says nothing more",
    ),
    ("ledger", "the behaviour under a gap whose rows only a test that reads source text killed, ", ""),
)


@pytest.mark.parametrize(
    ("rule", "old", "new"), [pytest.param(*m, id=f"{m[0]}-{i}") for i, m in enumerate(_MUTANTS)]
)
def test_each_rule_rejects_a_one_clause_mutant(rule, old, new):
    live = _read(_GATE)
    assert live.count(old) == 1, old
    mutant = live.replace(old, new, 1)
    assert mutant != live, "the mutant must actually change the text"
    predicate = _PARAGRAPH_RULES.get(rule)
    if predicate is not None:
        assert predicate(_paragraph(live)) and not predicate(_paragraph(mutant))
    else:
        assert _GATE_RULES[rule](live) and not _GATE_RULES[rule](mutant)


def test_the_killed_bullet_keeps_the_first_sentence_the_status_reading_takes():
    """The delta tests read each reading bullet by its first sentence, so the
    rule goes after it, never inside it."""
    bullet = _killed_bullet(_read(_GATE))
    assert bullet.split(". ")[0] + "." == _KILLED_FIRST


def test_the_new_prose_holds_no_em_dash_no_owned_and_never_the_overruled_phrase():
    live = _read(_GATE)
    added = (_paragraph(live), *(new for _, new in _EDITS))
    for piece in added:
        assert chr(0x2014) not in piece
    # Only the pre-existing owned-line sentences say "owned".
    for old, new in _EDITS:
        assert new.count("owned") == old.count("owned")
    assert "owned" not in _paragraph(live)
    fragment = _read(_FRAGMENT)
    assert chr(0x2014) not in fragment
    for text in (live, fragment, _read(_GATE_MODEL)):
        assert "open P0 gap" not in _flat(text)


def test_the_invariant_the_ledger_columns_and_the_kinds_are_unchanged():
    live = _read(_GATE)
    pre = _pre_edit(live)
    invariant = [line for line in live.splitlines() if line.startswith("**INVARIANT")]
    assert invariant == [line for line in pre.splitlines() if line.startswith("**INVARIANT")]
    header = "| id | source | severity | story | reason | suggested_action | status |"
    assert live.count(header) == pre.count(header) == 1
    kinds = sorted(set(re.findall(r"`kind` `([a-z-]+)`", live)))
    assert kinds == sorted(set(re.findall(r"`kind` `([a-z-]+)`", pre)))


# --- real mutate_check.py runs on a spelled file ------------------------------------


def _load_mutate_check():
    spec = importlib.util.spec_from_file_location("_source_reading_mutate_check", _MUTATE_CHECK)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_SPELLING_TEST = "test_panel_registers_its_close_handler"
_EXECUTING_TEST = "test_dispose_clears_the_view"


def _spelled_project(tmp_path: Path) -> Path:
    """Case 1's shape: a constructor no runner can build its host for, a test
    that reads the module's source text, and a test that executes `dispose`."""
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / "plugin.py").write_text(
        "class Panel:\n"
        "    def __init__(self, host):\n"
        "        self.view = host.workspace.create_view(\"panel\")\n"
        "        self.view.on_close(self.dispose)\n"
        "\n"
        "    def dispose(self):\n"
        "        self.view = None\n",
        encoding="utf-8",
        newline="\n",
    )
    (proj / "tests" / "test_panel_spelling.py").write_text(
        "from pathlib import Path\n\n\n"
        f"def {_SPELLING_TEST}():\n"
        "    source = Path(\"plugin.py\").read_text()\n"
        "    assert \"self.view.on_close(self.dispose)\" in source\n"
        "    assert \"self.view = None\" in source\n",
        encoding="utf-8",
        newline="\n",
    )
    (proj / "tests" / "test_dispose.py").write_text(
        "from plugin import Panel\n\n\n"
        f"def {_EXECUTING_TEST}():\n"
        "    panel = Panel.__new__(Panel)\n"
        "    panel.view = object()\n"
        "    panel.dispose()\n"
        "    assert panel.view is None\n",
        encoding="utf-8",
        newline="\n",
    )
    return proj


_STATUS_RE = re.compile(
    r"`(KILLED\+others|KILLED|MISATTRIBUTED|GREEN|STALE|NOT UNIQUE|UNDECODABLE)`(?: with the detail that ([^(.]+))?"
)


def _reads_killed(gate: str, row: dict, result: dict, spelled_files: set[str], readers: set[str]) -> bool:
    """Whether gate.md's killed bullet reads one row as a kill: its first
    sentence's statuses, then, when the bullet holds the rule for a file a
    test that reads source text reads, only an executing `expect_red`."""
    bullet = _killed_bullet(gate)
    killed = False
    for match in _STATUS_RE.finditer(bullet.split(". ")[0]):
        if match.group(1) != result["status"]:
            continue
        qualifier = match.group(2)
        if qualifier is None or qualifier.split("`")[-1].strip() in (result.get("detail") or ""):
            killed = True
    if not killed:
        return False
    if _ROW_RULE_CORE in _flat(bullet) and row["file"] in spelled_files:
        return result["status"] in ("KILLED", "KILLED+others") and not any(
            row["expect_red"] in name for name in readers
        )
    return True


def _run_rows(tmp_path: Path) -> list[tuple[dict, dict]]:
    proj = _spelled_project(tmp_path)
    command = f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests'
    rows = [
        # The behaviour's row: only the spelling test notices the mutant.
        {"file": "plugin.py", "anchor": "self.view.on_close(self.dispose)", "replacement": "pass",
         "command": command, "expect_red": _SPELLING_TEST},
        # Another row in the spelled file: an equivalent mutant, so the
        # executing test stays green while the spelling test fails.
        {"file": "plugin.py", "anchor": "self.view = None", "replacement": "self.view = (None)",
         "command": command, "expect_red": _EXECUTING_TEST},
        # A row an executing test kills, beside the spelling test.
        {"file": "plugin.py", "anchor": "self.view = None", "replacement": "pass",
         "command": command, "expect_red": _EXECUTING_TEST},
    ]
    results, _ = _load_mutate_check().run_table(rows, proj)
    return list(zip(rows, results))


def test_measured_a_spelled_row_reads_killed_and_the_gate_reads_no_kill(tmp_path):
    """Case 1 on `mutate_check.py` itself: the row the spelling test kills
    reads `KILLED`; the pre-edit bullet read that as the gap closed, the live
    one reads no kill. An `expect_red` the executing test answers to, beside
    the spelling test's failure, still reads killed."""
    (spelled, spelled_result), (other, other_result), (executed, executed_result) = _run_rows(tmp_path)
    assert spelled_result["status"] == "KILLED", spelled_result
    assert other_result["status"] == "MISATTRIBUTED", other_result
    assert "never appears beside a failure token" in other_result["detail"]
    assert executed_result["status"] == "KILLED+others", executed_result

    live, pre = _read(_GATE), _pre_edit(_read(_GATE))
    files, readers = {"plugin.py"}, {_SPELLING_TEST}
    assert _reads_killed(pre, spelled, spelled_result, files, readers)
    assert not _reads_killed(live, spelled, spelled_result, files, readers)
    # Case 2: another row in the spelled file, its executing test green.
    assert _reads_killed(pre, other, other_result, files, readers)
    assert not _reads_killed(live, other, other_result, files, readers)
    # A kill by a test that executes the code still counts.
    assert _reads_killed(live, executed, executed_result, files, readers)


# --- the field case, replayed on gate.md's own sentences ----------------------------


def _replay(gate: str, regates: int, summary_says_it_executes: bool = False) -> tuple[list[str], str]:
    """Cycle 1 measured C0 and backfilled the P0 gap with a test that reads
    `plugin.py`'s text, since no runner can build the panel's host; each later
    entry is a re-gate whose diff is empty. Returns each cycle's outcome
    (`closed`, the backfill commit, `ran` when automate ran and committed
    nothing, `skip` when it did not run) and the behaviour line's state."""
    flat = _flat(gate)
    paragraph = _flat(_paragraph(gate))
    read_check = _READ_FORM in paragraph and _BEFORE_STAGING in paragraph
    reads_source = (not summary_says_it_executes) or read_check
    rule = _ROW_RULE_CORE in _flat(_killed_bullet(gate))
    assert "When every row reads killed, the test closed the gap." in flat
    if not (rule and reads_source):
        return ["closed"], "none"
    # The rows read as `GREEN` does: the line for the behaviour is logged.
    state = "unmeasured" if _LOG_ONE[1] in flat and _FIELDS[1] in flat else "unkilled"
    no_second = _NO_SECOND[1] in flat and _NO_LATER_SPELLING in paragraph
    afresh = _AFRESH[1] in flat
    head, line_names, out = 1, 0, ["C1"]
    for _ in range(regates):
        if line_names == head:
            out.append("skip")
            continue
        # The line names another commit, so automate runs and measures it again.
        if state == "unkilled":
            out.append("ran")
            line_names = head
            continue
        if not no_second:
            # The P0 rule gives the gap a test, and the only test automate can
            # write for it is another one that reads the source.
            head += 1
            out.append(f"C{head}")
            continue
        out.append("ran")
        line_names = head
        if not afresh:
            # The generic rule logs a line whose rows can run afresh with this
            # pass's summary, which is a re-loop's finding.
            state = "summary"
    return out, state


def test_replay_carries_an_unmeasured_line_and_writes_no_second_spelling_test():
    assert _replay(_read(_GATE), 3) == (["C1", "ran", "skip", "skip"], "unmeasured")


def test_replay_reads_a_test_the_summary_calls_executing_by_its_text():
    assert _replay(_read(_GATE), 3, summary_says_it_executes=True) == (["C1", "ran", "skip", "skip"], "unmeasured")


def test_replay_on_the_pre_edit_text_closes_the_gap():
    """The mutant twin: the field failure, read off the pre-edit sentences."""
    assert _replay(_pre_edit(_read(_GATE)), 3) == (["closed"], "none")


def test_replay_without_the_read_check_trusts_a_summary_that_calls_the_test_executing():
    live = _read(_GATE)
    mutant = live.replace(_READ_FORM, "the summary decides.", 1)
    assert mutant != live
    assert _replay(mutant, 3, summary_says_it_executes=True) == (["closed"], "none")


def test_replay_without_the_no_second_test_rule_commits_a_spelling_test_at_every_regate():
    live = _read(_GATE)
    mutant = live.replace(_NO_SECOND[1], _NO_SECOND[0], 1).replace(_NO_LATER_SPELLING, ".", 1)
    assert mutant != live
    assert _replay(mutant, 3) == (["C1", "C2", "C3", "C4"], "unmeasured")


def test_replay_without_the_afresh_rule_turns_the_line_into_a_finding():
    live = _read(_GATE)
    mutant = live.replace(_AFRESH[1], _AFRESH[0], 1)
    assert mutant != live
    assert _replay(mutant, 3) == (["C1", "ran", "skip", "skip"], "summary")


# --- the docs and the fragment -------------------------------------------------------

_GATE_MODEL_SAYS = (
    "A test that reads the code's source text instead of executing it, where no test runner can execute that code, "
    "measures only its spelling: the behaviour stays an `unmeasured` gap naming the test and what could execute the "
    "code, and no test that reads source text closes it."
)


def test_the_gate_model_says_a_spelling_test_closes_nothing():
    assert _GATE_MODEL_SAYS in _flat(_read(_GATE_MODEL))


_FRAGMENT_SAYS = (
    "type: fixed",
    "scope: ultracode-goal",
    "issues: [239]",
    "a test that only reads that code's source text",
    "Such a test now measures the spelling only",
    "it is still committed with the backfill",
    "an `unmeasured` `gate-gap:` line for the behaviour that names the test and what could execute the code",
    "Automate's summary says beside each test whether it executes the code or reads its source text",
    "`fs::read`",
    "JavaScript's `Function.prototype.toString`",
    "automate is told to name each test that executes the code so that no test that reads source text has a name, a "
    "file path or a suite or class title that contains it",
    "the gate also reads each backfilled test",
    "counts as killed only as `KILLED` or `KILLED+others` with an `expect_red` that names a test that executes the "
    "code",
    "no later pass writes another such test for it",
    "Each pass logs the line afresh at its own commit",
    "whose reason names the test and whose suggested action names what could execute the code",
)


def test_the_fragment_says_what_the_prose_does():
    fragment = _flat(_read(_FRAGMENT))
    assert [s for s in _FRAGMENT_SAYS if s not in fragment] == []

