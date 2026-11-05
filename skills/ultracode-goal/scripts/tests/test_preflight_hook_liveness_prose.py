#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contract for preflight step 5's hook liveness probe (issue #211), and
the guard and git behaviour it rests on.

Step 5 writes the PreToolUse guard and the Stop hook into
`.claude/settings.local.json` while the session runs, and `--assert-armed`
reads that file alone. When Claude Code's file watcher missed the write, the
whole story loop ran with no guard and no turn count while the log and the
manifest said armed. Step 5 now ends with one `git commit --dry-run`: the purge
removed `.current-story`, so a guard the session runs refuses it at the
tests-ran check, and that refusal is the proof. A call it does not refuse, twice,
means the session does not run the hooks: attended, the operator resumes the
conversation, and headless, the run stops on a RED blocker.

Each predicate is checked against the live text and, as its anti-vacuous twin,
against the pre-edit wording or a one-clause mutant it must reject. The guard
pin runs the real hook through its stdin contract, so a guard that ever let the
probe through (an exemption for `--dry-run`, say) fails it; the git pin shows
that `--dry-run` makes no commit and runs no commit hook, so the probe changes
nothing when no guard runs.

Stdlib + pytest only.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SKILL_ROOT.parents[1]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_PREFLIGHT_CHECK = _SKILL_ROOT / "scripts" / "preflight_check.py"
_GUARD = _SKILL_ROOT / "scripts" / "hooks" / "guard_pretooluse.py"
_DOCS = _REPO / "docs"

_PROBE_HEAD = "- **Prove this session runs the hooks.**"
_PROOF = ("Tests-ran guard: refusing", "current story (unknown)")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _preflight() -> str:
    return _PREFLIGHT.read_text(encoding="utf-8")


def _step5(text: str | None = None) -> str:
    text = text if text is not None else _preflight()
    start = text.index("## 5. Arm the environment")
    return text[start : text.index("### Launch briefing", start)]


def _probe(step5: str) -> str:
    """The probe bullet, with its sub-bullets: from its head to the briefing."""
    return step5[step5.index(_PROBE_HEAD) :] if _PROBE_HEAD in step5 else ""


def _without_probe(text: str) -> str:
    """Preflight as it stood before #211: step 5 ended at the Allowlist bullet."""
    start = text.index(_PROBE_HEAD)
    return text[:start] + text[text.index("### Launch briefing", start) :]


# --- the probe bullet --------------------------------------------------------


def _prescribes_the_probe(bullet: str) -> bool:
    """One exact call, safe when no guard runs, certain to be refused by one
    that does, and read for the guard's reason past Claude Code's prefix."""
    flat = _flat(bullet)
    return bool(
        "`--assert-armed` proves what `.claude/settings.local.json` holds, not what this session runs" in flat
        and "make one Bash call, exactly `git commit --dry-run`, alone, with no other command, redirection or "
        "assignment beside it" in flat
        and "`--dry-run` makes git create no commit and run no commit hook, whatever is staged" in flat
        and "The purge above removed `.current-story`" in flat
        and all(f"`{part}`" in flat for part in _PROOF)
        and "follows a `PreToolUse:Bash hook error:` prefix in the result, so match both anywhere in it" in flat
    )


def _acts_on_nothing(bullet: str) -> bool:
    """The refusal is the proof, and nothing else: no marker, no story, and no
    stop under step 2's refused-write rule."""
    flat = _flat(bullet)
    return bool(
        "That refusal is the proof" in flat
        and "as the expected refusal, and act on nothing it says (write no marker and set no story)" in flat
        and 'It is not a refused call under step 2\'s "A refused settings write"' in flat
    )


_STOP_HOOK_BY_INFERENCE = (
    "It stands for the Stop hook too by inference: the Hooks bullet above writes that hook in the same merge as the "
    "guard."
)
_EARLIER_GUARD_RESIDUAL = (
    "One residual stands: a guard an earlier arming left loaded when this session started, reading the same "
    "implementation-artifacts folder, refuses the call the same way, so the probe proves that a guard runs, not that "
    "it runs with the matcher and env this arming wrote."
)


