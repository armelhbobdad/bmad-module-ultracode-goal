---
created: "2026-11-18 20:41"
session: "5b07f74c-c6ab-4198-89e2-8c44ba4ea42d"
---

# Workflow subagents refused report-file writes

A Workflow agent told to write its report to a file (`.../scratchpad/f2-causes/report.md`) had the Write refused by the harness: "Subagents should return findings as text, not write report files". That agent did not route around the refusal and carried the report in its structured return, so a script that kept only a `report_path` would have lost it. Write Workflow scripts so each agent returns its full findings through its `schema` result or final text. The refusal is aimed at report files: agents in later Workflow runs still built fixture repos and logs under the scratchpad through Bash.
