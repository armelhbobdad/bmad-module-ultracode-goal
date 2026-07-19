"""The --parallel fan-out prompt must tell each worktree agent to stage first.

Doc-shape assertions over the commit step of the runStory prompt string in
assets/execute-epic.workflow.js, read as TEXT (no Node runtime). The guard
denies a commit with an empty staged index and pre-evaluates the command
string, so a worktree agent reaching for `git commit -a` or a chained
`git add … && git commit` would be denied on a perfectly legitimate green
story. The prompt has to say so.

Stated limit, recorded rather than papered over: a presence lint's only
available mutation is removing the string itself, so the twin below proves the
instruction cannot silently vanish from the fan-out prompt. It does NOT prove a
worktree agent obeys it, and it is not end-to-end --parallel coverage. The
behavioral proof that a separately-staged commit passes the guard is in
test_guard_pretooluse.py, against the real hook. Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _SKILL_ROOT / "assets" / "execute-epic.workflow.js"

# The single AC matcher, reused verbatim by the twin below (not a lookalike).
_SEPARATE_STAGING_RE = re.compile(r"SEPARATE tool call.{0,40}git add", re.DOTALL)

# Both unsupported forms named in the same breath as their prohibition.
_FORBIDS_RE = re.compile(
    r"git commit -a.{0,80}chained.{0,80}unsupported", re.DOTALL
)

# The staging sentence the twin removes, anchored so the removal is surgical.
_STAGING_SENTENCE_RE = re.compile(
    r"Stage this story's paths in a prior, SEPARATE tool call.*?distinct tool call\. ",
    re.DOTALL,
)


def _commit_step() -> str:
    """Slice the runStory prompt's commit step out of the workflow source."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    start = text.index("5. COMMIT AT GREEN")
    return text[start:text.index("6. GATE THIS STORY", start)]


def test_commit_step_mandates_separate_staging_call():
    step = _commit_step()
    assert _SEPARATE_STAGING_RE.search(step), (
        "the fan-out commit step must mandate staging in a prior, separate tool call"
    )
    # the pre-existing framing must survive the edit
    assert "exactly ONE commit" in step
    assert "worktree's branch" in step
    assert "satisfy it rather than bypass it" in step
    # the enumeration of hook denials stays complete
    assert "empty staged index" in step


def test_commit_step_forbids_commit_a_and_chained_add():
    assert _FORBIDS_RE.search(_commit_step()), (
        "the fan-out commit step must name `git commit -a` and the chained add "
        "as unsupported"
    )


def test_mutant_without_staging_instruction_fails_lint():
    """Twin: with the staging sentence gone, the identical matcher must not match."""
    step = _commit_step()
    mutated = _STAGING_SENTENCE_RE.sub("", step, count=1)
    assert mutated != step, "staging-sentence anchor drifted out of the prompt"
    assert not _SEPARATE_STAGING_RE.search(mutated), (
        "the staging assertion must red once the instruction is removed"
    )
