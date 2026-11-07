#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for marking a story's new files before the step-2 sweep (issue #217).

Execute step 2 swept while the story's new files were still untracked, so a
conformance gate scoped to git's file list (a `git ls-files`-based check)
skipped them and reported green. Its red waited for step 5, after the commit,
where the fix cost an amend and two more full sweeps.

`references/execute.md` step 2 now marks the story's own new files
intent-to-add (`git add -N -- <files>`, one call of its own) before every sweep,
taken file by file from the `??` entries of `git status --porcelain
--untracked-files=all`, never a folder, a sibling story's tests, the scratch or
evidence folder, a run marker or an ignored path, and reads `git status
--porcelain --no-renames` again after a non-zero exit. A marked file the story
will not ship is deleted or moved out of the tree, then `git add -- <path>`
clears its entry; no `git reset`, `git rm` or `git restore` is prescribed. Step
4 stages every marked path, a deleted one too, since the guard refuses any
commit while a mark is left. Step 5 names what a mark cannot reach. The docs
(`docs/how-it-works.md`, `docs/architecture.md`) and `references/preflight.md`
say the same.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the text with the #217 wording taken out (the pre-edit text) and
against one-clause mutants it must reject. A locality twin moves the step-2
paragraph out of step 2. Then a temporary repository checks each git fact the
prose relies on, so a git that behaves otherwise reds here rather than in a
run. Stated limit: this is a presence proof over prose. It shows the
instruction is in the file, not that an executor obeys it.

Stdlib + pytest only.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_HOW_IT_WORKS = _REPO / "docs" / "how-it-works.md"
_ARCHITECTURE = _REPO / "docs" / "architecture.md"

