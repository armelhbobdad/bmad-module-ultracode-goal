"""Prose contract over preflight under Auto Mode: a refused settings write, a
repository with nothing committed, and a missing project-context.md.

A real run showed all three. Under Auto Mode the permission classifier refused
the conductor's write to `.claude/settings.local.json` and the calls after it,
and the reference had no route for that. A fresh `git init` hid the
protected-branch blocker, so a remediation commit could have become the
repository's root commit. And the project-context bullet named a generator that,
on BMAD Method 6.12, writes an AGENTS.md block instead of the file being counted.

Each predicate below is checked against the live reference; the ones that
could pass on prose that merely mentions the topic are also checked, as their
anti-vacuous twins, against a single-clause mutant or the pre-edit wording,
which they must reject. Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_SKILL = _SKILL_ROOT / "SKILL.md"


def _text() -> str:
    return _PREFLIGHT.read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i : text.index(end, i)]


def _step2() -> str:
    return _between(_text(), "## 2. Auto-remediation pass", "## 3. ")


def _step5() -> str:
    return _between(_text(), "## 5. Arm the environment", "### Launch briefing")


def _bullet(block: str, prefix: str) -> str:
    match = re.search(r"^" + re.escape(prefix) + r".*$", block, re.M)
    assert match, f"missing bullet starting {prefix!r}"
    return match.group(0)


# --- A refused settings write ----------------------------------------------


def _refused_write_rule() -> str:
    return _between(_step2(), "**A refused settings write.**", "**Ordering.**")


def _stops_on_a_refused_write(rule: str) -> bool:
    """True only for prose that stops, forbids the workarounds, and routes both modes."""
    return bool(
        re.search(r"as a stop", rule)
        and re.search(r"[Dd]o not retry it through another tool", rule)
        and re.search(r"do not forge a marker", rule)
        and re.search(r"do not skip the step-5 assertion", rule)
        and re.search(r"\*\*Attended:\*\*.*?/permissions", rule, re.S)
        and re.search(r"\*\*Headless:\*\*.*?\*\*RED\*\*", rule, re.S)
    )


def test_step2_routes_a_refused_settings_write():
    assert _stops_on_a_refused_write(_refused_write_rule())


def test_refused_write_predicate_rejects_the_pre_edit_disarm():
    """The pre-edit stale-hook paragraph demanded the disarm with no route for a
    refusal; the predicate must not be satisfied by it."""
    pre_edit = (
        "**Stale-hook pre-arming (before any remediation commit).** Do **not** forge "
        "a marker and do **not** wait on the gate: **disarm the prior-run hooks "
        "first**, then make the remediation commit."
    )
    assert not _stops_on_a_refused_write(pre_edit)


def _operator_route_is_bounded(rule: str) -> bool:
    """The terminal route skips every guard check for its one command, so it must
    be limited to a refused disarm, on the Epic branch, before Execute, with no push."""
    return bool(
        re.search(r"A refused \*\*disarm\*\* has one more route", rule)
        and re.search(
            r"only after confirming the current branch is `\{workflow\.epic_branch_prefix\}<epic-id>`",
            rule,
        )
        and re.search(r"only for a remediation commit made before Execute", rule)
        and re.search(r"no push", rule)
    )


def test_operator_commit_route_is_bounded():
    assert _operator_route_is_bounded(_refused_write_rule())


def test_operator_route_predicate_rejects_an_unbounded_route():
    """Drop only the branch condition: the route would then be offered on a
    protected branch, where the guard it bypasses exists to refuse commits."""
    mutant = _refused_write_rule().replace(
        "only after confirming the current branch is `{workflow.epic_branch_prefix}<epic-id>`, and ",
        "",
    )
    assert mutant != _refused_write_rule(), "the mutant must actually change the rule"
    assert not _operator_route_is_bounded(mutant)


def test_refusal_stop_covers_every_call_until_the_assertion_passes():
    """The classifier's refusals are contextual: one call after the write can pass
    and a later one be refused, so the stop cannot end at the next call."""
    assert re.search(
        r"any call after it until the assertion that write serves has passed",
        _refused_write_rule(),
    )


def test_headless_route_names_the_way_back():
    assert re.search(r"The way back is that attended pass, not `/ucg-resolve`", _refused_write_rule())


def _operator_route_needs_no_bang(rule: str) -> bool:
    """Issue #186: Claude Code's docs do not say whether a `!` command passes
    the PreToolUse hooks, so the route hands a command for a terminal outside
    the session, and says not to offer it as a `!` command."""
    return bool(
        re.search(r"one command, to run in a terminal outside this session", rule)
        and re.search(r"A command run there is no tool call, so no PreToolUse hook reads it", rule)
        and re.search(r"Do not offer it as a `!` command in the session", rule)
        and "`!`-prefixed command" not in rule
        and "A `!` command runs outside the PreToolUse hooks" not in rule
    )


def test_the_operator_route_does_not_rest_on_bang_mode():
    assert _operator_route_needs_no_bang(_refused_write_rule())


def test_the_bang_predicate_rejects_the_4_0_0_route():
    pre_edit = (
        "A refused **disarm** has one more route. Hand the operator one `!`-prefixed command that stages the "
        "named remediation paths and commits them on the current branch, with no push. A `!` command runs "
        "outside the PreToolUse hooks, so the commit needs no disarm and the hooks stay armed."
    )
    assert not _operator_route_needs_no_bang(pre_edit)


def _resume_way_back_is_named(rule: str) -> bool:
    """Issue #186: a headless resume escalates a refused write, so its way back
    closes that escalation with /ucg-resolve, unlike Stage 2's."""
    return bool(
        re.search(r"A resume never reaches this stage", rule)
        and re.search(r"it escalates the story it was about to drive instead", rule)
        and re.search(r"an attended resume that makes the write, with `/ucg-resolve` closing that escalation", rule)
    )


