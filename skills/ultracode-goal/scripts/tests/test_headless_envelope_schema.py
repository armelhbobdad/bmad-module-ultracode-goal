"""Headless envelope: the canonical JSON, and the file it lands in.

(1) Schema parity: the preflight step-4 blocked block and the SKILL.md master block carry
the same five canonical keys (+ conditional reason); no formalize-prefixed key. (2) The
build_headless_envelope adapter routes a formalize RED through the IDENTICAL channel as a
semantic-scan RED, with the formalize verdict never nested. (3) reason is positional blockers[0],
one physical line. (4) the formalize RED is logged. (5) one envelope definition tree-wide.

Then the file-based result: (6) a complete entry point that is EXACTLY the five keys, with
`reason` absent rather than null; (7) both shapes written to <impl-artifacts>/run-result.json,
byte-identical to the stdout emit, with the pre-resolution block skipping the file and still
emitting; (8) every headless terminal's prose routing through the adapter; (9) the documented CI
snippet reading the file rather than the transcript; (10) STABILITY.md agreeing with all of it.
Stdlib + pytest only.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SKILL_ROOT.parents[1]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"
_FINALIZE = _SKILL_ROOT / "references" / "finalize.md"
_INGEST = _SKILL_ROOT / "references" / "ingest-and-scope.md"
_SKILL_MD = _SKILL_ROOT / "SKILL.md"
_HELPER = _SKILL_ROOT / "scripts" / "headless_envelope.py"
_HOW_IT_WORKS = _REPO_ROOT / "docs" / "how-it-works.md"
_STABILITY = _REPO_ROOT / "docs" / "_internal" / "STABILITY.md"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"

CANONICAL = {"status", "skill", "decision_log", "report", "deferred_work"}
STATUS_ENUM = {"complete", "blocked", "complete|blocked"}

_ADAPTER = "scripts/headless_envelope.py"
_RESULT_FILE = "run-result.json"


def _load_helper():
    spec = importlib.util.spec_from_file_location("headless_envelope", _HELPER)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


he = _load_helper()


def _json_blocks(text: str) -> list[str]:
    return re.findall(r"```json\s*(.*?)```", text, re.DOTALL)


def _parse(block: str):
    try:
        return json.loads(block)
    except json.JSONDecodeError:
        return None


def _first_block_after(text: str, heading: str) -> dict:
    after = text[text.index(heading):]
    blocks = _json_blocks(after)
    for b in blocks:
        d = _parse(b)
        if isinstance(d, dict) and "status" in d:
            return d
    raise AssertionError(f"no status-bearing json block after {heading!r}")


def _canonical_block(text: str) -> dict:
    for b in _json_blocks(text):
        d = _parse(b)
        if isinstance(d, dict) and (set(d) - {"reason"}) == CANONICAL:
            return d
    raise AssertionError("no canonical envelope block found")


# Case 1 ---------------------------------------------------------------------
def test_preflight_blocked_block_has_exact_canonical_keys():
    pre = _first_block_after(_PREFLIGHT.read_text(encoding="utf-8"), "## 4. Hard gate")
    skill = _canonical_block(_SKILL_MD.read_text(encoding="utf-8"))
    assert set(pre.keys()) == CANONICAL | {"reason"}
    assert (set(pre) - {"reason"}) == (set(skill) - {"reason"}) == CANONICAL
    assert not any("formalize" in k for k in pre), "no formalize-prefixed key on the headless surface"


# Case 2 ---------------------------------------------------------------------
def test_formalize_red_routes_through_blocked_envelope(tmp_path):
    log = tmp_path / "dl.md"
    fr5 = {
        "verdict": "blocked",
        "mechanical_gaps": [],
        "judgment_candidates": [
            {"source": "prd.md:42", "kind": "undecided-architecture", "why_machine_cannot_decide": "choose store"}
        ],
        "checks": {},
    }
    env = he.build_headless_envelope(fr5, str(log))
    assert env == {
        "status": "blocked",
        "skill": "ultracode-goal",
        "decision_log": str(log),
        "report": None,
        "deferred_work": None,
        "reason": he._one_line({"source": "prd.md:42", "decision_needed": "choose store"}),
    }
    assert all(v is not fr5 and v != fr5 for v in env.values()), "the formalize verdict must never be an envelope value"

    # anti-vacuous: a SEMANTIC-SCAN red with identical content yields the byte-identical envelope
    sem = [{"source": "prd.md:42", "decision_needed": "choose store", "kind": "undecided-architecture"}]
    env2 = he.build_headless_envelope(sem, str(log))
    assert env2 == env, "formalize and semantic-scan reds share one channel"


# Case 3 ---------------------------------------------------------------------
def test_reason_is_first_red_one_line(tmp_path):
    log = str(tmp_path / "dl.md")
    sem = {"source": "prd.md:10", "decision_needed": "pick auth", "kind": "undecided-product"}
    formal = {"source": "arch.md:7", "decision_needed": "pick store", "kind": "undecided-architecture"}
    assert he.build_headless_envelope([sem, formal], log)["reason"] == he._one_line(sem)
    assert he.build_headless_envelope([formal, sem], log)["reason"] == he._one_line(formal)
    assert he.build_headless_envelope([formal], log)["reason"] == he._one_line(formal)
    # one physical line even from a multi-line decision_needed
    multi = {"source": "x.md:1", "decision_needed": "line1\nline2\nline3"}
    reason = he.build_headless_envelope([multi], log)["reason"]
    assert "\n" not in reason and "line1" in reason and "line3" in reason


# Case 4 ---------------------------------------------------------------------
def test_blocked_envelope_logs_formalize_red(tmp_path):
    log = tmp_path / "dl.md"
    red = {"source": "epic.md:99", "decision_needed": "resolve the undecided NFR threshold"}
    env = he.build_headless_envelope([red], str(log))
    assert env["decision_log"] == str(log)
    assert log.exists()
    body = log.read_text(encoding="utf-8")
    assert "epic.md:99" in body and "resolve the undecided NFR threshold" in body


def test_complete_shaped_mapping_is_rejected_with_no_side_effects(tmp_path):
    """The blocked adapter must refuse a complete-shaped dict, before writing anything.

    Handed one, it read no blockers from it, SYNTHESISED a "formalize verdict is
    unreadable or missing" blocker, appended that fabrication to the decision log,
    and wrote a `blocked` run-result.json over a successful run. Both artifacts
    are what an automator and a resume read, and it happened in the field.
    """
    log = tmp_path / "dl.md"
    log.write_text("# Decision log\n\n- pre-existing line\n", encoding="utf-8")
    impl = tmp_path / "impl"
    impl.mkdir()
    complete_shaped = {
        "status": "complete",
        "skill": "ultracode-goal",
        "decision_log": str(log),
        "report": str(impl / "run-report.md"),
        "deferred_work": None,
    }

    with pytest.raises(ValueError, match="BLOCKED adapter"):
        he.build_headless_envelope(complete_shaped, str(log), impl_artifacts=str(impl))

    # Neither side effect fired.
    assert log.read_text(encoding="utf-8") == "# Decision log\n\n- pre-existing line\n"
    assert not (impl / "run-result.json").exists()


def test_a_genuine_blocker_dict_is_still_accepted(tmp_path):
    """The guard keys on `status == complete`, not on "is a dict"."""
    log = tmp_path / "dl.md"
    verdict = {"verdict": "blocked", "judgment_candidates": [
        {"source": "prd.md:4", "why_machine_cannot_decide": "pick a store", "kind": "undecided"}
    ]}
    env = he.build_headless_envelope(verdict, str(log))
    assert env["status"] == "blocked"
    assert "pick a store" in env["reason"]


def test_an_escalated_blocked_envelope_can_carry_its_report(tmp_path):
    """A blocked exit is not always artifact-less.

    An escalated run reaches Stage 6 and DOES produce a run report and a gate
    trail, but the adapter hard-coded `report: None` with no parameter to supply
    one - so the envelope under-reported what was on disk for the one run most
    worth reading.
    """
    log = tmp_path / "dl.md"
    env = he.build_headless_envelope(
        [{"source": "gate", "decision_needed": "story escalated"}],
        str(log),
        report=tmp_path / "run-report.md",
        deferred_work=tmp_path / "deferred.md",
    )
    assert env["status"] == "blocked"
    assert env["report"] == str(tmp_path / "run-report.md")
    assert env["deferred_work"] == str(tmp_path / "deferred.md")
    assert list(env) == [*he.CANONICAL_KEYS, "reason"], "key order and the five-key set are unchanged"


def test_an_early_block_still_reports_null_artifacts(tmp_path):
    """Omitting the new kwargs keeps the pre-existing shape exactly."""
    env = he.build_headless_envelope(
        [{"source": "preflight", "decision_needed": "unresolvable secret"}], str(tmp_path / "dl.md")
    )
    assert env["report"] is None
    assert env["deferred_work"] is None


def test_the_adapter_injects_no_em_dash_into_its_output(tmp_path):
    """The reason line and the log heading carry only bytes the caller supplied.

    `_one_line` joined source and decision_needed with U+2014, so both the stdout
    envelope and the run-result.json written beside it carried a character the
    caller never wrote. Harmless here, red in any project that lints its tracked
    run artifacts for it.
    """
    log = tmp_path / "dl.md"
    env = he.build_headless_envelope(
        [{"source": "formalize", "decision_needed": "pick a store"}], str(log)
    )
    assert "—" not in env["reason"]
    assert "—" not in log.read_text(encoding="utf-8")


def test_blocked_alias_names_the_same_adapter():
    assert he.build_blocked_envelope is he.build_headless_envelope


def test_run_result_stays_byte_identical_with_the_new_kwargs(tmp_path):
    """The single-serialization property must hold on the escalated shape too.

    The existing byte-identity test covers a blocked envelope with null
    artifacts; `report=`/`deferred_work=` add two populated string fields, which
    is exactly where a second `json.dumps` with different kwargs would diverge.
    """
    impl = tmp_path / "impl"
    impl.mkdir()
    env = he.build_headless_envelope(
        [{"source": "gate", "decision_needed": "story escalated"}],
        str(tmp_path / "dl.md"),
        impl_artifacts=str(impl),
        report=tmp_path / "run-report.md",
        deferred_work=tmp_path / "deferred.md",
    )
    on_disk = (impl / "run-result.json").read_text(encoding="utf-8")
    assert on_disk == he.render_envelope(env)
    assert json.loads(on_disk)["report"] == str(tmp_path / "run-report.md")


# Case 5 ---------------------------------------------------------------------
def test_single_envelope_definition():
    canon_keysets = []
    statuses = []
    for md in _SKILL_ROOT.rglob("*.md"):
        if ".analysis" in md.parts:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # deliberate non-UTF8 / unreadable fixtures are not envelope docs
        for block in _json_blocks(text):
            d = _parse(block)
            if not isinstance(d, dict):
                continue
            if (set(d) - {"reason"}) == CANONICAL:
                canon_keysets.append(frozenset(set(d) - {"reason"}))
            if "status" in d:
                statuses.append(d["status"])
    assert canon_keysets, "expected at least one canonical envelope block"
    assert len(set(canon_keysets)) == 1, "all canonical envelope blocks must share one key set"
    for s in statuses:
        assert s in STATUS_ENUM, f"non-canonical headless status string: {s!r}"


# --- the file-based result -------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+", _norm(text))


def _section(text: str, heading: str, *, stop_at_sub: bool = False) -> str:
    """Body of a `## <heading>` section, up to the next `## ` (or `### ` too)."""
    stop = r"(?=^#{2,3} |\Z)" if stop_at_sub else r"(?=^## |\Z)"
    m = re.search(r"^#{2,3} " + re.escape(heading) + r".*?" + stop, text, re.MULTILINE | re.DOTALL)
    assert m is not None, f"section {heading!r} not found"
    return m.group(0)


# Case 6: the complete entry point ------------------------------------------
def test_complete_envelope_is_exactly_the_five_canonical_keys(tmp_path):
    env = he.build_complete_envelope(
        tmp_path / "dl.md",
        report=tmp_path / "run-report.md",
        deferred_work=tmp_path / "deferred-work.md",
    )
    # SET-EQUALITY, not subset: the natural "reuse the blocked builder and null out
    # reason" implementation returns SIX keys and passes a subset check.
    assert set(env) == CANONICAL, f"complete envelope drifted: {sorted(set(env) ^ CANONICAL)}"
    assert "reason" not in env, "a complete emit OMITS reason; it is not present-and-null"
    assert env["status"] == "complete"
    assert env["skill"] == "ultracode-goal"
    # positive control on the values the mutation would leave intact, so the red above
    # is attributable to the reason key alone
    assert env["decision_log"] == str(tmp_path / "dl.md")
    assert env["report"] == str(tmp_path / "run-report.md")
    assert env["deferred_work"] == str(tmp_path / "deferred-work.md")
    # an unproduced artifact is null, never absent: the five stay KeyError-safe
    bare = he.build_complete_envelope(tmp_path / "dl.md")
    assert set(bare) == CANONICAL
    assert bare["report"] is None and bare["deferred_work"] is None


# Case 7: byte-identity between the file and the stdout emit -----------------
def _file_matches_stdout(path: Path, envelope: dict) -> bool:
    """AC helper: are the file's bytes EXACTLY the adapter's serialization of `envelope`?"""
    return path.read_bytes() == he.render_envelope(envelope).encode("utf-8")


def test_run_result_file_is_byte_identical_to_stdout_envelope(tmp_path):
    for name, build in (
        ("complete", lambda impl: he.build_complete_envelope(tmp_path / "dl.md", impl_artifacts=impl)),
        (
            "blocked",
            lambda impl: he.build_headless_envelope(
                [{"source": "prd.md:42", "decision_needed": "choose store"}],
                tmp_path / "dl.md",
                impl_artifacts=impl,
            ),
        ),
    ):
        impl = tmp_path / name / "impl"
        impl.mkdir(parents=True)
        env = build(impl)

        # exact path: the basename, directly in impl-artifacts. No run-id suffix, no subdir.
        written = sorted(p.relative_to(impl).as_posix() for p in impl.rglob("*.json"))
        assert written == ["run-result.json"], f"{name}: unexpected result artifacts {written}"

        path = impl / "run-result.json"
        # BYTES, not a re-parse: an indent/separator/key-order divergence between the two
        # serializations reds here while `json.loads(...) == env` would stay green.
        assert _file_matches_stdout(path, env), (
            f"{name}: file bytes {path.read_bytes()!r} != serialized envelope "
            f"{he.render_envelope(env).encode()!r}"
        )
        # positive control: the file is also semantically the envelope, so the byte
        # assertion above is not passing over a file that is wrong in both ways.
        assert json.loads(path.read_text(encoding="utf-8")) == env


def test_pre_resolution_block_skips_file_and_still_returns_envelope(tmp_path):
    """The "not a BMAD project" stop fires before impl-artifacts can resolve."""
    env = he.build_headless_envelope(
        [{"decision_needed": "not a BMAD project"}], tmp_path / "dl.md", impl_artifacts=None
    )
    # the emit is NOT skipped: skipping the file by returning early or raising would red here
    assert set(env) == CANONICAL | {"reason"}, "the pre-resolution block still emits the full shape"
    assert env["status"] == "blocked"
    assert env["reason"] == "not a BMAD project"
    assert env["report"] is None and env["deferred_work"] is None
    # nothing written ANYWHERE, not merely nothing at the expected path: a skip that
    # relocates the file reds too.
    assert list(tmp_path.rglob("run-result.json")) == []

    # the same call WITH a resolved path does write, so the assertion above is a real
    # skip rather than a write path that never works in this test's conditions.
    impl = tmp_path / "impl"
    impl.mkdir()
    he.build_headless_envelope([{"decision_needed": "x"}], tmp_path / "dl.md", impl_artifacts=impl)
    assert (impl / "run-result.json").is_file()


def test_unresolved_placeholder_is_treated_as_unresolved(tmp_path):
    """An unsubstituted `{workflow.…}` scalar is the same unresolved case as None."""
    he.build_complete_envelope(
        tmp_path / "dl.md", impl_artifacts="{workflow.implementation_artifacts}"
    )
    assert list(tmp_path.rglob(_RESULT_FILE)) == []
    assert not Path("{workflow.implementation_artifacts}").exists()


def test_unwritable_target_logs_and_still_returns_the_envelope(tmp_path):
    """The write is best-effort: a terminal emit must never die on an unwritable dir."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    log = tmp_path / "dl.md"
    env = he.build_complete_envelope(log, impl_artifacts=blocker / "impl")
    assert set(env) == CANONICAL and env["status"] == "complete"
    assert "run-result-write-failed" in log.read_text(encoding="utf-8")


