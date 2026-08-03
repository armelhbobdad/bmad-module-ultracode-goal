#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""The artifact-resolution property, over a generated space of directories.

Run: uv run --with pytest pytest scripts/tests/test_artifact_resolution_property.py

WHY THIS FILE EXISTS. Nine separate violations of one property have been found
and fixed by hand across four sessions, each as its own example-based test over
one hand-built directory. Every one of them was the same sentence:

    For any artifact directory and any story id, resolution returns a file named
    for THAT story, or a generically-named file in a directory where every
    artifact is generically named, or nothing at all. It NEVER returns a file
    named for a different story, and never one named for the epic a story
    belongs to.

Enumerating the next hand-built directory catches the tenth violation and not the
eleventh. This file enumerates the SPACE instead: directory layouts are generated
from artifact-name templates crossed with owner ids, and every layout is probed
with every story id, including ids that own nothing anywhere in it.

THE ORACLE IS THIS FILE'S OWN OWNERSHIP MAP, NEVER THE PRODUCTION MATCHER. Each
layout declares which story owns each filename it writes, and the assertions look
the resolved path up in that map. Asking `gate_eval._stem_matches_story` whether
the resolved file belongs to the story would make the test circular: a matcher
that answered "yes" to everything would pass its own test. The only production
knowledge this file reproduces is separator equivalence (`11-6` == `11.6` ==
`11_6`), which is an independent fact about the id spelling and not the rule
under test.

THE PROPERTY IS A SAFETY PROPERTY, SO IT IS NOT ENOUGH ON ITS OWN. "Return None"
satisfies every safety clause above perfectly, and a resolver that resolved
nothing at all would pass this file if safety were all it asserted. The liveness
half is therefore not decoration: a story that DID write its own conventionally
named gate file must still resolve exactly that file, and the sanctioned isolated
single-story directory must still resolve its generic one. Both halves fail the
same build for opposite reasons, which is what makes a green run mean something.

WHAT IS DELIBERATELY NOT HERE. This file asserts only WHICH artifact resolution
picks. Everything about what a gate then MEANS - the gate_status to verdict map,
the production AND of NFR and test-review, the re-loop budget - belongs to
`test_gate_eval.py`, which also keeps the mutation twins that prove the
fail-closed branches are non-vacuous. Those tests are not made redundant by this
one; they answer a different question about the same code.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


gate_eval = _load("gate_eval", SCRIPTS / "gate_eval.py")
gate_trail = _load("gate_trail", SCRIPTS / "gate_trail.py")


# ---------------------------------------------------------------------------
# the generated space
# ---------------------------------------------------------------------------

# Artifact filename templates this module and TEA actually write, each with the
# generic spelling used when a run's output is not named per story.
# `traceability-matrix` is TEA's own default trace-report filename
# (bmad-testarch-trace writes it), which is why it is in this table and not only
# the module's shorter `trace`.
TEMPLATES: list[tuple[str, str, bool]] = [
    # (per-story template, generic spelling, declares itself a trace report)
    ("trace-{id}.md", "trace.md", True),
    ("traceability-matrix-{id}.md", "traceability-matrix.md", True),
    ("nfr-assessment-{id}.md", "nfr-assessment.md", False),
    ("gate-decision-{id}.json", "gate-decision.json", False),
    ("e2e-trace-summary-{id}.json", "e2e-trace-summary.json", False),
]

MD_TEMPLATES = [t for t in TEMPLATES if t[0].endswith(".md")]
JSON_TEMPLATES = [t for t in TEMPLATES if t[0].endswith(".json")]

# Owner ids written INTO layouts. Deliberately mixed: a plain child id, a second
# child of the same epic, the bare EPIC id (the roll-up, whose artifacts a child
# story must never resolve), an alphanumeric split id, a slugged id, and an id
# whose components are a suffix-collision trap with another (`11-6` / `1-11-6`).
OWNERS = ["4-1", "4-2", "92", "92-0a", "11-6", "7-3-some-title-slug"]

