"""Every surface that appends to `.decision-log.md` names how (#208).

The log is canonical memory, and it grows one session's prose per invocation.
Two things make appending to it harder than it looks:

  - a Bash heredoc puts the log's prose into a Bash command string, and the
    PreToolUse guard's git gates read that string as commands, so a log line
    that quotes a commit verb, a backticked name or an apostrophe is denied;
  - once the log is too large to Read, both file tools refuse it, so the two
    sanctioned writers are closed at once.

Execute's step 4 held the remedy (Write the entry to a new slice file, then
append it with one `cat`), but `/ucg-resolve` and `/ucg-formalize` run cold
and never load execute.md before they write, and Stages 1 and 2 append before
it is loaded. Step 4 also named the slice
`{workflow.implementation_artifacts}/dlog-slice-<story_id>-<n>.md`, a folder
other than the run folder that holds the log, while calling it a sibling of
the log, and appended it with a relative `cat <slice> >> .decision-log.md`.

These checks pin the rule on each surface, the slice beside the log with both
paths in full, and Finalize's audit looking for slices there. Every check reds
on the text as it stood before #208, and the `cat` command each surface gives
is run as written: the guard makes no decision on it and it appends the slice.

Each `cat` double-quotes both paths. `{project-root}` is wherever the project
sits, and a space in it splits a bare path into two words, so the append
fails. The command is run from a project path that holds a space too, and
the bare form, as #208 first gave it, reds a quoting check of its own.

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
_SKILLS = _SKILL_ROOT.parent
_REPO = _SKILLS.parent
_RESOLVE = _SKILLS / "ucg-resolve" / "SKILL.md"
_FORMALIZE = _SKILLS / "ucg-formalize" / "SKILL.md"
_PARENT = _SKILL_ROOT / "SKILL.md"
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_FINALIZE = _SKILL_ROOT / "references" / "finalize.md"
_HOOK = _SKILL_ROOT / "scripts" / "hooks" / "guard_pretooluse.py"

_FILES = {
    "resolve": _RESOLVE,
    "formalize": _FORMALIZE,
    "parent": _PARENT,
    "execute": _EXECUTE,
    "finalize": _FINALIZE,
}

_RUN = "epic-7-20260604T172512Z"
_HEREDOC_RULE_RE = re.compile(r"Write/Edit,? (and )?never a Bash heredoc")
_NO_SLICE_IN_IMPL = "{workflow.implementation_artifacts}/dlog-slice"


def _world() -> dict[str, str]:
    return {name: path.read_text(encoding="utf-8") for name, path in _FILES.items()}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _md_section(text: str, heading: str) -> str:
    """Body of a `## <heading>` section, up to the next `## `."""
    m = re.search(r"^## " + re.escape(heading) + r".*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert m is not None, f"section {heading!r} not found"
    return m.group(0)


def _line(text: str, lead: str) -> str:
    """The one line (a paragraph, in these files) that starts with `lead`."""
    lines = [ln for ln in text.splitlines() if ln.startswith(lead)]
    assert len(lines) == 1, f"expected one line starting {lead!r}, found {len(lines)}"
    return lines[0]


def _step4(text: str) -> str:
    """Execute's step 4: from its marker up to step 5's."""
    start = text.index("\n4. ")
    return text[start : text.index("\n5. ", start)]


def _resolve_log(w: dict) -> str:
    """Resolve section 3 from the end of the `defer` bullet: the log paragraph.

    The new rule sits in its own paragraph after the dispositions, so the
    `defer` bullet (which must name no clear) and the `close` bullet (whose
    coupled-stories text is pinned verbatim) stay as they were.
    """
    section = _md_section(w["resolve"], "3.")
    return _norm(section[section.index("- **`defer`**") :].split("\n\n", 1)[1])


def _resolve_conventions(w: dict) -> str:
    return _norm(_md_section(w["resolve"], "Conventions"))


def _formalize_conventions(w: dict) -> str:
    return _norm(_md_section(w["formalize"], "Conventions"))


def _parent_rule(w: dict) -> str:
    return _line(w["parent"], "Run the stages in order")


def _execute_step4(w: dict) -> str:
    return _norm(_step4(w["execute"]))


def _finalize_audit(w: dict) -> str:
    return _line(w["finalize"], "Walk every entry ")


_RESOLVE_DIR = "{project-root}/_bmad-output/ultracode-goal/<run folder>"
_RESOLVE_SLICE = _RESOLVE_DIR + "/dlog-slice-resolve-<n>.md"
_RESOLVE_CAT = f'`cat "{_RESOLVE_SLICE}" >> "{_RESOLVE_DIR}/.decision-log.md"`'
_FORMALIZE_CAT = '`cat "<run folder>/dlog-slice-formalize-<n>.md" >> "<run folder>/.decision-log.md"`'
_PARENT_CAT = '`cat "<log folder>/dlog-slice-<label>-<n>.md" >> "<log folder>/.decision-log.md"`'
_EXECUTE_CAT = '`cat "<log folder>/dlog-slice-<story_id>-<n>.md" >> "<log folder>/.decision-log.md"`'

# The `cat` a surface gives, found whatever its quoting: one per surface.
_CAT_RE = re.compile(r'`(cat [^`]*dlog-slice-[^`]*>>[^`]*\.decision-log\.md"?)`')
# Both of its paths in double quotes, so a space in either stays in one word.
_QUOTED_CAT_RE = re.compile(r'cat "[^"`]+" >> "[^"`]+"')


def _bare(text: str) -> str:
    """The text with its double quotes dropped, for the checks on the paths."""
    return text.replace('"', "")


def _quotes_both_paths(text: str) -> bool:
    found = _CAT_RE.findall(_norm(text))
    return len(found) == 1 and bool(_QUOTED_CAT_RE.fullmatch(found[0]))


# One named check per rule. Each reads one surface and keys on one sentence, so
# a cut of that sentence reds that check alone.
_CHECKS = {
    # --- /ucg-resolve, section 3 ---------------------------------------------
    "resolve writes the log with Write/Edit, never a heredoc": lambda w: bool(
        re.search(r"`\.decision-log\.md` as you apply it, with Write/Edit and never a Bash heredoc", _resolve_log(w))
    ),
    "resolve says why a heredoc collides with the guard": lambda w: (
        "the PreToolUse guard's git gates read that string as commands" in _resolve_log(w)
    ),
    "resolve rules out Reading a log too large to Read": lambda w: (
        "Once the log is too large to Read affordably, do not Read it" in _resolve_log(w)
    ),
    "resolve writes the slice beside the log, in full": lambda w: (
        f"a new file beside the log, `{_RESOLVE_SLICE}`" in _resolve_log(w)
    ),
    "resolve numbers each slice past the highest on disk": lambda w: (
        "with `<n>` one past the highest number a `dlog-slice-resolve-*.md` in that folder already carries"
        in _resolve_log(w)
    ),
    "resolve appends with one cat, both paths in full": lambda w: _bare(_RESOLVE_CAT) in _bare(_resolve_log(w)),
    "resolve double-quotes both paths in its cat": lambda w: _quotes_both_paths(_resolve_log(w)),
    "resolve keeps the slice": lambda w: "Keep the slice rather than deleting it" in _resolve_log(w),
    "resolve covers the coupled-stories entry": lambda w: (
        "This holds for every entry the pass writes, the coupled-stories entry above included." in _resolve_log(w)
    ),
    "resolve's conventions point at section 3": lambda w: (
        "Append to it with Write/Edit, never a Bash heredoc, as section 3 says" in _resolve_conventions(w)
    ),
    # --- /ucg-formalize -------------------------------------------------------
    "formalize writes the log with Write/Edit, never a heredoc": lambda w: (
        "Append to the log with Write/Edit, never a Bash heredoc" in _formalize_conventions(w)
    ),
    "formalize writes the slice beside the log": lambda w: (
        "a new file beside the log, `<run folder>/dlog-slice-formalize-<n>.md`, where `<run folder>` is the "
        "resolved folder above in full" in _formalize_conventions(w)
    ),
    "formalize appends with one cat, both paths in full": lambda w: (
        _bare(_FORMALIZE_CAT) in _bare(_formalize_conventions(w))
    ),
    "formalize double-quotes both paths in its cat": lambda w: _quotes_both_paths(_formalize_conventions(w)),
    "formalize's remediation log points at its conventions": lambda w: (
        "Log each remediation to `.decision-log.md` as you apply it, appended the way Conventions says."
        in _norm(w["formalize"])
    ),
    # --- the parent skill, read before any stage reference --------------------
    "the parent skill rules the append method from Stage 1": lambda w: (
        "**Append it with Write/Edit, never a Bash heredoc**, from Stage 1 on" in _parent_rule(w)
    ),
    "the parent skill writes the slice beside the log": lambda w: (
        "a new file beside the log, in the run folder that holds it, `<log folder>/dlog-slice-<label>-<n>.md`"
        in _parent_rule(w)
    ),
    "the parent skill labels a slice by story or stage": lambda w: (
        "`<label>` is the story's id for an entry about a story and `stage<k>` for one a stage writes outside a story"
        in _parent_rule(w)
    ),
    "the parent skill appends with one cat, both paths in full": lambda w: _bare(_PARENT_CAT) in _bare(_parent_rule(w)),
    "the parent skill double-quotes both paths in its cat": lambda w: _quotes_both_paths(_parent_rule(w)),
    # --- execute.md step 4, the rule's owner ---------------------------------
    "execute puts the slice beside the log, not in implementation_artifacts": lambda w: (
        "a NEW sibling file beside the log, in the folder that holds `.decision-log.md` and never in "
        "`{workflow.implementation_artifacts}`" in _execute_step4(w)
        and "`<log folder>/dlog-slice-<story_id>-<n>.md`" in _execute_step4(w)
    ),
    "execute numbers each slice past the highest on disk": lambda w: (
        "`<n>` is one past the highest number a `dlog-slice-<story_id>-*.md` there already carries"
        in _execute_step4(w)
    ),
    "execute appends with one cat, both paths in full": lambda w: _bare(_EXECUTE_CAT) in _bare(_execute_step4(w)),
    "execute double-quotes both paths in its cat": lambda w: _quotes_both_paths(_execute_step4(w)),
    # --- finalize's audit -----------------------------------------------------
    "finalize audits the slices beside the log": lambda w: (
        "this session's own `dlog-slice-*.md` files, which sit beside the log in the run folder (never in "
        "`{workflow.implementation_artifacts}`)" in _finalize_audit(w)
    ),
}


def _unmet(w: dict) -> list[str]:
    return sorted(name for name, check in _CHECKS.items() if not check(w))


def _span(text: str, start: str, end: str) -> re.Pattern:
    """A pattern for the text from `start` through `end`, whatever whitespace (a
    line wrap included) stands where either has a space; it must match once."""

    def words(s: str) -> str:
        return r"\s+".join(map(re.escape, s.split(" ")))

    pattern = re.compile(words(start) + r".*?" + words(end), re.DOTALL)
    assert len(pattern.findall(text)) == 1, (start, end)
    return pattern


def _replace(text: str, start: str, end: str, old: str) -> str:
    return _span(text, start, end).sub(lambda _: old, text, count=1)


_OLD_RESOLVE_LOG = "Record each answer and its disposition in `.decision-log.md` as you apply it."
_OLD_EXECUTE_SLICE = (
    "Compose this session's entry with Write into a NEW sibling file in the run folder, "
    "`{workflow.implementation_artifacts}/dlog-slice-<story_id>-<n>.md`, where `<n>` increments per append: "
    "the name has to be unique per append, not per story, or a story's SECOND entry finds the slice already "
    "on disk and walks straight back into the Read it was escaping; then append it in one Bash call, "
    "`cat <slice> >> .decision-log.md`."
)
_OLD_PARENT_RULE = (
    "The decision log is canonical memory \u2014 record scope, the preflight verdict, every gate outcome, and "
    "every deferral as you go."
)
_OLD_FINALIZE_AUDIT = (
    "on a mature Epic it is not, and must not be \u2014 execute.md step 4 forbids Reading the log once it is too "
    "large to Read affordably, so the auditable unit there is this session's own `dlog-slice-*.md` files plus "
    "what is still in context."
)


def _pre_208(w: dict) -> dict:
    """The five files as they read before #208, rebuilt from the live text."""
    old = dict(w)
    old["resolve"] = _replace(
        w["resolve"],
        "Record each answer and its disposition",
        "the coupled-stories entry above included.",
        _OLD_RESOLVE_LOG,
    )
    old["resolve"] = _replace(old["resolve"], " Append to it with Write/Edit,", "too large to Read.", "")
    old["formalize"] = _replace(w["formalize"], " Append to the log with Write/Edit,", "append is interrupted.", "")
    old["formalize"] = _replace(
        old["formalize"],
        "Log each remediation to `.decision-log.md` as you apply it,",
        "the way Conventions says.",
        "Log each remediation to `.decision-log.md` as you apply it.",
    )
    old["parent"] = _replace(
        w["parent"], "The decision log is canonical memory:", "and keep the slice.", _OLD_PARENT_RULE
    )
    old["execute"] = _replace(
        w["execute"],
        "Compose this session's entry with Write into a NEW sibling file beside the log",
        '/.decision-log.md"`.',
        _OLD_EXECUTE_SLICE,
    )
    old["finalize"] = _replace(
        w["finalize"], "on a mature Epic it is not, and must not be:", "plus what is still in context.",
        _OLD_FINALIZE_AUDIT,
    )
    return old


