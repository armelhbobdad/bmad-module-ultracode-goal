#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for health_check_fp.py.

Covers the fingerprint byte-format (fp and the keyless legacy_fp, locked against
golden sha1s computed in the test), the fp regex contract and the severity,
stage, slug and defect-key validation; the section heading and defect name read
from --stdin, with the slug and key rules; `queue`'s naming, counter and
byte-for-byte copy; the `seen` verdict table, including the
legacy-fingerprint demotions and the issue-state check it runs through `gh`
(a fake gh on PATH that answers, fails, prints junk or hangs, and a gh planted
in the current folder that must never run); and `record`'s validation, merge,
resolved guard, lock, fsync-and-rename write and corrupt-cache set-aside.

The script is exercised via subprocess (sys.executable + absolute path) to test
the real CLI surface, mirroring test_preflight_check.py. Every subprocess gets a
PATH that holds no gh, so no test reaches a gh the developer installed. Tests
that need a time limit shorter than the script's own, a patched clock or a
failing rename load the script as a module and call main() in-process. The fake
gh is a POSIX shell script, so the tests that need it skip on Windows.

Run: uv run --with pytest pytest test_health_check_fp.py -v
"""

from __future__ import annotations

import errno
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "health_check_fp.py"
HEALTH_CHECK_MD = Path(__file__).resolve().parents[2] / "references" / "health-check.md"

# A folder that does not exist, so it holds no gh: the PATH of every CLI call.
NO_GH_PATH = str(Path(__file__).resolve().parent / "no-gh-here")

URL = "https://github.com/o/r/issues/1"
FP, LEGACY, OTHER = "fp-abc1234", "fp-1234abc", "fp-7654321"
DAY = "2026-11-14"

needs_posix = pytest.mark.skipif(os.name == "nt", reason="the fake gh is a POSIX shell script")


def _env(path: str = NO_GH_PATH, **extra: str) -> dict:
    env = dict(os.environ)
    env["PATH"] = path
    env.update(extra)
    return env


def _run(*args: str, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=_env() if env is None else env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )


def _load():
    """The script as a fresh module, so a constant patched in one test never leaks into another."""
    spec = importlib.util.spec_from_file_location("health_check_fp_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mod():
    return _load()


def _main(module, capsys, *args: str) -> tuple[int, dict]:
    code = module.main(list(args))
    out = capsys.readouterr().out
    return code, json.loads(out)


def _fingerprint(severity: str, stage: str, slug: str, key: str = "staging-path") -> subprocess.CompletedProcess[str]:
    # The `=` form, so a value that starts with a dash reaches the script's own check.
    return _run(
        "fingerprint",
        "--severity",
        severity,
        "--stage",
        stage,
        f"--section-slug={slug}",
        f"--defect-key={key}",
    )


def _expected_fp(severity: str, stage: str, slug: str, key: str) -> tuple[str, str, str]:
    """Recompute both fingerprints independently to lock the byte format."""
    step_file = f"skills/ultracode-goal/references/{stage}.md"
    legacy = f"{severity}|ultracode-goal/{stage}|{step_file}|{slug}"
    keyed = f"{legacy}|{key}"

    def sha7(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:7]

    return f"fp-{sha7(keyed)}", f"fp-{sha7(legacy)}", keyed


def _write_cache(path: Path, data) -> Path:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _live(action: str = "created", url: str | None = URL) -> dict:
    record = {"action": action, "date": "2026-10-01"}
    if url is not None:
        record["issue_url"] = url
    return record


def _seen(cache: Path, fp: str = FP, legacy: str = LEGACY, env: dict | None = None,
          cwd: Path | None = None) -> dict:
    proc = _run("seen", "--fp", fp, "--legacy-fp", legacy, "--cache", str(cache), env=env, cwd=cwd)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def _record(cache: Path, *extra: str, fp: str = FP, action: str = "created", url: str = URL,
            day: str = DAY) -> subprocess.CompletedProcess[str]:
    return _run("record", "--fp", fp, "--cache", str(cache), f"--issue-url={url}", "--action", action,
                "--date", day, *extra)


# --- Fingerprint: golden byte-format lock ----------------------------------


def test_fingerprint_matches_independent_golden():
    proc = _fingerprint("bug", "preflight", "missing-staging-path", "staging-path")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)

    expected_fp, expected_legacy, expected_tuple = _expected_fp(
        "bug", "preflight", "missing-staging-path", "staging-path"
    )
    assert payload == {
        "fp": expected_fp,
        "legacy_fp": expected_legacy,
        "tuple": expected_tuple,
        "section_slug": "missing-staging-path",
        "defect_key": "staging-path",
    }
    # The exact tuple the script hashes: install-mode-invariant step_file form, then the defect key.
    assert payload["tuple"] == (
        "bug|ultracode-goal/preflight|"
        "skills/ultracode-goal/references/preflight.md|missing-staging-path|staging-path"
    )


def test_the_keyed_fingerprint_and_its_legacy_twin():
    proc = _fingerprint("bug", "gate", "verdict-mapping", "gate-status")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert set(payload) == {"fp", "legacy_fp", "tuple", "section_slug", "defect_key"}
    assert payload["tuple"].endswith("|verdict-mapping|gate-status")
    assert (payload["fp"], payload["legacy_fp"]) == _expected_fp("bug", "gate", "verdict-mapping", "gate-status")[:2]
    # Literal goldens. fp-3d74222 is what the keyless script (91f0e02) printed as the fingerprint
    # of this finding: issues and records made before the defect key carry it.
    assert payload["fp"] == "fp-4e6fb0f"
    assert payload["legacy_fp"] == "fp-3d74222"


def test_fingerprint_matches_fp_regex():
    payload = json.loads(_fingerprint("friction", "execute", "ambiguous-budget").stdout)
    assert re.fullmatch(r"fp-[0-9a-f]{7}", payload["fp"])
    assert re.fullmatch(r"fp-[0-9a-f]{7}", payload["legacy_fp"])


# --- Fingerprint: determinism + sensitivity --------------------------------


def _fps(severity: str, stage: str, slug: str, key: str = "gate-status") -> dict:
    proc = _fingerprint(severity, stage, slug, key)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_fingerprint_is_deterministic_for_identical_inputs():
    assert _fps("gap", "gate", "verdict-mapping") == _fps("gap", "gate", "verdict-mapping")


def test_changing_severity_changes_fp():
    assert _fps("bug", "gate", "verdict-mapping")["fp"] != _fps("friction", "gate", "verdict-mapping")["fp"]


def test_changing_stage_changes_fp():
    assert _fps("bug", "gate", "verdict-mapping")["fp"] != _fps("bug", "finalize", "verdict-mapping")["fp"]


def test_changing_section_slug_changes_fp():
    assert _fps("bug", "gate", "verdict-mapping")["fp"] != _fps("bug", "gate", "reloop-budget")["fp"]


def test_two_defects_in_one_section_share_only_the_legacy_fp():
    a = _fps("bug", "gate", "verdict-mapping", "gate-status")
    b = _fps("bug", "gate", "verdict-mapping", "nfr-status")
    assert a["fp"] != b["fp"], "two defect keys in one section must get two fingerprints"
    assert a["legacy_fp"] == b["legacy_fp"], "the section fingerprint ignores the key"


# --- Fingerprint: validation -----------------------------------------------


def test_invalid_stage_exits_one_with_json_error():
    proc = _fingerprint("bug", "not-a-stage", "some-slug")
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


def test_invalid_severity_exits_one():
    proc = _fingerprint("critical", "preflight", "some-slug")
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


@pytest.mark.parametrize("slug", ["Some-Slug", "some_slug", "some-slug\n", "", "-some"])
def test_invalid_slug_exits_one(slug):
    proc = _fingerprint("bug", "preflight", slug)
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


@pytest.mark.parametrize(
    "key",
    ["a-b-c-d-e", "Gate-Status", "gate_status", "gate-status\n", "", "-gate", "gate--status", "gate status"],
)
def test_a_defect_key_that_is_not_one_to_four_kebab_words_exits_one(key):
    proc = _fingerprint("bug", "gate", "verdict-mapping", key)
    assert proc.returncode == 1
    assert "defect-key" in json.loads(proc.stdout)["error"]


@pytest.mark.parametrize("key", ["gate", "gate-status", "a-b-c-d", "cycle-profile-2"])
def test_a_defect_key_of_one_to_four_words_is_accepted(key):
    assert _fingerprint("bug", "gate", "verdict-mapping", key).returncode == 0


def test_the_defect_key_is_required():
    proc = _run("fingerprint", "--severity", "bug", "--stage", "gate", "--section-slug", "verdict-mapping")
    assert proc.returncode == 2, "an argparse usage error exits 2"


# --- Fingerprint: the heading and the name on stdin ---------------------------


def _fingerprint_stdin(severity: str, stage: str, names, *flags: str) -> tuple[int, dict]:
    """fingerprint --stdin, fed `names` as UTF-8 JSON (or as given when it is bytes)."""
    data = names if isinstance(names, bytes) else json.dumps(names, ensure_ascii=False).encode("utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "fingerprint", "--severity", severity, "--stage", stage, "--stdin", *flags],
        capture_output=True, env=_env(), input=data, timeout=120,
    )
    return proc.returncode, json.loads(proc.stdout.decode("utf-8"))


@pytest.mark.parametrize(
    "heading",
    ["1b. Run the formalize readiness check", "## 1b. Run the formalize readiness check", "  1b. Run the formalize readiness check  "],
)
def test_a_heading_of_the_stage_file_gives_its_slug(heading):
    code, payload = _fingerprint_stdin("bug", "preflight", {"section_heading": heading, "defect_name": "gate_status"})
    assert code == 0, payload
    assert payload["section_slug"] == "run-the-formalize-readiness-check"
    assert payload["defect_key"] == "gate-status"
    # The fingerprints hash the derived slug, exactly as if it had been given with --section-slug.
    assert (payload["fp"], payload["legacy_fp"], payload["tuple"]) == _expected_fp(
        "bug", "preflight", "run-the-formalize-readiness-check", "gate-status"
    )
    assert payload == json.loads(_fingerprint("bug", "preflight", "run-the-formalize-readiness-check",
                                              "gate-status").stdout)


@pytest.mark.parametrize(
    "stage, heading, slug",
    [
        ("preflight", "3. Semantic intervention scan (the part the script cannot do)",
         "semantic-intervention-scan-the-part-the-script-cannot-do"),
        ("execute", "The per-invocation work bound (`--max-stories N`)", "the-per-invocation-work-bound-max-stories-n"),
        ("define-done", "Stage 3 \u2014 Define Done", "stage-3-define-done"),
        ("gate", "Non-web stack: the red phase by hand, and the trace artifacts where trace cannot run",
         "non-web-stack-the-red-phase-by-hand-and-the-trace-artifacts-where-trace-cannot-run"),
    ],
)
def test_real_stage_headings_give_their_slugs(stage, heading, slug):
    code, payload = _fingerprint_stdin("friction", stage, {"section_heading": heading}, "--defect-key=x")
    assert code == 0, payload
    assert payload["section_slug"] == slug


@pytest.mark.parametrize(
    "heading, slug",
    [
        ("1b. Run the formalize readiness check", "run-the-formalize-readiness-check"),
        ("### 5a-ii. If no matching open issue exists", "if-no-matching-open-issue-exists"),
        ("### 4-headless. Unattended routing (no human at the gate)", "unattended-routing-no-human-at-the-gate"),
        ("## 0.5. Enabled gate", "enabled-gate"),
        ("## 5. Severity routing (attended [Y] and [A])", "severity-routing-attended-y-and-a"),
        ("## Step 2.5 is not numbering", "step-2-5-is-not-numbering"),
        ("## 3.5 GHz is not numbering", "3-5-ghz-is-not-numbering"),
        ("## Closing hashes ##", "closing-hashes"),
    ],
)
def test_the_slug_rule(mod, heading, slug):
    assert mod.section_slug(heading) == slug


@pytest.mark.parametrize("stage", ["ingest-and-scope", "preflight", "define-done", "execute", "gate", "finalize"])
def test_every_heading_of_every_stage_file_gives_a_slug(mod, stage):
    headings = mod._stage_headings(mod.REFERENCES_DIR / f"{stage}.md")
    assert headings, stage
    slugs = [mod.section_slug(heading) for heading in headings]
    assert all(slugs), [h for h, slug in zip(headings, slugs) if not slug]
    # Two sections of one stage file never share a slug, so a slug names one section.
    assert len(set(slugs)) == len(slugs), sorted(slug for slug in slugs if slugs.count(slug) > 1)


def test_a_stage_file_that_is_not_utf8_exits_one(tmp_path, mod, monkeypatch, capsys):
    (tmp_path / "gate.md").write_bytes(b"# Stage 5\n\xff\xfe\n")
    monkeypatch.setattr(mod, "REFERENCES_DIR", tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"section_heading": "Stage 5"})))
    code, payload = _main(mod, capsys, "fingerprint", "--severity", "bug", "--stage", "gate", "--stdin", "--defect-key=x")
    assert code == 1
    assert "could not read" in payload["error"]


@pytest.mark.parametrize("heading", ["Run the formalize readiness check (missing)", "verdict-mapping", "1b."])
def test_a_heading_that_is_no_heading_of_the_stage_file_exits_one(heading):
    code, payload = _fingerprint_stdin("bug", "preflight", {"section_heading": heading}, "--defect-key=x")
    assert code == 1
    assert "no heading of references/preflight.md" in payload["error"]


def test_a_heading_line_in_fenced_code_or_frontmatter_is_no_heading(tmp_path, mod, monkeypatch, capsys):
    (tmp_path / "gate.md").write_text(
        "---\n# front: matter\n---\n# Stage 5\n\n```markdown\n# Deferred Work\n```\n\n~~~~\n## In tildes\n~~~~\n"
        "## Route on the verdict ##\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "REFERENCES_DIR", tmp_path)
    for heading, ok in (("Stage 5", True), ("Route on the verdict", True), ("Deferred Work", False),
                        ("In tildes", False), ("front: matter", False)):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"section_heading": heading})))
        code, payload = _main(mod, capsys, "fingerprint", "--severity", "bug", "--stage", "gate", "--stdin",
                              "--defect-key=x")
        assert (code == 0) is ok, (heading, payload)


@pytest.mark.parametrize(
    "name, key",
    [
        ("gate_status", "gate-status"),
        ("--cycle-profile", "cycle-profile"),
        ("operator's own evidence", "operators-own-evidence"),
        ("gate_eval.py", "gate-eval"),
        ("composeStories", "compose-stories"),
        ("one two three four five", "two-three-four-five"),
        ("_private_helper", "private-helper"),
        ("formalize_check.py ready", "formalize-check-py-ready"),
        ("story moved criteria", "story-moved-criteria"),
        ("buildHeadlessEnvelope", "build-headless-envelope"),
        # A path keeps its last component, and a line suffix goes with the extension.
        ("scripts/gate_eval.py", "gate-eval"),
        ("skills\\ultracode-goal\\scripts\\gate_eval.py", "gate-eval"),
        ("gate_eval.py:42", "gate-eval"),
        ("scripts/gate_eval.py:42-50", "gate-eval"),
        # Only a lower-case letter followed by an upper-case one splits, so an acronym stays one word.
        ("getHTTPResponse", "get-httpresponse"),
    ],
)
def test_a_name_gives_its_defect_key(name, key):
    code, payload = _fingerprint_stdin("bug", "gate", {"defect_name": name}, "--section-slug=verdict-mapping")
    assert code == 0, payload
    assert payload["defect_key"] == key
    assert payload["fp"] == _expected_fp("bug", "gate", "verdict-mapping", key)[0]


@pytest.mark.parametrize("name", ["--__", "...", "'"])
def test_a_name_that_yields_no_word_exits_one(name):
    code, payload = _fingerprint_stdin("bug", "gate", {"defect_name": name}, "--section-slug=verdict-mapping")
    assert code == 1
    assert "yields no word" in payload["error"]


@pytest.mark.parametrize(
    "names, flags",
    [
        ({"section_heading": "Route on the verdict", "defect_name": "x"}, ("--section-slug=verdict-mapping",)),
        ({"section_heading": "Route on the verdict", "defect_name": "x"}, ("--defect-key=x",)),
        ({"section_heading": "Route on the verdict"}, ()),
        ({"defect_name": "x"}, ()),
        ({}, ()),
    ],
    ids=["slug-twice", "key-twice", "no-key", "no-slug", "neither"],
)
def test_each_pair_takes_exactly_one_form(names, flags):
    code, payload = _fingerprint_stdin("bug", "gate", names, *flags)
    assert code == 1
    assert "--section-slug" in payload["error"] or "--defect-key" in payload["error"]


@pytest.mark.parametrize(
    "raw",
    [b"", b"not json", b"[1]", b'{"section": "x"}', b'{"section_heading": 1, "defect_name": "x"}',
     b'{"section_heading": " ", "defect_name": "x"}', b"\xff\xfe"],
    ids=["empty", "junk", "list", "unknown-key", "not-a-string", "blank", "not-utf8"],
)
def test_stdin_that_is_not_the_names_object_exits_one(raw):
    code, payload = _fingerprint_stdin("bug", "gate", raw)
    assert code == 1
    assert "error" in payload


def test_the_flags_alone_still_need_both_without_stdin():
    proc = _run("fingerprint", "--severity", "bug", "--stage", "gate", "--defect-key", "gate-status")
    assert proc.returncode == 2, "an argparse usage error exits 2"


# --- queue ---------------------------------------------------------------------------


def _queue(mod, capsys, queue_dir: Path, body: Path, stage: str = "gate") -> tuple[int, dict]:
    return _main(mod, capsys, "queue", "--queue-dir", str(queue_dir), "--stage", stage, "--body-file", str(body))


def test_two_queued_findings_in_the_same_second_get_a_counter(tmp_path, mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_queue_stamp", lambda: "20261114-093012")
    body = tmp_path / "hc-body-fp-abc1234.md"
    body.write_bytes(b"## Workflow\n`ultracode-goal/gate`\r\n\nSection fingerprint: `fp-1234abc`\n\xe2\x9c\x93\n")
    queue_dir = tmp_path / "out" / "improvement-queue"
    paths = []
    for _ in range(3):
        code, result = _queue(mod, capsys, queue_dir, body)
        assert code == 0, result
        paths.append(Path(result["path"]))
    assert [p.name for p in paths] == [
        "hc-ultracode-goal-gate-20261114-093012.md",
        "hc-ultracode-goal-gate-20261114-093012-2.md",
        "hc-ultracode-goal-gate-20261114-093012-3.md",
    ]
    assert all(p.is_absolute() and p.parent == queue_dir.resolve() for p in paths)
    # The body, byte for byte: no frontmatter, line endings and characters as written.
    assert all(p.read_bytes() == body.read_bytes() for p in paths)


def test_a_file_already_there_is_never_overwritten(tmp_path, mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_queue_stamp", lambda: "20261114-093012")
    (tmp_path / "hc-ultracode-goal-execute-20261114-093012.md").write_text("earlier", encoding="utf-8")
    body = tmp_path / "body.md"
    body.write_text("later", encoding="utf-8")
    code, result = _queue(mod, capsys, tmp_path, body, stage="execute")
    assert code == 0
    assert Path(result["path"]).name == "hc-ultracode-goal-execute-20261114-093012-2.md"
    assert (tmp_path / "hc-ultracode-goal-execute-20261114-093012.md").read_text(encoding="utf-8") == "earlier"


def test_the_queue_name_is_the_utc_time(tmp_path, mod, monkeypatch):
    from datetime import datetime, timedelta, timezone

    instant = datetime(2026, 11, 14, 9, 30, 12, tzinfo=timezone.utc)

    class Clock:
        """A host four hours east of UTC: its wall clock differs from the UTC instant."""

        @staticmethod
        def now(tz=None):
            if tz is None:
                return (instant + timedelta(hours=4)).replace(tzinfo=None)
            return instant.astimezone(tz)

    monkeypatch.setattr(mod, "datetime", Clock)
    assert mod._queue_stamp() == "20261114-093012"
    monkeypatch.undo()
    body = tmp_path / "body.md"
    body.write_text("x", encoding="utf-8")
    proc = _run("queue", "--queue-dir", str(tmp_path / "q"), "--stage", "preflight", "--body-file", str(body))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert re.fullmatch(r"hc-ultracode-goal-preflight-[0-9]{8}-[0-9]{6}\.md", Path(json.loads(proc.stdout)["path"]).name)


def test_a_failed_write_leaves_no_partial_queue_file(tmp_path, mod, monkeypatch, capsys):
    body = tmp_path / "body.md"
    body.write_text("x" * 4096, encoding="utf-8")
    queue_dir = tmp_path / "q"

    def disk_full(fd, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(mod.os, "write", disk_full)
    code, result = _queue(mod, capsys, queue_dir, body)
    monkeypatch.undo()
    assert code == 1
    assert "could not write" in result["error"]
    assert queue_dir.is_dir() and list(queue_dir.iterdir()) == []


def test_a_missing_body_file_exits_one_and_creates_nothing(tmp_path):
    proc = _run("queue", "--queue-dir", str(tmp_path / "q"), "--stage", "gate", "--body-file", str(tmp_path / "nope.md"))
    assert proc.returncode == 1
    assert "body file" in json.loads(proc.stdout)["error"]
    assert not (tmp_path / "q").exists()


def test_queue_refuses_a_stage_outside_its_set(tmp_path):
    body = tmp_path / "body.md"
    body.write_text("x", encoding="utf-8")
    proc = _run("queue", "--queue-dir", str(tmp_path / "q"), "--stage", "health-check", "--body-file", str(body))
    assert proc.returncode == 1
    assert "invalid stage" in json.loads(proc.stdout)["error"]
    assert not (tmp_path / "q").exists()


def test_queue_needs_all_three_arguments(tmp_path):
    assert _run("queue", "--queue-dir", str(tmp_path), "--stage", "gate").returncode == 2


# --- seen: the verdict table -------------------------------------------------


def test_seen_missing_cache_is_unseen(tmp_path):
    assert _seen(tmp_path / "nope.json") == {
        "seen": False,
        "status": "unseen",
        "record": None,
        "matched_on": None,
    }


@pytest.mark.parametrize("flag", ["--fp", "--legacy-fp"])
def test_seen_invalid_fingerprint_exits_one(tmp_path, flag):
    values = {"--fp": FP, "--legacy-fp": LEGACY, flag: "fp-XYZ"}
    proc = _run("seen", "--fp", values["--fp"], "--legacy-fp", values["--legacy-fp"],
                "--cache", str(tmp_path / "c.json"))
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


def test_seen_requires_the_legacy_fp(tmp_path):
    proc = _run("seen", "--fp", FP, "--cache", str(tmp_path / "c.json"))
    assert proc.returncode == 2


def test_record_then_seen_round_trip(tmp_path):
    cache = tmp_path / "seen.json"
    rec = _record(cache)
    assert rec.returncode == 0, rec.stdout
    new = {"issue_url": URL, "action": "created", "date": DAY}
    assert json.loads(rec.stdout) == {"written": True, "fp": FP, "record": new, "set_aside": None}

    # No gh on PATH: the issue-state check cannot run, so the record stays handled.
    assert _seen(cache) == {"seen": True, "status": "handled", "record": new, "matched_on": "fp"}


@pytest.mark.parametrize("action", ["created", "reacted", "commented"])
@pytest.mark.parametrize("url", ["", None])
def test_a_written_action_with_no_url_is_handled(tmp_path, action, url):
    cache = _write_cache(tmp_path / "seen.json", {FP: _live(action, url)})
    payload = _seen(cache)
    assert (payload["seen"], payload["status"], payload["matched_on"]) == (True, "handled", "fp")


def test_seen_resolved_does_not_suppress(tmp_path):
    # The fail-open this closes: a fixed finding used to keep suppressing
    # forever, so a REGRESSION of the same defect was silently swallowed.
    cache = _write_cache(tmp_path / "seen.json", {FP: {"action": "resolved", "issue_url": "", "date": "2026-07-19"}})
    payload = _seen(cache)
    assert payload["seen"] is False, "a resolved fingerprint must not suppress"
    assert payload["status"] == "regression"
    # The record RIDES ALONG so the caller can link the original rather than
    # file the recurrence as a first sighting.
    assert payload["record"] == {"action": "resolved", "issue_url": "", "date": "2026-07-19"}
    assert payload["matched_on"] == "fp"


@pytest.mark.parametrize(
    "record",
    [
        {"action": "queued", "issue_url": "", "date": "2026-07-19"},
        {"action": "teleported", "issue_url": "", "date": "2026-07-19"},
        {"issue_url": URL, "date": "2026-07-19"},
        ["not", "an", "object"],
        "created",
    ],
    ids=["old-queued", "unknown-action", "no-action", "a-list", "a-string"],
)
def test_a_record_this_version_does_not_write_is_unrecognized(tmp_path, record):
    # An old `queued` record, a hand-edit or a newer module's record cannot be
    # confirmed handled, so it reports: a duplicate is closed by the dedup Action,
    # a silenced regression is caught by nothing.
    cache = _write_cache(tmp_path / "seen.json", {FP: record})
    payload = _seen(cache)
    assert payload == {"seen": False, "status": "unrecognized", "record": record, "matched_on": "fp"}


def test_a_queued_bug_never_suppresses_a_later_attended_report(tmp_path):
    """A headless run with autosubmit off used to record `queued`, which suppressed the [Y] filing later."""
    cache = tmp_path / "seen.json"
    refused = _record(cache, action="queued", url="")
    assert refused.returncode == 1, "nothing records a queued finding any more"
    assert not cache.exists()
    assert _seen(cache)["seen"] is False


# --- seen: the legacy (section) fingerprint ------------------------------------


@pytest.mark.parametrize("action", ["created", "reacted", "commented"])
def test_a_legacy_record_that_would_suppress_is_unseen(tmp_path, action):
    record = _live(action, "")
    cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
    assert _seen(cache) == {"seen": False, "status": "unseen", "record": record, "matched_on": "legacy_fp"}


def test_a_resolved_legacy_record_is_a_possible_regression(tmp_path):
    record = {"action": "resolved", "issue_url": URL, "date": "2026-07-19"}
    cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
    assert _seen(cache) == {
        "seen": False,
        "status": "possible-regression",
        "record": record,
        "matched_on": "legacy_fp",
    }


def test_an_unrecognized_legacy_record_stays_unrecognized(tmp_path):
    record = {"action": "queued", "issue_url": "", "date": "2026-07-19"}
    cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
    payload = _seen(cache)
    assert (payload["status"], payload["matched_on"]) == ("unrecognized", "legacy_fp")


def test_the_record_under_fp_decides_over_the_legacy_one(tmp_path):
    cache = _write_cache(
        tmp_path / "seen.json",
        {FP: _live("created", ""), LEGACY: {"action": "resolved", "issue_url": "", "date": "2026-01-01"}},
    )
    payload = _seen(cache)
    assert (payload["status"], payload["matched_on"]) == ("handled", "fp")
    assert payload["record"] == _live("created", "")


# --- seen: the issue-state check through gh -------------------------------------

FAKE_GH = """#!/bin/sh
PATH=/usr/bin:/bin
export PATH
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
case "$FAKE_GH_MODE" in
  fail) echo "gh: could not resolve to an issue" >&2; exit 1 ;;
  junk) echo "this is not json" ;;
  hang) sleep 60 & echo $! > "$FAKE_GH_CHILD"; wait ;;
  *) printf '%s\\n' "$FAKE_GH_MODE" ;;
