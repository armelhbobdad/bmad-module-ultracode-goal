#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for lib/mem_common.py (Cross-Session Recall shared library).

mem_common is the only pure-library module in scripts/ — it has no CLI, so
(unlike the other script tests, which drive subprocesses) it is imported
directly. We insert the scripts dir on sys.path and import the namespace
subpackage exactly as the CLIs do (``from lib import mem_common``).

Covers the load-bearing pure functions: the taxonomy mapping, git-remote
normalization (ssh/https/scp/port collapse), high-precision secret redaction,
untrusted-text neutralization (bidi/backtick strip + clamp), the repo
fingerprint across its basis branches, the state-file latch roundtrip, and
remove_own_state, which removes only this run's latch (``mem_recall.py
unlatch``).

The local run store tests (the CSR-* rows of the cross-session recall test
design whose target is this file, plus the store-module halves of the CLI rows)
cover the run_id check, store path resolution, the Windows-legal fingerprint
directory, the self-ignoring store root, the immutable writer and its Windows
fault paths (forced os.link failures and a scanner holding the temp, both by
monkeypatch), the reader over a list of roots, the write probe, legacy outbox
conversion and latch v2. Every store test points HOME and USERPROFILE at
tmp_path, so nothing reaches the real home.

Run: uv run --with pytest pytest test_mem_common.py -v
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from lib import mem_common as mc  # noqa: E402  (after sys.path mutation)

# Same GIT_* scrub as test_mem_recall: keep repo_fingerprint() pinned to the
# temp repos these tests build, never the host checkout.
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


def _init_repo(repo: Path, remote: str | None = "https://github.com/acme/widget.git") -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    if remote:
        _git(repo, "remote", "add", "origin", remote)


# ---------------------------------------------------------------------------
# canonical_class — unknown collapses to "other"
# ---------------------------------------------------------------------------


def test_canonical_class_keeps_known_collapses_unknown_and_none():
    assert mc.canonical_class("test-flake") == "test-flake"
    assert mc.canonical_class("security") == "security"
    assert mc.canonical_class("not-a-real-class") == "other"
    assert mc.canonical_class(None) == "other"
    # Surrounding whitespace is stripped before the membership check.
    assert mc.canonical_class("  build-error  ") == "build-error"
    # The taxonomy is the frozen 12-class contract callers rely on.
    assert len(mc.TAXONOMY) == 12
    assert "other" in mc.TAXONOMY


# ---------------------------------------------------------------------------
# normalize_remote — ssh / https / scp forms collapse to one key
# ---------------------------------------------------------------------------


def test_normalize_remote_collapses_ssh_and_https_forms():
    https = mc.normalize_remote("https://github.com/Acme/Widget.git/")
    ssh = mc.normalize_remote("git@github.com:Acme/Widget.git")
    scp_scheme = mc.normalize_remote("ssh://git@github.com/Acme/Widget.git")
    assert https == ssh == scp_scheme == "github.com/acme/widget"


def test_normalize_remote_preserves_host_port():
    # A numeric "host:port" must NOT be rewritten as "host/port".
    assert mc.normalize_remote("ssh://git@example.com:22/org/repo.git") == "example.com:22/org/repo"
    assert mc.normalize_remote("git@example.com:2222/org/repo.git") == "example.com:2222/org/repo"


# ---------------------------------------------------------------------------
# redact — high-precision secret scrubbing
# ---------------------------------------------------------------------------


def test_redact_scrubs_known_credential_shapes():
    assert mc.redact("id AKIAABCDEFGHIJKLMNOP done") == "id [redacted] done"
    assert mc.redact("gh token gh" + "p_" + "a" * 30) == "gh token [redacted]"
    assert mc.redact("use sk-" + "B" * 24 + " now") == "use [redacted] now"
    assert "[redacted]" in mc.redact("Authorization: Bearer abcdefghijklmnop")
    # key=value assignment redacts the value but stops at whitespace.
    assert mc.redact("token=supersecretvalue here") == "[redacted] here"


def test_redact_leaves_ordinary_prose_and_handles_none():
    text = "the build failed because the test was flaky on retry"
    assert mc.redact(text) == text
    assert mc.redact(None) == ""
    assert mc.redact("") == ""


# ---------------------------------------------------------------------------
# neutralize — defang untrusted free text
# ---------------------------------------------------------------------------


def test_neutralize_strips_fences_collapses_ws_and_clamps():
    assert mc.neutralize("a```b   c\n\nd") == "ab c d"
    # Bidi controls (Trojan Source) are dropped entirely.
    assert mc.neutralize("safe‮txet") == "safetxet"
    # Clamp to 80 codepoints on a boundary; idempotent.
    out = mc.neutralize("x" * 200)
    assert len(out) == 80
    assert mc.neutralize(out) == out
    assert mc.neutralize(None) == ""


def test_neutralize_replaces_a_lone_surrogate_so_the_text_encodes():
    # A JSON "\ud800" escape decodes to a lone surrogate, which UTF-8 cannot
    # encode, so the filter's byte clamp and its output would raise on it.
    out = mc.neutralize("advance \ud800 tail \udcff")
    assert out == "advance \ufffd tail \ufffd"
    assert out.encode("utf-8")
    assert mc.neutralize("ok \U0001f600") == "ok \U0001f600"  # a real astral character stays
    assert mc.replace_surrogates("a\ud800b\udfff") == "a\ufffdb\ufffd"


# ---------------------------------------------------------------------------
# repo_fingerprint — stable per-repo identity across basis branches
# ---------------------------------------------------------------------------


def test_repo_fingerprint_none_outside_git(tmp_path):
    fp = mc.repo_fingerprint(tmp_path)
    assert fp == {"basis": None, "value": None}


@pytest.mark.skipif(not __import__("shutil").which("git"), reason="git not on PATH")
def test_repo_fingerprint_remote_root_is_stable_and_deterministic(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo, remote="git@github.com:acme/widget.git")
    fp = mc.repo_fingerprint(repo)
    assert fp["basis"] == "remote+root"
    assert isinstance(fp["value"], str) and len(fp["value"]) == 16
    # Same repo -> same fingerprint (deterministic, no clock/random input).
    assert mc.repo_fingerprint(repo) == fp


@pytest.mark.skipif(not __import__("shutil").which("git"), reason="git not on PATH")
def test_repo_fingerprint_local_basis_when_no_remote(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo, remote=None)
    fp = mc.repo_fingerprint(repo)
    assert fp["basis"] == "local"
    assert fp["value"].startswith("local:")


# ---------------------------------------------------------------------------
# state-file latch — write/read/remove roundtrip
# ---------------------------------------------------------------------------


def test_state_path_is_under_impl_artifacts(tmp_path):
    assert mc.state_path(tmp_path) == tmp_path / ".mem-state.json"


def test_state_roundtrip_write_read_remove_own(tmp_path):
    # Written by latch, read back unchanged, removed by unlatch with its own
    # run_id; a second unlatch finds nothing (a close-out run twice is harmless).
    state = mc.build_latch_v2(
        run_id=_RUN, recall="off", store=None, store_ok=False, fingerprint=None
    )
    path = mc.write_state(tmp_path, state)
    assert path.exists()
    assert mc.read_state(tmp_path) == state
    assert mc.remove_own_state(tmp_path, _RUN) == (True, "removed")
    assert not path.exists()
    assert mc.remove_own_state(tmp_path, _RUN) == (False, "absent")


def test_read_state_returns_none_on_missing_and_corrupt(tmp_path):
    # Missing file.
    assert mc.read_state(tmp_path) is None
    # Corrupt JSON -> None, never raises.
    mc.state_path(tmp_path).write_text("{not json", encoding="utf-8")
    assert mc.read_state(tmp_path) is None
    # Valid JSON but not an object -> None.
    mc.state_path(tmp_path).write_text("[1, 2, 3]", encoding="utf-8")
    assert mc.read_state(tmp_path) is None


@pytest.mark.parametrize(
    "payload",
    ["[" * 100000 + "]" * 100000, '{"a":' * 50000 + "1" + "}" * 50000],
    ids=["deep-array", "deep-object"],
)
def test_read_state_returns_none_on_json_nested_past_the_recursion_limit(tmp_path, payload):
    # json.loads raises RecursionError, not ValueError, on these; read_state
    # still never raises, and reads them as the PreToolUse guard does (AC-24).
    mc.state_path(tmp_path).write_text(payload, encoding="utf-8")
    assert mc.read_state(tmp_path) is None


# ===========================================================================
# Local run store (cross_session_recall_store)
# ===========================================================================

_HAS_GIT = shutil.which("git") is not None
_needs_git = pytest.mark.skipif(not _HAS_GIT, reason="git not on PATH")

