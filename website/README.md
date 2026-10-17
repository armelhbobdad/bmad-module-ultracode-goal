# UltraCode Goal Documentation Website

This directory contains the documentation website for UltraCode Goal (UCG). The
Markdown sources live in the repository's top-level `docs/` directory; this
project renders them into a static, deployable site.

## Setup

Install the website's dependencies from this directory:

```bash
npm --prefix website ci
```

The website keeps its own `package.json` and lockfile, separate from the root
package, so its toolchain stays isolated from the module's runtime.

## Development

Run the local development server:

```bash
npm run docs:dev
```

The `docs:dev` script is defined at the repository root and forwards to this
project. Once it is running, open the printed local URL (typically
<http://localhost:4321>) to preview the docs with live reload.

## Build

Build the production site:

```bash
npm run docs:build
```

Run from the repository root, this drives `tools/build-docs.js`, which:

- generates the AI-readable text bundles (`llms.txt`, `llms-full.txt`) from
  `docs/*.md`, and
- builds this website.

The final, deployable output is written to `../build/site` (relative to this
directory), and the generated text bundles are copied alongside it so AI agents
can fetch them from the published site.

To build only this website without the surrounding pipeline:

```bash
npm --prefix website run build
```

## Preview

Preview the production build locally:

```bash
npm run docs:preview
```

## Configuration

### Site URL

The public site URL is read from the `SITE_URL` environment variable. When it is
not set, the build falls back to a URL derived from the repository, which is the
right default for a project page under
<https://armelhbobdad.github.io/bmad-module-ultracode-goal>.

To build against an explicit URL:

```bash
SITE_URL=https://armelhbobdad.github.io/bmad-module-ultracode-goal npm run docs:build
```

## Deployment

The `Deploy Documentation` GitHub Actions workflow at
`.github/workflows/docs.yaml` builds the site from a release tag and publishes
`build/site` to GitHub Pages, so the site shows the latest stable release, not
`main`. A merge to `main` does not deploy it: the release workflow dispatches
`docs.yaml` at the end of every stable release, with `ref` set to the new tag.
To deploy by hand, run `gh workflow run docs.yaml` (the latest stable tag) or
`gh workflow run docs.yaml -f ref=vX.Y.Z` (a given tag); see
`docs/_internal/RELEASING.md`, The docs site.

The workflow reads `SITE_URL` from a repository variable, so the production URL
can be configured without changing code. The `docs-links` job of
`quality.yaml` builds the same site on every pull request and checks its links.

## Links

- Repository: <https://github.com/armelhbobdad/bmad-module-ultracode-goal>
- BMAD Method: <https://docs.bmad-method.org>
