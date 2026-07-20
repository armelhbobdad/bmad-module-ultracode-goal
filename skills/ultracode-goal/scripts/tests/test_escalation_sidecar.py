"""The typed escalation sidecar: one shape, one promoter, zero envelope leakage.

Static prose-contract assertions over execute.md's '### Escalation sidecar'
section and gate.md's escalate route (the sidecar is a single JSON object with
exactly four string fields; `kind` is open vocabulary; the turn-budget markdown
is promoted by Execute alone and left in place), plus `ast`-level NEGATIVE
assertions over the real shipped `hooks/budget_stop.py` (no sidecar emission, no
process launch) and a direct call into the headless adapter (the sidecar is a
file on disk, never an envelope key).

Follows the prose-contract pattern of test_execute_baseline_marker.py and
test_run_status_heartbeat.py: module-level `_SKILL_ROOT`, a section-slicing
helper, named-check dicts so a twin can assert which assertion reds, and
assertions against the shipped source rather than a copy. Anti-vacuous twins are
applied inline as mutations of the shipped text. Stdlib + pytest only.
"""

import ast
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_GATE = _SKILL_ROOT / "references" / "gate.md"
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_HOOK = _SKILL_ROOT / "scripts" / "hooks" / "budget_stop.py"
_ENVELOPE = _SKILL_ROOT / "scripts" / "headless_envelope.py"
_SCHEMA_TEST = Path(__file__).resolve().parent / "test_headless_envelope_schema.py"

_HEADING = "### Escalation sidecar"
_SIDECAR_PATH = "escalation-<story_id>.json"
_SIDECAR_FIELDS = ("source", "kind", "decision_needed", "evidence")

# The canonical headless envelope: five always-present keys, `reason` conditional.
_CANONICAL_KEYS = {"status", "skill", "decision_log", "report", "deferred_work"}

# The semantic scan's red-kind vocabulary. It is a planning-artifact taxonomy and
# must never travel to an escalation surface as a whitelist for the sidecar's `kind`.
_PREFLIGHT_ENUM = "undecided-product|undecided-architecture|contradiction|undefinable-done"

# Where that literal legitimately lives: the semantic-scan return object, declared
# once in preflight.md and mirrored verbatim by the formalize sub-skill that runs the
# SAME scan (ucg-formalize/SKILL.md calls it "the live three-key contract the parent
# references/preflight.md semantic scan uses"), plus the two fixtures that pin those
# mirrors verbatim -- the second being the pre-edit copy of preflight's step-3 section,
# which carries the enum only because it is a byte-for-byte capture of the section that
# declares it. Every extra site is the SAME declaration, so they are enumerated rather
# than silently tolerated -- the exact-set assertion below still reds the moment a new
# site imports the literal as its own vocabulary.
_ENUM_HOMES = {
    "references/preflight.md",
    "skills/ucg-formalize/SKILL.md",
    "scripts/tests/fixtures/ucg_formalize/subagent_two_key_contract.txt",
    "scripts/tests/fixtures/preflight_step3_no_decisions_override.md",
}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


he = _load(_ENVELOPE, "headless_envelope")


def _section(text: str | None = None) -> str:
    """Slice the '### Escalation sidecar' section (to the next heading or EOF)."""
    text = text if text is not None else _EXECUTE.read_text(encoding="utf-8")
    start = text.index(_HEADING)
    nxt = re.search(r"\n#{2,3} ", text[start + len(_HEADING):])
    return text[start:] if nxt is None else text[start:start + len(_HEADING) + nxt.start()]


def _halt_catchall(text: str | None = None) -> str:
    """Execute's sub-skill halt catch-all paragraph."""
    text = text if text is not None else _EXECUTE.read_text(encoding="utf-8")
    hits = [ln for ln in text.splitlines() if ln.startswith("**Sub-skill halt catch-all.**")]
    assert len(hits) == 1, f"expected exactly one halt catch-all, got {len(hits)}"
    return hits[0]


def _gate_escalate_route(text: str | None = None) -> str:
    """gate.md's escalate bullet plus its sub-skill-halt sentence, as one blob."""
    text = text if text is not None else _GATE.read_text(encoding="utf-8")
    bullet = [ln for ln in text.splitlines() if ln.startswith("- **`escalate`**")]
    assert len(bullet) == 1, f"expected exactly one escalate bullet, got {len(bullet)}"
    halt = [
        ln
        for ln in text.splitlines()
        if ln.startswith("If any orchestrated sub-skill blocks on interactive input")
    ]
    assert len(halt) == 1, f"expected exactly one gate halt sentence, got {len(halt)}"
    return bullet[0] + "\n" + halt[0]