# Case 8 (twin for byte-identity): a file missing `reason` is not the envelope
def test_blocked_file_without_reason_fails_the_byte_identity_check(tmp_path):
    impl = tmp_path / "impl"
    impl.mkdir()
    env = he.build_headless_envelope(
        [{"source": "epic.md:7", "decision_needed": "resolve the NFR threshold"}],
        tmp_path / "dl.md",
        impl_artifacts=impl,
    )
    path = impl / _RESULT_FILE
    assert _file_matches_stdout(path, env), "control: the real file matches before mutation"

    stripped = {k: v for k, v in env.items() if k != "reason"}
    path.write_text(he.render_envelope(stripped), encoding="utf-8")
    assert not _file_matches_stdout(path, env), (
        "a blocked run-result.json that omits `reason` must fail the byte-identity check: "
        "blocked is SIX keys on disk, exactly as on stdout"
    )


def test_reason_stripped_file_differs_from_stdout_only_by_reason(tmp_path):
    """Twin-integrity for the test above: it must red for the RIGHT reason.

    An emptied or non-JSON run-result.json also fails a byte comparison while proving
    nothing about `reason`, so pin that the stripped file is otherwise intact.
    """
    impl = tmp_path / "impl"
    impl.mkdir()
    env = he.build_headless_envelope(
        [{"source": "epic.md:7", "decision_needed": "resolve the NFR threshold"}],
        tmp_path / "dl.md",
        impl_artifacts=impl,
    )
    path = impl / _RESULT_FILE
    stripped = {k: v for k, v in env.items() if k != "reason"}
    path.write_text(he.render_envelope(stripped), encoding="utf-8")

    on_disk = json.loads(path.read_text(encoding="utf-8"))  # still parses as JSON
    assert set(on_disk) == CANONICAL, "the stripped file must still carry all five canonical keys"
    for key in CANONICAL:
        assert on_disk[key] == env[key], f"{key} diverged; the only difference must be `reason`"
    assert set(env) - set(on_disk) == {"reason"}


