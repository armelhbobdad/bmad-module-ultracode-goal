#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""docs/architecture.md lists every script the skill ships.

The docs site's file layout gives each script under `scripts/` a line of its
own, beside what it does. probe_servers.py (#182) shipped without one, as
link_worktree_deps.py had before it, so a reader of the layout could not find
the script the gate runs to check for a server a test runner would reuse.

Read: the top-level scripts, lib/ and the two hooks, against the lines of the
layout's `scripts/` tree. Not read: tests/.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
_ARCHITECTURE = _SCRIPTS.parents[2] / "docs" / "architecture.md"

SHIPPED = sorted(
    path.relative_to(_SCRIPTS).as_posix()
    for path in [*_SCRIPTS.glob("*.py"), *(_SCRIPTS / "lib").glob("*.py"), *(_SCRIPTS / "hooks").glob("*.py")]
)


def _listed(layout: str) -> set[str]:
    """The scripts the layout's `scripts/` tree lists: each entry under it
    until the tree goes back to the skill's level, by its path below
    `scripts/` (a hook's under `hooks/`)."""
    lines = layout.splitlines()
    start = next((i for i, line in enumerate(lines) if re.search(r"── scripts/\s", line)), None)
    if start is None:
        return set()
    listed, folder = set(), ""
    for line in lines[start + 1 :]:
        entry = re.match(r"^│   ( *)(?:[│ ]   )*[├└]── (\S+)", line)
        if entry is None:
            break
        name = entry.group(2)
        depth = (len(line) - len(line.lstrip("│ "))) // 4
        if name.endswith("/"):
            folder = name
        elif name.endswith(".py"):
            listed.add(folder + name if depth > 1 else name)
    return listed


def _layout() -> str:
    return _ARCHITECTURE.read_text(encoding="utf-8")


def test_the_scan_sees_the_scripts():
    assert {"mutate_check.py", "probe_servers.py", "lib/mem_common.py", "hooks/guard_pretooluse.py"} <= set(SHIPPED)
    assert {"mutate_check.py", "lib/mem_common.py", "hooks/budget_stop.py"} <= _listed(_layout())


@pytest.mark.parametrize("script", SHIPPED)
def test_the_architecture_layout_lists_every_script(script):
    assert script in _listed(_layout()), f"docs/architecture.md's scripts/ tree has no line for {script}"


@pytest.mark.parametrize("script", ["probe_servers.py", "link_worktree_deps.py", "hooks/budget_stop.py"])
def test_layout_reader_misses_a_dropped_line(script):
    """The twin: a layout without a script's line does not list it."""
    layout = _layout()
    name = script.rsplit("/", 1)[-1]
    mutant = "\n".join(line for line in layout.splitlines() if f"── {name} " not in line)
    assert mutant != layout, "the mutant must actually change the text"
    assert script not in _listed(mutant)
    assert script in _listed(layout)
