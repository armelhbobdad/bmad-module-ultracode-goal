#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for where a test review and an NFR assessment are written.

`gate_eval.py` reads the test review's Quality Score and Recommendation and the
NFR assessment's Overall Status as written, and it cannot tell who wrote either
file. The 8.1.0 bound on what a test reviewer is handed, and the bound on what
the NFR assessor is handed beside it, apply when the assessment is delegated.
A conductor that ran `bmad-testarch-test-review` or `bmad-testarch-nfr` in its
own context, which holds every ruling of the run, or typed a score or a status
into a file by hand, was bound by neither.

`references/gate.md` now adds a paragraph in "Backfill the gate evidence",
directly after the NFR assessor's: each test review (the gate's, or Execute
step 3's) and each NFR assessment is delegated to an agent started for that one
assessment, one that starts without this conversation, so never a fork, which
inherits it; the conductor runs neither skill in its own context, writes
neither file, and changes no Quality Score, Recommendation or Overall Status in
a file an assessor wrote. When the host refuses the agent's write of its file,
the agent returns the file's full text and the conductor writes that text
unchanged, as "Automate's summary records its rows" has it write automate's. A
file written to the hand-authored shapes is for a story whose TEA skill cannot
run, and a delegated agent writes it. Two cases leave the work to the
conductor's own context: a session that cannot start such an agent runs the
skill itself, or, where the skill cannot run, writes that file itself, and so
does one whose delegated assessment ends in TEA's error that its execution mode
cannot run (`tea_capability_probe: false` with `tea_execution_mode` `subagent`
or `agent-team`), which runs the skill where that mode can run, for the rest of
the run. In each case the conductor says so in `.decision-log.md`, and the rule
stops none of them. Execute step 3, where the test review normally runs, points
at the paragraph and names the fork it excludes.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text without the change and one-clause mutants it must reject. The
paragraph is pinned whole and in place, and the mode case has a test of its
own. Its cross-reference to automate's summary is checked against that
paragraph, below this one, its facts about forks against the tracked reference
skill under `skf-skills/cc-primitives/`, and its facts about TEA against the
tracked reference skill under `skf-skills/tea-testarch/` (the installed skills
under `.claude/skills/` are not tracked, so no test reads them). Stated limit:
this is a presence proof over prose. It shows the instruction is in the files,
not that a conductor obeys it, that an agent it starts can or cannot start
agents, that a host refuses or allows a write, or that TEA and Claude Code
behave as their references say.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_REFERENCES = _SKILL_ROOT / "references"
GATE = (_REFERENCES / "gate.md").read_text(encoding="utf-8")
EXECUTE = (_REFERENCES / "execute.md").read_text(encoding="utf-8")
PREFLIGHT = (_REFERENCES / "preflight.md").read_text(encoding="utf-8")

_REVIEW_HEAD = "**The test reviewer reads the tests, not the run's account of them.**"
_NFR_HEAD = "**The NFR assessor reads what the commit shows, not the run's account of it.**"
_HEAD = "**No test review and no NFR assessment is written in your own context.**"
_CITED = '"No test review and no NFR assessment is written in your own context"'
_SHAPES_HEAD = "**Hand-authored `nfr-assessment.md` and `test-review.md` shapes (production path only).**"
_SUMMARY_HEAD = "**Automate's summary records its rows.**"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def _backfill_section(text: str = GATE) -> str:
    return _section(text, "## Backfill the gate evidence")


def _paragraph(text: str, opener: str) -> str:
    """The paragraph that opens with `opener`, or "" when `text` has none."""
    start = text.find(opener)
    if start == -1:
        return ""
    end = text.find("\n\n", start)
    return text[start : end if end != -1 else len(text)]


def _rule(text: str = GATE) -> str:
    return _paragraph(_backfill_section(text), _HEAD)


def _without_the_rule(text: str = GATE) -> str:
    """The gate text without this paragraph: the state before the edit."""
    rule = _rule(text)
    assert rule, "the live text must hold the paragraph"
    return text.replace(rule + "\n\n", "", 1)


def _step3(text: str = EXECUTE) -> str:
    start = text.index("\n3. **Production profile only:**")
    return text[start + 1 : text.index("\n4. ", start)]


