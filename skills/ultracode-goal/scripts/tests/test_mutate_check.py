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
import time
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


def _run_table(project: Path, rows: list[dict], env: dict | None = None):
    table = project / "table.json"
    table.write_text(json.dumps(rows), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--table", str(table), "--project-root", str(project)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc


def _ci_env(ci: bool) -> dict:
    """The environment with pytest's CI switch set or cleared. pytest prints
    each short summary entry's whole message when `CI` or `BUILD_NUMBER` is set,
    as GitHub Actions sets it, so a test that reads pytest's output runs both
    ways and reads the same on a laptop and in CI."""
    env = {key: value for key, value in os.environ.items() if key not in ("CI", "BUILD_NUMBER")}
    if ci:
        env["CI"] = "true"
    return env


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


# --- A mutant that breaks a module: pytest's collection error ------------------

_CLAMP = "def clamp(x, hi):\n    if x > hi:\n        return hi\n    return x\n"


def _pytest_project(tmp_path: Path, tests: dict[str, str]) -> Path:
    (tmp_path / "tests").mkdir()
    (tmp_path / "calc.py").write_text(_CLAMP, encoding="utf-8", newline="\n")
    for name, body in tests.items():
        (tmp_path / "tests" / name).write_text(body, encoding="utf-8", newline="\n")
    return tmp_path


def _pytest_row(flags: str, replacement: str, expect_red: str = "test_clamp_at_the_bound") -> dict:
    return {
        "file": "calc.py",
        "anchor": "if x > hi:",
        "replacement": replacement,
        "command": f'"{sys.executable}" -m pytest {flags} -p no:cacheprovider tests',
        "expect_red": expect_red,
    }


_AT_THE_BOUND = "from calc import clamp\n\n\ndef test_clamp_at_the_bound():\n    assert clamp(9, 5) == 5\n"
_OTHER = "def test_other():\n    assert True\n"


# Each shape leans on one sign of the error: `-q --tb=no -rN` prints only the
# `Interrupted:` line, `-q -rN -n 2` only the `ERROR collecting` header, and
# `-q --tb=no -n 2` only the short summary line.
@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize(
    "flags", ["-q", "-qq", "-q --tb=no -rN", "-q -n 2", "-q -rN -n 2", "-q --tb=no -n 2", "-qq -n 2"]
)
def test_a_mutant_that_breaks_collection_is_no_kill(tmp_path, flags, ci):
    """A replacement that drops the colon breaks `calc.py`, so pytest stops at
    collecting the module that imports it and no test runs. The output never
    names the row's test, and pytest counts the collection error in its
    `error` total, so the row read `MISATTRIBUTED` as a missing name, which
    the gate reads as another test's kill: the gap closed with no test run.
    It now reads 0 failed, a collection error. Under xdist pytest does not
    stop, and a module that collects still runs beside the error."""
    if "-n" in flags:
        pytest.importorskip("xdist")
    project = _pytest_project(tmp_path, {"test_clamp.py": _AT_THE_BOUND, "test_other.py": _OTHER})
    proc = _run_table(project, [_pytest_row(flags, "if x > hi")], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {
        0: ("MISATTRIBUTED", "red, but the output's own count says 0 failed - a collection or harness error, not the observer"),
    }, proc.stdout + proc.stderr
    assert proc.returncode == 1


def test_a_setup_error_still_counts_as_a_failure(tmp_path):
    """The twin: a fixture that raises under the mutant is an error AT SETUP of
    a test that pytest collected, named with its `::` id, and it still kills."""
    fixture = (
        "import pytest\nfrom calc import clamp\n\n\n@pytest.fixture\ndef bound():\n"
        "    assert clamp(9, 5) == 5\n    return 5\n\n\n"
        "def test_clamp_at_the_bound(bound):\n    assert bound == 5\n"
    )
    project = _pytest_project(tmp_path, {"test_clamp.py": fixture, "test_other.py": _OTHER})
    proc = _run_table(project, [_pytest_row("-q", "if False:")])
    assert _ledger_rows(proc.stdout) == {0: ("KILLED", "exactly 'test_clamp_at_the_bound' went red")}, (
        proc.stdout + proc.stderr
    )
    assert proc.returncode == 0


@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize("flags", ["-q", "-q -n 2"])
def test_a_setup_error_kill_whose_fixture_prints_an_error_line_still_kills(tmp_path, flags, ci):
    """pytest prints a failing fixture's captured output above the short
    summary, so a line such as `ERROR bound-not-enforced` reaches the output
    beside the setup error's own line. Read as a short summary line, it took
    the row's one kill off the count, and the kill read 0 failed, a row that
    cannot run. Only a line under the short summary's header is read."""
    if "-n" in flags:
        pytest.importorskip("xdist")
    fixture = (
        "import pytest\nfrom calc import clamp\n\n\n@pytest.fixture\ndef bound():\n"
        "    if clamp(9, 5) != 5:\n        print('ERROR bound-not-enforced')\n"
        "        raise RuntimeError('bound')\n    return 5\n\n\n"
        "def test_clamp_at_the_bound(bound):\n    assert bound == 5\n"
    )
    project = _pytest_project(tmp_path, {"test_clamp.py": fixture, "test_other.py": _OTHER})
    proc = _run_table(project, [_pytest_row(flags, "if False:")], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {0: ("KILLED", "exactly 'test_clamp_at_the_bound' went red")}, (
        proc.stdout + proc.stderr
    )
    assert proc.returncode == 0


@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize("flags", ["-q --tb=no -n 2", "-vv --tb=no -n 2", "-q -n 2"])
def test_every_collection_error_counts_when_entries_span_lines(tmp_path, flags, ci):
    """Under `-vv`, or when `CI` is set, pytest prints each short summary
    entry's whole message, and under xdist a collection error's message is its
    traceback, so one `ERROR <path>` entry spans many lines. A scan that ended
    the short summary at the first line opening no entry read only the first of
    two collection errors, so `2 errors` left one standing as a failure and the
    row read as another test's kill."""
    pytest.importorskip("xdist")
    project = _pytest_project(
        tmp_path, {"test_clamp.py": _AT_THE_BOUND, "test_below.py": _AT_THE_BOUND, "test_other.py": _OTHER}
    )
    proc = _run_table(project, [_pytest_row(flags, "if x > hi")], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1


_SUBTESTS = (
    "import sys\n\nimport pytest\n\n\ndef test_cases(subtests):\n    for n in (1, 2):\n"
    "        with subtests.test(n=n):\n            assert n > 0\n\n\n"
    "def test_platforms(subtests):\n    with subtests.test(msg='nt'):\n"
    "        if sys.platform != 'nt':\n            pytest.skip('windows only')\n"
)


@pytest.mark.parametrize("flags", ["-q -n 2", "-q -ra --tb=no -n 2"])
def test_a_collection_error_beside_subtests_is_no_kill(tmp_path, flags):
    """pytest 9 counts passed subtests apart on the stats line (`2 passed, 1
    error, 2 subtests passed`), which the stats pattern did not read, and lists a
    skipped subtest as `SUBSKIPPED(...)` in the short summary. Either way the
    collection error beside them stood as a failure, so a mutant that only broke
    collection read as another test's kill."""
    pytest.importorskip("xdist")
    if int(pytest.__version__.split(".")[0]) < 9:
        pytest.skip("pytest 9 ships the subtests fixture")
    project = _pytest_project(tmp_path, {"test_clamp.py": _AT_THE_BOUND, "test_subtests.py": _SUBTESTS})
    proc = _run_table(project, [_pytest_row(flags, "if x > hi")], _ci_env(False))
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1


_SKIP_WITH_A_LOG = (
    "import pytest\n\n\ndef test_database():\n"
    "    pytest.skip('database unreachable, server log:\\n  connecting to db:5432\\nERROR connection-refused')\n"
)
_FAIL_WITH_A_LOG = (
    "import pytest\nfrom calc import clamp\n\n\n@pytest.fixture\ndef bound():\n"
    "    if clamp(9, 5) != 5:\n"
    "        pytest.fail('checking bounds\\n  hi=5 x=9\\nERROR bound-not-enforced')\n    return 5\n\n\n"
    "def test_clamp_at_the_bound(bound):\n    assert bound == 5\n"
)


@pytest.mark.parametrize(
    ("tests", "flags", "ci"),
    [
        ({"test_clamp.py": None, "test_env.py": _SKIP_WITH_A_LOG}, "-q -rs", False),
        ({"test_clamp.py": None, "test_env.py": _SKIP_WITH_A_LOG}, "-q -rs -n 2", False),
        ({"test_clamp.py": _FAIL_WITH_A_LOG}, "-vv", False),
        ({"test_clamp.py": _FAIL_WITH_A_LOG}, "-q", True),
        ({"test_clamp.py": _FAIL_WITH_A_LOG}, "-q -n 2", True),
    ],
    ids=["skip-reason", "skip-reason-xdist", "kill-message-vv", "kill-message-ci", "kill-message-ci-xdist"],
)
def test_an_error_line_inside_a_summary_entry_is_no_collection_error(tmp_path, tests, flags, ci):
    """A short summary entry runs over lines when its reason or message does: a
    skip or xfail reason always, a kill's message under `-vv` or when `CI` is
    set. A line of it such as `ERROR connection-refused` is no collected path,
    so it is not a collection error, and the row's setup-error kill is still the
    one failure. Counted as one, it took that kill off the count and the row
    read 0 failed, a row that cannot run."""
    if "-n" in flags:
        pytest.importorskip("xdist")
    fixture = (
        "import pytest\nfrom calc import clamp\n\n\n@pytest.fixture\ndef bound():\n"
        "    if clamp(9, 5) != 5:\n        raise RuntimeError('bound')\n    return 5\n\n\n"
        "def test_clamp_at_the_bound(bound):\n    assert bound == 5\n"
    )
    project = _pytest_project(tmp_path, {name: body or fixture for name, body in tests.items()})
    proc = _run_table(project, [_pytest_row(flags, "if False:")], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {0: ("KILLED", "exactly 'test_clamp_at_the_bound' went red")}, (
        proc.stdout + proc.stderr
    )
    assert proc.returncode == 0


@pytest.mark.parametrize("flags", ["-q", "-qq", "-q -n 2"])
def test_a_mutant_that_breaks_a_startup_plugin_is_no_kill(tmp_path, flags):
    """A module the root conftest names in `pytest_plugins` is imported while
    pytest sets itself up, and one that fails to import is not reported as a
    conftest error: pytest dies with a bare traceback through `_prepareconfig`,
    exit 1, no summary. No test ran, so the row reads 0 failed, not a kill by a
    test of another name."""
    if "-n" in flags:
        pytest.importorskip("xdist")
    project = _pytest_project(tmp_path, {"test_clamp.py": _THROUGH_A_FIXTURE, "test_other.py": _OTHER})
    (project / "conftest.py").write_text('pytest_plugins = ["fixtures.calc_fixtures"]\n', encoding="utf-8", newline="\n")
    (project / "fixtures").mkdir()
    (project / "fixtures" / "__init__.py").write_text("", encoding="utf-8")
    (project / "fixtures" / "calc_fixtures.py").write_text(_CONFTEST, encoding="utf-8", newline="\n")
    proc = _run_table(project, [_pytest_row(flags, "if x > hi")], _ci_env(False))
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1
    # The twin: a mutant the plugin still imports under fails the test, a kill.
    proc = _run_table(project, [_pytest_row(flags, "if False:")], _ci_env(False))
    status, detail = _ledger_rows(proc.stdout)[0]
    assert status.startswith("KILLED") or detail.startswith("red, but 'test_clamp_at_the_bound' never appears"), (
        proc.stdout + proc.stderr
    )


@pytest.mark.parametrize("flags", ["-q --tb=no -n 2", "-qq -n 2"])
def test_a_top_level_directory_whose_conftest_fails_is_a_collection_error(tmp_path, flags):
    """A conftest.py in a top-level directory that fails to import is listed as
    `ERROR sub` when pytest collects from the project root, a bare name with no
    `.py` and no separator: it counts because that name is a directory under the
    project root. (Named on the command line, the directory's conftest.py loads
    at startup instead, as `ImportError while loading conftest`.)"""
    pytest.importorskip("xdist")
    project = _pytest_project(tmp_path, {"test_other.py": _OTHER})
    (project / "sub").mkdir()
    (project / "sub" / "conftest.py").write_text(_CONFTEST, encoding="utf-8", newline="\n")
    (project / "sub" / "test_clamp.py").write_text(_THROUGH_A_FIXTURE, encoding="utf-8", newline="\n")
    row = _pytest_row(flags, "if x > hi")
    row["command"] = row["command"][: -len(" tests")]
    proc = _run_table(project, [row], _ci_env(False))
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1


def test_a_collection_error_beside_a_kill_is_not_counted(tmp_path):
    """Under xdist a module that fails to collect sits beside the modules that
    ran. Here the mutant makes one module fail at import and the row's test
    fail: the one test that went red is the kill, and the collection error is
    not a second failure (it read `KILLED+others` among 2)."""
    pytest.importorskip("xdist")
    import_time = "from calc import clamp\n\nassert clamp(9, 5) == 5\n\n\ndef test_import_time():\n    assert True\n"
    project = _pytest_project(tmp_path, {"test_clamp.py": _AT_THE_BOUND, "test_import_time.py": import_time})
    proc = _run_table(project, [_pytest_row("-q -n 2", "if False:")])
    assert _ledger_rows(proc.stdout) == {0: ("KILLED", "exactly 'test_clamp_at_the_bound' went red")}, (
        proc.stdout + proc.stderr
    )
    # Without xdist pytest stops at that module, so no test ran at all.
    proc = _run_table(project, [_pytest_row("-q", "if False:")])
    assert _ledger_rows(proc.stdout)[0][0] == "MISATTRIBUTED", proc.stdout
    assert "0 failed" in proc.stdout


def test_a_collection_error_beside_a_setup_error_kill_is_one_kill(tmp_path):
    """Under xdist, a mutant that breaks `calc.py` stops one module at import,
    which pytest prints once as an `ERROR collecting` header and once as a
    short summary line, and the row's own test errors at setup, since its
    fixture imports the module only then: `2 errors`, one of them the kill.
    The collection error is taken off that count once, so the row reads
    `KILLED`. Taken off once for each sign of it, the kill read 0 failed, a
    row that cannot run."""
    pytest.importorskip("xdist")
    eager = "from calc import clamp\n\n\ndef test_a_uses_clamp():\n    assert clamp(1, 5) == 1\n"
    lazy = (
        "import pytest\n\n\n@pytest.fixture\ndef clamp():\n    import calc\n    return calc.clamp\n\n\n"
        "def test_clamp_at_the_bound(clamp):\n    assert clamp(9, 5) == 5\n"
    )
    project = _pytest_project(tmp_path, {"test_a.py": eager, "test_b.py": lazy})
    proc = _run_table(project, [_pytest_row("-q -n 2", "if x > hi")])
    assert _ledger_rows(proc.stdout) == {0: ("KILLED", "exactly 'test_clamp_at_the_bound' went red")}, (
        proc.stdout + proc.stderr
    )
    assert proc.returncode == 0


_ZERO_FAILED = "red, but the output's own count says 0 failed - a collection or harness error, not the observer"
_CONFTEST = "import pytest\nimport calc\n\n\n@pytest.fixture\ndef clamp():\n    return calc.clamp\n"
_THROUGH_A_FIXTURE = "def test_clamp_at_the_bound(clamp):\n    assert clamp(9, 5) == 5\n"


@pytest.mark.parametrize("flags", ["-q", "-qq", "-q --tb=no -rN", "-q -n 2", "-q -rN -n 2", "-q --tb=no -n 2"])
def test_a_mutant_that_breaks_what_the_root_conftest_imports_is_no_kill(tmp_path, flags):
    """In a Flask, Django or FastAPI project, conftest.py imports the app. A
    replacement that breaks the module it imports stops pytest before it
    collects anything: it writes `ImportError while loading conftest` and the
    error, and exits 4 with no summary and no `ERROR collecting` line, under
    xdist too, so no test runs. The row read `MISATTRIBUTED` as a missing
    name, which the gate reads as another test's kill; it now reads 0
    failed."""
    if "-n" in flags:
        pytest.importorskip("xdist")
    project = _pytest_project(tmp_path, {"test_clamp.py": _THROUGH_A_FIXTURE, "test_other.py": _OTHER})
    (project / "conftest.py").write_text(_CONFTEST, encoding="utf-8", newline="\n")
    proc = _run_table(project, [_pytest_row(flags, "if x > hi")])
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1
    # The twin: a mutant the conftest still loads under fails the test through
    # the fixture, a kill, never 0 failed (a shape that prints no failed test's
    # name reads it as a kill by another name, and one with no summary line as
    # a kill with an unparseable count, as for any kill).
    proc = _run_table(project, [_pytest_row(flags, "if False:")])
    status, detail = _ledger_rows(proc.stdout)[0]
    assert status.startswith("KILLED") or detail.startswith("red, but 'test_clamp_at_the_bound' never appears"), (
        proc.stdout + proc.stderr
    )


@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize(
    "flags", ["-q", "-qq", "-q --tb=no -rN", "-q -n 2", "-q -rN -n 2", "-q --tb=no -n 2", "-qq -n 2"]
)
def test_a_mutant_that_breaks_what_a_nested_conftest_imports_is_no_kill(tmp_path, flags, ci):
    """A conftest.py below the path the command names is loaded while pytest
    collects, and one that fails to import is a collection error of its
    directory: the short summary line reads `ERROR tests/sub`, a path that is
    no module's. Under `--tb=no -n 2` that line is the only sign of it, so the
    row read `MISATTRIBUTED` as a missing name; it now reads 0 failed."""
    if "-n" in flags:
        pytest.importorskip("xdist")
    project = _pytest_project(tmp_path, {"test_other.py": _OTHER})
    (project / "tests" / "sub").mkdir()
    (project / "tests" / "sub" / "conftest.py").write_text(_CONFTEST, encoding="utf-8", newline="\n")
    (project / "tests" / "sub" / "test_clamp.py").write_text(_THROUGH_A_FIXTURE, encoding="utf-8", newline="\n")
    proc = _run_table(project, [_pytest_row(flags, "if x > hi")], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1


# --- A test file jest or vitest cannot load ------------------------------------
#
# Real output, captured on Linux with Node 24.21.0 outside Claude Code, of a
# mutant that breaks the module a test file imports at its top (`if (x > hi {`
# in calc.js), beside a second test file that does not import it:
#   jest-one-of-two     jest 30.2.0, `jest` over both files
#   jest-alone          `jest tests/clamp.test.js`
#   vitest-one-of-two   vitest 3.2.4, `vitest run` over both files
#   vitest-alone        `vitest run tests/clamp.test.js`
# The file that fails to load runs no test. Its test, `clamp at the bound`,
# appears only in jest's code frame. Local paths are replaced with
# /home/dev/work/load-failure.

LOAD_FAILURES = Path(__file__).resolve().parent / "fixtures" / "mutate_check_load_failure"

LOAD_FAILURE_CHECKER = """\
import sys
from pathlib import Path
if "LIMIT = 5" in open("code.py", encoding="utf-8").read():
    print("all green")
    sys.exit(0)
sys.stdout.buffer.write(Path("capture.txt").read_bytes())
sys.exit(1)
"""


@pytest.mark.parametrize("capture", ["jest-one-of-two", "jest-alone", "vitest-one-of-two", "vitest-alone"])
def test_a_test_file_jest_or_vitest_cannot_load_is_no_kill(tmp_path, capture):
    """jest's `Test Suites:` line and vitest's `Test Files` line count the file
    that failed to load as a failed one. When the `Tests` line counted no
    failure (`1 passed`, `0 total`, `no tests`), the fallback count shapes
    took `1 failed` from the files line, no failure line named the row's test,
    and the row read `MISATTRIBUTED` as a missing name, which the gate reads
    as another test's kill. The `Tests` line now gives the count: 0 failed."""
    project = _project(tmp_path)
    _custom_checker(project, LOAD_FAILURE_CHECKER)
    (project / "capture.txt").write_bytes((LOAD_FAILURES / f"{capture}.txt").read_bytes())
    proc = _run_table(project, [_row(expect_red="clamp at the bound")])
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1


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


# Imports the module under test, so CPython caches its bytecode in __pycache__.
IMPORT_CHECKER = """\
import sys
import guard
failures = []
if guard.LIMIT != 5:
    failures.append("test_limit_pinned")
if guard.FLAG != "on":
    failures.append("test_flag_on")
if failures:
    print(f"{len(failures)} failed:", ", ".join(failures))
    sys.exit(1)
print("all green")
"""


def test_same_size_mutations_never_run_stale_bytecode(tmp_path, monkeypatch):
    """CPython reuses cached bytecode whose recorded source mtime, in whole
    seconds, and size match the file. Two same-size mutations of one module
    and their restores, all written within one second, used to run each
    other's bytecode: the second row read MISATTRIBUTED (the first mutation
    failed again), and the next run refused a red baseline, the restored
    source still running the mutated bytecode. Every write now lands in a
    later second than the file's mtime before it; the file starts an hour
    ahead here so that holds whatever the clock does during the run."""
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
    project = tmp_path
    guard = project / "guard.py"
    guard.write_text('LIMIT = 5\nFLAG = "on"\n', encoding="utf-8", newline="\n")
    (project / "check.py").write_text(IMPORT_CHECKER, encoding="utf-8", newline="\n")
    ahead = (int(time.time()) + 3600) * 1_000_000_000
    os.utime(guard, ns=(ahead, ahead))
    before = guard.read_bytes()
    rows = [
        _row(file="guard.py", expect_red="test_limit_pinned"),
        _row(
            file="guard.py",
            anchor='FLAG = "on"',
            replacement='FLAG = "no"',
            expect_red="test_flag_on",
        ),
    ]
    killed = {
        0: ("KILLED", "exactly 'test_limit_pinned' went red"),
        1: ("KILLED", "exactly 'test_flag_on' went red"),
    }

    first = _run_table(project, rows)
    assert _ledger_rows(first.stdout) == killed, first.stdout + first.stderr
    assert first.returncode == 0
    assert guard.read_bytes() == before
    assert guard.stat().st_mtime_ns // 1_000_000_000 > ahead // 1_000_000_000

    again = _run_table(project, rows)
    assert _ledger_rows(again.stdout) == killed, again.stdout + again.stderr
    assert again.returncode == 0


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


# --- Real runners' output ------------------------------------------------------
#
# Each folder under fixtures/mutate_check/ holds what a real runner printed for
# one test file of three cases after three mutations: flag.txt with FLAG turned
# off (one red), mode.txt with MODE turned off (one red, a case whose own name
# holds "fails"), and both.txt with both (two reds in one file). Every passing
# neighbour is named with a failure word ("rejects error input", "fails when
# mode is loose"). In the JavaScript file the first case's body calls
# assertLimit, which jest and vitest quote in the code frame of the failing
# case beside it, and in the pytest file the first case prints, so -rA lists
# it in its PASSES section. Local paths are replaced with /home/dev/work.
#
# Captured on Linux with Node 24.21.0 and Python 3.14:
#   jest-default          jest 30.2.0, `jest` over two test files
#   jest-verbose          jest 30.2.0, `jest --verbose`
#   jest-agent            jest 30.5.2, `jest` under Claude Code, which makes
#                         jest pick its agent reporter (no per-test lines)
#   vitest-default        vitest 3.2.4, `vitest run`
#   vitest5-agent         vitest 5.0.5, `vitest run` under Claude Code
#   vitest5-colour        vitest 5.0.5, `vitest run` with COLORTERM set
#   pytest-default        pytest 9.1.1, `pytest`
#   pytest-v              `pytest -v`
#   pytest-sv             `pytest -sv`: the passing case's print lands on the
#                         line that names it, before its PASSED
#   pytest-rA             `pytest -rA`
#   pytest-xdist-v        pytest-xdist 3.8.0, `pytest -v -n 2`
#   pytest-class-rA       `pytest -rA`, the cases in a class TestErrorCases
#   pytest-class-xdist-v  `pytest -v -n 2`, the same class
#   pytest-setup-error    `pytest`, the FLAG case reading FLAG through a fixture
#                         that raises, so pytest counts it as an error
#   node-spec             `node --test`, the spec reporter
#   node-tap              `node --test --test-reporter=tap`
#   node-spec-two-runs    a passing `node --test` run, then the failing one
#   node-tap-two-runs     the same under TAP
#   turbo-node-spec       turbo 2.5.8, `turbo run test --force --filter=guard`,
#                         each line behind turbo's `guard:test: ` prefix
#   pnpm-node-spec        pnpm 9.15.9, `pnpm -r test` over two packages, each
#                         line behind pnpm's `packages/guard test: ` prefix
#   mixed-node-pytest-q   a passing `node --test` run, then `pytest -q`
#   mixed-node-jest       a passing `node --test` run, then `jest`
#
# jest-windows is not a capture: it is jest-verbose with the marks jest prints
# on Windows (U+221A for a pass, U+00D7 for a failure, from jest-util's ICONS).

CAPTURES = Path(__file__).resolve().parent / "fixtures" / "mutate_check"
REAL_RUNS = sorted(p.name for p in CAPTURES.iterdir() if p.is_dir()) + ["jest-windows"]

REPLAY_CHECKER = """\
import sys
from pathlib import Path
text = open("code.py", encoding="utf-8").read()
flag_off = 'FLAG = "on"' not in text
mode_off = 'MODE = "strict"' not in text
state = "both" if flag_off and mode_off else "flag" if flag_off else "mode" if mode_off else ""
if not state:
    print("all green")
    sys.exit(0)
sys.stdout.buffer.write(Path("captures", state + ".txt").read_bytes())
sys.exit(1)
"""

_MODE_ROW = {"anchor": 'MODE = "strict"', "replacement": 'MODE = "loose"'}
_BOTH_ROW = {
    "anchor": 'FLAG = "on"\nMODE = "strict"',
    "replacement": 'FLAG = "off"\nMODE = "loose"',
}


def _names(run: str) -> dict[str, str]:
    if "pytest" in run:
        return {
            "error": "test_rejects_error_input",
            "flag": "test_flag_on",
            "mode": "test_fails_when_mode_is_loose",
        }
    return {
        "error": "rejects error input",
        "flag": "flag is on",
        "mode": "fails when mode is loose",
    }


def _replay_project(tmp_path: Path, run: str) -> Path:
    project = _project(tmp_path, code='LIMIT = 5\nFLAG = "on"\nMODE = "strict"\n')
    _custom_checker(project, REPLAY_CHECKER)
    (project / "captures").mkdir()
    for state in ("flag", "mode", "both"):
        captured = "jest-verbose" if run == "jest-windows" else run
        text = (CAPTURES / captured / f"{state}.txt").read_bytes()
        if run == "jest-windows":
            text = text.replace("✓".encode(), "√".encode()).replace("✕".encode(), "×".encode())
        (project / "captures" / f"{state}.txt").write_bytes(text)
    return project


def _ledger_rows(stdout: str) -> dict[int, tuple[str, str]]:
    """{row index: (status, detail)} from the printed ledger."""
    rows = {}
    for line in stdout.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0].isdigit():
            rows[int(cells[0])] = (cells[1], cells[4])
    return rows


@pytest.mark.parametrize("run", REAL_RUNS)
def test_real_runner_output_attributes_and_counts_a_kill(tmp_path, run):
    """A real kill reads KILLED with the exactly-one claim, also when the
    case's own name holds a failure word, and two reds in one file read
    KILLED+others with both counted. Before, jest's default and agent
    reporters read MISATTRIBUTED, jest counted failing files instead of
    failing tests, turbo's or pnpm's prefix hid every count, and a passing
    Node run before pytest or jest read 0 failed."""
    names = _names(run)
    project = _replay_project(tmp_path, run)
    proc = _run_table(
        project,
        [
            _row(**_FLAG_ROW, expect_red=names["flag"]),
            _row(**_MODE_ROW, expect_red=names["mode"]),
            _row(**_BOTH_ROW, expect_red=names["flag"]),
        ],
    )
    assert _ledger_rows(proc.stdout) == {
        0: ("KILLED", f"exactly {names['flag']!r} went red"),
        1: ("KILLED", f"exactly {names['mode']!r} went red"),
        2: ("KILLED+others", f"{names['flag']!r} went red among 2 failures"),
    }, proc.stdout + proc.stderr
    assert proc.returncode == 0


@pytest.mark.parametrize("run", REAL_RUNS)
def test_real_runner_output_never_credits_a_passing_test_named_with_a_failure_word(
    tmp_path, run
):
    """Each row names a case that stayed green while a neighbour went red.
    Before, the failure word in its own name credited it from a jest or
    vitest code frame, a pytest -rA PASSES header, an xdist start line, the
    line `pytest -sv` prints its output on, or a line behind turbo's or
    pnpm's prefix."""
    names = _names(run)
    project = _replay_project(tmp_path, run)
    proc = _run_table(
        project,
        [
            _row(**_FLAG_ROW, expect_red=names["error"]),
            _row(**_FLAG_ROW, expect_red=names["mode"]),
            _row(**_MODE_ROW, expect_red=names["error"]),
        ],
    )
    rows = _ledger_rows(proc.stdout)
    assert [rows[index][0] for index in range(3)] == ["MISATTRIBUTED"] * 3, proc.stdout
    assert proc.returncode == 1


def test_a_count_never_reads_a_digit_from_the_line_above(tmp_path):
    """`2` ending one line and `FAILED` opening the next are not "2 failed"."""
    project = _project(tmp_path)
    _custom_checker(
        project,
        "import sys\n"
        'text = open("code.py", encoding="utf-8").read()\n'
        'if "LIMIT = 5" not in text:\n'
        '    print("collected on shard 2")\n'
        '    print("FAILED test_limit_pinned")\n'
        '    print("failures: 1")\n'
        "    sys.exit(1)\n"
        'print("all green")\n',
    )
    proc = _run_table(project, [_row()])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "exactly 'test_limit_pinned' went red" in proc.stdout


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


# --- Four more misreads of a count (issue #179) --------------------------------
#
# pytest's report (its ERRORS, FAILURES and PASSES sections, its warnings and its
# short summary) quotes each test's traceback, message and captured output, so a
# count there is no run's count. Under xdist pytest does not stop at a collection
# error, so its short summary can be the only sign of one, at a path that holds a
# space or at a class. One command can run pytest twice. Node's test runner
# reports a test file whose process failed as a failed test named after the file.
#
# The Node captures, each of a mutant to calc.mjs, captured as the jest and
# vitest ones above (Node 24.21.0, or Node 20.19.5 for the node20 ones):
#   node-spec-one-of-two, node20-spec-one-of-two, node-tap-one-of-two
#                       `node --test` over clamp.test.mjs, which the mutant
#                       (`if (x > hi {`) stops loading, and a passing file
#   node-spec-alone, node20-tap-alone
#                       `node --test clamp.test.mjs`
#   node-spec-kill-beside-load-failure, node-tap-kill-beside-load-failure
#                       the row's test fails in test/clamp.test.mjs, and
#                       test/loader.test.mjs fails an assert as it loads
#   node-spec-test-named-after-a-file
#                       the row's test, named `calc.mjs`, fails
#   node-spec-exits-after-its-tests-pass, node-tap-exits-after-its-tests-pass
#                       clamp.test.mjs's test passes, then a timer the mutant
#                       adds calls `process.exit(1)`, beside a passing file

_QUOTES_A_COUNT = (
    "from calc import clamp\n\n\ndef test_clamp_at_the_bound():\n"
    "    print('summary of the batch: 0 failed')\n    assert clamp(9, 5) == 5\n"
)
_IMPORT_TIME = "from calc import clamp\n\nassert clamp(9, 5) == 5\n\n\ndef test_import_time():\n    assert True\n"
_SETUP_ERROR_KILL = (
    "import pytest\nfrom calc import clamp\n\n\n@pytest.fixture\ndef bound():\n"
    "    if clamp(9, 5) != 5:\n        raise RuntimeError('bound')\n    return 5\n\n\n"
    "def test_clamp_at_the_bound(bound):\n    assert bound == 5\n"
)
_UNPARSEABLE = ("KILLED+others", "'test_clamp_at_the_bound' went red; failure count unparseable")
_EXACTLY = ("KILLED", "exactly 'test_clamp_at_the_bound' went red")


@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize("flags", ["-qq", "-qq -n 2"])
def test_a_count_a_kill_quotes_is_not_its_count(tmp_path, flags, ci):
    """`-qq` prints no stats line, so the shapes other runners' counts are read
    by were tried on every other line, and took `0 failed` from what the
    killing test printed, which pytest quotes in its report: the kill read 0
    failed, a row that cannot run. No line of pytest's report is read for such
    a count now, so the kill stands, with its count unknown."""
    if "-n" in flags:
        pytest.importorskip("xdist")
    project = _pytest_project(tmp_path, {"test_clamp.py": _QUOTES_A_COUNT, "test_other.py": _OTHER})
    proc = _run_table(project, [_pytest_row(flags, "if False:")], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {0: _UNPARSEABLE}, proc.stdout + proc.stderr
    assert proc.returncode == 0


@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize("flags", ["-q", "-qq", "-vv", "-q -n 2", "-qq -n 2"])
def test_a_count_a_collection_error_quotes_is_no_kill(tmp_path, flags, ci):
    """A module that prints `1 failed lookup` as it is imported, then raises,
    fails to collect, and pytest quotes the print in its ERRORS section. The
    stats line counts no failure, since a collection error is none, so the
    fallback shapes were tried and took `1 failed` from the quote, under plain
    `-q` too: a kill by a test of another name. It now reads 0 failed."""
    if "-n" in flags:
        pytest.importorskip("xdist")
    project = _pytest_project(tmp_path, {"test_clamp.py": _AT_THE_BOUND, "test_other.py": _OTHER})
    (project / "calc.py").write_text(
        "print('cache warm-up: 1 failed lookup')\n" + _CLAMP, encoding="utf-8", newline="\n"
    )
    row = _pytest_row(flags, "if x > hi:")
    row.update(anchor="def clamp(x, hi):", replacement="raise RuntimeError('warm-up')\n\n\ndef clamp(x, hi):")
    proc = _run_table(project, [row], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1


def _spaced_project(tmp_path: Path, tests: dict[str, str]) -> Path:
    project = _pytest_project(tmp_path, {"test_other.py": _OTHER})
    (project / "tests" / "my dir").mkdir()
    for name, body in tests.items():
        (project / "tests" / "my dir" / name).write_text(body, encoding="utf-8", newline="\n")
    return project


@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize(
    "flags", ["-q --tb=no -n 2", "-vv --tb=no -n 2", "-qq --tb=no -n 2", "-q -n 2", "-qq -n 2"]
)
def test_a_collection_error_at_a_path_with_a_space_is_no_kill(tmp_path, flags, ci):
    """Under xdist pytest does not stop at a collection error, and both its
    `ERROR collecting` header and its short summary entry were read as one
    word, so neither counted a module under `tests/my dir`: the error stood as
    a failure, a kill by a test of another name."""
    pytest.importorskip("xdist")
    project = _spaced_project(tmp_path, {"test_clamp.py": _AT_THE_BOUND})
    proc = _run_table(project, [_pytest_row(flags, "if x > hi")], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1


@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize("flags", ["-q -n 2", "-q --tb=no -n 2"])
def test_a_kill_at_a_path_with_a_space_beside_a_collection_error_still_kills(tmp_path, flags, ci):
    """Beside the row's kill, a module under `tests/my dir` that fails to
    collect counted as more failures, so the kill read `KILLED+others`."""
    pytest.importorskip("xdist")
    project = _spaced_project(tmp_path, {"test_clamp.py": _AT_THE_BOUND, "test_import_time.py": _IMPORT_TIME})
    proc = _run_table(project, [_pytest_row(flags, "if False:")], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {0: _EXACTLY}, proc.stdout + proc.stderr
    assert proc.returncode == 0


_IN_A_CLASS_WITH_IDS = (
    "import pytest\n\nfrom calc import clamp, label\n\n\nclass TestClamp:\n"
    "    @pytest.mark.parametrize('x', [9], ids=label)\n"
    "    def test_clamp_at_the_bound(self, x):\n        assert clamp(x, 5) == 5\n"
)


@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize("flags", ["-q --tb=no -n 2", "-vv --tb=no -n 2", "-qq --tb=no -n 2", "-qq -n 2"])
def test_a_class_pytest_cannot_collect_is_no_kill(tmp_path, flags, ci):
    """A parametrize `ids` function that raises stops pytest collecting the
    class, which its short summary lists as `ERROR <path>::TestClamp`. Read as
    a test's setup error for its `::` id, it counted as a failure, and under
    `-qq` it kept the short summary from reading as one that lists collection
    errors only: a kill, by a test of another name or with others."""
    pytest.importorskip("xdist")
    project = _pytest_project(tmp_path, {"test_clamp.py": _IN_A_CLASS_WITH_IDS, "test_other.py": _OTHER})
    (project / "calc.py").write_text(
        _CLAMP + "\n\ndef label(x):\n    return f'x{x}'\n", encoding="utf-8", newline="\n"
    )
    row = _pytest_row(flags, "if x > hi:")
    row.update(anchor="return f'x{x}'", replacement="return x.name")
    proc = _run_table(project, [row], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1


_SETUP_ERROR_IN_A_CLASS = (
    "import pytest\nfrom calc import clamp\n\n\n@pytest.fixture\ndef bound():\n"
    "    if clamp(9, 5) != 5:\n        raise RuntimeError('bound')\n    return 5\n\n\n"
    "class TestClamp:\n    def test_clamp_at_the_bound(self, bound):\n        assert bound == 5\n"
)


@pytest.mark.parametrize("flags", ["-q --tb=no -n 2", "-qq --tb=no -n 2"])
def test_a_setup_error_of_a_test_in_a_class_still_kills(tmp_path, flags):
    """The twin: a test in a class whose fixture raises is listed as `ERROR
    <path>::TestClamp::test_clamp_at_the_bound`, an id that ends at the test,
    and it still kills. Read as a class for the capital letter inside its id,
    it read 0 failed."""
    pytest.importorskip("xdist")
    project = _pytest_project(tmp_path, {"test_clamp.py": _SETUP_ERROR_IN_A_CLASS, "test_other.py": _OTHER})
    proc = _run_table(project, [_pytest_row(flags, "if False:")], _ci_env(False))
    assert _ledger_rows(proc.stdout)[0][0].startswith("KILLED"), proc.stdout + proc.stderr
    assert proc.returncode == 0


def _two_runs_project(tmp_path: Path) -> Path:
    """tests_a and tests_c each hold a module that fails to collect under the
    mutant, and tests_b the row's test, whose fixture raises under it."""
    project = _pytest_project(tmp_path, {})
    for folder, body in (("tests_a", _IMPORT_TIME), ("tests_b", _SETUP_ERROR_KILL), ("tests_c", _IMPORT_TIME)):
        (project / folder).mkdir()
        (project / folder / "test_mod.py").write_text(body, encoding="utf-8", newline="\n")
        (project / folder / "test_other.py").write_text(
            _OTHER.replace("test_other", f"test_other_{folder}"), encoding="utf-8", newline="\n"
        )
    return project


@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("-q -rN -n 2 tests_a", "-q --tb=no -n 2 tests_c", ("MISATTRIBUTED", _ZERO_FAILED)),
        ("-q --tb=no -rN tests_a", "-q --tb=no -n 2 tests_c", ("MISATTRIBUTED", _ZERO_FAILED)),
        ("-qq tests_a", "-q tests_b", _EXACTLY),
        ("-q tests_a", "-qq tests_b", _UNPARSEABLE),
        ("-qq tests_a", "-qq tests_b", _UNPARSEABLE),
        ("-q -n 2 tests_a", "-q -n 2 tests_b", _EXACTLY),
        ("-q -rN -n 2 tests_a", "-q -rN -n 2 tests_b", _EXACTLY),
    ],
    ids=[
        "disjoint-signs",
        "disjoint-signs-no-xdist",
        "qq-then-q",
        "q-then-qq",
        "qq-then-qq",
        "same-signs",
        "same-signs-no-summary",
    ],
)
def test_two_pytest_runs_count_their_own_collection_errors(tmp_path, first, second, expected, ci):
    """A command that runs pytest twice had its collection errors counted once
    across both runs, by the sign of them that showed the most. When the two
    runs' flags print different signs (only the `ERROR collecting` header, only
    `Interrupted:`, only the short summary entry), one error stood as a
    failure, a kill by a test of another name. A `-qq` run, which prints no
    stats line, had its collection error taken off the other run's kill, or its
    stop read as the whole command's, so the kill read 0 failed. Each run's
    collection errors now come off its own stats line, and a `-qq` run that
    lists a test leaves the count unknown. The last two cases are the twins:
    two runs that print the same signs were already read right, the second run
    included when it collects every module, so none of the first run's errors
    is taken off its kill."""
    if "-n" in first + second:
        pytest.importorskip("xdist")
    project = _two_runs_project(tmp_path)
    run = f'"{sys.executable}" -m pytest -p no:cacheprovider'
    row = _pytest_row("-q", "if False:")
    # `||`, which cmd.exe reads as bash does: the second run starts only when the first fails.
    row["command"] = f"{run} {first} || {run} {second}"
    proc = _run_table(project, [row], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {0: expected}, proc.stdout + proc.stderr


@pytest.mark.parametrize(
    "capture",
    ["node-spec-one-of-two", "node-spec-alone", "node-tap-one-of-two", "node20-tap-alone", "node20-spec-one-of-two"],
)
def test_a_test_file_node_cannot_load_is_no_kill(tmp_path, capture):
    """Node's test runner reports a test file it cannot load as a failed test
    named after the file, counted in its `fail N`, so the row read
    `MISATTRIBUTED` as a missing name, which the gate reads as another test's
    kill. That test, located at the file's line 1, column 1, no longer counts:
    the row reads 0 failed."""
    project = _project(tmp_path)
    _custom_checker(project, LOAD_FAILURE_CHECKER)
    (project / "capture.txt").write_bytes((LOAD_FAILURES / f"{capture}.txt").read_bytes())
    proc = _run_table(project, [_row(expect_red="clamp at the bound")])
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1


@pytest.mark.parametrize(
    ("capture", "expect_red"),
    [
        ("node-spec-kill-beside-load-failure", "clamp at the bound"),
        ("node-tap-kill-beside-load-failure", "clamp at the bound"),
        ("node-spec-test-named-after-a-file", "calc.mjs"),
    ],
)
def test_a_node_kill_beside_a_load_failure_is_one_kill(tmp_path, capture, expect_red):
    """A kill beside a test file Node could not load read `KILLED+others`
    among 2 failures. The last capture is the twin: a failing test the file
    declares under a file's name, `calc.mjs`, is located where it is declared,
    so it still counts as the kill."""
    project = _project(tmp_path)
    _custom_checker(project, LOAD_FAILURE_CHECKER)
    (project / "capture.txt").write_bytes((LOAD_FAILURES / f"{capture}.txt").read_bytes())
    proc = _run_table(project, [_row(expect_red=expect_red)])
    assert _ledger_rows(proc.stdout) == {0: ("KILLED", f"exactly {expect_red!r} went red")}, (
        proc.stdout + proc.stderr
    )
    assert proc.returncode == 0


@pytest.mark.parametrize("capture", ["node-spec-exits-after-its-tests-pass", "node-tap-exits-after-its-tests-pass"])
def test_a_node_test_file_that_exits_non_zero_after_its_tests_pass_reads_0_failed(tmp_path, capture):
    """Node reports a test file whose tests pass and whose process then exits
    non-zero the same way, a failed test named after the file at its line 1,
    column 1. No test went red, so the row reads 0 failed, a harness error,
    where it read as a kill by a test of another name."""
    project = _project(tmp_path)
    _custom_checker(project, LOAD_FAILURE_CHECKER)
    (project / "capture.txt").write_bytes((LOAD_FAILURES / f"{capture}.txt").read_bytes())
    proc = _run_table(project, [_row(expect_red="clamp at the bound")])
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
@pytest.mark.parametrize(
    ("anchor", "replacement"),
    [
        ("LIMIT = 5;", "LIMIT = = 5;"),
        ("export const FLAG = 'on';", "export const FLAG = 'on';\nprocess.exitCode = 1;"),
    ],
    ids=["cannot-load", "exits-non-zero"],
)
def test_real_node_test_runner_file_failure_is_no_kill(tmp_path, anchor, replacement):
    """The real `node --test`, with whatever reporter this Node defaults to,
    over a test file that cannot load under the mutant, or whose process exits
    non-zero after its tests pass, beside a passing one."""
    (tmp_path / "code.mjs").write_text(
        "export const LIMIT = 5;\nexport const FLAG = 'on';\n", encoding="utf-8", newline="\n"
    )
    (tmp_path / "check.test.mjs").write_text(NODE_TEST_FILE, encoding="utf-8", newline="\n")
    (tmp_path / "other.test.mjs").write_text(
        "import { test } from 'node:test';\ntest('other passes', () => {});\n", encoding="utf-8", newline="\n"
    )
    row = {
        "file": "code.mjs",
        "anchor": anchor,
        "replacement": replacement,
        "command": "node --test check.test.mjs other.test.mjs",
        "expect_red": "limit is pinned",
    }
    proc = _run_table(tmp_path, [row])
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _ZERO_FAILED)}, proc.stdout + proc.stderr
    assert proc.returncode == 1


_FAKE_CARGO = (
    "import sys\nsys.path.insert(0, '.')\nfrom calc import clamp\n"
    "if clamp(9, 5) == 5:\n    raise SystemExit(0)\n"
    "print('test tests::clamp_at_the_bound ... FAILED')\n"
    "print('test result: FAILED. 1 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out')\n"
    "raise SystemExit(101)\n"
)


def test_a_count_another_runner_prints_after_pytest_is_still_read(tmp_path):
    """The twin: pytest passes, then a runner whose count only the fallback
    shapes read fails. Its count lies outside pytest's report, so it is still
    read: a rule that read no fallback shape once pytest ran read this kill 0
    failed."""
    project = _pytest_project(tmp_path, {"test_other.py": _OTHER})
    (project / "fake_cargo.py").write_text(_FAKE_CARGO, encoding="utf-8", newline="\n")
    row = _pytest_row("-q", "if False:", expect_red="clamp_at_the_bound")
    row["command"] += f' && "{sys.executable}" fake_cargo.py'
    proc = _run_table(project, [row])
    assert _ledger_rows(proc.stdout) == {0: ("KILLED", "exactly 'clamp_at_the_bound' went red")}, (
        proc.stdout + proc.stderr
    )
    assert proc.returncode == 0


# --- What a review of #179's fix found -----------------------------------------
#
# A parametrized test's id can hold `::` and a capital letter. A Node test file
# the command's own `timeout` interrupts is counted as cancelled, not failed. A
# Node test file's process can die during a test, which Node reports the way it
# reports a file that cannot load. An `=` rule that is not pytest's opened what
# was read as pytest's report. A `-qq` run's listing sat beside a `0 failed`
# that a later run or another runner printed.
#
# The Node captures (Node 24.21.0, local paths replaced with /home/dev/work):
#   node-spec-exits-during-a-test, node-tap-exits-during-a-test
#                       `node --test cli.test.mjs other.test.mjs`: the mutant
#                       (`args.length === 0` to `!== 0` in cli.mjs) makes the
#                       test `run reads its file` call `process.exit(2)`
#   node-spec-heap-runs-out-during-a-test, node-tap-heap-runs-out-during-a-test
#                       `node --max-old-space-size=64 --test walk.test.mjs`:
#                       the mutant (`if (depth > MAX_DEPTH) break;` to
#                       `if (false) break;` in walk.mjs) makes the test
#                       `depth guard fires` fill the heap
#   node-spec-load-failure-beside-an-exit
#                       `node --test cli.test.mjs loader.test.mjs`: the mutant
#                       (`MODE = 'strict'` to `'loose'` in mode.mjs) makes the
#                       test `run reads its file` call `process.exit(2)`, and
#                       loader.test.mjs fail an assert as it loads
#   node-spec-interrupted-beside-a-kill
#                       `timeout 5 node --test a.test.mjs b.test.mjs`: the
#                       mutant (`LIMIT = 5` to `6` in code.mjs) fails the test
#                       `limit is pinned` in a.test.mjs, and makes b.test.mjs
#                       loop until the timeout stops node

_NEVER_APPEARS = (
    "red, but {!r} never appears beside a failure token - whatever failed, it was not the observer this row claims"
)
_NAMED_PARAMETER = (
    "import pytest\nfrom calc import clamp\n\n\n@pytest.fixture\ndef bound():\n"
    "    if clamp(9, 5) != 5:\n        raise RuntimeError('bound')\n    return 5\n\n\n"
    "@pytest.mark.parametrize('name', ['App::Models::User'])\n"
    "def test_clamp_at_the_bound(bound, name):\n    assert bound == 5\n"
)


@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize("flags", ["-q", "-q --tb=no -n 2", "-qq -n 2"])
def test_a_setup_error_of_a_test_whose_parameter_holds_a_class_path_still_kills(tmp_path, flags, ci):
    """The twin of the class rule at a parametrized id: pytest lists the kill
    as `ERROR <path>::test_clamp_at_the_bound[App::Models::User]`, and the part
    after its last `::`, `User]`, starts with a capital letter. Read as a class
    pytest could not collect, the kill came off the stats line's `1 error` and
    read 0 failed, a row that cannot run."""
    if "-n" in flags:
        pytest.importorskip("xdist")
    project = _pytest_project(tmp_path, {"test_names.py": _NAMED_PARAMETER, "test_other.py": _OTHER})
    proc = _run_table(project, [_pytest_row(flags, "if False:")], _ci_env(ci))
    assert _ledger_rows(proc.stdout)[0][0].startswith("KILLED"), proc.stdout + proc.stderr
    assert proc.returncode == 0


def test_a_node_kill_beside_a_file_the_command_interrupts_is_one_kill(tmp_path):
    """A `timeout` around `node --test` stops a file the mutant makes loop.
    Node counts that file as cancelled, not in `fail N`, though it reports the
    file's own test failed at its line 1, column 1. Taken off `fail 1`, which
    counted only the row's kill, it made the kill read 0 failed, a row that
    cannot run."""
    project = _project(tmp_path)
    _custom_checker(project, LOAD_FAILURE_CHECKER)
    (project / "capture.txt").write_bytes((LOAD_FAILURES / "node-spec-interrupted-beside-a-kill.txt").read_bytes())
    proc = _run_table(project, [_row(expect_red="limit is pinned")])
    assert _ledger_rows(proc.stdout) == {0: ("KILLED", "exactly 'limit is pinned' went red")}, (
        proc.stdout + proc.stderr
    )
    assert proc.returncode == 0


@pytest.mark.parametrize(
    ("capture", "expect_red"),
    [
        ("node-spec-exits-during-a-test", "run reads its file"),
        ("node-tap-exits-during-a-test", "run reads its file"),
        ("node-spec-heap-runs-out-during-a-test", "depth guard fires"),
        ("node-tap-heap-runs-out-during-a-test", "depth guard fires"),
        ("node-spec-load-failure-beside-an-exit", "run reads its file"),
    ],
)
def test_a_node_test_file_whose_process_dies_during_a_test_reads_as_a_kill(tmp_path, capture, expect_red):
    """A process that dies during a test (an exit the mutant makes the test
    reach, a heap the test fills) never reports that test, and Node reports
    its file as it reports one that cannot load. Taken off the count, it read
    0 failed, a row that cannot run, though the row's own test went red. Node
    printed no load error for it, so it counts: the row reads as a kill whose
    name never appears. In the last capture another file fails to load, and
    only that file's test comes off the count."""
    project = _project(tmp_path)
    _custom_checker(project, LOAD_FAILURE_CHECKER)
    (project / "capture.txt").write_bytes((LOAD_FAILURES / f"{capture}.txt").read_bytes())
    proc = _run_table(project, [_row(expect_red=expect_red)])
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _NEVER_APPEARS.format(expect_red))}, (
        proc.stdout + proc.stderr
    )
    assert proc.returncode == 1


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_real_node_test_file_that_exits_during_a_test_reads_as_a_kill(tmp_path):
    """The real `node --test`, with whatever reporter this Node defaults to,
    over a test file whose test reaches `process.exit(2)` under the mutant,
    beside a passing one."""
    (tmp_path / "cli.mjs").write_text(
        "export function run(args) {\n  if (args.length === 0) {\n    process.exit(2);\n  }\n"
        "  return `read ${args[0]}`;\n}\n",
        encoding="utf-8",
        newline="\n",
    )
    (tmp_path / "cli.test.mjs").write_text(
        "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"
        "import { run } from './cli.mjs';\n"
        "test('run reads its file', () => { assert.equal(run(['a.txt']), 'read a.txt'); });\n",
        encoding="utf-8",
        newline="\n",
    )
    (tmp_path / "other.test.mjs").write_text(
        "import { test } from 'node:test';\ntest('other passes', () => {});\n", encoding="utf-8", newline="\n"
    )
    row = {
        "file": "cli.mjs",
        "anchor": "if (args.length === 0) {",
        "replacement": "if (args.length !== 0) {",
        "command": "node --test cli.test.mjs other.test.mjs",
        "expect_red": "run reads its file",
    }
    proc = _run_table(tmp_path, [row])
    assert _ledger_rows(proc.stdout) == {0: ("MISATTRIBUTED", _NEVER_APPEARS.format("run reads its file"))}, (
        proc.stdout + proc.stderr
    )
    assert proc.returncode == 1


# A Node run whose one test passes and prints a banner, as `console.log` writes it.
_FAKE_NODE = (
    "import sys\n"
    "sys.stdout.buffer.write('\\u2714 other passes (0.4ms)\\n=== fixtures seeded ===\\n"
    "\\u2139 tests 1\\n\\u2139 pass 1\\n\\u2139 fail 0\\n'.encode('utf-8'))\n"
)


@pytest.mark.parametrize("before", ["a-banner", "node-prints-a-banner", "pytest-then-a-banner"])
def test_a_rule_pytest_did_not_print_hides_no_count(tmp_path, before):
    """Any `=` rule with text in it opened what was read as pytest's report,
    with no pytest run at all, so no count after it was read: a script's
    `===== rust =====` before cargo's count, or `=== fixtures seeded ===` that
    a passing Node test prints, made cargo's kill read 0 failed or lose its
    count. Only the rules of pytest's own sections open its report now."""
    project = _pytest_project(tmp_path, {"test_other.py": _OTHER})
    (project / "fake_cargo.py").write_text(_FAKE_CARGO, encoding="utf-8", newline="\n")
    (project / "banner.py").write_text("print('===== rust =====')\n", encoding="utf-8", newline="\n")
    (project / "fake_node.py").write_text(_FAKE_NODE, encoding="utf-8", newline="\n")
    run = f'"{sys.executable}"'
    first = {
        "a-banner": f"{run} banner.py",
        "node-prints-a-banner": f"{run} fake_node.py",
        "pytest-then-a-banner": f"{run} -m pytest -q -p no:cacheprovider tests && {run} banner.py",
    }[before]
    row = _pytest_row("-q", "if False:", expect_red="clamp_at_the_bound")
    row["command"] = f"{first} && {run} fake_cargo.py"
    proc = _run_table(project, [row])
    assert _ledger_rows(proc.stdout) == {0: ("KILLED", "exactly 'clamp_at_the_bound' went red")}, (
        proc.stdout + proc.stderr
    )
    assert proc.returncode == 0


@pytest.mark.parametrize(
    "body",
    [
        "def test_other():\n    print('batch: 2 failed')\n",
        "import warnings\n\n\ndef test_other():\n    warnings.warn('retry 3 failed')\n",
    ],
    ids=["passes-section", "warnings-section"],
)
def test_a_count_pytest_quotes_before_another_runner_is_not_read(tmp_path, body):
    """The twin: a passing test's output, which `-rA` quotes in pytest's
    PASSES section, and its warning, which the warnings summary quotes, open
    pytest's report when no failure section comes first, so neither count is
    read before cargo's."""
    project = _pytest_project(tmp_path, {"test_other.py": body})
    (project / "fake_cargo.py").write_text(_FAKE_CARGO, encoding="utf-8", newline="\n")
    row = _pytest_row("-q -rA", "if False:", expect_red="clamp_at_the_bound")
    row["command"] += f' && "{sys.executable}" fake_cargo.py'
    proc = _run_table(project, [row])
    assert _ledger_rows(proc.stdout) == {0: ("KILLED", "exactly 'clamp_at_the_bound' went red")}, (
        proc.stdout + proc.stderr
    )
    assert proc.returncode == 0


# Runs pytest once for each argument, in turn, and exits with the worst code,
# as `;` and `exit $((a|b))` would in bash, but under cmd.exe too.
_RUN_EACH = (
    "import subprocess\nimport sys\n\n"
    "codes = [\n"
    "    subprocess.call([sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider', *flags.split()])\n"
    "    for flags in sys.argv[1:]\n"
    "]\n"
    "sys.exit(max(codes))\n"
)
_PASSING_CARGO = (
    "print('running 3 tests')\n"
    "print('test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s')\n"
)


@pytest.mark.parametrize("ci", [False, True], ids=["no-ci", "ci"])
@pytest.mark.parametrize("kill", [_AT_THE_BOUND, _SETUP_ERROR_KILL], ids=["assert", "setup-error"])
@pytest.mark.parametrize(
    "command",
    [
        'run_each.py "-qq tests_b" "-q tests_c"',
        'run_each.py "-qq -n 2 tests_b" "-q -n 2 tests_c"',
        "passing_cargo.py && {pytest} -qq tests_b",
    ],
    ids=["qq-then-passing-q", "qq-then-passing-q-xdist", "passing-cargo-then-qq"],
)
def test_a_qq_run_that_lists_a_kill_leaves_the_count_unknown(tmp_path, command, kill, ci):
    """A `-qq` run prints no stats line, so no count holds the kill it lists.
    A passing `-q` run after it prints no `test session starts` and no report
    rule, so the `-qq` run's listing was read as the `-q` run's and dropped at
    its `1 passed`, and a `0 failed` another runner printed was taken for the
    count: both read the kill 0 failed, a row that cannot run. A `-q` run's
    progress line now opens a run of its own, and a `-qq` run that lists a
    test leaves the count unknown whatever else the command printed."""
    if "-n" in command:
        pytest.importorskip("xdist")
    project = _pytest_project(tmp_path, {})
    for folder, body in (("tests_b", kill), ("tests_c", _OTHER)):
        (project / folder).mkdir()
        (project / folder / f"test_{folder}.py").write_text(body, encoding="utf-8", newline="\n")
    (project / "run_each.py").write_text(_RUN_EACH, encoding="utf-8", newline="\n")
    (project / "passing_cargo.py").write_text(_PASSING_CARGO, encoding="utf-8", newline="\n")
    run = f'"{sys.executable}"'
    row = _pytest_row("-q", "if False:")
    row["command"] = f"{run} " + command.format(pytest=f"{run} -m pytest -p no:cacheprovider")
    proc = _run_table(project, [row], _ci_env(ci))
    assert _ledger_rows(proc.stdout) == {0: _UNPARSEABLE}, proc.stdout + proc.stderr
    assert proc.returncode == 0