esac
"""


def _plant_gh(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    gh = folder / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    return gh


@pytest.fixture
def fake_gh(tmp_path):
    """A fake gh in its own folder; returns (folder, log). Its mode is the env var FAKE_GH_MODE."""
    folder = tmp_path / "fake-bin"
    _plant_gh(folder)
    return folder, tmp_path / "gh.log"


def _gh_env(fake, mode: str) -> dict:
    folder, log = fake
    return _env(str(folder), FAKE_GH_LOG=str(log), FAKE_GH_MODE=mode)


def _gh_calls(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _answer(state: str, reason: str = "") -> str:
    return json.dumps({"state": state, "stateReason": reason})


@needs_posix
@pytest.mark.parametrize(
    "mode, status",
    [
        (_answer("OPEN"), "handled"),
        (_answer("CLOSED", "NOT_PLANNED"), "handled"),
        (_answer("CLOSED", "DUPLICATE"), "handled"),
        ("fail", "handled"),
        ("junk", "handled"),
        ("[]", "handled"),
        (json.dumps({"stateReason": "COMPLETED"}), "handled"),
        (_answer("CLOSED", "COMPLETED"), "regression"),
        (_answer("MERGED"), "regression"),
    ],
    ids=["open", "not-planned", "duplicate", "fail", "junk", "a-list", "no-state", "completed", "merged"],
)
def test_the_issue_state_decides_a_keyed_record(tmp_path, fake_gh, mode, status):
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})
    payload = _seen(cache, env=_gh_env(fake_gh, mode))
    assert payload == {"seen": status == "handled", "status": status, "record": _live("created"), "matched_on": "fp"}
    assert _gh_calls(fake_gh[1]) == [f"issue view {URL} --json state,stateReason"]


@needs_posix
def test_a_completed_close_under_the_legacy_fp_is_a_possible_regression(tmp_path, fake_gh):
    cache = _write_cache(tmp_path / "seen.json", {LEGACY: _live("created")})
    payload = _seen(cache, env=_gh_env(fake_gh, _answer("CLOSED", "COMPLETED")))
    assert (payload["status"], payload["matched_on"]) == ("possible-regression", "legacy_fp")


def test_an_absent_gh_keeps_a_keyed_record_handled(tmp_path):
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})
    assert _seen(cache)["status"] == "handled"


@needs_posix
@pytest.mark.parametrize(
    "url",
    ["http://github.com/o/r/issues/1", "--web", "https://github.com/o/r/issues/1 --web", "github.com/o/r/issues/1",
     "https://github.com/o/r/issues/1\n"],
    ids=["http", "a-flag", "whitespace", "no-scheme", "newline"],
)
def test_gh_never_runs_for_a_url_that_is_not_plain_https(tmp_path, fake_gh, url):
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created", url)})
    payload = _seen(cache, env=_gh_env(fake_gh, _answer("CLOSED", "COMPLETED")))
    assert payload["status"] == "handled"
    assert _gh_calls(fake_gh[1]) == []


@needs_posix
def test_gh_never_runs_for_a_resolved_or_unrecognized_record(tmp_path, fake_gh):
    cache = _write_cache(
        tmp_path / "seen.json",
        {FP: {"action": "resolved", "issue_url": URL, "date": DAY}, OTHER: {"action": "queued", "issue_url": URL}},
    )
    env = _gh_env(fake_gh, _answer("OPEN"))
    assert _seen(cache, env=env)["status"] == "regression"
    assert _seen(cache, fp=OTHER, env=env)["status"] == "unrecognized"
    assert _gh_calls(fake_gh[1]) == []


@needs_posix
@pytest.mark.parametrize("path_form", [".", "empty-entry", "absolute"])
def test_a_gh_planted_in_the_current_folder_never_runs(tmp_path, path_form):
    """The current folder is the user's project: a gh planted there reads as no gh, and nothing is started."""
    project = tmp_path / "project"
    _plant_gh(project)
    log = tmp_path / "planted.log"
    path = {
        ".": ".",
        "empty-entry": os.pathsep + NO_GH_PATH,
        "absolute": str(project),
    }[path_form]
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})
    env = _env(path, FAKE_GH_LOG=str(log), FAKE_GH_MODE=_answer("CLOSED", "COMPLETED"))
    payload = _seen(cache, env=env, cwd=project)
    assert payload["status"] == "handled"
    assert not log.exists(), "the gh in the current folder ran"


