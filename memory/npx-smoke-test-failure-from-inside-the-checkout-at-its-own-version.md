---
created: "2026-06-04 13:20"
session: "d8b3ff6b-9cc2-4e88-9519-91e7549ab6bf"
---

# npx smoke test failure from inside the checkout at its own version

`npx bmad-module-ultracode-goal@<X.Y.Z> --version` run from anywhere inside this checkout fails with `sh: 1: bmad-module-ultracode-goal: not found` (exit 127) exactly when `<X.Y.Z>` equals the checkout's own `package.json` version, which is the post-release smoke case. npm's libnpmexec matches the exact-version spec against the checkout's root package in the local Arborist tree, skips the registry fetch and tries `node_modules/.bin`, where the bin does not exist because the package is not a dependency of itself; `@latest`, any other exact version, and the same command from outside the checkout all succeed. The `bin` entry (`tools/ucg-npx-wrapper.js`) is fine, so this looks like a broken publish when it is not. Run the post-release check from outside the checkout or with `@latest`; it still reproduces at v2.2.0 with npm 11.19 / Node 24, and step 5 of [RELEASING.md](../docs/_internal/RELEASING.md) does not warn about it.