_HEAD = "**Mark this story's new files intent-to-add before every sweep this step runs.**"
_NEXT_HEAD = "**Scope the sweep on three axes, not one.**"
_STEP4_CLEARING = (
    "and a mark on a path `HEAD` already holds is staged in place like the rest; a marked new file the story will not "
    "ship is moved aside into `.scratch-<story_id>/` before that call, so staging its path drops its entry the same "
    "way, and moved back after it, untracked again (deleted instead only when nothing needs it): "
)
_STEP4_SENTENCE = (
    "Those paths take in every path step 2 marked intent-to-add, a marked file since deleted included (staging a "
    "deleted file's path drops its entry), " + _STEP4_CLEARING + "the guard refuses any commit while the index holds "
    "a mark, naming each one, because the commit would leave that file out while the index keeps it, or, for a mark "
    "on a path `HEAD` holds, delete `HEAD`'s file."
)
# The round-2 wording: moving a `DA` mark aside stages its deletion.
_STEP4_CLEARING_R2 = (
    "and a marked file the story will not ship is moved out of the work tree before that call, so staging its path "
    "drops its entry the same way, and moved back after it, untracked again (deleted instead only when nothing needs "
    "it): "
)
# The round-1 wording of the clause a review replaced: deleting or moving out
# lost a file the tree still needs.
_STEP4_LOSES_THE_FILE = (
    "is deleted or moved out of the tree before that call, so its path drops out the same way: "
)
_STEP4_ANCHOR = "stage this story's source + test paths explicitly (`git add <this story's paths>`) instead."
_STEP5_SENTENCE = (
    "Step 2's marks show a story's **new** files to a **conformance gate scoped to *tracked* files** (a "
    "`git ls-files`-based ref/ownership/architecture-boundary check) before the commit, but three kinds of new file "
    "still hide from it there, so the gate skips them and reports green at step 2, then reds the instant the commit "
    "tracks them: a generated or `.gitignore`d file, which no mark can reach; a file created after step 2's last mark; "
    "and, for a gate that reads the staged content (one built on git grep --cached, say), every new file, since a mark "
    "holds an empty blob."
)
# The sentence it replaced, which the pre-edit text gets back.
_STEP5_PRE = (
    "Step 2's pre-commit run cannot see a **conformance gate scoped to *tracked* files** (a `git ls-files`-based "
    "ref/ownership/architecture-boundary check): a story's **new** files are still untracked at step 2, so the gate "
    "skips them and reports green, then reds the instant the commit tracks them (generated or `.gitignore`d files hide "
    "the same way)."
)
_DOCS_CHAIN = (
    "→ mark the story's new files intent-to-add (`git add -N`), so a conformance gate scoped to git's tracked files "
    "sees them, then run tests/lint/build and **print the raw output** as evidence →"
)
_DOCS_CHAIN_PRE = "→ run tests/lint/build and **print the raw output** as evidence →"
_DOCS_BECAUSE = (
    "because a new file no mark reaches (a generated or ignored one, or one made after the last mark) is untracked "
    "until the commit, so a tracked-files conformance gate can only red on it once it lands;"
)
_DOCS_BECAUSE_PRE = (
    "because a story's new files are untracked until the commit, so a tracked-files conformance gate can only red "
    "once they land;"
)
_PREFLIGHT_SENTENCE = (
    "Before it reads them, the guard refuses any commit while the index holds an intent-to-add entry (`git add -N`, "
    "which `references/execute.md` step 2 makes for a story's new files), naming each one: `git show :<path>` reads "
    "such an entry as an empty blob, with no `test.skip(` in it, and the commit would leave the file out, so the "
    "proof never reads one."
)
_ARCHITECTURE_CLAUSE = (
    ", or while it holds an intent-to-add entry (`git add -N`, which Execute makes for a story's new files before its "
    "sweep), naming each one, since the commit would leave that file out, or, for a mark over a path HEAD holds, "
    "delete HEAD's file"
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _step(text: str, number: int) -> str:
    """One numbered step of the spine; the last is bounded at its own blank line."""
    start = text.index(f"\n{number}. ")
    following = text.find(f"\n{number + 1}. ", start)
    if following != -1:
        return text[start:following]
    end = text.find("\n\n", start)
    return text[start:] if end == -1 else text[start:end]


def _paragraph(text: str) -> str:
    """The step-2 paragraph, from its bold head to the blank line after it."""
    if _HEAD not in text:
        return ""
    start = text.index(_HEAD)
    end = text.find("\n\n", start)
    return text[start:] if end == -1 else text[start:end]


# --- the pre-edit text: the live text with the #217 wording taken out ---------


def _execute_pre_edit(text: str) -> str:
    text = text.replace(_paragraph(text) + "\n\n", "", 1)
    text = text.replace(_STEP4_ANCHOR + " " + _STEP4_SENTENCE, _STEP4_ANCHOR, 1)
    return text.replace(_STEP5_SENTENCE, _STEP5_PRE, 1)


def test_the_pre_edit_text_is_a_real_reconstruction():
    live = _read(_EXECUTE)
    pre = _execute_pre_edit(live)
    assert _HEAD not in pre and _STEP4_SENTENCE not in pre and _STEP5_SENTENCE not in pre
    assert _STEP5_PRE in _step(pre, 5)
    assert len(live) - len(pre) == (
        len(_paragraph(live)) + 2 + 1 + len(_STEP4_SENTENCE) + len(_STEP5_SENTENCE) - len(_STEP5_PRE)
    )
    # Step 2's opening line is followed again by the sweep-scope paragraph.
    opening = pre.index("\n2. Run the tests, lint, and build")
    assert pre[pre.index("\n\n", opening + 1) + 2 :].startswith(_NEXT_HEAD)


# --- execute.md step 2: the mark ------------------------------------------------


def _is_placed_in_step2(text: str) -> bool:
    """Once in the file, inside step 2, right after its opening line and before
    the sweep-scope paragraph, and in no other step."""
    if text.count(_HEAD) != 1:
        return False
    opening = text.index("\n2. Run the tests, lint, and build")
    after_opening = text[text.index("\n\n", opening + 1) + 2 :]
    return bool(
        _HEAD in _step(text, 2)
        and after_opening.startswith(_HEAD)
        and _paragraph(text) + "\n\n" + _NEXT_HEAD in text
        and not any(_HEAD in _step(text, n) for n in (0, 1, 3, 4, 5))
    )


def _marks_before_every_sweep(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(
        "before every sweep this step runs" in flat
        and "Before each sweep, a re-loop's and a resumed session's included" in flat
        and "skips a file git does not track" in flat
    )


def _takes_the_storys_own_untracked_files(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(
        "read `git status --porcelain --untracked-files=all` and take this story's own files from its `??` entries"
        in flat
        and "the source and test paths step 4 will stage, the acceptance tests this story's checklist lists among them"
        in flat
    )


def _marks_file_by_file_in_one_call(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(
        "Mark them in one call of its own, `git add -N -- <those paths>`, naming each file by its path" in flat
        and "Never name a folder (git marks every file under it)" in flat
    )


def _never_marks_what_is_not_the_storys(paragraph: str) -> bool:
    return (
        "Never name a folder (git marks every file under it), a sibling story's red-phase tests, anything under "
        "`.scratch-<story_id>/` or `evidence-<story_id>/`, a run marker, or a path git ignores."
    ) in _flat(paragraph)


def _a_mark_stages_no_content(paragraph: str) -> bool:
    return (
        "A mark puts the path in the index with no content (the index holds an empty blob for it): a gate that lists "
        "git's files now sees the file, nothing of it is staged, and step 4 still stages each one in full."
    ) in _flat(paragraph)


def _marking_again_is_safe(paragraph: str) -> bool:
    return (
        "Marking a path the index already holds changes nothing, so a re-loop or a resume runs this again safely."
    ) in _flat(paragraph)


_QUOTING = (
    "Without `-z`, any name git prints inside double quotes is C-quoted (a space, a double quote, a backslash or a "
    "control character in it, and under git's default `core.quotePath` a non-ASCII byte, which it writes as an octal "
    "escape: `\"my file.ts\"`, `\"caf\\303\\251.ts\"`): pass it as the name it stands for, its escapes decoded and "
    "quoted for the shell, never as printed, which matches no file."
)
# The round-2 wording: it named three characters and printed octal escapes
# whatever `core.quotePath` says.
_QUOTING_R2 = (
    "Without `-z`, git prints a name that holds a space, a double quote or a non-ASCII byte C-quoted, in double "
    "quotes with octal escapes (`\"my file.ts\"`, `\"caf\\303\\251.ts\"`): pass such a name as the file name "
    "it stands for, its escapes decoded and quoted for the shell, never as printed, which matches no file."
)


def _passes_a_quoted_name_as_the_file_name(paragraph: str) -> bool:
    return _QUOTING in _flat(paragraph)


_RECOVERY = (
    "A non-zero exit can leave some paths marked and others not: git refuses an ignored path and marks the rest, and a "
    "path that matches no file makes git exit 128 and mark none of the paths in the call. After any non-zero exit, "
    "read `git status --porcelain --no-renames --untracked-files=all` again, where a marked file shows as ` A`, and "
    "mark again, in one more call, every chosen path still listed `??` that git did not refuse as ignored. When that "
    "call fails too, mark nothing more: log the paths left unmarked in `.decision-log.md` and sweep, since step 5 runs "
    "the tracked-file gates on the commit."
)
# The round-1 wording: it covered only an ignored path, and marked nothing again.
_RECOVERY_PRE = (
    "A non-zero exit can leave some paths marked and others not (git refuses an ignored path and marks the rest): "
    "read `git status --porcelain --no-renames` again, where a marked file shows as ` A`, and mark no path git "
    "refused."
)
# The round-2 wording: nothing said what follows when the one more call fails.
_RECOVERY_R2 = (
    "A non-zero exit can leave some paths marked and others not: git refuses an ignored path and marks the rest, and a "
    "path that matches no file makes git exit 128 and mark none of the paths in the call. After any non-zero exit, "
    "read `git status --porcelain --no-renames --untracked-files=all` again, where a marked file shows as ` A`, and "
    "mark again, in one more call, every chosen path still listed `??` that git did not refuse as ignored."
)


def _rereads_status_after_a_failure(paragraph: str) -> bool:
    return _RECOVERY in _flat(paragraph)


_CLEARING = (
    "A mark on a path `HEAD` already holds (status `DA`) is cleared by staging the file in place, `git add -- <path>`, "
    "since moving it aside would stage its deletion. A marked new file the story will not ship (a sibling story's test "
    "marked by mistake, a mark another session left) is moved aside into "
    "`{workflow.implementation_artifacts}/.scratch-<story_id>/`, untracked in the run's own folder, then "
    "`git add -- <path>` clears its entry, and the file is moved back, where it is untracked again; delete it instead "
    "only when nothing needs it. The guard refuses any commit while the index holds a mark (step 4)."
)
# The round-1 wording: deleting or moving out lost a file the tree still needs.
_CLEARING_PRE = (
    "A marked file the story will not ship is deleted or moved out of the tree, then `git add -- <path>` clears its "
    "entry, since the guard refuses any commit while the index holds a mark (step 4)."
)
# The round-2 wording: moving a `DA` mark aside stages its deletion, and a
# file parked outside the tree is recorded nowhere.
_CLEARING_R2 = (
    "A marked file the story will not ship (a sibling story's test marked by mistake, a mark another session left) is "
    "moved out of the work tree, then `git add -- <path>` clears its entry, and the file is moved back, where it is "
    "untracked again; delete it instead only when nothing needs it. The guard refuses any commit while the index holds "
    "a mark (step 4)."
)


def _clears_a_mark_without_an_undo_command(paragraph: str) -> bool:
    flat = _flat(paragraph)
    return bool(_CLEARING in flat and not re.search(r"git (reset|rm|restore)\b", flat))


_DIRTY_TREE = (
    "A gate that fails on any uncommitted change (`git diff --exit-code`, say) reads a mark as one, as it reads an "
    "edit to a tracked file. Its red is the state before the commit, and does not count against the tests-ran marker "
    "this step writes once all three go green, only when its output names no path but those this story changes or "
    "marks: any other path in it (a stale generated file the story never touched, say) makes it a red. State in the "
    "printed evidence that the red was read that way. Step 5 runs that gate on the committed tree, where a red is a "
    "red."
)
# The round-1 wording: it left open whether that red holds back the marker.
_DIRTY_TREE_PRE = (
    "A gate that fails on any uncommitted change (`git diff --exit-code`, say) reads a mark as one, as it reads an "
    "edit to a tracked file: that red is the state before the commit, and step 5 runs the gate again on the "
    "committed tree."
)
# The round-2 wording: it exempted every red of such a gate, a real one too.
_DIRTY_TREE_R2 = (
    "A gate that fails on any uncommitted change (`git diff --exit-code`, say) reads a mark as one, as it reads an "
    "edit to a tracked file: that red is the state before the commit and does not count against the tests-ran marker "
    "this step writes once all three go green, since step 5 runs that gate on the committed tree, where a red is a "
    "red."
)


def _reads_a_dirty_tree_red_as_the_pre_commit_state(paragraph: str) -> bool:
    return _DIRTY_TREE in _flat(paragraph)


_CLAUSES = (
    _marks_before_every_sweep,
    _takes_the_storys_own_untracked_files,
    _marks_file_by_file_in_one_call,
    _passes_a_quoted_name_as_the_file_name,
    _never_marks_what_is_not_the_storys,
    _a_mark_stages_no_content,
    _marking_again_is_safe,
    _rereads_status_after_a_failure,
    _clears_a_mark_without_an_undo_command,
    _reads_a_dirty_tree_red_as_the_pre_commit_state,
)


def _rules_the_mark(text: str) -> bool:
    paragraph = _paragraph(text)
    return _is_placed_in_step2(text) and all(clause(paragraph) for clause in _CLAUSES)


def test_step2_marks_the_storys_new_files_before_every_sweep():
    assert _rules_the_mark(_read(_EXECUTE))


def test_the_mark_predicate_rejects_the_pre_edit_execute_md():
    pre = _execute_pre_edit(_read(_EXECUTE))
    assert not _rules_the_mark(pre)
    assert not _is_placed_in_step2(pre)
    assert not any(clause(_paragraph(pre)) for clause in _CLAUSES)


@pytest.mark.parametrize(
    ("clause", "old", "new"),
    [
        pytest.param(_marks_before_every_sweep, "before every sweep this step runs", "before the first sweep",
                     id="first-sweep-only"),
        pytest.param(_marks_before_every_sweep, ", a re-loop's and a resumed session's included", "",
                     id="no-reloop"),
        pytest.param(_takes_the_storys_own_untracked_files, "`git status --porcelain --untracked-files=all` and take",
                     "`git status --porcelain` and take", id="collapsed-folders"),
        pytest.param(_takes_the_storys_own_untracked_files, "take this story's own files from its `??` entries",
                     "take every path it lists", id="every-path"),
        pytest.param(_takes_the_storys_own_untracked_files, ", the acceptance tests this story's checklist lists "
                     "among them", "", id="no-acceptance-tests"),
        pytest.param(_marks_file_by_file_in_one_call, "`git add -N -- <those paths>`, naming each file by its path",
                     "`git add -N -- <the folders that hold them>`", id="folders"),
        pytest.param(_marks_file_by_file_in_one_call, "Mark them in one call of its own",
                     "Mark them in the sweep's own call", id="chained"),
        pytest.param(_never_marks_what_is_not_the_storys, " a sibling story's red-phase tests,", "", id="siblings"),
        pytest.param(_never_marks_what_is_not_the_storys, " anything under `.scratch-<story_id>/` or "
                     "`evidence-<story_id>/`,", "", id="scratch-and-evidence"),
        pytest.param(_never_marks_what_is_not_the_storys, ", or a path git ignores", "", id="ignored"),
        pytest.param(_a_mark_stages_no_content, "nothing of it is staged, and step 4 still stages each one in full",
                     "so step 4 need not stage it", id="mark-is-staged"),
        pytest.param(_marking_again_is_safe, "changes nothing", "fails", id="not-idempotent"),
        pytest.param(_passes_a_quoted_name_as_the_file_name, "never as printed", "as printed",
                     id="quoted-as-printed"),
        pytest.param(_passes_a_quoted_name_as_the_file_name, "its escapes decoded and quoted for the shell, ", "",
                     id="escapes-kept"),
        pytest.param(_passes_a_quoted_name_as_the_file_name, "a double quote, a backslash or a control character in "
                     "it", "or a double quote in it", id="only-space-and-quote"),
        pytest.param(_passes_a_quoted_name_as_the_file_name, "and under git's default `core.quotePath` a non-ASCII "
                     "byte, which it writes as an octal escape", "and a non-ASCII byte, always as an octal escape",
                     id="octal-always"),
        pytest.param(_rereads_status_after_a_failure, "`git status --porcelain --no-renames --untracked-files=all`",
                     "`git status --porcelain --untracked-files=all`", id="renames-on"),
        # A new folder collapses to one `?? <folder>/` entry, which lists no
        # chosen path under it.
        pytest.param(_rereads_status_after_a_failure, "`git status --porcelain --no-renames --untracked-files=all`",
                     "`git status --porcelain --no-renames`", id="recovery-collapsed-folders"),
        pytest.param(_rereads_status_after_a_failure, "can leave some paths marked and others not",
                     "marks nothing", id="nothing-marked"),
        pytest.param(_rereads_status_after_a_failure, ", and a path that matches no file makes git exit 128 and mark "
                     "none of the paths in the call", "", id="missing-path-unruled"),
        pytest.param(_rereads_status_after_a_failure, "and mark again, in one more call, every chosen path still "
                     "listed `??` that git did not refuse as ignored", "and mark no path git refused",
                     id="no-second-call"),
        pytest.param(_rereads_status_after_a_failure, " When that call fails too, mark nothing more: log the paths "
                     "left unmarked in `.decision-log.md` and sweep, since step 5 runs the tracked-file gates on the "
                     "commit.", "", id="second-failure-unruled"),
        pytest.param(_rereads_status_after_a_failure, "mark nothing more", "mark again until it succeeds",
                     id="retry-forever"),
        pytest.param(_rereads_status_after_a_failure, "log the paths left unmarked in `.decision-log.md` and ", "",
                     id="unmarked-unlogged"),
        pytest.param(_clears_a_mark_without_an_undo_command, "is moved aside into "
                     "`{workflow.implementation_artifacts}/.scratch-<story_id>/`, untracked in the run's own folder, "
                     "then `git add -- <path>` clears its entry", "is unmarked with `git reset -q -- <path>`",
                     id="reset"),
        pytest.param(_clears_a_mark_without_an_undo_command, "is moved aside into "
                     "`{workflow.implementation_artifacts}/.scratch-<story_id>/`, untracked in the run's own folder, "
                     "then `git add -- <path>` clears its entry", "is unmarked with `git rm --cached -- <path>`",
                     id="rm-cached"),
        pytest.param(_clears_a_mark_without_an_undo_command, ", and the file is moved back, where it is untracked "
                     "again; delete it instead only when nothing needs it", "", id="never-moved-back"),
        pytest.param(_clears_a_mark_without_an_undo_command, "A mark on a path `HEAD` already holds (status `DA`) is "
                     "cleared by staging the file in place, `git add -- <path>`, since moving it aside would stage its "
                     "deletion. ", "", id="tracked-path-moved-aside"),
        pytest.param(_clears_a_mark_without_an_undo_command, "moved aside into "
                     "`{workflow.implementation_artifacts}/.scratch-<story_id>/`, untracked in the run's own folder",
                     "moved out of the work tree", id="parked-outside-the-run"),
        pytest.param(_reads_a_dirty_tree_red_as_the_pre_commit_state, "Its red is the state before the commit",
                     "Its red is the story's", id="dirty-tree-red-is-the-storys"),
        pytest.param(_reads_a_dirty_tree_red_as_the_pre_commit_state, ", and does not count against the tests-ran "
                     "marker this step writes once all three go green", "", id="marker-held-back"),
        pytest.param(_reads_a_dirty_tree_red_as_the_pre_commit_state, ", only when its output names no path but those "
                     "this story changes or marks: any other path in it (a stale generated file the story never "
                     "touched, say) makes it a red", "", id="every-red-exempt"),
        pytest.param(_reads_a_dirty_tree_red_as_the_pre_commit_state, " State in the printed evidence that the red was "
                     "read that way.", "", id="reading-unstated"),
    ],
)
def test_each_mark_clause_rejects_its_one_clause_mutant(clause, old, new):
    paragraph = _flat(_paragraph(_read(_EXECUTE)))
    assert paragraph.count(old) == 1, "the mutant must change the one clause it names"
    mutant = paragraph.replace(old, new)
    assert mutant != paragraph, "the mutant must actually change the text"
    assert clause(paragraph)
    assert not clause(mutant)


@pytest.mark.parametrize(
    ("clause", "old", "new"),
    [
        pytest.param(_rereads_status_after_a_failure, _RECOVERY, _RECOVERY_PRE, id="recovery-round-1"),
        pytest.param(_rereads_status_after_a_failure, _RECOVERY, _RECOVERY_R2, id="recovery-round-2"),
        pytest.param(_clears_a_mark_without_an_undo_command, _CLEARING, _CLEARING_PRE, id="clearing-round-1"),
        pytest.param(_clears_a_mark_without_an_undo_command, _CLEARING, _CLEARING_R2, id="clearing-round-2"),
        pytest.param(_reads_a_dirty_tree_red_as_the_pre_commit_state, _DIRTY_TREE, _DIRTY_TREE_PRE,
                     id="dirty-tree-round-1"),
        pytest.param(_reads_a_dirty_tree_red_as_the_pre_commit_state, _DIRTY_TREE, _DIRTY_TREE_R2,
                     id="dirty-tree-round-2"),
        pytest.param(_passes_a_quoted_name_as_the_file_name, _QUOTING, _QUOTING_R2, id="quoting-round-2"),
        # Not an earlier wording: round 1 had no such sentence, so its twin is
        # the sentence deleted.
        pytest.param(_passes_a_quoted_name_as_the_file_name, " " + _QUOTING, "", id="quoting-deleted"),
    ],
)
def test_each_reviewed_clause_rejects_its_earlier_wording(clause, old, new):
    paragraph = _flat(_paragraph(_read(_EXECUTE)))
    assert paragraph.count(old) == 1
    mutant = paragraph.replace(old, new, 1)
    assert mutant != paragraph
    assert clause(paragraph) and not clause(mutant)


@pytest.mark.parametrize("where", ["step4", "step5", "after-the-scope-paragraph"])
def test_the_mark_is_anchored_to_the_top_of_step2(where):
    """Locality twin: the paragraph moved out of place must red, not only the
    paragraph removed."""
    live = _read(_EXECUTE)
    paragraph = _paragraph(live)
    pre = _execute_pre_edit(live)
    if where == "step4":
        mutant = pre.replace(_STEP4_ANCHOR, _STEP4_ANCHOR + " " + paragraph, 1)
    elif where == "step5":
        step5 = _step(pre, 5)
        mutant = pre.replace(step5, step5 + " " + paragraph, 1)
    else:
        scope = pre.index(_NEXT_HEAD)
        end = pre.index("\n\n", scope)
        mutant = pre[:end] + "\n\n" + paragraph + pre[end:]
    assert mutant != pre and _HEAD in mutant
    assert not _is_placed_in_step2(mutant)
    # The clauses still read, so only the placement check catches the move.
    assert all(clause(_paragraph(mutant)) for clause in _CLAUSES)


def test_the_new_prose_holds_no_em_dash_and_no_numbered_line():
    """Step slicers split on a newline and `N. `, so the paragraph starts no
    line with a number, and nothing #217 added holds an em dash."""
    live = _read(_EXECUTE)
    for added in (_paragraph(live), _STEP4_SENTENCE, _STEP5_SENTENCE):
        assert chr(0x2014) not in added
    assert not re.search(r"(?m)^\d+\. ", _paragraph(live))
    numbered = re.findall(r"(?m)^(\d+)\. ", live)
    assert numbered == re.findall(r"(?m)^(\d+)\. ", _execute_pre_edit(live))


# --- execute.md step 4: every mark is staged -----------------------------------


def _step4_stages_every_mark(text: str) -> bool:
    step4 = _flat(_step(text, 4))
    return bool(
        _STEP4_ANCHOR + " " + _STEP4_SENTENCE in step4
        and "two distinct tool calls" in step4
        and "sibling" in step4
    )


def test_step4_stages_every_marked_path():
    assert _step4_stages_every_mark(_read(_EXECUTE))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_STEP4_ANCHOR + " " + _STEP4_SENTENCE, _STEP4_ANCHOR, id="pre-edit"),
        pytest.param(", a marked file since deleted included (staging a deleted file's path drops its entry)", "",
                     id="deleted-left"),
        pytest.param("every path step 2 marked", "the paths step 2 marked that still exist", id="existing-only"),
        pytest.param("the guard refuses any commit while the index holds a mark, naming each one",
                     "the commit carries any mark left", id="mark-rides"),
        pytest.param(_STEP4_CLEARING, "and a marked file the story will not ship " + _STEP4_LOSES_THE_FILE,
                     id="round-1-loses-the-file"),
        pytest.param(_STEP4_CLEARING, _STEP4_CLEARING_R2, id="round-2-moves-a-tracked-mark-aside"),
        pytest.param(", or, for a mark on a path `HEAD` holds, delete `HEAD`'s file", "",
                     id="tracked-path-deletion-unsaid"),
    ],
)
def test_the_step4_predicate_rejects_its_mutants(old, new):
    text = _read(_EXECUTE)
    assert text.count(old) == 1, "the mutant must change the one clause it names"
    mutant = text.replace(old, new, 1)
    assert mutant != text
    assert not _step4_stages_every_mark(mutant)


def test_the_step4_sentence_is_anchored_to_step4():
    text = _read(_EXECUTE)
    moved = text.replace(" " + _STEP4_SENTENCE, "", 1)
    step5 = _step(moved, 5)
    moved = moved.replace(step5, step5 + " " + _STEP4_SENTENCE, 1)
    assert _STEP4_SENTENCE in moved
    assert not _step4_stages_every_mark(moved)


# --- execute.md step 5: what the marks leave ------------------------------------


def _step5_names_what_a_mark_cannot_reach(text: str) -> bool:
    step5 = _step(text, 5)
    return bool(
        _STEP5_SENTENCE in step5
        and "still untracked at step 2" not in step5
        and "**Run it cache-defeating.**" in step5
        and "tracking state* and not one of its bytes" in step5
    )


def test_step5_names_what_a_mark_cannot_reach():
    assert _step5_names_what_a_mark_cannot_reach(_read(_EXECUTE))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_STEP5_SENTENCE, _STEP5_PRE, id="pre-edit"),
        pytest.param("a generated or `.gitignore`d file, which no mark can reach; ", "", id="no-ignored"),
        pytest.param("a file created after step 2's last mark; ", "", id="no-late-file"),
        pytest.param("and, for a gate that reads the staged content (one built on git grep --cached, say), every new "
                     "file, since a mark holds an empty blob", "and nothing else", id="no-staged-content-gate"),
    ],
)
def test_the_step5_predicate_rejects_its_mutants(old, new):
    text = _read(_EXECUTE)
    assert text.count(old) == 1, "the mutant must change the one clause it names"
    mutant = text.replace(old, new, 1)
    assert mutant != text
    assert not _step5_names_what_a_mark_cannot_reach(mutant)


