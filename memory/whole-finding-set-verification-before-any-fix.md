---
created: "2026-08-03 02:40"
session: "4e2f68a1-8a5e-438b-af3a-ea847b88489e"
---

# Whole-finding-set verification before any fix

When triaging a set of findings (quality-scan items, improvement-queue filings, review findings), verify every finding against the current tree before fixing any of them. The user's rule, from the 2026-08-03 handoff prompt: "verify the whole finding set BEFORE fixing anything (fixing mid-verification corrupted two verdicts last session)". A fix applied mid-triage changes the tree the remaining findings are checked against, so later verdicts describe a tree nobody filed against; a whole-set pass over the GMC queue found three of five filings confirmed-but-misdiagnosed. Nothing in the repository records this habit; it is distinct from gate.md's "generalize before fixing" (naming the defect class) and operating-tips' "re-measure the committed tree" (a dirty spawn tree).
