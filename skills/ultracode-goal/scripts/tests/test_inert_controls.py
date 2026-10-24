"""Controls that reported themselves active while enforcing nothing.

Static prose-contract assertions, plus the recall commands the prose spells
driven through the real guard and the real scripts. Each group below pins a
clause written because a surface CLAIMED to be gating something and was not -
the failure mode that is worse than an absent control, because the log says it
is armed.

  - MATCHER. The PreToolUse guard's Cross-Session Recall rules act on tools
    other than Bash: while a run latch is present it denies Read, Grep, Glob,
    Write, Edit, MultiEdit and NotebookEdit calls that name the recall store,
    file-tool calls that would change the latch, and every claude-mem MCP call.
    Claude Code only invokes a hook group for tools its matcher selects, so a
    group armed with `matcher: "Bash"` (what both known installs did) is never
    asked about any of them. preflight.md's arming assertion once checked
    PRESENCE only, which a Bash-only arming passes.

  - THE GUARD THAT "SEES BASH ONLY". Both preflight.md and execute.md said the
    guard evaluates Bash command strings only and has nothing to evaluate for a
    Write. The recall store and latch rules made that false: the guard decides
    on file tools. The conclusion the sentence served (a decision-log append
    made with Write trips no gate) still holds, for a different reason.

  - RECALL THROUGH TWO SCRIPTS. Recall used to depend on claude-mem's MCP
    tools: a third, permission-refused state no fork named, a read probe that
    authorized a write, and a drain that replayed parked payloads against no
    write tool at all. The backend is now a local run store that only
    `mem_recall.py` and `mem_observation.py` touch. These checks pin that
    ingest-and-scope.md and finalize.md call those two scripts only, in their
    store modes, with the recall- NOTE tokens a run report needs to say recall
    was off, and that every terminal removes the latch with
    `mem_recall.py unlatch` and nothing else. The prose commands are driven
    through the real guard under a live latch: an exemption that refuses them
    turns recall off in every run, and nothing short of a headless rehearsal
    would see it.

  - THE RESUME THAT COULD NEVER LAUNCH. formalize_check.py is epic-scoped by
    construction, so on a long Epic it reads blocked on gaps belonging to
    undrafted stories (41 mechanical gaps and 20 judgment candidates on one real
    Epic, essentially none in the story being driven). A conductor applying the
    launch non-negotiable literally on every resume blocks a healthy run forever.

Retired with the claude-mem backend (each inverted below where its hazard could
come back): the third-state fork, never-synthesize-a-probe, the first-denial
rule, still-make-the-call, the read-probe-is-not-a-write-tool branch, the drain
skip, NOTE mem-write-unavailable, and the operator doc's MCP caveats (that doc
is rewritten with the store).

Stdlib + pytest only.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REFERENCES = _SKILL_ROOT / "references"
_PREFLIGHT = _REFERENCES / "preflight.md"
_INGEST = _REFERENCES / "ingest-and-scope.md"
_FINALIZE = _REFERENCES / "finalize.md"
_EXECUTE = _REFERENCES / "execute.md"
_SKILL = _SKILL_ROOT / "SKILL.md"
_CUSTOMIZE = _SKILL_ROOT / "customize.toml"
_HOOK = _SKILL_ROOT / "scripts" / "hooks" / "guard_pretooluse.py"

_RUN = "epic-7-20260604T172512Z"
_NEEDS_GIT = pytest.mark.skipif(not shutil.which("git"), reason="git not on PATH")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(path: Path, heading: str) -> str:
    """One `## ` section's body. Locality matters more than presence here.

    A whole-file search would let a guard clause be relocated BELOW the step it
    is supposed to guard and stay green - and an instruction that arrives after
    the step it governs is not an instruction.
    """
    text = _read(path)
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start:] if end == -1 else text[start:end]


def _recall_read_section() -> str:
    return _section(_INGEST, "## Cross-Session Recall")


def _recall_write_section() -> str:
    return _section(_FINALIZE, "## Cross-Session Recall write")


def _preflight_step4() -> str:
    return _section(_PREFLIGHT, "## 4. Hard gate")


def _hooks_bullet() -> str:
    text = _read(_PREFLIGHT)
    start = text.index("- **Hooks.**")
    end = text.index("\n- **Allowlist.**", start)
    return text[start:end]


# The fenced recall commands the prose spells, the subject of most checks below.
_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_RECALL_SCRIPT = re.compile(r"\bmem_(?:recall|observation)\.py\b")


def _recall_commands(path: Path) -> list[str]:
    """Every fenced line of `path` that runs a recall script, in file order."""
    commands = []
    for block in _FENCE.findall(_read(path)):
        for line in block.splitlines():
            if _RECALL_SCRIPT.search(line):
                commands.append(line.strip())
    return commands


def _subcommand(command: str) -> str:
    """`mem_recall.py latch ...` -> "mem_recall.py latch"."""
    match = re.search(r"\b(mem_(?:recall|observation)\.py)\s+(\S+)", command)
    assert match, f"no subcommand after the script: {command!r}"
    return f"{match.group(1)} {match.group(2)}"


def _all_prose() -> dict[str, str]:
    files = sorted(_REFERENCES.glob("*.md")) + [_SKILL]
    return {path.name: _read(path) for path in files}


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


def test_the_matcher_rule_is_in_the_hooks_bullet_not_merely_in_the_file():
    """Locality: preflight.md is 200+ lines and the arming instruction is one bullet."""
    hooks_bullet = _hooks_bullet()
    assert re.search(r'"matcher":\s*"\*"', hooks_bullet), (
        "the matcher rule must live in the Hooks bullet, where a run arming the "
        "hooks is actually reading"
    )
    assert re.search(r"presence-only assertion", hooks_bullet)


def test_the_matcher_reason_is_the_file_tools_the_recall_rules_deny():
    """The reason changed with the backend: no MCP call is left to gate.

    The matcher stays all-tools because the store and latch rules act on Read,
    Grep, Glob, Write and Edit, which a Bash-only group never reaches. A reason
    that still said "it exists to gate an MCP call" would read as obsolete and
    invite narrowing the matcher back.
    """
    hooks_bullet = _hooks_bullet()
    assert "exists to gate an **MCP tool call**" not in hooks_bullet
    assert "mcp__plugin_claude-mem" not in hooks_bullet
    rationale = next(
        ln for ln in hooks_bullet.splitlines() if "covers EVERY tool, not just `Bash`" in ln
    )
    assert "Read, Grep, Glob, Write, Edit" in rationale, "the file tools it must reach"
    assert "recall store" in rationale and "latch" in rationale


def test_the_latch_invariant_says_it_depends_on_the_matcher():
    """The sub-bullet claiming the guard 'reads it automatically' needs the caveat."""
    latch_bullet = next(
        ln for ln in _read(_PREFLIGHT).splitlines() if "Cross-Session Recall latch from" in ln
    )
    assert "enforces nothing unless the matcher above covers every tool" in latch_bullet
    assert "recall store" in latch_bullet, "it says what the latch protects now"
    assert "change the latch itself" in latch_bullet
    assert "Reading the latch stays allowed" in latch_bullet
    assert "enforces nothing unless the matcher above covers MCP tools" not in latch_bullet


# --- The guard that "sees Bash only" ------------------------------------------


@pytest.mark.parametrize("path", [_PREFLIGHT, _EXECUTE], ids=lambda p: p.name)
def test_no_surface_claims_the_guard_sees_bash_only(path: Path):
    """CSR-UNIT-040: inverted from the old pin, which required the first phrase.

    The guard decides on file tools now (the recall store and latch rules), so
    "evaluates Bash command strings only" and "has nothing to evaluate and
    returns no decision" are both false. A reader who believes them and meets a
    store deny on a Write has no way to reconcile the two.
    """
    body = _read(path)
    for claim in (
        "evaluates Bash command strings only",
        "has nothing to evaluate and returns no decision",
        "The PreToolUse guard sees Bash commands only",
        "The guard never sees Write/Edit at all,",
    ):
        assert claim not in body, f"{path.name} still asserts: {claim!r}"
    # It still says why the matcher covers every tool, and what a Write meets.
    sentence = next(
        p for p in body.split("\n") if "the hook IS invoked for a `Write`" in p
    )
    assert "recall store" in sentence and "latch" in sentence, (
        f"{path.name} must say which rules a Write can meet"
    )
    assert "Bash command strings alone" in sentence, "the git gates still read Bash only"


# --- Recall through two scripts -------------------------------------------------

# The claude-mem operations and discovery calls no recall prose may name.
_MCP_TOKENS = ("mcp__", "save_observation", "get_observations", "smart_", "ToolSearch", "selftest")
# The script forms PR 3 removed, which no prose may still spell.
_REMOVED_FORMS = (
    "--probe",
    "--claude-mem-absent",
    "--tool-form",
    "mem_observation.py build",
    "mem_observation.py spill",
    "mem-write-unavailable",
)


@pytest.mark.parametrize("name", sorted(_all_prose()))
def test_no_reference_calls_an_mcp_tool_toolsearch_or_selftest(name: str):
    """No stage file or SKILL.md reaches recall any way but the two scripts."""
    text = _all_prose()[name]
    for token in _MCP_TOKENS + _REMOVED_FORMS:
        assert token not in text, f"{name} still names {token!r}"


@pytest.mark.parametrize("path", [_INGEST, _FINALIZE], ids=lambda p: p.name)
def test_ingest_and_finalize_name_no_claude_mem_operation(path: Path):
    """CSR-UNIT-028: neither file names a claude-mem MCP operation.

    Neither file ever contained `mcp__`; the operation names ("One
    `get_observations`", "One `save_observation`") were what carried the call.
    """
    text = _read(path)
    for token in _MCP_TOKENS + ("claude-mem MCP", "MCP tools are present", "write tool"):
        assert token not in text, f"{path.name} still names {token!r}"


def test_ingest_has_no_third_state_and_no_probe():
    """Inverted from the third-state, never-synthesize, first-denial and
    still-make-the-call pins: each guarded a hazard of a probed MCP surface, and
    with no probe left, their text would only route a reader back to one."""
    section = _recall_read_section()
    for retired in (
        "THIRD state",
        "probe",
        "Never synthesize",
        "first denial",
        "Still make the call",
        "tools are not available",
    ):
        assert retired.lower() not in section.lower(), f"ingest-and-scope.md still says {retired!r}"


def test_finalize_has_no_write_tool_branch_and_no_drain_skip():
    """Inverted from the read-probe-is-not-a-write-tool pins. The latch now
    certifies that the store can be WRITTEN, so a green latch is the clearance
    to drain and write, and the write-tool branch has nothing left to guard."""
    section = _recall_write_section()
    for retired in (
        "certifies the READ surface",
        "do not call and do not drain",
        "Skipping the drain",
        "a write tool",
        "claude-mem is present",
    ):
        assert retired not in section, f"finalize.md still says {retired!r}"
    # The deferred write keeps its meaning: the store could not take the
    # record, and it waits in the outbox.
    assert "`WARN mem-write-deferred`" in section


_STORE_MODES = {
    "mem_recall.py latch",
    "mem_recall.py filter",
    "mem_recall.py unlatch",
    "mem_observation.py write",
    "mem_observation.py drain",
}


@pytest.mark.parametrize(
    "path", sorted(_REFERENCES.glob("*.md")) + [_SKILL], ids=lambda p: p.name
)
def test_every_prose_recall_call_uses_a_store_mode(path: Path):
    """The only CLI the scripts keep: latch, filter, unlatch, write, drain.

    A removed mode or flag exits 2, so prose that still spelled one would turn
    recall off on every run while its log line read like a recall step.
    """
    for command in _recall_commands(path):
        assert command.startswith("uv run {skill-root}/scripts/mem_"), (
            f"{path.name}: a recall call must be the pinned `uv run` form: {command!r}"
        )
        mode = _subcommand(command)
        assert mode in _STORE_MODES, f"{path.name}: {mode!r} is not a store mode"
        assert "--impl-artifacts {workflow.implementation_artifacts}" in command
        if mode.endswith(("latch", "unlatch")):
            assert "--run-id <run-id>" in command
        if not mode.endswith("unlatch"):
            assert "--store '{workflow.cross_session_recall_store}'" in command, (
                f"{path.name}: {mode} without a single-quoted --store is a removed "
                "claude-mem form, or a value the shell expands or splits"
            )
        assert not re.search(r"--project(?!-root)\b", command), (
            f"{path.name}: --project is a removed flag: {command!r}"
        )


def test_ingest_calls_one_latch_and_one_filter():
    """CSR-UNIT-028: Ingest reads through one latch and one filter."""
    modes = [_subcommand(c) for c in _recall_commands(_INGEST)]
    assert modes.count("mem_recall.py latch") == 1
    assert modes.count("mem_recall.py filter") == 1
    assert not any(m.startswith("mem_observation.py") for m in modes), "Ingest writes nothing"
    assert modes.index("mem_recall.py latch") < modes.index("mem_recall.py filter"), (
        "the filter reads only once the latch has been written"
    )


def test_finalize_drains_then_writes():
    """CSR-UNIT-028: Finalize lands what was parked before this run's record."""
    modes = [_subcommand(c) for c in _recall_commands(_FINALIZE)]
    assert modes.count("mem_observation.py drain") == 1
    assert modes.count("mem_observation.py write") == 1
    assert modes.index("mem_observation.py drain") < modes.index("mem_observation.py write")
    assert "mem_recall.py latch" not in modes and "mem_recall.py filter" not in modes


def test_recall_note_tokens_are_pinned():
    """CSR-UNIT-029: the run-level tokens are literal strings a report can carry."""
    finalize = _recall_write_section()
    ingest = _recall_read_section()
    assert "`NOTE recall-latch-missing`" in finalize
    assert "`NOTE recall-write-refused`" in finalize
    assert "`NOTE recall-read-refused`" in ingest
    assert "`NOTE recall-store-unset`" in ingest + finalize


def test_every_unlatch_step_names_the_unlatch_failed_note():
    """A refused or failed unlatch leaves a latch that keeps denying in later
    sessions, so each prose step that runs unlatch tells the person, through a
    NOTE, that it is theirs to delete."""
    for path in (_FINALIZE, _INGEST, _PREFLIGHT):
        text = _read(path)
        assert "mem_recall.py unlatch" in text, path.name
        assert "`NOTE recall-unlatch-failed`" in text, path.name


def test_finalize_logs_every_mem_token_to_the_decision_log():
    """CSR-UNIT-029: the scripts print the mem- tokens; the prose logs them."""
    section = _recall_write_section()
    paragraph = next(p for p in section.split("\n\n") if p.startswith("Each call prints"))
    assert re.search(r"every line in its `notes` to `\.decision-log\.md`", paragraph)
    assert "`mem-` tokens" in paragraph
    for token in (
        "WARN mem-write-deferred",
        "NOTE mem-target-foreign",
        "NOTE mem-run-id-invalid",
        "NOTE mem-legacy-unconvertible",
    ):
        assert token in paragraph, f"the run report must be told about {token!r}"


def _latch_missing_rule() -> str:
    return next(
        ln for ln in _recall_write_section().splitlines() if "NOTE recall-latch-missing" in ln
    )


def test_finalize_logs_latch_missing_whatever_the_knob():
    """CSR-UNIT-030: a run whose recall turned off silently says so."""
    rule = _latch_missing_rule()
    assert rule.startswith("- **No latch"), "the no-latch case is a branch of its own"
    assert "whatever `{workflow.cross_session_recall}` says" in rule
    assert "no `drain` and no `write` call" in rule


def test_a_foreign_latch_at_finalize_counts_as_missing():
    """CSR-UNIT-032 (default C-1): another run's latch is not this run's record.

    It logs the same NOTE, writes nothing, and the close-out unlatch leaves it
    in place, since it removes only a latch carrying this run's id.
    """
    rule = _latch_missing_rule()
    assert "a latch whose `run_id` is not this run's id" in rule
    assert "left in place" in rule


def test_the_latch_missing_rule_precedes_the_drain_step():
    """An instruction that arrives after the write step is not one."""
    section = _recall_write_section()
    assert section.index("NOTE recall-latch-missing") < section.index("**Drain the outbox**")
    assert section.index("green") < section.index("**Drain the outbox**"), (
        "the drain and write sit under the green-latch branch"
    )


def test_finalize_passes_no_project():
    """CSR-UNIT-038: the store tells repos apart by fingerprint alone."""
    for command in _recall_commands(_FINALIZE):
        assert not re.search(r"--project(?!-root)\b", command), command


@pytest.mark.parametrize("path", [_INGEST, _FINALIZE], ids=lambda p: p.name)
def test_each_recall_call_is_attempted_once(path: Path):
    """CSR-UNIT-043: no retry, so a refusal costs one call and never a loop."""
    section = _recall_read_section() if path == _INGEST else _recall_write_section()
    assert "attempted once and never retried" in section


def test_a_refused_read_call_is_named_before_the_filter_call():
    """A reader who reaches the filter call first has already spent it."""
    section = _recall_read_section()
    assert section.index("NOTE recall-read-refused") < section.index("mem_recall.py filter")


def test_finalize_reports_the_drain_counts():
    """CSR-UNIT-044: the legacy conversion is visible in the run report."""
    text = _read(_FINALIZE)
    report = _section(_FINALIZE, "## Run report")
    for count in ("`converted`", "`legacy_unconvertible`"):
        assert count in report, f"the run report bullet must name {count}"
        assert count in _recall_write_section()
    assert "Cross-Session Recall:" in report and "recall-" in report
    assert "operator-remedy line" not in text, "the claude-mem permission remedy is gone"


def test_stage1_latches_whatever_the_knob_and_replaces_by_latching():
    """The guard gates uniformly only if every run writes its latch, recall off
    included; a stale latch is replaced by the latch command, never deleted."""
    section = _recall_read_section()
    assert "**Always run the latch**, whatever the knob says" in section
    assert "replaced by this command and only by it" in section
    assert "never delete the file" in section


def test_ingest_shows_a_rendered_line_and_logs_run_id_and_epoch():
    """The operator reads the line the script rendered, never a raw record, and
    each consumed advisory is attributed by the run that wrote it."""
    section = _recall_read_section()
    interactive = section[section.index("**Interactive:**"):section.index("**Headless:**")]
    assert "`title_noun_phrase`" in interactive
    assert "never a raw run file" in interactive
    assert re.search(r"its `id`, which is the `run_id` of the run that wrote it, and its `epoch`", section)


# --- The latch leaves through unlatch, and only through it ----------------------

_UNLATCH = "uv run {skill-root}/scripts/mem_recall.py unlatch --impl-artifacts {workflow.implementation_artifacts} --run-id <run-id>"


def test_each_terminal_removes_the_latch_with_unlatch():
    """CSR-UNIT-031 / AC-32: Finalize, the preflight STOP and the Stage 1 block."""
    assert _UNLATCH in _recall_write_section(), "Finalize's close-out"
    step4 = _preflight_step4()
    assert _UNLATCH in step4, "preflight step 4's STOP"
    assert step4.index("remove this run's recall latch") < step4.index("**STOP**")
    assert _UNLATCH in _recall_read_section(), "the Stage 1 command the blocks reuse"
    progression = _section(_INGEST, "## Progression")
    assert "`mem_recall.py unlatch`" in progression, "the epic-unresolved block"


def test_every_stop_before_finalize_unlatches_first():
    """CAP-7: every terminal removes this run's latch, the attended stops that
    never reach Finalize or preflight step 4 included. A declined launch, an
    operator who neither approves nor makes a refused settings write, an
    abort at a checkpoint and a resume that stops on its RED each left a
    latch that kept denying the operator's own session until they deleted it."""
    removal = next(
        p for p in _recall_read_section().split("\n\n") if p.startswith("It prints `{\"removed\"")
    )
    assert "**Any stop after this step that does not reach Finalize runs it first**" in removal
    for stop in ("declined launch confirm", "aborts at a checkpoint", "a resume that stops on its RED"):
        assert stop in removal, stop
    preflight = _read(_PREFLIGHT)
    confirm = next(ln for ln in preflight.splitlines() if ln.startswith("Then **one soft confirm**"))
    assert "If the operator declines, the run stops here: remove this run's recall latch first" in confirm
    attended = next(ln for ln in preflight.splitlines() if ln.startswith("- **Attended:** show the operator"))
    assert "the run stops here: remove this run's recall latch first" in attended


def test_no_prose_removes_the_latch_any_other_way():
    """AC-32: the guard refuses any other removal while a latch is present, so a
    removal step spelled any other way fails exactly where it is needed."""
    for name, text in _all_prose().items():
        for block in _FENCE.findall(text):
            assert ".mem-state.json" not in block, f"{name}: a command names the latch file"
        assert "**remove** `{workflow.implementation_artifacts}/.mem-state.json`" not in text
        assert not re.search(r"\b(?:rm|del|unlink)\b[^\n`]*\.mem-state\.json", text), name
    for section in (_recall_read_section(), _recall_write_section(), _preflight_step4()):
        assert "never remove the latch any other way" in section


def test_execute_resume_relatches_and_never_inherits():
    """The resume re-runs Stage 1's latch step and names unlatch as the remover;
    the probe-era reasons (a `claude_mem` value, never-synthesize) are gone."""
    resume = next(ln for ln in _read(_EXECUTE).splitlines() if ln.startswith("**On resume,"))
    assert "`mem_recall.py unlatch`" in resume
    assert "`mem_recall.py latch`" in resume
    assert "never inherit its `store_ok` colour" in resume
    assert "claude_mem" not in resume and "never-synthesize" not in resume


def test_a_resume_mints_its_own_run_id():
    """AC-18 and decision 1: each invocation, a resume or a drive_epic spawn
    included, is its own run with its own run id. A resume that reused the id
    an earlier invocation logged would find that record file already written,
    since record files are never rewritten, and lose its own record as
    `skipped-existing`."""
    skill_resume = next(ln for ln in _read(_SKILL).splitlines() if ln.startswith("**Resume.**"))
    assert "minting this invocation's own run id" in skill_resume
    assert "never reusing one an earlier invocation logged" in skill_resume
    execute_resume = next(ln for ln in _read(_EXECUTE).splitlines() if ln.startswith("**On resume,"))
    assert "this invocation's own run id" in execute_resume
    assert "A resume never reuses an id an earlier invocation logged" in execute_resume
    assert "`skipped-existing`" in execute_resume
    ingest = _recall_read_section()
    assert "A resumed invocation is a run of its own: it mints a fresh id" in ingest


def test_a_resume_from_stage_2_relatches_before_preflight():
    """A preflight RED's STOP removed the run's latch, and Stage 2 has no latch
    step: a re-run from Stage 2 that skipped Stage 1's recall section ran with
    no latch and wrote no record at Finalize."""
    resume = next(ln for ln in _read(_SKILL).splitlines() if ln.startswith("**Resume.**"))
    rule = "A re-run from Stage 2 first runs Stage 1's Cross-Session Recall section with a fresh run id"
    assert rule in resume
    assert resume.index("re-run from that stage") < resume.index(rule)


def test_recall_calls_run_as_written_and_the_filter_result_is_kept_with_write():
    """The guard lets a recall call through only as the pinned form: a
    redirection, a `2>&1` or a pipe on it is denied. Prose that said only "save
    the filter result" invited `filter ... > file`, which the run's own latch
    denies."""
    for section in (_recall_read_section(), _recall_write_section()):
        assert "no redirection, no `2>&1`, no pipe" in section
    ingest = _recall_read_section()
    assert "with the Write tool to `recall-filter-<run-id>.json` in this run's folder" in ingest
    assert "Save the filter result where Stage 2 can read it back." not in ingest


def test_the_store_value_is_single_quoted_and_says_why():
    """An unquoted `$VAR` store value is expanded by the shell before the
    script can count it as unset, and a value with a space splits."""
    ingest = _recall_read_section()
    assert "The store value stays in single quotes, here and in every recall command" in ingest
    assert "a `$VAR` reaches the script unexpanded, where it counts as unset" in ingest


def test_finalize_logs_the_write_status():
    """`skipped-existing`, `no-fingerprint` and `skip` print no note, so a run
    report that logged notes alone said nothing when no record landed."""
    paragraph = next(p for p in _recall_write_section().split("\n\n") if p.startswith("Each call prints"))
    assert "Log the write's `status`" in paragraph
    for status in ("`skipped-existing`", "`no-fingerprint`", "`skip`", "`deferred`"):
        assert status in paragraph, status


def test_finalize_counts_an_unreadable_latch_as_missing():
    """An unreadable latch is never this run's (unlatch says the same), so it
    takes the missing branch, not a write."""
    rule = _latch_missing_rule()
    assert rule.startswith("- **No latch, an unreadable one, or a latch whose `run_id`")
    assert "Another run's latch, or an unreadable one, is left in place" in rule


# --- The operator doc (CSR-UNIT-039) --------------------------------------------

_RECALL_DOC = _SKILL_ROOT.parents[1] / "docs" / "cross-session-recall.md"


def test_the_operator_doc_states_the_unit_of_record_and_the_store_rules():
    """CSR-UNIT-039 (AC-18, AC-26): one record file per spawn and its
    consequence, the self-ignoring store, and growth with no pruning."""
    doc = _read(_RECALL_DOC)
    assert "one record file per spawn" in doc
    assert "two stories of one drive hitting the same root cause count as recurring" in doc
    assert "they write a `.gitignore` holding `*` inside it" in doc
    assert "The store has no pruning yet." in doc
    for token in (
        "NOTE recall-store-unset",
        "NOTE recall-read-refused",
        "NOTE recall-latch-missing",
        "NOTE recall-write-refused",
        "NOTE recall-unlatch-failed",
        "WARN mem-write-deferred",
        "NOTE mem-target-foreign",
        "NOTE mem-run-id-invalid",
        "NOTE mem-legacy-unconvertible",
    ):
        assert f"| `{token}` |" in doc, f"the troubleshooting table must name {token}"
    for retired in ("selftest", "ToolSearch", "--claude-mem-absent"):
        assert f"run {retired}" not in doc and f"`{retired}` to" not in doc


def test_skill_md_names_the_store_not_claude_mem():
    text = _read(_SKILL)
    advisory = next(ln for ln in text.splitlines() if "Cross-Session Recall is advisory-only" in ln)
    assert "claude-mem is present" not in advisory
    assert "{workflow.cross_session_recall_store}" in advisory
    assert "`mem_recall.py unlatch`" in advisory
    resume = next(ln for ln in text.splitlines() if ln.startswith("**Resume.**"))
    assert "`mem_recall.py latch`" in resume


def test_customize_comment_points_at_the_store_key():
    text = _read(_CUSTOMIZE)
    end = text.index("cross_session_recall = ")
    comment = text[text.rindex("# --- Cross-Session Recall", 0, end):end]
    assert "claude-mem" not in comment
    assert "cross_session_recall_store" in comment
    assert "Advisory only, never gates." in comment


# --- The prose commands under the real guard (CSR-UNIT-047) --------------------

_PROSE_FILES = (_INGEST, _FINALIZE, _PREFLIGHT)


class _World:
    """A tmp home, store, repo and artifacts folder, and the placeholder values
    that turn a prose command into one a shell would run."""

    def __init__(self, tmp: Path, store_name: str = "recall") -> None:
        self.home = tmp / "home"
        self.store = self.home / ".ultracode-goal" / store_name
        self.repo = tmp / "repo"
        self.impl = tmp / "impl"
        self.deferred = self.impl / "deferred-work.md"
        for folder in (self.home, self.repo, self.impl):
            folder.mkdir(parents=True)

    @property
    def env(self) -> dict:
        return {
            **os.environ,
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "ULTRACODE_IMPL_ARTIFACTS": str(self.impl),
        }

    def fill(self, command: str) -> str:
        values = {
            # The optional repeated groups first: they hold <...> of their own.
            "[--root-cause class=<taxonomy>,path=<artifact>]…": "--root-cause class=test-failure,path=src/app.py",
            "[--advisory sig=<s>,recurred=<yes|no|unknown>]…": "--advisory sig=0123456789ab,recurred=no",
            "{skill-root}": _SKILL_ROOT.as_posix(),
            "{workflow.implementation_artifacts}": self.impl.as_posix(),
            "{workflow.cross_session_recall_store}": self.store.as_posix(),
            "{workflow.deferred_work_path}": self.deferred.as_posix(),
            "{project-root}": self.repo.as_posix(),
            "<run-id>": _RUN,
            "<on|off>": "on",
            "<id>": "7",
            "<status>": "PASS",
            "<advance|blocked>": "advance",
        }
        for placeholder, value in values.items():
            command = command.replace(placeholder, value)
        leftover = re.findall(r"[{}<>\[\]…|]", command)
        assert not leftover, (
            f"a placeholder this test does not know survived ({leftover}): give it a "
            f"value here, since a shell would read < > | as redirections: {command!r}"
        )
        return command


def _prose_calls() -> list[tuple[str, str]]:
    calls = []
    for path in _PROSE_FILES:
        for command in _recall_commands(path):
            calls.append((path.name, command))
    return calls


def test_the_extraction_finds_every_recall_call():
    """CSR-UNIT-047's own control: an extractor that found nothing passes vacuously."""
    modes = {_subcommand(command) for _name, command in _prose_calls()}
    assert modes == _STORE_MODES
    assert sum(1 for _n, c in _prose_calls() if "unlatch" in c) == 3, (
        "one unlatch each in ingest-and-scope.md, preflight.md and finalize.md"
    )


def _v2_latch(world: _World, recall: str) -> dict:
    return {
        "latch_version": 2,
        "run_id": _RUN,
        "backend": "jsonl",
        "store_ok": recall == "on",
        "recall": recall,
        "store": str(world.store),
        "fingerprint": "0123456789abcdef",
        "created_at": "2026-06-04T17:25:12Z",
    }


def _guard(tmp_path: Path, command: str, recall: str = "on", drift=None) -> subprocess.CompletedProcess:
    """Run the shipped hook on one prose command, filled (then drifted, for
    the twin below), under a live v2 latch."""
    world = _World(tmp_path)
    world.store.mkdir(parents=True)
    (world.impl / ".mem-state.json").write_text(json.dumps(_v2_latch(world, recall)), encoding="utf-8")
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": (drift or str)(world.fill(command))},
        "cwd": str(world.repo),
    }
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(event),
        cwd=world.repo,
        capture_output=True,
        text=True,
        env=world.env,
    )