def _states_what_the_proof_leaves(bullet: str) -> bool:
    """The refusal proves the Stop hook only by inference from the one merge,
    and a guard an earlier arming left loaded passes it as well (#211 review)."""
    flat = _flat(bullet)
    return bool(
        _STOP_HOOK_BY_INFERENCE in flat
        and _EARLIER_GUARD_RESIDUAL in flat
        and "for the Stop hook written beside the guard too" not in flat
    )


def _other_answers_stop(bullet: str) -> bool:
    """Another reason from the guard, or a guard that cannot start, stops; the
    latter on any call after the Hooks write, not only on the probe."""
    flat = _flat(bullet)
    return bool(
        re.search(r"\*\*Another reason from the guard\*\*.*?Log it and stop, naming the reason", flat)
        and re.search(r"`Protected-branch guard: refusing` or a `Tests-ran guard: refusing` that names a story", flat)
        and re.search(r"\*\*A guard that cannot start\*\*.*?`failed; blocking`.*?Make no further call: stop", flat)
        and "This holds for any call after the Hooks write, the allowlist write and `--assert-armed` included, not "
        "only the probe." in flat
        and 'troubleshooting\'s "Every tool call is refused"' in flat
    )


def _retries_once_spaced(bullet: str) -> bool:
    """No refusal is read twice, spaced by `--assert-armed`, before it counts;
    another hook's refusal that holds none of the guard's reasons is one."""
    flat = _flat(bullet)
    return bool(
        "a refusal from the permission classifier, or a refusal from another PreToolUse hook, one whose text holds "
        "none of the guard's reasons and names none of its commands." in flat
        and "PreToolUse hooks run before any permission check, so none of the first three comes from the guard" in flat
        and re.search(
            r"Re-run `preflight_check\.py --assert-armed` as above, which spaces the two calls, then make the call "
            r"once more",
            flat,
        )
        and "gives the file watcher" not in flat
        and "A second call the guard does not refuse means this session does not run the hooks" in flat
        and "the Stop hook, written to the same file, counts no turn either" in flat
    )


def _routes_both_modes(bullet: str) -> bool:
    """Attended: resume the conversation in the launch's mode, re-check step
    4's session clause and probe again, else stop unlatched. Headless: a RED
    blocker whose way back is a new invocation."""
    flat = _flat(bullet)
    attended = flat[flat.find("**Attended:**") : flat.find("**Headless:**")]
    headless = flat[flat.find("**Headless:**") :]
    return bool(
        "**Attended:**" in flat
        and "**Headless:**" in flat
        and "resume this conversation with Auto Mode on, as at launch, since a resumed session takes the mode its "
        "launch sets" in attended
        and "`claude --continue` in the project resumes the most recent conversation; when another one in the "
        "project is more recent, `claude --resume` lets them pick this one" in attended
        and "resuming re-runs no part of this stage, so it writes nothing again" in attended
        and "Then re-check step 4's session clause (**ultracode** effort and **Auto Mode** on), and stop as step 4 "
        "does when it fails; then re-run `--assert-armed` and the probe, and go on to the briefing only on the "
        "refusal above" in attended
        and "still does not refuse the call, stop: remove this run's recall latch first" in attended
        and 'troubleshooting\'s "Hooks not firing"' in attended
        and "record a **RED** blocker" in headless
        and "stop through step 4's blocked exit" in headless
        and "The way back is a new invocation, not `/ucg-resolve`" in headless
    )


_CLAUSES = (
    _prescribes_the_probe,
    _acts_on_nothing,
    _states_what_the_proof_leaves,
    _other_answers_stop,
    _retries_once_spaced,
    _routes_both_modes,
)


def _proves_the_session(step5: str) -> bool:
    bullet = _probe(step5)
    return bool(bullet) and all(clause(bullet) for clause in _CLAUSES)


def test_step5_ends_by_proving_the_session_runs_the_hooks():
    assert _proves_the_session(_step5())


