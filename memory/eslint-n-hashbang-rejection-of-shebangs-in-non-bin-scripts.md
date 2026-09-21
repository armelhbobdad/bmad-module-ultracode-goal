---
created: "2026-08-03 02:09"
session: "33431228-168c-400b-b592-dbc99cd63661"
---

# ESLint n/hashbang rejection of shebangs in non-bin scripts

Any `*.js`/`*.mjs`/`*.cjs` file starting with `#!/usr/bin/env node` that is not listed under `bin` in package.json fails `npm run lint` (and so `npm run quality`) with `This file needs no shebang` (rule `n/hashbang`, from `nodePlugin.configs['flat/mixed-esm-and-cjs']` in eslint.config.mjs). The only file allowed a shebang is the sole bin entry, `tools/ucg-npx-wrapper.js`. Delete the shebang (tools/ scripts run as `node tools/<script>.js`), add the file to `bin`, or let `npx eslint --fix <file>` strip it. Because `quality` runs its stages through `run-p --aggregate-output`, only the lint stage's output carries the message; grep the quality log for `n/hashbang` before hunting elsewhere.