_FP = "0123456789abcdef"
_LOCAL_FP = "local:0123456789abcdef"
_RUN = "epic-7-20260604T172512Z"
_RUN_B = "epic-7-20260605T090000Z"
_DATE = "2026-06-04T17:25:12Z"
_DATE_MS = int(datetime(2026, 6, 4, 17, 25, 12, tzinfo=timezone.utc).timestamp()) * 1000
_WINDOWS_ILLEGAL = set('<>:"/\\|?*')
# JSON nested past the recursion limit: json.loads raises RecursionError, not
# ValueError, on these (about 2 KB of brackets is enough on Python 3.11).
_DEEP_ARRAY = "[" * 100000 + "]" * 100000
_DEEP_OBJECT = '{"a":' * 50000 + "1" + "}" * 50000
_nested_past_the_limit = pytest.mark.parametrize(
    "nested", [_DEEP_ARRAY, _DEEP_OBJECT], ids=["deep-array", "deep-object"]
)
_needs_fifo = pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")


def _returns_within(call, seconds: float = 10):
    """call() on a daemon thread; fails when it blocks (a FIFO opened with no writer)."""
    result: list = []
    worker = threading.Thread(target=lambda: result.append(call()), daemon=True)
    worker.start()
    worker.join(timeout=seconds)
    assert not worker.is_alive(), "blocked opening a FIFO"
    assert result, "raised instead of returning"
    return result[0]


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point HOME and USERPROFILE at one tmp folder (expanduser reads either)."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    return home_dir


def _payload(run_id: str = _RUN, fingerprint: str | None = _FP) -> dict:
    """The run payload mem_observation.py write stores (see the drift test below)."""
    return {
        "ucg": 1,
        "schema_version": 1,
        "kind": "run-summary",
        "epic": "7",
        "run_id": run_id,
        "fingerprint": fingerprint,
        "gate_status": "PASS",
        "verdict": "advance",
        "valid_until": {"sha": None, "date": _DATE},
        "signatures": [{"class": "test-flake", "path": "tests/x.py", "sig": "abc123def456"}],
        "deferred_count": 0,
        "advisories": [{"sig": "abc123def456", "recurred": "yes"}],
    }


def _record(run_id: str = _RUN, fingerprint: str | None = _FP, **overrides) -> dict:
    record = mc.store_record(
        _payload(run_id, fingerprint), created_at_epoch=_DATE_MS, project="widget"
    )
    record.update(overrides)
    return record


def _legacy(inner: dict | str, project: object = "widget") -> dict:
    """A claude-mem era outbox payload, shaped as the removed build printed it."""
    body = inner if isinstance(inner, str) else json.dumps(inner, sort_keys=True)
    return {
        "text": f"UCG run for epic 7: gate PASS.\n{mc.UCG_MARKER}\n```json\n{body}\n```",
        "title": "UCG run epic 7: advance",
        "project": project,
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(runs: Path) -> list[str]:
    return sorted(p.name for p in runs.iterdir() if p.name.endswith(".jsonl"))


# ---------------------------------------------------------------------------
# remove_own_state: unlatch removes this run's latch and no other (AC-31)
# ---------------------------------------------------------------------------


def _own_latch(**overrides) -> dict:
    state = {
        "latch_version": 2, "run_id": _RUN, "backend": "jsonl", "store_ok": True,
        "recall": "on", "store": None, "fingerprint": None, "created_at": _DATE,
    }
    state.update(overrides)
    return state


def test_remove_own_state_removes_a_latch_of_any_version_naming_this_run(tmp_path):
    # Version and colour do not matter, only the run_id: a claude-mem era v1
    # latch this run wrote before an upgrade goes too.
    for state in (
        _own_latch(),
        _own_latch(store_ok=False, recall="off"),
        {"latch_version": 1, "run_id": _RUN, "claude_mem": "absent", "recall": "off"},
        {"run_id": _RUN},
    ):
        mc.write_state(tmp_path, state)
        assert mc.remove_own_state(tmp_path, _RUN) == (True, "removed")
        assert not mc.state_path(tmp_path).exists()


@pytest.mark.parametrize(
    "state",
    [
        _own_latch(run_id="epic-6-20260101T000000Z"),
        _own_latch(run_id=None),
        _own_latch(run_id=["epic-7-20260604T172512Z"]),
        {k: v for k, v in _own_latch().items() if k != "run_id"},
        {"latch_version": 1, "run_id": "r1", "claude_mem": "present", "recall": "on"},
    ],
    ids=["another-run", "null-run-id", "list-run-id", "no-run-id", "v1-old-shape"],
)
def test_remove_own_state_leaves_a_foreign_latch_byte_identical(state, tmp_path):
    path = mc.write_state(tmp_path, state)
    before = path.read_bytes()
    assert mc.remove_own_state(tmp_path, _RUN) == (False, "foreign")
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"   \n",
        b"{not json",
        b'{"run_id": "' + _RUN.encode() + b'"',
        b'["' + _RUN.encode() + b'"]',
        json.dumps(_RUN).encode(),
        b"\xff\xfe" + _RUN.encode(),
        b'{"run_id":' * 50000 + json.dumps(_RUN).encode() + b"}" * 50000,
    ],
    ids=["empty", "blank", "corrupt", "truncated", "array", "string", "binary", "nested-past-the-limit"],
)
def test_remove_own_state_never_assumes_an_unreadable_latch_is_this_runs(content, tmp_path):
    # Most of these hold this run's id somewhere; none is read as naming it.
    path = mc.state_path(tmp_path)
    path.write_bytes(content)
    before = path.read_bytes()
    assert mc.remove_own_state(tmp_path, _RUN) == (False, "unreadable")
    assert path.read_bytes() == before


def test_remove_own_state_leaves_a_directory_at_the_latch_path(tmp_path):
    folder = mc.state_path(tmp_path)
    folder.mkdir()
    (folder / "inside").write_text(_RUN, encoding="utf-8")
    assert mc.remove_own_state(tmp_path, _RUN) == (False, "unreadable")
    assert (folder / "inside").read_text(encoding="utf-8") == _RUN


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_remove_own_state_never_opens_a_fifo_at_the_latch_path(tmp_path):
    # Opening a FIFO with no writer for reading blocks forever, so unlatch
    # would hang at a terminal (PR 3 latch review E). It is not a regular
    # file, so it reads as unreadable without being opened, and stays.
    path = mc.state_path(tmp_path)
    os.mkfifo(path)
    result: list = []
    worker = threading.Thread(target=lambda: result.append(mc.remove_own_state(tmp_path, _RUN)))
    worker.daemon = True
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive(), "remove_own_state blocked on a FIFO"
    assert result == [(False, "unreadable")]
    assert stat.S_ISFIFO(os.lstat(path).st_mode)


def test_remove_own_state_follows_a_symlink_to_this_runs_latch(tmp_path):
    # A link whose target is this run's latch reads as the latch; removing it
    # takes the link away and leaves the file it pointed at.
    target = tmp_path / "elsewhere.json"
    target.write_text(json.dumps(_own_latch()), encoding="utf-8")
    link = mc.state_path(tmp_path)
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert mc.remove_own_state(tmp_path, _RUN) == (True, "removed")
    assert not os.path.lexists(link)
    assert target.is_file()


def test_remove_own_state_with_no_latch_creates_nothing(tmp_path):
    impl = tmp_path / "impl"
    assert mc.remove_own_state(impl, _RUN) == (False, "absent")
    assert not impl.exists()
    impl.mkdir()
    (impl / "mem-outbox.x.jsonl").write_text("{}\n", encoding="utf-8")
    assert mc.remove_own_state(impl, _RUN) == (False, "absent")
    assert sorted(p.name for p in impl.iterdir()) == ["mem-outbox.x.jsonl"]


@pytest.mark.parametrize(
    "run_id",
    ["r1", "", "epic-..-20260604T172512Z", "../epic-7-20260604T172512Z", "epic-7-20260604T172512Z\n", None],
    ids=["no-pattern", "empty", "dot-dot", "parent", "newline", "none"],
)
def test_remove_own_state_refuses_a_bad_run_id_before_reading(run_id, tmp_path):
    # A latch carrying that very value stays: a malformed run_id matches nothing.
    path = mc.write_state(tmp_path, _own_latch(run_id=run_id))
    before = path.read_bytes()
    with pytest.raises(ValueError):
        mc.remove_own_state(tmp_path, run_id)
    assert path.read_bytes() == before


def test_remove_own_state_reports_a_failed_removal_and_keeps_the_latch(tmp_path, monkeypatch):
    # A Windows reader holding the file, or a read-only folder: the latch
    # stays (fail closed) and the reason says why.
    path = mc.write_state(tmp_path, _own_latch())

    def held(self, *args, **kwargs):
        raise PermissionError(errno.EACCES, "held by another process", str(self))

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", held)
        removed, reason = mc.remove_own_state(tmp_path, _RUN)
    assert removed is False
    assert reason.startswith("remove-failed: ")
    assert "held by another process" in reason
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == _RUN


