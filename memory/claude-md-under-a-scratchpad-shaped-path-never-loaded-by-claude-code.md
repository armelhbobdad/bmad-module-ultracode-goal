---
created: "2026-11-19 01:21"
session: "045508f3-51e8-4dfb-9e6e-d39301ebd8b2"
---

# CLAUDE.md under a scratchpad-shaped path never loaded by Claude Code

Claude Code 2.1.327 refuses to load a CLAUDE.md that sits in, or links into, a session scratchpad or any folder laid out like one (`claude/<project>/<session id>/scratchpad`), and says so only in the `--debug` log: "[CLAUDE.md] not loading .../p8/repo/CLAUDE.md: it, or what it links to, is in a session's scratchpad or a folder laid out like one (claude/<project>/<session id>/scratchpad). To load it, move it out of that folder." It surfaced when headless `claude -p` probes ran in throwaway git repos under `/tmp/claude-1000/<project>/<session id>/scratchpad/`: the throwaway repo's own CLAUDE.md silently never loaded, so a first-request token count with and without it compared two identical prompts. A throwaway repo that has to load its own CLAUDE.md (a CLAUDE.md token measurement, a `claudeMdExcludes` or `omitClaudeMd` test) must live outside such a folder. The workaround used there loaded this repository's CLAUDE.md read-only with `--add-dir <repo>` and `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`; the transcript's instructions attachment then listed it as type `Project`, but the same flag also added this repository's skills to the skill listing.