# The paragraph's sentences, in order. The whole-paragraph pin joins them.
_WHY = (
    _HEAD + " You hold every ruling of the run, so an assessment you make reads the run's account whatever you hand "
    "yourself, and `gate_eval.py` cannot tell who wrote a file."
)
_DELEGATE = (
    "Delegate each test review, here or at `references/execute.md`'s step 3, and each NFR assessment to an agent you "
    "start for that one assessment, one that starts without this conversation (never a fork, which inherits it): run "
    "neither skill in your own context, write neither file yourself, and change no Quality Score, Recommendation or "
    "Overall Status in a file an assessor wrote."
)
_REFUSED = (
    "Tell it that when the host refuses its write of the file, it returns the file's full text in its result, and "
    "write that text yourself, unchanged, as \"Automate's summary records its rows\" (below) has you write automate's."
)
_HAND_AUTHORED = (
    "A file written to \"Hand-authored `nfr-assessment.md` and `test-review.md` shapes\" (below) is for a story whose "
    "TEA skill cannot run, and a delegated agent writes it."
)
_SUCH_AN_AGENT = "A session that cannot start such an agent "
_SKILL_FIRST = "runs the skill itself, or, where the skill cannot run, writes that file itself."
_NO_AGENT = _SUCH_AN_AGENT + _SKILL_FIRST
_MODE_CASE = (
    "So does one whose delegated assessment ends in TEA's error that its execution mode cannot run "
    "(`tea_capability_probe: false` with a `tea_execution_mode` of `subagent` or `agent-team`, since an agent you "
    "start may be unable to start agents): it runs the skill where that mode can run, for the rest of the run."
)
_LOGGED = "In each of these cases, say so in `.decision-log.md`: this rule stops none of them."
_SENTENCES = (_WHY, _DELEGATE, _REFUSED, _HAND_AUTHORED, _NO_AGENT, _MODE_CASE, _LOGGED)


def _mutant(old: str, new: str) -> str:
    rule = _flat(_rule())
    mutant = rule.replace(old, new)
    assert mutant != rule, "the mutant must actually change the text"
    return mutant


# --- both assessments are delegated, each to its own agent -----------------------

_DELEGATES = (
    "Delegate each test review, here or at `references/execute.md`'s step 3, and each NFR assessment to an agent you "
    "start for that one assessment,"
)


def _delegates_both(rule: str) -> bool:
    return _DELEGATES in _flat(rule)


def test_rule_delegates_each_assessment_to_an_agent_started_for_it():
    assert _delegates_both(_rule())
    # "Here or at step 3": both places a test review runs, and Execute step 3
    # runs one.
    assert _step3().startswith("3. **Production profile only:** `bmad-testarch-test-review`, then")


def test_delegation_predicate_rejects_the_text_without_the_paragraph():
    assert not _delegates_both(_backfill_section(_without_the_rule()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(", here or at `references/execute.md`'s step 3,", "", id="gate-review-only"),
        pytest.param(" and each NFR assessment", "", id="nfr-in-own-context"),
        pytest.param("Delegate each test review, here or at `references/execute.md`'s step 3, and each",
                     "Delegate each", id="test-review-in-own-context"),
        pytest.param("to an agent you start for that one assessment,", "to an agent you start for the gate,",
                     id="one-agent-for-all"),
        pytest.param("Delegate each test review", "Prefer to delegate each test review", id="optional"),
    ],
)
def test_delegation_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _delegates_both(_mutant(old, new))


# --- the agent starts without this conversation, so never a fork -----------------

_FRESH = " one that starts without this conversation (never a fork, which inherits it):"


def _excludes_a_fork(rule: str) -> bool:
    """The agent each assessment is delegated to is one started for it that does
    not carry this conversation, and a fork, which does, is named and excluded."""
    return (_DELEGATES + _FRESH) in _flat(rule)


def test_rule_starts_the_agent_without_this_conversation_and_never_as_a_fork():
    assert _excludes_a_fork(_rule())


def test_fork_predicate_rejects_the_text_without_the_paragraph():
    assert not _excludes_a_fork(_backfill_section(_without_the_rule()))
    # The NFR assessor's rule above delegates without naming the agent's kind.
    assert not _excludes_a_fork(_paragraph(_backfill_section(), _NFR_HEAD))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("," + _FRESH, ":", id="dropped"),
        pytest.param("(never a fork, which inherits it)", "(a fork, which inherits it, will do)", id="fork-allowed"),
        pytest.param("(never a fork, which inherits it)", "(a fork if fork mode is on)", id="fork-when-on"),
        pytest.param(" (never a fork, which inherits it)", "", id="fork-unnamed"),
        pytest.param("one that starts without this conversation (never a fork, which inherits it)",
                     "an agent of any kind", id="an-agent-of-any-kind"),
        pytest.param("one that starts without this conversation", "one that starts with this conversation",
                     id="with-the-conversation"),
    ],
)
def test_fork_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _excludes_a_fork(_mutant(old, new))


