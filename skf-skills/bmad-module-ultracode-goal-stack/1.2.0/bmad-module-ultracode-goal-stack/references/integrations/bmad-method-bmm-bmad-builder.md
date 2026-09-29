# bmad-method-bmm + bmad-builder Integration

**Type:** Adapter/Wrapper
**Co-import files:** 0 (compose-mode; no codebase — the contract is documented in a constituent skill)
**Detection:** constituent-documented-contract (`detection_method: constituent_documented_contract`) — documented by bmad-method-bmm (`references/pattern-v6-shims.md`, `references/pattern-planning.md`)
**Confidence:** T1-low (constituent-documented-contract) [composed] — weaker of bmad-method-bmm (T1-low) and bmad-builder (T1-low)

## Integration Pattern

BMAD v6 keeps deprecated core IDs as shims that forward to their replacements, for example `bmad-review-adversarial-general` → the `bmad-review` adversarial lens. The bmad-method-bmm skill, which catalogues the 6 core shims under `src/core-skills/v6-shims/`, records that external module repos, including `bmb`, still invoke the core IDs. When shims are installed, a BMad Builder call on an old core ID goes through the v6 shim rather than straight to the replacement. On a fresh v6.12.0 install, shims need `--shims`. In the other direction, BMM's `bmad-architecture` sends misrouted asks to BMad Builder's `bmad-workflow-builder`.

## Key Files

Upstream source files behind the cited lines (from the constituents' `[SRC:…]` tags):

- `src/core-skills/v6-shims/README.md`
- `src/core-skills/v6-shims/bmad-review-adversarial-general/SKILL.md`
- `src/bmm-skills/plan/bmad-architecture/SKILL.md`
- `skills/module.yaml`

## Usage Convention

Prefer the replacement named in the core shim table (for example the `bmad-review` adversarial lens) over the deprecated core ID; the shim only forwards. If bmb must run on a fresh v6.12.0 install that relies on old core IDs, check whether the shims were installed (`--shims`). Send workflow- and skill-building requests to `bmad-workflow-builder`, not `bmad-architecture`.

## Evidence

Verbatim citations from the constituent skills (file relative to the skill root, nearest heading, line):

- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` — ## Core shim map, L49: "External module repos (gds, loop, tea, bmb, os-utils) still invoke the core IDs."
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` — ## Core shim map, L45: "| `bmad-review-adversarial-general` | `bmad-review` adversarial lens"
- [from skill: bmad-method-bmm] `SKILL.md` — ## Overview, L18: "6 core shims under `src/core-skills/v6-shims/`"
- [from skill: bmad-method-bmm] `references/pattern-planning.md` — ## bmad-architecture, L45: "misrouted asks go to `bmad-prd`, `bmad-ux`, `bmad-spec`, `bmad-create-epics-and-stories` or `bmad-workflow-builder`."
- [from skill: bmad-method-bmm] `SKILL.md` — ## Migration & Deprecation Warnings, L82: "v6.12.0: deprecated shims are opt-in on fresh installs (`--shims` keeps them)"
- [from skill: bmad-builder] `SKILL.md` — ## Description, L27: "`skills/module.yaml` registers the module as code `bmb`"
- [from skill: bmad-builder] `SKILL.md` — ## Description, L25: "A BMad Core expansion module"
- [from skill: bmad-builder] `SKILL.md` — ## Key Exports, L31: "The module's public surface is its skills (folder name = frontmatter `name`):"
- [from skill: bmad-builder] `SKILL.md` — ## Key Exports, L36: "| `bmad-workflow-builder` | skill | Builds, edits, and analyzes workflows and skills. |"
- [from skill: bmad-builder] `SKILL.md` — ## Notes, L74: "skill bodies, step files and scripts were not extracted"