# ---------------------------------------------------------------------------
# CSR-UNIT-001: the run_id check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "run_id",
    ["epic-7-20260604T172512Z", "epic-a.b_c-20260604T172512Z", "epic-ucg-2.1-20261024T000000Z"],
)
def test_run_id_check_accepts_minted_ids(run_id):
    assert mc.valid_run_id(run_id) is True


@pytest.mark.parametrize(
    "run_id",
    [
        "epic-7/x-20260604T172512Z",  # POSIX separator
        "epic-7\\x-20260604T172512Z",  # Windows separator
        "epic-..-20260604T172512Z",  # the bare pattern accepts this one
        "epic-a..b-20260604T172512Z",
        "../epic-7-20260604T172512Z",
        "epic-7-20260604T172512Z\n",  # re.match with $ would accept it
        "epic-7-2026060٤T172512Z",  # Arabic-Indic digit
        "epic-7-２0260604T172512Z",  # full-width digit
        "epic-7-20260604T172512z",  # lowercase z
        "epic-7-20260604T172512",
        "epic--20260604T172512Z",
        "7-20260604T172512Z",  # no epic- prefix
        "r1",
        "",
        None,
        7,
    ],
)
def test_run_id_check_rejects_unsafe_or_malformed_ids(run_id):
    assert mc.valid_run_id(run_id) is False


def test_run_id_dot_dot_rule_is_load_bearing():
    # The spec pattern alone lets "..", so the separate refusal is what stops it.
    bare = re.compile(r"^epic-[A-Za-z0-9._-]+-\d{8}T\d{6}Z$", re.ASCII)
    assert bare.fullmatch("epic-..-20260604T172512Z") is not None
    assert mc.valid_run_id("epic-..-20260604T172512Z") is False


def test_run_file_path_refuses_a_bad_run_id(tmp_path):
    with pytest.raises(ValueError):
        mc.run_file_path(tmp_path, _FP, "../../etc/passwd")
    assert mc.run_file_path(tmp_path, _FP, _RUN) == tmp_path / _FP / "runs" / f"{_RUN}.jsonl"


# ---------------------------------------------------------------------------
# CSR-UNIT-023: unset store values, store path resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "\t\n",
        "{workflow.cross_session_recall_store}",
        "{project-root}/_bmad-output/recall",  # unresolved without a project root
        "$HOME/.ultracode-goal/recall",
        "${HOME}/.ultracode-goal/recall",
        "$VAR",
        "%USERPROFILE%\\.ultracode-goal\\recall",  # never expanded: a literal folder
        "C:\\Users\\%USERNAME%\\recall",
        "%ProgramFiles(x86)%\\recall",
        "/abs/re\0call",  # a NUL would crash expanduser, abspath or mkdir
        None,
        0,
    ],
)
def test_store_value_counts_as_unset(value, tmp_path, home):
    assert mc.is_store_unset(value) is True
    assert mc.resolve_store_root(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "~/.ultracode-goal/recall",
        "/abs/recall",
        "recall",
        "/home/u/my$proj/recall",  # a "$" inside a name is part of it
        "\\\\server\\C$\\recall",  # a Windows admin share
        "/x/50%off%/recall",
    ],
)
def test_store_value_counts_as_set(value):
    # The raw-text check only: a relative value passes it, and is refused by
    # resolve_store_root (see below).
    assert mc.is_store_unset(value) is False


@pytest.mark.parametrize("value", ["recall", "./recall", "../recall", "sub/dir"])
def test_relative_store_value_resolves_to_nothing(value, tmp_path, monkeypatch):
    # Not an accepted form: resolved against whatever cwd each script ran in,
    # one value could name two stores.
    monkeypatch.chdir(tmp_path)
    assert mc.resolve_store_root(value) is None
    assert list(tmp_path.iterdir()) == []


def test_resolve_store_root_expands_home_like_the_seen_cache(home, tmp_path):
    got = mc.resolve_store_root("~/.ultracode-goal/recall")
    assert got == home / ".ultracode-goal" / "recall"
    assert got.is_absolute()
    # Surrounding whitespace is not part of the path.
    assert mc.resolve_store_root("  ~/.ultracode-goal/recall  ") == got


def test_resolve_store_root_never_turns_empty_into_the_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert mc.resolve_store_root("") is None
    assert mc.resolve_store_root(" ") is None


def test_resolve_store_root_project_root_relative_and_absolute(tmp_path, home, monkeypatch):
    project = tmp_path / "proj"
    got = mc.resolve_store_root("{project-root}/_bmad-output/recall", project_root=project)
    assert got == project / "_bmad-output" / "recall"
    # A relative project root is made absolute against the process cwd first.
    monkeypatch.chdir(tmp_path)
    assert mc.resolve_store_root("{project-root}/recall", project_root="proj") == project / "recall"
    absolute = tmp_path / "a" / ".." / "store"
    assert mc.resolve_store_root(str(absolute)) == tmp_path / "store"
    # Any other brace token stays unresolved even when a project root is given.
    assert mc.resolve_store_root("{project-root}/{other}", project_root=project) is None


def test_project_root_holding_a_brace_or_dollar_is_not_an_unresolved_token(tmp_path):
    project = tmp_path / "odd{name}$dir"
    got = mc.resolve_store_root("{project-root}/recall", project_root=project)
    assert got == project / "recall"


def test_resolve_store_root_split_homes_follow_the_platform(tmp_path, monkeypatch):
    posix_home = tmp_path / "posix-home"
    win_home = tmp_path / "win-home"
    posix_home.mkdir()
    win_home.mkdir()
    monkeypatch.setenv("HOME", str(posix_home))
    monkeypatch.setenv("USERPROFILE", str(win_home))
    got = mc.resolve_store_root("~/.ultracode-goal/recall")
    expected_home = win_home if sys.platform == "win32" else posix_home
    assert got == expected_home / ".ultracode-goal" / "recall"


# ---------------------------------------------------------------------------
# CSR-UNIT-018: the Windows-legal fingerprint directory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fingerprint, expected",
    [
        (_LOCAL_FP, "local-0123456789abcdef"),
        (_FP, _FP),
        ("nul", "_nul"),
        ("CON.x", "_CON.x"),
        ("COM0", "_COM0"),
        ("lpt0.x", "_lpt0.x"),
        ("COM10", "COM10"),
        ("abc. ", "abc"),
        ('a<b>c"d/e\\f|g?h*i', "a-b-c-d-e-f-g-h-i"),
    ],
)
def test_fingerprint_dir_is_windows_legal(fingerprint, expected):
    name = mc.fingerprint_dir(fingerprint)
    assert name == expected
    assert not (_WINDOWS_ILLEGAL & set(name))
    assert not name.endswith((".", " "))


@pytest.mark.parametrize("fingerprint", [None, "", "   ", ":", "..", ".", 12])
def test_fingerprint_dir_refuses_values_with_no_name(fingerprint, tmp_path):
    assert mc.fingerprint_dir(fingerprint) is None
    with pytest.raises(ValueError):
        mc.runs_dir(tmp_path, fingerprint)


def test_a_new_run_file_flushes_its_runs_folder(tmp_path, home, monkeypatch):
    # #160 item 12: the record's bytes were fsynced but its link into the runs
    # folder was not, so a power loss right after the write could lose it.
    flushed = []
    monkeypatch.setattr(mc, "_fsync_dir", flushed.append)
    store = home / ".ultracode-goal" / "recall"

    result = mc.write_run_record(store, _record())

    assert result.status == mc.WRITE_WRITTEN
    assert flushed == [result.path.parent]
    assert mc.write_run_record(store, _record()).status == mc.WRITE_SKIPPED_EXISTING
    assert flushed == [result.path.parent]


def test_flushing_a_folder_never_raises(tmp_path):
    mc._fsync_dir(tmp_path)
    mc._fsync_dir(tmp_path / "missing")


def test_local_fingerprint_lands_in_a_safe_folder_and_stays_raw_in_the_record(tmp_path, home):
    store = home / ".ultracode-goal" / "recall"
    result = mc.write_run_record(store, _record(fingerprint=_LOCAL_FP))
    assert result.status == mc.WRITE_WRITTEN
    assert result.path == store / "local-0123456789abcdef" / "runs" / f"{_RUN}.jsonl"
    assert json.loads(result.path.read_text(encoding="utf-8"))["fingerprint"] == _LOCAL_FP
    records, dropped = mc.read_store([store], _LOCAL_FP)
    assert [r["run_id"] for r in records] == [_RUN]
    assert dropped == {"invalid": 0, "cross_schema": 0, "foreign": 0}


