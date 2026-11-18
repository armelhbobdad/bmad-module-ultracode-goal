---
created: "2026-10-18 21:11"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# Reference skill names with an area suffix instead of the bare tool name

Asked "What should the two new skills be called? Exporting creates `.claude/skills/<name>`, so a bare `graphify` would shadow your global `~/.claude/skills/graphify` tool skill.", the user chose "graphify-kg + iwe-kg (Recommended)" on 2026-10-18, so the reference skills for graphify and iwe carry the tool name plus an area suffix, like `tea-testarch` and `cc-primitives`, rather than the bare tool name. The reason is that an export creates `.claude/skills/<name>`, where a bare tool name would shadow a user-global tool skill of the same name. A future reference skill for a tool that also has a global skill needs a suffixed name for the same reason.