def _fenced_json(section: str) -> dict:
    """Parse THE one fenced json block in the section; assert there is exactly one."""
    blocks = re.findall(r"```json\n(.*?)\n```", section, re.S)
    assert len(blocks) == 1, f"the section must carry exactly one fenced json block, got {len(blocks)}"
    parsed = json.loads(blocks[0])
    assert isinstance(parsed, dict), "the sidecar is one object, not an array"
    return parsed


def _envelope_keys_ok(env: dict) -> bool:
    """True iff `env` is the canonical envelope key set: the five plus at most `reason`.

    One helper serves both directions -- the real envelope must pass it and a
    leaked-field envelope must fail it -- so neither a leaked sidecar field nor a
    wave-everything-through helper can hide behind the other.
    """
    keys = set(env)
    return _CANONICAL_KEYS <= keys <= (_CANONICAL_KEYS | {"reason"})


def _rel_paths_containing(needle: str) -> set[str]:
    """Every shipped-tree file carrying `needle`, as skill-root-relative posix paths."""
    hits: set[str] = set()
    for path in _SKILL_ROOT.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or ".analysis" in path.parts:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue  # this module names the literal in order to police it
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if needle in text:
            hits.add(path.relative_to(_SKILL_ROOT).as_posix())
    return hits


# --- named-check dicts: one entry per bound property, so a twin can name what reds.

_SIDECAR_SHAPE_CHECKS = {
    "names the typed sidecar path": lambda s: _SIDECAR_PATH in s,
    "roots it at the impl-artifacts dir": lambda s: "{workflow.implementation_artifacts}/" + _SIDECAR_PATH in s,
    "carries exactly one parseable fenced json block": lambda s: bool(_fenced_json(s)),
    "block key set is exactly the four fields": lambda s: set(_fenced_json(s)) == set(_SIDECAR_FIELDS),
    "all four values are strings": lambda s: all(isinstance(v, str) for v in _fenced_json(s).values()),
    "states it is one object, not an array": lambda s: bool(
        re.search(r"one object, never an array", s, re.I)
    ),
}

_OPEN_VOCAB_CHECKS = {
    "declares kind open vocabulary": lambda s: bool(re.search(r"`kind` is \*\*open vocabulary\*\*", s)),
    "rules out validating against a fixed list": lambda s: bool(
        re.search(r"never validates it against a fixed list", s, re.I)
    ),
    "points at the scan vocabulary it must not import": lambda s: bool(
        re.search(r"red-kind vocabulary .*? `references/preflight\.md`", s, re.S)
    ),
    "names budget-overrun as a live kind": lambda s: "`budget-overrun` is a live `kind`" in s,
    "places budget-overrun outside that vocabulary": lambda s: bool(
        re.search(r"outside that vocabulary", s, re.I)
    ),
}

_PROMOTION_CHECKS = {
    "pins the trigger to /goal returning": lambda s: bool(
        re.search(r"after `/goal` returns", s, re.I)
    ),
    "names the hook's dotted markdown as the input": lambda s: ".escalation-<story_id>.md" in s,
    "maps source to the markdown's path": lambda s: bool(
        re.search(r"`source` to that markdown's path", s)
    ),
    "maps kind to budget-overrun": lambda s: bool(
        re.search(r"`kind` to `budget-overrun`", s)
    ),
    "maps decision_needed to the human decision": lambda s: bool(
        re.search(r"`decision_needed` to the human decision .*?re-scope, split, or hand off", s, re.S)
    ),
    "maps evidence to one quoted line": lambda s: bool(
        re.search(r"`evidence` to one line quoted from the marker", s)
    ),
    "leaves the markdown in place": lambda s: bool(
        re.search(r"never delete it, never rewrite it", s, re.I)
    ),
    "says why leaving it matters": lambda s: bool(
        re.search(r"only evidence that an escalation happened", s, re.I)
    ),
    "names Execute the sole promoter": lambda s: bool(
        re.search(r"Execute is the sole promoter", s)
    ),
    "keeps the Stop hook a recorder that emits no JSON": lambda s: bool(
        re.search(r"stays a recorder: it emits no JSON and starts no process", s)
    ),
}


def _unmet(checks: dict, section: str) -> list[str]:
    return sorted(name for name, check in checks.items() if not check(section))


