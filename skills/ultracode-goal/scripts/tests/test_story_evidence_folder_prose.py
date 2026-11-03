#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""The story's evidence folder, which outlives its scratch directory (#196).

Execute removes `.scratch-<story_id>/` once step 5's re-verify goes green, and
the gate's backfill removes it again after its claim check recreates it. The
red-phase capture, the sweep logs, the coupled-stories measurements and the
planted-defect runs that trace, the gate and the story record cite lived there,
so following the rule deleted them before trace read them, and every story of
one Epic logged keeping the folder as a deviation.

The scratch lifetime is unchanged. The evidence goes to
`{workflow.implementation_artifacts}/evidence-<story_id>/` instead, which no
step removes, and each place that owes such a file points there. This pins:

- the rule, between step 0 and step 1 of the story loop, with what goes there
  (captured output and its notes), the mutation ledger's own path, each capture named
  by the step that wrote it and the commit `HEAD` named then (the next free
  number when that name is taken), an earlier run's files never cited, and
  the folder staying untracked, off the evidence commit's list of paths;
- the five places that write evidence or remove scratch point at it;
- no sentence on any reference removes the folder, by its name with or without
  the slash or as the evidence folder, other than the three that say no step
  removes it, and none names it with the dot of the `.evidence-owed-<story_id>`
  marker;
- that `formalize_check.py`'s story-file and leaked-artifact scans skip a
  file inside a top-level `evidence-*` or `.scratch-*` folder, and read the
  same file anywhere else, and that the two marker globs never read the
  evidence folder.

Each prose predicate is checked, as its anti-vacuous twin, against a
one-clause mutant it must reject.

Run: uv run --with pytest pytest skills/ultracode-goal/scripts/tests/test_story_evidence_folder_prose.py -v
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REFS = SCRIPTS.parent / "references"
EXECUTE = (REFS / "execute.md").read_text(encoding="utf-8")
GATE = (REFS / "gate.md").read_text(encoding="utf-8")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


_RULE = (
    "**Evidence never goes in scratch.** The scratch directory is removed before the story advances, while trace, the "
    "gate and the story record cite their evidence after that, so the story's evidence has a folder of its own, "
    "`{workflow.implementation_artifacts}/evidence-<story_id>/`, which no step removes."
)
_WHAT_GOES_THERE = (
    "The red-phase capture (step 1's, on a stack where Stage 3 could not generate the ATDD scaffold), a sweep log the "
    "record or the gate cites, a coupled-stories measurement and a planted-defect run (a case shown red against a "
    "defect planted for it) go there; a runner or harness built only to produce them stays in scratch."
)
_RUNNABLE = (
    "It holds captured output and the notes recorded on it (the red count `references/gate.md`'s non-web item 4 "
    "records beside a red-phase capture), nothing runnable: it has no dot prefix, so on a tracked tree a repo-wide tool "
    "can reach it."
)
_LEDGER = "The mutation ledger keeps its own name-pinned path (step 2)."
_CYCLES = (
    "Name each capture by the step that wrote it and the commit `HEAD` named when it ran "
    "(`sweep-step2-<short sha>.log`, `sweep-step5-<short sha>.log`, `sweep-backfill-<short sha>.log`), and give a "
    "name already taken the next free number (`-2`), so no capture overwrites another: step 2's sweep can run at the "
    "`HEAD` the cycle before it measured at step 5 (when that cycle's gate committed no backfill), and the backfill's "
    "sweep runs at the `HEAD` step 5 measured. A file already in the folder when step 0 writes a fresh baseline is an "
    "earlier run's, never cited as this run's."
)
# The first fix's wording: one name per measured commit, which step 2 and the
# backfill share with the step 5 before them.
_CYCLES_FIRST = (
    "A file a later cycle would write again carries the commit it measured in its name (`sweep-full-<short sha>.log`), "
    "so a re-loop's capture never overwrites one an earlier verdict cites, and a file already in the folder when step "
    "0 writes a fresh baseline is an earlier run's, never cited as this run's."
)
_UNTRACKED = (
    "On a tracked artifact tree the folder stays untracked, as the mutation ledger does: the gate's evidence commit "
    "stages its own list of paths, and this folder is not on it."
)
# The names as a run files them, a taken name's next free number included.
_FILED = (
    "red-phase-step1-1a2b3c4.log",
    "sweep-step2-1a2b3c4.log",
    "sweep-step5-1a2b3c4.log",
    "sweep-step5-1a2b3c4-2.log",
    "sweep-backfill-1a2b3c4.log",
    "planted-defect-step2-1a2b3c4.log",
)


