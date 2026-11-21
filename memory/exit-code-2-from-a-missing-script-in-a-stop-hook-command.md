---
created: "2026-11-20 18:15"
session: "5b07f74c-c6ab-4198-89e2-8c44ba4ea42d"
---

# Exit code 2 from a missing script in a Stop hook command

A Stop hook command that names a script file exits 2 when that file is missing, whichever interpreter runs it: `python3 -I <path>` prints `python3: can't open file '<path>': [Errno 2] No such file or directory`, and `uv run --no-project <path>` prints `error: Failed to spawn` with `cause: No such file or directory (os error 2)`. Claude Code reads exit 2 from a Stop hook as a blocking error, so a hook left in a settings file after its script is moved or deleted would keep sessions from stopping (with a user-level hook, every session on the machine). Ending the command with `|| true` makes it exit 0 in that case. Both exit codes were measured in a shell on 2026-11-20, with Claude Code 2.1.329 installed; the block itself was not exercised and is taken from the hooks page of the Claude Code documentation. UCG wires its own Stop budget hook as `uv run '{skill-root}/scripts/hooks/budget_stop.py'` (`skills/ultracode-goal/references/preflight.md`), which exits 2 the same way when the skill folder is gone.