def test_blocked_envelope_never_carries_an_empty_reason(tmp_path):
    """An empty blocker list must not yield a causeless blocked envelope.

    `fr5_blockers` returns [] for a non-blocking verdict, so a `ready` verdict adapted
    through the blocked builder used to emit a valid-looking blocked envelope with
    reason "" and write nothing to the log: a silent headless block, which is exactly
    what this module's contract says cannot happen.
    """
    for source in ([], {"verdict": "ready"}, {"verdict": "remediable"}):
        log = tmp_path / f"dl-{id(source)}.md"
        env = he.build_headless_envelope(source, log)
        assert env["reason"].strip(), f"{source!r} produced a blocked envelope with no cause"
        assert log.exists() and env["reason"].split()[0] in log.read_text(encoding="utf-8"), (
            "a blocked envelope's cause is always written to the decision log"
        )
    # control: a real blocker still renders positionally, unchanged by the fallback
    red = {"source": "prd.md:1", "decision_needed": "pick auth"}
    assert he.build_headless_envelope([red], tmp_path / "c.md")["reason"] == he._one_line(red)


# Case 9: every headless terminal routes through the adapter -----------------
_WRITE_VERB = re.compile(r"\bwrit(?:e|es|ten|er)\b", re.IGNORECASE)


def _adapter_routing_gaps(section: str, *, require_both_shapes: bool = False) -> list[str]:
    """What this terminal's prose is missing to route through the adapter.

    Returns [] when the section names the adapter as the WRITER of run-result.json in
    one sentence (naming both nearby but never connecting them is the drift this
    catches), plus, for finalize, both shape entry points.
    """
    norm = _norm(section)
    gaps = []
    if _ADAPTER not in norm:
        gaps.append("adapter not named")
    if _RESULT_FILE not in norm:
        gaps.append("run-result.json not named")
    if not any(
        _ADAPTER in s and _RESULT_FILE in s and _WRITE_VERB.search(s) for s in _sentences(section)
    ):
        gaps.append("the adapter is not named as the writer of run-result.json")
    if require_both_shapes:
        for entry in ("build_complete_envelope", "build_headless_envelope"):
            if entry not in norm:
                gaps.append(f"{entry} not named")
    return gaps


