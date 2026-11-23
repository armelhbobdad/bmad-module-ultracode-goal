---
created: "2026-11-23 12:49"
session: "775f5088-65e5-4882-8e03-0238bc221ade"
---

# Parallel workflow agents overwriting each other's files in a shared scratchpad

Workflow agents get the session's scratchpad folder, and agents running in parallel use the same file names in it. On 2026-11-23 four build agents of one workflow each wrote `commit-msg.txt` and a quality log at the scratchpad root: the part 3 agent's message overwrote the others', one agent's message was lost outright, and two agents noticed only by reading another part's subject line in their own file. A later workflow whose prompt gave each agent its own folder (`<scratchpad>/review-<part>/`) and said "never write files elsewhere in the shared scratchpad" had no collision. Name a private subfolder per agent in every parallel workflow prompt, and have agents return anything that matters in their structured result rather than only in a file.
