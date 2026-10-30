"""Execute: the route for a row that is well-formed and too large to drive.

Filed four separate times against one Epic, which took the decomposition path
SEVEN times and re-derived the reasoning from scratch on each, because the stage
file described no such route. Both of the routes it did offer are wrong for this
case: driving the row reaches the turn bound with markers on disk and no commit,
and escalating reaches the same conclusion having first spent the whole budget
proving what an AC count showed in five minutes.

The conventions pinned here are PROPERTIES OF THE SHIPPED DRIVER, not taste, and
`test_drive_epic.py` exercises the driver side. They are asserted as prose here
because a run reads this file, not the driver.

Stdlib + pytest only.
"""

import ast
import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_FINALIZE = _SKILL_ROOT / "references" / "finalize.md"
_GATE = _SKILL_ROOT / "references" / "gate.md"
_DRIVER = _SKILL_ROOT / "scripts" / "drive_epic.py"
_PREFLIGHT_CHECK = _SKILL_ROOT / "scripts" / "preflight_check.py"


def _sizing_section() -> str:
    text = _EXECUTE.read_text(encoding="utf-8")
    start = text.index("### Sizing: a story too large to drive")
    return text[start : text.index("\n### ", start + 1)]


_CHECKS = {
    "sizes the row BEFORE step 0 writes a marker": lambda s: bool(
        re.search(r"[Bb]efore step 0 writes any marker", s)
    ),
    "names what to count": lambda s: bool(
        re.search(r"acceptance criteria and tasks", s, re.I)
    ),
    # Scoped to the sizing sentence, not a bare mention: the placeholder also
    # appears in the /goal condition and the work bound, so a file-wide check
    # for it passes on a file with no sizing rule at all.
    "keys the threshold on the turn ceiling": lambda s: bool(
        re.search(r"implausible against `\{workflow\.max_turns_per_story\}`", s)
    ),
    # The threshold reads the criteria alone. Criteria plus tasks flagged 25 of
    # one real Epic's 30 rows and 4 of another's 5, nearly all then driven whole,
    # so nearly every row cost a recorded override.
    "counts criteria, not criteria plus tasks, for the threshold": lambda s: bool(
        re.search(
            r"acceptance-criteria count reaches roughly half of `\{workflow\.max_turns_per_story\}`",
            s,
        )
    ),
    "keeps the tasks out of the threshold": lambda s: bool(
        re.search(r"keep them out of the threshold", s)
    ),
    # The Stop hook counts responses, so the turn count follows how a drive
    # waits. A threshold justified as a turn forecast is justified by a count
    # the hook does not keep.
    "says the threshold is not a turn forecast": lambda s: bool(
        re.search(r"not a forecast of turns", s)
    ),
    # The turns come from the count the gate logged, never the live counter:
    # a /ucg-resolve close resets or deletes `.budget-<story_id>.json`, and a
    # later session's responses keep landing on the last story `.current-story`
    # named, so one real Epic's files read 11 and 12 for rows logged at 7 and 9,
    # and 1 for a row that escalated at 25.
    "the tie-break reads the turns each driven row used": lambda s: bool(
        re.search(
            r"with the turns each one used as `\.decision-log\.md` logged them beside the verdict that advanced it",
            s,
        )
    ),
    "the tie-break never reads the turns from the live counter": lambda s: bool(
        re.search(r"Read those turns from the log, never from the row's `\.budget-<story_id>\.json`", s)
        and re.search(r"`/ucg-resolve` resets or deletes that file", s)
        and re.search(r"adds each response of a later session to the story `\.current-story` still names", s)
    ),
    # The sizing call's keys as `story_sizing.py` prints them: the ratio is the
    # criteria over the ceiling, and the summed `load` is gone.
    "says the sizing call's ratio is the criteria over the ceiling": lambda s: bool(
        re.search(r"returning `ratio` \(the criteria count over the ceiling\)", s)
    ),
    "says do not start the story": lambda s: bool(re.search(r"do not start the story", s, re.I)),
    "calls decomposition a legitimate terminal": lambda s: bool(
        re.search(r"legitimate terminal for an invocation", s, re.I)
    ),
    "states that no marker is written": lambda s: bool(
        re.search(r"writes no baseline and no tests-ran marker", s, re.I)
    ),
    "orders children BEFORE the parent row": lambda s: bool(
        re.search(r"child rows BEFORE the parent row", s)
    ),
    "explains the row-order rule by pending\\[0\\] in FILE order": lambda s: bool(
        re.search(r"first not-`done` row in FILE order", s)
    ),
    "names the no-progress halt that results": lambda s: bool(
        re.search(r"halts with `no-progress`", s)
    ),
    "requires the parent row be set done": lambda s: bool(
        re.search(r"[Ss]et the parent row to `done`", s)
    ),
    "forbids editing the parent story file": lambda s: bool(
        re.search(r"[Dd]o not edit the parent story file", s)
    ),
    "says why: a second copy of the contract": lambda s: bool(
        re.search(r"second copy of the contract", s, re.I)
    ),
    "requires the AC mapping be checked mechanically": lambda s: bool(
        re.search(r"[Cc]heck that mapping mechanically", s)
    ),
    # The word alone was satisfiable by prose, and was: the section demanded a
    # mechanical check while the module shipped no tool to do it, so every
    # decomposition improvised a parser and one of them reported two false
    # double-claims. Naming the script is what makes the demand answerable.
    "names the script that performs the mechanical check": lambda s: bool(
        re.search(r"story_sizing\.py", s)
    ),
    "states that a failing check blocks the split": lambda s: bool(
        re.search(r"fixed before the child rows are written", s, re.I)
    ),
    "cites the false-double-claim that motivated it": lambda s: bool(
        re.search(r"REQ-1", s)
    ),
}