HEARTBEAT = """
import pathlib, subprocess, sys
beat = pathlib.Path(sys.argv[1])
child = (
    "import pathlib, sys, time\\n"
    "beat = pathlib.Path(sys.argv[1])\\n"
    "while True:\\n"
    "    beat.write_text(str(time.monotonic()))\\n"
    "    time.sleep(0.1)\\n"
)
subprocess.Popen([sys.executable, "-c", child, str(beat)])
import time
time.sleep(60)
"""


def test_run_stops_a_call_and_everything_it_started_at_the_limit(tmp_path, mod):
    """Runs on every platform: killpg on POSIX, taskkill /T on Windows. The child's heartbeat stops."""
    beat = tmp_path / "beat"
    start = time.monotonic()
    returncode, _out, _err = mod._run([sys.executable, "-c", HEARTBEAT, str(beat)], 1.0)
    assert returncode is None, "a call stopped at the limit has no exit code"
    assert time.monotonic() - start < 1.0 + 3 * mod.KILL_WAIT_SEC + 5
    assert beat.exists(), "the child never started"
    time.sleep(0.5)
    settled = beat.read_text()
    time.sleep(1.0)
    assert beat.read_text() == settled, "the process the call started outlived the time limit"


def test_replace_is_retried_while_windows_holds_the_target_open(tmp_path, mod, monkeypatch):
    """Windows refuses a rename over a file another process has open; the write lands once it is let go."""
    target = tmp_path / "seen.json"
    target.write_text("{}\n", encoding="utf-8")
    real_replace = os.replace
    refusals = []

    def busy_twice(src, dst):
        if len(refusals) < 2:
            refusals.append(dst)
            raise PermissionError(13, "The process cannot access the file")
        real_replace(src, dst)

    monkeypatch.setattr(mod, "_IS_WINDOWS", True)
    monkeypatch.setattr(mod.os, "replace", busy_twice)
    mod._atomic_write(target, '{"fp-abc1234": {}}\n')
    assert len(refusals) == 2
    assert target.read_text(encoding="utf-8") == '{"fp-abc1234": {}}\n'
    assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"], "no temp file is left"


