#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""UltraCode-Goal PreToolUse guard (Claude Code hook).

Enforces invariants that must NOT live in memory (context, not enforcement):
  1. No `git commit`/`git push` while on a protected branch. The branch is read
     from the hook event's `cwd`, i.e. the session's working directory, NOT the
     repository the command targets, so a `cd /other/repo && git commit` is
     denied while the session's own repo sits on a protected branch. Deliberate
     for now (it errs toward denying), but it is the reason a legitimate commit
     in an unrelated checkout can be refused.
  2. No `git commit` until a "tests-ran" marker exists for the current story.
  3. Marker freshness: no `git commit` unless that marker carries a
     `baseline=<sha>` line matching, character for character, the SHA the story
     recorded when it started. A bare existence check accepts a marker replayed
     from an earlier code state; this ties the marker to the story it claims to
     be green for. Both values are READ from disk (two file reads, no git call)
     and neither is recomputed, so a story spanning several commits stays valid
     after HEAD moves. Fail closed: a marker with no `baseline=` line, or an
     unreadable baseline file, denies.
  4. No `git commit` while the staged index is empty (a commit that captures no
     work), or while the staged-index probe cannot answer (fail closed).
  5. Un-skip proof: in production (an atdd-checklist for the current story is on
     disk), no `git commit` while the STAGED CONTENT of any acceptance-test file
     that checklist enumerates still contains `test.skip(`. The files are the
     ones its `generatedTestFiles` frontmatter lists; only a checklist with no
     such list, or one naming no JS/TS test file, is scanned whole for
     test-file paths. A list that cannot be read as a list denies. This reads
     the blob being committed, not a diff, so it also catches a story's first
     commit, where there is no prior blob to compare against.
  6. Cross-Session Recall, claude-mem: while a run latch (.mem-state.json) is
     present, every claude-mem MCP call (the plugin form and both bare-server
     forms, an MCP resource read or listing on a claude-mem server, and a
     resource listing that names no server, which lists them all) and every
     reach into .claude-mem is denied, whatever the latch's version (v1 or
     v2) or colour. There is no green path: UCG no longer uses claude-mem.
     With no latch, the user's own claude-mem usage is never touched.
     Accepted residual, as for the store below: a search of a folder above
     .claude-mem (a Grep, a `grep -r` or a `**` glob from the home folder).
  7. Cross-Session Recall, local run store and latch file: while a run latch
     is present, the model's tool calls may read the latch but not change it,
     and may not reach the store the latch names.
     - The latch file, whatever the latch holds: a Write, Edit, MultiEdit or
       NotebookEdit call that names the latch path is denied, and so is a Bash
       segment that names it, by path or by its file name on its own
       (_names_file_name), and is not a plain read (_read_segment). Read,
       Grep and Glob are left alone, since Finalize reads the latch.
     - The store, when the latch names a usable store path: a Read, Grep,
       Glob, Write, Edit, MultiEdit, NotebookEdit or Bash call that names that
       path is denied.
     Both read a Bash command without each heredoc body the guard can tell
     bash only hands to a `cat` or `tee` that leads its simple command, as
     data (_without_heredoc_data, whose section comment lists the
     conditions); every other body is read as commands.
     A Bash segment is exempt from both only when it runs this skill's own
     scripts/mem_recall.py or scripts/mem_observation.py, by path, as
     `uv run <path> ...` or `python <path> ...`, with no redirection, command
     substitution or wrapper, in a command that changes no environment or
     command lookup. So only mem_recall.py changes the latch: `latch` writes
     it, and `unlatch` removes it when it carries the caller's run_id.
     Accepted residual, stated like the exec-wrapper one below: indirection
     (for the store, a `cd` then a relative path; for both, a variable
     holding part of the path or the name, a script that names the store or
     the latch in its contents, whether a file tool or a heredoc fed to `cat`
     or `tee` wrote it), commands on an ancestor directory (a search
     of it, removing the implementation artifacts folder, a `git clean` or
     `git stash --all`), repo-wide searches that reach a store inside the
     workspace, the interpreter `uv` or `python` resolves to, with the
     configuration it reads, and a pinned call itself: the exemption checks
     the script's path, not its arguments, so a model that ignores the deny
     note can still run `latch` or `unlatch` on its own.
  Invariants 6 and 7 count a present latch as a live run: the guard reads no
  clock and detects no dead run, so a latch a dead run left behind keeps
  denying until the next Stage 1 replaces it or the user deletes it by hand.
  Every deny a latch causes names the latch path and ends with a note for the
  person: a latch left behind is theirs to delete by hand, and the model must
  not try to remove it.

Hook contract (reads one JSON object on stdin):
  in : {tool_name, tool_input:{command,...}, cwd, ...}
  out: exit 0 + JSON {hookSpecificOutput:{hookEventName,permissionDecision,
       permissionDecisionReason}} where permissionDecision is "deny" to block.
  Defensive fallback: also exit 2 with the reason on stderr (older clients
  honor exit-code-2-blocks even when they ignore the JSON).

This hook is invoked standalone from settings.local.json. It MUST stay fully
self-contained: no sibling imports (the shared library lib/mem_common.py et al.
are NOT imported).

Config resolution (all optional, env wins so the conductor can inject per run):
  ULTRACODE_PROTECTED_BRANCHES  comma-separated; default "main,master"
  ULTRACODE_IMPL_ARTIFACTS      dir holding run state (story id + markers)
  ULTRACODE_STORY_ID            current story id (blank counts as unset);
                                else read from <impl_artifacts>/.current-story
  ULTRACODE_TEST_ARTIFACTS      TEA test-artifacts root; arms the un-skip proof.
                                No default is derived here on purpose (see
                                _test_artifacts): unset means the check is out
                                of scope, never a deny.
  Marker file checked: <impl_artifacts>/.tests-ran-<story_id>
  Baseline read:       <impl_artifacts>/.baseline-<story_id>, the SHA the story
                  recorded before any implementation. Compared as a verbatim,
                  whitespace-stripped string against the marker's `baseline=`
                  line: no `git rev-parse`, no short-SHA normalization, no
                  case-folding. Same <impl_artifacts> and same <story_id> the
                  tests-ran marker uses, deliberately, so there is one
                  resolution path rather than two that can drift apart.
  State latch checked: <impl_artifacts>/.mem-state.json (Cross-Session Recall),
                  read v1 or v2 by this file's own copy of lib/mem_common.py's
                  read_state() and latch_view(), so both read one latch the
                  same way (pinned by a parity test).
  Skill root:     this file's own location, <skill-root>/scripts/hooks/, so
                  the pinned recall scripts are <skill-root>/scripts/
                  mem_recall.py and mem_observation.py (see _pinned_scripts).
  Checklist read: <test_artifacts>/atdd-checklist-<story_id>.md, keyed by the
                  SAME story id the tests-ran marker uses (the id resolved by
                  _current_story). A story_key/story_id drift here would make
                  the un-skip proof silently inert, the worst failure mode a
                  deny guard has. The paths come from its `generatedTestFiles`
                  frontmatter, the list TEA's ATDD writes of the test files it
                  scaffolded (see _listed_test_files).
  Skip token matched: the literal `test.skip(`. That token is JS/Vitest-specific
                  (the Playwright/Vitest form TEA's ATDD generates, which is
                  web/JS-only today); a pytest or Go acceptance suite marks
                  skips differently and this check would not see them.
"""

import bisect
import fnmatch
import functools
import json
import os
import re
import shlex
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import NamedTuple, NoReturn

DEFAULT_PROTECTED = ["main", "master"]


def _read_event() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _allow() -> NoReturn:
    """No decision needed: stay silent, let the normal permission flow run."""
    sys.exit(0)


def _deny(reason: str, hint: str = "") -> NoReturn:
    reason += hint
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    # Belt-and-suspenders: clients that ignore JSON still block on exit 2.
    print(reason, file=sys.stderr)
    sys.exit(2)


def _note(message: str) -> None:
    """Say something on stderr and RETURN (no decision, no exit).

    stdout is the decision channel: anything printed there is parsed as the
    hook's verdict, so a path that reaches no decision must stay off it.
    """
    print(message, file=sys.stderr)


def _protected_branches() -> list[str]:
    env = os.environ.get("ULTRACODE_PROTECTED_BRANCHES")
    if env:
        return [b.strip() for b in env.split(",") if b.strip()]
    return DEFAULT_PROTECTED


def _current_branch(cwd: str | None) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode == 0:
        branch = out.stdout.strip()
        return branch or None
    # An unborn HEAD (a fresh `git init`, nothing committed) fails rev-parse
    # while still printing the literal `HEAD`, which matched no protected name
    # and let a commit through on an unborn `main`. The symbolic ref still
    # names the branch; outside a repository it fails too, and None stands.
    try:
        ref = subprocess.run(
            ["git", "symbolic-ref", "--short", "-q", "HEAD"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if ref.returncode != 0:
        return None
    return ref.stdout.strip() or None


def _staged_index_nonempty(cwd: str | None) -> bool:
    """True only when something is provably staged for the next commit.

    `git diff --cached --quiet` implies `--exit-code`: 0 means nothing is
    staged, 1 means something is, and any other code (128 outside a repo, for
    one) means the probe could not answer. Unlike _current_branch above, which
    swallows the same failures and fails OPEN by returning None, this one fails
    CLOSED: an unanswerable probe reports "nothing staged" so the caller blocks
    the commit rather than waving through a commit it could not inspect.
    """
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False  # git missing, timeout, ...: cannot answer -> fail closed
    if out.returncode == 0:
        return False  # nothing staged
    if out.returncode == 1:
        return True  # something staged
    return False  # any other exit code is a probe failure -> fail closed


def _impl_artifacts(cwd: str | None) -> Path | None:
    env = os.environ.get("ULTRACODE_IMPL_ARTIFACTS")
    if env:
        return Path(env)
    if cwd:
        return Path(cwd) / "_bmad-output" / "implementation-artifacts"
    return None


def _test_artifacts() -> Path | None:
    """TEA test-artifacts root, from env ONLY.

    Mirrors _impl_artifacts above but deliberately WITHOUT its cwd-derived
    fallback. Hooks armed by a run that predates the un-skip proof inject no
    ULTRACODE_TEST_ARTIFACTS; synthesizing a path here would pull every such
    session into scope and brick its commits on a checklist it never wrote.
    Unset means out of scope (an advisory note, never a deny); fail-closed
    behavior applies only *within* scope, once the var is set.
    """
    env = os.environ.get("ULTRACODE_TEST_ARTIFACTS")
    if env:
        return Path(env)
    return None


def _current_story(impl: Path | None) -> str | None:
    # A blank ULTRACODE_STORY_ID counts as unset, as the Stop hook reads it, so
    # both hooks resolve the same story from the same .current-story marker.
    sid = (os.environ.get("ULTRACODE_STORY_ID") or "").strip()
    if sid:
        return sid
    if impl is not None:
        marker = impl / ".current-story"
        if marker.is_file():
            try:
                return marker.read_text(encoding="utf-8").strip() or None
            except OSError:
                return None
    return None


# --- git write detection ----------------------------------------------------
# `git commit` and `git push` are the targets. A shell segment counts as a git
# write only when `git` is its LEADING token — once leading `VAR=val`
# assignments and known exec wrappers are stripped — and the subcommand it would
# run is exactly one of those verbs. Anchoring on the leading token is what
# keeps a verb merely MENTIONED (inside an `echo`, a log line, a here-string)
# from being read as a real commit; matching the verb by exact token equality is
# what keeps `git commit-tree`-style near-misses out, which a trailing `\b`
# never did (`-` is itself a word boundary). A subcommand that is not one git
# runs before any alias counts as both verbs (_unknown_subcommand_verbs).

_WRITE_VERBS = frozenset({"commit", "push"})

# Legacy matches-anywhere scan. Kept ONLY as the fail-closed fallback for a
# segment this tokenizer cannot honestly read (see _segment_write_verbs): for
# those, biasing toward a deny beats guessing.
_GIT_WRITE_ANYWHERE = re.compile(
    r"\bgit\b[^\n;&|]*?\b(?P<verb>commit|push)\b", re.IGNORECASE
)

# Commands that exec another command, so the real leading token sits further
# right. Extendable on purpose: add a name here and its prefixed form anchors
# too. A wrapper NOT on this list leaves a non-`git` leading token and its
# segment is allowed through — the accepted residual, stated in
# references/preflight.md rather than hidden.
_EXEC_WRAPPERS = frozenset(
    {
        "env",
        "command",
        "sudo",
        "time",
        "nice",
        "nohup",
        "timeout",
        "setsid",
        "stdbuf",
        "ionice",
        "doas",
        "exec",
        "builtin",
    }
)

# Shells whose `-c` string payload is re-entered as a command in its own right.
_SHELL_WRAPPERS = frozenset({"sh", "bash", "zsh", "dash"})

# Shell keywords and group openers that occupy the command position inside a
# compound command. Without these, `then git commit`, `do git commit` and
# `( git commit )` lead with a token that is neither `git` nor any wrapper, so
# the segment classified as "no git write" and skipped EVERY commit gate.
# Stripping them is biased toward finding the `git`, exactly as _EXEC_WRAPPERS
# is: a keyword consumed here can only ever make the guard see more, never less.
_SHELL_KEYWORDS = frozenset(
    {
        "if",
        "then",
        "elif",
        "else",
        "fi",
        "for",
        "while",
        "until",
        "do",
        "done",
        "case",
        "esac",
        "select",
        "function",
        "coproc",
        "!",
        "{",
        "}",
        "(",
        ")",
    }
)

# Group openers can also sit glued to the command name (`(git commit -m x)` is
# a valid subshell), where they are part of the first token rather than a token
# of their own.
_GROUP_OPENERS = "({"

# A redirection operator, with its descriptor, at the start of a word; what
# follows it in the same word is its target.
_REDIRECTION = re.compile(r"^\d*(?:&>>|&>|>>|>&|>\||<<<|<<-|<<|<>|<&|>|<)")

# Global `git` options taking a SEPARATE value. The value must be skipped along
# with the option, or `git -C <path> commit` would read <path> as the
# subcommand and wave a real commit through.
_GIT_VALUE_OPTIONS = frozenset(
    {
        "-C",
        "-c",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--exec-path",
        "--config-env",
        "--super-prefix",
        "--attr-source",
        "--shallow-file",
    }
)

_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Openers of a substitution that runs a command this tokenizer cannot see. A
# segment carrying one takes the fail-closed path instead of being anchored.
_SUBSTITUTION_MARKERS = ("$(", "`", "<(")

# Depth cap on `sh -c` recursion: a bound, not a behavior anyone should rely on.
# Past it, a `git` the guard cannot read deeper counts as both verbs.
_MAX_SHELL_DEPTH = 4
_GIT_WORD = re.compile(r"\bgit\b")

# A short-option cluster that carries `-c`, whose operand is the command string.
# Matching only the bare `-c` token was a fail-open: every real combined form
# (`bash -lc`, `sh -lc`, `bash -cx`, `zsh -ic`, `bash -ec`) located no payload,
# so the segment classified as carrying no git write and took the allow path
# BEFORE the protected-branch, tests-ran, marker-freshness and empty-index gates.
# The `c` is matched anywhere in the cluster, not just at the end, because the
# shells treat it positionally-indifferently: `bash -cx` and `bash -xc` both run
# the next token (verified against bash, sh and dash). A long option (`--login`)
# cannot match, since the character after the lone leading dash must be a letter.
_PAYLOAD_FLAG = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")


# --- git subcommands that are not git's own --------------------------------
# `git ci` runs `git commit` when `alias.ci = commit`, and nothing in the
# command says what an alias runs: git reads it from configuration the command
# can change before git starts. Whether `git <name>` is an external
# `git-<name>` command instead depends on PATH, which can differ between this
# hook and the shell that runs the command, or change inside it. So the guard
# reads neither. A git subcommand counts as no write only when it is one of
# git's built-in commands, which git runs before any alias and which nothing
# can move or shadow, spelled as git spells it (git matches its command names
# case-sensitively, so `git LOG` runs `alias.log`), or one of the commands git
# ships as scripts in its exec-path, while the command does not mention that
# path. Every other subcommand (an alias, an external command such as `git
# lfs`, a typo) counts as both verbs, so the commit and push gates judge it,
# and the deny names it (_unknown_hint). A built-in whose job is to run another
# git subcommand stays off the list (`for-each-repo`). Only commands built in on every
# supported build belong on the first list: none newer than Git 2.30, and no
# `whatchanged`, which Git 3.0 drops. A test checks both lists on both CI legs.
_GIT_COMMANDS = frozenset(
    {
        "add", "am", "annotate", "apply", "archive", "bisect", "blame",
        "branch", "bugreport", "bundle", "cat-file", "check-attr",
        "check-ignore", "check-mailmap", "check-ref-format", "checkout",
        "checkout-index", "cherry", "cherry-pick", "clean", "clone", "column",
        "commit-graph", "commit-tree", "config", "count-objects", "credential",
        "describe", "diff", "diff-files", "diff-index", "diff-tree",
        "difftool", "fast-export", "fast-import", "fetch", "fetch-pack",
        "fmt-merge-msg", "for-each-ref", "format-patch",
        "fsck", "gc", "grep", "hash-object", "help", "index-pack", "init",
        "init-db", "interpret-trailers", "log", "ls-files", "ls-remote",
        "ls-tree", "mailinfo", "mailsplit", "maintenance", "merge",
        "merge-base", "merge-file", "merge-index", "merge-tree", "mktag",
        "mktree", "multi-pack-index", "mv", "name-rev", "notes",
        "pack-objects", "pack-refs", "patch-id", "prune", "prune-packed",
        "pull", "range-diff", "read-tree", "rebase", "receive-pack", "reflog",
        "remote", "repack", "replace", "rerere", "reset", "restore",
        "rev-list", "rev-parse", "revert", "rm", "send-pack", "shortlog",
        "show", "show-branch", "show-index", "show-ref", "sparse-checkout",
        "stage", "stash", "status", "stripspace", "switch", "symbolic-ref",
        "tag", "unpack-objects", "update-index", "update-ref",
        "update-server-info", "upload-archive", "upload-pack", "var",
        "verify-commit", "verify-pack", "verify-tag", "version", "worktree",
        "write-tree",
    }
)
# Commands git ships as scripts in its exec-path, which it also runs before an
# alias of the name, unless the command moves that path (`--exec-path`,
# `GIT_EXEC_PATH`): a mention of it anywhere in the command, a nested shell's
# included, makes them count as both verbs too.
_GIT_SCRIPT_COMMANDS = frozenset({"filter-branch", "mergetool", "quiltimport", "request-pull", "submodule"})
_EXEC_PATH_TEXT = re.compile(r"exec[-_]path", re.IGNORECASE)

# What a git subcommand that is not git's own counts as: both verbs, so the
# commit and push gates judge it, which is where the doubt belongs.
_UNRESOLVED_VERBS = frozenset(_WRITE_VERBS)

# A subcommand the deny's hint may quote: the shape of a command or alias name,
# so a fragment torn from a quoted argument never reaches the reason.
_NAME_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class _CommandScope:
    """What classifying one command collects and reuses along the way."""

    def __init__(self, command: str = "") -> None:
        self.moves_exec_path = bool(_EXEC_PATH_TEXT.search(command))
        # The subcommands counted as both verbs, in the order first met.
        self.unknown: dict[str, None] = {}
        # Each substitution body's verbs at a depth, so the four readings of a
        # command, and their own readings of a nested body, classify it once
        # there (a body met at the depth cap is read more shallowly elsewhere).
        self.bodies: dict[tuple[str, int], set[str]] = {}


def _tokenize(segment: str) -> list[str]:
    """Split one shell segment into words; raises ValueError on bad quoting.

    A named seam on purpose: it gives the fail-closed fallback below a single
    trigger to catch, instead of scattering shlex handling through the caller.
    """
    return shlex.split(segment)


def _strip_assignments(tokens: list[str]) -> list[str]:
    """Drop the leading `VAR=val` prefix, so `FOO=bar git commit` still anchors."""
    index = 0
    while index < len(tokens) and _ASSIGNMENT.match(tokens[index]):
        index += 1
    return tokens[index:]


def _git_subcommand_index(tokens: list[str]) -> int | None:
    """Where the subcommand `git` would run sits among the tokens after `git`."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _GIT_VALUE_OPTIONS:
            index += 2  # skip the option AND its separate value
            continue
        if token.startswith("-"):
            index += 1
            continue
        return index
    return None


