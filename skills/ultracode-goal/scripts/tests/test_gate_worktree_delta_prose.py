#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Prose contracts for gate-time isolation (measure the commit, not the working
tree) and the delta cycle profile's instruction side.

gate_eval.py's delta cap is pinned by test_gate_eval.py; these tests pin what
no script test can: that gate.md still orders assessors onto a worktree of the
commit under assessment (with the four caveats that were each a measured
failure when skipped), and that the delta profile's use is bounded by the
mechanical attribution fallback rather than judgment.

They also pin the order the assessors share that worktree in. Automate's
mutation runs edit source there, and the gate used to let NFR and test review
measure beside them (#174). A test automate backfilled was left for the
evidence commit after the verdict, so trace counted a test the assessed commit
did not hold, and nothing bounded repeated automate passes (#175). Each new
predicate is also checked, as its anti-vacuous twin, against the pre-edit
wording or a one-clause mutant it must reject. The same goes for what a review
of that fix found: a red backfill sweep fixed inside the gate, a resume that
re-drove the story or ran automate twice, a reported gap no route took, a gap
a re-loop was sent to close that no gate re-measured, and copies of the commit
structure that still named two commits. A final review of that branch found
more, each pinned below: a gap with no rows, or one a test-only re-loop left,
that no later gate re-measured (a gap now stays open until a later pass
measures it closed), rows kept nowhere a later cycle could find, a red sweep's
re-loop that dropped the gaps beside the red, a resume that missed a backfill
or re-gated a re-loop nobody ran, and a test automate wrote into the worktree
that was dropped without a gap.

The maintainer then ruled on a P0 gap: write a test, never block. Automate
backfills every gap it finds on a P0 criterion, in any cycle, and the gate
script decides on the test; a `gate-gap:` line never changes a route, and the
only stop before trace is a red backfill sweep. The last review of that rule
found a closing test of another name read as no close, a resume that re-ran a
finished automate pass into the same summary, a pre-trace verdict with nothing
for the heartbeat or the attended print to carry, a resumed backfill read
against the turn ceiling, and five sentences no test pinned.

The review after that found, each pinned below with a mutant twin: a P0
`gate-gap:` row on the ledger that the ledger's own `high` bar sent back to a
re-loop; a P0 gap no test can kill (an equivalent mutant), which every pass
backfilled again and which could loop operator re-gates without bound (now an
`unkilled` line, confirmed in the pass that writes the test, that gets no second
test while its rows run); a repo commit hook that rejected the backfill commit
with two routes to take; a same-pass confirmation that could not see the test it
confirmed (mutation rows run in the worktree, so automate copies the test there);
a closing test in a file the row's own command never ran; a session that died
after automate with no backfill line and resumed as mid-story (now a
`gate-automate:` line); and eighteen rule sentences one-sentence mutations
changed with no test failing.

The review after that found, each pinned below: a gap no row could measure,
which one pass measured afresh without end (now once in a pass, then an
`unmeasured` line); a second run the full sweep could not make, which sent a
`GREEN` row to be measured afresh instead of leaving it a gap; a mutant that
broke a module pytest then could not collect, read as another test's kill
(`mutate_check.py` now reads it 0 failed, a row that cannot run); `SKILL.md`,
the other references and the docs left outside the scan of sentences that put
a gap beside a route; "the one thing that ends a cycle before trace", which the
sub-skill halt escalation contradicted; execute.md's "the one exception", which
put the evidence commit under the hook rule gate.md forbids for it; and a
release note that limited the second run to re-run rows.

The review after that found, each pinned below with a mutant twin: a mutant
that broke what a conftest.py imports, or a test file jest or vitest could not
load, still read as another test's kill (`mutate_check.py` now reads both 0
failed, and the cannot-run bullet and the release note name exactly what reads
that way); a backfill that kills its mutant logged `unkilled` when the row's
own command never ran the test and the full sweep's run was refused (a
confirmation row now runs the test's file); an evidence-commit hook rule that
let the gate edit TEA's files and its own ledger rows, without bound (now only
the gate's own files, at most twice, then an `evidence-commit-rejected`
escalation a resume waits on); a scan of gap-routing sentences that missed one
naming only an `unkilled` or `unmeasured` line; and a release note no test
read.

#179 then found four more misreads in `mutate_check.py`, pinned in
test_mutate_check.py. Two of them change what reads 0 failed: a class pytest
cannot collect, and a test file Node's test runner cannot load or whose
process exits non-zero after its tests pass. The cannot-run bullet now names
both, and its release note is pinned below, each with a mutant twin.

The status view's skill joined both scans when it learned to render a story
that still owes its evidence commit (#179): it now tells an operator what a
rejected evidence commit leaves owed, so its sentences are read against the
bound like every other surface's.

Then a run showed the worktree itself leaking (#182): Playwright's
`reuseExistingServer` attached the worktree's browser runs to a dev server
started from the main tree, so they measured the main tree's source, and a
source mutation automate wrote into the worktree read `GREEN` with no run
seeing it, a false gap the rules would backfill or log `unkilled`. The fourth
caveat checks for such a server with probe_servers.py, gives the worktree its
own server where a scratch runner config can, and otherwise briefs every
assessor with the limit and reads a row through that server as one that
cannot run. Each of those rules is pinned below with a mutant twin.

A later run found a summary automate could not write (#183): the host refused
its write of a draft of the summary, automate returned the summary as text,
and the gate named no step for that, so the conductor composed a summary of
its own, frontmatter included. The gate now writes automate's text unchanged
at the summary's name, before anything reads it, and logs that it did; the
pins below also hold the maintainer's ruling that the step names no host's
rule and adds no automate pass.
"""

from __future__ import annotations

import functools
import hashlib
import http.server
import importlib.util
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REFS = Path(__file__).resolve().parents[2] / "references"
GATE = (REFS / "gate.md").read_text(encoding="utf-8")
EXECUTE = (REFS / "execute.md").read_text(encoding="utf-8")


def _worktree_section() -> str:
    start = GATE.index("## Measure the commit, not the working tree")
    return GATE[start : GATE.index("\n## ", start + 1)]


def _delta_paragraph() -> str:
    start = GATE.index("**The delta cycle profile")
    return GATE[start : GATE.index("\n\n", start)]


# --- the worktree isolation rule ----------------------------------------------


def test_assessors_measure_a_worktree_of_the_commit():
    section = _worktree_section()
    assert "`git worktree add <tmp-path> <commit>`" in section
    assert "`git worktree remove --force <tmp-path>`" in section
    assert re.search(r"binds every assessor that runs or times anything", section)


def test_worktree_caveat_dependency_dirs_prefer_symlink_over_node_path():
    """NODE_PATH is honoured by the CJS resolver only; an ESM gate set breaks
    silently under it. The preference itself is asserted, not just the factoid:
    a rewrite recommending NODE_PATH while keeping the factoid inverted-in-place
    passed the factoid-only version of this test."""
    section = _worktree_section()
    assert re.search(r"prefer the symlink over resolver environment variables", section)
    assert re.search(r"Node's ESM resolver ignores `NODE_PATH` \(it is honoured by the CJS resolver only\)", section)
    assert re.search(r"root \*and\* nested", section)


def test_worktree_caveat_untracked_inputs_enumerated():
    section = _worktree_section()
    assert re.search(r"enumerate what the declared gate commands actually read", section)
    assert re.search(r"measures a different harness", section)


# --- a server the gate set reuses (#182) ----------------------------------------
#
# Playwright's `reuseExistingServer` attached a gate worktree's browser runs to a
# vite dev server started from the main tree, so they measured the main tree's
# source, and a source mutation automate wrote into the worktree read `GREEN`
# without any run seeing it (test_probe_servers.py reproduces that).

_REUSED = "- **A server the gate set reuses does not follow the commit.**"
_REUSED_SAYS = (
    "`reuseExistingServer`",
    "Read each runner config the declared gate commands load, list each URL it may reuse (`http://localhost:<port>` "
    "for an entry that gives only a port)",
    "and check them before the first run in the worktree and again after the rebuild, with "
    "`uv run {skill-root}/scripts/probe_servers.py --url <url>`",
    "A server that answers is not the gate's to stop.",
    # The own-server route, where the runner config allows one.
    "When the runner config lets the worktree's runs have their own server without editing a tracked file, give them "
    "one:",
    "to a port the probe reports free, with reuse turned off and the base URL pointed at that port.",
    "The runner takes it by its config flag (`--config <file>` for Playwright), never by an environment variable set "
    "in front of the command, which the command's allow rule does not match past.",
    "Tell every assessor to run the runner with it, a mutation row's `command` included,",
    # Otherwise the limit, in every brief, automate's included.
    "Otherwise tell every assessor, automate included, in its brief, which URL answers",
    "and that no mutation in the worktree reaches it.",
    "Tell automate, too, that it writes no mutation row whose mutant only a run through that server would load:",
    "and a risk on a P0 criterion that no such row can measure is one it leaves unmeasured",
    "Any such row it runs, one behind a carried `gate-gap:` line or a previous backfill included, is a row that "
    "cannot run, whatever `mutate_check.py` prints",
    "so it is no gap, no test is backfilled for it and no `unkilled` line is logged from it.",
)


def _caveats(section: str) -> list[str]:
    """The caveat bullets: the `- **` lines after the sentence that counts them."""
    lead = re.search(r"(\w+) caveats the setup owes, each a measured failure when skipped:", section)
    if lead is None:
        return []
    block = section[lead.end() :].split("\n\n", 2)[1]
    return [line for line in block.splitlines() if line.startswith("- **")]


def _reused_server_bullet(section: str) -> str:
    return next((line for line in section.splitlines() if line.startswith(_REUSED)), "")


def _owns_a_reused_server(section: str) -> bool:
    bullet = _reused_server_bullet(section)
    lead = re.search(r"(\w+) caveats the setup owes", section)
    return bool(
        bullet
        and lead
        and lead.group(1) == "Four"
        and len(_caveats(section)) == 4
        and all(phrase in bullet for phrase in _REUSED_SAYS)
    )


def test_worktree_caveat_a_reused_server_is_probed_and_never_measured_as_the_commit():
    assert _owns_a_reused_server(_worktree_section())


def test_reused_server_predicate_rejects_the_three_caveat_section():
    """3.2.0's section: three caveats, none naming a process the runner reuses."""
    section = _worktree_section()
    bullet = _reused_server_bullet(section)
    assert bullet
    pre = section.replace(bullet + "\n", "").replace("Four caveats", "Three caveats")
    assert len(_caveats(pre)) == 3
    assert pre != section, "the mutant must actually change the text"
    assert not _owns_a_reused_server(pre)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # A GREEN through the reused server read by mutate_check.py's word: a false gap, a backfill, an `unkilled`.
        ("is a row that cannot run, whatever `mutate_check.py` prints", "is read by what `mutate_check.py` prints"),
        ("so it is no gap, no test is backfilled for it and no `unkilled` line is logged from it.",
         "so it is a gap like any other."),
        # Checked once only: a server started after the first check goes unseen by trace, NFR and test review.
        ("before the first run in the worktree and again after the rebuild", "before the first run in the worktree"),
        # The operator's server stopped by the run.
        ("A server that answers is not the gate's to stop.", "Stop a server that answers."),
        # No own-server route, so every project takes the stated limit.
        ("give them one:", "say so in the brief:"),
        # A moved server the runner still reuses, or one reached through an assignment no allow rule matches.
        ("with reuse turned off and the base URL", "with the base URL"),
        ("never by an environment variable set in front of the command, which the command's allow rule does not match "
         "past", "or by setting `BASE_URL` in front of the command"),
        # Automate's brief without the limit, though it is the assessor that runs the mutants.
        ("Otherwise tell every assessor, automate included, in its brief,",
         "Otherwise tell trace, NFR and test review, in their briefs,"),
        # A fifth caveat added without its count, or this one counted without its bullet.
        ("Four caveats the setup owes", "Five caveats the setup owes"),
    ],
)
def test_reused_server_predicate_rejects_a_one_clause_mutant(old, new):
    section = _worktree_section()
    mutant = section.replace(old, new)
    assert mutant != section, "the mutant must actually change the text"
    assert not _owns_a_reused_server(mutant)


_REUSED_CANNOT_RUN = (
    "A row whose mutant only a run through a server the gate set reuses would load cannot run either, whatever "
    "`mutate_check.py` prints, and the two bullets above do not read it (\"A server the gate set reuses does not "
    "follow the commit\", under \"Measure the commit, not the working tree\"): that run measures the tree the server "
    "was started from and never the mutant, so its `GREEN` is no gap, no test is backfilled for it and no `unkilled` "
    "line is logged from it."
)


def _reading_a_served_row(para: str, status: str, detail: str, through_reused: bool) -> str | None:
    """How gate.md reads a row: one whose mutant only a run through a reused
    server would load by the cannot-run bullet, when that bullet names such a
    row, before the two bullets above it; any other row as `_reading` does."""
    bullet = next((line for line in para.splitlines() if line.startswith("- A row cannot run when it reads")), "")
    if through_reused and _REUSED_CANNOT_RUN in re.sub(r"\s+", " ", bullet):
        return "cannot run"
    return _reading(para, status, detail)


def _served_rows(tmp_path: Path) -> tuple[dict, dict]:
    """Measured on `mutate_check.py`: one row whose command fetches a page from
    a server started from another tree (the main tree's dev server), and the
    same row through a server started from the worktree."""
    mutate_check = _load_script("mutate_check")
    main_tree, worktree = tmp_path / "main", tmp_path / "worktree"
    for tree in (main_tree, worktree):
        tree.mkdir()
        (tree / "app.txt").write_text("ok\n", encoding="utf-8", newline="\n")
    (worktree / "check_app.py").write_text(
        "import sys\nimport urllib.request\n\n"
        # No proxy: a request sent through one set in the environment would not reach this machine's 127.0.0.1.
        "opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))\n"
        "body = opener.open(f'http://127.0.0.1:{sys.argv[1]}/app.txt').read()\n"
        "if body != b'ok\\n':\n"
        "    print('FAILED test_app_serves_ok')\n    print('1 failed')\n    sys.exit(1)\n"
        "print('1 passed')\n",
        encoding="utf-8",
        newline="\n",
    )

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    servers = [
        http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tree)))
        for tree in (main_tree, worktree)
    ]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        reused, own = (
            mutate_check.run_table(
                [
                    {
                        "file": "app.txt",
                        "anchor": "ok\n",
                        "replacement": "broken\n",
                        "command": f'"{sys.executable}" check_app.py {server.server_address[1]}',
                        "expect_red": "test_app_serves_ok",
                    }
                ],
                worktree,
            )[0][0]
            for server in servers
        )
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
    return reused, own


def test_a_row_through_a_reused_server_is_one_that_cannot_run(tmp_path):
    """The row through the main tree's server reads `GREEN`, though its mutant
    never reached the run: read as a gap, it was backfilled, or logged
    `unkilled` once a backfilled spec read `GREEN` again. It now cannot run,
    so the gap is measured afresh once and otherwise logged `unmeasured`. The
    worktree's own server sees the mutant, and that row reads killed."""
    reused, own = _served_rows(tmp_path)
    para = _bound()
    assert reused["status"] == "GREEN", reused
    assert own["status"].startswith("KILLED"), own
    assert _reading_a_served_row(para, reused["status"], reused["detail"], through_reused=True) == "cannot run"
    assert _reading_a_served_row(para, own["status"], own["detail"], through_reused=False) == "killed"
    assert _REUSED_CANNOT_RUN in re.sub(r"\s+", " ", para)
    assert _AFRESH_ONCE in re.sub(r"\s+", " ", para)


def test_without_the_reused_server_rule_that_row_reads_as_a_false_gap(tmp_path):
    """The mutant twin, 3.2.0's bullet: the same row reads as a gap."""
    reused, _ = _served_rows(tmp_path)
    para = _bound()
    mutant = para.replace(" " + _REUSED_CANNOT_RUN, "")
    assert mutant != para, "the mutant must actually change the text"
    assert _reading_a_served_row(mutant, reused["status"], reused["detail"], through_reused=True) == "gap"


_REBUILD_RECHECKS = (
    "Then check the URLs the gate set may reuse again (\"A server the gate set reuses does not follow the commit\" "
    "above), and act on what it finds, as that caveat says, before trace, NFR and test review start: a server may "
    "have started since the first check, one started from the old worktree among them, which outlives the "
    "worktree's removal."
)


def test_the_rebuild_checks_the_reused_servers_again():
    assert _REBUILD_RECHECKS in re.sub(r"\s+", " ", _rebuild())


def test_rebuild_predicate_rejects_a_rebuild_with_no_second_check():
    """The mutant twin: a rebuild that checks nothing again lets trace, NFR and
    test review run through a server started after the first check."""
    para = _rebuild()
    mutant = para.replace(" " + _REBUILD_RECHECKS, "")
    assert mutant != para, "the mutant must actually change the text"
    assert _REBUILD_RECHECKS not in re.sub(r"\s+", " ", mutant)


_HONEST_ABOUT_THE_SERVER = (
    "When a runner reused a server the gate did not start, the line also names its URL, the folder it ran from when "
    "the probe could read one, and what it left unmeasured."
)


def _honesty_line(section: str) -> str:
    return _paragraph(section, "Record in `.decision-log.md`, once per gated story")


def test_worktree_honesty_line_names_a_reused_server():
    assert _HONEST_ABOUT_THE_SERVER in _honesty_line(_worktree_section())


def test_honesty_predicate_rejects_a_line_silent_on_the_server():
    """The mutant twin: unmutated browser evidence through another tree's
    server, recorded as the worktree's."""
    section = _worktree_section()
    mutant = section.replace(" " + _HONEST_ABOUT_THE_SERVER, "")
    assert mutant != section, "the mutant must actually change the text"
    assert _HONEST_ABOUT_THE_SERVER not in _honesty_line(mutant)


_TIP_SAYS = (
    "**Stop a dev server before an unattended drive.**",
    "a mutation the gate writes into the worktree never reaches them.",
    "The gate checks the URLs a runner config may reuse and never stops a server it did not start:",
)


def _tip_gaps(tips: str) -> list[str]:
    return [phrase for phrase in _TIP_SAYS if phrase not in re.sub(r"\s+", " ", tips)]


def _tips() -> str:
    return (_REPO_ROOT / "docs" / "operating-tips.md").read_text(encoding="utf-8")


def test_the_operating_tips_say_to_stop_a_dev_server_before_a_drive():
    assert _tip_gaps(_tips()) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("**Stop a dev server before an unattended drive.**", "**A dev server can stay up during a drive.**"),
        ("and never stops a server it did not start:", "and stops any server that answers:"),
    ],
)
def test_tip_predicate_rejects_a_tip_that_contradicts_the_gate(old, new):
    tips = _tips()
    mutant = tips.replace(old, new)
    assert mutant != tips, "the mutant must actually change the text"
    assert _tip_gaps(mutant)


_REUSED_FRAGMENT_SAYS = (
    "again after the rebuild",
    "The new `scripts/probe_servers.py`, run with `uv run`,",
    "The gate never stops such a server.",
    "otherwise it tells every assessor, automate included, what the server limits.",
    "a row it runs through that server reads as one that cannot run, whatever `mutate_check.py` prints, rather than "
    "as a `GREEN` gap: no test is backfilled for it and no `unkilled` line is logged from it,",
)


def _reused_fragment() -> str:
    return re.sub(
        r"\s+", " ", (_REPO_ROOT / "changes" / "gate-worktree-reused-server.yaml").read_text(encoding="utf-8")
    )


def _reused_fragment_gaps(fragment: str) -> list[str]:
    missing = [phrase for phrase in _REUSED_FRAGMENT_SAYS if phrase not in fragment]
    if not fragment.startswith("type: fixed"):
        missing.append("#182 is a fix")
    return missing


def test_the_reused_server_fragment_says_what_the_prose_does():
    assert _reused_fragment_gaps(_reused_fragment()) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("reads as one that cannot run, whatever `mutate_check.py` prints, rather than as a `GREEN` gap",
         "reads as a `GREEN` gap"),
        ("The gate never stops such a server.", "The gate stops such a server."),
        (", automate included,", ""),
        ("type: fixed", "type: changed"),
    ],
)
def test_reused_fragment_predicate_rejects_a_sentence_that_contradicts_the_prose(old, new):
    fragment = _reused_fragment()
    mutant = fragment.replace(old, new)
    assert mutant != fragment, "the mutant must actually change the text"
    assert _reused_fragment_gaps(mutant)


def test_worktree_licenses_no_overlap():
    """Part B (build N+1 while N gates) is a separate decision with its own
    risk budget; this section must say the sequence is unchanged or it becomes
    the smuggling route for it."""
    section = _worktree_section()
    assert re.search(r"licenses no overlap", section)
    assert re.search(r"sequential spine is unchanged", section)


def test_worktree_honesty_line_in_decision_log():
    section = _worktree_section()
    assert re.search(r"whether the gate measured a worktree or the main tree", section)
    assert re.search(r"false claim about the evidence", section)


# --- the delta cycle profile (instruction side) --------------------------------


def test_delta_profile_bounded_by_mechanical_attribution_fallback():
    """Trigger AND consequent: an inverted fallback ("assign it to the likeliest
    dimension and proceed") satisfied the trigger-only version of this test."""
    para = _delta_paragraph()
    assert "`--cycle-profile delta`" in para
    assert re.search(r"caps the verdict at `reloop`", para)
    assert re.search(r"fallback is mechanical, not judgment", para)
    assert re.search(r"lacks a clean dimension attribution.*run the full gate", para, re.S)


def test_delta_profile_pairs_with_the_sweep_split():
    para = _delta_paragraph()
    assert re.search(r"mid-loop cycles ride `scope=scoped` sweeps and delta gates", para)
    assert re.search(r"advance-bound cycle runs the full sweep and the full gate", para)


def test_delta_profile_is_not_a_light_mode():
    """The exact policy sentence, not a satisfiable-by-inversion wildcard."""
    para = _delta_paragraph()
    assert "so the profile buys nothing there; omit it" in para


def test_delta_recheck_base_is_recorded_state():
    """The non-failing assessors' diff base must be computable from the record:
    the previous gate's assessed-commit line, with a missing line routing to
    the full gate rather than to a guessed base."""
    para = _delta_paragraph()
    assert re.search(r"previous gate's `assessed-commit` line", para)
    assert re.search(r"without that line[^.]*run the full gate", para)
    # And the Run-the-gate section actually orders that line written.
    assert re.search(r"log `assessed-commit: <sha>`", GATE)


def test_worktree_outputs_land_in_the_main_tree():
    """The fail-open this pins: an artifact written into the worktree dies with
    it, and the gate re-reads the previous cycle's same-named artifact as
    current (name-based resolution, no freshness check)."""
    section = _worktree_section()
    assert re.search(r"Their OUTPUTS go home", section)
    assert re.search(r"resolved to absolute paths against `\{project-root\}`", section)
    assert re.search(r"the main tree is the record", section)
    assert re.search(r"stale PASS advancing a story whose fresh assessment was never read", section)


def test_worktree_placement_and_teardown_are_pinned():
    section = _worktree_section()
    assert ".gate-worktree-<story_id>" in section
    assert "`git worktree remove --force <tmp-path>`" in section
    assert "`git worktree prune`" in section
    assert re.search(r"never an improvised repo-root directory", section)


def test_cap_only_carveout_names_both_caps_and_drops_the_flag():
    """A delta-cap-only reloop must reach the ceremony skip, and the re-gate
    must drop the flag or it caps again forever."""
    assert re.search(r"the sweep-scope cap, the delta-profile cap, or both", GATE)
    assert re.search(r"dropping\s+`--cycle-profile`", GATE)


# --- automate first and alone (#174) -------------------------------------------


def _backfill_section() -> str:
    start = GATE.index("## Backfill the gate evidence")
    return GATE[start : GATE.index("\n## ", start + 1)]


def _between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i : text.index(end, i)]


def _paragraph(text: str, opener: str) -> str:
    start = text.index(opener)
    end = text.find("\n\n", start)
    return text[start : end if end != -1 else len(text)]


_ORDER = (
    "1. `bmad-testarch-automate` backfills coverage",
    "2. Once automate has finished, log its `gate-gap:` lines",
    "3. `bmad-testarch-trace` (re)builds",
)


def _runs_automate_alone(section: str) -> bool:
    """Automate is step 1 and alone, its commit and the rebuild are step 2,
    trace is step 3, and NFR and test review wait for step 2."""
    if not all(step in section for step in _ORDER):
        return False
    positions = [section.index(step) for step in _ORDER]
    return bool(
        positions == sorted(positions)
        and "**It runs first and alone.**" in section
        and re.search(
            r"no other assessor reads, runs or times anything in the worktree until automate has finished",
            section,
        )
        and re.search(r"once step 2 is done, run them in any order, or concurrently with trace", section)
        and re.search(
            r"None of the three may edit a file in the worktree, so none of them runs a mutant: an assessor that "
            r"would probe one names the mutant it would run as a finding in its own artifact instead, and when you "
            r"delegate NFR or test review, tell it so",
            section,
        )
    )


def test_automate_runs_first_and_alone():
    assert _runs_automate_alone(_backfill_section())