@_needs_git
def test_no_remote_repo_writes_and_reads_back_its_record(tmp_path, home):
    # AC-22: the windows-latest run of this test is the Windows evidence.
    repo = tmp_path / "widget"
    _init_repo(repo, remote=None)
    fingerprint = mc.repo_fingerprint(repo)["value"]
    assert fingerprint.startswith("local:")
    store = home / ".ultracode-goal" / "recall"
    result = mc.write_run_record(store, _record(fingerprint=fingerprint))
    assert result.status == mc.WRITE_WRITTEN
    assert result.path.parent.parent.name == "local-" + fingerprint.split(":", 1)[1]
    records, _ = mc.read_store([store], fingerprint)
    assert [r["fingerprint"] for r in records] == [fingerprint]


# ---------------------------------------------------------------------------
# AC-26: the self-ignoring store root
# ---------------------------------------------------------------------------


def test_store_root_created_with_a_gitignore_holding_star(tmp_path):
    store = tmp_path / "a" / "recall"
    assert mc.ensure_store_root(store) is True
    assert (store / ".gitignore").read_bytes() == b"*\n"
    # Only the store root gets one, not the parents this call created.
    assert not (tmp_path / "a" / ".gitignore").exists()
    assert mc.ensure_store_root(store) is False


def test_existing_gitignore_is_never_overwritten(tmp_path, home):
    store = home / "recall"
    store.mkdir()
    (store / ".gitignore").write_text("keep-me\n", encoding="utf-8")
    mc.write_run_record(store, _record())
    mc.write_run_record(store, _record(run_id=_RUN_B))
    assert (store / ".gitignore").read_text(encoding="utf-8") == "keep-me\n"


def test_store_root_the_user_made_gets_no_gitignore(tmp_path, home):
    store = home / "recall"
    store.mkdir()
    mc.write_run_record(store, _record())
    assert not (store / ".gitignore").exists()


def test_store_root_that_is_a_file_is_an_oserror(tmp_path):
    store = tmp_path / "recall"
    store.write_text("not a dir", encoding="utf-8")
    with pytest.raises(OSError):
        mc.ensure_store_root(store)
    assert store.read_text(encoding="utf-8") == "not a dir"


def test_store_root_is_removed_again_when_its_gitignore_cannot_be_written(tmp_path, monkeypatch):
    store = tmp_path / "recall"
    real = mc._create_exclusive

    def fail_gitignore(path, data):
        if Path(path).name == ".gitignore":
            raise PermissionError(errno.EACCES, "denied", str(path))
        return real(path, data)

    monkeypatch.setattr(mc, "_create_exclusive", fail_gitignore)
    with pytest.raises(OSError):
        mc.ensure_store_root(store)
    assert not store.exists()


@_needs_git
def test_store_inside_a_git_repo_leaves_status_clean(tmp_path, home):
    repo = tmp_path / "widget"
    _init_repo(repo)
    store = repo / "_bmad-output" / "recall"
    result = mc.write_run_record(store, _record())
    assert result.status == mc.WRITE_WRITTEN
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    assert status.stdout == ""


# ---------------------------------------------------------------------------
# The immutable writer (AC-1 to AC-4 at the module level)
# ---------------------------------------------------------------------------


def test_write_creates_exactly_one_run_file_holding_one_json_line(tmp_path, home):
    store = home / "recall"
    record = _record()
    result = mc.write_run_record(store, record)
    assert result == mc.WriteResult(mc.WRITE_WRITTEN, mc.run_file_path(store, _FP, _RUN))
    lines = result.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == record
    assert isinstance(json.loads(lines[0])["created_at_epoch"], int)
    runs = result.path.parent
    assert _jsonl(runs) == [f"{_RUN}.jsonl"]
    if sys.platform != "win32":
        # A Windows scanner may keep the temp; elsewhere none is left.
        assert [p.name for p in runs.iterdir()] == [f"{_RUN}.jsonl"]


def test_replay_skips_existing_and_leaves_the_file_byte_identical(tmp_path, home):
    store = home / "recall"
    first = mc.write_run_record(store, _record())
    before = _sha(first.path)
    again = mc.write_run_record(store, _record())
    # A replay carrying another created_at_epoch still never rewrites the file.
    later = mc.write_run_record(store, _record(created_at_epoch=_DATE_MS + 5))
    assert again.status == later.status == mc.WRITE_SKIPPED_EXISTING
    assert again.path == first.path
    assert _sha(first.path) == before


@pytest.mark.parametrize(
    "content",
    [
        b"{not json",
        b"",
        json.dumps(_record(fingerprint="ffffffffffffffff")).encode(),  # another repo
        json.dumps(_record(run_id=_RUN_B)).encode(),  # another run
        json.dumps({"run_id": _RUN, "fingerprint": _FP}).encode(),  # wrong shape
        _DEEP_ARRAY.encode(),
        _DEEP_OBJECT.encode(),
    ],
    ids=["unparseable", "empty", "other-fingerprint", "other-run-id", "wrong-shape", "deep-array", "deep-object"],
)
def test_foreign_or_unparseable_target_is_never_touched(content, tmp_path, home):
    store = home / "recall"
    target = mc.run_file_path(store, _FP, _RUN)
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    result = mc.write_run_record(store, _record())
    assert result.status == mc.WRITE_FOREIGN_TARGET
    assert target.read_bytes() == content


def test_directory_at_the_target_path_is_foreign(tmp_path, home):
    store = home / "recall"
    target = mc.run_file_path(store, _FP, _RUN)
    target.mkdir(parents=True)
    assert mc.write_run_record(store, _record()).status == mc.WRITE_FOREIGN_TARGET
    assert target.is_dir()


@_needs_fifo
def test_fifo_at_the_target_path_is_foreign_and_never_blocks(tmp_path, home):
    # Opening a FIFO with no writer for reading blocks forever, so the write
    # would hang at Finalize. It is not a regular file: foreign, left in place.
    store = home / "recall"
    target = mc.run_file_path(store, _FP, _RUN)
    target.parent.mkdir(parents=True)
    os.mkfifo(target)
    result = _returns_within(lambda: mc.write_run_record(store, _record()))
    assert result.status == mc.WRITE_FOREIGN_TARGET
    assert stat.S_ISFIFO(os.lstat(target).st_mode)


@pytest.mark.parametrize("run_id", ["epic-7/../../x-20260604T172512Z", "../x", "r1", "epic-..-20260604T172512Z"])
def test_invalid_run_id_writes_nothing(run_id, tmp_path, home):
    store = home / "recall"
    with pytest.raises(ValueError):
        mc.write_run_record(store, _record(run_id=run_id))
    assert not store.exists()


@pytest.mark.parametrize(
    "overrides",
    [{"fingerprint": None}, {"fingerprint": ""}, {"schema_version": 2}, {"signatures": "x"}],
    ids=["no-fingerprint", "empty-fingerprint", "newer-schema", "wrong-shape"],
)
def test_record_that_does_not_validate_writes_nothing(overrides, tmp_path, home):
    store = home / "recall"
    with pytest.raises(ValueError):
        mc.write_run_record(store, _record(**overrides))
    assert not store.exists()


def test_unset_store_root_is_a_valueerror():
    with pytest.raises(ValueError):
        mc.write_run_record(None, _record())


def test_unwritable_store_raises_oserror_and_creates_nothing(tmp_path, home):
    # A store whose parent is a regular file: mkdir fails on Linux and Windows
    # alike, where chmod would not stop a directory write.
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    with pytest.raises(OSError):
        mc.write_run_record(blocker / "recall", _record())
    assert blocker.read_text(encoding="utf-8") == "file"


def test_runs_folder_replaced_by_a_file_raises_oserror(tmp_path, home):
    store = home / "recall"
    mc.ensure_store_root(store)
    runs = mc.runs_dir(store, _FP)
    runs.parent.mkdir(parents=True)
    runs.write_text("file", encoding="utf-8")
    with pytest.raises(OSError):
        mc.write_run_record(store, _record())
    assert runs.read_text(encoding="utf-8") == "file"


class _Forbidden(Exception):
    """Raised by a patched move or copy: never caught as an OSError."""


def test_writer_never_moves_or_copies_onto_a_run_file(tmp_path, home, monkeypatch):
    # CSR-UNIT-017: os.rename overwrites silently on POSIX, so patching
    # os.replace alone could be beaten.
    def forbidden(*_args, **_kwargs):
        raise _Forbidden("a run file must never be moved or copied into place")

    for owner, name in ((os, "replace"), (os, "rename"), (shutil, "move"), (shutil, "copyfile")):
        monkeypatch.setattr(owner, name, forbidden)
    store = home / "recall"
    assert mc.write_run_record(store, _record()).status == mc.WRITE_WRITTEN
    assert mc.write_run_record(store, _record()).status == mc.WRITE_SKIPPED_EXISTING
    other = mc.run_file_path(store, _FP, _RUN_B)
    other.write_bytes(b"{not json")
    assert mc.write_run_record(store, _record(run_id=_RUN_B)).status == mc.WRITE_FOREIGN_TARGET


# ---------------------------------------------------------------------------
# CSR-UNIT-019: os.link unsupported -> O_EXCL fallback
# ---------------------------------------------------------------------------