def test_a_fork_inherits_the_conversation_and_other_subagents_do_not():
    """The fact the clause rests on, from the tracked Claude Code reference: a
    non-fork subagent starts with no conversation history, a fork inherits it,
    and fork mode is on by default, so an agent started without naming its kind
    can be a fork."""
    group = _REPO / "skf-skills" / "cc-primitives"
    active = group / "active"
    version = active.resolve().name if active.is_dir() else active.read_text(encoding="utf-8").strip()
    subagents = _flat(
        (group / version / "cc-primitives" / "references" / "subagents-and-workflows.md").read_text(encoding="utf-8")
    )
    assert "Non-fork subagents start with no conversation history" in subagents
    assert "A fork inherits the conversation but cannot fork again." in subagents
    assert "Fork mode is on by default" in subagents


# --- the conductor runs neither skill and writes neither file --------------------

_NEITHER = (
    ": run neither skill in your own context, write neither file yourself, and change no Quality Score, "
    "Recommendation or Overall Status in a file an assessor wrote."
)


def _runs_and_writes_neither(rule: str) -> bool:
    """The three bans are the delegation sentence's own tail: nothing between the
    delegation and them ends a sentence or opens another list."""
    return re.search(re.escape(_DELEGATES) + r"[^.:]*" + re.escape(_NEITHER), _flat(rule)) is not None


def test_rule_runs_neither_skill_writes_neither_file_and_changes_no_field():
    assert _runs_and_writes_neither(_rule())
    # The fields named are the three `gate_eval.py` reads from the two files.
    assert "The reader takes a line that opens with `Quality Score`, `Recommendation` or `Overall Status`" in _flat(
        _section(GATE, "## Non-web stack")
    )


def test_neither_predicate_rejects_the_text_without_the_paragraph():
    assert not _runs_and_writes_neither(_backfill_section(_without_the_rule()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("run neither skill in your own context, ", "", id="runs-a-skill-itself"),
        pytest.param("write neither file yourself, ", "", id="writes-a-file-itself"),
        pytest.param("run neither skill in your own context", "run neither skill in an agent", id="inverted"),
        pytest.param("change no Quality Score, Recommendation or Overall Status",
                     "change no Quality Score or Overall Status", id="recommendation-editable"),
        pytest.param("change no Quality Score, Recommendation or Overall Status",
                     "change no Quality Score or Recommendation", id="status-editable"),
        pytest.param("change no Quality Score, Recommendation or Overall Status",
                     "change no Recommendation or Overall Status", id="score-editable"),
        pytest.param("in a file an assessor wrote.", "in a file an assessor wrote unless a ruling allows it.",
                     id="ruling-may-edit"),
    ],
)
def test_neither_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _runs_and_writes_neither(_mutant(old, new))


# --- a refused write comes back as text the conductor writes unchanged -----------

_REFUSED_RE = re.compile(
    r"Tell it that when the host refuses its write of the file, it returns the file's full text in its result, and "
    r'write that text yourself, unchanged, as "(?P<cited>[^"]+)" \(below\) has you write automate\'s\.'
)


def _cited_paragraph_below(cited: str, text: str = GATE) -> str:
    """The paragraph `cited` names, when it opens exactly one paragraph and sits
    below this one; "" otherwise."""
    head = "**" + cited + ".**"
    if text.count("\n" + head + " ") != 1:
        return ""
    if text.index("\n" + head + " ") < text.index(_HEAD):
        return ""
    return _paragraph(text, "\n" + head + " ")


_CONDUCTOR_WRITES = "When it returns that text, write it at that name yourself, unchanged,"


def _refused_write_is_routed(rule: str, text: str = GATE) -> bool:
    """Right after the three bans, the agent is told to return the file's full
    text when the host refuses its write, and the conductor writes that text
    unchanged, as a paragraph below has it write automate's returned text, which
    that paragraph does."""
    flat = _flat(rule)
    match = _REFUSED_RE.search(flat)
    if match is None or (_NEITHER[2:] + " " + match.group(0)) not in flat:
        return False
    return _CONDUCTOR_WRITES in _flat(_cited_paragraph_below(match.group("cited"), text))