def test_alone_predicate_rejects_the_pre_edit_licence():
    """The pre-edit wording let NFR and test review run beside automate's
    mutation runs in the one worktree, which is how a mutant reached a sibling's
    measurement."""
    pre_edit = (
        "**The only ordering constraint is `bmad-testarch-automate` to `bmad-testarch-trace`**: "
        "trace reads the coverage automate backfills, so that pair runs in series:\n\n"
        "1. `bmad-testarch-automate` backfills coverage for code that landed during Execute, then\n"
        "2. `bmad-testarch-trace` (re)build the traceability matrix and write the gate decision.\n\n"
        "`bmad-testarch-nfr` and `bmad-testarch-test-review` are independent of each other and of "
        "the automate-to-trace chain, so run them in any order, or concurrently with it."
    )
    assert not _runs_automate_alone(pre_edit)
    assert "The only ordering constraint" not in GATE
    assert "or concurrently with it;" not in GATE


def test_alone_predicate_rejects_a_licence_to_run_beside_automate():
    section = _backfill_section()
    mutant = section.replace(
        "once step 2 is done, run them in any order, or concurrently with trace",
        "run them in any order, or concurrently with automate",
    )
    assert mutant != section, "the mutant must actually change the text"
    assert not _runs_automate_alone(mutant)


_PROBE_RULE = (
    "so none of them runs a mutant: an assessor that would probe one names the mutant it would run as a "
    "finding in its own artifact instead, and when you delegate NFR or test review, tell it so"
)


def test_alone_predicate_rejects_an_assessor_that_probes_a_mutant_in_the_worktree():
    """A mutant run in the shared worktree is the #174 contamination, whoever
    runs it; the first wording sent it to a copy no sentence located."""
    section = _backfill_section()
    mutant = section.replace(_PROBE_RULE, "and an assessor that probes a mutant may do it in the worktree")
    assert mutant != section, "the mutant must actually change the text"
    assert not _runs_automate_alone(mutant)
    assert "does it on a copy outside the worktree" not in GATE


_SUB_SKILL_HALT = (
    "A sub-skill that blocks on input or is not installed still escalates the story, at this step or any other, as "
    "`references/execute.md`'s sub-skill halt catch-all says."
)


def _only_a_red_sweep_stops(step: str) -> bool:
    """The maintainer's rule: a script result (a red sweep) is the one stop
    before trace that automate's pass and its backfill can produce, and no
    logged gap ends a cycle. A sub-skill halt still escalates, so the rule is
    scoped to what automate produces rather than to every stop."""
    flat = re.sub(r"\s+", " ", step)
    return bool(
        re.search(
            r"log its `gate-gap:` lines \(\"A reported gap stays open until a later pass measures it closed\" below\)",
            step,
        )
        and re.search(
            r"A red backfill sweep ends the cycle here instead, before trace \(\"A red backfill sweep ends the cycle "
            r"at a re-loop\" below\), and nothing else automate's pass or its backfill produces does: a `gate-gap:` "
            r"line never ends a cycle\.",
            step,
        )
        and _SUB_SKILL_HALT in flat
        and "P0" not in step
    )


def test_step_two_ends_the_cycle_only_on_a_red_sweep():
    assert _only_a_red_sweep_stops(_between(_backfill_section(), _ORDER[1], _ORDER[2]))
    # The catch-all step 2 points at covers a sub-skill that is not installed too.
    assert (
        "A sub-skill that is not installed at all (the Skill tool does not know its name) takes the same route: "
        "escalate" in EXECUTE
    )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The first wording: absolute, so a sub-skill halt mid-gate had two rules.
        ("and nothing else automate's pass or its backfill produces does", "and nothing else does"),
        (" " + _SUB_SKILL_HALT, ""),
    ],
)
def test_stop_predicate_rejects_an_unscoped_only_stop(old, new):
    step = re.sub(r"\s+", " ", _between(_backfill_section(), _ORDER[1], _ORDER[2]))
    mutant = step.replace(old, new)
    assert mutant != step, "the mutant must actually change the text"
    assert not _only_a_red_sweep_stops(mutant)


def test_stop_predicate_rejects_the_p0_gap_stop_the_maintainer_overruled():
    step = _between(_backfill_section(), _ORDER[1], _ORDER[2])
    overruled = (
        "2. Once automate has finished, log its `gate-gap:` lines (\"A reported gap stays open until a later pass "
        "measures it closed\" below), commit its backfill if it made one (\"When automate backfills\" below), then "
        "rebuild the gate worktree at the commit under assessment (\"Rebuild the worktree once automate has "
        "finished\" below). A red backfill sweep, or an open `gate-gap:` line on a P0 criterion, ends the cycle "
        "here instead, before trace (\"A red backfill sweep or an open P0 gap ends the cycle at a re-loop\" below).\n"
    )
    assert not _only_a_red_sweep_stops(overruled)
    assert _only_a_red_sweep_stops(step)


_OVERRULED = "open P0 gap"


def test_no_surface_sends_a_gap_to_a_reloop_before_trace():
    """The maintainer's ruling, "write a test, never block": every copy of the
    rule that a P0 gap ends its cycle before trace is gone."""
    surfaces = {
        "gate.md": GATE,
        "execute.md": EXECUTE,
        "gate-model.md": (_REPO_ROOT / "docs" / "gate-model.md").read_text(encoding="utf-8"),
        "backfill fragment": (_REPO_ROOT / "changes" / "gate-automate-backfill-commit.yaml").read_text(
            encoding="utf-8"
        ),
    }
    for name, text in surfaces.items():
        flat = re.sub(r"\s+", " ", text)
        assert _OVERRULED not in flat, name
        assert "an open gap on a P0 criterion" not in flat, name
        assert "P0 gap never reaches trace" not in flat, name
        assert "is gate-blocking too" not in flat, name
    assert "A green sweep goes on to step 3 unless" not in GATE


# A gap by any of its names, in any case: an `unkilled` or `unmeasured` line is a
# `gate-gap:` line, a `GREEN` row is a gap again, and a surviving mutant is one, so
# a sentence can route one without the word "gap". A route by any of its verbs
# too: a sentence that holds or stops the story, keeps it at `review`, sends it
# back to Execute, fails it or defers it changes its route as surely as one that
# re-loops it.
_GAP = re.compile(r"\bgaps?\b|gate-gap|\bunkilled\b|\bunmeasured\b|`GREEN`|surviv(?:or|ing mutant)", re.I)
_ROUTE = re.compile(
    r"re-?loop|escalat|ends? (?:the|a|its) cycle|sends? (?:a|the|it)\b"
    r"|\b(?:holds?|keeps?|blocks?|stops?|parks?|halts?|fails?|routes?|loops?) (?:the|a|its|this|that) "
    r"(?:story|stories|advance|run|Epic|done sync|gate|Finalize)"
    r"|at `review`|back to (?:Execute|`review`|`in-progress`|dev)|correct-course|from advancing|re-?drives?"
    r"|\bloops? back",
    re.I,
)
# Route words whose case carries the meaning: a gate `FAIL`, and the route and
# status names a sentence can hand a story.
_ROUTE_NAMES = re.compile(r"\bFAIL\b|gate-blocking|`defer`|`blocked`|decision-pending|`in-progress`")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*(\"-])")
_GAP_ROUTE_SENTENCES = {
    "gate.md": (
        ("**A red backfill sweep and the `gate-gap:` lines take this route their o", "5a2e9c096ce6"),
        ("- A row that reads `GREEN` is still a gap unless it reads killed when re", "3e2d3fc82a87"),
        ("A `gate-gap:` line never changes the route the verdict takes, and each r", "50bb3001484c"),
        ("A re-loop sent to close a reported gap often adds only a test, which lea", "9d1ca0df0d3f"),
        ("A re-run of the previous backfill's mutation table alone would leave a r", "72d065e855d6"),
        ("A red backfill sweep ends the cycle here instead, before trace (\"A red b", "8f40b503ed2c"),
        ("A row from a `gate-gap:` line is neither a FAIL nor a critical finding, ", "82ccbaf6ae2d"),
        ("A row from an open `gate-gap:` line is always `med`: whatever its criter", "2d48981044c4"),
        ("An open `gate-gap:` line in a cycle whose re-loop is cap-only is not one", "dce7a8288ce2"),
        ("An open `gate-gap:` line is neither a FAIL nor a critical finding, whate", "4a2a9042f915"),
        ("No `gate-gap:` line, on any criterion, sends a story to this route: only", "4a7a9665cb92"),
        ("No such row is a gate FAIL or a critical finding, whatever its criterion", "fcea9e5c10a5"),
        ("Of what automate's pass and its backfill produce, it is the one thing th", "1e0272c410c2"),
        ("On `owed: true`, take `escalate` with `kind` `operator-evidence-owed`: `", "2c68ae51e44a"),
        ("On a `reloop` from `gate_eval.py` that is not cap-only, each open `gate-", "563f6cff0aa6"),
        ("One heading per Epic, then a row per parked item; `status` is `open` at ", "f1e1214fac05"),
        ("Only non-gate-blocking work (CONCERNS, non-critical findings, parked dec", "cf302cd47862"),
        ("Then take the `reloop` route under \"Route on the verdict\" with the red a", "495cb8d41eb8"),
    ),
    # Reviewed: the heartbeat's time gap since a prior run, and a formalize gap, not coverage gaps.
    "preflight.md": (
        ("- **Purge stale run markers.** Delete any `{workflow.implementation_arti", "0da82953aa14"),
        ("A `--story` key that names no not-`done` story row of the Epic is a gap ", "bfbb8059a532"),
    ),
    "SKILL.md": (
        ("**A resume routed into Execute does NOT re-run the Stage-2 formalize gat", "eb3a0433fa26"),
    ),
    "gate-model.md": (
        ("A `gate-gap:` row is neither, whatever its criterion's priority: it reac", "ebba9c527611"),
        ("This is reinforced by the routing invariant in Stage 5: **a P0/critical ", "08bbb9c0834a"),
    ),
    "how-it-works.md": (
        ("The **deferred-work ledger** (at `deferred_work_path`, outside the run f", "5ec2c7433cc7"),
    ),
    "backfill fragment": (
        ("A `gate-gap:` line never changes the route a verdict takes: on a `reloop", "40555bb9276c"),
        ("A red that needs any other change ends the cycle before trace, and of wh", "b1f4ed28379b"),
    ),
}


def _reviewed(sentence: str) -> tuple[str, str]:
    """A sentence as a reviewed list holds it: its opening, to find it by, and a
    digest of the whole of it, so a clause added inside a reviewed sentence makes
    it a sentence nobody has reviewed yet."""
    return sentence[:72], hashlib.sha256(sentence.encode("utf-8")).hexdigest()[:12]


def _gap_route_sentences(text: str) -> tuple[tuple[str, str], ...]:
    """Every sentence that names a gap beside a route word, as `_reviewed` holds it."""
    flat = re.sub(r"\s+", " ", text)
    return tuple(
        sorted(
            {
                _reviewed(s)
                for s in _SENTENCE.split(flat)
                if _GAP.search(s) and (_ROUTE.search(s) or _ROUTE_NAMES.search(s))
            }
        )
    )


def _gate_surfaces() -> dict[str, str]:
    """Every surface a conductor or a reader takes the gate's routes from: the
    skill's non-negotiables, every stage reference, the docs that describe the
    gate, the two skills an operator reads a stopped run through and the
    fragments of this change."""
    docs, changes = _REPO_ROOT / "docs", _REPO_ROOT / "changes"
    surfaces = {ref.name: ref.read_text(encoding="utf-8") for ref in sorted(REFS.glob("*.md"))}
    surfaces.update(
        {
            "SKILL.md": (REFS.parent / "SKILL.md").read_text(encoding="utf-8"),
            "gate-model.md": (docs / "gate-model.md").read_text(encoding="utf-8"),
            "how-it-works.md": (docs / "how-it-works.md").read_text(encoding="utf-8"),
            "troubleshooting.md": (docs / "troubleshooting.md").read_text(encoding="utf-8"),
            "operating-tips.md": (docs / "operating-tips.md").read_text(encoding="utf-8"),
            "ucg-resolve SKILL.md": (REFS.parent.parent / "ucg-resolve" / "SKILL.md").read_text(encoding="utf-8"),
            "ucg-status SKILL.md": (REFS.parent.parent / "ucg-status" / "SKILL.md").read_text(encoding="utf-8"),
            "backfill fragment": (changes / "gate-automate-backfill-commit.yaml").read_text(encoding="utf-8"),
            "alone fragment": (changes / "gate-automate-runs-alone.yaml").read_text(encoding="utf-8"),
            "collection fragment": (changes / "mutate-check-collection-error.yaml").read_text(encoding="utf-8"),
            "count fragment": (changes / "mutate-check-count-misreads.yaml").read_text(encoding="utf-8"),
            "reused-server fragment": (changes / "gate-worktree-reused-server.yaml").read_text(encoding="utf-8"),
        }
    )
    return surfaces


def test_every_sentence_that_puts_a_gap_beside_a_route_is_one_reviewed_against_the_ruling():
    """The maintainer's ruling: only gate_eval.py reading TEA's gate file
    decides a route, the only stop before trace is a red backfill sweep, and a
    `gate-gap:` line never changes the route a verdict takes. Each sentence
    below names a gap beside a re-loop, an escalation or a cycle's end, and each
    was read against that ruling; a new one (a P1 gap that escalates, a P0 gap
    "re-looped rather than parked", a ledger bar that sends a gap row back) has
    to be read the same way before it joins the list."""
    for name, text in _gate_surfaces().items():
        assert _gap_route_sentences(text) == tuple(sorted(_GAP_ROUTE_SENTENCES.get(name, ()))), name


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        # X2: the conductor's always-loaded non-negotiables.
        ("SKILL.md", "a P0/critical FAIL never defers", "a P0/critical FAIL or an open P0 `gate-gap:` line never defers"),
        ("how-it-works.md", "a P0/critical FAIL is never deferred.",
         "a P0/critical FAIL is never deferred, and an open P0 gap re-loops the story."),
        ("troubleshooting.md", "then `bmad-testarch-trace` and `bmad-testarch-nfr`) before the gate;",
         "then `bmad-testarch-trace` and `bmad-testarch-nfr`) before the gate, and an open P0 gap escalates;"),
        ("finalize.md", "**This never gates.**", "**This never gates.** An open P0 gap escalates the story here."),
        # V1: a gap routed by its line's own name, with no word "gap" in the sentence.
        ("SKILL.md", "it re-loops within budget or escalates.",
         "it re-loops within budget or escalates. An `unkilled` line on a P0 criterion re-loops the story too."),
        ("execute.md", "make no commit and take the `decision-pending` route below for that story",
         "make no commit and take the `decision-pending` route below for that story. An `unmeasured` line on a P0 "
         "criterion escalates the story"),
        # The status view, which an operator reads a stopped run through.
        ("ucg-status SKILL.md", "stops `evidence-owed` rather than `all-done`.",
         "stops `evidence-owed` rather than `all-done`. An open P0 `gate-gap:` line on that story re-loops it too."),
    ],
)
def test_the_gap_route_scan_covers_every_surface_beyond_gate_md(name, old, new):
    """`SKILL.md`, the other references and the docs were outside the scan, so
    a sentence there that routed a P0 gap passed the whole suite. So did one
    that routed an `unkilled` or `unmeasured` line without the word "gap"."""
    surfaces = _gate_surfaces()
    assert name in surfaces
    mutant = re.sub(r"\s+", " ", surfaces[name]).replace(old, new)
    assert mutant != re.sub(r"\s+", " ", surfaces[name]), "the mutant must actually change the text"
    assert _gap_route_sentences(mutant) != tuple(sorted(_GAP_ROUTE_SENTENCES.get(name, ())))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # M50
        ("and nothing else automate's pass or its backfill produces does: a `gate-gap:` line never ends a cycle.",
         "and nothing else automate's pass or its backfill produces does: a `gate-gap:` line never ends a cycle. An "
         "open `gate-gap:` line on a P1 criterion that a re-loop already took sends the story to escalate."),
        # M51
        ("is backfilled rather than parked", "is re-looped rather than parked"),
        # M47
        ("A `high` that maps to a gate FAIL or a P0/critical finding does **not** belong here",
         "A `high` that maps to a gate FAIL, a P0/critical finding or an open `gate-gap:` line on a P0 criterion does "
         "**not** belong here"),
        # M3: a route by another verb than re-loop or escalate.
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. Until a later pass kills its mutant, "
         "though, an `unkilled` line on a P0 criterion holds the story at `review`."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. An `unmeasured` line on a P0 "
         "criterion sends the story back to Execute instead."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. An open P0 gap stops the run."),
        # Routes by a gate result's own name, by a route's or a status's name, and by a gap's other names.
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. An open `gate-gap:` line on a P0 criterion blocks the gate."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. An `unkilled` line on a P0 criterion counts as a gate FAIL."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. An open `unkilled` line on a P0 criterion is gate-blocking, though."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. An `unmeasured` line on a P0 criterion turns an `advance` into a `defer`."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. Gaps on a P0 criterion re-loop the story."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. Unkilled lines on a P0 criterion escalate the story."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. A `GREEN` row on a P0 criterion re-loops the story."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. A P0 gap re-drives the story."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. An open P0 `gate-gap:` line ends the run `blocked`."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. An open P0 `gate-gap:` line takes the `decision-pending` route."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. An `unkilled` P0 line loops the story back to dev."),
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story. A surviving mutant on a P0 criterion leaves the story `in-progress`."),
        # A clause added inside a reviewed sentence is a sentence nobody reviewed.
        ("so it belongs on the ledger and never re-loops or escalates the story.",
         "so it belongs on the ledger and never re-loops or escalates the story, unless its criterion is P0."),
    ],
)
def test_gap_route_scanner_rejects_a_sentence_that_routes_a_gap(old, new):
    mutant = GATE.replace(old, new)
    assert mutant != GATE, "the mutant must actually change the text"
    assert _gap_route_sentences(mutant) != tuple(sorted(_GAP_ROUTE_SENTENCES["gate.md"]))


def _rebuild() -> str:
    return _paragraph(GATE, "**Rebuild the worktree once automate has finished (production).**")


def test_the_worktree_is_rebuilt_from_the_commit_after_automate():
    """No allowlisted command reads another worktree's status, so the gate
    replaces the worktree a mutation run touched instead of checking it."""
    para = _rebuild()
    assert para.index("`git worktree remove --force <tmp-path>`") < para.index(
        "`git worktree add <tmp-path> <commit>`"
    )
    assert re.search(r"at the commit under assessment \(the backfill's commit when automate made one", para)
    assert re.search(
        r"the same `link_worktree_deps\.py` call and copy the same untracked inputs in again", para
    )
    assert re.search(r"Rebuild whether or not automate backfilled", para)
    assert re.search(
        r"skip the rebuild only when no automate pass ran in this cycle \(`--light`, or a later cycle that skips it\)",
        para,
    )
    # A pass a resume reused ran in a dead session's worktree, which still holds its mutants' leftovers.
    assert re.search(r"whether this session ran the pass or a resume reused it", para)
    assert re.search(r"`git -C <tmp-path> status`, a command no allowlist entry covers", para)


_OVERCLAIM = "no assessor can contaminate another's measurement"


def _narrowed(bullet: str) -> bool:
    return bool(
        _OVERCLAIM not in bullet
        and re.search(r"no stray tree state, the next remediation's included, can contaminate a gate mid-read", bullet)
        and re.search(r"It does not keep the assessors apart, since they all measure the one worktree", bullet)
        and re.search(r"automate, the one assessor that edits source, runs alone and the worktree is rebuilt", bullet)
        and re.search(r"none of them changes the tree another one measures", bullet)
        and re.search(r"carries the load caveat `references/execute\.md` gives a wide sweep", bullet)
    )


def test_the_contamination_sentence_is_narrowed_to_what_holds():
    bullet = _paragraph(_worktree_section(), "- **The ordering rule stands.**")
    assert _narrowed(bullet)
    assert _OVERCLAIM not in GATE


def test_narrowed_predicate_rejects_the_pre_edit_bullet():
    pre_edit = (
        "- **The ordering rule stands.** Isolation removes the contamination, not the sequence. "
        "What it buys today is that no assessor can contaminate another's measurement and no "
        "stray tree state can contaminate a gate mid-read."
    )
    assert not _narrowed(pre_edit)


_NONWEB_WAIT = (
    "`bmad-testarch-test-review` are independent of trace and wait only for automate "
    "and the step after it, its backfill commit and the worktree rebuild"
)


def test_nfr_and_review_wait_for_automate_everywhere_gate_md_says_so():
    """The non-web section restates the order, so it must name the backfill
    commit and the rebuild too: started when automate finishes, NFR and test
    review would measure the old commit in a worktree mutation runs edited."""
    assert "independent of the automate→trace pair" not in GATE
    assert _NONWEB_WAIT in GATE
    # The first wording of this fix stopped at automate.
    assert "wait only for automate (see" not in GATE


def test_a_review_older_than_the_backfill_is_not_current():
    assert re.search(
        r"One written before automate's backfill is not current, since no review has read the tests",
        _backfill_section(),
    )


def test_worktree_honesty_line_names_the_rebuild():
    assert re.search(
        r"whether automate ran alone and the worktree was rebuilt before the other assessors started, "
        r"and names the commit it was rebuilt at",
        _worktree_section(),
    )


# --- the backfill is committed and the gate re-pointed before trace (#175) -----


_BOUND = "**At most one automate pass finishes per gate cycle, and a backfill never restarts the cycle.**"


def _backfill_commit() -> str:
    return _between(GATE, "**When automate backfills, commit the backfill before trace runs.**", _BOUND)


_COMMIT_STEPS = (
    "1. Stage the test files this pass's summary",
    "2. With them staged",
    "3. Once the sweep is green, write a fresh `.tests-ran-<story_id>` marker",
    "4. Run `references/execute.md` step 4's claim check",
    "5. Refresh `.commit-<story_id>` from `HEAD`",
)


def _commits_then_repoints(para: str) -> bool:
    if not all(step in para for step in _COMMIT_STEPS):
        return False
    positions = [para.index(step) for step in _COMMIT_STEPS]
    return bool(
        positions == sorted(positions)
        and re.search(r"So never run trace, NFR or test review on that commit", para)
        and re.search(r"While `\.current-story` still names this story", para)
        and re.search(r"by explicit path, in one call", para)
        and re.search(
            r"A path it lists that the summary does not name is not part of the backfill and stays unstaged", para
        )
        and re.search(r"run the full three-axis sweep over the main tree, cache-defeated", para)
        and re.search(r"copied from `\.baseline-<story_id>`, never re-derived, and `scope=full`", para)
        and re.search(r"in a call separate from the staging call", para)
        # M1: why the guard lets this commit through, which a conductor would otherwise expect it to deny.
        and re.search(
            r"The guard allows this commit as it allows the evidence commit in \"Route on the verdict\": the story is "
            r"still current, its marker was written in a prior call, and the index is not empty\.",
            para,
        )
        # M2: the backfill is part of its gate cycle, so no turn-ceiling check turns it into an escalation.
        and re.search(
            r"is not a re-loop: it writes no `class:` line, spends no re-loop, and never meets the turn-ceiling check "
            r"that runs before a re-loop",
            para,
        )
        and re.search(r"log `gate-backfill-base: <sha>` in `\.decision-log\.md`, naming `HEAD`", para)
        and para.index("`gate-backfill-base: <sha>`") < para.index(_COMMIT_STEPS[0])
        and re.search(r"log `gate-backfill: <sha>`", para)
        and re.search(
            r"The new commit is now the commit under assessment: the worktree is rebuilt at it, "
            r"trace, NFR and test review measure it, and the verdict's `assessed-commit` line names it",
            para,
        )
    )


def test_a_backfill_is_committed_and_the_gate_repointed_before_trace():
    assert _commits_then_repoints(_backfill_commit())


def test_backfill_predicate_rejects_trace_on_the_old_commit():
    para = _backfill_commit()
    mutant = para.replace("So never run trace, NFR or test review on that commit. ", "")
    assert mutant != para, "the mutant must actually change the text"
    assert not _commits_then_repoints(mutant)


def test_backfill_predicate_rejects_staging_paths_the_summary_does_not_name():
    """A sibling story's red-phase test sits in the same main tree; staging
    every listed path would carry it into this story's backfill commit."""
    para = _backfill_commit()
    mutant = para.replace(
        "A path it lists that the summary does not name is not part of the backfill and stays unstaged.",
        "Stage every path it lists, whether or not the summary names it.",
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _commits_then_repoints(mutant)


def test_backfill_predicate_rejects_a_marker_written_before_the_sweep():
    para = _backfill_commit()
    sweep = para[para.index(_COMMIT_STEPS[1]) : para.index(_COMMIT_STEPS[2])]
    marker = para[para.index(_COMMIT_STEPS[2]) : para.index(_COMMIT_STEPS[3])]
    mutant = para.replace(sweep + marker, marker + sweep)
    assert mutant != para, "the mutant must actually change the text"
    assert not _commits_then_repoints(mutant)


def test_the_backfill_is_no_reloop():
    para = _backfill_commit()
    assert re.search(r"is not a re-loop: it writes no `class:` line, spends no re-loop", para)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # M1
        (
            " The guard allows this commit as it allows the evidence commit in \"Route on the verdict\": the story is "
            "still current, its marker was written in a prior call, and the index is not empty.",
            "",
        ),
        # M2
        ("and never meets the turn-ceiling check", "and meets the turn-ceiling check"),
    ],
)
def test_backfill_predicate_rejects_a_dropped_guard_note_or_a_ceiling_check(old, new):
    para = _backfill_commit()
    mutant = para.replace(old, new)
    assert mutant != para, "the mutant must actually change the text"
    assert not _commits_then_repoints(mutant)


