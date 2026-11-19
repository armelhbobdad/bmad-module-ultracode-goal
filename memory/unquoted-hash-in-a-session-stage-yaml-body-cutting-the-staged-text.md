---
created: "2026-11-18 01:19"
session: "2e0859f5-9e6d-4ee2-9f4b-2f2cdbb0f2dc"
---

# Unquoted `#` in a session stage YAML body cutting the staged text

`iwe internal claude session stage --content -` parses its input as YAML, so an unquoted `body:` (or `title:` or `evidence:`) holding a space followed by `#` is cut there, the rest read as a comment, and the stage still reports success. The first case was the Fixes-line candidate, whose body ending "(Fixes #N) appear once" was stored ending at "(Fixes"; the writer had to rebuild the note from its title and evidence. It recurred on 2026-11-19, when three candidates staged by distill reader subagents stopped at "(SKF issue" and lost their issue numbers, which had to be recovered from the readers' reports. Single-quote any staged field that contains " #", doubling any single quote inside it, and tell distill subagents to do the same.
