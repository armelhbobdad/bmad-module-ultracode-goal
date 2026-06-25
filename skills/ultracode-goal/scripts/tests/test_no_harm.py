#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest", "tomli-w"]
# ///
"""No-harm test for the non-UCG path.

With the four planning shaping fragments merged into their
``_bmad/custom/{skill}.toml`` overlays but UCG itself NEVER invoked, a plain
BMAD authoring run resolves through the SAME live engine (``deep_merge`` from
``_bmad/scripts/resolve_customization.py``) identically-except-additively, and
never auto-fires a ``/ucg-formalize`` prompt or gate.

CRITICAL NESTING FACT (load-bearing, audit fix): the live engine returns a
table whose only top-level key is ``workflow``; ``persistent_facts`` AND every
human-owned scalar (``prd_template`` etc.) live at ``resolved['workflow'][...]``.
So the all-keys-equal-except-``persistent_facts`` and strict-prefix checks MUST
run on ``resolved['workflow']`` — a top-level comprehension filters nothing and
would let an out-of-channel scalar write under ``[workflow]`` slip through.
The opt-out and schema-mismatch checks instead compare the FULL resolved dict
recursively (``resolved == baseline``), which naturally walks into the nested
workflow sub-table.

Conventions mirror the sibling tests (PEP-723 header, ``SCRIPT =
parents[1] / "merge_customization.py"``, subprocess + ``json.loads(stdout)``).
The base customize.toml files under ``.claude/skills/`` are GITIGNORED, so the
base greps are guarded skip-if-absent (CI-portable + honest). The in-test base
is a faithful FIXTURE (not the gitignored live file) for the same
reason; the real tracked fragment is consumed live.

Run: uv run --with pytest --with tomli-w pytest \
       skills/ultracode-goal/scripts/tests/test_no_harm.py -v
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "merge_customization.py"
# The live engine a plain BMAD run resolves through — vendored under fixtures/
# so the suite stays hermetic in CI (the real _bmad/ tree is gitignored).
REAL_ENGINE = Path(__file__).resolve().parent / "fixtures" / "engine" / "resolve_customization.py"
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets" / "ucg-awareness"
REPO_ROOT = Path(__file__).resolve().parents[4]

WORKFLOW_KEY = "workflow"
CHANNEL = "persistent_facts"

# The four planning targets (live PRD surface, never the deprecated
# bmad-create-prd / bmad-edit-prd shims).
PLANNING_SKILLS = (
    "bmad-prd",
    "bmad-architecture",
    "bmad-create-epics-and-stories",
    "bmad-create-story",
)
REAL_FRAGMENTS = {skill: ASSETS_DIR / f"{skill}.toml" for skill in PLANNING_SKILLS}
REAL_PRD_FRAGMENT = REAL_FRAGMENTS["bmad-prd"]

# Tokens that would indicate a /ucg-formalize auto-fire surface.
AUTOFIRE_TOKENS = re.compile(r"ucg-formalize|formalize_check|/ucg-formalize")
# Activation/execution channels that WOULD run on a plain authoring run.
EXECUTION_CHANNELS = (
    "activation_steps_append",
    "activation_steps_prepend",
    "on_complete",
)

UCG_MARKER = re.compile(r"\[ucg:([a-z0-9-]+-\d+)\]")


# --- engine + tooling helpers ----------------------------------------------


def _import_deep_merge():
    """Import deep_merge from the REAL engine (the live import contract)."""
    spec = importlib.util.spec_from_file_location("_resolve_customization_no_harm", REAL_ENGINE)
    assert spec is not None and spec.loader is not None, REAL_ENGINE
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.deep_merge


DEEP_MERGE = _import_deep_merge()


def _tomli_w_dumps(data: dict) -> str:
    """Serialize through tomli-w (lazy import so suite collection stays stdlib-
    only under the shared `npm run test:python` runner, which carries only
    pytest); fall back to a `uv run --with tomli-w` subprocess otherwise.
    """
    try:
        import tomli_w  # noqa: WPS433 — lazy

        return tomli_w.dumps(data)
    except ImportError:
        proc = subprocess.run(
            ["uv", "run", "--with", "tomli-w", "python", "-c",
             "import sys, json, tomli_w;"
             "print(tomli_w.dumps(json.loads(sys.stdin.read())), end='')"],
            input=json.dumps(data),
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout


def _engine_tree(tmp_path: Path) -> Path:
    """Synthetic project tree with the real engine at _bmad/scripts/, so the
    tool's guarded deep_merge import resolves exactly as at install time.
    Returns the _bmad/custom/ dir where targets live.
    """
    custom = tmp_path / "_bmad" / "custom"
    scripts = tmp_path / "_bmad" / "scripts"
    custom.mkdir(parents=True, exist_ok=True)
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL_ENGINE, scripts / "resolve_customization.py")
    return custom


def _write_toml(path: Path, data: dict) -> bytes:
    raw = _tomli_w_dumps(data).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def run_tool(target: Path, fragment: Path | None = None, extra=None):
    """Invoke merge_customization.py via its `uv run --script` shebang (which
    auto-provisions tomli-w from the PEP-723 block).
    """
    cmd = ["uv", "run", "--script", str(SCRIPT), "--target", str(target)]
    if fragment is not None:
        cmd += ["--fragment", str(fragment)]
    if extra:
        cmd += extra
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def resolve(base: dict, overlay: dict) -> dict:
    """The plain-BMAD resolve: base + (team) overlay through the LIVE engine."""
    return DEEP_MERGE(base, overlay)


# A faithful fixture BASE mirroring the real bmad-prd customize.toml shape: the
# configurable surface is the top-level [workflow] table, owning the channel
# AND human scalars. CI-portable (does NOT read the gitignored .claude/ base).
def _fixture_base() -> dict:
    return {
        WORKFLOW_KEY: {
            CHANNEL: ["file:{project-root}/**/project-context.md"],
            "prd_template": "assets/prd-template.md",
            "prd_output_path": "{output_folder}/prd.md",
            "doc_standards": "house-style",
        },
    }


# --- resolve diff is persistent_facts append-only ---------------------------


def test_resolve_diff_is_persistent_facts_append_only(tmp_path):
    custom = _engine_tree(tmp_path)
    base = _fixture_base()

    # Merge the REAL fragment into a temp _bmad/custom/bmad-prd.toml. The target
    # is fresh-seeded from the fixture base so the overlay carries the base
    # human surface + the appended UCG rows (the realistic team-overlay shape).
    target = custom / "bmad-prd.toml"
    _write_toml(target, base)
    proc = run_tool(target, REAL_PRD_FRAGMENT)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "success"
    overlay = load_toml(target)

    resolved_with = resolve(base, overlay)
    resolved_without = resolve(base, {})  # no overlay == plain BMAD run

    # NESTING: bind to the workflow sub-table that owns persistent_facts AND the
    # human scalars (NEVER the top-level dict, whose only key is `workflow`).
    assert list(resolved_without.keys()) == [WORKFLOW_KEY]  # empirical nesting fact
    wf_with = resolved_with[WORKFLOW_KEY]
    wf_without = resolved_without[WORKFLOW_KEY]

    # Every workflow key byte-identical EXCEPT persistent_facts (additive-only,
    # sanctioned-channel: never a human scalar, never a new key).
    except_pf_with = {k: v for k, v in wf_with.items() if k != CHANNEL}
    except_pf_without = {k: v for k, v in wf_without.items() if k != CHANNEL}
    assert except_pf_with == except_pf_without

    # persistent_facts differs by exactly the additive UCG items appended on the
    # end: the no-overlay list is a strict, order-preserving PREFIX.
    pf_with = wf_with[CHANNEL]
    pf_without = wf_without[CHANNEL]
    assert pf_without == pf_with[: len(pf_without)]
    assert len(pf_with) > len(pf_without)  # genuinely grew (not vacuous)
    # The appended tail carries the UCG markers (the additive items are UCG's).
    appended_tail = pf_with[len(pf_without):]
    assert any(UCG_MARKER.search(s) for s in appended_tail if isinstance(s, str))

    # Anti-vacuous twin: a MUTATED fragment that sets a human-owned scalar UNDER
    # [workflow] (prd_template) — or adds a NEW workflow key — must FAIL the
    # workflow-level except-persistent_facts dict-equality. A top-level
    # comprehension would have MISSED this (prd_template lives under workflow).
    mutant_overlay = {
        WORKFLOW_KEY: {
            CHANNEL: list(wf_without[CHANNEL]) + ["UCG row. [ucg:bmad-prd-01]"],
            "prd_template": "hijacked.md",  # out-of-channel scalar write
        },
    }
    m_with = resolve(base, mutant_overlay)[WORKFLOW_KEY]
    m_except_pf = {k: v for k, v in m_with.items() if k != CHANNEL}
    assert m_except_pf != except_pf_without  # the workflow-level check has teeth
    assert m_with["prd_template"] == "hijacked.md"

    # Proof the comprehension MUST run at the workflow level, not the top level
    # (the orphaned-index audit fix). At the top level, `persistent_facts` is
    # NEVER a key (the only top-level key is `workflow`), so a top-level
    # `{k:v for k,v in resolved.items() if k!='persistent_facts'}` filters
    # NOTHING — it keeps the whole `workflow` value, persistent_facts included.
    # That makes the top-level check FALSELY FAIL the legitimate additive-only
    # case (the benign UCG append) because it cannot isolate persistent_facts:
    top_with = {k: v for k, v in resolved_with.items() if k != CHANNEL}
    top_without = {k: v for k, v in resolved_without.items() if k != CHANNEL}
    assert "persistent_facts" not in top_with  # nothing was filtered at top level
    assert top_with != top_without  # top-level filter wrongly flags the benign append
    # …whereas the workflow-level check correctly passed it (asserted above:
    # except_pf_with == except_pf_without). So the level matters: top-level both
    # misses out-of-channel scalar writes' isolation AND mis-flags additive ones.


# --- no formalize auto-fire surface -----------------------------------------


def _autofire_in_execution_channel(text: str) -> bool:
    """True iff an auto-fire token appears inside an EXECUTION channel
    (activation_steps_*/on_complete) — i.e. a wired auto-fire, not inert text.
    Parses the TOML and checks those channels' string contents.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return False

    def _scan(scope: dict) -> bool:
        for chan in EXECUTION_CHANNELS:
            val = scope.get(chan)
            if isinstance(val, str) and AUTOFIRE_TOKENS.search(val):
                return True
            if isinstance(val, list) and any(
                isinstance(x, str) and AUTOFIRE_TOKENS.search(x) for x in val
            ):
                return True
        return False

    if _scan(data):
        return True
    wf = data.get(WORKFLOW_KEY)
    return isinstance(wf, dict) and _scan(wf)