def test_rule_routes_a_refused_write_through_the_agent_s_text():
    assert _refused_write_is_routed(_rule())
    assert _REFUSED in _flat(_rule())


def test_the_cited_paragraph_exists_below_and_gives_the_route():
    """"Automate's summary records its rows" (below) opens one paragraph, below
    this one, and that paragraph has the conductor write automate's returned
    text unchanged."""
    assert GATE.count("\n" + _SUMMARY_HEAD + " ") == 1
    assert GATE.index(_rule()) < GATE.index(_SUMMARY_HEAD)
    summary = _flat(_paragraph(GATE, _SUMMARY_HEAD))
    assert _CONDUCTOR_WRITES in summary
    assert _SUMMARY_HEAD == "**" + _REFUSED_RE.search(_flat(_rule())).group("cited") + ".**"


def test_refused_write_predicate_rejects_the_text_without_the_paragraph():
    assert not _refused_write_is_routed(_backfill_section(_without_the_rule()))
    # The cited paragraph alone, which routes automate's text, routes no assessor's.
    assert not _refused_write_is_routed(_paragraph(GATE, _SUMMARY_HEAD))


def test_refused_write_predicate_rejects_a_citation_placed_above():
    """With the cited paragraph moved above this one, "(below)" no longer holds."""
    summary = _paragraph(GATE, _SUMMARY_HEAD)
    moved = GATE.replace(summary + "\n\n", "", 1).replace(_HEAD, summary + "\n\n" + _HEAD, 1)
    assert moved != GATE and moved.index(_SUMMARY_HEAD) < moved.index(_HEAD)
    assert not _refused_write_is_routed(_rule(), moved)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(" " + _REFUSED, "", id="dropped"),
        pytest.param("it returns the file's full text in its result", "it writes it some other way",
                     id="write-it-some-other-way"),
        pytest.param("it returns the file's full text in its result", "it returns a summary of the file in its result",
                     id="summary-not-the-text"),
        pytest.param("write that text yourself, unchanged,", "rewrite that text yourself, unchanged in substance,",
                     id="conductor-rewrites-the-text"),
        pytest.param("write that text yourself, unchanged,", "write that text yourself,", id="unchanged-dropped"),
        pytest.param("\"Automate's summary records its rows\"", "\"Automate's summary records its text\"",
                     id="cites-a-heading-that-does-not-exist"),
        pytest.param("\"Automate's summary records its rows\"",
                     "\"A summary already at that name is this cycle's own\"",
                     id="cites-a-paragraph-without-the-route"),
        pytest.param("(below) has you write automate's.", "(above) has you write automate's.", id="cited-above"),
        # The route moved after the fallbacks, away from the bans it qualifies.
        pytest.param(" " + _REFUSED + " " + _HAND_AUTHORED + " " + _NO_AGENT + " " + _MODE_CASE,
                     " " + _HAND_AUTHORED + " " + _NO_AGENT + " " + _MODE_CASE + " " + _REFUSED, id="moved-after"),
    ],
)
def test_refused_write_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _refused_write_is_routed(_mutant(old, new))


# --- a hand-authored file is a delegated agent's, where TEA cannot run ------------


def _hand_authored_is_delegated(rule: str) -> bool:
    return _HAND_AUTHORED in _flat(rule)


def test_rule_has_a_delegated_agent_write_a_hand_authored_file():
    assert _hand_authored_is_delegated(_rule())
    # The cited heading exists, below the paragraph, as "(below)" says.
    cited = re.search(r'A file written to "([^"]+)" \(below\)', _rule()).group(1)
    assert _SHAPES_HEAD.startswith("**" + cited + " ")
    assert GATE.count(_SHAPES_HEAD) == 1
    assert GATE.index(_rule()) < GATE.index(_SHAPES_HEAD)
    # The shapes cover a file an agent writes, not only one written by hand.
    assert "a hand- or agent-authored file must carry the exact fields below" in _flat(_paragraph(GATE, _SHAPES_HEAD))


def test_hand_authored_predicate_rejects_the_text_without_the_paragraph():
    assert not _hand_authored_is_delegated(_backfill_section(_without_the_rule()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(", and a delegated agent writes it.", ", and you write it.", id="conductor-writes-it"),
        pytest.param(", and a delegated agent writes it.", ".", id="writer-unstated"),
        pytest.param("is for a story whose TEA skill cannot run", "is for any story", id="any-story"),
        pytest.param('"Hand-authored `nfr-assessment.md` and `test-review.md` shapes"',
                     '"Hand-authored `nfr-assessment.md` shapes"', id="cites-another-heading"),
    ],
)
def test_hand_authored_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _hand_authored_is_delegated(_mutant(old, new))


