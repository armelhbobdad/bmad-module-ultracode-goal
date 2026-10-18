---
created: "2026-10-18 15:04"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# BMAD plugin resolver keeps the module definition only for a single listed skill

BMAD's installer reads `.claude-plugin/marketplace.json` and hands each plugin entry to `PluginResolver` (`tools/installer/modules/plugin-resolver.js`, checked on 6.12.4), which tries five strategies in order. UCG's `assets/module.yaml` (code `ultracode-goal`) and `assets/module-help.csv` are found only through strategy 3, which requires exactly one listed skill path that exists (`skillPaths.length === 1`), with both files in its `assets/`. Listing `./skills/ucg-create-story` and `./skills/ucg-dev-story` beside `./skills/ultracode-goal` fails strategy 1 (no `module.yaml` and `module-help.csv` at their common parent `skills/`), 2 (no `-setup` skill) and 4 ("Only use strategy 4 if ALL skills have module files"), and falls to `_synthesizeFallback`: a module coded `bmad-module-ultracode-goal` (the plugin name) with a synthesized help row for every listed skill. So `marketplace.json` lists `./skills/ultracode-goal` alone (pinned in `test/test-installation-components.js`); a BMAD plugin install copies only that skill, so it needs `npx bmad-module-ultracode-goal install` for the story skills and the `ucg-*` commands. Both files directly under `skills/` would satisfy strategy 1 instead, ahead of strategy 3, with the help catalog then read from `skills/module-help.csv`; that route is untried.
