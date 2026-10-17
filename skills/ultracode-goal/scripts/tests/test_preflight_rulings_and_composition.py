#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Two drafting rules for preflight (references/preflight.md).

- Step 2: a file remediation writes for many later agents to apply (a
  cross-story arbitration) may only apply a decision an artifact already
  makes, each entry citing it; settling an open question there would hide a
  RED from the scan. The file goes stale as later decisions overtake its
  entries, so it numbers them, keeps a `Status:` line and a supersession block
  that strikes an overtaken entry by number without editing its text, and
  every prompt that hands it out says to read that block first.
- Step 3: stories each scoped to one component can leave a surface that no
  story mounts. The gap exists only in their union, so the semantic scan, the
  one whole-corpus reader, hunts for it, scoped to a user interface, with a
  fixed `kind` and `source` so the same gap keeps one RED id across scans.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_preflight_rulings_and_composition.py -v
"""

from __future__ import annotations

from pathlib import Path

PREFLIGHT = Path(__file__).resolve().parent.parent.parent / "references" / "preflight.md"
RED_KINDS = ("undecided-product", "undecided-architecture", "contradiction", "undefinable-done")


def _section(heading: str) -> str:
    text = PREFLIGHT.read_text(encoding="utf-8")
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start : end if end != -1 else len(text)]


def _ruling_rule() -> str:
    step2 = _section("## 2. Auto-remediation pass")
    start = step2.find("**A ruling that later agents apply.**")
    assert start != -1, "step 2 lost the ruling rule"
    end = step2.find("Log each supersession to `.decision-log.md`.", start)
    assert end != -1, "the ruling rule no longer ends on its log line"
    return step2[start:end]


def test_a_ruling_applies_a_decision_an_artifact_already_makes():
    rule = _ruling_rule()
    assert "it may only **apply** a decision an artifact already makes" in rule
    assert "Each entry cites the artifact line that decides it." in rule
    assert "is not a ruling: it is a step-3 RED" in rule
    # The scan reads what the stories were made to follow.
    assert "Hand the ruling file to the step-3 subagent" in rule


def test_a_ruling_file_keeps_its_own_supersession_record():
    rule = _ruling_rule()
    assert "The file lives in the run folder beside `.decision-log.md`" in rule
    assert "Number each entry" in rule
    assert "A `Status:` line at its head names the entries in force" in rule
    assert "`~~R3~~ replaced by R7: <why>; re-touched: <each artifact already edited under R3>`" in rule
    assert "entry `R3`'s own text stays as it was" in rule
    # The load-bearing line: the consumers are told the file may be partly dead.
    assert "Every prompt that hands the file to an agent says to read the supersession block first" in rule


def _composition_bullet() -> str:
    step3 = _section("## 3. Semantic intervention scan")
    hunt = [line for line in step3.splitlines() if line.startswith("- ")]
    hits = [line for line in hunt if line.startswith("- a surface the Epic ships that no story composes.")]
    assert len(hits) == 1, hits
    # It sits in the hunt list itself, after the undefinable-done item.
    assert hunt.index('- a story whose "done" is undefinable from the artifacts,') + 1 == hunt.index(hits[0])
    return hits[0]


def test_the_scan_hunts_a_surface_no_story_composes():
    bullet = _composition_bullet()
    assert "check the union" in bullet
    assert "must name the story that does the mounting" in bullet


def test_the_composition_hunt_is_scoped_to_a_user_interface():
    bullet = _composition_bullet()
    assert "This covers a user interface only: a page, screen or other entry point a user reaches." in bullet
    assert "a child component its parent renders in the same story" in bullet
    assert "an Epic that ships components for others to compose" in bullet
    assert "a mount the exclusion assigns to a named story of another Epic, which is a concern" in bullet


def test_the_composition_red_has_one_kind_and_one_source():
    # A RED id is minted from kind and path, so a kind or anchor that varies
    # between scans would ask the operator the same question again.
    bullet = _composition_bullet()
    kinds = [kind for kind in RED_KINDS if "`%s`" % kind in bullet]
    assert kinds == ["undecided-architecture"], kinds
    assert "with `source` at the line of the story that creates the surface" in bullet
