#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for mem_observation.py (Cross-Session Recall build / spill / drain).

Risk-named, hermetic. The CLI is exercised via subprocess so the real
stdin/stdout contract is tested. GIT_* env is scrubbed so repo_fingerprint()
runs against the temp repos these tests build.

Run: uv run --with pytest pytest test_mem_observation.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "mem_observation.py"

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


def _payload_from_build(out_text: str) -> dict:
    """Extract the embedded UCG JSON payload from a build() text field."""
    assert MARKER in out_text
    after = out_text.split(MARKER, 1)[1]
    brace = after.index("{")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(after[brace:])
    return obj


# --- build: NOT_EVALUATED skips, WAIVED writes ------------------------------


def test_not_evaluated_skips(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    proc = _run(
        "build", "--impl-artifacts", str(tmp_path / "impl"),
        "--epic", "7", "--run-id", "r1", "--gate-status", "NOT_EVALUATED",
        "--verdict", "blocked", "--project", "proj", "--cwd", str(repo),
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["skip"] is True
    assert "text" not in out


def test_waived_writes_payload(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    proc = _run(
        "build", "--impl-artifacts", str(tmp_path / "impl"),
        "--epic", "7", "--run-id", "r1", "--gate-status", "WAIVED",
        "--verdict", "advance", "--project", "proj", "--cwd", str(repo),
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["title"] == "UCG run — epic 7: advance"
    assert out["project"] == "proj"
    payload = _payload_from_build(out["text"])
    assert payload["ucg"] == 1
    assert payload["schema_version"] == 1
    assert payload["kind"] == "run-summary"
    assert payload["gate_status"] == "WAIVED"
    assert payload["verdict"] == "advance"
    assert payload["fingerprint"]  # a real fingerprint was pinned


def test_build_marker_and_fenced_block_present(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    out = json.loads(_run(
        "build", "--impl-artifacts", str(tmp_path / "impl"),
        "--epic", "9", "--run-id", "r1", "--gate-status", "PASS",
        "--verdict", "advance", "--project", "proj", "--cwd", str(repo),
    ).stdout)
    assert MARKER in out["text"]
    assert "```json" in out["text"]


# --- build: root cause taxonomy + signature --------------------------------


def test_root_cause_unknown_maps_to_other(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    out = json.loads(_run(
        "build", "--impl-artifacts", str(tmp_path / "impl"),
        "--epic", "7", "--run-id", "r1", "--gate-status", "PASS",
        "--verdict", "advance", "--project", "proj", "--cwd", str(repo),
        "--root-cause", "class=not-a-real-class,path=src/x.py",
    ).stdout)
    payload = _payload_from_build(out["text"])
    assert payload["signatures"][0]["class"] == "other"


def test_root_cause_signature_is_sha1_12(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    out = json.loads(_run(
        "build", "--impl-artifacts", str(tmp_path / "impl"),
        "--epic", "7", "--run-id", "r1", "--gate-status", "PASS",
        "--verdict", "advance", "--project", "proj", "--cwd", str(repo),
        "--root-cause", "class=race-condition,path=src/x.py",
    ).stdout)
    sig = payload = _payload_from_build(out["text"])["signatures"][0]
    assert sig["class"] == "race-condition"
    assert len(sig["sig"]) == 12
    assert all(c in "0123456789abcdef" for c in sig["sig"])


# --- build: redaction -------------------------------------------------------


def test_build_redacts_known_secrets(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    # Plant an AKIA key in a root-cause path and a ghp_ token in the verdict.
    out = json.loads(_run(
        "build", "--impl-artifacts", str(tmp_path / "impl"),
        "--epic", "7", "--run-id", "r1", "--gate-status", "PASS",
        "--verdict", "advance ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "--project", "proj", "--cwd", str(repo),
        "--root-cause", "class=security,path=AKIAIOSFODNN7EXAMPLE/creds.txt",
    ).stdout)
    text = out["text"]
    assert "AKIAIOSFODNN7EXAMPLE" not in text
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in text
    assert "[redacted]" in text
    payload = _payload_from_build(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in payload["signatures"][0]["path"]


def test_build_redacts_advisory_sig(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    out = json.loads(_run(
        "build", "--impl-artifacts", str(tmp_path / "impl"),
        "--epic", "7", "--run-id", "r1", "--gate-status", "PASS",
        "--verdict", "advance", "--project", "proj", "--cwd", str(repo),
        "--advisory", "sig=token=supersecretvalue123,recurred=yes",
    ).stdout)
    payload = _payload_from_build(out["text"])
    adv = payload["advisories"][0]
    assert adv["recurred"] == "yes"
    assert "supersecretvalue123" not in adv["sig"]


def test_advisory_recurred_normalized(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    out = json.loads(_run(
        "build", "--impl-artifacts", str(tmp_path / "impl"),
        "--epic", "7", "--run-id", "r1", "--gate-status", "PASS",
        "--verdict", "advance", "--project", "proj", "--cwd", str(repo),
        "--advisory", "sig=abc,recurred=maybe",
    ).stdout)
    payload = _payload_from_build(out["text"])
    assert payload["advisories"][0]["recurred"] == "unknown"


# --- build: deferred_count --------------------------------------------------


DEFERRED_LEDGER = """# Deferred Work

## Epic 7 deferred

- skip flaky integration test for now
- backfill perf benchmark
- harden the retry path

## Epic 8 deferred

- unrelated item
"""


def test_deferred_count_parses_ledger(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    ledger = tmp_path / "deferred-work.md"
    ledger.write_text(DEFERRED_LEDGER)
    out = json.loads(_run(
        "build", "--impl-artifacts", str(tmp_path / "impl"),
        "--epic", "7", "--run-id", "r1", "--gate-status", "PASS",
        "--verdict", "advance", "--project", "proj", "--cwd", str(repo),
        "--deferred", str(ledger),
    ).stdout)
    payload = _payload_from_build(out["text"])
    assert payload["deferred_count"] == 3  # only Epic 7's three bullets


def test_deferred_count_absent_file_is_zero(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    out = json.loads(_run(
        "build", "--impl-artifacts", str(tmp_path / "impl"),
        "--epic", "7", "--run-id", "r1", "--gate-status", "PASS",
        "--verdict", "advance", "--project", "proj", "--cwd", str(repo),
        "--deferred", str(tmp_path / "nope.md"),
    ).stdout)
    payload = _payload_from_build(out["text"])
    assert payload["deferred_count"] == 0


# --- build: valid_until -----------------------------------------------------


def test_valid_until_sha_passed_through(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    out = json.loads(_run(
        "build", "--impl-artifacts", str(tmp_path / "impl"),
        "--epic", "7", "--run-id", "r1", "--gate-status", "PASS",
        "--verdict", "advance", "--project", "proj", "--cwd", str(repo),
        "--valid-until-sha", "abc123", "--valid-until-date", "2026-12-31T00:00:00Z",
    ).stdout)
    payload = _payload_from_build(out["text"])
    assert payload["valid_until"]["sha"] == "abc123"
    assert payload["valid_until"]["date"] == "2026-12-31T00:00:00Z"


# --- spill: two independent JSONL lines in one run --------------------------


def test_spill_appends_two_independent_lines(tmp_path):
    impl = tmp_path / "impl"
    p1 = _run("spill", "--impl-artifacts", str(impl), "--run-id", "run-X",
              stdin=json.dumps({"text": "a", "title": "t1", "project": "p"}))
    p2 = _run("spill", "--impl-artifacts", str(impl), "--run-id", "run-X",
              stdin=json.dumps({"text": "b", "title": "t2", "project": "p"}))
    assert p1.returncode == 0 and p2.returncode == 0
    outbox = impl / "mem-outbox.run-X.jsonl"
    lines = outbox.read_text().splitlines()
    assert len(lines) == 2
    e1 = json.loads(lines[0])
    e2 = json.loads(lines[1])
    assert e1["payload"]["title"] == "t1"
    assert e2["payload"]["title"] == "t2"
    assert e1["attempts"] == 0 and e2["attempts"] == 0
    assert "spilled_at" in e1 and "spilled_at" in e2


def test_spill_creates_impl_dir(tmp_path):
    impl = tmp_path / "deep" / "nested" / "impl"
    proc = _run("spill", "--impl-artifacts", str(impl), "--run-id", "r",
                stdin=json.dumps({"x": 1}))
    assert proc.returncode == 0
    assert (impl / "mem-outbox.r.jsonl").is_file()


# --- drain: TTL expiry / dead-letter / attempt increment --------------------


def _spill_raw(impl: Path, run_id: str, payload: dict, attempts: int, spilled_at: str) -> None:
    impl.mkdir(parents=True, exist_ok=True)
    entry = {"payload": payload, "attempts": attempts, "spilled_at": spilled_at}
    with (impl / f"mem-outbox.{run_id}.jsonl").open("a", encoding="utf-8") as h:
        h.write(json.dumps(entry, sort_keys=True) + "\n")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_drain_expires_past_ttl_with_tombstone(tmp_path):
    impl = tmp_path / "impl"
    now = datetime(2026, 6, 4, tzinfo=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    old = _iso(now - timedelta(days=30))  # older than ttl 14
    _spill_raw(impl, "run-old", {"k": "v"}, attempts=0, spilled_at=old)
    proc = _run("drain", "--impl-artifacts", str(impl),
                "--ttl-days", "14", "--now-epoch", str(now_ms))
    out = json.loads(proc.stdout)
    assert out["tombstones"] == 1
    assert out["replayable"] == []
    # The expired entry is removed (file emptied -> removed).
    assert not (impl / "mem-outbox.run-old.jsonl").exists()


def test_drain_dead_letters_attempts_at_three(tmp_path):
    impl = tmp_path / "impl"
    now = datetime(2026, 6, 4, tzinfo=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    fresh = _iso(now - timedelta(days=1))
    _spill_raw(impl, "run-dl", {"k": "v"}, attempts=3, spilled_at=fresh)
    proc = _run("drain", "--impl-artifacts", str(impl),
                "--ttl-days", "14", "--now-epoch", str(now_ms))
    out = json.loads(proc.stdout)
    assert out["dead_lettered"] == 1
    assert out["replayable"] == []
    dead = (impl / "mem-outbox.dead.jsonl").read_text().splitlines()
    assert len(dead) == 1
    dead_entry = json.loads(dead[0])
    assert dead_entry["attempts"] == 3
    assert dead_entry["spilled_at"] == fresh  # original stamp preserved verbatim


def test_drain_replays_and_increments_attempts(tmp_path):
    impl = tmp_path / "impl"
    now = datetime(2026, 6, 4, tzinfo=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    fresh = _iso(now - timedelta(days=1))
    _spill_raw(impl, "run-r", {"text": "payload-body"}, attempts=1, spilled_at=fresh)
    proc = _run("drain", "--impl-artifacts", str(impl),
                "--ttl-days", "14", "--now-epoch", str(now_ms))
    out = json.loads(proc.stdout)
    assert out["tombstones"] == 0
    assert out["dead_lettered"] == 0
    assert len(out["replayable"]) == 1
    item = out["replayable"][0]
    assert item["payload"] == {"text": "payload-body"}
    assert item["line_no"] == 1
    assert item["file"].endswith("mem-outbox.run-r.jsonl")
    # attempts bumped 1 -> 2 in place; spilled_at preserved.
    line = (impl / "mem-outbox.run-r.jsonl").read_text().splitlines()[0]
    entry = json.loads(line)
    assert entry["attempts"] == 2
    assert entry["spilled_at"] == fresh
    assert entry["payload"] == {"text": "payload-body"}


def test_drain_mixed_batch(tmp_path):
    impl = tmp_path / "impl"
    now = datetime(2026, 6, 4, tzinfo=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    fresh = _iso(now - timedelta(days=1))
    old = _iso(now - timedelta(days=40))
    # One replayable, one expired, one dead-lettered — across two run files.
    _spill_raw(impl, "run-a", {"id": 1}, attempts=0, spilled_at=fresh)
    _spill_raw(impl, "run-a", {"id": 2}, attempts=0, spilled_at=old)
    _spill_raw(impl, "run-b", {"id": 3}, attempts=5, spilled_at=fresh)
    proc = _run("drain", "--impl-artifacts", str(impl),
                "--ttl-days", "14", "--now-epoch", str(now_ms))
    out = json.loads(proc.stdout)
    assert out["tombstones"] == 1
    assert out["dead_lettered"] == 1
    assert len(out["replayable"]) == 1
    assert out["replayable"][0]["payload"] == {"id": 1}


def test_drain_empty_dir(tmp_path):
    impl = tmp_path / "impl"
    impl.mkdir()
    proc = _run("drain", "--impl-artifacts", str(impl), "--now-epoch", "1780000000000")
    out = json.loads(proc.stdout)
    assert out == {"replayable": [], "tombstones": 0, "dead_lettered": 0}


def test_drain_missing_dir(tmp_path):
    proc = _run("drain", "--impl-artifacts", str(tmp_path / "nope"),
                "--now-epoch", "1780000000000")
    out = json.loads(proc.stdout)
    assert out == {"replayable": [], "tombstones": 0, "dead_lettered": 0}


def test_drain_ignores_dead_letter_file(tmp_path):
    impl = tmp_path / "impl"
    impl.mkdir()
    # A pre-existing dead-letter file must not be re-scanned as an outbox.
    (impl / "mem-outbox.dead.jsonl").write_text(
        json.dumps({"payload": {"x": 1}, "attempts": 9, "spilled_at": "2026-06-04T00:00:00Z"}) + "\n"
    )
    proc = _run("drain", "--impl-artifacts", str(impl), "--now-epoch", "1780000000000")
    out = json.loads(proc.stdout)
    assert out["replayable"] == []
    assert out["dead_lettered"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