def _unsupported_link_errors():
    cases = [
        pytest.param(OSError(errno.EOPNOTSUPP, "Operation not supported"), id="EOPNOTSUPP"),
        pytest.param(PermissionError(errno.EPERM, "Operation not permitted"), id="EPERM-vfat"),
        pytest.param(OSError(errno.ENOSYS, "Function not implemented"), id="ENOSYS"),
    ]
    if sys.platform == "win32":
        cases.append(
            pytest.param(OSError(0, "The request is not supported", None, 50), id="winerror-50")
        )
    return cases


@pytest.mark.parametrize("error", _unsupported_link_errors())
def test_link_unsupported_falls_back_to_o_excl_with_the_same_bytes(error, tmp_path, home, monkeypatch):
    calls = []

    def no_links(src, dst, *args, **kwargs):
        calls.append(dst)
        raise error

    monkeypatch.setattr(os, "link", no_links)
    store = home / "recall"
    record = _record()
    result = mc.write_run_record(store, record)
    assert calls == [str(result.path)]
    assert result.status == mc.WRITE_WRITTEN
    assert result.path.read_bytes() == (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    # The replay never reaches the link: the existing target answers first.
    assert mc.write_run_record(store, record).status == mc.WRITE_SKIPPED_EXISTING


def test_platform_without_os_link_uses_o_excl(tmp_path, home, monkeypatch):
    monkeypatch.delattr(os, "link")
    store = home / "recall"
    assert mc.write_run_record(store, _record()).status == mc.WRITE_WRITTEN
    assert mc.write_run_record(store, _record()).status == mc.WRITE_SKIPPED_EXISTING


@pytest.mark.parametrize(
    "existing, expected",
    [
        (lambda: (json.dumps(_record(), sort_keys=True) + "\n").encode(), mc.WRITE_SKIPPED_EXISTING),
        (lambda: b"{not json", mc.WRITE_FOREIGN_TARGET),
    ],
    ids=["same-run", "foreign"],
)
def test_o_excl_fallback_never_overwrites_a_target_that_appeared(existing, expected, tmp_path, home, monkeypatch):
    store = home / "recall"
    target = mc.run_file_path(store, _FP, _RUN)
    target.parent.mkdir(parents=True)
    content = existing()
    target.write_bytes(content)
    real_lexists = os.path.lexists
    # The target "appears" after the existence check, so the fallback's O_EXCL
    # create is what meets it.
    monkeypatch.setattr(
        os.path, "lexists", lambda p: False if Path(p) == target else real_lexists(p)
    )
    monkeypatch.setattr(
        os, "link", lambda *a, **k: (_ for _ in ()).throw(OSError(errno.EOPNOTSUPP, "no links"))
    )
    result = mc.write_run_record(store, _record())
    assert result.status == expected
    assert target.read_bytes() == content


def test_link_file_exists_is_the_existing_target_path_not_a_fallback(tmp_path, home, monkeypatch):
    store = home / "recall"
    mc.ensure_store_root(store)  # its .gitignore is the only other O_EXCL create
    target = mc.run_file_path(store, _FP, _RUN)

    def racing_link(src, dst, *args, **kwargs):
        Path(dst).write_bytes(b"{written by someone else")
        raise FileExistsError(errno.EEXIST, "File exists", dst)

    def no_fallback(*_args, **_kwargs):
        raise AssertionError("FileExistsError must not reach the O_EXCL fallback")

    monkeypatch.setattr(os, "link", racing_link)
    monkeypatch.setattr(mc, "_create_exclusive", no_fallback)
    result = mc.write_run_record(store, _record())
    assert result.status == mc.WRITE_FOREIGN_TARGET
    assert target.read_bytes() == b"{written by someone else"


def test_other_link_error_propagates_for_the_caller_to_spill(tmp_path, home, monkeypatch):
    def full_disk(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "link", full_disk)
    store = home / "recall"
    with pytest.raises(OSError) as info:
        mc.write_run_record(store, _record())
    assert info.value.errno == errno.ENOSPC
    runs = mc.runs_dir(store, _FP)
    assert _jsonl(runs) == []  # no target
    if sys.platform != "win32":
        assert list(runs.iterdir()) == []  # and the temp was removed


# ---------------------------------------------------------------------------
# CSR-UNIT-020: a scanner holding the temp (PermissionError on its delete)
# ---------------------------------------------------------------------------


def test_permission_error_deleting_the_temp_is_swallowed(tmp_path, home, monkeypatch):
    real_unlink, real_remove = os.unlink, os.remove

    def held(real):
        def guarded(path, *args, **kwargs):
            if str(path).endswith(".tmp"):
                raise PermissionError(errno.EACCES, "held by a scanner", str(path))
            return real(path, *args, **kwargs)
        return guarded

    monkeypatch.setattr(os, "unlink", held(real_unlink))
    monkeypatch.setattr(os, "remove", held(real_remove))
    store = home / "recall"
    record = _record()
    result = mc.write_run_record(store, record)
    assert result.status == mc.WRITE_WRITTEN
    assert json.loads(result.path.read_text(encoding="utf-8")) == record
    leftovers = [p.name for p in result.path.parent.iterdir() if p.name.endswith(".tmp")]
    assert len(leftovers) == 1  # left behind, and outside the reader's glob
    assert [item.record["run_id"] for item in mc.iter_store_records([store], _FP)] == [_RUN]


# ---------------------------------------------------------------------------
# The reader over a list of roots (AC-7, AC-8 at the module level)
# ---------------------------------------------------------------------------


def _seed_mixed_store(store: Path) -> Path:
    mc.write_run_record(store, _record())
    mc.write_run_record(store, _record(run_id=_RUN_B))
    runs = mc.runs_dir(store, _FP)
    (runs / "epic-7-20260601T000000Z.jsonl").write_bytes(b"{not json")
    (runs / "epic-7-20260602T000000Z.jsonl").write_text(
        json.dumps({"ucg": 1, "schema_version": 1, "run_id": "epic-7-20260602T000000Z"}),
        encoding="utf-8",
    )
    newer = _record(run_id="epic-7-20260603T000000Z", schema_version=mc.UCG_SCHEMA_VERSION + 1)
    (runs / "epic-7-20260603T000000Z.jsonl").write_text(json.dumps(newer), encoding="utf-8")
    foreign = _record(run_id="epic-9-20260603T000000Z", fingerprint="ffffffffffffffff")
    (runs / "epic-9-20260603T000000Z.jsonl").write_text(json.dumps(foreign), encoding="utf-8")
    (runs / "empty.jsonl").write_bytes(b"")
    (runs / ".epic-7-20260604T172512Z.abc.tmp").write_bytes(b"{partial")
    (runs / "notes.txt").write_text("not a record", encoding="utf-8")
    (runs / "unreadable.jsonl").mkdir()  # fails to open on both OSes
    return runs


def test_reader_validates_each_file_on_its_own(tmp_path, home):
    store = home / "recall"
    runs = _seed_mixed_store(store)
    items = list(mc.iter_store_records([store], _FP))
    statuses = {item.path.name: item.status for item in items}
    assert statuses == {
        f"{_RUN}.jsonl": mc.RECORD_OK,
        f"{_RUN_B}.jsonl": mc.RECORD_OK,
        "epic-7-20260601T000000Z.jsonl": mc.RECORD_INVALID,
        "epic-7-20260602T000000Z.jsonl": mc.RECORD_INVALID,
        "epic-7-20260603T000000Z.jsonl": mc.RECORD_CROSS_SCHEMA,
        "epic-9-20260603T000000Z.jsonl": mc.RECORD_FOREIGN,
        "empty.jsonl": mc.RECORD_INVALID,
    }
    # Sorted name order, so two reads (and two listings) agree.
    assert [item.path.name for item in items] == sorted(statuses)
    assert all(item.path.parent == runs for item in items)
    records, dropped = mc.read_store([store], _FP)
    assert [r["run_id"] for r in records] == [_RUN, _RUN_B]
    assert dropped == {"invalid": 3, "cross_schema": 1, "foreign": 1}
    assert mc.read_store([store], _FP) == (records, dropped)


def test_run_file_with_a_byte_order_mark_reads_as_its_record(tmp_path, home):
    # An editor such as Notepad may save a run file with a UTF-8 BOM and CRLF.
    store = home / "recall"
    record = _record()
    target = mc.run_file_path(store, _FP, _RUN)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xef\xbb\xbf" + (json.dumps(record) + "\r\n").encode("utf-8"))
    before = _sha(target)
    records, dropped = mc.read_store([store], _FP)
    assert records == [record]
    assert dropped == {"invalid": 0, "cross_schema": 0, "foreign": 0}
    # A replay of that run meets its own record, not a foreign target.
    assert mc.write_run_record(store, record).status == mc.WRITE_SKIPPED_EXISTING
    assert _sha(target) == before


@_nested_past_the_limit
def test_reader_drops_a_run_file_nested_past_the_recursion_limit_as_invalid(nested, tmp_path, home):
    # One hand-made file must not stop the read: it is invalid like any other
    # file that does not parse, and the records beside it still come back.
    store = home / "recall"
    mc.write_run_record(store, _record())
    (mc.runs_dir(store, _FP) / "epic-9-20260101T000000Z.jsonl").write_text(nested, encoding="utf-8")
    records, dropped = mc.read_store([store], _FP)
    assert records == [_record()]
    assert dropped == {"invalid": 1, "cross_schema": 0, "foreign": 0}


def _nest(depth: int) -> object:
    """A list nested ``depth`` levels deep, built without recursion."""
    value: object = []
    for _ in range(depth - 1):
        value = [value]
    return value


def test_nested_too_deep_counts_lists_and_objects_past_the_bound():
    assert not mc.nested_too_deep(_record())
    assert not mc.nested_too_deep(_nest(32))
    assert mc.nested_too_deep(_nest(33))
    assert mc.nested_too_deep({"a": {"b": _nest(31)}})
    assert not mc.nested_too_deep({"a": [_nest(30)], "b": "text"})
    assert not mc.nested_too_deep("[[[[")


def test_reader_drops_a_record_nested_deeper_than_any_record_as_invalid(tmp_path, home):
    # Parseable on every Python, but json.dumps can still raise RecursionError
    # writing JSON nested just inside the limit back out (a drain requeue or
    # dead-letter): nothing that deep reads as a record, on any version.
    store = home / "recall"
    mc.write_run_record(store, _record())
    deep = _record(run_id=_RUN_B, extra=_nest(40))
    (mc.runs_dir(store, _FP) / f"{_RUN_B}.jsonl").write_text(json.dumps(deep), encoding="utf-8")
    records, dropped = mc.read_store([store], _FP)
    assert records == [_record()]
    assert dropped == {"invalid": 1, "cross_schema": 0, "foreign": 0}
    assert mc.extract_payload(_legacy(_payload(run_id=_RUN_B) | {"extra": _nest(40)})) is None


@_needs_fifo
def test_reader_never_blocks_on_a_fifo_named_like_a_run_file(tmp_path, home):
    # A FIFO, or a link to one, is not a regular file: it is skipped unread,
    # like a directory of that name, and the read goes on.
    store = home / "recall"
    mc.write_run_record(store, _record())
    runs = mc.runs_dir(store, _FP)
    os.mkfifo(runs / "epic-8-20260101T000000Z.jsonl")
    os.mkfifo(tmp_path / "elsewhere")
    (runs / "epic-9-20260101T000000Z.jsonl").symlink_to(tmp_path / "elsewhere")
    records, dropped = _returns_within(lambda: mc.read_store([store], _FP))
    assert records == [_record()]
    assert dropped == {"invalid": 0, "cross_schema": 0, "foreign": 0}


def test_reader_order_does_not_depend_on_write_order(tmp_path, home):
    one, two = home / "one", home / "two"
    for run_id in (_RUN, _RUN_B, "epic-8-20260601T000000Z"):
        mc.write_run_record(one, _record(run_id=run_id))
    for run_id in ("epic-8-20260601T000000Z", _RUN_B, _RUN):
        mc.write_run_record(two, _record(run_id=run_id))
    assert mc.read_store([one], _FP) == mc.read_store([two], _FP)


def test_reader_spans_roots_and_reads_one_run_once(tmp_path, home):
    first, second = home / "first", home / "second"
    mc.write_run_record(first, _record())
    mc.write_run_record(second, _record())  # the same run seen through two roots
    mc.write_run_record(second, _record(run_id=_RUN_B))
    records, dropped = mc.read_store([first, None, home / "missing", second], _FP)
    assert [r["run_id"] for r in records] == [_RUN, _RUN_B]
    assert dropped == {"invalid": 0, "cross_schema": 0, "foreign": 0}


def test_reader_reads_only_this_fingerprints_folder(tmp_path, home):
    store = home / "recall"
    mc.write_run_record(store, _record())
    mc.write_run_record(store, _record(run_id=_RUN_B, fingerprint="ffffffffffffffff"))
    assert [r["run_id"] for r in mc.read_store([store], _FP)[0]] == [_RUN]
    assert list(mc.iter_store_records([store], None)) == []


def test_classify_record_foreign_by_fingerprint_only():
    record = _record()
    assert mc.classify_record(record, _FP) == mc.RECORD_OK
    assert mc.classify_record(record, "ffffffffffffffff") == mc.RECORD_FOREIGN
    assert mc.classify_record(record, None) == mc.RECORD_FOREIGN
    # project is display only: another directory name is still this repo.
    assert mc.classify_record(_record(project="widget-clone"), _FP) == mc.RECORD_OK


# ---------------------------------------------------------------------------
# validate_record (AC-7, AC-9)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"ucg": None},
        {"ucg": True},
        {"schema_version": 0},
        {"schema_version": "1"},
        {"schema_version": True},
        {"run_id": "r1"},
        {"fingerprint": None},
        {"created_at_epoch": True},
        {"created_at_epoch": "1780000000000"},
        {"created_at_epoch": -1},
        {"deferred_count": None},
        {"project": None},
        {"kind": 1},
        {"valid_until": "2026-06-04"},
        {"valid_until": {"sha": 1, "date": _DATE}},
        {"signatures": {"sig": "x"}},
        {"signatures": [{"class": "test-flake", "path": "x"}]},
        {"advisories": ["abc"]},
    ],
    ids=lambda o: next(iter(o)) + "=" + repr(next(iter(o.values()))),
)
def test_wrong_shape_records_are_invalid(overrides):
    assert mc.validate_record(_record(**overrides)) == mc.RECORD_INVALID


