---
created: "2026-06-04 21:57"
session: "18a523d3-45ac-4b3e-b7d8-bb5f184840e1"
---

# scan-scripts.py sys.exit detection blind spot

BMAD's `scan-scripts.py` (installed at `.claude/skills/bmad-workflow-builder/scripts/scan-scripts.py`, gitignored) flagged `skills/ultracode-goal/scripts/health_check_fp.py` with "No sys.exit() calls — may not return meaningful exit codes" while its entrypoint was `raise SystemExit(main())`. The scanner's AST walk only sets `has_sys_exit` for a call to `.exit`/`exit`, so `raise SystemExit(...)` is invisible to it (the check is file-wide and fires only for scripts over 20 lines). Switching to `sys.exit(main())` cleared it, and every script under `skills/ultracode-goal/scripts/` now uses that form; a new script should too, so the bmad-workflow-builder quality check scans clean.
