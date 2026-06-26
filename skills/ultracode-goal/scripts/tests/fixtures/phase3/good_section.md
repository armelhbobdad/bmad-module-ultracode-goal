## 2026-01-01 — Phase-3 evidence gate (FIXTURE — canonical valid section, mutation base)

A self-contained VALID Phase-3 evidence-gate section used only as the base for the parametrized
anti-vacuous mutations in test_phase3_evidence_gate.py. It is intentionally decoupled from the real
skills/ultracode-goal/.decision-log.md section (positives run against the real log); this fixture only
needs to be a valid section that each mutation breaks. Grounding cites the real on-disk architecture path
(`_bmad-output/planning-artifacts/architecture-ucg-ready-planning.md:57`, `:132`) and the PRD
(`_bmad-output/planning-artifacts/prd-ucg-ready-planning.md`); no epics-file path, no phantom story id.

**Downstream-map (self-declared, intra-artifact):**

| fragment | downstream shaping work (deferred) |
|---|---|
| bmad-dev-story | dev-story trust-the-gate guardrail SHAPING fragment |
| bmad-code-review | code-review adversarial-layers guidance SHAPING fragment |
| bmad-sprint-planning | sprint-planning legal-sprint-status.yaml guardrail SHAPING fragment (SHAPING only) |

cut-ability: the clean-partition / cut-ability PROOF across all three fragments — each removable with zero
dangling references — is the future obligation any promotion must satisfy; not recorded here.

### Promotion gate — bmad-dev-story
status: DEFERRED — not built (pending field evidence)
decision_needed: cut-vs-build — should the dev-story trust-the-gate guardrail SHAPING fragment be authored
  and wired, or cut outright? Open until a real observed dev-story need is attributed in this field.
attribution_rubric: satisfied ONLY by a decision_needed entry that names a concrete, real observed
  dev-story artifact shape — per the AD-4 explicit-attribution rubric. A bare question that names no
  dev-story artifact shape does NOT satisfy it.
nfr8_collision_check: co-equal, possibly-terminal reason distinct from YAGNI — promote ONLY if landing this
  fragment in persistent_facts does not duplicate, override, or fight the runtime enforcement held by
  preflight, the PreToolUse/Stop hooks, and gate_eval.py. Failing it is a CUT outcome (terminal — not
  promoted), never a defer-and-revisit.
promotion_trigger: a named dev-story attribution_rubric match AND a passed nfr8_collision_check — BOTH
  required. Back-reference: downstream-map row bmad-dev-story.

### Promotion gate — bmad-code-review
status: DEFERRED — not built (pending field evidence)
decision_needed: cut-vs-build — should the code-review adversarial-layers guidance SHAPING fragment be
  authored and wired, or cut outright? Open until a real observed code-review need is attributed here.
attribution_rubric: satisfied ONLY by a decision_needed entry that names a concrete, real observed
  code-review (adversarial-layers) artifact shape — per the AD-4 explicit-attribution rubric. A generic
  question that names no code-review artifact shape does NOT satisfy it.
nfr8_collision_check: co-equal, possibly-terminal reason distinct from YAGNI — promote ONLY if shaping
  bmad-code-review through persistent_facts does not duplicate, override, or fight the runtime enforcement
  held by preflight, the PreToolUse/Stop hooks, and gate_eval.py. Failing it is a CUT outcome (terminal —
  not promoted), never a defer-and-revisit.
promotion_trigger: a named code-review attribution_rubric match AND a passed nfr8_collision_check — BOTH
  required. Back-reference: downstream-map row bmad-code-review.

### Promotion gate — bmad-sprint-planning
status: DEFERRED — not built (pending field evidence)
decision_needed: cut-vs-build — should the sprint-planning legal-sprint-status.yaml guardrail SHAPING
  fragment ONLY be authored and wired, or cut outright? SCOPE — the SHAPING fragment alone, NOT the
  Phase-1/2 readiness check. Open until a real observed sprint-planning SHAPING need is attributed here.
attribution_rubric: satisfied ONLY by a decision_needed entry that names a concrete, real observed
  sprint-planning / sprint-status.yaml SHAPING artifact shape — per the AD-4 explicit-attribution rubric.
  A question that names no sprint-status.yaml artifact shape does NOT satisfy it.
nfr8_collision_check: co-equal, possibly-terminal reason distinct from YAGNI — promote ONLY if shaping
  bmad-sprint-planning through persistent_facts does not duplicate, override, or fight the runtime
  enforcement held by preflight, the PreToolUse/Stop hooks, and gate_eval.py. Failing it is a CUT outcome
  (terminal — not promoted), never a defer-and-revisit.
promotion_trigger: a named sprint-planning attribution_rubric match AND a passed nfr8_collision_check —
  BOTH required. Back-reference: downstream-map row bmad-sprint-planning.