def _unmet(section: str) -> list[str]:
    return sorted(name for name, check in _CHECKS.items() if not check(section))


def test_execute_states_the_decomposition_route():
    assert _unmet(_sizing_section()) == []


def test_the_sizing_rule_claims_no_turn_per_criterion():
    """The hook counts one turn per response, whatever the response did, so a
    rule that sizes on "a turn or more per acceptance criterion" sizes on a cost
    nothing measures: drives of 9 and 13 criteria took 6 and 7 turns, and a
    3-criterion row driven step by step passed the ceiling twice over."""
    text = _EXECUTE.read_text(encoding="utf-8")
    assert "a turn or more per acceptance criterion" not in text
    assert "AC count plus task count" not in text
    assert "`load`" not in text


_TIE_BREAK_SOURCE = (
    "with the turns each one used as `.decision-log.md` logged them beside the verdict that advanced it "
    '(its turn-budget outcome, "Record" below), versus rows already split;'
)
_LIVE_COUNTER = " Read those turns from the log, never from the row's `.budget-<story_id>.json`:"
_NO_COUNT = "A row the log gives no count for offers its criteria count alone."


def test_the_tie_break_checks_reject_the_live_counter_as_the_source():
    """The branch first pointed the tie-break at `.budget-<story_id>.json`,
    which a close resets and a later session inflates; both turn checks must
    fail on that text."""
    section = _sizing_section()
    assert "(`turns` in its `.budget-<story_id>.json`)" not in section
    start, end = section.index(_LIVE_COUNTER), section.index(_NO_COUNT) + len(_NO_COUNT)
    mutant = (section[:start] + section[end:]).replace(
        _TIE_BREAK_SOURCE,
        "with the turns each one used (`turns` in its `.budget-<story_id>.json`), versus rows already split;",
    )
    assert _TIE_BREAK_SOURCE in section and _TIE_BREAK_SOURCE not in mutant
    unmet = _unmet(mutant)
    assert "the tie-break reads the turns each driven row used" in unmet
    assert "the tie-break never reads the turns from the live counter" in unmet


_RECORD_TURNS = (
    "per-story turn-budget outcomes (beside each gate verdict, the story's `turns` from its "
    "`.budget-<story_id>.json` against `{workflow.max_turns_per_story}`, which the sizing tie-break reads back "
    "once the story is driven)"
)


def _record_logs_the_turns(text: str) -> bool:
    start = text.index("\n## Record\n")
    section = re.sub(r"\s+", " ", text[start : text.index("\n## ", start + 1)])
    return _RECORD_TURNS in section


def test_the_record_logs_the_count_the_tie_break_reads():
    """The tie-break reads a driven row's turns from the log, so the log must
    hold them, written beside the verdict while the story's counter is its own."""
    text = _EXECUTE.read_text(encoding="utf-8")
    assert _record_logs_the_turns(text)
    # Twin: the bare list item the branch shipped, which says nothing of when
    # or what the turn-budget outcome is.
    mutant = text.replace(_RECORD_TURNS, "per-story turn-budget outcomes", 1)
    assert mutant != text
    assert not _record_logs_the_turns(mutant)