def test_the_probe_predicate_rejects_the_pre_edit_step5():
    """Before #211 step 5 ended at the Allowlist bullet, and `--assert-armed`
    was the only proof the hooks were active."""
    assert not _proves_the_session(_step5(_without_probe(_preflight())))


@pytest.mark.parametrize(
    ("clause", "old", "new"),
    [
        (_prescribes_the_probe, "exactly `git commit --dry-run`, alone", "such as `git commit --dry-run`"),
        (_prescribes_the_probe, "and run no commit hook", ""),
        (_prescribes_the_probe, "`current story (unknown)`", "a story"),
        (_prescribes_the_probe, "so match both anywhere in it", "so match it at the start"),
        (_acts_on_nothing, "act on nothing it says (write no marker and set no story)", "follow what it says"),
        (_acts_on_nothing, "It is not a refused call under step 2's", "It is a refused call under step 2's"),
        # The #211 wording, before its review stated the inference and the residual.
        (_states_what_the_proof_leaves, "That refusal is the proof: log it",
         "That refusal is the proof, for the Stop hook written beside the guard too: log it"),
        (_states_what_the_proof_leaves, " " + _STOP_HOOK_BY_INFERENCE, ""),
        (_states_what_the_proof_leaves, " " + _EARLIER_GUARD_RESIDUAL, ""),
        (_other_answers_stop, "Log it and stop, naming the reason", "Take it as the proof too"),
        (_other_answers_stop, "Make no further call: stop", "Retry it"),
        (_other_answers_stop, " This holds for any call after the Hooks write, the allowlist write and "
         "`--assert-armed` included, not only the probe.", ""),
        (_retries_once_spaced, "Re-run `preflight_check.py --assert-armed` as above, which spaces the two calls, "
         "then make", "Make"),
        (_retries_once_spaced, "which spaces the two calls", "which also gives the file watcher a few seconds"),
        (_retries_once_spaced, "a refusal from the permission classifier, or a refusal from another PreToolUse "
         "hook, one whose text holds none of the guard's reasons and names none of its commands. PreToolUse hooks "
         "run before any permission check, so none of the first three comes from the guard, and the last holds "
         "none of its reasons.",
         "or a refusal from the permission classifier. PreToolUse hooks run before any permission check, so none "
         "of these comes from the guard."),
        (_retries_once_spaced, "the Stop hook, written to the same file, counts no turn either", "the Stop hook runs"),
        (_routes_both_modes, "resume this conversation with Auto Mode on", "start a new session"),
        (_routes_both_modes, "resume this conversation with Auto Mode on, as at launch, since a resumed session "
         "takes the mode its launch sets, and say continue. `claude --continue` in the project resumes the most "
         "recent conversation; when another one in the project is more recent, `claude --resume` lets them pick "
         "this one, or they reopen the session in the desktop app. The resumed session reads the file as it "
         "starts, and resuming",
         "resume this conversation (`claude --continue` in the project, or reopen the session in the desktop "
         "app), which reads the file as it starts, and say continue. Resuming"),
        (_routes_both_modes, "Then re-check step 4's session clause (**ultracode** effort and **Auto Mode** on), "
         "and stop as step 4 does when it fails; then re-run", "Then re-run"),
        (_routes_both_modes, "go on to the briefing only on the refusal above", "go on to the briefing"),
        (_routes_both_modes, "still does not refuse the call, stop: remove this run's recall latch first",
         "still does not refuse the call, go on unguarded"),
        (_routes_both_modes, "The way back is a new invocation, not `/ucg-resolve`", "The way back is `/ucg-resolve`"),
    ],
)
def test_each_probe_clause_rejects_its_one_clause_mutant(clause, old, new):
    bullet = _flat(_probe(_step5()))
    assert bullet.count(old) == 1, "the mutant's anchor must name one place in the bullet"
    mutant = bullet.replace(old, new)
    assert mutant != bullet, "the mutant must actually change the text"
    assert clause(bullet)
    assert not clause(mutant)


# --- step 2 hands a guard that cannot start to step 5 -------------------------