# Story ids RESOLUTION IS PROBED WITH. Every owner above, plus ids that own
# nothing in any generated layout - the never-driven stories whose resolution
# must come back empty rather than borrowing a neighbour's verdict.
#
# ONE AMBIGUITY IS DELIBERATELY KEPT OUT OF THIS LIST rather than resolved here.
# The module treats a slugged id as the same story as its bare numeric prefix
# when that prefix still carries an epic AND a story component
# (`gate_trail._prefix_scope`: `4-2-some-slug` -> `4-2`), so probing `4-2-some-slug`
# against a directory owned by `4-2` asks a question the module answers "same
# story" and this file has no independent standing to answer differently. What
# the module does NOT pin anywhere is which spelling is canonical - the sprint
# key, the filename, or the `--story` argument - and that gap is a documentation
# defect, not a resolution defect. So every never-driven probe below is one whose
# prefix collapses to no owner at all, and the slug question is left to the
# reference that should have pinned it.
NEVER_DRIVEN = [
    "9-9",
    # Prefix collapses to the bare epic `92`, which is a DIFFERENT artifact set
    # (the roll-up), never a shorter spelling of this story.
    "92-7f-never-driven",
    "1-11-6",
    "4-01",
    "116",
    "8-8-some-title-slug",
]
PROBES = OWNERS + NEVER_DRIVEN

PASS_GATE = {
    "gate_status": "PASS",
    "p0_status": "MET",
    "p1_status": "MET",
    "overall_status": "MET",
    "gate_criteria": {"p0_status": "MET", "p1_status": "MET", "overall_status": "MET"},
}