# --- a session that cannot start such an agent runs the skill, then writes ------


def _no_agent_does_it_itself(rule: str) -> bool:
    """A session that cannot start the agent the delegation names ("such an
    agent") runs the skill itself first, and writes the hand-authored file
    ("that file") itself only where the skill cannot run. The sentence follows
    the delegation, which gives "such an agent" its kind, and directly follows
    the hand-authored sentence, which gives "that file" its antecedent; the mode
    case and the log sentence follow it."""
    flat = _flat(rule)
    if (_HAND_AUTHORED + " " + _NO_AGENT + " " + _MODE_CASE + " " + _LOGGED) not in flat:
        return False
    return (_DELEGATES + _FRESH) in flat and flat.index(_DELEGATES + _FRESH) < flat.index(_NO_AGENT)


def test_a_session_that_cannot_start_such_an_agent_runs_the_skill_then_writes_the_file():
    assert _no_agent_does_it_itself(_rule())
    assert _NO_AGENT in _flat(_rule())


def test_no_agent_predicate_rejects_the_text_without_the_paragraph():
    assert not _no_agent_does_it_itself(_backfill_section(_without_the_rule()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("cannot start such an agent", "cannot start an agent", id="an-agent-of-any-kind"),
        pytest.param(_SKILL_FIRST, "escalates the story.", id="escalates"),
        pytest.param(_SKILL_FIRST, "stops the run.", id="stops"),
        pytest.param(_SKILL_FIRST, "waits until it can start one.", id="waits"),
        pytest.param(_SKILL_FIRST, "skips the assessment.", id="skips"),
        pytest.param(_SKILL_FIRST, "runs the skill itself.", id="skill-only-no-hand-authored-file"),
        pytest.param(_SKILL_FIRST, "writes that file itself.", id="file-only"),
        pytest.param(_SKILL_FIRST, "runs the skill itself or writes that file itself.",
                     id="file-a-free-alternative"),
        pytest.param(", or, where the skill cannot run, writes", ", or, where it prefers, writes", id="file-by-choice"),
        pytest.param(_SKILL_FIRST, "writes that file itself, or, where it cannot, runs the skill itself.",
                     id="file-first"),
        pytest.param(" " + _NO_AGENT, "", id="dropped"),
        # "That file" moved away from the sentence that names it.
        pytest.param(_HAND_AUTHORED + " " + _NO_AGENT, _NO_AGENT + " " + _HAND_AUTHORED, id="before-the-file"),
    ],
)
def test_no_agent_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _no_agent_does_it_itself(_mutant(old, new))


# --- THE MODE CASE: TEA's mode error falls back, it does not stop ----------------

_MODE_OPENER = "So does one whose delegated assessment ends in TEA's error that its execution mode cannot run ("
_FALLBACK = "): it runs the skill where that mode can run, for the rest of the run."


def _mode_case_falls_back(rule: str) -> bool:
    """A delegated assessment that ends in TEA's mode error, for either mode TEA
    can fail to run with its probe off, is followed by running the skill where
    that mode can run, for the rest of the run and not for one assessment, and
    the case is logged and stops nothing."""
    flat = _flat(rule)
    start = flat.find(_MODE_OPENER)
    if start == -1:
        return False
    end = flat.find(_FALLBACK, start)
    if end == -1:
        return False
    condition = flat[start + len(_MODE_OPENER) : end]
    if not (
        "`tea_capability_probe: false`" in condition
        and re.search(r"a `tea_execution_mode` of `subagent` or `agent-team`(?:,|$)", condition)
    ):
        return False
    # "So does one" takes its verb from the no-agent sentence, and the log
    # sentence after it covers each case.
    sentence = flat[start : end + len(_FALLBACK)]
    return (_NO_AGENT + " " + sentence + " " + _LOGGED) in flat and _adds_no_stop(rule)


_STOP_WORDS = re.compile(
    r"escalat|halt|park|block|re-?loop|abort|paus|\bwait|\bends? the run|\bstop(?!s none of them)", re.IGNORECASE
)


def _adds_no_stop(rule: str) -> bool:
    return _STOP_WORDS.search(_flat(rule)) is None


