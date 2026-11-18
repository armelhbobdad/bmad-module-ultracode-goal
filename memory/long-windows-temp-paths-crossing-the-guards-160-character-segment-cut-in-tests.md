---
created: "2026-10-24 19:48"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# Long Windows temp paths crossing the guard's 160-character segment cut in tests

Guard tests that hard-code the expected quoted segment of a deny reason pass on Linux but fail on the `python (windows-latest)` CI job, because the runner's long temp path pushes the text past `_SEGMENT_SHOWN = 160` in `skills/ultracode-goal/scripts/hooks/guard_pretooluse.py`, so the cut falls inside the path. It hit twice in one series on 2026-10-24: `test_csr_deny_reason_quotes_a_long_segment_cut_short` in #156 and `test_csr_latch_path_deny_reason_states_the_rule` in #157. Build the expected text from the segment itself or with `guard_module._shown(...)`, as `test_guard_pretooluse.py` now does, so the assertion holds at any path length.