class Layout:
    """A directory of artifacts plus the ground truth of who owns each file.

    `files` maps filename -> owner story id, with None meaning "generically
    named, so owned by no story in particular".
    """

    def __init__(self, name: str, files: dict[str, str | None], hints: dict[str, str] | None = None):
        self.name = name
        self.files = files
        self.hints = hints or {}

    @property
    def all_generic(self) -> bool:
        return all(owner is None for owner in self.files.values())

    def owners(self) -> set[str]:
        return {o for o in self.files.values() if o is not None}

    def build(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        for filename, owner in self.files.items():
            path = root / filename
            if filename.endswith(".json"):
                path.write_text(json.dumps(PASS_GATE), encoding="utf-8")
                continue
            declares = self._declares_trace(filename, owner)
            front = ["---"]
            if declares:
                front.append("workflowType: trace")
            if filename in self.hints:
                front.append(f"gateDecisionFile: {self.hints[filename]}")
            front.append("---")
            # The criterion id is spelled without the house-forbidden `AC-<n>`
            # form: `test_gate_trail.py::test_shipped_surfaces_cite_no_plan_identifiers`
            # bans plan identifiers on shipped surfaces, and this file is now in
            # that test's list. Resolution never reads the table body anyway.
            body = "\n| Criterion | Verification | Status |\n| --- | --- | --- |\n| one | a named test | PASS |\n"
            path.write_text("\n".join(front) + "\n" + body, encoding="utf-8")
        return root

    @staticmethod
    def _declares_trace(filename: str, owner: str | None) -> bool:
        for per, generic, is_trace in TEMPLATES:
            if filename == generic or (owner is not None and filename == per.format(id=owner)):
                return is_trace
        return False

    def __repr__(self) -> str:  # pragma: no cover - pytest id only
        return self.name


def _norm(story: str) -> str:
    """Separator-insensitive spelling of an id: `11.6` and `11_6` are `11-6`.

    This is the ONLY piece of id knowledge the oracle reproduces, and it is not
    the rule under test - it is an equivalence between spellings of one id.
    """
    return story.replace(".", "-").replace("_", "-")


def _layouts() -> list[Layout]:
    """Every generated directory shape, adversarial by construction."""
    out: list[Layout] = []

    # 1. One story's own artifacts, every md/json pairing. The liveness base case
    #    and the shape a well-behaved per-story run produces.
    for (md, _, _), (js, _, _) in itertools.product(MD_TEMPLATES, JSON_TEMPLATES):
        for owner in OWNERS:
            out.append(
                Layout(
                    f"own[{md.split('-{')[0]}+{js.split('-{')[0]}]@{owner}",
                    {md.format(id=owner): owner, js.format(id=owner): owner},
                )
            )

    # 2. Two stories sharing one directory, only the FIRST holding a gate file.
    #    The shared multi-story dir --story exists for: the second story and every
    #    never-driven probe must not resolve the first story's gate.
    for md, _, _ in MD_TEMPLATES:
        for js, _, _ in JSON_TEMPLATES:
            for a, b in itertools.combinations(OWNERS, 2):
                out.append(
                    Layout(
                        f"shared[{md.split('-{')[0]}]@{a}+{b}",
                        {
                            md.format(id=a): a,
                            js.format(id=a): a,
                            md.format(id=b): b,
                        },
                    )
                )

    # 3. A per-story artifact beside a GENERIC one. The generic file belongs to no
    #    story, so no story may resolve it here - this is not the isolated dir.
    for md, md_generic, _ in MD_TEMPLATES:
        for js, js_generic, _ in JSON_TEMPLATES:
            for owner in OWNERS:
                out.append(
                    Layout(
                        f"mixed[{md.split('-{')[0]}@{owner}+{js_generic}]",
                        {md.format(id=owner): owner, js_generic: None},
                    )
                )
                out.append(
                    Layout(
                        f"mixed[{md_generic}+{js.split('-{')[0]}@{owner}]",
                        {md_generic: None, js.format(id=owner): owner},
                    )
                )

    # 3b. TWO JSON artifacts in one directory - a per-story one beside a generic
    #     one. Every family above pairs at most ONE json with markdown, so the
    #     space could not express "the story owns its own summary AND a shared
    #     gate-decision.json is sitting here". That is the shape where a guard
    #     which merely SUPPRESSES a fail-closed return, without steering
    #     resolution to the artifact that justified suppressing it, falls through
    #     to the run-wide file: measured at PASS -> advance for a story whose own
    #     summary said CONCERNS.
    for js_a, _js_a_generic, _ in JSON_TEMPLATES:
        for js_b, js_b_generic, _ in JSON_TEMPLATES:
            if js_a == js_b:
                continue
            for owner in ("4-1", "92-0a"):
                out.append(
                    Layout(
                        f"two-json[{js_a.split('-{')[0]}@{owner}+{js_b_generic}]",
                        {js_a.format(id=owner): owner, js_b_generic: None},
                    )
                )
                out.append(
                    Layout(
                        f"two-json-neighbour[{js_a.split('-{')[0]}@{owner}+{js_b_generic}]",
                        {
                            js_a.format(id=owner): owner,
                            js_b_generic: None,
                            "trace-9-9.md": "9-9",
                        },
                    )
                )

    # 4. The sanctioned isolated single-story directory: every candidate generic.
    #    Resolution is DOCUMENTED to work here, so this is liveness, not safety.
    for (_, md_generic, _), (_, js_generic, _) in itertools.product(MD_TEMPLATES, JSON_TEMPLATES):
        out.append(Layout(f"isolated[{md_generic}+{js_generic}]", {md_generic: None, js_generic: None}))

    # 5. A story's own trace report pointing its gateDecisionFile hint somewhere
    #    it must not be followed: a NEIGHBOUR's gate file, a relative path that
    #    escapes the artifact directory, and an absolute path off it entirely.
    for md, _, is_trace in MD_TEMPLATES:
        if not is_trace:
            continue
        out.append(
            Layout(
                f"hint-neighbour[{md.split('-{')[0]}]",
                {
                    md.format(id="4-1"): "4-1",
                    md.format(id="9-9-neighbour"): "9-9-neighbour",
                    "gate-decision-9-9-neighbour.json": "9-9-neighbour",
                },
                hints={md.format(id="4-1"): "gate-decision-9-9-neighbour.json"},
            )
        )
        out.append(
            Layout(
                f"hint-escape[{md.split('-{')[0]}]",
                {md.format(id="4-1"): "4-1", "gate-decision-4-1.json": "4-1"},
                hints={md.format(id="4-1"): "../outside/gate-decision.json"},
            )
        )
        # The isolated single-story directory, hinted. LIVENESS: the generic gate
        # file is this story's, and following the hint is correct.
        out.append(
            Layout(
                f"hint-generic-isolated[{md.split('-{')[0]}]",
                {md.format(id="4-1"): "4-1", "gate-decision.json": None},
                hints={md.format(id="4-1"): "gate-decision.json"},
            )
        )
        # The SAME hint from two stories' reports at one shared generic gate file.
        # SAFETY: neither story may take it, because it cannot be both stories'.
        out.append(
            Layout(
                f"hint-generic-shared[{md.split('-{')[0]}]",
                {
                    md.format(id="4-1"): "4-1",
                    md.format(id="4-2"): "4-2",
                    "gate-decision.json": None,
                },
                hints={
                    md.format(id="4-1"): "gate-decision.json",
                    md.format(id="4-2"): "gate-decision.json",
                },
            )
        )

    # 6. The epic roll-up's artifacts alone in the directory. Every CHILD story of
    #    that epic is a never-driven story here.
    for md, _, _ in MD_TEMPLATES:
        for js, _, _ in JSON_TEMPLATES:
            out.append(
                Layout(
                    f"rollup-only[{md.split('-{')[0]}]",
                    {md.format(id="92"): "92", js.format(id="92"): "92"},
                )
            )

    return out


LAYOUTS = _layouts()


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict[str, Path]:
    """Every layout materialized once; the probe loop reads them read-only."""
    root = tmp_path_factory.mktemp("resolution-space")

    # The escape hint is the literal `../outside/gate-decision.json`, relative to
    # a layout directory `root/L####`, so it points at `root/outside`. Planting
    # the target anywhere else (an `L####-outside` sibling, say) leaves the hint
    # aimed at a file that does not exist, and then EVERY build refuses it for
    # the wrong reason - the layout would go green with the containment check
    # deleted. Written once, where the hint actually points.
    outside = root / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "gate-decision.json").write_text(json.dumps(PASS_GATE), encoding="utf-8")

    out: dict[str, Path] = {}
    for index, layout in enumerate(LAYOUTS):
        # Index-keyed so two layouts that stringify alike cannot share a directory.
        out[f"L{index:04d}"] = layout.build(root / f"L{index:04d}")
    return out