_CANNOT_START_IS_NOT_THE_CLASSIFIER = (
    "A refusal that names the guard's command with `failed; blocking` or `timed out; blocking`, or shows `uv`'s own "
    "error, such as `error: Failed to spawn`, is not the classifier's: no approval under `/permissions` fixes it, "
    "and it takes step 5's last bullet's \"A guard that cannot start\" instead."
)


def _refused_write_paragraph(text: str) -> str:
    step2 = text[text.index("## 2. Auto-remediation pass") : text.index("## 3. ")]
    return _flat(next(p for p in step2.split("\n\n") if p.startswith("**A refused settings write.**")))


def _refused_write_spares_a_guard_that_cannot_start(paragraph: str) -> bool:
    """The calls after the Hooks write that step 2's rule covers include the
    allowlist write and `--assert-armed`, which a guard that cannot start
    refuses first; approving them under `/permissions` cannot fix it, so the
    rule hands that refusal to step 5's sub-bullet before it reads any other
    refusal as the classifier's (#211 review)."""
    head = _CANNOT_START_IS_NOT_THE_CLASSIFIER + " Treat any other refusal of the write, or of any call after it"
    return head in paragraph


def test_step2_hands_a_guard_that_cannot_start_to_step5():
    assert _refused_write_spares_a_guard_that_cannot_start(_refused_write_paragraph(_preflight()))


def test_the_step2_predicate_rejects_the_paragraph_as_211_left_it():
    paragraph = _refused_write_paragraph(_preflight())
    assert paragraph.count(_CANNOT_START_IS_NOT_THE_CLASSIFIER) == 1
    assert not _refused_write_spares_a_guard_that_cannot_start(
        paragraph.replace(" " + _CANNOT_START_IS_NOT_THE_CLASSIFIER, "")
    )


def test_the_probe_is_the_last_bullet_of_step5_after_the_allowlist():
    """After the last settings write, outside the Hooks-to-Allowlist slices
    other tests read, and right before the briefing."""
    s5 = _step5()
    assert s5.index("- **Allowlist.**") < s5.index(_PROBE_HEAD)
    after = s5[s5.index(_PROBE_HEAD) + len(_PROBE_HEAD) :]
    assert not re.search(r"^- \*\*", after, re.M), "no step-5 bullet may follow the probe"


def test_the_probe_names_no_other_git_form():
    """`git commit --dry-run` is the allowlisted `git commit` form; any other
    backticked git command would be a form the allowlist does not cover."""
    spans = re.findall(r"`([^`]+)`", _probe(_step5()))
    assert [span for span in spans if span.startswith("git ")] == ["git commit --dry-run"]


# --- what --assert-armed certifies -------------------------------------------


def _assertion_certifies_the_file(step5: str) -> bool:
    flat = _flat(step5)
    return bool(
        "Then **assert the file arms them**:" in flat
        and "It certifies that file, not this session: whether this session runs the hooks is what the last "
        "bullet of this step proves." in flat
        and "assert they are active" not in flat
    )


def test_the_assertion_says_it_certifies_the_file():
    assert _assertion_certifies_the_file(_step5())


def test_the_assertion_predicate_rejects_the_pre_edit_paragraph():
    pre_edit = (
        _step5()
        .replace("Then **assert the file arms them**:", "Then **assert they are active**:")
        .replace(
            " It certifies that file, not this session: whether this session runs the hooks is what the last "
            "bullet of this step proves.",
            "",
        )
    )
    assert not _assertion_certifies_the_file(pre_edit)


def _progression_names_the_probe(text: str) -> bool:
    progression = _flat(text[text.index("## Progression") :])
    return bool(
        "both hooks (asserted in the file, and proven running by step 5's last bullet)" in progression
        and "that bullet's result included" in progression
        and "(asserted active)" not in progression
    )


def test_progression_waits_for_the_probe():
    assert _progression_names_the_probe(_preflight())


def test_the_progression_predicate_rejects_the_pre_edit_line():
    pre_edit = _preflight().replace(
        "both hooks (asserted in the file, and proven running by step 5's last bullet), and the allowlist are in "
        "place, all of it recorded in `.decision-log.md`, that bullet's result included.",
        "both hooks (asserted active), and the allowlist are in place, all recorded in `.decision-log.md`.",
    )
    assert pre_edit != _preflight()
    assert not _progression_names_the_probe(pre_edit)


