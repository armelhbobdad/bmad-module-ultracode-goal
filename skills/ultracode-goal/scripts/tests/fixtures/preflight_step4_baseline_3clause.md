## 4. Hard gate

**Launch only when ALL hold:**

- post-remediation script `budget == 0` (every mechanical blocker cleared),
- the semantic scan found **no RED** (no undecided product/architecture, no unresolvable secret),
- **ultracode** session effort and **Auto Mode** are on (gated to Opus/Sonnet 4.6+; required for unattended xhigh + auto-workflow execution).

If any fails: write the blockers — mechanical and semantic — to `.decision-log.md` with what each needs to clear, and **STOP**.