def _unknown_subcommand_verbs(name: str, scope: _CommandScope | None) -> set[str]:
    """Both verbs for `git <name> ...` when `name` is not one of git's own commands.

    Empty for a built-in command (_GIT_COMMANDS) and, while the command does
    not mention git's exec-path, for one git ships as a script there
    (_GIT_SCRIPT_COMMANDS). Anything else counts as both verbs and is recorded
    on the scope, when it has a name's shape, for the deny's hint.
    """
    if name in _GIT_COMMANDS:
        return set()
    if name in _GIT_SCRIPT_COMMANDS and not (scope and scope.moves_exec_path):
        return set()
    if scope is not None and _NAME_SHAPE.match(name):
        scope.unknown.setdefault(name, None)
    return set(_UNRESOLVED_VERBS)


def _substitution_bodies(text: str) -> list[str]:
    """The commands inside each `$(...)`, `<(...)`, `>(...)` and backtick pair.

    Text in single quotes is skipped, since the shell substitutes nothing
    there (`echo 'run `git ci` later'`), and so is a backslash-escaped
    character; double quotes do not stop a substitution. Parentheses are
    counted, not parsed, and a heredoc is read as plain text: a body that comes
    out wrong is classified anyway, which can only add verbs.
    """
    bodies: list[str] = []
    index = 0
    in_double = False
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
        elif char == "'" and not in_double:
            end = text.find("'", index + 1)
            index = len(text) if end == -1 else end + 1
        elif char == '"':
            in_double = not in_double
            index += 1
        elif text.startswith(("$(", "<(", ">("), index):
            start = index = index + 2
            level = 1
            while index < len(text) and level:
                if text[index] == "(":
                    level += 1
                elif text[index] == ")":
                    level -= 1
                index += 1
            bodies.append(text[start : index - 1 if level == 0 else index])
        elif char == "`":
            end = text.find("`", index + 1)
            end = len(text) if end == -1 else end
            bodies.append(text[index + 1 : end])
            index = end + 1
        else:
            index += 1
    return bodies


# shlex's punctuation mode yields a run of these characters as one token (a
# newline is one of them, so it ends a segment as it does in bash). The run is
# split into bash's own operators, longest first: a control operator ends a
# segment (`;`, `&&`, `|&`, a newline, the `()` of a function definition, a
# process substitution's `<(` or `>(`, so `true;>(git commit)` reads its
# body), and a redirection (`>&`, `>|`, `<<`) stays in the segment it opens,
# where _strip_leading_noise reads it.
_PUNCTUATION = "();<>|&\n"
_OPERATORS = (
    ";;&", "&>>", "<<<", "<<-", ";;", ";&", "&&", "||", "|&", "&>", ">>", ">&",
    "<&", ">|", "<>", "<<", "<(", ">(", ";", "&", "|", "<", ">", "(", ")", "\n",
)  # fmt: skip
_CONTROL_OPERATORS = frozenset(
    {";;&", ";;", ";&", "&&", "||", "|&", ";", "&", "|", "(", ")", "\n", "<(", ">("}
)


# Punctuation inside quotes, or escaped, is a word's text, not an operator, but
# shlex hands a quoted `')>'` back as `)>`, which reads as one. So it is masked
# before lexing, with a quote scan that follows shlex's own posix rules (a
# backslash escapes outside single quotes; single quotes take everything up to
# the next one; double quotes take an escaped character as it is), and unmasked
# in the tokens after.
_MASK_BASE = 0xE000


def _mask_quoted(text: str) -> str:
    """`text` with each punctuation character inside quotes or escaped masked.

    Unbalanced quotes leave the text as it is, for shlex to refuse.
    """
    out: list[str] = []
    index = 0
    size = len(text)

    def masked(char: str) -> str:
        return chr(_MASK_BASE + ord(char)) if char in _PUNCTUATION else char

    while index < size:
        char = text[index]
        if char == "\\" and index + 1 < size:
            out.append(char + masked(text[index + 1]))
            index += 2
        elif char == "'":
            end = text.find("'", index + 1)
            if end == -1:
                return text
            out.append("'" + "".join(masked(c) for c in text[index + 1 : end]) + "'")
            index = end + 1
        elif char == '"':
            end = index + 1
            body: list[str] = []
            while end < size and text[end] != '"':
                if text[end] == "\\" and end + 1 < size:
                    body.append(text[end] + masked(text[end + 1]))
                    end += 2
                else:
                    body.append(masked(text[end]))
                    end += 1
            if end >= size:
                return text
            out.append('"' + "".join(body) + '"')
            index = end + 1
        else:
            out.append(char)
            index += 1
    return "".join(out)


def _unmask(token: str) -> str:
    return "".join(
        chr(ord(c) - _MASK_BASE) if _MASK_BASE <= ord(c) < _MASK_BASE + 128 else c for c in token
    )


def _operators(token: str) -> list[str] | None:
    """A run of punctuation as bash's operators, longest first; None for a word."""
    if not token or not set(token) <= set(_PUNCTUATION):
        return None
    found: list[str] = []
    index = 0
    while index < len(token):
        operator = next(op for op in _OPERATORS if token.startswith(op, index))
        found.append(operator)
        index += len(operator)
    return found

# A heredoc's start, with its delimiter, quoted or not.
_HEREDOC_START = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _lexable(command: str) -> str:
    """The command with what shlex reads unlike bash taken out, for a reading
    of its own.

    A comment (a `#` that starts a word, outside quotes, up to its line's end),
    an ANSI-C string `$'...'`, whose backslash escapes shlex does not know and
    in which nothing is substituted (it becomes an empty word), and a heredoc's
    body (the lines up to its delimiter, which may hold any text, apostrophes
    included). The rest is copied as it is, quotes and escapes included, for
    shlex to read. Its reading of comments and heredocs is rough (a `#` after
    `$(...)`, a `<<` in arithmetic), and a misread takes out text bash runs, so
    this text is only ever read beside the command as it is
    (_command_write_verbs): it can add a reading, never replace one.
    """
    out: list[str] = []
    pending: list[str] = []  # heredoc delimiters whose bodies start at the next newline
    index = 0
    size = len(command)
    word_start = True
    while index < size:
        char = command[index]
        if char == "\\":
            out.append(command[index : index + 2])
            index += 2
            word_start = False
        elif command.startswith("$'", index):
            end = index + 2
            while end < size and command[end] != "'":
                end += 2 if command[end] == "\\" else 1
            out.append("''")
            index = end + 1
            word_start = False
        elif char in "'\"":
            end = index + 1
            while end < size and command[end] != char:
                end += 2 if char == '"' and command[end] == "\\" else 1
            out.append(command[index : end + 1])
            index = end + 1
            word_start = False
        elif char == "#" and word_start:
            end = command.find("\n", index)
            index = size if end == -1 else end
        elif command.startswith("<<", index) and not command.startswith("<<<", index):
            match = _HEREDOC_START.match(command, index)
            if match:
                pending.append(match.group(2))
                out.append(command[index : match.end()])
                index = match.end()
            else:
                out.append("<<")
                index += 2
            word_start = False
        elif char == "\n":
            out.append("\n")
            index += 1
            word_start = True
            for delimiter in pending:
                while index < size:
                    end = command.find("\n", index)
                    line = command[index : size if end == -1 else end]
                    index = size if end == -1 else end + 1
                    if line.lstrip("\t") == delimiter:
                        break
            pending.clear()
        else:
            out.append(char)
            index += 1
            word_start = char in " \t;&|()<>"
    return "".join(out)


def _quoted_segments(command: str) -> list[list[str]]:
    """The command's segments as quote-aware tokens, or none when it cannot be read.

    The quote-blind splits in _command_write_verbs tear a quoted `;`, `&&` or
    `|` apart (`git ci -m 'fix: a; b'`), and each fragment then tokenizes to
    nothing. shlex in punctuation mode keeps it inside its word.
    """
    lexer = shlex.shlex(_mask_quoted(command), posix=True, punctuation_chars=_PUNCTUATION)
    lexer.whitespace = " \t\r"  # a newline is punctuation, so it ends a segment
    lexer.whitespace_split = True
    lexer.commenters = ""  # shlex would start one mid-word; bash does not
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    segments: list[list[str]] = [[]]
    for token in tokens:
        operators = _operators(token)
        if operators is None:
            segments[-1].append(_unmask(token))
            continue
        for operator in operators:
            if operator in _CONTROL_OPERATORS:
                segments.append([])
            else:
                segments[-1].append(operator)
    return [segment for segment in segments if segment]


def _shell_payload_verbs(
    tokens: list[str], depth: int, scope: _CommandScope | None = None
) -> set[str] | None:
    """Verbs written by the string payload of a `sh -c '…'`-style invocation.

    Returns ``None`` — not an empty set — when the payload cannot be located at
    all, so the caller can fall back to the anywhere-scan instead of reading
    "no payload found" as "no git write here". A LISTED shell wrapper failing
    open is not part of the accepted residual (an UNLISTED one is; see
    test_unlisted_wrapper_is_an_accepted_fail_open), and every other lane that
    cannot honestly read a segment — unbalanced quotes, `$(…)`/backticks —
    already biases toward the deny. This one now matches them.
    """
    if depth >= _MAX_SHELL_DEPTH:
        # The cap is a recursion bound, not a verdict: refusing to look deeper
        # is exactly the "cannot read it" case, so it fails closed too, and a
        # `git` in what it cannot read counts as both verbs (the
        # matches-anywhere scan knows only the literal verbs, not an alias).
        return set(_UNRESOLVED_VERBS) if any(_GIT_WORD.search(t) for t in tokens) else None
    for index, token in enumerate(tokens):
        if _PAYLOAD_FLAG.match(token) and index + 1 < len(tokens):
            return _command_write_verbs(tokens[index + 1], depth + 1, scope)
    return None


def _strip_leading_noise(tokens: list[str]) -> list[str]:
    """Drop leading `VAR=val` assignments, shell keywords, group openers and
    redirections.

    Applied repeatedly because they nest: `if ! FOO=1 git commit …` puts three
    different kinds of noise ahead of the verb. A name after `function`, or
    after `coproc` ahead of a group, names the function, not a command; a
    redirection ahead of the command (`>/dev/null git commit`, `2>&1 git
    commit`, `> out git commit`) is no command either. Every strip here can
    only turn an unclassifiable segment into a classifiable one, so this
    direction is fail-closed by construction.
    """
    while True:
        stripped = _strip_assignments(tokens)
        if stripped:
            head = stripped[0]
            bare = head.lstrip(_GROUP_OPENERS)
            redirect = _REDIRECTION.match(head)
            if bare != head:
                # `(git commit …)` — opener glued to the command name.
                stripped = ([bare] + stripped[1:]) if bare else stripped[1:]
            elif head == "function" and len(stripped) > 1:
                stripped = stripped[2:]
            elif head == "coproc" and len(stripped) > 2 and stripped[2] in ("{", "("):
                stripped = stripped[2:]
            elif head.lower() in _SHELL_KEYWORDS:
                stripped = stripped[1:]
            elif redirect:
                # An operator alone (`>`, `2>&`) takes the next word as its
                # target, unless that word is `git`: a quoted punctuation word
                # (`exec -a ')>' git ci`) reads as an operator here, and the
                # git after it must not be taken for its target.
                alone = redirect.end() == len(head)
                target_is_git = alone and len(stripped) > 1 and os.path.basename(stripped[1]).lower() == "git"
                stripped = stripped[2:] if alone and not target_is_git else stripped[1:]
            elif head.isdigit() and len(stripped) > 1 and _REDIRECTION.match(stripped[1]):
                stripped = stripped[1:]  # the descriptor of `2 >&1`, split by the quote-aware reading
        if stripped == tokens:
            return stripped
        tokens = stripped


def _token_write_verbs(
    tokens: list[str], depth: int, scope: _CommandScope | None = None
) -> set[str] | None:
    """Classify one tokenized segment: which write verbs would it actually run?

    ``None`` propagates the "cannot honestly read this" signal up to
    :func:`_segment_write_verbs`, which owns the raw segment the fallback needs.
    """
    tokens = _strip_leading_noise(tokens)
    if not tokens:
        return set()
    head = os.path.basename(tokens[0]).lower()
    if head == "git":
        index = _git_subcommand_index(tokens[1:])
        if index is None:
            return set()
        if tokens[1 + index].lower() in _WRITE_VERBS:
            return {tokens[1 + index].lower()}
        return _unknown_subcommand_verbs(tokens[1 + index], scope)
    if head in _SHELL_WRAPPERS:
        return _shell_payload_verbs(tokens[1:], depth, scope)
    if head == "eval":
        # `eval` runs its arguments, joined, as a command of its own, after a
        # `--` it skips.
        if depth >= _MAX_SHELL_DEPTH:
            return set(_UNRESOLVED_VERBS) if any(_GIT_WORD.search(t) for t in tokens) else None
        args = tokens[2:] if tokens[1:2] == ["--"] else tokens[1:]
        return _command_write_verbs(" ".join(args), depth + 1, scope)
    if head in _EXEC_WRAPPERS:
        # Every wrapper has its own option grammar (`timeout 30 …`, `nice -n 10
        # …`, `sudo -u u …`, `stdbuf -oL …`), and modelling them one by one is
        # exactly how a LISTED wrapper turns into a fail-open. So hand the rest
        # of the segment back to this same classifier from the first token that
        # could start a command — biased toward finding the git, not toward
        # parsing the wrapper.
        for index in range(1, len(tokens)):
            name = os.path.basename(tokens[index]).lower()
            if name in ("git", "eval") or name in _SHELL_WRAPPERS or name in _EXEC_WRAPPERS:
                return _token_write_verbs(tokens[index:], depth, scope)
    return set()


def _anywhere_write_verbs(segment: str) -> set[str]:
    """Fail-closed fallback: the legacy scan for the verb anywhere in a segment."""
    match = _GIT_WRITE_ANYWHERE.search(segment)
    return {match.group("verb").lower()} if match else set()


def _body_verbs(segment: str, depth: int, scope: _CommandScope | None) -> set[str]:
    """The write verbs of each substitution body in the segment, each read as a
    command of its own, once per body and depth; past the depth cap, both verbs
    for a `git` the guard cannot read deeper."""
    if depth >= _MAX_SHELL_DEPTH:
        return set(_UNRESOLVED_VERBS) if _GIT_WORD.search(segment) else set()
    verbs: set[str] = set()
    for body in _substitution_bodies(segment):
        if scope is None:
            verbs |= _command_write_verbs(body, depth + 1, scope)
            continue
        key = (body, depth)
        if key not in scope.bodies:
            scope.bodies[key] = set()  # a body that holds itself stops here
            scope.bodies[key] = _command_write_verbs(body, depth + 1, scope)
        verbs |= scope.bodies[key]
    return verbs


