"""Phase-3 evidence gate, doc-lint, stdlib + pytest.

The load-bearing deliverable is the `## … — Phase-3 evidence gate` section appended to
skills/ultracode-goal/.decision-log.md: three `### Promotion gate — <fragment>` blocks (one each for
bmad-dev-story / bmad-code-review / bmad-sprint-planning), each carrying the five readiness fields
status / decision_needed / attribution_rubric / nfr8_collision_check / promotion_trigger, plus a
self-binding downstream-map table and a cut-ability line. This test is a pure ci-deterministic doc-lint
(no runtime stop-authority): it string-parses the markdown and asserts the gate is
non-vacuous and orphan-checked.

POSITIVE assertions run against the REAL .decision-log.md section. ANTI-VACUOUS twins run the SAME
checks against named programmatic mutations of fixtures/phase3/good_section.md and assert each flips red.

CI-portability: the section's grounding cites gitignored `_bmad-output/…` planning paths.
The on-disk existence check hard-asserts only the tracked decision-log itself; a cited `_bmad-output/`
planning path is asserted to be a file only WHEN present (verified manually at authoring; not CI-gated).
The no-phantom-epics-path and no-3.[2-5]-story-id checks are pure regex and ARE CI-enforced — they catch
the orphan/phantom failure modes that matter regardless of the gitignored tree.
"""

import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DECISION_LOG = _SKILL_ROOT / ".decision-log.md"
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "phase3" / "good_section.md"

_FRAGMENTS = ("bmad-dev-story", "bmad-code-review", "bmad-sprint-planning")
_FRAGMENT_SET = frozenset(_FRAGMENTS)
_KNOWN_LABELS = (
    "status",
    "decision_needed",
    "attribution_rubric",
    "nfr8_collision_check",
    "promotion_trigger",
)
_REQUIRED_STATUS = "DEFERRED — not built (pending field evidence)"
# Forbidden placeholder tokens (word-boundary, case-insensitive) + literal '???'.
_PLACEHOLDER_TOKENS = ("tbd", "todo", "placeholder", "none")
_RUNTIME_TOKENS = ("preflight", "PreToolUse", "Stop", "gate_eval.py")
_CUT_TOKENS = ("cut", "terminal", "not promoted")
_ANCHORS = {
    "bmad-dev-story": ("dev-story",),
    "bmad-code-review": ("code-review", "adversarial"),
    "bmad-sprint-planning": ("sprint-status.yaml", "sprint-planning"),
}
_HEADING_RE = re.compile(r"(?m)^### Promotion gate — ")
_LABEL_RE = re.compile(r"^(%s):\s?(.*)$" % "|".join(_KNOWN_LABELS))


# --------------------------------------------------------------------------- parsers


def _extract_section(text):
    """Slice the Phase-3 evidence-gate section. For the real log, from its `## … Phase-3
    evidence gate` heading to the next top-level `## `; a standalone fixture is returned whole."""
    m = re.search(r"(?m)^##[^\n]*Phase-3 evidence gate.*$", text)
    if not m:
        return text
    nxt = re.search(r"(?m)^## ", text[m.end():])
    end = m.end() + nxt.start() if nxt else len(text)
    return text[m.start():end]


def _parse_fields(body):
    fields, cur, buf = {}, None, []
    for line in body.splitlines():
        if line.startswith("### ") or line.startswith("## "):
            break
        m = _LABEL_RE.match(line)
        if m:
            if cur is not None:
                fields[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1), [m.group(2)]
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        fields[cur] = "\n".join(buf).strip()
    return fields


def _parse_blocks(section):
    """Return (headings_in_order, {fragment_id: fields}). Duplicate ids are preserved in the
    ordered list (so the exact-three-distinct check can catch them); the dict keeps last-wins."""
    parts = _HEADING_RE.split(section)
    headings, blocks = [], {}
    for chunk in parts[1:]:
        nl = chunk.find("\n")
        frag = (chunk[:nl] if nl != -1 else chunk).strip()
        body = chunk[nl + 1:] if nl != -1 else ""
        headings.append(frag)
        blocks[frag] = _parse_fields(body)
    return headings, blocks


def _parse_downstream_map(section):
    rows = []
    for line in section.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        left = [c.strip() for c in s.strip("|").split("|")][0]
        if left.startswith("bmad-"):
            rows.append(left)
    return rows


# ------------------------------------------------------------------- reusable AC checks


def _check_three_blocks(section):
    """Case 1: exactly three blocks, the three target ids each once, all five fields present."""
    headings, blocks = _parse_blocks(section)
    assert len(headings) == 3, "expected exactly 3 promotion blocks, got %d" % len(headings)
    assert sorted(headings) == sorted(_FRAGMENTS), "block ids %r != target set" % headings
    # reproducible grep cross-check
    assert len(_HEADING_RE.findall(section)) == 3
    for frag in _FRAGMENTS:
        assert len(re.findall(r"(?m)^### Promotion gate — %s$" % re.escape(frag), section)) == 1
        fields = blocks[frag]
        for label in _KNOWN_LABELS:
            assert label in fields, "%s missing field %s" % (frag, label)
        assert fields["status"] == _REQUIRED_STATUS, "%s status not the literal DEFERRED string" % frag


