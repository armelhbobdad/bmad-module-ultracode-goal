---
created: "2026-11-17 22:16"
session: "60ac1f41-93ab-4fff-b3c7-bdf99f676ae8"
---

# Targeted fix over full revert on a BMAD review intent gap

bmad-build's step 4 (`step-04-review.md` under `_bmad/render/bmad-build/`) routes an `intent_gap` or `bad_spec` triage entry to a loopback that reverts every code change and re-derives the whole diff from the amended spec. On 2026-11-17, closing #239, #240 and #241 (PR #242), round 1's only intent gap sat in a few sentences of the #240 escalation handling on a three-commit, 2500-line branch, and asked "Targeted fix" against "Full revert and redo", the user chose the targeted fix. So when a review finding needs the user's decision, put that choice to them rather than reverting by default. On a targeted fix, write the answer into the spec's `<frozen-after-approval>` block as a decision with a Spec Change Log entry naming the commits kept, send the same step-03 implementing subagent only the affected parts plus the round's patch findings, re-run `npm run quality`, and review the new changes in a second round. Related: [[feature-branch-pr-flow-with-user-side-merge-and-main-only-cleanup]].
