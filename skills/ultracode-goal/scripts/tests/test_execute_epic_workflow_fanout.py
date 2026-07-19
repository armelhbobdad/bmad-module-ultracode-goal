"""The --parallel fan-out prompt must serve the marker-freshness clause.

Doc-shape assertions over the runStory prompt string in
assets/execute-epic.workflow.js, read as TEXT (no Node runtime). The PreToolUse
guard requires every tests-ran marker to carry a `baseline=<sha>` line matching
the story's recorded baseline, and it does not know or care which path produced
the commit. So the worktree agent needs BOTH halves in its prompt: a step-0
equivalent that records the baseline before any implementation, and a
marker-write step that mandates the line, copied verbatim rather than re-derived
from `git rev-parse HEAD`. Without them every fan-out commit is denied.

Stated limit, recorded rather than papered over: this is a presence proof. It
shows the two instructions are in the prompt; it does NOT run --parallel and
proves nothing about the fan-out end to end. A presence lint's only available
mutation is removing the string itself, so the twin below proves the
instructions cannot silently vanish, and that is all it proves. The behavioral
proof that a matching marker passes the guard is in test_guard_pretooluse.py,
against the real hook.

There are other copies of this asset on disk; skills/ultracode-goal/assets/ is
the shipped source of truth and the only one this lint reads. Stdlib + pytest
only.
"""

import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _SKILL_ROOT / "assets" / "execute-epic.workflow.js"

# Half one: record the baseline, before implementation, as the long 40-hex form
# the reader compares verbatim.
_RECORDS_BASELINE_RE = re.compile(
    r"before any implementation"
    r".{0,400}?\$\{implArtifacts\}/\.baseline-\$\{id\}",
    re.DOTALL,
)
_LONG_FORM_RE = re.compile(r"40-hex.{0,200}?not --short", re.DOTALL)

# Half two: the marker carries that value, copied rather than recomputed.
_MARKER_EMBEDS_BASELINE_RE = re.compile(
    r"\\`baseline=<sha>\\` line"
    r".{0,300}?\$\{implArtifacts\}/\.baseline-\$\{id\}"
    r".{0,200}?copied, never re-derived from \\`git rev-parse HEAD\\`",
    re.DOTALL,
)


def _source() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def _run_story_prompt(src: str) -> str:
    """The per-worktree agent prompt: the template literals inside runStory()."""
    start = src.index("function runStory(")
    return src[start:src.index("\n// ", start)]


def _fanout_prompt_serves_freshness(src: str) -> bool:
    """The single AC predicate, reused verbatim by the twin below.

    True only when the prompt carries BOTH halves: the baseline record and the
    marker-format rule. Either one alone leaves the fan-out denied at commit.
    """
    prompt = _run_story_prompt(src)
    return bool(
        _RECORDS_BASELINE_RE.search(prompt)
        and _MARKER_EMBEDS_BASELINE_RE.search(prompt)
    )


# The two instruction strings, each anchored so the twin's removal is surgical.
_BASELINE_STEP_RE = re.compile(
    r"`0\. RECORD THIS STORY'S BASELINE.*?even after HEAD moves\.\\n` \+\n\s*",
    re.DOTALL,
)
_MARKER_FORMAT_RE = re.compile(
    r"That marker MUST contain a \\`baseline=<sha>\\` line.*?deny your own commit\. ",
    re.DOTALL,
)


def test_fanout_records_baseline_and_marker_embeds_it():
    src = _source()
    assert _fanout_prompt_serves_freshness(src), (
        "the fan-out prompt must both record .baseline-<id> before any "
        "implementation and mandate the copied `baseline=<sha>` marker line"
    )
    prompt = _run_story_prompt(src)
    # the recorded value is the long form the reader compares with no normalization
    assert _LONG_FORM_RE.search(prompt), "the baseline must be the full 40-hex SHA"
    # it is this worktree's own HEAD: each worktree branches independently
    assert "this worktree's own HEAD" in prompt
    # the pre-existing prompt shape must survive the edit: no step was renumbered
    for step in ("1. bmad-create-story", "3. Run and PRINT", "5. COMMIT AT GREEN",
                 "6. GATE THIS STORY"):
        assert step in prompt, f"step numbering drifted: {step!r} missing"
    assert "${implArtifacts}/.tests-ran-${id}" in prompt


@pytest.mark.parametrize(
    "name,pattern",
    [
        ("baseline-record step 0", _BASELINE_STEP_RE),
        ("marker `baseline=` format rule", _MARKER_FORMAT_RE),
    ],
)
def test_twin_removing_either_fanout_instruction_reds_the_lint(name, pattern):
    """Twin: delete one instruction from an in-memory copy of the source.

    Control + mutant in one function. The predicate must be True on the
    UNMUTATED source and False on each mutant: a deletion whose pattern matched
    nothing would leave the predicate True on the "mutant" and red here, which
    is the only way a presence lint can go vacuous.
    """
    src = _source()
    assert _fanout_prompt_serves_freshness(src), (
        "control: the shipped source must satisfy the predicate"
    )

    mutant = pattern.sub("", src, count=1)
    assert mutant != src, f"instruction anchor drifted out of the prompt: {name}"
    assert not _fanout_prompt_serves_freshness(mutant), (
        f"removing the {name} must red the fan-out lint"
    )