def test_the_time_limit_is_ten_seconds(mod):
    assert mod.GH_TIMEOUT_SEC == 10.0


def test_seen_hands_gh_the_ten_second_limit(tmp_path, mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_resolve_outside_cwd", lambda name: "/fake/gh" if name == "gh" else None)
    limits = []

    def fake_run(argv, timeout):
        limits.append((argv, timeout))
        return 0, _answer("OPEN").encode("utf-8"), b""

    monkeypatch.setattr(mod, "_run", fake_run)
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})
    code, payload = _main(mod, capsys, "seen", "--fp", FP, "--legacy-fp", LEGACY, "--cache", str(cache))
    assert code == 0 and payload["status"] == "handled"
    assert limits == [(["/fake/gh", "issue", "view", URL, "--json", "state,stateReason"], 10.0)]


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    try:
        return stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"  # a zombie has ended
    except (OSError, IndexError):
        return False


@needs_posix
def test_a_hanging_gh_is_stopped_with_everything_it_started(tmp_path, fake_gh, mod, monkeypatch, capsys):
    folder, log = fake_gh
    child = tmp_path / "child.pid"
    monkeypatch.setenv("PATH", str(folder))
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_MODE", "hang")
    monkeypatch.setenv("FAKE_GH_CHILD", str(child))
    monkeypatch.setattr(mod, "GH_TIMEOUT_SEC", 1.0)
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})

    start = time.monotonic()
    code, payload = _main(mod, capsys, "seen", "--fp", FP, "--legacy-fp", LEGACY, "--cache", str(cache))
    elapsed = time.monotonic() - start

    assert code == 0
    assert (payload["seen"], payload["status"]) == (True, "handled")
    assert elapsed < 1.0 + 3 * mod.KILL_WAIT_SEC + 5
    pid = int(child.read_text(encoding="utf-8").strip())
    deadline = time.monotonic() + 5
    while not _gone(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _gone(pid), "the process gh started outlived the time limit"


# --- record --------------------------------------------------------------------


def test_record_creates_nested_parent_dirs(tmp_path):
    cache = tmp_path / "deep" / "nested" / "tree" / "seen.json"
    rec = _record(cache)
    assert rec.returncode == 0, rec.stdout
    assert cache.is_file()


def test_record_merges_distinct_fps_and_keeps_every_other_key(tmp_path):
    others = {
        LEGACY: {"action": "resolved", "issue_url": "", "date": "2026-01-01"},
        "not-a-fingerprint": [1, 2, 3],
        OTHER: {"action": "queued", "issue_url": "", "date": "2026-02-02"},
    }
    cache = _write_cache(tmp_path / "seen.json", others)
    assert _record(cache, action="reacted").returncode == 0

    data = json.loads(cache.read_text(encoding="utf-8"))
    assert data[FP] == {"issue_url": URL, "action": "reacted", "date": DAY}
    assert {k: v for k, v in data.items() if k != FP} == others, "a legacy record is never rewritten"


def test_record_overwrites_same_fp_in_place(tmp_path):
    cache = tmp_path / "seen.json"
    assert _record(cache, action="created", day="2026-06-04").returncode == 0
    assert _record(cache, action="commented", day="2026-06-05").returncode == 0
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert list(data.keys()) == [FP]
    assert data[FP] == {"issue_url": URL, "action": "commented", "date": "2026-06-05"}


@pytest.mark.parametrize(
    "over",
    [
        {"action": "queued", "url": ""},
        {"action": "upvoted"},
        {"action": "created", "url": ""},
        {"action": "reacted", "url": "http://github.com/o/r/issues/1"},
        {"action": "commented", "url": "--web"},
        {"action": "created", "url": "https://github.com/o/r/issues/1 x"},
        {"action": "resolved", "url": "http://github.com/o/r/pull/2"},
        {"day": "2026-13-01"},
        {"day": "2026-02-30"},
        {"day": "20261114"},
        {"day": DAY + "\n"},
        {"fp": "fp-XYZ"},
        {"fp": FP + "\n"},
    ],
    ids=["queued", "unknown-action", "created-empty-url", "http", "a-flag", "whitespace", "resolved-http",
         "month-13", "feb-30", "no-dashes", "date-newline", "bad-fp", "fp-newline"],
)
def test_a_record_that_breaks_its_rule_exits_one_and_writes_nothing(tmp_path, over):
    cache = tmp_path / "seen.json"
    proc = _record(cache, **over)
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)
    assert not cache.exists()
    assert list(tmp_path.iterdir()) == [], "a refused record takes no lock and writes no file"


