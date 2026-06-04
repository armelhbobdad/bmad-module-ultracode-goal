# Module Setup

Standalone module self-registration for UltraCode Goal. This file is loaded when:

- The user passes `setup`, `configure`, or `register` as an argument to the skill
- The module is not yet registered in `{project-root}/_bmad/config.yaml` and the user accepts the skill's one-time self-registration offer

The npx installer (`npx bmad-module-ultracode-goal install`) performs its own registration, including the help catalog — this flow exists for installs that bypass it (plugin marketplace, manual copy) and for re-registration in an existing BMad project.

## Overview

Registers this standalone module into a project. Module identity (name, code) comes from `./assets/module.yaml` (resolved from the skill root). Writes three files:

- **`{project-root}/_bmad/config.yaml`** — shared project config: core settings at root (e.g. `output_folder`, `document_output_language`) plus an `ultracode-goal` section. User-only keys (`user_name`, `communication_language`) are **never** written here.
- **`{project-root}/_bmad/config.user.yaml`** — personal settings intended to be gitignored: `user_name` and `communication_language` live exclusively here.
- **The BMad help catalog** — registers the module's capability rows so `bmad-help` can route to it (targets below).

Both merge scripts use an anti-zombie pattern — existing entries for this module are removed before writing fresh ones, so re-running is idempotent and stale values never persist.

`{project-root}` is a **literal token** in config values — never substitute it with an actual path. It signals to the consuming LLM that the value is relative to the project root, not the skill root.

## Check Existing Config

1. Read `./assets/module.yaml` for module metadata (the `code` field, `ultracode-goal`, is the module identifier)
2. Check if `{project-root}/_bmad/config.yaml` exists — if an `ultracode-goal` section is already present, inform the user this is an update (re-registration)

If the user provides arguments (e.g. `accept all defaults`, `--headless`, or inline values like `user name is Armel`), map any provided values to config keys, use defaults for the rest, and skip interactive prompting. Still display the full confirmation summary at the end.

## Collect Configuration

UltraCode Goal has **no promptable module variables** — runtime knobs (budgets, branch prefix, allowlist, health check, Cross-Session Recall) live in the skill's `customize.toml` and are overridden per project in `_bmad/custom/ultracode-goal.toml`, not in `_bmad/config.yaml`.

Only collect core config, and only if no core keys exist yet in `config.yaml` or `config.user.yaml`:

- `user_name` (default: from `git config user.name`, else BMad) — written exclusively to `config.user.yaml`
- `communication_language` and `document_output_language` (default: English — ask as a single language question, both keys get the same answer) — `communication_language` written exclusively to `config.user.yaml`
- `output_folder` (default: `{project-root}/_bmad-output`) — written to `config.yaml` at root, shared across all modules

Show defaults in brackets and present all values together so the user can respond once with only the values they want to change. Never tell the user to "press enter" or "leave blank" — in a chat interface they must type something to respond.

## Write Files

Write a temp JSON file with the collected answers structured as `{"core": {...}, "module": {}}` (omit `core` if it already exists). Then run the merge scripts from the skill root:

```bash
uv run ./scripts/merge-config.py --config-path "{project-root}/_bmad/config.yaml" --user-config-path "{project-root}/_bmad/config.user.yaml" --module-yaml ./assets/module.yaml --answers {temp-file}
uv run ./scripts/merge-help-csv.py --target "{project-root}/_bmad/module-help.csv" --source ./assets/module-help.csv --module-yaml ./assets/module.yaml --module-code ultracode-goal
```

**Additionally**, if `{project-root}/_bmad/_config/bmad-help.csv` exists (the assembled catalog that the installed `bmad-help` skill loads), merge into it too so the module is immediately routable:

```bash
uv run ./scripts/merge-help-csv.py --target "{project-root}/_bmad/_config/bmad-help.csv" --source ./assets/module-help.csv --module-yaml ./assets/module.yaml --module-code ultracode-goal
```

`--module-yaml` makes the script synthesize the module's `_meta` docs row (from `name` + `docs_llms`) alongside the capability rows — the identical catalog state the npx installer produces.

The merge is positional and keeps the target's own header line, so the source's `after`/`before` column names and the assembled catalog's `preceded-by`/`followed-by` interoperate without translation.

All scripts output JSON to stdout with results. If any exits non-zero, surface the error and stop.

Run `uv run ./scripts/merge-config.py --help` or `uv run ./scripts/merge-help-csv.py --help` for full usage.

## Create Output Directories

After writing config, create any configured output directories that do not yet exist — at minimum `output_folder`. For filesystem operations only, resolve the `{project-root}` token to the actual project root; the values stored in the config files keep the literal token. Use `mkdir -p` or equivalent.

## Confirm

Use the script JSON output to display what was written — core values set, user settings written to `config.user.yaml` (`user_keys` in the result), help rows added per target (`rows_added` / `rows_removed`), fresh install vs update.

Then display the `module_greeting` from `./assets/module.yaml` to the user.

## Return to Skill

Setup is complete. Resume the main skill's normal activation flow — load config from the freshly written files and proceed with whatever the user originally intended.
