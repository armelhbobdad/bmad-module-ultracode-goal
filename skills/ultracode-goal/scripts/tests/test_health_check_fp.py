#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for health_check_fp.py.

Covers the fingerprint byte-format (locked against a golden sha1 computed in the
test), the fp regex contract, severity/stage/slug validation, and the seen/record
seen-cache round-trip including corrupt-cache resilience and merge/overwrite
semantics. The script is exercised via subprocess (sys.executable + absolute
path) to test the real CLI surface, mirroring test_preflight_check.py.

Run: uv run --with pytest pytest test_health_check_fp.py -v
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "health_check_fp.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def _fingerprint(severity: str, stage: str, slug: str) -> subprocess.CompletedProcess[str]:
    return _run(
        "fingerprint",
        "--severity",
        severity,
        "--stage",
        stage,
        "--section-slug",
        slug,
    )


def _expected_fp(severity: str, stage: str, slug: str) -> tuple[str, str]:
    """Recompute the fingerprint independently to lock the byte format."""
    step_file = f"skills/ultracode-goal/references/{stage}.md"
    tuple_str = f"{severity}|ultracode-goal/{stage}|{step_file}|{slug}"
    digest = hashlib.sha1(tuple_str.encode("utf-8")).hexdigest()[:7]
    return f"fp-{digest}", tuple_str


# --- Fingerprint: golden byte-format lock ----------------------------------


def test_fingerprint_matches_independent_golden():
    proc = _fingerprint("bug", "preflight", "missing-staging-path")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)

    expected_fp, expected_tuple = _expected_fp("bug", "preflight", "missing-staging-path")
    assert payload["fp"] == expected_fp
    assert payload["tuple"] == expected_tuple
    # The exact tuple the script hashes — install-mode-invariant step_file form.
    assert payload["tuple"] == (
        "bug|ultracode-goal/preflight|"
        "skills/ultracode-goal/references/preflight.md|missing-staging-path"
    )


def test_fingerprint_matches_fp_regex():
    import re

    proc = _fingerprint("friction", "execute", "ambiguous-budget")
    assert proc.returncode == 0, proc.stderr
    fp = json.loads(proc.stdout)["fp"]
    assert re.match(r"^fp-[0-9a-f]{7}$", fp)


# --- Fingerprint: determinism + sensitivity --------------------------------


def test_fingerprint_is_deterministic_for_identical_inputs():
    first = json.loads(_fingerprint("gap", "gate", "verdict-mapping").stdout)["fp"]
    second = json.loads(_fingerprint("gap", "gate", "verdict-mapping").stdout)["fp"]
    assert first == second


def test_changing_severity_changes_fp():
    a = json.loads(_fingerprint("bug", "gate", "verdict-mapping").stdout)["fp"]
    b = json.loads(_fingerprint("friction", "gate", "verdict-mapping").stdout)["fp"]
    assert a != b


def test_changing_stage_changes_fp():
    a = json.loads(_fingerprint("bug", "gate", "verdict-mapping").stdout)["fp"]
    b = json.loads(_fingerprint("bug", "finalize", "verdict-mapping").stdout)["fp"]
    assert a != b


def test_changing_section_slug_changes_fp():
    a = json.loads(_fingerprint("bug", "gate", "verdict-mapping").stdout)["fp"]
    b = json.loads(_fingerprint("bug", "gate", "reloop-budget").stdout)["fp"]
    assert a != b


# --- Fingerprint: validation -----------------------------------------------


def test_invalid_stage_exits_one_with_json_error():
    proc = _fingerprint("bug", "not-a-stage", "some-slug")
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert "error" in payload


def test_invalid_severity_exits_one():
    proc = _fingerprint("critical", "preflight", "some-slug")
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


def test_invalid_slug_uppercase_exits_one():
    proc = _fingerprint("bug", "preflight", "Some-Slug")
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


def test_invalid_slug_underscore_exits_one():
    proc = _fingerprint("bug", "preflight", "some_slug")
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


# --- seen: missing cache ----------------------------------------------------


def test_seen_missing_cache_is_unseen(tmp_path):
    cache = tmp_path / "nope.json"
    proc = _run("seen", "--fp", "fp-abc1234", "--cache", str(cache))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["seen"] is False
    assert payload["record"] is None


