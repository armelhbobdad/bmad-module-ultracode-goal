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

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_FINALIZE = _SKILL_ROOT / "references" / "finalize.md"
_DRIVER = _SKILL_ROOT / "scripts" / "drive_epic.py"


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
    "cites the false-double-claim that motivated it": lambda s: bool(
        re.search(r"REQ-1", s)
    ),
}


def _unmet(section: str) -> list[str]:
    return sorted(name for name, check in _CHECKS.items() if not check(section))


def test_execute_states_the_decomposition_route():
    assert _unmet(_sizing_section()) == []


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


def test_the_two_handoff_kinds_agree_with_the_driver():
    """The doc and the driver must name the SAME kinds, or the branch never fires."""
    text = _EXECUTE.read_text(encoding="utf-8")
    driver = _DRIVER.read_text(encoding="utf-8")
    documented = {k for k in ("story-decomposed", "defined-not-driven") if f'"{k}"' in text}
    in_driver = set(re.findall(r'"(story-decomposed|defined-not-driven)"', driver))
    assert documented == in_driver == {"story-decomposed", "defined-not-driven"}


def test_finalize_names_the_handoff_as_a_terminal_route():
    text = _FINALIZE.read_text(encoding="utf-8")
    assert re.search(r"advanced \*\*no row at all\*\*", text)
    assert re.search(r"reached by one of five routes", text), (
        "the route count must move with the route, or the enumeration lies"
    )
    # And the trap: it resembles the work bound but emits the other status.
    assert re.search(r"a handoff took \*\*zero\*\*", text)