# ---------------------------------------------------------------------------
# the property
# ---------------------------------------------------------------------------


def _assert_owned_or_absent(resolved, story: str, layout: Layout, directory: Path, surface: str) -> None:
    """The safety half, at the resolver level."""
    if resolved is None:
        return
    resolved = Path(resolved)
    where = f"{surface} in {layout.name} probed with {story!r}"

    # A resolved path must name a file this layout actually wrote, inside the
    # artifact directory. Anything else means resolution followed something out
    # of the directory it was pointed at.
    try:
        inside = resolved.resolve().relative_to(directory.resolve())
    except ValueError:
        pytest.fail(f"{where}: resolved OUTSIDE the artifact directory -> {resolved}")
    assert inside.parent == Path("."), f"{where}: resolved below the artifact directory -> {inside}"

    if not resolved.exists():
        # Naming a file that is not there is how the module signals "the
        # conventional path, which happens to be absent"; it carries no verdict.
        return

    assert resolved.name in layout.files, f"{where}: resolved a file no layout wrote -> {resolved.name}"
    owner = layout.files[resolved.name]

    if owner is None:
        # A generically-named file carries no id, so the question it raises is
        # not "does this directory name anything per story" but "could this file
        # be SOMEONE ELSE'S". Those differ on exactly the directory
        # `references/gate.md` tells an operator to build - one story's artifacts
        # isolated into a fresh dir - where a TEA build that names the trace
        # report per story and the gate decision generically produces
        # `trace-<id>.md` + `gate-decision.json`. No other story is present, so
        # the unnamed file provably belongs to the story being gated. Requiring
        # the whole directory to be generic escalated that story instead.
        others = sorted(o for o in layout.owners() if _norm(o) != _norm(story))
        assert not others, (
            f"{where}: resolved the generically-named {resolved.name}, which belongs to no story, "
            f"in a directory that also holds artifacts owned by {others}"
        )
        return

    assert _norm(owner) == _norm(story), (
        f"{where}: resolved {resolved.name}, which is story {owner!r}'s artifact, "
        f"as story {story!r}'s"
    )


@pytest.mark.parametrize("index", range(len(LAYOUTS)), ids=[l.name for l in LAYOUTS])
def test_resolution_never_returns_another_storys_artifact(index, built):
    """SAFETY: no resolution surface hands a story an artifact that is not its own."""
    layout = LAYOUTS[index]
    directory = built[f"L{index:04d}"]

    for story in PROBES:
        _assert_owned_or_absent(
            gate_eval._resolve_gate_file(directory, story), story, layout, directory, "gate_eval._resolve_gate_file"
        )
        _assert_owned_or_absent(
            gate_eval._per_story_slim(directory, story), story, layout, directory, "gate_eval._per_story_slim"
        )
        _assert_owned_or_absent(
            gate_trail.trace_report_path(directory, story), story, layout, directory, "gate_trail.trace_report_path"
        )