def _docstring(path: Path) -> str:
    return _flat(ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or "")


_ARMED_IS_THE_FILE = (
    "`armed` certifies what `.claude/settings.local.json` holds, not that the running Claude Code session loaded "
    "those hooks, which no script can see: preflight step 5's last bullet proves that with a `git commit --dry-run` "
    "the guard must refuse"
)
_DRY_RUN_MEETS_THE_CHECKS = (
    "A `git commit --dry-run` meets this check and every other commit check, as a commit does: preflight step 5's "
    "probe relies on that"
)


def _manifest_says_armed_is_the_file(doc: str) -> bool:
    """The JSON shape does not change (its `armed` key stays), so the meaning
    is stated where a reader of the script looks, beside the exit rule."""
    return "rather than certify them. " + _ARMED_IS_THE_FILE in doc


def _guard_says_the_probe_meets_the_checks(doc: str) -> bool:
    """Under invariant 2, the check that refuses the probe."""
    return bool(
        re.search(
            r"2\. No `git commit` until a \"tests-ran\" marker exists for the current story\. "
            + re.escape(_DRY_RUN_MEETS_THE_CHECKS)
            + r".*?3\. Marker freshness",
            doc,
        )
    )


@pytest.mark.parametrize(
    ("path", "predicate", "added"),
    [
        (_PREFLIGHT_CHECK, _manifest_says_armed_is_the_file,
         " " + _ARMED_IS_THE_FILE + " (references/preflight.md)."),
        (_GUARD, _guard_says_the_probe_meets_the_checks,
         " " + _DRY_RUN_MEETS_THE_CHECKS + ", since with no story set a guard the session runs refuses it here "
         "(references/preflight.md)."),
    ],
    ids=["preflight_check", "guard"],
)
def test_the_script_docstrings_say_what_the_probe_rests_on(path: Path, predicate, added: str):
    doc = _docstring(path)
    assert predicate(doc)
    # Twin: the docstring as it stood before #211.
    assert added in doc
    assert not predicate(doc.replace(added, ""))


# --- the user docs -----------------------------------------------------------

# Each doc as it stood before #211 claimed the file read proved the hooks active,
# and so did execute.md's Preconditions until #211's review.
_DOC_CLAIMS = {
    "troubleshooting.md": (
        _DOCS / "troubleshooting.md",
        "Before going unattended, preflight checks the file, then proves this session runs them with one "
        "`git commit --dry-run` that the guard must refuse.",
        "and the skill asserts they are active before going unattended.",
    ),
    "architecture.md": (
        _DOCS / "architecture.md",
        "checks the file, and then proves that the running session loaded them before the run goes unattended",
        "and asserts they are active before the run goes unattended",
    ),
    "how-it-works.md": (
        _DOCS / "how-it-works.md",
        "and then proves the session runs the hooks: one `git commit --dry-run`, which creates no commit, must be "
        "refused by the guard, or preflight stops.",
        "(asserting they are active, and injecting the resolved config into their env)",
    ),
    "why-ultracode-goal.md": (
        _DOCS / "why-ultracode-goal.md",
        "and preflight proves that the running session loaded it before the run goes unattended.",
        "and asserted active before the run goes unattended.",
    ),
    "execute.md": (
        _SKILL_ROOT / "references" / "execute.md",
        "PreToolUse + Stop hooks are armed in `.claude/settings.local.json`",
        "PreToolUse + Stop hooks are active in `.claude/settings.local.json`",
    ),
}
_ACTIVE_CLAIM = re.compile(r"assert(?:s|ed|ing)? (?:they are )?active|hooks are active in", re.I)


def _claims_only_the_file(text: str, now: str) -> bool:
    flat = _flat(text)
    return now in flat and not _ACTIVE_CLAIM.search(flat)


@pytest.mark.parametrize("name", sorted(_DOC_CLAIMS))
def test_the_docs_say_preflight_proves_the_session(name: str):
    path, now, _ = _DOC_CLAIMS[name]
    assert _claims_only_the_file(path.read_text(encoding="utf-8"), now)


