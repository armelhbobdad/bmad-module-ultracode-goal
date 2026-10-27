"""Prose contract over the turn bound: who can start `/goal`, and what the count sees.

A real run showed that the conductor never starts `/goal`. It is a built-in slash
command with no tool surface, so an attended session, a `-H` session and a
`drive_epic.py` spawn all run without one unless the operator starts it, and then
on the operator's own condition. Yet the references and docs called the
in-condition "…or stop after N turns" clause "the real bound". The turn count the
Stop hook records is the only one every session keeps, and it advances once per
response, so it cannot see re-loops spent inside a single response.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against a single-clause mutant or the pre-edit wording it must reject.
Stdlib + pytest only.
"""

import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_FINALIZE = _SKILL_ROOT / "references" / "finalize.md"

# Wording that stated the `/goal` turn clause as the active bound, `/goal` as what
# drives Execute or a primitive the run composes, the turn count as a cap, or one
# commit per story where a story now lands two. Matched case-insensitively.
_RETIRED = (
    "the turn clause inside the condition is the real bound",
    "wrap the loop in a single `/goal`",
    "what the `/goal` driver reads to pace itself",
    "after `/goal` returns",
    "the real in-loop bound",
    "primary runaway guard",
    "enforced inside the `/goal` condition",
    "the hard bounds are the in-condition turn clause",
    "the loop is wrapped in a single `/goal`",
    "the `/goal` loop drives execution",
    "the `/goal` evaluator that drives execution",
    "the `/goal` loop that drives execute",
    "paced by claude code's `/goal` evaluator",
    "encoded in the `/goal` condition and enforced at the gate",
    "it is also that loop's condition",
    "the same number `run-status.json` reports",
    "the bound that holds in every session",
    "worst-case envelope",
    "turns consumed vs",
    "composes `/goal`",
    "`/goal`, auto mode, auto memory, hooks, and git branches, the primitives ucg composes",
    "primitives: `/goal`, dynamic workflows",
    "one commit per green story",
    "worst-case turn envelope",
    "is one git commit on",
    "primitives (`/goal`,",
    "primitives — `/goal`",
    "primitives (/goal,",
    "goal mode",
    "a turn cap the stop hook counts",
)

# Paraphrases of the retired wording, each carrying its phrase verbatim, so the
# twin below proves every phrase in the list matches real old prose. Three of
# them ("it is also that loop's condition", "the same number `run-status.json`
# reports", "the bound that holds in every session") come from a first draft of
# this fix that a review rejected, not from main.
_PRE_EDIT = (
    "Wrap the loop in a single `/goal` whose condition is under 4000 characters. "
    "A Stop hook cannot force `/goal` to halt mid-condition, so the turn clause inside "
    "the condition is the real bound. This printed evidence is what keeps the run "
    "judgeable mid-flight and what the `/goal` driver reads to pace itself. "
    "Execute is the sole promoter of that markdown, after `/goal` returns, read any marker.",
    "the in-condition \"stop after N turns\" clause inside the `/goal` condition (the real "
    "in-loop bound). Today the in-`/goal`-condition turn cap is the primary runaway guard.",
    "The per-story turn ceiling is the skill's own, enforced inside the `/goal` condition "
    "and the budget_stop.py Stop hook.",
    "So at this layer the ceiling is advisory; the hard bounds are the in-condition turn "
    "clause and the gate re-loop budget.",
    "The loop is wrapped in a single `/goal` whose condition encodes the Definition-of-Done.",
    "Claude Code primitives: the `/goal` loop drives execution. The `/goal` evaluator that "
    "drives execution can only see what the run surfaces.",
    "The `/goal` loop that drives Execute ends with an evaluator confirming the condition.",
    "The per-story loop is paced by Claude Code's `/goal` evaluator (an LLM). UCG's is a "
    "turn cap, encoded in the `/goal` condition and enforced at the gate.",
    "when the operator did start a `/goal`, it is also that loop's condition. The bound that "
    "holds in every session is the turn count (the same number `run-status.json` reports).",
    "- **Worst-case envelope:** up to `story count × {workflow.max_turns_per_story}` turns. "
    "- Turns consumed vs `{workflow.max_turns_per_story}`.",
    "UCG composes `/goal`, Auto Mode, Auto Memory, and runtime hooks. | `/goal`, Auto Mode, "
    "Auto Memory, hooks, and git branches, the primitives UCG composes |",
    "The run also depends on recent Claude Code primitives: `/goal`, dynamic workflows, and "
    "Auto Memory. The real undo is an Epic branch, one commit per green story.",
    "The briefing lists what is about to run, the worst-case turn envelope. Every green "
    "story is one git commit on an isolated epic branch. Composing Claude Code primitives "
    "(`/goal`, Auto Mode). It composes Claude Code primitives — `/goal`, Auto Mode. Claude "
    "Code primitives (/goal, Auto Mode). Supercharges BMAD with Claude Code Goal Mode. "
    "UCG's is a turn cap the Stop hook counts.",
)

