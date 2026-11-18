---
created: "2026-11-03 17:21"
session: "18a0e403-10ce-436e-a0f4-b2362871b122"
---

# git push piped through grep hiding a failed pre-push quality run

The pre-push hook runs the whole `npm run quality`, with minutes of output, and `git push ... 2>&1 | grep ...` reports the exit status of grep, not of the push. So on PR #200 a push the hook refused (a failing allowlist prose test) came back as "completed (exit code 0)" while `git status -sb` still showed the branch two commits ahead and the remote stayed at 7523acc. Send the push output to a log and print the push's own status (`git push > <log> 2>&1; echo "push exit=$?"`), then confirm with `git ls-remote origin <branch>` before reporting the push as done.