def _between_step_0_and_step_1(text: str) -> str:
    start = text.index("\n0. **Set the current story and record its baseline commit**")
    return text[start : text.index("\n1. `ucg-create-story`", start)]


def _states_the_evidence_folder(text: str) -> bool:
    try:
        between = _between_step_0_and_step_1(text)
    except ValueError:
        return False
    paragraph = next((p for p in between.split("\n\n") if p.startswith("**Evidence never goes in scratch.**")), "")
    rule = (_RULE, _WHAT_GOES_THERE, _RUNNABLE, _LEDGER, _CYCLES, _UNTRACKED)
    return " ".join(rule) == _flat(paragraph).strip()


def test_execute_gives_the_evidence_a_folder_no_step_removes():
    assert _states_the_evidence_folder(EXECUTE)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The second fix the report offered: keep scratch until the verdict, which
        # still deletes evidence cited after the fact.
        (_RULE, "**Evidence never goes in scratch.** Keep the scratch directory until the story's verdict is logged."),
        (", which no step removes.", "."),
        ("a sweep log the record or the gate cites, ", ""),
        ("a coupled-stories measurement and a planted-defect run", "a planted-defect run"),
        ("; a runner or harness built only to produce them stays in scratch", ""),
        (" " + _RUNNABLE, ""),
        # The first wording, which left no room for gate.md's red count beside a capture.
        ("It holds captured output and the notes recorded on it (the red count `references/gate.md`'s non-web item 4 "
         "records beside a red-phase capture), nothing runnable", "It holds captured output only, nothing runnable"),
        # The first reason, which a backfill commit made wrong.
        ("step 2's sweep can run at the `HEAD` the cycle before it measured at step 5 (when that cycle's gate committed "
         "no backfill), and", "step 2's sweep runs at the `HEAD` the cycle before it measured at step 5, and"),
        (" " + _LEDGER, ""),
        # Named by the measured commit alone, step 2 and the backfill overwrite step 5's log.
        (_CYCLES, _CYCLES_FIRST),
        ("the step that wrote it and the commit `HEAD` named", "the commit `HEAD` named"),
        (", and give a name already taken the next free number (`-2`), so no capture overwrites another",
         ", so no capture overwrites another"),
        # A later run of the same story cites what an earlier run left.
        (" A file already in the folder when step 0 writes a fresh baseline is an earlier run's, never cited as this "
         "run's.", ""),
        (" " + _UNTRACKED, ""),
        # The folder moved out of the story loop's step 0 slot.
        ("\n\n" + _RULE, "\n\nThe folder rule is in the gate. " + _RULE),
    ],
)
def test_evidence_folder_predicate_rejects_a_weaker_rule(old, new):
    live = EXECUTE
    mutant = live.replace(old, new)
    assert mutant != live, "the mutant must actually change the text"
    assert not _states_the_evidence_folder(mutant)


def test_the_evidence_folder_predicate_rejects_the_rule_outside_the_story_loop():
    between = _between_step_0_and_step_1(EXECUTE)
    paragraph = next(p for p in between.split("\n\n") if p.startswith("**Evidence never goes in scratch.**"))
    moved = EXECUTE.replace("\n\n" + paragraph, "", 1) + "\n\n" + paragraph + "\n"
    assert not _states_the_evidence_folder(moved)


# --- every place that writes evidence or removes scratch points there --------------