@pytest.mark.parametrize("url", ["", "https://github.com/o/r/pull/2"])
def test_resolved_takes_an_empty_or_https_url(tmp_path, url):
    cache = tmp_path / "seen.json"
    proc = _record(cache, action="resolved", url=url)
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["record"] == {"issue_url": url, "action": "resolved", "date": DAY}


def _resolved_cache(tmp_path: Path) -> tuple[Path, dict]:
    resolved = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
    return _write_cache(tmp_path / "seen.json", {FP: resolved, OTHER: _live()}), resolved


@pytest.mark.parametrize("action", ["created", "reacted", "commented"])
def test_a_resolved_record_is_never_downgraded(tmp_path, action):
    cache, resolved = _resolved_cache(tmp_path)
    before = cache.read_bytes()
    proc = _record(cache, action=action, url="https://github.com/o/r/issues/5")
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout) == {"written": False, "fp": FP, "record": resolved, "set_aside": None}
    assert cache.read_bytes() == before


def test_the_regression_issue_replaces_a_resolved_record(tmp_path):
    cache, _ = _resolved_cache(tmp_path)
    new_url = "https://github.com/o/r/issues/5"
    proc = _record(cache, "--regression", url=new_url)
    assert proc.returncode == 0, proc.stdout
    new = {"issue_url": new_url, "action": "created", "date": DAY}
    assert json.loads(proc.stdout) == {"written": True, "fp": FP, "record": new, "set_aside": None}
    assert json.loads(cache.read_text(encoding="utf-8")) == {FP: new, OTHER: _live()}


def test_regression_on_a_record_that_is_not_resolved_writes_as_usual(tmp_path):
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})
    proc = _record(cache, "--regression", action="reacted")
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["written"] is True


def test_a_resolved_record_can_be_resolved_again(tmp_path):
    # The resolve recipe re-run with the resolving PR's URL: not a downgrade.
    cache, _ = _resolved_cache(tmp_path)
    proc = _record(cache, action="resolved", url="https://github.com/o/r/pull/9")
    assert json.loads(proc.stdout)["written"] is True
    assert json.loads(cache.read_text(encoding="utf-8"))[FP]["issue_url"] == "https://github.com/o/r/pull/9"


def test_a_seeded_defect_slug_carries_over_a_resolved_replace(tmp_path):
    """A record written by 7854e70's `record --defect-slug` keeps its slug when the resolve recipe replaces it."""
    seeded = {"action": "created", "issue_url": URL, "date": "2026-08-01", "defect_slug": "wrong-event-guard"}
    cache = _write_cache(tmp_path / "seen.json", {FP: seeded})
    proc = _record(cache, action="resolved", url="", day="2026-08-04")
    assert proc.returncode == 0, proc.stdout
    expected = {"issue_url": "", "action": "resolved", "date": "2026-08-04", "defect_slug": "wrong-event-guard"}
    assert json.loads(proc.stdout)["record"] == expected
    assert json.loads(cache.read_text(encoding="utf-8"))[FP] == expected


def test_record_no_longer_takes_a_defect_slug(tmp_path):
    proc = _record(tmp_path / "seen.json", "--defect-slug", "some-defect")
    assert proc.returncode == 2


# --- record: the corrupt cache ----------------------------------------------------

STAMPED = re.compile(r"seen\.json\.corrupt-\d{8}T\d{6}Z")


@pytest.mark.parametrize(
    "content",
    [b"\x00\xff garbage not json {{{", b"{bad", b"[]", b'"text"', b"\xff\xfe{}", b"[" * 200_000],
    ids=["garbage", "truncated", "a-list", "a-string", "not-utf8", "nested-past-the-parsers-depth"],
)
def test_a_corrupt_cache_is_set_aside_not_erased(tmp_path, content):
    cache = tmp_path / "seen.json"
    cache.write_bytes(content)
    proc = _record(cache)
    assert proc.returncode == 0, proc.stdout
    result = json.loads(proc.stdout)

    aside = Path(result["set_aside"])
    assert aside.parent == tmp_path and STAMPED.fullmatch(aside.name), aside
    assert aside.read_bytes() == content, "the corrupt records stay on disk for a hand repair"
    assert json.loads(cache.read_text(encoding="utf-8")) == {FP: {"issue_url": URL, "action": "created",
                                                                  "date": DAY}}
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["seen.json", "seen.json.lock", aside.name])


def test_seen_reads_a_corrupt_cache_as_unseen(tmp_path):
    cache = tmp_path / "seen.json"
    cache.write_bytes(b"\x00\xff not json at all {{{")
    assert _seen(cache)["status"] == "unseen"
    assert cache.read_bytes() == b"\x00\xff not json at all {{{", "seen never moves or rewrites the cache"


@pytest.mark.parametrize("content", [b"", b"  \n"])
def test_an_empty_cache_is_not_set_aside(tmp_path, content):
    cache = tmp_path / "seen.json"
    cache.write_bytes(content)
    proc = _record(cache)
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["set_aside"] is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json", "seen.json.lock"]


def test_a_bom_cache_is_read(tmp_path):
    cache = tmp_path / "seen.json"
    cache.write_bytes(b"\xef\xbb\xbf" + json.dumps({OTHER: _live()}).encode("utf-8"))
    proc = _record(cache)
    assert json.loads(proc.stdout)["set_aside"] is None
    assert set(json.loads(cache.read_text(encoding="utf-8"))) == {OTHER, FP}


def test_a_second_set_aside_in_the_same_second_counts_up(tmp_path, mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_corrupt_stamp", lambda: "20261114T093012Z")
    cache = tmp_path / "seen.json"
    names = []
    for garbage in (b"{one", b"{two", b"{three"):
        cache.write_bytes(garbage)
        code, result = _main(mod, capsys, "record", "--fp", FP, "--cache", str(cache), "--issue-url", URL,
                             "--action", "created", "--date", DAY)
        assert code == 0
        names.append(Path(result["set_aside"]).name)
    assert names == [
        "seen.json.corrupt-20261114T093012Z",
        "seen.json.corrupt-20261114T093012Z-2",
        "seen.json.corrupt-20261114T093012Z-3",
    ]
    assert (tmp_path / names[0]).read_bytes() == b"{one"
    assert (tmp_path / names[2]).read_bytes() == b"{three"


def test_a_failed_set_aside_exits_one_and_writes_nothing(tmp_path, mod, monkeypatch, capsys):
    real_replace = mod._replace

    def refuse_set_aside(src, dst):
        if ".corrupt-" in str(dst):
            raise PermissionError(13, "Permission denied")
        real_replace(src, dst)

    monkeypatch.setattr(mod, "_replace", refuse_set_aside)
    cache = tmp_path / "seen.json"
    cache.write_bytes(b"{corrupt")
    code, result = _main(mod, capsys, "record", "--fp", FP, "--cache", str(cache), "--issue-url", URL,
                         "--action", "created", "--date", DAY)
    assert code == 1
    assert "nothing was written" in result["error"]
    assert cache.read_bytes() == b"{corrupt"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json", "seen.json.lock"]


# --- record: the lock ---------------------------------------------------------------


def test_eight_parallel_records_all_land(tmp_path):
    cache = tmp_path / "seen.json"
    fps = [f"fp-{i:07x}" for i in range(8)]
    procs = [
        subprocess.Popen(
            [sys.executable, str(SCRIPT), "record", "--fp", fp, "--cache", str(cache), "--issue-url",
             f"{URL}{i}", "--action", "created", "--date", DAY],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_env(), stdin=subprocess.DEVNULL,
        )
        for i, fp in enumerate(fps)
    ]
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, out + err
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert sorted(data) == fps
    assert all(data[fp]["issue_url"] == f"{URL}{i}" for i, fp in enumerate(fps))


HOLDER = """
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("holder", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
fd = mod._acquire(mod.Path(sys.argv[2]), 5)
print("locked", flush=True)
time.sleep(30)
"""


def test_a_lock_held_past_the_wait_exits_one_and_writes_nothing(tmp_path, mod, monkeypatch, capsys):
    cache = _write_cache(tmp_path / "seen.json", {OTHER: _live()})
    before = cache.read_bytes()
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(SCRIPT), str(tmp_path / "seen.json.lock")],
        stdout=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL,
    )
    try:
        assert holder.stdout.readline().strip() == "locked"
        monkeypatch.setattr(mod, "LOCK_WAIT_SEC", 0.5)
        start = time.monotonic()
        code, result = _main(mod, capsys, "record", "--fp", FP, "--cache", str(cache), "--issue-url", URL,
                             "--action", "created", "--date", DAY)
        waited = time.monotonic() - start
    finally:
        holder.kill()
        holder.wait(timeout=30)
    assert code == 1
    assert "nothing was written" in result["error"]
    assert waited >= 0.4, "the call gives up only at the end of its wait"
    assert cache.read_bytes() == before