def test_the_staging_listing_names_files_inside_a_new_directory():
    """The plain `git status --porcelain` prints `?? tests/new/` for a new
    folder, so a backfilled test inside one looked absent and was left out of
    the backfill commit."""
    step = _between(_backfill_commit(), _COMMIT_STEPS[0], _COMMIT_STEPS[1])
    assert "`git status --porcelain --untracked-files=all` lists them" in step
    assert re.search(r"the plain `git status --porcelain` lists a new directory instead of the files in it", step)


def _step_one_recovers_or_logs(step: str) -> bool:
    return bool(
        re.search(
            r"this pass's summary \(`automation-summary-<story_id>-<sha>\.md`, with `<sha>` the `gate-backfill-base:` commit",
            step,
        )
        and re.search(
            r"look for the file in the worktree: at that path when the summary gives it under `<tmp-path>`, "
            r"and otherwise at the same repo-relative path under `<tmp-path>`",
            step,
        )
        and re.search(
            r"copy it to its repo-relative path in the main tree before the rebuild destroys it, and list again", step
        )
        and re.search(
            r"When git still lists no change at that path, or neither tree holds the file, the test the summary names "
            r"was never written: leave the path out, and log a `gate-gap:` line for the gap that test was written for",
            step,
        )
        and re.search(r"When this step stages nothing, there is no backfill: skip steps 2 through 5", step)
        and "otherwise log that git shows no change at that path" not in step
    )


def test_a_test_written_into_the_worktree_is_copied_and_a_lost_one_is_a_gap():
    """TEA names files repo-relative, so a test automate wrote into the
    worktree looked like a main-tree path git did not list, and the rebuild
    destroyed it with no gap logged for the P0 rule to act on."""
    assert _step_one_recovers_or_logs(_between(_backfill_commit(), _COMMIT_STEPS[0], _COMMIT_STEPS[1]))


def test_step_one_predicate_rejects_the_first_wording():
    step = _between(_backfill_commit(), _COMMIT_STEPS[0], _COMMIT_STEPS[1])
    start = step.index("A path the summary names that it does not list")
    first = (
        "A path the summary names that it does not list has no change in the main tree: when the summary gives "
        "that path under the worktree, automate wrote it there, so copy it into the main tree before the rebuild "
        "destroys it and list again; otherwise log that git shows no change at that path, and leave it out.\n"
    )
    mutant = step[:start] + first
    assert mutant != step, "the mutant must actually change the text"
    assert not _step_one_recovers_or_logs(mutant)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_the_prescribed_listing_shows_a_test_the_plain_one_hides(tmp_path):
    """The reason the step names the flag, measured on git itself."""
    _git(tmp_path, "init", "-q")
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "a.test.ts").write_text("a\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "init")
    (tmp_path / "tests" / "integration").mkdir()
    (tmp_path / "tests" / "integration" / "b.test.ts").write_text("b\n", encoding="utf-8")
    plain = _git(tmp_path, "status", "--porcelain").splitlines()
    every = _git(tmp_path, "status", "--porcelain", "--untracked-files=all").splitlines()
    assert plain == ["?? tests/integration/"]
    assert every == ["?? tests/integration/b.test.ts"]


def test_the_backfill_commit_removes_the_scratch_folder_its_claim_check_recreates():
    """Execute removes `.scratch-<story_id>/` after step 5, before the gate;
    the claim check writes its message files there again."""
    step = _between(_backfill_commit(), _COMMIT_STEPS[4], "The new commit is now the commit under assessment")
    assert re.search(r"remove `\.scratch-<story_id>/` again: the claim check's message files recreated it", step)
    assert re.search(r"`references/execute\.md` step 0 has it removed before the story advances", step)
    assert re.search(r"Remove the directory after step 5's re-verify goes green, before the story advances", EXECUTE)


# --- a red backfill sweep, and nothing else, ends the cycle before trace -------


_PRE_TRACE = "**A red backfill sweep ends the cycle at a re-loop.**"
_FINDINGS = (
    "with the red and every open `gate-gap:` line of this cycle that is neither `unmeasured` nor `unkilled` as its "
    "findings"
)
_RESUME_POINTER = (
    "A resume that finds this verdict logged and `HEAD` still at its `assessed-commit:` commit takes this re-loop "
    "where the log stopped (`references/execute.md`'s fifth resume case)."
)
_STANDS_IN = (
    "It stands in for the `gate_eval.py` result this cycle never produced: the run-status heartbeat's "
    "`last_reasons` copies its `reasons` (`references/execute.md`, \"Run-status heartbeat\"), and an attended run "
    "prints the one verdict line \"Attended runs also print the verdict, once\" (under \"Run the gate\") describes "
    "when this verdict is logged, with `n/a` as the `gate_status`."
)


def _reloop_bullet() -> str:
    return _between(GATE, "- **`reloop`**", "- **`escalate`**")


def _red_route(para: str) -> bool:
    step = para[para.index(_COMMIT_STEPS[1]) : para.index(_COMMIT_STEPS[2])]
    return bool(
        re.search(r"A red that a change to the backfilled test files alone fixes", step)
        and re.search(r"is fixed there, staged, and re-run, at most twice", step)
        and re.search(r"A red that needs a change to any other path, or that is still red after the second fix", step)
        and re.search(r"commit nothing, and take \"A red backfill sweep ends the cycle at a re-loop\" below", step)
        and re.search(r"A green sweep goes on to step 3, whatever `gate-gap:` lines this cycle has logged", step)
        and _PRE_TRACE in para
        and re.search(
            r"Of what automate's pass and its backfill produce, it is the one thing that ends a cycle before trace, "
            r"because a failing sweep is a script's result and not a judgment; a `gate-gap:` line never ends a cycle",
            para,
        )
        and re.search(r"commit nothing and run no trace, NFR or test review in this cycle", para)
        and re.search(
            r"Log this cycle's verdict in `\.decision-log\.md` as a fenced JSON object holding only `verdict` and "
            r"`reasons`, `\{\"verdict\": \"reloop\", \"reasons\": \[\.\.\.\]\}`, with one reason naming the red",
            para,
        )
        and re.search(
            r"an `assessed-commit:` line naming the `gate-backfill-base:` commit, the commit automate measured", para
        )
        and _STANDS_IN in para
        and re.search(
            r"take the `reloop` route under \"Route on the verdict\" " + re.escape(_FINDINGS) + r", turn-ceiling check included",
            para,
        )
        and re.search(r"the re-loop's `references/execute\.md` step 4 commits them with its fix", para)
        and _RESUME_POINTER in para
        and "one finding" not in para
        and "P0" not in para[para.index(_PRE_TRACE) :]
    )


def test_a_red_sweep_alone_ends_the_cycle_at_a_reloop_before_trace():
    """A source fix made inside the gate lands after automate's only pass, so
    no automate pass searches it and no generalize step reads it. A failing
    sweep is a script's result; a logged gap is not, so it never stops a cycle."""
    assert _red_route(_backfill_commit())
    reloop = _reloop_bullet()
    assert re.search(
        r"A re-loop that ended its cycle before trace \(\"A red backfill sweep ends the cycle at a re-loop\", under "
        r"\"Backfill the gate evidence\"\) takes the full route above, with its red and every open `gate-gap:` line "
        r"of its cycle that is neither `unmeasured` nor `unkilled` as its findings, and the gate after it is a full one",
        reloop,
    )
    # M21: the reloop bullet's own sentence that makes a gap one of gate_eval's re-loop's findings.
    assert re.search(
        r"On a `reloop` from `gate_eval\.py` that is not cap-only, each open `gate-gap:` line that is neither "
        r"`unmeasured` nor `unkilled` is among the findings the generalize step reads, though none of them is a "
        r"reason for the verdict",
        reloop,
    )
    assert re.search(
        r"No `gate-gap:` line, on any criterion, sends a story to this route: only the verdict or a red backfill "
        r"sweep does",
        reloop,
    )
    assert re.search(r"or when a red backfill sweep ended the cycle before trace", _rebuild())
    assert "one finding" not in GATE


def test_red_route_predicate_rejects_the_unscoped_one_thing():
    """"It is the one thing that ends a cycle before trace" contradicted the
    sub-skill halt catch-all, which also ends a cycle before trace."""
    para = _backfill_commit()
    mutant = para.replace("Of what automate's pass and its backfill produce, it is the one thing", "It is the one thing")
    assert mutant != para, "the mutant must actually change the text"
    assert not _red_route(mutant)


def test_red_route_predicate_rejects_a_red_as_the_one_finding():
    """The first wording took the red as the re-loop's one finding, which
    dropped every gap the same automate pass reported."""
    para = _backfill_commit()
    mutant = para.replace(_FINDINGS, "with the red as its one finding")
    assert mutant != para, "the mutant must actually change the text"
    assert not _red_route(mutant)


def test_red_route_predicate_rejects_a_p0_gap_that_ends_the_cycle():
    """The branch's own first answer to a P0 gap, which the maintainer overruled."""
    para = _backfill_commit()
    mutant = para.replace(
        "A green sweep goes on to step 3, whatever `gate-gap:` lines this cycle has logged.",
        "A green sweep goes on to step 3 unless an open `gate-gap:` line in this cycle's entry is on a P0 "
        "criterion: then commit nothing either, and take the same paragraph.",
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _red_route(mutant)


def test_red_route_predicate_rejects_a_verdict_logged_as_prose():
    """`gate_trail.py` reads a verdict only from a fenced JSON object, so a
    verdict logged as a word reads as no verdict at all."""
    para = _backfill_commit()
    start = para.index("Log this cycle's verdict in `.decision-log.md`")
    end = para.index("Then take the `reloop` route", start)
    mutant = (
        para[:start]
        + "Log the red in `.decision-log.md` as this cycle's verdict, `reloop`, with an `assessed-commit:` line "
        "naming the `gate-backfill-base:` commit. "
        + para[end:]
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _red_route(mutant)


def test_red_route_predicate_rejects_a_record_nothing_downstream_can_carry():
    """With no `gate_eval.py` result, the heartbeat and the attended print had
    no reasons and no `gate_status` to copy."""
    para = _backfill_commit()
    mutant = para.replace(_STANDS_IN + " ", "")
    assert mutant != para, "the mutant must actually change the text"
    assert not _red_route(mutant)


def test_red_route_predicate_rejects_a_record_with_no_resume_pointer():
    para = _backfill_commit()
    mutant = para.replace(" " + _RESUME_POINTER, "")
    assert mutant != para, "the mutant must actually change the text"
    assert not _red_route(mutant)


def test_the_heartbeat_names_the_pre_trace_record():
    """The heartbeat copied `last_reasons` from a `gate_eval.py` result, which a
    re-loop logged before trace never has. (The attended print's own paragraph
    keeps its wording; the red sweep's paragraph orders its `n/a` line.)"""
    heartbeat = _paragraph(EXECUTE, "`last_reasons` and `budget_used` are machine-derived")
    assert re.search(
        r"\(after a re-loop `references/gate\.md` logs before trace, in \"A red backfill sweep ends the cycle at a "
        r"re-loop\", no `gate_eval\.py` result exists, and it is the `reasons` array of the verdict object logged "
        r"there\)",
        heartbeat,
    )
    assert _STANDS_IN in _paragraph(GATE, _PRE_TRACE)
    # The pre-edit sentence, which a re-loop logged before trace could not follow.
    pre_edit = (
        "copied across unedited, so a poller sees *why* the last verdict landed instead of only the verdict word;"
    )
    assert pre_edit not in heartbeat


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"_prose_{name}", REFS.parent / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_the_pre_trace_verdict_record_is_one_the_gate_trail_reads(tmp_path):
    """The resume cursor and the trail key on a logged verdict, so the record
    gate.md prescribes must be one `recorded_verdicts` reads."""
    gate_trail = _load_script("gate_trail")
    shape = re.search(r'`(\{"verdict": "reloop", "reasons": \[\.\.\.\]\})`', _paragraph(GATE, _PRE_TRACE)).group(1)
    record = shape.replace("[...]", '["red backfill sweep: lint names tests/unit/a.test.ts"]')
    sha = "a" * 40
    log = tmp_path / ".decision-log.md"
    log.write_text(
        f"## Story 4-2\n\ngate-backfill-base: {sha}\n\n```json\n{record}\n```\n\nassessed-commit: {sha}\n",
        encoding="utf-8",
    )
    assert gate_trail.recorded_verdicts(log) == {"4-2": "reloop"}
    # The first wording logged the verdict as a word, which the trail never reads.
    log.write_text(f"## Story 4-2\n\nverdict: reloop (red backfill sweep)\nassessed-commit: {sha}\n", encoding="utf-8")
    assert gate_trail.recorded_verdicts(log) == {}


def test_a_staged_backfill_survives_an_escalation_and_the_next_gate_is_full():
    para = _paragraph(GATE, _PRE_TRACE)
    assert re.search(
        r"When the turn-ceiling check turns that re-loop into `escalate`, the backfilled files stay staged too, "
        r"and the escalation sidecar's `decision_needed` names each of them as staged for this story",
        para,
    )
    assert re.search(
        r"The cycle after this re-loop runs the full gate, never a delta gate: this cycle wrote no trace, NFR or "
        r"test review artifact for a delta gate to re-check",
        para,
    )
    assert re.search(
        r"A re-loop that ended its cycle before trace \(\"A red backfill sweep ends the cycle at a re-loop\"\) left "
        r"no trace, NFR or test review artifact to re-check, so the gate after it is always the full gate",
        _delta_paragraph(),
    )


def test_red_route_predicate_rejects_the_first_wording():
    para = _backfill_commit()
    step = para[para.index(_COMMIT_STEPS[1]) : para.index(_COMMIT_STEPS[2])]
    first = (
        "2. With them staged, so that a gate reading git's file list sees a new test file, run the full "
        "three-axis sweep over the main tree, cache-defeated and printed, as `references/execute.md` step 5 "
        "runs it. A red is step 5's red: remediate, stage what the remediation changed, and re-run to green "
        "before anything is committed.\n"
    )
    mutant = para.replace(step, first)
    assert mutant != para, "the mutant must actually change the text"
    assert not _red_route(mutant)


# --- a commit hook that rejects the backfill commit -------------------------------


_HOOK_AS_RED = (
    "A repo commit hook that rejects this commit is read as step 2's red, and `references/execute.md` step 4's own "
    "rule for a hook rejection does not apply to it: when a change to the backfilled test files alone answers the "
    "hook, make it there, stage it, and go back to step 2, whose sweep runs again before step 3 writes a fresh marker "
    "and this step retries the commit, all within step 2's budget of two fixes; when the hook needs a change to any "
    "other path, or rejects the commit again after the second fix, commit nothing, and take \"A red backfill sweep "
    "ends the cycle at a re-loop\" below."
)
_EXECUTE_HOOK_EXCEPTION = (
    "and only then retry the commit. This rule binds the story's own commits: this step's, and any re-commit or "
    "amend step 5 makes. The gate's two commits keep their own rules in `references/gate.md`: \"When automate "
    "backfills\" reads a hook rejection of its commit of a test `bmad-testarch-automate` backfilled as its backfill "
    "sweep's red, which it fixes only in the backfilled test files and otherwise ends the cycle at a re-loop, and the "
    "advance route says how to answer a hook rejection of its evidence commit."
)
_EVIDENCE_HOOK = (
    "reuse that marker as it stands and never rewrite it for this commit. A repo commit hook that rejects this commit "
    "is not `references/execute.md` step 4's case, whose rule for a hook rejection binds the story's own commits."
)
_EVIDENCE_EXECUTABLE = (
    "If it must carry an executable path all the same (a source or test file left uncommitted when trace ran, which "
    "this gate therefore never measured: log why), re-run the sweep and write a fresh marker"
)


def _hook_rejection_has_one_route(gate: str, execute: str) -> bool:
    """Step 4 of the story loop fixes a hook rejection anywhere and retries;
    inside the gate that fix would skip the generalize step, so the gate reads
    it as its sweep's red and execute.md names the exception."""
    para = re.sub(r"\s+", " ", _between(gate, "**When automate backfills, commit the backfill before trace runs.**", _BOUND))
    return bool(
        _HOOK_AS_RED in para
        and "is fixed there, staged, and re-run, at most twice in this backfill, a fix step 4 makes for a commit hook "
        "included." in para
        and "A red in step 2's sweep, a commit hook's rejection at step 4 included, that needs a change outside the "
        "backfilled test files, or is still red after the second fix, means the backfill has found a defect in the "
        "story's code." in para
        and _EXECUTE_HOOK_EXCEPTION in re.sub(r"\s+", " ", execute)
        # The evidence commit reuses its marker, so step 4's rule must not reach it.
        and _EVIDENCE_HOOK in re.sub(r"\s+", " ", gate)
        and _EVIDENCE_EXECUTABLE in re.sub(r"\s+", " ", gate)
        and "is the one exception" not in execute
    )


def test_a_hook_rejection_of_the_backfill_commit_is_the_sweeps_red():
    assert _hook_rejection_has_one_route(GATE, EXECUTE)


@pytest.mark.parametrize(
    ("where", "old", "new"),
    [
        ("gate", " " + _HOOK_AS_RED, ""),
        ("gate", "all within step 2's budget of two fixes", "until the hook passes"),
        ("gate", "when a change to the backfilled test files alone answers the hook", "when any change answers the hook"),
        ("gate", ", a fix step 4 makes for a commit hook included", ""),
        ("execute", _EXECUTE_HOOK_EXCEPTION, "and only then retry the commit."),
        # The first wording, which put the evidence commit under step 4's rule.
        ("execute", _EXECUTE_HOOK_EXCEPTION,
         "and only then retry the commit. The gate's commit of a test `bmad-testarch-automate` backfilled is the one "
         "exception: `references/gate.md`'s \"When automate backfills\" reads a hook rejection there as its backfill "
         "sweep's red, which it fixes only in the backfilled test files and otherwise ends the cycle at a re-loop."),
        ("gate", _EVIDENCE_HOOK, "reuse that marker as it stands and never rewrite it for this commit."),
        # A hook that needs a source or test file changed now escalates instead.
        ("gate", "(a source or test file left uncommitted when trace ran, which",
         "(a source or test file left uncommitted when trace ran, or one a commit hook needs changed, which"),
    ],
)
def test_hook_predicate_rejects_a_second_route(where, old, new):
    gate, execute = re.sub(r"\s+", " ", GATE), re.sub(r"\s+", " ", EXECUTE)
    if where == "gate":
        mutant = gate.replace(old, new)
        assert mutant != gate, "the mutant must actually change the text"
        assert not _hook_rejection_has_one_route(mutant, execute)
    else:
        mutant = execute.replace(old, new)
        assert mutant != execute, "the mutant must actually change the text"
        assert not _hook_rejection_has_one_route(gate, mutant)


# --- a commit hook that rejects the evidence commit -----------------------------


_EVIDENCE_HOOK_FIX = (
    "Make a change the hook asks for only in a file the gate itself writes for this commit, `sprint-status.yaml` (its "
    "`done` sync) or `.decision-log.md`, then stage it and retry, with the marker as it stands, at most twice for this "
    "commit."
)
_EVIDENCE_HOOK_ESCALATES = (
    "When the hook asks for a change to any other path, such as a file TEA wrote (an edit there would make its "
    "provenance false) or a ledger row (the ledger schema below never rewrites one), or rejects the commit again after "
    "the second fix, commit nothing: log the rejection in `.decision-log.md`, write the typed escalation sidecar "
    "`escalation-<story_id>.json` (shape in `references/execute.md`, under \"Escalation sidecar\") with `kind` "
    "`evidence-commit-rejected` and a `decision_needed` that names the hook, its message, the paths left uncommitted "
    "and this run's id (so a rejection on a later run is a new decision, never one `/ucg-resolve` has closed already), "
    "write `.evidence-owed-<story_id>` beside it, listing those paths one per line, and stop before the next story's "
    "step 0, as the `escalate` route below stops."
)
_EVIDENCE_STAYS_STAGED = (
    "The story keeps its `advance` verdict, and its evidence stays staged for the commit a resume makes."
)
_EVIDENCE_RESUME_WAITS = (
    "While that story's `evidence-commit-rejected` escalation is still open, the resume commits nothing and stops on "
    "it instead (`references/execute.md`'s resume rule says how it reads one); once `/ucg-resolve` has closed it, the "
    "resume makes the commit, under the hook rule above."
)
_EXECUTE_RESUME_WAITS = (
    "That story carries an `evidence-commit-rejected` escalation when a repo commit hook rejected that commit in a way "
    "the gate may not answer, so run the `--assert-armed` call below with `--story` naming that story first: while its "
    "`escalation` reads `open`, make no commit and take the `decision-pending` route below for that story, and once "
    "`/ucg-resolve` has closed it (its sidecar is gone, and `.evidence-owed-<story_id>` is still on disk), make the "
    "commit and remove that marker."
)
_EXECUTE_KIND = (
    "So is `evidence-commit-rejected`: the story advanced, and a repo commit hook rejected its evidence commit in a "
    "way the gate may not answer, so that evidence waits, uncommitted, for the operator (`references/gate.md`'s "
    "advance route)."
)


def _evidence_hook_is_bounded(gate: str, execute: str) -> bool:
    """The evidence commit carries files TEA wrote and ledger rows, which the
    gate never edits, so a hook is answered only in what the gate itself wrote
    for that commit, at most twice; anything else leaves the evidence staged
    and escalates the story, and a resume commits it only once that escalation
    is closed."""
    flat_gate, flat_execute = re.sub(r"\s+", " ", gate), re.sub(r"\s+", " ", execute)
    para = _between(
        flat_gate, "**Commit the gate's evidence before the next story starts.**", "When **every story of the Epic"
    )
    return bool(
        _EVIDENCE_HOOK + " " + _EVIDENCE_HOOK_FIX + " " + _EVIDENCE_HOOK_ESCALATES + " " + _EVIDENCE_STAYS_STAGED
        in para
        and _EVIDENCE_RESUME_WAITS in para
        and "make the change the hook asks for in the files this commit carries" not in para
        and _EXECUTE_RESUME_WAITS in flat_execute
        and _EXECUTE_KIND in flat_execute
    )


def test_the_evidence_commit_hook_rule_reaches_only_the_gates_own_files():
    """The first rule, "make the change the hook asks for in the files this
    commit carries", reached TEA's files (an edit makes their provenance false)
    and the ledger rows the gate had just appended (never rewritten), and it had
    no bound, so a hook it could not satisfy looped the conductor."""
    assert _evidence_hook_is_bounded(GATE, EXECUTE)


@pytest.mark.parametrize(
    ("where", "old", "new"),
    [
        # The first wording: any file the commit carries, retried with no bound.
        ("gate", "own commits. " + _EVIDENCE_HOOK_FIX + " " + _EVIDENCE_HOOK_ESCALATES,
         "own commits: make the change the hook asks for in the files this commit carries, stage it and retry, with "
         "the marker as it stands."),
        ("gate", "only in a file the gate itself writes for this commit, `sprint-status.yaml` (its `done` sync) or "
         "`.decision-log.md`", "in the files this commit carries"),
        ("gate", "`sprint-status.yaml` (its `done` sync) or `.decision-log.md`, then",
         "`sprint-status.yaml` (its `done` sync), `.decision-log.md` or a file TEA wrote, then"),
        ("gate", ", at most twice for this commit", ""),
        ("gate", "or rejects the commit again after the second fix, ", ""),
        ("gate", "then stage it and retry, with the marker as it stands,", "then stage it, write a fresh marker and retry,"),
        ("gate", "with `kind` `evidence-commit-rejected` and a", "with a"),
        ("gate", "names the hook, its message, the paths left uncommitted and this run's id", "names the hook"),
        # A re-rejection on a later run minted the id `/ucg-resolve` had closed, so it read closed.
        ("gate", " and this run's id (so a rejection on a later run is a new decision, never one `/ucg-resolve` has "
         "closed already)", ""),
        ("gate", "write `.evidence-owed-<story_id>` beside it, listing those paths one per line, ", ""),
        ("gate", _EVIDENCE_STAYS_STAGED, "Unstage its evidence and move to the next story."),
        ("gate", " " + _EVIDENCE_RESUME_WAITS, ""),
        ("execute", " " + _EXECUTE_RESUME_WAITS, ""),
        ("execute", "while its `escalation` reads `open`, make no commit", "while its `escalation` reads `open`, commit"),
        ("execute", " " + _EXECUTE_KIND, ""),
    ],
)
def test_evidence_hook_predicate_rejects_an_unbounded_or_unguarded_rule(where, old, new):
    gate, execute = re.sub(r"\s+", " ", GATE), re.sub(r"\s+", " ", EXECUTE)
    if where == "gate":
        mutant = gate.replace(old, new)
        assert mutant != gate, "the mutant must actually change the text"
        assert not _evidence_hook_is_bounded(mutant, execute)
    else:
        mutant = execute.replace(old, new)
        assert mutant != execute, "the mutant must actually change the text"
        assert not _evidence_hook_is_bounded(gate, mutant)


# Every sentence on a gate surface that names a hook's rejection, or the evidence
# commit, its `evidence-commit-rejected` kind or its `.evidence-owed-` marker. The bound above is read in its own paragraph,
# so a sentence elsewhere (in the ledger schema, the decision-pending paragraph or
# a release note) could let a hook reach a ledger row or TEA's files, or let a
# resume commit past an open escalation, and the predicate would still pass.
_HOOK = re.compile(r"\bhooks?\b|pre-commit", re.I)
_REJECT = re.compile(r"reject|refus|\bfail(?:s|ed)?\b|\bblocks?\b|\bden(?:y|ies)\b", re.I)
_EVIDENCE_COMMIT = re.compile(r"evidence commit|evidence-commit|\.evidence-owed", re.I)
_HOOK_REJECTION_SENTENCES = {
    "execute.md": (
        ("**A commit can also be rejected by something that is NOT the guard, and ", "0f2c634952fd"),
        ("**Commit at green** (one implementation commit per green story; the gate", "50b2448580e8"),
        ("A fix that writes `.claude/settings.local.json` (a hook, its env, the al", "9df5f7b5d3f4"),
        ("Before the next story's step 0, also check whether the last advanced sto", "88ce12f730cc"),
        ("Check every `.evidence-owed-<story_id>` of this Epic's stories this way,", "ca850de04101"),
        ("Evaluate it only after the story's Stage-5 verdict has landed, and after", "502e14ca0ed3"),
        ("Exit 0 asserts the branch, both hooks with the all-tools matcher, the fi", "38bd10c9eb2f"),
        ("Said that way rather than \"the guard never sees Write/Edit\", because pre", "4dd6e00dabed"),
        ("Skip the write and both hooks keep reading whatever the file last named:", "381bdfbe5299"),
        ("So is `evidence-commit-rejected`: the story advanced, and a repo commit ", "96b74b528b7e"),
        ("Stage 1 resolved no in-scope story for that resume, so Finalize passes t", "d1b5e1b4c74c"),
        ("That story carries an `evidence-commit-rejected` escalation when a repo ", "65ae5d8b6c6c"),
        ("The PreToolUse hook blocks a commit on a protected branch, blocks a comm", "16e73dd4d02c"),
        ("The gate's two commits keep their own rules in `references/gate.md`: \"Wh", "ffd0e5f04fb0"),
        ("The hook itself only records and warns (a Stop hook **cannot force `/goa", "e875fa4537ca"),
        ("Treat a hook rejection exactly as step 5 treats a post-commit red: remed", "90ca77631228"),
        ("Unlike the baseline, **this marker is refreshed, not preserved**: step 5", "6428639f8eb2"),
    ),
    "finalize.md": (
        ("A run that stopped on an `evidence-commit-rejected` escalation keeps tha", "e2cb75bb035a"),
        ("A story whose escalation is still open (`escalation-<story_id>.json` on ", "c9a848d0ddf8"),
        ("On a `blocked` run (a story escalated, so the Epic never advanced or the", "b59ae034f8db"),
        ("This hook fires **only on a `blocked` run** (a story escalated, so the E", "168e3ecabf77"),
        ("`status` is `complete` when the Epic-level gate advanced and its evidenc", "db204ac9c025"),
    ),
    "gate.md": (
        ("**A red backfill sweep ends the cycle at a re-loop.** A red in step 2's ", "2413be2b7f02"),
        ("A repo commit hook that rejects this commit is not `references/execute.m", "83390652ac30"),
        ("A repo commit hook that rejects this commit is read as step 2's red, and", "dcf8f8ed71b6"),
        ("A resume that finds the marker with the sidecar gone and none of the pat", "7dd5fdbf2466"),
        ("Once the commit is made, remove `.evidence-owed-<story_id>`: `/ucg-resol", "9836fd83431a"),
        ("The guard allows this commit as it allows the evidence commit in \"Route ", "8d2321fc1967"),
        ("Then refresh `.commit-<story_id>` from `HEAD`, so this story's range in ", "ce627b835c8e"),
        ("When the Epic-level gate returns `advance`, or `defer` (whose route adva", "8d4edc0a121d"),
        ("When the hook asks for a change to any other path, such as a file TEA wr", "7b73afb417cb"),
        ("While `.evidence-owed-<story_id>` is on disk, Stage 1's already-done sho", "f0e57b4516e9"),
        ("While that story's `evidence-commit-rejected` escalation is still open, ", "3b854d310f4f"),
    ),
    "ingest-and-scope.md": (
        ("An Epic whose every story reads `done` while one of its stories still ow", "eb2d564ab482"),
    ),
    "preflight.md": (
        ("- The same PreToolUse guard also enforces the Cross-Session Recall latch", "76381c13dda0"),
        ("Claude Code only invokes a PreToolUse group for tools its matcher select", "5df2ca1f552d"),
        ("Deleting it costs nothing a later step needs: step 0 writes it afresh be", "df83ff84a5f2"),
        ("Now that the group is armed for every tool, the hook IS invoked for a `W", "54ce49130885"),
        ("The same assertion is scriptable: `preflight_check.py --assert-armed` pe", "11b5f8f09dc2"),
    ),
    "SKILL.md": (
        ("An Epic whose stories all read `done` while a story's `.evidence-owed-<s", "a5bb6b9a9f94"),
        ("The hook-enforced latch (`.mem-state.json`) fails closed while it is pre", "ed3ddc055043"),
    ),
    "troubleshooting.md": (
        ("**What to check.** - **Older Claude Code.** The hook returns a `deny` de", "b9349b662d21"),
        ("- **A refused settings write.** Preflight writes its hooks and allow rul", "298ba71ea2eb"),
        ("--- title: Troubleshooting description: Maps the real failure modes of a", "74417cea7b2a"),
        ("See the cap sections in the [gate model](./gate-model.md). ## Hooks not ", "b86d92214a9b"),
    ),
    "operating-tips.md": (
        ("The Epic is finished. | | `evidence-owed` | Every story is `done`, but a", "2dbc62bde6cc"),
        ("Two sharper edges: it probes the staged index in the hook event's workin", "5f6b40df02ed"),
    ),
    "ucg-resolve SKILL.md": (
        ("**Closing an `evidence-commit-rejected` escalation makes no commit.** Re", "c6b0813fb562"),
        ("Leave the staged evidence and `{workflow.implementation_artifacts}/.evid", "b44b7cb32271"),
        ("When every story advanced and a story's `.evidence-owed-<story_id>` is o", "04dd1f1b7b30"),
    ),
    # Reviewed: the table's stories row runs into the sentence before the table,
    # and the hunk paragraph's evidence commit into the sentence before its
    # heading; neither says anything of a hook.
    "ucg-status SKILL.md": (
        ("**A story that still owes its gate evidence commit says so on its row.**", "883232a2fd3c"),
        ("Report the story as advanced at its gate with its evidence not committed", "88bf86916146"),
        ("The one recency signal is the heartbeat's `Updated` row, and it belongs ", "f6d245c9b78e"),
        ("The render does not read `HEAD`, so it does not say which of the two hol", "8dc561829a92"),
        ("The story renders under stories as `gate evidence commit owed: a commit ", "e4d4865b3d39"),
    ),
    "backfill fragment": (
        ("A repo commit hook that rejects the advance route's evidence commit is a", "a26bde51243e"),
        ("Before, the backfill waited for the evidence commit after the verdict, s", "383c44c33ef4"),
        ("The gate fixes a red in that sweep only in the backfilled test files, at", "3ad0dcec2ef8"),
        ("The gate leaves a `.evidence-owed-<story_id>` marker until that commit i", "f8c6fa3697fb"),
    ),
}


def _hook_rejection_sentences(text: str) -> tuple[tuple[str, str], ...]:
    """Every sentence that names a hook beside a rejection, or the evidence
    commit, as `_reviewed` holds it."""
    flat = re.sub(r"\s+", " ", text)
    return tuple(
        sorted(
            {
                _reviewed(s)
                for s in _SENTENCE.split(flat)
                if (_HOOK.search(s) and _REJECT.search(s)) or _EVIDENCE_COMMIT.search(s)
            }
        )
    )


def test_every_sentence_on_a_hook_rejection_is_one_reviewed_against_the_bound():
    """Each sentence below was read against the evidence commit's bound: a hook
    is answered only in what the gate writes for that commit, at most twice;
    otherwise the evidence stays staged and the story escalates, and a resume
    commits it only once that escalation is closed. A new one has to be read the
    same way before it joins the list."""
    for name, text in _gate_surfaces().items():
        assert _hook_rejection_sentences(text) == tuple(sorted(_HOOK_REJECTION_SENTENCES.get(name, ()))), name


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        # M1: the ledger schema lets a hook rewrite a ledger row, with no bound.
        ("gate.md", "that single transition is the one sanctioned edit to an existing row",
         "that single transition is the one sanctioned edit to an existing row, except that a ledger row a repo commit "
         "hook rejects in the advance route's evidence commit is reformatted as the hook asks and the commit retried "
         "until the hook accepts it"),
        # M2: the decision-pending paragraph lets the resume commit past an open escalation.
        ("execute.md", "the residue of an answered decision that `/ucg-resolve` would not offer again.",
         "the residue of an answered decision that `/ucg-resolve` would not offer again. Nor does an "
         "`evidence-commit-rejected` sidecar: its story advanced, so make its evidence commit before the next story's "
         "step 0 whatever the sidecar's state."),
        # M5: the release note answers a hook in TEA's file.
        ("backfill fragment", "and a resume makes that commit only once `/ucg-resolve` has closed the escalation.",
         "and a resume makes that commit only once `/ucg-resolve` has closed the escalation. A hook that rejects it over "
         "a file TEA wrote is answered in that file first."),
        # A hook that refuses, or a pre-commit check that fails, rather than one that rejects.
        ("gate.md", "Then move to the next story.",
         "Then move to the next story. A commit hook that refuses the evidence commit over a file TEA wrote is answered "
         "in that file, and the commit retried until the hook passes."),
        ("gate.md", "Then move to the next story.",
         "Then move to the next story. If the repo's pre-commit check fails on the evidence commit over a ledger row, "
         "rewrite the row and retry until it passes."),
        # A clause added inside a reviewed sentence.
        ("execute.md", "Treat a hook rejection exactly as step 5 treats a post-commit red: remediate,",
         "Treat a hook rejection exactly as step 5 treats a post-commit red: remediate (in any file the hook names, for "
         "the gate's evidence commit too, TEA's files and ledger rows included),"),
        # H2: a sentence on the evidence commit that names no hook.
        ("execute.md", "the residue of an answered decision that `/ucg-resolve` would not offer again.",
         "the residue of an answered decision that `/ucg-resolve` would not offer again. Nor does a sidecar left by a "
         "failed evidence commit: its story advanced, so make that commit before the next story's step 0 whatever the "
         "sidecar's state."),
        # The surface that closes the escalation.
        ("ucg-resolve SKILL.md", "`/ucg-resolve` defines no resume of its own.",
         "`/ucg-resolve` defines no resume of its own. Closing an `evidence-commit-rejected` escalation also makes the "
         "staged evidence commit, answering the hook in whatever file it names, TEA's included."),
        # The last story's resume answers the hook wherever it points.
        ("SKILL.md", "then goes to Finalize (`references/execute.md`'s resume rule).",
         "then goes to Finalize (`references/execute.md`'s resume rule). A hook that rejects that commit again is "
         "answered in whatever file it names."),
        # The status view, which an operator reads a stopped run through.
        ("ucg-status SKILL.md", "stops `evidence-owed` rather than `all-done`.",
         "stops `evidence-owed` rather than `all-done`. A hook that rejects the resume's commit again is answered in "
         "whatever file it names, TEA's included."),
        ("ucg-status SKILL.md", "`/ucg-resolve` closes it first, and once the block is gone",
         "the operator may make the commit at once, and once the block is gone"),
    ],
)
def test_the_hook_rejection_scan_lists_a_sentence_that_breaks_the_bound(name, old, new):
    surfaces = _gate_surfaces()
    flat = re.sub(r"\s+", " ", surfaces[name])
    mutant = flat.replace(old, new)
    assert mutant != flat, "the mutant must actually change the text"
    assert _hook_rejection_sentences(mutant) != tuple(sorted(_HOOK_REJECTION_SENTENCES.get(name, ())))


# The Epic's last story makes its evidence commit after the Epic-level gate, so a
# rejection there leaves every story, and the epic row, `done` in the working tree.
_LAST_STORY_REJECTION = (
    ("gate.md", "On the story whose advance makes every story `done`, this commit follows the Epic-level gate, so the "
     "`epic-<id>` row that gate's `advance` wrote stays staged with the rest, and the run ends `blocked` on that "
     "escalation all the same, because its evidence is not committed (`references/finalize.md`)."),
    ("gate.md", "While `.evidence-owed-<story_id>` is on disk, Stage 1's already-done short-circuit does not end that "
     "Epic's resume (`references/ingest-and-scope.md`, rule 4), nor does `scripts/drive_epic.py` report the Epic "
     "`all-done`: the resume waits on the escalation while it is open, makes the commit once it is closed, and then "
     "goes to Finalize with the Epic-level verdict the log holds, without running that gate again."),
    # The sidecar is deleted when `/ucg-resolve` closes it, so the case is keyed on a marker that outlives it.
    ("gate.md", "Once the commit is made, remove `.evidence-owed-<story_id>`: `/ucg-resolve` deletes the sidecar when it "
     "closes the escalation, so the marker is what tells a resume, and Stage 1's already-done short-circuit, that the "
     "commit is still owed."),
    ("ingest-and-scope.md", "while one of its stories still owes its evidence commit "
     "(`{workflow.implementation_artifacts}/.evidence-owed-<story_id>` is on disk: the gate writes it when it escalates "
     "that commit as `evidence-commit-rejected`, and it stays, after `/ucg-resolve` closes the escalation, until the "
     "commit is made) is not complete"),
    ("SKILL.md", "while a story's `.evidence-owed-<story_id>` is on disk (its evidence commit, escalated as "
     "`evidence-commit-rejected`, is still owed, whether or not `/ucg-resolve` has closed that escalation)"),
    ("finalize.md", "its terminal `last_reasons` carries one reason naming that story's `escalation-<story_id>.json` and "
     "saying its gate evidence is not committed"),
    ("finalize.md", "The resume that later makes that commit replaces those reasons with one naming the commit it made, "
     "rather than carrying the blocked run's forward."),
    # A marker whose evidence was committed some other way (by hand, or before a crash) never strands the Epic.
    ("gate.md", "A resume that finds the marker with the sidecar gone and none of the paths it lists staged or "
     "different from `HEAD` (`git diff --quiet HEAD -- <paths>` exits 0 for them) finds the evidence committed already, "
     "by the operator or by a run that stopped between its commit and this removal: log the commit that holds it and "
     "remove the marker, making no commit."),
    ("execute.md", "Check every `.evidence-owed-<story_id>` of this Epic's stories this way, not only the last advanced "
     "story's"),
    ("execute.md", "Finalize passes that story as its one `--story` to `scripts/gate_trail.py`"),
    # The close that deletes the sidecar leaves the commit, and the marker, to the resume.
    ("ucg-resolve SKILL.md", "**Closing an `evidence-commit-rejected` escalation makes no commit.**"),
    ("ucg-resolve SKILL.md", "Leave the staged evidence and `{workflow.implementation_artifacts}/.evidence-owed-<story_id>` "
     "alone, even when the answer is to commit as it stands"),
    ("ucg-resolve SKILL.md", "When every story advanced and a story's `.evidence-owed-<story_id>` is on disk, the resume "
     "drives no story: it makes that story's owed evidence commit and goes to Finalize."),
    ("execute.md", "When that story is the Epic's last, so every story reads `done`, no story is left to drive: after "
     "the commit go to Stage 6 (`references/finalize.md`) with the Epic-level verdict the log holds, and run neither a "
     "story nor the Epic-level gate again."),
    ("ingest-and-scope.md", "is not complete: neither ask nor emit, and resume it as a not-all-done Epic, which "
     "re-enters Execute only for that commit"),
    ("SKILL.md", "counts as not-all-done here and in Stage 1's already-done short-circuit: its resume re-enters Execute "
     "only for that commit, then goes to Finalize"),
    ("finalize.md", "This hook fires **only when the Epic-level gate verdict was `advance`** (a `complete` run) and its "
     "evidence is committed."),
    ("finalize.md", "This hook fires **only on a `blocked` run** (a story escalated, so the Epic never advanced or the "
     "evidence commit of its last story waits on the operator)"),
    ("finalize.md", "`status` is `complete` when the Epic-level gate advanced and its evidence is committed, or "
     "`blocked` when a story escalated, the last story's `evidence-commit-rejected` included"),
    # Once `/ucg-resolve` has closed the escalation, the status view reads the marker too.
    ("ucg-status SKILL.md", "While this line renders the Epic is not finished, even when every story reads `done` and "
     "escalations read `n/a`: it is the state in which `drive_epic.py` stops `evidence-owed` rather than `all-done`."),
)


@pytest.mark.parametrize(("name", "sentence"), _LAST_STORY_REJECTION)
def test_the_last_storys_rejected_evidence_commit_is_blocked_and_resumes_past_the_already_done_stop(name, sentence):
    """The rejection escalated the last story after the Epic-level gate had
    advanced, so Finalize had two statuses to report, and every story read
    `done`: Stage 1 ended the resume as "epic already complete", and execute.md's
    check, which runs before the next story's step 0, never ran, so the staged
    evidence was never committed. The run now ends `blocked`, its resume passes
    the already-done stop, makes the commit once the escalation is closed, and
    goes to Finalize."""
    assert sentence in re.sub(r"\s+", " ", _gate_surfaces()[name])


# --- the confirming rows see the test they confirm --------------------------------


_COPY_IS_INPUT = (
    "never under the worktree. The copy of a backfilled test that automate puts in the worktree, to run the rows that "
    "confirm it there, is an input to that measurement and not where the test lands: automate writes the test to the "
    "main tree first, the main tree's file is the one the backfill commit stages, and the rebuild after automate "
    "discards the copy (\"A backfill is confirmed in the pass that writes it\", under \"Backfill the gate evidence\")."
)
_COPY_NOT_LOST = (
    "A path the summary names that it lists is staged from the main tree, and the worktree's copy of that file, which "
    "automate ran the test's confirming rows against (\"A backfill is confirmed in the pass that writes it\" below), "
    "is not a test written into the worktree: the rebuild discards it."
)


def _confirming_rows_see_the_test(gate: str) -> bool:
    """Mutation rows run in the worktree and outputs land in the main tree, so
    a row could not see the test it confirmed; automate copies the test in, and
    every sentence about the worktree's contents says what that copy is."""
    flat = re.sub(r"\s+", " ", gate)
    return bool(
        _COPY_RULE in flat
        and _COPY_IS_INPUT in flat
        and _COPY_NOT_LOST in flat
        and "Automate's mutation runs edit source in the worktree, and it puts there a copy of each test it backfills "
        "to confirm the test" in flat
        and "nothing a mutation or a copied test left behind (a backfilled test the backfill commit carries is one of "
        "those tracked files)" in flat
    )


def test_automate_copies_each_backfilled_test_into_the_worktree_to_confirm_it():
    assert _confirming_rows_see_the_test(GATE)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The first wording: rows re-run in the worktree, with the test only in the main tree.
        ("copy that file unchanged to the same path in the gate worktree, where its mutation rows run, and re-run "
         "there", "and re-run in the gate worktree"),
        # "never under the worktree" with no word on the copy contradicts the copy rule.
        (_COPY_IS_INPUT, "never under the worktree."),
        # Read without its sentence, step 1 takes the copy for a test written into the worktree.
        (" " + _COPY_NOT_LOST, ""),
    ],
)
def test_copy_predicate_rejects_a_confirmation_that_cannot_see_its_test(old, new):
    flat = re.sub(r"\s+", " ", GATE)
    mutant = flat.replace(old, new)
    assert mutant != flat, "the mutant must actually change the text"
    assert not _confirming_rows_see_the_test(mutant)