@pytest.mark.parametrize("fingerprint", [".", "-", ":", "...", " "])
def test_record_whose_fingerprint_names_no_folder_is_invalid(fingerprint, tmp_path, home):
    # Its file name could never be built, so the writer would raise ValueError
    # on it, and a drain would crash on that outbox line again and again.
    record = _record(fingerprint=fingerprint)
    assert mc.validate_record(record) == mc.RECORD_INVALID
    with pytest.raises(ValueError):
        mc.write_run_record(home / "recall", record)
    assert not (home / "recall").exists()


def test_record_missing_a_field_is_invalid():
    for key in ("ucg", "run_id", "epic", "signatures", "advisories", "valid_until", "project"):
        record = _record()
        del record[key]
        assert mc.validate_record(record) == mc.RECORD_INVALID, key


def test_valid_record_and_unknown_extra_fields_pass():
    assert mc.validate_record(_record()) == mc.RECORD_OK
    assert mc.validate_record(_record(added_by_a_later_minor="x")) == mc.RECORD_OK
    assert mc.validate_record([_record()]) == mc.RECORD_INVALID
    assert mc.validate_record(None) == mc.RECORD_INVALID


def test_newer_schema_is_cross_schema_whatever_its_shape():
    newer = mc.UCG_SCHEMA_VERSION + 1
    assert mc.validate_record(_record(schema_version=newer)) == mc.RECORD_CROSS_SCHEMA
    assert mc.validate_record({"schema_version": newer}) == mc.RECORD_CROSS_SCHEMA


def test_schema_bump_still_reads_earlier_records(tmp_path, home, monkeypatch):
    # CSR-UNIT-024 / AC-9, in process so the patch reaches the validator.
    monkeypatch.setattr(mc, "UCG_SCHEMA_VERSION", 2)
    assert mc.validate_record(_record(schema_version=1)) == mc.RECORD_OK
    assert mc.validate_record(_record(schema_version=2)) == mc.RECORD_OK
    assert mc.validate_record(_record(schema_version=3)) == mc.RECORD_CROSS_SCHEMA
    store = home / "recall"
    mc.write_run_record(store, _record(schema_version=1))
    mc.write_run_record(store, _record(run_id=_RUN_B, schema_version=2))
    records, dropped = mc.read_store([store], _FP)
    assert [r["schema_version"] for r in records] == [1, 2]
    assert dropped["cross_schema"] == 0


# ---------------------------------------------------------------------------
# Record helpers
# ---------------------------------------------------------------------------


def test_iso_to_epoch_ms_is_integer_utc_milliseconds():
    assert mc.iso_to_epoch_ms(_DATE) == _DATE_MS
    assert mc.iso_to_epoch_ms("2026-06-04T17:25:12+00:00") == _DATE_MS
    assert mc.iso_to_epoch_ms("2026-06-04T19:25:12+02:00") == _DATE_MS
    assert mc.iso_to_epoch_ms("2026-06-04T17:25:12") == _DATE_MS  # naive reads as UTC
    for bad in (None, "", "yesterday", 1780000000):
        assert mc.iso_to_epoch_ms(bad) is None


def test_utc_now_epoch_ms_is_an_int_near_the_clock():
    now = mc.utc_now_epoch_ms()
    assert isinstance(now, int)
    assert abs(now - time.time() * 1000) < 60_000