@pytest.mark.parametrize("recall", ["on", "off"])
@pytest.mark.parametrize(
    "call", _prose_calls(), ids=[f"{n}:{_subcommand(c)}" for n, c in _prose_calls()]
)
def test_every_prose_recall_command_passes_the_real_guard(
    tmp_path: Path, call: tuple[str, str], recall: str
):
    """CSR-UNIT-047: each fenced recall call, placeholders filled, is allowed by
    the shipped hook under a live latch that names the store.

    Prose drift (a `--with` option, `uv run python ...`, a glued `--store=`, a
    redirection) would make the pinned-script exemption fail closed and turn
    recall off in every run, which otherwise only the headless rehearsal sees.
    """
    proc = _guard(tmp_path, call[1], recall)
    assert proc.returncode == 0, proc.stdout or proc.stderr
    assert proc.stdout.strip() == "", f"the guard decided on a prose command: {proc.stdout}"


@pytest.mark.parametrize(
    "drift",
    [
        lambda c: c.replace("uv run ", "uv run --with pytest ", 1),
        lambda c: c.replace("uv run ", "uv run python ", 1),
        lambda c: c + " > recall.log",
    ],
    ids=["uv-run-option", "uv-run-python", "redirection"],
)
def test_a_drifted_prose_command_is_denied_by_the_same_harness(tmp_path: Path, drift):
    """Anti-vacuous twin of CSR-UNIT-047: the harness above can red. The same
    filter call, drifted the ways the exemption refuses, is denied."""
    filter_call = next(c for c in _recall_commands(_INGEST) if "mem_recall.py filter" in c)
    proc = _guard(tmp_path, filter_call, drift=drift)
    assert proc.returncode == 2, proc.stdout or proc.stderr
    decision = json.loads(proc.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "recall store" in decision["permissionDecisionReason"]


@pytest.fixture
def _hermetic_git_env(monkeypatch):
    for var in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/")


def _init_repo(world: _World) -> None:
    """A tmp repo with one commit, so the scripts can fingerprint it."""
    for args in (
        ("init", "-q"),
        ("config", "user.email", "t@t"),
        ("config", "user.name", "t"),
    ):
        subprocess.run(["git", *args], cwd=world.repo, check=True, capture_output=True)
    (world.repo / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=world.repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=world.repo, check=True, capture_output=True)


def _run_prose(world: _World, command: str) -> dict:
    argv = shlex.split(world.fill(command))
    assert argv[:2] == ["uv", "run"], argv
    proc = subprocess.run(
        [sys.executable, *argv[2:]],
        cwd=world.repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=world.env,
    )
    assert proc.returncode == 0, f"{command!r} exited {proc.returncode}: {proc.stdout}{proc.stderr}"
    return json.loads(proc.stdout)


@_NEEDS_GIT
@pytest.mark.usefixtures("_hermetic_git_env")
def test_the_prose_recall_commands_run_as_written(tmp_path: Path):
    """The prose CLI is the scripts' CLI: one run through every fenced call, in
    the order a run makes them, against a real store in a tmp repo.

    A flag the scripts removed or renamed exits 2 here, where otherwise only a
    run report's NOTE line would show that recall never happened.
    """
    world = _World(tmp_path)
    _init_repo(world)

    ingest = {_subcommand(c): c for c in _recall_commands(_INGEST)}
    finalize = {_subcommand(c): c for c in _recall_commands(_FINALIZE)}
    preflight = {_subcommand(c): c for c in _recall_commands(_PREFLIGHT)}
    latch_file = world.impl / ".mem-state.json"

    latched = _run_prose(world, ingest["mem_recall.py latch"])
    assert latched["latch"]["store_ok"] is True, latched
    assert latched["latch"]["run_id"] == _RUN and latch_file.is_file()

    assert _run_prose(world, ingest["mem_recall.py filter"])["empty"] is True

    drained = _run_prose(world, finalize["mem_observation.py drain"])
    assert "converted" in drained and "legacy_unconvertible" in drained, drained

    written = _run_prose(world, finalize["mem_observation.py write"])
    assert written["status"] == "written", written

    seen = _run_prose(world, ingest["mem_recall.py filter"])
    assert [record["id"] for record in seen["records"]] == [_RUN]

    removed = _run_prose(world, finalize["mem_recall.py unlatch"])
    assert removed == {"removed": True, "reason": "removed"}
    assert not latch_file.exists()
    # The STOP's copy is the same command: on a removed latch it is a no-op.
    assert _run_prose(world, preflight["mem_recall.py unlatch"]) == {
        "removed": False,
        "reason": "absent",
    }


@_NEEDS_GIT
@pytest.mark.usefixtures("_hermetic_git_env")
@pytest.mark.parametrize(
    "store_value,green",
    [(None, True), ("$HOME/.ultracode-goal/recall", False)],
    ids=["a-space-stays-one-argument", "a-dollar-var-counts-as-unset"],
)
def test_the_quoted_store_value_reaches_the_script_as_configured(
    tmp_path: Path, store_value: str | None, green: bool
):
    """The prose single-quotes the store value: a path with a space reaches the
    latch whole and goes green, and a literal `$HOME` in the value reaches the
    script unexpanded, which reads it as unset (red, with the NOTE)."""
    world = _World(tmp_path, store_name="recall store")
    _init_repo(world)
    latch_call = next(c for c in _recall_commands(_INGEST) if "mem_recall.py latch" in c)
    if store_value is not None:
        latch_call = latch_call.replace("{workflow.cross_session_recall_store}", store_value)
    latched = _run_prose(world, latch_call)
    assert latched["latch"]["store_ok"] is green, latched
    if green:
        assert latched["latch"]["store"] == str(world.store), latched
    else:
        assert any("NOTE recall-store-unset" in note for note in latched["notes"]), latched


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