_SURFACES = (
    _EXECUTE,
    _PREFLIGHT,
    _FINALIZE,
    _SKILL_ROOT / "scripts" / "hooks" / "budget_stop.py",
    _SKILL_ROOT / "scripts" / "drive_epic.py",
    _REPO / "docs" / "architecture.md",
    _REPO / "docs" / "troubleshooting.md",
    _REPO / "docs" / "why-ultracode-goal.md",
    _REPO / "docs" / "how-it-works.md",
    _REPO / "docs" / "comparison.md",
    _REPO / "docs" / "gate-model.md",
    _REPO / "ROADMAP.md",
    _REPO / "README.md",
    _REPO / "docs" / "getting-started.md",
    _REPO / "docs" / "index.md",
    _SKILL_ROOT / "SKILL.md",
    _SKILL_ROOT / "assets" / "module.yaml",
    _REPO / ".claude-plugin" / "marketplace.json",
    _REPO / "tools" / "cli" / "lib" / "platform-codes.yaml",
    _REPO / "tools" / "cli" / "lib" / "ui.js",
)


def _execute() -> str:
    return _EXECUTE.read_text(encoding="utf-8")


def _states_the_count_honestly(text: str) -> bool:
    return bool(
        re.search(r"The conductor cannot start `/goal` itself", text)
        and re.search(r"`\{workflow\.implementation_artifacts\}/\.budget-<story_id>\.json`", text)
        and re.search(r"cannot see re-loops spent inside a single response", text)
        and re.search(r"\*\*Before a story's step 0\*\* on the `story-boundary` and `mid-story` resume routes", text)
        and re.search(r"A `gate-owed` story is exempt", text)
        and re.search(r"`kind` `budget-overrun`", text)
    )


def test_execute_states_what_the_turn_count_can_and_cannot_see():
    assert _states_the_count_honestly(_execute())


@pytest.mark.parametrize(
    "clause",
    [
        "cannot see re-loops spent inside a single response",
        "A `gate-owed` story is exempt",
    ],
)
def test_turn_count_predicate_rejects_a_single_dropped_clause(clause):
    mutant = _execute().replace(clause, "")
    assert mutant != _execute(), "the mutant must actually change the text"
    assert not _states_the_count_honestly(mutant)


def test_the_retired_bound_claims_stay_out_of_every_surface():
    for surface in _SURFACES:
        text = surface.read_text(encoding="utf-8").lower()
        for phrase in _RETIRED:
            assert phrase not in text, f"{surface.name} still says {phrase!r}"


def test_every_retired_phrase_matches_the_pre_edit_wording():
    """Twin of the check above: each phrase really catches the old sentence."""
    old = " ".join(_PRE_EDIT).lower()
    for phrase in _RETIRED:
        assert phrase in old, phrase


_WHO_CAN_START = re.compile(r"conductor cannot (start one|start `/goal`)")


def test_the_docs_say_who_can_start_goal():
    for name in ("architecture.md", "troubleshooting.md", "why-ultracode-goal.md", "how-it-works.md"):
        text = (_REPO / "docs" / name).read_text(encoding="utf-8")
        assert _WHO_CAN_START.search(text), name


def test_who_can_start_predicate_rejects_the_pre_edit_docs():
    assert not _WHO_CAN_START.search(" ".join(_PRE_EDIT))