def test_every_surface_names_the_append_method():
    assert _unmet(_world()) == []


def test_the_pre_208_text_fails_every_check():
    """Twin: the text before #208 reds on ALL of the checks, not merely one."""
    w = _world()
    old = _pre_208(w)
    # The rebuild is the old text, not an emptied file: each old sentence is
    # back and the rest of each file is as it stands.
    assert _OLD_RESOLVE_LOG + "\n\n## 4." in old["resolve"]
    assert _OLD_EXECUTE_SLICE in old["execute"]
    assert _OLD_PARENT_RULE in old["parent"]
    assert _OLD_FINALIZE_AUDIT in old["finalize"]
    for name in _FILES:
        assert len(old[name]) > len(w[name]) * 0.9, name
    assert _unmet(old) == sorted(_CHECKS), sorted(set(_CHECKS) - set(_unmet(old)))


def test_each_rule_reds_alone_when_cut():
    """Twin: a cut of one sentence reds its own check, and only that one."""
    w = _world()
    cuts = {
        "resolve writes the log with Write/Edit, never a heredoc": (
            "resolve", ", with Write/Edit and never a Bash heredoc.", ".",
        ),
        "resolve says why a heredoc collides with the guard": (
            "resolve", "the PreToolUse guard's git gates read that string as commands", "the guard objects",
        ),
        "resolve numbers each slice past the highest on disk": (
            "resolve", "one past the highest number", "the next number",
        ),
        "resolve keeps the slice": ("resolve", "Keep the slice rather than deleting it", "Delete the slice"),
        "resolve covers the coupled-stories entry": (
            "resolve", "This holds for every entry the pass writes, the coupled-stories entry above included.", "",
        ),
        "resolve's conventions point at section 3": (
            "resolve", "Append to it with Write/Edit, never a Bash heredoc, as section 3 says,", "",
        ),
        "formalize's remediation log points at its conventions": (
            "formalize", ", appended the way Conventions says.", ".",
        ),
        "the parent skill labels a slice by story or stage": (
            "parent", "`stage<k>` for one a stage writes outside a story", "the stage for another",
        ),
        "execute numbers each slice past the highest on disk": (
            "execute", "is one past the highest number a `dlog-slice-<story_id>-*.md` there already carries, so it",
            "",
        ),
        "finalize audits the slices beside the log": (
            "finalize", ", which sit beside the log in the run folder (never in `{workflow.implementation_artifacts}`)",
            "",
        ),
    }
    for name, (surface, cut, put) in cuts.items():
        pattern = re.compile(r"\s+".join(map(re.escape, cut.split(" "))))
        assert len(pattern.findall(w[surface])) == 1, name
        mutated = {**w, surface: pattern.sub(lambda _: put, w[surface], count=1)}
        assert _unmet(mutated) == [name], name