def test_store_record_adds_two_fields_and_leaves_the_payload_alone():
    payload = _payload()
    record = mc.store_record(payload, created_at_epoch=_DATE_MS, project="widget")
    assert record == {**payload, "created_at_epoch": _DATE_MS, "project": "widget"}
    assert "created_at_epoch" not in payload


@_needs_git
def test_hand_built_record_matches_real_write_output(tmp_path, home):
    # Drift guard: the fixtures above must keep the shape write really stores,
    # and that payload, wrapped the way the removed build wrapped it for
    # claude-mem, must convert back into the same record as a legacy entry.
    repo = tmp_path / "widget"
    _init_repo(repo)
    store = tmp_path / "store"
    proc = subprocess.run(
        [
            sys.executable, str(SCRIPTS / "mem_observation.py"), "write",
            "--impl-artifacts", str(tmp_path / "impl"), "--store", str(store),
            "--epic", "7", "--run-id", _RUN, "--gate-status", "PASS", "--verdict", "advance",
            "--cwd", str(repo), "--valid-until-date", _DATE,
            "--root-cause", "class=test-flake,path=tests/x.py",
            "--advisory", "sig=abc123def456,recurred=yes",
        ],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    out = json.loads(proc.stdout)
    assert out["status"] == "written"
    record = json.loads(Path(out["path"]).read_text(encoding="utf-8"))
    assert set(record) == set(_record())
    fingerprint = mc.repo_fingerprint(repo)["value"]
    inner = {k: v for k, v in record.items() if k not in ("created_at_epoch", "project")}
    assert set(inner) == set(_payload())
    assert inner == {
        **_payload(fingerprint=fingerprint),
        "signatures": [
            {
                "class": "test-flake",
                "path": "tests/x.py",
                "sig": hashlib.sha1(f"test-flake|tests/x.py|{fingerprint}".encode()).hexdigest()[:12],
            }
        ],
    }
    assert record["project"] == "widget"
    assert mc.validate_record(record) == mc.RECORD_OK
    converted = mc.legacy_payload_to_record(_legacy(inner))
    assert converted == {**record, "created_at_epoch": _DATE_MS}


# ---------------------------------------------------------------------------
# The latch's write probe (store health)
# ---------------------------------------------------------------------------


def test_probe_creates_the_root_with_its_gitignore_and_leaves_no_probe_file(tmp_path, home):
    store = home / "recall"
    assert mc.probe_store(store, _FP) == (True, None)
    assert (store / ".gitignore").read_bytes() == b"*\n"
    runs = mc.runs_dir(store, _FP)
    assert runs.is_dir()
    if sys.platform != "win32":
        assert list(runs.iterdir()) == []


def test_probe_unwritable_store_creates_nothing(tmp_path, home):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    ok, reason = mc.probe_store(blocker / "recall", _FP)
    assert ok is False
    assert reason.startswith("store-unwritable: ")
    assert blocker.read_text(encoding="utf-8") == "file"


def test_probe_unset_store_or_missing_fingerprint_creates_nothing(tmp_path, home):
    store = home / "recall"
    assert mc.probe_store(None, _FP) == (False, "store-unset")
    assert mc.probe_store(store, None) == (False, "no-fingerprint")
    assert not store.exists()  # in particular no <store>/None/ folder


def test_probe_tolerates_a_held_probe_file(tmp_path, home, monkeypatch):
    # C-15: a scanner holding the probe file must not turn the latch red.
    real_unlink = os.unlink

    def held(path, *args, **kwargs):
        if ".probe-" in str(path):
            raise PermissionError(errno.EACCES, "held by a scanner", str(path))
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", held)
    assert mc.probe_store(home / "recall", _FP) == (True, None)


def test_probe_links_its_file_the_way_the_writer_does(tmp_path, home, monkeypatch):
    calls = []
    real_link = os.link

    def spy(src, dst, *args, **kwargs):
        calls.append((Path(src).name, Path(dst).name))
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "link", spy)
    store = home / "recall"
    assert mc.probe_store(store, _FP) == (True, None)
    ((src, dst),) = calls
    assert src.startswith(".probe-") and src.endswith(".tmp")
    assert dst.startswith(".probe-") and dst.endswith(".link.tmp")  # outside *.jsonl
    if sys.platform != "win32":
        assert list(mc.runs_dir(store, _FP).iterdir()) == []


