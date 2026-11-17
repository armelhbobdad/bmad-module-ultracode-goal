#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for the opt-in scoped backfill sweep (issue #241).

A backfill that staged two test files re-ran the whole cache-defeated
three-axis sweep, 72 checks over 22 minutes, though `references/execute.md`
step 5 had run that same sweep green two hours earlier at the commit the
backfill built on, and nothing but the two test files had changed since.

A new `[workflow]` key, `backfill_sweep`, ships as `full`. Set to `scoped`,
`references/gate.md` lets a backfill whose staged paths are all test files (a
toolchain's test-file naming, and a name no other tracked file mentions) re-run
only the checks of the packages that hold them and every check that reads files
across packages or git's file list, on top of a green full step-5 sweep at the
base commit. It applies only while the marker reads `scope=full` with no
`sweep=` line, `.commit-<story_id>`, `HEAD` and the `gate-backfill-base:`
commit agree, the step-5 capture is in the evidence folder and every fix stays
in those files, and any doubt runs the full sweep. It prints what it leaves
out, the flaky-red rule reads it at its own scope, and the marker keeps
`scope=full` beside a `sweep=` line naming both captures, which
`gate_eval.py --tests-ran` does not read. A commit that takes in a path outside
the set gets the full sweep again. Any other value of the key reads as `full`.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text with the #241 wording taken out (the pre-edit text) and
against one-clause mutants it must reject. A locality twin moves the new
paragraph out of the backfill steps. A replay picks the sweep form off
gate.md's own sentences for a set of story states. The knob resolves through
the real customization engine. Stated limit: this is a presence proof over
prose. It shows the instruction is in the file, not that an executor obeys it.

Stdlib + pytest only.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_GATE = _SKILL_ROOT / "references" / "gate.md"
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_CUSTOMIZE = _SKILL_ROOT / "customize.toml"
_ENGINE = Path(__file__).resolve().parent / "fixtures" / "engine" / "resolve_customization.py"
_FRAGMENT = _REPO / "changes" / "gate-backfill-scoped-sweep.yaml"
_DOCS = _REPO / "docs"

_HEAD = "**A backfill of test files alone may scope its sweep.**"
_CITED = '"A backfill of test files alone may scope its sweep"'
_ASSESSED = "The new commit is now the commit under assessment:"
_PRE_TRACE = "**A red backfill sweep ends the cycle at a re-loop.**"

_SHIPS = "`{workflow.backfill_sweep}` ships as `full`, `scoped` opts in, and any other value reads as `full`."
_BUILDS_ON = (
    "The scoped form builds on the full sweep `references/execute.md` step 5 ran green at the commit the backfill "
    "builds on, and re-runs only the checks the backfill's files can change."
)
_CHECKED = "Use it only while all of these hold, checked before the sweep and again before each re-run after a fix:"
_NO_CHAIN = (
    "- the story's `.tests-ran-<story_id>` marker reads `scope=full` and holds no `sweep=` line, so a scoped sweep "
    "never builds on another;"
)
_ONE_COMMIT = "- `.commit-<story_id>`, `git rev-parse HEAD` and the `gate-backfill-base:` commit are one commit;"
_BASE_CAPTURE = (
    "- `evidence-<story_id>/` holds the capture of a full sweep that went green at that commit (`sweep-step5-<short "
    "sha>.log`, or the numbered capture of its second sweep);"
)
_MENTIONS = (
    "and no file but itself and the run's own records (under `{workflow.implementation_artifacts}` and "
    "`{workflow.trace_output_dir}`) mentions its name, the file name without its last extension (`a.test` for "
    "`a.test.ts`), which you check with the Grep tool, searching for that name as a literal string, not a pattern, in "
    "hidden files too (`.storybook/main.ts`, say), and a mention it finds in a file git does not track counts as well;"
)
_TEST_FILE = (
    "- every path `git diff --cached --name-only --no-renames` lists is a test file: it follows its toolchain's "
    "test-file naming (`*.test.*`, `*.spec.*`, `test_*.py`, `*_test.py`, `*_test.go`, or a file in a Rust crate's "
    "top-level `tests/` folder), " + _MENTIONS
)
_FIXES = "- every fix step 2 makes stays inside those files."
_DOUBT = "When one does not hold, or you are in any doubt, run the full sweep: it is never wrong, only slower."
_RUNS = (
    "The scoped form runs, cache-defeated and printed, every check of each package that holds a staged path, and "
    "every check that reads files across packages or git's file list (a format, lint or type check, a scanner, a "
    "tracked-files gate, a per-file line cap, a build-input manifest) unless its own declared inputs exclude every "
    "staged path."
)
_LEAVES_OUT = (
    "It leaves out only the checks of a package that holds no staged path, and a repo-wide check whose own declared "
    "inputs exclude every staged path, and it prints each check it leaves out and why; when it cannot tell whether a "
    "check reads a staged path, it runs that check."
)
_CAPTURE = (
    "Capture it as `sweep-backfill-<short sha>.log`, as the full form is captured, with the staged paths it ran for, "
    "as `git diff --cached --name-only --no-renames` listed them, printed in it."
)
_FLAKY = (
    "A red in it takes step 2's route, and `references/execute.md` step 2 reads a red the story's changes do not "
    "explain the same way here, its second sweep run at the same tree and the same scope."
)
_MARKER = (
    "Step 3 then writes `scope=full`, since the full sweep at the base and this one together cover the backfill's "
    "tree, beside the `sweep=` line that names the green capture on each side; `gate_eval.py --tests-ran` reads only "
    "the `scope=` line."
)
_LOG_LINE = (
    "The story's next step 5 writes a marker without that line, so log its value in `.decision-log.md` too, on a "
    "line of its own that starts `backfill-sweep:`, never inside the `gate-backfill:` line a resume reads."
)
_FALLBACK = (
    "Step 4's commit can take in a path outside the staged set (a `pre-commit` job that stages a file it rewrote), "
    "so step 5 opens with a check, which a resume that starts at step 5 runs too: before it refreshes "
    "`.commit-<story_id>`, when the marker carries a `sweep=` line and `git diff --name-only --no-renames <base> "
    "HEAD`, with `<base>` the `gate-backfill-base:` commit, lists a path the scoped capture's printed staged list "
    "does not hold, run the full sweep on `HEAD`. When it is green, write the marker again from it with no `sweep=` "
    "line, then go on with step 5. A red in it ends the cycle at a re-loop as \"A red backfill sweep ends the cycle "
    "at a re-loop\" below does, except that its `assessed-commit:` line names the backfill commit, `HEAD`, and the "
    "files are already committed; that logged verdict takes a resume out of `references/execute.md`'s fifth resume "
    "case."
)
# Step 5's own sentence keeps its pinned opening; the pointer goes at its end.
_STEP5_POINTER = (
    "When the marker carries a `sweep=` line, this step opens, before its refresh, with the check \"A backfill of "
    "test files alone may scope its sweep\" below gives, on a resume that starts here too."
)
_SECOND_RUN = (
    "The second run a row that reads `GREEN` gets (\"A reported gap stays open until a later pass measures it "
    "closed\" below) still takes the test command of the story's full sweep: the scoped form changes only this sweep."
)

# Each #241 edit outside the new paragraph as (pre-edit text, live text).
_SWITCH = (
    "as `references/execute.md` step 5 runs it. A red",
    "as `references/execute.md` step 5 runs it. When `{workflow.backfill_sweep}` is `scoped` and every condition of "
    + _CITED + " below holds, this sweep, and each re-run after a fix, takes that paragraph's scoped form instead; "
    "any other value of the key, or a condition that does not hold, keeps it the full sweep. A red",
)
_STEP3 = (
    "never re-derived, and `scope=full`.",
    "never re-derived, and `scope=full`. After the scoped form, it also carries a `sweep=` line naming the green "
    "capture of the full sweep that form builds on and the green capture of this one, "
    "`sweep=<base capture>+<backfill capture>` (" + _CITED + " below), and still says `scope=full`.",
)
_COMPOSED = (
    "was the full three-axis sweep and passes the verdict through;",
    "was the full three-axis sweep, or, beside a `sweep=` line, the full sweep at the commit a backfill of test files "
    "alone built on together with that backfill's scoped sweep (" + _CITED + ", under \"Backfill the gate "
    "evidence\"), and passes the verdict through;",
)
_INSTRUMENT = (
    "(every assessor over a `scope=full` sweep, with automate",
    "(every assessor over a `scope=full` sweep, a backfill's scoped sweep with the full one it builds on included, "
    "with automate",
)
_STEP5 = (
    "so the re-commit is denied.\n",
    "so the re-commit is denied. When `{workflow.backfill_sweep}` is `scoped`, capture this step's sweep in "
    "`evidence-<story_id>/` as `sweep-step5-<short sha>.log` (\"Evidence never goes in scratch\", above): the gate's "
    "scoped backfill sweep builds on that capture and names it (`references/gate.md`, " + _CITED + "), and without "
    "it the gate runs the full sweep. No marker this file writes carries a `sweep=` line.\n",
)
_GATE_EDITS = (_SWITCH, _STEP3, _COMPOSED, _INSTRUMENT)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _paragraph(text: str) -> str:
    """The new paragraph with its condition list, up to the red-sweep paragraph."""
    if _HEAD not in text:
        return ""
    start = text.index(_HEAD)
    end = text.find("\n\n" + _PRE_TRACE, start)
    return text[start : end if end != -1 else len(text)]


def _step(text: str, opener: str, next_opener: str) -> str:
    start = text.index(opener)
    return text[start : text.index(next_opener, start)]


def _step2(text: str) -> str:
    return _step(text, "\n2. With them staged", "\n3. Once the sweep is green")


def _step3(text: str) -> str:
    return _step(text, "\n3. Once the sweep is green", "\n4. Run `references/execute.md` step 4's")


def _sweep_and(text: str) -> str:
    start = text.index("**The sweep-scope AND")
    return text[start : text.index("\n\n", start)]


def _delta(text: str) -> str:
    start = text.index("**The delta cycle profile")
    return text[start : text.index("\n\n", start)]


def _backfill_step5(text: str) -> str:
    return _step(text, "\n5. Refresh `.commit-<story_id>` from `HEAD`", "\n\nThe new commit is now")


def _step5(text: str) -> str:
    return next(line for line in text.splitlines() if line.startswith("5. **Re-verify on the committed HEAD.**"))


def _pre_edit(gate: str) -> str:
    paragraph = _paragraph(gate)
    if paragraph:
        gate = gate.replace(paragraph + "\n\n", "", 1)
    gate = gate.replace(" " + _STEP5_POINTER, "", 1)
    for old, new in _GATE_EDITS:
        gate = gate.replace(new, old, 1)
    return gate


def _execute_pre_edit(execute: str) -> str:
    return execute.replace(_STEP5[1], _STEP5[0], 1)


def test_the_pre_edit_texts_are_real_reconstructions():
    live, execute = _read(_GATE), _read(_EXECUTE)
    pre, execute_pre = _pre_edit(live), _execute_pre_edit(execute)
    for old, new in _GATE_EDITS:
        assert live.count(new) == 1, new[:80]
        assert pre.count(old) == 1 and new not in pre, old[:80]
    assert _HEAD not in pre and _CITED not in pre and "backfill_sweep" not in pre and "sweep=" not in pre
    assert len(live) - len(pre) == (
        len(_paragraph(live)) + 2 + len(_STEP5_POINTER) + 1 + sum(len(new) - len(old) for old, new in _GATE_EDITS)
    )
    assert execute.count(_STEP5[1]) == 1 and "backfill_sweep" not in execute_pre
    # The step after the commit's paragraph is the red-sweep paragraph again.
    assert "turns like any wait (`references/execute.md`, \"Waiting spends turns\").\n\n" + _PRE_TRACE in pre


# --- the knob -------------------------------------------------------------------------


def _resolve(tree: Path, key: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(_ENGINE), "--skill", str(tree / "skills" / "ultracode-goal"), "--key", key],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_key_ships_full_and_a_team_layer_overrides_it(tmp_path):
    workflow = tomllib.loads(_read(_CUSTOMIZE))["workflow"]
    # Subscript, never `.get(..., "full")`: a defaulted read would pass against a
    # customize.toml that never declared the key.
    assert workflow["backfill_sweep"] == "full"
    skill = tmp_path / "skills" / "ultracode-goal"
    skill.mkdir(parents=True)
    shutil.copy2(_CUSTOMIZE, skill / "customize.toml")
    assert _resolve(tmp_path, "workflow.backfill_sweep") == {"workflow.backfill_sweep": "full"}
    custom = tmp_path / "_bmad" / "custom"
    custom.mkdir(parents=True)
    (custom / "ultracode-goal.toml").write_text('[workflow]\nbackfill_sweep = "scoped"\n', encoding="utf-8")
    assert _resolve(tmp_path, "workflow.backfill_sweep") == {"workflow.backfill_sweep": "scoped"}


def test_the_key_is_read_where_the_sweep_is_chosen_and_where_its_base_is_captured():
    assert "{workflow.backfill_sweep}" in _step2(_read(_GATE))
    assert "{workflow.backfill_sweep}" in _step5(_read(_EXECUTE))
    comment = _read(_CUSTOMIZE).split("backfill_sweep = ", 1)[0].rsplit("# --- ", 1)[1]
    assert "any value other than \"scoped\" reads as \"full\"" in _flat(comment.replace("# ", ""))
    comment = _flat(comment.replace("# ", ""))
    assert "mentioned by no other file outside the run's own records" in comment and "tracked file" not in comment
    assert "(unless its own declared inputs exclude every staged path)" in comment
    assert "allowlist_commands" not in comment
    # The first `allowlist_commands` in the file is still the key itself.
    assert _read(_CUSTOMIZE).split("allowlist_commands", 1)[1].startswith(" = [")


# --- the paragraph --------------------------------------------------------------------


def _is_placed_between_the_commit_and_the_red_sweep(text: str) -> bool:
    """Once in the file, in the backfill section, right after the paragraph
    that makes the backfill commit the commit under assessment and right
    before the red-sweep paragraph."""
    if text.count(_HEAD) != 1:
        return False
    backfill = text[text.index("## Backfill the gate evidence") : text.index("## Measure the commit")]
    if _HEAD not in backfill:
        return False
    before = backfill[: backfill.index(_HEAD)]
    previous = before.rstrip("\n")
    previous = previous[previous.rfind("\n\n") + 2 :]
    return bool(
        before.endswith("\n\n") and previous.startswith(_ASSESSED) and _paragraph(text) + "\n\n" + _PRE_TRACE in text
    )


def _ships_full(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return _SHIPS in flat and _BUILDS_ON in flat


def _holds_every_condition(paragraph: str) -> bool:
    lines = paragraph.splitlines()
    items = (_NO_CHAIN, _ONE_COMMIT, _BASE_CAPTURE, _TEST_FILE, _FIXES)
    return _CHECKED in _flat(paragraph) and all(item in lines for item in items) and _DOUBT in _flat(paragraph)


def _runs_what_the_files_can_change(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return _RUNS in flat and _LEAVES_OUT in flat and _CAPTURE in flat


def _reads_a_red_at_its_own_scope(paragraph: str) -> bool:
    return _FLAKY in _flat(paragraph)


def _writes_the_composed_marker(paragraph: str) -> bool:
    return _MARKER in _flat(paragraph) and _FALLBACK in _flat(paragraph)


def _logs_the_sweep_value(paragraph: str) -> bool:
    return _LOG_LINE in _flat(paragraph)


def _leaves_the_second_run_alone(paragraph: str) -> bool:
    return _SECOND_RUN in _flat(paragraph)


_PARAGRAPH_RULES = {
    "ships-full": _ships_full,
    "conditions": _holds_every_condition,
    "runs": _runs_what_the_files_can_change,
    "flaky": _reads_a_red_at_its_own_scope,
    "marker": _writes_the_composed_marker,
    "log-line": _logs_the_sweep_value,
    "second-run": _leaves_the_second_run_alone,
}


def test_the_paragraph_sits_between_the_commit_and_the_red_sweep():
    assert _is_placed_between_the_commit_and_the_red_sweep(_read(_GATE))


def test_locality_twin_rejects_the_paragraph_moved_out_of_the_backfill_steps():
    live = _read(_GATE)
    paragraph = _paragraph(live)
    moved = live.replace(paragraph + "\n\n", "", 1)
    moved = moved.replace("## Measure the commit, not the working tree\n", "## Measure the commit, not the working "
                          "tree\n\n" + paragraph + "\n", 1)
    assert moved != live
    assert not _is_placed_between_the_commit_and_the_red_sweep(moved)
    assert _ships_full(_paragraph(moved))


@pytest.mark.parametrize("rule", sorted(_PARAGRAPH_RULES))
def test_each_rule_of_the_paragraph_holds_and_is_absent_before_the_edit(rule):
    live = _read(_GATE)
    assert _PARAGRAPH_RULES[rule](_paragraph(live))
    assert not _PARAGRAPH_RULES[rule](_paragraph(_pre_edit(live)))


def _switches_in_step_2(text: str) -> bool:
    step = _flat(_step2(text))
    first = "run the full three-axis sweep over the main tree, cache-defeated and printed"
    pointer = "A red `references/execute.md` step 2 reads as not yet a red"
    return bool(
        _SWITCH[1] in step and first in step and pointer in step and step.index(first) < step.index(pointer)
    )


def _step3_names_both_captures(text: str) -> bool:
    return _STEP3[1] in _flat(_step3(text))


def _the_cap_reads_a_composed_marker_as_full(text: str) -> bool:
    paragraph = _flat(_sweep_and(text))
    return _COMPOSED[1] in paragraph and chr(0x2014) not in paragraph


def _the_full_instrument_takes_a_composed_sweep(text: str) -> bool:
    return _INSTRUMENT[1] in _flat(_delta(text))


def _step5_opens_with_the_check(text: str) -> bool:
    """Step 5, which a normal backfill and a resume both pass through, keeps
    its pinned opening and points at the check that runs before its refresh,
    and the check itself names that resume."""
    step = _flat(_backfill_step5(text))
    paragraph = _flat(_paragraph(text))
    return bool(
        step.strip().startswith("5. Refresh `.commit-<story_id>` from `HEAD`")
        and _STEP5_POINTER in step
        and "which a resume that starts at step 5 runs too" in paragraph
        and "before it refreshes `.commit-<story_id>`" in paragraph
    )


_GATE_RULES = {
    "switch": _switches_in_step_2,
    "step-3": _step3_names_both_captures,
    "composed": _the_cap_reads_a_composed_marker_as_full,
    "instrument": _the_full_instrument_takes_a_composed_sweep,
    "step-5-check": _step5_opens_with_the_check,
}


@pytest.mark.parametrize("rule", sorted(_GATE_RULES))
def test_each_rule_of_the_gate_holds_and_is_absent_before_the_edit(rule):
    live = _read(_GATE)
    assert _GATE_RULES[rule](live)
    assert not _GATE_RULES[rule](_pre_edit(live))


def _step5_captures_the_base(text: str) -> bool:
    return _STEP5[1].rstrip("\n") in _step5(text)


def test_step_5_captures_the_base_only_when_the_key_is_scoped():
    execute = _read(_EXECUTE)
    assert _step5_captures_the_base(execute)
    assert not _step5_captures_the_base(_execute_pre_edit(execute))


_MUTANTS = (
    ("ships-full", "and any other value reads as `full`.", "and any other value reads as `scoped`."),
    ("conditions", " and holds no `sweep=` line, so a scoped sweep never builds on another;", ";"),
    ("conditions", "and the `gate-backfill-base:` commit are one commit;", "are one commit;"),
    ("conditions", "holds the capture of a full sweep that went green at that commit", "holds a capture"),
    ("conditions", "and no file but itself and the run's own records (under", "and no file (under"),
    ("conditions", "the file name without its last extension (`a.test` for `a.test.ts`)", "its stem"),
    ("conditions", ", and a mention it finds in a file git does not track counts as well;", ";"),
    ("conditions", "searching for that name as a literal string, not a pattern,", "searching for that name"),
    ("conditions", " in hidden files too (`.storybook/main.ts`, say),", ""),
    ("conditions", "it follows its toolchain's test-file naming", "it sits under a test folder or follows its "
     "toolchain's test-file naming"),
    ("conditions", "- every fix step 2 makes stays inside those files.", "- step 2 may fix any path."),
    ("conditions", "checked before the sweep and again before each re-run after a fix:", "checked once:"),
    ("conditions", "or you are in any doubt, run the full sweep", "run the full sweep"),
    ("runs", "The scoped form runs, cache-defeated and printed,", "The scoped form runs"),
    ("runs", ", and every check that reads files across packages or git's file list", ""),
    ("runs", "and it prints each check it leaves out and why;", "and it prints nothing it leaves out;"),
    ("runs", ") unless its own declared inputs exclude every staged path.", ")."),
    ("runs", "when it cannot tell whether a check reads a staged path, it runs that check.", "it skips any other."),
    ("flaky", "its second sweep run at the same tree and the same scope.", "its second sweep run in full."),
    ("marker", "Step 3 then writes `scope=full`,", "Step 3 then writes `scope=scoped`,"),
    ("marker", "write the marker again from it with no `sweep=` line, then", "keep the marker, then"),
    ("marker", "lists a path the scoped capture's printed staged list does not hold", "lists any path"),
    (
        "marker",
        "except that its `assessed-commit:` line names the backfill commit, `HEAD`, and the files are already "
        "committed;",
        "naming the `gate-backfill-base:` commit;",
    ),
    ("runs", ", with the staged paths it ran for, as `git diff --cached --name-only --no-renames` listed them, "
     "printed in it.", "."),
    ("log-line", "so log its value in `.decision-log.md` too,", "so let it go,"),
    ("log-line", ", never inside the `gate-backfill:` line a resume reads.", ", or inside the `gate-backfill:` line."),
    ("second-run", "still takes the test command of the story's full sweep", "takes this sweep's command"),
)


@pytest.mark.parametrize(
    ("rule", "old", "new"), [pytest.param(*m, id=f"{m[0]}-{i}") for i, m in enumerate(_MUTANTS)]
)
def test_each_rule_of_the_paragraph_rejects_a_one_clause_mutant(rule, old, new):
    live = _read(_GATE)
    assert live.count(old) == 1, old
    mutant = live.replace(old, new, 1)
    assert mutant != live, "the mutant must actually change the text"
    predicate = _PARAGRAPH_RULES[rule]
    assert predicate(_paragraph(live)) and not predicate(_paragraph(mutant))


_GATE_MUTANTS = (
    ("switch", "and each re-run after a fix, takes", "takes"),
    ("switch", "any other value of the key, or a condition that does not hold, keeps it the full sweep",
     "any other value of the key keeps it the full sweep"),
    ("step-3", "and still says `scope=full`.", "and says `scope=scoped`."),
    ("composed", "the full sweep at the commit a backfill of test files alone built on together with",
     "a backfill's sweep without"),
    ("instrument", "a backfill's scoped sweep with the full one it builds on included, ", ""),
    # A resume that starts at step 5 runs the check: each half of that rule is load-bearing.
    ("step-5-check", ", on a resume that starts here too.", "."),
    ("step-5-check", ", which a resume that starts at step 5 runs too:", ":"),
    (
        "step-5-check",
        "this step opens, before its refresh, with the check",
        "this step ends, after its refresh, with the check",
    ),
)


@pytest.mark.parametrize(
    ("rule", "old", "new"), [pytest.param(*m, id=f"{m[0]}-{i}") for i, m in enumerate(_GATE_MUTANTS)]
)
def test_each_rule_of_the_gate_rejects_a_one_clause_mutant(rule, old, new):
    live = _read(_GATE)
    assert live.count(old) == 1, old
    mutant = live.replace(old, new, 1)
    assert mutant != live, "the mutant must actually change the text"
    assert _GATE_RULES[rule](live) and not _GATE_RULES[rule](mutant)


def test_the_step_5_rule_rejects_a_one_clause_mutant():
    execute = _read(_EXECUTE)
    old = "and without it the gate runs the full sweep."
    assert execute.count(old) == 1
    mutant = execute.replace(old, "and without it the gate runs the scoped form anyway.", 1)
    assert _step5_captures_the_base(execute) and not _step5_captures_the_base(mutant)


# --- the form the gate picks, replayed on its own sentences ---------------------------


_TEST_NAME = re.compile(r"(?:^|/)(?:[^/]+\.(?:test|spec)\.[^/]+|test_[^/]+\.py|[^/]+_test\.(?:py|go))$")


def _is_test_file(path: str, gate: str, mentions: dict[str, str]) -> bool:
    """A staged path's test-file reading off the bullet: its naming, then each
    mention of its name (the file name without its last extension) by where it
    sits: `records` (the run's own), `tracked` or `untracked`."""
    paragraph = _flat(_paragraph(gate))
    named = bool(_TEST_NAME.search(path)) or bool(re.match(r"(?:[^/]+/)*tests/[^/]+\.rs$", path))
    where = mentions.get(Path(path).stem)
    counted: set[str] = set()
    if "mentions its name, the file name without its last extension" in paragraph:
        counted.add("tracked")
        if "a mention it finds in a file git does not track counts as well" in paragraph:
            counted.add("untracked")
        if "no file but itself and the run's own records" not in paragraph:
            counted.add("records")
    return named and where not in counted


def _form(gate: str, state: dict) -> str:
    """`scoped` or `full`: the form gate.md's sentences give a backfill sweep."""
    flat = _flat(gate)
    paragraph = _paragraph(gate)
    lines = paragraph.splitlines()
    if _SWITCH[1] not in flat:
        return "full"
    if state["key"] != "scoped" and "and any other value reads as `full`." in flat:
        return "full"
    if state["marker_has_sweep"] and _NO_CHAIN in lines:
        return "full"
    if not state["one_commit"] and _ONE_COMMIT in lines:
        return "full"
    if not state["base_capture"] and _BASE_CAPTURE in lines:
        return "full"
    if not all(_is_test_file(path, gate, state["mentions"]) for path in state["staged"]):
        return "full"
    return "scoped"


_SCOPED = {
    "key": "scoped",
    "marker_has_sweep": False,
    "one_commit": True,
    "base_capture": True,
    "staged": ["packages/web/src/panel.test.ts", "tests/test_api.py"],
    "mentions": {},
}


@pytest.mark.parametrize(
    ("case", "change", "form"),
    [
        ("all-hold", {}, "scoped"),
        ("key-unset", {"key": "full"}, "full"),
        ("key-mistyped", {"key": "Scoped"}, "full"),
        ("composed-marker", {"marker_has_sweep": True}, "full"),
        ("moved-head", {"one_commit": False}, "full"),
        ("no-base-capture", {"base_capture": False}, "full"),
        ("a-helper", {"staged": ["tests/helpers.ts"]}, "full"),
        ("a-shared-test-module", {"mentions": {"test_api": "tracked"}}, "full"),
        ("named-in-an-untracked-file", {"mentions": {"panel.test": "untracked"}}, "full"),
        ("named-only-in-the-runs-records", {"mentions": {"test_api": "records", "panel.test": "records"}}, "scoped"),
        ("a-rust-integration-test", {"staged": ["crates/core/tests/parse.rs"]}, "scoped"),
    ],
)
def test_replay_picks_the_scoped_form_only_when_every_condition_holds(case, change, form):
    assert _form(_read(_GATE), {**_SCOPED, **change}) == form


def test_replay_on_the_pre_edit_text_always_runs_the_full_sweep():
    assert _form(_pre_edit(_read(_GATE)), _SCOPED) == "full"


@pytest.mark.parametrize(
    ("case", "old", "new", "change"),
    [
        ("chains", " and holds no `sweep=` line, so a scoped sweep never builds on another;", ";",
         {"marker_has_sweep": True}),
        ("ignores-an-untracked-mention", ", and a mention it finds in a file git does not track counts as well;", ";",
         {"mentions": {"panel.test": "untracked"}}),
        ("trusts-a-shared-module", _MENTIONS, "and that is all;", {"mentions": {"test_api": "tracked"}}),
        ("needs-no-base", "- `evidence-<story_id>/` holds the capture of a full sweep that went green at that commit "
         "(`sweep-step5-<short sha>.log`, or the numbered capture of its second sweep);\n", "",
         {"base_capture": False}),
        ("reads-any-value", "and any other value reads as `full`.", "and any other value reads as `scoped`.",
         {"key": "Scoped"}),
    ],
)
def test_replay_without_a_condition_scopes_a_sweep_it_must_run_in_full(case, old, new, change):
    live = _read(_GATE)
    mutant = live.replace(old, new, 1)
    assert mutant != live, case
    state = {**_SCOPED, **change}
    assert _form(live, state) == "full"
    assert _form(mutant, state) == "scoped"


# --- house rules ----------------------------------------------------------------------


def test_the_new_prose_breaks_no_house_rule():
    live = _read(_GATE)
    added = (_paragraph(live), *(new for _, new in _GATE_EDITS), _STEP5[1])
    for piece in added:
        assert chr(0x2014) not in piece
        assert "owned" not in piece
        assert "open P0 gap" not in piece
        # No command the prose gives leads with an environment variable.
        assert not re.search(r"`[A-Z_]+=\S+ ", piece)
    def run_the_gate(text: str) -> str:
        return text[text.index("## Run the gate") : text.index("## Route on the verdict")]

    # No new "moved" in "## Run the gate", which the sweep-scope AND sits in.
    assert run_the_gate(live).count("moved") == run_the_gate(_pre_edit(live)).count("moved")
    # The sweep-scope AND line now holds no em dash at all.
    assert chr(0x2014) not in _sweep_and(live)
    # A remove verb never shares a sentence with the evidence folder.
    remove = re.compile(r"\b(?:remov\w*|delet\w*|discard\w*|wip\w*|eras\w*|prun\w*|purg\w*|drop\w*)\b", re.I)
    for piece in added:
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z`*(\"-])", _flat(piece)):
            assert not ("evidence-<story_id>" in sentence and remove.search(sentence)), sentence


# --- the docs and the fragment --------------------------------------------------------

_DOCS_SAY = {
    "gate-model.md": (
        "With the opt-in `backfill_sweep = \"scoped\"` in `customize.toml`, a backfill that stages test files alone",
        "Its marker then keeps `scope=full` beside a `sweep=` line naming the two green captures it rests on, which "
        "the script does not read, and one scoped sweep never builds on another.",
        "The gate writes the marker too,",
        "unless that check's own declared inputs exclude every staged path,",
    ),
    "troubleshooting.md": ("A marker that carries a `sweep=` line beside `scope=full` is no cause",),
    "architecture.md": ("the opt-in `backfill_sweep`",),
    "_internal/STABILITY.md": ("`allowlist_commands`, `backfill_sweep`, `on_epic_complete`",),
    "operating-tips.md": (
        "**Turn on `backfill_sweep = \"scoped\"` when a backfill's full sweep costs you more than it tells you.**",
        "the green capture step 5 left in `evidence-<story_id>/` as `sweep-step5-<short sha>.log`",
        "Set the key before the story's Execute runs: a step 5 that ran with it unset saved no such capture, and the "
        "gate then runs the full sweep.",
    ),
}


@pytest.mark.parametrize("doc", sorted(_DOCS_SAY))
def test_the_docs_say_what_the_key_does(doc):
    text = _flat(_read(_DOCS / doc))
    assert [s for s in _DOCS_SAY[doc] if s not in text] == []


_FRAGMENT_SAYS = (
    "type: added",
    "scope: ultracode-goal",
    "issues: [241]",
    "`backfill_sweep`",
    "`full` by default",
    "`scoped`",
    "re-runs only the checks of the packages that hold those files and every check that reads files across packages "
    "or git's file list",
    "prints each check it leaves out",
    "keeps `scope=full` and gains a `sweep=` line naming both captures",
    "so `gate_eval.py --tests-ran` reads it as before",
    "Any other backfill, or any other value of the key, runs the full sweep",
)


def test_the_fragment_says_what_the_prose_does():
    fragment = _flat(_read(_FRAGMENT))
    assert chr(0x2014) not in fragment
    assert [s for s in _FRAGMENT_SAYS if s not in fragment] == []
