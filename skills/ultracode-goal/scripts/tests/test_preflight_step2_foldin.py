"""Step-2 fold-in + leaked-TEA-artifact MOVE remediation.

Two layers: (1) doc-shape assertions over preflight.md '## 2.' (bullet present, no
new pass, fold-in source contract, per-finding remediable gating prose); (2) a
deterministic dry-run MOVE-and-re-point harness that mechanizes the documented
steps, ENFORCES the per-finding `remediable` gate, and whose mutant variants
(skip-re-point, rewrite-body, gate-removed) break the meaning-preserving /
gate assertions — proving the checks are non-vacuous. Stdlib + pytest only.
"""

import hashlib
import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT = _SKILL_ROOT / "references" / "preflight.md"


def _text() -> str:
    return _PREFLIGHT.read_text(encoding="utf-8")


def _step2_block(text: str) -> str:
    start = text.index("## 2. Auto-remediation pass")
    end = text.index("## 3.", start)
    return text[start:end]


# --------------------------------------------------------------------------
# The documented MOVE-and-re-point dry-run harness (a test helper, not prod).
# --------------------------------------------------------------------------
def move_and_repoint(repo_root, leaked_rel, trace_root_rel, gap, *, mutant=None):
    """Mechanize the leaked-TEA-artifact MOVE-and-re-point, honoring `remediable`.

    A gap whose `remediable` is not True yields zero moves and zero rewrites
    (the per-finding remediable gate) — unless mutant='ignore_gate'.
    mutant in {None,'skip_repoint','rewrite_body','ignore_gate'}.
    Returns {'moves': int, 'dest': Path|None, 'refs_rewritten': int}.
    """
    repo_root = Path(repo_root)
    leaked = repo_root / leaked_rel
    if mutant != "ignore_gate" and gap.get("remediable") is not True:
        return {"moves": 0, "dest": None, "refs_rewritten": 0}
    body = leaked.read_bytes()
    trace_root = repo_root / trace_root_rel
    trace_root.mkdir(parents=True, exist_ok=True)
    dest = trace_root / leaked.name
    dest.write_bytes(body + b"\n<!-- mutated -->\n" if mutant == "rewrite_body" else body)
    leaked.unlink()
    refs = 0
    if mutant != "skip_repoint":
        # Re-point with a POSIX forward-slash reference: the MOVE rewrites a
        # documentation reference, not an OS path, so it must be portable
        # (str(Path(...)) emits backslashes on Windows and breaks the ref).
        new = dest.relative_to(repo_root).as_posix()
        for p in repo_root.rglob("*"):
            if not p.is_file() or p == dest:
                continue
            try:
                t = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if leaked_rel in t:
                p.write_text(t.replace(leaked_rel, new), encoding="utf-8")
                refs += 1
    return {"moves": 1, "dest": dest, "refs_rewritten": refs}