_POINTERS = (
    ("execute.md",
     "RUN them, and capture that run's raw output to a file in `{workflow.implementation_artifacts}/evidence-<story_id>/` "
     "(\"Evidence never goes in scratch\", above)."),
    ("execute.md",
     "capture for each clause a run on the earlier story's tree, to a file in the earlier story's "
     "`{workflow.implementation_artifacts}/evidence-<story_id>/` (\"Evidence never goes in scratch\", above), showing"),
    ("gate.md",
     "3. **Capture that run's raw output to a file** in `{workflow.implementation_artifacts}/evidence-<story_id>/`, "
     "which no step removes (`references/execute.md`, \"Evidence never goes in scratch\")."),
    ("gate.md",
     "and `references/execute.md` step 0 has it removed before the story advances. The story's "
     "`evidence-<story_id>/` folder stays: no step removes it (`references/execute.md`, \"Evidence never goes in "
     "scratch\")."),
    # Step 2's capture-then-slice log, which a record or a gate may cite.
    ("execute.md",
     "Redirect to a file (`cmd > <log> 2>&1`) and read the summary out of it as a second call. A log the record or the "
     "gate will cite goes in `evidence-<story_id>/` (\"Evidence never goes in scratch\", above)."),
)
_PRE_EDIT_POINTERS = (
    ("execute.md", "RUN them, and capture that run's raw output to a file under `{workflow.implementation_artifacts}`."),
    ("execute.md",
     "capture for each clause a run on the earlier story's tree, to a file under `{workflow.implementation_artifacts}`, "
     "showing"),
    ("gate.md", "3. **Capture that run's raw output to a file** under `{workflow.implementation_artifacts}`."),
    ("gate.md", "and `references/execute.md` step 0 has it removed before the story advances."),
    ("execute.md", "Redirect to a file (`cmd > <log> 2>&1`) and read the summary out of it as a second call."),
)


def _points_at_the_folder(execute: str, gate: str) -> bool:
    texts = {"execute.md": _flat(execute), "gate.md": _flat(gate)}
    return all(sentence in texts[name] for name, sentence in _POINTERS)


def test_each_place_that_owes_evidence_points_at_the_folder():
    assert _points_at_the_folder(EXECUTE, GATE)


@pytest.mark.parametrize(("pointer", "pre_edit"), list(zip(_POINTERS, _PRE_EDIT_POINTERS)))
def test_pointer_predicate_rejects_the_pre_edit_wording(pointer, pre_edit):
    (name, sentence), (_, old) = pointer, pre_edit
    execute, gate = _flat(EXECUTE), _flat(GATE)
    if name == "execute.md":
        mutant = execute.replace(sentence, old)
        assert mutant != execute
        assert not _points_at_the_folder(mutant, gate)
    else:
        mutant = gate.replace(sentence, old)
        assert mutant != gate
        assert not _points_at_the_folder(execute, mutant)


@pytest.mark.parametrize(
    ("text", "start"),
    [(GATE, "3. **Capture that run's raw output to a file**"), (EXECUTE, "**Capture, then slice")],
)
def test_a_touched_line_has_no_em_dash_left(text, start):
    """Each line these pointers touched held one em dash, rewritten with them."""
    line = next(line for line in text.splitlines() if line.startswith(start))
    assert chr(0x2014) not in line


# --- nothing removes the folder, and nothing names it with the marker's dot -------

