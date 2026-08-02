"""Four controls that reported themselves active while enforcing nothing.

Static prose-contract assertions. Each group below pins a clause written because
a surface CLAIMED to be gating something and was not - the failure mode that is
worse than an absent control, because the log says it is armed.

  - MATCHER. The PreToolUse guard's sixth invariant gates a claude-mem MCP call.
    Driven directly with a red latch, the shipped hook DOES deny
    `mcp__plugin_claude-mem_mcp-search__search`. But both known installs register
    the group with `matcher: "Bash"`, and Claude Code only invokes a group for
    tools its matcher selects - so the hook is never asked, and the invariant is
    inert in exactly the case it exists for. Nothing in preflight.md named a
    matcher; its arming assertion checked PRESENCE only, which a Bash-only
    arming passes.

  - THE THIRD STATE. ingest-and-scope.md forked recall on off / tools-unavailable.
    The ordinary headless reality is neither: the tools are LISTED, ToolSearch
    resolves them, and the refusal arrives only on the call. Recorded 25+
    consecutive runs. A reader who checked the tool list took the on-with-tools
    branch and failed mid-section, then had to decide unaided what to latch -
    and different runs latched differently.

  - THE READ PROBE AUTHORIZING A WRITE. The latch is validated by a
    `get_observations`-shaped probe, and finalize routed a `save_observation`
    off it. On a surface exposing read tools and no write tool of any name, the
    drain then replays every parked payload against nothing, bumping each one
    closer to the dead-letter file: the step meant to rescue parked work
    destroys it.

  - THE RESUME THAT COULD NEVER LAUNCH. formalize_check.py is epic-scoped by
    construction, so on a long Epic it reads blocked on gaps belonging to
    undrafted stories (41 mechanical gaps and 20 judgment candidates on one real
    Epic, essentially none in the story being driven). A conductor applying the
    launch non-negotiable literally on every resume blocks a healthy run forever.

Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_INGEST = _SKILL_ROOT / "references" / "ingest-and-scope.md"
_FINALIZE = _SKILL_ROOT / "references" / "finalize.md"
_SKILL = _SKILL_ROOT / "SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(path: Path, heading: str) -> str:
    """One `## ` section's body. Locality matters more than presence here.

    A whole-file search would let the drain-skip prose be relocated BELOW the
    drain step it is supposed to guard and stay green - and an instruction that
    arrives after the destructive step is not an instruction.
    """
    text = _read(path)
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start:] if end == -1 else text[start:end]


def _recall_write_section() -> str:
    return _section(_FINALIZE, "## Cross-Session Recall write")


# --- The PreToolUse matcher --------------------------------------------------


def test_preflight_pins_an_all_tools_matcher():
    text = _read(_PREFLIGHT)
    assert re.search(r'"matcher":\s*"\*"', text), "the all-tools matcher form is named literally"
    assert re.search(r"covers EVERY tool, not just `Bash`", text)
    # The reason, not just the instruction: a rule without its reason gets
    # optimized away by the next reader who finds Bash sufficient.
    assert re.search(r"only invokes a PreToolUse group for tools its matcher selects", text, re.I)


def test_preflight_requires_the_assertion_to_check_the_matcher_not_just_presence():
    text = _read(_PREFLIGHT)
    assert re.search(r"presence-only assertion passes on a `Bash`-only arming", text, re.I), (
        "the arming assertion must name what a presence check misses, or it "
        "stays the same check it was"
    )


def test_the_latch_invariant_says_it_depends_on_the_matcher():
    """The sub-bullet claiming the guard 'reads it automatically' needs the caveat."""
    text = _read(_PREFLIGHT)
    latch_bullet = next(
        ln for ln in text.splitlines() if "Cross-Session Recall latch from" in ln
    )
    assert "enforces nothing unless the matcher above covers MCP tools" in latch_bullet


# --- The third state ---------------------------------------------------------


def test_ingest_forks_on_three_states_not_two():
    text = _read(_INGEST)
    fork = next(ln for ln in text.splitlines() if ln.startswith("If recall is `\"off\"`"))
    assert "refused by the permission layer" in fork, "the third state is in the FORK itself"
    assert re.search(r"THIRD state", text), "and it is named as such"
    assert re.search(r"cannot be decided before spending one call", text, re.I)


def test_ingest_forbids_synthesizing_a_probe_for_a_denied_call():
    """The fabrication hazard: an empty probe latches GREEN off a call never made."""
    text = _read(_INGEST)
    assert re.search(r"Never synthesize a probe", text, re.I)
    assert re.search(r"latches GREEN", text), "it must say what the fabrication buys"


def test_ingest_still_requires_the_call_despite_a_prior_denial():
    """Skipping on a prior note asserts an unavailability THIS run never measured."""
    text = _read(_INGEST)
    assert re.search(r"Still make the call even when a prior session recorded", text, re.I)
    assert re.search(r"off in practice", text), "and says what a recurring denial means"


def test_the_denial_is_one_attempt_only():
    text = _read(_INGEST)
    assert re.search(r"Treat the first denial as final", text, re.I)


# --- The read probe authorizing a write --------------------------------------


def test_finalize_separates_read_capability_from_write_capability():
    text = _recall_write_section()
    assert re.search(r"certifies the READ surface", text, re.I)
    assert re.search(r"clearance to \*look\*, not proof there is anywhere to write", text, re.I)


def test_finalize_skips_the_drain_when_there_is_no_write_tool():
    """The drain is the destructive half, so its skip is the load-bearing clause."""
    text = _read(_FINALIZE)
    assert re.search(r"do not call and do not drain", text, re.I)
    assert re.search(r"Skipping the drain is the load-bearing half", text, re.I)
    assert re.search(r"closer to the dead-letter file", text, re.I)


def test_finalize_distinguishes_absence_from_a_failed_call():
    """`WARN mem-write-deferred` means a call was attempted; absence is not that."""
    text = _read(_FINALIZE)
    assert "NOTE mem-write-unavailable" in text
    assert re.search(r"Not `WARN mem-write-deferred`", text)


# --- The resume that could never launch --------------------------------------


def test_skill_scopes_the_formalize_gate_to_the_stage_2_entry():
    text = _read(_SKILL)
    assert re.search(
        r"resume routed into Execute does NOT re-run the Stage-2 formalize gate", text
    )
    assert re.search(r"epic-scoped by construction", text), "the mechanism, not just the rule"
    assert re.search(r"takes no `--story`", text)
    assert re.search(r"block a healthy run forever", text), "the consequence of reading it literally"


def test_the_launch_non_negotiable_still_says_what_it_always_said():
    """Scoping the bullet must not weaken it: the pinned opening is unchanged.

    `test_skill_nonnegotiable_formalize.py` asserts that exact phrase, and the
    scoping was appended rather than spliced in for precisely that reason.
    """
    text = _read(_SKILL)
    assert "Launch the unattended run only when `scripts/preflight_check.py` returns green" in text
    launch = next(ln for ln in text.splitlines() if ln.startswith("- **Launch the unattended run"))
    assert "This binds the **Stage-2 entry**." in launch
    assert len(re.findall(r"^- \*\*", text, re.M)) >= 6


def test_the_write_tool_precondition_is_in_the_branch_condition_itself():
    """The branch heading must NAME the write tool, not merely discuss it nearby.

    Reverting the heading from "+ a write tool" back to the original left every
    other check in this file green: the surrounding prose still explained the
    hazard while the branch a reader actually routes on said nothing about it.
    """
    section = _recall_write_section()
    heading = next(
        ln for ln in section.splitlines() if ln.startswith("**Present + `schema_ok`")
    )
    assert "a write tool" in heading, (
        "the routing condition itself must require a write tool; prose above it "
        "is not what a reader branches on"
    )


def test_the_drain_skip_precedes_the_drain_step():
    """An instruction that arrives after the destructive step is not one."""
    section = _recall_write_section()
    assert section.index("do not call and do not drain") < section.index(
        "**Drain the outbox**"
    ), "the do-not-drain rule must come before the drain step it guards"


def test_the_matcher_rule_is_in_the_hooks_bullet_not_merely_in_the_file():
    """Locality: preflight.md is 170+ lines and the arming instruction is one bullet."""
    text = _read(_PREFLIGHT)
    start = text.index("- **Hooks.**")
    end = text.index("\n- **Allowlist.**", start)
    hooks_bullet = text[start:end]
    assert re.search(r'"matcher":\s*"\*"', hooks_bullet), (
        "the matcher rule must live in the Hooks bullet, where a run arming the "
        "hooks is actually reading"
    )
    assert re.search(r"presence-only assertion", hooks_bullet)


def test_the_third_state_precedes_the_on_with_tools_branch():
    """A reader who reaches the on-with-tools branch first has already lost.

    The whole failure was: check the tool list, conclude on-with-tools, issue the
    search, get denied mid-section. The third state has to be readable before
    that branch, not after it.
    """
    text = _read(_INGEST)
    assert text.index("THIRD state") < text.index(
        "When `{workflow.cross_session_recall}` is `\"on\"` **and** the claude-mem MCP tools are present"
    )


def test_the_operator_doc_carries_the_headless_caveats():
    """The stage files tell the RUN what to do; this tells the OPERATOR why.

    `recall-on-but-unusable-every-run` is an operator/config item, so closing it
    only in the stage files would leave the person who can actually fix it - by
    granting the permission once, or setting the knob to off - reading a page
    that still says the dependency is just "claude-mem installed".
    """
    doc = Path(__file__).resolve().parents[4] / "docs" / "cross-session-recall.md"
    text = doc.read_text(encoding="utf-8")
    assert re.search(r"off in practice", text)
    assert re.search(r"25 consecutive runs", text), "the observed scale, not a vague caution"
    assert re.search(r"a group armed for `Bash` alone is never invoked", text)
    assert re.search(r"reads without a write", text, re.I)