# --- a resume re-enters after automate, in any cycle -----------------------------


_RESUME = "**A resume after a backfill does not run automate again.**"
_FIRST_RESUME = "A resume never runs automate twice in one cycle"
_HOLDS = (
    "holds a `gate-backfill-base:` or a `gate-backfill:` line with no verdict logged after it "
    "(when it holds both for this cycle, the later one decides which bullet applies)"
)


def _resume(para: str) -> bool:
    return bool(
        _RESUME in para
        and re.search(
            r"When this story's `\.decision-log\.md` " + re.escape(_HOLDS) + r", `references/execute\.md`'s fifth "
            r"resume case sends the resume here",
            para,
        )
        # M33: the committed backfill resumes at the rebuild and the three assessors, never at automate.
        and re.search(
            r"After `gate-backfill: <sha>` with `HEAD` still `<sha>`, remove `\.scratch-<story_id>/` if it is still "
            r"there, rebuild the worktree at that commit and run trace, NFR and test review on it\.",
            para,
        )
        and "run automate again on it" not in para
        and re.search(r"when `git rev-parse HEAD` prints `<sha>`, the backfill is not committed yet: start again at step 1", para)
        and re.search(r"When `git rev-parse HEAD~1` prints `<sha>`, it is committed: start at step 5", para)
        and re.search(
            r"At any other `HEAD`, the story is not in this case: take the route `preflight_check\.py` reports", para
        )
    )


def test_a_resume_reenters_after_automate_whether_or_not_the_backfill_committed():
    """The base line is logged before staging, so a session that dies between
    the backfill commit and its `gate-backfill:` line still resumes after
    automate."""
    assert _resume(_backfill_commit())


def test_resume_predicate_rejects_a_resume_keyed_on_the_post_commit_line_alone():
    para = _backfill_commit()
    start = para.index("- After `gate-backfill-base: <sha>`")
    mutant = para[:start] + para[para.index("- At any other `HEAD`") :]
    assert mutant != para, "the mutant must actually change the text"
    assert not _resume(mutant)


