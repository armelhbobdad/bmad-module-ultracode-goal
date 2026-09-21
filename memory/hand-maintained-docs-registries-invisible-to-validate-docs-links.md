---
created: "2026-07-30 08:19"
session: "141fcc0e-2445-4881-8063-fc2bff8f0aeb"
---

# Hand-maintained docs registries invisible to validate-docs-links

Adding or deleting a page under docs/ means hand-editing registries nothing enumerates: docs/index.md (`template: splash`, so it lists pages by hand), the `website/astro.config.mjs` sidebar, README.md's "Learn More" list, the hardcoded llms.txt list in `generateLlmsTxt` in tools/build-docs.js, the mermaid router at the top of docs/troubleshooting.md, and optionally docs/404.md. `validate:docs-links` (`node tools/validate-docs-links.js --strict`) checks `.md` targets in docs/, hrefs in build/site and site-internal links in llms.txt, but never reads README.md and cannot notice an omitted entry, so a page missing from a registry passes green: docs/operating-tips.md landed in the sidebar and nowhere else with the gate green, and after docs/parallel-mode.md was deleted README.md's `[Parallel Mode](./docs/parallel-mode.md)` survived with exit 0. On any page add or delete, grep the tree for the slug and title (`grep -rn 'parallel-mode\|Parallel Mode' --exclude-dir=node_modules .`) and run `npm run docs:build` first: `npm run quality` does not build the site, so the built pass validates whatever old build/site is lying around (it only prints a warnings-only `STALE BUILD` block).
