#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for mutate_check.py - the tracked mutation runner.

Driven as a subprocess (the surface a run uses), against a tiny fake project:
one source file and a checker script whose failure output carries pytest-shaped
counts, so attribution and the exactly-one claim are both exercised for real.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "mutate_check.py"

CODE = 'LIMIT = 5\nFLAG = "on"\n'

# Two named observers; prints "<n> failed: <names>" on red, pytest-count shaped.
CHECKER = """\
import sys
text = open("code.py", encoding="utf-8").read()
failures = []
if "LIMIT = 5" not in text:
    failures.append("test_limit_pinned")
if 'FLAG = "on"' not in text:
    failures.append("test_flag_on")
if failures:
    print(f"{len(failures)} failed:", ", ".join(failures))
    sys.exit(1)
print("all green")
"""

COMMAND = f'"{sys.executable}" check.py'


def _project(tmp_path: Path, code: str = CODE) -> Path:
    # newline="\n" is load-bearing: without it Windows translates \n to \r\n
    # on write while mutate_check reads BYTES, so every multi-line anchor
    # misses and the whole suite reds on the windows-latest CI matrix.
    (tmp_path / "code.py").write_text(code, encoding="utf-8", newline="\n")
    (tmp_path / "check.py").write_text(CHECKER, encoding="utf-8", newline="\n")
    return tmp_path


def _row(**overrides) -> dict:
    row = {
        "file": "code.py",
        "anchor": "LIMIT = 5",
        "replacement": "LIMIT = 6",
        "command": COMMAND,
        "expect_red": "test_limit_pinned",
    }
    row.update(overrides)
    return row