def test_resume_predicate_rejects_a_trigger_keyed_on_the_last_log_line():
    """A `gate-gap:` or worktree line logged after `gate-backfill:` made the
    backfill line no longer the last one, so the case never fired."""
    para = _backfill_commit()
    mutant = para.replace(
        _HOLDS,
        "last gate entry in `.decision-log.md` is a `gate-backfill-base:` or a `gate-backfill:` line, with no "
        "verdict logged after it",
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _resume(mutant)


def test_resume_predicate_rejects_automate_run_again_at_another_head():
    """The first wording ran the gate from automate at any other HEAD, which
    the old heading said never happens."""
    para = _backfill_commit()
    mutant = para.replace(
        "the story is not in this case: take the route `preflight_check.py` reports", "run the gate from automate"
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _resume(mutant)


def test_resume_predicate_rejects_a_committed_backfill_that_runs_automate_again():
    """M33: the mutant contradicted the paragraph's own heading and survived."""
    para = _backfill_commit()
    mutant = para.replace(
        "rebuild the worktree at that commit and run trace, NFR and test review on it", "run automate again on it"
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _resume(mutant)


def test_no_copy_quotes_the_heading_that_overclaimed():
    fragment = (_REPO_ROOT / "changes" / "gate-automate-backfill-commit.yaml").read_text(encoding="utf-8")
    for name, text in (("gate.md", GATE), ("execute.md", EXECUTE), ("fragment", fragment)):
        assert _FIRST_RESUME not in text, name
    assert "with no verdict logged, goes on with that gate cycle" not in fragment


def _fifth_case() -> str:
    return _between(EXECUTE, "**A fifth case: a gate stopped between automate and trace.**", "\n## ")


def _fifth(para: str) -> bool:
    return bool(
        re.search(r"reads such a story as `gate-owed` or `mid-story`; take this case instead of either", para)
        and re.search(r"but never instead of `decision-pending`", para)
        and re.search(r"It takes three forms, each read from the story's `\.decision-log\.md`", para)
        and re.search(
            r"When the log holds either line with no verdict logged after it \(when it holds both, the later one "
            r"decides\), the story owes the rest of that gate cycle",
            para,
        )
        and re.search(r"skip step 0's turn-ceiling read and steps 1 through 5", para)
        and '"A resume after a backfill does not run automate again"' in para
        and re.search(
            r"which says at which `HEAD` the case holds and sends a story at any other `HEAD` back to the route the "
            r"script reports",
            para,
        )
        and 'gate.md\'s "A red backfill sweep ends the cycle at a re-loop" logs a `reloop` verdict' in para
        and re.search(r"logs a `reloop` verdict whose JSON holds no `gate_status`, since no trace ran", para)
        and "P0" not in para
        and re.search(
            r"When that is the story's last logged verdict and `HEAD` is still the commit its `assessed-commit:` line "
            r"names, the re-loop has committed nothing yet, and the story owes that re-loop, not a gate",
            para,
        )
        and re.search(r"resume gate\.md's `reloop` route where the log stopped, its turn-ceiling check included", para)
        # M16: what "where the log stopped" means, step by step.
        and re.search(
            r"\(the generalize step when this re-loop's `class:` lines are not logged yet, then `bmad-correct-course`, "
            r"then the story's re-run through the story loop below\)",
            para,
        )
        and _FIRST_FORM_ENTRY in re.sub(r"\s+", " ", para)
        and _THIRD_FORM in re.sub(r"\s+", " ", para)
    )


# The first form's own instruction, pinned whole: the third form repeats its
# "skip step 0's turn-ceiling read" clause, so a regex on that clause alone no
# longer sees the first form lose its pointer re-set (M17).
_FIRST_FORM_ENTRY = (
    "Re-set the `.current-story` pointer (the pointer half of step 0 only), skip step 0's turn-ceiling read and steps "
    "1 through 5, and enter Stage 5 at gate.md's \"A resume after a backfill does not run automate again\", which says "
    "at which `HEAD` the case holds and sends a story at any other `HEAD` back to the route the script reports."
)


_THIRD_FORM = (
    "- **An automate pass with no verdict after it.** gate.md's \"A summary already at that name is this cycle's own\" "
    "logs `gate-automate: <sha>` right before it delegates automate, naming the commit automate measures. When the log "
    "holds a `gate-automate:` line with no verdict and no `gate-backfill-base:` or `gate-backfill:` line logged after "
    "it (a backfill line after it means the first form applies instead), and that line names the commit `git rev-parse "
    "HEAD` prints, the session ended while automate ran, or after it finished but before anything was committed, and "
    "the story owes the rest of that gate cycle, not a re-drive. Re-set the `.current-story` pointer (the pointer half "
    "of step 0 only), skip step 0's turn-ceiling read and steps 1 through 5, and enter Stage 5 at gate.md's \"Backfill "
    "the gate evidence\", whose paragraph \"A summary already at that name is this cycle's own\", read before automate "
    "is delegated, reuses the pass's summary when it is complete and runs automate again only when the summary is "
    "unfinished or absent. When that line names any other commit, the story is not in this form: take the route the "
    "script reports."
)


def test_execute_routes_a_stopped_gate_cycle_to_where_it_stopped():
    """In a later cycle the previous cycle's gate artifacts are on disk, so the
    script routes `mid-story` and the story would be re-driven from step 0; a
    re-loop logged before trace left no trace artifact, so the script routes
    `gate-owed` and the re-loop's generalize step and drive were skipped."""
    assert _fifth(_fifth_case())
    assert EXECUTE.index("**A fourth case:") < EXECUTE.index("**A fifth case:")


def test_fifth_case_predicate_rejects_the_first_wording():
    first = (
        "**A fifth case: a gate stopped between automate and trace.** `references/gate.md`'s \"When automate "
        "backfills\" logs `gate-backfill-base:` once automate has finished with a backfill, and `gate-backfill:` "
        "once that backfill is committed. When the story's last gate entry in `.decision-log.md` is either line, "
        "with no verdict logged after it, the story owes the rest of that gate cycle: not a re-drive, and not a "
        "second automate pass. `preflight_check.py` reads no log, so its `story` block cannot see this case and "
        "reads such a story as `gate-owed` or `mid-story`; take this case instead of either, but never instead of "
        "`decision-pending`. Re-set the `.current-story` pointer (the pointer half of step 0 only), skip step 0's "
        "turn-ceiling read and steps 1 through 5, and enter Stage 5 at gate.md's \"A resume never runs automate "
        "twice in one cycle\".\n"
    )
    assert not _fifth(first)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # M16
        (
            " (the generalize step when this re-loop's `class:` lines are not logged yet, then `bmad-correct-course`, "
            "then the story's re-run through the story loop below)",
            "",
        ),
        # The pre-fix fifth case had two forms: a later cycle that died after automate with no backfill line read
        # `mid-story` and was re-driven from step 0.
        (_THIRD_FORM, ""),
        # M17: the first form's resume without its pointer re-set books the cycle to whatever story the file names.
        ("Re-set the `.current-story` pointer (the pointer half of step 0 only), skip step 0's turn-ceiling read and "
         "steps 1 through 5, and enter Stage 5 at gate.md's \"A resume after a backfill",
         "Skip step 0's turn-ceiling read and steps 1 through 5, and enter Stage 5 at gate.md's \"A resume after a "
         "backfill"),
        # A third form that re-drives the story is the bug it replaced.
        ("the story owes the rest of that gate cycle, not a re-drive. Re-set",
         "the story owes a re-drive from step 0. Re-set"),
    ],
)
def test_fifth_case_predicate_rejects_a_dropped_or_redriving_form(old, new):
    para = re.sub(r"\s+", " ", _fifth_case())
    mutant = para.replace(old, new)
    assert mutant != para, "the mutant must actually change the text"
    assert not _fifth(mutant)


def _premise_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "proj"
    root.mkdir()
    ident = ("-c", "user.email=t@example.invalid", "-c", "user.name=t", "-c", "commit.gpgsign=false")
    _git(root, "init", "-q")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    _git(root, "add", "a.txt")
    _git(root, *ident, "commit", "-qm", "base")
    base = _git(root, "rev-parse", "HEAD").strip()
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    _git(root, "add", "b.txt")
    _git(root, *ident, "commit", "-qm", "story")
    head = _git(root, "rev-parse", "HEAD").strip()
    impl = root / "impl"
    trace = root / "trace"
    impl.mkdir()
    trace.mkdir()
    (impl / ".baseline-4-2").write_text(base + "\n", encoding="utf-8")
    (impl / ".tests-ran-4-2").write_text(f"baseline={base}\nscope=full\n", encoding="utf-8")
    (trace / "trace-4-1.md").write_text("---\nworkflowType: testarch-trace\n---\n", encoding="utf-8")
    (trace / "gate-decision-4-1.json").write_text('{"gate_status": "PASS"}', encoding="utf-8")
    (impl / ".decision-log.md").write_text(
        f"## Story 4-2\n\n```json\n{{\"verdict\": \"reloop\", \"reasons\": [\"red backfill sweep: lint names tests/unit/a.test.ts\"]}}\n```"
        f"\n\nassessed-commit: {head}\n",
        encoding="utf-8",
    )
    return root, impl, trace


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_the_script_cannot_see_a_reloop_logged_before_trace(tmp_path):
    """The premise of the fifth case's second form, measured on the script: a
    first cycle reads `gate-owed` (step 5, then a gate) and a later one reads
    `mid-story` (a re-drive past the generalize step), whatever the log says."""
    preflight = _load_script("preflight_check")
    root, impl, trace = _premise_repo(tmp_path)
    assert preflight._assert_story(root, impl, "4-2", trace)["route"] == "gate-owed"
    (trace / "trace-4-2.md").write_text("---\nworkflowType: testarch-trace\n---\n", encoding="utf-8")
    (trace / "gate-decision-4-2.json").write_text('{"gate_status": "FAIL"}', encoding="utf-8")
    assert preflight._assert_story(root, impl, "4-2", trace)["route"] == "mid-story"


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_the_script_reads_a_later_cycle_stopped_after_automate_as_mid_story(tmp_path):
    """The third form's premise, measured on the script: in a later cycle the
    previous cycle's trace artifacts exist, so a session that died after
    automate, with only `gate-automate:` logged for this cycle, reads
    `mid-story`, a re-drive from step 0 past its turn-ceiling read. The script
    needs no change: it reads no log, and the fifth case already outranks its
    `gate-owed` and `mid-story` routes, so the prose form alone reroutes it."""
    preflight = _load_script("preflight_check")
    root, impl, trace = _premise_repo(tmp_path)
    head = _git(root, "rev-parse", "HEAD").strip()
    (trace / "trace-4-2.md").write_text("---\nworkflowType: testarch-trace\n---\n", encoding="utf-8")
    (trace / "gate-decision-4-2.json").write_text('{"gate_status": "FAIL"}', encoding="utf-8")
    log = impl / ".decision-log.md"
    log.write_text(log.read_text(encoding="utf-8") + f"\ngate-automate: {head}\n", encoding="utf-8")
    assert preflight._assert_story(root, impl, "4-2", trace)["route"] == "mid-story"
    assert re.search(r"reads such a story as `gate-owed` or `mid-story`; take this case instead of either", _fifth_case())
    assert _THIRD_FORM in re.sub(r"\s+", " ", _fifth_case())


def test_the_script_docstring_leaves_the_log_cases_to_the_conductor():
    doc = re.sub(r"\s+", " ", _load_script("preflight_check")._assert_story.__doc__ or "")
    assert "resume rule exactly" not in doc
    assert "Routes mirror the artifact-derived cases of references/execute.md's resume rule" in doc
    assert "it is the conductor's call: such a story is reported here as gate-owed or mid-story" in doc


def test_the_evidence_commit_no_longer_carries_the_backfill():
    para = _between(
        GATE,
        "**Commit the gate's evidence before the next story starts.**",
        "When **every story of the Epic is `done`**",
    )
    assert "(in production, tests automate backfilled)" not in para
    assert re.search(r"Automate's backfill is not among its paths, because it was committed before trace ran", para)
    # The safety rule for any executable path stays.
    assert re.search(
        r"If it must carry an executable path all the same .*re-run the sweep and write a fresh "
        r"marker per `references/execute\.md` step 5 first",
        para,
        re.S,
    )


def test_execute_names_the_backfill_commit_inside_the_story_boundary():
    assert re.search(
        r"when the gate's `bmad-testarch-automate` backfills a test, a commit of that backfill comes before it",
        EXECUTE,
    )


# --- the turn ceiling on a resumed backfill ---------------------------------------


_EXEMPT_BACKFILL = (
    "and so is a story the fifth resume case's first or third form (a backfill, or an automate pass, with no verdict "
    "after it) sends into Stage 5, whatever route the script reports for it, because its gate cycle is already under "
    "way. The fifth case's second form reads the count at its re-loop's turn-ceiling check instead."
)


def _exempts_a_resumed_backfill(text: str) -> bool:
    flat = re.sub(r"\s+", " ", text)
    return (
        "A `gate-owed` story is exempt and goes straight to step 5 and the gate, because its work is already "
        "committed, " + _EXEMPT_BACKFILL
    ) in flat


def test_the_turn_ceiling_read_exempts_a_resumed_backfill():
    """A later cycle's backfill resume reads `mid-story`, the route whose read
    before step 0 escalates, while the fifth case skips that read."""
    assert _exempts_a_resumed_backfill(EXECUTE)


def test_exemption_predicate_rejects_a_gate_owed_only_exemption():
    mutant = EXECUTE.replace(", " + _EXEMPT_BACKFILL, ".")
    assert mutant != EXECUTE, "the mutant must actually change the text"
    assert not _exempts_a_resumed_backfill(mutant)


# --- the bound on automate --------------------------------------------------------


def _bound() -> str:
    return _between(GATE, _BOUND, "**Operator evidence is a recorded live result")


def _bounds_automate(para: str) -> bool:
    return bool(
        _BOUND in para
        and re.search(
            r"automate does not run in it again, so every cycle reaches a verdict whatever automate finds: "
            r"trace's, or the re-loop a red backfill sweep takes\.",
            para,
        )
        and re.search(
            r"Automate runs a second time in one cycle only when a resume finds the first pass's summary unfinished, "
            r"or finds none at all \(\"A summary already at that name is this cycle's own\" below\)\.",
            para,
        )
        # The exception the `unkilled` rule needs where a later cycle reads a GREEN row.
        and re.search(
            r"A row that reads `GREEN` is a gap again, and \"Automate backfills every gap it finds on a P0 criterion\" "
            r"below says whether automate backfills it or reports it, except a row behind an open `unkilled` line, "
            r"which keeps that line open and gets no new test",
            para,
        )
        # M11: a re-gate of the same commit is still the full instrument, which is what lets it advance.
        and re.search(
            r"so automate has nothing left to look at there unless an open line names another commit, and the gate "
            r"is still the full instrument\.",
            para,
        )
        and "unless a gap's rows last ran on another commit" not in para
        and re.search(
            r"automate's scope is the diff from the previous gate's `assessed-commit` line to the commit under assessment, "
            r"plus the mutation rows behind the previous cycle's backfilled gaps and behind every open `gate-gap:` line",
            para,
        )
        and re.search(
            r"It re-runs, at the commit under assessment, whatever the diff covers, the mutation rows behind each gap "
            r"the previous cycle backfilled \(the `scripts/mutate_check\.py` table rows recorded in the summary named "
            r"for that cycle's `gate-backfill-base:` commit\) and behind each open `gate-gap:` line \(the rows "
            r"recorded in the summary the line names\)",
            para,
        )
        and re.search(
            r"For an `unmeasured` line \(\"A risk automate names on a P0 criterion\" below\), and for a line whose rows "
            r"cannot run \([^)]*\), it measures the gap afresh instead and writes new rows for it",
            para,
        )
        and re.search(r"A row that reads `GREEN` is a gap again", para)
        and re.search(r"whether the re-gate is full or delta", para)
        and re.search(r"It searches for new gaps only in code that diff changes", para)
        and re.search(
            r"When that diff is empty, automate still runs, for the open `gate-gap:` lines alone, when any of them "
            r"names a commit other than the commit under assessment\. Otherwise skip automate and the rebuild, and "
            r"carry the open lines unchanged, `unmeasured` ones included",
            para,
        )
        and re.search(
            r"Each automate pass leaves every open line naming the commit that pass measured, so no cycle runs "
            r"automate at a commit an earlier cycle's pass has measured",
            para,
        )
        and re.search(r"no `assessed-commit` line, automate runs in full", para)
    )


def test_automate_finishes_once_per_cycle_and_a_later_cycle_is_scoped_to_its_diff():
    assert _bounds_automate(_bound())


def test_bound_predicate_rejects_a_later_cycle_that_may_search_anywhere():
    para = _bound()
    mutant = para.replace("only in code that diff changes", "wherever it finds one")
    assert mutant != para, "the mutant must actually change the text"
    assert not _bounds_automate(mutant)


def test_bound_predicate_rejects_a_backfill_that_restarts_automate():
    para = _bound()
    mutant = para.replace("automate does not run in it again", "automate runs in it again")
    assert mutant != para, "the mutant must actually change the text"
    assert not _bounds_automate(mutant)


def test_bound_predicate_rejects_the_unqualified_once_per_cycle():
    """A resume after a dead automate pass runs automate again in the same
    cycle, so "runs once per gate cycle" was false as written."""
    para = _bound()
    mutant = para.replace(
        _BOUND, "**Automate runs once per gate cycle, and a backfill never restarts the cycle.**"
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _bounds_automate(mutant)
    assert "**Automate runs once per gate cycle" not in GATE


def test_bound_predicate_rejects_an_empty_diff_that_skips_an_open_gap():
    """A cap-only re-gate after a backfill commit measures a commit the gap's
    rows never ran on; skipping automate there left the gap unmeasured."""
    para = _bound()
    start = para.index("- When that diff is empty")
    end = para.index("A cap-only re-gate, and the re-gate", start)
    mutant = para[:start] + "- When that diff is empty, skip automate and the rebuild. " + para[end:]
    assert mutant != para, "the mutant must actually change the text"
    assert not _bounds_automate(mutant)


def test_bound_predicate_rejects_a_later_cycle_that_never_remeasures_a_gap():
    """A re-loop sent to close a reported gap often adds only a test, so a
    diff-only scope never re-runs the mutants behind that gap."""
    para = _bound()
    start = para.index("- It re-runs, at the commit under assessment")
    mutant = para[:start] + para[para.index("- When that diff is empty") :]
    assert mutant != para, "the mutant must actually change the text"
    assert not _bounds_automate(mutant)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # M11
        (", and the gate is still the full instrument", ""),
        # The first wording keyed this on rows, which an `unmeasured` line does not have.
        ("unless an open line names another commit", "unless a gap's rows last ran on another commit"),
        # Without the exception a later pass backfills an equivalent mutant again in every cycle.
        (", except a row behind an open `unkilled` line, which keeps that line open and gets no new test", ""),
        # A resume that finds no summary at all runs automate again; the bound must say so.
        (", or finds none at all", ""),
    ],
)
def test_bound_predicate_rejects_a_lost_qualifier(old, new):
    para = _bound()
    mutant = para.replace(old, new)
    assert mutant != para, "the mutant must actually change the text"
    assert not _bounds_automate(mutant)


_P0_RULE = "**Automate backfills every gap it finds on a P0 criterion.**"
_OPERATOR_AGAIN = (
    "A P0 backfill made while a live record sits at the commit under assessment moves that commit past the record, "
    "and that needs no rule of its own: a `pass` counts only at the commit trace measures (\"Operator evidence is a "
    "recorded live result\" below), so the gate at the backfill commit owes the AC again through the routes that "
    "already owe one (the `operator-evidence-owed` escalation on a FAIL, a ledger row on `advance` or `defer`), as "
    "`references/execute.md`'s fourth resume case already says of the commit a red makes past the assessed commit."
)


def _p0_backfilled(para: str) -> bool:
    return bool(
        _P0_RULE in para
        and re.search(
            r"In any cycle, whatever its scope, and even while the story's live results file holds a record at the "
            r"commit under assessment, a gap automate finds on a P0 criterion gets a test: the backfill is committed "
            r"before trace \(\"When automate backfills\" above\), so TEA's trace counts the test and `gate_eval\.py` "
            r"decides",
            para,
        )
        and re.search(
            r"A gap on any other criterion it backfills only when the gap's code is in this cycle's search scope "
            r"\(the code that landed during Execute in a story's first cycle, the diff in a later one\) and the "
            r"story's live results file holds no record at the commit under assessment",
            para,
        )
        and re.search(
            r"Otherwise it reports the gap rather than backfills it: it names the gap in its summary, with its "
            r"mutation evidence, and adds no test",
            para,
        )
        and re.search(r"So only a gap on a criterion other than P0 is ever reported rather than backfilled", para)
        and re.search(
            r"A gap behind an open `unkilled` line already has its test, so no pass writes it another while its rows "
            r"can run",
            para,
        )
        and _OPERATOR_AGAIN in para
    )


def test_automate_backfills_every_gap_on_a_p0_criterion():
    """The maintainer's ruling: write a test, never block. The script decides
    on the test, so no gap needs a judgment to stop the cycle."""
    assert _p0_backfilled(_bound())


def test_p0_predicate_rejects_the_live_results_rule_it_replaced():
    """The branch's first rule reported every gap, a P0 one included, while
    operator records sat at the commit."""
    para = _bound()
    start = para.index(_P0_RULE)
    end = para.index("\n\n", start)
    first = (
        "In any cycle, automate also reports rather than backfills while the story's live results file holds a "
        "record at the commit under assessment: a backfill commit would leave that record at a commit trace no "
        "longer measures, and the AC it proves would be owed again."
    )
    mutant = para[:start] + first + para[end:]
    assert not _p0_backfilled(mutant)
    assert first not in GATE


def test_p0_predicate_rejects_a_p0_gap_reported_outside_the_scope():
    para = _bound()
    mutant = para.replace("In any cycle, whatever its scope, and even while", "In any cycle, inside its scope, and even while")
    assert mutant != para, "the mutant must actually change the text"
    assert not _p0_backfilled(mutant)


def test_the_operator_evidence_routes_already_owe_a_record_at_a_stale_commit():
    """The one sentence above says the backfill commit needs no new rule; the
    two texts it leans on must say what it says they say."""
    assert re.search(r"A `pass` counts only at the commit trace measures\.", GATE)
    fourth = _between(EXECUTE, "**A fourth case:", "**A fifth case:")
    assert re.search(
        r"that commit moves `HEAD` past the assessed commit, so the records no longer count and the "
        r"`\.regate-<story_id>` marker is stale, and the re-gate at the new `HEAD` escalates "
        r"`operator-evidence-owed` again at the new commit",
        fourth,
    )
    defer = _between(GATE, "- **`defer`**", "- **A FAIL only operator evidence can change is not a re-loop.**")
    assert re.search(r"It is owed while its live results file holds no `pass` record for it at the commit the gate measured", defer)


def _p0_risk(para: str) -> bool:
    return bool(
        "**A risk automate names on a P0 criterion is measured in the same pass.**" in para
        and re.search(r"tell it to measure each risk it names on a P0 criterion before it finishes", para)
        and re.search(
            r"a mutation row for each failure arm the criterion names, its own backfilled tests included, and to "
            r"backfill each gap that measuring confirms, as it backfills every gap on a P0 criterion",
            para,
        )
        and re.search(
            r"A named P0 risk it still leaves unmeasured is logged as a `gate-gap:` line that says `unmeasured` in "
            r"place of a summary, and carried: the story's next automate pass measures it, and backfills the gap when "
            r"a row confirms one",
            para,
        )
        and re.search(
            r"An `unmeasured` line is not a finding, since no mutant has run for it yet, and like every `gate-gap:` "
            r"line it never changes the route the verdict takes",
            para,
        )
    )


def test_a_named_p0_risk_is_measured_and_a_confirmed_gap_backfilled():
    """With one automate pass per cycle, a P0 risk the pass names but never
    measures would otherwise reach an advance unmeasured."""
    assert _p0_risk(_bound())