def test_the_refused_write_rule_names_a_resume_s_way_back():
    assert _resume_way_back_is_named(_refused_write_rule())


_DOCS = _SKILL_ROOT.parents[1] / "docs"


def _troubleshooting_refused_write() -> str:
    text = (_DOCS / "troubleshooting.md").read_text(encoding="utf-8")
    bullet = re.search(r"^- \*\*A refused settings write\.\*\*.*$", text, re.M)
    assert bullet
    return bullet.group(0)


def test_troubleshooting_gives_a_headless_resume_its_way_back():
    """Issue #186: the bullet said /ucg-resolve is not the way back, while a
    headless resume's refused write leaves an escalation only /ucg-resolve
    closes. And a headless session is not always refused the write."""
    bullet = _troubleshooting_refused_write()
    assert "At preflight the run then stops, and `/ucg-resolve` is not the way back" in bullet
    assert "a headless resume whose write is refused escalates the story it was about to drive instead" in bullet
    assert "close that escalation with `/ucg-resolve`, which the resume offers before it drives the story" in bullet
    assert "under `bypassPermissions` the write lands, under Auto Mode the classifier decides" in bullet


def test_getting_started_no_longer_says_a_headless_session_cannot_approve_the_write():
    text = " ".join((_DOCS / "getting-started.md").read_text(encoding="utf-8").split())
    assert "A headless session cannot approve that write" not in text
    assert "A headless session may be refused that write, and then nobody is there to approve it" in text
    assert "Only `bypassPermissions` lets it land unreviewed." in text


def test_troubleshooting_names_the_ancestor_project_a_missing_guard_syncs():
    text = " ".join((_DOCS / "troubleshooting.md").read_text(encoding="utf-8").split())
    assert (
        "When the project, or a folder above it, holds a `pyproject.toml`, `uv run` syncs that project on every call "
        "before it finds the script missing" in text
    )


def test_troubleshooting_says_a_missing_budget_script_blocks_each_stop():
    """Review of #186: `uv run` exits 2 for a script it cannot find, and exit 2
    on a Stop hook blocks the stop, though the budget script itself never does."""
    text = " ".join((_DOCS / "troubleshooting.md").read_text(encoding="utf-8").split())
    assert (
        "The budget hook's command points at nothing too. `uv` exits 2 when it cannot find the script, which on a "
        "`Stop` hook Claude Code reads as a block" in text
    )
    assert "and `uv` exits 2 when it cannot find a script" not in text


def test_troubleshooting_names_the_blocks_after_which_a_stop_goes_through():
    """Review of #186's fix (4.1.0): Claude Code overrides a Stop hook's block
    after eight consecutive continuations, and the count resets when Claude
    calls a tool (cc-primitives hooks reference, from the hooks docs), so the
    session is not sent back every time it tries to stop."""
    text = " ".join((_DOCS / "troubleshooting.md").read_text(encoding="utf-8").split())
    assert (
        "each time the session tries to stop, it is sent back with uv's error instead, up to eight times in a row, "
        "after which Claude Code lets the stop through (the count starts again whenever Claude calls a tool)."
        in text
    )


def test_troubleshooting_says_a_project_that_fails_to_build_lets_each_stop_through():
    """Review of #186's fix (4.1.0): the sentence said every missing budget
    script blocks each stop. Where the ancestor project fails to build, or to
    resolve, uv 0.12.15 stops there and exits 1, not 2, and exit 1 on a Stop
    hook is a non-blocking error: the stop goes through, and the turn goes
    uncounted. Its review: a resolve that fails on the network exits 2, not 1
    (uv 0.12.15 behind a proxy it could not reach, for the project's
    dependencies and for its build backend alike), so that stop is sent back."""
    text = " ".join((_DOCS / "troubleshooting.md").read_text(encoding="utf-8").split())
    assert "or its dependencies cannot be resolved" not in text
    assert (
        "When that project fails to build, or its requirements cannot be satisfied, `uv` stops there and exits 1, "
        "which Claude Code reads on a `Stop` hook as a non-blocking error: the session stops, and the turn goes "
        "uncounted. A network failure in that sync exits 2 instead, and each stop is sent back as above." in text
    )