def test_mode_error_falls_back_to_running_the_skill_where_the_mode_can_run():
    assert _mode_case_falls_back(_rule())
    assert _MODE_CASE in _flat(_rule())


def test_mode_case_predicate_rejects_the_text_without_the_paragraph():
    assert not _mode_case_falls_back(_backfill_section(_without_the_rule()))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_FALLBACK, ").", id="fallback-dropped"),
        pytest.param(_FALLBACK, "): it escalates the story.", id="escalates"),
        pytest.param(_FALLBACK, "): it halts the run.", id="halts"),
        pytest.param(_FALLBACK, "): it parks the story.", id="parks"),
        pytest.param(_FALLBACK, "): it is blocked until the operator answers.", id="blocks"),
        pytest.param(_FALLBACK, "): it re-loops the story.", id="re-loops"),
        pytest.param(", for the rest of the run.", ".", id="rest-of-the-run-dropped"),
        pytest.param("for the rest of the run.", "for this assessment.", id="this-assessment-only"),
        pytest.param("for the rest of the run.", "for the rest of the story.", id="this-story-only"),
        pytest.param("a `tea_execution_mode` of `subagent` or `agent-team`", "a `tea_execution_mode` of `agent-team`",
                     id="subagent-mode-dropped"),
        pytest.param("a `tea_execution_mode` of `subagent` or `agent-team`", "a `tea_execution_mode` of `subagent`",
                     id="agent-team-mode-dropped"),
        pytest.param("`tea_capability_probe: false` with ", "", id="probe-dropped"),
        pytest.param("So does one whose delegated assessment", "So does one whose assessment", id="any-assessment"),
        pytest.param(_LOGGED, "This rule stops none of these cases.", id="unlogged"),
        pytest.param(": this rule stops none of them.", ", then escalate the story.", id="log-then-escalate"),
        # The case moved ahead of the sentence whose verb it borrows.
        pytest.param(_NO_AGENT + " " + _MODE_CASE, _MODE_CASE + " " + _NO_AGENT, id="before-no-agent"),
    ],
)
def test_mode_case_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _mode_case_falls_back(_mutant(old, new))


def test_the_paragraph_adds_no_stop():
    """Neither fallback stops the run, and the paragraph names no stop of any
    kind, so no run that works today starts to stop on it."""
    assert _adds_no_stop(_rule())
    assert _LOGGED in _flat(_rule())


# --- the last sentence: each case is logged, and the rule stops none ------------

_NO_STOP_CLAUSE = ": this rule stops none of them."


def _logs_each_case_and_stops_none(rule: str) -> bool:
    """The paragraph ends on one sentence, right after the mode case, that has
    each case it names logged in `.decision-log.md` and says the rule stops none
    of them, and nothing in the paragraph names a stop (the word check)."""
    return _flat(rule).strip().endswith(_MODE_CASE + " " + _LOGGED) and _adds_no_stop(rule)


def test_the_last_sentence_logs_each_case_and_stops_none():
    assert _logs_each_case_and_stops_none(_rule())


def test_logged_predicate_rejects_the_text_without_the_paragraph():
    assert not _logs_each_case_and_stops_none(_backfill_section(_without_the_rule()))
    assert not _logs_each_case_and_stops_none(_paragraph(_backfill_section(), _NFR_HEAD))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(" " + _LOGGED, "", id="dropped"),
        pytest.param(", say so in `.decision-log.md`:", ",", id="log-dropped"),
        pytest.param("say so in `.decision-log.md`", "say so in the story file", id="logged-elsewhere"),
        pytest.param("say so in `.decision-log.md`", "say so to the operator", id="told-not-logged"),
        pytest.param("In each of these cases", "In the first of these cases", id="first-case-only"),
        pytest.param(_NO_STOP_CLAUSE, ".", id="no-stop-clause-dropped"),
        pytest.param("this rule stops none of them", "this rule stops each of them", id="stops-each"),
        pytest.param("this rule stops none of them", "this rule stops the second of them", id="stops-one"),
        pytest.param(_NO_STOP_CLAUSE, ", then escalate the story.", id="log-then-escalate"),
        pytest.param(_LOGGED, _LOGGED + " A mode error that recurs halts the run.", id="stop-appended"),
        pytest.param(_MODE_CASE + " " + _LOGGED, _LOGGED + " " + _MODE_CASE, id="before-the-mode-case"),
    ],
)
def test_logged_predicate_rejects_a_one_clause_mutant(old, new):
    assert not _logs_each_case_and_stops_none(_mutant(old, new))


