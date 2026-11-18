---
created: "2026-11-03 17:21"
session: "18a0e403-10ce-436e-a0f4-b2362871b122"
---

# Backticked git phrases in reference prose read as command forms by the allowlist test

`skills/ultracode-goal/scripts/tests/test_allowlist_covers_prose.py` reads every inline code span and fenced line of the ultracode-goal SKILL.md and `references/*.md` (plus the SKILL.md of ucg-create-story and ucg-dev-story), splits each at `&&`, `||`, `;` and `|`, and treats any segment whose first word is exactly `git` or `uv` (or a python interpreter) as a prescribed command form named by its first two words. So a merely descriptive span such as `git runs`, added to gate.md for #198, failed `test_the_prose_prescribes_exactly_the_listed_forms` with "command forms the prose names that this test does not place", and the pre-push quality run refused the push. The first-word match is case-sensitive, so reword the span or drop its backticks. For a real new command, place it in `PRESCRIBED` (and the allowlist) or in `NOT_RUN_UNDER_THE_ALLOWLIST` with its reason, before pushing a prose change there.
