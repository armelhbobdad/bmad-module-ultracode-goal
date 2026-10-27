#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for mem_observation.py (Cross-Session Recall write / drain).

Risk-named, hermetic. The CLI is exercised via subprocess so the real
stdin/stdout contract is tested. GIT_* env is scrubbed so repo_fingerprint()
runs against the temp repos these tests build.

The tests (the CSR-* rows of the cross-session recall test design whose target
is this file) drive ``write`` and ``drain --store`` as subprocesses and read the
store back through lib/mem_common, the reader ``mem_recall.py filter --store``
uses. Every store test points HOME and USERPROFILE at tmp_path, so nothing
reaches the real home. An unwritable store is a store path whose parent is a
regular file, which fails the same way on Linux and Windows. The claude-mem
forms (``build``, ``spill`` and a drain without ``--store``) are gone; their
tests retired with them, except the payload checks, which now run through
``write``, and each removed form's exit 2.

Run: uv run --with pytest pytest test_mem_observation.py -v
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "mem_observation.py"
sys.path.insert(0, str(SCRIPT.parent))

from lib import mem_common as mc  # noqa: E402  (after sys.path mutation)

MARKER = "[ucg-payload:v1]"

_GIT_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
)


@pytest.fixture(autouse=True)
def _hermetic_git_env(monkeypatch):
    for var in _GIT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", "https://github.com/acme/widget.git")


def _run(*args: str, stdin: str | None = None):
    # PYTHONIOENCODING=cp1252 simulates the hostile Windows console default on
    # every platform; the script must pin its own streams to UTF-8 (regression
    # guard for the windows-latest UnicodeEncodeError CI failure).
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", input=stdin,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )


# ===========================================================================
# write and drain --store
# ===========================================================================

_HAS_GIT = shutil.which("git") is not None
_needs_git = pytest.mark.skipif(not _HAS_GIT, reason="git not on PATH")