def test_no_formalize_autofire_surface():
    # (a) The four shipped fragments: any auto-fire token must live ONLY inside
    # an inert persistent_facts string, NEVER an execution channel.
    fragments_checked = 0
    for skill, path in REAL_FRAGMENTS.items():
        assert path.exists(), path
        text = path.read_text(encoding="utf-8")
        fragments_checked += 1
        assert not _autofire_in_execution_channel(text), (
            f"{skill}: /ucg-formalize wired into an execution channel"
        )
        # Any token that IS present sits in persistent_facts (inert) only.
        if AUTOFIRE_TOKENS.search(text):
            data = tomllib.loads(text)
            facts = data.get(CHANNEL, []) or (data.get(WORKFLOW_KEY, {}) or {}).get(CHANNEL, [])
            joined_facts = "\n".join(s for s in facts if isinstance(s, str))
            # every token occurrence must be accounted for by the facts strings
            assert AUTOFIRE_TOKENS.search(joined_facts) or not AUTOFIRE_TOKENS.search(text)
    assert fragments_checked == len(PLANNING_SKILLS)

    # (b) The base customize.toml files are GITIGNORED — guard each grep with
    # skip-if-absent (honest + CI-portable). When present, zero auto-fire tokens.
    bases_present = 0
    for skill in PLANNING_SKILLS:
        base = REPO_ROOT / ".claude" / "skills" / skill / "customize.toml"
        if not base.exists():
            continue  # CI-portable skip — the gitignored base is not shipped
        bases_present += 1
        base_text = base.read_text(encoding="utf-8")
        assert not AUTOFIRE_TOKENS.search(base_text), (
            f"{skill} base customize.toml references a UCG auto-fire token"
        )
    # (No assert on bases_present: the bases may legitimately all be absent in a
    # clean CI checkout — the skip-if-absent guard keeps the test honest.)

    # Anti-vacuous twin: a planted fragment carrying an EXECUTABLE auto-fire
    # wired into an activation channel is DETECTED and fails the inert check.
    planted = (
        '[workflow]\n'
        'activation_steps_append = ["run /ucg-formalize"]\n'
        'persistent_facts = ["inert guardrail [ucg:bmad-prd-01]"]\n'
    )
    assert _autofire_in_execution_channel(planted)  # the real check would FAIL on this
    # And the inverse: an inert persistent_facts mention is NOT flagged.
    inert = (
        '[workflow]\n'
        'persistent_facts = ["mention /ucg-formalize only as a fact [ucg:bmad-prd-01]"]\n'
    )
    assert not _autofire_in_execution_channel(inert)


