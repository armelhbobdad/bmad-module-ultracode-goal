## Epic-complete hook

This hook fires **only when the Epic-level gate verdict was `advance`** (a `complete` run). On a `blocked` run — a story escalated and the Epic never advanced — skip this step entirely; a "notify success" command must not fire on a blocked Epic.

When the Epic advanced, run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow.on_epic_complete`

If the resolved `{workflow.on_epic_complete}` is non-empty, follow it as the final terminal instruction (a prompt to run or a shell command) before exiting.

