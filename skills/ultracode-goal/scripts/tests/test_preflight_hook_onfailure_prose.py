#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""The guard is armed to refuse a tool call when it fails, and only the guard.

Claude Code reads a hook that cannot start, exits with a code other than 0 or
2, or times out as no objection, so the tool call runs unchecked. From 2.1.295
a command hook item that carries `"onFailure": "block"` makes each of those a
refusal instead. Nothing in UCG writes the hook entries: the conductor writes
them by following references/preflight.md step 5's Hooks bullet, so the
setting exists exactly as far as that bullet spells it. These checks pin:

- the item templates in the Hooks bullet: the guard's carries
  `"onFailure": "block"` beside `"type"` and `"command"`, and the Stop budget
  hook's carries no `onFailure` (Claude Code ignores it on Stop, and the
  budget hook never blocks by design);
- what the setting does, its exact lower-case value (another value drops the
  whole item, so no guard runs), and its cost under the all-tools matcher;
- the no-write equality list and the assertion naming it, so a 3.x arming
  without it is rewritten rather than kept;
- the resume route in execute.md for a run a 3.x release armed: re-merge
  through the Hooks bullet alone, replace never append, purge nothing, then
  assert again;
- the sentence that said a crashing hook lets the command through, restated;
- the step-1 checks list against the keys build_report emits.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_preflight_hook_onfailure_prose.py -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REFERENCES = SCRIPTS.parent / "references"
PREFLIGHT = REFERENCES / "preflight.md"
EXECUTE = REFERENCES / "execute.md"
PREFLIGHT_CHECK = SCRIPTS / "preflight_check.py"
REPO_ROOT = SCRIPTS.parents[2]
SECURITY = REPO_ROOT / "SECURITY.md"
TROUBLESHOOTING = REPO_ROOT / "docs" / "troubleshooting.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _hooks_bullet(text: str | None = None) -> str:
    text = _read(PREFLIGHT) if text is None else text
    start = text.index("- **Hooks.**")
    end = text.index("\n- **Allowlist.**", start)
    return text[start:end]


# An inline code span holding one hook item, as the bullet writes it.
_ITEM = re.compile(r'`(\{"type": "command".*?\})`')


def _items(bullet: str) -> dict[str, dict]:
    """The hook item templates in the bullet, keyed by the script each runs."""
    found: dict[str, dict] = {}
    for raw in _ITEM.findall(bullet):
        item = json.loads(raw)
        for script in ("guard_pretooluse.py", "budget_stop.py"):
            if script in item["command"]:
                assert script not in found, f"two templates for {script}"
                found[script] = item
    return found


# How the guard template ends in the bullet: the quoted script path, then the key.
_GUARD_TAIL = "guard_pretooluse.py'\", \"onFailure\": \"block\"}"


def _arms_only_the_guard_with_block(bullet: str) -> bool:
    """The guard template carries exactly "block"; the Stop template none."""
    items = _items(bullet)
    guard, budget = items.get("guard_pretooluse.py"), items.get("budget_stop.py")
    if guard is None or budget is None:
        return False
    return guard.get("onFailure") == "block" and guard.get("type") == "command" and "onFailure" not in budget


# --- the item templates ------------------------------------------------------


def test_the_hooks_bullet_writes_the_guard_item_with_on_failure_block():
    items = _items(_hooks_bullet())
    guard = items["guard_pretooluse.py"]
    assert guard == {
        "type": "command",
        "command": "<env> uv run '{skill-root}/scripts/hooks/guard_pretooluse.py'",
        "onFailure": "block",
    }
    assert _arms_only_the_guard_with_block(_hooks_bullet())


def test_the_hooks_bullet_writes_the_stop_item_without_on_failure():
    budget = _items(_hooks_bullet())["budget_stop.py"]
    assert budget == {"type": "command", "command": "<env> uv run '{skill-root}/scripts/hooks/budget_stop.py'"}
    flat = _flat(_hooks_bullet())
    assert "the budget hook's item carries no `onFailure` key" in flat
    assert "The Stop budget hook carries no `onFailure`: Claude Code ignores the key on `Stop`" in flat
    assert "the budget hook never blocks a stop by design" in flat


