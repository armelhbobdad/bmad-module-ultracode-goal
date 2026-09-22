---
created: "2026-09-22 00:29"
session: "24303682-9e4b-4ebd-85fd-9ade65f1e93c"
---

# Memory changes get their own commits

A commit touches either the memory store (`memory/`, `MEMORY.md`, `.iwe/`) or the project's code, docs and tooling (`skills/`, `tools/`, `docs/`, `website/`, `.github/`, the root config files), never both. The user's rule, stated on 2026-09-22: "all related memory should be committed in an isolated commit (we should never have a commit with both memory files and features files)." Memory commits record what the project remembers and feature commits change what it does, so `git log` and `git blame` on the shipped tree never show note churn, a memory commit can be reverted or cherry-picked without touching behaviour, and code review stays focused on code. In practice: stage the memory paths on their own (`git add memory/ MEMORY.md .iwe/`) and commit them under the `chore(memory):` prefix, which fits the scoped conventional-commit convention in CONTRIBUTING.md and, as a `chore` type, also keeps them out of the CHANGELOG section release.yaml generates; when a feature session also produced notes, the notes are a second commit, on the same branch or PR if convenient, never in the same commit. The store's bootstrap commit 0bd764a (PR #106, 2026-09-21) predates the rule and mixed the first 48 notes with the ignore-rule and ESLint edits; it is not a precedent.
