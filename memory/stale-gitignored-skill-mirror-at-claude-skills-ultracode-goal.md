---
created: "2026-08-02 14:23"
session: "69c5ff6f-e98d-41a7-866b-444f3e6f1641"
---

# Stale gitignored skill mirror at .claude/skills/ultracode-goal

Claude Code in this repository loads the skill from `.claude/skills/ultracode-goal/`, a copy the installer writes (`target_dir: .claude/skills` in `tools/cli/lib/platform-codes.yaml`), and the whole `.claude` directory is gitignored (`git check-ignore -v .claude/skills/ultracode-goal/SKILL.md` shows the bare `.claude` entry). Nothing re-syncs that copy when `skills/ultracode-goal/` is edited, so it goes stale until `npm run ucg:update`; `npm run ucg:status` reports the drift as `out of sync` / `differs from this CLI's bundled source`. A session reading the skill through Claude Code then follows pre-fix instructions: on 2026-08-02 the mirror still told operators to use the inert `matcher="Bash"` hook form after the source had been fixed. `diff -rq skills/ultracode-goal .claude/skills/ultracode-goal` exposes it; [docs/getting-started.md](../docs/getting-started.md) says the installer copy and the clone copy are the same files but not that the copy drifts.