@pytest.mark.parametrize(
    "added",
    [
        pytest.param("When neither can, escalate the story.", id="escalate"),
        pytest.param("Halt when the mode cannot run anywhere.", id="halt"),
        pytest.param("Park the story until an operator answers.", id="park"),
        pytest.param("A mode error blocks the story.", id="block"),
        pytest.param("A mode error is a reloop.", id="reloop"),
        pytest.param("A mode error is a re-loop.", id="re-loop"),
        pytest.param("A mode error stops the run.", id="stop"),
        pytest.param("The run waits for the operator.", id="wait"),
        pytest.param("A mode error aborts the run.", id="abort"),
        pytest.param("The run pauses for the operator.", id="pause"),
        pytest.param("A mode error ends the run.", id="ends-the-run"),
    ],
)
def test_no_stop_predicate_rejects_an_added_stop(added):
    assert not _adds_no_stop(_mutant(_LOGGED, _LOGGED + " " + added))


def test_no_stop_predicate_rejects_a_no_agent_sentence_that_stops_the_run():
    assert not _adds_no_stop(_mutant(_NO_AGENT, _SUCH_AN_AGENT + "stops the run."))


def test_the_stop_word_check_does_not_match_the_live_paragraph():
    """The one stop word the paragraph holds is its own "stops none of them"."""
    flat = _flat(_rule())
    assert _STOP_WORDS.search(flat) is None
    assert _STOP_WORDS.search(flat.replace("stops none of them", "stops each of them")) is not None


def test_the_modes_are_the_ones_tea_and_preflight_name():
    """TEA's execution modes, as preflight and TEA's reference name them, and the
    probe that, set to false, makes an unexecutable mode fail instead of falling
    back. Of the four modes, only `subagent` and `agent-team` start agents."""
    assert (
        "`tea_execution_mode` is TEA's parallelism setting (`auto`, `subagent`, `agent-team` or `sequential`)"
        in _flat(PREFLIGHT)
    )
    tea = _repo_tea_reference()
    skill = _flat((tea / "SKILL.md").read_text(encoding="utf-8"))
    assert "`tea_execution_mode` (`auto`, `subagent`, `agent-team` or `sequential`)" in skill
    assert "Setting `tea_capability_probe: false` makes an unexecutable mode fail instead of falling back." in skill
    config = _flat((tea / "references" / "pattern-config-and-registration.md").read_text(encoding="utf-8"))
    assert "| `tea_capability_probe` | `true` | Probe runtime support and fall back; `false` honours the mode strictly" in (
        config
    )
    # The error is one both assessments can end in: NFR step 4 and test-review
    # step 3 resolve the mode the same way.
    shared = _flat((tea / "references" / "pattern-atdd-and-automate.md").read_text(encoding="utf-8"))
    assert "NFR step 4, test-review step 3" in shared
    assert "with probing off an unexecutable mode fails with an explicit error" in shared
    nfr = _flat((tea / "references" / "pattern-nfr.md").read_text(encoding="utf-8"))
    assert "unexecutable mode with probing off" in nfr


def _repo_tea_reference() -> Path:
    """The tracked reference skill for the TEA version this module targets."""
    group = _REPO / "skf-skills" / "tea-testarch"
    active = group / "active"
    version = active.resolve().name if active.is_dir() else active.read_text(encoding="utf-8").strip()
    return group / version / "tea-testarch"


# --- the paragraph holds these sentences and nothing else, in its place ----------


def _rule_is_whole(rule: str) -> bool:
    return _flat(rule).strip() == " ".join(_SENTENCES)


def test_rule_holds_nothing_else():
    assert _rule_is_whole(_rule())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_LOGGED, _LOGGED + " A ruling may lift a status.", id="appended"),
        pytest.param(_WHY, _WHY + " A summary of the rulings may go with each delegation.", id="after-the-why"),
    ],
)
def test_whole_rule_predicate_rejects_an_added_sentence(old, new):
    assert not _rule_is_whole(_mutant(old, new))


_BACKFILL_COMMIT_HEAD = "**When automate backfills, commit the backfill before trace runs.**"


