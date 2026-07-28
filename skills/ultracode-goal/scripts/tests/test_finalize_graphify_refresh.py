#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""The optional graphify knowledge-graph refresh: one knob, finalize-only.

`graphify_integration` has exactly two values, `off` (shipped default, a complete
no-op) and `refresh`. In `refresh` mode the terminal stage delegates ONE
incremental rebuild of the project's `graphify-out/` and nothing else: the
delegation is hard time-boxed, a failure is logged once and never retried, and an
absent graphify is a SILENT no-op that leaves the run byte-identical to an `off`
run. The delegation is graphify's `update` subcommand, which re-extracts code
files against the existing graph with no LLM call, so an unattended exit step
spends no API budget and makes no network request.

Two halves, and the second is what makes the first mean anything:

- Positive: static prose-contract assertions over `references/finalize.md`'s
  `## Knowledge-graph refresh (optional)` section plus a tomllib parse and a live
  drive of the VENDORED merge engine against the shipped `customize.toml`.
- Negative: a sweep proving the token `graphify` reaches NO preflight, per-story,
  gate, hook or envelope surface. A negative assertion's failure mode is being
  vacuously green, so it ships with a positive control that feeds the SAME
  helper a planted call and requires it to flag, and with a per-path
  `is_file()` assertion so a renamed or mistyped path reds instead of silently
  sweeping nothing.

**Backtick convention, deliberate and load-bearing.** Inside the finalize
section, every backticked BARE lowercase word is read here as a mode literal, and
the set must be exactly `{off, refresh}` — that is what makes the closed enum
mechanically checkable, so a re-added `query` (or any third mode) reds. Spell
non-mode bare words in that section without backticks; every other token the
section needs (`graphify update`, `command -v graphify`, `graphify-out/graph.json`,
`WARN graphify-refresh-failed`, `.decision-log.md`) already carries a character
that excludes it. That is why the delegation is written as `graphify update` and
never as a bare `update`: the bare form would be read as a third mode literal and
red the closed-enum assertion, which is the convention working, not fighting.

Anti-vacuous twin: `fixtures/finalize_no_graphify_section.md` is a verbatim
pre-edit snapshot of `references/finalize.md`, taken before this contract landed.
It must satisfy ZERO of the section checks the live file satisfies, and a
twin-integrity assertion pins it as a real snapshot rather than an emptied file
that trivially lacks the section.

Stated limit: these are **presence proofs** over shipped prose and config. They
show the knob ships off, that the delegation is declared incremental and bounded,
and that no other shipped surface names graphify. They make NO claim that an
executor obeys the section, and no live graphify run is performed — the
behavioral consequence (a real `graphify-out/` refreshed on a developer's
machine) is deliberately outside the gate, which is the whole point of the
advisory posture.

Stdlib + pytest only.

Run: uv run --with pytest pytest \
       skills/ultracode-goal/scripts/tests/test_finalize_graphify_refresh.py -v
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
_TESTS = Path(__file__).resolve().parent
_FIXTURES = _TESTS / "fixtures"

_FINALIZE = _SKILL_ROOT / "references" / "finalize.md"
_CUSTOMIZE = _SKILL_ROOT / "customize.toml"

# The real engine, vendored under fixtures/ so the suite stays hermetic in CI
# (the real _bmad/ tree is gitignored and absent on a clean checkout).
REAL_ENGINE = _FIXTURES / "engine" / "resolve_customization.py"

# Verbatim pre-edit snapshot of finalize.md, captured before this story's edit.
_FIX_PRE_EDIT = _FIXTURES / "finalize_no_graphify_section.md"

_HEADING = "## Knowledge-graph refresh"
_TERMINAL_HEADING = "## Workflow health check"

# The closed value space. Nothing else is a legal mode.
_MODES = {"off", "refresh"}

# The surfaces graphify must never reach: the preflight scan, the per-story
# spine (its prose, its fan-out driver), the gate that judges a story, the two
# hooks that can deny or stop a run, and the adapter that builds the terminal
# envelope. `references/gate.md` is swept alongside `gate_eval.py` because the
# gate's PROSE surface is just as natural a place to write a gate-side call as
# its script is.
_SWEPT = (
    "references/preflight.md",
    "references/execute.md",
    "references/gate.md",
    "assets/execute-epic.workflow.js",
    "scripts/gate_eval.py",
    "scripts/headless_envelope.py",
    "scripts/hooks/guard_pretooluse.py",
    "scripts/hooks/budget_stop.py",
)


