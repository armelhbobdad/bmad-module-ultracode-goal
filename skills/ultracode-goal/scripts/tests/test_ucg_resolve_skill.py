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

import importlib.util
import json
import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_SKILL = _SKILL_ROOT.parent / "ucg-resolve" / "SKILL.md"
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


# --- an earlier answer is never dropped (#189) -----------------------------
#
# Measured on a real project: 4 of 47 `.decisions.json` entries held
# multi-sentence rulings with no `action` key, written by an earlier version of
# this surface. A scoped pass that deferred them replaced each entry, as the
# read-modify-write rule said, and each ruling was gone; only the entry count
# (47 + 51 answers) showed it. An entry with no `action` is neither closed nor
# deferred, so the pass must offer it again, show what it held, carry every
# replaced answer forward, and say which entries it replaced.


_NO_ACTION_PENDING = (
    "An entry with no `action`, or with an `action` that is neither `close` nor `defer`, is pending as well "
    "while an item this pass enumerated carries its `id`."
)
_SHOW_EARLIER = (
    "When an item you present already has an entry, show its `answer`, and each earlier answer its `history` "
    "holds (section 3), beside the decision needed."
)
_CARRY_LEAD = "**A replacement never drops an earlier answer.**"
_CARRY_RULE = (
    "copy the replaced entry's `history` list as it stands, then append the replaced entry itself, with every "
    "field but `id` and `history` copied verbatim"
)
_CARRY_DUPLICATES = "carry each forward, in file order, and write one entry in their place"
_READERS_IGNORE = "Every reader of the file keys on `id` and `action` alone"
_REPORT_REPLACED = (
    "Name every entry this pass replaced, by `id`, with the earlier answer it carried into `history`"
)


def _history_checks() -> dict:
    return {
        "an entry with no action is pending, and presented again": lambda t: (
            _NO_ACTION_PENDING in _norm(_section(t, "2."))
            and "Present it again, as you present a deferred one." in _norm(_section(t, "2."))
        ),
        "the pass shows the earlier answers when it presents an item": lambda t: (
            _SHOW_EARLIER in _norm(_section(t, "2."))
        ),
        "the recorded shape carries history": lambda t: '"history": [' in _section(t, "3."),
        "a replacement carries the replaced entry forward": lambda t: (
            _CARRY_LEAD in _section(t, "3.") and _CARRY_RULE in _norm(_section(t, "3."))
        ),
        "every entry for the id is carried forward": lambda t: _CARRY_DUPLICATES in _norm(_section(t, "3.")),
        "the readers ignore history": lambda t: _READERS_IGNORE in _norm(_section(t, "3.")),
        "the summary names every replaced entry": lambda t: _REPORT_REPLACED in _norm(_section(t, "4.")),
    }


def _history_failures(text: str) -> list[str]:
    return [name for name, check in _history_checks().items() if not check(text)]


def test_no_replacement_drops_an_earlier_answer():
    assert _history_failures(_text()) == []


def _mutate(text: str, old: str, new: str) -> str:
    """`text` with its one `old` replaced, whatever whitespace (a line wrap
    included) stands where `old` has a space."""
    pattern = re.compile(r"\s+".join(map(re.escape, old.split(" "))))
    assert len(pattern.findall(text)) == 1, old
    return pattern.sub(lambda _: new, text, count=1)


def test_the_history_pin_reds_on_the_rule_that_replaced_an_entry_whole():
    """Twin: section 3 as it read before, a new answer replacing the entry and
    nothing carried forward, with no history in the shape."""
    text = _text()
    section = _section(text, "3.")
    start = section.index(_CARRY_LEAD)
    old = text.replace(section, section[:start] + section[section.index("**If an existing", start) :])
    old = old.replace(',\n                "history": [', "]}]}\n#", 1)
    failures = _history_failures(old)
    assert {
        "the recorded shape carries history",
        "a replacement carries the replaced entry forward",
        "every entry for the id is carried forward",
        "the readers ignore history",
    } <= set(failures), failures


