---
created: "2026-10-17 16:39"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# Platform path separator in formalize candidate sources failing tests on the Windows job

`formalize_check.py`'s `_rel` returns `str(path.relative_to(project_root))`, so a candidate's `source`, and the path inside its line-free id, use `\` on Windows. Tests that hard-code `impl-artifacts/4-1-signal.md` pass on Linux and fail only on the `python (windows-latest)` job, with `AssertionError: assert None` from `re.fullmatch(r"unclassified_signal:impl-artifacts/4-1-signal\.md:[0-9a-f]{12}", ...)`; build the expected path with `re.escape(str(Path(...)))`, as `test_formalize_scan_answers.py` now does. The same shape hit `claim_check.py`, where an absolute message path never matched a backslash root until it compared against `project_root.resolve().as_posix()`. Write path-bearing assertions platform-neutral before pushing, since only CI runs Windows.

Related: [[pytest-test-ids-over-32767-characters-error-on-the-windows-job]], [[os-name-nt-monkeypatch-failure-on-linux]]