def _has_placeholder(text):
    low = text.lower()
    if "???" in text:
        return True
    return any(re.search(r"\b%s\b" % tok, low) for tok in _PLACEHOLDER_TOKENS)


def _check_rubrics(section):
    """Case 2: each attribution_rubric names its fragment-specific artifact shape, no placeholder."""
    _, blocks = _parse_blocks(section)
    for frag in _FRAGMENTS:
        rubric = blocks[frag]["attribution_rubric"]
        assert any(a in rubric for a in _ANCHORS[frag]), (
            "%s rubric missing its anchor token %r" % (frag, _ANCHORS[frag])
        )
        assert not _has_placeholder(rubric), "%s rubric contains a forbidden placeholder token" % frag


def _check_nfr8(section):
    """Case 3: nfr8_collision_check is co-equal/terminal (names a runtime layer + a cut outcome);
    promotion_trigger requires BOTH rubric AND check via a standalone AND."""
    _, blocks = _parse_blocks(section)
    for frag in _FRAGMENTS:
        nfr8 = blocks[frag]["nfr8_collision_check"]
        assert any(t in nfr8 for t in _RUNTIME_TOKENS), "%s nfr8 names no runtime layer" % frag
        assert any(t in nfr8.lower() for t in _CUT_TOKENS), "%s nfr8 states no cut outcome" % frag
        trig = blocks[frag]["promotion_trigger"]
        assert "attribution_rubric" in trig and "nfr8_collision_check" in trig, (
            "%s trigger does not reference both gates" % frag
        )
        assert re.search(r"\bAND\b", trig), "%s trigger lacks the standalone AND link" % frag


def _check_backrefs(section):
    """Case 4: self-binding, zero dangling refs against artifacts that exist today."""
    headings, blocks = _parse_blocks(section)
    rows = _parse_downstream_map(section)
    # (a) downstream-map closes bidirectionally with the blocks
    assert set(rows) == _FRAGMENT_SET, "downstream-map rows %r != target set" % rows
    for frag in rows:
        assert frag in blocks, "downstream-map row %s has no block" % frag
    for frag in headings:
        assert frag in rows, "block %s has no downstream-map row" % frag
    # (b) cut-ability line present
    assert re.search(r"(?m)^cut-ability:", section), "missing cut-ability line"
    # (c) no phantom epics-file path (a contiguous _bmad-output/…epics… path token, not prose),
    #     no phantom 3.[2-5] story id
    assert not re.search(r"_bmad-output/[^\s`)]*epics", section), "cites a phantom epics-file path"
    assert not re.search(r"\b3\.[2-5]\b", section), "cites a phantom 3.[2-5] story id"
    # (d) every bmad-* fragment id mentioned is one of the three targets. The lookbehind excludes
    #     the directory token in `_bmad-output/…` (underscore-prefixed), which is not a fragment id.
    for tok in re.findall(r"(?<![\w-])bmad-[a-z]+(?:-[a-z]+)*", section):
        assert tok in _FRAGMENT_SET, "orphan fragment id: %s" % tok
    # (e) every cited on-disk path resolves WHEN present. Planning paths under _bmad-output/ are
    #     gitignored (absent in CI) → checked only when present (CI-portability rule); the
    #     no-phantom-epics-path + no-3.[2-5] regex checks above are the CI-enforced orphan guards.
    for cited in re.findall(r"_bmad-output/[^\s`)]+\.md", section):
        p = _PROJECT_ROOT / cited
        if p.exists():
            assert p.is_file()


# ------------------------------------------------------------------- positive (real log)


def _real_section():
    # skills/ultracode-goal/.decision-log.md is gitignored working memory (.gitignore: **/.decision-log.md),
    # so it is absent on a fresh CI checkout. The real-log positives verify it at authoring / on every
    # local UCG run; in CI the structure is proven on the tracked good_section.md fixture + mutation twins.
    if not _DECISION_LOG.exists():
        pytest.skip(".decision-log.md gitignored/absent (CI) — structure CI-proven on tracked fixture+twins")
    return _extract_section(_DECISION_LOG.read_text(encoding="utf-8"))


def test_three_blocks_with_required_fields():
    _check_three_blocks(_real_section())


def test_attribution_rubric_names_fragment_specific_shape():
    _check_rubrics(_real_section())


def test_nfr8_collision_check_is_coequal_terminal():
    _check_nfr8(_real_section())


def test_story_backrefs_resolve():
    _check_backrefs(_real_section())


def test_good_fixture_is_itself_valid():
    """Guard: the mutation base must be a VALID section, else the twins below prove nothing."""
    section = _FIXTURE.read_text(encoding="utf-8")
    _check_three_blocks(section)
    _check_rubrics(section)
    _check_nfr8(section)
    _check_backrefs(section)