def test_every_headless_terminal_routes_through_the_adapter():
    finalize = _section(_FINALIZE.read_text(encoding="utf-8"), "Headless output")
    assert _adapter_routing_gaps(finalize, require_both_shapes=True) == [], (
        "finalize's Headless output must route BOTH emits through the adapter and name the file"
    )
    # and it no longer tells the model to hand-compose the JSON
    assert not re.search(r"compose the final JSON", finalize), (
        "finalize must not instruct hand-composing the final JSON"
    )
    # headless-only, so an attended run leaves no stale result behind
    assert re.search(r"attended run writes no", finalize, re.IGNORECASE)

    preflight = _section(_PREFLIGHT.read_text(encoding="utf-8"), "4. Hard gate")
    assert _adapter_routing_gaps(preflight) == [], (
        "preflight's hard gate must name the adapter as the writer of the result file"
    )

    ingest = _INGEST.read_text(encoding="utf-8")
    # the three blocked exits, located by their reason string, never by line number
    for reason, expects_file in (
        ("not a BMAD project", False),
        ("epic already complete", True),
        ("epic unresolved", True),
    ):
        hits = [s for s in _sentences(ingest) if reason in s]
        assert hits, f"no sentence carries the {reason!r} exit"
        sentence = next((s for s in hits if _ADAPTER in s), None)
        assert sentence is not None, f"the {reason!r} exit does not name the adapter"
        if expects_file:
            assert _RESULT_FILE in sentence and _WRITE_VERB.search(sentence), (
                f"the {reason!r} exit must name the adapter as writing the result file"
            )

    # the pre-resolution exit states the file is SKIPPED there
    first_touch = _section(ingest, "First-touch reality check")
    assert re.search(
        r"writes no `?run-result\.json`?|no `?run-result\.json`? is written", first_touch, re.IGNORECASE
    ), "the not-a-BMAD-project exit must state that the result file is skipped"
    assert re.search(r"sole output", first_touch, re.IGNORECASE), (
        "and that the stdout envelope is the sole output there"
    )