def test_p0_risk_predicate_rejects_a_confirmed_risk_left_unbackfilled():
    para = _bound()
    mutant = para.replace(
        ", and to backfill each gap that measuring confirms, as it backfills every gap on a P0 criterion", ""
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _p0_risk(mutant)


def test_p0_risk_predicate_rejects_an_unmeasured_risk_that_changes_a_route():
    para = _bound()
    mutant = para.replace(
        "An `unmeasured` line is not a finding, since no mutant has run for it yet, and like every `gate-gap:` line "
        "it never changes the route the verdict takes.",
        "An open `unmeasured` line on a P0 criterion ends the cycle at a re-loop before trace.",
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _p0_risk(mutant)


def test_an_empty_diff_covers_both_regates_of_the_same_commit():
    """A cap-only re-gate and an operator-evidence re-gate measure the commit
    the previous gate measured."""
    assert re.search(
        r"A cap-only re-gate, and the re-gate a closed `operator-evidence-owed` escalation owes, "
        r"measure the commit the previous gate measured",
        _bound(),
    )


def test_a_gap_never_changes_a_route():
    para = _bound()
    assert re.search(r"A `gate-gap:` line never changes the route the verdict takes", para)
    assert re.search(
        r"On a `reloop` that is not cap-only, each open line that is neither `unmeasured` nor `unkilled` is one of "
        r"the findings the generalize step reads",
        para,
    )
    assert re.search(
        r"An `unmeasured` line's row says the risk or the gap is unmeasured, and an `unkilled` line's row says the "
        r"backfilled "
        r"test did not kill the mutant, which may be equivalent",
        para,
    )
    assert "the INVARIANT below sends it to a re-loop" not in GATE
    ledger = next(line for line in GATE.splitlines() if line.startswith("- `source` ∈"))
    assert (
        "`gate` (CONCERNS, an operator-evidence AC's evidence still owed, or an open `gate-gap:` line: a coverage "
        "gap automate reported rather than backfilled, a risk on a P0 criterion it left unmeasured, a gap whose rows "
        "could not run, a backfilled test that was never written, or a backfilled test that did not kill its mutant)"
    ) in ledger
    assert re.search(r"take the verdict's `reasons` and the review's findings", GATE)


# --- a gate-gap row is a ledger row at `med`, never a re-loop ----------------------


_NEITHER = (
    "No such row is a gate FAIL or a critical finding, whatever its criterion's priority, so it belongs on the ledger "
    "and never re-loops or escalates the story, and neither the INVARIANT under \"Route on the verdict\" nor the "
    "ledger schema's `severity` bar sends it anywhere else: a FAIL is the `gate_status` that `gate_eval.py` reads "
    "from TEA's trace, which no `gate-gap:` line changes, and a critical finding is one a code review or the NFR "
    "assessment rates critical, while a `gate-gap:` line records automate's mutation measurement, an `unmeasured` one "
    "a measurement nobody has made yet and an `unkilled` one a test that did not kill its mutant, not a defect anyone "
    "found."
)
_LEDGER_ROW = (
    "On `advance` or `defer`, each open line becomes a ledger row with `source` `gate` and `severity` `med`, "
    "whatever its criterion's priority."
)
_INVARIANT_ROW = (
    "A row from a `gate-gap:` line is neither a FAIL nor a critical finding, whatever its criterion's priority, so it "
    "belongs on the ledger and never re-loops or escalates the story."
)
_SEVERITY_BAR = (
    "- `severity` ∈ `low`, `med`, `high`. A `high` that maps to a gate FAIL or a P0/critical finding does **not** "
    "belong here: re-loop or escalate it. A row from an open `gate-gap:` line is always `med`: whatever its "
    "criterion's priority, it is neither a gate FAIL nor a P0/critical finding, so it belongs here and never re-loops "
    "or escalates the story."
)
_ADDENDUM = (
    "An open `gate-gap:` line is neither a FAIL nor a critical finding, whatever its criterion's priority, so the "
    "ledger row it becomes on `advance` or `defer` keeps this rule"
)
_BACKFILLED_NOT_PARKED = (
    "A gap automate finds on a P0 criterion is backfilled rather than parked (\"Automate backfills every gap it finds "
    "on a P0 criterion\", under the same section), and `gate_eval.py` decides on the test, so a `gate-gap:` line on a "
    "P0 criterion is only ever a risk or a gap nobody has measured yet, a backfilled test that was never written, "
    "or a "
    "backfilled test that did not kill its mutant."
)
_GATE_MODEL_LEDGER = (
    "Only non-gate-blocking work (CONCERNS, non-critical findings, parked decisions, and the coverage gaps automate "
    "logged as `gate-gap:` lines that are still open) reaches the deferred-work ledger; a FAIL or a P0/critical "
    "finding re-loops within budget or escalates. A `gate-gap:` row is neither, whatever its criterion's priority: it "
    "reaches the ledger at `med` severity and never re-loops or escalates the story."
)


def _gap_rows_stay_on_the_ledger(gate: str, gate_model: str) -> bool:
    """Every sentence that bars work from the ledger says a `gate-gap:` row is
    not what it bars, whatever its criterion's priority, and the row's severity
    is fixed below the `high` bar."""
    flat = re.sub(r"\s+", " ", gate)
    invariant = next((line for line in gate.splitlines() if line.startswith("**INVARIANT")), "")
    severity = next((line for line in gate.splitlines() if line.startswith("- `severity` ∈")), "")
    return bool(
        _LEDGER_ROW in flat
        and _NEITHER in flat
        and "Only non-gate-blocking work (CONCERNS, non-critical findings, parked decisions, and the rows open "
        "`gate-gap:` lines become) is allowed onto the ledger." in invariant
        and "If you find yourself about to write a FAIL or a critical finding to the ledger, you are violating the "
        "gate: re-loop within budget or escalate instead. " + _INVARIANT_ROW in invariant
        and severity == _SEVERITY_BAR
        and _ADDENDUM in flat
        and _BACKFILLED_NOT_PARKED in flat
        and "re-looped rather than parked" not in flat
        and _GATE_MODEL_LEDGER in re.sub(r"\s+", " ", gate_model)
    )


def test_a_gate_gap_row_is_a_med_ledger_row_whatever_its_priority():
    """A P0 `gate-gap:` row met the ledger's own bar ("a `high` that maps to a
    gate FAIL or a P0/critical finding does not belong here: re-loop or escalate
    it") and gate-model.md's "a P0/critical finding re-loops", so a literal
    conductor re-looped a line the maintainer ruled never changes a route."""
    gate_model = (_REPO_ROOT / "docs" / "gate-model.md").read_text(encoding="utf-8")
    assert _gap_rows_stay_on_the_ledger(GATE, gate_model)


@pytest.mark.parametrize(
    ("where", "old", "new"),
    [
        # M51: the rule the maintainer overruled, restored in the addendum.
        ("gate", "is backfilled rather than parked", "is re-looped rather than parked"),
        # M47: a ledger sentence that sends a gap row to a re-loop.
        (
            "gate",
            "A `high` that maps to a gate FAIL or a P0/critical finding does **not** belong here",
            "A `high` that maps to a gate FAIL, a P0/critical finding or an open `gate-gap:` line on a P0 criterion "
            "does **not** belong here",
        ),
        # A row with no fixed severity can be written `high` and meet the bar.
        ("gate", " and `severity` `med`, whatever its criterion's priority.", "."),
        ("gate", " A row from an open `gate-gap:` line is always `med`: whatever its criterion's priority, it is "
         "neither a gate FAIL nor a P0/critical finding, so it belongs here and never re-loops or escalates the "
         "story.", ""),
        # The INVARIANT's own sentence, and the bar it says a gap row escapes.
        ("gate", " " + _INVARIANT_ROW, ""),
        ("gate", "so it belongs on the ledger and never re-loops or escalates the story",
         "so it re-loops within budget or escalates the story"),
        ("gate_model", " A `gate-gap:` row is neither, whatever its criterion's priority: it reaches the ledger at "
         "`med` severity and never re-loops or escalates the story.", ""),
        ("gate_model", ", and the coverage gaps automate logged as `gate-gap:` lines that are still open", ""),
    ],
)
def test_ledger_predicate_rejects_a_gap_row_sent_to_a_reloop(where, old, new):
    gate_model = (_REPO_ROOT / "docs" / "gate-model.md").read_text(encoding="utf-8")
    gate, model = GATE, gate_model
    if where == "gate":
        gate = GATE.replace(old, new)
        assert gate != GATE, "the mutant must actually change the text"
    else:
        model = gate_model.replace(old, new)
        assert model != gate_model, "the mutant must actually change the text"
    assert not _gap_rows_stay_on_the_ledger(gate, model)


def test_an_unmeasured_ledger_row_says_why_the_invariant_allows_it():
    """The INVARIANT bars a FAIL or a critical finding from the ledger; an
    `unmeasured` P0 row must say why it is neither, or the two contradict."""
    assert _NEITHER in re.sub(r"\s+", " ", _bound())
    invariant = next(line for line in GATE.splitlines() if line.startswith("**INVARIANT"))
    assert "If you find yourself about to write a FAIL or a critical finding to the ledger" in invariant


_STAYS_OPEN = "**A reported gap stays open until a later pass measures it closed.**"


_AFRESH_ONCE = (
    "It measures nothing, so its line stays open, and the pass measures that gap afresh, once in the pass: when a row "
    "it writes for the gap then cannot run either, it measures that gap no further, and logs the gap's line as "
    "`unmeasured`, in place of a summary, for the story's next automate pass to measure."
)


def _carries_gaps(para: str, reloop: str) -> bool:
    return bool(
        _STAYS_OPEN in para
        and re.search(
            r"Once automate has finished, log in this cycle's `\.decision-log\.md` entry one `gate-gap:` line for "
            r"each gap it reported, for each risk on a P0 criterion it left unmeasured, for each gap it could not "
            r"measure because its rows could not run even afresh, and for each backfill its confirmation left "
            r"`unkilled`, beside any line step 1 of \"When automate backfills\" logs for a test that was never written",
            para,
        )
        and re.search(
            r"Each line names the criterion, its priority, the commit automate measured and the summary that recorded "
            r"its rows, or `unmeasured` in place of the summary for a risk it did not measure or a gap it could not, and "
            r"an `unkilled` line also says `unkilled` and names the test that did not kill its rows",
            para,
        )
        # M3: when the carry happens, so a cycle that skips automate still carries.
        and re.search(
            r"Every later cycle of the story copies the previous cycle's open `gate-gap:` lines into its own entry, "
            r"whatever route the previous verdict took: once its automate has finished, or before trace when "
            r"automate does not run\.",
            para,
        )
        # M35: why a MISATTRIBUTED row reads killed.
        and re.search(
            r"In each, something the row's command runs failed under the mutant, and a test a re-loop added under a "
            r"name other than the row's `expect_red` reads `MISATTRIBUTED` that way\.",
            para,
        )
        # M34: a row that cannot run keeps its line open and is measured afresh.
        and _AFRESH_ONCE in re.sub(r"\s+", " ", para)
        and re.search(
            r"A line closes when an automate pass at a later commit than the one the line names finds every row "
            r"behind it reading killed",
            para,
        )
        # M4: a closed line leaves; it is not carried.
        and re.search(r"That pass's cycle leaves the line out\.", para)
        and "keeps the line" not in para
        # M5: what the carried line names once a pass has measured it again.
        and re.search(
            r"A carried line that pass does not close is logged afresh in place of the copied line, naming this commit "
            r"and this pass's summary, or `unmeasured` while the risk still is or the gap's rows still cannot run, or "
            r"`unkilled`, naming its test, while a test backfilled for the gap has not killed its rows\.",
            para,
        )
        and re.search(
            r"A cap-only `reloop` has no finding to generalize and an `escalate` only stops, so neither of them takes one",
            para,
        )
        and re.search(r"Whatever the route, a line stays open, so the story's next gate cycle, when there is one, copies it", para)
        and re.search(
            r"An open `gate-gap:` line in a cycle whose re-loop is cap-only is not one of that re-loop's findings, "
            r"so it gets no `class:` line and no ledger row here: like a capped CONCERNS's findings, it goes to the "
            r"next gate, by its `gate-gap:` line",
            reloop,
        )
    )


def test_a_gap_stays_open_until_a_later_pass_measures_it_closed():
    """A cap-only re-loop has no generalize step, and its confirming re-gate
    measures the same commit, so automate is skipped there: without the carry
    the gap reached neither a re-loop nor the ledger. A normal re-loop that
    took the gap and added only a test dropped it too, and a gap with no rows
    had nothing for a later cycle to re-run."""
    assert _carries_gaps(_bound(), _reloop_bullet())


def test_carry_predicate_rejects_a_carry_after_two_routes_only():
    """The first wording carried a gap only past a cap-only re-loop or an
    escalation, so a normal re-loop's test-only fix dropped it unmeasured."""
    para = _bound()
    mutant = para.replace(
        "whatever route the previous verdict took", "after a cap-only `reloop` or an `escalate` only"
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _carries_gaps(mutant, _reloop_bullet())
    assert "on `escalate` it is recorded beside the verdict in `.decision-log.md`" not in GATE
    assert "leaving out only a gap whose rows that automate re-ran" not in GATE


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # M3
        (": once its automate has finished, or before trace when automate does not run", ": once trace has run"),
        # M4
        ("That pass's cycle leaves the line out. ", "That pass's cycle keeps the line. "),
        # M5
        (", naming this commit and this pass's summary, or `unmeasured` while the risk still is", ""),
        # M34
        (" " + _AFRESH_ONCE, ""),
        # An unbounded afresh measurement: a gap no row can measure loops the pass.
        (_AFRESH_ONCE, "It measures nothing, so its line stays open, and the pass measures that gap afresh."),
        (" or the gap's rows still cannot run", ""),
        # M35
        (
            " In each, something the row's command runs failed under the mutant, and a test a re-loop added under a "
            "name other than the row's `expect_red` reads `MISATTRIBUTED` that way.",
            "",
        ),
        # An unkilled backfill that no line records is a gap trace counts as covered and nobody sees.
        (", for each risk on a P0 criterion it left unmeasured, for each gap it could not measure because its rows could "
         "not run even afresh, and for each backfill its confirmation left `unkilled`",
         " and for each risk on a P0 criterion it left unmeasured"),
        (", for each gap it could not measure because its rows could not run even afresh,", ""),
    ],
)
def test_carry_predicate_rejects_a_mutated_carry_or_close_rule(old, new):
    para = _bound()
    mutant = para.replace(old, new)
    assert mutant != para, "the mutant must actually change the text"
    assert not _carries_gaps(mutant, _reloop_bullet())


def _replay_a_gap_no_row_can_measure(gate: str, limit: int = 10) -> tuple[str, int]:
    """Replay, on gate.md's own sentences, one automate pass over a gap whose
    every row cannot run: the review's case, a worktree whose untracked copy of
    a backfilled test turns a tracked-files check in the sweep red, so
    `mutate_check.py` refuses every table the pass gives it. Each step is one
    set of rows the pass runs for the gap; the result is how the pass leaves
    the gap and how many sets it ran before it finished."""
    flat = re.sub(r"\s+", " ", gate)
    afresh = "It measures nothing, so its line stays open, and the pass measures that gap afresh" in flat
    once = _AFRESH_ONCE in flat
    for ran in range(1, limit + 1):
        if not afresh:
            return ("open", ran)  # nothing sends the pass back to the gap
        if once and ran == 2:
            return ("unmeasured", ran)  # its own rows, then one afresh measurement
    return ("never finishes", limit)


def test_a_gap_no_row_can_measure_is_measured_afresh_once_then_carried_unmeasured():
    assert _replay_a_gap_no_row_can_measure(GATE) == ("unmeasured", 2)
    assert _AFRESH_ONCE in re.sub(r"\s+", " ", _bound())


def test_replay_without_the_bound_never_finishes_the_pass():
    """The mutant twin: "the pass measures that gap afresh", with nothing to
    stop it, sends a pass whose fresh rows cannot run either back to the gap
    for ever, and the cycle never reaches a verdict."""
    flat = re.sub(r"\s+", " ", GATE)
    mutant = flat.replace(_AFRESH_ONCE, "It measures nothing, so its line stays open, and the pass measures that gap afresh.")
    assert mutant != flat, "the mutant must actually change the text"
    assert _replay_a_gap_no_row_can_measure(mutant) == ("never finishes", 10)


def test_carry_predicate_rejects_a_gap_dropped_once_a_route_takes_it():
    para = _bound()
    mutant = para.replace(
        "Whatever the route, a line stays open, so the story's next gate cycle, when there is one, copies it.", ""
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _carries_gaps(mutant, _reloop_bullet())


# --- when a re-run row closes its gap: mutate_check's own classifications ---------


_STATUS_RE = re.compile(
    r"`(KILLED\+others|KILLED|MISATTRIBUTED|GREEN|STALE|NOT UNIQUE|UNDECODABLE)`(?: with the detail that ([^(.]+))?"
)
_READINGS = (
    ("killed", "- A row reads killed when it is"),
    ("gap", "- A row that reads `GREEN` is still a gap"),
    ("cannot run", "- A row cannot run when it reads"),
)


def _reading(para: str, status: str, detail: str) -> str | None:
    """How gate.md's three bullets read one `mutate_check.py` row: `killed`,
    `gap` or `cannot run`, or None when no bullet names it. A qualified status
    counts only when the row's own detail carries the qualifier's words."""
    for kind, opener in _READINGS:
        bullet = next((line for line in para.splitlines() if line.startswith(opener)), "")
        for match in _STATUS_RE.finditer(bullet.split(". ")[0]):
            if match.group(1) != status:
                continue
            qualifier = match.group(2)
            if qualifier is None or qualifier.split("`")[-1].strip() in detail:
                return kind
    return None


_FIRST_CLOSE = "finds them all `KILLED`"
_SECOND_RUN = (
    "- A row that reads `GREEN` is still a gap unless it reads killed when re-run once more with its `command` "
    "replaced by the test command of the story's full sweep that covers its `file`, cache-defeated"
)
_SECOND_READS = (
    "When the second run reads killed, the row reads killed. When it reads `GREEN`, or cannot run (the next bullet), "
    "the row is still a gap, read by its first run: a second run that cannot run is no reason to measure the gap "
    "afresh."
)
_SECOND_READS_BEFORE = "When the second run reads anything else, these bullets read the row by the second run."
_REFUSED = "or when `mutate_check.py` refuses its table with exit 2 (no row ran)"


def _run_reading(para: str, result: dict | None) -> str | None:
    """A row's reading, with None for a table `mutate_check.py` refused."""
    if result is None:
        return "cannot run" if _REFUSED in para else None
    return _reading(para, result["status"], result["detail"])


def _settled(para: str, row: dict, full_command: str, run) -> str | None:
    """How gate.md reads one re-run row: verbatim first, and when that reads
    `GREEN` and the bullet orders it, once more with the full sweep's test
    command: a kill there reads the row killed, and anything else leaves it
    the gap its first run read."""
    kind = _run_reading(para, run(row))
    if kind == "gap" and _SECOND_RUN in para:
        second = _run_reading(para, run(dict(row, command=full_command)))
        if second != "killed" and _SECOND_READS in re.sub(r"\s+", " ", para):
            return "gap"
        return second
    return kind


def _clamp_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    # newline="\n", as test_mutate_check.py writes its projects: mutate_check reads bytes.
    (proj / "calc.py").write_text(
        "def clamp(x, hi):\n    if x > hi:\n        return hi\n    return x\n", encoding="utf-8", newline="\n"
    )
    (proj / "tests" / "test_basic.py").write_text(
        "from calc import clamp\n\n\ndef test_clamp_keeps_a_small_value():\n    assert clamp(1, 5) == 1\n",
        encoding="utf-8",
        newline="\n",
    )
    return proj


def test_a_gap_a_reloop_closes_with_a_test_of_another_name_reads_closed(tmp_path):
    """Measured on `mutate_check.py` itself. A reported gap's row names a test
    nobody wrote, so it reads GREEN; once a re-loop adds a killing test under its
    own name, the same row, re-run verbatim, reads MISATTRIBUTED, which the first
    wording (`KILLED` only) kept open for ever. A row whose own command runs one
    test file read the same close GREEN for ever when the killing test landed in
    another file; the full sweep's command, run once more, reads it killed."""
    mutate_check = _load_script("mutate_check")
    para = _bound()
    proj = _clamp_project(tmp_path)
    command = f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests'
    row = {
        "file": "calc.py",
        "anchor": "if x > hi:",
        "replacement": "if False:",
        "command": command,
        "expect_red": "test_clamp_caps_at_hi",
    }
    one_file = dict(row, command=f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests/test_basic.py')
    rows, code = mutate_check.run_table([row, one_file], proj)
    assert ([r["status"] for r in rows], code) == (["GREEN", "GREEN"], 1), rows
    assert _reading(para, "GREEN", rows[0]["detail"]) == "gap"

    def run(r: dict) -> dict:
        return mutate_check.run_table([r], proj)[0][0]

    # Before the re-loop's test the full command reads it GREEN too, so the gap stands.
    assert _settled(para, one_file, command, run) == "gap"

    (proj / "tests" / "test_reloop.py").write_text(
        "from calc import clamp\n\n\ndef test_upper_bound_is_enforced():\n    assert clamp(9, 5) == 5\n",
        encoding="utf-8",
        newline="\n",
    )
    named = dict(row, expect_red="test_upper_bound_is_enforced")
    stale = dict(row, anchor="if x >= hi:")
    rows, _ = mutate_check.run_table([row, named, stale, one_file], proj)
    assert [r["status"] for r in rows] == ["MISATTRIBUTED", "KILLED", "STALE", "GREEN"], rows
    assert [_reading(para, r["status"], r["detail"]) for r in rows] == ["killed", "killed", "cannot run", "gap"]
    # Re-run verbatim, the one-file row still reads GREEN; the full command's second run reads it killed.
    assert _settled(para, one_file, command, run) == "killed"
    assert _SECOND_READS in re.sub(r"\s+", " ", para)
    assert _FIRST_CLOSE not in GATE
    # Who makes the second run, and where its result is kept for the conductor to read.
    assert re.search(
        r"Automate makes that second run in the same pass, for each row it runs that reads `GREEN`, so when you "
        r"delegate it, tell it to, and to record both results beside the row in its summary\.",
        para,
    )


def test_closure_predicate_rejects_a_green_read_off_the_rows_own_command_alone(tmp_path):
    """The mutant twin of the second run: without it the one-file row keeps a
    closed gap open, rides every re-loop as a finding and lands on the ledger."""
    mutate_check = _load_script("mutate_check")
    para = _bound()
    start = para.index(_SECOND_RUN)
    end = para.index("\n", start)
    mutant = para[:start] + "- A row that reads `GREEN` is still a gap: the mutant survived." + para[end:]
    assert mutant != para, "the mutant must actually change the text"
    proj = _clamp_project(tmp_path)
    (proj / "tests" / "test_reloop.py").write_text(
        "from calc import clamp\n\n\ndef test_upper_bound_is_enforced():\n    assert clamp(9, 5) == 5\n",
        encoding="utf-8",
        newline="\n",
    )
    full = f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests'
    one_file = {
        "file": "calc.py",
        "anchor": "if x > hi:",
        "replacement": "if False:",
        "command": f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests/test_basic.py',
        "expect_red": "test_clamp_caps_at_hi",
    }

    def run(r: dict) -> dict:
        return mutate_check.run_table([r], proj)[0][0]

    assert _settled(para, one_file, full, run) == "killed"
    assert _settled(mutant, one_file, full, run) == "gap"


def _refusable(mutate_check, proj: Path):
    def run(r: dict) -> dict | None:
        try:
            return mutate_check.run_table([r], proj)[0][0]
        except SystemExit as exc:
            assert exc.code == 2
            return None  # refused: a red baseline, so no row ran

    return run


def _tracked_files_project(tmp_path: Path) -> tuple[Path, dict, str]:
    """The review's worktree: automate's untracked copy of a backfilled test
    (`tests/test_clamp.py`, exhaustive, its mutant equivalent) beside a tracked-
    files check the full sweep runs, which that copy turns red."""
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / "calc.py").write_text(
        "def clamp(x, hi):\n    if x > hi:\n        return hi\n    return x\n", encoding="utf-8", newline="\n"
    )
    (proj / "tracked.txt").write_text("tests/test_tracked.py\n", encoding="utf-8", newline="\n")
    (proj / "tests" / "test_tracked.py").write_text(
        "from pathlib import Path\n\n\ndef test_every_test_file_is_tracked():\n"
        "    tracked = Path('tracked.txt').read_text().split()\n"
        "    assert sorted(p.as_posix() for p in Path('tests').glob('test_*.py')) == sorted(tracked)\n",
        encoding="utf-8",
        newline="\n",
    )
    (proj / "tests" / "test_clamp.py").write_text(
        "import pytest\nfrom calc import clamp\n\n\n@pytest.mark.parametrize('x', range(-20, 20))\n"
        "def test_clamp_every_value(x):\n    assert clamp(x, 5) == (5 if x > 5 else x)\n\n\n"
        "def test_clamp_at_the_bound():\n    assert clamp(5, 5) == 5\n",
        encoding="utf-8",
        newline="\n",
    )
    row = {
        "file": "calc.py",
        "anchor": "if x > hi:",
        "replacement": "if x >= hi:",
        "command": f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests/test_clamp.py',
        "expect_red": "test_clamp_at_the_bound",
    }
    return proj, row, f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests'


def test_a_second_run_the_full_sweep_cannot_make_leaves_the_row_a_gap(tmp_path):
    """Measured on `mutate_check.py`: the row's own command reads the
    equivalent mutant GREEN, and the full sweep's command is red before any
    mutation, so the second run is refused with exit 2. That refusal measures
    nothing, so the row stays the gap its first run read (a confirmation then
    logs it `unkilled`) instead of sending the pass to measure it afresh."""
    mutate_check = _load_script("mutate_check")
    proj, row, full = _tracked_files_project(tmp_path)
    run = _refusable(mutate_check, proj)
    assert run(row)["status"] == "GREEN"
    assert run(dict(row, command=full)) is None
    para = _bound()
    assert _SECOND_RUN in para and _SECOND_READS in re.sub(r"\s+", " ", para)
    assert _settled(para, row, full, run) == "gap"


def test_closure_predicate_rejects_a_refused_second_run_read_as_cannot_run(tmp_path):
    """The mutant twin, the first wording: the second run's own reading stood,
    so a refused second run read `cannot run` and sent the gap to be measured
    afresh, where the same refusal met its fresh rows."""
    mutate_check = _load_script("mutate_check")
    proj, row, full = _tracked_files_project(tmp_path)
    para = _bound()
    mutant = para.replace(_SECOND_READS, _SECOND_READS_BEFORE)
    assert mutant != para, "the mutant must actually change the text"
    assert _settled(mutant, row, full, _refusable(mutate_check, proj)) == "cannot run"


def test_a_mutant_that_breaks_a_module_is_a_row_that_cannot_run(tmp_path):
    """Measured on `mutate_check.py`: a replacement that drops the colon breaks
    `calc.py`, pytest cannot collect the module that imports it, and no test
    runs. It read `MISATTRIBUTED` as a missing name, which the killed bullet
    reads as another test's kill, so the gap closed with no test run; it now
    reads 0 failed, which the cannot-run bullet names."""
    mutate_check = _load_script("mutate_check")
    proj = _clamp_project(tmp_path)
    (proj / "tests" / "test_clamp.py").write_text(
        "from calc import clamp\n\n\ndef test_clamp_at_the_bound():\n    assert clamp(9, 5) == 5\n",
        encoding="utf-8",
        newline="\n",
    )
    row = {
        "file": "calc.py",
        "anchor": "if x > hi:",
        "replacement": "if x > hi",
        "command": f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests',
        "expect_red": "test_clamp_at_the_bound",
    }
    rows, _ = mutate_check.run_table([row], proj)
    assert rows[0]["status"] == "MISATTRIBUTED", rows
    assert _reading(_bound(), rows[0]["status"], rows[0]["detail"]) == "cannot run"
    assert _ZERO_FAILED_CASES in re.sub(r"\s+", " ", _bound())
    assert "a mutant that breaks a module reads this way" not in _bound()


_ZERO_FAILED_CASES = (
    "(a collection or harness error, not a test: a mutant reads this way when pytest then cannot collect a test "
    "module or class or load a conftest.py, or jest, vitest or Node's test runner cannot load a test file, since no "
    "test in that file or class runs, or when a Node test file's process exits non-zero after its tests pass, and no "
    "other test fails)"
)
# 3.2.0's wording, which named neither a class pytest cannot collect nor Node's test runner.
_ZERO_FAILED_CASES_BEFORE = (
    "(a collection or harness error, not a test: a mutant reads this way when pytest then cannot collect a test "
    "module or load a conftest.py, or jest or vitest cannot load a test file, and no other test fails, since no test "
    "in that file runs)"
)
_NODE_CAPTURES = Path(__file__).resolve().parent / "fixtures" / "mutate_check_load_failure"


@pytest.mark.parametrize(
    "capture", ["node-spec-one-of-two", "node20-tap-alone", "node-tap-exits-after-its-tests-pass"]
)
def test_a_test_file_node_cannot_run_is_a_row_that_cannot_run(capture):
    """Measured on `mutate_check.py`, over real `node --test` output (#179):
    Node's test runner reports a test file whose process failed, because a
    mutant stops it loading or because its process exits non-zero after its
    tests pass, as a failed test named after the file. It read as another
    test's kill; it now reads 0 failed, which the cannot-run bullet names, Node
    and the non-zero exit included."""
    mutate_check = _load_script("mutate_check")
    output = (_NODE_CAPTURES / f"{capture}.txt").read_text(encoding="utf-8")
    status, detail, _ = mutate_check._classify_red(output, "clamp at the bound")
    assert status == "MISATTRIBUTED"
    assert _reading(_bound(), status, detail) == "cannot run"
    assert _ZERO_FAILED_CASES in re.sub(r"\s+", " ", _bound())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (_ZERO_FAILED_CASES, _ZERO_FAILED_CASES_BEFORE),
        ("cannot collect a test module or class or load", "cannot collect a test module or load"),
        ("or jest, vitest or Node's test runner cannot load", "or jest or vitest cannot load"),
        (", or when a Node test file's process exits non-zero after its tests pass,", ","),
    ],
    ids=["3.2.0", "no-class", "no-node", "no-exit"],
)
def test_zero_failed_pin_rejects_a_bullet_that_drops_a_case(old, new):
    """The twin: the cannot-run bullet's list of what reads 0 failed, read as
    3.2.0 wrote it or with one of #179's cases dropped, fails the pin."""
    para = re.sub(r"\s+", " ", _bound())
    mutant = para.replace(old, new)
    assert mutant != para, "the mutant must actually change the text"
    assert _ZERO_FAILED_CASES not in mutant


