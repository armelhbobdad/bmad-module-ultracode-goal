"""Prose-contract tests for the nested ucg-resolve SKILL.md.

`/ucg-resolve` is the decide-surface: it enumerates pending decisions from on-disk
artifacts alone, walks them once, records answers to `.decisions.json`, applies what a
`close` resolves, and hands control back to the EXISTING resume. These tests pin the
three structural properties that make that loop closeable:

  - enumeration names all three artifact sources, and the id is minted line-free so an
    answer survives a re-scan that moved the finding (+ twin: the id recipe must not be
    the raw `source` field, which carries a `:line` suffix);
  - `close` clears and `defer` does not, with a strictly two-valued action enum
    (+ twin: the defer disposition must not be a clear in disguise);
  - the handoff reuses the shipped resume rule rather than authoring a second one
    (+ twin: no alternative re-entry point, and no rebuild of the re-assert set).

Cross-file assertions locate the resume rule by CONTENT in `references/execute.md` and
the parent `SKILL.md`, never by hardcoded line number. Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_SKILL = _SKILL_ROOT / "skills" / "ucg-resolve" / "SKILL.md"
_PARENT_SKILL = _SKILL_ROOT / "SKILL.md"
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"

# Candidate values for the `action` enum. Only `close` and `defer` may appear quoted.
_ACTION_VOCAB = {"close", "defer", "skip", "ignore", "reopen", "wontfix", "dismiss", "postpone"}

_REENTRY_RE = re.compile(
    r"re-enter Execute at the first story whose last[^.;()]*?verdict is not advance",
    re.IGNORECASE,
)


def _text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+", _norm(text))


def _section(text: str, heading: str) -> str:
    """Body of a `## <heading>` section, up to the next `## `."""
    m = re.search(
        r"^## " + re.escape(heading) + r".*?(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert m is not None, f"section {heading!r} not found"
    return m.group(0)


def _canonical_reentry(text: str) -> str:
    """The re-entry rule, normalized so the three files' wordings are comparable.

    `execute.md` says 'last logged gate verdict', the parent SKILL says 'last verdict';
    dropping that one qualifier is the only permitted difference.
    """
    m = _REENTRY_RE.search(_norm(text))
    assert m is not None, "re-entry rule not found"
    return m.group(0).lower().replace("logged gate ", "")


# --- enumeration + line-free id -------------------------------------------


def test_enumerates_three_sources_and_mints_line_free_ids():
    text = _text()

    # (1) the typed escalation sidecar
    assert "escalation-<story_id>.json" in text, "must name the typed escalation sidecar"

    # (2) the single preflight RED sidecar, with its bound shape
    assert ".preflight-reds.json" in text, "must name the RED sidecar by its literal path"
    assert re.search(r'\{"reds":\s*\[', text), "must pin the `{\"reds\": [...]}` shape"

    # ONE file: no second and no per-story RED sidecar path anywhere in the file.
    reds_paths = set(re.findall(r"[\w.\-<>]*reds[\w.\-<>]*\.json", text))
    assert reds_paths == {".preflight-reds.json"}, (
        "exactly one RED sidecar path may be named, got %s" % sorted(reds_paths)
    )

    # (3) the ledger's `decision:` rows, scoped to the source column and still-open rows
    assert "`decision:` rows" in text, "must name the ledger's `decision:` rows"
    assert re.search(r"`source` column[^.]{0,40}`decision`", text), (
        "the ledger rows must be scoped by the `source` column reading `decision`"
    )
    assert re.search(r"`status`[^.]{0,40}`open`", text), "only still-open ledger rows are pending"

    # the id recipe: kind + artifact path, line numbers EXCLUDED
    assert re.search(r"`kind`[^.]{0,120}(path|artifact)", text), (
        "the id must be derived from `kind` plus the source-artifact path"
    )
    assert re.search(r"line numbers?\s+\*{0,2}excluded", text, re.IGNORECASE), (
        "the id recipe must state that line numbers are EXCLUDED"
    )
    # and the point of it: a re-detected RED inherits its id
    assert re.search(r"inherits its existing id", text, re.IGNORECASE), (
        "must state that a re-detected RED inherits its existing id"
    )


def test_id_recipe_rejects_the_raw_source_field():
    """Twin: the mutation mints the id from the subagent's raw `source` field, which the
    preflight contract defines as `<artifact path:line>` — a line-bearing id."""
    text = _text()

    # The `:line` suffix is named as the thing stripped.
    assert "`:line`" in text, "the `:line` suffix must be named"
    assert re.search(r"`:line`[^.]{0,60}strip|strip[^.]{0,60}`:line`", text, re.IGNORECASE), (
        "the `:line` suffix must be named as the thing stripped before minting"
    )

    # No sentence may instruct minting from `source` without negating it.
    offenders = [
        s
        for s in _sentences(text)
        if re.search(r"mint", s, re.IGNORECASE)
        and re.search(r"source", s, re.IGNORECASE)
        and not re.search(r"\bnever\b|\bnot\b|strip|exclud", s, re.IGNORECASE)
    ]
    assert offenders == [], (
        "the id must not be minted from the raw `source` field: %s" % offenders
    )


# --- close clears, defer records; the enum is two-valued --------------------


def _disposition(action: str) -> str:
    section = _section(_text(), "3.")
    m = re.search(
        r"- \*\*`" + action + r"`\*\*.*?(?=\n- \*\*`|\n\n)",
        section,
        re.DOTALL,
    )
    assert m is not None, f"`{action}` disposition bullet not found"
    return m.group(0)


def test_close_clears_defer_records_only_enum_is_two_valued():
    text = _text()

    # the sidecar path and its three per-entry keys are pinned
    assert ".decisions.json" in text, "must pin the `.decisions.json` path"
    for key in ("id", "answer", "action"):
        assert f'"{key}"' in text, f"the recorded entry must carry the {key!r} key"
    assert '"close|defer"' in text, "the action enum must be pinned in the recorded shape"

    # the two dispositions are distinct: close clears, defer does not
    close, defer = _disposition("close"), _disposition("defer")
    assert re.search(r"\bclear", close, re.IGNORECASE), "the `close` disposition must clear"
    assert re.search(r"without clearing|clears nothing", defer, re.IGNORECASE), (
        "the `defer` disposition must record without clearing"
    )

    # entry-level removal, never deleting the whole RED sidecar
    assert re.search(r"entry-level removal", close, re.IGNORECASE), (
        "clearing the RED sidecar must be entry-level removal"
    )
    assert re.search(r"never deleting the file", close, re.IGNORECASE), (
        "clearing must not delete the whole RED sidecar"
    )

    # the enum is EXACTLY two-valued: no stray third verb appears quoted anywhere.
    quoted = {m.group(1) for m in re.finditer(r'[`"]([a-z][a-z-]*)[`"]', text)}
    assert quoted & _ACTION_VOCAB == {"close", "defer"}, (
        "the action enum must be exactly {close, defer}, found %s"
        % sorted(quoted & _ACTION_VOCAB)
    )


def test_defer_disposition_is_not_a_clear():
    """Twin: the mutation makes `defer` also clear the sidecar, collapsing the enum to
    one behavior with two names and silently discarding an unanswered blocker."""
    defer = _disposition("defer")

    # An explicit negated-clear phrase is present ...
    assert re.search(r"without clearing|clears nothing", defer, re.IGNORECASE), (
        "the `defer` disposition must carry a negated clear"
    )
    # ... and once those negated phrases are removed, NO clear verb survives. Scanning a
    # window around each occurrence would false-pass on an unrelated nearby "not"; this
    # keys on the negating construction itself.
    residue = re.sub(
        r"without clearing\s+\w+|clears nothing|never clear\w*|does not clear\w*",
        "",
        defer,
        flags=re.IGNORECASE,
    )
    assert not re.search(r"clear\w*", residue, re.IGNORECASE), (
        "unnegated clear verb in the `defer` disposition: %r" % residue
    )

    # and the defer bullet states the item stays pending
    assert re.search(r"stays pending|still blocks|stays exactly where it is", defer, re.IGNORECASE), (
        "a deferred item must remain pending"
    )


# --- handoff reuses the existing resume ------------------------------------


def _handoff() -> str:
    return _section(_text(), "4.")


def test_handoff_reuses_the_existing_resume_rule():
    handoff = _handoff()

    assert re.search(r"defines no resume of its own", handoff, re.IGNORECASE), (
        "the handoff must state that this skill defines no resume of its own"
    )
    assert _REENTRY_RE.search(_norm(handoff)), "the handoff must carry the re-entry rule"
    assert "advanced stories are not re-run" in _norm(handoff).lower(), (
        "the handoff must state that advanced stories are not re-run"
    )
    assert re.search(r"already lives in|not restated", handoff, re.IGNORECASE), (
        "the handoff must refer to the existing rule, not author a new one"
    )

    # CROSS-FILE EQUALITY: the same rule, located by content in all three files.
    phrases = {
        _canonical_reentry(handoff),
        _canonical_reentry(_EXECUTE.read_text(encoding="utf-8")),
        _canonical_reentry(_PARENT_SKILL.read_text(encoding="utf-8")),
    }
    assert len(phrases) == 1, (
        "the re-entry wording diverged across the three files: %s" % sorted(phrases)
    )
    for source in (_EXECUTE, _PARENT_SKILL):
        assert "advanced stories are not re-run" in _norm(
            source.read_text(encoding="utf-8")
        ).lower(), f"{source.name} must carry the not-re-run clause this handoff reuses"


def test_handoff_does_not_author_a_second_resume_rule():
    """Twin: the mutation re-enters at the FIRST story of the Epic (or at the story the
    decision names), re-running stories that already advanced."""
    handoff = _handoff()

    # any alternative re-entry point named must be negated
    for candidate in ("first story of the Epic", "story the answered decision"):
        for sentence in _sentences(handoff):
            if candidate.lower() in sentence.lower():
                assert re.search(r"\bnot\b|\bnever\b|\bno other\b", sentence, re.IGNORECASE), (
                    "alternative re-entry point named without negation: %r" % sentence
                )
    assert re.search(r"no other re-entry point", handoff, re.IGNORECASE), (
        "the handoff must rule out any other re-entry point"
    )

    # the re-assert set is named, and is re-asserted rather than rebuilt
    for item in ("branch", "hooks", "allowlist", "baseline marker"):
        assert item in handoff, f"the re-assert set must name the {item}"
    assert re.search(r"re-assert", handoff, re.IGNORECASE), "the set is re-asserted"
    # Every `rebuild` must be IMMEDIATELY negated — a nearby unrelated "not" must not
    # launder a real rebuild instruction.
    for m in re.finditer(r"rebuild\w*", handoff, re.IGNORECASE):
        prefix = handoff[max(0, m.start() - 24) : m.start()]
        assert re.search(r"(never|not|rather than)\s*(—\s*)?$", prefix, re.IGNORECASE), (
            "the handoff must not instruct rebuilding: %r"
            % handoff[max(0, m.start() - 40) : m.end() + 20]
        )
    assert re.search(r"re-read, never regenerated", handoff, re.IGNORECASE), (
        "the baseline marker is re-read, never regenerated"
    )
