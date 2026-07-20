"""Run-status heartbeat: the additive snapshot keys and their provenance.

Static prose-contract assertions over execute.md's '## Run-status heartbeat'
section: the snapshot documents `last_reasons`, `stories[]` and `budget_used`
on top of the eight pre-existing keys; `budget_used` is turns-only with two
named sources; the hook state file wins a disagreement with the prior snapshot;
and an absent hook file renders zero turns rather than skipping the write. The
verbatim pre-edit section is kept under fixtures/ as the anti-vacuous twin
(mirroring how fixtures/execute_step0_baseline_no_sha.md is used in
test_execute_baseline_marker.py). finalize.md's inline restatement of the same
shape is held to the same key set by one matcher applied to both sites.

The fenced block is deliberately NOT valid JSON — it mixes quoted placeholders
("<epic id>") with unquoted ones (<in-scope story count>) — so keys are scanned
out by brace depth rather than parsed. Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_FINALIZE = _SKILL_ROOT / "references" / "finalize.md"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_PRE_EDIT = _FIXTURES / "execute_run_status_preedit.md"

_HEADING = "## Run-status heartbeat"

# The shape finalize.md restated before this edit, kept as the AC-6 twin: the
# default outcome of editing execute.md alone is finalize still listing these.
_PRE_EDIT_FINALIZE_KEYS = {
    "epic",
    "story",
    "index",
    "total",
    "last_verdict",
    "reloop_count",
    "profile",
    "updated",
}

# No token or cost dimension: the budget is turns-only, and this section must
# not be where a second one creeps back in.
_BUDGET_VOCAB = re.compile(r"token|cost|\$|story_token_budget", re.I)


def _section(text: str | None = None) -> str:
    """Slice the '## Run-status heartbeat' section (to the next '##' or EOF)."""
    text = text if text is not None else _EXECUTE.read_text(encoding="utf-8")
    start = text.index(_HEADING)
    nxt = text.find("\n## ", start + len(_HEADING))
    return text[start:] if nxt == -1 else text[start:nxt]


def _preedit_section() -> str:
    return _section(_PRE_EDIT.read_text(encoding="utf-8"))


def _fenced_block(section: str) -> str:
    m = re.search(r"```json\n(.*?)\n```", section, re.S)
    assert m, "the section must carry one fenced json snapshot block"
    return m.group(1)


def _entries(blob: str) -> dict[str, str]:
    """Map `"key": value-text` at the outermost brace/bracket depth of `blob`.

    Scans rather than parses: the block is not valid JSON. Quoted strings are
    tracked so a comma inside a placeholder ("<advance|defer, or null…>") is
    not mistaken for an entry separator.
    """
    depth = 0
    in_str = False
    buf: list[str] = []
    parts: list[str] = []
    for ch in blob:
        if in_str:
            buf.append(ch)
            if ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            buf.append(ch)
            continue
        if ch in "{[":
            depth += 1
            if depth == 1:
                buf = []
            else:
                buf.append(ch)
            continue
        if ch in "}]":
            if depth == 1:
                parts.append("".join(buf))
                buf = []
            depth -= 1
            if depth >= 1:
                buf.append(ch)
            continue
        if ch == "," and depth == 1:
            parts.append("".join(buf))
            buf = []
            continue
        if depth >= 1:
            buf.append(ch)
    out: dict[str, str] = {}
    for part in parts:
        m = re.match(r'\s*"([^"]+)"\s*:\s*(.*)', part, re.S)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _top_keys(section: str) -> dict[str, str]:
    return _entries(_fenced_block(section))


def _nested(section: str, key: str) -> dict[str, str]:
    """Entries of a nested object value, unwrapping a one-entry array if present."""
    val = _top_keys(section).get(key)
    if val is None:
        return {}
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        val = val[1:-1].strip()
    return _entries(val)


def _sentences(section: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=\.)\s+", section) if s.strip()]


def _reconciliation_sentence(section: str) -> str | None:
    """The single sentence stating who wins when the two counters disagree."""
    hits = [
        s
        for s in _sentences(section)
        if re.search(r"disagree", s, re.I) and ".budget-<story>.json" in s
    ]
    return hits[0] if len(hits) == 1 else None


# --- named-check dicts: one entry per bound property, so a twin can assert that
# --- *every* one of them reds (not merely that something raised).

_ADDITIVE_CHECKS = {
    "declares last_reasons": lambda s: "last_reasons" in _top_keys(s),
    "declares stories": lambda s: "stories" in _top_keys(s),
    "declares budget_used": lambda s: "budget_used" in _top_keys(s),
    "stories entry carries phase": lambda s: "phase" in _nested(s, "stories"),
    "stories entry carries verdict": lambda s: "verdict" in _nested(s, "stories"),
    "stories entry carries dev_attempts": lambda s: "dev_attempts" in _nested(s, "stories"),
    "stories entry carries reloop_count": lambda s: "reloop_count" in _nested(s, "stories"),
}

_BUDGET_CHECKS = {
    "names the hook state file as the turns source": lambda s: ".budget-<story>.json" in s,
    "names the resolved max-turns scalar": lambda s: "{workflow.max_turns_per_story}" in s,
    "budget_used is exactly turns + max_turns": lambda s: set(_nested(s, "budget_used"))
    == {"turns", "max_turns"},
    "carries no token or cost vocabulary": lambda s: not _BUDGET_VOCAB.search(s),
}

_RECONCILE_CHECKS = {
    "has exactly one reconciliation sentence": lambda s: _reconciliation_sentence(s) is not None,
    "names the prior snapshot value": lambda s: bool(
        re.search(r"prior snapshot.*budget_used\.turns", _reconciliation_sentence(s) or "", re.S | re.I)
    ),
    "names the hook state file in the same sentence": lambda s: ".budget-<story>.json"
    in (_reconciliation_sentence(s) or ""),
    "pins the hook file as the winner": lambda s: bool(
        re.search(r"hook file wins", _reconciliation_sentence(s) or "", re.I)
    ),
    "states re-read on every write": lambda s: bool(
        re.search(r"re-?read it on every write", _reconciliation_sentence(s) or "", re.I)
    ),
    "rules out carry-forward": lambda s: bool(
        re.search(r"never carry .*? forward", _reconciliation_sentence(s) or "", re.S | re.I)
    ),
}

_ABSENT_FILE_CHECKS = {
    "states the absent-hook-file case": lambda s: bool(
        re.search(r"no `\.budget-<story>\.json` exists yet", s, re.I)
    ),
    "renders zero turns with max_turns populated": lambda s: bool(
        re.search(r'\{"turns": 0, "max_turns": <[^>]+>\}', s)
    ),
    "says the write still proceeds": lambda s: bool(
        re.search(r"write the snapshot anyway", s, re.I)
    ),
    "rules out skipping or a partial write": lambda s: bool(
        re.search(r"never a reason to skip the write, defer it, or leave", s, re.I)
    ),
}


def _unmet(checks: dict, section: str) -> list[str]:
    return sorted(name for name, check in checks.items() if not check(section))


def _finalize_section() -> str:
    text = _FINALIZE.read_text(encoding="utf-8")
    start = text.index("## Record the terminal run-status")
    nxt = text.find("\n## ", start + 10)
    return text[start:] if nxt == -1 else text[start:nxt]


def _finalize_shape_keys(section: str | None = None) -> set[str]:
    section = section if section is not None else _finalize_section()
    m = re.search(r"shape:\s*`\{([^}]*)\}`", section)
    assert m, "finalize must restate the snapshot shape as an inline `{…}` list"
    return {k.strip() for k in m.group(1).split(",") if k.strip()}


def test_heartbeat_block_declares_the_three_additive_keys():
    section = _section()
    assert _unmet(_ADDITIVE_CHECKS, section) == [], (
        f"heartbeat block does not declare: {_unmet(_ADDITIVE_CHECKS, section)}"
    )
    # the pre-existing write semantics survive the extension: same single
    # overwrite-in-place snapshot, same cadence, not an append log
    assert re.search(r"Overwrite it in place", section), "the snapshot is overwritten in place"
    assert "it is a single live snapshot, not an append log" in section
    assert re.search(
        r"each time you move to a new story, log a gate verdict, or spend a re-loop", section
    ), "the additive keys ride the existing write cadence, not a new trigger"


def test_budget_used_is_turns_and_max_turns_only():
    section = _section()
    assert _unmet(_BUDGET_CHECKS, section) == [], (
        f"budget_used contract unmet: {_unmet(_BUDGET_CHECKS, section)}"
    )
    # anti-vacuous: documenting a third sub-key reds both the exact-key-set
    # check and the vocabulary check, and reds for that alone
    mutant = section.replace(
        '"max_turns": <the resolved per-story turn ceiling>}',
        '"max_turns": <the resolved per-story turn ceiling>, "tokens": <tokens spent>}',
    )
    assert mutant != section, "mutation did not apply; the twin would be vacuous"
    assert _unmet(_BUDGET_CHECKS, mutant) == [
        "budget_used is exactly turns + max_turns",
        "carries no token or cost vocabulary",
    ]
    assert _unmet(_ADDITIVE_CHECKS, mutant) == [], "the third sub-key must not red the key list"


def test_budget_used_prefers_hook_file():
    section = _section()
    assert _unmet(_RECONCILE_CHECKS, section) == [], (
        f"reconciliation rule unmet: {_unmet(_RECONCILE_CHECKS, section)}"
    )
    # anti-vacuous: deleting that one sentence reds every check above
    sentence = _reconciliation_sentence(section)
    assert sentence is not None
    without = section.replace(sentence, "")
    assert _unmet(_RECONCILE_CHECKS, without) == sorted(_RECONCILE_CHECKS)


def test_reconciliation_sentence_is_the_only_sentence_removed():
    """Twin integrity: the sentence carries the rule and nothing else, so its
    removal cannot red the additive-key, budget-shape or absent-file checks."""
    section = _section()
    sentence = _reconciliation_sentence(section)
    assert sentence is not None
    assert sentence.endswith("."), "must be one self-contained sentence"
    # it carries neither the key list nor the absent-file default
    for foreign in ("last_reasons", "stories", "dev_attempts", '"turns": 0'):
        assert foreign not in sentence, f"reconciliation sentence also carries {foreign!r}"
    without = section.replace(sentence, "")
    assert _unmet(_ADDITIVE_CHECKS, without) == []
    assert _unmet(_BUDGET_CHECKS, without) == []
    assert _unmet(_ABSENT_FILE_CHECKS, without) == []


def test_budget_used_defaults_to_zero_turns_when_no_hook_file():
    section = _section()
    assert _unmet(_ABSENT_FILE_CHECKS, section) == [], (
        f"absent-hook-file case unmet: {_unmet(_ABSENT_FILE_CHECKS, section)}"
    )
    # anti-vacuous: omitting the key instead of rendering zero turns reds this
    # check alone -- the shape and the reconciliation rule stay green
    mutant = section.replace(
        'render `budget_used` as `{"turns": 0, "max_turns": <the resolved ceiling>}` and write '
        "the snapshot anyway",
        "omit the `budget_used` key entirely",
    )
    assert mutant != section, "mutation did not apply; the twin would be vacuous"
    assert "renders zero turns with max_turns populated" in _unmet(_ABSENT_FILE_CHECKS, mutant)
    assert _unmet(_BUDGET_CHECKS, mutant) == []
    assert _unmet(_RECONCILE_CHECKS, mutant) == []


def test_preexisting_keys_survive_byte_identical():
    shipped = _top_keys(_section())
    pre_edit = _top_keys(_preedit_section())
    assert set(pre_edit) <= set(shipped), (
        f"pre-existing keys lost: {sorted(set(pre_edit) - set(shipped))}"
    )
    for key, value in pre_edit.items():
        assert shipped[key] == value, f"{key} value text changed: {value!r} -> {shipped[key]!r}"
    assert set(shipped) - set(pre_edit) == {"last_reasons", "stories", "budget_used"}
    # anti-vacuous: renaming the run-scoped reloop_count (the tempting edit once
    # a story-scoped one exists) reds both assertions above
    mutant = _entries(
        _fenced_block(_section()).replace(
            '"reloop_count": <re-loops spent so far this run>',
            '"run_reloop_count": <re-loops spent so far this run>',
        )
    )
    assert "run_reloop_count" in mutant, "mutation did not apply; the twin would be vacuous"
    assert not set(pre_edit) <= set(mutant)
    assert set(mutant) - set(pre_edit) != {"last_reasons", "stories", "budget_used"}


def test_preedit_fixture_is_the_verbatim_shipped_section():
    """Twin integrity: an emptied or truncated fixture proves nothing, so pin it."""
    raw = _PRE_EDIT.read_text(encoding="utf-8")
    assert raw.count(_HEADING) == 1, "fixture must slice to exactly one heartbeat section"
    pre_edit = _section(raw)
    assert set(_top_keys(pre_edit)) == _PRE_EDIT_FINALIZE_KEYS, (
        "fixture must still parse to exactly the eight pre-existing keys"
    )
    for sentence in (
        "it is a single live snapshot, not an append log",
        "Skip the ticker in headless",
    ):
        assert sentence in pre_edit, f"fixture lost the verbatim {sentence!r} clause"
        assert sentence in _section(), f"shipped section dropped the {sentence!r} clause"


def test_finalize_restated_shape_matches_execute():
    shipped = set(_top_keys(_section()))
    assert _finalize_shape_keys() == shipped, (
        "finalize's restated shape and execute's snapshot block must not drift: "
        f"finalize-only={sorted(_finalize_shape_keys() - shipped)}, "
        f"execute-only={sorted(shipped - _finalize_shape_keys())}"
    )
    # anti-vacuous: leaving finalize at its pre-edit eight-key list -- the
    # default outcome of editing only the story's named file -- reds this
    assert _PRE_EDIT_FINALIZE_KEYS != shipped
    # and finalize is told not to drop the new keys on its terminal overwrite
    assert re.search(r"Write the whole shape, not a subset", _finalize_section())


def test_preedit_section_fails_additive_key_assertions():
    """Twin: with the three additive keys absent, every AC check reds."""
    pre_edit = _preedit_section()
    unmet = _unmet(_ADDITIVE_CHECKS, pre_edit)
    assert unmet == sorted(_ADDITIVE_CHECKS), (
        "the pre-edit section must fail every additive-key assertion; it already "
        f"satisfies {sorted(set(_ADDITIVE_CHECKS) - set(unmet))}"
    )
