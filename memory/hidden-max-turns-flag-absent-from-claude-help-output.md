---
created: "2026-10-16 18:35"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# Hidden --max-turns flag absent from claude --help output

Claude Code's print-mode `--max-turns <turns>` flag exists but is declared with `.hideHelp()`, so `claude --help | grep max-turns` prints nothing. `skills/ultracode-goal/scripts/drive_epic.py` carried a "verified" claim that there is no `--max-turns` flag, based on a `--help` read on 2.1.220, until a review on 2026-10-16 found the flag in the 2.1.301 binary (`strings "$(readlink -f "$(which claude)")" | grep -- --max-turns`) and in anthropics/claude-code issue #16963. Never treat `--help` output as proof that a Claude Code flag is absent: check the cc-primitives reference (its headless-and-cli page lists `--max-turns`) or the binary.