def test_the_lock_is_released_when_its_holder_dies(tmp_path):
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(SCRIPT), str(tmp_path / "seen.json.lock")],
        stdout=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL,
    )
    assert holder.stdout.readline().strip() == "locked"
    holder.kill()
    holder.wait(timeout=30)
    proc = _record(tmp_path / "seen.json")
    assert proc.returncode == 0, proc.stdout
    assert (tmp_path / "seen.json.lock").exists(), "the lock file is never deleted"


def test_the_lock_wait_is_ten_seconds(mod):
    assert mod.LOCK_WAIT_SEC == 10.0


def test_record_leaves_no_temp_file(tmp_path):
    cache = tmp_path / "seen.json"
    for action in ("created", "reacted"):
        assert _record(cache, action=action).returncode == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json", "seen.json.lock"]


# --- the action vocabulary -----------------------------------------------------


def test_suppressing_actions_is_not_derived_from_actions():
    """`resolved` must be opted OUT of suppression by construction.

    SUPPRESSING_ACTIONS is a literal tuple rather than `ACTIONS` minus
    `resolved`, so a disposition added later defaults to NOT suppressing until
    someone opts it in. Deriving it would silently re-arm suppression for every
    future action, which is the exact defect this disposition exists to fix.
    """
    src = SCRIPT.read_text(encoding="utf-8")

    # A literal tuple, not `tuple(a for a in ACTIONS if ...)` or a set-difference.
    match = re.search(r"^SUPPRESSING_ACTIONS = \(([^)]*)\)", src, re.MULTILINE)
    assert match, "SUPPRESSING_ACTIONS must be a module-level literal tuple"
    suppressing = re.findall(r'"([a-z]+)"', match.group(1))
    assert "resolved" not in suppressing
    # A queued finding is not an issue: it neither suppresses nor is recordable.
    assert "queued" not in suppressing

    actions = re.search(r"^ACTIONS = \(([^)]*)\)", src, re.MULTILINE)
    assert actions, "ACTIONS must be a module-level literal tuple"
    valid = re.findall(r'"([a-z]+)"', actions.group(1))
    assert "resolved" in valid, "resolved must be a recordable action"
    assert "queued" not in valid
    # No drift: every suppressing action is still a valid action.
    assert set(suppressing) < set(valid)


# --- the stage reference that drives the script --------------------------------


def _reference() -> str:
    return HEALTH_CHECK_MD.read_text(encoding="utf-8")


def _flow(text: str) -> str:
    return " ".join(text.split())


def _section(start: str, end: str | None = None) -> str:
    """The reference from `start` to `end`, or to the end of the file when `end` is None."""
    text = _reference()
    assert text.count(start) == 1, start
    i = text.index(start)
    j = len(text) if end is None else text.index(end, i + len(start))
    return text[i:j]


def _fenced_blocks(text: str) -> list[str]:
    return re.findall(r"^```[^\n]*\n(.*?)^```", text, re.MULTILINE | re.DOTALL)


QUEUE = "### 5c. Local queue"


def test_the_script_not_the_prose_reads_the_issue_state():
    """`CLOSED` alone cannot tell a fix from an auto-closed duplicate, and the script owns that check.

    The dedup Action closes duplicates with `state_reason: 'not_planned'`, so `seen` reads stateReason. The stage
    reference only acts on the verdict, so it no longer restates which issue states give which status.
    """
    assert '"state,stateReason"' in SCRIPT.read_text(encoding="utf-8")
    seen = _flow(_section("**1. Check the seen-cache via the script:**", "**Regression treatment**"))
    assert "the script reads that issue's state itself: never run that check yourself" in seen
    for status in ("`handled`, the only verdict that suppresses", "`unseen` or `unrecognized`", "`regression`",
                   "`possible-regression`"):
        assert status in seen, status
    assert "If the call fails or prints no JSON, treat it as `unseen`." in seen


def test_no_instruction_runs_timeout_or_puts_a_cached_url_into_a_shell_command():
    """`timeout` is not on stock macOS, and a recorded URL pasted into a shell is a command the cache wrote."""
    body = _reference()
    assert not re.search(r"\btimeout\b", body), "the issue-state check is the script's, bounded there"
    blocks = _fenced_blocks(body)
    commands = blocks + re.findall(r"`([^`\n]*gh [^`\n]*)`", body)
    assert blocks
    for command in commands:
        assert "record." not in command, command
    for block in blocks:
        assert "gh issue view" not in block, block
    assert not re.search(r"gh issue view \{", body), "the stage never hands gh a placeholder to view"


def test_every_call_passes_the_new_arguments():
    blocks = _fenced_blocks(_reference())
    fingerprint = [b for b in blocks if "health_check_fp.py fingerprint" in b]
    seen = [b for b in blocks if "health_check_fp.py seen" in b]
    # The names go through a file on stdin, so no quote in a heading or a name ever meets the shell.
    assert len(fingerprint) == 1
    assert '--stdin < "<run folder>/hc-name-{n}.json"' in fingerprint[0]
    assert "--section-slug" not in fingerprint[0] and "--defect-key" not in fingerprint[0]
    assert len(seen) == 1 and "--legacy-fp {legacy_fp}" in seen[0]
    body = _reference()
    assert '`{"section_heading": "<the heading>", "defect_name": "<the name>"}`' in body
    for retired in ("--queue-path", "--defect-slug", "--action queued", "defect_slug"):
        assert retired not in body, retired


def test_the_regression_records_and_treatments_are_described():
    body = _flow(_reference())
    assert "add `--regression`" in body
    assert "REGRESSION: {short description}" in body
    assert "Possibly a regression of {record.issue_url}" in body
    assert "`possible-regression`" in body


def test_the_section_and_defect_naming_rule_is_stated():
    body = _flow(_reference())
    assert "**Name the section and the defect.**" in body
    assert "copied exactly as that file writes it, numbering included" in body
    assert "Never use the section's own subject alone" in body
    # The script derives the key, and names a script by its stem.
    assert "one to four lower-case ASCII words joined by hyphens (`gate_eval.py` gives `gate-eval`" in body
    assert "Never use a path, a line number, a severity or words from this run's own story" in body
    # The slug and key rules themselves live in the script, not in the prose.
    assert "split it at spaces" not in body
    # Every finding has a heading the script accepts, and a refused one is retried once, never in a loop.
    assert "A bold run-in label (`**Foo.**`) is no heading: take the heading that encloses it." in body
    assert ("A defect in an instruction of `SKILL.md` or of a script takes the heading of the stage-file section that "
            "was running when it bit, or the file's H1 when none fits.") in body
    assert "when it refuses the heading, take the heading that encloses that one" in body
    assert ("Never loop: when that second call fails too, or a call prints no JSON at all (uv or Python could not "
            "run), log it, naming the finding, and drop that finding.") in body


def test_every_failure_after_drafting_has_a_route():
    body = _flow(_reference())
    assert "write `N/A` when it is `null`, or when the call fails or prints no JSON" in body
    assert ('If adding either opening line to the draft fails, log its error and write the finding to the local '
            'queue (§5c) with the reason "Posting these to GitHub failed."') in body
    # The comment is written at the dedup gate, so it is shown before it is posted.
    assert "show the user its text, and run `gh issue comment" in body
    # A configured path with a space in it stays one argument.
    blocks = _fenced_blocks(_reference())
    assert all('--cache "{workflow.health_check_seen_cache}"' in b for b in blocks if "--cache" in b)
    assert all('--queue-dir "{workflow.health_check_queue_path}"' in b for b in blocks if "--queue-dir" in b)


