#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Every git and script command the prose prescribes is on the default allowlist.

Under `acceptEdits` (drive_epic.py's default mode) a Bash call that no allow
rule matches stops with "This command requires approval", and an unattended
run has nobody to approve it. Preflight step 5 writes each entry of
`allowlist_commands` as an allow rule, `Bash(<entry>:*)`, and Claude Code
matches such a rule only against a command that is the entry itself or starts
with the entry and a space. The #105 headless rehearsal hit three commands the
prose runs and the default list missed (issue #158): the `python3` form of the
customization resolver, `git worktree` at the gate, and `git check-ignore` at
preflight and Execute.

What the test reads: SKILL.md and references/*.md of this skill, and the
SKILL.md of ucg-create-story and ucg-dev-story, which Execute runs inside the
armed run. In each, every inline code span and every line of a fenced block is
a candidate. A candidate is split into shell segments at `&&`, `||`, `;` and
`|`, and the wrappers Claude Code strips before matching are dropped:
`timeout N`, `time`, `nice`, `nohup`, `stdbuf` with its options, the shell
builtins `command` (not `command -v`) and `builtin`, zsh's `noglob`, and bare
`xargs` (not `xargs` with flags). A segment whose first word is `git`, `uv` or
a `python` interpreter is a command form, named by its prefix:
`git <subcommand>`, `uv <subcommand>`, or the interpreter alone.

What it ignores, and why:
  - A segment led by anything else. That covers an assignment
    (`FOO=bar git commit`), a wrapper Claude Code does not strip
    (`sudo git commit`, `xargs -0 git commit`), a shell keyword, and another
    program. In this prose those are the guard's worked examples, the hook's own
    command line (`KEY=value uv run ...`, which runs outside the Bash tool), or
    commands outside this test's scope: `gh` at the health check, the opt-in
    graphify refresh (docs/knowledge-graph-refresh.md says how to allow it),
    `date` (test_mutation_heartbeat_prose.py pins it) and the project's own test
    commands.
  - A bare `git` with no subcommand, which names the program.
  - The git subcommands in NOT_RUN_UNDER_THE_ALLOWLIST, each with its reason.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_SKILLS = _SKILL_ROOT.parent
_CUSTOMIZE = _SKILL_ROOT / "customize.toml"

# The prose the armed run follows.
SCANNED = [
    _SKILL_ROOT / "SKILL.md",
    *sorted((_SKILL_ROOT / "references").glob("*.md")),
    _SKILLS / "ucg-create-story" / "SKILL.md",
    _SKILLS / "ucg-dev-story" / "SKILL.md",
]

# Every command form the scanned prose prescribes, and where.
PRESCRIBED = {
    "git add": "execute.md step 4 stages the story's paths",
    "git commit": "execute.md step 4 commits at green",
    "git rev-parse": "execute.md step 0 records the baseline SHA; ucg-dev-story does too",
    "git diff": "execute.md reads the staged diff with `git diff --cached`",
    "git check-ignore": "preflight.md step 5 and execute.md ask which run outputs git ignores",
    "git status": "gate.md lists the tests automate backfilled with `git status --porcelain --untracked-files=all`",
    "git worktree": "gate.md adds, removes, rebuilds after automate and prunes the measurement worktree",
    "uv run": "every script call, the customization resolver included",
}

# Git subcommands the prose names in a code span that the armed run does not
# issue through the Bash tool under the allowlist.
NOT_RUN_UNDER_THE_ALLOWLIST = {
    "git push": "named only as the other verb the guard checks; the run never pushes",
    "git init": "names how an unborn HEAD comes about; the run never runs it",
    "git checkout": (
        "preflight step 2 cuts the Epic branch before step 5 writes the allowlist, "
        "and a new Epic's preflight is attended (getting-started.md); an entry "
        "would also let an unattended run discard work with `git checkout -- <path>`"
    ),
    "git show": "the guard runs `git show :<path>` itself, in the hook process, outside any permission rule",
    "git ls-files": "names the kind of project conformance gate execute.md warns about; the run never calls it",
    "git -c": "the guard's worked example of a quoted `&` (`git -c alias.x='a&b' commit`)",
    "git -C": (
        "gate.md names `git -C <tmp-path> status` only as the status read it does not make: "
        "no entry covers it (#158's rehearsal saw `git -C <repo> rev-parse` refused), and an "
        "entry would cover every git command in any folder, so the gate rebuilds its worktree instead"
    ),
}

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_SEPARATORS = re.compile(r"&&|\|\||;|\|")
# The wrappers Claude Code strips before it matches an allow rule (its
# permissions page lists them; the list is built in and not configurable).
_STRIPPED_WRAPPERS = re.compile(
    r"^(?:(?:timeout\s+\d+[smhd]?|time|nice|nohup|stdbuf(?:\s+-\S+)*"
    r"|command(?!\s+-)|builtin|noglob|xargs(?!\s+-))\s+)+"
)
_PYTHON = re.compile(r"^python(?:\d+(?:\.\d+)*)?$")


def _fenced_lines_and_paragraphs(text: str) -> tuple[list[str], list[str]]:
    """The lines inside fenced blocks, and the prose outside them, by paragraph."""
    fenced: list[str] = []
    prose: list[str] = []
    fence = None
    for line in text.splitlines():
        match = _FENCE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)
            else:
                prose.append(line)
            continue
        if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) \
                and not line.strip()[len(match.group(1)):].strip():
            fence = None
        else:
            fenced.append(line)
    return fenced, re.split(r"\n[ \t]*\n", "\n".join(prose))


def _code_spans(paragraph: str) -> list[str]:
    """The inline code spans of one paragraph, by CommonMark's rule: a run of
    backticks opens a span that the next run of the same length closes."""
    runs = [(match.start(), match.end()) for match in re.finditer(r"`+", paragraph)]
    spans: list[str] = []
    index = 0
    while index < len(runs):
        start, end = runs[index]
        width = end - start
        close = next(
            (later for later in range(index + 1, len(runs)) if runs[later][1] - runs[later][0] == width),
            None,
        )
        if close is None:
            index += 1
            continue
        spans.append(" ".join(paragraph[end:runs[close][0]].split()))
        index = close + 1
    return spans


def _candidates(path: Path) -> list[str]:
    fenced, paragraphs = _fenced_lines_and_paragraphs(path.read_text(encoding="utf-8"))
    return [line.strip() for line in fenced] + [
        span for paragraph in paragraphs for span in _code_spans(paragraph)
    ]


def _prefixes(command: str) -> list[str]:
    """The command forms in one candidate, as `git <subcommand>`, `uv <subcommand>`
    or the interpreter name."""
    found = []
    for segment in _SEPARATORS.split(command):
        words = _STRIPPED_WRAPPERS.sub("", segment.strip()).split()
        if not words:
            continue
        if _PYTHON.match(words[0]):
            found.append(words[0])
        elif words[0] in ("git", "uv") and len(words) > 1:
            found.append(f"{words[0]} {words[1]}")
    return found


def _found() -> dict[str, list[str]]:
    """Each command form the scanned prose names, with the files that name it."""
    found: dict[str, list[str]] = {}
    for path in SCANNED:
        label = f"{path.parent.name}/{path.name}"
        for candidate in _candidates(path):
            for prefix in _prefixes(candidate):
                files = found.setdefault(prefix, [])
                if label not in files:
                    files.append(label)
    return found


def _allowlist() -> list[str]:
    with _CUSTOMIZE.open("rb") as handle:
        return tomllib.load(handle)["workflow"]["allowlist_commands"]


def _covered(command: str, entries: list[str]) -> bool:
    """Whether a `Bash(<entry>:*)` rule for some entry matches the command.

    `:*` at the end of a rule matches the same commands as ` *`: the entry
    itself, or the entry, a space and anything after it.
    """
    return any(command == entry or command.startswith(entry + " ") for entry in entries)


def test_the_scan_reads_every_file():
    for path in SCANNED:
        assert path.is_file(), path
    found = _found()
    assert "git worktree" in found and "git check-ignore" in found and "uv run" in found


def test_the_prose_prescribes_exactly_the_listed_forms():
    """A command form added to the prose has to be placed: in PRESCRIBED, which
    the next test checks against the allowlist, or in
    NOT_RUN_UNDER_THE_ALLOWLIST with its reason."""
    found = _found()
    unplaced = {prefix: files for prefix, files in found.items()
                if prefix not in PRESCRIBED and prefix not in NOT_RUN_UNDER_THE_ALLOWLIST}
    assert not unplaced, (
        f"command forms the prose names that this test does not place: {unplaced}"
    )
    stale = sorted(set(PRESCRIBED) - set(found))
    assert not stale, f"PRESCRIBED lists forms the prose no longer names: {stale}"


@pytest.mark.parametrize("command", sorted(PRESCRIBED))
def test_every_prescribed_form_is_on_the_default_allowlist(command):
    assert _covered(command, _allowlist()), (
        f"`{command}` ({PRESCRIBED[command]}) matches no `Bash(<entry>:*)` rule "
        "built from the default allowlist_commands, so an unattended run stops "
        "for approval there"
    )


def test_no_scanned_prose_runs_a_script_with_python():
    """No allowlist entry covers `python3 <script>`. The scripts carry PEP 723
    headers and run under `uv run`, which the list already covers. That is not
    the narrower choice: `uv run` runs any program, so its rule already lets
    any Python or other command run through uv. It keeps one rule instead of
    two, and the scripts' headers pick their interpreter."""
    offenders = {prefix: files for prefix, files in _found().items() if _PYTHON.match(prefix)}
    assert not offenders, offenders


def test_every_resolver_call_in_every_skill_runs_under_uv_run():
    """The customization resolver is the call the rehearsal saw refused 8 times.
    The sibling skills call it too, from a session that may not be the armed
    run; they use the same form so a copied line never brings `python3` back.
    Every call to a script under `_bmad/scripts/` passes `--no-project`, the
    story skills' `resolve_config.py` included: BMAD 6.10's resolvers have no
    PEP 723 header (and an older BMAD 6 has no `resolve_config.py` at all), and
    a plain `uv run` of such a script, or of a missing one, inside a Python
    project creates the project's `.venv` and `uv.lock` before preflight's
    clean-tree check."""
    calls = []
    for path in sorted([*_SKILLS.glob("*/SKILL.md"), *_SKILLS.glob("*/references/*.md")]):
        _, paragraphs = _fenced_lines_and_paragraphs(path.read_text(encoding="utf-8"))
        for paragraph in paragraphs:
            for span in _code_spans(paragraph):
                if re.search(r"_bmad/scripts/\w+\.py", span):
                    calls.append((f"{path.parent.name}/{path.name}", span))
    assert len(calls) >= 14, calls
    scripts = {re.search(r"_bmad/scripts/(\w+\.py)", span).group(1) for _, span in calls}
    assert {"resolve_customization.py", "resolve_config.py"} <= scripts, scripts
    wrong = [
        call for call in calls
        if not call[1].startswith("uv run --no-project {project-root}/_bmad/scripts/")
    ]
    assert not wrong, wrong


def test_the_rule_model():
    """The matching this test relies on, on the cases #158 recorded."""
    entries = ["git rev-parse", "git worktree", "git check-ignore", "uv run", "git diff"]
    assert _covered("git rev-parse HEAD", entries)
    assert _covered("git worktree add --detach /tmp/w abc123", entries)
    assert _covered("git check-ignore -q _bmad-output/x.md", entries)
    assert _covered("uv run /p/_bmad/scripts/resolve_customization.py --skill s --key workflow", entries)
    assert _covered(
        "uv run --no-project /p/_bmad/scripts/resolve_customization.py --skill s --key workflow",
        entries,
    )
    assert _covered("uv run --no-project /p/_bmad/scripts/resolve_config.py --project-root /p", entries)
    # The model's own `git -C <repo> rev-parse` did not match, and still would not.
    assert not _covered("git -C /repo rev-parse HEAD", entries)
    assert not _covered("python3 /p/_bmad/scripts/resolve_customization.py --skill s", entries)
    # The space is part of the rule: `git diff` does not cover `git difftool`.
    assert not _covered("git difftool", entries)


def test_the_gate_rebuilds_its_worktree_with_commands_the_allowlist_runs():
    """Issue #174: once automate's mutation runs have edited the gate worktree,
    the gate rebuilds it rather than reading its status, because the status read
    would need `git -C`, which no entry covers and none should."""
    entries = _allowlist()
    for command in (
        "git worktree remove --force /p/_bmad-output/implementation-artifacts/.gate-worktree-4-2",
        "git worktree add /p/_bmad-output/implementation-artifacts/.gate-worktree-4-2 0123abc",
        "uv run /s/scripts/link_worktree_deps.py --project-root /p --worktree /w",
        "git status --porcelain --untracked-files=all",
        "git add tests/unit/a.test.ts",
        # The backfill resume tells a committed backfill from an uncommitted one.
        "git rev-parse HEAD~1",
    ):
        assert _covered(command, entries), command
    assert not _covered("git -C /p/.gate-worktree-4-2 status --porcelain", entries)
    assert "git -C" not in entries


def test_the_extraction_on_the_shapes_the_prose_uses():
    assert _prefixes("git add … && git commit") == ["git add", "git commit"]
    assert _prefixes("timeout 300 git worktree prune") == ["git worktree"]
    assert _prefixes("FOO=bar git commit") == []
    assert _prefixes("sudo git commit") == []
    # Claude Code strips these wrappers too, so a rule for the inner command
    # matches, and the scan has to see that command.
    for wrapper in ("xargs", "command", "builtin", "noglob", "stdbuf -oL", "nice timeout 30"):
        assert _prefixes(f"{wrapper} git worktree prune") == ["git worktree"], wrapper
    # It does not strip these, so no rule for the inner command can match.
    for wrapper in ("xargs -0", "command -v", "env", "sudo"):
        assert _prefixes(f"{wrapper} git worktree prune") == [], wrapper
    assert _prefixes("python3 x.py --key workflow") == ["python3"]
    assert _prefixes("git") == []
    assert _code_spans("run ``a ` b`` then `git worktree add <p> <c>` here") == [
        "a ` b",
        "git worktree add <p> <c>",
    ]
    fenced, _ = _fenced_lines_and_paragraphs("text\n\n```\nuv run x.py\n```\nmore `y`\n")
    assert fenced == ["uv run x.py"]
