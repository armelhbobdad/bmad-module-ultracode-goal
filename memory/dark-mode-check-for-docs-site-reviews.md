---
created: "2026-06-04 16:23"
session: "777ccc3f-9c9a-4209-9a55-13ba5469e1a3"
---

# Dark-mode check for docs site reviews

Any review of the docs site (`website/`, the Astro Starlight build of `docs/`) is checked in dark mode as well as light, and at mobile width; the user's instruction when the site went live: "Also review the whole site using /frontend-design:frontend-design /hallmark . Do not forget to also test the dark mode properly". The reason is that the site carries dark-mode-only overrides a light check never exercises: Mermaid's stock dark theme rendered sequence-diagram `messageText`/`loopText` too dim on the indigo background (fixed with a `#cbd5e1 !important` fill override under `:root[data-theme='dark']` in `website/src/styles/custom.css`), and diagram containers needed a faint border to read as surfaces. Toggle it for testing by setting localStorage `starlight-theme` to `dark` (which puts `data-theme="dark"` on the document root) against `npm run docs:dev` or `npm run docs:preview`.