def test_the_second_search_offers_possible_matches_and_n_rekeys_an_exact_one():
    body = _flow(_reference())
    assert '"{legacy_fp} in:title,body"' in body
    assert "Possible match: #{N}: {title}" in body
    assert "choose a more specific defect name" in body
    # A re-keyed finding gets a new draft and is checked again: the old verdict's treatment never carries over.
    assert "run §3's call again with it and write the draft anew under the new `{fp}`, without a line the old verdict added" in body
    assert "run steps 1 to 3 again for the new fingerprints" in body
    assert "the new `seen` verdict alone decides the regression treatment and `--regression`" in body
    # A failed search is not a search that found nothing.
    assert ('If either search exits non-zero, it has not shown that no issue matches: log its error and send the '
            'finding to the local queue (§5c) with the reason "Posting these to GitHub failed."') in body


def test_the_enabled_gate_comes_first_and_headless_announces_nothing():
    body = _reference()
    assert not body.startswith("---"), "the stage reference carries no frontmatter aliases"
    first = re.search(r"^## [0-9]", body, re.MULTILINE)
    assert first and body[first.start():].startswith("## 1. Enabled gate")
    gate = _flow(_section("## 1. Enabled gate", "## 2."))
    assert gate.index("If `{workflow.health_check_repo}` is empty, the check is off") < gate.index("in an attended run")
    assert "touching nothing else" in gate
    assert "arrival announcement" not in body


def test_one_name_per_setting():
    """The body reads each setting by its {workflow.*} name: no frontmatter alias, none that nothing reads."""
    body = _reference()
    for alias in ("{healthCheckRepo}", "{seenCachePath}", "liveSubmitSeverities", "localFallbackFolder", "autosubmit:"):
        assert alias not in body, alias
    for name in ("{workflow.health_check_repo}", "{workflow.health_check_seen_cache}",
                 "{workflow.health_check_queue_path}", "{workflow.health_check_autosubmit}"):
        assert name in body, name


def test_reflection_reads_the_logged_friction_entries_first():
    find = _flow(_section("## 2. Find the findings", "## 3."))
    # This invocation's entries only, as Finalize's audit scopes its walk, found with the Grep tool.
    assert find.startswith("## 2. Find the findings Read the `friction:` entries this invocation wrote first, the "
                           "scope Finalize's decision-log audit walks")
    assert "Find them with the Grep tool, never a shell grep" in find
    assert "grep -n" not in find
    assert "Report only what a logged entry or the live context shows." in find
    skill_root = Path(__file__).resolve().parents[2]
    skill = _flow((skill_root / "SKILL.md").read_text(encoding="utf-8"))
    assert ('and, without stopping, a one-line `friction: <stage>.md "<section heading, exactly as the file writes it, '
            'numbering included>": <what was unclear, contradictory or missing>` entry whenever an instruction is '
            "unclear, contradictory or silent on the case in hand") in skill
    finalize = _flow((skill_root / "references" / "finalize.md").read_text(encoding="utf-8"))
    assert "A `friction:` entry is left for the health check, which reports it." in finalize


def test_every_finding_is_drafted_before_the_gate_and_routed_unchanged():
    body = _reference()
    assert body.index("## 3. Fingerprint and draft each finding") < body.index("### 4a. Attended routing")
    draft = _flow(_section("## 3. Fingerprint and draft each finding", "## 4."))
    assert "Write each finding's issue body with the Write tool to `hc-body-{fp}.md` in the run folder" in draft
    assert "Every route uses that file as it stands" in draft
    assert ("After the gate the draft changes only by a regression's opening line (§5a step 1) or an **[N]** re-key "
            "at the dedup gate (§5a-i).") in draft
    # A file an earlier invocation left is Read before it is overwritten, and a failed Write drops the finding.
    assert "Read a file of that name an earlier invocation left" in draft
    assert "If either Write fails, log its error, naming the finding, and drop that finding" in draft
    assert "Two findings that get one `{fp}` are one defect: merge them into one finding before drafting." in draft
    # The dedup Action reads `## Fingerprint` and `## Severity`, so the body uses the template's headings.
    assert "`## Fingerprint` with `` `{fp}` `` alone on the line below it" in draft
    assert "`## Severity` (`{severity}`)" in draft
    # The live create and the queue both take that draft as their body file.
    create = [b for b in _fenced_blocks(_section("**5a-ii. If no matching open issue exists**", "### 5b."))
              if "gh issue create" in b]
    assert len(create) == 1 and '--body-file "<run folder>/hc-body-{fp}.md"' in create[0]
    queue = [b for b in _fenced_blocks(_section(QUEUE)) if "health_check_fp.py queue" in b]
    assert len(queue) == 1 and '--body-file "<run folder>/hc-body-{fp}.md"' in queue[0]


def test_the_gate_shows_each_title_and_body_and_y_submits_only_bugs():
    gate = _flow(_section("### 4a. Attended routing", "### 4-headless."))
    assert "For each one show its title" in gate and "the path of its draft and the draft's full text" in gate
    assert "**[Y]** Yes: submit the bug findings; friction and gap findings stay local" in gate
    assert "**[A]** All: submit every finding, friction and gap included" in gate
    assert gate.index("the draft's full text") < gate.index("**HALT and wait for input.**")
    assert "write the draft anew as `hc-body-{fp}.md` under the new `{fp}`" in gate, "[E] edits the drafts"
    assert "a confirmed regression's title gains `REGRESSION: `" in gate
    routing = _flow(_section("## 5. Severity routing", "### 5a."))
    assert ("Each `friction` and `gap` finding, the most subjective kinds and the ones that draw the most "
            "near-duplicates, goes to the local queue (§5c) with the reason "
            '"Friction and gap findings stay local unless you choose [A]."') in routing
    assert "**[A]**: every finding live-submits (§5a)." in routing
    # One prompt, not two: no second friction/gap question after the gate.
    assert "[y/N]" not in _reference()


def test_the_attended_gate_offers_queue_locally():
    gate = _flow(_section("### 4a. Attended routing", "### 4-headless."))
    assert "**[Q]** Queue locally" in gate
    assert "Make no GitHub call" in gate
    assert '"The review gate queued these locally."' in gate


def test_the_never_block_rule_is_stated_once_with_its_reason():
    body = _flow(_reference())
    assert body.count("block or delay") == 1
    headless = _flow(_section("### 4-headless.", "## 5. Severity routing"))
    assert ("Never block or delay the final headless JSON emit: Finalize emits it only after this step returns, and "
            "an automator is waiting on it.") in headless
    assert "## Terminal step" not in _reference()
    skill_root = Path(__file__).resolve().parents[2]
    for path in (skill_root / "SKILL.md", skill_root / "references" / "finalize.md"):
        text = path.read_text(encoding="utf-8")
        for stale in ("queue-only", "queues findings locally"):
            assert stale not in text, (path.name, stale)
    finalize = _flow((skill_root / "references" / "finalize.md").read_text(encoding="utf-8"))
    assert "It routes its own headless mode and **never blocks the emit**." in finalize
    assert "Do not perform any other action between this section and executing the health check." in finalize


def test_an_unattended_match_takes_skip_and_posts_nothing():
    headless = _flow(_section("### 4-headless.", "## 5. Severity routing"))
    assert "takes **[S]**" in headless and "nothing is posted" in headless
    menu = _flow(_section("**5a-i. If a matching open issue exists**", "**5a-ii."))
    assert "**Unattended default: [S].**" in menu
    assert "nothing is posted on a guess" in menu


def test_a_queued_finding_records_nothing():
    queue = _section(QUEUE)
    assert "health_check_fp.py record" not in queue
    assert "**Record nothing in the seen-cache for it**" in queue


def test_the_queue_step_writes_into_the_configured_queue_path():
    """#228's rewrite dropped the folder from the one step that writes queued files (customization-1)."""
    queue = _section(QUEUE)
    assert "{workflow.health_check_queue_path}" in queue
    [block] = [b for b in _fenced_blocks(queue) if "health_check_fp.py queue" in b]
    assert 'queue --queue-dir "{workflow.health_check_queue_path}"' in _flow(block.replace("\\\n", " "))
    assert "--stage {stage}" in block


def test_a_queued_file_is_the_draft_with_no_frontmatter():
    queue = _flow(_section(QUEUE))
    assert "copies the draft unchanged" in queue
    for gone in ("section_fingerprint:", "type: workflow-health-finding", "```yaml"):
        assert gone not in _section(QUEUE), gone


def test_every_local_outcome_shows_its_paths_reason_and_body_file_command():
    queue = _flow(_section(QUEUE))
    assert '"{N} finding(s) saved locally:" then each path, each followed by the two commands that submit it' in queue
    assert '"{reason sentence} Run a finding\'s two commands to submit it as an issue' in queue
    assert ("log the same lines (each path with its `gh label create` and `gh issue create --body-file` commands, "
            "and the reason sentence with its note for a reporter without push access)") in queue
    # The printed commands file an issue the dedup Action and the title search can find: the full title, the
    # health-check and fp-* labels, and the label guard first.
    [block] = [b for b in _fenced_blocks(_section(QUEUE)) if "gh issue create" in b]
    command = _flow(block.replace("\\\n", " "))
    assert command.index('gh label create "{fp}"') < command.index("gh issue create")
    assert "2>/dev/null || true" in command
    assert '--title "[health-check][{severity}][{fp}] {workflow}: {short description}"' in command
    assert '--label "health-check,workflow-improvement,{severity},{fp}"' in command
    assert "--body-file {file-path}" in command
    # A reporter without push access drops the `--label` line, so the body file is on a line of its own.
    assert "\n  --body-file {file-path}\n" in block
    assert not any("--label" in line and "--body-file" in line for line in block.splitlines())
    assert "[title]" not in queue
    # Every reason the routing names is one the §5c table lists.
    body = _reference()
    reasons = set(re.findall(r'with the reason "([^"]+)"', body))
    assert reasons
    for reason in reasons:
        assert f'"{reason}"' in queue, reason