def test_the_history_pin_reds_without_each_rule():
    """Twin: each sentence cut on its own reds its check, and only that one."""
    text = _text()
    cuts = {
        "an entry with no action is pending, and presented again": _NO_ACTION_PENDING,
        "the pass shows the earlier answers when it presents an item": _SHOW_EARLIER,
        "every entry for the id is carried forward": _CARRY_DUPLICATES,
        "the readers ignore history": _READERS_IGNORE,
        "the summary names every replaced entry": _REPORT_REPLACED,
    }
    for name, sentence in cuts.items():
        assert _history_failures(_mutate(text, sentence, "")) == [name], name


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"_resolve_{name}", _SKILL_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _shape(**fields) -> dict:
    """One entry of the documented `.decisions.json` shape, as section 3's fence
    gives it, with `fields` set over its placeholders."""
    fence = re.search(r"```json\n(\{\"decisions\".*?)\n```", _section(_text(), "3."), re.DOTALL)
    assert fence is not None, "section 3 must show the recorded shape"
    entry = json.loads(fence.group(1))["decisions"][0]
    return {**entry, **fields}


def test_the_readers_read_the_documented_shape_with_history(tmp_path):
    """Every reader of `.decisions.json` keys on `id` and `action` alone: a
    `close` carrying `history` (and a key no reader knows) still suppresses its
    RED and closes its escalation, and an entry with no `action` closes
    nothing, so its question is still pending."""
    red_ids, preflight_check = _load_script("red_ids"), _load_script("preflight_check")
    impl = tmp_path / "impl"
    impl.mkdir()
    sidecar = {
        "source": "impl/coupled-7-1.md",
        "kind": "coupled-stories",
        "decision_needed": "Move AC 7 (a) from 7-1 to 7-2 as measured, or re-plan the rows.",
        "evidence": "AC 7 (a): the handler it needs lands only in 7-2's build.",
    }
    (impl / "escalation-7-1.json").write_text(json.dumps(sidecar), encoding="utf-8")
    sidecar_id = red_ids.mint_id(sidecar["kind"], sidecar["source"], sidecar["decision_needed"])
    red_id = red_ids.mint_id("undecided-product", "docs/prd.md:14", "Which retention period applies?")
    earlier = {"answer": "Ninety days, as legal ruled on 2026-10-01. Revisit after the audit.", "note": "kept"}
    decisions = impl / ".decisions.json"

    closed = [
        _shape(id=sidecar_id, answer="Move AC 7 (a) as proposed.", action="close", history=[earlier], extra=1),
        _shape(id=red_id, answer="Ninety days.", action="close", history=[earlier]),
    ]
    decisions.write_text(json.dumps({"decisions": closed}), encoding="utf-8")
    assert red_ids.closed_ids(decisions) == {sidecar_id, red_id}
    assert preflight_check._escalation_of(impl, "7-1", tmp_path)["state"] == "closed"

    pending = [{k: v for k, v in entry.items() if k != "action"} for entry in closed]
    decisions.write_text(json.dumps({"decisions": pending}), encoding="utf-8")
    assert red_ids.closed_ids(decisions) == set()
    assert preflight_check._escalation_of(impl, "7-1", tmp_path)["state"] == "open"


# --- an entry no enumerated item carries is listed apart, never asked (#209) --
#
# Section 2 called every entry that is not a `close` pending, and said its
# question still blocks, whether or not any source still carries its id. What
# blocks is a source: preflight blocks on the reds of `.preflight-reds.json`,
# the resume on an open `escalation-<story_id>.json`, and both read only the
# `close` entries of `.decisions.json`. So an entry is pending only while an
# item the pass enumerated carries its id, under every spelling the resume
# reads a close of a sidecar by; one no item carries is orphaned, listed apart
# with its answers and never asked; and when a source could not be read in
# full, nothing is called orphaned.
#
# Review loop 1: `.preflight-reds.json` is one project-wide file each
# preflight replaces, so after another Epic's preflight a RED this Epic
# deferred reads orphaned while this Epic's next preflight blocks on it again.
# The pass never says an orphan blocks nothing: the orphan paragraph and the
# summary say a later preflight can raise it again and block on it, and a pass
# that found only orphans is not called a non-decision stop.