# --- opt-out resolves to baseline -------------------------------------------


def test_optout_resolves_to_baseline(tmp_path):
    custom = _engine_tree(tmp_path)
    base = _fixture_base()

    # Opt-OUT (enable_ucg_awareness=OFF): Installer Step 6b never spawns the
    # merge tool, so the team overlay is empty. Model that as no merge call.
    baseline = resolve(base, {})  # the no-overlay baseline

    optout_overlay = {}  # nothing merged (Step 6b gated off)
    resolved_optout = resolve(base, optout_overlay)

    # FULL recursive dict equality (walks the entire nested workflow sub-table):
    # a declined/uninstalled state is a true no-op.
    assert resolved_optout == baseline

    # Anti-vacuous twin: opt-IN (fragment actually merged) makes the FULL
    # resolved dict DIVERGE from baseline — proving opt-out is a genuine no-op
    # distinct from opt-in, not a flag-independent pass.
    target = custom / "bmad-prd.toml"
    _write_toml(target, base)
    proc = run_tool(target, REAL_PRD_FRAGMENT)
    assert proc.returncode == 0, proc.stderr
    optin_overlay = load_toml(target)
    resolved_optin = resolve(base, optin_overlay)
    assert resolved_optin != baseline
    # And the divergence is precisely in workflow.persistent_facts.
    assert resolved_optin[WORKFLOW_KEY][CHANNEL] != baseline[WORKFLOW_KEY][CHANNEL]