# --- helpers -----------------------------------------------------------------


def _section(text: str | None = None) -> str:
    """The `## Knowledge-graph refresh` section body, or "" when absent.

    Returns "" rather than raising so the pre-edit twin can be run through the
    same checks the live file is run through, instead of through a different
    (and therefore weaker) code path.
    """
    text = text if text is not None else _FINALIZE.read_text(encoding="utf-8")
    match = re.search(
        rf"^{re.escape(_HEADING)}[^\n]*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    return match.group(1) if match else ""


def _mode_literals(section: str) -> set[str]:
    """Every backticked BARE lowercase word in the section.

    See the module docstring: inside this one section that shape is reserved for
    mode literals, which is what makes the enum closed rather than merely
    documented.
    """
    return {
        tok
        for tok in re.findall(r"`([^`]*)`", section)
        if re.fullmatch(r"[a-z][a-z-]*", tok)
    }


def _delegation_lines(section: str) -> list[str]:
    """Non-empty lines inside the section's fenced code blocks.

    The delegation is the only fenced content in the section; the config resolve
    is an inline span, matching how the epic-complete hook spells its own.
    """
    lines: list[str] = []
    for block in re.findall(r"^```[^\n]*\n(.*?)^```", section, re.MULTILINE | re.DOTALL):
        lines.extend(line.strip() for line in block.splitlines() if line.strip())
    return lines


def _files_naming_graphify(paths: list[Path]) -> list[str]:
    """The subset of `paths` whose text names graphify, by name.

    Case-insensitive and substring-based on purpose: this is a sweep for a
    forbidden token, so it should over-match rather than be dodged by casing or
    by the token sitting inside a longer word.
    """
    return sorted(p.name for p in paths if "graphify" in p.read_text(encoding="utf-8").lower())


def _swept_paths() -> list[Path]:
    return [_SKILL_ROOT / rel for rel in _SWEPT]


# The section contract, as one dict of named checks, so the pre-edit twin can be
# measured against the SAME matcher the live file passes.
_SECTION_CHECKS = {
    # AC-1 shape: the knob resolves through the same engine invocation the
    # epic-complete hook uses.
    "resolves the knob through resolve_customization.py": lambda s: (
        "resolve_customization.py --skill {skill-root} --key workflow.graphify_integration" in s
    ),
    "names both modes": lambda s: _MODES <= _mode_literals(s),
    "pins off as a complete no-op": lambda s: "complete no-op" in s,
    # detect-and-degrade
    "names the PATH probe": lambda s: "command -v graphify" in s,
    "names the graph precondition": lambda s: "graphify-out/graph.json" in s,
    "absence writes no decision-log entry": lambda s: (
        "write no `.decision-log.md` entry" in s
    ),
    # Pinned to the whole clause, not the bare word: finalize.md already uses
    # "byte-identical" of the headless run-result write, so a looser token would
    # be satisfied by an unrelated section.
    "absence leaves the run byte-identical": lambda s: (
        "byte-identical to an `off` run" in s
    ),
    "separates absence from failure": lambda s: "Absence is silent; failure is logged." in s,
    # incremental, never a cold build
    "delegates the `update` subcommand": lambda s: any(
        re.search(r"\bgraphify update \.$", line) for line in _delegation_lines(s)
    ),
    "pins the no-LLM property": lambda s: "no LLM call" in s,
    "refuses a cold full build": lambda s: "Never a cold full build." in s,
    # bounding
    "time-boxes the delegation": lambda s: any(
        re.match(r"^timeout \d+ ", line) for line in _delegation_lines(s)
    ),
    "logs one WARN line on failure": lambda s: "`WARN graphify-refresh-failed`" in s,
    "does not retry": lambda s: "not retried" in s,
    # advisory posture
    "never changes the gate verdict": lambda s: "never changes the gate verdict" in s,
    "never changes the terminal envelope": lambda s: "never changes the terminal envelope" in s,
    "states the outcome is unchanged": lambda s: bool(
        re.search(r"the run's outcome \([^)]*\)[^.]*are unchanged", s)
    ),
    "claims advisory-only, like Cross-Session Recall": lambda s: (
        "advisory-only" in s and "Cross-Session Recall" in s
    ),
}


def _unmet(section: str) -> list[str]:
    return sorted(name for name, check in _SECTION_CHECKS.items() if not check(section))


def _resolve(engine_tree: Path, key: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(REAL_ENGINE),
         "--skill", str(engine_tree / "skills" / "ultracode-goal"), "--key", key],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --- AC-1: the knob ships off, with a closed two-value enum ------------------
def test_knob_declared_off_by_default_with_closed_enum(tmp_path: Path):
    workflow = tomllib.loads(_CUSTOMIZE.read_text(encoding="utf-8"))["workflow"]

    # Subscript, never `.get(..., "off")`: a defaulted read passes against a
    # customize.toml that never declared the key, leaving the knob unreachable
    # while every prose assertion below stayed green.
    try:
        shipped = workflow["graphify_integration"]
    except KeyError:  # pragma: no cover - the failure this guard exists to force
        raise AssertionError(
            "customize.toml's [workflow] table declares no `graphify_integration` key; "
            "the knob is unreachable no matter what finalize.md says"
        )
    assert shipped == "off", (
        "the shipped default must be `off`: an unconfigured run must delegate nothing, "
        f"probe nothing and log nothing, but ships {shipped!r}"
    )

    section = _section()
    assert section, "finalize.md has no `## Knowledge-graph refresh` section"

    # The engine invocation shape, identical to the epic-complete hook's.
    assert _SECTION_CHECKS["resolves the knob through resolve_customization.py"](section), (
        "the section does not resolve the knob the way the epic-complete hook resolves its own"
    )
    control_hook = "--key workflow.on_epic_complete"
    assert control_hook in _FINALIZE.read_text(encoding="utf-8"), (
        "control: the shape being mirrored is still in the file"
    )

    # The enum is CLOSED, not merely documented. Adding `query` back reds here.
    assert _mode_literals(section) == _MODES, (
        "the section's backticked bare lowercase words must be exactly the two legal "
        f"modes {sorted(_MODES)}, but are {sorted(_mode_literals(section))}. Every such "
        "word in this section is read as a mode literal — that convention is what makes "
        "the enum checkable, so spell non-mode bare words without backticks"
    )

    # And it resolves as a scalar through the real engine: base ships off, a
    # team layer can turn it on. A scalar overrides across layers; an array
    # would append and leave the run in two modes at once.
    custom = tmp_path / "_bmad" / "custom"
    custom.mkdir(parents=True)
    skill = tmp_path / "skills" / "ultracode-goal"
    skill.mkdir(parents=True)
    shutil.copy2(_CUSTOMIZE, skill / "customize.toml")

    assert _resolve(tmp_path, "workflow.graphify_integration") == {
        "workflow.graphify_integration": "off"
    }
    (custom / "ultracode-goal.toml").write_text(
        '[workflow]\ngraphify_integration = "refresh"\n', encoding="utf-8"
    )
    assert _resolve(tmp_path, "workflow.graphify_integration") == {
        "workflow.graphify_integration": "refresh"
    }


def test_closed_enum_matcher_rejects_a_third_mode():
    """The mutation AC-1's enum half must catch, applied.

    Re-adding `query` to the section reds the exact-set assertion while the
    off-by-default assertion stays green, so the two halves of AC-1 fail for
    disjoint reasons and neither stands in for the other.
    """
    section = _section()
    mutant = section.replace("Two values, and no others.", "Three values: `query` is one.", 1)
    assert mutant != section, "mutation did not apply"

    assert _mode_literals(mutant) == _MODES | {"query"}
    assert _mode_literals(mutant) != _MODES  # the enum assertion reds ...
    # ... while the shipped default is untouched, so the red names the enum alone
    assert tomllib.loads(_CUSTOMIZE.read_text(encoding="utf-8"))["workflow"][
        "graphify_integration"
    ] == "off"

    # positive control: the matcher is not a blanket reject
    assert _mode_literals(section) == _MODES


# --- AC-2: absent graphify degrades to silence, not to a log line ------------
def test_absent_graphify_degrades_silently():
    section = _section()
    assert section, "finalize.md has no `## Knowledge-graph refresh` section"

    for name in (
        "names the PATH probe",
        "names the graph precondition",
        "absence writes no decision-log entry",
        "absence leaves the run byte-identical",
        "separates absence from failure",
    ):
        assert _SECTION_CHECKS[name](section), f"the section fails to: {name}"

    # The two preconditions are conjunctive: EITHER one missing means no-op.
    # Requiring only the PATH probe would let a first-ever run in `refresh` mode
    # fall into an unbounded cold crawl on a machine that happens to have the
    # tool installed.
    assert "both required" in section, (
        "the section must state the probe and the graph are BOTH required"
    )
    assert "If either is missing" in section

    # And the silence is stated as the reason, not as an accident: the naive
    # implementation ("log that we skipped it") is the one that breaks
    # byte-identity while looking helpful, so the section forbids it by name.
    assert "do not add one" in section, (
        "the section must actively forbid a skipped-it log line, not merely omit it"
    )


def test_silence_assertion_is_not_satisfied_by_the_probe_prose():
    """AC-2's twin: deleting the silence sentence must red on silence alone.

    The mutation is degrade-quietly becoming degrade-with-a-log-line: the probe
    sentence stays, the byte-identity clause goes.
    """
    section = _section()
    silence = (
        " and write no `.decision-log.md` entry, so the run stays byte-identical "
        "to an `off` run."
    )
    assert silence in section, "the silence clause moved; this twin would be vacuous"

    mutant = section.replace(silence, ".", 1)
    assert mutant != section, "mutation did not apply"

    # the silence checks red ...
    assert not _SECTION_CHECKS["absence writes no decision-log entry"](mutant)
    assert not _SECTION_CHECKS["absence leaves the run byte-identical"](mutant)
    # ... while the detection prose stays green, so the red is attributable to
    # the byte-identity property and not to a garbled probe
    assert _SECTION_CHECKS["names the PATH probe"](mutant)
    assert _SECTION_CHECKS["names the graph precondition"](mutant)


# --- AC-3: incremental, and finalize is the sole call site -------------------
def test_refresh_is_incremental_and_finalize_only():
    text = _FINALIZE.read_text(encoding="utf-8")
    section = _section(text)
    assert section, "finalize.md has no `## Knowledge-graph refresh` section"

    lines = _delegation_lines(section)
    assert len(lines) == 1, f"expected exactly one delegation command, got {lines}"
    delegation = lines[0]
    assert re.search(r"\bgraphify update \.$", delegation), (
        f"the delegation must be the no-LLM incremental subcommand: {delegation!r}"
    )
    assert _SECTION_CHECKS["refuses a cold full build"](section)
    assert _SECTION_CHECKS["pins the no-LLM property"](section)

    # One line, and the WHOLE line. The fullmatch is what carries this: the
    # anchored search above inspects only the tail, so it accepts a chained
    # smuggle, and a loop re-checking the same single line with a WEAKER pattern
    # is a test that cannot fail. `graphify extract` is the LLM path and a
    # bare-path `graphify .` aliases straight to it, so either one chained ahead
    # of the update would dispatch semantic extraction from an unattended exit.
    assert re.fullmatch(r"timeout \d+ graphify update \.", delegation), (
        f"the delegation must be exactly the no-LLM incremental subcommand: {delegation!r}"
    )

    # Positive control for that fullmatch: the smuggle it exists to reject has to
    # actually fail it, and the weaker form has to actually let it through, or
    # the assertion above is decoration.
    smuggle = "timeout 300 graphify extract . && graphify update ."
    assert re.search(r"\bgraphify update \.$", smuggle), "control is not a valid smuggle"
    assert not re.fullmatch(r"timeout \d+ graphify update \.", smuggle), (
        "the fullmatch does not reject a chained `graphify extract`"
    )

    # Position: after the run's other optional integration, and well before the
    # true terminal step. finalize.md forbids acting between the health-check
    # section and the health check itself.
    assert text.index("## Cross-Session Recall write") < text.index(_HEADING)
    assert text.index(_HEADING) < text.index("## Record the terminal run-status")
    assert text.index(_HEADING) < text.index(_TERMINAL_HEADING)


# --- AC-4: the negative twin, plus the control that makes it non-vacuous -----
def test_no_graphify_in_preflight_or_story_spine():
    assert _files_naming_graphify(_swept_paths()) == [], (
        "graphify reached a preflight, per-story, gate, hook or envelope surface. "
        "It is finalize-only by design: a call on any of these paths can change a "
        "gate verdict or a terminal envelope, which is exactly what this "
        "integration must never do"
    )

    section = _section()
    assert _SECTION_CHECKS["never changes the gate verdict"](section)
    assert _SECTION_CHECKS["never changes the terminal envelope"](section)
    assert _SECTION_CHECKS["states the outcome is unchanged"](section)
    assert _SECTION_CHECKS["claims advisory-only, like Cross-Session Recall"](section)

    # finalize.md is the sole shipped file that names graphify at all.
    assert "graphify" in _FINALIZE.read_text(encoding="utf-8").lower(), (
        "control: the one legal call site still names the tool"
    )


def test_graphify_sweep_catches_a_planted_call(tmp_path: Path):
    """The positive control. A negative assertion's failure mode is being
    vacuously green — a mistyped path, a helper that reads nothing, or a token
    that never matches would all pass forever.
    """
    planted = tmp_path / "execute.md"
    planted.write_text(
        "Step 7. Refresh the graph before the gate:\n\n"
        "```\ntimeout 300 graphify update .\n```\n",
        encoding="utf-8",
    )
    assert _files_naming_graphify([planted]) == ["execute.md"], (
        "the sweep helper cannot see a planted graphify call; every green it "
        "reports elsewhere is meaningless"
    )

    # It discriminates: a file without the token is not flagged.
    clean = tmp_path / "gate.md"
    clean.write_text("Step 7. Run the gate.\n", encoding="utf-8")
    assert _files_naming_graphify([clean]) == []
    assert _files_naming_graphify([planted, clean]) == ["execute.md"]

    # And every swept path really exists, so a rename or a typo is a red rather
    # than a silently-skipped file.
    for path in _swept_paths():
        assert path.is_file(), (
            f"swept path {path.relative_to(_SKILL_ROOT)} does not exist; the sweep "
            "would pass over it forever"
        )
    assert len(_swept_paths()) == len(_SWEPT) == 8


# --- AC-5: the delegation is hard time-boxed --------------------------------
def test_refresh_delegation_is_hard_timeboxed():
    section = _section()
    delegation = _delegation_lines(section)[0]

    bound = re.match(r"^timeout (\d+) ", delegation)
    assert bound, (
        f"the delegation carries no literal time-box: {delegation!r}. The bound must be "
        "an integer the shell enforces, not an adverb in the prose"
    )
    assert int(bound.group(1)) > 0

    assert _SECTION_CHECKS["logs one WARN line on failure"](section), (
        "the failure path must log one WARN line, the idiom the deferred memory "
        "write already uses"
    )
    assert _SECTION_CHECKS["does not retry"](section)
    assert _SECTION_CHECKS["states the outcome is unchanged"](section)
    assert _SECTION_CHECKS["never changes the terminal envelope"](section)

    # The failure path is logged; the ABSENT path is not. Holding both in one
    # assertion is what keeps an implementer from picking one rule and breaking
    # the other property.
    assert _SECTION_CHECKS["absence writes no decision-log entry"](section)
    assert _SECTION_CHECKS["separates absence from failure"](section)


def test_refresh_delegation_command_survives_the_timeout_mutation():
    """AC-5's control: strip the bound, keep everything else byte-identical.

    The time-box assertion must red, and the red must be attributable to the
    missing bound alone — so this asserts the command is still present, still
    names graphify and still names the incremental flag under that mutation.
    """
    section = _section()
    delegation = _delegation_lines(section)[0]

    mutant_line = re.sub(r"^timeout \d+ ", "", delegation)
    assert mutant_line != delegation, "mutation did not apply"

    mutant = section.replace(delegation, mutant_line, 1)
    # the bound assertion reds ...
    assert not _SECTION_CHECKS["time-boxes the delegation"](mutant)
    assert not re.match(r"^timeout \d+ ", _delegation_lines(mutant)[0])
    # ... while the command itself is intact, so no deleted or garbled command
    # can explain the failure
    assert re.search(r"\bgraphify update \.$", mutant_line)
    assert _SECTION_CHECKS["delegates the `update` subcommand"](mutant)
    assert _SECTION_CHECKS["logs one WARN line on failure"](mutant)
    assert _SECTION_CHECKS["does not retry"](mutant)


# --- the twin: the pre-edit file satisfies none of it ------------------------
def test_pre_edit_fixture_lacks_the_whole_section():
    blob = _FIX_PRE_EDIT.read_text(encoding="utf-8")

    assert _section(blob) == "", "the pre-edit fixture already has the section"
    assert "graphify" not in blob.lower(), (
        "the pre-edit fixture already names graphify; this twin would be vacuous"
    )

    # Measured through the SAME matcher the live file passes, so the twin proves
    # the contract, not merely a missing heading. Run against the whole file, not
    # a slice, so a section-slicing bug cannot manufacture the red.
    assert _unmet(blob) == sorted(_SECTION_CHECKS), (
        f"the pre-edit fixture already satisfies part of the contract: "
        f"{sorted(set(_SECTION_CHECKS) - set(_unmet(blob)))}"
    )

    # ... and the live file satisfies all of it.
    assert _unmet(_section()) == []


def test_pre_edit_fixture_is_a_real_snapshot():
    """The twin must red for the RIGHT reason: an emptied file proves nothing."""
    blob = _FIX_PRE_EDIT.read_text(encoding="utf-8")
    live = _FINALIZE.read_text(encoding="utf-8")

    for anchor in (
        "# Stage 6 — Finalize",
        "## Cross-Session Recall write (optional)",
        "## Record the terminal run-status",
        "## Epic-complete hook",
        "--key workflow.on_epic_complete",
        "## Workflow health check (terminal)",
    ):
        assert anchor in blob, f"the fixture is not a real finalize.md snapshot: {anchor!r}"
        assert anchor in live, f"control: the live file still carries {anchor!r}"

    # The edit was additive: every line of the pre-edit file survives in the live
    # one, so the section was inserted rather than swapped in over something.
    assert set(blob.splitlines()) <= set(live.splitlines()), (
        "the live finalize.md dropped lines the pre-edit snapshot carried; this "
        "story's edit was supposed to be purely additive"
    )
    assert len(live) > len(blob)


def test_customize_knob_is_documented_as_advisory():
    """The knob's own comment must not read as a feature that does something to
    the run. A future reader reaching for it decides from `customize.toml`, not
    from finalize.md.
    """
    text = _CUSTOMIZE.read_text(encoding="utf-8")
    block = text[text.index("graphify_integration") - 700:text.index("graphify_integration")]
    assert "Advisory only, never gates." in block
    assert "silently inactive" in block
    for mode in sorted(_MODES):
        assert f'"{mode}"' in block, f"the comment does not name the {mode!r} mode"
    # and the comment does not promise a third one
    assert "query" not in block.lower()


def test_no_graphify_bullet_was_added_to_the_nonnegotiables():
    """Guard the sibling contract this story could plausibly have broken.

    `SKILL.md`'s Non-negotiables list is asserted elsewhere to hold exactly six
    bullets. The advisory posture belongs in the finalize section (where AC-4
    asserts it), not in a seventh bullet that would red an unrelated module.
    """
    skill_md = (_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^## Non-negotiables\s*$(.*?)(?=^## |\Z)", skill_md, re.MULTILINE | re.DOTALL)
    assert match, "SKILL.md has no `## Non-negotiables` section"
    body = match.group(1)
    assert len(re.findall(r"^- \*\*", body, re.MULTILINE)) == 6, (
        "the Non-negotiables bullet count is pinned at six by "
        "test_skill_nonnegotiable_formalize.py; adding a graphify bullet reds that module"
    )
    assert "graphify" not in body.lower()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