_DEFER_SCOPE = (
    "Present it again while an item this pass enumerated carries its `id`, and replace its entry in place "
    "when the operator decides it"
)
_STAYS_OPEN = "preflight drops none of their ids, so that item's question stays open."
_OLD_STILL_BLOCK = "so their questions still block"
_CARRIES_LEAD = "**An item carries an entry's `id` only on an exact match, as written.**"
_SIDECAR_SPELLINGS = (
    "one more for each spelling of the sidecar file's own path the resume reads a close by (`_sidecar_ids` in "
    "`{ucg-root}/scripts/preflight_check.py`): its path relative to `{project-root}`, its absolute path, that "
    "absolute path with its folder's symlinks resolved, and the resolved path relative to `{project-root}`, "
    "each written with forward slashes and, on Windows, with backslashes too."
)
_RECOGNIZE_ONLY = (
    "Mint them only to recognize an entry already recorded, never to key an answer: an entry keyed by any of "
    "them belongs to that sidecar's item."
)
_SECTION1_PATH = (
    "never key an answer by an id minted from that path: section 2 mints those ids only to recognize an entry "
    "already recorded."
)
_ORPHAN_LEAD = "**An entry no enumerated item carries is orphaned, not pending.**"
_ORPHAN_UNHELD = (
    "That is an entry whose `action` is anything but `close` and whose `id` no item of this pass carries: none "
    "of the three sources holds its question at this pass, so there is no item to present it with."
)
_ORPHAN_LISTED = (
    "List the orphaned entries after the pending items, apart from them, each with its `id`, its `answer` and "
    "each earlier answer its `history` holds, and ask nothing about them; the record keeps each one as it stands."
)
_ORPHAN_CAN_RETURN = "Say beside that list that a later preflight can raise an orphaned entry again and block on it."
_REGISTRY_REPLACED = (
    "`.preflight-reds.json` is one project-wide file that each preflight replaces, so it holds only the REDs of "
    "the last preflight, from whichever Epic ran it: a RED one Epic's preflight raised can be gone from it after "
    "another Epic's preflight, while that first Epic's next preflight can raise it again."
)
_ORPHAN_AGAIN = (
    "An orphaned entry whose `id` a later RED, sidecar or ledger row carries is pending again at that pass, "
    "which asks it."
)
_FAIL_CLOSED_LEAD = "**When a source could not be read in full, call nothing orphaned.**"
_FAIL_CLOSED_PENDING = (
    "In that case present every entry that is not a `close` as pending, with its `id`, its `answer` and its "
    "`history`, since an id that source would carry cannot be ruled out."
)
_SUMMARY_ORPHANS = (
    "List the orphaned entries apart from both, by `id`, and say that a later preflight can raise any of them "
    "again and block on it, and that the pass after that preflight asks it."
)
_ONLY_ORPHANS_NOT_EMPTY = (
    "A pass that found only orphaned entries is not an empty enumeration, so do not say the run stopped for a "
    "non-decision reason: the run can have stopped on a RED that another Epic's preflight has since dropped "
    "from `.preflight-reds.json`, and its next preflight raises that RED again."
)
_ONLY_ORPHANS_HAND_BACK = "Such a pass closed nothing, so it hands back only when the operator asks for the resume."


def _orphan_checks() -> dict:
    def s1(t: str) -> str:
        return _norm(_section(t, "1."))

    def s2(t: str) -> str:
        return _norm(_section(t, "2."))

    def s4(t: str) -> str:
        return _norm(_section(t, "4."))

    return {
        "a deferred entry is presented again while an item carries its id": lambda t: _DEFER_SCOPE in s2(t),
        "an action-less entry is pending while an item carries its id": lambda t: _NO_ACTION_PENDING in s2(t),
        "its question stays open, and no claim that it still blocks": lambda t: (
            _STAYS_OPEN in s2(t) and _OLD_STILL_BLOCK not in s2(t)
        ),
        "an item carries an id on an exact match": lambda t: _CARRIES_LEAD in s2(t),
        "a sidecar carries every path spelling the resume reads a close by": lambda t: _SIDECAR_SPELLINGS in s2(t),
        "the path ids are minted only to recognize an entry": lambda t: _RECOGNIZE_ONLY in s2(t),
        "section 1 keys no answer by a path id": lambda t: _SECTION1_PATH in s1(t),
        "an entry no item carries is orphaned": lambda t: _ORPHAN_LEAD in s2(t),
        "no source holds an orphaned entry's question at this pass": lambda t: _ORPHAN_UNHELD in s2(t),
        "orphaned entries are listed apart and not asked": lambda t: _ORPHAN_LISTED in s2(t),
        "a later preflight can raise an orphaned entry again and block on it": lambda t: (
            _ORPHAN_CAN_RETURN in s2(t)
        ),
        "the RED list is project-wide and each preflight replaces it": lambda t: _REGISTRY_REPLACED in s2(t),
        "an orphaned entry an item carries again is pending again and asked": lambda t: _ORPHAN_AGAIN in s2(t),
        "nothing is orphaned when a source could not be read": lambda t: (
            _FAIL_CLOSED_LEAD in s2(t) and _FAIL_CLOSED_PENDING in s2(t)
        ),
        "the summary lists orphaned entries apart and says they can come back": lambda t: (
            _SUMMARY_ORPHANS in s4(t)
        ),
        "only orphaned entries is not called a non-decision stop": lambda t: _ONLY_ORPHANS_NOT_EMPTY in s4(t),
        "a pass of only orphaned entries hands back only when asked": lambda t: _ONLY_ORPHANS_HAND_BACK in s4(t),
    }


