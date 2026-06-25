---
title: Portability-Honesty Operator Benchmark
description: The AC5 operator-benchmark rubric for story 1.11 — a non-author installs UCG on a non-Claude-Code target, reads ONLY the printed gap line plus the README/docs portability paragraph, and answers three questions that test whether the honest-degradation story actually communicates. Pass bar is definitional (every reviewer all-three-correct, zero cross-provider inference); the reviewer count is recorded as observed data, never pre-authored.
---

# Portability-Honesty Operator Benchmark

This is the story-1.11 AC5 operator gate. Whether the degraded non-Claude-Code
experience is *honest to a human* — not merely denylist-clean — is a human
judgment, so it is measured by an operator benchmark rather than a static
assertion. Test Suite 6 in `test/test-installation-components.js` already proves
the gap line prints exactly once, that the gap-line constant and the README/docs
paragraphs are forbidden-phrase-clean and carry all three required markers, that
the portable half lands, and that no forked envelope is introduced. This
benchmark covers the one thing those checks cannot: that a real operator reading
only the surfaced output reaches the correct understanding without external help.

## Setup (what the reviewer does)

1. The reviewer is a **non-author**: someone who did not write the gap line, the
   README/docs paragraph, or this rubric.
2. The reviewer performs a UCG install against a **non-Claude-Code** target
   (any IDE selection that excludes `claude-code`), with UCG-awareness enabled
   so Step 6b runs and prints its output.
3. The reviewer reads **ONLY** two things: (a) the gap line printed at install,
   and (b) the README portability paragraph plus the `docs/how-it-works.md`
   "Portability" paragraph. No source code, no architecture docs, no help from
   the author.
4. The reviewer answers the three-question rubric below from that reading alone.

## The rubric (three questions)

Each question has one correct answer. The reviewer answers all three from the
printed output + paragraph only.

- **(i) Is autonomous / preflight enforcement available on this install?**
  Correct answer: **No.** The FR-7 preflight enforcement that fires the
  readiness gate automatically at run start is a Claude Code-only capability and
  is unavailable on this non-Claude-Code target.

- **(ii) Does `/ucg-formalize` still work here, and how?**
  Correct answer: **Yes — as a manual, on-demand verdict the operator invokes
  themselves.** The standalone gate still installs and runs; only its automatic
  invocation is absent.

- **(iii) Is any cross-provider enforcement being claimed?**
  Correct answer: **No.** The text claims no automatic/cross-provider
  enforcement on a provider that cannot run it; it documents the gap plainly and
  scopes the automatic invocation to Claude Code only.

## Pass bar (definitional — AD-5, do not pre-author a cutoff)

Per AD-5 ("record the result, do not pre-author a pass-rate cutoff") and NFR-9
(provenance), the pass bar is **definitional, not a guessed percentage and not a
fixed panel size**:

- **Every** reviewer who runs the benchmark answers **all three** questions
  correctly, **and**
- **zero** reviewer infers any cross-provider enforcement claim from the text.

That is 100% by construction — it is the definition of the honest-degradation
contract being met, not a chosen threshold. No minimum reviewer count is frozen,
because no AD or NFR prescribes one. The **reviewer count is an observed datum**
recorded from the real run (below), never a pre-authored panel size.

### Anti-vacuous note

This rubric measures whether the honesty content *communicates*, not that any
text was printed. If the gap line and paragraph were replaced with a bare
`installed.` (stripping the Claude-Code / manual-only honesty content), reviewers
would be unable to answer question (i) or (ii) — which is exactly the failure the
benchmark is designed to catch.

## `.decision-log.md` recording template (NFR-9 provenance)

When a reviewer runs the benchmark, record the result to the story's run
`.decision-log.md` using the block below. The reviewer count and per-reviewer
answers are observed data captured from the real run — fill in what actually
happened; do not invent reviewers or pre-size the panel.

```markdown
## AC5 Operator Benchmark — Portability-Honesty (story 1.11)

- Date: <YYYY-MM-DD>
- Install target (non-Claude-Code IDE selection): <e.g. cursor, opencode>
- Surfaced output read by reviewers: gap line + README portability paragraph + docs/how-it-works.md "Portability" paragraph
- Provenance: <commit SHA / install-manifest path the run was taken from>

### Reviewers (observed count: <N>)

| Reviewer | Q(i) enforcement unavailable? | Q(ii) /ucg-formalize manual on-demand? | Q(iii) zero cross-provider claim inferred? | All-three-correct |
| -------- | ----------------------------- | -------------------------------------- | ------------------------------------------ | ----------------- |
| <name>   | <Yes/No + correct?>           | <Yes/No + correct?>                    | <Yes/No + correct?>                        | <PASS/FAIL>       |

### Verdict

- Every reviewer all-three-correct: <Yes/No>
- Zero reviewer inferred a cross-provider enforcement claim: <Yes/No>
- Result: <PASS / FAIL>  (PASS only when both lines above are Yes)
- Notes: <any reviewer wording that suggests a wording fix, even on a PASS>
```
