---
created: "2026-10-21 00:13"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# Claude Code allow rules stop matching at an unknown leading assignment

Claude Code strips the wrappers `timeout`, `time`, `nice`, `nohup` and `stdbuf` (plus `command`, `builtin`, `noglob` and bare `xargs`) and a leading assignment of certain known-safe environment variables before it matches a Bash allow rule, but "an allow rule won't match past an assignment of any other variable" (<https://code.claude.com/docs/en/permissions>); deny and ask rules match past any assignment. Probed on Claude Code 2.1.304 headless (`claude -p --setting-sources project --permission-mode default --settings '{"permissions":{"allow":[RULE]}}'`) with `UCG_PROBE_VAR=1 timeout 5 touch marker.txt`: the exact rule and the same rule plus a trailing ` *` allowed it, while `Bash(touch *)` and `Bash(timeout 5 touch *)` denied it, so `timeout` is no longer stripped once an unknown assignment comes first; `Bash(touch *)` did allow `timeout 5 touch marker.txt`. This is why Finalize's `GRAPHIFY_NO_AUTO_REFRESH=1 timeout 300 graphify update .` (PR #150) is not approved by an `allowlist_commands` entry for the bare binary `graphify` (written by preflight as a rule like `Bash(graphify:*)`): the allowlist entry must be the whole line. Under Auto Mode an unmatched command goes to the permission classifier instead of a prompt, so the outcome there is the classifier's call. Prefix any command meant to be allowlisted with a variable assignment only when the matching rule starts with that same assignment.