def test_seen_invalid_fp_exits_one(tmp_path):
    cache = tmp_path / "c.json"
    proc = _run("seen", "--fp", "fp-XYZ", "--cache", str(cache))
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


# --- record -> seen round-trip ---------------------------------------------


def test_record_then_seen_round_trip(tmp_path):
    cache = tmp_path / "seen.json"
    fp = "fp-abc1234"
    rec = _run(
        "record",
        "--fp",
        fp,
        "--cache",
        str(cache),
        "--issue-url",
        "https://github.com/o/r/issues/1",
        "--action",
        "created",
        "--date",
        "2026-06-04",
    )
    assert rec.returncode == 0, rec.stderr
    assert json.loads(rec.stdout) == {"written": True, "fp": fp}

    seen = _run("seen", "--fp", fp, "--cache", str(cache))
    payload = json.loads(seen.stdout)
    assert payload["seen"] is True
    assert payload["record"] == {
        "issue_url": "https://github.com/o/r/issues/1",
        "action": "created",
        "date": "2026-06-04",
    }


def test_record_creates_nested_parent_dirs(tmp_path):
    cache = tmp_path / "deep" / "nested" / "tree" / "seen.json"
    rec = _run(
        "record",
        "--fp",
        "fp-0000000",
        "--cache",
        str(cache),
        "--issue-url",
        "https://example/1",
        "--action",
        "queued",
        "--date",
        "2026-06-04",
    )
    assert rec.returncode == 0, rec.stderr
    assert cache.is_file()


def test_record_merges_distinct_fps(tmp_path):
    cache = tmp_path / "seen.json"
    _run("record", "--fp", "fp-aaaaaaa", "--cache", str(cache),
         "--issue-url", "https://example/a", "--action", "created", "--date", "2026-06-04")
    _run("record", "--fp", "fp-bbbbbbb", "--cache", str(cache),
         "--issue-url", "https://example/b", "--action", "queued", "--date", "2026-06-04")

    data = json.loads(cache.read_text(encoding="utf-8"))
    assert "fp-aaaaaaa" in data
    assert "fp-bbbbbbb" in data
    assert data["fp-aaaaaaa"]["action"] == "created"
    assert data["fp-bbbbbbb"]["action"] == "queued"


def test_record_overwrites_same_fp_in_place(tmp_path):
    cache = tmp_path / "seen.json"
    fp = "fp-1234567"
    _run("record", "--fp", fp, "--cache", str(cache),
         "--issue-url", "https://example/1", "--action", "queued", "--date", "2026-06-04")
    _run("record", "--fp", fp, "--cache", str(cache),
         "--issue-url", "https://example/1", "--action", "created", "--date", "2026-06-05")

    data = json.loads(cache.read_text(encoding="utf-8"))
    assert list(data.keys()) == [fp]
    assert data[fp]["action"] == "created"
    assert data[fp]["date"] == "2026-06-05"


def test_record_invalid_action_exits_one(tmp_path):
    cache = tmp_path / "seen.json"
    proc = _run("record", "--fp", "fp-abc1234", "--cache", str(cache),
                "--issue-url", "https://example/1", "--action", "upvoted", "--date", "2026-06-04")
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


# --- the resolved disposition: seen is a verdict, not cache presence -------


def _seen_after(tmp_path, action, issue_url="https://github.com/o/r/issues/1"):
    """Record one fp with `action`, then read the seen verdict back."""
    cache = tmp_path / "seen.json"
    fp = "fp-abc1234"
    rec = _run("record", "--fp", fp, "--cache", str(cache),
               "--issue-url", issue_url, "--action", action, "--date", "2026-07-19")
    assert rec.returncode == 0, rec.stderr
    proc = _run("seen", "--fp", fp, "--cache", str(cache))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_record_accepts_resolved(tmp_path):
    cache = tmp_path / "seen.json"
    proc = _run("record", "--fp", "fp-abc1234", "--cache", str(cache),
                "--issue-url", "", "--action", "resolved", "--date", "2026-07-19")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["written"] is True