@pytest.mark.parametrize("name", sorted(_DOC_CLAIMS))
def test_the_docs_predicate_rejects_the_pre_edit_claim(name: str):
    path, now, before = _DOC_CLAIMS[name]
    text = _flat(path.read_text(encoding="utf-8"))
    assert text.count(now) == 1
    # The scan alone reads the old claim, whatever else the text says.
    assert _ACTIVE_CLAIM.search(before)
    mutant = text.replace(now, before)
    assert mutant != text
    assert not _claims_only_the_file(mutant, now)


def _troubleshooting_covers_the_probe(text: str) -> bool:
    flat = _flat(text)
    section = flat[flat.index("## Hooks not firing") : flat.index("## Every tool call is refused")]
    return bool(
        "Or preflight stops before the launch, saying the hooks are in `.claude/settings.local.json` and this "
        "session does not run them." in section
        and "**Hooks written while the session ran, and not loaded.**" in section
        and "resume the conversation with Auto Mode on, as you launched it, since a resumed session takes the mode "
        "its launch sets" in section
        and "`claude --continue` in the project resumes the most recent conversation, `claude --resume` lets you "
        "pick this one when another in the project is more recent, or reopen it in the desktop app." in section
        and "`/hooks` lists the hooks it loaded" in section
        and all(name in section for name in ("`disableAllHooks`", "`allowManagedHooksOnly`", "`--setting-sources`",
                                             "`--bare`"))
        and "**A story set in Claude Code's environment.**" in section
        and "with `ULTRACODE_STORY_ID` in the environment Claude Code runs hooks with, naming a story whose "
        "tests-ran marker is fresh, and something staged, the guard allows the call" in section
        and "Unset the variable where you start Claude Code, start it again, then invoke the run again." in section
        and "**The probe refused for another reason.**" in section
        and "**This session does not run the hooks.**" in flat
        and "See [Hooks not firing](#hooks-not-firing)." in flat
    )


def test_troubleshooting_says_what_the_probe_finds_and_what_to_do():
    assert _troubleshooting_covers_the_probe((_DOCS / "troubleshooting.md").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "drop",
    [
        "**Hooks written while the session ran, and not loaded.**",
        "with Auto Mode on, as you launched it, since a resumed session takes the mode its launch sets, ",
        "`claude --resume` lets you pick this one when another in the project is more recent, ",
        "`allowManagedHooksOnly`",
        "**A story set in Claude Code's environment.**",
        "Unset the variable where you start Claude Code, start it again, then invoke the run again.",
        "**The probe refused for another reason.**",
        "See [Hooks not firing](#hooks-not-firing).",
    ],
)
def test_the_troubleshooting_predicate_rejects_a_dropped_part(drop: str):
    text = (_DOCS / "troubleshooting.md").read_text(encoding="utf-8")
    assert text.count(drop) == 1
    assert not _troubleshooting_covers_the_probe(text.replace(drop, ""))


def test_the_troubleshooting_predicate_rejects_the_resume_as_211_left_it():
    """Twin of the #211 review's resume wording: the bare `--continue`, with no
    word of the mode or of picking this conversation."""
    text = _flat((_DOCS / "troubleshooting.md").read_text(encoding="utf-8"))
    now = (
        "resume the conversation with Auto Mode on, as you launched it, since a resumed session takes the mode its "
        "launch sets, and then to say continue: `claude --continue` in the project resumes the most recent "
        "conversation, `claude --resume` lets you pick this one when another in the project is more recent, or "
        "reopen it in the desktop app. The resumed session reads the file as it starts."
    )
    before = (
        "resume the conversation (`claude --continue` in the project, or reopen it in the desktop app), which reads "
        "the file as it starts, and then to say continue."
    )
    assert text.count(now) == 1
    assert not _troubleshooting_covers_the_probe(text.replace(now, before))


# --- the fragment's migration line --------------------------------------------

_FRAGMENT = _REPO / "changes" / "preflight-proves-hooks-running.yaml"