def test_a_red_with_no_failed_test_is_a_row_that_cannot_run():
    """`MISATTRIBUTED` also covers a red run whose own count says 0 failed, a
    collection or harness error: no test killed that mutant."""
    mutate_check = _load_script("mutate_check")
    status, detail, _ = mutate_check._classify_red(
        "FAILED tests/test_a.py::test_x - AssertionError\n===== 0 failed in 0.01s =====\n", "test_x"
    )
    assert status == "MISATTRIBUTED"
    assert _reading(_bound(), status, detail) == "cannot run"
    status, detail, _ = mutate_check._classify_red(
        "FAILED tests/test_a.py::test_x - assert 1 == 2\n===== 1 failed, 1 passed in 0.01s =====\n", "test_y"
    )
    assert status == "MISATTRIBUTED"
    assert _reading(_bound(), status, detail) == "killed"


def test_closure_predicate_rejects_the_killed_only_wording():
    mutate_check = _load_script("mutate_check")
    status, detail, _ = mutate_check._classify_red(
        "FAILED tests/test_reloop.py::test_upper - assert 9 == 5\n===== 1 failed, 1 passed in 0.01s =====\n",
        "test_clamp_caps_at_hi",
    )
    para = _bound()
    mutant = para.replace(
        "`KILLED`, `KILLED+others`, or `MISATTRIBUTED` with the detail that its `expect_red` never appears beside a "
        "failure token",
        "`KILLED`",
    )
    assert mutant != para, "the mutant must actually change the text"
    assert _reading(para, status, detail) == "killed"
    assert _reading(mutant, status, detail) is None


def test_closure_predicate_rejects_a_harness_error_read_as_a_kill():
    mutate_check = _load_script("mutate_check")
    status, detail, _ = mutate_check._classify_red(
        "FAILED tests/test_a.py::test_x - AssertionError\n===== 0 failed in 0.01s =====\n", "test_x"
    )
    para = _bound()
    mutant = para.replace(
        "or `MISATTRIBUTED` with the detail that its `expect_red` never appears beside a failure token",
        "or `MISATTRIBUTED`",
    )
    assert mutant != para, "the mutant must actually change the text"
    assert _reading(mutant, status, detail) == "killed"
    assert _reading(para, status, detail) == "cannot run"


def test_every_classification_mutate_check_prints_has_a_reading():
    """A status the prose never names would leave its line in no state."""
    mutate_check = _load_script("mutate_check")
    statuses = set(mutate_check._LEDGER_ORDER) | {"KILLED", "KILLED+others"}
    named = {m.group(1) for line in _bound().splitlines() for m in _STATUS_RE.finditer(line)}
    assert statuses <= named, statuses - named
    assert re.search(r"or when `mutate_check\.py` refuses its table with exit 2 \(no row ran\)", _bound())


# --- a backfill confirmed in its own pass, and the gap no test kills ---------------


def _backfill_kills_project(tmp_path: Path) -> tuple[Path, dict, str]:
    """The review's worktree for a backfill that does kill: automate's
    untracked copy of `tests/test_bound.py`, which kills `if False:`, beside a
    tracked-files check the full sweep runs, which that copy turns red, and a
    gap row whose own command runs only `tests/test_clamp.py`."""
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / "calc.py").write_text(
        "def clamp(x, hi):\n    if x > hi:\n        return hi\n    return x\n", encoding="utf-8", newline="\n"
    )
    (proj / "tracked.txt").write_text("tests/test_clamp.py\ntests/test_tracked.py\n", encoding="utf-8", newline="\n")
    (proj / "tests" / "test_tracked.py").write_text(
        "from pathlib import Path\n\n\ndef test_every_test_file_is_tracked():\n"
        "    tracked = Path('tracked.txt').read_text().split()\n"
        "    assert sorted(p.as_posix() for p in Path('tests').glob('test_*.py')) == sorted(tracked)\n",
        encoding="utf-8",
        newline="\n",
    )
    (proj / "tests" / "test_clamp.py").write_text(
        "from calc import clamp\n\n\ndef test_clamp_keeps_a_small_value():\n    assert clamp(1, 5) == 1\n",
        encoding="utf-8",
        newline="\n",
    )
    (proj / "tests" / "test_bound.py").write_text(
        "from calc import clamp\n\n\ndef test_upper_bound_is_enforced():\n    assert clamp(9, 5) == 5\n",
        encoding="utf-8",
        newline="\n",
    )
    row = {
        "file": "calc.py",
        "anchor": "if x > hi:",
        "replacement": "if False:",
        "command": f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests/test_clamp.py',
        "expect_red": "test_upper_bound_is_enforced",
    }
    return proj, row, f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests'


def _confirmation_reading(gate: str, row: dict, test_file: str, full_command: str, run) -> str | None:
    """How gate.md reads one of a gap's rows that automate re-runs to confirm
    the test it backfilled in `test_file`: with a command that also runs that
    file when the confirmation paragraph says so, then as any row is read."""
    confirm = _between(gate, _CONFIRM, "**Automate's summary records its rows.**")
    if _CONFIRM_COMMAND in re.sub(r"\s+", " ", confirm):
        row = dict(row, command=f"{row['command']} {test_file}")
    bound = _between(gate, _BOUND, "**Operator evidence is a recorded live result")
    return _settled(bound, row, full_command, run)


def test_a_confirmation_row_runs_the_backfilled_test_so_unkilled_means_it_ran(tmp_path):
    """Measured on `mutate_check.py`: the gap's row, run with its own command,
    never runs the backfilled test and reads `GREEN`, and the second run, with
    the full sweep's command, is refused, since the worktree's untracked copy
    of the test turns its tracked-files check red. Read by its first run, the
    row was logged `unkilled` and reached the ledger as a test that did not
    kill its mutant, though it does. A confirmation row now runs the test's
    file, so it reads killed, and `unkilled` means the test ran."""
    mutate_check = _load_script("mutate_check")
    proj, row, full = _backfill_kills_project(tmp_path)
    run = _refusable(mutate_check, proj)
    assert run(row)["status"] == "GREEN"
    assert run(dict(row, command=full)) is None
    assert run(dict(row, command=f"{row['command']} tests/test_bound.py"))["status"] == "KILLED"
    assert _confirmation_reading(GATE, row, "tests/test_bound.py", full, run) == "killed"


def test_confirmation_predicate_rejects_a_row_that_never_runs_the_test(tmp_path):
    """The mutant twin, the wording before: the same killing test reads as a
    gap, which the confirmation logs `unkilled`."""
    mutate_check = _load_script("mutate_check")
    proj, row, full = _backfill_kills_project(tmp_path)
    mutant = GATE.replace(" " + _CONFIRM_COMMAND, "")
    assert mutant != GATE, "the mutant must actually change the text"
    assert _confirmation_reading(mutant, row, "tests/test_bound.py", full, _refusable(mutate_check, proj)) == "gap"


_CONFIRM = "**A backfill is confirmed in the pass that writes it.**"
_COPY_RULE = (
    "When you delegate automate, tell it to write each test it backfills to its repo-relative path in the main tree, "
    "copy that file unchanged to the same path in the gate worktree, where its mutation rows run, and re-run there, "
    "with the test in place, the rows behind the gap the test was written for, making any later edit to the test in "
    "the main tree and copying it again."
)
_CONFIRM_COMMAND = (
    "Tell it, too, to give each row it re-runs there a `command` that runs the backfilled test's file, so that the "
    "row's own run sees the test: a row written before the test may select only the tests that existed then, and the "
    "second run with the full sweep's command (the second bullet below) can be refused in the worktree, where a "
    "tracked-files check sees the copy as a file git does not track."
)
_NO_SECOND_TEST = (
    "No later pass writes another test for an `unkilled` line while its rows can run: each later pass re-runs them, "
    "the line closes when they read killed, a row that reads `GREEN` keeps it open, and a row that cannot run "
    "(`STALE` once the code it mutates has moved) has the gap measured afresh, as for any line."
)


def _unkilled_rule(gate: str) -> bool:
    """A P0 backfill whose rows still read GREEN with its test in place is an
    `unkilled` line: logged, committed, not a finding, never a route, and never
    backfilled again while its rows run."""
    flat = re.sub(r"\s+", " ", gate)
    if _CONFIRM not in flat:
        return False
    confirm = _between(flat, _CONFIRM, "**Automate's summary records its rows.**")
    return bool(
        _COPY_RULE in confirm
        and "Read each row as \"A reported gap stays open until a later pass measures it closed\" below reads one."
        in confirm
        and "When every row reads killed, the test closed the gap." in confirm
        and _CONFIRM_COMMAND in confirm
        and "When a row still reads `GREEN` with the test in place, the test ran and did not kill that row's mutant, "
        "which may be an equivalent one that no test can tell from the code: log an `unkilled` `gate-gap:` line for "
        "the gap, naming the summary that records its rows and the test that did not kill them." in confirm
        and "The test is still committed with the backfill." in confirm
        and _NO_SECOND_TEST in confirm
        and "Like an `unmeasured` line, an `unkilled` line is not a finding, and it never changes the route the "
        "verdict takes." in confirm
        # The sentences elsewhere that the rule needs to hold as written.
        and "except a row behind an open `unkilled` line, which keeps that line open and gets no new test" in flat
        and "A gap behind an open `unkilled` line already has its test, so no pass writes it another while its rows "
        "can run" in flat
        and "in place of any `unkilled` line logged for that gap" in flat
        and "every open `gate-gap:` line of this cycle that is neither `unmeasured` nor `unkilled` as its findings"
        in flat
        and "an `unkilled` line's row says the backfilled test did not kill the mutant, which may be equivalent" in flat
    )


def test_a_backfill_its_test_leaves_green_is_an_unkilled_line():
    """An equivalent mutant reads GREEN whatever test automate writes, so the
    rule that every P0 gap gets a test backfilled it again in every pass, and
    nothing recorded it on advance."""
    assert _unkilled_rule(GATE)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (" " + _NO_SECOND_TEST, ""),
        ("an `unkilled` line is not a finding", "an `unkilled` line is a finding"),
        (", except a row behind an open `unkilled` line, which keeps that line open and gets no new test", ""),
        ("The test is still committed with the backfill.", "The test is dropped from the backfill."),
        ("copy that file unchanged to the same path in the gate worktree, where its mutation rows run, and re-run "
         "there", "and re-run in the gate worktree"),
        (" " + _CONFIRM_COMMAND, ""),
        ("the test ran and did not kill that row's mutant", "the test did not kill that row's mutant"),
    ],
)
def test_unkilled_predicate_rejects_a_mutated_rule(old, new):
    mutant = re.sub(r"\s+", " ", GATE).replace(old, new)
    assert mutant != re.sub(r"\s+", " ", GATE), "the mutant must actually change the text"
    assert not _unkilled_rule(mutant)


def test_an_equivalent_mutant_reads_green_under_both_commands(tmp_path):
    """The case the rule exists for, measured on `mutate_check.py`: `x >= hi`
    in a clamp is equivalent to `x > hi`, so an exhaustive test leaves the row
    GREEN under its own command and under the full sweep's command alike."""
    mutate_check = _load_script("mutate_check")
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / "calc.py").write_text(
        "def clamp(x, hi):\n    if x > hi:\n        return hi\n    return x\n", encoding="utf-8", newline="\n"
    )
    (proj / "tests" / "test_clamp.py").write_text(
        "import pytest\nfrom calc import clamp\n\n\n@pytest.mark.parametrize('x', range(-20, 20))\n"
        "def test_clamp_every_value(x):\n    assert clamp(x, 5) == (5 if x > 5 else x)\n\n\n"
        "def test_clamp_at_the_bound():\n    assert clamp(5, 5) == 5\n",
        encoding="utf-8",
        newline="\n",
    )
    row = {
        "file": "calc.py",
        "anchor": "if x > hi:",
        "replacement": "if x >= hi:",
        "command": f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests/test_clamp.py',
        "expect_red": "test_clamp_at_the_bound",
    }
    full = f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests'

    def run(r: dict) -> dict:
        return mutate_check.run_table([r], proj)[0][0]

    assert run(row)["status"] == "GREEN"
    assert _settled(_bound(), row, full, run) == "gap"


def _replay_operator_regates(gate: str, regates: int) -> list[str | None]:
    """Replay, on gate.md's own sentences, the loop the review described: a P0
    gap whose mutant is equivalent, on a story whose P0 operator-evidence AC
    escalates `operator-evidence-owed` at every commit the operator has not
    recorded at. Cycle 1 measured C0, backfilled a test that left the row GREEN
    and committed it as C1, so its line names C0 and the operator records at C1.
    Each later entry is one operator re-gate of the commit the previous gate
    measured, and holds the commit its backfill made, or None for no commit,
    which leaves the operator's records counting."""
    flat = re.sub(r"\s+", " ", gate)
    runs_for_a_line = (
        "When that diff is empty, automate still runs, for the open `gate-gap:` lines alone, when any of them names "
        "a commit other than the commit under assessment" in flat
    )
    no_search = "It searches for new gaps only in code that diff changes" in flat
    no_test = _NO_SECOND_TEST in flat
    no_commit = (
        "When this step stages nothing, there is no backfill: skip steps 2 through 5, and the commit under "
        "assessment stays the `gate-backfill-base:` commit" in flat
    )
    renamed = "A carried line that pass does not close is logged afresh in place of the copied line, naming this commit" in flat
    assert runs_for_a_line and no_search and no_commit and renamed
    head, line_names, made = 1, 0, []
    for _ in range(regates):
        if line_names == head:
            made.append(None)  # every open line names this commit: automate and the rebuild are skipped
            continue
        measured = head
        if no_test:
            made.append(None)  # its rows read GREEN, no test is written, step 1 stages nothing
        else:
            head += 1  # its rows read GREEN, so the P0 rule backfills the gap again and commits past the records
            made.append(f"C{head}")
        line_names = measured
    return made


def test_an_operator_regate_over_an_unkilled_gap_commits_nothing():
    """Bounded: the first re-gate runs automate only to re-run the line's rows,
    writes no test and commits nothing, so the operator's records at that commit
    still count; the line then names that commit and later re-gates skip
    automate. The fourth resume case's own rule is what the records rest on."""
    assert _replay_operator_regates(GATE, 4) == [None, None, None, None]
    fourth = _between(EXECUTE, "**A fourth case:", "**A fifth case:")
    assert re.search(
        r"Commit nothing before that gate while step 5's re-measure is green, since a commit past the assessed commit "
        r"makes the records stale",
        fourth,
    )


def test_replay_without_the_unkilled_rule_commits_past_the_records_every_time():
    """The mutant twin: with a second test allowed, each re-gate backfills the
    equivalent mutant again, commits past the operator's records, owes them
    again at the new commit, and never ends."""
    mutant = re.sub(r"\s+", " ", GATE).replace(_NO_SECOND_TEST, "")
    assert _replay_operator_regates(mutant, 4) == ["C2", "C3", "C4", "C5"]


# --- the summary a dead session left ----------------------------------------------


_REUSE = "**A summary already at that name is this cycle's own.**"
_GATE_AUTOMATE = (
    "and right before each time you delegate it, log `gate-automate: <sha>` in `.decision-log.md`, with `<sha>` the "
    "commit it measures, the one its summary's name carries: a session that ends while automate runs, or after it "
    "finishes but before anything is committed, then leaves a record of where its cycle stopped, and "
    "`references/execute.md`'s fifth resume case sends a resume that finds that line for `HEAD`, with no verdict and "
    "no backfill line after it, back to this paragraph instead of re-driving the story."
)


def _reuses_a_finished_pass(para: str) -> bool:
    return bool(
        _REUSE in para
        and re.search(r"No two cycles run automate at one commit \(\"When that diff is empty\", above\)", para)
        and re.search(
            r"TEA adds each step's output to a summary that already exists rather than starting a new one", para
        )
        and re.search(r"before you delegate automate, look for it", para)
        and _GATE_AUTOMATE in re.sub(r"\s+", " ", para)
        and "When none is there, delegate automate." in para
        and re.search(
            r"When it is there and complete \(its frontmatter's `lastStep` reads `step-04-validate-and-summarize`, "
            r"the last step of TEA's automate\), that pass finished: do not run automate again",
            para,
        )
        and re.search(r"logging only the `gate-gap:` lines this cycle's entry does not hold yet", para)
        and re.search(r"leave the dead session's worktree in place until the rebuild removes it", para)
        and re.search(
            r"When it is there but not complete, that pass stopped part way: move it aside to "
            r"`automation-summary-<story_id>-<sha>-stale-<n>\.md` in the same folder, with `<n>` the first number "
            r"from 1 that no file there carries yet, log the move in `\.decision-log\.md`, and only then delegate "
            r"automate",
            para,
        )
    )


def test_a_resume_reuses_a_finished_pass_and_sets_an_unfinished_one_aside():
    """A session that died after automate, before any backfill line, sent the
    resume through the ordinary route into Stage 5, which ran automate again
    and TEA appended the new pass to the dead one's summary."""
    assert _reuses_a_finished_pass(_bound())


def test_reuse_predicate_rejects_a_rerun_into_the_same_summary():
    para = _bound()
    start = para.index("When it is there but not complete")
    end = para.index("\n\n", start)
    mutant = para[:start] + "When it is there but not complete, delegate automate." + para[end:]
    assert not _reuses_a_finished_pass(mutant)


def test_reuse_predicate_rejects_a_reuse_with_no_completeness_check():
    para = _bound()
    mutant = para.replace(
        " and complete (its frontmatter's `lastStep` reads `step-04-validate-and-summarize`, the last step of TEA's "
        "automate)",
        "",
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _reuses_a_finished_pass(mutant)


def test_reuse_predicate_rejects_a_delegation_that_leaves_no_line():
    """A later-cycle session that died after automate, with no backfill line,
    left nothing a resume could read, so it resumed as `mid-story`."""
    para = _bound()
    flat = re.sub(r"\s+", " ", para)
    mutant = flat.replace(", " + _GATE_AUTOMATE, ".")
    assert mutant != flat, "the mutant must actually change the text"
    assert not _reuses_a_finished_pass(mutant)


def _records_rows(para: str) -> bool:
    return bool(
        "**Automate's summary records its rows.**" in para
        and re.search(
            r"name its summary `\{workflow\.implementation_artifacts\}/automation-summary-<story_id>-<sha>\.md`, "
            r"with `<sha>` the commit it measures as `git rev-parse HEAD` prints it",
            para,
        )
        and re.search(
            r"tell it to copy into that summary, verbatim, each `scripts/mutate_check\.py` table row \(`file`, "
            r"`anchor`, `replacement`, `command`, `expect_red`\) behind a gap it backfilled or reported, or behind an "
            r"open `gate-gap:` line it re-ran and leaves open, so a later cycle can re-run them",
            para,
        )
        and re.search(r"If automate writes the flat file anyway, move it to that name before anything else reads it", para)
    )


def test_automate_records_its_rows_in_a_summary_named_per_story_and_commit():
    """A later cycle re-runs these rows, so they need a home it can find: TEA's
    flat summary is updated by every pass, and the generated ledger drops the
    keys a re-run needs."""
    assert _records_rows(_bound())


def test_rows_predicate_rejects_a_summary_with_no_rows():
    para = _bound()
    start = para.index("and tell it to copy into that summary, verbatim")
    end = para.index("so a later cycle can re-run them.", start) + len("so a later cycle can re-run them")
    mutant = para[:start] + para[end:]
    assert mutant != para, "the mutant must actually change the text"
    assert not _records_rows(mutant)


def test_the_rows_named_are_the_keys_a_table_row_needs():
    """The five keys the prose names are the keys `mutate_check.py` refuses a
    row without, and its ledger leaves three of them out."""
    mutate_check = _load_script("mutate_check")
    named = re.search(r"table row \(((?:`\w+`(?:, )?)+)\) behind a gap", _bound()).group(1)
    assert tuple(re.findall(r"`(\w+)`", named)) == mutate_check.REQUIRED_KEYS
    header = mutate_check.render_ledger([]).splitlines()[4]
    for key in ("anchor", "replacement", "command"):
        assert key not in header
    assert re.search(r"leaves out each row's anchor, replacement and command", _bound())


_ROWS = "**Automate's summary records its rows.**"
_RETURNED = (
    "A host can also refuse a delegated agent's write of a report file, so tell automate, too, that when the host "
    "refuses its write of the summary, or of a draft of it, it returns the summary's full text, its frontmatter and "
    "its rows included, in its result, rather than write it some other way.",
    "When it returns that text, write it at that name yourself, unchanged, in place of whatever is there, before "
    "anything else reads it and before you log its `gate-gap:` lines, and log in `.decision-log.md` that you wrote it "
    "from automate's text.",
    "Its rows are then the ones automate copied, and its frontmatter's `lastStep` the one automate's text gives, "
    "never one you set, so a resume reads it as \"A summary already at that name is this cycle's own\" below says.",
)


def _writes_a_returned_summary(para: str) -> bool:
    flat = re.sub(r"\s+", " ", para)
    return bool(
        _ROWS in flat
        and all(sentence in flat for sentence in _RETURNED)
        # The maintainer's ruling on #183: the step names no host's own rule,
        # and a summary automate returned as text adds no automate pass.
        and "Claude Code" not in flat
        and not re.search(r"(?<!not )(?:delegate|run) automate (?:again|a second time)", flat)
    )


def test_a_summary_automate_could_not_write_is_written_from_its_text():
    """#183: the host refused automate's write of a draft of its summary, and
    automate returned the summary as text, but the gate named no step for that,
    so the conductor composed a summary of its own, frontmatter included. With
    no summary at that name, the backfill has no list of tests to stage, a later
    cycle loses the rows it re-runs, and a resume runs automate again at a
    commit it measured."""
    assert _writes_a_returned_summary(_paragraph(GATE, _ROWS))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The improvisation: the conductor composes a summary, or a lastStep, of its own.
        ("write it at that name yourself, unchanged, in place", "write it at that name yourself, in place"),
        ("its frontmatter and its rows included, ", ""),
        ("the one automate's text gives, never one you set", "`step-04-validate-and-summarize`, which you set"),
        # A refused draft, the case #183 met, left out.
        ("refuses its write of the summary, or of a draft of it,", "refuses its write of the summary,"),
        # Written after something has read it, or after the lines that name it.
        ("before anything else reads it and before you log", "before you log"),
        ("before anything else reads it and before you log its `gate-gap:` lines", "after you log its `gate-gap:` lines"),
        # A delegate that routes around the host's refusal.
        (", rather than write it some other way.", ", or writes it some other way."),
        # No record of who wrote the file.
        (", and log in `.decision-log.md` that you wrote it from automate's text.", "."),
        # The host's own rule named, or an automate pass the step adds.
        ("below says.", "below says. Claude Code refuses a subagent's write of a `.md` file whose name starts with "
         "`summary`."),
        ("below says.", "below says. When it returns no text either, delegate automate again."),
    ],
)
def test_returned_summary_predicate_rejects_a_weaker_rule(old, new):
    para = re.sub(r"\s+", " ", _paragraph(GATE, _ROWS))
    mutant = para.replace(old, new)
    assert mutant != para, "the mutant must actually change the text"
    assert not _writes_a_returned_summary(mutant)


def test_returned_summary_predicate_rejects_the_pre_edit_paragraph():
    para = re.sub(r"\s+", " ", _paragraph(GATE, _ROWS))
    pre_edit = para
    for sentence in _RETURNED:
        pre_edit = pre_edit.replace(" " + sentence, "")
    assert pre_edit != para, "the pre-edit paragraph must actually differ"
    assert _records_rows(pre_edit)
    assert not _writes_a_returned_summary(pre_edit)