def test_seen_resolved_does_not_suppress(tmp_path):
    # The fail-open this closes: a fixed finding used to keep suppressing
    # forever, so a REGRESSION of the same defect was silently swallowed.
    payload = _seen_after(tmp_path, "resolved")

    assert payload["seen"] is False, "a resolved fingerprint must not suppress"
    assert payload["status"] == "regression"
    # The record RIDES ALONG so the caller can link the original rather than
    # file the recurrence as a first sighting. Returning None here would restore
    # the signal but throw away the history, which is the point of `resolved`.
    assert payload["record"] is not None
    assert payload["record"]["action"] == "resolved"
    assert payload["record"]["date"] == "2026-07-19"


@pytest.mark.parametrize("action", ["created", "reacted", "commented", "queued"])
def test_seen_suppressing_actions_still_suppress(tmp_path, action):
    # Anti-vacuous twin for the test above: the identical flow, differing only
    # in the action. Without it, `seen: false` unconditionally would pass the
    # resolved test while re-reporting every finding on every run.
    payload = _seen_after(tmp_path, action)

    assert payload["seen"] is True, "%s must still suppress" % action
    assert payload["status"] == "handled"
    assert payload["record"]["action"] == action


def test_seen_unrecognized_action_does_not_suppress(tmp_path):
    # Written by a hand-edit or a newer module. It cannot be confirmed handled,
    # so it reports: a duplicate is closed by the dedup Action, a silenced
    # regression is caught by nothing.
    cache = tmp_path / "seen.json"
    cache.write_text(
        json.dumps({"fp-abc1234": {"action": "teleported", "date": "2026-07-19",
                                   "issue_url": ""}}),
        encoding="utf-8",
    )
    proc = _run("seen", "--fp", "fp-abc1234", "--cache", str(cache))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)

    assert payload["seen"] is False
    assert payload["status"] == "unrecognized"
    assert payload["record"]["action"] == "teleported"


def test_seen_unseen_carries_status(tmp_path):
    proc = _run("seen", "--fp", "fp-abc1234", "--cache", str(tmp_path / "nope.json"))
    payload = json.loads(proc.stdout)
    assert payload == {"seen": False, "status": "unseen", "record": None, "prior": None}


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

    actions = re.search(r"^ACTIONS = \(([^)]*)\)", src, re.MULTILINE)
    assert actions, "ACTIONS must be a module-level literal tuple"
    valid = re.findall(r'"([a-z]+)"', actions.group(1))
    assert "resolved" in valid, "resolved must be a recordable action"
    # No drift: every suppressing action is still a valid action.
    assert set(suppressing) < set(valid)


# --- the stage's issue-state refinement -------------------------------------

_HEALTH_CHECK_MD = (
    Path(__file__).resolve().parents[2] / "references" / "health-check.md"
)


def test_issue_state_check_reads_state_reason_not_state_alone():
    """`CLOSED` alone cannot tell a fix from an auto-closed duplicate.

    The dedup Action closes duplicates with `state_reason: 'not_planned'`, so a
    reporter who lost a race holds a record pointing at a CLOSED issue for a
    defect nobody fixed. Keying on `state` alone flips that to `regression` and
    files a REGRESSION issue against a live defect every session, forever.
    """
    body = _HEALTH_CHECK_MD.read_text(encoding="utf-8")

    assert "--json state,stateReason" in body, (
        "the issue-state check must read stateReason, not state alone"
    )
    assert "CLOSED/COMPLETED" in body, "only a completed close counts as a fix"
    assert "CLOSED/NOT_PLANNED" in body, (
        "the stage must say an auto-closed duplicate is NOT a fix"
    )
    # A PR link is what CONTRIBUTING invites when recording `resolved`, and
    # `gh issue view` reports MERGED for one, never CLOSED.
    assert "MERGED" in body, "a merged PR link must also trigger the regression path"
    # Terminal step of finalize: an unbounded call can stall the run's last stage.
    assert "timeout 10 gh issue view" in body, "the issue lookup must be bounded"


def test_contributing_does_not_promise_a_bare_closed_counts_as_fixed():
    """The contributor-facing note must not contradict the stage.

    It is the doc that tells a maintainer how to close a finding out, so if it
    implies any close counts, the stage's narrower rule reads as a bug.
    """
    body = (Path(__file__).resolve().parents[4] / "CONTRIBUTING.md").read_text(
        encoding="utf-8"
    )
    assert "not planned" in body.lower(), (
        "CONTRIBUTING must say a not-planned close does not count as a fix"
    )


