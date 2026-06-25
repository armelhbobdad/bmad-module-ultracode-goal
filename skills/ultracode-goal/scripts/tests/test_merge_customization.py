#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest", "tomli-w"]
# ///
"""Tests for merge_customization.py (story 1.5).

Run: uv run --with pytest --with tomli-w pytest scripts/tests/test_merge_customization.py -v

Covers the seven story-1.5 ACs, each with its anti-vacuous twin:
  AC1 test_merge_appends_stamped_facts
  AC2 test_idempotent_reinstall
  AC3 test_absent_channel_is_failloud_skip
  AC4 test_handedit_conflict_reported_not_clobbered
  AC5 test_guarded_import_and_no_reimplement
  AC6 test_remove_strips_only_ucg_rows
  AC7 test_exit_code_lane_and_pep723

Each test builds its fixtures programmatically in tmp_path. The target lives
under a synthetic ``_bmad/custom/`` tree with the real
``_bmad/scripts/resolve_customization.py`` copied alongside, so the tool's
guarded ``deep_merge`` import resolves exactly as it will at install time.

Byte-identity note (AC2, AC6): tomli-w round-trips reorder/reformat unrelated
tables, so every byte-identity assertion compares against a snapshot produced
THROUGH tomli-w (write the baseline once via the serializer before
snapshotting). This makes the assertions test merge_customization's strip, not
tomli-w formatting drift.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "merge_customization.py"
# The real engine the tool imports deep_merge from, at _bmad/scripts/.
REAL_ENGINE = Path(__file__).resolve().parents[4] / "_bmad" / "scripts" / "resolve_customization.py"


# tomli-w is the writer dep the TOOL declares in its PEP-723 block. The shared
# `npm run test:python` runner only provisions pytest (every sibling test is
# stdlib-only), so we must NOT import tomli_w at module top level — that would
# break collection of the whole suite. Instead, serialize fixtures through the
# SAME serializer the tool uses via a lazy helper: prefer an in-process import
# when available (fast path, e.g. `--with tomli-w`), else shell out to
# `uv run --with tomli-w` so byte-identity still tests the tool's strip, not a
# different serializer. The tool itself is always invoked via `uv run --script`
# (its shebang), which auto-provisions tomli-w from its PEP-723 block.
_UV_DUMPS = (
    "import sys, json, tomli_w;"
    "print(tomli_w.dumps(json.loads(sys.stdin.read())), end='')"
)


def tomli_w_dumps(data: dict) -> str:
    try:
        import tomli_w  # noqa: WPS433 — lazy so suite collection stays stdlib-only

        return tomli_w.dumps(data)
    except ImportError:
        proc = subprocess.run(
            ["uv", "run", "--with", "tomli-w", "python", "-c", _UV_DUMPS],
            input=json.dumps(data),
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout

UCG_MARKER = re.compile(r"\[ucg:([a-z0-9-]+-\d+)\]")

# A fragment shaped like assets/ucg-awareness/bmad-prd.toml: flat
# persistent_facts string array + a four-key [ucg] stamp.
FRAGMENT_FACTS = [
    "Steer every NFR toward a machine-checkable budget. [ucg:bmad-prd-01]",
    "Steer every NFR threshold number to cite a source. [ucg:bmad-prd-02]",
    "Steer every requirement to declare its gate-ability tag. [ucg:bmad-prd-03]",
]
FRAGMENT_STAMP = {
    "managed": True,
    "version": "0.3.0",
    "block": "ucg-awareness",
    "installed_at": "2026-06-25T00:00:00Z",
}

HUMAN_FACT = "file:{project-root}/**/project-context.md"

# Real customize targets nest the channel under [workflow] (verified:
# .claude/skills/{bmad-prd,...}/customize.toml — [workflow] then
# persistent_facts). A top-level shape is unfaithful and would let a top-level-
# writing tool pass while producing a dark write the live resolve ignores.
WORKFLOW_KEY = "workflow"
CHANNEL = "persistent_facts"
# A human-owned scalar that lives UNDER [workflow] alongside the channel, so a
# byte-identity / preservation check bites at the workflow level (a top-level
# comprehension would miss a workflow-scalar clobber).
HUMAN_WORKFLOW_SCALAR_KEY = "prd_template"
HUMAN_WORKFLOW_SCALAR_VAL = "assets/prd-template.md"


# --- fixture builders -------------------------------------------------------


def _engine_tree(tmp_path: Path) -> Path:
    """Build a synthetic project tree with the real engine at _bmad/scripts/
    and return the _bmad/custom/ dir where targets should live.
    """
    custom = tmp_path / "_bmad" / "custom"
    scripts = tmp_path / "_bmad" / "scripts"
    custom.mkdir(parents=True, exist_ok=True)
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL_ENGINE, scripts / "resolve_customization.py")
    return custom


def _write_through_serializer(path: Path, data: dict) -> bytes:
    """Write ``data`` THROUGH tomli-w (the same serializer the tool uses) so a
    byte-identity snapshot tests the tool's strip, not tomli-w drift.
    Returns the bytes written.
    """
    raw = tomli_w_dumps(data).encode("utf-8")
    path.write_bytes(raw)
    return raw


def write_fragment(tmp_path: Path, facts=None, stamp=None) -> Path:
    frag = tmp_path / "fragment-bmad-prd.toml"
    data = {
        "persistent_facts": list(facts if facts is not None else FRAGMENT_FACTS),
        "ucg": dict(stamp if stamp is not None else FRAGMENT_STAMP),
    }
    frag.write_bytes(tomli_w_dumps(data).encode("utf-8"))
    return frag


def write_target_with_channel(custom: Path, extra_facts=None) -> Path:
    """A target customize TOML faithful to the real shape: a [workflow] table
    exposing persistent_facts, a human-owned scalar UNDER [workflow], a
    human-owned non-UCG fact in the channel, and a top-level human scalar —
    written through tomli-w.
    """
    target = custom / "bmad-prd.toml"
    facts = [HUMAN_FACT]
    if extra_facts:
        facts.extend(extra_facts)
    data = {
        WORKFLOW_KEY: {
            CHANNEL: facts,
            HUMAN_WORKFLOW_SCALAR_KEY: HUMAN_WORKFLOW_SCALAR_VAL,
        },
        "on_complete": "",
    }
    _write_through_serializer(target, data)
    return target


def write_target_without_channel(custom: Path, with_workflow: bool = True) -> Path:
    """A target that does NOT expose workflow.persistent_facts (schema
    mismatch). With ``with_workflow`` it has a [workflow] table that lacks the
    persistent_facts key (the story-1.9 AC4 case); otherwise it has no
    [workflow] table at all.
    """
    target = custom / "bmad-prd.toml"
    if with_workflow:
        data = {WORKFLOW_KEY: {HUMAN_WORKFLOW_SCALAR_KEY: HUMAN_WORKFLOW_SCALAR_VAL}, "on_complete": ""}
    else:
        data = {"on_complete": "", "some_other_scalar": "x"}
    _write_through_serializer(target, data)
    return target


def run_tool(target: Path, fragment: Path | None = None, extra=None):
    # Invoke the tool exactly as production will: through its `uv run --script`
    # shebang, which auto-provisions tomli-w from the script's PEP-723 block.
    # (The shared test:python runner does NOT carry tomli-w, so calling it via
    # sys.executable would ImportError.)
    cmd = ["uv", "run", "--script", str(SCRIPT), "--target", str(target)]
    if fragment is not None:
        cmd += ["--fragment", str(fragment)]
    if extra:
        cmd += extra
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def load_target(target: Path) -> dict:
    return tomllib.loads(target.read_text(encoding="utf-8"))


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def channel_facts(data: dict) -> list:
    """The nested workflow.persistent_facts list (empty when absent)."""
    workflow = data.get(WORKFLOW_KEY)
    if not isinstance(workflow, dict):
        return []
    facts = workflow.get(CHANNEL)
    return list(facts) if isinstance(facts, list) else []


def ucg_facts(data: dict) -> list[str]:
    return [s for s in channel_facts(data) if isinstance(s, str) and UCG_MARKER.search(s)]


# --- AC1 --------------------------------------------------------------------


def test_merge_appends_stamped_facts(tmp_path):
    custom = _engine_tree(tmp_path)
    target = write_target_with_channel(custom)
    fragment = write_fragment(tmp_path)

    proc = run_tool(target, fragment)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "success"

    data = load_target(target)  # re-parseable by stdlib tomllib => valid TOML
    stamped = ucg_facts(data)

    # Every appended fact carries an embedded [ucg:<id>] marker.
    for s in stamped:
        assert s.startswith("Steer") and UCG_MARKER.search(s), s

    # Anti-vacuous twin: a result with ZERO stamped items after merge fails;
    # the count must equal the fragment's item count and be > 0.
    assert len(stamped) == len(FRAGMENT_FACTS)
    assert len(stamped) > 0

    # Exactly one [ucg] stamp table with all four required keys.
    stamp = data["ucg"]
    for key in ("managed", "version", "block", "installed_at"):
        assert key in stamp, key
    assert stamp["managed"] is True
    assert stamp["block"] == "ucg-awareness"

    # The human row survives untouched alongside the UCG rows, and the items
    # landed in the NESTED workflow channel (not a top-level dark write).
    assert HUMAN_FACT in channel_facts(data)
    assert CHANNEL not in data, "items must NOT be written top-level (dark write)"
    # The human-owned scalar under [workflow] is preserved alongside the channel.
    assert data[WORKFLOW_KEY][HUMAN_WORKFLOW_SCALAR_KEY] == HUMAN_WORKFLOW_SCALAR_VAL


# --- AC2 --------------------------------------------------------------------


def test_idempotent_reinstall(tmp_path):
    custom = _engine_tree(tmp_path)
    target = write_target_with_channel(custom)
    fragment = write_fragment(tmp_path)

    proc1 = run_tool(target, fragment)
    assert proc1.returncode == 0, proc1.stderr
    bytes_run1 = target.read_bytes()
    ucg_count_run1 = len(ucg_facts(load_target(target)))

    proc2 = run_tool(target, fragment)
    assert proc2.returncode == 0, proc2.stderr
    bytes_run2 = target.read_bytes()
    result2 = json.loads(proc2.stdout)

    # Byte-identical after the second run (idempotent convergence).
    assert sha256(bytes_run1) == sha256(bytes_run2)

    # Second run stripped the prior UCG rows then re-appended them: equal.
    assert result2["rows_removed"] == result2["rows_added"]
    assert result2["rows_added"] == len(FRAGMENT_FACTS)

    # UCG-marker count unchanged across runs (no duplication), exactly one stamp.
    data2 = load_target(target)
    assert len(ucg_facts(data2)) == ucg_count_run1 == len(FRAGMENT_FACTS)
    assert isinstance(data2["ucg"], dict)

    # Anti-vacuous twin: prove idempotency comes from the strip, not the
    # appender. A hollow tool that omits the strip-by-marker would, on the
    # second run, produce a STRICTLY LARGER file with duplicated rows. We model
    # that mutant by plain-appending the fragment again to run1's bytes and
    # asserting it diverges in exactly the way the real run does not.
    mutant = load_target(target)
    mutant_facts = channel_facts(mutant) + list(FRAGMENT_FACTS)  # naive re-append
    mutant[WORKFLOW_KEY][CHANNEL] = mutant_facts
    mutant_bytes = tomli_w_dumps(mutant).encode("utf-8")
    assert len(mutant_bytes) > len(bytes_run2)
    assert len(ucg_facts(mutant)) == 2 * len(FRAGMENT_FACTS)
    assert sha256(mutant_bytes) != sha256(bytes_run2)


# --- AC3 --------------------------------------------------------------------


def test_absent_channel_is_failloud_skip(tmp_path):
    custom = _engine_tree(tmp_path)
    target = write_target_without_channel(custom)
    fragment = write_fragment(tmp_path)

    before = target.read_bytes()
    proc = run_tool(target, fragment)
    after = target.read_bytes()

    assert proc.returncode == 0  # a skip is not an invocation error
    assert sha256(before) == sha256(after)  # wrote NOTHING
    result = json.loads(proc.stdout)
    assert result["skipped"] == "schema-mismatch"

    # Anti-vacuous twin (positive control): a target that DOES expose the
    # channel does NOT skip and DOES mutate — proving the probe discriminates,
    # not always-skips.
    good_custom = _engine_tree(tmp_path / "good")
    good_target = write_target_with_channel(good_custom)
    good_before = good_target.read_bytes()
    good_proc = run_tool(good_target, fragment)
    good_after = good_target.read_bytes()
    assert good_proc.returncode == 0, good_proc.stderr
    good_result = json.loads(good_proc.stdout)
    assert good_result.get("skipped") is None
    assert sha256(good_before) != sha256(good_after)  # it mutated
    assert good_result["rows_added"] == len(FRAGMENT_FACTS)


# --- AC4 --------------------------------------------------------------------


def test_handedit_conflict_reported_not_clobbered(tmp_path):
    custom = _engine_tree(tmp_path)
    target = write_target_with_channel(custom)
    fragment = write_fragment(tmp_path)

    # First, a clean install so the manifest records canonical hashes.
    proc1 = run_tool(target, fragment)
    assert proc1.returncode == 0, proc1.stderr

    # Hand-edit ONE stamped row in place (keep its [ucg:<id>] marker), so its
    # content-hash diverges from the manifest. Also add a NON-stamped human row.
    data = load_target(target)
    tampered_text = "HAND EDITED by an operator. [ucg:bmad-prd-01]"
    human_row = "Operator added: investor PRDs need a market sizing section."
    new_facts = []
    for s in channel_facts(data):
        match = UCG_MARKER.search(s) if isinstance(s, str) else None
        if match is not None and match.group(1) == "bmad-prd-01":
            new_facts.append(tampered_text)
        else:
            new_facts.append(s)
    new_facts.append(human_row)
    data[WORKFLOW_KEY][CHANNEL] = new_facts
    target.write_bytes(tomli_w_dumps(data).encode("utf-8"))

    # Re-run the merge.
    proc2 = run_tool(target, fragment)
    assert proc2.returncode == 0, proc2.stderr
    result2 = json.loads(proc2.stdout)

    after = load_target(target)
    facts_after = channel_facts(after)

    # The tampered text survives verbatim; the canonical fragment text for that
    # id was NOT written over it.
    assert tampered_text in facts_after
    canonical = next(f for f in FRAGMENT_FACTS if "[ucg:bmad-prd-01]" in f)
    assert canonical not in facts_after
    # The id is reported in conflicts.
    assert "bmad-prd-01" in result2["conflicts"]

    # Anti-vacuous twin: the NON-stamped human row is preserved untouched and
    # NEVER appears in conflicts (INV-1 human-content safety).
    assert human_row in facts_after
    assert "bmad-prd-01" in result2["conflicts"]  # the stamped one is flagged
    assert all(not c.startswith("Operator") for c in result2["conflicts"])
    # And the human row is plainly not a [ucg:] marker, so it cannot be a conflict id.
    assert UCG_MARKER.search(human_row) is None


# --- AC5 --------------------------------------------------------------------


def test_guarded_import_and_no_reimplement(tmp_path):
    # (a) The script never defines deep_merge/_merge_arrays locally (INV-2).
    proc = subprocess.run(
        ["grep", "-c", r"def deep_merge\|def _merge_arrays", str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    # grep -c prints the count; with zero matches it exits 1 and prints "0".
    assert proc.stdout.strip() == "0", proc.stdout

    # (b) With the engine REMOVED, exit code 2, target untouched, one stderr line.
    custom = _engine_tree(tmp_path)
    (custom.parent / "scripts" / "resolve_customization.py").unlink()
    target = write_target_with_channel(custom)
    fragment = write_fragment(tmp_path)
    before = target.read_bytes()

    proc_missing = run_tool(target, fragment)
    after = target.read_bytes()
    assert proc_missing.returncode == 2
    assert sha256(before) == sha256(after)  # wrote nothing
    warning_lines = [ln for ln in proc_missing.stderr.splitlines() if ln.strip()]
    assert len(warning_lines) == 1, proc_missing.stderr

    # Anti-vacuous twin: with the engine PRESENT, the SAME invocation reaches
    # the merge and exits 0 (not 2) — exit 2 is the missing-dep signal, not the
    # default. (A bare `import` would raise an unhandled traceback here; the
    # guarded try/except is what yields the clean exit 2 above.)
    custom2 = _engine_tree(tmp_path / "present")
    target2 = write_target_with_channel(custom2)
    proc_present = run_tool(target2, fragment)
    assert proc_present.returncode == 0, proc_present.stderr


# --- AC6 --------------------------------------------------------------------


def test_remove_strips_only_ucg_rows(tmp_path):
    custom = _engine_tree(tmp_path)
    # Pre-install snapshot: a baseline with a HUMAN-authored non-stamped row,
    # written THROUGH tomli-w once so byte-identity tests the strip, not drift.
    human_extra = "Operator: always cite an ADR for load-bearing decisions."
    target = write_target_with_channel(custom, extra_facts=[human_extra])
    pre_install_snapshot = target.read_bytes()

    fragment = write_fragment(tmp_path)
    proc_merge = run_tool(target, fragment)
    assert proc_merge.returncode == 0, proc_merge.stderr
    # Sanity: the merge actually added UCG rows + a stamp (not a no-op).
    merged = load_target(target)
    assert len(ucg_facts(merged)) == len(FRAGMENT_FACTS)
    assert "ucg" in merged

    proc_remove = run_tool(target, extra=["--remove"])
    assert proc_remove.returncode == 0, proc_remove.stderr
    after_remove = target.read_bytes()

    # Byte-identical reversal to the pre-install snapshot (INV-10 / NFR-5).
    assert sha256(after_remove) == sha256(pre_install_snapshot)

    # The human-authored non-stamped rows survive --remove, and the human-owned
    # scalar under [workflow] is byte-preserved too.
    reverted = load_target(target)
    assert human_extra in channel_facts(reverted)
    assert HUMAN_FACT in channel_facts(reverted)
    assert reverted[WORKFLOW_KEY][HUMAN_WORKFLOW_SCALAR_KEY] == HUMAN_WORKFLOW_SCALAR_VAL
    assert "ucg" not in reverted  # stamp table removed

    # Anti-vacuous twin: a --remove that widened to strip the whole
    # workflow.persistent_facts array would destroy the human rows and break
    # byte identity. We model that mutant and prove it diverges from the snapshot.
    mutant = load_target(target)
    mutant[WORKFLOW_KEY][CHANNEL] = []  # the over-wide strip
    mutant_bytes = tomli_w_dumps(mutant).encode("utf-8")
    assert sha256(mutant_bytes) != sha256(pre_install_snapshot)
    assert human_extra not in tomli_w_dumps(mutant)


# --- AC7 --------------------------------------------------------------------


def test_exit_code_lane_and_pep723(tmp_path):
    # (a) The PEP-723 inline-script block declares tomli-w as a dependency.
    text = SCRIPT.read_text(encoding="utf-8")
    block = re.search(r"# /// script\n(.*?)# ///", text, re.DOTALL)
    assert block is not None, "no PEP-723 script block"
    block_body = block.group(1)
    assert "tomli-w" in block_body, block_body
    assert 'requires-python = ">=3.11"' in block_body

    # (b) A syntactically-broken fragment TOML => exit 1 (validation), not 2.
    custom = _engine_tree(tmp_path)
    target = write_target_with_channel(custom)
    bad_fragment = tmp_path / "broken.toml"
    bad_fragment.write_text("persistent_facts = [ this is not valid toml\n", encoding="utf-8")
    proc_bad = run_tool(target, bad_fragment)
    assert proc_bad.returncode == 1, (proc_bad.returncode, proc_bad.stderr)

    # An unparseable TARGET is also a validation error (exit 1).
    custom_b = _engine_tree(tmp_path / "badtarget")
    bad_target = custom_b / "bmad-prd.toml"
    bad_target.write_text("persistent_facts = [ broken\n", encoding="utf-8")
    good_fragment = write_fragment(tmp_path)
    proc_bad_t = run_tool(bad_target, good_fragment)
    assert proc_bad_t.returncode == 1, (proc_bad_t.returncode, proc_bad_t.stderr)

    # Anti-vacuous twin: a well-formed successful merge exits 0 (not 1) —
    # exit 1 is reserved for validation failure, not emitted unconditionally.
    custom_ok = _engine_tree(tmp_path / "ok")
    ok_target = write_target_with_channel(custom_ok)
    proc_ok = run_tool(ok_target, good_fragment)
    assert proc_ok.returncode == 0, proc_ok.stderr

    # And removing tomli-w from the PEP-723 block would fail part (a):
    # confirm the dep is genuinely declared (the tool is NOT stdlib-only).
    deps_line = re.search(r"dependencies = \[([^\]]*)\]", block_body)
    assert deps_line is not None and "tomli-w" in deps_line.group(1)


# --- Integration: the real fragment must reach the RESOLVED workflow channel.
# This is the regression test that catches the top-level dark-write bug — a
# tool that wrote a TOP-LEVEL persistent_facts key would leave the items OUT of
# deep_merge(base, overlay)['workflow']['persistent_facts'] (the live resolve
# ignores top-level keys when the base nests under [workflow]).


REAL_FRAGMENT = (
    Path(__file__).resolve().parents[2] / "assets" / "ucg-awareness" / "bmad-prd.toml"
)


def _import_real_deep_merge():
    """Import deep_merge from the same REAL_ENGINE the tool imports it from."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_resolve_customization_for_test", REAL_ENGINE)
    assert spec is not None and spec.loader is not None, REAL_ENGINE
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.deep_merge