def test_execute_prescribes_no_undo_command_for_a_mark():
    """A `git reset`, `git rm` or `git restore` prefix would also allow its
    destructive forms (`git reset --hard` deletes a marked file, `git restore`
    empties it), and none is on the allowlist: the way out of a mark is to
    stage it, or delete it and stage its path."""
    for span in re.findall(r"`([^`\n]+)`", _read(_EXECUTE)):
        assert not re.match(r"git (reset|rm|restore)\b", span), span


# --- the docs and preflight.md --------------------------------------------------


def _docs_chain_marks(text: str) -> bool:
    flat = _flat(text)
    return bool(
        _DOCS_CHAIN in flat
        and _DOCS_BECAUSE in flat
        and "a red here means the story is not done and must be remediated and re-committed before it advances" in flat
    )


def test_how_it_works_marks_the_new_files_before_the_sweep():
    assert _docs_chain_marks(_read(_HOW_IT_WORKS))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(_DOCS_CHAIN, _DOCS_CHAIN_PRE, id="no-mark"),
        pytest.param(_DOCS_BECAUSE, _DOCS_BECAUSE_PRE, id="untracked-until-the-commit"),
    ],
)
def test_the_docs_predicate_rejects_the_pre_edit_wording(old, new):
    text = _read(_HOW_IT_WORKS)
    assert text.count(old) == 1
    assert not _docs_chain_marks(text.replace(old, new, 1))


