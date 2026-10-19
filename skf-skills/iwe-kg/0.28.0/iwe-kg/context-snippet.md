[iwe-kg v0.28.0]|root: .claude/skills/iwe-kg/
|IMPORTANT: iwe-kg v0.28.0 — read SKILL.md before writing iwe-kg code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start} — iwe find --lexical "TERMS" --limit 5; iwe retrieve -k KEY; iwe create KEY --strict --if-exists fail --content -
|key-types:{SKILL.md#key-types} — config version 4 ([workspace], deny_unknown_fields); exit 2 = already initialized/enabled, --strict schema block, missing/violated expect guard, malformed argument or clap usage error (read stderr); knobs distill.max_chunk_size 25000/max_proposals 5/remind_after_days 7
|gotchas: .iwe/config.toml is read from cwd only and rewritten in place to version 4 (docs/config.md still says 3); iwe internal claude is hidden and unstable; iwec/iwes serve their start directory (plus workspace.path); memory is on only when key MEMORY exists