def test_the_route_precedes_the_loop_it_is_an_alternative_to():
    """A sizing rule placed after the loop is a rule nobody reaches in time."""
    text = _EXECUTE.read_text(encoding="utf-8")
    assert text.index("### Sizing: a story too large to drive") < text.index("\n0. "), (
        "the sizing section must come before step 0"
    )


def test_the_checks_are_anchored_to_the_sizing_section():
    """Locality: the same words elsewhere in the file must not satisfy them.

    Without this the checks are file-wide greps, and prose relocated out of the
    section would keep them green - the defect found in the previous batch.
    """
    text = _EXECUTE.read_text(encoding="utf-8")
    section = _sizing_section()
    without = text.replace(section, "### Sizing: a story too large to drive\n\n")
    assert sorted(_unmet(without)) == sorted(_CHECKS), (
        "these checks pass on a file whose sizing section was emptied, so they "
        "are searching the wrong text"
    )


def test_the_terminal_is_representable_and_named():
    """Durable work with no row advanced must be sayable, not improvised."""
    text = _EXECUTE.read_text(encoding="utf-8")
    assert re.search(r"durable work and advanced no row", text, re.I)
    for kind in ('"story-decomposed"', '"defined-not-driven"'):
        assert kind in text, f"the sidecar kind {kind} is not named"
    # It is `blocked`, and the reason it cannot be `complete` is stated.
    assert re.search(r"no story reached a Stage-5 verdict", text)
    assert re.search(r"indistinguishable in the envelope from a run that drove", text, re.I)


def _driver_handoff_kinds() -> set[str]:
    """The driver's `HANDOFF_KINDS`, read from its source rather than from a list here.

    A list written in this file passed while the driver gained a kind the doc
    never named: the regex only looked for the kinds it already knew.
    """
    tree = ast.parse(_DRIVER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "HANDOFF_KINDS" for t in node.targets
        ):
            call = node.value
            assert isinstance(call, ast.Call) and call.func.id == "frozenset"
            return set(ast.literal_eval(call.args[0]))
    raise AssertionError("drive_epic.py defines no HANDOFF_KINDS")


def test_the_handoff_kinds_agree_with_the_driver():
    """The doc and the driver must name the SAME kinds, or the branch never fires."""
    text = _EXECUTE.read_text(encoding="utf-8")
    in_driver = _driver_handoff_kinds()
    assert in_driver == {"story-decomposed", "defined-not-driven", "operator-evidence-owed"}
    undocumented = sorted(k for k in in_driver if not re.search(rf"[`\"]{re.escape(k)}[`\"]", text))
    assert undocumented == [], f"execute.md does not name the handoff kind(s) {undocumented}"
    # The gate writes the third kind, so the gate names it too.
    assert "`operator-evidence-owed`" in _GATE.read_text(encoding="utf-8")


def test_a_resume_stops_on_every_open_sidecar_but_the_two_handoffs():
    """The resume manifest routes the two handoffs whose work the next
    invocation picks up (`story-decomposed`, `defined-not-driven`) as `handoff`,
    and every other open sidecar as `decision-pending`. `operator-evidence-owed`
    is a handoff to the driver, but not to a resume: re-driving the story cannot
    record the evidence an operator owes, so the resume stops until
    `/ucg-resolve` closes it."""
    manifest = _PREFLIGHT_CHECK.read_text(encoding="utf-8")
    exempt = set(re.findall(r'"(story-decomposed|defined-not-driven|operator-evidence-owed)"', manifest))
    assert exempt == {"story-decomposed", "defined-not-driven"}
    assert exempt < _driver_handoff_kinds()


def test_finalize_names_the_handoff_as_a_terminal_route():
    text = _FINALIZE.read_text(encoding="utf-8")
    assert re.search(r"advanced \*\*no row at all\*\*", text)
    assert re.search(r"reached by one of five routes", text), (
        "the route count must move with the route, or the enumeration lies"
    )
    # And the trap: it resembles the work bound but emits the other status.
    assert re.search(r"a handoff took \*\*zero\*\*", text)