def test_preflight_and_architecture_name_the_intent_to_add_refusal():
    preflight = _flat(_read(_PREFLIGHT))
    unskip = preflight[preflight.index("**Un-skip proof (production only).**") :]
    unskip = unskip[: unskip.index("**The commit/push guard anchors")]
    assert _PREFLIGHT_SENTENCE in unskip
    assert _PREFLIGHT_SENTENCE not in preflight.replace(_PREFLIGHT_SENTENCE, "", 1)
    architecture = _flat(_read(_ARCHITECTURE))
    assert "denies it when the staged index is empty or unreadable" + _ARCHITECTURE_CLAUSE + ";" in architecture
    assert "enforces seven invariants" in architecture
    assert "The marker, freshness, staged-index, intent-to-add, and recall-latch checks fail **closed**" in architecture


# --- the git facts the prose relies on ------------------------------------------
# Each one is a sentence above that a git which behaved otherwise would make
# false. Run against a temporary repository, immune to the runner's config.

_GIT_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def _env() -> dict:
    env = {key: value for key, value in os.environ.items() if key not in _GIT_ENV_VARS}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
    return env


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args], cwd=repo, capture_output=True, env=_env()
    )


def _git(repo: Path, *args: str) -> str:
    proc = _run(repo, *args)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return proc.stdout.decode("utf-8")