def test_the_resume_predicate_rejects_the_4_0_0_rule():
    mutant = _refused_write_rule()
    cut = mutant.index(" A resume never reaches this stage")
    mutant = mutant[:cut] + mutant[mutant.index("\n", cut) :]
    assert not _resume_way_back_is_named(mutant)


def test_step5_skips_a_no_op_write_and_points_at_the_rule():
    s5 = _step5()
    hooks = _between(s5, "- **Hooks.**", "- **Allowlist.**")
    assert "makes no write" in hooks
    assert re.search(r"`--assert-armed` alone is not that comparison", hooks), (
        "the no-write check must compare injected values, not mere presence"
    )
    assert '"A refused settings write"' in hooks
    assert "refused write" in _bullet(s5, "- **Allowlist.**")


# --- An unborn HEAD --------------------------------------------------------


def _forbids_branch_and_commit(bullet: str) -> bool:
    return bool(
        "git_unborn" in bullet
        and "`remediable: false`" in bullet
        and re.search(r"make \*\*no\*\* branch and \*\*no\*\* commit", bullet)
        and re.search(r"run \*\*no\*\* other remediation that writes to the tree", bullet)
        and re.search(r"never on an Epic branch", bullet)
    )


def test_step2_unborn_bullet_forbids_branching_and_committing():
    assert _forbids_branch_and_commit(_bullet(_step2(), "- **HEAD has no commit yet**"))


def test_unborn_predicate_rejects_a_bullet_that_still_branches():
    mutant = (
        "- **HEAD has no commit yet** (`git_unborn`, `remediable: false`): create the "
        "Epic branch, then commit the tree."
    )
    assert not _forbids_branch_and_commit(mutant)


def test_unborn_bullet_precedes_the_protected_branch_bullet():
    s2 = _step2()
    assert s2.index("- **HEAD has no commit yet**") < s2.index("- **On a protected branch**")


def test_ordering_paragraph_names_the_unborn_suspension():
    assert "While `git_unborn` stands" in _bullet(_step2(), "**Ordering.**")


# --- project-context.md ----------------------------------------------------

_RETIRED_GENERATOR = "generate via `bmad-generate-project-context`"


def _invokes_no_generator(bullet: str) -> bool:
    return bool(
        _RETIRED_GENERATOR not in bullet
        and re.search(r"invoke \*\*no\*\* sub-skill", bullet)
        and "never becomes a RED" in bullet
    )


def test_project_context_bullet_invokes_no_generator():
    bullet = _bullet(_step2(), "- **`project-context.md` count != 1**")
    assert _invokes_no_generator(bullet)
    assert "Auto-Memory" not in bullet, "the file never fed Auto Memory"
    assert _RETIRED_GENERATOR not in _text()


def test_project_context_predicate_rejects_the_pre_edit_bullet():
    pre_edit = (
        "- **`project-context.md` count != 1** (`project_context_count`): advisory "
        "only. Resolve to exactly **one** anyway (generate via "
        "`bmad-generate-project-context` if zero; de-dup if multiple)."
    )
    assert not _invokes_no_generator(pre_edit)


# --- SKILL.md: the headless envelope under a refusal -----------------------


def _envelope_paragraph() -> str:
    skill = _SKILL.read_text(encoding="utf-8")
    return next(
        p for p in skill.split("\n\n") if p.startswith("**One core schema, every exit point.**")
    )


def _attempts_once_never_hand_builds(para: str) -> bool:
    return bool(
        re.search(r"Attempt that adapter call once even when other calls", para)
        and re.search(r"if the adapter call itself is refused, build nothing by hand", para)
        and "never by hand" in para
    )


def test_skill_md_attempts_the_adapter_once_and_never_hand_builds():
    assert _attempts_once_never_hand_builds(_envelope_paragraph())


def test_adapter_predicate_rejects_a_hand_build_fallback():
    """The tempting wrong fix: fall back to writing the JSON by hand when the
    adapter call is refused, which adds a second writer of run-result.json."""
    mutant = _envelope_paragraph().replace(
        "if the adapter call itself is refused, build nothing by hand",
        "if the adapter call itself is refused, write the envelope by hand",
    )
    assert not _attempts_once_never_hand_builds(mutant)


def test_execute_resume_routes_a_refused_settings_write():
    execute = (_SKILL_ROOT / "references" / "execute.md").read_text(encoding="utf-8")
    sweep = next(
        p for p in execute.split("\n\n") if p.startswith("**The re-assertion sweep is one script call")
    )
    assert '"A refused settings write"' in sweep
    assert re.search(r"never work around it", sweep)
