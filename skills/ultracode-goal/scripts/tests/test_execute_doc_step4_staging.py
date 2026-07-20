"""Execute steps 4 and 5: staging is a prior, SEPARATE tool call.

Doc-shape assertions over execute.md's two commit sites. The guard denies a
commit whose staged index is empty, and it pre-evaluates the command string, so
a chained `git add … && git commit` has staged nothing when it is judged. Both
commit sites (step 4's commit-at-green and step 5's post-re-verify re-commit)
must therefore mandate the two-call form; a rule that governs one site and not
the other is a half-covered guard.

ONE matcher is applied to both blocks, so the step-5 twin below can red the
step-5 site while the same matcher stays green on step 4 — proving the lint is
pinned to each site rather than matching the sentence anywhere in the file.

Stated limit: this is a presence proof. It shows the instruction is in the file,
not that an executor obeys it. The behavioral proof that a separately-staged
commit passes the guard lives in test_guard_pretooluse.py. Stdlib + pytest only.
"""

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_EXECUTE = _SKILL_ROOT / "references" / "execute.md"

# The staging rule: a SEPARATE tool call, co-located with the `git add` it names.
# Case-exact on SEPARATE: step 4 already carried "in a prior, SEPARATE command"
# for the tests-ran marker, and that older sentence must not satisfy this check.
_SEPARATE_STAGING_RE = re.compile(r"SEPARATE tool call.{0,60}`git add", re.DOTALL)

# Both unsupported commit-time staging forms, named as unsupported.
_REJECTS_RE = re.compile(
    r"`git commit -a`.{0,120}commit-time pathspecs.{0,160}unsupported", re.DOTALL
)


def _text() -> str:
    return _EXECUTE.read_text(encoding="utf-8")


def _step4(text: str | None = None) -> str:
    text = text if text is not None else _text()
    start = text.index("\n4. ")
    return text[start:text.index("\n5. ", start)]


def _step5(text: str | None = None) -> str:
    text = text if text is not None else _text()
    start = text.index("\n5. ")
    return text[start:text.index("\n\n", start)]


def test_step4_mandates_separate_add_call():
    assert _SEPARATE_STAGING_RE.search(_step4()), (
        "step 4 must mandate `git add <paths>` in its own prior tool call"
    )
    # the pre-existing marker rule and scoped-add guidance must survive the edit
    block = _step4()
    assert "two distinct tool calls" in block
    assert "`git add <this story's paths>`" in block
    assert "sibling" in block, "sibling-test-pollution guidance must stay"


def test_step4_rejects_commit_a_and_commit_time_pathspecs():
    assert _REJECTS_RE.search(_step4()), (
        "step 4 must name `git commit -a` and commit-time pathspecs as unsupported"
    )


def test_step5_recommit_mandates_separate_add_call():
    block = _step5()
    assert "re-commit" in block, "step-5 slice must be the re-verify/re-commit block"
    assert _SEPARATE_STAGING_RE.search(block), (
        "step 5's re-commit path must carry the same separate-staging rule as step 4"
    )


def test_mutant_step5_without_staging_sentence_reds_only_step5():
    """Twin: strip the staging sentence from step 5 only.

    The step-5 matcher must red while the IDENTICAL matcher stays green on step
    4. Without that paired assertion a lint that matched the sentence anywhere
    in the file would satisfy the step-5 check vacuously, off step 4's copy.
    """
    text = _text()
    original = _step5(text)
    mutated_block = re.sub(
        r"That re-commit carries the SAME staging rule.*?(?=\Z)", "", original,
        flags=re.DOTALL,
    )
    assert mutated_block != original, "step-5 staging sentence anchor drifted"
    mutated = text.replace(original, mutated_block, 1)

    assert not _SEPARATE_STAGING_RE.search(_step5(mutated)), (
        "with the sentence stripped, the step-5 assertion must fail"
    )
    assert _SEPARATE_STAGING_RE.search(_step4(mutated)), (
        "the step-4 control must stay green under the same mutation"
    )


def test_mutant_step4_without_staging_sentence_reds_only_step4():
    """Twin, mirrored: strip the staging sentence from step 4 only.

    The step-4 direction was verified by hand while step 4 was authored, which
    left the two commit sites unevenly proven: step 5 had an executed twin and
    step 4 had none. This is that twin, and it carries the same paired shape -
    step 4 reds while the IDENTICAL matcher stays green on step 5 - so neither
    site can satisfy its own check off the other's copy of the sentence.
    """
    text = _text()
    original = _step4(text)
    mutated_block = re.sub(
        r"\*\*Staging is itself a prior, SEPARATE tool call\*\*.*?rule the marker fol",
        "", original, flags=re.DOTALL,
    )
    assert mutated_block != original, "step-4 staging sentence anchor drifted"
    mutated = text.replace(original, mutated_block, 1)

    assert not _SEPARATE_STAGING_RE.search(_step4(mutated)), (
        "with the sentence stripped, the step-4 assertion must fail"
    )
    assert _SEPARATE_STAGING_RE.search(_step5(mutated)), (
        "the step-5 control must stay green under the same mutation"
    )


# ---------------------------------------------------------------------------
# Decision-log prose goes through Write/Edit, not a Bash heredoc.
#
# Stages 4 and 6 require a log of what happened, and what happened IS commit
# behaviour, so the log quotes the verbs. A heredoc carrying that prose is a
# Bash command string: a line leading with the verb is a verb-leading segment,
# and a backticked identifier or an apostrophe routes the segment down the
# fail-closed matches-anywhere path. The guard never sees Write/Edit, so the
# tool choice removes the collision rather than phrasing around it.
# ---------------------------------------------------------------------------

_LOG_TOOL_RE = re.compile(
    r"`\.decision-log\.md`.{0,40}Write/Edit.{0,40}never a Bash heredoc", re.DOTALL
)


def test_step4_routes_decision_log_prose_to_the_file_tools():
    assert _LOG_TOOL_RE.search(_step4()), (
        "step 4 must direct decision-log appends to Write/Edit rather than a "
        "Bash heredoc: it is the shape that collides with the commit guard"
    )


def test_step4_states_why_the_heredoc_collides():
    """A bare 'use Write/Edit' reads as style. The reason is what makes it stick."""
    block = _step4()
    assert re.search(r"guard (never sees|evaluates)", block, re.I), (
        "the rule must name the mechanism: the guard evaluates Bash strings and "
        "never sees the file tools"
    )


def test_mutant_step4_without_log_tool_rule_reds():
    """Anti-vacuous twin: strip the sentence and the assertion must fail."""
    text = _text()
    original = _step4(text)
    mutated_block = re.sub(
        r"\*\*Append `\.decision-log\.md` with Write/Edit.*?mean to run\.",
        "", original, flags=re.DOTALL,
    )
    assert mutated_block != original, "decision-log tool sentence anchor drifted"
    assert not _LOG_TOOL_RE.search(mutated_block), (
        "with the sentence stripped, the assertion must fail"
    )