# --- the typed shape, named by every escalation route ------------------------
def test_execute_pins_typed_sidecar_four_fields():
    section = _section()
    assert _unmet(_SIDECAR_SHAPE_CHECKS, section) == [], (
        f"sidecar shape unmet: {_unmet(_SIDECAR_SHAPE_CHECKS, section)}"
    )
    # exact equality, not containment: a fifth field is a contract change
    assert set(_fenced_json(section)) == set(_SIDECAR_FIELDS)

    # every escalation route names the ONE file, so none can leave an untyped
    # marker as the only record
    for name, blob in (
        ("execute.md's sub-skill halt catch-all", _halt_catchall()),
        ("gate.md's escalate route", _gate_escalate_route()),
    ):
        assert _SIDECAR_PATH in blob, f"{name} does not name the typed sidecar"
        assert not re.search(r"write the escalation marker", blob), (
            f"{name} still routes to a bare untyped 'escalation marker'"
        )

    # anti-vacuous twin: drop `evidence` from the fenced block, leaving the
    # section otherwise byte-identical. The key-set equality reds; the two
    # positive controls (one parseable block, the path still named) stay green,
    # so the red is attributable to the missing field alone.
    mutant = section.replace(',\n "evidence": "<one quoted line supporting it>"', "")
    assert mutant != section, "mutation did not apply; the twin would be vacuous"
    unmet = _unmet(_SIDECAR_SHAPE_CHECKS, mutant)
    assert unmet == ["block key set is exactly the four fields"], (
        f"deleting `evidence` must red exactly the key-set check, got {unmet}"
    )


# --- `kind` is open vocabulary, and the scan enum stays home -----------------
def test_kind_is_open_vocabulary_not_preflight_enum():
    section = _section()
    assert _unmet(_OPEN_VOCAB_CHECKS, section) == [], (
        f"open-vocabulary rule unmet: {_unmet(_OPEN_VOCAB_CHECKS, section)}"
    )

    # locality: the pipe-joined scan enum lives only at its declaration sites.
    # Positive control first -- a test that stopped finding it anywhere (renamed
    # enum, unreadable tree) must fail loudly rather than pass vacuously.
    homes = _rel_paths_containing(_PREFLIGHT_ENUM)
    assert "references/preflight.md" in homes, (
        "the scan enum must still be declared in its native home; if it is not, "
        "this locality assertion is measuring nothing"
    )
    assert homes == _ENUM_HOMES, (
        f"the scan enum literal escaped its declaration sites: {sorted(homes - _ENUM_HOMES)}"
    )
    # and, said directly: no escalation surface carries it
    for surface in (_EXECUTE, _GATE):
        assert _PREFLIGHT_ENUM not in surface.read_text(encoding="utf-8"), (
            f"{surface.name} imported the scan enum as a whitelist for `kind`"
        )

    # anti-vacuous twin: paste the enum into the sidecar block as the `kind`
    # value (the shape a copy-paste from the scan's return object takes). The
    # locality assertion reds naming execute.md.
    mutant_text = _EXECUTE.read_text(encoding="utf-8").replace(
        '"kind": "<short slug naming the escalation\'s origin>"',
        f'"kind": "{_PREFLIGHT_ENUM}"',
    )
    assert _PREFLIGHT_ENUM in mutant_text, "mutation did not apply; the twin would be vacuous"
    assert _PREFLIGHT_ENUM in _PREFLIGHT.read_text(encoding="utf-8"), "positive control holds"
    mutant_homes = _ENUM_HOMES | {"references/execute.md"}
    assert mutant_homes != _ENUM_HOMES and mutant_homes - _ENUM_HOMES == {"references/execute.md"}


# --- promotion: Execute alone, markdown left in place ------------------------
def test_budget_marker_promoted_by_execute_only():
    section = _section()
    assert _unmet(_PROMOTION_CHECKS, section) == [], (
        f"promotion recipe unmet: {_unmet(_PROMOTION_CHECKS, section)}"
    )

    # anti-vacuous twin: the tempting "clean up after yourself" edit -- say the
    # markdown is deleted once promoted. Only the leave-in-place clauses red;
    # the trigger, the four mapped values and the sole-promoter statement stay
    # green, so the red is attributable to that clause alone.
    mutant = section.replace(
        "**Leave the markdown in place — never delete it, never rewrite it.** It is the "
        "residual that survives a session which died between the hook's write and this "
        "promotion, so consuming it would destroy the only evidence that an escalation "
        "happened at all.",
        "**Delete the markdown once it has been promoted.**",
    )
    assert mutant != section, "mutation did not apply; the twin would be vacuous"
    assert _unmet(_PROMOTION_CHECKS, mutant) == [
        "leaves the markdown in place",
        "says why leaving it matters",
    ]


