# Module Validation Report — ultracode-goal

- **Date:** 2026-06-04
- **Module:** `ultracode-goal` (UCG: UltraCode Goal — Autonomous Epic Execution), standalone single-skill module at `skills/`
- **Validator:** BMad Module Builder — Validate Module (VM), structural script + 5-lens quality assessment with adversarial verification (18 agents; 13 raw findings → 5 confirmed, 8 refuted)
- **Status:** `fail` (structural) — 1 root-cause HIGH gap, 3 LOW; module quality otherwise excellent

---

## Verdict

The skill itself, the npx installer, packaging hygiene, and all description surfaces are in excellent shape — the adversarial pass refuted 8 of 13 candidate findings, mostly because the custom installer already covers what BMad scaffolding would (IDE registration for 23+ IDEs, manifest-tracked uninstall/update, dev-artifact exclusion on both shipping paths).

**The one material gap: the module is invisible to BMad's own help/routing system.** Nothing — not the installer, not a shipped `module-help.csv`, not a merge script — ever registers UCG into `{project-root}/_bmad/_config/bmad-help.csv`. Two independent lenses converged on this; both verifications confirmed at high confidence, including the decisive corroboration that this very repo's catalog has 69 rows from five modules and zero for UCG. There is also **no documented decision** in `.decision-log.md` (D1–D12) to skip help-catalog registration — this is drift, not a recorded trade-off.

---

## Structural results (validate-module.py)

```json
{
  "status": "fail",
  "findings": [{
    "severity": "critical",
    "category": "structure",
    "message": "No setup skill found (*-setup directory) and no standalone module detected"
  }]
}
```

Root cause: `detect_standalone_module()` requires `skills/ultracode-goal/assets/module.yaml`; this module keeps `module.yaml` at `skills/module.yaml` (sibling of the skill dir). The validator therefore bails before its CSV checks. Of the five convention artifacts the script would then require, the adversarial pass judged only **two** as genuinely needed (see F1, F4); `module-setup.md` and `merge-config.py` were **refuted** as real gaps (the installer covers their function — see "Refuted" below).

---

## Confirmed findings

### F1 — HIGH · UCG is never registered into `_bmad/_config/bmad-help.csv` (invisible to bmad-help routing)

*Lenses: registration-completeness + scaffolding-compliance (independent convergence; both verified high-confidence)*

`bmad-help` assembles its catalog exclusively from `{project-root}/_bmad/_config/bmad-help.csv` (`bmad-help/SKILL.md:25`, `workflow.md:58`). The installer writes `_bmad/_config/ucg-manifest.yaml` (`manifest.js:10-11`) and copies the skill, but no code anywhere in `tools/`, `build/`, `skills/`, or `docs/` creates or appends a help-catalog row (repo-wide grep for `bmad-help.csv|module-help|menu-code|merge-help` → no matches). Consequence: after `npx … install` into a BMad project, a user asking bmad-help *"how do I run an epic autonomously"* or *"what's next after sprint-planning"* gets **zero routing to UCG** — despite UCG positioning itself exactly in the 4-implementation slot (`bmad-sprint-planning → ucg → bmad-retrospective`). The skill remains reachable via IDE auto-invoke and `/ultracode-goal`, which is why this is HIGH, not critical.

**Fix (two complementary parts):**

1. Author `skills/ultracode-goal/assets/module-help.csv` with the catalog header and the primary row. Suggested seed:

   ```csv
   module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by,required,output-location,outputs
   ucg,ultracode-goal,UltraCode Goal — Autonomous Epic Execution,UG,Run a BMAD Epic autonomously to a deterministic TEA-gated Definition-of-Done; preflights to a remediated green light then advances only on a machine-checked gate verdict,,{--light: trace gate only}|{--parallel: experimental worktree fan-out}|{-H: headless}|{--yes: skip launch confirm}|{--retro: close-out retrospective},4-implementation,bmad-sprint-planning,bmad-retrospective,false,implementation_artifacts,run-report.md|deferred-work.md|decision log
   ```

2. Register it at install time: either add `lib/help-catalog.js` called from `installer.js` after `writeManifest` (idempotent upsert: create CSV with header if absent; replace existing `module==ucg` rows on update; remove on uninstall alongside `removeAllUcgSkills`), **or** ship `scripts/merge-help-csv.py` per the BMad standalone template and call it from `install.js`.