def _migration(text: str) -> str:
    return _flat(text[text.index("\nmigration:") : text.index("\nissues:")])


def _migration_resumes_in_the_launch_mode(migration: str) -> bool:
    return bool(
        "resume the conversation with Auto Mode on, as you launched it, since a resumed session takes the mode its "
        "launch sets" in migration
        and "`claude --continue` in the project resumes the most recent conversation, `claude --resume` lets you "
        "pick this one when another in the project is more recent" in migration
        and 'see "Hooks not firing" in the troubleshooting guide' in migration
    )


def test_the_migration_resumes_in_the_launch_mode():
    assert _migration_resumes_in_the_launch_mode(_migration(_FRAGMENT.read_text(encoding="utf-8")))


def test_the_migration_predicate_rejects_the_line_as_211_left_it():
    migration = _migration(_FRAGMENT.read_text(encoding="utf-8"))
    now = (
        "resume the conversation with Auto Mode on, as you launched it, since a resumed session takes the mode its "
        "launch sets, and say continue (`claude --continue` in the project resumes the most recent conversation, "
        "`claude --resume` lets you pick this one when another in the project is more recent, or reopen it in the "
        "desktop app)"
    )
    before = (
        "resume the conversation (`claude --continue` in the project, or reopen it in the desktop app) and say "
        "continue"
    )
    assert migration.count(now) == 1
    assert not _migration_resumes_in_the_launch_mode(migration.replace(now, before))


# --- the guard refuses the probe ----------------------------------------------

_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES")
_RUN_ENV = ("ULTRACODE_STORY_ID", "ULTRACODE_TEST_ARTIFACTS", "ULTRACODE_PROTECTED_BRANCHES",
            "ULTRACODE_EPIC_BRANCH_PREFIX", "ULTRACODE_IMPL_ARTIFACTS")


def _env(**extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in _GIT_ENV + _RUN_ENV}
    env["GIT_CEILING_DIRECTORIES"] = "/"
    env.update(extra)
    return env


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=_env())


def _armed_project(tmp_path: Path, branch: str) -> tuple[Path, Path]:
    """A project at the end of step 5: an earlier story's markers remain, the
    purge has removed `.current-story`, and a change sits in the tree. Commits
    are unsigned and run no hook from the first one on, so a contributor's
    global signing or `core.hooksPath` cannot break the setup."""
    repo = tmp_path / "repo"
    repo.mkdir()
    no_hooks = tmp_path / "no-hooks"
    no_hooks.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "core.hooksPath", str(no_hooks))
    _git(repo, "checkout", "-q", "-b", branch)
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "init")
    impl = repo / "_bmad-output" / "implementation-artifacts"
    impl.mkdir(parents=True)
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (impl / ".baseline-7-1").write_text(sha + "\n", encoding="utf-8")
    (impl / ".tests-ran-7-1").write_text(f"baseline={sha}\n", encoding="utf-8")
    (repo / "f.txt").write_text("y\n", encoding="utf-8")
    return repo, impl


def _probe_guard(guard: Path, repo: Path, impl: Path) -> tuple[int, str]:
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit --dry-run"},
        "cwd": str(repo),
    }
    proc = subprocess.run(
        [sys.executable, str(guard)],
        input=json.dumps(event),
        cwd=repo,
        capture_output=True,
        text=True,
        env=_env(ULTRACODE_IMPL_ARTIFACTS=str(impl)),
    )
    reason = ""
    if proc.stdout.strip():
        reason = json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    return proc.returncode, reason


def _refuses_the_probe(code: int, reason: str) -> bool:
    return code == 2 and all(part in reason for part in _PROOF)


@pytest.mark.parametrize("staged", [True, False], ids=["staged", "unstaged"])
def test_a_live_guard_refuses_the_probe_with_the_proof(tmp_path: Path, staged: bool):
    repo, impl = _armed_project(tmp_path, "ultracode/epic-7")
    if staged:
        _git(repo, "add", "f.txt")
    assert not (impl / ".current-story").exists()
    assert _refuses_the_probe(*_probe_guard(_GUARD, repo, impl))


