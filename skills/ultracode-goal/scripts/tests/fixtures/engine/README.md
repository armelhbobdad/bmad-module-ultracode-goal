# Vendored merge engine, before BMAD 6.11 (test fixture)

`resolve_customization.py` here is a verbatim copy of the single-file
`_bmad/scripts/resolve_customization.py` that BMAD releases before 6.11 install,
which defines the structural merge itself as `deep_merge`. It is pinned so the
customization-merge suites (`test_no_harm.py`, `test_merge_customization.py`,
`test_tea_fragments.py`, and the Node `test-cli-integration.js` Step 6b suite)
stay hermetic and run in CI: the real `_bmad/` tree is gitignored and absent on
a clean checkout. `../engine-6.12/` holds the layout 6.11 introduced, where the
merge lives in `config_utils.py`, and the suites run against both.

The module's runtime imports the merge from the user's installed
`_bmad/scripts/` (never reimplemented). This copy is for tests only and is
excluded from the published package.

Refresh it from a project on BMAD 6.10.0 or earlier:

```sh
cp _bmad/scripts/resolve_customization.py \
  skills/ultracode-goal/scripts/tests/fixtures/engine/resolve_customization.py
```
