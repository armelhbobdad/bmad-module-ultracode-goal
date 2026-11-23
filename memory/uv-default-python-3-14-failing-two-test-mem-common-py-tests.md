---
created: "2026-11-23 10:55"
session: "775f5088-65e5-4882-8e03-0238bc221ade"
---

# uv default Python 3.14 failing two test_mem_common.py tests

On this host `uv` now picks CPython 3.14.7 by default, and under it two tests in `skills/ultracode-goal/scripts/tests/test_mem_common.py` fail every time: `test_read_state_returns_none_on_json_nested_past_the_recursion_limit[deep-object]` (`read_state` returns the nested dict instead of `None`) and `test_remove_own_state_never_assumes_an_unreadable_latch_is_this_runs[nested-past-the-limit]` (`remove_own_state` returns `'foreign'` instead of `'unreadable'`). Python 3.14's `json.loads` parses the tests' 50,000-deep payload without raising `RecursionError`, which both tests rely on. Both pass on 3.12, which `.github/workflows/quality.yaml` pins, and on 3.13. So `npm run quality`, and with it the husky pre-push hook, fails on every branch here while CI stays green. On 2026-11-23 setting `UV_PYTHON=3.12` on `npm run quality` and on the push let the hook run green (8444 passed); the tests and the code they cover were left unchanged, so a contributor whose uv picks 3.14 still meets them.
