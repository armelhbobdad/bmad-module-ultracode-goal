"""Registration surface for the nested ucg-resolve skill.

A skill can ship, pass `validate-skills` (which walks skill dirs and never reads the
CSV), and still be invisible to the help catalog. These two tests close that gap: the
first pins the row's shape and a unique menu code, the second pins the set-equality
that makes a shipped-but-unregistered skill (or a registered-but-unshipped row) fail.

Stdlib + pytest only.
"""

import csv
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_HELP_CSV = _SKILL_ROOT / "assets" / "module-help.csv"
# The three ucg-* entry points are SIBLINGS of the parent module, not children of
# it. They shipped nested until the IDE loader was found to enumerate one level
# only, which left every one of them unreachable as a slash command.
_SIBLING_SKILLS_DIR = _SKILL_ROOT.parent

_MODULE = "UltraCode Goal"
_PARENT_SKILL = "ultracode-goal"
_EXPECTED_COLUMNS = 13


def _rows() -> tuple[list[str], list[list[str]]]:
    with _HELP_CSV.open(encoding="utf-8", newline="") as handle:
        parsed = list(csv.reader(handle))
    assert parsed, "help catalog is empty"
    return parsed[0], [r for r in parsed[1:] if r]


def test_help_csv_row_is_13col_with_fresh_menu_code():
    header, data = _rows()
    assert len(header) == _EXPECTED_COLUMNS, (
        "help catalog header must be %d columns, got %d" % (_EXPECTED_COLUMNS, len(header))
    )
    skill_col = header.index("skill")
    menu_col = header.index("menu-code")

    matches = [r for r in data if r[skill_col] == "ucg-resolve"]
    assert len(matches) == 1, "exactly one `ucg-resolve` row expected, got %d" % len(matches)
    row = matches[0]

    assert len(row) == _EXPECTED_COLUMNS, (
        "the `ucg-resolve` row must have %d fields, got %d" % (_EXPECTED_COLUMNS, len(row))
    )
    assert row[header.index("module")] == _MODULE, "row must belong to the module"

    # the menu code is non-empty and unique across EVERY data row in the file
    codes = [r[menu_col] for r in data]
    assert row[menu_col], "the `ucg-resolve` row must carry a menu code"
    assert codes.count(row[menu_col]) == 1, (
        "menu code %r collides with another row" % row[menu_col]
    )
    assert len(codes) == len(set(codes)), "menu codes must be unique: %s" % codes


def test_every_shipped_nested_skill_has_a_help_row():
    """Twin: shipping the SKILL.md while deleting its CSV row leaves the skill invisible
    to the help catalog and still green under `validate-skills`. Set-equality catches it
    in both directions."""
    header, data = _rows()
    skill_col = header.index("skill")

    shipped = {
        d.name
        for d in _SIBLING_SKILLS_DIR.iterdir()
        if d.is_dir()
        and d.name != _PARENT_SKILL
        and d.name.startswith("ucg-")
        and (d / "SKILL.md").is_file()
    }
    registered = {r[skill_col] for r in data} - {_PARENT_SKILL}

    assert shipped, "no ucg-* companion skills discovered"
    assert shipped == registered, (
        "shipped nested skills and help-catalog rows diverged: "
        "shipped-but-unregistered=%s, registered-but-unshipped=%s"
        % (sorted(shipped - registered), sorted(registered - shipped))
    )