def _delta_says_automate_is_scoped(para: str) -> bool:
    return bool(
        "exactly as before" not in para
        and re.search(
            r"ADVANCE requires the full instrument \(every assessor over a `scope=full` sweep, with automate in the scope "
            r"\"At most one automate pass finishes per gate cycle\"",
            para,
        )
        and re.search(r"Automate is not one of the assessors this choice sorts", para)
        and re.search(r"that scope's re-run of the gap's mutation rows is the re-run in full of its dimension", para)
    )


def test_the_delta_profile_defines_the_full_instrument_with_automate_scoped():
    """Two definitions of the full instrument would let a literal conductor run
    automate in full on the confirming cycle, which reopens the unbounded loop."""
    assert _delta_says_automate_is_scoped(_delta_paragraph())


def test_delta_predicate_rejects_the_pre_edit_sentence():
    para = _delta_paragraph()
    mutant = re.sub(
        r"ADVANCE requires the full instrument \(.*?\), so the oracle",
        "ADVANCE requires the full instrument (every assessor, over a `scope=full` sweep), exactly as before, so the oracle",
        para,
        flags=re.S,
    )
    assert mutant != para, "the mutant must actually change the text"
    assert not _delta_says_automate_is_scoped(mutant)


# --- the commit structure every copy states ---------------------------------------


_REPO_ROOT = REFS.parents[2]


def test_every_copy_of_the_commit_structure_names_the_backfill_commit():
    """SKILL.md's rollback bullet names the backfill commit; its copies in the
    docs, the README and ucg-status said implementation plus evidence only."""
    skill = (REFS.parent / "SKILL.md").read_text(encoding="utf-8")
    assert "plus its gate's commits (a test backfill when automate makes one, then the evidence)" in skill
    copies = {
        "docs/architecture.md": "plus its gate's commits: a test backfill when automate makes one, then the evidence",
        "docs/why-ultracode-goal.md": "plus its gate's commits (a test backfill when automate makes one, then the evidence)",
        "docs/index.md": "plus its gate's commits (a test backfill when the gate adds coverage, then the evidence)",
        "README.md": "code + gate commits per story",
        "skills/ucg-status/SKILL.md": "the gate's test backfill commit when automate made one",
        "docs/how-it-works.md": (
            "one implementation commit per green story; the gate's commits follow it: a test backfill when "
            "automate makes one, then the evidence"
        ),
    }
    for path, phrase in copies.items():
        text = re.sub(r"\s+", " ", (_REPO_ROOT / path).read_text(encoding="utf-8"))
        assert phrase in text, path
        assert "plus its gate's evidence commit" not in text, path
        assert "code + evidence commit per story" not in text, path


def test_the_end_marker_names_the_backfill_commit_among_its_writers():
    """`.commit-<story_id>` names the story's last commit, and the backfill
    commit is one of the commits that can be last before the evidence."""
    assert re.search(
        r"step 5 rewrites it after any remediation re-commit or amend, the gate rewrites it after the commit of a "
        r"test `bmad-testarch-automate` backfilled \(gate\.md's \"When automate backfills\"\), and the gate's advance "
        r"route rewrites it after its evidence commit",
        EXECUTE,
    )


def _gate_model_scopes_automate(text: str) -> bool:
    text = re.sub(r"\s+", " ", text)
    return bool(
        re.search(
            r"`bmad-testarch-automate` sits outside this choice: after a story's first gate cycle, full or delta, it "
            r"searches only the diff since the previous gate and re-runs the mutation rows behind the gaps that gate "
            r"backfilled and behind every gap still open, and the full instrument runs it at that scope too",
            text,
        )
        and re.search(
            r"It backfills every gap it finds on a P0 criterion, in any cycle, so trace counts the new test and the "
            r"script decides; only a gap on another criterion is reported instead, when it lies outside that scope "
            r"or while operator live results sit at the commit under assessment",
            text,
        )
        and re.search(
            r"A reported gap stays open until a pass at a later commit finds its mutants killed, and it never changes "
            r"the route a verdict takes",
            text,
        )
    )


def test_the_gate_model_states_automate_scope_and_the_p0_backfill_rule():
    assert _gate_model_scopes_automate((_REPO_ROOT / "docs" / "gate-model.md").read_text(encoding="utf-8"))


def test_gate_model_predicate_rejects_a_full_search_every_cycle():
    text = (_REPO_ROOT / "docs" / "gate-model.md").read_text(encoding="utf-8")
    mutant = text.replace(
        "it searches only the diff since the previous gate", "it searches the whole codebase again, as on the first cycle"
    )
    assert mutant != text, "the mutant must actually change the text"
    assert not _gate_model_scopes_automate(mutant)


def test_gate_model_predicate_rejects_the_p0_stop_the_maintainer_overruled():
    text = (_REPO_ROOT / "docs" / "gate-model.md").read_text(encoding="utf-8")
    start = text.index("It backfills every gap it finds on a P0 criterion")
    end = text.index("`--epic-level` refuses the flag", start)
    mutant = (
        text[:start]
        + "A gap it reports stays open until a pass at a later commit finds its mutants all killed, and an open gap "
        "on a P0 criterion sends the story back to a re-loop before trace runs. "
        + text[end:]
    )
    assert not _gate_model_scopes_automate(mutant)


_STAGE5 = (
    "In production, the skill first backfills the evidence: `bmad-testarch-automate` runs first and alone, a test "
    "it backfills is committed before anything else measures the story, and only then do `bmad-testarch-trace` "
    "(which writes the gate decision), `bmad-testarch-nfr` and, when the story lacks a current review, "
    "`bmad-testarch-test-review` run."
)


def test_how_it_works_runs_automate_first_and_alone_then_commits_its_backfill():
    """The Stage 5 overview listed automate, trace and NFR as a plain sequence,
    which said nothing of the backfill commit between them."""
    text = re.sub(r"\s+", " ", (_REPO_ROOT / "docs" / "how-it-works.md").read_text(encoding="utf-8"))
    assert _STAGE5 in text
    assert "backfills the evidence in order: `bmad-testarch-automate`, `bmad-testarch-trace`" not in text


_GATE_MODEL_UNKILLED = (
    "Automate confirms each test it backfills in the same pass, with the test copied into the worktree, and a test "
    "that leaves its mutant alive (perhaps an equivalent mutant, which no test can kill) is logged as an `unkilled` "
    "gap that no later pass writes another test for while that code stands."
)
_HOW_IT_WORKS_LEDGER = (
    "only non-gate-blocking work lands here (CONCERNS, non-critical findings, parked decisions, and the coverage gaps "
    "the gate's automate pass logged that are still open, at `med` severity whatever their priority); a P0/critical "
    "FAIL is never deferred."
)
_TROUBLESHOOTING_ORDER = (
    "In production, Stage 5 must backfill evidence first (`bmad-testarch-automate` first and alone, then the commit "
    "of any test it backfilled, then `bmad-testarch-trace` and `bmad-testarch-nfr`) before the gate;"
)


def _docs_say_what_the_gate_does(gate_model: str, how: str, trouble: str) -> bool:
    gate_model, how, trouble = (re.sub(r"\s+", " ", text) for text in (gate_model, how, trouble))
    return bool(
        _GATE_MODEL_UNKILLED in gate_model
        and _HOW_IT_WORKS_LEDGER in how
        and _TROUBLESHOOTING_ORDER in trouble
        and "`bmad-testarch-automate` → `bmad-testarch-trace` → `bmad-testarch-nfr`" not in trouble
    )


def test_the_docs_name_the_unkilled_gap_the_gap_rows_and_the_backfill_commit():
    """The ledger copies in the docs listed only CONCERNS, non-critical findings
    and parked decisions, and troubleshooting's order left out the backfill
    commit between automate and trace."""
    docs = _REPO_ROOT / "docs"
    assert _docs_say_what_the_gate_does(
        (docs / "gate-model.md").read_text(encoding="utf-8"),
        (docs / "how-it-works.md").read_text(encoding="utf-8"),
        (docs / "troubleshooting.md").read_text(encoding="utf-8"),
    )


@pytest.mark.parametrize(
    ("doc", "old", "new"),
    [
        ("gate-model.md", " " + _GATE_MODEL_UNKILLED, ""),
        ("how-it-works.md", ", and the coverage gaps the gate's automate pass logged that are still open, at `med` "
         "severity whatever their priority", ""),
        ("troubleshooting.md", "`bmad-testarch-automate` first and alone, then the commit of any test it backfilled, "
         "then `bmad-testarch-trace` and `bmad-testarch-nfr`",
         "`bmad-testarch-automate` → `bmad-testarch-trace` → `bmad-testarch-nfr`"),
    ],
)
def test_docs_predicate_rejects_a_dropped_rule(doc, old, new):
    docs = _REPO_ROOT / "docs"
    texts = {name: (docs / name).read_text(encoding="utf-8") for name in ("gate-model.md", "how-it-works.md",
                                                                          "troubleshooting.md")}
    flat = re.sub(r"\s+", " ", texts[doc])
    mutant = flat.replace(old, new)
    assert mutant != flat, "the mutant must actually change the text"
    texts[doc] = mutant
    assert not _docs_say_what_the_gate_does(texts["gate-model.md"], texts["how-it-works.md"], texts["troubleshooting.md"])


def test_the_trail_names_every_writer_of_the_end_marker():
    """`.commit-<story>` names the story's last commit; the trail's docstring
    listed its writers and left out the gate's backfill commit."""
    doc = re.sub(r"\s+", " ", _load_script("gate_trail").commit_sha.__doc__ or "")
    assert (
        "step 5 refreshes it after any amend or remediation re-commit, the gate refreshes it after it commits a test "
        "`bmad-testarch-automate` backfilled (`references/gate.md`, \"When automate backfills\"), and the gate's "
        "advance route refreshes it after its evidence commit"
    ) in doc


def _fragments() -> tuple[str, str]:
    changes = _REPO_ROOT / "changes"
    alone = re.sub(r"\s+", " ", (changes / "gate-automate-runs-alone.yaml").read_text(encoding="utf-8"))
    backfill = re.sub(r"\s+", " ", (changes / "gate-automate-backfill-commit.yaml").read_text(encoding="utf-8"))
    return alone, backfill


_ALONE_SAYS = (
    "None of them may edit a file in the worktree, so none of them runs a mutant",
    "Once automate has finished, and its backfill, when it made one, is committed, the gate rebuilds the worktree "
    "at the commit under assessment",
    "and the rebuild also discards the copy of each backfilled test that automate puts in the worktree to confirm "
    "the test there.",
    "Only then do trace, NFR and test review start, in any order or concurrently.",
    "The rebuild is skipped only when no automate pass ran in the cycle, or when a red sweep over the backfill ended "
    "the cycle before trace, since then no other assessor runs in it.",
    # M27
    "The decision log's worktree line now also says whether automate ran alone and names the commit the worktree "
    "was rebuilt at.",
)
_BACKFILL_SAYS = (
    "stages the test files that pass's summary names by explicit path",
    # M28
    "A test the summary names that neither tree holds as a change is left out and logged as a gap.",
    "The gate fixes a red in that sweep only in the backfilled test files, at most twice, and reads a repo commit "
    "hook's rejection of the backfill commit as such a red, within the same two fixes.",
    "A red that needs any other change ends the cycle before trace, and of what automate's pass and its backfill "
    "produce it is the only thing that does (a sub-skill that blocks on input or is not installed still escalates the "
    "story)",
    "a `reloop` verdict is logged as a JSON object with its `reasons` and an `assessed-commit` line naming the "
    "commit automate measured (the heartbeat's `last_reasons` copies those reasons, and an attended run prints the "
    "verdict with `gate_status` `n/a`)",
    "the re-loop takes the red and every open gap that is neither `unmeasured` nor `unkilled` as its findings, and "
    "the gate after it is a full one",
    "The gate logs a `gate-automate:` line naming the commit automate measures right before it delegates automate, "
    "so a resume that finds that line for `HEAD` with no verdict and no backfill line after it goes on with that gate "
    "cycle, through that summary check, instead of re-driving the story.",
    "It also confirms each test it backfills in the same pass: it writes the test to the main tree, copies it into "
    "the gate worktree and re-runs the gap's rows there with it in place, each with a command that runs the test's "
    "file.",
    "A test that runs and leaves a row `GREEN` (its mutant may be an equivalent one, which no test can kill) is still "
    "committed and is logged as an `unkilled` gap, which no later pass writes another test for while its rows still "
    "run.",
    "A repo commit hook that rejects the advance route's evidence commit is answered only in what the gate writes for "
    "that commit (the `done` sync in `sprint-status.yaml` and `.decision-log.md`), at most twice; when it asks for a "
    "change to any other path, such as a file TEA wrote or a ledger row, or rejects the commit a third time, the gate "
    "commits nothing and escalates the story with `kind` `evidence-commit-rejected`, and a resume makes that commit "
    "only once `/ucg-resolve` has closed the escalation.",
    # M46
    "A later cycle of the same story, full or delta, scopes automate's search",
    "and when that diff is empty runs automate only when an open gap's line names a commit other than the commit "
    "under assessment.",
    "A row that reads `GREEN`, in any pass and whether it searches, re-runs or confirms, counts as a gap unless it "
    "reads killed when run again with its command replaced by the test command of the story's full sweep that covers "
    "its file, so a closing test in a file the row's own command does not run still closes the gap; automate records "
    "both results beside the row in its summary, and a second run that cannot run leaves the row a gap.",
    "holds, verbatim, the `mutate_check.py` table rows behind each gap it backfilled or reported and behind each open "
    "gap it re-ran and leaves open.",
    "A gap whose rows cannot run (a stale anchor, a mutant that breaks a module so no test runs, or a table "
    "`mutate_check.py` refuses) is measured afresh once in the pass, and when the fresh rows cannot run either it is "
    "logged `unmeasured` for the next pass, so a pass always finishes.",
    # M29
    "on a `reloop` that is not cap-only it is one of the findings unless it is `unmeasured` or `unkilled`, and on "
    "`advance` or `defer` it becomes a ledger row with `source` `gate` and `severity` `med`, which is neither a gate "
    "FAIL nor a critical finding whatever its criterion's priority, so it never re-loops or escalates the story.",
    "At most one automate pass now finishes per gate cycle, and a backfill never restarts the cycle.",
    "`automation-summary-<story_id>-<sha>.md`",
    "A resume that finds that summary complete reuses it instead of running automate again, and one that finds it "
    "incomplete moves it aside with a `-stale-<n>` suffix, logged, before automate runs.",
    "Automate backfills every gap it finds on a P0 criterion, in any cycle and whatever its scope, even while "
    "operator live results sit at the commit under assessment (the backfill commit moves the commit past them, and "
    "the gate's existing operator-evidence routes owe them again at the new commit), so TEA's trace counts the new "
    "test and `gate_eval.py` decides.",
    "Automate measures each risk it names on a P0 criterion in the same pass, and backfills each gap that measuring "
    "confirms.",
    "Only a gap on another criterion is reported rather than backfilled: one outside a later cycle's scope, or any "
    "while live results sit at the commit.",
    "which every later cycle carries until a pass at a later commit finds the gap's mutants killed (`KILLED`, "
    "`KILLED+others`, or `MISATTRIBUTED` because a test of another name went red)",
    "A `gate-gap:` line never changes the route a verdict takes",
    "while `HEAD` is still that backfill's base or its commit, goes on with that gate cycle",
    "a resume after a re-loop that ended its cycle before trace, with `HEAD` still at its assessed commit, "
    "resumes that re-loop",
)


_COLLECTION_SAYS = (
    # What R1 catches, and no more: the headline once said "a mutant that breaks a module".
    "`mutate_check.py` no longer reads a mutant as another test's kill when it stops pytest collecting a test module "
    "or loading a conftest.py, or stops jest or vitest loading a test file.",
    "nor does a conftest.py it cannot load before it collects, which it reports as `ImportError while loading "
    "conftest` with no summary at all, nor a module the root conftest names in `pytest_plugins`, which stops pytest "
    "with a bare traceback.",
    "A line inside a multi-line skip reason or failure message that starts with `ERROR` no longer counts as a "
    "collection error",
    "jest's `Test Suites:` line and vitest's `Test Files` line, which count a test file that failed to load as a "
    "failed one, are no longer read for a count once their `Tests` line was, one that reads `no tests` included.",
    # V5: the reading the gate gives a 0-failed row.
    "A red run whose count of failures is 0 now reads `MISATTRIBUTED` with the detail that the output's own count "
    "says 0 failed, which the gate reads as a row that cannot run, whether or not the output names the test.",
    "A test whose fixture raises still counts as a failure",
    "the collection error is no longer counted as a second failure beside a kill.",
    "Node's test runner counts a test file it cannot load as a failed test, so there such a mutant still reads as a "
    "kill.",
)


def _collection_fragment() -> str:
    return re.sub(
        r"\s+", " ", (_REPO_ROOT / "changes" / "mutate-check-collection-error.yaml").read_text(encoding="utf-8")
    )


def _collection_gaps(collection: str) -> list[str]:
    missing = [phrase for phrase in _COLLECTION_SAYS if phrase not in collection]
    if not collection.startswith("type: fixed"):
        missing.append("the collection error is a fix")
    if "no longer reads a mutant that breaks a module as another test's kill" in collection:
        missing.append("the headline claims every mutant that breaks a module")
    return missing


# #179's release note: the four misreads, each as mutate_check.py now reads it.
_COUNT_SAYS = (
    "and a count quoted there, such as a `0 failed` a test prints, no longer stands in for the run's count.",
    "A count that another runner in the same command prints outside pytest's report, such as `cargo test`'s, is still "
    "read.",
    "a collection error at a path that holds a space, and one for a test class (`ERROR <path>::<Class>` in the short "
    "summary, an id whose last part starts with a capital letter), now count as collection errors rather than "
    "failures, so such a mutant reads 0 failed instead of a kill.",
    "When one command runs pytest twice, each run's collection errors are taken off its own stats line only",
    "a kill no longer reads 0 failed beside a `-qq` run.",
    "Node's test runner reports a test file whose process failed (a mutant stops it loading, or its process exits "
    "non-zero after its tests pass) as a failed test named after the file and located at its line 1, column 1.",
    "That test no longer counts, so such a mutant reads 0 failed, a row that cannot run,",
)


def _count_fragment() -> str:
    return re.sub(
        r"\s+", " ", (_REPO_ROOT / "changes" / "mutate-check-count-misreads.yaml").read_text(encoding="utf-8")
    )


def _count_gaps(count: str) -> list[str]:
    missing = [phrase for phrase in _COUNT_SAYS if phrase not in count]
    if not count.startswith("type: fixed"):
        missing.append("#179 is a fix")
    return missing


def _fragment_gaps(alone: str, backfill: str) -> list[str]:
    missing = [phrase for phrase in _ALONE_SAYS if phrase not in alone]
    missing += [phrase for phrase in _BACKFILL_SAYS if phrase not in backfill]
    if not alone.startswith("type: fixed"):
        missing.append("#174 is a fix")
    if not backfill.startswith("type: changed"):
        missing.append("#175 is a change")
    return missing


def test_the_fragments_say_what_the_prose_does():
    alone, backfill = _fragments()
    assert _fragment_gaps(alone, backfill) == []
    assert _collection_gaps(_collection_fragment()) == []
    assert _count_gaps(_count_fragment()) == []
    # Earlier wordings: a carry past two routes only, a P0 gap that never reached
    # trace, and automate once per cycle with no resume to qualify it.
    assert "a gap a cap-only re-loop or an escalation leaves untaken is carried" not in backfill
    assert "a gap on a P0 criterion never defers" not in backfill
    assert "Automate now runs once per gate cycle" not in backfill
    # The rows wording did not hold for an `unmeasured` line, which has no rows.
    assert "an open gap's rows last ran on another commit" not in backfill
    # The second run limited to re-run rows, and an only-stop that a sub-skill halt contradicted.
    assert "A re-run row that reads `GREEN` counts as a gap only when" not in backfill
    assert "and it is the only thing that does:" not in backfill


@pytest.mark.parametrize(
    ("which", "old", "new"),
    [
        ("alone", "Only then do trace, NFR and test review start, in any order or concurrently.",
         "Trace, NFR and test review may start beside it."),
        ("backfill", "at most twice,", "in any file, until green,"),
        # M27, M28, M29 and M46, which survived the previous round.
        ("alone", " The decision log's worktree line now also says whether automate ran alone and names the commit "
         "the worktree was rebuilt at.", ""),
        ("backfill", " A test the summary names that neither tree holds as a change is left out and logged as a gap.",
         ""),
        ("backfill", "on a `reloop` that is not cap-only it is one of the findings unless it is `unmeasured` or "
         "`unkilled`, and on `advance` or `defer` it becomes a ledger row with `source` `gate` and `severity` `med`",
         "it is dropped once the verdict is logged"),
        ("backfill", "A later cycle of the same story, full or delta,", "A later cycle of the same story, full only,"),
        ("alone", " The rebuild is skipped only when no automate pass ran in the cycle, or when a red sweep over the "
         "backfill ended the cycle before trace, since then no other assessor runs in it.", ""),
        ("backfill", "is still committed and is logged as an `unkilled` gap", "is backfilled again in the next pass"),
        ("backfill", "by explicit path", "every path `git status` lists"),
        ("backfill", "Automate measures each risk it names on a P0 criterion in the same pass, and backfills each gap "
         "that measuring confirms. ", ""),
        ("backfill", "A `gate-gap:` line never changes the route a verdict takes",
         "An open P0 gap ends the cycle before trace"),
        # Finding 7 and its neighbours, each pinned.
        ("backfill", "A row that reads `GREEN`, in any pass and whether it searches, re-runs or confirms,",
         "A re-run row that reads `GREEN`"),
        ("backfill", " and behind each open gap it re-ran and leaves open", ""),
        ("backfill", "; automate records both results beside the row in its summary", ""),
        ("backfill", " (a sub-skill that blocks on input or is not installed still escalates the story)", ""),
        ("backfill", ", so a pass always finishes", ""),
        # The confirmation row's command, and the evidence commit's hook rule.
        ("backfill", ", each with a command that runs the test's file", ""),
        ("backfill", "A test that runs and leaves a row `GREEN`", "A test that leaves a row `GREEN`"),
        ("backfill", ", at most twice; when it asks", "; when it asks"),
        ("backfill", "only in what the gate writes for that commit (the `done` sync in `sprint-status.yaml` and "
         "`.decision-log.md`)", "in the files that commit carries"),
        ("backfill", " and escalates the story with `kind` `evidence-commit-rejected`", ""),
        # V5, and the headline the review found claimed more than mutate_check catches.
        ("collection", "which the gate reads as a row that cannot run", "which the gate reads as a kill"),
        ("collection", "no longer reads a mutant as another test's kill when it stops pytest collecting a test module "
         "or loading a conftest.py, or stops jest or vitest loading a test file.",
         "no longer reads a mutant that breaks a module as another test's kill."),
        ("collection", ", nor does a conftest.py it cannot load before it collects, which it reports as `ImportError "
         "while loading conftest` with no summary at all", ""),
        ("collection", ", nor a module the root conftest names in `pytest_plugins`, which stops pytest with a bare "
         "traceback", ""),
        ("collection", ", one that reads `no tests` included", ""),
        ("collection", " Node's test runner counts a test file it cannot load as a failed test, so there such a mutant "
         "still reads as a kill.", ""),
        # #179: each of the four misreads, the reading it now gives, and the count still read.
        ("count", ", such as `cargo test`'s, is still read.", ", such as `cargo test`'s, is no longer read."),
        ("count", ", and one for a test class (`ERROR <path>::<Class>` in the short summary, an id whose last part "
         "starts with a capital letter),", ""),
        ("count", "a collection error at a path that holds a space, and one", "one"),
        ("count", "are taken off its own stats line only", "are taken off its first stats line"),
        ("count", " and a kill no longer reads 0 failed beside a `-qq` run.", ""),
        ("count", "(a mutant stops it loading, or its process exits non-zero after its tests pass)",
         "(a mutant stops it loading)"),
        ("count", "so such a mutant reads 0 failed, a row that cannot run,", "so such a mutant reads as a kill,"),
    ],
)
def test_fragment_predicate_rejects_a_sentence_that_contradicts_the_prose(which, old, new):
    """Fragment sentences that once survived mutation, each pinned now."""
    alone, backfill = _fragments()
    if which == "count":
        count = _count_fragment()
        mutant = count.replace(old, new)
        assert mutant != count, "the mutant must actually change the text"
        assert _count_gaps(mutant)
    elif which == "collection":
        collection = _collection_fragment()
        mutant = collection.replace(old, new)
        assert mutant != collection, "the mutant must actually change the text"
        assert _collection_gaps(mutant)
    elif which == "alone":
        mutant = alone.replace(old, new)
        assert mutant != alone, "the mutant must actually change the text"
        assert _fragment_gaps(mutant, backfill)
    else:
        mutant = backfill.replace(old, new)
        assert mutant != backfill, "the mutant must actually change the text"
        assert _fragment_gaps(alone, mutant)