def _names(output: str) -> list[str]:
    return sorted(name for name in output.split("\0") if name)


def _write(repo: Path, rel: str, body: str = "content\n") -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _write(root, "base.txt", "base\n")
    _write(root, ".gitignore", "dist/\n")
    _git(root, "add", "--", "base.txt", ".gitignore")
    _git(root, "commit", "-qm", "seed")
    return root


def test_fact_a_mark_puts_a_new_file_in_gits_file_list(repo: Path):
    """The #217 fix itself: a `git ls-files`-scoped gate skips an untracked
    file and lists a marked one."""
    _write(repo, "src/new.ts")
    assert "src/new.ts" not in _names(_git(repo, "ls-files", "-z"))
    _git(repo, "add", "-N", "--", "src/new.ts")
    assert "src/new.ts" in _names(_git(repo, "ls-files", "-z"))


def test_fact_a_mark_stages_no_content(repo: Path):
    """The index holds the empty blob, porcelain `git diff --cached` leaves the
    mark out, `git show :<path>` reads it empty with exit 0, and git grep
    --cached finds none of its content (step 5's third kind)."""
    _write(repo, "src/new.ts", "needle\n")
    _git(repo, "add", "-N", "--", "src/new.ts")
    assert _git(repo, "show", ":src/new.ts") == ""
    assert _names(_git(repo, "diff", "--cached", "--name-only", "-z")) == []
    assert _run(repo, "grep", "--cached", "-q", "needle").returncode == 1
    empty = subprocess.run(
        ["git", "hash-object", "-t", "blob", "--stdin"], cwd=repo, input=b"", capture_output=True, env=_env()
    )
    assert empty.returncode == 0
    assert _git(repo, "ls-files", "-s", "--", "src/new.ts").split()[1] == empty.stdout.decode("ascii").strip()