# --- corrupt cache resilience ----------------------------------------------


def test_corrupt_cache_seen_is_unseen(tmp_path):
    cache = tmp_path / "seen.json"
    cache.write_bytes(b"\x00\xff not json at all {{{")
    proc = _run("seen", "--fp", "fp-abc1234", "--cache", str(cache))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["seen"] is False
    assert payload["record"] is None


def test_corrupt_cache_record_succeeds_and_recovers(tmp_path):
    cache = tmp_path / "seen.json"
    cache.write_bytes(b"\x00\xff garbage not json {{{")
    fp = "fp-abc1234"
    rec = _run("record", "--fp", fp, "--cache", str(cache),
               "--issue-url", "https://example/1", "--action", "created", "--date", "2026-06-04")
    assert rec.returncode == 0, rec.stderr
    assert json.loads(rec.stdout) == {"written": True, "fp": fp}
    # The corrupt content was treated as empty; the file is now valid JSON.
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert data[fp]["action"] == "created"


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


# --- seen --queue-path: the prior filing, inline -----------------------------
# The handled branch's mandated same-defect comparison used to start with a
# manual retrieval (grep the queue for the fp). `--queue-path` returns the
# recorded filing inline; informational only - it never changes the status.


def _filing(directory, name, fp, *, slug=None, title="The prior finding"):
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "type: workflow-health-finding",
        f"fingerprint: {fp}",
    ]
    if slug:
        lines.append(f"defect_slug: {slug}")
    lines += ["date: 2026-08-01", "---", "", f"# {title}", "", "Body."]
    (directory / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_seen_queue_path_returns_the_prior_filing(tmp_path):
    fp = "fp-1234abc"
    cache = tmp_path / "cache.json"
    _run("record", "--fp", fp, "--cache", str(cache), "--issue-url", "", "--action", "queued", "--date", "2026-08-01")
    queue = tmp_path / "queue"
    _filing(queue, "hc-x-20260801-000000.md", fp, slug="the-real-defect")
    proc = _run("seen", "--fp", fp, "--cache", str(cache), "--queue-path", str(queue))
    out = json.loads(proc.stdout)
    assert out["status"] == "handled"
    assert out["prior"]["title"] == "The prior finding"
    assert out["prior"]["defect_slug"] == "the-real-defect"
    assert out["prior"]["path"].endswith("hc-x-20260801-000000.md")


def test_seen_queue_path_searches_the_resolved_subfolder(tmp_path):
    fp = "fp-1234abc"
    cache = tmp_path / "cache.json"
    _run("record", "--fp", fp, "--cache", str(cache), "--issue-url", "", "--action", "resolved", "--date", "2026-08-01")
    queue = tmp_path / "queue"
    _filing(queue / "resolved", "old-filing.md", fp, title="Resolved prior")
    proc = _run("seen", "--fp", fp, "--cache", str(cache), "--queue-path", str(queue))
    out = json.loads(proc.stdout)
    assert out["status"] == "regression", "prior lookup must not change the status"
    assert out["prior"]["title"] == "Resolved prior"


def test_seen_prior_is_null_when_nothing_matches_and_status_is_unchanged(tmp_path):
    fp = "fp-1234abc"
    cache = tmp_path / "cache.json"
    _run("record", "--fp", fp, "--cache", str(cache), "--issue-url", "", "--action", "queued", "--date", "2026-08-01")
    queue = tmp_path / "queue"
    _filing(queue, "other.md", "fp-9999999")
    proc = _run("seen", "--fp", fp, "--cache", str(cache), "--queue-path", str(queue))
    out = json.loads(proc.stdout)
    assert out["status"] == "handled"
    assert out["prior"] is None


def test_seen_prior_never_matches_a_body_mention(tmp_path):
    """A filing that merely DISCUSSES the fp in its body is not the prior."""
    fp = "fp-1234abc"
    cache = tmp_path / "cache.json"
    _run("record", "--fp", fp, "--cache", str(cache), "--issue-url", "", "--action", "queued", "--date", "2026-08-01")
    queue = tmp_path / "queue"
    queue.mkdir()
    (queue / "discussion.md").write_text(
        "---\nfingerprint: fp-7777777\n---\n\n# Other\n\nSee also fp-1234abc elsewhere.\n",
        encoding="utf-8",
    )
    proc = _run("seen", "--fp", fp, "--cache", str(cache), "--queue-path", str(queue))
    out = json.loads(proc.stdout)
    assert out["prior"] is None


def test_seen_without_queue_path_keeps_the_old_shape_plus_null_prior(tmp_path):
    fp = "fp-1234abc"
    cache = tmp_path / "cache.json"
    _run("record", "--fp", fp, "--cache", str(cache), "--issue-url", "", "--action", "queued", "--date", "2026-08-01")
    proc = _run("seen", "--fp", fp, "--cache", str(cache))
    out = json.loads(proc.stdout)
    assert out["prior"] is None
    assert set(out.keys()) == {"seen", "status", "record", "prior"}


# --- record --defect-slug ----------------------------------------------------


def test_record_defect_slug_round_trips(tmp_path):
    fp = "fp-1234abc"
    cache = tmp_path / "cache.json"
    _run(
        "record", "--fp", fp, "--cache", str(cache), "--issue-url", "",
        "--action", "queued", "--date", "2026-08-01", "--defect-slug", "wrong-event-guard",
    )
    proc = _run("seen", "--fp", fp, "--cache", str(cache))
    out = json.loads(proc.stdout)
    assert out["record"]["defect_slug"] == "wrong-event-guard"
    assert out["status"] == "handled", "the slug is informational, never a key"


def test_record_without_slug_keeps_the_legacy_record_shape(tmp_path):
    fp = "fp-1234abc"
    cache = tmp_path / "cache.json"
    _run("record", "--fp", fp, "--cache", str(cache), "--issue-url", "", "--action", "queued", "--date", "2026-08-01")
    proc = _run("seen", "--fp", fp, "--cache", str(cache))
    out = json.loads(proc.stdout)
    assert set(out["record"].keys()) == {"issue_url", "action", "date"}


def test_record_rejects_a_malformed_slug(tmp_path):
    proc = _run(
        "record", "--fp", "fp-1234abc", "--cache", str(tmp_path / "c.json"),
        "--issue-url", "", "--action", "queued", "--date", "2026-08-01",
        "--defect-slug", "Not_A_Slug",
    )
    assert proc.returncode == 1
    assert "defect-slug" in proc.stdout or "defect-slug" in proc.stderr


def test_resolve_without_slug_preserves_the_recorded_slug(tmp_path):
    """The documented resolve recipe re-records the fp without --defect-slug;
    a plain replace erased the slug at the exact moment the regression-naming
    feature needed it (the resolve that precedes the regression)."""
    fp = "fp-1234abc"
    cache = tmp_path / "cache.json"
    _run(
        "record", "--fp", fp, "--cache", str(cache), "--issue-url", "",
        "--action", "queued", "--date", "2026-08-01", "--defect-slug", "wrong-event-guard",
    )
    _run("record", "--fp", fp, "--cache", str(cache), "--issue-url", "", "--action", "resolved", "--date", "2026-08-04")
    proc = _run("seen", "--fp", fp, "--cache", str(cache))
    out = json.loads(proc.stdout)
    assert out["status"] == "regression"
    assert out["record"]["defect_slug"] == "wrong-event-guard"


def test_a_new_slug_replaces_the_recorded_one(tmp_path):
    fp = "fp-1234abc"
    cache = tmp_path / "cache.json"
    _run(
        "record", "--fp", fp, "--cache", str(cache), "--issue-url", "",
        "--action", "queued", "--date", "2026-08-01", "--defect-slug", "first-defect",
    )
    _run(
        "record", "--fp", fp, "--cache", str(cache), "--issue-url", "",
        "--action", "queued", "--date", "2026-08-02", "--defect-slug", "second-defect",
    )
    proc = _run("seen", "--fp", fp, "--cache", str(cache))
    assert json.loads(proc.stdout)["record"]["defect_slug"] == "second-defect"
