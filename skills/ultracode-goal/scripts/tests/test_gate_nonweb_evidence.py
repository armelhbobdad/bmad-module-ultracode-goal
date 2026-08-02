"""Gate: what the non-web author owes, on the path where TEA cannot help.

The non-web-stack section makes the run responsible for four artifacts TEA would
otherwise produce. Two gaps, both filed from real runs:

  - It pinned per-story names for two of the four and left the other two unnamed,
    so each story's NFR and review overwrote the previous story's in the shared
    trace directory. The `--nfr` / `--test-review` flags take an explicit path,
    so nothing mechanical was ever going to catch it.

  - It ruled the artifacts thoroughly and ruled the acceptance-test BAR
    ("un-skipped and passing"), and said nothing at all about how un-skipped is
    reached from a red start - `grep -i "red.phase" references/gate.md` returned
    zero hits across the whole file. So a run that skipped the red phase entirely
    satisfied every sentence in the section, on the one path where the browser
    generator that normally creates the skips cannot run.

Scoped to the non-web section: a check that searched the whole file would pass on
prose living anywhere, and `references/define-done.md` legitimately discusses the
red phase elsewhere.

Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_GATE = _SKILL_ROOT / "references" / "gate.md"


def _nonweb_section(text: str | None = None) -> str:
    text = text if text is not None else _GATE.read_text(encoding="utf-8")
    start = text.index("## Non-web stack")
    return text[start : text.index("\n## ", start + 1)]


_CHECKS = {
    "names all four artifacts, not two": lambda s: bool(
        re.search(r"Name all four for the story", s)
    ),
    "gives the per-story name for the NFR": lambda s: "nfr-assessment-<id>.md" in s,
    "gives the per-story name for the review": lambda s: "test-review-<id>.md" in s,
    "says why the second pair needs naming anyway": lambda s: bool(
        re.search(r"binds nothing mechanically", s)
    ),
    "names the consequence of leaving them unnamed": lambda s: bool(
        re.search(r"overwrite the last one's", s)
    ),
    "requires the red phase to be established by hand": lambda s: bool(
        re.search(r"red phase is established BY HAND", s)
    ),
    "orders the red run BEFORE the first implementation edit": lambda s: bool(
        re.search(r"RUN them before the first implementation edit", s, re.I)
    ),
    "requires the red output be captured to a file": lambda s: bool(
        re.search(r"capture that run's raw output to a file", s, re.I)
    ),
    "requires a justification for each already-green case": lambda s: bool(
        re.search(r"justification for every case that was already green", s, re.I)
    ),
    "says why the gap existed: every other sentence is satisfiable without it": lambda s: bool(
        re.search(r"skipped the red phase entirely satisfies every other sentence", s, re.I)
    ),
    "states the honesty bar in one line": lambda s: bool(
        re.search(r"A case nobody ever saw fail is not evidence", s)
    ),
}


def _unmet(section: str) -> list[str]:
    return sorted(name for name, check in _CHECKS.items() if not check(section))


def test_the_non_web_section_states_both_obligations():
    assert _unmet(_nonweb_section()) == []


def test_the_checks_are_scoped_to_the_non_web_section():
    """Locality: emptying the section must red every check.

    Without this they are file-wide greps, and `references/define-done.md`
    discusses the red phase legitimately elsewhere - so a file-wide check could
    be satisfied by text that has nothing to do with this path.
    """
    text = _GATE.read_text(encoding="utf-8")
    emptied = text.replace(_nonweb_section(), "## Non-web stack (emptied)\n\n")
    assert sorted(_unmet(emptied)) == sorted(_CHECKS)


def test_the_worked_example_agrees_with_the_naming_rule():
    """A rule contradicted by the example beside it is a rule nobody follows."""
    section = _nonweb_section()
    invocation = next(
        ln for ln in section.splitlines() if "--nfr <" in ln or "--nfr …" in ln
    )
    assert "nfr-assessment-<story_id>.md" in invocation, (
        "the flag sketch still shows an unnamed NFR path while the rule above "
        "requires a per-story one"
    )
    assert "test-review-<story_id>.md" in invocation


def test_the_red_phase_rule_sits_on_the_production_path():
    """`--light` reads neither file, so the rule belongs with the production ANDs.

    Placed under the `--light` discussion it would bind the profile that does not
    need it and miss the one that does.
    """
    section = _nonweb_section()
    assert section.index("Under **production**") < section.index("red phase is established BY HAND")
