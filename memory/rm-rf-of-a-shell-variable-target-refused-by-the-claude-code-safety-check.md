---
created: "2026-11-15 19:43"
session: "36d1b26b-c2ef-451e-ae63-24abfb0b9fe2"
---

# rm -rf of a shell-variable target refused by the Claude Code safety check

Rebuilding the rsync scratch copy that the BMad Builder quality-gate prepass scans (the copy that excludes `scripts/tests`, `.analysis` and `.memlog.md`) with an `rm -rf "$U"`-style cleanup is refused before it runs: "Permission for this command was denied by a built-in Claude Code safety check, not by the user ... a target it cannot resolve, such as a shell variable that, if unset or empty, turns this into `rm -rf /`", and the message says not to work around it by splitting or scripting the removal. It hit twice in one session (the UCG gate rounds and Skill Forge gate round 1, 2026-11-15), costing a round trip each time. Do not remove: write each rebuilt copy to a new timestamped folder under the session scratchpad (or name a literal path), and leave stale files in place. Related: [[scan-path-standards-utf8-crash-on-the-utf16-formalize-fixture]].
