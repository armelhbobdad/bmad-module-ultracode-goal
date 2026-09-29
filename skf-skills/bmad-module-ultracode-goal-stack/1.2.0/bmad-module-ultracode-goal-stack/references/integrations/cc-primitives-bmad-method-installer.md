# cc-primitives + bmad-method-installer Integration

**Type:** Configuration Bridge
**Co-import files:** 0 (compose-mode; no codebase — the contract is documented in a constituent skill)
**Detection:** constituent-documented-contract (`detection_method: constituent_documented_contract`) — documented by bmad-method-installer (Quick Start, Pattern Surface row 19, `references/pattern-update-and-cleanup.md`)
**Confidence:** T3 (constituent-documented-contract) [composed] — weaker of cc-primitives (T3) and bmad-method-installer (T1-low)

## Integration Pattern

Run with --tools claude-code, the BMAD installer's _setupIdes() phase copies every skill listed in skill-manifest.csv into .claude/skills/<canonicalId>. It runs cleanup first, deleting each old folder along with previously installed IDs and removals.txt entries, and keeps bmad-os-* skills (bmad-method-installer SKILL.md Quick Start L25, L28 and L38; references/pattern-update-and-cleanup.md L63-L64). That target is the same path cc-primitives documents for project skills, .claude/skills/<name>/SKILL.md, which Claude Code loads from the start directory up to the repo root (cc-primitives SKILL.md L52 and L68; references/skills-and-plugins.md L16). The two sides differ in how strict they are about frontmatter. The installer skips any SKILL.md without --- frontmatter at the very start and a string name equal to the folder name, so that skill never reaches .claude/skills. Claude Code treats every field as optional, defaults name to the directory name, and still loads a skill whose YAML fails to parse, just with no fields (installer SKILL.md L51 and references/pattern-manifests-and-help.md L27-L28; cc-primitives references/skills-and-plugins.md L24 and L28). The installer also lists a global claude-code target, ~/.claude/skills, and refuses to install when an ancestor already holds BMAD skills in the same target. Claude Code treats ~/.claude/skills as the personal scope, and personal skills outrank same-named project skills (references/pattern-update-and-cleanup.md L62 and L65; references/skills-and-plugins.md L15 and L20).

## Key Files

