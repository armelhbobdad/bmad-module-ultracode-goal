---
created: "2026-08-04 20:21"
session: "aaa0183f-7e6f-4b48-9a53-6932565cebe1"
---

# ESLint failures on pytest YAML fixtures under an in-tree TMPDIR

With `TMPDIR` pointed at a directory under the repo root that `eslint.config.mjs`'s `ignores` does not cover (e.g. `TMPDIR=$PWD/.verifier-tmp/t npm run quality`), the lint stage fails with `yml` errors such as "Unexpected scalar at node end" and "Empty documents are forbidden" (`yml/no-empty-document`) on the deliberately malformed `config.yaml`/`sprint-status.yaml` fixtures that `test_formalize_tea_reader.py` and `test_formalize_check.py` write under `<TMPDIR>/pytest-of-<user>/pytest-N/`. `.prettierignore` skips every `.*` directory but ESLint 9 flat config lints dot-directories, and the config ignores only `.claude/**`, `.codex/**`, `.playwright-mcp/**`, `temp/**` and `z*/**`. pytest keeps the last three basetemps, so the fixtures persist after `TMPDIR` is moved and the next lint still fails on them. Keep a redirected `TMPDIR` outside the checkout or add it to the eslint `ignores`, and delete leftover `pytest-of-*` directories before linting.
