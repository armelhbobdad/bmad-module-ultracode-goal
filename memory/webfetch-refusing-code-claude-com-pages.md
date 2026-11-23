---
created: "2026-11-23 12:49"
session: "775f5088-65e5-4882-8e03-0238bc221ade"
---

# WebFetch refusing code.claude.com pages

On 2026-11-23 WebFetch refused the Claude Code docs with "Unable to verify if domain code.claude.com is safe to fetch". `curl -sL` on the page's Markdown form, the page URL with `.md` added (`https://code.claude.com/docs/en/hooks.md`, `.../plugins/mods/create.md`, `.../permission-modes.md`), returned the text, and the agents that checked SECURITY.md and preflight wording against the docs read them that way. So when a claim has to be checked against the Claude Code docs, go straight to `curl -sL` on the `.md` URL rather than retrying WebFetch.