def test_the_slice_back_in_implementation_artifacts_reds():
    """Twin: the folder Execute used to name, on the owner and on resolve."""
    w = _world()
    slice_name = "/dlog-slice-<story_id>-<n>.md`"
    moved_execute = w["execute"].replace("`<log folder>" + slice_name, "`{workflow.implementation_artifacts}" + slice_name, 1)
    moved = {**w, "execute": moved_execute}
    assert "execute puts the slice beside the log, not in implementation_artifacts" in _unmet(moved)
    assert _slices_in_implementation_artifacts(moved) == ["execute"]

    relative_cat = '`cat "dlog-slice-resolve-<n>.md" >> ".decision-log.md"`.'
    relative = {**w, "resolve": _replace(w["resolve"], '`cat "{project-root}', '.decision-log.md"`.', relative_cat)}
    assert _unmet(relative) == ["resolve appends with one cat, both paths in full"]


# Each surface's `cat` as #208 first gave it, both paths bare.
_UNQUOTED_CATS = {
    "resolve": (
        "resolve",
        "`cat {project-root}/_bmad-output/ultracode-goal/<run folder>/dlog-slice-resolve-<n>.md >> "
        "{project-root}/_bmad-output/ultracode-goal/<run folder>/.decision-log.md`",
        _RESOLVE_CAT,
    ),
    "formalize": (
        "formalize",
        "`cat <run folder>/dlog-slice-formalize-<n>.md >> <run folder>/.decision-log.md`",
        _FORMALIZE_CAT,
    ),
    "parent": (
        "the parent skill",
        "`cat <log folder>/dlog-slice-<label>-<n>.md >> <log folder>/.decision-log.md`",
        _PARENT_CAT,
    ),
    "execute": (
        "execute",
        "`cat <log folder>/dlog-slice-<story_id>-<n>.md >> <log folder>/.decision-log.md`",
        _EXECUTE_CAT,
    ),
}