def _orphan_failures(text: str) -> list[str]:
    return [name for name, check in _orphan_checks().items() if not check(text)]


def test_an_entry_no_item_carries_is_listed_apart_and_never_asked():
    assert _orphan_failures(_text()) == []


# (the check the old wording reds, the new wording, the old wording)
_RESTORE_OLD = [
    (
        "a deferred entry is presented again while an item carries its id",
        "Present it again while an item this pass enumerated carries its `id`, and",
        "Present it again, and",
    ),
    (
        "an action-less entry is pending while an item carries its id",
        "is pending as well while an item this pass enumerated carries its `id`. An earlier",
        "is pending as well. An earlier",
    ),
    (
        "its question stays open, and no claim that it still blocks",
        "so that item's question stays open.",
        "so their questions still block.",
    ),
    ("section 1 keys no answer by a path id", _SECTION1_PATH, "never mint a new id from that path."),
]


def _cut_paragraph(text: str, lead: str) -> str:
    start = text.index(lead)
    return text[:start] + text[text.index("\n\n", start) + 2 :]


def _before_209(text: str) -> str:
    """`text` rebuilt as sections 1, 2 and 4 read before #209."""
    for _name, new, old in _RESTORE_OLD:
        text = _mutate(text, new, old)
    for lead in (_CARRIES_LEAD, _ORPHAN_LEAD, _FAIL_CLOSED_LEAD):
        text = _cut_paragraph(text, lead)
    for sentence in (_SUMMARY_ORPHANS, _ONLY_ORPHANS_NOT_EMPTY, _ONLY_ORPHANS_HAND_BACK):
        text = _mutate(text, " " + sentence, "")
    return text


def test_the_orphan_pins_red_on_the_text_before_209():
    """Twin: the pass as it read before, every entry that is not a `close`
    pending and its question said to still block, reds every check."""
    old = _before_209(_text())
    assert (
        "is pending as well. An earlier version of this surface wrote some entries that way, and preflight drops "
        "none of their ids, so their questions still block. Present it again, as you present a deferred one."
    ) in _norm(old)
    assert (
        "the operator sees what the record held before this pass. **Hand back only when the pass closed at least "
        "one item"
    ) in _norm(old)
    assert "`/ucg-status`, and hand nothing back.\n\nOtherwise hand back" in old
    assert "orphan" not in old.lower()
    assert _orphan_failures(old) == list(_orphan_checks())


@pytest.mark.parametrize("name,new,old", _RESTORE_OLD, ids=["defer", "no-action", "stays-open", "section-1"])
def test_each_old_sentence_restored_reds_its_pin(name, new, old):
    assert name in _orphan_failures(_mutate(_text(), new, old))


# The orphan rules as the attempt dropped in review loop 1 worded them: an
# orphan said to block nothing, with no word that a later preflight can raise
# it again, and an only-orphans pass counted as an empty enumeration, which
# says the run stopped for a non-decision reason.
_SAID_TO_BLOCK_NOTHING = [
    (
        _ORPHAN_UNHELD,
        "That is an entry whose `action` is anything but `close` and whose `id` no item of this pass carries: "
        "no scan raises it and no resume stops on it, so it blocks nothing.",
    ),
    (" " + _ORPHAN_CAN_RETURN, ""),
    (" " + _REGISTRY_REPLACED, ""),
    (_ORPHAN_AGAIN, "An orphaned entry whose `id` a later RED, sidecar or ledger row carries is pending again at that pass."),
    (_SUMMARY_ORPHANS, "List the orphaned entries apart from both, by `id`, and say that none of them blocks."),
    (
        _ONLY_ORPHANS_NOT_EMPTY + " " + _ONLY_ORPHANS_HAND_BACK,
        "An enumeration that found only orphaned entries is an empty one.",
    ),
]