def _build_fixture(root: Path) -> str:
    """A leaked TEA artifact under a source dir + a markdown file referencing it."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir()
    (root / "docs").mkdir()
    leaked_rel = "src/test-design-epic-X.md"
    (root / leaked_rel).write_text("# risk matrix\nP0 core-flow ...\n", encoding="utf-8")
    (root / "docs" / "ref.md").write_text(
        f"See the plan at {leaked_rel} for details.\n", encoding="utf-8"
    )
    return leaked_rel


# --------------------------------------------------------------------------
# Case 1 — MOVE bullet present, no new pass / no 6th step heading.
# --------------------------------------------------------------------------
def test_leaked_artifact_move_bullet_present():
    block = _step2_block(_text())
    assert re.search(r"move .*(trace_output|test_artifacts).*re-?point", block, re.I), (
        "leaked-TEA MOVE-and-re-point bullet missing under '## 2.'"
    )
    assert len(re.findall(r"^## [0-9]+\.", _text(), re.M)) == 5, "step-heading count must stay 5"
    # anti-vacuous: stripping the bullet defeats the regex
    mutated = re.sub(r"^- \*\*Formalize mechanical gaps\*\*.*$", "", block, flags=re.M)
    assert not re.search(r"move .*(trace_output|test_artifacts).*re-?point", mutated, re.I)


# --------------------------------------------------------------------------
# Case 2 — fold-in source contract: mechanical_gaps + named gaps + re-run loop.
# --------------------------------------------------------------------------
def test_foldin_cites_formalize_mechanical_gaps():
    block = _step2_block(_text())
    for tok in ("formalize_check.py", "mechanical_gaps", "leaked", "orphaned"):
        assert tok in block, f"step-2 fold-in must name {tok!r}"
    assert "missing-AC" in block or "missing AC" in block
    assert "run the script from step 1 again" in _text(), "existing re-run line must survive"
    # anti-vacuous: hollow bullet stripped of the wiring tokens fails the contract
    hollow = block.replace("formalize_check.py", "").replace("mechanical_gaps", "")
    assert not ("formalize_check.py" in hollow and "mechanical_gaps" in hollow)


# --------------------------------------------------------------------------
# Case 3 — per-finding `remediable` gate: real harness behavior + prose contract.
# --------------------------------------------------------------------------
def test_move_gated_on_remediable_literal(tmp_path):
    # layer 1 — BEHAVIOR
    a = tmp_path / "false"
    leaked = _build_fixture(a)
    r = move_and_repoint(a, leaked, "trace_out", {"kind": "leaked_tea_artifact", "remediable": False})
    assert r["moves"] == 0 and (a / leaked).exists() and r["refs_rewritten"] == 0

    b = tmp_path / "true"
    leaked = _build_fixture(b)
    r = move_and_repoint(b, leaked, "trace_out", {"kind": "leaked_tea_artifact", "remediable": True})
    assert r["moves"] == 1 and not (b / leaked).exists()
    assert (b / "trace_out" / "test-design-epic-X.md").exists()

    # mutant: gate removed -> moves a remediable:false fixture (layer-1 twin FAILS)
    c = tmp_path / "gateoff"
    leaked = _build_fixture(c)
    move_and_repoint(c, leaked, "trace_out", {"remediable": False}, mutant="ignore_gate")
    assert not (c / leaked).exists(), "gate-removed mutant moves a remediable:false file (the twin defeater)"

    # layer 2 — PROSE CONTRACT
    block = _step2_block(_text())
    assert "remediable" in block
    assert re.search(r"only .*remediable|remediable[`'\" ]*[:=]?[`'\" ]*true", block, re.I)
    assert re.search(
        r"(judgment|remediable[`'\" :=]*false).*(step 3|step 4|hard gate)", block, re.I | re.S
    )


# --------------------------------------------------------------------------
# Case 4 — the MOVE is mechanical, meaning-preserving, and gate-honoring.
# --------------------------------------------------------------------------
def test_leaked_artifact_move_is_meaning_preserving(tmp_path):
    ok = tmp_path / "ok"
    leaked = _build_fixture(ok)
    orig = (ok / leaked).read_bytes()
    move_and_repoint(ok, leaked, "trace_out", {"kind": "leaked_tea_artifact", "remediable": True})
    dest = ok / "trace_out" / "test-design-epic-X.md"
    assert not (ok / leaked).exists()
    assert dest.exists()
    # (b) content byte-identical
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == hashlib.sha256(orig).hexdigest()
    # (c) zero dangling references; the former reference resolves to the new path
    assert all(
        leaked not in p.read_text(encoding="utf-8")
        for p in ok.rglob("*.md")
        if p.is_file()
    )
    assert "trace_out/test-design-epic-X.md" in (ok / "docs" / "ref.md").read_text()

    # (d) remediable:false companion -> no move, no rewrite
    gated = tmp_path / "gated"
    leaked2 = _build_fixture(gated)
    r2 = move_and_repoint(gated, leaked2, "trace_out", {"remediable": False})
    assert r2["moves"] == 0 and (gated / leaked2).exists()
    assert not (gated / "trace_out").exists()

    # mutant (i) skip-re-point -> a dangling reference remains (breaks (c))
    skip = tmp_path / "skip"
    lr = _build_fixture(skip)
    move_and_repoint(skip, lr, "trace_out", {"remediable": True}, mutant="skip_repoint")
    assert lr in (skip / "docs" / "ref.md").read_text(), "skip-re-point must leave a dangling ref"

    # mutant (ii) rewrite-body -> sha256 mismatch (breaks (b))
    bod = tmp_path / "body"
    lr2 = _build_fixture(bod)
    ob = (bod / lr2).read_bytes()
    move_and_repoint(bod, lr2, "trace_out", {"remediable": True}, mutant="rewrite_body")
    moved = bod / "trace_out" / "test-design-epic-X.md"
    assert hashlib.sha256(moved.read_bytes()).hexdigest() != hashlib.sha256(ob).hexdigest()