def _without_comments(segment: str) -> str:
    """The segment with its line continuations joined and each line's trailing
    `#` comment, and a trailing backslash, taken out. Read quote-blind, so it
    can cut a quoted `#` too: it is only ever an extra reading."""
    lines = segment.replace("\\\n", " ").split("\n")
    return "\n".join(re.sub(r"(^|\s)#.*$", r"\1", line) for line in lines).rstrip().rstrip("\\")


def _uncommented_verbs(segment: str, depth: int, scope: _CommandScope | None) -> set[str]:
    """The verbs of the segment read without its comments, when it does not
    tokenize as it is: an apostrophe in a trailing comment (`git ci # it's`)
    leaves no tokens, and the matches-anywhere scan knows no alias."""
    stripped = _without_comments(segment)
    if stripped == segment:
        return set()
    try:
        tokens = _tokenize(stripped)
    except ValueError:
        return set()
    return _token_write_verbs(tokens, depth, scope) or set()


def _segment_write_verbs(segment: str, depth: int, scope: _CommandScope | None = None) -> set[str]:
    if any(marker in segment for marker in _SUBSTITUTION_MARKERS):
        # The real command hides inside the substitution; anchoring would read
        # the outer word and allow it. Fall back rather than fail open. Each
        # substitution's body is classified as a command of its own, and the
        # outer words too where they tokenize, so a git alias inside one
        # (`echo "$(git ci)"`) or around one (`git ci -m "$(date)"`) is seen.
        verbs = _anywhere_write_verbs(segment) | _body_verbs(segment, depth, scope)
        try:
            tokens = _tokenize(segment)
        except ValueError:
            return verbs | _uncommented_verbs(segment, depth, scope)
        return verbs | (_token_write_verbs(tokens, depth, scope) or set())
    # An output process substitution's body is a command too. It is read on its
    # own, not through the matches-anywhere scan, which would deny a read whose
    # words name a verb (`git log --grep=push > >(cat)`).
    verbs = _body_verbs(segment, depth, scope) if ">(" in segment else set()
    try:
        tokens = _tokenize(segment)
    except ValueError:
        # Unbalanced quotes: there are no trustworthy tokens, so fall back to
        # the legacy scan rather than wave the segment through, and read the
        # segment once more without its comments. Letting the exception escape
        # would exit non-zero, which is neither a clean allow nor a clean deny.
        return verbs | _anywhere_write_verbs(segment) | _uncommented_verbs(segment, depth, scope)
    found = _token_write_verbs(tokens, depth, scope)
    if found is None:
        # A listed shell wrapper whose payload could not be located. Same
        # treatment as the two lanes above: scan the raw segment rather than
        # let an unreadable invocation classify as carrying no write.
        return verbs | _anywhere_write_verbs(segment)
    return verbs | found


def _command_write_verbs(command: str, depth: int, scope: _CommandScope | None = None) -> set[str]:
    verbs: set[str] = set()
    # Classified under BOTH separator sets, unioned. Neither alone is safe:
    #
    #   - Without the newline, `printf ok > .tests-ran-1\ngit commit -m x` is one
    #     segment led by `printf`, which anchors to nothing and waves through a
    #     real commit — bypassing the protected-branch, tests-ran, freshness AND
    #     empty-index gates in a single Bash call.
    #   - With ONLY the newline set, the split is quote-blind, so a newline inside
    #     a quoted argument that sits between `git` and its verb
    #     (`git -c foo.bar="a\nb" commit -m x`, and every other
    #     `_GIT_VALUE_OPTIONS` form) tears the command into two fragments that
    #     each fail to tokenize and each miss the newline-anchored fallback
    #     regex — a real commit, allowed.
    #
    # Unioning makes the result a strict SUPERSET of what the separator-only set
    # detects, so this cannot classify less than it did before the newline was
    # added. That property is what is being bought here, and it is why this is a
    # union rather than one cleverer regex: a quote-aware splitter would be a
    # second hand-rolled shell parser whose every disagreement with `shlex` is a
    # new fail-open, and getting it wrong in the do-not-split direction silently
    # restores the newline bypass above.
    #
    #   - Neither of those two sets matches a LONE `&`, which is a real bash
    #     separator (background-then-continue), so `npm run build & git commit`
    #     stayed ONE segment led by `npm` and was waved through. It gets its own
    #     set rather than an `&` bolted onto the two above, for the same reason
    #     the newline did: splitting on `&` is quote-blind too, so
    #     `git -c a.b='x&y' commit -m z` would tear into two fragments that each
    #     fail to tokenize AND each miss the fallback regex (fragment one has no
    #     verb, fragment two has no `git`) — turning a deny into an allow. Added
    #     as a third member of the union, it can only ever classify MORE.
    #
    # The `\|\|` alternative must precede `\|` so `||` is consumed whole, and
    # `&&` must precede `&` for the same reason. `\r` rides along with `\n` for
    # CRLF-authored commands.
    for separators in (
        r"&&|\|\||;|\|",
        r"&&|\|\||;|\||\n|\r",
        r"&&|\|\||;|\||&|\n|\r",
    ):
        for segment in re.split(separators, command):
            verbs |= _segment_write_verbs(segment, depth, scope)
    # Quote-aware readings join the union: they keep a quoted separator inside
    # its word (`git ci -m 'fix: a; b'`), which the three quote-blind splits
    # tear into fragments that classify as nothing, and like them they can
    # only add verbs. One reads the command as it is; the other reads it with
    # what shlex cannot lex taken out (_lexable: a comment holding an
    # apostrophe, `$'...'`, a heredoc body), and adds to the first, never
    # replaces it. A text shlex cannot read adds none.
    lexable = _lexable(command)
    for text in (command,) if lexable == command else (command, lexable):
        for tokens in _quoted_segments(text):
            verbs |= _token_write_verbs(tokens, depth, scope) or set()
    return verbs


def _classify(command: str) -> tuple[set[str], list[str]]:
    """The {'commit','push'} subset the command would perform, and the git
    subcommands that are not git's own it counted as both, for the git gates'
    deny hint (_unknown_hint)."""
    scope = _CommandScope(command)
    return _command_write_verbs(command, 0, scope), list(scope.unknown)


def _git_writes(command: str) -> set[str]:
    """Return the {'commit','push'} subset the command would perform.

    Classifies each shell segment independently, so a chained
    `git add && git commit` is still caught. A git subcommand that is not one
    of git's own counts as both (_unknown_subcommand_verbs).
    """
    return _classify(command)[0]


def _unknown_hint(names: list[str]) -> str:
    """The note a git gate's deny adds when the command runs a subcommand that
    is not git's own: it may be why the command was denied, and what to do."""
    if not names:
        return ""
    shown = ", ".join(f"`git {name}`" for name in names[:3])
    return (
        f" Note: this command runs {shown}, which is not one of git's built-in "
        "commands, so this guard counts it as a commit and a push: it cannot tell "
        "what an alias runs. If that is why it was denied, run the git command an "
        "alias stands for, or an external command by its own name (`git-lfs pull` "
        "for `git lfs pull`)."
    )


# --- Marker freshness -------------------------------------------------------
# A tests-ran marker proves that a suite once ran green. Nothing in a bare
# existence check stops that marker from being REPLAYED: written against an
# earlier code state, or left over from a previous story, it satisfies the check
# forever. So the marker carries the commit the story started from, and this
# clause requires it to equal the SHA the story recorded.
#
# Both sides are read as strings from files that already exist for other
# reasons, so this costs two file reads and one comparison — no `git rev-parse`.
# That is not an optimization: recomputing the SHA here would compare against a
# HEAD that has already moved on any story that commits more than once, and
# would deny its second commit. Read, never derive.

_MARKER_BASELINE_RE = re.compile(r"^baseline=(.*)$", re.MULTILINE)


def _marker_baseline_sha(marker: Path) -> str | None:
    """The SHA on the marker's FIRST `baseline=` line, whitespace-stripped.

    None when the marker cannot be read at all or carries no such line — both
    of which the caller treats as a deny, not as "check not applicable".
    """
    try:
        text = marker.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = _MARKER_BASELINE_RE.search(text)
    return match.group(1).strip() if match else None


def _recorded_baseline_sha(baseline: Path) -> str | None:
    """The story's recorded baseline SHA, read verbatim off its own file.

    Deliberately NOT `git rev-parse HEAD`: the story is anchored to where it
    started, and HEAD walks away from that as soon as the story's first commit
    lands.
    """
    try:
        return baseline.read_text(encoding="utf-8").strip() or None
    except (OSError, UnicodeDecodeError):
        return None


def _marker_freshness_gate(marker: Path, baseline: Path) -> None:
    """Deny a commit whose tests-ran marker was not written for this baseline.

    Fail closed on both absences. There is no inert path here (unlike the
    un-skip proof's unset-env case): a marker that cannot be tied to a baseline
    is exactly the replayed marker this clause exists to refuse, so "cannot
    tell" and "does not match" get the same answer.
    """
    marker_sha = _marker_baseline_sha(marker)
    if marker_sha is None:
        _deny(
            "Marker-freshness guard: refusing `git commit` — the tests-ran "
            f"marker {marker} carries no `baseline=<sha>` line, so it cannot be "
            f"tied to the commit this story started from ({baseline}) and may "
            "be a marker replayed from an earlier code state. Failing closed. "
            "Re-run the story's test/lint/build to green, then rewrite "
            f"{marker} with a `baseline=<sha>` line copied verbatim from "
            f"{baseline}, then commit. The rewrite must be its own, prior tool "
            "call: this guard pre-evaluates the command string, so a marker "
            "written in the same compound command as the commit does not exist "
            "yet when the commit is evaluated."
        )
    baseline_sha = _recorded_baseline_sha(baseline)
    if baseline_sha is None:
        _deny(
            "Marker-freshness guard: refusing `git commit` — this story's "
            f"recorded baseline {baseline} is missing or unreadable, so the "
            f"tests-ran marker {marker} cannot be checked against it. Failing "
            "closed. If this story has already committed, restore that file "
            "(the full 40-hex commit this story started from, one line); if it "
            "has not yet committed — a fresh story at a resume boundary never "
            "had one — write it now from `git rev-parse HEAD` exactly as step 0 "
            "does. Then re-run the story's test/lint/build to green, rewrite "
            f"{marker} with a `baseline=<sha>` line copied verbatim from it, "
            "and commit — each write its own, prior tool call, never chained "
            "into the commit command."
        )
    if marker_sha != baseline_sha:
        _deny(
            "Marker-freshness guard: refusing `git commit` — the tests-ran "
            f"marker {marker} records baseline={marker_sha}, but this story's "
            f"recorded baseline {baseline} is {baseline_sha}. The marker was "
            "written against a different code state, so it proves nothing "
            "about the tree being committed now. Re-run the story's "
            f"test/lint/build to green, then rewrite {marker} with a "
            f"`baseline=<sha>` line copied verbatim from {baseline} (copied, "
            "never re-derived from `git rev-parse HEAD` — the baseline does "
            "not move while the story runs), then commit. The rewrite must be "
            "its own, prior tool call: the guard pre-evaluates the command "
            "string, so a marker written in the same compound command as the "
            "commit does not exist yet when the commit is evaluated."
        )


# --- Un-skip proof ----------------------------------------------------------
# In production the story's atdd-checklist is the ground truth for which files
# carry its acceptance tests. This clause reads the STAGED post-image of each of
# them and refuses a commit that would capture a still-skipped acceptance test.
# It asserts absence in the blob being committed, so it holds on a story's first
# commit as well as on later ones; it is not a diff of "was the marker removed".

_SKIP_TOKEN = "test.skip("

# Path-shaped tokens naming a JS/TS acceptance-test file. Deliberately loose on
# the leading segment ({project-root}/…, an absolute path, a bare relative one)
# and strict on the extension, so prose around the paths is not mistaken for one.
_TEST_FILE = re.compile(
    r"""[^\s`'"()\[\],]+\.(?:spec|test)\.(?:[cm]?[jt]sx?)\b"""
)


def _checklist_test_files(text: str) -> list[str]:
    """Every acceptance-test path the checklist names, in order, deduplicated."""
    found: list[str] = []
    for match in _TEST_FILE.finditer(text):
        token = match.group(0)
        if token not in found:
            found.append(token)
    return found


# TEA's ATDD writes the test files it scaffolded to the checklist's
# `generatedTestFiles` frontmatter (step-04c sets it, step-05 keeps it). Its
# prose and tables also cite files the story only read (`inputDocuments`), bare
# `file::case` references, globs and partial paths, none of which `git show :`
# can read, so when that list names a test file it is the whole set. A
# checklist with no such list (hand-written, or older) is scanned whole, as is
# one whose list names no JS/TS test file (TEA starts it as `[]`).
_LISTED_KEY = re.compile(r"generatedTestFiles\s*:(.*)$")


def _strip_comment(
    line: str, quote: str = "", depth: int = 0, start: bool = True
) -> tuple[str, str, int, bool]:
    """`line` up to its YAML comment, the quote still open at its end, and how
    many `[` or `{` collections are still open there.

    A `#` starts a comment at the start of the line or after whitespace, and
    only outside a single- or double-quoted scalar, so the `#3` of
    `['a.spec.ts (AC #3)', 'b.spec.ts']` cuts off neither the rest of its
    entry nor the entry after it. A quote opens a scalar only where one may
    start: at the start of the line, after a `- `, `? ` or `: ` indicator, or
    inside a `[` or `{` collection after its opening bracket or a `,`. So the
    `'` of a plain `it's`, or of a plain block entry's `(AC 2, 'til done)`,
    opens nothing. `quote` and `depth` are what the line before left open,
    since a quoted scalar or a collection may run over lines.
    """
    # whether a scalar may start here; inside a flow collection a line break
    # is only whitespace, so the line before decides it
    start = not quote and (start or depth == 0)
    i = 0
    while i < len(line):
        char = line[i]
        if quote:
            if char == "\\" and quote == '"':
                i += 1  # an escaped character, such as \"
            elif char == quote == "'" and line[i + 1:i + 2] == "'":
                i += 1  # '' is a quote inside a single-quoted scalar
            elif char == quote:
                quote = ""
        elif char == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i], "", depth, start
        elif char in "'\"" and start:
            quote, start = char, False
        elif char in "&!" and start:
            while i + 1 < len(line) and not line[i + 1].isspace():
                i += 1  # a node property: a node may still start after it
        elif not char.isspace():
            spaced = i + 1 == len(line) or line[i + 1].isspace()
            indicator = spaced and (char == ":" or (start and char in "-?"))
            opens = char in "[{" and (start or depth > 0)
            if opens:
                depth += 1
            elif char in "]}" and depth:
                depth -= 1
            start = opens or (char == "," and depth > 0) or indicator
        i += 1
    return line, quote, depth, start


def _listed_test_files(text: str) -> list[str] | None:
    """The acceptance-test paths the checklist's `generatedTestFiles` lists.

    None when the checklist has no frontmatter or its frontmatter has no such
    key. Raises ValueError, saying what is wrong, when the key is there but its
    value is not a list this reader can take apart: `- ` items on the lines
    under it, or a `[...]` list on one line or several. Comments are cut off
    as _strip_comment reads them, so a `#` in a quoted note keeps the rest of
    its line, and a line a quoted entry or an open `[` list runs onto, even at
    column 0, continues it. Entries go through _TEST_FILE, so a listed source file, a Rust
    test or a note in parentheses after a path is not read as an
    acceptance-test file.
    """
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].rstrip() != "---":
        return None
    end = next(
        (i for i in range(1, len(lines)) if lines[i].rstrip() in ("---", "...")),
        None,
    )
    if end is None:
        return None
    block = lines[1:end]
    keys = [i for i, line in enumerate(block) if _LISTED_KEY.match(line)]
    if not keys:
        return None
    if len(keys) > 1:
        raise ValueError("the key appears more than once")
    key_line, quote, depth, start = _strip_comment(block[keys[0]])
    inline = _LISTED_KEY.match(key_line).group(1).strip()
    items: list[str] = []
    for line in block[keys[0] + 1:]:
        carried, nested = quote, depth
        item, quote, depth, start = _strip_comment(line, quote, depth, start)
        item = item.strip()
        if not item:
            continue
        if carried and items:
            items[-1] += " " + item  # the quoted entry the line before left open
            continue
        if not line[0].isspace() and not nested and not item.startswith(("-", "]")):
            break  # the next key; a `- ` item, a `]` or a line in an open list may sit at column 0
        items.append(item)
    if inline or (items and items[0].startswith("[")):
        flow = " ".join([inline, *items]).strip()
        if not flow.startswith("["):
            raise ValueError("its value is not a list")
        if not flow.endswith("]"):
            raise ValueError("its `[` list is not closed by `]`")
        return _checklist_test_files(flow[1:-1])
    if any(not item.startswith("-") for item in items):
        raise ValueError("a line under it is not a `- ` item")
    return _checklist_test_files("\n".join(item[1:] for item in items))


def _repo_relative(raw: str, cwd: str | None) -> str:
    """Normalize a checklist entry to the repo-relative form `git show :` needs.

    Checklist entries may be `{project-root}`-prefixed or absolute; `git show :`
    accepts neither. Anything that still cannot be made repo-relative is passed
    through unchanged so the read fails loudly rather than being skipped.
    """
    text = raw.replace("\\", "/")
    if "{project-root}" in text:
        return text.split("{project-root}", 1)[1].lstrip("/")
    if text.startswith("./"):
        text = text[2:]
    if text.startswith("/") and cwd:
        try:
            return str(Path(text).relative_to(Path(cwd)))
        except ValueError:
            return text
    return text


