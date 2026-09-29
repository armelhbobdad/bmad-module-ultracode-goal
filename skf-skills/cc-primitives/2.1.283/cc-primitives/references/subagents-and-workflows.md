# Subagents and dynamic workflows

## Contents

- [Subagent definitions](#subagent-definitions)
- [Delegation and execution](#delegation-and-execution)
- [Limits](#limits)
- [Dynamic workflows](#dynamic-workflows)
- [Workflow limits and cost](#workflow-limits-and-cost)

## Subagent definitions

- Each subagent has its own context window, system prompt, tools and permissions; it gets its own system prompt plus basic environment details, not the Claude Code system prompt. [EXT:https://code.claude.com/docs/en/sub-agents]
- Priority: managed (1), `--agents` JSON (2, session only), `.claude/agents/` (3, walked up from the working directory), `~/.claude/agents/` (4), plugin `agents/` (5); identity comes from the `name` field. [EXT:https://code.claude.com/docs/en/sub-agents]
- Frontmatter: `name`, `description` required; `tools` (allowlist, default inherit), `disallowedTools` (applied first), `model` (sonnet, opus, haiku, fable, full ID or inherit), `permissionMode`, `maxTurns`, `skills` (preloaded), `memory` (user/project/local), `background`, `omitClaudeMd`, `effort`, `isolation: worktree`. [EXT:https://code.claude.com/docs/en/sub-agents]
- In `--agents` JSON each key is an agent name; `prompt` is the system prompt. [EXT:https://code.claude.com/docs/en/sub-agents]
- Unset `permissionMode` inherits the parent's; under bypass/acceptEdits/auto the subagent's mode is ignored. [EXT:https://code.claude.com/docs/en/sub-agents]
- Omit `Agent` from `tools` to stop a subagent spawning subagents; a fixed set of tools (including `AskUserQuestion` and `Workflow`) is always removed from subagents. [EXT:https://code.claude.com/docs/en/sub-agents]

## Delegation and execution

- Claude delegates by `description`; an @-mention guarantees the named subagent runs; `claude --agent <name>` makes the main thread that agent. [EXT:https://code.claude.com/docs/en/sub-agents]
- Foreground subagents block; with fork mode (default interactive) spawns run in the background and report via a completion notification; fork mode is off in `-p` and the SDK. [EXT:https://code.claude.com/docs/en/sub-agents]
- Non-fork subagents start with no conversation history — restate rules in the delegation prompt; a fork inherits the conversation but cannot fork again. [EXT:https://code.claude.com/docs/en/sub-agents]
- Resume with SendMessage by agent ID or name; Explore and Plan are one-shot. [EXT:https://code.claude.com/docs/en/sub-agents]
- No agent message counts as user approval. [EXT:https://code.claude.com/docs/en/sub-agents]
- Transcripts: `~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl`. [EXT:https://code.claude.com/docs/en/sub-agents]
- Disable one with `permissions.deny` `Agent(subagent-name)`; Stop hooks in frontmatter become SubagentStop. [EXT:https://code.claude.com/docs/en/sub-agents]

## Limits

Nesting up to three layers (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, 1 disables); 20 concurrent (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`; ultracode exempt); no total limit; startup warning over 15,000 tokens of descriptions; `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` forces one model. [EXT:https://code.claude.com/docs/en/sub-agents]

## Dynamic workflows

- A JavaScript script, written by Claude, that orchestrates many subagents in the background; only the final answer returns to Claude's context. [EXT:https://code.claude.com/docs/en/workflows]
- Opt in with the keyword `ultracode` in a typed prompt (not from `-p`, scheduled tasks or webhooks); `claude --effort ultracode` or the `ultracode` setting; Pro plans enable it in `/config`. [EXT:https://code.claude.com/docs/en/workflows]
- `/workflows` lists runs; saved workflows live in `.claude/workflows/` or `~/.claude/workflows/` and read `args`. [EXT:https://code.claude.com/docs/en/workflows]
- Script API: `meta` first (literal with `name`, `description`), `agent()` (optionally with `schema`), `parallel()`, `pipeline()`, `phase()`, `log()`; `meta.phases` titles must match `phase()` calls. [EXT:https://code.claude.com/docs/en/workflows]
- `agent()` resolves to null when stopped or on unrecoverable errors. [EXT:https://code.claude.com/docs/en/workflows]
- Permissions: workflow agents get normal checks; approval prompt on first launch in auto mode, never in `-p`/SDK; allow rule `Workflow` or `Workflow(<name>)`. [EXT:https://code.claude.com/docs/en/workflows]
- Resume: paused runs resume from `/workflows`; a relaunch replays completed agents until the first changed prompt; resumable within the same session. [EXT:https://code.claude.com/docs/en/workflows]

## Workflow limits and cost

No mid-run user input, no direct filesystem/shell access, no `import()`, no `Date.now()`/`Math.random()`; 16 concurrent agents by default (`CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`, 1–256); ≤4,096 items per call; ≤1,000 agents per run; a Large workflow warning above 25 agents or 1.5M projected tokens; `disableWorkflows` / `CLAUDE_CODE_DISABLE_WORKFLOWS=1` turn workflows off. [EXT:https://code.claude.com/docs/en/workflows]
