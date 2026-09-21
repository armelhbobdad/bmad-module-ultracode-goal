---
created: "2026-07-28 17:59"
session: "5f3680c8-d5d8-4591-8abe-e1a7bd118f15"
---

# Quality-scan grade bar of excellent with zero critical or high

When the bmad-workflow-builder quality scanners run over `skills/ultracode-goal`, the run is not finished at the report in the gitignored `skills/ultracode-goal/.analysis/`: confirmed findings get fixed and the scan re-run until the grade is `excellent` with 0 critical and 0 high, 0 medium where possible and as few low as possible. The user's bar, in a 2026-07-28 `/goal` prompt: "we should hove 0 critical/high. If possible, 0 medium and the less possible LOW. Quality grade = EXCELLENT"; the same bar was set on 2026-06-03 as "drive the report to Excellent with 0 critical/high/medium". The builder's own scale is looser (`scan-orchestration.md` calls `excellent` "no high or critical, few medium") and its Analyze step ends at presenting the grade, so without this rule a session stops at the report. The bar tolerates open medium and low items that need real feature work: the 2026-08-02 scan reached excellent still carrying 23 medium / 42 low, and 976553e (2026-08-06) shipped with seven findings left open "because each needs new shipped code or a restructure rather than a prose fix". Grade history lives only in the gitignored `.memlog.md`; no tracked doc records the practice.