def test_the_unquoted_cat_reds_its_quoting_check_alone():
    """Twin: the bare command on one surface reds that surface's quoting check,
    and only that one: its paths are still in full, only the quotes are gone."""
    w = _world()
    for surface, (owner, unquoted, quoted) in _UNQUOTED_CATS.items():
        assert _bare(quoted) == unquoted, surface
        pattern = re.compile(r"\s+".join(map(re.escape, quoted.split(" "))))
        assert len(pattern.findall(w[surface])) == 1, surface
        mutated = {**w, surface: pattern.sub(lambda _: unquoted, w[surface], count=1)}
        assert _unmet(mutated) == [f"{owner} double-quotes both paths in its cat"], surface

    # One path quoted is not enough: the log's path is the one a space splits
    # into a redirect target and a stray argument.
    half = _EXECUTE_CAT.replace('>> "<log folder>/.decision-log.md"', ">> <log folder>/.decision-log.md")
    assert half != _EXECUTE_CAT
    mutated = {**w, "execute": w["execute"].replace(_EXECUTE_CAT, half, 1)}
    assert _unmet(mutated) == ["execute double-quotes both paths in its cat"]


def _slices_in_implementation_artifacts(w: dict) -> list[str]:
    return sorted(name for name, text in w.items() if _NO_SLICE_IN_IMPL in text)


