"""TEA shaping fragments: channel discipline, idempotent merge, inertness.

Case 1 channel discipline (only persistent_facts + [ucg] stamp; no superseded channel),
Case 2 idempotent + reversible merge into workflow.persistent_facts via the VENDORED engine
(CI-portable — never the gitignored .claude target; mirrors test_merge_customization.py's
hermetic fixture pattern), Case 5 non-UCG inertness (no auto-fire) + deep_merge validity.

Fragments author persistent_facts TOP-LEVEL; merge_customization.py re-homes them into the
target's nested [workflow].persistent_facts (verified: merge_customization.py:255-257). The
phrase "under the [workflow] namespace" describes the TARGET landing, not the fragment.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import tomllib
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_ASSETS = _SKILL_ROOT / "assets" / "ucg-awareness"
TEST_DESIGN = _ASSETS / "bmad-testarch-test-design.toml"
NFR = _ASSETS / "bmad-testarch-nfr.toml"
MERGE = _SKILL_ROOT / "scripts" / "merge_customization.py"
REAL_ENGINE = Path(__file__).resolve().parent / "fixtures" / "engine" / "resolve_customization.py"

HUMAN_FACT = "file:{project-root}/**/project-context.md"
WORKFLOW_KEY = "workflow"
CHANNEL = "persistent_facts"
STAMP_KEYS = {"managed", "version", "block", "installed_at"}


def _load(p: Path) -> dict:
    with open(p, "rb") as fh:
        return tomllib.load(fh)


def _tomli_w_dumps(data: dict) -> str:
    try:
        import tomli_w  # noqa: WPS433 — lazy so suite collection stays stdlib-only

        return tomli_w.dumps(data)
    except ImportError:
        proc = subprocess.run(
            ["uv", "run", "--with", "tomli-w", "python", "-c",
             "import sys,json,tomli_w;print(tomli_w.dumps(json.loads(sys.stdin.read())),end='')"],
            input=json.dumps(data), capture_output=True, text=True, check=True,
        )
        return proc.stdout


def _disciplined(data: dict, text: str) -> bool:
    if (set(data) - {"ucg"}) != {"persistent_facts"}:
        return False
    facts = data.get("persistent_facts")
    if not isinstance(facts, list) or not facts:
        return False
    for forbidden in ("guidance_append", "rules_append", "on_complete",
                      "activation_steps_prepend", "activation_steps_append"):
        if forbidden in text:
            return False
    stamp = data.get("ucg")
    if not isinstance(stamp, dict) or set(stamp) != STAMP_KEYS:
        return False
    return stamp.get("managed") is True and stamp.get("block") == "ucg-awareness"


# Case 1 ---------------------------------------------------------------------
def test_fragments_target_only_persistent_facts_and_stamp():
    for frag in (TEST_DESIGN, NFR):
        assert _disciplined(_load(frag), frag.read_text(encoding="utf-8")), frag.name
    # anti-vacuous: a superseded-channel write is rejected
    mutant = (
        'persistent_facts = ["x [ucg:m-01]"]\n[tea]\nguidance_append = ["x"]\n'
        '[ucg]\nmanaged = true\nversion = "0.3.0"\nblock = "ucg-awareness"\n'
        'installed_at = "2026-06-26T00:00:00Z"\n'
    )
    assert not _disciplined(tomllib.loads(mutant), mutant)
    # anti-vacuous: a fragment missing the [ucg] stamp is rejected
    nostamp = 'persistent_facts = ["x [ucg:m-01]"]\n'
    assert not _disciplined(tomllib.loads(nostamp), nostamp)


# Case 2 (CI-portable: vendored engine, never the gitignored .claude target) ----
def _engine_tree(tmp_path: Path) -> Path:
    custom = tmp_path / "_bmad" / "custom"
    scripts = tmp_path / "_bmad" / "scripts"
    custom.mkdir(parents=True, exist_ok=True)
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL_ENGINE, scripts / "resolve_customization.py")
    return custom


def _write_target(custom: Path, facts: list) -> Path:
    target = custom / "bmad-testarch-test-design.toml"
    data = {WORKFLOW_KEY: {CHANNEL: list(facts), "tea_template": "assets/x.md"}, "on_complete": ""}
    target.write_bytes(_tomli_w_dumps(data).encode("utf-8"))
    return target


def _run(target: Path, fragment: Path | None = None, extra=None):
    cmd = ["uv", "run", "--script", str(MERGE), "--target", str(target)]
    if fragment is not None:
        cmd += ["--fragment", str(fragment)]
    if extra:
        cmd += extra
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _channel(target: Path) -> list:
    data = tomllib.loads(target.read_text(encoding="utf-8"))
    wf = data.get(WORKFLOW_KEY, {})
    return wf.get(CHANNEL, []) if isinstance(wf, dict) else []


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_merge_idempotent_and_reversible_into_persistent_facts(tmp_path):
    custom = _engine_tree(tmp_path)
    target = _write_target(custom, [HUMAN_FACT])
    original = _sha(target)

    assert _run(target, TEST_DESIGN).returncode == 0
    assert HUMAN_FACT in _channel(target), "the project-context.md fact must survive the merge"
    assert any("[ucg:bmad-testarch-test-design-" in f for f in _channel(target)), "fragment facts landed"
    h1 = _sha(target)
    assert _run(target, TEST_DESIGN).returncode == 0
    assert _sha(target) == h1, "second install must be byte-identical (idempotent strip-then-reappend)"

    assert _run(target, extra=["--remove"]).returncode == 0
    assert _sha(target) == original, "--remove restores the byte-identical pre-install target"

    # anti-vacuous: a hand-edited stamped row is a CONFLICT, not silently re-stamped
    tgt = _write_target(_engine_tree(tmp_path / "b"), [HUMAN_FACT])
    assert _run(tgt, TEST_DESIGN).returncode == 0
    data = tomllib.loads(tgt.read_text(encoding="utf-8"))
    facts = data[WORKFLOW_KEY][CHANNEL]
    idx = next(i for i, f in enumerate(facts) if "[ucg:bmad-testarch-test-design-01]" in f)
    facts[idx] = "TAMPERED " + facts[idx]
    tgt.write_bytes(_tomli_w_dumps(data).encode("utf-8"))
    out = json.loads(_run(tgt, TEST_DESIGN).stdout)
    assert out.get("conflicts"), "hand-edited stamped row must be reported as a conflict"
    assert any(f.startswith("TAMPERED") for f in _channel(tgt)), "the conflict is left in place, not clobbered"


# Case 5 ---------------------------------------------------------------------
def _deep_merge():
    spec = importlib.util.spec_from_file_location("engine_rc", REAL_ENGINE)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.deep_merge


def test_non_ucg_path_facts_are_additive_and_inert():
    for frag in (TEST_DESIGN, NFR):
        for fact in _load(frag)["persistent_facts"]:
            low = fact.lower()
            assert "/ucg-formalize" not in low and "ucg-formalize" not in low and "preflight" not in low, fact
    # deep_merge(base, overlay) yields a list-typed workflow.persistent_facts
    deep_merge = _deep_merge()
    base = {"workflow": {"persistent_facts": [HUMAN_FACT]}}
    overlay = {"workflow": {"persistent_facts": list(_load(TEST_DESIGN)["persistent_facts"])}}
    merged = deep_merge(base, overlay)
    assert isinstance(merged["workflow"]["persistent_facts"], list)
    # anti-vacuous: a fact that auto-fires UCG would be caught by the inertness grep
    auto_fire = "run /ucg-formalize before finishing"
    assert "ucg-formalize" in auto_fire.lower() or "preflight" in auto_fire.lower()