def test_pre_edit_finalize_section_fails_adapter_routing_assertion():
    """Twin: the verbatim pre-edit `## Headless output`, which hand-composed the JSON."""
    fixture = _FIXTURES / "finalize_headless_output_hand_composed.md"
    pre_edit = fixture.read_text(encoding="utf-8")

    gaps = _adapter_routing_gaps(pre_edit, require_both_shapes=True)
    assert "run-result.json not named" in gaps and "build_complete_envelope not named" in gaps, (
        f"the pre-edit section must FAIL adapter routing, got gaps={gaps}"
    )
    assert "the adapter is not named as the writer of run-result.json" in gaps

    # Twin integrity: the red above must be the missing routing, not a mangled fixture.
    # The pre-edit section carries ONE fenced envelope block (the complete emit; the
    # blocked shape is described in prose, not fenced) and the five-key sentence.
    blocks = [_parse(b) for b in _json_blocks(pre_edit)]
    canonical = [d for d in blocks if isinstance(d, dict) and set(d) == CANONICAL]
    assert len(canonical) == len(blocks) == 1, (
        f"fixture lost its fenced envelope block: {blocks}"
    )
    assert canonical[0]["status"] == "complete" and canonical[0]["skill"] == "ultracode-goal"
    assert "**same five-canonical-key shape every headless exit point honors**" in pre_edit
    assert "compose the final JSON" in pre_edit, "the fixture must keep the hand-compose wording"

    # and it is genuinely the PRE-edit text: the shipped section has moved on
    assert pre_edit not in _FINALIZE.read_text(encoding="utf-8")