def _said_to_block_nothing(text: str) -> str:
    for new, old in _SAID_TO_BLOCK_NOTHING:
        text = _mutate(text, new, old)
    return text


def test_the_orphan_pins_red_on_an_orphan_said_to_block_nothing():
    """Twin: the wording review loop 1 dropped reds each check of the
    renegotiated decision, and only those."""
    assert set(_orphan_failures(_said_to_block_nothing(_text()))) == {
        "no source holds an orphaned entry's question at this pass",
        "a later preflight can raise an orphaned entry again and block on it",
        "the RED list is project-wide and each preflight replaces it",
        "an orphaned entry an item carries again is pending again and asked",
        "the summary lists orphaned entries apart and says they can come back",
        "only orphaned entries is not called a non-decision stop",
        "a pass of only orphaned entries hands back only when asked",
    }


def test_the_orphan_pins_red_without_each_rule():
    """Twin: each sentence cut on its own reds its check, and only that one."""
    text = _text()
    cuts = [
        ("a deferred entry is presented again while an item carries its id", _DEFER_SCOPE),
        ("an action-less entry is pending while an item carries its id", _NO_ACTION_PENDING),
        ("its question stays open, and no claim that it still blocks", _STAYS_OPEN),
        ("an item carries an id on an exact match", _CARRIES_LEAD),
        ("a sidecar carries every path spelling the resume reads a close by", _SIDECAR_SPELLINGS),
        ("the path ids are minted only to recognize an entry", _RECOGNIZE_ONLY),
        ("section 1 keys no answer by a path id", _SECTION1_PATH),
        ("an entry no item carries is orphaned", _ORPHAN_LEAD),
        ("no source holds an orphaned entry's question at this pass", _ORPHAN_UNHELD),
        ("orphaned entries are listed apart and not asked", _ORPHAN_LISTED),
        ("a later preflight can raise an orphaned entry again and block on it", _ORPHAN_CAN_RETURN),
        ("the RED list is project-wide and each preflight replaces it", _REGISTRY_REPLACED),
        ("an orphaned entry an item carries again is pending again and asked", _ORPHAN_AGAIN),
        ("nothing is orphaned when a source could not be read", _FAIL_CLOSED_LEAD),
        ("nothing is orphaned when a source could not be read", _FAIL_CLOSED_PENDING),
        ("the summary lists orphaned entries apart and says they can come back", _SUMMARY_ORPHANS),
        ("only orphaned entries is not called a non-decision stop", _ONLY_ORPHANS_NOT_EMPTY),
        ("a pass of only orphaned entries hands back only when asked", _ONLY_ORPHANS_HAND_BACK),
    ]
    assert {name for name, _ in cuts} == set(_orphan_checks())
    for name, sentence in cuts:
        assert _orphan_failures(_mutate(text, sentence, "")) == [name], name


def _orphan_blocking_claims(text: str) -> list[str]:
    return [
        s
        for s in _sentences(text)
        if "orphan" in s.lower() and re.search(r"re-blocks?\b|still blocks?\b|blocks the run|is blocking", s, re.I)
    ]


def test_no_sentence_calls_an_orphaned_entry_blocking():
    assert _orphan_blocking_claims(_text()) == []


def test_the_blocking_scan_reds_on_an_orphan_said_to_re_block():
    """Twin: the summary says the orphaned entries re-block, as it says of the
    pending ones."""
    mutant = _mutate(
        _text(), _SUMMARY_ORPHANS, "List the orphaned entries apart from both, by `id`, and say that they re-block."
    )
    assert len(_orphan_blocking_claims(mutant)) == 1