@pytest.mark.parametrize("index", range(len(LAYOUTS)), ids=[l.name for l in LAYOUTS])
def test_a_story_that_wrote_nothing_here_gets_no_verdict(index, built):
    """SAFETY, end to end: a never-driven story's VERDICT is absent, not a neighbour's.

    The resolver-level property above can hold while the verdict still leaks,
    because both readers have a summary fallback that is reached by a different
    path than the gate file. This asserts on what the run actually acts on.
    """
    layout = LAYOUTS[index]
    if layout.all_generic:
        # The isolated single-story directory is DOCUMENTED to answer any story:
        # its files provably belong to the one story being driven.
        return
    directory = built[f"L{index:04d}"]

    for story in NEVER_DRIVEN:
        if any(_norm(story) == _norm(o) for o in layout.owners()):
            continue

        reasons: list[str] = []
        gate = gate_eval.load_gate(directory, reasons, story)
        assert gate["gate_status"] == "NOT_EVALUATED", (
            f"gate_eval.load_gate in {layout.name} gave never-driven story {story!r} "
            f"a {gate['gate_status']} verdict; reasons={reasons}"
        )

        status, source = gate_trail.gate_status_for(directory, story)
        assert status is None, (
            f"gate_trail.gate_status_for in {layout.name} rendered never-driven story "
            f"{story!r} as {status!r}, read from {source!r}"
        )

        assert gate_trail.trace_report_path(directory, story) is None, (
            f"gate_trail.trace_report_path in {layout.name} gave never-driven story "
            f"{story!r} a trace report it never wrote"
        )


@pytest.mark.parametrize("index", range(len(LAYOUTS)), ids=[l.name for l in LAYOUTS])
def test_a_story_still_resolves_the_gate_file_it_did_write(index, built):
    """LIVENESS: safety is satisfiable by resolving nothing, so pin the positive case.

    Without this, deleting every fallback in both readers would leave the two
    safety tests above perfectly green.
    """
    layout = LAYOUTS[index]
    directory = built[f"L{index:04d}"]

    for story in OWNERS:
        own_slim = f"gate-decision-{story}.json"
        if layout.files.get(own_slim) != story:
            continue

        resolved = gate_eval._resolve_gate_file(directory, story)
        assert resolved is not None and resolved.name == own_slim, (
            f"{layout.name}: story {story!r} wrote {own_slim} and resolution returned {resolved}"
        )

        reasons: list[str] = []
        assert gate_eval.load_gate(directory, reasons, story)["gate_status"] == "PASS", (
            f"{layout.name}: story {story!r}'s own PASS did not survive resolution; reasons={reasons}"
        )

        status, _ = gate_trail.gate_status_for(directory, story)
        assert status == "PASS", (
            f"{layout.name}: gate_trail read {status!r} for story {story!r}, which wrote its own PASS"
        )


def test_the_isolated_single_story_directory_still_resolves_its_generic_gate(built):
    """LIVENESS: the documented all-generic dir answers the story being driven."""
    checked = 0
    for index, layout in enumerate(LAYOUTS):
        if not (layout.all_generic and "gate-decision.json" in layout.files):
            continue
        directory = built[f"L{index:04d}"]
        reasons: list[str] = []
        assert gate_eval.load_gate(directory, reasons, "4-1")["gate_status"] == "PASS", (
            f"{layout.name}: the isolated single-story directory stopped resolving; reasons={reasons}"
        )
        checked += 1
    assert checked, "no isolated all-generic layout was generated; the liveness half is vacuous"


