# License

This skill is adapted from the `bmad-create-story` workflow of BMAD Method 6.12.4
(<https://github.com/bmad-code-org/BMAD-METHOD>, `src/bmm-skills/v6-shims/bmad-create-story`), which BMAD
deprecated in favour of `bmad-build` and removes at v7. UltraCode Goal ships this copy under its
own name so its runs keep the story-file contract without the deprecated shim installed.

The changes from upstream are limited to: the skill name and description, with the shim lifecycle
metadata removed; this attribution and the notice below; a fallback for loading config when
`_bmad/scripts/resolve_config.py` is absent; the customization resolver called without
`--project-root`, which BMAD Method 6.10's resolver does not accept, with a fallback for
`on_complete` when the call fails; the removed deprecation notice; references to the dev-story
workflow renamed to `ucg-dev-story`, and the template's note about the nonexistent
`validate-create-story` replaced by a check against this skill's checklist; and em dashes replaced
by other punctuation. The workflow steps are otherwise unchanged.

UltraCode Goal's own changes are under its license (the `LICENSE` file at the repository root).
The upstream work is distributed under the following license:

MIT License

Copyright (c) 2025 BMad Code, LLC

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

BMad, BMad Method and BMad Core are trademarks of BMad Code, LLC. Their use here does not
grant any rights to use the trademarks for any other purpose.