# Case 10: the documented CI snippet ----------------------------------------
def _ci_snippet() -> str:
    section = _section(_HOW_IT_WORKS.read_text(encoding="utf-8"), "Headless contract")
    blocks = re.findall(r"```bash\s*(.*?)```", section, re.DOTALL)
    assert blocks, "the Headless contract section must carry a CI snippet"
    return blocks[0]


def test_documented_ci_snippet_reads_the_file_not_the_transcript():
    snippet = _ci_snippet()

    # (a) the primary read is the file
    assert _RESULT_FILE in snippet, "the snippet must read run-result.json"
    assert re.search(r"result=.*" + re.escape(_RESULT_FILE), snippet), (
        "run-result.json must be the snippet's primary read, not an aside"
    )
    assert snippet.index(_RESULT_FILE) < snippet.index("$run_output"), (
        "the file is read first; stdout is the fallback"
    )

    # (b) no transcript scraping as the status source, in EITHER branch. Independent of
    # (a): a snippet that merely mentions run-result.json while grepping stdout for the
    # verdict passes (a) and must red here.
    for tool in ("grep", "tail", "sed", "awk"):
        assert not re.search(r"\b" + tool + r"\b", snippet), (
            f"the snippet scrapes output with {tool}; the verdict comes from parsed JSON"
        )

    # (c) an absent file plus a parseable blocked envelope on stdout is a VALID blocked
    # terminal, not a harness error
    assert "else" in snippet, "the snippet must carry a fallback branch"
    fallback = snippet[snippet.index("else"):]
    assert re.search(r"valid blocked terminal", fallback, re.IGNORECASE), (
        "the fallback must state that a missing file with a parseable envelope is a valid "
        "blocked terminal"
    )
    assert "fromjson" in fallback, "the fallback parses stdout as JSON rather than scraping it"
    # blocked is a distinct exit from an unparseable one
    assert re.search(r"blocked\)", snippet) and re.search(r"complete\)", snippet), (
        "the snippet must branch on the status vocabulary"
    )


