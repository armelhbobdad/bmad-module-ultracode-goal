#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Every script in scripts/ carries a PEP 723 `# /// script` header.

The stage references run each script as `uv run {skill-root}/scripts/<name>.py`
from inside the user's project. Without the header, uv treats the script as
part of whatever project encloses the installed skill and sets that project up
first, which fails when the project's own dependencies do not resolve. With the
header, uv builds the script's environment from the header alone.
mutate_check.py was the one script without it (issue #158), and runs fell back
to `uv run --no-project`. test_mutate_check.py drives that case for real.

Scanned: the top-level scripts and the two hooks, which the hook commands in
.claude/settings.local.json also start with `uv run`. Not scanned: lib/, whose
module is imported, and tests/. The value of requires-python is checked by
tools/tool-requirements.js against the Python minimum, so it is only required
here.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]

# The reference regular expression of PEP 723 (Inline script metadata).
_BLOCK = re.compile(r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$")

SCRIPT_FILES = sorted([*_SCRIPTS.glob("*.py"), *(_SCRIPTS / "hooks").glob("*.py")])


def _script_metadata(text: str) -> dict | None:
    """The parsed `script` block, the way PEP 723's reference reader does it.

    None when there is no block. More than one is an error under the PEP, so
    that is None too.
    """
    blocks = [match for match in _BLOCK.finditer(text) if match.group("type") == "script"]
    if len(blocks) != 1:
        return None
    content = "".join(
        line[2:] if line.startswith("# ") else line[1:]
        for line in blocks[0].group("content").splitlines(keepends=True)
    )
    return tomllib.loads(content)


def test_the_scan_sees_the_scripts():
    names = {path.name for path in SCRIPT_FILES}
    assert {"mutate_check.py", "gate_eval.py", "preflight_check.py", "guard_pretooluse.py"} <= names


@pytest.mark.parametrize("script", SCRIPT_FILES, ids=lambda path: path.name)
def test_every_script_has_a_pep_723_header(script):
    metadata = _script_metadata(script.read_text(encoding="utf-8"))
    assert metadata is not None, (
        f"{script.name} has no `# /// script` block, so `uv run` sets up the "
        "enclosing project before it runs the script"
    )
    assert isinstance(metadata.get("requires-python"), str), script.name
    assert isinstance(metadata.get("dependencies", []), list), script.name


def test_the_reader_refuses_a_file_without_a_block():
    assert _script_metadata('#!/usr/bin/env python3\n"""No header."""\n') is None
    assert _script_metadata(
        '"""A docstring that quotes one:\n# /// script\n# requires-python = ">=3.11"\n"""\n'
    ) is None