def _blocks_nothing_claims(text: str) -> list[str]:
    """Sentences of sections 2 and 4 that say something blocks nothing."""
    pattern = r"\bblocks? nothing\b|\bnone of them blocks?\b|\bnever blocks?\b|\bcan(?:not| never) block\b"
    return [
        s for s in _sentences(_section(text, "2.") + _section(text, "4.")) if re.search(pattern, s, re.I)
    ]


def _only_orphans_called_empty(text: str) -> list[str]:
    """Sentences of section 4 that count an only-orphans pass as an empty
    enumeration, or as a non-decision stop, without negating it."""
    return [
        s
        for s in _sentences(_section(text, "4."))
        if "only orphaned" in s
        and re.search(r"\bempty\b|non-decision", s)
        and not re.search(r"\bnot\b|\bnever\b", s)
    ]


def test_no_sentence_says_an_orphan_blocks_nothing_or_calls_an_only_orphans_pass_empty():
    text = _text()
    assert _blocks_nothing_claims(text) == []
    assert _only_orphans_called_empty(text) == []


def test_the_scans_red_on_the_wording_review_loop_1_dropped():
    """Twin: the orphan said to block nothing, the summary saying none of them
    blocks, and the only-orphans pass called an empty enumeration."""
    mutant = _said_to_block_nothing(_text())
    assert len(_blocks_nothing_claims(mutant)) == 2
    assert len(_only_orphans_called_empty(mutant)) == 1


def test_no_reader_reads_an_orphaned_entry(tmp_path):
    """No reader that blocks reads an orphaned entry. With the orphaned entries
    in `.decisions.json` or without them, preflight's override keeps the same
    reds, the same ids read as closed, and the resume reads the same sidecar
    state. The entries an item carries are the RED's id and the sidecar's ids,
    so the pass can tell the two apart by an exact compare."""
    red_ids, preflight_check = _load_script("red_ids"), _load_script("preflight_check")
    impl = tmp_path / "impl"
    impl.mkdir()
    scan = [
        {
            "source": "docs/prd.md:14",
            "kind": "undecided-product",
            "decision_needed": "Which retention period applies?",
            "evidence": "The PRD names none.",
        }
    ]
    sidecar = {
        "source": "impl/coupled-7-1.md",
        "kind": "coupled-stories",
        "decision_needed": "Move AC 7 (a) from 7-1 to 7-2 as measured, or re-plan the rows.",
        "evidence": "AC 7 (a): the handler it needs lands only in 7-2's build.",
    }
    sidecar_path = impl / "escalation-7-1.json"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    red_id = red_ids.mint_id(scan[0]["kind"], scan[0]["source"], scan[0]["decision_needed"])
    sidecar_id = red_ids.mint_id(sidecar["kind"], sidecar["source"], sidecar["decision_needed"])
    pending = [
        _shape(id=red_id, answer="Ask legal first.", action="defer"),
        {"id": sidecar_id, "answer": "Wait for 7-2's build, as ruled on 2026-10-01."},
    ]
    gone_red = red_ids.mint_id("undecided-product", "docs/prd.md", "Which region hosts the data?")
    gone_sidecar = red_ids.mint_id("budget-overrun", "impl/7-0.md", "Re-scope 7-0 or grant a fresh budget.")
    orphaned = [
        {"id": gone_red, "answer": "EU only, as legal ruled."},
        _shape(id=gone_sidecar, answer="Parked until the audit.", action="defer"),
        {"id": "undecided-product:docs/prd.md", "answer": "Keyed before ids had a digest.", "action": "later"},
    ]
    decisions = impl / ".decisions.json"

    def readers() -> tuple:
        return (
            red_ids.apply(scan, impl),
            red_ids.closed_ids(decisions),
            preflight_check._escalation_of(impl, "7-1", tmp_path),
        )

    decisions.write_text(json.dumps({"decisions": pending}), encoding="utf-8")
    without = readers()
    decisions.write_text(json.dumps({"decisions": pending + orphaned}), encoding="utf-8")
    assert readers() == without
    assert [red["id"] for red in without[0]["reds"]] == [red_id]
    assert without[1] == set()
    assert without[2]["state"] == "open"

    carried = {red["id"] for red in without[0]["reds"]} | set(
        preflight_check._sidecar_ids(dict(sidecar), sidecar_path, tmp_path)
    )
    assert {entry["id"] for entry in pending} <= carried
    assert not {entry["id"] for entry in orphaned} & carried