def test_fact_a_folder_marks_every_file_under_it(repo: Path):
    """Why the step names each file: a folder marks a sibling story's test too."""
    _write(repo, "tests/this-story.spec.ts")
    _write(repo, "tests/sibling-story.spec.ts")
    _git(repo, "add", "-N", "--", "tests")
    assert {"tests/this-story.spec.ts", "tests/sibling-story.spec.ts"} <= set(_names(_git(repo, "ls-files", "-z")))


def test_fact_the_status_entries_list_each_file_with_untracked_files_all(repo: Path):
    """`--untracked-files=all` names each new file, where the default names
    only its folder."""
    _write(repo, "src/feature/a.ts")
    _write(repo, "src/feature/b.ts")
    default = _git(repo, "status", "--porcelain", "-z")
    every = _git(repo, "status", "--porcelain", "-z", "--untracked-files=all")
    assert "?? src/" in _names(default)
    assert {"?? src/feature/a.ts", "?? src/feature/b.ts"} <= set(_names(every))


def test_fact_a_nonzero_exit_can_still_mark_the_other_paths(repo: Path):
    """git refuses an ignored path, exits non-zero, and marks the rest."""
    _write(repo, "src/new.ts")
    _write(repo, "dist/out.js")
    proc = _run(repo, "add", "-N", "--", "src/new.ts", "dist/out.js")
    assert proc.returncode != 0
    listed = _names(_git(repo, "ls-files", "-z"))
    assert "src/new.ts" in listed and "dist/out.js" not in listed


