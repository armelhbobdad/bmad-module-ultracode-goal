#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""The `on_escalation` lifecycle hook: two fire sites, one run-scoped dedup marker.

Static prose-contract assertions over execute.md's post-spine escalation-ping
clause and finalize.md's `## Escalation hook` section (ONE matcher applied to
both, so a per-site twin reds one while the other stays green), over
preflight.md's step-5 arming purge, plus a tomllib parse of the shipped
`customize.toml` and a live drive of the VENDORED merge engine.

Anti-vacuous twins are fixture-driven: three verbatim pre-edit snapshots taken
before this contract landed (`finalize_epic_complete_hook_no_escalation.md`,
`execute_spine_end_no_escalation_fire.md`, `preflight_step5_no_escalation_purge.md`)
must FAIL the same assertions the live files pass, and a twin-integrity test
pins that each fixture is a real snapshot rather than an emptied file that
trivially lacks the clause.

Stated limit: these are **presence proofs**. They show the fire sites, the
shared marker path and the purge are in the shipped files. They do not show that
an executor obeys them; no end-to-end "the hook actually fired" claim is made.

Stdlib + pytest only.
"""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_TESTS = Path(__file__).resolve().parent
_FIXTURES = _TESTS / "fixtures"

_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_FINALIZE = _SKILL_ROOT / "references" / "finalize.md"
_CUSTOMIZE = _SKILL_ROOT / "customize.toml"
_HOOK = _SKILL_ROOT / "scripts" / "hooks" / "budget_stop.py"

# The real engine, vendored under fixtures/ so the suite stays hermetic in CI
# (the real _bmad/ tree is gitignored and absent on a clean checkout).
REAL_ENGINE = _FIXTURES / "engine" / "resolve_customization.py"

_FIX_FINALIZE = _FIXTURES / "finalize_epic_complete_hook_no_escalation.md"
_FIX_EXECUTE = _FIXTURES / "execute_spine_end_no_escalation_fire.md"
_FIX_STEP5 = _FIXTURES / "preflight_step5_no_escalation_purge.md"

# The one dedup marker path, spelled once here. Site agreement is asserted
# between the two EXTRACTED tokens, not against this literal alone, so a rename
# that drifts one site reds even when the new name is otherwise well-formed.
_DEDUP_TOKEN = "{workflow.implementation_artifacts}/.on-escalation-fired-<run-id>"

# The two run-scoping conjuncts, and the sidecar glob that is deliberately NOT purged.
_PLAN_CONJUNCT = "names a story in this run's plan"
_TIME_CONJUNCT = "was written after this run's start"
_PURGED_GLOBS = (".escalation-*", ".on-escalation-fired-*")
_UNPURGED_GLOB = "escalation-*.json"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# Reuse the sibling module's step-5 slicer verbatim rather than re-deriving it:
# the arming block must be sliced the SAME way in both, or the two contracts
# could silently be asserting over different text.
_hook_env = _load(_TESTS / "test_preflight_step5_hook_env.py", "test_preflight_step5_hook_env")
_step5 = _hook_env._step5
_hook_env_entries = _hook_env._hook_env_entries


# --- section slicing ---------------------------------------------------------

def _clause_a(text: str | None = None) -> str:
    """Execute's post-spine paragraph plus the escalation-ping clause.

    Sliced exactly as `fixtures/execute_spine_end_no_escalation_fire.md` was
    captured, so the fixture is this same region before the clause landed.
    """
    text = text if text is not None else _EXECUTE.read_text(encoding="utf-8")
    start = text.index("After the spine finishes")
    return text[start:text.index("### Escalation sidecar", start)]


def _finalize_site(text: str | None = None) -> str:
    text = text if text is not None else _FINALIZE.read_text(encoding="utf-8")
    start = text.index("## Escalation hook")
    return text[start:text.index("## Headless output", start)]


def _sentences(block: str) -> list[str]:
    """Split on a period followed by whitespace (markdown bold/backticks do not
    end a sentence, so `foo.md` and `**Heading.**` stay intact)."""
    return re.split(r"(?<=\.)\s+", block)


# --- the shared matchers -----------------------------------------------------

def _dedup_tokens(site: str) -> set[str]:
    """Every backticked code span in `site` naming a fired-marker path."""
    return {tok for tok in re.findall(r"`([^`]*)`", site) if "fired" in tok}


def _fire_offset(site: str) -> int:
    """Where the site actually fires: the resolve of the hook key."""
    return site.find("--key workflow.on_escalation")


_FIRE_SITE_CHECKS = {
    "names exactly one fired-marker path token": lambda s: len(_dedup_tokens(s)) == 1,
    "roots that marker under the impl-artifacts dir": lambda s: _dedup_tokens(s) == {_DEDUP_TOKEN},
    "states the dedup is check-then-write": lambda s: "check-then-write" in s,
    "marker present -> skip silently": lambda s: bool(
        re.search(r"already present, skip silently", s)
    ),
    "marker absent -> proceed to fire": lambda s: "If it is absent" in s,
    "resolves the on_escalation key": lambda s: _fire_offset(s) >= 0,
    "writes the marker only after firing": lambda s: "only then write the fired-marker" in s,
    "carries the escalating story id as context": lambda s: "the escalating story id" in s,
    "names the typed sidecar as the context path": lambda s: "escalation-<story_id>.json" in s,
    "a resolved-empty value is a silent no-op": lambda s: bool(
        re.search(r"resolved-empty value is a silent no-op", s)
    ),
    "and an empty value writes no marker": lambda s: "no fired-marker is written" in s,
}


def _unmet(checks: dict, section: str) -> list[str]:
    return sorted(name for name, check in checks.items() if not check(section))


def _live_sites() -> dict[str, str]:
    return {"execute.md clause (a)": _clause_a(), "finalize.md escalation hook": _finalize_site()}


def _scoping_is_conjunctive(text: str) -> bool:
    """True only when BOTH run-scoping conjuncts are present AND joined as a
    conjunction. A half-scoped clause is the real hazard, not an absent one:
    plan-membership alone re-fires on a prior run's stale marker, and
    written-after alone fires on another Epic's concurrent marker.
    """
    pi, ti = text.find(_PLAN_CONJUNCT), text.find(_TIME_CONJUNCT)
    if pi < 0 or ti < 0:
        return False
    joiner = text[min(pi + len(_PLAN_CONJUNCT), ti + len(_TIME_CONJUNCT)):max(pi, ti)]
    return bool(re.search(r"\band\b", joiner)) and not re.search(r"\bor\b", joiner)


def _deletion_instructed(block: str, glob: str) -> bool:
    """True when `block` instructs deleting `glob`.

    Scoped to the delete INSTRUCTION, not to a bare substring: the arming block
    may legitimately mention a glob in a clarifying aside ("but not `x`"), and a
    naive substring check would red that correct implementation. A mention counts
    only when a delete verb governs it and no negation sits between the two (or
    ahead of the verb).
    """
    for sentence in _sentences(block):
        for hit in re.finditer(re.escape(glob), sentence):
            head = sentence[:hit.start()]
            verbs = list(re.finditer(r"\bdelet\w*", head, re.I))
            if not verbs:
                continue
            verb = verbs[-1]  # the nearest preceding verb is the one that governs
            if re.search(r"\b(not|never|except)\b", head[verb.end():], re.I):
                continue  # "delete A but not <glob>"
            if re.search(r"\b(not|never)\b", head[:verb.start()], re.I):
                continue  # "do not delete <glob>"
            return True
    return False


# --- AC-1: one dedup marker path, byte-identical at both sites ---------------
def test_both_fire_sites_share_one_dedup_marker_path():
    sites = _live_sites()
    for name, site in sites.items():
        assert _unmet(_FIRE_SITE_CHECKS, site) == [], (
            f"{name} does not honor the fire contract: {_unmet(_FIRE_SITE_CHECKS, site)}"
        )

    # Equality between the two EXTRACTED tokens, so a rename that drifts one
    # site reds even if the new name is otherwise well-formed.
    extracted = [_dedup_tokens(site).pop() for site in sites.values()]
    assert extracted[0] == extracted[1], (
        f"the two sites dedup against different paths: {extracted}"
    )
    assert extracted[0] == _DEDUP_TOKEN

    # And the raw ordering: skip-if-present is stated before the fire at both.
    for name, site in sites.items():
        assert site.index("already present, skip silently") < _fire_offset(site), (
            f"{name} fires before it checks the dedup marker"
        )


# --- AC-2: the scalar ships, defaults empty, and resolves as a scalar --------
def _resolve(engine_tree: Path, key: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(REAL_ENGINE),
         "--skill", str(engine_tree / "skills" / "ultracode-goal"), "--key", key],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_on_escalation_scalar_defaults_empty_and_resolves(tmp_path: Path):
    parsed = tomllib.loads(_CUSTOMIZE.read_text(encoding="utf-8"))
    assert parsed["workflow"]["on_escalation"] == "", (
        "the shipped default must be empty: an unconfigured run fires nothing"
    )
    # positive control on the shape it mirrors, so a customize.toml that lost
    # BOTH hooks reds here rather than passing half of this assertion
    assert parsed["workflow"]["on_epic_complete"] == ""

    # Synthetic three-layer tree driven through the VENDORED engine.
    custom = tmp_path / "_bmad" / "custom"
    custom.mkdir(parents=True)
    skill = tmp_path / "skills" / "ultracode-goal"
    skill.mkdir(parents=True)
    shutil.copy2(_CUSTOMIZE, skill / "customize.toml")

    # base layer alone
    assert _resolve(tmp_path, "workflow.on_escalation") == {"workflow.on_escalation": ""}

    # team layer overrides the empty base, exactly as a scalar must (an array
    # would append across layers and run the team's hook as well as the user's)
    (custom / "ultracode-goal.toml").write_text(
        '[workflow]\non_escalation = "notify-oncall.sh"\n', encoding="utf-8"
    )
    assert _resolve(tmp_path, "workflow.on_escalation") == {
        "workflow.on_escalation": "notify-oncall.sh"
    }

    # and the prose at BOTH sites pins the empty case as a silent no-op, so an
    # empty hook cannot leave a fired-marker that suppresses a later real one
    for name, site in _live_sites().items():
        assert "resolved-empty value is a silent no-op" in site, name
        assert "no fired-marker is written" in site, name


def test_missing_scalar_is_not_silently_tolerated():
    """The key's ABSENCE must be a failure, never a defaulted pass.

    A `.get("on_escalation", "")` in the test above would pass against a
    customize.toml that never declared the key, leaving the feature unreachable
    while every fire-site assertion stayed green. This pins that shut.
    """
    workflow = tomllib.loads(_CUSTOMIZE.read_text(encoding="utf-8"))["workflow"]
    try:
        value = workflow["on_escalation"]
    except KeyError:  # pragma: no cover - the failure this test exists to force
        raise AssertionError(
            "customize.toml's [workflow] table declares no `on_escalation` key; "
            "the hook is unreachable no matter what the fire sites say"
        )
    assert value == ""

    # the mutation, applied: strip the key and confirm subscripting raises,
    # while the tempting defaulted form would have waved it through
    mutant = {k: v for k, v in workflow.items() if k != "on_escalation"}
    with pytest.raises(KeyError):
        mutant["on_escalation"]
    assert mutant.get("on_escalation", "") == "", (
        "the defaulted form passes against a stripped table: that is the vacuous "
        "shape this test refuses to use"
    )


# --- AC-3: the turn-budget marker reaches the hook, promoted first -----------
def _hook_marker_affixes() -> tuple[str, str]:
    """The marker filename budget_stop.py ACTUALLY writes, read from its source."""
    src = _HOOK.read_text(encoding="utf-8")
    match = re.search(r'marker\s*=\s*impl\s*/\s*f"([^"]+)"', src)
    assert match, "budget_stop.py no longer writes a marker under a recognizable name"
    template = match.group(1)
    assert "{story}" in template, f"unexpected marker template {template!r}"
    prefix, suffix = template.split("{story}", 1)
    return prefix, suffix


def test_budget_escalation_reaches_the_hook():
    prefix, suffix = _hook_marker_affixes()
    assert (prefix, suffix) == (".escalation-", ".md"), (
        "control: the hook's dotted markdown marker is the in-scope trigger"
    )

    clause = _clause_a()
    pattern = re.escape(prefix) + r"[^\s`]*" + re.escape(suffix)
    assert re.search(pattern, clause), (
        f"clause (a) names no marker matching what the Stop hook writes ({prefix}…{suffix}); "
        "a writer/reader rename on either side must red here"
    )

    # promotion is ordered before the fire, so a hook that reads the sidecar
    # finds it already on disk
    assert clause.index("promote it to the typed sidecar") < _fire_offset(clause)

    # and the Stop hook stays a recorder: it never resolves or fires this hook
    src = _HOOK.read_text(encoding="utf-8")
    assert 'f".escalation-{story}.md"' in src, "control: the hook still writes its marker"
    for forbidden in ("on_escalation", "resolve_customization", ".on-escalation-fired-"):
        assert forbidden not in src, (
            f"the Stop hook must never fire the escalation hook; found {forbidden!r}. "
            "A Stop hook fires while Claude is already stopping, cannot block, and has "
            "no config resolver in scope"
        )


def test_promotion_precedes_the_fire_in_clause_a():
    """The reordered form must red HERE and nowhere else in this module."""
    clause = _clause_a()
    # the live ordering, asserted on the shipped clause: promotion first, so a
    # shell-form hook reading the sidecar off disk finds it already written
    assert clause.index("promote it to the typed sidecar") < _fire_offset(clause), (
        "clause (a) fires before it promotes the marker; a hook that reads the "
        "typed sidecar would find nothing there"
    )

    sentence = (
        "On the first in-scope marker, promote it to the typed sidecar "
        "`{workflow.implementation_artifacts}/escalation-<story_id>.json` "
        '(see "Escalation sidecar" below) before firing anything, so a hook that '
        "reads the sidecar finds it already on disk."
    )
    assert sentence in clause, "the promotion sentence moved; this twin would be vacuous"

    mutant = clause.replace(sentence + " ", "") + " " + sentence
    assert mutant != clause, "mutation did not apply"

    # the ordering assertion reds ...
    assert mutant.index("promote it to the typed sidecar") > _fire_offset(mutant)
    # ... while every other bound property stays green, so the red is
    # attributable to the ordering alone
    assert _unmet(_FIRE_SITE_CHECKS, mutant) == []
    assert re.search(re.escape(".escalation-") + r"[^\s`]*" + re.escape(".md"), mutant)


# --- AC-4 (twin): the pre-edit sites fail every fire assertion ---------------
def test_pre_edit_site_fixtures_lack_the_escalation_fire():
    for fixture in (_FIX_FINALIZE, _FIX_EXECUTE):
        blob = fixture.read_text(encoding="utf-8")
        unmet = _unmet(_FIRE_SITE_CHECKS, blob)
        assert unmet == sorted(_FIRE_SITE_CHECKS), (
            f"{fixture.name} already satisfies part of the fire contract: "
            f"met {sorted(set(_FIRE_SITE_CHECKS) - set(unmet))}"
        )


def test_second_site_is_suppressed_not_duplicated():
    """Neither site fires unconditionally, so two active sites cannot both fire."""
    for name, site in _live_sites().items():
        fire = _fire_offset(site)
        assert fire > 0, name
        absent = site.index("If it is absent")
        present = site.index("already present, skip silently")
        assert present < absent < fire, (
            f"{name}'s fire is not inside a marker-absent condition "
            f"(present={present}, absent={absent}, fire={fire})"
        )
        # the fire sentence is the one guarded by that condition, not a later
        # unguarded restatement
        assert site.count("--key workflow.on_escalation") == 1, (
            f"{name} names the resolve more than once; only one can be the guarded fire"
        )


def test_pre_edit_fixtures_differ_only_by_the_escalation_clause():
    """The twins must red for the RIGHT reason: an emptied fixture proves nothing."""
    finalize = _FIX_FINALIZE.read_text(encoding="utf-8")
    assert "only when the Epic-level gate verdict was `advance`" in finalize
    assert (
        "resolve_customization.py --skill {skill-root} --key workflow.on_epic_complete"
        in finalize
    ), "the finalize fixture must still carry the epic-complete resolve verbatim"

    execute = _FIX_EXECUTE.read_text(encoding="utf-8")
    assert (
        "proceed to Stage 5 for the deterministic per-story and epic-level gate" in execute
    ), "the execute fixture must still carry the post-spine sentence it snapshots"

    # and each fixture is a real prefix of what shipped, not a rewrite
    assert "## Epic-complete hook" in _FINALIZE.read_text(encoding="utf-8")
    assert execute.strip() in _clause_a()


# --- AC-5: run scoping, purge at one end and read-time scan at the other ----
def test_preflight_step5_purges_stale_escalation_artifacts():
    block = _step5()
    for glob in _PURGED_GLOBS:
        assert _deletion_instructed(block, glob), (
            f"step 5 must delete stale `{glob}` when arming: a leftover marker makes "
            "this run look like it already escalated, or swallows its first ping"
        )
    assert not _deletion_instructed(block, _UNPURGED_GLOB), (
        "step 5 must NOT purge the typed sidecar. It is named per story, not per run, "
        "so arming cannot tell a deliberately-pending decision from a stale one, and "
        "deleting it destroys a decision the operator chose to leave open"
    )
    # the assertion above is on the delete instruction, not the bare substring:
    # a clarifying aside naming the glob is correct prose and must stay green
    aside = "Delete `.escalation-*`. In particular do **not** delete `escalation-*.json`."
    assert _deletion_instructed(aside, ".escalation-*")
    assert not _deletion_instructed(aside, _UNPURGED_GLOB)
    # and the naive form this replaces would have failed that correct prose
    assert _UNPURGED_GLOB in aside


def test_execute_clause_a_is_run_scoped_by_plan_and_time():
    assert _scoping_is_conjunctive(_clause_a()), (
        "clause (a) must scope its marker scan by plan membership AND write time, "
        "joined as a conjunction"
    )


def test_pre_edit_step5_fixture_lacks_the_purge():
    fixture = _FIX_STEP5.read_text(encoding="utf-8")
    for glob in _PURGED_GLOBS:
        assert not _deletion_instructed(fixture, glob), (
            f"the pre-edit arming block already purges `{glob}`; this twin is vacuous"
        )
    # co-assertion: it is a real snapshot of that block, not an empty file that
    # trivially lacks the purge
    assert "Inject the hook env" in fixture, "the fixture must be the same section"
    assert len(_hook_env_entries(fixture)) == 5, (
        "the fixture must still list the pre-existing hook-env injections"
    )
    # and the live block still lists them too, so the purge was added, not swapped in
    assert len(_hook_env_entries(_step5())) == 5


def test_single_conjunct_scoping_forms_are_rejected():
    """AC-5's green cannot be bought with half the scoping."""
    plan_only = f"a marker is in scope when it {_PLAN_CONJUNCT}."
    time_only = f"a marker is in scope when it {_TIME_CONJUNCT}."
    disjunctive = f"a marker is in scope when it {_PLAN_CONJUNCT} or {_TIME_CONJUNCT}."
    for form in (plan_only, time_only, disjunctive):
        assert not _scoping_is_conjunctive(form), f"half-scoped form accepted: {form!r}"

    # positive control: the matcher is not a blanket reject
    assert _scoping_is_conjunctive(
        f"a marker is in scope when it {_PLAN_CONJUNCT} and {_TIME_CONJUNCT}."
    )