_REMOVE = re.compile(
    r"\b(?:remov\w*|delet\w*|rm -|clean\w* up|discard\w*|wip\w*|eras\w*|prun\w*|purg\w*|clear\w* (?:out|away)"
    r"|drop\w*)\b",
    re.I,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*(\"-])")


# The folder by its name, with or without the slash, or by what it is.
_FOLDER = re.compile(r"evidence-(?:<[^>]+>|\*)|evidence (?:folder|directory)", re.I)
# The three sentences that say no step removes the folder, each exempt by its own
# text, so a removal added to one of them makes it a sentence the scan lists.
_DEFINING = (
    _RULE,
    "The story's `evidence-<story_id>/` folder stays: no step removes it (`references/execute.md`, \"Evidence never "
    "goes in scratch\").",
    "**Capture that run's raw output to a file** in `{workflow.implementation_artifacts}/evidence-<story_id>/`, which "
    "no step removes (`references/execute.md`, \"Evidence never goes in scratch\").",
)


def _removals_of_the_folder(texts: dict[str, str]) -> list[str]:
    """Each sentence that names the folder beside a remove verb, other than the three that define it."""
    found = []
    for name, text in texts.items():
        for sentence in _SENTENCE.split(_flat(text)):
            if _FOLDER.search(sentence) and _REMOVE.search(sentence) and sentence not in _DEFINING:
                found.append(f"{name}: {sentence[:120]}")
    return found


def _references() -> dict[str, str]:
    surfaces = {ref.name: ref.read_text(encoding="utf-8") for ref in sorted(REFS.glob("*.md"))}
    surfaces["SKILL.md"] = (REFS.parent / "SKILL.md").read_text(encoding="utf-8")
    return surfaces


def test_no_reference_removes_the_evidence_folder():
    assert _removals_of_the_folder(_references()) == []


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        ("finalize.md", None, "Remove each story's `evidence-<story_id>/` once the Epic's verdict is logged."),
        # The folder named without its slash.
        ("finalize.md", None, "Delete `{workflow.implementation_artifacts}/evidence-<story_id>` once the Epic advances."),
        # The folder named by what it is.
        ("gate.md", None, "Once the verdict is logged, remove the story's evidence folder."),
        # The verbs beside remove and delete.
        ("finalize.md", None, "Discard `evidence-<story_id>/` once the Epic advances."),
        ("finalize.md", None, "Wipe the story's `evidence-<story_id>/` at the Epic's close."),
        ("finalize.md", None, "Erase `evidence-<story_id>/` before the next run."),
        ("finalize.md", None, "Prune `evidence-<story_id>/` to the last cycle's captures."),
        ("preflight.md", None, "Purge each `evidence-<story_id>/` an earlier run left."),
        ("execute.md", None, "Clear out the story's evidence folder before step 1."),
        ("gate.md", None, "Drop `evidence-<story_id>` once the verdict is logged."),
        # The folder as a glob, by another placeholder, or as a directory.
        ("finalize.md", None, "Remove every `evidence-*` folder once the Epic advances."),
        ("finalize.md", None, "Delete each `evidence-<id>/` an earlier run left."),
        ("gate.md", None, "Remove the story's evidence directory at the Epic's close."),
        # A removal added inside a sentence that also says no step removes it.
        ("execute.md", "`{workflow.implementation_artifacts}/evidence-<story_id>/`, which no step removes.",
         "`{workflow.implementation_artifacts}/evidence-<story_id>/`, which no step removes until Finalize deletes it."),
    ],
)
def test_removal_scan_lists_a_sentence_that_removes_the_folder(name, old, new):
    texts = _references()
    if old is None:
        texts[name] += "\n\n" + new + "\n"
    else:
        flat = _flat(texts[name])
        assert old in flat
        texts[name] = flat.replace(old, new)
    assert _removals_of_the_folder(texts) != []


_EVIDENCE_COMMIT = "**Commit the gate's evidence before the next story starts.**"


def _evidence_commit_names_the_folder(gate: str) -> bool:
    """Whether the gate's evidence commit paragraph names the folder anywhere:
    its list of paths, its staging sentence, or any sentence after them."""
    flat = _flat(gate)
    start = flat.index(_EVIDENCE_COMMIT)
    return bool(_FOLDER.search(flat[start : flat.index("Then move to the next story.", start)]))


def test_the_evidence_commit_does_not_carry_the_folder():
    """The folder stays untracked on a tracked tree, so the evidence commit's
    list of paths is the one it had."""
    assert not _evidence_commit_names_the_folder(GATE)


@pytest.mark.parametrize(
    "added", [" and its `evidence-<story_id>/` folder", " and its `evidence-<story_id>`", " and its evidence folder"]
)
def test_evidence_commit_predicate_lists_the_folder_added_to_its_paths(added):
    old = "and the decision log (with the first story, also Stage 3's test-design output)"
    flat = _flat(GATE)
    assert old in flat
    assert _evidence_commit_names_the_folder(flat.replace(old, old.replace(" (with", added + " (with")))


@pytest.mark.parametrize("added", [" and the story's `evidence-<story_id>/` folder", " and every `evidence-*` folder"])
def test_evidence_commit_predicate_lists_the_folder_added_to_its_staging(added):
    old = "stage those of these paths that exist and are not ignored"
    flat = _flat(GATE)
    assert old in flat
    mutant = flat.replace(old, "stage those of these paths" + added + " that exist and are not ignored")
    assert _evidence_commit_names_the_folder(mutant)


def test_the_folder_is_never_named_with_the_markers_dot():
    """`.evidence-owed-<story_id>` is the marker status_render.py and
    drive_epic.py read; the folder takes no dot, so no glob mistakes one for the
    other."""
    for name, text in _references().items():
        assert ".evidence-<story_id>" not in text, name