# --- schema-mismatch target is untouched ------------------------------------


def test_schema_mismatch_target_is_untouched(tmp_path):
    custom = _engine_tree(tmp_path)

    # A synthetic target with a [workflow] table but NO persistent_facts key
    # under it (the schema-drift case). It is non-empty so the probe's
    # schema-mismatch branch (not the fresh-seed branch) fires.
    target = custom / "bmad-prd.toml"
    mismatch_base = {WORKFLOW_KEY: {"prd_template": "x.md"}, "on_complete": ""}
    before_bytes = _write_toml(target, mismatch_base)

    proc = run_tool(target, REAL_PRD_FRAGMENT)
    after_bytes = target.read_bytes()

    assert proc.returncode == 0  # a skip is not an invocation error
    result = json.loads(proc.stdout)
    assert result["skipped"] == "schema-mismatch"
    assert before_bytes == after_bytes  # wrote NOTHING (no dark write)

    # FULL recursive baseline-equal resolve: the schema-mismatch target resolves
    # exactly as its no-overlay baseline (the overlay == the unchanged file).
    base = load_toml(target)
    baseline = resolve(base, {})
    resolved = resolve(base, load_toml(target))
    assert resolved == baseline

    # Anti-vacuous twin: a target that DOES expose workflow.persistent_facts is
    # NOT skipped — it merges and the bytes change (proving the skip is driven by
    # the real shape probe, not an unconditional skip that would make no-harm
    # vacuously true by never writing).
    good = custom / "bmad-architecture.toml"
    good_base = {WORKFLOW_KEY: {CHANNEL: ["file:human [ucg-not]"], "spine_template": "s.md"}}
    good_before = _write_toml(good, good_base)
    good_proc = run_tool(good, REAL_FRAGMENTS["bmad-architecture"])
    good_after = good.read_bytes()
    assert good_proc.returncode == 0, good_proc.stderr
    good_result = json.loads(good_proc.stdout)
    assert good_result.get("skipped") is None  # NOT skipped
    assert good_result["status"] == "success"
    assert good_before != good_after  # it merged + changed bytes


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