@pytest.mark.parametrize(
    "old,new",
    [
        pytest.param(_GUARD_TAIL, "guard_pretooluse.py'\"}", id="guard-without-it"),
        pytest.param(_GUARD_TAIL, _GUARD_TAIL.replace('"block"', '"Block"'), id="wrong-case"),
        pytest.param(_GUARD_TAIL, _GUARD_TAIL.replace('"block"', '"continue"'), id="continue"),
        pytest.param("budget_stop.py'\"}", "budget_stop.py'\", \"onFailure\": \"block\"}", id="on-stop-too"),
    ],
)
def test_the_template_predicate_rejects_a_drifted_template(old: str, new: str):
    """Twin: the predicate is not vacuous. Each mutant of the live bullet is
    a way the arming could drift: the 3.x item, a value Claude Code drops the
    item for, the value that lets a crash through, and the key on Stop."""
    live = _hooks_bullet()
    assert live.count(old) == 1, old
    mutant = live.replace(old, new)
    assert not _arms_only_the_guard_with_block(mutant)


def test_the_template_sits_in_the_hooks_bullet_not_merely_in_the_file():
    """Locality: the conductor arms from this bullet, so the template must be
    there and nowhere it would be read as a second, different shape."""
    text = _read(PREFLIGHT)
    bullet = _hooks_bullet(text)
    assert text.count('"onFailure": "block"}') == bullet.count('"onFailure": "block"}') == 1


# --- the filled-in templates start their scripts -----------------------------
# Claude Code hands a hook's command to a shell, which splits it at every
# unquoted space. Filled in literally under a folder whose name holds a space,
# an unquoted template hands the rest of the path to the shell as the command
# to run (exit 127), so the guard never starts and, under "onFailure":
# "block", every tool call is refused. These tests fill the templates in from
# the bullet itself, the way a conductor does.

_HOOK_VARS = (
    "ULTRACODE_PROTECTED_BRANCHES",
    "ULTRACODE_IMPL_ARTIFACTS",
    "ULTRACODE_MAX_TURNS",
    "ULTRACODE_EPIC_BRANCH_PREFIX",
    "ULTRACODE_TEST_ARTIFACTS",
)
_ENV_ENTRY = re.compile(r"^\s*- `(ULTRACODE_[A-Z_]+=[^`]*)`", re.M)


def _filled(bullet: str, script: str, root: Path) -> tuple[str, dict[str, str], str]:
    """(command, expected env, expected script path) for one template, with
    `<env>` built from the bullet's own env list and every placeholder given a
    value under `<root>/sp ace`."""
    spaced = (root / "sp ace").as_posix()
    values = {
        "{skill-root}": f"{spaced}/skill",
        "{workflow.protected_branches}": "main,master",
        "{workflow.implementation_artifacts}": f"{spaced}/impl",
        "{workflow.max_turns_per_story}": "25",
        "{workflow.epic_branch_prefix}": "ultracode/epic-",
        "<the resolved TEA test-artifacts root>": f"{spaced}/ta",
    }

    def fill(text: str) -> str:
        for placeholder, value in values.items():
            text = text.replace(placeholder, value)
        return text

    entries = _ENV_ENTRY.findall(bullet)
    assert [e.split("=", 1)[0] for e in entries] == list(_HOOK_VARS), entries
    command = fill(_items(bullet)[script]["command"].replace("<env>", " ".join(entries)))
    expected_env = {
        "ULTRACODE_PROTECTED_BRANCHES": "main,master",
        "ULTRACODE_IMPL_ARTIFACTS": f"{spaced}/impl",
        "ULTRACODE_MAX_TURNS": "25",
        "ULTRACODE_EPIC_BRANCH_PREFIX": "ultracode/epic-",
        "ULTRACODE_TEST_ARTIFACTS": f"{spaced}/ta",
    }
    return command, expected_env, f"{spaced}/skill/scripts/hooks/{script}"


