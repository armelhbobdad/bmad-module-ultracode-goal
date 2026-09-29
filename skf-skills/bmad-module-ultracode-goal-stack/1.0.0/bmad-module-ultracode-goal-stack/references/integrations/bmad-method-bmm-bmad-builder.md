# bmad-method-bmm + bmad-builder

- **Type:** Adapter/Wrapper
- **Detection:** constituent-documented-contract (compose-mode; no co-import files)
- **Confidence:** T1-low (constituent-documented-contract) [composed]

BMAD v6 keeps deprecated core IDs as shims that forward to their replacements (e.g. `bmad-review-adversarial-general` → the `bmad-review` adversarial lens). The BMM skill records that external module repos — including `bmb` — still invoke the core IDs, so a BMad Builder call on an old core ID goes through a v6 shim rather than the replacement skill.

**Convention:** prefer the replacement skill named in the core shim table over the deprecated core ID; the shim only forwards.

Evidence: [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` ("External module repos (gds, loop, tea, bmb, os-utils) still invoke the core IDs.") and the core shim → replacement table. [from skill: bmad-builder] Key Exports (module code `bmb`).