# --- the formalize scans skip a story's run folders, and the marker globs miss them ---


def _tree(tmp_path: Path, names: tuple[str, ...]) -> Path:
    impl = tmp_path / "implementation-artifacts"
    folder = impl / "evidence-4-1"
    folder.mkdir(parents=True)
    for name in names:
        (folder / name).write_text("captured\n", encoding="utf-8")
    return impl


# Each a file the formalize scans would misread anywhere else: a tool-named
# capture, a note named like a later Epic's story or like an uncovered story of
# this one, and a stale scratch build (memory/scratch-directory-children-
# flagged-as-leaked-tea-artifacts.md).
_IN_RUN_FOLDERS = (
    "evidence-4-1/trace.zip",
    "evidence-4-1/5-2-notes.md",
    "evidence-4-3/4-3-notes.md",
    ".scratch-2-3/target/debug/deps/libbacktrace-x.rlib",
)


def _formalize_reads(impl: Path, tmp_path: Path) -> list[Path]:
    """What the two scans read: story files for Epics 2, 4 and 5, and leaked TEA artifacts."""
    formalize = _load("formalize_check")
    stories = [path for epic, key in (("2", "2-3-cli"), ("4", "4-3-notes"), ("5", "5-2-notes"))
               for path in formalize._story_files(impl, epic, [key])]
    return stories + formalize._leaked_tea_artifacts(impl, tmp_path / "test-artifacts")


def _files(impl: Path, rels: tuple[str, ...]) -> Path:
    for rel in rels:
        (impl / rel).parent.mkdir(parents=True, exist_ok=True)
        (impl / rel).write_text("captured\n", encoding="utf-8")
    return impl


def test_the_formalize_scans_skip_a_storys_run_folders(tmp_path):
    impl = _files(tmp_path / "implementation-artifacts", (*_IN_RUN_FOLDERS, *("evidence-4-1/" + n for n in _FILED)))
    assert _formalize_reads(impl, tmp_path) == []


@pytest.mark.parametrize("where", ["root", "nested"])
def test_the_same_files_outside_a_top_level_run_folder_are_read(tmp_path, where):
    """Twin: at the artifacts root, or under a run-folder name below another
    folder, the scans read them as they always did."""
    impl = tmp_path / "implementation-artifacts"
    names = [rel.split("/", 1)[1] for rel in _IN_RUN_FOLDERS]
    rels = tuple(names) if where == "root" else tuple("notes/evidence-x/" + n for n in names)
    read = {path.name for path in _formalize_reads(_files(impl, rels), tmp_path)}
    assert read == {"trace.zip", "5-2-notes.md", "4-3-notes.md", "libbacktrace-x.rlib"}


def test_a_file_or_folder_only_named_like_a_run_folder_is_read(tmp_path):
    """Twin: the skip keys on a top-level folder named with the hyphen, never
    on a file named with the prefix or on a folder without the hyphen."""
    impl = _files(
        tmp_path / "implementation-artifacts",
        (
            "evidence-trace-matrix.md",
            "evidence-export.md",
            "evidence/traceability.md",
            "evidence/7-3-notes.md",
            ".scratch/traceability.md",
        ),
    )
    formalize = _load("formalize_check")
    stories = {p.relative_to(impl).as_posix() for p in formalize._story_files(impl, "7", ["evidence-export"])}
    leaked = {
        p.relative_to(impl).as_posix() for p in formalize._leaked_tea_artifacts(impl, tmp_path / "test-artifacts")
    }
    assert stories == {"evidence-export.md", "evidence/7-3-notes.md"}
    assert leaked == {"evidence-trace-matrix.md", "evidence/traceability.md", ".scratch/traceability.md"}


def test_the_folder_is_not_read_as_an_evidence_owed_marker(tmp_path):
    impl = _tree(tmp_path, _FILED)
    assert _load("status_render").owed_notes(impl) == {}
    assert _load("drive_epic").evidence_owed_ids(impl, ["4-1"]) == []
    (impl / ".evidence-owed-4-1").write_text("trace-4-1.md\n", encoding="utf-8")
    assert _load("drive_epic").evidence_owed_ids(impl, ["4-1"]) == ["4-1"]
