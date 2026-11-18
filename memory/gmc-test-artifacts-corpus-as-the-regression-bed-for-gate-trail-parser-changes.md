---
created: "2026-10-16 17:35"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# GMC test-artifacts corpus as the regression bed for gate_trail parser changes

A change to `gate_trail.py`'s table parsing (`criterion_rows`) passed the whole suite (1746 tests) yet rendered two real production ATDD checklists worse, which only showed when main's parser and the branch's were run over the 286 real checklists and trace reports in the GMC consumer checkout's `_bmad-output/test-artifacts/` (270 rendered the same, 16 differed). The same pass found that TEA 1.27.2's own ATDD checklist template (in the cached TEA module under `~/.bmad/cache/external-modules/tea/`) heads its AC table `| ID | ID source | Acceptance criterion |`, a shape the change would have turned into an `n/a` trail for every production story on 1.27.2. Before merging a change to how the gate trail or the trace readers parse tables, diff its output against main's across that corpus and TEA's template, since the fixtures do not hold every shape real runs write.
