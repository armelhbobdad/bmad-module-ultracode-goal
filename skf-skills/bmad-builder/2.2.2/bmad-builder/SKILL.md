---
name: bmad-builder
description: >
  Describes the BMad Builder v2.2.2 module (code bmb): the skills it registers under skills/ —
  bmad-agent-builder, bmad-workflow-builder, bmad-module-builder, bmad-eval-runner and
  bmad-bmb-setup — with their menu codes, actions, arguments and outputs from module-help.csv,
  and the two config keys from module.yaml. Use when choosing which BMad Builder skill builds,
  analyzes, converts, scaffolds or validates an agent, workflow or module, or when locating where
  its outputs and reports are written. Not for the BMAD Method BMM workflows or the installer.
---

# bmad-builder

## Overview
- **Package:** bmad-builder
- **Repository:** https://github.com/bmad-code-org/bmad-builder
- **Version / ref:** 2.2.2 (tag `v2.2.2`, commit `4a1422274a2acb0fb0ec0511753da6263948f072`)
- **Language:** javascript (package manifest); the skills' helper scripts are Python
- **Scope:** `skills/`
- **Source Authority:** community
- **Generated:** 2026-09-28

## Description

A BMad Core expansion module that guides users through the creation of Modules, Workflows and Agents (package.json `description`). The README presents it as the pipeline to create AI modules — agents with persistent memory, guided workflows, or full module ecosystems — built on the Agent Skills open standard and distributed through the BMad Marketplace or any compliant marketplace.

`skills/module.yaml` registers the module as code `bmb`, name "BMad Builder", description "Standard Skill Compliant Factory for BMad Agents, Workflows and Modules", `module_version: 1.0.0`, `default_selected: false`. The npm package publishes `skills/`, `.claude-plugin/` and `CHANGELOG.md` (package.json `files`); it has no `main` entry point.

## Key Exports

The module's public surface is its skills (folder name = frontmatter `name`):

| Skill | Type | Description (from its SKILL.md frontmatter) |
|-------|------|---------------------------------------------|
| `bmad-agent-builder` | skill | Builds, edits or analyzes Agent Skills through conversational discovery. |
| `bmad-workflow-builder` | skill | Builds, edits, and analyzes workflows and skills. |
| `bmad-module-builder` | skill | Plans, creates, and validates BMad modules. |
| `bmad-eval-runner` | skill | Runs a skill's evals and reports results (evaluate, benchmark, validate triggers, optimize a description, grade outputs). |
| `bmad-bmb-setup` | skill | Sets up the BMad Builder module in a project. |

## Usage Patterns

Capabilities registered in `skills/module-help.csv` (all phase `anytime`, none required):

| Code | Skill : action | Args | Output → location |
|------|----------------|------|-------------------|
| SB | `bmad-bmb-setup` : configure | `-H` headless; inline values skip prompts | `config.yaml` and `config.user.yaml` → `{project-root}/_bmad` |
| BA | `bmad-agent-builder` : build-process | `-H`; `description` (initial agent concept); `path` (existing agent to edit or rebuild) | agent skill → `bmad_builder_output_folder` |
| AA | `bmad-agent-builder` : quality-analysis | `-H`; `path` (agent to analyze) | quality report → `bmad_builder_reports` |
| BW | `bmad-workflow-builder` : build-process | `-H`; `description`; `path` | workflow skill → `bmad_builder_output_folder` |
| AW | `bmad-workflow-builder` : quality-analysis | `-H`; `path` (skill to analyze) | quality report → `bmad_builder_reports` |
| CW | `bmad-workflow-builder` : convert-process | `--convert` (path or URL to source skill); `-H` | converted skill + comparison report → `bmad_builder_reports` |
| IM | `bmad-module-builder` : ideate-module | `description` (initial module idea) | module plan → `bmad_builder_reports` |
| CM | `bmad-module-builder` : create-module | `-H`; `path` (skills folder or single SKILL.md) | setup skill → `bmad_builder_output_folder` |
| VM | `bmad-module-builder` : validate-module | `-H`; `path` (module or skill to validate) | validation report → `bmad_builder_reports` |

Registered sequences (`preceded-by` / `followed-by`): BA → AA and BW → AW (build then quality analysis); IM → CM → VM (ideate, create, validate a module). A `_meta` row points to `https://bmad-builder-docs.bmad-method.org/llms.txt`.

## Configuration

`skills/module.yaml` prompts for two keys:

| Key | Prompt | Default | Result |
|-----|--------|---------|--------|
| `bmad_builder_output_folder` | Where should your custom output (agent, workflow, module config) be saved? | `{project-root}/skills` | `{project-root}/{value}` |
| `bmad_builder_reports` | Output for Evals, Test, Quality and Planning Reports? | `{project-root}/skills/reports` | `{project-root}/{value}` |

## Scripts & Assets

This package may include scripts and assets (`skills/*/scripts/`, `skills/*/assets/`, e.g. `bmad-module-builder/scripts/validate-module.py`, `bmad-bmb-setup/scripts/merge-help-csv.py`). Run create-skill for full extraction with provenance tracking.

## Notes

- Quick-tier, best-effort skill from surface-level reading of `package.json`, `README.md`, `skills/module.yaml`, `skills/module-help.csv` and each skill's `SKILL.md` frontmatter at tag `v2.2.2`; skill bodies, step files and scripts were not extracted.
- The JavaScript export scanner found no exports (no `main` entry point, no JS files under `skills/`); the Key Exports table lists the registered skills instead.
- Full documentation: https://bmad-builder-docs.bmad-method.org
