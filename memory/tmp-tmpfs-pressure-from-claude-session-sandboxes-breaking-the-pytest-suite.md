---
created: "2026-08-02 15:25"
session: "69c5ff6f-e98d-41a7-866b-444f3e6f1641"
---

# /tmp tmpfs pressure from Claude session sandboxes breaking the pytest suite

`/tmp` on this machine is a 16G tmpfs with 1,048,576 inodes shared by every Claude session; when it fills, the suite under `skills/ultracode-goal/scripts/tests/` fails en masse with `OSError Errno 28 "No space left on device"` in `Path.mkdir`/`mkstemp`/git subprocesses or `could not create numbered dir with prefix ... in /tmp/pytest-of-<user>/pytest-14 after 10 tries` (693 errors in one `-n 4` run). Mass errors with that fingerprint are disk pressure, not code: ENOSPC hit at 60% byte usage, so check `df -i /tmp` as well as `df -h /tmp`, and `du --inodes -d1 /tmp/claude-<uid>` to find the consumer (old session sandboxes were at ~400k files). Clearing old sandboxes under `/tmp/claude-<uid>` plus `rm -rf /tmp/pytest-of-* /tmp/ucg-test-* /tmp/vdl-* /tmp/ucg-loader-* /tmp/tmp* /tmp/uv-*` restored green runs; `test:python` runs xdist (`-n auto`) over 32 files that build per-test git repos under `tmp_path`, which multiplies concurrent temp dirs. `export TMPDIR=<dir on /home>` before `npm run quality` moves them off the tmpfs, but not into the checkout: ESLint lints the pytest fixtures there, and `test_preflight_check.py::test_non_git_dir_is_a_blocker` fails when TMPDIR sits inside a git checkout.
