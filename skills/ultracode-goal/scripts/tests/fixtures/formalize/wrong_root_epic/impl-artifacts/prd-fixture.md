# PRD — MISPLACED under impl-artifacts (wrong root)

This PRD sits under impl-artifacts, not planning-artifacts. Resolution honors the
per-root flag, so `prd_present` must read false: the planning-artifacts root has
no PRD.