@pytest.mark.parametrize(
    "hint",
    [
        "../outside/gate-decision.json",
        "./../outside/gate-decision.json",
        "sub/../../outside/gate-decision.json",
        "nested/gate-decision.json",
        "{ABSOLUTE_OUTSIDE}",
        "",
        ".",
        "..",
    ],
    ids=[
        "parent-escape",
        "dot-parent-escape",
        "round-trip-escape",
        "subdirectory",
        "absolute-outside",
        "empty",
        "dot",
        "dotdot",
    ],
)
def test_a_hint_is_never_followed_outside_the_artifact_directory(tmp_path, hint):
    """CONTAINMENT: --trace-output is the boundary drawn around this run's evidence.

    A hint is a string inside a file the run itself wrote, and it was previously
    followed verbatim - so a relative `..` path, or an ABSOLUTE path naming
    anywhere on disk, was read as the story's verdict. This is parametrized
    rather than folded into the generated space because the generated layouts
    only ever probe what resolution RETURNS, and a returned path that does not
    exist satisfies the safety half trivially. Deleting the whole containment
    block from `_hinted_gate_file` left the property file green; it does not
    leave this one green.

    A PASS gate is planted at EVERY escape target, including the absolute one,
    and that is load-bearing rather than tidy. Pointing the absolute case at a
    path that does not exist (`/etc/gate-decision.json`) makes it pass whether
    the hint is refused or followed - a followed hint just returns a missing
    file - so the absolute lane, which is the one that reaches arbitrary paths on
    disk, would be the only shape with no regression net.
    """
    trace = tmp_path / "trace"
    (trace / "nested").mkdir(parents=True)
    (trace / "sub").mkdir()
    (tmp_path / "outside").mkdir()

    planted = json.dumps({"gate_status": "PASS", "p0_status": "MET"})
    outside_gate = tmp_path / "outside" / "gate-decision.json"
    outside_gate.write_text(planted, encoding="utf-8")
    (trace / "nested" / "gate-decision.json").write_text(planted, encoding="utf-8")

    hint = hint.replace("{ABSOLUTE_OUTSIDE}", str(outside_gate))
    (trace / "trace-4-1.md").write_text(
        f"---\nworkflowType: trace\ngateDecisionFile: {hint}\n---\n", encoding="utf-8"
    )

    resolved = gate_eval._resolve_gate_file(trace, "4-1")
    if resolved is not None:
        assert resolved.resolve().parent == trace.resolve(), (
            f"hint {hint!r} resolved to {resolved}, outside {trace}"
        )

    reasons: list[str] = []
    assert gate_eval.load_gate(trace, reasons, "4-1")["gate_status"] == "NOT_EVALUATED", (
        f"hint {hint!r} produced a verdict from outside the artifact directory; reasons={reasons}"
    )


@pytest.mark.parametrize(
    "hinted_status,other_status",
    [("FAIL", "PASS"), ("CONCERNS", "PASS"), ("FAIL", "CONCERNS")],
    ids=["fail-vs-pass", "concerns-vs-pass", "fail-vs-concerns"],
)
def test_a_refused_hint_never_resolves_a_better_verdict_from_another_file(
    tmp_path, hinted_status, other_status
):
    """A refused hint must not be quietly replaced by a file nobody pointed at.

    Refusing to FOLLOW a hint and then resolving the next candidate anyway is not
    a smaller answer, it is a DIFFERENT one, and the difference runs uphill:
    measured, a subdirectory hint carrying FAIL was refused and the story
    advanced on its own summary's PASS, and an unscoped run whose hinted CONCERNS
    was refused advanced on the generic summary. Both looked like ordinary
    successful reads in the log, because the fallback names a real file.

    Only the story's own `gate-decision-<id>.json` survives a refusal, and its
    liveness is asserted by the escape layout in the generated space.
    """
    trace = tmp_path / "trace"
    (trace / "gates").mkdir(parents=True)
    (trace / "gates" / "gate-decision.json").write_text(
        json.dumps({"gate_status": hinted_status, "p0_status": "NOT_MET"}), encoding="utf-8"
    )
    # the file that would be resolved instead, carrying a BETTER verdict
    (trace / "e2e-trace-summary.json").write_text(
        json.dumps({"gate_status": other_status, "gate_criteria": {"p0_status": "MET"}}),
        encoding="utf-8",
    )
    (trace / "trace.md").write_text(
        "---\nworkflowType: trace\ngateDecisionFile: gates/gate-decision.json\n---\n",
        encoding="utf-8",
    )

    reasons: list[str] = []
    gate = gate_eval.load_gate(trace, reasons, None)

    assert gate["gate_status"] != other_status, (
        f"a refused hint resolved {other_status!r} from a file the run never pointed at; "
        f"reasons={reasons}"
    )
    assert gate["gate_status"] == "NOT_EVALUATED", reasons
    assert any("hint" in r for r in reasons), (
        f"the refusal must be visible to the operator, not only fail closed; reasons={reasons}"
    )


