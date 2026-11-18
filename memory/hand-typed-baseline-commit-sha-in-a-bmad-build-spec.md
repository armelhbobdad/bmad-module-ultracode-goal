---
created: "2026-11-05 19:10"
session: "18a0e403-10ce-436e-a0f4-b2362871b122"
---

# Hand-typed baseline_commit SHA in a bmad-build spec

Twice in one session a bmad-build spec's frontmatter got an invented full SHA for `baseline_commit` (65e7c8159d9c7f4c0f0a6c6c1e2fd2bb37d0cb22 while HEAD was 65e7c81068a2700b927080510eef903c21273d40, the two sharing only a short prefix). Step 3 (`step-03-implement.md`) keeps a `baseline_commit` already present in the frontmatter and never overwrites it, and step 4 (`step-04-review.md`) diffs against it, so an invented value makes the review read the wrong range. Fill it only from `git rev-parse HEAD` output at the moment it is written, never from memory or by extending a short sha.
