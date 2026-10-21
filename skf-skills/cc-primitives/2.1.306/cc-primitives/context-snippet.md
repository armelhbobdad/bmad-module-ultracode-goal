[cc-primitives v2.1.306]|root: .claude/skills/cc-primitives/
|IMPORTANT: cc-primitives v2.1.306 — read SKILL.md before writing cc-primitives code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start} — claude -p "/goal CONDITION" runs the goal loop to completion; /goal is a prompt-based Stop hook
|api: /goal, --permission-mode, permissions.allow, autoMode, hooks.PreToolUse, hooks.Stop, SKILL.md frontmatter, .claude/agents, dynamic workflows, claude -p, --output-format
|key-types:{SKILL.md#key-types} — hook exit 0/2; permissionDecision allow|deny|ask|defer; Stop decision block + reason; modes default|acceptEdits|plan|auto|dontAsk|bypassPermissions
|gotchas: -p starts in default (Manual) mode when nothing sets a mode: no --permission-mode or --dangerously-skip-permissions and no permissions.defaultMode (v2.1.302+); autoMode, and defaultMode auto or bypassPermissions, are ignored in project/local settings; Stop hooks need stop_hook_active checks (8-block cap); a Bash allow rule doesn't match past a leading VAR= assignment of a variable that isn't known-safe