def test_a_hint_is_still_followed_inside_the_artifact_directory(tmp_path):
    """Containment's liveness twin: an ordinary in-directory hint still resolves.

    Without this, refusing every hint would pass the containment test above.
    """
    trace = tmp_path / "trace"
    trace.mkdir(parents=True)
    (trace / "gate-decision-4-1.json").write_text(
        json.dumps({"gate_status": "PASS", "p0_status": "MET"}), encoding="utf-8"
    )
    (trace / "trace-4-1.md").write_text(
        "---\nworkflowType: trace\ngateDecisionFile: gate-decision-4-1.json\n---\n",
        encoding="utf-8",
    )

    resolved = gate_eval._resolve_gate_file(trace, "4-1")
    assert resolved is not None and resolved.name == "gate-decision-4-1.json"

    reasons: list[str] = []
    assert gate_eval.load_gate(trace, reasons, "4-1")["gate_status"] == "PASS", reasons


def test_an_isolated_storys_generic_gate_file_is_still_followed_by_its_own_hint(built):
    """LIVENESS: the shape `references/gate.md` tells an operator to build.

    Isolate one story's artifacts into a fresh directory, with a TEA build that
    names the trace report per story and the gate decision generically, and the
    hint from that report is the only thing pointing at the gate. The SAFETY half
    above passes whether or not this hint is followed - absent satisfies it - so
    without this assertion the fix that refuses a cross-story hint could refuse
    this one too and nothing would red. It did, before this test existed: the
    story's real PASS came back NOT_EVALUATED -> escalate.

    Its twin is in the safety pass: `hint-generic-shared`, where TWO stories'
    reports hint at ONE generic gate file, must resolve for neither.
    """
    checked = 0
    for index, layout in enumerate(LAYOUTS):
        if not layout.name.startswith("hint-generic-isolated["):
            continue
        directory = built[f"L{index:04d}"]
        reasons: list[str] = []
        assert gate_eval.load_gate(directory, reasons, "4-1")["gate_status"] == "PASS", (
            f"{layout.name}: the isolated story's own hint stopped resolving; reasons={reasons}"
        )
        checked += 1
    assert checked, "no isolated-with-generic-hint layout was generated"


def test_the_generated_space_is_actually_adversarial():
    """The space must contain the shapes the property is about, or green means nothing.

    A refactor that trimmed TEMPLATES or OWNERS could quietly shrink this file to
    a handful of benign layouts and stay green. These are the load-bearing shapes.
    """
    names = " ".join(l.name for l in LAYOUTS)
    assert any(l.all_generic for l in LAYOUTS), "no isolated all-generic directory"
    assert "shared[" in names, "no shared multi-story directory"
    assert "mixed[" in names, "no per-story-beside-generic directory"
    assert "hint-neighbour[" in names, "no cross-story frontmatter hint"
    assert "hint-escape[" in names, "no directory-escaping frontmatter hint"
    assert "hint-generic-isolated[" in names, "no isolated single-story dir with a generic hint"
    assert "hint-generic-shared[" in names, "no two-stories-one-generic-gate-file hint"
    assert "two-json[" in names, "no directory pairing a per-story json with a generic one"
    assert any(
        sum(1 for name in layout.files if name.endswith(".json")) >= 2 for layout in LAYOUTS
    ), "no layout holds two json artifacts, so the run-wide-file fall-open is inexpressible"
    assert "rollup-only[" in names, "no epic-roll-up-only directory"
    every_filename = {name for layout in LAYOUTS for name in layout.files}
    assert any(name.startswith("traceability-matrix-") for name in every_filename), (
        "TEA's own traceability-matrix filename is not in the space"
    )
    assert any(name.startswith("e2e-trace-summary-") for name in every_filename), (
        "the per-story summary spelling is not in the space"
    )
    assert len(LAYOUTS) > 200, f"the generated space collapsed to {len(LAYOUTS)} layouts"