def test_no_shipped_text_puts_a_slice_in_implementation_artifacts():
    """The run folder holds the log, so a slice there is the only sibling it has.

    Scans every Markdown file the skills and the user docs ship, outside the
    test fixtures (an old snapshot of execute.md keeps the old text on purpose).
    """
    hits = []
    for root in (_SKILLS, _REPO / "docs"):
        for path in root.rglob("*.md"):
            if "fixtures" in path.parts or ".analysis" in path.parts:
                continue
            if _NO_SLICE_IN_IMPL in path.read_text(encoding="utf-8"):
                hits.append(str(path.relative_to(_REPO)))
    assert hits == []
    assert _slices_in_implementation_artifacts(_pre_208(_world())) == ["execute"]


def test_every_slice_name_matches_finalizes_audit_glob():
    """Finalize audits `dlog-slice-*.md`: each surface's slice name has that shape,
    and every surface rules out Reading a log too large to Read."""
    w = _world()
    for name in ("resolve", "formalize", "parent", "execute"):
        text = _norm(w[name])
        names = re.findall(r"dlog-slice-[^`/ ]*?\.md", text)
        assert names, name
        assert all(re.fullmatch(r"dlog-slice-[^*]+-<n>\.md|dlog-slice-[^*]+-\*\.md", n) for n in names), names
        assert "too large to Read affordably" in text, name
        assert _HEREDOC_RULE_RE.search(text), name


