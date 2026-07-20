## 3. Semantic intervention scan (the part the script cannot do)

The script counts mechanical facts; it cannot read a PRD and tell that a product decision is still open, or read an ADR and tell that an architecture choice is unresolved. That judgment happens now — but **not in your context**. The artifacts this scan reads are the same multi-thousand-token corpus the run is about to delegate to sub-skills; reading them here would make the conductor carry it through the entire unattended Execute phase (Stage 1's "do not open story or planning files for deep reading" rule exists for exactly this trap).

**Delegate the read to one throwaway subagent.** Spawn a single subagent with the artifact paths noted in Stage 1 (the Epic's stories, PRD, ADR/architecture) and — when Stage 1 Cross-Session Recall produced advisories — the typed `records`/`recurrence` output of the Stage 1 filter, as prior-failure **hypotheses to check** (attributed and advisory; re-use that filtered output, never a fresh MCP call). Instruct it to read the corpus and hunt **undecided product or architecture decisions** that an autonomous run would have to *guess*:

- open questions, "TBD" / "TODO: decide" / "to be determined" / "(?)" placeholders on a load-bearing requirement,
- contradictions between PRD and ADR,
- acceptance criteria that presuppose a decision no artifact actually makes,
- a story whose "done" is undefinable from the artifacts.

**Second hypothesis stream — seed the formalize candidates.** Pass that SAME single throwaway subagent a second set of targeted hypotheses alongside the recall advisories: `formalize_check.py`'s `judgment_candidates[]` (from step 1b) as a **`source:line` list** — the references only, never the inlined artifact bodies — so the subagent confirms machine-flagged candidates *instead of scanning blind*. The kernel only *flags*; the throwaway subagent *decides* — it must **confirm-or-clear** each seeded `judgment_candidate` into `reds` or `concerns`, never recording one as a RED unprompted. Fail-closed: a `judgment_candidate` the subagent can neither confirm nor clear **defaults to RED** (JUDGMENT), mirroring `gate_eval.py`'s `nfr_status is None → failing`. This adds zero net subagent and zero net conductor context — the same single spawn, the same discarded-context discipline, and the same three-key return object below.

The subagent must return **ONLY this object — no prose, no document quotes beyond the one-line evidence fields**, so you hold the findings while the corpus stays in its discarded context:

```json
{"reds": [{"source": "<artifact path:line>",
           "kind": "undecided-product|undecided-architecture|contradiction|undefinable-done",
           "decision_needed": "<the exact decision a human must make>",
           "evidence": "<one quoted line>"}],
 "concerns": [{"source": "<artifact path:line>", "note": "<cosmetic / non-blocking gap, one line>"}],
 "advisories_checked": [{"sig": "<advisory id>", "status": "recurred|not-observed|unknown"}]}
```

**Retrieving the result on an async-spawn platform.** The contract above assumes a *synchronous* spawn whose return text reaches you directly. If this run spawns the subagent as a **background teammate** instead, its plain-text return is **not** routed back to the conductor — so additionally instruct it to persist this *same* object to a **run-scoped** file — `{workflow.implementation_artifacts}/.preflight-scan-<run-id>.json`, using the `<run-id>` minted in Stage 1 (`epic-<id>-<UTC yyyymmddThhmmssZ>`) so a **prior** run's scan sitting at a shared path can never be misread as this one's — and read *that* file back, or message you the object explicitly. Because the async write may not have landed yet, wait for **this** run's file to appear and never fall back to an older or differently-named one; before feeding the object into the step-4 hard gate, confirm it is this run's scan (its findings reference this Epic, not a prior one). The discarded-context discipline is unchanged: you ingest only the object, never the corpus, which stays discarded in the subagent's context. (The same retrieval rule applies to any subagent this run spawns asynchronously — e.g. a background-delegated Execute `bmad-dev-story` or a gate TEA sub-skill: route its structured result through a file or an explicit message, never an unrouted plain-text return.)

Every `reds` entry is **RED** — it cannot be auto-remediated, because the fix is a human decision, and an unattended run guessing it produces confidently wrong work. A purely cosmetic gap belongs in `concerns`, never RED; recall-derived hypotheses are attributed under `advisories_checked` and are never themselves RED and never block launch. Record each RED finding with its source and the exact decision needed in `.decision-log.md`.