def test_promotion_mapping_matches_real_hook_output(tmp_path: Path):
    """The mapping the prose pins is derivable from the hook's REAL output."""
    impl = tmp_path / "impl"
    impl.mkdir()
    env_extra = {
        "ULTRACODE_IMPL_ARTIFACTS": str(impl),
        "ULTRACODE_STORY_ID": "S1",
        "ULTRACODE_MAX_TURNS": "2",
    }
    import os

    def _run() -> int:
        proc = subprocess.run(
            [sys.executable, str(_HOOK)],
            input=json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)}),
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env={**os.environ, **env_extra},
        )
        return proc.returncode

    assert _run() == 0
    assert _run() == 0  # second Stop crosses the ceiling

    marker = impl / ".escalation-S1.md"
    assert marker.is_file(), "the hook must really write the dotted markdown marker"

    # `source` is that markdown's path -- a real file the promotion can name
    assert marker.name == ".escalation-S1.md"

    body = marker.read_text(encoding="utf-8")
    quotable = [
        ln
        for ln in body.splitlines()
        if re.search(r"turns \d+/\d+", ln)
        and all(t in ln for t in ("re-scope", "split", "hand off"))
    ]
    assert len(quotable) == 1, (
        "the marker must carry exactly one line naming the turn count AND the "
        f"re-scope/split/hand-off decision, so `evidence` has something to quote; got {quotable}"
    )
    # and the hook emitted no typed sidecar of its own
    assert not list(impl.glob("escalation-*.json")), (
        "promotion is Execute's job; the hook must not have written the typed sidecar"
    )


# --- the envelope is untouched by the sidecar --------------------------------
def test_envelope_unchanged_by_sidecar(tmp_path: Path):
    log = tmp_path / "dl.md"
    blockers = [
        {
            "source": "prd.md:42",
            "kind": "budget-overrun",
            "decision_needed": "re-scope, split, or hand off",
            "evidence": "Story turn budget exceeded (turns 26/25).",
        }
    ]
    env = he.build_headless_envelope(blockers, str(log))
    assert set(env) == _CANONICAL_KEYS | {"reason"}, (
        f"the envelope grew keys: {sorted(set(env) - (_CANONICAL_KEYS | {'reason'}))}"
    )
    for field in _SIDECAR_FIELDS:
        assert field not in env, f"sidecar field {field!r} leaked onto the envelope"
    assert _envelope_keys_ok(env), "the real envelope must pass the shared key-set helper"
    # the blocker fields did reach the adapter -- so the absence above is a real
    # boundary, not an input that never carried them
    assert "prd.md:42" in env["reason"] and "re-scope" in env["reason"]

    # control: this story added no second envelope key set anywhere in the tree
    schema = _load(_SCHEMA_TEST, "test_headless_envelope_schema")
    schema.test_single_envelope_definition()


# --- twin: a leaked sidecar field fails the same key-set helper --------------
def test_leaked_sidecar_field_fails_envelope_schema(tmp_path: Path):
    log = tmp_path / "dl.md"
    env = he.build_headless_envelope(
        [{"source": "prd.md:42", "decision_needed": "pick one"}], str(log)
    )
    # True branch: the unmutated envelope passes, so a blanket-False helper
    # (the way this twin could red for the wrong reason) is pinned shut.
    assert _envelope_keys_ok(env) is True

    for field in _SIDECAR_FIELDS:
        leaked = {**env, field: "budget-overrun"}
        assert _envelope_keys_ok(leaked) is False, (
            f"an envelope leaking {field!r} must be rejected by the same helper"
        )
    # and a dropped canonical key is rejected too, so the helper is not merely
    # a superset check
    assert _envelope_keys_ok({k: v for k, v in env.items() if k != "status"}) is False


# --- source-level negatives over the real shipped Stop hook ------------------
def _docstring_node_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def test_budget_stop_emits_no_typed_sidecar_and_fires_nothing():
    src = _HOOK.read_text(encoding="utf-8")
    tree = ast.parse(src)  # positive control: the module must still parse

    # positive controls pinning the file's identity, so an emptied, truncated or
    # renamed hook shows up as a CONTROL failure, not as a negative that passed
    assert 'f".escalation-{story}.md"' in src, "the hook must still write its markdown marker"
    assert "ULTRACODE_MAX_TURNS" in src, "the hook must still read its turn ceiling"

    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    assert roots <= {"json", "os", "sys", "pathlib", "typing"}, (
        f"the Stop hook grew an import it has no business holding: {sorted(roots - {'json', 'os', 'sys', 'pathlib', 'typing'})}"
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            assert not (attr in ("system", "popen") or attr.startswith("exec")), (
                f"the Stop hook must launch no process; found a call to .{attr}()"
            )

    doc_ids = _docstring_node_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Constant, ast.JoinedStr)) and id(node) not in doc_ids:
            if isinstance(node, ast.Constant) and not isinstance(node.value, str):
                continue
            literal = ast.unparse(node)
            assert not ("escalation-" in literal and ".json" in literal), (
                f"the Stop hook must emit no typed sidecar; found literal {literal!r}"
            )

    assert "on_escalation" not in src, (
        "any escalation lifecycle hook lives outside the Stop hook"
    )
