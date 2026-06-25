# Vendored merge engine (test fixture)

`resolve_customization.py` here is a verbatim copy of BMAD's
`_bmad/scripts/resolve_customization.py`, pinned so the customization-merge
suites (`test_no_harm.py`, `test_merge_customization.py`, and the Node
`test-cli-integration.js` Step 6b suite) stay hermetic and run in CI — the real
`_bmad/` tree is gitignored and absent on a clean checkout.

The module's runtime still imports `deep_merge` from the user's installed
`_bmad/scripts/resolve_customization.py` (never reimplemented). This copy is for
tests only and is excluded from the published package.

Refresh it when BMAD's engine changes:

```sh
cp _bmad/scripts/resolve_customization.py \
  skills/ultracode-goal/scripts/tests/fixtures/engine/resolve_customization.py
```