# --- the command each surface gives, run as written --------------------------


def _cat_command(text: str) -> str:
    found = _CAT_RE.findall(_norm(text))
    assert len(found) == 1, found
    return found[0]


def _v2_latch(store: Path) -> dict:
    """A green v2 latch, as `mem_recall.py latch` writes it: the guard's recall
    rules are armed, so the command is read by every rule a run has on."""
    return {
        "latch_version": 2,
        "run_id": _RUN,
        "backend": "jsonl",
        "store_ok": True,
        "recall": "on",
        "store": str(store),
        "fingerprint": "0123456789abcdef",
        "created_at": "2026-06-04T17:25:12Z",
    }


def _guard(command: str, cwd: Path, env: dict) -> tuple[int, str]:
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(event),
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )
    return proc.returncode, proc.stdout.strip()


@pytest.mark.skipif(not shutil.which("bash"), reason="needs bash to run the command")
@pytest.mark.parametrize("project_name", ["project", "my project"])
@pytest.mark.parametrize("surface", ["resolve", "formalize", "parent", "execute"])
def test_the_cat_command_clears_the_guard_and_appends(tmp_path: Path, surface: str, project_name: str):
    project = tmp_path / project_name
    folder = project / "_bmad-output" / "ultracode-goal" / _RUN
    folder.mkdir(parents=True)
    home = tmp_path / "home"
    store = home / ".ultracode-goal" / "recall"
    store.mkdir(parents=True)
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / ".mem-state.json").write_text(json.dumps(_v2_latch(store)), encoding="utf-8")
    env = {"HOME": str(home), "USERPROFILE": str(home), "ULTRACODE_IMPL_ARTIFACTS": str(impl)}

    command = _cat_command(_FILES[surface].read_text(encoding="utf-8"))
    for placeholder, value in {
        "{project-root}": project.as_posix(),
        "<log folder>": folder.as_posix(),
        "<run folder>": _RUN if surface == "resolve" else folder.as_posix(),
        "<story_id>": "7-1",
        "<label>": "stage1",
        "<n>": "1",
    }.items():
        command = command.replace(placeholder, value)
    assert not re.search(r"[<>{}]\w|\w[<>{}]", command.replace(" >> ", " ")), command

    words = shlex.split(command)
    assert len(words) == 4 and words[0] == "cat" and words[2] == ">>", words
    slice_path, log_path = Path(words[1]), Path(words[3])
    assert slice_path.parent == log_path.parent == folder, "the slice sits beside the log"
    head = "## 2026-06-04 session\n"
    log_path.write_text(head, encoding="utf-8")
    entry = "Closed d-1: the guard denied `git commit` and the operator's hook was fixed.\n"
    slice_path.write_text(entry, encoding="utf-8")

    # Control: the guard is armed in this world and reads Bash command strings.
    code, out = _guard(f"cat {store.as_posix()}/runs/x.jsonl", project, env)
    assert code == 2 and "deny" in out, out

    if " " in project_name:
        # Twin: bare, a path with a space splits into two words, so the
        # redirect lands on a stray file and the log never gets the entry.
        bare = subprocess.run(["bash", "-c", _bare(command)], cwd=project, capture_output=True, text=True)
        assert bare.returncode != 0, bare
        assert log_path.read_text(encoding="utf-8") == head, "the bare form must not append"

    assert _guard(command, project, env) == (0, ""), "the guard must make no decision on the append"
    subprocess.run(["bash", "-c", command], cwd=project, check=True)
    assert log_path.read_text(encoding="utf-8") == head + entry
    assert slice_path.read_text(encoding="utf-8") == entry, "the slice is kept"
