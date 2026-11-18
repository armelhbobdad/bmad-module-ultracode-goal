---
created: "2026-10-16 14:55"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# Ultracode effort indistinguishable from xhigh in env and transcripts

A Claude Code session launched with ultracode effort (`claude -p ... --effort ultracode`, or `/effort ultracode`, which answers "Ultracode on (this session only)... Effort stays xhigh.") reports `CLAUDE_EFFORT=xhigh`, and every API request in its transcript carries `output_config.effort: "xhigh"`, exactly as a plain xhigh session does. So nothing on disk proves a UCG run had the ultracode effort that the preflight hard gate requires: the run log records it as not machine-checkable, and the README Tested-with table dropped an "ultracode effort" claim for that reason. Claim ultracode effort for a run only when the operator knows how the session was launched.
