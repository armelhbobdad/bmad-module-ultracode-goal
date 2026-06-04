# UltraCode Goal (UCG)

Run a BMAD Epic autonomously to a machine-checked Definition-of-Done.

UltraCode Goal is a BMAD module that orchestrates the BMAD epic toolbox, the TEA Test Architect quality gates, and Claude Code primitives (`/goal`, Auto Mode, Auto Memory, hooks, worktree isolation) to deliver an Epic unattended. Completion is decided by a deterministic gate script reading TEA's `gate-decision.json` — never by the model's own judgment.

The skill lives at [`skills/ultracode-goal/`](skills/ultracode-goal/SKILL.md). Documentation is in [`docs/`](docs/index.md).

## License

[MIT](LICENSE)