**Column-name wrinkle to reconcile:** the live assembled catalog uses `preceded-by`/`followed-by`, while `validate-module.py`'s `CSV_HEADER` expects `after`/`before`. Use the catalog's names — that is what bmad-help actually parses (and report the validator mismatch upstream if you want script-green).

### F2 — LOW · `module.yaml` location breaks standalone-module detection

`validate-module.py:53-63` recognizes a standalone module only when `assets/module.yaml` lives **inside** the skill folder. Current location `skills/module.yaml` → detection returns None → the critical structural fail above, and any future BMad tooling that uses the same convention won't recognize the module either. The npx installer reads the current location fine (`installer.js:155`), so this is interop-only.

**Fix:** move `module.yaml` → `skills/ultracode-goal/assets/module.yaml`; update `installer.js:155-157` to the new path. This single relocation is the precondition that makes F1's `module-help.csv` land where the validator looks for it.

### F3 — LOW · `module.yaml` display metadata has no consumer

`skills/module.yaml:1-6` carries exactly the catalog metadata a help row needs (name/header/subheader/description), but nothing parses these fields — the installer copies the file verbatim. **Fix:** when implementing F1, source the row's display-name/description from `module.yaml` so the catalog stays single-sourced instead of hand-duplicated.

### F4 — LOW · Two dangling `docs/` pointers under the skill's own bare-path convention

`SKILL.md:16` declares bare paths resolve from the skill root, but `SKILL.md:44` cites `docs/cross-session-recall.md` and `customize.toml:38` cites `docs/health-check.md` — no `docs/` exists under the skill root in source **or** installed layout (the installer copies repo docs to `{project-root}/_ucg-learn/`, `installer.js:219-221`). Advisory pointers only; not load-bearing (the runtime protocol correctly uses `references/health-check.md`). **Fix:** repoint both to `_ucg-learn/…` or the docs-site URL, or label them as project docs.

---

## Refuted (checked and cleared — no action needed)

| Candidate finding | Why refuted |
|---|---|
| Run modes (`--light`, `--parallel`, `-H`, `--retro`) lack a discovery surface | README Quick Start (84-88) + `docs/getting-started.md` document all of them |
| `module.yaml` `health_check_repo` prompt block misdirects from the real override surface | Mechanics verified fine; comment correctly names `_bmad/custom/ultracode-goal.toml` |
| Installer config-merge gap (`merge-config.py` missing) | `_bmad/config.yaml` is BMad CORE's shared config, not UCG's to write; UCG's own config lands in `_bmad/ucg/` and resolves correctly |
| No `module-setup.md` self-registration for marketplace/manual installs | Marketplace path is a first-class documented route; skill activation degrades gracefully without `_bmad` config |
| `.decision-log.md` resume-collision risk via exclusion lists | Collision fully defused today by two independent verified gates; residual is defense-in-depth only |
| SKILL.md description misses natural trigger phrasings | Description's lead sentence carries the routing semantics; matches BMad house style exactly |
| `module.yaml` description leaks implementation jargon | That field has no surfaced reader pre-install; not a routing/marketing surface |
| No authored help-CSV description cell (craft lens) | Real issue is F1 (existence), not craft; merged |

---

## Healthy (verified strengths)

- **Packaging hygiene is belt-and-suspenders on both shipping paths**: `.npmignore` excludes `.analysis/`, `.decision-log.md`, `scripts/tests/`, `__pycache__/`, `.pytest_cache/`; `npm pack --dry-run` confirms a clean tarball; `installer.js` `DEV_ARTIFACTS` filters the install copy independently.
- **Accuracy**: zero critical/high drift across registration surfaces; module.yaml's headline claim is precisely backed by `gate_eval.py`'s actual contract; all six stage references exist and match.
- **Installer beats the BMad convention on its home turf**: config-driven IDE registration for 23+ IDEs, manifest-tracked update/uninstall, legacy-target cleanup, reinstall idempotency.
- **Description craft**: header/subheader verb-first and specific; SKILL.md frontmatter matches installed BMad house style (trigger-phrase block) exactly.
- `.decision-log.md` root placement: documented false positive (build-process mandates it); correctly excluded from both ship paths.

---

## Recommended fix order

1. **F2** — relocate `module.yaml` into `assets/` (5-minute precondition).
2. **F1** — author `assets/module-help.csv` + installer/uninstaller registration step (the only HIGH; closes the discoverability gap).
3. **F3** — single-source the row from `module.yaml` while doing F1.
4. **F4** — repoint the two `docs/` pointers (two-line fix).
5. Re-run `validate-module.py skills/` → should pass structurally; re-run VM for the green report.