def _run_table(project: Path, rows: list[dict]):
    table = project / "table.json"
    table.write_text(json.dumps(rows), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--table", str(table), "--project-root", str(project)],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc


def test_killed_attributable_row_exits_zero(tmp_path):
    project = _project(tmp_path)
    proc = _run_table(project, [_row()])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "| KILLED |" in proc.stdout
    assert "exactly 'test_limit_pinned' went red" in proc.stdout


def test_restore_verified_byte_identical(tmp_path):
    project = _project(tmp_path)
    before = (project / "code.py").read_bytes()
    proc = _run_table(project, [_row()])
    assert proc.returncode == 0
    assert (project / "code.py").read_bytes() == before
    assert "| verified |" in proc.stdout


def test_green_survivor_is_a_finding_and_leads_the_ledger(tmp_path):
    project = _project(tmp_path)
    survivor = _row(replacement="LIMIT = 5  # tweaked", expect_red="test_limit_pinned")
    proc = _run_table(project, [_row(), survivor])
    assert proc.returncode == 1
    assert "1 GREEN (survived)" in proc.stdout
    # Greens lead: the GREEN row renders before the KILLED row.
    assert proc.stdout.index("| GREEN |") < proc.stdout.index("| KILLED |")
    assert "SURVIVED" in proc.stdout


def test_misattributed_red_is_a_finding(tmp_path):
    """Something failed, but not the observer the row claims to test."""
    project = _project(tmp_path)
    proc = _run_table(project, [_row(expect_red="test_flag_on")])
    assert proc.returncode == 1
    assert "| MISATTRIBUTED |" in proc.stdout


def test_multi_case_red_is_killed_with_others_surfaced(tmp_path):
    """A mutation that reds several cases still kills, and the extra reds are
    surfaced rather than silently absorbed (the measured run had a mutation red
    four cases with only one intended observer)."""
    project = _project(tmp_path)
    row = _row(
        anchor='LIMIT = 5\nFLAG = "on"',
        replacement='LIMIT = 6\nFLAG = "off"',
        expect_red="test_limit_pinned",
    )
    proc = _run_table(project, [row])
    assert proc.returncode == 0
    assert "| KILLED+others |" in proc.stdout
    assert "among 2 failures" in proc.stdout


def test_stale_anchor_reported_distinctly(tmp_path):
    """0 occurrences is the formatter-reflow signature, named as such."""
    project = _project(tmp_path)
    proc = _run_table(project, [_row(anchor="LIMIT = 5  # long gone")])
    assert proc.returncode == 1
    assert "| STALE |" in proc.stdout
    assert "formatter-reflow" in proc.stdout


def test_duplicate_anchor_refused_per_row(tmp_path):
    project = _project(tmp_path, code='LIMIT = 5\nLIMIT = 5\nFLAG = "on"\n')
    proc = _run_table(project, [_row()])
    assert proc.returncode == 1
    assert "| NOT UNIQUE |" in proc.stdout
    # Nothing was mutated for that row, so nothing needed restoring.
    assert (project / "code.py").read_text(encoding="utf-8") == 'LIMIT = 5\nLIMIT = 5\nFLAG = "on"\n' 


def test_red_baseline_refuses_the_whole_table(tmp_path):
    project = _project(tmp_path, code="LIMIT = 4\n")
    before = (project / "code.py").read_bytes()
    proc = _run_table(project, [_row()])
    assert proc.returncode == 2
    assert "baseline is not green" in proc.stderr
    # Refused BEFORE mutating: the file is untouched and no ledger was printed.
    assert (project / "code.py").read_bytes() == before
    assert "Mutation ledger" not in proc.stdout


def test_invalid_table_refused(tmp_path):
    project = _project(tmp_path)
    proc = _run_table(project, [{"file": "code.py", "anchor": "LIMIT = 5"}])
    assert proc.returncode == 2
    assert "missing required string key" in proc.stderr


def test_identical_anchor_and_replacement_refused(tmp_path):
    project = _project(tmp_path)
    proc = _run_table(project, [_row(replacement="LIMIT = 5")])
    assert proc.returncode == 2
    assert "mutates nothing" in proc.stderr


def test_restore_wins_even_when_the_command_edits_the_target(tmp_path):
    """A checker that rewrites the file under test must not defeat the backup."""
    project = _project(tmp_path)
    (project / "check.py").write_text(
        CHECKER.replace(
            'print("all green")',
            # Binary append: a text-mode "a" would translate \n to \r\n on
            # Windows and break the byte-exact expectation below.
            'open("code.py", "ab").write(b"# scribble\\n")\n'
            'print("all green")',
        ),
        encoding="utf-8",
        newline="\n",
    )
    before = (project / "code.py").read_bytes()
    proc = _run_table(
        project, [_row(replacement="LIMIT = 5  # survive", expect_red="test_limit_pinned")]
    )
    # The survivor exit (1) is incidental; the property is the restore. The
    # BASELINE run scribbles once before the row's backup is taken, so the
    # restored state is before-plus-one-scribble: the row's own scribble (made
    # against the mutated file) was rolled back, the baseline's was not.
    assert proc.returncode == 1
    assert (project / "code.py").read_bytes() == before + b"# scribble\n"


def test_ledger_written_to_output_path_too(tmp_path):
    project = _project(tmp_path)
    table = project / "table.json"
    table.write_text(json.dumps([_row()]), encoding="utf-8")
    out = project / "ledger.md"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--table", str(table),
         "--project-root", str(project), "--output", str(out)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0
    content = out.read_text(encoding="utf-8")
    # print() adds one newline to the ledger string; the file carries it bare.
    assert content.rstrip("\n") == proc.stdout.rstrip("\n")
    assert "| KILLED |" in content


def _custom_checker(project: Path, body: str) -> None:
    (project / "check.py").write_text(body, encoding="utf-8", newline="\n")


VERBOSE_CHECKER = """\
import sys
text = open("code.py", encoding="utf-8").read()
limit_ok = "LIMIT = 5" in text
flag_ok = 'FLAG = "on"' in text
print("test_limit_pinned PASSED" if limit_ok else "test_limit_pinned FAILED")
print("test_flag_on PASSED" if flag_ok else "test_flag_on FAILED")
if not (limit_ok and flag_ok):
    failed = int(not limit_ok) + int(not flag_ok)
    print(f"{failed} failed, {2 - failed} passed")
    sys.exit(1)
print("all green")
"""


def test_verbose_reporter_cannot_launder_attribution(tmp_path):
    """A reporter that echoes PASSING names (the pytest -v shape) must not turn
    a wrong-observer kill into a clean one: the mutation breaks only the FLAG
    observer while the row claims the LIMIT one, and the LIMIT name appears in
    the output - on a PASSED line."""
    project = _project(tmp_path)
    _custom_checker(project, VERBOSE_CHECKER)
    row = _row(
        anchor='FLAG = "on"',
        replacement='FLAG = "off"',
        expect_red="test_limit_pinned",
    )
    proc = _run_table(project, [row])
    assert proc.returncode == 1
    assert "| MISATTRIBUTED |" in proc.stdout
    assert "beside a failure token" in proc.stdout


def test_zero_count_red_is_not_a_kill(tmp_path):
    """A red exit whose own summary counts zero failures (a collection error
    wearing a red exit code) must not satisfy the twin contract."""
    project = _project(tmp_path)
    _custom_checker(
        project,
        "import sys\n"
        'text = open("code.py", encoding="utf-8").read()\n'
        'if "LIMIT = 5" not in text:\n'
        '    print("ERROR collecting test_limit_pinned (import error)")\n'
        '    print("0 failed, 1 error")\n'
        "    sys.exit(2)\n"
        'print("all green")\n',
    )
    proc = _run_table(project, [_row()])
    assert proc.returncode == 1
    assert "| MISATTRIBUTED |" in proc.stdout
    assert "0 failed" in proc.stdout


def test_unparseable_count_still_kills_without_the_exactly_one_claim(tmp_path):
    project = _project(tmp_path)
    _custom_checker(
        project,
        "import sys\n"
        'text = open("code.py", encoding="utf-8").read()\n'
        'if "LIMIT = 5" not in text:\n'
        '    print("ERROR test_limit_pinned exploded")\n'
        "    sys.exit(1)\n"
        'print("all green")\n',
    )
    proc = _run_table(project, [_row()])
    assert proc.returncode == 0
    assert "| KILLED+others |" in proc.stdout
    assert "failure count unparseable" in proc.stdout


def test_alternate_count_shapes_parse(tmp_path):
    """The mocha/cargo count shapes are load-bearing, not decorative: each
    yields the exactly-one KILLED claim."""
    shapes = ('print("FAILED test_limit_pinned"); print("failures: 1")',
              'print("x test_limit_pinned FAILED"); print("1 failing")')
    for index, shape in enumerate(shapes):
        subdir = tmp_path / f"shape-{index}"
        subdir.mkdir()
        project = _project(subdir)
        _custom_checker(
            project,
            "import sys\n"
            'text = open("code.py", encoding="utf-8").read()\n'
            'if "LIMIT = 5" not in text:\n'
            f"    {shape}\n"
            "    sys.exit(1)\n"
            'print("all green")\n',
        )
        proc = _run_table(project, [_row()])
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "| KILLED |" in proc.stdout, shape
        assert "exactly 'test_limit_pinned' went red" in proc.stdout, shape


def test_note_reaches_the_ledger(tmp_path):
    """The note is the field that links a row to its story AC; a note that
    never reaches the artifact the reviewers read is decoration."""
    project = _project(tmp_path)
    proc = _run_table(project, [_row(note="AC-3 twin")])
    assert proc.returncode == 0
    assert "AC-3 twin" in proc.stdout


def test_undecodable_target_is_a_classified_row_not_a_traceback(tmp_path):
    project = _project(tmp_path)
    (project / "blob.bin").write_bytes(b"LIMIT = 5\xff\xfe\n")
    proc = _run_table(project, [_row(file="blob.bin")])
    assert proc.returncode == 1
    assert "| UNDECODABLE |" in proc.stdout
    assert "Traceback" not in proc.stderr


def test_sigterm_mid_command_still_restores(tmp_path):
    """The kill a harness timeout delivers must not strand the mutation on
    disk: SIGTERM is converted to SystemExit so the finally-restore runs."""
    import os
    import signal as signal_module
    import time

    if not hasattr(signal_module, "SIGTERM") or os.name == "nt":
        import pytest

        pytest.skip("POSIX-only: SIGTERM delivery semantics")

    project = _project(tmp_path)
    before = (project / "code.py").read_bytes()
    # Green on the baseline; on the mutated run, signal readiness then hang.
    _custom_checker(
        project,
        "import sys, time, pathlib\n"
        'text = open("code.py", encoding="utf-8").read()\n'
        'if "LIMIT = 5" not in text:\n'
        '    pathlib.Path("mutated-and-hanging").touch()\n'
        "    time.sleep(60)\n"
        '    print("1 failed: test_limit_pinned")\n'
        "    sys.exit(1)\n"
        'print("all green")\n',
    )
    table = project / "table.json"
    table.write_text(json.dumps([_row()]), encoding="utf-8", newline="\n")
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--table", str(table), "--project-root", str(project)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    ready = project / "mutated-and-hanging"
    deadline = time.monotonic() + 30
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert ready.exists(), "the mutated command never started"
    proc.send_signal(signal_module.SIGTERM)
    proc.wait(timeout=30)

    assert proc.returncode == 128 + signal_module.SIGTERM
    assert (project / "code.py").read_bytes() == before


# --- Node's test runner (issue #158) -----------------------------------------
#
# Since Node 23 the spec reporter is Node's default even when the output is
# captured, as it is here. It marks a failed test with U+2716, a passed one
# with U+2714, and ends with "fail N" behind U+2139. The runner used to know
# none of that: every kill read MISATTRIBUTED until a run switched Node to TAP.
# The checker below prints that output from fixed lines (taken from a real
# `node --test` run on Node 24), so these cases run without Node; the last
# case drives the real runner when Node is on PATH.

NODE_CHECKER = """\
import sys
SHAPE = __SHAPE__
FAIL, PASS, INFO = chr(0x2716), chr(0x2714), chr(0x2139)
COLOUR = SHAPE == "spec-colour"
RED, GREEN, BLUE, OFF = (
    ("\\x1b[31m", "\\x1b[32m", "\\x1b[34m", "\\x1b[39m") if COLOUR else ("", "", "", "")
)
text = open("code.py", encoding="utf-8").read()
cases = [
    ("limit rejects error input", "LIMIT = 5" in text),
    ("flag is on", 'FLAG = "on"' in text),
]
failed = [name for name, ok in cases if not ok]
if SHAPE == "tap":
    lines = ["TAP version 13"]
    for number, (name, ok) in enumerate(cases, 1):
        lines += ["# Subtest: " + name, ("ok " if ok else "not ok ") + str(number) + " - " + name]
    lines += ["1..2", "# tests 2", "# pass " + str(2 - len(failed)), "# fail " + str(len(failed))]
else:
    lines = [
        (GREEN + PASS if ok else RED + FAIL) + " " + name + " (0.4ms)" + OFF
        for name, ok in cases
    ]
    for key in ("tests 2", "pass " + str(2 - len(failed)), "fail " + str(len(failed))):
        lines.append(BLUE + INFO + " " + key + OFF)
    if failed:
        lines += ["", RED + FAIL + " failing tests:" + OFF, ""]
        for name in failed:
            lines += [
                "test at check.test.mjs:3:1",
                RED + FAIL + " " + name + " (0.4ms)" + OFF,
                "  AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:",
            ]
# Bytes, so a Windows console code page cannot refuse the marks.
sys.stdout.buffer.write(("\\n".join(lines) + "\\n").encode("utf-8"))
sys.exit(1 if failed else 0)
"""


def _node_project(tmp_path: Path, shape: str) -> Path:
    project = _project(tmp_path)
    _custom_checker(project, NODE_CHECKER.replace("__SHAPE__", repr(shape)))
    return project


_FLAG_ROW = {"anchor": 'FLAG = "on"', "replacement": 'FLAG = "off"'}


def test_node_spec_reporter_kill_is_attributed_and_counted(tmp_path):
    """The rehearsal's failure: a real kill, named on a line marked U+2716 and
    nothing else, used to read MISATTRIBUTED. It now reads KILLED, and the
    summary's "fail 1" gives the exactly-one claim."""
    project = _node_project(tmp_path, "spec")
    proc = _run_table(project, [_row(**_FLAG_ROW, expect_red="flag is on")])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "| KILLED |" in proc.stdout
    assert "exactly 'flag is on' went red" in proc.stdout


def test_node_spec_reporter_pass_mark_never_attributes(tmp_path):
    """A test named with a failure word ("error") that PASSED, on a line marked
    U+2714, is not the observer that fired. Before the pass mark was read,
    this row claimed a kill for a test that stayed green."""
    project = _node_project(tmp_path, "spec")
    proc = _run_table(project, [_row(**_FLAG_ROW, expect_red="limit rejects error input")])
    assert proc.returncode == 1
    assert "| MISATTRIBUTED |" in proc.stdout


def test_node_spec_reporter_extra_reds_are_counted(tmp_path):
    project = _node_project(tmp_path, "spec")
    row = _row(
        anchor='LIMIT = 5\nFLAG = "on"',
        replacement='LIMIT = 6\nFLAG = "off"',
        expect_red="flag is on",
    )
    proc = _run_table(project, [row])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "| KILLED+others |" in proc.stdout
    assert "among 2 failures" in proc.stdout


def test_node_spec_reporter_with_colour_codes(tmp_path):
    """FORCE_COLOR puts escape codes before each mark; they must not hide it."""
    project = _node_project(tmp_path, "spec-colour")
    proc = _run_table(project, [_row(**_FLAG_ROW, expect_red="flag is on")])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "| KILLED |" in proc.stdout
    assert "exactly 'flag is on' went red" in proc.stdout
    passed = _run_table(project, [_row(**_FLAG_ROW, expect_red="limit rejects error input")])
    assert "| MISATTRIBUTED |" in passed.stdout


def test_node_tap_reporter_count_and_pass_lines(tmp_path):
    """Node's TAP shape (its default before Node 23 when captured): `# fail 1`
    now gives the exactly-one claim, and an `ok N` line is a pass."""
    project = _node_project(tmp_path, "tap")
    proc = _run_table(project, [_row(**_FLAG_ROW, expect_red="flag is on")])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "exactly 'flag is on' went red" in proc.stdout
    passed = _run_table(project, [_row(**_FLAG_ROW, expect_red="limit rejects error input")])
    assert "| MISATTRIBUTED |" in passed.stdout


NODE_TEST_FILE = """\
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LIMIT, FLAG } from './code.mjs';
test('limit is pinned', () => { assert.equal(LIMIT, 5); });
test('flag is on', () => { assert.equal(FLAG, 'on'); });
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_real_node_test_runner_kill(tmp_path):
    """The real `node --test`, with whatever reporter this Node defaults to."""
    (tmp_path / "code.mjs").write_text(
        "export const LIMIT = 5;\nexport const FLAG = 'on';\n", encoding="utf-8", newline="\n"
    )
    (tmp_path / "check.test.mjs").write_text(NODE_TEST_FILE, encoding="utf-8", newline="\n")
    row = {
        "file": "code.mjs",
        "anchor": "LIMIT = 5",
        "replacement": "LIMIT = 6",
        "command": "node --test check.test.mjs",
        "expect_red": "limit is pinned",
    }
    proc = _run_table(tmp_path, [row])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "| KILLED |" in proc.stdout
    assert "exactly 'limit is pinned' went red" in proc.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_real_node_test_runner_two_runs_add_their_counts(tmp_path):
    """A command that runs a passing suite before the failing one prints two
    summaries, `fail 0` first. Reading only the first called a real kill
    MISATTRIBUTED, with "0 failed"."""
    (tmp_path / "code.mjs").write_text(
        "export const LIMIT = 5;\nexport const FLAG = 'on';\n", encoding="utf-8", newline="\n"
    )
    (tmp_path / "check.test.mjs").write_text(NODE_TEST_FILE, encoding="utf-8", newline="\n")
    (tmp_path / "other.test.mjs").write_text(
        "import { test } from 'node:test';\ntest('other passes', () => {});\n",
        encoding="utf-8",
        newline="\n",
    )
    row = {
        "file": "code.mjs",
        "anchor": "LIMIT = 5",
        "replacement": "LIMIT = 6",
        "command": "node --test other.test.mjs && node --test check.test.mjs",
        "expect_red": "limit is pinned",
    }
    proc = _run_table(tmp_path, [row])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "| KILLED |" in proc.stdout
    assert "exactly 'limit is pinned' went red" in proc.stdout


# --- Other reporters' pass and failure marks -----------------------------------
#
# The checker prints fixed lines in each runner's shape: GREEN while FLAG is
# on, RED once the row turns it off. Every RED output also names a PASSING test
# whose name holds a failure word, which must never be credited with the kill.

FIXED_CHECKER = """\
import sys
GREEN = __GREEN__
RED = __RED__
flag_on = 'FLAG = "on"' in open("code.py", encoding="utf-8").read()
sys.stdout.buffer.write(("\\n".join(GREEN if flag_on else RED) + "\\n").encode("utf-8"))
sys.exit(0 if flag_on else 1)
"""

SHAPES = {
    # Two `node --test` runs, the passing one first: both summaries count.
    "node-spec-two-runs": (
        ["✔ other passes (0.2ms)", "ℹ fail 0", "✔ flag is on (0.3ms)", "ℹ fail 0"],
        [
            "✔ other passes (0.2ms)",
            "ℹ tests 1",
            "ℹ fail 0",
            "✖ flag is on (0.3ms)",
            "  AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:",
            "ℹ tests 1",
            "ℹ fail 1",
        ],
    ),
    "node-tap-two-runs": (
        ["ok 1 - other passes", "# fail 0", "ok 1 - flag is on", "# fail 0"],
        [
            "TAP version 13",
            "ok 1 - other passes",
            "# fail 0",
            "TAP version 13",
            "not ok 1 - flag is on",
            "# fail 1",
        ],
    ),
    # pytest -v, with xdist, and the -rA summary line.
    "pytest-verbose": (
        ["t.py::test_rejects_error_input PASSED [ 50%]", "t.py::test_flag_on PASSED [100%]"],
        [
            "t.py::test_rejects_error_input PASSED                    [ 50%]",
            "t.py::test_flag_on FAILED                                [100%]",
            "FAILED t.py::test_flag_on - AssertionError: assert 'off' == 'on'",
            "========== 1 failed, 1 passed in 0.02s ==========",
        ],
    ),
    "pytest-xdist": (
        ["[gw0] [ 50%] PASSED t.py::test_rejects_error_input"],
        [
            "[gw0] [ 50%] PASSED t.py::test_rejects_error_input",
            "[gw1] [100%] FAILED t.py::test_flag_on",
            "PASSED t.py::test_rejects_error_input",
            "FAILED t.py::test_flag_on - AssertionError",
            "========== 1 failed, 1 passed in 0.02s ==========",
        ],
    ),
    # jest's verbose reporter, which also names a lone test file's tests.
    "jest": (
        ["  ✓ rejects error input (2 ms)", "  ✓ flag is on (1 ms)"],
        [
            "  ✓ rejects error input (2 ms)",
            "  ✕ flag is on (3 ms)",
            "  ● suite › flag is on",
            "Tests:       1 failed, 1 passed, 2 total",
        ],
    ),
    # jest on Windows prints U+221A and U+00D7.
    "jest-windows": (
        ["  √ rejects error input (2 ms)", "  √ flag is on (1 ms)"],
        [
            "  √ rejects error input (2 ms)",
            "  × flag is on (3 ms)",
            "Tests:       1 failed, 1 passed, 2 total",
        ],
    ),
}

_PYTEST_SHAPES = ("pytest-verbose", "pytest-xdist")


def _fixed_project(tmp_path: Path, shape: str) -> Path:
    project = _project(tmp_path)
    green, red = SHAPES[shape]
    _custom_checker(
        project,
        FIXED_CHECKER.replace("__GREEN__", repr(green)).replace("__RED__", repr(red)),
    )
    return project


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_each_reporter_shape_attributes_and_counts_a_real_kill(tmp_path, shape):
    project = _fixed_project(tmp_path, shape)
    name = "test_flag_on" if shape in _PYTEST_SHAPES else "flag is on"
    proc = _run_table(project, [_row(**_FLAG_ROW, expect_red=name)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "| KILLED |" in proc.stdout
    assert f"exactly {name!r} went red" in proc.stdout


@pytest.mark.parametrize("shape", sorted(s for s in SHAPES if not s.startswith("node")))
def test_a_passing_test_named_with_a_failure_word_is_never_credited(tmp_path, shape):
    """Before these pass lines were read, this row read KILLED for a test that
    stayed green, because "error" on its PASSED line counted as a failure."""
    project = _fixed_project(tmp_path, shape)
    name = "test_rejects_error_input" if shape in _PYTEST_SHAPES else "rejects error input"
    proc = _run_table(project, [_row(**_FLAG_ROW, expect_red=name)])
    assert proc.returncode == 1
    assert "| MISATTRIBUTED |" in proc.stdout


# --- The PEP 723 header (issue #158) -------------------------------------------


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_plain_uv_run_works_inside_a_project_with_its_own_pyproject(tmp_path):
    """Installed under a project with its own pyproject.toml, the script once
    had no `# /// script` header, so a plain `uv run .../mutate_check.py` set
    up THAT project first and failed with it, and runs fell back to
    `uv run --no-project`. With the header, uv runs the script on its own.

    The host project depends on a package that does not exist, and uv runs
    offline, so any attempt to set up the project fails at once.
    """
    host = tmp_path / "host"
    scripts = host / ".claude" / "skills" / "ultracode-goal" / "scripts"
    scripts.mkdir(parents=True)
    installed = scripts / SCRIPT.name
    shutil.copy2(SCRIPT, installed)
    (host / "pyproject.toml").write_text(
        '[project]\nname = "host"\nversion = "0"\nrequires-python = ">=3.11"\n'
        'dependencies = ["ucg-issue-158-no-such-package==9.9.9"]\n',
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "UV_OFFLINE": "1",
        "UV_PYTHON": sys.executable,
        "UV_PYTHON_DOWNLOADS": "never",
    }
    proc = subprocess.run(
        ["uv", "run", str(installed), "--help"],
        cwd=host,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "--table" in proc.stdout
    assert not (host / ".venv").exists(), "uv set up the host project"