def test_gate_names_the_count_its_reloop_budget_reads():
    gate = (_SKILL_ROOT / "references" / "gate.md").read_text(encoding="utf-8")
    assert re.search(
        r"the count is the `turns` value the Stop hook records in "
        r"`\{workflow\.implementation_artifacts\}/\.budget-<story_id>\.json`",
        gate,
    )


_BRIEFING_PRE_EDIT = Path(__file__).resolve().parent / "fixtures" / "preflight_briefing_five_bullets.md"


def _states_the_ceiling_honestly(text: str) -> bool:
    return bool(
        re.search(
            r"\*\*Turn ceiling:\*\* `\{workflow\.max_turns_per_story\}` turns per story, "
            r"as the Stop hook counts them \(one per response\)",
            text,
        )
        and re.search(r"It sizes stories; it does not cap time or cost\.", text)
    )


def test_the_briefing_states_the_turn_ceiling_as_a_sizing_bound():
    assert _states_the_ceiling_honestly(_PREFLIGHT.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "clause",
    ["as the Stop hook counts them (one per response)", "It sizes stories; it does not cap time or cost."],
)
def test_ceiling_predicate_rejects_a_single_dropped_clause(clause):
    live = _PREFLIGHT.read_text(encoding="utf-8")
    mutant = live.replace(clause, "")
    assert mutant != live, "the mutant must actually change the text"
    assert not _states_the_ceiling_honestly(mutant)


def test_ceiling_predicate_rejects_the_pre_edit_briefing():
    """Twin: the shipped five-bullet briefing, captured before any edit, fails it."""
    assert not _states_the_ceiling_honestly(_BRIEFING_PRE_EDIT.read_text(encoding="utf-8"))


_RUN_REPORT_COUNT = re.compile(
    r"Turns the Stop hook counted per story "
    r"\(`\{workflow\.implementation_artifacts\}/\.budget-<story_id>\.json`, "
    r"`0` when the hook never fired for it\)"
)


def test_the_run_report_names_the_count_it_reports():
    assert _RUN_REPORT_COUNT.search(_FINALIZE.read_text(encoding="utf-8"))


def test_run_report_predicate_rejects_the_pre_edit_line():
    """Twin: the run report captured before this edit still says "Turns consumed"."""
    pre_edit = Path(__file__).resolve().parent / "fixtures" / "finalize_no_graphify_section.md"
    text = pre_edit.read_text(encoding="utf-8")
    assert "Turns consumed vs" in text
    assert not _RUN_REPORT_COUNT.search(text)


# A real run reached the ceiling on waiting: of the seven Stops a comments-only
# re-loop spent, four were wake-ups from separately reporting background agents
# (one for another story) while a sweep ran. The count is responses, so
# execute.md says how a story's waits are kept few, inside the story loop where
# the conductor reads it, and the docs say what the count includes.
_TROUBLESHOOTING = _REPO / "docs" / "troubleshooting.md"
_PRE_WAITS_EXECUTE = Path(__file__).resolve().parent / "fixtures" / "execute_pre_verification_axes.md"

_WAIT_CLAUSES = (
    r"\*\*Waiting spends turns\.\*\* The Stop hook counts one turn per response, whatever the response did\.",
    r"that lands while the session is idle starts a response of its own",
    r"\*\*Make each wait report once\.\*\*",
    r"concurrent commands as one subagent the session waits for, which runs each as its own simple command "
    r"and reports every exit status in its one reply",
    r"One compound shell command that starts them together and collects their exit statuses "
    r"\(`&`, `wait`, `\$!`, `\$\?`\) is not an option: under `scripts/drive_epic\.py`'s default spawn mode, "
    r"`acceptEdits`, with the default allowlist, Claude Code refuses it before it runs",
    r"\*\*Watch for completion, not progress\.\*\*",
    r"The hook books every Stop to the story `\.current-story` names",
    r"Start such work in that story's own loop, once its step 0 has made it current\.",
)

