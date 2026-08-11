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
import subprocess
import sys
from pathlib import Path

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
            'open("code.py", "a", encoding="utf-8").write("# scribble\\n")\n'
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