_RUN = "epic-7-20260604T172512Z"
_RUN_B = "epic-7-20260605T090000Z"
_RUN_C = "epic-7-20260606T090000Z"
_DATE = "2026-06-04T17:25:12Z"
_DATE_MS = int(datetime(2026, 6, 4, 17, 25, 12, tzinfo=timezone.utc).timestamp()) * 1000
# Thirty days after _DATE: a legacy entry spilled at build time is 30 days old.
_NOW = datetime(2026, 7, 4, 17, 25, 12, tzinfo=timezone.utc)
_NOW_MS = int(_NOW.timestamp()) * 1000
_DEAD = "mem-outbox.dead.jsonl"
_STORE_DRAIN_COUNTS = (
    "converted", "dead_lettered", "deferred", "legacy_unconvertible", "run_id_invalid",
    "skipped_existing", "target_foreign", "tombstones", "written",
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point HOME and USERPROFILE at one tmp folder (expanduser reads either)."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    return home_dir


def _repo(tmp_path: Path, name: str = "widget") -> Path:
    repo = tmp_path / name
    _init_repo(repo)
    return repo


def _run_in(cwd: Path, *args: str):
    """_run with the script's process cwd pinned (where a relative value would land)."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", cwd=str(cwd),
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )


def _write(impl: Path, store: object, repo: Path, run_id: str = _RUN, *extra: str, cwd: Path | None = None):
    args = (
        "write", "--impl-artifacts", str(impl), "--store", str(store),
        "--epic", "7", "--run-id", run_id, "--gate-status", "PASS",
        "--verdict", "advance", "--cwd", str(repo), "--valid-until-date", _DATE, *extra,
    )
    return _run(*args) if cwd is None else _run_in(cwd, *args)


def _drain(impl: Path, store: object, *extra: str):
    return _run("drain", "--impl-artifacts", str(impl), "--store", str(store), *extra)


def _out(proc) -> dict:
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _recall_filter(impl: Path, store: Path, repo: Path, *extra: str):
    """The real reader: `mem_recall.py filter --store`, as Ingest calls it."""
    return subprocess.run(
        [
            sys.executable, str(SCRIPT.parent / "mem_recall.py"), "filter",
            "--impl-artifacts", str(impl), "--store", str(store), "--cwd", str(repo), *extra,
        ],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )


def _runs_of(store: Path, repo: Path) -> Path:
    return mc.runs_dir(store, mc.repo_fingerprint(repo)["value"])


def _jsonl_names(runs: Path) -> list[str]:
    return sorted(p.name for p in runs.iterdir() if p.name.endswith(".jsonl"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _blocked_store(tmp_path: Path) -> Path:
    """A store path whose parent is a regular file: mkdir fails on every OS."""
    blocker = tmp_path / "blocker"
    if not blocker.exists():
        blocker.write_text("a regular file, not a directory")
    return blocker / "store"


def _spill_raw(impl: Path, run_id: str, payload: dict, attempts: int, spilled_at: str) -> None:
    impl.mkdir(parents=True, exist_ok=True)
    entry = {"payload": payload, "attempts": attempts, "spilled_at": spilled_at}
    with (impl / f"mem-outbox.{run_id}.jsonl").open("a", encoding="utf-8") as h:
        h.write(json.dumps(entry, sort_keys=True) + "\n")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_lines(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in entries), encoding="utf-8"
    )


def _spill_via_write(tmp_path: Path, impl: Path, repo: Path, run_id: str, *extra: str) -> dict:
    """A real deferred store write: `write` against an unwritable store spills it."""
    out = _out(_write(impl, _blocked_store(tmp_path), repo, run_id, *extra))
    assert out["status"] == "deferred"
    return _lines(impl / f"mem-outbox.{run_id}.jsonl")[-1]


def _legacy_wrapper(repo: Path, run_id: str = _RUN) -> dict:
    """A claude-mem era outbox payload for this repo, shaped as the removed
    ``build`` printed it: a summary line, the marker, then the run payload as
    fenced JSON, wrapped in ``{text,title,project}``."""
    fingerprint = mc.repo_fingerprint(repo)["value"]
    sig = hashlib.sha1(f"race-condition|src/x.py|{fingerprint}".encode()).hexdigest()[:12]
    inner = _inner(
        run_id=run_id,
        fingerprint=fingerprint,
        signatures=[{"class": "race-condition", "path": "src/x.py", "sig": sig}],
    )
    return {
        "text": (
            "UCG run for epic 7: gate PASS, verdict advance, 1 signature(s), 0 deferred.\n"
            f"{MARKER}\n```json\n{json.dumps(inner, sort_keys=True)}\n```"
        ),
        "title": "UCG run, epic 7: advance",
        "project": "widget",
    }


def _hand_legacy(body: str) -> dict:
    """A legacy {text,title,project} payload around an arbitrary fenced body."""
    return {
        "text": f"UCG run for epic 7: gate PASS.\n{MARKER}\n```json\n{body}\n```",
        "title": "UCG run epic 7: advance",
        "project": "widget",
    }


def _inner(**overrides) -> dict:
    inner = {
        "ucg": 1, "schema_version": 1, "kind": "run-summary", "epic": "7",
        "run_id": _RUN, "fingerprint": "0123456789abcdef", "gate_status": "PASS",
        "verdict": "advance", "valid_until": {"sha": None, "date": _DATE},
        "signatures": [], "deferred_count": 0, "advisories": [],
    }
    inner.update(overrides)
    return inner


# --- write: the run file (AC-1, AC-2) ---------------------------------------


def _signature(cls: str, path: str, fingerprint: str) -> str:
    """sha1(class|path|fingerprint)[:12], the signature write computes."""
    return hashlib.sha1(f"{cls}|{path}|{fingerprint}".encode()).hexdigest()[:12]


def _record_of(tmp_path: Path, repo: Path, *extra: str) -> dict:
    """The record `write` stores for _RUN in a fresh store, with ``extra`` flags
    added (a repeated flag replaces the default _write passes)."""
    out = _out(_write(tmp_path / "impl", tmp_path / "store", repo, _RUN, *extra))
    assert out["status"] == "written", out
    return json.loads(Path(out["path"]).read_text(encoding="utf-8"))


@_needs_git
def test_write_creates_exactly_one_run_file_holding_the_run_payload(tmp_path, home):
    # CSR-INT-001 (AC-1): the run payload (the fields the removed build
    # embedded, without the claude-mem wrapper), plus created_at_epoch
    # (integer UTC ms, stamped now) and project (the main worktree's
    # directory name).
    repo = _repo(tmp_path)
    store = tmp_path / "store"
    extra = ("--root-cause", "class=race-condition,path=src/x.py",
             "--advisory", "sig=abc123def456,recurred=yes")
    before = mc.utc_now_epoch_ms()
    out = _out(_write(tmp_path / "impl", store, repo, _RUN, *extra))
    after = mc.utc_now_epoch_ms()

    runs = _runs_of(store, repo)
    run_file = runs / f"{_RUN}.jsonl"
    assert out == {"status": "written", "path": str(run_file), "notes": []}
    assert _jsonl_names(runs) == [f"{_RUN}.jsonl"]
    text = run_file.read_text(encoding="utf-8")
    assert text.endswith("\n") and len(text.splitlines()) == 1
    record = json.loads(text)

    fingerprint = mc.repo_fingerprint(repo)["value"]
    payload = {
        "ucg": 1,
        "schema_version": 1,
        "kind": "run-summary",
        "epic": "7",
        "run_id": _RUN,
        "fingerprint": fingerprint,
        "gate_status": "PASS",
        "verdict": "advance",
        "valid_until": {"sha": None, "date": _DATE},
        "signatures": [
            {"class": "race-condition", "path": "src/x.py",
             "sig": _signature("race-condition", "src/x.py", fingerprint)},
        ],
        "deferred_count": 0,
        "advisories": [{"sig": "abc123def456", "recurred": "yes"}],
    }
    assert {k: v for k, v in record.items() if k not in ("created_at_epoch", "project")} == payload
    assert set(record) == set(payload) | {"created_at_epoch", "project"}
    assert "text" not in record and "title" not in record
    assert isinstance(record["created_at_epoch"], int)
    assert before <= record["created_at_epoch"] <= after
    assert record["project"] == "widget"
    assert mc.validate_record(record) == mc.RECORD_OK
    if sys.platform != "win32":
        # Write step 1 lets a Windows scanner keep the temp; elsewhere none is left.
        assert not [p.name for p in runs.iterdir() if p.name.endswith(".tmp")]
    # Nothing spilled or dead-lettered on the happy path.
    assert not (tmp_path / "impl").exists()


# --- write: the run payload (the checks the removed build carried) -----------


@_needs_git
def test_write_waived_gate_writes_its_record(tmp_path, home):
    # NOT_EVALUATED is written only with verdict blocked
    # (test_write_a_run_that_blocked_with_no_gate_evaluated_writes_its_record);
    # a WAIVED outcome is a real one and is written.
    record = _record_of(tmp_path, _repo(tmp_path), "--gate-status", "waived")
    assert record["gate_status"] == "WAIVED"
    assert record["verdict"] == "advance"
    assert (record["ucg"], record["schema_version"], record["kind"]) == (1, 1, "run-summary")
    assert record["fingerprint"]  # a real fingerprint was pinned


@_needs_git
def test_write_maps_an_unknown_root_cause_class_to_other(tmp_path, home):
    record = _record_of(tmp_path, _repo(tmp_path), "--root-cause", "class=not-a-real-class,path=src/x.py")
    assert record["signatures"][0]["class"] == "other"


@_needs_git
def test_write_root_cause_signature_is_sha1_12_of_class_path_and_fingerprint(tmp_path, home):
    repo = _repo(tmp_path)
    record = _record_of(tmp_path, repo, "--root-cause", "class=race-condition,path=src/x.py")
    (sig,) = record["signatures"]
    assert sig["class"] == "race-condition"
    assert sig["sig"] == _signature("race-condition", "src/x.py", mc.repo_fingerprint(repo)["value"])
    assert len(sig["sig"]) == 12 and all(c in "0123456789abcdef" for c in sig["sig"])


@_needs_git
def test_write_redacts_known_secrets(tmp_path, home):
    # An AKIA key in a root-cause path and a ghp_ token in the verdict never
    # reach the run file.
    record = _record_of(
        tmp_path, _repo(tmp_path),
        "--verdict", "advance ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "--root-cause", "class=security,path=AKIAIOSFODNN7EXAMPLE/creds.txt",
    )
    text = json.dumps(record)
    assert "AKIAIOSFODNN7EXAMPLE" not in text
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in text
    assert "[redacted]" in record["verdict"]
    assert "[redacted]" in record["signatures"][0]["path"]


@_needs_git
def test_write_redacts_an_advisory_sig(tmp_path, home):
    record = _record_of(tmp_path, _repo(tmp_path), "--advisory", "sig=token=supersecretvalue123,recurred=yes")
    (advisory,) = record["advisories"]
    assert advisory["recurred"] == "yes"
    assert "supersecretvalue123" not in advisory["sig"]


@_needs_git
def test_write_normalizes_an_unknown_advisory_recurred_value(tmp_path, home):
    record = _record_of(tmp_path, _repo(tmp_path), "--advisory", "sig=abc,recurred=maybe")
    assert record["advisories"] == [{"sig": "abc", "recurred": "unknown"}]


DEFERRED_LEDGER = """# Deferred Work

## Epic 7 deferred

- skip flaky integration test for now
- backfill perf benchmark
- harden the retry path

## Epic 8 deferred

- unrelated item
"""

PREFIX_COLLIDING_LEDGER = """# Deferred Work

## Epic 1 deferred

- the one item Epic 1 actually parked

## Epic 11 deferred

- eleven's first
- eleven's second
- eleven's third
- eleven's fourth
"""


@_needs_git
@pytest.mark.parametrize(
    "ledger, epic, expected",
    [
        (DEFERRED_LEDGER, "7", 3),
        # Epic `1` must not claim Epic `11`'s parked items: a plain substring
        # test made every epic a prefix of its own successors, and the count
        # reported a neighbour's backlog as this run's, a number the record
        # an autonomous run leaves behind carries to the next one.
        (PREFIX_COLLIDING_LEDGER, "1", 1),
        # Its twin: the boundary is not so tight that a real heading stops matching.
        (PREFIX_COLLIDING_LEDGER, "11", 4),
        (None, "7", 0),
    ],
    ids=["this-epic-only", "no-prefix-match", "own-heading-matches", "absent-ledger"],
)
def test_write_counts_this_epics_deferred_items(tmp_path, home, ledger, epic, expected):
    path = tmp_path / "deferred-work.md"
    if ledger is not None:
        path.write_text(ledger, encoding="utf-8")
    record = _record_of(tmp_path, _repo(tmp_path), "--epic", epic, "--deferred", str(path))
    assert record["epic"] == epic
    assert record["deferred_count"] == expected


@_needs_git
def test_write_passes_valid_until_through(tmp_path, home):
    record = _record_of(
        tmp_path, _repo(tmp_path), "--valid-until-sha", "abc123", "--valid-until-date", "2026-12-31T00:00:00Z",
    )
    assert record["valid_until"] == {"sha": "abc123", "date": "2026-12-31T00:00:00Z"}


@_needs_git
def test_write_project_is_the_main_worktree_name_from_a_linked_worktree(tmp_path, home):
    # project is display only and derived by the script, never passed: a
    # linked worktree reports the main checkout's name and shares its folder.
    repo = _repo(tmp_path)
    worktree = tmp_path / "feature-wt"
    _git(repo, "worktree", "add", "-q", str(worktree))
    store = tmp_path / "store"
    out = _out(_write(tmp_path / "impl", store, worktree))
    assert out["status"] == "written"
    record = json.loads(Path(out["path"]).read_text(encoding="utf-8"))
    assert record["project"] == "widget"
    assert Path(out["path"]).parent == _runs_of(store, repo)


@_needs_git
def test_write_replay_prints_skipped_existing_and_leaves_the_file_byte_identical(tmp_path, home):
    # CSR-INT-002 (AC-2).
    repo = _repo(tmp_path)
    store = tmp_path / "store"
    impl = tmp_path / "impl"
    first = _out(_write(impl, store, repo))
    run_file = Path(first["path"])
    before = _sha(run_file)
    proc = _write(impl, store, repo)
    assert proc.returncode == 0
    assert "skipped-existing" in proc.stdout
    out = json.loads(proc.stdout)
    assert out == {"status": "skipped-existing", "path": str(run_file), "notes": []}
    assert _sha(run_file) == before
    assert not impl.exists()  # no spill, no dead-letter


# --- write: a target it must never touch (AC-3, AC-25) ----------------------


@_needs_git
@pytest.mark.parametrize("content", [
    b"{not json at all\n",
    # Nested past the recursion limit: json.loads raises RecursionError, not
    # ValueError, so it once escaped the write with exit 1 and nothing parked.
    ("[" * 100000 + "]" * 100000).encode(),
], ids=["unparseable", "nested-past-the-recursion-limit"])
def test_write_never_touches_an_unparseable_target_and_dead_letters_the_entry(tmp_path, home, content):
    # CSR-INT-003 (AC-3, AC-25): untouched, dead-lettered at once with the
    # pinned token on stdout, nothing spilled.
    repo = _repo(tmp_path)
    store = tmp_path / "store"
    impl = tmp_path / "impl"
    target = _runs_of(store, repo) / f"{_RUN}.jsonl"
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    before = _sha(target)

    proc = _write(impl, store, repo)
    assert proc.returncode == 0
    assert "NOTE mem-target-foreign" in proc.stdout
    out = json.loads(proc.stdout)
    assert out["status"] == "foreign-target"
    assert [n.split(":", 1)[0] for n in out["notes"]] == ["NOTE mem-target-foreign"]
    assert _sha(target) == before
    dead = _lines(impl / _DEAD)
    assert len(dead) == 1
    assert dead[0]["payload"]["run_id"] == _RUN
    assert dead[0]["attempts"] == 0
    assert dead[0]["note"] == "NOTE mem-target-foreign"
    assert not (impl / f"mem-outbox.{_RUN}.jsonl").exists()


@_needs_git
@pytest.mark.parametrize("field, value", [
    ("fingerprint", "ffffffffffffffff"),
    ("run_id", _RUN_B),
])
def test_write_never_touches_a_parseable_record_of_another_run_or_repo(tmp_path, home, field, value):
    # CSR-INT-004 (AC-3, AC-25): a valid record at this path whose fingerprint
    # (or run_id) is not this write's is foreign, not skipped-existing.
    repo = _repo(tmp_path)
    store = tmp_path / "store"
    impl = tmp_path / "impl"
    target = Path(_out(_write(impl, store, repo))["path"])
    record = json.loads(target.read_text(encoding="utf-8"))
    record[field] = value
    target.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    before = _sha(target)

    out = _out(_write(impl, store, repo))
    assert out["status"] == "foreign-target"
    assert out["notes"][0].startswith("NOTE mem-target-foreign")
    assert _sha(target) == before
    assert [e["note"] for e in _lines(impl / _DEAD)] == ["NOTE mem-target-foreign"]
    assert not (impl / f"mem-outbox.{_RUN}.jsonl").exists()


@_needs_git
@pytest.mark.skipif(os.name != "posix", reason="argv carries bytes only on POSIX")
def test_write_replaces_an_argument_byte_that_is_not_utf8(tmp_path, home):
    # Python decodes a non-UTF-8 argv byte to a lone surrogate, which UTF-8
    # cannot encode: a root-cause path holding one made the signature hash
    # raise, and a verdict holding one stayed in the record for good. Each
    # becomes U+FFFD, and the record reads back through the filter.
    repo = _repo(tmp_path)
    store = tmp_path / "store"
    impl = tmp_path / "impl"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "write", "--impl-artifacts", str(impl), "--store", str(store),
         "--epic", b"7\xff", "--run-id", _RUN, "--gate-status", b"PASS\xfe", "--verdict", b"advance \xff",
         "--root-cause", b"class=build-error,path=src/\xff.py", "--advisory", b"sig=\xfe,recurred=yes",
         "--cwd", str(repo), "--valid-until-date", _DATE],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    out = _out(proc)
    assert out["status"] == "written"
    record = json.loads(Path(out["path"]).read_text(encoding="utf-8"))
    fingerprint = mc.repo_fingerprint(repo)["value"]
    assert (record["epic"], record["gate_status"], record["verdict"]) == ("7\ufffd", "PASS\ufffd", "advance \ufffd")
    assert record["signatures"] == [{
        "class": "build-error", "path": "src/\ufffd.py",
        "sig": _signature("build-error", "src/\ufffd.py", fingerprint),
    }]
    assert record["advisories"] == [{"sig": "\ufffd", "recurred": "yes"}]
    read = _recall_filter(impl, store, repo)
    assert read.returncode == 0, read.stderr
    assert [r["id"] for r in json.loads(read.stdout)["records"]] == [_RUN]


# --- write: run_id check (AC-4) ---------------------------------------------


@pytest.mark.parametrize("run_id", [
    "epic-7/x-20260604T172512Z",
    "epic-7\\x-20260604T172512Z",
    "epic-..-20260604T172512Z",
    "../epic-7-20260604T172512Z",
    "r1",
])
def test_write_rejects_a_bad_run_id_with_exit_2_before_touching_anything(tmp_path, home, run_id):
    # CSR-UNIT-002 (AC-4): exits 2 before any git call, so no repo is needed;
    # no store root, no outbox, no dead-letter file. build and spill, the
    # other two commands that took --run-id, are removed and exit 2 before
    # reading anything (test_removed_claude_mem_forms_exit_2_naming_their_replacement).
    store = tmp_path / "store"
    impl = tmp_path / "impl"
    proc = _write(impl, store, tmp_path, run_id)
    assert proc.returncode == 2
    assert "invalid run_id" in json.loads(proc.stdout)["error"]
    assert not store.exists()
    assert not impl.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["home"]


# --- write: unset store, no fingerprint, NOT_EVALUATED ----------------------


@pytest.mark.parametrize("value", [
    "", "   ", "{project-root}/recall", "{output_folder}/recall", "$HOME/recall", "${HOME}/recall",
    "%USERPROFILE%\\.ultracode-goal\\recall", "relative/recall",
])
def test_write_with_an_unset_store_writes_nothing_and_names_the_key(tmp_path, home, value):
    work = tmp_path / "work"
    work.mkdir()
    impl = tmp_path / "impl"
    out = _out(_write(impl, value, work, _RUN, cwd=work))
    assert out["status"] == "store-unset"
    assert len(out["notes"]) == 1
    assert out["notes"][0].startswith("NOTE recall-store-unset")
    assert "cross_session_recall_store" in out["notes"][0]
    assert list(work.iterdir()) == []
    assert not impl.exists()


def test_a_bare_store_flag_counts_as_unset_for_write_and_drain(tmp_path, home):
    # An empty config value substituted unquoted leaves `--store` with no
    # value; it parses as unset instead of failing the call.
    impl = tmp_path / "impl"
    work = tmp_path / "work"
    work.mkdir()
    out = _out(_run(
        "write", "--impl-artifacts", str(impl), "--store",
        "--epic", "7", "--run-id", _RUN, "--gate-status", "PASS",
        "--verdict", "advance", "--cwd", str(work),
    ))
    assert out["status"] == "store-unset"
    assert out["notes"][0].startswith("NOTE recall-store-unset")
    drained = _out(_run("drain", "--impl-artifacts", str(impl), "--store", "--now-epoch", str(_NOW_MS)))
    assert drained["store"] is None
    assert drained["notes"][0].startswith("NOTE recall-store-unset")
    assert list(work.iterdir()) == [] and not impl.exists()


@_needs_git
def test_write_resolves_project_root_only_when_it_is_given(tmp_path, home):
    repo = _repo(tmp_path)
    out = _out(_write(
        tmp_path / "impl", "{project-root}/.ucg-recall", repo, _RUN, "--project-root", str(repo),
    ))
    assert out["status"] == "written"
    assert Path(out["path"]).parent == _runs_of(repo / ".ucg-recall", repo)


@_needs_git
def test_write_in_a_repo_with_zero_commits_creates_no_run_file_and_no_none_folder(tmp_path, home):
    # CSR-INT-038: repo_fingerprint gives no value. The latch half goes through
    # measure_latch_v2, which the latch CLI writes; neither creates a folder.
    repo = tmp_path / "empty"
    repo.mkdir()
    _git(repo, "init", "-q")
    store = tmp_path / "store"
    out = _out(_write(tmp_path / "impl", store, repo))
    assert out["status"] == "no-fingerprint"
    assert not store.exists()
    assert not (tmp_path / "impl").exists()

    measure = mc.measure_latch_v2(run_id=_RUN, recall="on", store_value=str(store), cwd=repo)
    assert measure.state["store_ok"] is False
    assert measure.reason == "no-fingerprint"
    assert not (store / "None").exists()
    assert not store.exists() or not list(store.rglob("*.jsonl"))


@_needs_git
@pytest.mark.parametrize("gate", ["NOT_EVALUATED", " not_evaluated "])
def test_write_a_run_that_blocked_with_no_gate_evaluated_writes_its_record(tmp_path, home, gate):
    # A run that escalated or handed off before Stage 5, or whose gate could
    # not be read, still blocked: the next run's recall must see it.
    record = _record_of(tmp_path, _repo(tmp_path), "--gate-status", gate, "--verdict", "blocked")
    assert (record["gate_status"], record["verdict"]) == ("NOT_EVALUATED", "blocked")
    assert mc.validate_record(record) == mc.RECORD_OK


@_needs_git
@pytest.mark.parametrize("verdict", ["advance", " Advance "])
def test_write_not_evaluated_gate_with_any_other_verdict_writes_no_record(tmp_path, home, verdict):
    # NOT_EVALUATED never advances (gate_eval maps it to escalate), so that
    # pair would store a false outcome.
    repo = _repo(tmp_path)
    store = tmp_path / "store"
    proc = _run(
        "write", "--impl-artifacts", str(tmp_path / "impl"), "--store", str(store),
        "--epic", "7", "--run-id", _RUN, "--gate-status", "NOT_EVALUATED",
        "--verdict", verdict, "--cwd", str(repo),
    )
    assert _out(proc)["status"] == "skip"
    assert not store.exists()
    assert not (tmp_path / "impl").exists()


@_needs_git
def test_a_pre_gate_blocked_record_reaches_the_reader_and_counts_toward_recurrence(tmp_path, home):
    # A pre-gate escalation that recurs used to read as a first occurrence,
    # since the run that blocked before its gate left no record.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    cause = "class=environment-config,path=_bmad-output/x.md"
    _out(_write(impl, store, repo, _RUN, "--gate-status", "FAIL", "--verdict", "blocked", "--root-cause", cause))
    _out(_write(impl, store, repo, _RUN_B, "--gate-status", "NOT_EVALUATED", "--verdict", "blocked", "--root-cause", cause))
    _out(_write(impl, store, repo, _RUN_C, "--gate-status", "NOT_EVALUATED", "--verdict", "blocked"))
    out = _out(_recall_filter(impl, store, repo, "--epic", "7"))
    assert out["dropped"]["invalid"] == 0
    by_id = {r["id"]: r for r in out["records"]}
    assert by_id[_RUN_B]["title_noun_phrase"] == "UCG run epic 7: gate NOT_EVALUATED, verdict blocked"
    assert by_id[_RUN_B]["recurring"] is True
    # A record with no root cause adds nothing to recurrence.
    assert by_id[_RUN_C]["recurring"] is False
    (entry,) = out["recurrence"]
    assert (entry["class"], entry["count"], entry["run_ids"]) == ("environment-config", 2, [_RUN, _RUN_B])


# --- write: deferral, then a drain lands it (AC-5) ---------------------------


@_needs_git
def test_write_spills_on_an_unwritable_store_and_drain_lands_the_original_time(tmp_path, home):
    # CSR-INT-005 (AC-5, AC-25 WARN token).
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = _blocked_store(tmp_path)
    proc = _write(impl, store, repo)
    assert proc.returncode == 0
    assert "WARN mem-write-deferred" in proc.stdout
    out = json.loads(proc.stdout)
    assert out["status"] == "deferred"
    assert out["notes"][0].startswith("WARN mem-write-deferred")
    outbox = impl / f"mem-outbox.{_RUN}.jsonl"
    assert out["outbox"] == str(outbox)
    entries = _lines(outbox)
    assert len(entries) == 1
    assert set(entries[0]) == {"payload", "attempts", "spilled_at"}
    assert entries[0]["attempts"] == 0
    created = entries[0]["payload"]["created_at_epoch"]
    assert mc.validate_record(entries[0]["payload"]) == mc.RECORD_OK
    assert not (impl / _DEAD).exists()

    (tmp_path / "blocker").unlink()  # the store becomes writable
    drained = _out(_drain(impl, store))
    assert drained["written"] == 1
    assert drained["deferred"] == 0 and drained["dead_lettered"] == 0
    record = json.loads((_runs_of(store, repo) / f"{_RUN}.jsonl").read_text(encoding="utf-8"))
    assert record["created_at_epoch"] == created
    assert record == entries[0]["payload"]
    assert not outbox.exists()


# --- write: where the store lands (AC-22, AC-19, AC-26) ----------------------


@_needs_git
def test_write_from_a_repo_with_no_remote_lands_in_the_local_folder_and_reads_back(tmp_path, home):
    # CSR-INT-009 (AC-22, AC-1): the windows-latest run is the AC-22 evidence.
    repo = _repo(tmp_path)
    _git(repo, "remote", "remove", "origin")
    fingerprint = mc.repo_fingerprint(repo)["value"]
    assert fingerprint.startswith("local:")
    store = tmp_path / "store"
    out = _out(_write(tmp_path / "impl", store, repo))
    folder = "local-" + fingerprint.split(":", 1)[1]
    assert Path(out["path"]) == store / folder / "runs" / f"{_RUN}.jsonl"
    records, dropped = mc.read_store([store], fingerprint)
    assert [r["run_id"] for r in records] == [_RUN]
    assert records[0]["fingerprint"] == fingerprint
    assert dropped == {"invalid": 0, "cross_schema": 0, "foreign": 0}


@_needs_git
@pytest.mark.skipif(sys.platform != "win32", reason="Windows file-handle semantics")
def test_write_replay_with_the_run_file_held_open_on_windows(tmp_path, home):
    # CSR-INT-010 (AC-2): a reader holding the target never breaks a replay.
    repo = _repo(tmp_path)
    store = tmp_path / "store"
    impl = tmp_path / "impl"
    run_file = Path(_out(_write(impl, store, repo))["path"])
    before = _sha(run_file)
    with open(run_file, "rb"):
        proc = _write(impl, store, repo)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["status"] == "skipped-existing"
        assert "PermissionError" not in proc.stderr
        records, _dropped = mc.read_store([store], mc.repo_fingerprint(repo)["value"])
        assert [r["run_id"] for r in records] == [_RUN]
        filtered = _out(_recall_filter(impl, store, repo))
        assert [r["id"] for r in filtered["records"]] == [_RUN]
    assert _sha(run_file) == before


@_needs_git
def test_write_tilde_store_follows_userprofile_on_windows_and_home_elsewhere(tmp_path, monkeypatch):
    # CSR-INT-011 (AC-19, AC-1): expanduser reads USERPROFILE on Windows and
    # HOME elsewhere; nothing appears under the other, nor the real home.
    posix_home = tmp_path / "posix-home"
    win_home = tmp_path / "win-home"
    posix_home.mkdir()
    win_home.mkdir()
    monkeypatch.setenv("HOME", str(posix_home))
    monkeypatch.setenv("USERPROFILE", str(win_home))
    repo = _repo(tmp_path)
    out = _out(_write(tmp_path / "impl", "~/.ultracode-goal/recall", repo))
    expected, other = (win_home, posix_home) if sys.platform == "win32" else (posix_home, win_home)
    store = expected / ".ultracode-goal" / "recall"
    assert Path(out["path"]) == _runs_of(store, repo) / f"{_RUN}.jsonl"
    assert Path(out["path"]).is_file()
    assert not (other / ".ultracode-goal").exists()


@_needs_git
def test_write_store_inside_a_git_repo_ignores_itself(tmp_path, home):
    # CSR-INT-017 (AC-26): the root write creates gets a create-only
    # .gitignore holding *, so git status --porcelain stays empty.
    repo = _repo(tmp_path)
    store = repo / ".ucg-recall"
    assert _out(_write(tmp_path / "impl", store, repo))["status"] == "written"
    assert (store / ".gitignore").read_bytes() == b"*\n"
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True,
    )
    assert status.stdout == ""


@_needs_git
def test_write_never_overwrites_an_existing_store_gitignore(tmp_path, home):
    # CSR-INT-018 (AC-26): later writes leave a .gitignore with other content
    # alone, and a root the user made gets none written (C-9).
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    _out(_write(impl, store, repo, _RUN))
    (store / ".gitignore").write_bytes(b"custom\n")
    _out(_write(impl, store, repo, _RUN_B))
    assert (store / ".gitignore").read_bytes() == b"custom\n"

    own = tmp_path / "own-store"
    own.mkdir()
    (own / ".gitignore").write_bytes(b"keep-me\n")
    assert _out(_write(impl, own, repo, _RUN))["status"] == "written"
    assert (own / ".gitignore").read_bytes() == b"keep-me\n"

    bare = tmp_path / "bare-store"
    bare.mkdir()
    assert _out(_write(impl, bare, repo, _RUN))["status"] == "written"
    assert not (bare / ".gitignore").exists()


# --- write: three spawns of one Epic (AC-18, store half) ---------------------


@_needs_git
def test_three_spawns_of_one_epic_leave_three_run_files_sharing_a_signature(tmp_path, home):
    # AC-18, the write half: one record file per spawn, and a root cause two
    # spawns hit carries one signature across two distinct run_ids, which is
    # what the filter's recurrence rule counts. (CSR-INT-029 drives the same
    # through drive_epic and the filter, in test_drive_epic.py.)
    repo = _repo(tmp_path)
    store = tmp_path / "store"
    impl = tmp_path / "impl"
    shared = "class=race-condition,path=src/x.py"
    _out(_write(impl, store, repo, _RUN, "--root-cause", shared))
    _out(_write(impl, store, repo, _RUN_B, "--root-cause", shared))
    _out(_write(impl, store, repo, _RUN_C, "--root-cause", "class=test-flake,path=tests/y.py"))

    runs = _runs_of(store, repo)
    assert _jsonl_names(runs) == sorted(f"{r}.jsonl" for r in (_RUN, _RUN_B, _RUN_C))
    records, dropped = mc.read_store([store], mc.repo_fingerprint(repo)["value"])
    assert dropped == {"invalid": 0, "cross_schema": 0, "foreign": 0}
    runs_by_sig: dict[str, set[str]] = {}
    for record in records:
        for sig in record["signatures"]:
            runs_by_sig.setdefault(sig["sig"], set()).add(record["run_id"])
    shared_sig = next(r for r in records if r["run_id"] == _RUN)["signatures"][0]
    assert shared_sig["class"] == "race-condition"
    assert runs_by_sig[shared_sig["sig"]] == {_RUN, _RUN_B}


# --- drain --store: landing and attempts (AC-5) ------------------------------


@_needs_git
def test_store_drain_removes_landed_and_skipped_existing_entries_without_bumping_attempts(tmp_path, home):
    # CSR-INT-006 (AC-5): an entry leaves the outbox once written or
    # skipped-existing; the same landed entry seen by three drains is never
    # dead-lettered and never bumped.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    entry_a = _spill_via_write(tmp_path, impl, repo, _RUN)
    _spill_via_write(tmp_path, impl, repo, _RUN_B)
    _out(_write(impl, store, repo, _RUN_B))  # B is already in the store
    runs = _runs_of(store, repo)
    sha_b = _sha(runs / f"{_RUN_B}.jsonl")

    first = _out(_drain(impl, store))
    assert first["written"] == 1 and first["skipped_existing"] == 1
    assert first["deferred"] == 0 and first["dead_lettered"] == 0
    assert not list(impl.glob("mem-outbox.epic-*.jsonl"))
    sha_a = _sha(runs / f"{_RUN}.jsonl")

    outbox_a = impl / f"mem-outbox.{_RUN}.jsonl"
    for _ in range(3):
        _write_lines(outbox_a, [entry_a])  # the landed entry, seen again
        again = _out(_drain(impl, store))
        assert again["skipped_existing"] == 1
        assert again["dead_lettered"] == 0 and again["deferred"] == 0
        assert not outbox_a.exists()
    assert not (impl / _DEAD).exists()
    assert _sha(runs / f"{_RUN}.jsonl") == sha_a
    assert _sha(runs / f"{_RUN_B}.jsonl") == sha_b


@_needs_git
def test_store_drain_bumps_attempts_only_on_oserror_and_dead_letters_at_the_third(tmp_path, home):
    # CSR-INT-012 (AC-5): attempt counting applies only to OSError spills.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = _blocked_store(tmp_path)
    spilled = _spill_via_write(tmp_path, impl, repo, _RUN)
    outbox = impl / f"mem-outbox.{_RUN}.jsonl"
    for expected in (1, 2):
        out = _out(_drain(impl, store))
        assert out["deferred"] == 1 and out["dead_lettered"] == 0
        assert out["notes"][0].startswith("WARN mem-write-deferred")
        (entry,) = _lines(outbox)
        assert entry["attempts"] == expected
        assert entry["spilled_at"] == spilled["spilled_at"]
        assert entry["payload"] == spilled["payload"]
    out = _out(_drain(impl, store))
    assert out["dead_lettered"] == 1 and out["deferred"] == 0
    # The record leaves the replay path for good, so the drain says so: the
    # run report carries the token, and the dead line names it.
    assert [n.split(":", 1)[0] for n in out["notes"]] == ["WARN mem-write-dead-lettered"]
    assert f"{outbox.name} line 1" in out["notes"][0] and _DEAD in out["notes"][0]
    assert not outbox.exists()
    (dead,) = _lines(impl / _DEAD)
    assert dead["attempts"] == 3
    assert dead["payload"] == spilled["payload"]
    assert dead["note"] == "WARN mem-write-dead-lettered"


@_needs_git
def test_store_drain_dead_letters_a_bad_run_id_and_lands_the_entries_around_it(tmp_path, home):
    # CSR-INT-007 (AC-25, AC-4): one entry fails the check, the others land,
    # and no path is ever built from the bad value.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    entries = [_spill_via_write(tmp_path, impl, repo, r) for r in (_RUN, _RUN_B, _RUN_C)]
    for path in impl.glob("mem-outbox.epic-*.jsonl"):
        path.unlink()
    bad = "../escaped-epic-7-20260605T090000Z"
    entries[1]["payload"]["run_id"] = bad
    outbox = impl / f"mem-outbox.{_RUN}.jsonl"
    _write_lines(outbox, entries)

    proc = _drain(impl, store)
    assert "NOTE mem-run-id-invalid" in proc.stdout
    out = _out(proc)
    assert out["written"] == 2
    assert out["run_id_invalid"] == 1 and out["dead_lettered"] == 1
    assert [n.split(":", 1)[0] for n in out["notes"]] == ["NOTE mem-run-id-invalid"]
    assert _jsonl_names(_runs_of(store, repo)) == [f"{_RUN}.jsonl", f"{_RUN_C}.jsonl"]
    (dead,) = _lines(impl / _DEAD)
    assert dead["payload"]["run_id"] == bad
    assert dead["note"] == "NOTE mem-run-id-invalid"
    assert not outbox.exists()
    assert [p for p in tmp_path.rglob("*") if "escaped" in p.name] == []


@_needs_git
@pytest.mark.parametrize("kind", ["unparseable", "foreign-record"])
def test_store_drain_dead_letters_an_entry_whose_target_is_foreign(tmp_path, home, kind):
    # CSR-INT-013 (AC-25, AC-3): the drain half of the mem-target-foreign token.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    entry = _spill_via_write(tmp_path, impl, repo, _RUN)
    target = _runs_of(store, repo) / f"{_RUN}.jsonl"
    target.parent.mkdir(parents=True)
    if kind == "unparseable":
        target.write_bytes(b"\x00garbage, not a record\n")
    else:
        other = dict(entry["payload"], fingerprint="ffffffffffffffff")
        target.write_text(json.dumps(other, sort_keys=True) + "\n", encoding="utf-8")
    before = _sha(target)

    proc = _drain(impl, store)
    assert "NOTE mem-target-foreign" in proc.stdout
    out = _out(proc)
    assert out["target_foreign"] == 1 and out["dead_lettered"] == 1
    assert out["written"] == 0 and out["deferred"] == 0
    assert _sha(target) == before
    (dead,) = _lines(impl / _DEAD)
    assert dead["note"] == "NOTE mem-target-foreign"
    assert dead["payload"] == entry["payload"]
    assert not (impl / f"mem-outbox.{_RUN}.jsonl").exists()


@_needs_git
def test_store_drain_ttl_tombstones_a_30_day_old_deferred_write_and_lands_a_13_day_old_one(tmp_path, home):
    # CSR-INT-016 (AC-27): deferred store writes keep the 14-day TTL.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    for run_id, days in ((_RUN, 30), (_RUN_B, 13)):
        entry = _spill_via_write(tmp_path, impl, repo, run_id)
        entry["spilled_at"] = _iso(_NOW - timedelta(days=days))
        _write_lines(impl / f"mem-outbox.{run_id}.jsonl", [entry])

    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out["tombstones"] == 1 and out["written"] == 1
    assert out["dead_lettered"] == 0
    assert _jsonl_names(_runs_of(store, repo)) == [f"{_RUN_B}.jsonl"]
    assert not list(impl.glob("mem-outbox.epic-*.jsonl"))


# --- drain --store: legacy conversion (AC-15, AC-27) -------------------------


@_needs_git
def test_store_drain_converts_a_30_day_old_legacy_entry_before_the_ttl(tmp_path, home):
    # CSR-INT-014 (AC-15, AC-27): converted before the TTL check, with
    # created_at_epoch from valid_until.date, not the drain time.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    wrapper = _legacy_wrapper(repo)
    _spill_raw(impl, _RUN, wrapper, attempts=0, spilled_at=_iso(_NOW - timedelta(days=30)))

    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out["converted"] == 1 and out["written"] == 1
    assert out["tombstones"] == 0 and out["legacy_unconvertible"] == 0
    record = json.loads((_runs_of(store, repo) / f"{_RUN}.jsonl").read_text(encoding="utf-8"))
    assert record["created_at_epoch"] == _DATE_MS
    assert record["run_id"] == _RUN
    assert "text" not in record and "title" not in record
    assert record == mc.legacy_payload_to_record(wrapper)
    assert not (impl / f"mem-outbox.{_RUN}.jsonl").exists()


@_needs_git
@pytest.mark.parametrize("attempts", [2, 5])
def test_store_drain_resets_legacy_attempts_so_a_writable_store_lands_it(tmp_path, home, attempts):
    # CSR-INT-015 (AC-27, AC-15), first half: with attempts reset to 0 the
    # entry lands rather than dead-letters.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    wrapper = _legacy_wrapper(repo)
    _spill_raw(impl, _RUN, wrapper, attempts=attempts, spilled_at=_iso(_NOW - timedelta(days=30)))
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out["converted"] == 1 and out["written"] == 1
    assert out["dead_lettered"] == 0
    assert not (impl / _DEAD).exists()


@_needs_git
def test_store_drain_requeues_a_failed_legacy_conversion_so_the_next_drain_lands_it(tmp_path, home):
    # CSR-INT-015 (AC-27, AC-15), second half (C-16): an unwritable store ends
    # the drain at attempts 1; a second drain at the same clock, 30 days past
    # the legacy spill stamp, lands it with no tombstone. The requeued entry is
    # the converted record, marked converted so the TTL never applies to it,
    # with its original spill stamp.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = _blocked_store(tmp_path)
    wrapper = _legacy_wrapper(repo)
    _spill_raw(impl, _RUN, wrapper, attempts=2, spilled_at=_iso(_NOW - timedelta(days=30)))

    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out["converted"] == 1 and out["deferred"] == 1 and out["dead_lettered"] == 0
    assert out["notes"][0].startswith("WARN mem-write-deferred")
    (requeued,) = _lines(impl / f"mem-outbox.{_RUN}.jsonl")
    assert requeued["attempts"] == 1
    assert requeued["payload"]["created_at_epoch"] == _DATE_MS
    assert requeued["payload"] == mc.legacy_payload_to_record(wrapper)
    assert requeued["spilled_at"] == _iso(_NOW - timedelta(days=30))
    assert requeued["converted"] is True

    (tmp_path / "blocker").unlink()
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out["written"] == 1 and out["tombstones"] == 0
    record = json.loads((_runs_of(store, repo) / f"{_RUN}.jsonl").read_text(encoding="utf-8"))
    assert record["created_at_epoch"] == _DATE_MS
    assert not (impl / f"mem-outbox.{_RUN}.jsonl").exists()


@pytest.mark.parametrize("payload", [
    _hand_legacy("{not json"),
    _hand_legacy(json.dumps({k: v for k, v in _inner().items() if k != "run_id"})),
    _hand_legacy('{"a": ' + "[" * 100000 + "]" * 100000 + "}"),
], ids=["fenced-json-unparseable", "missing-run-id", "fenced-json-nested-past-the-recursion-limit"])
def test_store_drain_dead_letters_an_unconvertible_legacy_entry_at_once(tmp_path, home, payload):
    # CSR-UNIT-021 (AC-15, AC-27): no store needed, nothing written.
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    _spill_raw(impl, _RUN, payload, attempts=1, spilled_at=_iso(_NOW - timedelta(days=1)))
    proc = _drain(impl, store, "--now-epoch", str(_NOW_MS))
    assert "NOTE mem-legacy-unconvertible" in proc.stdout
    out = _out(proc)
    assert out["legacy_unconvertible"] == 1 and out["dead_lettered"] == 1
    assert out["converted"] == 0 and out["written"] == 0
    (dead,) = _lines(impl / _DEAD)
    assert dead["payload"] == payload
    assert dead["note"] == "NOTE mem-legacy-unconvertible"
    assert not store.exists()
    assert not (impl / f"mem-outbox.{_RUN}.jsonl").exists()


def test_store_drain_dead_letters_a_legacy_entry_whose_run_id_fails_the_check(tmp_path, home):
    # A legacy entry naming a run_id that fails the check gets the more
    # specific NOTE mem-run-id-invalid (a missing run_id is unconvertible).
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    payload = _hand_legacy(json.dumps(_inner(run_id="../escaped-epic-7-20260604T172512Z")))
    _spill_raw(impl, _RUN, payload, attempts=0, spilled_at=_iso(_NOW))
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out["run_id_invalid"] == 1 and out["legacy_unconvertible"] == 0
    assert out["notes"][0].startswith("NOTE mem-run-id-invalid")
    assert _lines(impl / _DEAD)[0]["note"] == "NOTE mem-run-id-invalid"
    assert not store.exists()


def test_store_drain_dead_letters_an_unmarked_wrapper_as_unconvertible(tmp_path, home):
    # C-18: a {text,title,project} payload with no marker is not legacy by the
    # spec's definition; it is not a store record either, so it cannot land
    # and is dead-lettered as unconvertible rather than replayed or dropped.
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    payload = {"text": "a summary with no marker", "title": "t", "project": "widget"}
    _spill_raw(impl, _RUN, payload, attempts=0, spilled_at=_iso(_NOW))
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out["legacy_unconvertible"] == 1 and out["converted"] == 0
    assert out["notes"][0].startswith("NOTE mem-legacy-unconvertible")
    assert not store.exists()


def test_store_drain_leaves_the_dead_letter_file_unconverted_and_always_reports_counts(tmp_path, home):
    # CSR-UNIT-022 (AC-27): mem-outbox.dead.jsonl stays terminal, byte-identical.
    impl = tmp_path / "impl"
    impl.mkdir()
    store = tmp_path / "store"
    dead = impl / _DEAD
    dead.write_text(json.dumps(
        {"payload": _hand_legacy(json.dumps(_inner())), "attempts": 3, "spilled_at": _DATE},
        sort_keys=True,
    ) + "\n", encoding="utf-8")
    before = _sha(dead)

    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert all(out[key] == 0 for key in _STORE_DRAIN_COUNTS)
    assert out["converted"] == 0 and out["legacy_unconvertible"] == 0
    assert _sha(dead) == before
    assert not store.exists()

    missing = _out(_drain(tmp_path / "nope", store, "--now-epoch", str(_NOW_MS)))
    assert set(_STORE_DRAIN_COUNTS) <= set(missing)
    assert missing["converted"] == 0 and missing["legacy_unconvertible"] == 0


@pytest.mark.parametrize("value", ["", "{project-root}/recall", "$HOME/recall"])
def test_store_drain_with_an_unset_store_leaves_the_outbox_as_it_is(tmp_path, home, value):
    impl = tmp_path / "impl"
    payload = _hand_legacy(json.dumps(_inner()))
    _spill_raw(impl, _RUN, payload, attempts=1, spilled_at=_iso(_NOW - timedelta(days=30)))
    outbox = impl / f"mem-outbox.{_RUN}.jsonl"
    before = _sha(outbox)
    out = _out(_drain(impl, value, "--now-epoch", str(_NOW_MS), "--cwd", str(tmp_path)))
    assert out["store"] is None
    assert [n.split(":", 1)[0] for n in out["notes"]] == ["NOTE recall-store-unset"]
    assert all(out[key] == 0 for key in _STORE_DRAIN_COUNTS)
    assert _sha(outbox) == before
    assert not (impl / _DEAD).exists()


def test_store_drain_dead_letters_an_entry_already_at_the_attempt_cap_with_its_stamps(tmp_path, home):
    # An entry an earlier drain left at three attempts is dead-lettered without
    # a write, its payload and original spill stamp kept verbatim.
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    record = mc.store_record(_inner(), created_at_epoch=_DATE_MS, project="widget")
    fresh = _iso(_NOW - timedelta(days=1))
    _spill_raw(impl, _RUN, record, attempts=3, spilled_at=fresh)
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out["dead_lettered"] == 1
    assert out["written"] == 0 and out["deferred"] == 0 and out["tombstones"] == 0
    assert [n.split(":", 1)[0] for n in out["notes"]] == ["WARN mem-write-dead-lettered"]
    assert _lines(impl / _DEAD) == [
        {"payload": record, "attempts": 3, "spilled_at": fresh, "note": "WARN mem-write-dead-lettered"}
    ]
    assert not (impl / f"mem-outbox.{_RUN}.jsonl").exists()
    assert not store.exists()


def test_store_drain_handles_a_mixed_batch_across_two_outboxes(tmp_path, home):
    # One entry lands, one past the TTL tombstones, one past the attempt cap is
    # dead-lettered; each outbox left empty is removed.
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    fresh = _iso(_NOW - timedelta(days=1))
    old = _iso(_NOW - timedelta(days=40))
    records = {
        run_id: mc.store_record(_inner(run_id=run_id), created_at_epoch=_DATE_MS, project="widget")
        for run_id in (_RUN, _RUN_B, _RUN_C)
    }
    _spill_raw(impl, _RUN, records[_RUN], attempts=0, spilled_at=fresh)
    _spill_raw(impl, _RUN, records[_RUN_B], attempts=0, spilled_at=old)
    _spill_raw(impl, _RUN_C, records[_RUN_C], attempts=5, spilled_at=fresh)
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert (out["written"], out["tombstones"], out["dead_lettered"]) == (1, 1, 1)
    assert _jsonl_names(mc.runs_dir(store, _inner()["fingerprint"])) == [f"{_RUN}.jsonl"]
    assert [e["payload"]["run_id"] for e in _lines(impl / _DEAD)] == [_RUN_C]
    assert sorted(p.name for p in impl.iterdir()) == [_DEAD]


def test_store_drain_tombstones_a_line_nested_past_the_recursion_limit_and_lands_the_rest(tmp_path, home):
    # json.loads raises RecursionError, not ValueError, on such a line: it is
    # unparseable like any other, so it is dropped, and the outboxes sorted
    # after it still land instead of every drain exiting 1 on it.
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    impl.mkdir()
    (impl / "mem-outbox.epic-1-20260101T000000Z.jsonl").write_text(
        "[" * 100000 + "]" * 100000 + "\n", encoding="utf-8"
    )
    record = mc.store_record(_inner(), created_at_epoch=_DATE_MS, project="widget")
    _spill_raw(impl, _RUN, record, attempts=0, spilled_at=_iso(_NOW - timedelta(days=1)))
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert (out["tombstones"], out["written"], out["dead_lettered"]) == (1, 1, 0)
    assert _jsonl_names(mc.runs_dir(store, _inner()["fingerprint"])) == [f"{_RUN}.jsonl"]
    assert list(impl.iterdir()) == []


def test_store_drain_tombstones_a_record_nested_deeper_than_any_record(tmp_path, home):
    # JSON parsed just inside the recursion limit can still raise it when the
    # drain writes it back out (on Python 3.11 a field nested 990 deep crashed
    # every drain). Nothing nested deeper than a record could be is replayed.
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    deep: object = []
    for _ in range(39):
        deep = [deep]
    record = mc.store_record(_inner(), created_at_epoch=_DATE_MS, project="widget")
    _spill_raw(impl, _RUN, {**record, "extra": deep}, attempts=0, spilled_at=_iso(_NOW - timedelta(days=1)))
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert (out["tombstones"], out["written"], out["dead_lettered"]) == (1, 0, 0)
    assert not store.exists()
    assert list(impl.iterdir()) == []


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_store_drain_never_blocks_on_a_fifo_named_like_an_outbox(tmp_path, home):
    # Opening a FIFO with no writer for reading blocks forever, so Finalize
    # would hang. It is not a regular file: never read, left as it is.
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    record = mc.store_record(_inner(run_id=_RUN_B), created_at_epoch=_DATE_MS, project="widget")
    _spill_raw(impl, _RUN_B, record, attempts=0, spilled_at=_iso(_NOW - timedelta(days=1)))
    fifo = impl / f"mem-outbox.{_RUN}.jsonl"
    os.mkfifo(fifo)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "drain", "--impl-artifacts", str(impl), "--store", str(store),
         "--now-epoch", str(_NOW_MS)],
        capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL, timeout=30,
    )
    out = _out(proc)
    assert out["written"] == 1 and out["tombstones"] == 0 and out["dead_lettered"] == 0
    assert _jsonl_names(mc.runs_dir(store, _inner()["fingerprint"])) == [f"{_RUN_B}.jsonl"]
    assert fifo.is_fifo()


def test_store_drain_of_an_empty_artifacts_folder_reports_zero_counts(tmp_path, home):
    impl = tmp_path / "impl"
    impl.mkdir()
    store = tmp_path / "store"
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out == {**{key: 0 for key in _STORE_DRAIN_COUNTS}, "notes": [], "store": os.path.abspath(store)}
    assert list(impl.iterdir()) == []
    assert not store.exists()


# --- the removed claude-mem forms (R-15) ----------------------------------------


@pytest.mark.parametrize(
    "args, form, replacement",
    [
        (
            ("build", "--impl-artifacts", "I", "--epic", "7", "--run-id", _RUN, "--gate-status", "PASS",
             "--verdict", "advance", "--project", "widget", "--cwd", "P"),
            "build", "write --store VALUE",
        ),
        # CSR-UNIT-002 (AC-4): a path-like run_id names no file either.
        (
            ("build", "--impl-artifacts", "I", "--epic", "7", "--run-id", "x/../../escaped",
             "--gate-status", "PASS", "--verdict", "advance", "--project", "widget"),
            "build", "write --store VALUE",
        ),
        (("spill", "--impl-artifacts", "I", "--run-id", _RUN), "spill", "write --store VALUE"),
        (("spill", "--impl-artifacts", "I", "--run-id", "x/../../escaped"), "spill", "write --store VALUE"),
        (("drain", "--impl-artifacts", "I"), "drain without --store", "drain --store VALUE"),
        (
            ("drain", "--impl-artifacts", "I", "--ttl-days", "14", "--now-epoch", str(_NOW_MS)),
            "drain without --store", "drain --store VALUE",
        ),
        (("drain", "--impl-artifacts", "I", "--project-root", "P"), "drain without --store", "drain --store VALUE"),
        (("drain", "--impl-artifacts", "I", "--cwd", "P"), "drain without --store", "drain --store VALUE"),
        (
            ("write", "--impl-artifacts", "I", "--store", "S", "--epic", "7", "--run-id", _RUN,
             "--gate-status", "PASS", "--verdict", "advance", "--project", "widget", "--cwd", "P"),
            "--project, a build flag,", "write takes project from the main worktree",
        ),
    ],
    ids=[
        "build", "build-path-like-run-id", "spill", "spill-path-like-run-id", "drain-no-store",
        "drain-no-store-with-ttl", "drain-no-store-project-root", "drain-no-store-cwd", "write-project",
    ],
)
def test_removed_claude_mem_forms_exit_2_naming_their_replacement(args, form, replacement, tmp_path, home):
    # R-15, CSR-UNIT-002: each form the claude-mem backend needed exits 2 with
    # one stderr line naming what replaces it, before reading stdin or touching
    # anything: the outbox it would have drained stays byte-identical.
    impl = tmp_path / "impl"
    record = mc.store_record(_inner(), created_at_epoch=_DATE_MS, project="widget")
    _spill_raw(impl, _RUN, record, attempts=1, spilled_at=_iso(_NOW - timedelta(days=1)))
    outbox = impl / f"mem-outbox.{_RUN}.jsonl"
    before = _sha(outbox)
    tree = sorted(str(p) for p in tmp_path.rglob("*"))
    values = {"I": str(impl), "S": str(tmp_path / "store"), "P": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *(values.get(a, a) for a in args)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(tmp_path),
        input='{"text": "a claude-mem payload", "title": "t", "project": "widget"}',
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert proc.returncode == 2
    assert proc.stdout == ""
    (line,) = proc.stderr.splitlines()
    assert line.startswith("mem_observation.py: error: ")
    assert f"{form} was removed with the claude-mem backend" in line
    assert replacement in line
    assert _sha(outbox) == before
    assert sorted(str(p) for p in tmp_path.rglob("*")) == tree


def test_help_lists_only_write_and_drain(tmp_path):
    text = _run_in(tmp_path, "--help").stdout
    assert "{write,drain}" in text
    # A subcommand line is indented four spaces; a wrapped help line, more.
    listed = [line.split()[0] for line in text.splitlines() if line.startswith("    ") and line[4:5].strip()]
    assert listed == ["write", "drain"]
    assert "--project " not in _run_in(tmp_path, "write", "--help").stdout


# --- review follow-ups: drain order, converted entries, the reader -------------


@_needs_git
def test_write_from_a_repo_with_no_remote_reads_back_through_filter(tmp_path, home):
    # CSR-INT-009 (AC-22, AC-1), the read half through the real filter CLI: a
    # no-remote repo's local:<hex> fingerprint must reach the reader raw.
    repo = _repo(tmp_path)
    _git(repo, "remote", "remove", "origin")
    store, impl = tmp_path / "store", tmp_path / "impl"
    assert _out(_write(impl, store, repo))["status"] == "written"
    out = _out(_recall_filter(impl, store, repo, "--epic", "7"))
    assert [r["id"] for r in out["records"]] == [_RUN]
    assert out["dropped"] == {"foreign": 0, "stale": 0, "cross_schema": 0, "invalid": 0}


@pytest.mark.parametrize("age_days, attempts", [(30, 0), (1, 3), (30, 5)], ids=["past-ttl", "attempts-3", "both"])
def test_store_drain_dead_letters_a_bad_run_id_whatever_its_age_or_attempts(tmp_path, home, age_days, attempts):
    # AC-25, AC-4: the run_id check comes before the TTL and the attempt cap,
    # so such an entry is never tombstoned silently or dead-lettered unnamed.
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    payload = mc.store_record(
        _inner(run_id="../escaped-epic-7-20260604T172512Z"), created_at_epoch=_DATE_MS, project="widget",
    )
    _spill_raw(impl, _RUN, payload, attempts=attempts, spilled_at=_iso(_NOW - timedelta(days=age_days)))
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out["run_id_invalid"] == 1 and out["dead_lettered"] == 1
    assert out["tombstones"] == 0
    assert [n.split(":", 1)[0] for n in out["notes"]] == ["NOTE mem-run-id-invalid"]
    (dead,) = _lines(impl / _DEAD)
    assert dead["note"] == "NOTE mem-run-id-invalid"
    assert dead["payload"] == payload
    assert not store.exists()


def test_store_drain_dead_letters_an_unmarked_wrapper_past_the_ttl_as_unconvertible(tmp_path, home):
    # C-18 with an old entry: it is unconvertible, never a silent tombstone.
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    payload = {"text": "a summary with no marker", "title": "t", "project": "widget"}
    _spill_raw(impl, _RUN, payload, attempts=4, spilled_at=_iso(_NOW - timedelta(days=30)))
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out["legacy_unconvertible"] == 1 and out["dead_lettered"] == 1
    assert out["tombstones"] == 0
    assert out["notes"][0].startswith("NOTE mem-legacy-unconvertible")
    assert _lines(impl / _DEAD)[0]["note"] == "NOTE mem-legacy-unconvertible"


@_needs_git
@pytest.mark.parametrize("fingerprint", [".", ":", "..."])
def test_store_drain_dead_letters_a_record_whose_fingerprint_names_no_folder(tmp_path, home, fingerprint):
    # One such line used to crash the drain before the outbox was rewritten,
    # so every later drain crashed on it and the entries behind it never landed.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = tmp_path / "store"
    good = _spill_via_write(tmp_path, impl, repo, _RUN_B)
    bad = dict(good, payload=dict(good["payload"], run_id=_RUN, fingerprint=fingerprint))
    outbox = impl / f"mem-outbox.{_RUN_B}.jsonl"
    _write_lines(outbox, [bad, good])
    proc = _drain(impl, store)
    assert "NOTE mem-legacy-unconvertible" in proc.stdout
    out = _out(proc)
    assert out["written"] == 1
    assert out["legacy_unconvertible"] == 1 and out["dead_lettered"] == 1
    assert _jsonl_names(_runs_of(store, repo)) == [f"{_RUN_B}.jsonl"]
    (dead,) = _lines(impl / _DEAD)
    assert dead["payload"]["fingerprint"] == fingerprint
    assert dead["note"] == "NOTE mem-legacy-unconvertible"
    assert not outbox.exists()


def test_replay_dead_letters_a_record_the_writer_refuses(tmp_path, monkeypatch):
    # The backstop behind the validation above: a ValueError from the writer
    # dead-letters the entry at once instead of crashing the drain.
    import mem_observation  # noqa: PLC0415  (scripts dir is on sys.path)

    def refuse(*_args, **_kwargs):
        raise ValueError("record is not writable: invalid")

    monkeypatch.setattr(mc, "write_run_record", refuse)
    counts = {key: 0 for key in _STORE_DRAIN_COUNTS}
    notes: list[str] = []
    entry = {
        "payload": mc.store_record(_inner(), created_at_epoch=_DATE_MS, project="widget"),
        "attempts": 0, "spilled_at": _DATE,
    }
    action, dead = mem_observation._replay_into_store(
        tmp_path / "store", entry, "x line 1", "x", counts, notes,
    )
    assert action == "dead"
    assert dead["note"] == "NOTE mem-legacy-unconvertible"
    assert counts["legacy_unconvertible"] == 1 and counts["dead_lettered"] == 1
    assert [n.split(":", 1)[0] for n in notes] == ["NOTE mem-legacy-unconvertible"]
    assert not (tmp_path / "store").exists()


@_needs_git
def test_store_drain_never_tombstones_a_converted_legacy_entry(tmp_path, home):
    # R-09, C-16: a legacy entry whose converted write was deferred is the
    # only history the upgrade carries over. A drain 15 days later, past the
    # 14-day TTL counted from either stamp, still lands it.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = _blocked_store(tmp_path)
    wrapper = _legacy_wrapper(repo)
    _spill_raw(impl, _RUN, wrapper, attempts=0, spilled_at=_iso(_NOW - timedelta(days=30)))
    out = _out(_drain(impl, store, "--now-epoch", str(_NOW_MS)))
    assert out["converted"] == 1 and out["deferred"] == 1

    (tmp_path / "blocker").unlink()
    later = _NOW + timedelta(days=15)
    out = _out(_drain(impl, store, "--now-epoch", str(int(later.timestamp()) * 1000)))
    assert out["written"] == 1 and out["tombstones"] == 0 and out["converted"] == 0
    record = json.loads((_runs_of(store, repo) / f"{_RUN}.jsonl").read_text(encoding="utf-8"))
    assert record["created_at_epoch"] == _DATE_MS
    assert not (impl / f"mem-outbox.{_RUN}.jsonl").exists()


@_needs_git
def test_store_drain_dead_letters_a_converted_entry_at_the_attempt_cap(tmp_path, home):
    # The TTL exemption never makes an entry immortal: three failed writes
    # dead-letter it, and the dead-letter file keeps it for inspection.
    repo = _repo(tmp_path)
    impl = tmp_path / "impl"
    store = _blocked_store(tmp_path)
    wrapper = _legacy_wrapper(repo)
    _spill_raw(impl, _RUN, wrapper, attempts=0, spilled_at=_iso(_NOW - timedelta(days=30)))
    for days, deferred in ((0, 1), (20, 1), (40, 0)):
        clock = int((_NOW + timedelta(days=days)).timestamp()) * 1000
        out = _out(_drain(impl, store, "--now-epoch", str(clock)))
        assert out["deferred"] == deferred and out["tombstones"] == 0
    assert out["dead_lettered"] == 1
    assert [n.split(":", 1)[0] for n in out["notes"]] == ["WARN mem-write-dead-lettered"]
    assert not (impl / f"mem-outbox.{_RUN}.jsonl").exists()
    (dead,) = _lines(impl / _DEAD)
    assert dead["attempts"] == 3 and dead["converted"] is True
    assert dead["payload"] == mc.legacy_payload_to_record(wrapper)
    assert dead["note"] == "WARN mem-write-dead-lettered"


def test_every_token_the_scripts_print_is_logged_and_explained():
    # A token the scripts print but Finalize never logs, or the operator doc
    # never explains, is a recall problem that leaves no line anyone can act on.
    tokens = sorted(v for k, v in vars(mc).items() if k.startswith(("NOTE_", "WARN_")))
    assert "WARN mem-write-dead-lettered" in tokens
    root = SCRIPT.parents[3]
    finalize = (SCRIPT.parents[1] / "references" / "finalize.md").read_text(encoding="utf-8")
    doc = (root / "docs" / "cross-session-recall.md").read_text(encoding="utf-8")
    for token in tokens:
        assert f"`{token}`" in finalize, f"finalize.md must tell the run to log {token}"
        assert f"| `{token}` |" in doc, f"the troubleshooting table must explain {token}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