# ------------------------------------------------------------------- mutation helpers


def _field_region(lines, label, occ=1):
    """Return (start, end) line indices of the occ-th `label:` field (label line through the
    line before the next known-label / heading line)."""
    seen = 0
    for i, line in enumerate(lines):
        m = _LABEL_RE.match(line)
        if m and m.group(1) == label:
            seen += 1
            if seen == occ:
                j = i + 1
                while j < len(lines):
                    nxt = _LABEL_RE.match(lines[j])
                    if (nxt is not None) or lines[j].startswith("### ") or lines[j].startswith("## "):
                        break
                    j += 1
                return i, j
    raise AssertionError("field %s (occ %d) not found" % (label, occ))


def _replace_field(text, label, new_line, occ=1):
    lines = text.splitlines()
    s, e = _field_region(lines, label, occ)
    lines[s:e] = [new_line]
    return "\n".join(lines) + "\n"


def _drop_field(text, label, occ=1):
    lines = text.splitlines()
    s, e = _field_region(lines, label, occ)
    del lines[s:e]
    return "\n".join(lines) + "\n"


def _good():
    return _FIXTURE.read_text(encoding="utf-8")


# Each mutation -> (mutated_section, the check it must flip red)
def _mut_drop_rubric():
    return _drop_field(_good(), "attribution_rubric", 1), _check_three_blocks


def _mut_dup_heading():
    return _good().replace("### Promotion gate — bmad-code-review",
                           "### Promotion gate — bmad-dev-story", 1), _check_three_blocks


def _mut_fourth_heading():
    extra = (
        "\n### Promotion gate — bmad-ghost\n"
        "status: DEFERRED — not built (pending field evidence)\n"
        "decision_needed: x\nattribution_rubric: x\nnfr8_collision_check: x\npromotion_trigger: x\n"
    )
    return _good() + extra, _check_three_blocks


def _mut_remove_block():
    text = _good()
    idx = text.index("### Promotion gate — bmad-sprint-planning")
    return text[:idx], _check_three_blocks


def _mut_tbd_rubric():
    return _replace_field(_good(), "attribution_rubric", "attribution_rubric: TBD", 1), _check_rubrics


def _mut_cross_anchor():
    new = "attribution_rubric: satisfied ONLY by a sprint-status.yaml artifact shape entry."
    return _replace_field(_good(), "attribution_rubric", new, 1), _check_rubrics


def _mut_yagni_collision():
    new = "nfr8_collision_check: just YAGNI — we do not need it yet, revisit later."
    return _replace_field(_good(), "nfr8_collision_check", new, 1), _check_nfr8


def _mut_weak_trigger():
    new = "promotion_trigger: a named dev-story attribution_rubric match is sufficient on its own."
    return _replace_field(_good(), "promotion_trigger", new, 1), _check_nfr8


def _mut_phantom_row():
    text = _good().replace(
        "| bmad-sprint-planning | sprint-planning legal-sprint-status.yaml guardrail SHAPING fragment (SHAPING only) |",
        "| bmad-sprint-planning | sprint-planning legal-sprint-status.yaml guardrail SHAPING fragment (SHAPING only) |\n| bmad-ghost | phantom |",
        1,
    )
    return text, _check_backrefs


def _mut_injected_story_id():
    return _replace_field(_good(), "decision_needed",
                          "decision_needed: cut-vs-build — see story 3.2 for the dev-story shape.", 1), _check_backrefs


def _mut_injected_epics_path():
    return _replace_field(_good(), "decision_needed",
                          "decision_needed: cut-vs-build — see _bmad-output/planning-artifacts/epics-ucg-ready-planning.md.", 1), _check_backrefs


def _mut_dropped_cut_ability():
    lines = [ln for ln in _good().splitlines() if not ln.startswith("cut-ability:")]
    return "\n".join(lines) + "\n", _check_backrefs


_MUTATIONS = {
    "drop_rubric_field": _mut_drop_rubric,
    "duplicate_heading": _mut_dup_heading,
    "fourth_fragment_heading": _mut_fourth_heading,
    "remove_one_block": _mut_remove_block,
    "tbd_rubric": _mut_tbd_rubric,
    "cross_fragment_anchor": _mut_cross_anchor,
    "yagni_only_collision": _mut_yagni_collision,
    "weakened_trigger": _mut_weak_trigger,
    "phantom_fragment_row": _mut_phantom_row,
    "injected_story_id_3_2": _mut_injected_story_id,
    "injected_nonexistent_epics_path": _mut_injected_epics_path,
    "dropped_cut_ability_line": _mut_dropped_cut_ability,
}


@pytest.mark.parametrize("name", sorted(_MUTATIONS))
def test_anti_vacuous_mutation_flips_red(name):
    mutated, check = _MUTATIONS[name]()
    with pytest.raises(AssertionError):
        check(mutated)
