---
created: "2026-07-30 08:19"
session: "141fcc0e-2445-4881-8063-fc2bff8f0aeb"
---

# Astro scratch build failure with symlinked node_modules

A scratch copy of `website/` whose `node_modules` is a symlink back to the repo's install fails `npx astro build` (so `npm run docs:build` / `node tools/build-docs.js`) with `Could not load .../Page.astro?astro&type=style&index=0&lang.css ...: No cached compile metadata found` and `The main Astro module .../Page.astro should have compiled and filled the metadata first`. It built only after replacing the symlink with a full copy of `website/node_modules` (leaving out `node_modules/.astro` and `node_modules/.vite`) and placing the repo's `docs/` beside it, since `website/src/content/docs` is a symlink to `../../../docs`. This is the exception to the per-`node_modules` symlink rule in [gate.md](../skills/ultracode-goal/references/gate.md): for `website/`, copy. A scratch root that is not a git worktree also needs the root `package.json`, because `website/src/components/Header.astro` reads the version from `../../../package.json` at build time.