@pytest.mark.parametrize("error", _unsupported_link_errors())
def test_probe_stays_green_where_links_are_unsupported(error, tmp_path, home, monkeypatch):
    # The writer falls back to O_EXCL there, which the probe's mkstemp exercised.
    def no_links(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(os, "link", no_links)
    assert mc.probe_store(home / "recall", _FP) == (True, None)
    monkeypatch.delattr(os, "link")
    assert mc.probe_store(home / "recall-2", _FP) == (True, None)


def test_probe_is_red_when_the_store_refuses_the_link(tmp_path, home, monkeypatch):
    # A store that creates files but refuses a link with any other error would
    # spill every write while the latch read green, so the probe says so.
    def refused(*_args, **_kwargs):
        raise PermissionError(errno.EACCES, "Access is denied")

    monkeypatch.setattr(os, "link", refused)
    store = home / "recall"
    ok, reason = mc.probe_store(store, _FP)
    assert ok is False
    assert reason.startswith("store-unwritable: ")
    if sys.platform != "win32":
        assert list(mc.runs_dir(store, _FP).iterdir()) == []


# ---------------------------------------------------------------------------
# Legacy outbox payloads (AC-15, AC-27 at the module level)
# ---------------------------------------------------------------------------


def test_legacy_payload_is_recognised_by_shape_and_marker():
    assert mc.is_legacy_payload(_legacy(_payload())) is True
    assert mc.is_legacy_payload(_record()) is False  # a deferred store write
    no_marker = _legacy(_payload())
    no_marker["text"] = no_marker["text"].replace(mc.UCG_MARKER, "")
    assert mc.is_legacy_payload(no_marker) is False
    no_title = _legacy(_payload())
    del no_title["title"]
    assert mc.is_legacy_payload(no_title) is False
    assert mc.is_legacy_payload(None) is False
    assert mc.is_legacy_payload([_legacy(_payload())]) is False


def test_legacy_payload_converts_with_its_own_build_time():
    record = mc.legacy_payload_to_record(_legacy(_payload(), project="widget"))
    assert record == _record()
    assert record["created_at_epoch"] == _DATE_MS  # valid_until.date, not now
    assert mc.legacy_payload_to_record(_legacy(_payload(), project=None))["project"] == ""


@pytest.mark.parametrize(
    "inner",
    [
        "{not json",
        {k: v for k, v in _payload().items() if k != "run_id"},
        _payload(run_id="r1"),
        _payload(fingerprint=None),
        {**_payload(), "valid_until": {"sha": None, "date": "not a date"}},
        {**_payload(), "schema_version": 99},
    ],
    ids=["fenced-json-unparseable", "no-run-id", "bad-run-id", "no-fingerprint", "bad-date", "newer-schema"],
)
def test_unconvertible_legacy_payload_returns_none(inner):
    assert mc.legacy_payload_to_record(_legacy(inner)) is None


def test_non_legacy_payload_is_not_converted():
    assert mc.legacy_payload_to_record(_record()) is None
    assert mc.legacy_payload_to_record({"text": "x", "title": "y", "project": "z"}) is None


def test_extract_payload_reads_only_what_follows_the_marker():
    # Only the marker proves an outbox payload is ours, and only the first
    # JSON object after it is read: never foreign prose from position 0.
    assert mc.extract_payload(_legacy(_payload())) == _payload()
    for sample in (
        {"text": "no marker {\"a\": 1}"},
        {"text": f"x {mc.UCG_MARKER} no brace"},
        {"text": f"x {mc.UCG_MARKER} {{not json"},
        {"text": f"x {mc.UCG_MARKER} [1, 2]"},
        {"text": None},
        {},
        "not a dict",
    ):
        assert mc.extract_payload(sample) is None
    assert mc.carries_marker(_legacy(_payload())) is True
    assert mc.carries_marker({"text": "UCG run for epic 7"}) is False
    assert mc.carries_marker("text") is False


@_nested_past_the_limit
def test_extract_payload_returns_none_on_json_nested_past_the_recursion_limit(nested):
    # Never raises: the drain dead-letters such an entry as unconvertible.
    legacy = _legacy('{"a": ' + nested + "}")
    assert mc.extract_payload(legacy) is None
    assert mc.legacy_payload_to_record(legacy) is None


# ---------------------------------------------------------------------------
# Latch v2
# ---------------------------------------------------------------------------

_LATCH_V2_KEYS = {
    "latch_version", "run_id", "backend", "store_ok", "recall", "store", "fingerprint", "created_at",
}


def test_v1_latch_helpers_are_unchanged():
    assert mc.LATCH_VERSION == 1
    assert mc.LATCH_VERSION_V2 == 2


def test_build_latch_v2_has_the_exact_shape(tmp_path):
    state = mc.build_latch_v2(
        run_id=_RUN, recall="on", store=tmp_path, store_ok=True, fingerprint=_FP
    )
    assert set(state) == _LATCH_V2_KEYS
    assert state["latch_version"] == 2
    assert state["backend"] == "jsonl"
    assert state["store"] == str(tmp_path)
    assert state["store_ok"] is True
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", state["created_at"])
    with pytest.raises(ValueError):
        mc.build_latch_v2(run_id="r1", recall="on", store=None, store_ok=False, fingerprint=None)
    with pytest.raises(ValueError):
        mc.build_latch_v2(run_id=_RUN, recall="maybe", store=None, store_ok=False, fingerprint=None)


@_needs_git
def test_measure_latch_green_with_a_writable_store(tmp_path, home):
    repo = tmp_path / "widget"
    _init_repo(repo)
    measure = mc.measure_latch_v2(
        run_id=_RUN, recall="on", store_value="~/.ultracode-goal/recall", cwd=repo
    )
    store = home / ".ultracode-goal" / "recall"
    assert measure.reason is None
    assert measure.notes == []
    assert measure.state["store_ok"] is True
    assert measure.state["store"] == str(store)
    assert measure.state["fingerprint"] == mc.repo_fingerprint(repo)["value"]
    assert (store / ".gitignore").read_bytes() == b"*\n"
    path = mc.write_state(tmp_path / "impl", measure.state)
    view = mc.latch_view(mc.read_state(tmp_path / "impl"))
    assert view == {
        "latch_version": 2, "store_ok": True, "store": str(store), "run_id": _RUN, "recall": "on",
    }
    assert [p.name for p in path.parent.iterdir()] == [".mem-state.json"]


@pytest.mark.parametrize("value", ["", "   ", "{workflow.cross_session_recall_store}", "$VAR", None])
def test_measure_latch_on_with_unset_store_is_red_with_the_note(value, tmp_path, home):
    measure = mc.measure_latch_v2(run_id=_RUN, recall="on", store_value=value, cwd=tmp_path)
    assert measure.state["store_ok"] is False
    assert measure.state["store"] is None
    assert measure.reason == "store-unset"
    assert len(measure.notes) == 1
    assert measure.notes[0].startswith("NOTE recall-store-unset")
    assert "cross_session_recall_store" in measure.notes[0]


def test_measure_latch_off_never_probes_and_never_notes(tmp_path, home):
    unset = mc.measure_latch_v2(run_id=_RUN, recall="off", store_value="", cwd=tmp_path)
    assert (unset.state["store"], unset.state["store_ok"], unset.notes) == (None, False, [])
    assert unset.reason == "recall-off"
    store = home / "recall"
    set_off = mc.measure_latch_v2(run_id=_RUN, recall="off", store_value=str(store), cwd=tmp_path)
    assert set_off.state["store"] == str(store)  # the guard still gates by path
    assert set_off.state["store_ok"] is False
    assert set_off.state["recall"] == "off"
    assert not store.exists()


@_needs_git
def test_measure_latch_unwritable_store_is_red_and_creates_nothing(tmp_path, home):
    repo = tmp_path / "widget"
    _init_repo(repo)
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    measure = mc.measure_latch_v2(
        run_id=_RUN, recall="on", store_value=str(blocker / "recall"), cwd=repo
    )
    assert measure.state["store_ok"] is False
    assert measure.state["store"] == str(blocker / "recall")
    assert measure.reason.startswith("store-unwritable: ")
    assert blocker.read_text(encoding="utf-8") == "file"


@_needs_git
def test_measure_latch_in_a_repo_with_no_commits_is_red_and_writes_no_folder(tmp_path, home):
    repo = tmp_path / "empty"
    repo.mkdir()
    _git(repo, "init", "-q")
    store = home / "recall"
    measure = mc.measure_latch_v2(run_id=_RUN, recall="on", store_value=str(store), cwd=repo)
    assert measure.state["store_ok"] is False
    assert measure.state["fingerprint"] is None
    assert measure.reason == "no-fingerprint"
    assert not store.exists()


def test_measure_latch_bad_run_id_raises_before_any_write(tmp_path, home):
    store = home / "recall"
    with pytest.raises(ValueError):
        mc.measure_latch_v2(run_id="../x", recall="on", store_value=str(store), cwd=tmp_path)
    assert not store.exists()


# An absolute path on this OS ("/abs/recall" has no drive on Windows).
_ABS_STORE = os.path.abspath(os.path.join(os.sep, "abs", "recall"))


def _v2(**overrides) -> dict:
    state = {
        "latch_version": 2, "run_id": _RUN, "backend": "jsonl", "store_ok": True,
        "recall": "on", "store": _ABS_STORE, "fingerprint": _FP,
        "created_at": "2026-06-04T17:25:12Z",
    }
    state.update(overrides)
    return state


def test_latch_view_reads_v1_as_red(tmp_path):
    v1_green_by_old_rules = {
        "latch_version": 1, "run_id": _RUN, "claude_mem": "present", "schema_ok": True,
        "recall": "on", "tool_form": "plugin", "fingerprint": _FP, "created_at": _DATE,
    }
    view = mc.latch_view(v1_green_by_old_rules)
    assert (view["latch_version"], view["store_ok"], view["store"]) == (1, False, None)


@pytest.mark.parametrize(
    "state, version, green",
    [
        (_v2(), 2, True),
        (_v2(store_ok=False), 2, False),
        (_v2(store_ok="true"), 2, False),
        (_v2(recall="off"), 2, False),
        (_v2(backend="claude-mem"), 2, False),
        (_v2(latch_version=3), 3, False),
        (_v2(latch_version=True), None, False),
        (_v2(latch_version="2"), None, False),
        (None, None, False),
        ([1, 2], None, False),
        ("latch", None, False),
    ],
    ids=["green", "store-not-ok", "store-ok-string", "recall-off", "other-backend", "v3",
         "version-bool", "version-string", "none", "list", "string"],
)
def test_latch_view_colour(state, version, green):
    view = mc.latch_view(state)
    assert view["latch_version"] == version
    assert view["store_ok"] is green
    if green:
        assert view["store"] == _ABS_STORE


@pytest.mark.parametrize(
    "store",
    ["", "   ", "{workflow.cross_session_recall_store}", "$VAR", "recall", "/abs/re\0call", 7, None, "missing"],
)
def test_latch_view_unset_store_reads_as_no_store(store, tmp_path, home):
    state = _v2()
    if store == "missing":
        del state["store"]
    else:
        state["store"] = store
    view = mc.latch_view(state)
    assert view["store"] is None
    assert view["store_ok"] is False


def test_latch_view_resolves_a_home_relative_store(tmp_path, home):
    view = mc.latch_view(_v2(store="~/.ultracode-goal/recall"))
    assert view["store"] == str(home / ".ultracode-goal" / "recall")
    assert view["store_ok"] is True


@pytest.mark.parametrize("name", ["my$proj", "a$b", "${x}", "{x}", "odd{name}$dir", "%TEMP%"])
def test_latch_view_takes_a_resolved_store_as_written(name, tmp_path, home):
    # The latch holds the resolved root, which may carry a "$", braces or "%"
    # of its own (a project root named my$proj): it reads green, with that
    # store, exactly as measure_latch_v2 wrote it. Re-applying the unset-token
    # rule here would read a green latch as red with no store, and the guard,
    # which mirrors this view, would then match no store path at all.
    project = tmp_path / name
    measure = mc.measure_latch_v2(
        run_id=_RUN, recall="on", store_value="{project-root}/.recall",
        cwd=tmp_path, project_root=project,
    )
    assert measure.state["store"] == str(project / ".recall")
    view = mc.latch_view({**measure.state, "store_ok": True})
    assert view["store"] == str(project / ".recall")
    assert view["store_ok"] is True


# ---------------------------------------------------------------------------
# project: the main worktree's directory name (AC-28 at the module level)
# ---------------------------------------------------------------------------


@_needs_git
def test_main_worktree_name_is_shared_by_worktrees(tmp_path, home):
    repo = tmp_path / "widget"
    _init_repo(repo)
    (repo / "sub").mkdir()
    assert mc.main_worktree_name(repo) == "widget"
    assert mc.main_worktree_name(repo / "sub") == "widget"
    worktree = tmp_path / "widget-feature"
    _git(repo, "worktree", "add", "-q", "-b", "feature", str(worktree))
    assert mc.main_worktree_name(worktree) == "widget"
    # One fingerprint, so the worktree reads the main checkout's records.
    assert mc.repo_fingerprint(worktree) == mc.repo_fingerprint(repo)


def test_main_worktree_name_outside_git_is_none(tmp_path):
    assert mc.main_worktree_name(tmp_path) is None