Upstream source files behind the cited lines (from the constituents' `[SRC:…]` tags):

- `tools/installer/core/installer.js`
- `tools/installer/ide/platform-codes.yaml`
- `tools/installer/ide/_config-driven.js`
- `tools/installer/core/manifest-generator.js`
- `tools/installer/ide/manager.js`
- `tools/installer/core/legacy-warnings.js`

## Usage Convention

Author every BMAD module skill as `<canonicalId>/SKILL.md` with `---` frontmatter on line 1 and a string `name` equal to the folder name; this meets the installer's stricter rule and Claude Code's. Treat `.claude/skills/<canonicalId>` as installer output: change skills at the module source and re-run `npx bmad-method install --tools claude-code`, since setup deletes and replaces the folder. Check `~/.claude/skills` for same-named copies, because a personal skill beats the project one.

## Evidence

Verbatim citations from the constituent skills (file relative to the skill root, nearest heading, line):

- [from skill: bmad-method-installer] `SKILL.md` — ## Quick Start, L28: "npx bmad-method install --yes --directory <project> --modules bmm --tools claude-code"
- [from skill: bmad-method-installer] `SKILL.md` — ## Quick Start, L38: "`_setupIdes()`: copy every skill in `skill-manifest.csv` into the tool's skill folder (`.claude/skills/<canonicalId>` for claude-code), cleaning removed IDs first."
- [from skill: bmad-method-installer] `SKILL.md` — ## Adoption Steps, L51: "**Make every skill a folder with `SKILL.md` whose frontmatter `name` equals the folder name** — mismatches are skipped from `skill-manifest.csv`, and skills not in that CSV are never copied into `.claude/skills`."
- [from skill: bmad-method-installer] `SKILL.md` — ## Pattern Surface, L77: "| 19 | `tools/installer/ide/platform-codes.yaml` | `claude-code` target | `.claude/skills` install folder"
- [from skill: bmad-method-installer] `references/pattern-update-and-cleanup.md` — ## IDE skill install and cleanup, L62: "One handler per platform in `platform-codes.yaml`; `claude-code` installs to `.claude/skills` (global `~/.claude/skills`)."
- [from skill: bmad-method-installer] `references/pattern-update-and-cleanup.md` — ## IDE skill install and cleanup, L63: "Setup always runs cleanup first; skills come from `skill-manifest.csv` and land in `<target_dir>/<canonicalId>` after the old folder is deleted; `.DS_Store` and `__pycache__` are skipped."
- [from skill: bmad-method-installer] `references/pattern-update-and-cleanup.md` — ## IDE skill install and cleanup, L64: "Cleanup removes previously installed skill IDs plus `removals.txt` entries, keeps `bmad-os-*`, and uses prefix ownership only when no removal set exists."
- [from skill: bmad-method-installer] `references/pattern-update-and-cleanup.md` — ## IDE skill install and cleanup, L65: "`ancestor_conflict_check` refuses an install when an ancestor already holds BMAD skills in the same target."
- [from skill: bmad-method-installer] `references/pattern-update-and-cleanup.md` — ## IDE skill install and cleanup, L67: "Pre-6.1.0 installs get exact `rm -rf` hints for stale `.claude/commands` and legacy skill paths."
- [from skill: bmad-method-installer] `references/pattern-manifests-and-help.md` — ## skill-manifest.csv, L27: "`SKILL.md` needs `---` frontmatter at the very start with a string `name` equal to the folder name; otherwise the skill is skipped."
- [from skill: bmad-method-installer] `references/pattern-manifests-and-help.md` — ## skill-manifest.csv, L28: "`canonicalId` is the folder name; `path` is `_bmad/<module>/<relativePath>/SKILL.md`."
- [from skill: bmad-method-installer] `SKILL.md` — ## Quick Start, L25: "Non-interactive install into a project, with Claude Code as the tool target:"
- [from skill: bmad-method-installer] `SKILL.md` — ## Quick Start, L31: "`--tools` is required for a fresh `--yes` install"
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## SKILL.md frontmatter, L36: "| `hooks` | Registered on invocation for the rest of the session"
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Skill locations and precedence, L17: "| `<subdir>/.claude/skills/<name>/SKILL.md` | Nested; loads once Claude works on files there"
- [from skill: cc-primitives] `SKILL.md` — ## Common Workflows, L52: "**Ship a workflow as a skill:** write `.claude/skills/<name>/SKILL.md` with `description` frontmatter."
- [from skill: cc-primitives] `SKILL.md` — ## Key API Summary, L68: "| Skills | `.claude/skills/<name>/SKILL.md` | Frontmatter `description`, `disable-model-invocation`, `allowed-tools`, `context: fork`, `hooks`"
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Skill locations and precedence, L15: "| `~/.claude/skills/<name>/SKILL.md` | Personal, all projects"
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Skill locations and precedence, L16: "| `.claude/skills/<name>/SKILL.md` | Project; loaded from the start directory up to the repo root"
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Skill locations and precedence, L20: "Same-named skills: enterprise > personal > project; a skill beats a same-named `.claude/commands/` file; plugin skills are namespaced."
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Skill locations and precedence, L20: "Custom slash commands were merged into skills; `.claude/commands/` files still work but lack `name`/`paths` and supporting files."
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Skill locations and precedence, L20: "Edits under skill directories are picked up live; plugin hooks/agents/MCP need `/reload-plugins`."
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## SKILL.md frontmatter, L24: "Frontmatter must start on line 1; unknown keys and YAML parse failures are silently ignored (the skill loads with no fields)."
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## SKILL.md frontmatter, L24: "All fields are optional; `description` is recommended."
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## SKILL.md frontmatter, L28: "| `name` | Command name (defaults to the directory name)"
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Invocation and substitutions, L44: "`${CLAUDE_SKILL_DIR}` (the skill folder), `${CLAUDE_PROJECT_DIR}`"