def test_a_failed_create_is_retried_once_without_labels():
    """A reporter without push access can create no label and set none (#227).

    The guard's `|| true` hides the failed `gh label create`, so `gh issue create --label {fp}` fails on the
    missing label and the first report of every defect was only ever queued. The retry files it bare, and the
    dedup Action labels it from its title.
    """
    section = _section("**5a-ii. If no matching open issue exists**", "### 5b. Record the outcome")
    create = _flow(section)
    # The first run still passes --label, so a collaborator's filing is unchanged.
    [block] = [b for b in _fenced_blocks(section) if "gh issue create" in b]
    assert '--label "health-check,workflow-improvement,{severity},{fp}"' in block
    assert ("**If `gh issue create` exits non-zero, run it once more without the `--label` line**, with the same "
            "title and body file.") in create
    assert "cannot create the label (the guard's `|| true` hides that) or set any label" in create
    assert "The dedup Action applies the labels from the title" in create
    # The outcome is recorded and queued as before: created after either run, queued after the second failure.
    assert "After the issue is created, by the first run or the retry, record it (§5b)" in create
    assert "If `gh issue create` fails on its retry too, log its error and record nothing" in create
    record = _flow(_section("### 5b. Record the outcome", QUEUE))
    assert "`created` after `gh issue create` succeeded, on its first run or its retry without `--label`" in record
    queue = _flow(_section(QUEUE))
    assert ("| A search, a regression line's edit, the reaction or the comment failed, or `gh issue create` failed "
            "twice") in queue


def test_the_queue_tells_a_reporter_without_push_access_to_drop_the_guard_and_labels():
    queue = _flow(_section(QUEUE))
    assert ("Without push access to {workflow.health_check_repo}, drop the `gh label create` command and the "
            "`--label` line: you can neither create a label nor set one, and the dedup Action labels the issue from "
            "its title.") in queue


def test_evidence_cites_only_module_files():
    assert "**Cite only this module's files.**" in _reference()


# --- the contributor docs --------------------------------------------------------


def test_contributing_does_not_promise_a_bare_closed_counts_as_fixed():
    """The contributor-facing note must not contradict the stage.

    It is the doc that tells a maintainer how to close a finding out, so if it
    implies any close counts, the stage's narrower rule reads as a bug.
    """
    body = (Path(__file__).resolve().parents[4] / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "not planned" in body.lower(), "CONTRIBUTING must say a not-planned close does not count as a fix"


def test_the_issue_template_gives_the_stdin_fingerprint_command():
    """A manual filer runs the script with the heading and the name in a file, never hashing by hand."""
    template = (Path(__file__).resolve().parents[4] / ".github" / "ISSUE_TEMPLATE" / "workflow-health-check.md")
    lines = template.read_text(encoding="utf-8").splitlines()
    [command] = [line.strip() for line in lines if "health_check_fp.py fingerprint" in line]
    assert re.search(r"health_check_fp\.py fingerprint .*--stdin < names\.json$", command), command
    [names] = [line.strip() for line in lines if line.strip().startswith('{"section_heading"')]
    assert set(json.loads(names)) == {"section_heading", "defect_name"}


# --- version: probe ladder --------------------------------------------------


def _version(project_root: Path, skill_root: Path) -> subprocess.CompletedProcess[str]:
    return _run(
        "version",
        "--project-root",
        str(project_root),
        "--skill-root",
        str(skill_root),
    )


def test_version_nothing_found_is_null_na(tmp_path):
    proj = tmp_path / "proj"
    skill = tmp_path / "skill"
    proj.mkdir()
    skill.mkdir()
    proc = _version(proj, skill)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"version": None, "source": "N/A"}


def test_version_bmad_ucg_version_wins(tmp_path):
    proj = tmp_path / "proj"
    skill = tmp_path / "skill"
    (proj / "_bmad" / "ucg").mkdir(parents=True)
    (proj / "_bmad" / "ucg" / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    proc = _version(proj, skill)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload == {"version": "1.2.3", "source": "_bmad/ucg/VERSION"}


def test_version_skill_root_version_wins_when_bmad_absent(tmp_path):
    proj = tmp_path / "proj"
    skill = tmp_path / "skill"
    proj.mkdir()
    skill.mkdir()
    (skill / "VERSION").write_text("  0.9.0  ", encoding="utf-8")
    proc = _version(proj, skill)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["version"] == "0.9.0"
    assert payload["source"] == f"{skill}/VERSION"


def test_version_marketplace_wins_when_version_files_absent(tmp_path):
    proj = tmp_path / "proj"
    skill = tmp_path / "skill"
    (proj / ".claude-plugin").mkdir(parents=True)
    skill.mkdir()
    (proj / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"plugins": [{"version": "2.0.0"}]}), encoding="utf-8"
    )
    proc = _version(proj, skill)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"version": "2.0.0", "source": "marketplace.json"}


def test_version_package_json_is_last_rung(tmp_path):
    proj = tmp_path / "proj"
    skill = tmp_path / "skill"
    proj.mkdir()
    skill.mkdir()
    (proj / "package.json").write_text(
        json.dumps({"version": "3.1.4"}), encoding="utf-8"
    )
    proc = _version(proj, skill)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"version": "3.1.4", "source": "package.json"}


def test_version_first_hit_wins_precedence(tmp_path):
    """Every rung is populated; the earliest (bmad VERSION) must win."""
    proj = tmp_path / "proj"
    skill = tmp_path / "skill"
    (proj / "_bmad" / "ucg").mkdir(parents=True)
    (proj / ".claude-plugin").mkdir(parents=True)
    skill.mkdir()
    (proj / "_bmad" / "ucg" / "VERSION").write_text("first", encoding="utf-8")
    (skill / "VERSION").write_text("second", encoding="utf-8")
    (proj / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"plugins": [{"version": "third"}]}), encoding="utf-8"
    )
    (proj / "package.json").write_text(
        json.dumps({"version": "fourth"}), encoding="utf-8"
    )
    proc = _version(proj, skill)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"version": "first", "source": "_bmad/ucg/VERSION"}


def test_version_skill_precedes_marketplace_and_package(tmp_path):
    """skill-root VERSION outranks both JSON rungs when bmad VERSION is absent."""
    proj = tmp_path / "proj"
    skill = tmp_path / "skill"
    (proj / ".claude-plugin").mkdir(parents=True)
    skill.mkdir()
    (skill / "VERSION").write_text("skill-wins", encoding="utf-8")
    (proj / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"plugins": [{"version": "mp"}]}), encoding="utf-8"
    )
    (proj / "package.json").write_text(json.dumps({"version": "pkg"}), encoding="utf-8")
    proc = _version(proj, skill)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["version"] == "skill-wins"
    assert payload["source"] == f"{skill}/VERSION"


def test_version_malformed_marketplace_falls_through_to_package(tmp_path):
    proj = tmp_path / "proj"
    skill = tmp_path / "skill"
    (proj / ".claude-plugin").mkdir(parents=True)
    skill.mkdir()
    (proj / ".claude-plugin" / "marketplace.json").write_text(
        "{ this is not valid json {{{", encoding="utf-8"
    )
    (proj / "package.json").write_text(json.dumps({"version": "5.5.5"}), encoding="utf-8")
    proc = _version(proj, skill)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"version": "5.5.5", "source": "package.json"}


def test_version_marketplace_missing_key_falls_through(tmp_path):
    """marketplace.json present but missing plugins[0].version -> next rung."""
    proj = tmp_path / "proj"
    skill = tmp_path / "skill"
    (proj / ".claude-plugin").mkdir(parents=True)
    skill.mkdir()
    (proj / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"plugins": [{"name": "x"}]}), encoding="utf-8"
    )
    (proj / "package.json").write_text(json.dumps({"version": "6.0.0"}), encoding="utf-8")
    proc = _version(proj, skill)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"version": "6.0.0", "source": "package.json"}


def test_version_empty_version_file_falls_through(tmp_path):
    """An empty/whitespace VERSION file is not a hit; later rungs win."""
    proj = tmp_path / "proj"
    skill = tmp_path / "skill"
    (proj / "_bmad" / "ucg").mkdir(parents=True)
    skill.mkdir()
    (proj / "_bmad" / "ucg" / "VERSION").write_text("   \n  ", encoding="utf-8")
    (skill / "VERSION").write_text("7.7.7", encoding="utf-8")
    proc = _version(proj, skill)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["version"] == "7.7.7"
    assert payload["source"] == f"{skill}/VERSION"


def test_version_malformed_package_json_with_nothing_else_is_null(tmp_path):
    proj = tmp_path / "proj"
    skill = tmp_path / "skill"
    proj.mkdir()
    skill.mkdir()
    (proj / "package.json").write_text("not json at all }{", encoding="utf-8")
    proc = _version(proj, skill)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"version": None, "source": "N/A"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