def test_real_fragment_lands_in_resolved_workflow_channel(tmp_path):
    assert REAL_FRAGMENT.exists(), REAL_FRAGMENT
    fragment_data = tomllib.loads(REAL_FRAGMENT.read_text(encoding="utf-8"))
    fragment_ucg_facts = [
        s for s in fragment_data["persistent_facts"] if UCG_MARKER.search(s)
    ]
    assert len(fragment_ucg_facts) > 0  # the real fragment authors UCG items

    # Merge the REAL fragment into a FRESH temp target via the tool. Fresh-seed
    # path: the tool creates [workflow] and lands the channel there.
    custom = _engine_tree(tmp_path)
    target = custom / "bmad-prd.toml"  # does not exist yet -> fresh install
    proc = run_tool(target, REAL_FRAGMENT)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "success"

    overlay = load_target(target)

    # A COMMITTED-style base customize.toml mirroring the real shape (built as a
    # fixture string so the test is CI-portable — _bmad/ and .claude/ are
    # gitignored). It carries a HUMAN baseline fact + a human scalar.
    base_human_fact = "file:human-baseline [ucg-not]"
    base = tomllib.loads(
        f'[{WORKFLOW_KEY}]\n'
        f'{CHANNEL} = ["{base_human_fact}"]\n'
        f'{HUMAN_WORKFLOW_SCALAR_KEY} = "base.md"\n'
    )
    base_channel = list(base[WORKFLOW_KEY][CHANNEL])  # [base_human_fact]

    deep_merge = _import_real_deep_merge()
    resolved = deep_merge(base, overlay)
    resolved_channel = resolved[WORKFLOW_KEY][CHANNEL]

    # THE load-bearing assertion: the fragment's UCG items genuinely reach the
    # RESOLVED workflow channel (a top-level-writing tool would leave them out).
    for fact in fragment_ucg_facts:
        assert fact in resolved_channel, fact
    assert all(UCG_MARKER.search(f) for f in fragment_ucg_facts)

    # Additive + order-preserving: the base channel is a strict PREFIX of the
    # resolved channel (UCG appended on the end, base untouched).
    assert resolved_channel[: len(base_channel)] == base_channel
    assert len(resolved_channel) == len(base_channel) + len(fragment_ucg_facts)
    assert base_human_fact in resolved_channel

    # Anti-vacuous: prove this is RED on the old top-level behavior. A mutant
    # overlay that wrote the channel TOP-LEVEL (as the buggy tool did) lands
    # NOTHING in the resolved workflow channel — only the base survives.
    toplevel_overlay = dict(overlay)
    toplevel_overlay.pop(WORKFLOW_KEY, None)
    toplevel_overlay[CHANNEL] = list(fragment_ucg_facts)  # the dark write
    mutant_resolved = deep_merge(base, toplevel_overlay)
    assert mutant_resolved[WORKFLOW_KEY][CHANNEL] == base_channel  # items lost
    for fact in fragment_ucg_facts:
        assert fact not in mutant_resolved[WORKFLOW_KEY][CHANNEL]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
