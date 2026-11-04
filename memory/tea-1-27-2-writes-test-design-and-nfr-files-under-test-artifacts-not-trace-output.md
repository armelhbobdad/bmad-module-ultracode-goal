---
created: "2026-11-03 19:35"
session: "18a0e403-10ce-436e-a0f4-b2362871b122"
---

# TEA 1.27.2 writes test-design and NFR files under test_artifacts, not trace_output

The TEA 1.27.2 installer writes two folder keys into `_bmad/tea/config.yaml`: `test_artifacts: _bmad-output/test-artifacts` and `trace_output: _bmad-output/test-artifacts/traceability`. Only `test_artifacts` is wired: `trace_output` is an unused "future" key that no TEA workflow reads, and it is gone after 1.27.2. TEA writes `test-design-epic-{epic_num}.md`, the system-level `test-design-architecture.md` and `test-design-qa.md`, and `nfr-assessment.md` flat at the `{test_artifacts}` root, never under `traceability/`. Through 4.1.0, `skills/ultracode-goal/scripts/formalize_check.py` searched `trace_output` first, so on a default install its TEA reader found nothing and its TEA checks never ran (#201, fixed in PR #202, fragment `changes/formalize-check-reads-the-epics-tea-files.yaml`). Code that reads TEA's output should resolve the root the way `preflight_check.py` does (`test_artifacts`, else `_bmad-output/test-artifacts`), which is also what preflight injects as `ULTRACODE_TEST_ARTIFACTS`. No `nfr-assessment.md` exists before the Epic is built either, because `bmad-testarch-nfr` runs only "when implementation evidence exists".