def _unquoted(bullet: str) -> str:
    """The bullet as 4.0.0's draft wrote it: no quotes in the templates or the
    env list."""
    lines = []
    for line in bullet.splitlines():
        if line.lstrip().startswith(("- guard: `", "- budget: `", "- `ULTRACODE_")):
            head, _, tail = line.partition("`")
            code, _, rest = tail.partition("`")
            line = f"{head}`{code.replace(chr(39), '')}`{rest}"
        lines.append(line)
    return "\n".join(lines)


def _run_through_sh(command: str, tmp_path: Path) -> dict | None:
    """Run the command as Claude Code does, through `sh -c`, with a stub `uv`
    that records its arguments and the injected env. None when the shell never
    reached `uv` with them."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    dump = tmp_path / "dump.py"
    out = tmp_path / "uv-call.json"
    dump.write_text(
        "import json, os, sys\n"
        f"keys = {list(_HOOK_VARS)!r}\n"
        "with open(os.environ['UCG_STUB_OUT'], 'w', encoding='utf-8') as fh:\n"
        "    json.dump({'argv': sys.argv[1:], 'env': {k: os.environ.get(k) for k in keys}}, fh)\n",
        encoding="utf-8",
    )
    stub = bin_dir / "uv"
    stub.write_text(f"#!/bin/sh\nexec '{sys.executable}' '{dump}' \"$@\"\n", encoding="utf-8")
    stub.chmod(0o755)
    if out.exists():
        out.unlink()
    env = {k: v for k, v in os.environ.items() if k not in _HOOK_VARS}
    env.update({"PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}", "UCG_STUB_OUT": str(out)})
    proc = subprocess.run(["sh", "-c", command], input="{}", capture_output=True, text=True, env=env, timeout=60)
    if proc.returncode != 0 or not out.exists():
        return None
    return json.loads(out.read_text(encoding="utf-8"))


_POSIX_SHELL = pytest.mark.skipif(
    os.name == "nt" or shutil.which("sh") is None, reason="runs the hook command through a POSIX sh"
)


@_POSIX_SHELL
@pytest.mark.parametrize("script", ["guard_pretooluse.py", "budget_stop.py"])
def test_each_filled_in_template_starts_its_script_under_a_path_with_a_space(script: str, tmp_path: Path):
    command, env, path = _filled(_hooks_bullet(), script, tmp_path)
    call = _run_through_sh(command, tmp_path)
    assert call is not None, command
    assert call["argv"] == ["run", path]
    assert call["env"] == env


@_POSIX_SHELL
@pytest.mark.parametrize("script", ["guard_pretooluse.py", "budget_stop.py"])
def test_the_unquoted_templates_do_not_start_their_scripts(script: str, tmp_path: Path):
    """Twin: the sh run tells the shapes apart. Unquoted, the shell runs the
    rest of the first spaced value as the command and never reaches uv."""
    bullet = _unquoted(_hooks_bullet())
    assert "'" not in _items(bullet)[script]["command"]
    command, _, _ = _filled(bullet, script, tmp_path)
    assert _run_through_sh(command, tmp_path) is None, command


def _command_problem():
    spec = importlib.util.spec_from_file_location("preflight_check_split", PREFLIGHT_CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._command_problem


@pytest.mark.parametrize("script", ["guard_pretooluse.py", "budget_stop.py"])
def test_assert_armed_reads_the_filled_in_templates_the_way_the_shell_does(script: str, tmp_path: Path):
    """The check `--assert-armed` runs passes what the bullet writes and fails
    the unquoted form, on every platform (it splits, it never runs)."""
    problem = _command_problem()
    command, _, _ = _filled(_hooks_bullet(), script, tmp_path)
    assert problem(command, script) is None
    unquoted, _, _ = _filled(_unquoted(_hooks_bullet()), script, tmp_path)
    assert problem(unquoted, script) is not None


def test_the_bullet_says_to_quote_and_why():
    flat = _flat(_hooks_bullet())
    for clause in (
        "**Quote each injected value and the script path in single quotes, as the templates do.**",
        "Claude Code runs the command through a shell, which splits it at every unquoted space.",
        "as the recall store value is kept (`references/ingest-and-scope.md`)",
        "write a single quote inside a value as `'\\''`",
        "`--assert-armed` reads each UCG hook command the way the shell splits it",
        "each value in single quotes as the templates above write them: `KEY='value' uv run '…'`",
        # Final pass: the name quoted with its value, and an operator, which
        # the check now reads as the shell does.
        "Quote the value alone, never its name with it: the shell runs `'KEY=a b'` as the command.",
        "or that holds a shell operator or redirection (`;`, `||`, `&`, `<`, `2>&1`) outside quotes.",
    ):
        assert clause in flat, clause
    problem = _command_problem()
    assert problem("'KEY=a b' uv run '/srv/guard_pretooluse.py'", "guard_pretooluse.py") is not None
    assert problem("KEY='a b' uv run '/srv/guard_pretooluse.py'", "guard_pretooluse.py") is None
    for operator in (";", "||", "&", "<", "2>&1"):
        command = "uv run '/srv/guard_pretooluse.py' %s x" % operator
        assert problem(command, "guard_pretooluse.py") is not None, command
    no_write = flat[flat.index("A merge that would change nothing makes no write") :]
    no_write = no_write[: no_write.index("assert instead of writing")]
    assert "each command quoted as the templates below write it" in no_write


def test_the_bullet_says_what_an_unquoted_budget_command_costs():
    """Review of #186's fix (4.1.0): the bullet said Claude Code skips a budget
    hook that cannot start without a word. Where the shell cannot run the
    command (exit 127) the stop goes through, but an unquoted script path
    leaves `uv run` a script it cannot find, and uv 0.12.15 exits 2 ("Failed
    to spawn"), which on Stop sends the stop back, up to the eight blocks in a
    row after which Claude Code lets it through. Final pass: uv syncs the
    project in the hook's folder before it looks for the script, and where
    that project fails to build or resolve it exits 1 (a non-blocking error
    on Stop), so the stop goes through, as docs/troubleshooting.md says for a
    moved skill."""
    flat = _flat(_hooks_bullet())
    assert "skips the budget hook without a word" not in flat
    assert (
        "and the budget hook counts no turn (a command the shell cannot run lets each stop through; a script `uv` "
        "cannot find sends each stop back with uv's error, up to eight times in a row, unless the project `uv` "
        "syncs first fails to build or resolve, when `uv` exits 1 and each stop goes through too)." in flat
    )


# --- what the setting does, and what it costs --------------------------------


def test_the_bullet_says_what_the_setting_does_and_without_it():
    flat = _flat(_hooks_bullet())
    for clause in (
        "Claude Code refuses the tool call when the guard cannot start (`uv` missing from `PATH`, say), "
        "crashes, exits with a code other than 0 or 2, or times out.",
        "Without it each of those lets the call run unchecked",
        "Claude Code honors the key from 2.1.295, the minimum step 1's `cc_version` check enforces",
        'Write the value exactly `"block"`, in lower case',
        "so a mistyped one leaves no guard at all",
    ):
        assert clause in flat, clause


def test_the_bullet_states_the_cost_and_the_fix_made_outside_the_session():
    flat = _flat(_hooks_bullet())
    assert "A guard that cannot run refuses every tool call, Read and Edit included" in flat
    assert "the fix is made outside the session: put `uv` back on `PATH`" in flat
    assert "remove the guard item from `.claude/settings.local.json` by hand as SECURITY.md describes" in flat


def test_the_no_write_comparison_and_the_assertion_name_the_setting():
    """Without it in the equality list, a 3.x arming reads as matching and is
    kept instead of rewritten; without it in the assertion, nothing checks it."""
    flat = _flat(_hooks_bullet())
    no_write = flat[flat.index("A merge that would change nothing makes no write") :]
    no_write = no_write[: no_write.index("assert instead of writing")]
    assert "the guard item's `\"onFailure\": \"block\"`" in no_write
    assert "every guard item carries `\"onFailure\": \"block\"`" in flat
    assert (
        "(branch, both hooks under their own events, matcher form, the guard's `onFailure`, "
        "how the shell splits each UCG command, injected env," in flat
    )
    assert "**and** that each UCG command quotes its injected values and script path." in flat


def test_the_crash_sentence_states_the_new_behaviour():
    preflight = _flat(_read(PREFLIGHT))
    security = _flat(_read(SECURITY))
    assert "a hook that crashes makes no decision" not in preflight.lower()
    assert "a hook that crashes makes no decision" not in security.lower()
    assert (
        "What it cannot catch itself (an interpreter or `uv` that cannot start, a timeout) Claude Code refuses, "
        "under the guard item's `\"onFailure\": \"block\"` above" in preflight
    )
    assert "preflight arms the guard's hook item with `\"onFailure\": \"block\"`" in security
    assert "a guard that cannot run refuses every tool call, Read and Edit included" in security


def test_troubleshooting_names_the_message_and_the_recovery():
    text = _read(TROUBLESHOOTING)
    section = text[text.index("## Every tool call is refused") :]
    section = _flat(section[: section.index("\n## ", 1)])
    assert 'blocking because onFailure is "block"' in section
    assert "`guard_pretooluse.py`" in section
    assert "Fix it from outside the session" in section
    # The cause a folder name with a space gives, and what the message shows.
    assert "**A path with a space, left unquoted in the command.**" in section
    assert "`/bin/sh: 1: Projects/app/_bmad-output/implementation-artifacts: not found`" in section
    assert "put each injected value and the script path in single quotes" in section
    assert 'REF["See: Every tool call is refused"]' in text


# --- the resume route --------------------------------------------------------

_ROUTE_HEAD = "**A hooks reason is fixed in place, not by a return to Stage 2.**"


def _resume_route(text: str | None = None) -> str:
    text = _read(EXECUTE) if text is None else text
    return next(p for p in text.split("\n\n") if p.startswith(_ROUTE_HEAD))


def _routes_a_3x_arming(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return all(
        clause in flat
        for clause in (
            'the guard not armed with `"onFailure": "block"`',
            "apply `references/preflight.md` step 5's **Hooks** bullet alone",
            "(replace, never append)",
            "every run armed by UCG 3.x or earlier carries",
            "Purge nothing",
            "Run none of preflight's checks, remediation or launch gate",
            "Then run the same `--assert-armed` call again, and drive the story only once it exits 0.",
        )
    )


def test_execute_gives_a_3x_arming_a_re_merge_route_on_resume():
    assert _routes_a_3x_arming(_resume_route())


@pytest.mark.parametrize(
    "clause",
    [
        "(replace, never append)",
        "Purge nothing",
        "Then run the same `--assert-armed` call again, and drive the story only once it exits 0.",
    ],
)
def test_the_route_predicate_rejects_a_dropped_clause(clause: str):
    paragraph = _resume_route()
    assert clause in paragraph
    assert not _routes_a_3x_arming(paragraph.replace(clause, ""))


def test_the_route_follows_the_sweep_and_the_precondition_points_at_it():
    """It sits right after the sweep that produces its reasons, and the
    precondition list that sends hooks 'to Stage 2' names it."""
    text = _read(EXECUTE)
    paragraphs = text.split("\n\n")
    index = next(i for i, p in enumerate(paragraphs) if p.startswith(_ROUTE_HEAD))
    assert paragraphs[index - 1].startswith("**The re-assertion sweep is one script call")
    preconditions = next(p for p in paragraphs if p.startswith("Preconditions (asserted, not assumed)"))
    assert "(on a resume, the hooks by re-merging them through Stage 2's step 5 **Hooks** bullet alone" in preconditions


def test_the_preflight_bullet_hands_a_resume_to_that_route():
    flat = _flat(_hooks_bullet())
    assert (
        "a resume, which never reaches this stage, re-merges through this bullet when its `--assert-armed` "
        "names the missing key (`references/execute.md`, the re-assertion sweep)" in flat
    )


# Review of #186's fix (4.1.0): a run UCG 3.x armed on a Claude Code below
# 2.1.295 meets the missing key and the version together, and the sweep takes
# the escalation route first and fixes none of the others (a hooks re-merge
# writes a protected file a headless session may be refused). Each sentence
# that sends that first resume, or any resume with a hooks reason, to
# re-merge says so where it says it, since a conductor or an operator that
# reads it alone would otherwise make the write.
_OPERATORS_REASON_FIRST = {
    "preflight.md Hooks bullet": (
        "the re-assertion sweep), unless a reason that is the operator's to fix stands beside it (a skills failure, "
        "or a Claude Code below the minimum): that resume escalates the story it was about to drive first, and the "
        "resume after the operator's fix re-merges."
    ),
    "execute.md resume route": (
        "meets this reason and re-arms here, unless a reason that is the operator's to fix (a skills failure, or a "
        "Claude Code below the minimum) stands beside it: the paragraph above takes the escalation route first, and "
        "the resume after the operator's fix re-arms here."
    ),
    # The route's own lead, which orders the re-merge for every hooks reason.
    "execute.md resume route lead": (
        "or injected env that is missing) and no reason that is the operator's to fix stands beside them (the "
        "paragraph above escalates that one first), apply `references/preflight.md` step 5's **Hooks** bullet alone"
    ),
    "troubleshooting.md": (
        "The resume re-checks the hooks and re-arms them if they need it, unless it also finds a reason that is "
        "yours to fix, a missing story skill or a Claude Code older than 2.1.295: it then escalates the story it "
        "was about to drive first, and re-arms the hooks on the resume after you fix that."
    ),
    # The refused settings write, which names the first resume after an update.
    "troubleshooting.md refused write": (
        "A resume rewrites the file too when the hooks need re-arming (the first resume after an update to 4.x "
        "does, unless it first escalates a reason that is yours to fix, such as a Claude Code older than 2.1.295)"
    ),
}


@pytest.mark.parametrize("where", sorted(_OPERATORS_REASON_FIRST))
def test_a_resume_re_arms_only_once_no_operators_reason_stands_beside_it(where: str):
    text = {
        "preflight.md Hooks bullet": _flat(_hooks_bullet()),
        "execute.md resume route": _flat(_resume_route()),
        "execute.md resume route lead": _flat(_resume_route()),
        "troubleshooting.md": _flat(_read(TROUBLESHOOTING)),
        "troubleshooting.md refused write": _flat(_read(TROUBLESHOOTING)),
    }[where]
    assert _OPERATORS_REASON_FIRST[where] in text
    # The sweep's own rule, which these sentences now defer to.
    assert (
        "When one stands beside other reasons, a hooks reason included, take this route first and fix none of the "
        "others" in _flat(_read(EXECUTE))
    )


def test_the_assert_armed_reason_names_the_same_route():
    """The conductor reads the reason first: it names the bullet and the rules."""
    spec = importlib.util.spec_from_file_location("preflight_check_onfailure", PREFLIGHT_CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reason = module._on_failure_reason([None])
    assert "(found: missing)" in reason
    assert "Re-merge the hooks as preflight.md step 5's Hooks bullet says" in reason
    assert "replace, never append; on a resume purge nothing" in reason


# --- the step-1 checks list ----------------------------------------------------


def test_step1_lists_every_check_key_build_report_emits(tmp_path: Path):
    """preflight.md step 1 spells the `checks` keys; the new version flag is one."""
    text = _read(PREFLIGHT)
    block = text[text.index(" checks: {") : text.index("}}", text.index(" checks: {"))]
    listed = {key.strip() for key in block.split("{", 1)[1].replace("\n", " ").split(",")}
    proc = subprocess.run(
        [
            sys.executable,
            str(PREFLIGHT_CHECK),
            "--project-root",
            str(tmp_path),
            "--epic",
            "1",
            "--tea-config",
            str(tmp_path / "tea.yaml"),
            "--impl-artifacts",
            str(tmp_path / "impl"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.stdout, proc.stderr
    emitted = set(json.loads(proc.stdout)["checks"])
    assert "hook_onfailure_ok" in listed
    assert listed == emitted
