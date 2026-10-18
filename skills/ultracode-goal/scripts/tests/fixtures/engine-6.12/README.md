# Vendored merge engine, BMAD 6.12 (test fixture)

`resolve_customization.py` and `config_utils.py` here are verbatim copies of
BMAD Method 6.12.4's `_bmad/scripts/` files of the same names. BMAD 6.11 moved
the structural merge out of `resolve_customization.py` (where earlier releases
define it as `deep_merge`) into `config_utils.py` as `structural_merge`, which
the resolver applies through `load_customization`; 6.11.0's `config_utils.py` is
byte-identical to this one. `merge_customization.py` imports whichever of the
two functions the installed engine has, so the customization-merge suites run
against this copy and against the earlier single-file engine in `../engine/`.

Like `../engine/`, this copy is for tests only and is excluded from the
published package.

Refresh it when BMAD's engine changes:

```sh
cp _bmad/scripts/resolve_customization.py _bmad/scripts/config_utils.py \
  skills/ultracode-goal/scripts/tests/fixtures/engine-6.12/
```
