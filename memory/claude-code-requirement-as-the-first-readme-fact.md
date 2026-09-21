---
created: "2026-06-04 10:08"
session: "d8b3ff6b-9cc2-4e88-9519-91e7549ab6bf"
---

# Claude Code requirement as the first README fact

UCG runs only under Claude Code, and the user made saying so a README rule: "users should be aware it only works for claude code users. It is one of the first information user should know when he reads the readme". Commit adac4e0 ("docs: state the Claude Code requirement up front") put it in three places: the "Requires Claude Code" badge first among the badges, the bold lead sentence right after them ("Built for Claude Code, and only Claude Code."), and Claude Code first in the Install requirements line. The same commit made it the top prerequisites row of docs/getting-started.md. Any README rewrite keeps the badge and the bold lead within the first ~25 lines, before the problem and feature sections; `grep -n 'only Claude Code\|Requires Claude Code' README.md docs/getting-started.md` is the check. The docs landing page (docs/index.md) lost its matching opening sentence in the Starlight rewrite f824cd4 and has not had it back.
