---
created: "2026-10-17 17:23"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# GIT_CONFIG_NOSYSTEM in tests drops Windows core.autocrlf

Setting `GIT_CONFIG_NOSYSTEM=1` in a pytest fixture to keep the host's ignore rules out of `git check-ignore` cases also drops the Windows runner's system `core.autocrlf=true`. Python's `write_text` writes CRLF there and the fixture repo was committed with autocrlf on (LF in the index), so whenever git re-checks content the clean tree reads as modified: on windows-latest CI, `test_a_gitignored_artifact_tree_is_reported_and_never_blocks` in `skills/ultracode-goal/scripts/tests/test_preflight_check.py` failed `assert report["green"] is True` on two runs of one commit, while the same test had passed on another PR's Windows run (the mechanism is inferred; the fix below made it pass). Override only the excludes file instead: `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=core.excludesFile`, `GIT_CONFIG_VALUE_0=<an empty file>`, which leaves system config in place (`_no_host_ignores` there, and the autouse fixture in `test_claim_check.py`). Related: [[os-name-nt-monkeypatch-failure-on-linux]].