# Case 11: STABILITY.md -----------------------------------------------------
def test_stability_enumerates_run_result_json_as_a_contract_path():
    text = _STABILITY.read_text(encoding="utf-8")

    public = _section(text, "Public contract")
    assert _RESULT_FILE in public, "run-result.json must be enumerated in the public contract"
    # sharper: it is its own contract subsection, not a passing mention in another one
    result_section = _section(text, "The headless result file", stop_at_sub=True)
    assert _RESULT_FILE in result_section
    assert "{workflow.implementation_artifacts}" in result_section, (
        "the contract path must be pinned to the impl-artifacts scalar"
    )

    # and the @internal section does not sweep it back up
    internal = _section(text, "@internal: not covered")
    bullet = next((b for b in internal.split("\n- ") if "_bmad-output/" in b), None)
    assert bullet is not None, "the @internal `_bmad-output/` bullet is missing"
    assert _RESULT_FILE in bullet, (
        "the @internal `_bmad-output/` bullet sweeps run-result.json into the uncovered set; "
        "it must except it, or the document declares the path contractual and internal at once"
    )
    assert re.search(r"exception|except", bullet, re.IGNORECASE), (
        "run-result.json must be named in that bullet as an EXCEPTION, not just mentioned"
    )
    # the rest of the layout stays internal: this is an exception, not a repeal
    assert "run-status.json" in bullet and "run-status.json" not in public


def test_stability_headless_block_matches_the_omit_reason_contract():
    section = _section(
        _STABILITY.read_text(encoding="utf-8"),
        "The headless five-key JSON emit shape",
        stop_at_sub=True,
    )
    block = next(
        (d for b in _json_blocks(section) if isinstance(d := _parse(b), dict) and "status" in d),
        None,
    )
    assert block is not None, "the emit-shape section must carry a fenced envelope block"
    assert (set(block) - {"reason"}) == CANONICAL

    gloss = block["reason"]
    assert re.search(r"\bomitted\b", gloss, re.IGNORECASE), (
        f"the `reason` gloss must state the key is omitted on a complete emit, got {gloss!r}"
    )
    assert re.search(r"complete", gloss, re.IGNORECASE), "and say on WHICH emit it is omitted"
    assert not re.search(r"else:?\s*`?null`?", gloss, re.IGNORECASE), (
        f"the `reason` gloss still says it is null on a complete emit: {gloss!r}"
    )
    # the block agrees with the code, which is the drift this closes
    assert "reason" not in he.build_complete_envelope("/tmp/dl.md")