def test_a_later_preflight_raises_an_orphaned_red_again(tmp_path):
    """`.preflight-reds.json` is one project-wide file each preflight replaces.
    Epic B's preflight raises a RED and the operator defers it. Epic A's
    preflight then writes the file from its own scan, so no RED carries B's
    entry and the next pass reads it orphaned. B's next preflight raises that
    RED again under the same id, the defer suppresses nothing, and the hard
    gate blocks on it: the pass after that preflight carries the entry's id
    and asks it."""
    red_ids = _load_script("red_ids")
    impl = tmp_path / "impl"
    impl.mkdir()
    red_b = {
        "source": "docs/epic-b-prd.md:14",
        "kind": "undecided-product",
        "decision_needed": "Which retention period applies?",
        "evidence": "The PRD names none.",
    }
    red_a = {
        "source": "docs/epic-a-prd.md:9",
        "kind": "undecided-product",
        "decision_needed": "Which region hosts the data?",
        "evidence": "The PRD names none.",
    }

    def preflight(*reds: dict) -> set:
        """One preflight's step 3, as preflight.md runs it: the scan through
        the id layer, which writes the registry. The ids of its `reds`."""
        scan = tmp_path / "scan.json"
        scan.write_text(json.dumps({"reds": list(reds)}), encoding="utf-8")
        assert red_ids.main(["--scan", str(scan), "--impl-artifacts", str(impl)]) == 0
        registry = json.loads((impl / ".preflight-reds.json").read_text(encoding="utf-8"))
        return {red["id"] for red in registry["reds"]}

    b_id = red_ids.mint_id(red_b["kind"], red_b["source"], red_b["decision_needed"])
    assert preflight(red_b) == {b_id}
    (impl / ".decisions.json").write_text(
        json.dumps({"decisions": [_shape(id=b_id, answer="Ask legal first.", action="defer")]}),
        encoding="utf-8",
    )
    assert b_id not in preflight(red_a), "Epic A's preflight replaced the registry, so B's entry reads orphaned"
    assert preflight(red_b) == {b_id}, "B's next preflight raises the orphaned RED again and blocks on it"


def test_the_path_spellings_are_the_ones_the_resume_reads(tmp_path):
    """The spellings section 2 lists for a sidecar's own path are the ones
    `_sidecar_ids` mints from, so an entry keyed by any of them is carried by
    the live sidecar, never orphaned. The resolved one counts too: a `close`
    keyed by it closes the sidecar at the resume."""
    red_ids, preflight_check = _load_script("red_ids"), _load_script("preflight_check")
    root = tmp_path.resolve()
    real = root / "_bmad-output" / "implementation-artifacts"
    real.mkdir(parents=True)
    link = root / "artifacts-link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot make a directory symlink here")
    sidecar = {
        "source": "docs/stories/7-1.md:40",
        "kind": "coupled-stories",
        "decision_needed": "Move AC 7 (a) from 7-1 to 7-2 as measured, or re-plan the rows.",
        "evidence": "AC 7 (a): the handler it needs lands only in 7-2's build.",
    }
    (real / "escalation-7-1.json").write_text(json.dumps(sidecar), encoding="utf-8")
    path = link / "escalation-7-1.json"
    resolved = path.parent.resolve() / path.name
    assert resolved == real / path.name

    # As section 2 lists them: relative to the project root, absolute, absolute
    # with the folder's symlinks resolved, and that resolved path made relative.
    spellings = [path.relative_to(root), path, resolved, resolved.relative_to(root)]
    mint = red_ids.mint_id
    expected = {mint(sidecar["kind"], sidecar["source"], sidecar["decision_needed"])} | {
        mint(sidecar["kind"], written, sidecar["decision_needed"])
        for spelling in spellings
        for written in (spelling.as_posix(), str(spelling))
    }
    assert set(preflight_check._sidecar_ids(dict(sidecar), path, root)) == expected

    closed = mint(sidecar["kind"], resolved.relative_to(root).as_posix(), sidecar["decision_needed"])
    (real / ".decisions.json").write_text(
        json.dumps({"decisions": [_shape(id=closed, answer="Move AC 7 (a) as proposed.", action="close")]}),
        encoding="utf-8",
    )
    assert preflight_check._escalation_of(link, "7-1", root)["state"] == "closed"