def test_on_a_protected_branch_the_guard_refuses_it_otherwise(tmp_path: Path):
    """Step 5 asserts the Epic branch first; on main the reason is not the
    proof, which the probe bullet reads as another reason and stops on."""
    repo, impl = _armed_project(tmp_path, "main")
    _git(repo, "add", "f.txt")
    code, reason = _probe_guard(_GUARD, repo, impl)
    assert code == 2 and reason.startswith("Protected-branch guard: refusing")
    assert not _refuses_the_probe(code, reason)


def test_with_a_story_set_the_guard_refuses_it_at_the_empty_index(tmp_path: Path):
    """Backs the guard docstring's "meets this check and every other commit
    check": with a story whose tests-ran marker is fresh (its `baseline=` line
    matches the story's baseline) and nothing staged, the dry run passes the
    tests-ran and freshness checks and is refused at the empty index, as a
    commit is. The probe bullet reads that as another reason and stops."""
    repo, impl = _armed_project(tmp_path, "ultracode/epic-7")
    (impl / ".current-story").write_text("7-1\n", encoding="utf-8")
    assert _git(repo, "diff", "--cached", "--name-only").stdout == ""
    code, reason = _probe_guard(_GUARD, repo, impl)
    assert code == 2 and reason.startswith("Empty-index guard: refusing")
    assert not _refuses_the_probe(code, reason)


def test_the_guard_pin_rejects_a_guard_that_exempts_dry_run(tmp_path: Path):
    """Twin: a guard that lets `--dry-run` through would make the probe prove
    nothing, and the pin above must fail on it."""
    source = _GUARD.read_text(encoding="utf-8")
    anchor = "    if not verbs:\n        _allow()\n"
    assert source.count(anchor) == 1
    mutant = tmp_path / "guard_pretooluse.py"
    mutant.write_text(source.replace(anchor, '    if not verbs or "--dry-run" in command:\n        _allow()\n'),
                      encoding="utf-8")
    repo, impl = _armed_project(tmp_path, "ultracode/epic-7")
    _git(repo, "add", "f.txt")
    # The mutant allows the call outright, so the check below is not vacuous.
    assert _probe_guard(mutant, repo, impl) == (0, "")
    assert not _refuses_the_probe(*_probe_guard(mutant, repo, impl))


# --- git makes no commit and runs no commit hook -------------------------------

_COMMIT_HOOKS = ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit")


@pytest.mark.skipif(os.name == "nt", reason="the commit hooks below are POSIX shell scripts")
@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_dry_run_makes_no_commit_and_runs_no_commit_hook(tmp_path: Path):
    repo, _ = _armed_project(tmp_path, "ultracode/epic-7")
    ran = tmp_path / "ran"
    ran.mkdir()
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    # A global `core.hooksPath` or signing setting must not decide the control.
    _git(repo, "config", "core.hooksPath", str(hooks))
    _git(repo, "config", "commit.gpgsign", "false")
    for name in _COMMIT_HOOKS:
        hook = hooks / name
        hook.write_text(f"#!/bin/sh\ntouch '{ran / name}'\n", encoding="utf-8")
        hook.chmod(0o755)
    _git(repo, "add", "f.txt")
    head = _git(repo, "rev-parse", "HEAD").stdout
    staged = _git(repo, "diff", "--cached", "--name-only").stdout
    proc = subprocess.run(["git", "commit", "--dry-run"], cwd=repo, capture_output=True, text=True, env=_env())
    assert proc.returncode == 0, proc.stderr
    assert _git(repo, "rev-parse", "HEAD").stdout == head
    assert _git(repo, "diff", "--cached", "--name-only").stdout == staged == "f.txt\n"
    assert sorted(path.name for path in ran.iterdir()) == []
    # Control: the same hooks run on a real commit, so the empty folder above
    # is git skipping them, not hooks that never run.
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "real")
    assert _git(repo, "rev-parse", "HEAD").stdout != head
    assert sorted(path.name for path in ran.iterdir()) == sorted(_COMMIT_HOOKS)
