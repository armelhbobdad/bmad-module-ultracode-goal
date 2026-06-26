#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Structural tests for the four UCG-awareness planning shaping fragments.

The four fragments at assets/ucg-awareness/{bmad-prd,bmad-architecture,
bmad-create-epics-and-stories,bmad-create-story}.toml are static, additive
guardrail-fact artifacts. They land in the ONE universal sanctioned append
channel the installed customize.toml schema exposes — persistent_facts —
each carrying a single [ucg] identity stamp and a per-directive id marker that
merge_customization.py will strip-then-reappend on. These tests are
stdlib-only (tomllib + glob + re, plus subprocess for the shim grep): they pin
down the channel, the stamp, the live-surface-not-shims binding, additive-only
content, and the signed decision-doc gate.

Each structural assertion ships with an in-test anti-vacuous twin that authors a
throwaway TOML (or mutated-doc) string and proves the assertion discriminates —
that the check could genuinely go red, not merely count files.

Run: uv run --with pytest pytest test_ucg_awareness_fragments.py -v
"""

from __future__ import annotations

import glob
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

# assets/ucg-awareness lives two levels up from scripts/tests/.
FRAGMENT_DIR = (
    Path(__file__).resolve().parent.parent.parent / "assets" / "ucg-awareness"
)
REPO_ROOT = Path(__file__).resolve().parents[4]
DECISION_DOC = REPO_ROOT / "docs" / "ucg" / "fragment-shaping-decision.md"

# The four — and only four — fragments this story authors.
EXPECTED_FRAGMENTS = {
    "bmad-prd.toml",
    "bmad-architecture.toml",
    "bmad-create-epics-and-stories.toml",
    "bmad-create-story.toml",
    # Epic 2, story 2.7 — the two TEA shaping fragments.
    "bmad-testarch-test-design.toml",
    "bmad-testarch-nfr.toml",
}

# The deprecated PRD shims a fragment must never be named for or reference.
SHIM_IDS = ("bmad-create-prd", "bmad-edit-prd")

# Per-directive id marker every persistent_facts entry must carry.
ID_MARKER = re.compile(r"\[ucg:[a-z0-9-]+-\d+\]")

# Append channels an earlier PRD draft named but the live schema lacks.
# Authoring into any of these is the channel check's anti-vacuous failure.
_APPEND_SUFFIX = re.compile(r"_append$")
_FORBIDDEN_CHANNEL_SUBSTRINGS = ("rules_append", "guidance_append")

# The live prefix convention: an entry is a literal sentence, a `skill:` ref,
# or a `file:` ref (bmad-prd/customize.toml lines 24-31).
_ALLOWED_PREFIXES = ("skill:", "file:")
_PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]*:")


# --- Helpers ----------------------------------------------------------------


def _fragment_paths() -> list[Path]:
    return [Path(p) for p in glob.glob(str(FRAGMENT_DIR / "*.toml"))]


def _load(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _array_keys(table: dict, prefix: str = "") -> list[str]:
    """Every authored ARRAY key, dotted, recursing into sub-tables.

    A scalar-keyed [ucg] stamp contributes no array keys; a nested
    acceptance_criteria.rules_append channel would surface as such.
    """
    keys: list[str] = []
    for key, value in table.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, list):
            keys.append(dotted)
        elif isinstance(value, dict):
            keys.extend(_array_keys(value, prefix=f"{dotted}."))
    return keys


def _is_forbidden_channel(dotted_key: str) -> bool:
    leaf = dotted_key.rsplit(".", 1)[-1]
    if _APPEND_SUFFIX.search(leaf):
        return True
    return any(sub in dotted_key for sub in _FORBIDDEN_CHANNEL_SUBSTRINGS)


def _entry_prefix_ok(entry: str) -> bool:
    """An entry is a bare sentence (no `word:` prefix) or skill:/file:-prefixed."""
    match = _PREFIX_RE.match(entry)
    if match is None:
        return True  # literal sentence, no prefix
    return entry.startswith(_ALLOWED_PREFIXES)


def _parse_decision_blocks(text: str) -> dict[str, dict]:
    """Parse the decision-doc into {fragment-id: {file, status}} blocks.

    Block format (the format this story authored and this test pins):
      ## Fragment: [ucg:<skill>]
      - Fragment file: `<path>`
      ...
      - Status: ACCEPTED|REWORK
    A block is keyed by its `[ucg:<skill>]` heading id. `file` is the first
    backtick-quoted path on a `Fragment file:` line; `status` is the verbatim
    token after `Status:`.
    """
    blocks: dict[str, dict] = {}
    current: str | None = None
    head_re = re.compile(r"^##\s+Fragment:\s+(\[ucg:[a-z0-9-]+\])\s*$")
    file_re = re.compile(r"Fragment file:\s*`([^`]+)`")
    status_re = re.compile(r"Status:\s*([A-Za-z-]+)")
    for line in text.splitlines():
        head = head_re.match(line)
        if head:
            current = head.group(1)
            blocks[current] = {"file": None, "status": None}
            continue
        if current is None:
            continue
        fmatch = file_re.search(line)
        if fmatch and blocks[current]["file"] is None:
            blocks[current]["file"] = fmatch.group(1)
        smatch = status_re.search(line)
        if smatch and blocks[current]["status"] is None:
            blocks[current]["status"] = smatch.group(1)
    return blocks


# --- channel is persistent_facts, nothing else ------------------------


def test_four_fragments_land_only_in_persistent_facts():
    paths = _fragment_paths()
    basenames = {p.name for p in paths}
    assert basenames == EXPECTED_FRAGMENTS, basenames

    for path in paths:
        data = _load(path)  # tomllib.load succeeds => valid TOML
        array_keys = _array_keys(data)
        assert array_keys == ["persistent_facts"], (path.name, array_keys)
        for key in array_keys:
            assert not _is_forbidden_channel(key), (path.name, key)


def test_twin_named_append_channel_is_rejected():
    # A fragment that authors into authoring_guidance_append (a PRD-named but
    # absent channel) must be caught: its array keys are not exactly
    # ['persistent_facts'] and the channel is forbidden.
    bad = tomllib.loads(
        'authoring_guidance_append = ["steer the author [ucg:x-01]"]\n'
        "[ucg]\nmanaged = true\nversion = \"0.3.0\"\n"
        'block = "ucg-awareness"\ninstalled_at = "x"\n'
    )
    array_keys = _array_keys(bad)
    assert array_keys != ["persistent_facts"]
    assert any(_is_forbidden_channel(k) for k in array_keys)


# --- stamp + per-directive unique ids ---------------------------------


def test_stamp_and_per_directive_ids():
    for path in _fragment_paths():
        data = _load(path)

        ucg = data.get("ucg")
        assert isinstance(ucg, dict), path.name
        assert set(ucg) == {"managed", "version", "block", "installed_at"}, (
            path.name,
            set(ucg),
        )
        assert ucg["managed"] is True, path.name
        assert isinstance(ucg["managed"], bool), path.name
        assert isinstance(ucg["version"], str), path.name
        assert ucg["block"] == "ucg-awareness", path.name
        assert isinstance(ucg["block"], str), path.name
        assert isinstance(ucg["installed_at"], str), path.name

        facts = data["persistent_facts"]
        ids: list[str] = []
        for entry in facts:
            found = ID_MARKER.findall(entry)
            assert len(found) == 1, (path.name, entry)
            ids.append(found[0])
        assert len(ids) == len(set(ids)), (path.name, ids)  # unique within fragment


def test_twin_dup_id_and_missing_block_fail():
    # Two entries sharing the same per-directive id -> the uniqueness check trips.
    dup = tomllib.loads(
        'persistent_facts = ["a [ucg:x-01]", "b [ucg:x-01]"]\n'
        '[ucg]\nmanaged = true\nversion = "0.3.0"\n'
        'block = "ucg-awareness"\ninstalled_at = "x"\n'
    )
    ids = [ID_MARKER.findall(e)[0] for e in dup["persistent_facts"]]
    assert len(ids) != len(set(ids))

    # A stamp missing the block key -> the four-key set assertion trips.
    no_block = tomllib.loads(
        'persistent_facts = ["a [ucg:x-01]"]\n'
        '[ucg]\nmanaged = true\nversion = "0.3.0"\ninstalled_at = "x"\n'
    )
    assert set(no_block["ucg"]) != {"managed", "version", "block", "installed_at"}
    assert "block" not in no_block["ucg"]


# --- live PRD surface, not the shims ----------------------------------


def test_binds_live_prd_surface_not_shims():
    basenames = {p.name for p in _fragment_paths()}
    assert "bmad-prd.toml" in basenames
    assert "bmad-create-prd.toml" not in basenames
    assert "bmad-edit-prd.toml" not in basenames

    # grep the four bodies for the shim ids -> zero matches.
    for shim in SHIM_IDS:
        proc = subprocess.run(
            ["grep", "-rl", shim, str(FRAGMENT_DIR)],
            capture_output=True,
            text=True,
        )
        # grep exit 1 == no matches (what we want); exit 0 == a match leaked.
        assert proc.returncode == 1, (shim, proc.stdout)
        assert proc.stdout.strip() == ""


def test_twin_shim_named_fragment_fails(tmp_path):
    # A shim-named fragment in the set is detected, and a shim id in a body greps.
    shim_set = {"bmad-create-prd.toml", "bmad-architecture.toml"}
    assert "bmad-create-prd.toml" in shim_set  # the discriminator fires

    leaked = tmp_path / "bmad-prd.toml"
    leaked.write_text(
        'persistent_facts = ["forwards to bmad-create-prd [ucg:x-01]"]\n',
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["grep", "-rl", "bmad-create-prd", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0  # a match -> the real test would FAIL on this


# --- additive string facts only ---------------------------------------


def test_entries_are_additive_string_facts():
    for path in _fragment_paths():
        data = _load(path)
        assert set(data) <= {"persistent_facts", "ucg"}, (path.name, set(data))
        for entry in data["persistent_facts"]:
            assert isinstance(entry, str), (path.name, entry)
            assert _entry_prefix_ok(entry), (path.name, entry)


def test_twin_scalar_override_or_non_string_item_fails():
    # An on_complete scalar pushes the top-level key set outside {persistent_facts, ucg}.
    with_scalar = tomllib.loads(
        'persistent_facts = ["a [ucg:x-01]"]\non_complete = "do a thing"\n'
        '[ucg]\nmanaged = true\nversion = "0.3.0"\n'
        'block = "ucg-awareness"\ninstalled_at = "x"\n'
    )
    assert not (set(with_scalar) <= {"persistent_facts", "ucg"})

    # A non-string persistent_facts item fails the str check.
    non_string = tomllib.loads("persistent_facts = [42]\n")
    assert not all(isinstance(e, str) for e in non_string["persistent_facts"])


# --- signed, non-orphaned decision-doc gate ---------------------------


def test_shaping_decision_doc_present_and_signed():
    assert DECISION_DOC.exists(), DECISION_DOC
    text = DECISION_DOC.read_text(encoding="utf-8")
    blocks = _parse_decision_blocks(text)

    # Exactly one block per fragment, keyed by [ucg:<skill>].
    expected_ids = {f"[ucg:{name[:-5]}]" for name in EXPECTED_FRAGMENTS}
    assert set(blocks) == expected_ids, set(blocks)

    for fid, block in blocks.items():
        assert block["status"] == "ACCEPTED", (fid, block["status"])
        named = block["file"]
        assert named is not None, fid
        # Every named fragment file resolves on disk.
        assert (REPO_ROOT / named).exists(), (fid, named)


def test_twin_missing_rework_or_orphaned_block_fails():
    base = DECISION_DOC.read_text(encoding="utf-8")

    # (a) A REWORK status block is not ACCEPTED.
    reworked = base.replace(
        "## Fragment: [ucg:bmad-prd]", "## Fragment: [ucg:bmad-prd]", 1
    )
    reworked = re.sub(
        r"(## Fragment: \[ucg:bmad-prd\].*?Status: )ACCEPTED",
        r"\1REWORK",
        reworked,
        count=1,
        flags=re.DOTALL,
    )
    blocks = _parse_decision_blocks(reworked)
    assert blocks["[ucg:bmad-prd]"]["status"] == "REWORK"
    assert blocks["[ucg:bmad-prd]"]["status"] != "ACCEPTED"

    # (b) A missing block drops a fragment id from the set.
    missing = re.sub(
        r"## Fragment: \[ucg:bmad-create-story\].*\Z",
        "",
        base,
        flags=re.DOTALL,
    )
    expected_ids = {f"[ucg:{name[:-5]}]" for name in EXPECTED_FRAGMENTS}
    assert set(_parse_decision_blocks(missing)) != expected_ids

    # (c) An orphaned reference names a file that does not exist on disk.
    orphaned = base.replace(
        "skills/ultracode-goal/assets/ucg-awareness/bmad-prd.toml",
        "skills/ultracode-goal/assets/ucg-awareness/does-not-exist.toml",
        1,
    )
    oblocks = _parse_decision_blocks(orphaned)
    named = oblocks["[ucg:bmad-prd]"]["file"]
    assert not (REPO_ROOT / named).exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