def test_fact_a_name_printed_c_quoted_marks_nothing_as_printed(repo: Path):
    """Without `-z`, status C-quotes a name with a space, and one with a
    non-ASCII byte under git's default `core.quotePath` (this repository's
    config is the default: no global or system file is read); passed as
    printed it matches no file, and git exits 128 marking nothing. Passed as
    the file name it stands for, it marks."""
    _write(repo, "my file.ts")
    _write(repo, "caf\u00e9.ts")
    printed = _git(repo, "status", "--porcelain", "--untracked-files=all")
    quoted = [line[3:] for line in printed.splitlines() if line.startswith('?? "')]
    assert '"my file.ts"' in quoted
    # The non-ASCII name as git spells it (octal escapes, whatever the
    # platform's Unicode normal form).
    assert any(name.startswith('"caf\\') for name in quoted)
    proc = _run(repo, "add", "-N", "--", *quoted)
    assert proc.returncode == 128
    assert _names(_git(repo, "ls-files", "-z")) == [".gitignore", "base.txt"]
    _git(repo, "add", "-N", "--", "my file.ts", "caf\u00e9.ts")
    assert len(_names(_git(repo, "ls-files", "-z"))) == 4


def test_fact_a_path_that_matches_no_file_marks_none_in_the_call(repo: Path):
    """Exit 128, and the good path in the same call stays `??`: the step marks
    it again in one more call."""
    _write(repo, "src/new.ts")
    proc = _run(repo, "add", "-N", "--", "src/new.ts", "src/missing.ts")
    assert proc.returncode == 128
    assert "?? src/new.ts" in _names(
        _git(repo, "status", "--porcelain", "--no-renames", "--untracked-files=all", "-z")
    )
    # Without `--untracked-files=all` the new folder hides the path.
    assert _names(_git(repo, "status", "--porcelain", "--no-renames", "-z")) == ["?? src/"]
    _git(repo, "add", "-N", "--", "src/new.ts")
    assert " A src/new.ts" in _names(_git(repo, "status", "--porcelain", "--no-renames", "-z"))


