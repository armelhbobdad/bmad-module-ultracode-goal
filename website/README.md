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

Deployment is automated by the `Deploy Documentation` GitHub Actions workflow at
`.github/workflows/docs.yaml`. On a push to `main` that touches `docs/**`,
`website/**`, `tools/build-docs.js`, `package.json`, or the workflow file, the
pipeline installs dependencies, runs `npm run docs:build`, and publishes
`build/site` to GitHub Pages.

The workflow reads `SITE_URL` from a repository variable, so the production URL
can be configured without changing code. The workflow can also be triggered
manually from the Actions tab.

## Links

- Repository: <https://github.com/armelhbobdad/bmad-module-ultracode-goal>
- BMAD Method: <https://bmad-method.org>
