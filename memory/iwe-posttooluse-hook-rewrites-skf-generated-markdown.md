---
created: "2026-09-28 20:38"
session: "12efedd0-eb20-46bb-99c5-c36b6ed0f15d"
---

# IWE PostToolUse hook rewrites SKF-generated markdown

During gap-driven `skf-update-skill` runs on cc-primitives and tea-testarch on 2026-09-28, the IWE plugin's PostToolUse hook (`iwe internal claude hook post-tool`, matcher `Write|Edit|MultiEdit|Bash` in the plugin's `hooks/hooks.json`) rewrote the whole `SKILL.md` right after merge §6b's Edit call. It deleted the `[MANUAL]` blocks, re-padded the tables, changed fence openers from ```` ```bash ```` to ```` ``` bash ```` and merged the `## CORRECTION` lines. The IWE library is the repo root (`.iwe/config.toml` has `[library] path = ""`), so markdown under `skf-skills/` and `forge-data/` is in its reach. The runners recovered by re-issuing the merged content through the shell and `skf-atomic-write.py`, which the hook left alone, then confirmed with `diff -u` against a pre-run snapshot and `manual-verify` that only the intended line had changed. Any SKF workflow here that writes `.md` artifacts with the Edit or Write tool is exposed: snapshot the skill package before a run, diff it after, and write SKF markdown through the shell. The matching SKF health-check finding `fp-47c32b2` was ruled out of scope in the 2026-09-29 triage and never filed upstream: the rewrite comes from this local hook, not from SKF, and update-skill `write.md`'s manual-verify HALT already catches lost `[MANUAL]` blocks.