# The bullet once offered concurrent commands as one background command that
# starts them together and prints each exit status. Under drive_epic.py's
# default acceptEdits with the default allowlist, Claude Code refused every
# shell form of it (`&` with `$!`, subshells with `wait`, `$?` after a `;`, a
# bare `wait`), while each command alone ran. The offer must not come back.
_RETIRED_WAIT_FORM = "one background command that starts them together"
_PRE_FIX_COMMANDS_CLAUSE = (
    "concurrent commands as one background command that starts them together, waits for each and prints "
    "each one's exit status (a bare `wait` returns 0 even when a job failed)"
)


def _story_loop(text: str) -> str:
    start = text.index("### The story loop")
    return text[start : text.index("### The per-invocation work bound", start)]


def _states_that_waits_spend_turns(text: str) -> bool:
    try:
        loop = _story_loop(text)
    except ValueError:
        return False
    if _RETIRED_WAIT_FORM in loop:
        return False
    return all(re.search(c, loop) for c in _WAIT_CLAUSES) and bool(
        re.search(
            r"It counts responses, not work: a response that only acknowledges a background task's "
            r"notification counts the same as one that edits code",
            text,
        )
    )


def test_execute_says_waiting_spends_turns():
    assert _states_that_waits_spend_turns(_execute())


@pytest.mark.parametrize(
    "clause",
    [
        "whatever the response did.",
        "that lands while the session is idle starts a response of its own",
        "**Make each wait report once.**",
        "which runs each as its own simple command and reports every exit status in its one reply",
        "(`&`, `wait`, `$!`, `$?`) is not an option",
        "Claude Code refuses it before it runs",
        "**Watch for completion, not progress.**",
        "The hook books every Stop to the story `.current-story` names",
        "in that story's own loop, once its step 0 has made it current.",
        "It counts responses, not work: ",
    ],
)
def test_waits_predicate_rejects_a_single_dropped_clause(clause):
    mutant = _execute().replace(clause, "")
    assert mutant != _execute(), "the mutant must actually change the text"
    assert not _states_that_waits_spend_turns(mutant)


def test_waits_predicate_rejects_the_paragraph_outside_the_story_loop():
    live = _execute()
    start = live.index("**Waiting spends turns.**")
    end = live.index("\n### The per-invocation work bound", start)
    moved = live[:start] + live[end:] + "\n" + live[start:end]
    assert not _states_that_waits_spend_turns(moved)


def test_waits_predicate_rejects_an_execute_without_it():
    """Twin: an older shipped execute.md, captured before this edit, fails it."""
    assert not _states_that_waits_spend_turns(_PRE_WAITS_EXECUTE.read_text(encoding="utf-8"))


def test_waits_predicate_rejects_the_compound_command_offer():
    """Twin: the bullet as first written, offering the one background command
    the default spawn mode refuses, fails it, and so does that offer added back
    beside the subagent form."""
    live = _execute()
    new_clause = (
        "concurrent commands as one subagent the session waits for, which runs each as its own simple command "
        "and reports every exit status in its one reply"
    )
    assert new_clause in live
    assert not _states_that_waits_spend_turns(live.replace(new_clause, _PRE_FIX_COMMANDS_CLAUSE))
    both = live.replace(new_clause, new_clause + ", or " + _PRE_FIX_COMMANDS_CLAUSE)
    assert not _states_that_waits_spend_turns(both)


_TROUBLE_WAITS = re.compile(
    r"It counts responses, not work: a background task's notification that lands while the session is idle "
    r"starts a response of its own, which counts the same as one that edits code"
)


def _budget_section(text: str) -> str:
    start = text.index("## Budget exhausted mid-story")
    return text[start : text.index("\n## ", start + 1)]


def test_troubleshooting_says_waits_spend_the_count():
    assert _TROUBLE_WAITS.search(_budget_section(_TROUBLESHOOTING.read_text(encoding="utf-8")))


def test_troubleshooting_predicate_rejects_the_section_without_it():
    section = _budget_section(_TROUBLESHOOTING.read_text(encoding="utf-8"))
    start = section.index(" It counts responses, not work:")
    end = section.index("while a story is current.", start) + len("while a story is current.")
    assert not _TROUBLE_WAITS.search(section[:start] + section[end:])