def test_fact_moving_a_mark_aside_and_back_leaves_the_file_untracked(repo: Path):
    """The way out of a mark on a new file the tree still needs: aside into
    the untracked scratch folder, stage the path, back. The file keeps its
    bytes and is untracked again."""
    _write(repo, "tests/sibling.spec.ts", "sibling story's test\n")
    _git(repo, "add", "-N", "--", "tests/sibling.spec.ts")
    scratch = repo / "_bmad-output" / ".scratch-1-1"
    scratch.mkdir(parents=True)
    (repo / "tests/sibling.spec.ts").rename(scratch / "sibling.spec.ts")
    _git(repo, "add", "--", "tests/sibling.spec.ts")
    (scratch / "sibling.spec.ts").rename(repo / "tests/sibling.spec.ts")
    assert "?? tests/sibling.spec.ts" in _names(_git(repo, "status", "--porcelain", "--untracked-files=all", "-z"))
    assert (repo / "tests/sibling.spec.ts").read_text(encoding="utf-8") == "sibling story's test\n"


def test_fact_a_mark_on_a_tracked_path_is_cleared_in_place_not_aside(repo: Path):
    """A mark over a path HEAD holds (`DA`): moved aside, staging the path
    stages its deletion; staged in place, the entry is HEAD's file again."""
    _git(repo, "rm", "-q", "--cached", "--", "base.txt")
    _git(repo, "add", "-N", "--", "base.txt")
    assert "DA base.txt" in _names(_git(repo, "status", "--porcelain", "--no-renames", "-z"))
    (repo / "base.txt").rename(repo / "parked.txt")
    _git(repo, "add", "--", "base.txt")
    (repo / "parked.txt").rename(repo / "base.txt")
    aside = _names(_git(repo, "status", "--porcelain", "--no-renames", "-z"))
    assert "D  base.txt" in aside and "?? base.txt" in aside, "moved aside, the commit would delete it"
    _git(repo, "add", "--", "base.txt")
    assert _names(_git(repo, "status", "--porcelain", "--no-renames", "-z")) == []


def test_fact_marking_again_changes_nothing(repo: Path):
    """A mark on a marked path, or on a path staged with its content, is a
    no-op that exits 0, so a re-loop or a resume can run step 2 again."""
    _write(repo, "src/marked.ts")
    _write(repo, "src/staged.ts", "staged content\n")
    _git(repo, "add", "-N", "--", "src/marked.ts")
    _git(repo, "add", "--", "src/staged.ts")
    before = _git(repo, "ls-files", "-s", "-z")
    _git(repo, "add", "-N", "--", "src/marked.ts", "src/staged.ts")
    assert _git(repo, "ls-files", "-s", "-z") == before


def test_fact_no_renames_shows_a_mark_as_space_a(repo: Path):
    """With `--no-renames` a mark reads ` A`; with rename detection on, a
    moved tracked file's mark pairs into an ` R` entry instead."""
    _write(repo, "src/old.ts", "a body long enough to pair as a rename\n" * 3)
    _git(repo, "add", "--", "src/old.ts")
    _git(repo, "commit", "-qm", "old")
    (repo / "src/old.ts").rename(repo / "src/new.ts")
    _git(repo, "add", "-N", "--", "src/new.ts")
    plain = _names(_git(repo, "status", "--porcelain", "--no-renames", "-z"))
    assert " A src/new.ts" in plain
    renamed = _names(_git(repo, "-c", "status.renames=true", "status", "--porcelain", "-z"))
    assert " R src/new.ts" in renamed and " A src/new.ts" not in renamed


def test_fact_staging_a_marked_path_clears_the_mark(repo: Path):
    """`git add -- <path>` stages a marked file in full, and for one deleted or
    moved out of the tree it drops the entry: no undo command is needed."""
    for rel in ("src/ships.ts", "src/deleted.ts", "src/moved.ts"):
        _write(repo, rel, "body\n")
    _git(repo, "add", "-N", "--", "src/ships.ts", "src/deleted.ts", "src/moved.ts")
    (repo / "src/deleted.ts").unlink()
    (repo / "src/moved.ts").rename(repo / "elsewhere.ts")
    _git(repo, "add", "--", "src/ships.ts", "src/deleted.ts", "src/moved.ts")
    status = _names(_git(repo, "status", "--porcelain", "--no-renames", "-z"))
    assert "A  src/ships.ts" in status
    assert not any(entry.endswith(("src/deleted.ts", "src/moved.ts")) for entry in status)
    visible = _names(_git(repo, "diff", "--cached", "--ita-visible-in-index", "--name-only", "--no-renames", "-z"))
    assert visible == _names(_git(repo, "diff", "--cached", "--name-only", "--no-renames", "-z"))


def test_fact_a_commit_leaves_a_mark_out_while_the_index_keeps_it(repo: Path):
    """Why the guard refuses a commit while a mark is left."""
    _write(repo, "src/staged.ts")
    _write(repo, "src/marked.ts")
    _git(repo, "add", "--", "src/staged.ts")
    _git(repo, "add", "-N", "--", "src/marked.ts")
    _git(repo, "commit", "-qm", "story")
    committed = _names(_git(repo, "ls-tree", "-r", "--name-only", "-z", "HEAD"))
    assert "src/staged.ts" in committed and "src/marked.ts" not in committed
    assert "src/marked.ts" in _names(_git(repo, "ls-files", "-z"))


def test_fact_a_dirty_tree_gate_reads_a_mark_as_a_change(repo: Path):
    """On a story that only adds files, `git diff --exit-code` passes with the
    file untracked and fails once it is marked: the state before the commit."""
    _write(repo, "src/new.ts")
    assert _run(repo, "diff", "--exit-code", "--quiet").returncode == 0
    _git(repo, "add", "-N", "--", "src/new.ts")
    assert _run(repo, "diff", "--exit-code", "--quiet").returncode == 1