def _in_place(text: str) -> bool:
    """The paragraph sits in "Backfill the gate evidence", directly after the NFR
    assessor's and directly before the backfill-commit paragraph, so no paragraph
    added beside it can take back what it says (a stop, a fork, your own context)
    without failing this pin."""
    section = _backfill_section(text)
    nfr = _paragraph(section, _NFR_HEAD)
    rule = _paragraph(section, _HEAD)
    return bool(nfr and rule) and (nfr + "\n\n" + rule + "\n\n" + _BACKFILL_COMMIT_HEAD) in section


def test_rule_sits_directly_after_the_nfr_paragraph():
    assert _in_place(GATE)


def test_placement_predicate_rejects_a_moved_or_separated_paragraph():
    rule = _rule()
    without = _without_the_rule()
    assert not _in_place(without)
    moved = without.replace("## Run the gate\n", "## Run the gate\n\n" + rule + "\n", 1)
    assert moved != without and not _in_place(moved)
    nfr = _paragraph(GATE, _NFR_HEAD)
    swapped = GATE.replace(nfr + "\n\n" + rule, rule + "\n\n" + nfr, 1)
    assert swapped != GATE and not _in_place(swapped)
    split = GATE.replace(nfr + "\n\n", nfr + "\n\nAn assessor may read the decision log.\n\n", 1)
    assert split != GATE and not _in_place(split)
    # A paragraph added after it, before the backfill-commit paragraph, is rejected too.
    for added in ("When no such agent can be started, escalate the story.",
                  "A fork will do for either assessment when fork mode is on."):
        after = GATE.replace(rule + "\n\n", rule + "\n\n" + added + "\n\n", 1)
        assert after != GATE and not _in_place(after)


# --- Execute step 3 points at the paragraph ---------------------------------------

_POINTER_8_1_0 = (
    "Hand the test reviewer only what `references/gate.md`'s \"The test reviewer reads the tests, not the run's "
    "account of them\" lists, and move the story's earlier review aside as it says, on a re-loop's review too: unless "
    "the gate runs a test review of its own, it reads this one's score."
)
_POINTER = (
    "Run the test review in an agent you start for it, never a fork, as `references/gate.md`'s " + _CITED + " says."
)


def _step3_points_at_the_rule(step: str) -> bool:
    """Step 3 still opens with the test review and ends with the 8.1.0 pointer
    followed directly by this one, so no sentence after it can take it back."""
    flat = _flat(step).strip()
    return flat.startswith("3. **Production profile only:** `bmad-testarch-test-review`") and flat.endswith(
        _POINTER_8_1_0 + " " + _POINTER
    )


def test_execute_step_3_points_at_the_rule():
    assert _step3_points_at_the_rule(_step3())
    # The name step 3 cites is the paragraph's opener, in the backfill section.
    assert _HEAD == "**" + _CITED.strip('"') + ".**"
    assert _HEAD in _backfill_section()
    assert EXECUTE.count(_CITED) == 1


def test_step_3_predicate_rejects_the_step_without_the_pointer():
    step = _step3()
    without = step.replace(" " + _POINTER, "", 1)
    assert without != step
    assert not _step3_points_at_the_rule(without)
    # The 8.1.0 pointer is still in the step once this one is cut.
    assert _POINTER_8_1_0 in _flat(without)
    # A sentence added after the pointer could take it back, so it is rejected.
    for added in ("When no such agent can be started, escalate the story.",
                  "Where fork mode is on, a fork will do.",
                  "A re-loop's review may run in your own context."):
        assert not _step3_points_at_the_rule(_flat(step).strip() + " " + added)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_CITED, '"The test reviewer reads the tests, not the run\'s account of them"',
                     id="cites-another-paragraph"),
        pytest.param("Run the test review in an agent you start for it,", "Run the test review yourself,",
                     id="own-context"),
        pytest.param("Run the test review in an agent you start for it,", "Run the test review in any agent,",
                     id="shared-agent"),
        pytest.param("Run the test review in an agent", "Run the code review in an agent", id="names-the-code-review"),
        pytest.param(", never a fork, as", ", as", id="fork-allowed"),
        pytest.param(", never a fork, as", ", a fork if fork mode is on, as", id="fork-when-on"),
        pytest.param(_POINTER_8_1_0 + " " + _POINTER, _POINTER + " " + _POINTER_8_1_0, id="before-the-8-1-0-pointer"),
    ],
)
def test_step_3_predicate_rejects_a_one_clause_mutant(old, new):
    step = _flat(_step3())
    mutant = step.replace(old, new)
    assert mutant != step, "the mutant must actually change the text"
    assert not _step3_points_at_the_rule(mutant)