def _staged_blob(path: str, cwd: str | None) -> tuple[bool, str]:
    """Return (readable, staged content) for one path via `git show :<path>`.

    `:<path>` addresses the index, i.e. exactly the bytes this commit would
    write. readable is False when the probe could not answer at all (git
    missing, timeout, path not in the index): the caller fails closed on it.
    """
    try:
        out = subprocess.run(
            ["git", "show", f":{path}"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        return False, ""
    if out.returncode != 0:
        return False, ""
    return True, out.stdout


def _unskip_gate(cwd: str | None, story: str | None) -> None:
    """Deny a commit whose staged acceptance tests still carry the skip marker.

    Scope, in order:
      - test-artifacts root unresolvable (env unset) -> out of scope, note only.
      - no story id -> nothing to look up.
      - no checklist for this story -> inert. That is the `--light` profile,
        where acceptance tests are not generated at all.
      - checklist present but unreadable -> deny (in scope, cannot verify).
      - `generatedTestFiles` present but not readable as a list -> deny.
      - checklist naming no acceptance-test file -> inert. Doc-only and refactor
        stories are legitimate and must not be blocked.
    The files are the JS/TS test paths `generatedTestFiles` lists, or, when it
    is absent or lists none, every such path the checklist's text names.
    Every enumerated file is read from the index whether or not this commit
    touched it: the checklist, not the diff, says what the story must deliver.
    """
    tests_root = _test_artifacts()
    if tests_root is None:
        _note(
            "Un-skip proof: ULTRACODE_TEST_ARTIFACTS is unset, so the staged "
            "acceptance-test check is out of scope for this commit and made no "
            "decision. Inject it on the guard's hook command (preflight step 5) "
            "to arm the check."
        )
        return
    if not story:
        return

    checklist = tests_root / f"atdd-checklist-{story}.md"
    if not checklist.is_file():
        return  # no acceptance tests for this story: nothing to prove
    try:
        text = checklist.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        _deny(
            "Un-skip proof: refusing `git commit` — the acceptance-test "
            f"checklist {checklist} exists but could not be read, so the staged "
            "acceptance tests cannot be verified un-skipped. Failing closed. "
            "Repair or regenerate the checklist, then commit."
        )

    try:
        listed = _listed_test_files(text)
    except ValueError as problem:
        _deny(
            "Un-skip proof: refusing `git commit` because the `generatedTestFiles` "
            f"list in the frontmatter of {checklist} cannot be read ({problem}), "
            "so the story's acceptance-test files cannot be enumerated. Failing "
            "closed. Rewrite it as a YAML list, one repo-relative path per "
            "`- '<path>'` line, in a prior, SEPARATE tool call, then commit."
        )
    source = (
        f"the generatedTestFiles list of {checklist.name}" if listed else checklist.name
    )
    entries = listed or _checklist_test_files(text)
    files = [_repo_relative(entry, cwd) for entry in entries]
    if not files:
        return  # checklist names no acceptance-test file (doc-only story)

    still_skipped: list[str] = []
    for rel in files:
        readable, blob = _staged_blob(rel, cwd)
        if not readable:
            _deny(
                "Un-skip proof: refusing `git commit` — `git show :"
                f"{rel}` failed, so the staged content of an acceptance-test "
                f"file named by {source} could not be read. Failing "
                "closed. Stage that file (`git add <path>`) in a prior, "
                "SEPARATE tool call, or fix the path the checklist names."
            )
        if _SKIP_TOKEN in blob:
            still_skipped.append(rel)
    if still_skipped:
        _deny(
            "Un-skip proof: refusing `git commit` — the staged content of "
            f"{', '.join(still_skipped)} still contains `{_SKIP_TOKEN}`, so this "
            "commit would capture a story whose acceptance tests are skipped "
            "rather than green. Un-skip every acceptance test the checklist "
            f"({checklist.name}) enumerates, drive them to green, restage those "
            "paths in a prior, SEPARATE tool call, then commit."
        )


# --- Cross-Session Recall gate ----------------------------------------------
# While a UCG run is active, nothing reaches claude-mem, and only the pinned
# recall scripts reach the local run store or change the latch. The run is
# signalled by a machine latch written at Stage 1 Ingest and removed at every
# terminal (Finalize, a preflight STOP, the headless envelope path) by
# `mem_recall.py unlatch`. Its presence arms this gate, not any env flag and
# not its colour: a present latch counts as live. The guard reads no clock and
# detects no dead run, so a latch a dead run left behind keeps denying until
# the next Stage 1 replaces it or the user deletes it by hand, and every deny
# it causes names it and tells the person how to clear it.

_MEM_STATE_FILENAME = ".mem-state.json"

# A claude-mem MCP call is one of two segment-exact forms:
#   plugin-install form: mcp__plugin_claude-mem_<server-seg>__<op>
#       the trailing '_' after 'plugin_claude-mem' blocks plugin_claude-memoir_*
#   bare-server form:    mcp__claude-mem__<op>  (also claude_mem; exact segment)
# Claude Code writes `_` in a tool name for any character of the server name
# outside letters, digits, `_` and `-` (_MCP_NAME_UNSAFE), so the plugin's
# server segment may hold a `_` (a server key `mem.search` or `mem_search`).
# Case-exact on purpose (real tool names are lowercase); missing/empty -> no match.
_CLAUDE_MEM_SERVER_NAME = r"(?:plugin_claude-mem_[A-Za-z0-9_-]+|claude[-_]mem)"
_CLAUDE_MEM_TOOL = re.compile(rf"^mcp__{_CLAUDE_MEM_SERVER_NAME}__.+$")
_MCP_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")


# The client's own MCP resource tools reach a server named in their `server`
# input rather than in the tool name. That input is the server's own name,
# `plugin:claude-mem:<server>` for the plugin install, so it is matched as the
# tool name spells it: a server whose tools the form above denies is
# claude-mem's. A listing that names no server lists every server's resources,
# claude-mem's included.
_MCP_RESOURCE_TOOLS = frozenset(
    {"ListMcpResourcesTool", "ReadMcpResourceTool", "ReadMcpResourceDirTool"}
)
_MCP_LIST_RESOURCES = "ListMcpResourcesTool"
_CLAUDE_MEM_SERVER = re.compile(rf"^{_CLAUDE_MEM_SERVER_NAME}$")


def _mem_state_path(impl: Path | None) -> Path | None:
    return (impl / _MEM_STATE_FILENAME) if impl is not None else None


def _is_claude_mem_tool(tool_name: object) -> bool:
    """True iff tool_name is a claude-mem MCP call (segment-exact dual form)."""
    if not isinstance(tool_name, str) or not tool_name:
        return False
    return _CLAUDE_MEM_TOOL.match(tool_name) is not None


def _claude_mem_resource_server(tool_name: object, tool_input: dict) -> str | None:
    """The claude-mem server an MCP resource read or listing names, or None."""
    if tool_name not in _MCP_RESOURCE_TOOLS:
        return None
    server = tool_input.get("server")
    if isinstance(server, str) and _CLAUDE_MEM_SERVER.match(_MCP_NAME_UNSAFE.sub("_", server)):
        return server
    return None


# --- The latch, read the way lib/mem_common.py reads it ----------------------
# This hook imports nothing from lib/ (module docstring), so it keeps its own
# copy of mem_common.read_state() and mem_common.latch_view(). The two must
# read one latch file the same way: the parity test in test_guard_pretooluse.py
# drives both over one corpus of latch files, resolved store path included, so
# a change to either side reds until it is made to both.

_LATCH_V2 = 2
_STORE_BACKEND = "jsonl"

# A real latch is a few hundred bytes. The latch is opened without blocking (a
# FIFO there would otherwise hold this read until the hook timed out) and a
# latch past this size reads as unreadable. Only a hostile file differs from
# mem_common.read_state() here, which would block or read on.
_LATCH_READ_CAP = 1 << 20


def _latch_present(state_path: Path) -> bool:
    """True when anything sits at the latch path, or when that cannot be told.

    Only a clean "no such file" reads as absent (no active run). Any other
    failure to look may hide a latch, so it reads as present: fail closed. A
    present latch that cannot be read or parsed still arms the claude-mem deny.
    """
    try:
        os.lstat(state_path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except (OSError, ValueError):
        return True
    return True


def _read_latch(state_path: Path) -> dict | None:
    """mem_common.read_state(): the latch object, or None. Never raises.

    Missing, unreadable, blank, unparseable and non-object latches all read as
    None. It also swallows the errors a hostile path can raise (a NUL in the
    path, a folder), opens the latch without blocking and reads at most
    _LATCH_READ_CAP bytes: an exception or a hang here would end with no
    decision at all.
    """
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(state_path, flags)
    except (OSError, ValueError):
        return None
    try:
        chunks: list[bytes] = []
        size = 0
        while size <= _LATCH_READ_CAP:
            chunk = os.read(fd, _LATCH_READ_CAP + 1 - size)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
    except OSError:
        return None
    finally:
        os.close(fd)
    if size > _LATCH_READ_CAP:
        return None
    text = b"".join(chunks).decode("utf-8", errors="replace")
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _is_int(value: object) -> bool:
    """True for a real int (bool is an int subclass and is not one here)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _latch_store_path(value: object) -> Path | None:
    """mem_common._latch_store_path(): a latch's `store` as an absolute path.

    Taken as written (the latch holds the resolved root, which may carry a
    `$` or braces of its own); only a leading `~` is expanded. Anything that is
    not then absolute, a string holding a NUL, or a non-string reads as None.
    """
    if not isinstance(value, str) or not value or "\0" in value:
        return None
    try:
        path = Path(value).expanduser() if value.startswith("~") else Path(value)
        if not path.is_absolute():
            return None
        return Path(os.path.abspath(path))
    except (RuntimeError, ValueError):
        return None


def _latch_view(state: object) -> dict:
    """mem_common.latch_view(): how a latch reads, version and colour.

    {"latch_version": int|None, "store_ok": bool, "store": str|None,
     "run_id": object, "recall": object}. `store` is set for a v2 latch whose
    `store` is an absolute path, whatever its colour; `store_ok` is green only
    for a v2 latch with store_ok literally true, the jsonl backend, recall on
    and a store. A v1 latch, any other version and a non-object read as red
    with no store.
    """
    if not isinstance(state, dict):
        return {
            "latch_version": None,
            "store_ok": False,
            "store": None,
            "run_id": None,
            "recall": None,
        }
    version = state.get("latch_version")
    version = version if _is_int(version) else None
    store: Path | None = None
    green = False
    if version == _LATCH_V2:
        store = _latch_store_path(state.get("store"))
        green = (
            state.get("store_ok") is True
            and state.get("backend") == _STORE_BACKEND
            and state.get("recall") == "on"
            and store is not None
        )
    return {
        "latch_version": version,
        "store_ok": green,
        "store": None if store is None else str(store),
        "run_id": state.get("run_id"),
        "recall": state.get("recall"),
    }


# --- Store-path rule ----------------------------------------------------------
# A latch naming a usable store arms one more deny: a model tool call that
# names the store path. Each file tool is read on the keys it names a path in;
# `file_path` and `path` are read for every one of them, as the gate read them
# before the store existed. A relative `pattern` or `glob` is taken against the
# tool's own `path` as well as against the cwd.
#
# "Names" is read wide, and every widening is on the deny side: the store root
# found anywhere inside a word (`-o<store>`, `@<store>`, `file://<store>`), a
# word or a piece of one that resolves under it as written or with its
# symlinks resolved, a brace expansion or a glob that can match it, and the
# home and working-folder spellings a shell expands. The same matching finds a
# path, glob or brace expansion that reaches claude-mem's own folder under a
# home, beside the literal `.claude-mem` check.

_PATH_KEYS = ("file_path", "path")
_TOOL_EXTRA_KEYS = {
    "Read": (),
    "Write": (),
    "Edit": (),
    "MultiEdit": (),
    "NotebookEdit": ("notebook_path",),
    "Glob": ("pattern",),
    "Grep": ("glob",),
}
_PATTERN_KEYS = frozenset({"pattern", "glob"})

# The three separator sets _command_write_verbs splits a command under, kept
# equal to them by a test. Each one exposes a segment the others can leave
# inside an exempt-looking one (a newline, a lone `&`), so a segment that names
# the store is looked for under all three.
_STORE_SEPARATOR_SETS = (
    r"&&|\|\||;|\|",
    r"&&|\|\||;|\||\n|\r",
    r"&&|\|\||;|\||&|\n|\r",
)

# $HOME, ${HOME} and %USERPROFILE%, and the same three spellings of the other
# variable: every one is read as each home folder this process knows of, so a
# spelling the shell expands one way is not missed for being read another. A
# `${HOME<op>...}` form (`${HOME:-x}`, `${HOME%/}`) reads as the home too.
_HOME_VAR = re.compile(
    r"\$\{(?:HOME|USERPROFILE)(?:[^}A-Za-z0-9_][^}]*)?\}"
    r"|\$(?:HOME|USERPROFILE)(?![A-Za-z0-9_])"
    r"|%(?:HOME|USERPROFILE)%",
    re.IGNORECASE,
)

# $PWD and ${PWD...}, read as the event's cwd, as a leading `~+` is, and the
# `$(pwd)` and backtick `pwd` substitutions that print it.
_PWD_VAR = re.compile(
    r"\$\{PWD(?:[^}A-Za-z0-9_][^}]*)?\}|\$PWD(?![A-Za-z0-9_])"
    r"|\$\(\s*pwd(?:\s+-[LP])?\s*\)|`\s*pwd(?:\s+-[LP])?\s*`"
)

# A bash extglob group, ?(...) *(...) +(...) @(...) !(...), read as a `*`
# standing for whatever it matches: a wider match, never a narrower one.
_EXTGLOB = re.compile(r"[?*+@!]\([^()]*\)")

# Bash ANSI-C quoting, $'...', whose escapes can spell any character. Such a
# word is read decoded as well, so `$'\x2f'` counts as `/`.
_ANSI_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.DOTALL)
_ANSI_C_ESCAPE = re.compile(
    r"\\(x[0-9A-Fa-f]{1,2}|u[0-9A-Fa-f]{1,4}|U[0-9A-Fa-f]{1,8}|[0-7]{1,3}|c.|.)",
    re.DOTALL,
)
_ANSI_C_SIMPLE = {
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "E": "\x1b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
}

# Quotes and backslashes, taken out before the literal `.claude-mem` check so
# `.claude-m'e'm` and `.claude-m\em` still read as the folder.
_QUOTING = re.compile(r"""["'\\]""")

# What ends a path inside one shell word: whitespace, quotes, `=` (the
# `--opt=<path>` and `FOO=<path>` forms), redirection and control operators,
# and the paren, brace and comma of substitutions, brace expansion and lists.
_PATH_BREAK = re.compile(r"""[\s=<>|&;(){},'"`]+""")

# A character that, right after the store root inside a longer text, would
# continue its last folder name (`recall2` is not `recall`). Anything else
# there (the end, a separator, a quote, an operator, a glob or brace
# character, `:` or `=`) ends the name, so the text names the store.
_ROOT_CONTINUES = re.compile(r"""[^\s/\\'"`;|&<>(){}\[\],=:*?!$]""")

# Glob characters, and the cap on how many words one brace expansion yields.
# Past the cap, or in a word longer than _BRACE_WORD_CAP, a brace group is read
# as a `*` standing for whatever it expands to: a wider match, never a
# narrower one, and a bounded cost.
_GLOB_CHARS = re.compile(r"[*?\[]")
_BRACE_LIMIT = 64
_BRACE_STEPS = 256
_BRACE_WORD_CAP = 1024
_BRACE_SEQUENCE = re.compile(r"^(-?\d+|[A-Za-z])\.\.(-?\d+|[A-Za-z])(?:\.\.(-?\d+))?$")

# The scripts the exemption admits, under <skill-root>/scripts/.
_RECALL_SCRIPTS = ("mem_recall.py", "mem_observation.py")

# The leading command of an exempt segment is `uv run` or python, matched on
# the bare word: an interpreter given by path (`./python`) is not exempt.
_EXEMPT_PYTHON = re.compile(r"^python(?:3(?:\.\d+)?)?$")

# Any of these anywhere in a segment refuses the exemption. Every redirection
# form (`>`, `>>`, `<`, `2>`, `&>`, `>|`, `&>>`, `<<<`, `>&2`, and `<(...)` and
# `>(...)`) carries a `<` or a `>`; command substitution is `$(` or a backtick.
_EXEMPT_REFUSED = ("<", ">", "`", "$(")

# A leading assignment that changes which interpreter, which modules, which
# libraries, which configuration or which home folder the exempt call would
# use refuses the exemption.
_EXEMPT_UNSAFE_ASSIGNMENT = re.compile(
    r"^[({]*(?:PATH|VIRTUAL_ENV|CONDA_\w*|PYTHON\w*|UV_\w*|LD_\w*|DYLD_\w*"
    r"|HOME|USERPROFILE|APPDATA|LOCALAPPDATA|XDG_\w*|GIT_\w*)="
)

# A directory change anywhere in the command moves where a relative script
# path lands when the command runs, so it refuses a relative operand.
_CHDIR = re.compile(r"""(?:^|[\s;&|(){}'"`])(?:cd|pushd|popd)(?=$|[\s;&|(){}'"`])""")

# What can change, for the rest of a command, what a later `uv` or `python`
# resolves to or the environment it runs with: these builtins at the head of
# any segment, these keywords ahead of it (a loop or coprocess variable, a
# function), a segment of assignments only (`PATH=/x; ...`), a function
# definition, `printf -v`, and arithmetic or a `${VAR:=...}` default, which
# assign as well. Any one of them refuses the exemption to every segment of
# that command; the leading assignments of an exempt segment itself are
# checked against _EXEMPT_UNSAFE_ASSIGNMENT instead.
_REBINDING_WORDS = frozenset(
    {
        ".",
        "source",
        "export",
        "declare",
        "typeset",
        "readonly",
        "local",
        "unset",
        "alias",
        "hash",
        "enable",
        "eval",
        "shopt",
        "builtin",
        "trap",
        "read",
        "mapfile",
        "readarray",
        "let",
        "getopts",
    }
)
_REBINDING_KEYWORDS = frozenset({"for", "select", "function", "coproc"})
# Words that run what follows them in this shell, so a rebinding builtin behind
# them rebinds as it does at the head (`command export PATH=...`), and so does
# an assignment behind the `time` keyword (`time PATH=...`). `command -v` and
# `-V` only look a name up and run nothing.
_CURRENT_SHELL_WRAPPERS = frozenset({"command", "time"})
_MAX_WRAPPERS = 32
# Rebinding shapes the word scan in _command_rebinds cannot reach, because it
# splits a command at blanks and reads only each segment's head. Each changes
# command lookup or the environment where a bare `NAME=` head does not sit:
#   - `((` and `$[` open arithmetic (a `$((` holds `((`), which can assign;
#   - the hash and alias arrays rebind a command name by entry. Any mention of
#     them counts, even one that only reads them (`${#BASH_CMDS[@]}`, a search
#     for the word): a command whose name the text does not spell can write an
#     entry (`"$(printf %s r e a d)" 'BASH_CMDS[cat]' <<< /bin/rm` runs `read`),
#     and then the array's name is all the text shows of the write.
_REBINDING_TEXT = re.compile(r"\(\(|\$\[|(?<![A-Za-z0-9_])BASH_(?:CMDS|ALIASES)(?![A-Za-z0-9_])")
# A subscript may nest (`PATH[a[0]]=x`), and bash reads one with blanks in it
# (`PATH[ 0 ]=x`) as a single assignment word, which shlex splits at the blanks:
# _command_rebinds also matches a head that opens a subscript against the
# segment's words joined again.
_ANY_ASSIGNMENT = re.compile(r"^[({]*[A-Za-z_][A-Za-z0-9_]*(?:\[.*\])?\+?=")
_OPEN_SUBSCRIPT_HEAD = re.compile(r"^[({]*[A-Za-z_][A-Za-z0-9_]*\[")

# A mutation: a `=` that is not a comparison (`==`, `!=`, `<=`, `>=`, `=~`), a
# compound assignment (`+= -= *= /= %= &= ^= |= <<= >>=`), or `++`/`--`. Where
# bash evaluates arithmetic, it assigns.
_MUTATION = r"(?:(?<![=!<>])=(?![=~])|\+=|-=|\*=|/=|%=|\^=|\|=|&=|<<=|>>=|\+\+|--)"
# A mutation in arithmetic: after a name or a subscript's `]`, blanks allowed
# between (`PATH = 1`, `BASH_CMDS[cat]++`), or a `++`/`--` before a name.
_ARITHMETIC_MUTATION = re.compile(
    rf"(?:(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*|\])[ \t]*(?P<op>{_MUTATION})"
    r"|(?P<pre>\+\+|--)[ \t]*[A-Za-z_]"
)
# A mutation glued to a name or a subscript's `]`, the only kind read in a
# `[[ ]]` test: there a lone `=` compares strings, and `--help` is a word.
_GLUED_MUTATION = re.compile(rf"(?:(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*|\])(?P<op>{_MUTATION})")

# Where bash evaluates arithmetic outside `((` and `$[`, so a mutation there
# assigns (_arithmetic_rebinds):
#   - the offset and length of a `${...}` substring (`${PWD:PATH=1}`);
#   - a subscript inside a `${...}` (`${a[PATH=1]}`, `${a[BASH_CMDS[cat]++]}`),
#     in a word that assigns to it (`a[PATH=1]=x`), and in a name that `-v` or
#     `-R` reads in a `test`, `[` or `[[` (`test -v 'a[PATH=1]'`);
#   - a `[[ ]]` test that compares numbers (`-eq`, `-ne`, `-lt`, `-le`, `-gt`,
#     `-ge`), whose operands are arithmetic (`[[ 1 -eq PATH=1 ]]`), with the
#     subscripts inside it.
# A bracket anywhere else is no subscript bash evaluates (`grep 'a[b=c]'` hands
# grep a character class), so a mutation in it does not count. A `${...}` also
# assigns by its operator: a `=` or `:=` right after the name and any subscript
# (`${x=1}`, `${x:=1}`, `${BASH_CMDS[cat]:=/bin/rm}`, `${!x:=1}`); a `=` later in
# it (`${PWD#*=}`, `${line%=*}`, `${x:-a=b}`, `${x/=/-}`) is only text. Brackets
# and braces are paired quote-blind in one pass and every span is found from
# them, so the reading stays linear in the command's length. In order below: a
# `${` with its `!` or `#` and its parameter, a `NAME[` that opens a subscript,
# `[[` and `]]` where they stand as words, `test` or `[` as a word, a `-v` or
# `-R` operand, and the text between two of `;`, `&`, `|` and a newline.
_PARAMETER =re.compile(r"\$\{([!#]?)([A-Za-z_][A-Za-z0-9_]*|[0-9]+|[@*#?$!-])")
_SUBSCRIPT = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*\[")
_TEST_BOUND = re.compile(r"(?<![^\s;&|(){}!])\[\[(?=\s)|(?<=\s)\]\](?![^\s;&|()])")
_TEST_COMMAND = re.compile(r"""(?<![^\s;&|(){}!'"])(?:test|\[)(?=[\s'"])""")
_NAME_OPERAND = re.compile(r"""(?<![^\s!('"])-[vR](?=[\s'"])""")
_ARITH_COMPARISON = re.compile(r"(?<![A-Za-z0-9_])-(?:eq|ne|lt|le|gt|ge)(?![A-Za-z0-9_])")
_SIMPLE_PIECE = re.compile(r"[^;&|\n]+")
# An assignment whose value OPENS a command substitution, for a name that
# changes command lookup or the interpreter (the names _EXEMPT_UNSAFE_ASSIGNMENT
# lists). shlex splits the substitution at its blanks, so _strip_assignments
# would eat `PATH=$(printf` and read the rest as a command; this keeps the whole
# assignment a rebinding (`PATH=$(printf %s /x):$PATH`). The opener must sit
# right after the `=`, so a markdown code span such as `` `PYTHON_COLORS=0` ``
# in a heredoc body is not read as one.
_VALUE_SUBSTITUTION = re.compile(
    r"(?:^|[\s;&|(){}])(?:PATH|VIRTUAL_ENV|CONDA_\w*|PYTHON\w*|UV_\w*|LD_\w*"
    r"|DYLD_\w*|HOME|USERPROFILE|APPDATA|LOCALAPPDATA|XDG_\w*|GIT_\w*)"
    r"(?:\[[^][]*\])?\+?=(?:\$\(|`)"
)


def _closers(text: str, opener: str, closer: str) -> dict[int, int]:
    """Where each `opener` in the text closes, paired quote-blind the way
    nested brackets pair; one that never closes runs to the text's end."""
    closes: dict[int, int] = {}
    unclosed: list[int] = []
    for match in re.finditer(f"[{re.escape(opener)}{re.escape(closer)}]", text):
        if match.group() == opener:
            unclosed.append(match.start())
        elif unclosed:
            closes[unclosed.pop()] = match.start()
    for index in unclosed:
        closes[index] = len(text)
    return closes


def _mutation_within(command: str, pattern: re.Pattern[str], spans: list[tuple[int, int]]) -> bool:
    """True when a mutation `pattern` finds has its operator inside one of the
    (start, end) spans."""
    if not spans:
        return False
    starts: list[int] = []
    ends: list[int] = []
    for start, end in sorted(spans):
        if starts and start <= ends[-1]:
            ends[-1] = max(ends[-1], end)
        else:
            starts.append(start)
            ends.append(end)
    for match in pattern.finditer(command):
        at = match.start("op") if match.group("op") is not None else match.start("pre")
        index = bisect.bisect_right(starts, at) - 1
        if index >= 0 and at < ends[index]:
            return True
    return False


def _arithmetic_rebinds(command: str) -> bool:
    """True when a `${...}` assigns by its operator, or a mutation stands where
    bash evaluates arithmetic outside `((` and `$[` (see the comment above)."""
    brackets = _closers(command, "[", "]") if "[" in command else {}
    braces: dict[int, int] | None = None
    spaced: list[tuple[int, int]] = []  # blanks may stand around the operator
    glued: list[tuple[int, int]] = []  # `[[ ]]` number tests: glued to a name

    def subscripts(start: int, end: int) -> None:
        for match in _SUBSCRIPT.finditer(command, start, end):
            spaced.append((match.end(), brackets[match.end() - 1]))

    for match in _PARAMETER.finditer(command):
        after = match.end()
        if command.startswith("[", after):
            spaced.append((after + 1, brackets[after]))
            after = brackets[after] + 1
        if command.startswith(("=", ":="), after):
            return True
        if command.startswith(":", after) and command[after + 1 : after + 2] not in ("-", "=", "+", "?"):
            if braces is None:
                braces = _closers(command, "{", "}")
            spaced.append((after + 1, braces[match.start() + 1]))
    for match in _SUBSCRIPT.finditer(command):
        close = brackets[match.end() - 1]
        if command.startswith(("=", "+="), close + 1):
            spaced.append((match.end(), close))
    tests: list[tuple[int, int]] = []
    opened: int | None = None
    for match in _TEST_BOUND.finditer(command):
        if match.group() == "[[":
            if opened is None:
                opened = match.end()
        elif opened is not None:
            tests.append((opened, match.start()))
            opened = None
    if opened is not None:
        tests.append((opened, len(command)))
    for start, end in tests:
        numbers = _ARITH_COMPARISON.search(command, start, end) is not None
        if numbers:
            glued.append((start, end))
        if numbers or _NAME_OPERAND.search(command, start, end):
            subscripts(start, end)
    for piece in _SIMPLE_PIECE.finditer(command):
        start, end = piece.span()
        if _TEST_COMMAND.search(command, start, end) and _NAME_OPERAND.search(command, start, end):
            subscripts(start, end)
    return _mutation_within(command, _ARITHMETIC_MUTATION, spaced) or _mutation_within(
        command, _GLUED_MUTATION, glued
    )


def _rebinding_text(command: str) -> bool:
    """The rebinding shapes the per-segment word scan in _command_rebinds
    cannot reach (see _REBINDING_TEXT): `((` or `$[`, any mention of the hash
    or alias arrays, a `${...}` that assigns or a mutation where bash evaluates
    arithmetic (_arithmetic_rebinds), and an assignment whose value opens a
    substitution. Read quote-blind, like the word scan and the separator
    split, and in time linear in the command's length."""
    if _REBINDING_TEXT.search(command) or _VALUE_SUBSTITUTION.search(command):
        return True
    return _arithmetic_rebinds(command)


# How much of a denied segment its deny reason quotes.
_SEGMENT_SHOWN = 160

# macOS file systems ignore case and Unicode normalization by default, so on
# macOS the deny side compares paths NFC-normalized and casefolded.
_FOLD_CASE_AND_FORM = sys.platform == "darwin"


def _scripts_dir() -> str:
    """<skill-root>/scripts, from this file's own path (scripts/hooks/<this>)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pinned_paths() -> list[str]:
    """The two recall scripts the exemption admits, as absolute paths.

    The skill root comes from this file's location, not from an env var: the
    guard ships in <skill-root>/scripts/hooks/ beside the scripts it pins, its
    own path cannot be absent or set by a tool call, and an env var would mean
    a new value on the hook command that preflight writes, which an older
    arming lacks. Both the path this file runs from and its symlink-resolved
    form count, so a skill reached through a symlinked folder still matches.
    """
    here = os.path.abspath(__file__)
    pinned: list[str] = []
    for hook in (here, os.path.realpath(here)):
        scripts = os.path.dirname(os.path.dirname(hook))
        for name in _RECALL_SCRIPTS:
            path = os.path.join(scripts, name)
            if path not in pinned:
                pinned.append(path)
    return pinned


def _pinned_scripts() -> frozenset[str]:
    """The pinned paths as written, folded by os.path.normcase only."""
    return frozenset(os.path.normcase(path) for path in _pinned_paths())


def _pinned_real_scripts() -> frozenset[str]:
    """The files the pinned paths lead to, symlinks resolved, normcased."""
    return frozenset(os.path.normcase(_real(path)) for path in _pinned_paths())


def _home_dirs() -> list[str]:
    """Every home folder a spelling can mean: HOME, USERPROFILE and `~`."""
    homes: list[str] = []
    for value in (
        os.environ.get("HOME"),
        os.environ.get("USERPROFILE"),
        os.path.expanduser("~"),
    ):
        if value and not value.startswith("~") and value not in homes:
            homes.append(value)
    return homes


def _fold(path: str) -> str:
    """A path or text as the deny side compares it.

    os.path.normcase (case and separators on Windows), and on macOS, whose
    file systems ignore case and Unicode normalization by default, NFC and
    casefolded too. Never used to grant the exemption, where a wider match
    would let another file through.
    """
    folded = os.path.normcase(path)
    if _FOLD_CASE_AND_FORM:
        folded = unicodedata.normalize("NFC", folded).casefold()
    return folded


@functools.lru_cache(maxsize=None)
def _real(path: str) -> str:
    """os.path.realpath, memoized; the path unchanged when it cannot resolve."""
    try:
        return os.path.realpath(path)
    except (OSError, ValueError, RuntimeError):
        return path


def _roots(path: str) -> tuple[str, ...]:
    """A folder as written and with its symlinks resolved, both folded."""
    try:
        absolute = os.path.abspath(path)
    except (TypeError, ValueError):
        return (_fold(path),)
    forms = (_fold(absolute), _fold(_real(absolute)))
    return forms if forms[0] != forms[1] else forms[:1]


def _claude_mem_roots(homes: list[str]) -> tuple[str, ...]:
    """claude-mem's own folder under each home, written and resolved, folded."""
    roots: list[str] = []
    for home in homes:
        for root in _roots(os.path.join(home, ".claude-mem")):
            if root not in roots:
                roots.append(root)
    return tuple(roots)


def _ansi_c_char(match: re.Match) -> str:
    body = match.group(1)
    try:
        if body[0] in "xuU" and len(body) > 1:
            return chr(int(body[1:], 16))
        if body[0] in "01234567":
            return chr(int(body, 8) & 0xFF)
    except (ValueError, OverflowError):
        return ""
    if body[0] == "c" and len(body) == 2:
        return chr(ord(body[1]) & 0x1F)
    return _ANSI_C_SIMPLE.get(body, body)


def _decode_ansi_c(text: str) -> str:
    """Each $'...' word decoded and quoted again, so shlex reads it as one word."""
    return _ANSI_C.sub(
        lambda match: shlex.quote(_ANSI_C_ESCAPE.sub(_ansi_c_char, match.group(1))),
        text,
    )


def _mentions_claude_mem(value: str) -> bool:
    """True when `.claude-mem` sits anywhere in the value, read with its quotes
    and backslashes taken out and its $'...' words decoded."""
    target = _fold(".claude-mem")
    texts = [value, _decode_ansi_c(value)] if "$'" in value else [value]
    return any(target in _fold(_QUOTING.sub("", text)) for text in texts)


def _spellings(text: str, homes: list[str], cwd: str) -> list[str]:
    """The text as written, plus copies with each extglob group read as a `*`,
    with $PWD (or `$(pwd)`) read as the cwd, and with each home variable
    spelling read as each home folder, in every combination."""
    out = [text]
    if _EXTGLOB.search(text):
        out.append(_EXTGLOB.sub("*", text))
    if _PWD_VAR.search(text):
        out.extend([_PWD_VAR.sub(lambda _match: cwd, variant) for variant in list(out)])
    if _HOME_VAR.search(text):
        for variant in list(out):
            for home in homes:
                out.append(_HOME_VAR.sub(lambda _match, home=home: home, variant))
    return out


def _brace_sequence(body: str) -> list[str] | None:
    """The words of a `{a..b}` or `{a..b..step}` sequence, or None."""
    match = _BRACE_SEQUENCE.match(body)
    if not match:
        return None
    first, last, step_text = match.groups()
    step = abs(int(step_text)) if step_text else 1
    step = step or 1
    numeric = [part.lstrip("-").isdigit() for part in (first, last)]
    if all(numeric):
        start, end = int(first), int(last)
        to_text = str
    elif not any(numeric):
        start, end = ord(first), ord(last)
        to_text = chr
    else:
        return None
    count = abs(end - start) // step + 1
    if count > _BRACE_LIMIT:
        return ["*"]
    direction = 1 if end >= start else -1
    return [to_text(start + direction * step * index) for index in range(count)]


def _brace_group(word: str) -> tuple[int, int, list[str]] | None:
    """The leftmost brace expansion in a word: (open, close, alternatives).

    A group is a `{...}` holding a comma of its own, or a `{a..b}` sequence;
    other braces are literal, as in bash. Quoting is not tracked, so a quoted
    group expands too: a wider match, never a narrower one. One pass.
    """
    stack: list[tuple[int, list[int]]] = []
    best: tuple[int, int, list[str]] | None = None
    for pos, char in enumerate(word):
        if char == "{":
            stack.append((pos, []))
        elif char == "," and stack:
            stack[-1][1].append(pos)
        elif char == "}" and stack:
            start, commas = stack.pop()
            if best is not None and best[0] < start:
                continue
            if commas:
                edges = [start, *commas, pos]
                alternatives = [word[a + 1 : b] for a, b in zip(edges, edges[1:])]
            else:
                alternatives = _brace_sequence(word[start + 1 : pos])
            if alternatives is not None:
                best = (start, pos, alternatives)
    return best


def _brace_flatten(word: str) -> str:
    """Every outermost brace group as one `*`, in one pass."""
    closes: dict[int, int] = {}
    stack: list[int] = []
    for pos, char in enumerate(word):
        if char == "{":
            stack.append(pos)
        elif char == "}" and stack:
            closes[stack.pop()] = pos
    out: list[str] = []
    pos = 0
    while pos < len(word):
        end = closes.get(pos)
        if end is None:
            out.append(word[pos])
            pos += 1
        else:
            out.append("*")
            pos = end + 1
    return "".join(out)


def _brace_variants(word: str) -> list[str]:
    """Every word a brace expansion of `word` yields, within the caps."""
    if "{" not in word or "}" not in word:
        return [word]
    if len(word) > _BRACE_WORD_CAP:
        return [_brace_flatten(word)]
    done: list[str] = []
    pending = [word]
    steps = 0
    while pending:
        current = pending.pop()
        group = _brace_group(current)
        if group is None:
            done.append(current)
            continue
        steps += 1
        start, end, alternatives = group
        if steps > _BRACE_STEPS or len(done) + len(pending) + len(alternatives) > _BRACE_LIMIT:
            done.append(_brace_flatten(current))
            continue
        pending.extend(current[:start] + alt + current[end + 1 :] for alt in alternatives)
    return done


def _holds_root(folded: str, root: str) -> bool:
    """True when a root sits anywhere in the (folded) text and its last folder
    name ends there: the `-o<store>`, `@<store>`, `file://<store>`,
    `host:<store>`, `//<store>` and `/proc/self/root<store>` forms."""
    if root.endswith(os.sep):  # a file-system root
        return root in folded
    start = folded.find(root)
    while start != -1:
        end = start + len(root)
        if end == len(folded) or not _ROOT_CONTINUES.match(folded[end]):
            return True
        start = folded.find(root, start + 1)
    return False


def _components(path: str) -> list[str]:
    return [part for part in path.split(os.sep) if part]


def _under(path: str, root: str) -> bool:
    """True when `path` is the root, lies under it, or is a glob that can match
    it or a path under it (both folded). A `**` above the root's depth is a
    search from an ancestor, the accepted residual, so it is not a match."""
    if path == root:
        return True
    if path.startswith(root if root.endswith(os.sep) else root + os.sep):
        return True
    if not _GLOB_CHARS.search(path):
        return False
    pattern, names = _components(path), _components(root)
    if len(pattern) < len(names):
        return False
    for part, name in zip(pattern, names):
        if part == "**" or not fnmatch.fnmatchcase(name, part):
            return False
    return True


def _pathlike(piece: str) -> bool:
    """A piece of a word that reads as a path: `~`, `.` or a drive in front, or
    a separator in it. A bare word is left to the whole-word check, so a word
    of a commit message that equals a relative store name is not a path."""
    if not piece:
        return False
    if piece[0] in "~." or "/" in piece or os.sep in piece:
        return True
    return bool(os.path.splitdrive(piece)[0])


def _abs_forms(candidate: str, base: str, homes: list[str], cwd: str) -> list[str]:
    """Every absolute path a candidate can mean, as written and with symlinks
    resolved, folded.

    A leading `~` is read as each home folder and `~+` as the cwd; a relative
    candidate is taken against `base`. The resolved form also collapses the
    POSIX `//` prefix that abspath keeps.
    """
    forms = [candidate]
    if candidate.startswith("~"):
        rest = candidate[1:]
        if rest[:1] == "+" and (len(rest) == 1 or rest[1] in "/\\"):
            forms = [cwd + rest[1:]]
        elif not rest or rest[0] in "/\\":
            forms = [home + rest for home in homes]
        try:
            forms.append(os.path.expanduser(candidate))
        except (KeyError, ValueError):
            pass
    out: list[str] = []
    for form in forms:
        try:
            path = os.path.abspath(form if os.path.isabs(form) else os.path.join(base, form))
        except (TypeError, ValueError):
            continue
        out.append(_fold(path))
        out.append(_fold(_real(path)))
    return out


def _names_store(
    text: str,
    roots: tuple[str, ...],
    bases: list[str],
    homes: list[str],
    cwd: str,
    *,
    whole: bool,
) -> bool:
    """True when the text names a root: holding it anywhere, as a whole
    (`whole`), or through any path-like piece of it, in any home or cwd
    spelling and any brace expansion, against any base."""
    for spelling in _spellings(text, homes, cwd):
        for variant in _brace_variants(spelling):
            folded = _fold(variant)
            if any(_holds_root(folded, root) for root in roots):
                return True
            candidates = [variant] if whole else []
            candidates.extend(p for p in _PATH_BREAK.split(variant) if _pathlike(p))
            for candidate in candidates:
                for base in bases:
                    forms = _abs_forms(candidate, base, homes, cwd)
                    if any(_under(path, root) for path in forms for root in roots):
                        return True
    return False


@functools.lru_cache(maxsize=None)
def _word_names(
    word: str, roots: tuple[str, ...], cwd: str, homes: tuple[str, ...], whole: bool
) -> bool:
    """_names_store for one shell word or raw chunk against the cwd, memoized:
    a long command repeats its words across segments and separator sets."""
    return _names_store(word, roots, [cwd], list(homes), cwd, whole=whole)


@functools.lru_cache(maxsize=None)
def _words(text: str) -> tuple[str, ...]:
    """The shell words of a text, or none when its quoting does not parse."""
    try:
        return tuple(_tokenize(text))
    except ValueError:
        return ()


@functools.lru_cache(maxsize=None)
def _bash_names(segment: str, roots: tuple[str, ...], cwd: str, homes: tuple[str, ...]) -> bool:
    """True when one shell segment names a root.

    The whole text is searched for a root; each shell word counts whole and by
    its pieces; each whitespace-separated chunk of the raw text counts by its
    pieces too, since it keeps what shlex drops (an unquoted Windows backslash
    path) and still reads a segment whose quoting does not parse. A segment
    with a $'...' word is read decoded as well.
    """
    texts = [segment, _decode_ansi_c(segment)] if "$'" in segment else [segment]
    for text in texts:
        for spelling in _spellings(text, list(homes), cwd):
            folded = _fold(spelling)
            if any(_holds_root(folded, root) for root in roots):
                return True
        if any(_word_names(word, roots, cwd, homes, True) for word in _words(text)):
            return True
        if any(_word_names(chunk, roots, cwd, homes, False) for chunk in text.split()):
            return True
    return False


def _exempt_operand(segment: str) -> str | None:
    """The script operand of a segment shaped like an exempt call, or None.

    After the leading assignment, keyword and group-opener strip, the segment
    must lead with `uv run` or a python and name the script right after it:
    an option first (`uv run --with x`, `python -c ...`) is not exempt, so no
    payload can sit ahead of the pinned path. A wrapper (`env`, `sudo`,
    `bash -c`) leads with another word and is never exempt.
    """
    if any(marker in segment for marker in _EXEMPT_REFUSED):
        return None
    try:
        words = _tokenize(segment)
    except ValueError:
        return None
    rest = _strip_leading_noise(words)
    if any(_EXEMPT_UNSAFE_ASSIGNMENT.match(w) for w in words[: len(words) - len(rest)]):
        return None
    if len(rest) >= 3 and rest[0] == "uv" and rest[1] == "run":
        return rest[2]
    if len(rest) >= 2 and _EXEMPT_PYTHON.match(rest[0]):
        return rest[1]
    return None


@functools.lru_cache(maxsize=64)
def _command_rebinds(command: str) -> bool:
    """True when some segment of the command can change what a later `uv` or
    `python` resolves to, or the environment it runs with: a rebinding builtin
    or keyword at a segment head (_REBINDING_WORDS), or one of the shapes the
    head scan cannot reach (_rebinding_text): `((` or `$[`, a mutation where
    bash evaluates arithmetic (a `[[ ... -eq NAME=1 ]]` test, a `${...}`
    substring, a subscript in a `${...}`, in an assignment word or in a test
    with `-v` or `-R`), any mention of the hash or alias arrays, a `${...}`
    whose operator assigns, and an assignment to an interpreter or path
    variable whose value opens a substitution. Read under every separator
    set, quote-blind like them. A head behind `command` or `time`
    (_CURRENT_SHELL_WRAPPERS) is read as a head."""
    if _rebinding_text(command):
        return True
    for separators in _STORE_SEPARATOR_SETS:
        for segment in re.split(separators, command):
            try:
                words = _tokenize(segment)
            except ValueError:
                words = segment.split()
            if _segment_rebinds(words):
                return True
    return False


def _segment_rebinds(words: list[str]) -> bool:
    """True when one segment's words rebind at its head (see _command_rebinds).
    A loop, not a recursion, over the wrappers ahead of the head, and a bounded
    one: each pass re-reads the rest of the segment, so a run of more wrappers
    than _MAX_WRAPPERS counts as a rebind (fail closed) rather than costing
    time quadratic in its length."""
    for _ in range(_MAX_WRAPPERS + 1):
        rest = _strip_leading_noise(words)
        prefix = words[: len(words) - len(rest)]
        if any(w.lower().lstrip(_GROUP_OPENERS) in _REBINDING_KEYWORDS for w in prefix):
            return True
        if not rest:
            return any(_ANY_ASSIGNMENT.match(w) for w in prefix)
        head = rest[0]
        if head not in _CURRENT_SHELL_WRAPPERS:
            break
        index = 1
        while index < len(rest) and rest[index].startswith("-"):
            option = rest[index]
            index += 1
            if option == "--":
                break
            if head == "command" and ("v" in option or "V" in option):
                return False
        words = rest[index:]
    else:
        return True
    if head in _REBINDING_WORDS or _ANY_ASSIGNMENT.match(head):
        return True
    if _OPEN_SUBSCRIPT_HEAD.match(head) and _ANY_ASSIGNMENT.match(" ".join(rest)):
        return True
    if "()" in head or (len(rest) > 1 and rest[1].startswith("()")):
        return True
    return head == "printf" and len(rest) > 1 and rest[1].startswith("-v")


def _operand_path(operand: str, cwd: str) -> str | None:
    """The operand as an absolute path, a relative one joined to cwd, with its
    `.` and `..` steps still in it (see _is_pinned).

    No `~` or variable expansion: a script spelled that way is not exempt,
    which fails closed (recall off), never open.
    """
    try:
        return operand if os.path.isabs(operand) else os.path.join(cwd, operand)
    except (TypeError, ValueError):
        return None


def _is_pinned(path: str | None) -> bool:
    """True when the path is a pinned script as written (lexically, `.` and
    `..` folded away) AND leads to one when walked step by step with its
    symlinks resolved, so a `..` that leaves a symlinked folder for another
    file of the pinned name is not exempt."""
    if path is None:
        return False
    try:
        lexical = os.path.normcase(os.path.abspath(path))
    except (TypeError, ValueError):
        return False
    if lexical not in _pinned_scripts():
        return False
    return os.path.normcase(_real(path)) in _pinned_real_scripts()


def _exempt_segment(segment: str, cwd: str, command: str) -> bool:
    """True when the segment runs one of the pinned recall scripts.

    Checked per segment, never on the whole command, and pinned by path, not
    by basename.
    """
    operand = _exempt_operand(segment)
    if not operand:
        return False
    if not os.path.isabs(operand) and _CHDIR.search(command):
        return False
    absolute = _operand_path(operand, cwd)
    return _is_pinned(absolute)


# --- Latch-path rule ----------------------------------------------------------
# Decision 11: while a latch is present, whatever it holds, a model tool call
# may read the latch but not change it. Only mem_recall.py changes it: `latch`
# writes or replaces it, and `unlatch` removes it when it carries the caller's
# run_id. The latch path is matched as the store rule matches the store, every
# spelling, glob, brace expansion and symlink included, and the pinned script
# exemption applies to it per segment. In a Bash segment the latch's file name
# on its own counts too (_names_file_name), so a `cd` into its folder is no
# way around the rule.
#
# The tools that write files (_LATCH_CHANGING_TOOLS) are denied on the path.
# Read, Grep and Glob only read, so this rule does not look at them. A Bash
# segment that names the latch counts as a change unless it can be told to
# only read it (_read_segment, in a command _command_allows_reads accepts).
# So rm, mv, cp, ln, tee, a redirection, sed -i, truncate and python -c are
# examples of a change, not a list of them: anything the guard cannot tell
# only reads the latch is denied.
#
# A read is led, by bare name, by a command that writes no file whatever its
# options. `less` is not one (`less -o FILE` copies its input into FILE), nor
# `sed` (`-i`, and its `w` command), `find` (`-delete`, `-fprint`), `sort -o`,
# `uniq IN OUT` or `file -C`. The name is matched bare, so a `./cat` the model
# wrote is not a read, and the command must leave command lookup alone, so a
# function or alias named `cat` is not one either.
_LATCH_CHANGING_TOOLS = frozenset({"Bash", "Write", "Edit", "MultiEdit", "NotebookEdit"})
_LATCH_READERS = frozenset(
    {"cat", "head", "tail", "wc", "grep", "egrep", "fgrep", "jq", "ls", "stat", "test", "[", "[["}
)

# Any of these in a segment makes it more than a read: every output
# redirection (`>`, `>>`, `2>`, `&>`, `>|`, `<>`, `>(...)`), command
# substitution, process substitution, which runs a command of its own, and
# the `[[ ... =~ ... ]]` match, which hands what it matched on through
# BASH_REMATCH (`[[ <latch> =~ .* ]] && rm "$BASH_REMATCH"`), as `$_` does.
_READ_REFUSED = (">", "`", "$(", "<(", "=~")

# Bash's `$_`, the last word of the previous command: `cat <latch>; rm "$_"`
# hands the path on without naming it again, so in a command holding one, no
# segment counts as a read.
_LAST_WORD = re.compile(r"\$\{?_(?![A-Za-z0-9_])")

# A pipe, `|` or `|&`, but not `||`. A read piped into another command can
# hand the path on (`ls <latch> | xargs rm`), so in a command holding one,
# every segment must be a read for any of them to count as one.
_PIPE = re.compile(r"(?<!\|)\|(?!\|)")


def _read_segment(segment: str) -> bool:
    """True when the segment can only read: after the leading assignment,
    keyword and group-opener strip, it is led by one of _LATCH_READERS, by
    bare name, with nothing of _READ_REFUSED in it and no leading assignment
    that changes command lookup or what the command loads. A segment that
    runs nothing (a bare `fi`, a closing brace) counts as one too."""
    if any(marker in segment for marker in _READ_REFUSED):
        return False
    try:
        words = _tokenize(segment)
    except ValueError:
        return False
    rest = _strip_leading_noise(words)
    if any(_EXEMPT_UNSAFE_ASSIGNMENT.match(w) for w in words[: len(words) - len(rest)]):
        return False
    return not rest or rest[0] in _LATCH_READERS


@functools.lru_cache(maxsize=64)
def _command_allows_reads(command: str) -> bool:
    """True when a read segment of this command counts as a read: the command
    changes nothing about the environment or command lookup (_command_rebinds),
    uses no `$_`, and, when it holds a pipe, is made of reads only, under
    every separator set."""
    if _command_rebinds(command) or _LAST_WORD.search(command):
        return False
    if not _PIPE.search(command):
        return True
    return all(
        _read_segment(segment)
        for separators in _STORE_SEPARATOR_SETS
        for segment in re.split(separators, command)
    )


# The latch's file name on its own, beside its path: a `cd` into the artifacts
# folder and then `rm .mem-state.json`, a `find -name .mem-state.json -delete`,
# a path an interpreter joins at run time (`os.path.join(dir, '.mem-state.json')`)
# and a `**/` glob all name the file without spelling its path. The name
# counts when nothing that could extend it (a letter, digit, `_`, `.` or `-`)
# sits right before it and nothing that would continue it sits right after,
# past any trailing dots: Windows drops those from a file name, so there
# `.mem-state.json.` is the latch. A path needs no such step: on Windows
# os.path.abspath calls GetFullPathNameW, which trims trailing dots the way
# opening the path would, and elsewhere `<store>.` is another folder.
_NAME_EXTENDS = re.compile(r"[A-Za-z0-9_.-]")


def _dot_glob(word: str) -> bool:
    """A glob that starts with a literal dot and holds a literal character
    after it (`.m*`, `.mem-state.js?n`, `.*json`). A bare `.*`, `.??*` or
    `.[!.]*`, which matches every dotfile, is not one: it is how a search
    such as `find -not -path '*/.*'` skips hidden folders."""
    if not word.startswith(".") or not _GLOB_CHARS.search(word):
        return False
    return bool(re.sub(r"\[[^\]]*\]|[*?]", "", word[1:]))


@functools.lru_cache(maxsize=256)
def _names_file_name(segment: str, name: str) -> bool:
    """True when the segment holds the file name `name` on its own, or a word
    piece whose last step is a _dot_glob that matches it. Read with quotes
    taken out, backslashes taken out or read as separators, $'...' decoded,
    each extglob group read as a `*` and each brace expansion expanded."""
    target = _fold(name)
    texts = [segment, _decode_ansi_c(segment)] if "$'" in segment else [segment]
    for text in texts:
        plains = (_QUOTING.sub("", text), re.sub(r"[\"']", "", text.replace("\\", "/")))
        for plain in dict.fromkeys(plains):
            for spelling in dict.fromkeys((plain, _EXTGLOB.sub("*", plain))):
                for variant in _brace_variants(spelling):
                    folded = _fold(variant)
                    start = folded.find(target)
                    while start != -1:
                        end = start + len(target)
                        while folded[end : end + 1] == ".":
                            end += 1
                        if (start == 0 or not _NAME_EXTENDS.match(folded[start - 1])) and (
                            end == len(folded) or not _ROOT_CONTINUES.match(folded[end])
                        ):
                            return True
                        start = folded.find(target, start + 1)
                    for piece in _PATH_BREAK.split(variant):
                        last = _fold(piece.replace("\\", "/").rsplit("/", 1)[-1])
                        if _dot_glob(last) and fnmatch.fnmatchcase(target, last):
                            return True
    return False


# --- Heredoc bodies that are data ---------------------------------------------
# The latch and store rules split a command at its separators whatever the
# quoting, so a heredoc's body was read line by line as shell segments (issue
# #176): a report appended with `cat >> <file> <<'EOF'` from the latch's own
# folder was denied for a markdown line ending `row 6).**`, whose `.**` reads as
# a dot glob that matches the latch, and a table's `|` made the whole command
# count as piped. Bash hands a body to its command on standard input and, when
# the delimiter is quoted, runs none of it, so the two rules read a command
# without the bodies that are only data to it (_without_heredoc_data).
#
# Leaving text out is the direction that can let a call through, so the
# reading is narrow, and wherever it is unsure it keeps the whole command:
#   - A body is data only when its simple command is led by `cat` or `tee`
#     (_HEREDOC_SINKS), by bare name, after plain assignments that leave command
#     lookup alone, with no keyword, `{`, `!` or redirection in front. Any other
#     command may run what it reads (`bash`, `python3 -`, `xargs`,
#     `source /dev/stdin`, `git apply`, `ed`, `sqlite3`, a `while read` loop),
#     so its body is read as before.
#   - A sink with a `|` after it, before the next `;`, `&`, `&&`, `||` or the
#     end of its line, keeps its body: `cat <<'EOF' | sh` hands it to a shell,
#     and so does `cat <<'EOF' |` with `sh` on the line after the delimiter. A
#     `|` anywhere else in the command cannot reach the body.
#   - Nothing before a sink may change what `cat` or `tee` runs: no rebinding
#     _command_rebinds finds, and no assignment at all (_HEREDOC_ASSIGNS).
#     What follows the sink runs after it, unless a group, a subshell, a loop
#     or a function wraps it, and then a `|` or such a change anywhere in the
#     command keeps the body: `{ cat <<'EOF'; } | sh`, a loop that changes
#     PATH after the sink, and `f() {` with a later `f | sh` all reach it. A
#     `(` that opens no substitution or arithmetic, and `{`, `if`, `while`,
#     `until`, `for`, `select`, `function` or `coproc` where a word starts,
#     count as such a wrapper for every sink after them (_HEREDOC_COMPOUNDS).
#   - A `<(` or `>(` outside the bodies, even inside quotes, keeps every body.
#   - A quoted delimiter (`<<'EOF'`, `<<"EOF"`, `<<\EOF`) expands nothing in the
#     body. An unquoted one runs each `$(...)`, `$((...))`, `${...}`, `$[...]`
#     and backtick in it, so those stay in the reading, each read wide
#     (_heredoc_expansions).
#   - A `<<` counts only where bash reads one: outside quotes, comments and
#     arithmetic. One inside `[[ ]]`, `$(...)` or backticks keeps the whole
#     command, since bash ends a body inside a substitution at a line that only
#     starts with its delimiter (`EOF)`), and so does a `case`, whose patterns'
#     `)` the reading does not pair. A body ends at the first line equal to its
#     delimiter, leading tabs stripped for `<<-`, and several heredocs on one
#     line take consecutive bodies. In an unquoted body a line ending in a
#     backslash joins the next before bash compares it, so such a body keeps
#     the whole command too, and so does a body no delimiter line ends.
#   - A quote-aware second reading (_quoted_segments) must find the same
#     heredocs, in the same order, with the same delimiters.
# What follows a delimiter line is a command again, and is read as one. The
# claude-mem rule keeps reading every body: it denies `.claude-mem` anywhere in
# a call, by design. Accepted residual, the one stated for a script that names
# the store or the latch: a body written to a file that another command runs
# (a FIFO reader can start before the writer, so not only a later one).
_HEREDOC_SINKS = frozenset({"cat", "tee"})

# A heredoc operator and its delimiter word: a name, bare, quoted whole in
# single or double quotes, or behind a backslash, ended by a metacharacter. A
# word of any other shape keeps the whole command.
_HEREDOC_OPERATOR = re.compile(
    r"<<(?P<dash>-?)[ \t]*(?:'(?P<single>[A-Za-z_][A-Za-z0-9_]*)'"
    r"|\"(?P<double>[A-Za-z_][A-Za-z0-9_]*)\"|\\(?P<escaped>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<bare>[A-Za-z_][A-Za-z0-9_]*))(?![^ \t\n;&|()<>])"
)

# The head of a heredoc's simple command that makes its body data: plain
# assignments (no quote, expansion or operator in the value), then a sink by
# bare name, ended by a blank, a redirection or the command's end.
_HEREDOC_SINK = re.compile(
    r"[ \t]*((?:[A-Za-z_][A-Za-z0-9_]*=[^\s$`'\"\\(){};&|<>]*[ \t]+)*)"
    rf"(?:{'|'.join(sorted(_HEREDOC_SINKS))})(?![^ \t<>])"
)

# What ends a word where a keyword (`case`, `[[`, `]]`) can stand.
_HEREDOC_METACHARS = " \t\n;&|()<>"

# The keywords that open a group, a loop or a function, which can wrap a sink
# in a pipeline or run it again. A `(` counts too, wherever it stands, unless
# it opens a substitution or arithmetic (`$(`, `$((`, `((`).
_HEREDOC_COMPOUNDS = ("{", "if", "while", "until", "for", "select", "function", "coproc")

# What _command_rebinds still does not count (see _rebinding_text), because
# flagging it everywhere would over-deny the read and exemption paths: a plain
# `NAME=` or `NAME[...]=` anywhere, read quote-blind. The heredoc path is
# stricter than those, so it treats ANY such assignment before a sink as able
# to change what `cat` or `tee` runs, an argument such as `CC=gcc` included;
# one led by `-`, `.` or `/` (`--format=`, `user.name=`) cannot assign and does
# not. A `${...}` counts as it does there, where its operator assigns
# (`${x:=1}`), and here also where it holds such a `NAME=` (`${x:+a=b}`); a `=`
# after no name, or after one led by `-` (`${PWD#*=}`, `${x:-a=b}`), is text.
_HEREDOC_ASSIGNS = re.compile(r"(?<![A-Za-z0-9_./-])[A-Za-z_][A-Za-z0-9_]*(?:\[[^][]*\])?\+?=")


class _Unsure(Exception):
    """A command whose heredocs the reading cannot vouch for: it is read whole."""


class _Heredoc(NamedTuple):
    """One heredoc, as _HeredocScan finds it."""

    word: str  # its delimiter, `-` in front for `<<-`, as _quoted_heredoc_words reads it
    quoted: bool  # the delimiter was quoted, so bash expands nothing in the body
    head: str  # the simple command its operator sits in
    start: int  # where that simple command starts
    piped: bool  # a `|` follows that command in its pipeline
    body: int  # where its body starts
    close: int  # where its delimiter line starts
    end: int  # past its delimiter line


class _HeredocScan:
    """One pass over a command that finds its heredocs where bash does, or
    raises _Unsure. What it reads, and why, is in the section comment above."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.found: list[_Heredoc] = []
        # The operators read on the current line, each with the start and,
        # once read, the end of its simple command; their bodies start at the
        # next line.
        self.pending: list[dict] = []
        # Where the first group, subshell, loop or function opens, if any
        # does (_HEREDOC_COMPOUNDS).
        self.compound: int | None = None

    def run(self) -> list[_Heredoc]:
        self.command(0, None, True)
        return self.found

    def keyword(self, index: int, word: str) -> bool:
        end = index + len(word)
        return self.text.startswith(word, index) and (
            end == len(self.text) or self.text[end] in _HEREDOC_METACHARS
        )

    def command(self, index: int, closer: str | None, heredocs: bool) -> int:
        """Shell text from `index` to the `)` that closes it (`closer`), or to
        the end at the top; returns the index past it. `heredocs` is false in a
        substitution, where a `<<` keeps the whole command."""
        text = self.text
        size = len(text)
        start = index  # where the current simple command starts
        current: list[dict] = []
        # The operators read in the current pipeline, up to a `;`, `&`, `&&`,
        # `||` or the line's end: a `|` after one hands its command's output on.
        pipeline: list[dict] = []
        word_start = True
        in_test = False

        def end_command(at: int) -> None:
            for entry in current:
                entry["end"] = at
            current.clear()

        while index < size:
            char = text[index]
            if (
                word_start
                and self.compound is None
                and any(self.keyword(index, word) for word in _HEREDOC_COMPOUNDS)
            ):
                self.compound = index
            if char == "\\":
                index += 2  # an escaped character, a line continuation included
                word_start = False
            elif char == "#" and word_start:
                end = text.find("\n", index)
                index = size if end == -1 else end
            elif char == "'":
                index = self.single(index + 1)
                word_start = False
            elif text.startswith("$'", index):
                index = self.ansi_c(index + 2)
                word_start = False
            elif char == '"':
                index = self.double(index + 1)
                word_start = False
            elif char == "`":
                index = self.backtick(index + 1)
                word_start = False
            elif text.startswith("$((", index):
                index = self.arithmetic(index + 3)
                word_start = False
            elif text.startswith("$(", index):
                index = self.command(index + 2, ")", False)
                word_start = False
            elif text.startswith("${", index):
                index = self.braced(index + 2)
                word_start = False
            elif text.startswith(("$[", "<(", ">("), index):
                raise _Unsure
            elif word_start and text.startswith("((", index):
                index = self.arithmetic(index + 2)
                word_start = False
            elif word_start and self.keyword(index, "case"):
                raise _Unsure  # a pattern's `)` would close a `(` early
            elif word_start and self.keyword(index, "[["):
                in_test = True
                index += 2
            elif word_start and self.keyword(index, "]]"):
                in_test = False
                index += 2
            elif text.startswith("<<<", index):
                index += 3
                word_start = True
            elif text.startswith("<<", index):
                match = _HEREDOC_OPERATOR.match(text, index)
                if in_test or not heredocs or match is None:
                    raise _Unsure
                entry = {"match": match, "start": start, "end": None, "piped": False}
                self.pending.append(entry)
                current.append(entry)
                pipeline.append(entry)
                index = match.end()
                word_start = True
            elif char in "<>":
                index += 2 if text.startswith((">>", ">&", ">|", "<&", "<>"), index) else 1
                word_start = True
            elif text.startswith("&>", index):
                index += 3 if text.startswith("&>>", index) else 2
                word_start = True
            elif char == "|" and not text.startswith("||", index):
                end_command(index)
                for entry in pipeline:
                    entry["piped"] = True
                index += 2 if text.startswith("|&", index) else 1
                start = index
                word_start = True
            elif char in ";&|":
                end_command(index)
                pipeline.clear()
                index += 2 if text.startswith(("&&", "||"), index) else 1
                start = index
                word_start = True
            elif char == "(":
                if self.compound is None:
                    self.compound = index
                end_command(index)
                # A `(` glued to a word (an array, an extglob group, a function
                # name) opens no subshell, so no heredoc counts inside it.
                index = self.command(index + 1, ")", heredocs and word_start)
                start = index
                word_start = True
            elif char == ")":
                if closer is None:
                    raise _Unsure
                end_command(index)
                return index + 1
            elif char == "\n":
                if in_test:
                    raise _Unsure
                end_command(index)
                pipeline.clear()
                index = self.bodies(index + 1, heredocs)
                start = index
                word_start = True
            else:
                index += 1
                word_start = char in " \t"
        if closer is not None or self.pending:
            raise _Unsure  # an unclosed `(`, or an operator with no line after it
        end_command(size)
        return index

    def bodies(self, index: int, heredocs: bool) -> int:
        """The bodies of the operators on the line just ended, in order, from
        `index`; returns the index past the last delimiter line."""
        if not self.pending:
            return index
        if not heredocs:
            raise _Unsure
        text = self.text
        size = len(text)
        for entry in self.pending:
            match = entry["match"]
            if entry["end"] is None:
                raise _Unsure
            name = match["single"] or match["double"] or match["escaped"] or match["bare"]
            quoted = match["bare"] is None
            body = index
            while True:
                if index >= size:
                    raise _Unsure  # no delimiter line ends the body
                newline = text.find("\n", index)
                line_end = size if newline == -1 else newline
                line = text[index:line_end]
                if (line.lstrip("\t") if match["dash"] else line) == name:
                    break
                if not quoted and line.endswith("\\"):
                    raise _Unsure  # bash joins it to the next line first
                index = line_end + 1
            after = min(line_end + 1, size)
            head = text[entry["start"] : entry["end"]]
            self.found.append(
                _Heredoc(match["dash"] + name, quoted, head, entry["start"], entry["piped"], body, index, after)
            )
            index = after
        self.pending.clear()
        return index

    def single(self, index: int) -> int:
        end = self.text.find("'", index)
        if end == -1 or (self.pending and "\n" in self.text[index:end]):
            raise _Unsure
        return end + 1

    def ansi_c(self, index: int) -> int:
        text = self.text
        while index < len(text):
            if text[index] == "\\":
                index += 2
                continue
            if text[index] == "'":
                return index + 1
            if text[index] == "\n" and self.pending:
                raise _Unsure
            index += 1
        raise _Unsure

    def double(self, index: int) -> int:
        """A double-quoted string from past its opening quote, the
        substitutions in it read as bash reads them."""
        text = self.text
        while index < len(text):
            char = text[index]
            if char == "\\":
                index += 2
            elif char == '"':
                return index + 1
            elif char == "`":
                index = self.backtick(index + 1)
            elif text.startswith("$((", index):
                index = self.arithmetic(index + 3)
            elif text.startswith("$(", index):
                index = self.command(index + 2, ")", False)
            elif text.startswith("${", index):
                index = self.braced(index + 2)
            elif text.startswith("$[", index) or (char == "\n" and self.pending):
                raise _Unsure
            else:
                index += 1
        raise _Unsure

    def backtick(self, index: int) -> int:
        """Old-style substitution, which bash ends at the first backtick no
        backslash escapes; a `<<` in it keeps the whole command."""
        text = self.text
        start = index
        while index < len(text):
            if text[index] == "\\":
                index += 2
            elif text[index] == "`":
                inner = text[start:index]
                if "<<" in inner or (self.pending and "\n" in inner):
                    raise _Unsure
                return index + 1
            else:
                index += 1
        raise _Unsure

    def arithmetic(self, index: int) -> int:
        """Arithmetic, `$((...))` or `((...))`, up to its `))`, where a `<<` is
        a shift. One that spans lines, holds a quote or a backslash, or does
        not close as arithmetic keeps the whole command."""
        text = self.text
        depth = 0
        while index < len(text):
            char = text[index]
            if char in "\n'\"`\\" or text.startswith("$[", index):
                raise _Unsure
            if text.startswith("$((", index):
                index = self.arithmetic(index + 3)
                continue
            if text.startswith("$(", index):
                index = self.command(index + 2, ")", False)
                continue
            if text.startswith("${", index):
                index = self.braced(index + 2)
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                if depth:
                    depth -= 1
                elif text.startswith("))", index):
                    return index + 2
                else:
                    raise _Unsure
            index += 1
        raise _Unsure

    def braced(self, index: int) -> int:
        """A `${...}` from past its `{`, up to its `}`; one that quotes,
        substitutes or spans lines keeps the whole command."""
        text = self.text
        depth = 1
        while index < len(text):
            char = text[index]
            if char in "\n'\"`\\" or text.startswith(("$(", "$["), index):
                raise _Unsure
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if not depth:
                    return index + 1
            index += 1
        raise _Unsure


def _heredoc_lookup_changes(text: str) -> bool:
    """True when the text can change what a later `cat` or `tee` runs: what
    _command_rebinds finds, and any assignment it can miss (_HEREDOC_ASSIGNS)."""
    return _command_rebinds(text) or _HEREDOC_ASSIGNS.search(text) is not None


def _heredoc_sink(head: str) -> bool:
    """True when a heredoc's simple command hands its body to a command that
    only reads it as data (_HEREDOC_SINK), after no assignment that changes
    command lookup or what the command loads."""
    match = _HEREDOC_SINK.match(head)
    if match is None:
        return False
    return not any(_EXEMPT_UNSAFE_ASSIGNMENT.match(word) for word in match.group(1).split())


def _heredoc_expansions(body: str) -> list[str]:
    """What bash runs in an unquoted heredoc body: each backtick span, up to
    the first backtick no backslash escapes, and each `$(`, `${` or `$[` from
    its opener up to the body's last `)`, `}` or `]`, which holds its real
    closer whatever nests in it. Quotes mean nothing in a body, so none is
    read as one."""
    spans: list[str] = []
    index = 0
    size = len(body)
    while index < size:
        char = body[index]
        if char == "\\":
            index += 2
        elif char == "`":
            end = index + 1
            while end < size and body[end] != "`":
                end += 2 if body[end] == "\\" else 1
            spans.append(body[index : end + 1])
            index = end + 1
        elif char == "$" and body[index + 1 : index + 2] in ("(", "{", "["):
            closer = body.rfind({"(": ")", "{": "}", "[": "]"}[body[index + 1]])
            end = closer + 1 if closer > index + 1 else size
            spans.append(body[index:end])
            index = end
        else:
            index += 1
    return spans


def _quoted_heredoc_words(text: str) -> list[str]:
    """The delimiter after each `<<` the quote-aware reading finds, in order,
    `-` in front for `<<-`; none when the text does not lex."""
    words: list[str] = []
    for tokens in _quoted_segments(text):
        for index, token in enumerate(tokens):
            if token != "<<":
                continue
            after = tokens[index + 1 : index + 3]
            if after[:1] == ["-"] and len(after) == 2:
                words.append("-" + after[1])
            else:
                words.append(after[0] if after else "")
    return words


def _cut(text: str, cuts: list[tuple[int, int, str]]) -> str:
    """The text with each (start, end) span, in order, replaced by its string."""
    out: list[str] = []
    index = 0
    for start, end, kept in cuts:
        out.append(text[index:start])
        out.append(kept)
        index = end
    out.append(text[index:])
    return "".join(out)


@functools.lru_cache(maxsize=64)
def _without_heredoc_data(command: str) -> str:
    """The command as the latch and store rules read it: each heredoc body bash
    only hands to `cat` or `tee` as data left out, with its delimiter line, and
    of an unquoted one only what bash runs in it kept, a line each. Any other
    body is kept, and the command is kept as it is wherever the reading is
    unsure (see the section comment above)."""
    if "<<" not in command:
        return command
    scan = _HeredocScan(command)
    try:
        heredocs = scan.run()
    except (_Unsure, RecursionError):  # a substitution nested past the stack is unsure too
        return command
    if not heredocs:
        return command
    bodies = [(heredoc.body, heredoc.end, "") for heredoc in heredocs]
    skeleton = _cut(command, bodies)
    if (
        "<(" in skeleton
        or ">(" in skeleton
        or _quoted_heredoc_words(skeleton) != [heredoc.word for heredoc in heredocs]
    ):
        return command
    cuts: list[tuple[int, int, str]] = []
    # A lookup change before a sink, in the already-data-cut prefix, keeps its
    # body. A sink's simple command starts at a top-level boundary (a `<<`
    # inside `[[ ]]`, `(( ))`, `${...}`, a substitution or a `(` raises _Unsure
    # or opens a compound, so no boundary here sits inside one), and no
    # rebinding shape spans such a boundary. So each sink's prefix extends the
    # last one's, and once something before a sink changes lookup so does every
    # later prefix: carry a flag and read only the text added since the last
    # check, which keeps the whole pass linear in the command's length.
    lookup_changed = False
    checked = 0
    for heredoc in heredocs:
        if not _heredoc_sink(heredoc.head):
            continue
        if heredoc.piped:
            continue
        if scan.compound is not None and scan.compound < heredoc.start:
            # A group, subshell, loop or function may wrap the sink, so what
            # follows it can reach it too.
            if _PIPE.search(skeleton) or _heredoc_lookup_changes(skeleton):
                continue
        else:
            # Only the bodies already left out as data leave this text: any
            # other body may run in this shell before the sink does. Read the
            # slice added since the last check (checked..start), with the data
            # bodies cut in that slice left out, and keep the running flag.
            if not lookup_changed and heredoc.start > checked:
                delta = _cut(
                    command[checked : heredoc.start],
                    [(s - checked, e - checked, k) for s, e, k in cuts if checked <= s and e <= heredoc.start],
                )
                lookup_changed = _heredoc_lookup_changes(delta)
                checked = heredoc.start
            if lookup_changed:
                continue
        kept = ""
        if not heredoc.quoted:
            spans = _heredoc_expansions(command[heredoc.body : heredoc.close])
            kept = "".join(f"{span}\n" for span in spans)
        cuts.append((heredoc.body, heredoc.end, kept))
    return _cut(command, cuts)


def _store_segment(
    command: str,
    roots: tuple[str, ...],
    cwd: str,
    homes: list[str],
    *,
    exempt: bool = True,
    reads: bool = False,
    name: str | None = None,
    data: bool = False,
) -> str | None:
    """The first shell segment that names a root and is not let through.

    With `exempt` false (the claude-mem folder) no segment is exempt. A
    command that can rebind `uv` or `python` (_command_rebinds) exempts none
    of its segments either. With `reads` true (the latch), a segment that
    only reads is let through as well, in a command that allows reads. With
    a `name` (the latch's file name), a segment that holds that name on its
    own (_names_file_name) counts as naming the root. With `data` true (the
    latch and the store), the command is read without the heredoc bodies bash
    only hands to `cat` or `tee` (_without_heredoc_data), by every check here:
    bash runs none of that text, so it can neither name a root nor rebind,
    pipe, change folder or hand on a `$_`.
    """
    if data:
        command = _without_heredoc_data(command)
    home_key = tuple(homes)
    reads = reads and _command_allows_reads(command)
    for separators in _STORE_SEPARATOR_SETS:
        for segment in re.split(separators, command):
            if not _bash_names(segment, roots, cwd, home_key) and not (
                name and _names_file_name(segment, name)
            ):
                continue
            if (
                exempt
                and not _command_rebinds(command)
                and _exempt_segment(segment, cwd, command)
            ):
                continue
            if reads and _read_segment(segment):
                continue
            return segment
    return None


def _input_names(
    key: str,
    value: str,
    tool_input: dict,
    roots: tuple[str, ...],
    cwd: str,
    homes: list[str],
    *,
    exempt: bool,
    reads: bool = False,
    name: str | None = None,
    data: bool = False,
) -> str | None:
    """What in one input names a root: the Bash segment, or the file-tool
    value; None when nothing does. `reads` lets a Bash read through and
    `name` matches a Bash segment on the file name alone too (both for the
    latch rule), and `data` reads a Bash command without the heredoc bodies
    that are only data (the latch and store rules); a file tool is matched on
    its value alone."""
    if key == "command":
        return _store_segment(
            value, roots, cwd, homes, exempt=exempt, reads=reads, name=name, data=data
        )
    bases = [cwd]
    own_path = tool_input.get("path")
    if key in _PATTERN_KEYS and isinstance(own_path, str) and own_path:
        bases.append(os.path.join(cwd, os.path.expanduser(own_path)))
    return value if _names_store(value, roots, bases, homes, cwd, whole=True) else None


def _tool_inputs(tool_name: object, tool_input: dict) -> list[tuple[str, str]]:
    """(key, value) for every non-empty string input the gate reads."""
    if tool_name == "Bash":
        keys: tuple[str, ...] = ("command",)
    elif isinstance(tool_name, str) and tool_name in _TOOL_EXTRA_KEYS:
        keys = _PATH_KEYS + _TOOL_EXTRA_KEYS[tool_name]
    else:
        return []
    out: list[tuple[str, str]] = []
    for key in keys:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            out.append((key, value))
    return out


def _event_cwd(event: dict) -> str:
    cwd = event.get("cwd")
    return cwd if isinstance(cwd, str) and cwd else os.getcwd()


def _shown(segment: str) -> str:
    """A denied segment as its deny reason quotes it, cut to _SEGMENT_SHOWN."""
    text = segment.strip()
    if len(text) > _SEGMENT_SHOWN:
        text = text[:_SEGMENT_SHOWN] + "..."
    return repr(text)


def _latch_deny(state_path: Path, what: str) -> NoReturn:
    """Deny for a reason the latch causes. The reason names the latch and ends
    with a note for the person, not the model (AC-33): a latch a run left
    behind is theirs to delete by hand, and the model must not try to remove
    it, which the latch-path rule denies anyway."""
    _deny(
        f"Cross-Session Recall guard: {what} The run latch {state_path} is "
        "present, and a present latch counts as a live UltraCode-Goal run, "
        "whatever its version or colour. For the user: if no UltraCode-Goal "
        "run is active, a run ended without removing this latch. Delete "
        f"{state_path} by hand. The model must not try to remove it itself."
    )


def _latch_rule_text() -> str:
    """The one rule a latch-path deny states: the model may read the latch,
    never change it, and what counts as a read. It gives no recipe for
    changing the latch: the run's own steps already carry the one call that
    may, and a deny is no cue to make it."""
    return (
        "While a run latch is present, the model's tool calls may read it but "
        "not change it, by its path or by its file name. Reading it stays "
        "allowed: Read, Grep and Glob, or a Bash segment led by one of "
        f"{', '.join(f'`{name}`' for name in sorted(_LATCH_READERS))}, with no "
        "output redirection, command substitution or `=~`, piped only into "
        "another such read (a `|` counts as a pipe even inside quotes)."
    )


def _store_rule_text() -> str:
    """The one rule a store deny states: what may reach the store."""
    return (
        "While a run latch is present, only this skill's recall scripts reach "
        "the store: `uv run`, `python`, `python3` or `python3.N` followed "
        f"directly by {os.path.join(_scripts_dir(), _RECALL_SCRIPTS[0])} or "
        f"{os.path.join(_scripts_dir(), _RECALL_SCRIPTS[1])}, as a shell segment "
        "of its own, with no redirection, command substitution or wrapper, in a "
        "command that changes nothing about the environment or about what `uv` "
        "and `python` resolve to."
    )


_CLAUDE_MEM_REFUSED = (
    "UltraCode-Goal no longer uses claude-mem, so while a run latch is present "
    "every claude-mem call is denied."
)


def _latch_gate(event: dict, state_path: Path) -> None:
    """The denies a present latch causes; returns when none applies."""
    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    # 1) claude-mem MCP calls, every name form, whatever the latch says, an MCP
    # resource read or listing on a claude-mem server, and a listing that
    # names no server, which lists claude-mem's resources too.
    if _is_claude_mem_tool(tool_name):
        _latch_deny(
            state_path,
            f"refusing the claude-mem MCP call {tool_name}. {_CLAUDE_MEM_REFUSED}",
        )
    server = _claude_mem_resource_server(tool_name, tool_input)
    if server is not None:
        _latch_deny(
            state_path,
            f"refusing a {tool_name} call on the claude-mem MCP server {server}. "
            f"{_CLAUDE_MEM_REFUSED}",
        )
    if tool_name == _MCP_LIST_RESOURCES and not tool_input.get("server"):
        _latch_deny(
            state_path,
            f"refusing a {tool_name} call that names no server: it lists every "
            "server's resources, claude-mem's included. Name the server whose "
            f"resources you need. {_CLAUDE_MEM_REFUSED}",
        )

    inputs = _tool_inputs(tool_name, tool_input)
    cwd = _event_cwd(event)
    homes = _home_dirs()

    # 2) Reach into claude-mem's own files, through every inspected input: the
    # folder's name anywhere, or a path, glob or brace expansion that reaches
    # it under a home. A heredoc body is read too, data or not.
    mem_roots = _claude_mem_roots(homes)
    for key, value in inputs:
        if _mentions_claude_mem(value) or (
            _input_names(key, value, tool_input, mem_roots, cwd, homes, exempt=False)
            is not None
        ):
            _latch_deny(
                state_path,
                f"refusing a {tool_name} call whose {key} reaches into "
                "'.claude-mem'. While a run latch is present, nothing reads or "
                "writes claude-mem's files.",
            )

    # 3) The latch-path rule (decision 11), whatever the latch holds: a call
    # that names the latch and may change it. Read, Grep and Glob only read,
    # so they are not looked at; a Bash segment that only reads passes, and a
    # heredoc body that is only data to its command is not read.
    if tool_name in _LATCH_CHANGING_TOOLS:
        latch_roots = _roots(str(state_path))
        for key, value in inputs:
            found = _input_names(
                key,
                value,
                tool_input,
                latch_roots,
                cwd,
                homes,
                exempt=True,
                reads=True,
                name=state_path.name,
                data=True,
            )
            if found is None:
                continue
            if key == "command":
                _latch_deny(
                    state_path,
                    f"refusing a Bash command whose segment {_shown(found)} names "
                    f"the run latch and may change it. {_latch_rule_text()}",
                )
            _latch_deny(
                state_path,
                f"refusing a {tool_name} call whose {key} names the run latch. "
                f"{_latch_rule_text()}",
            )

    # 4) The store-path rule, for a latch that names a usable store. A latch
    # with none (a v1 latch, an unset store, an unreadable latch) has no path
    # to match, so it denies only through 1) to 3). A heredoc body that is
    # only data to its command is not read, as for the latch.
    store = _latch_view(_read_latch(state_path))["store"]
    if store is None:
        return
    roots = _roots(store)
    for key, value in inputs:
        found = _input_names(key, value, tool_input, roots, cwd, homes, exempt=True, data=True)
        if found is None:
            continue
        if key == "command":
            _latch_deny(
                state_path,
                f"refusing a Bash command whose segment {_shown(found)} names the "
                f"recall store {store}. {_store_rule_text()}",
            )
        _latch_deny(
            state_path,
            f"refusing a {tool_name} call whose {key} names the recall store "
            f"{store}. {_store_rule_text()}",
        )


def _mem_gate(event: dict, impl: Path | None) -> None:
    """Apply the Cross-Session Recall gate for ALL tool names.

    Runs before any Bash-only git logic and re-reads the latch per call. With
    no latch (no active run) it returns: the user's own claude-mem usage
    outside a run is never touched.
    """
    state_path = _mem_state_path(impl)
    if state_path is None:
        # Cannot locate impl-artifacts (no cwd in the event, env unset): the
        # run state is UNKNOWABLE, not provably absent. Uncertain implies deny
        # for claude-mem calls; everything else passes through untouched.
        if _is_claude_mem_tool(event.get("tool_name")):
            _deny(
                "Cross-Session Recall guard: cannot locate impl-artifacts "
                "(event carries no cwd and ULTRACODE_IMPL_ARTIFACTS is unset), "
                "so whether a run latch is present cannot be told, and this "
                "claude-mem MCP call is refused (failing closed). Set "
                "ULTRACODE_IMPL_ARTIFACTS on the hook command to restore latch "
                "resolution."
            )
        return
    # No latch -> no active UCG run -> nothing to gate.
    if not _latch_present(state_path):
        return
    try:
        _latch_gate(event, state_path)
    except Exception as exc:  # noqa: BLE001  fail closed on the unforeseen
        # A crash would exit non-zero, which the client reads as no decision,
        # letting the call through. A present latch means deny instead.
        _latch_deny(
            state_path,
            f"could not evaluate this {event.get('tool_name')} call against the "
            f"run latch ({type(exc).__name__}), so it is refused (failing closed).",
        )


def main() -> None:
    event = _read_event()

    cwd = event.get("cwd")
    impl = _impl_artifacts(cwd)

    # Cross-Session Recall gate runs for EVERY tool name, before the Bash-only
    # git logic below. It either denies (and exits) or returns to let the rest
    # of the guard proceed unchanged.
    _mem_gate(event, impl)

    if event.get("tool_name") != "Bash":
        _allow()

    command = (event.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str):
        _allow()

    verbs, unknown = _classify(command)
    if not verbs:
        _allow()
    hint = _unknown_hint(unknown)

    protected = _protected_branches()
    branch = _current_branch(cwd)

    if branch is not None and branch in protected:
        _deny(
            f"Protected-branch guard: refusing `git {'/'.join(sorted(verbs))}` "
            f"on '{branch}'. UltraCode-Goal commits one green story per commit "
            f"on an epic branch ('{os.environ.get('ULTRACODE_EPIC_BRANCH_PREFIX', 'ultracode/epic-')}<id>'), "
            f"never on {protected}. Switch to the epic branch first.",
            hint,
        )

    if "commit" in verbs:
        impl = _impl_artifacts(cwd)
        story = _current_story(impl)
        marker = (impl / f".tests-ran-{story}") if (impl and story) else None
        # Same impl-artifacts dir and same story id as the marker, on purpose:
        # one resolution path, so the two files cannot drift apart.
        baseline = (impl / f".baseline-{story}") if (impl and story) else None
        if marker is None or baseline is None or not marker.is_file():
            target = str(marker) if marker else "<impl-artifacts>/.tests-ran-<story>"
            _deny(
                "Tests-ran guard: refusing `git commit` — no tests-ran marker "
                f"for the current story ({story or 'unknown'}). Run the story's "
                f"test/lint/build to green and write {target} before committing. "
                "Commit only at a verified-green story boundary.",
                hint,
            )
        _marker_freshness_gate(marker, baseline)
        if not _staged_index_nonempty(cwd):
            _deny(
                "Empty-index guard: refusing `git commit` — the staged index is "
                "empty (or could not be read), so this commit would capture no "
                "work. Stage this story's paths in a prior, SEPARATE tool call "
                "(`git add <this story's paths>`), then commit as a second, "
                "distinct tool call. `git commit -a` and commit-time pathspecs "
                "are unsupported inside a story loop: the guard evaluates the "
                "command string before it runs, so anything they would stage "
                "does not exist yet at that point.",
                hint,
            )
        _unskip_gate(cwd, story)

    _allow()


if __name__ == "__main__":
    main()
