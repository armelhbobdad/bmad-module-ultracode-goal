---
created: "2026-10-18 20:41"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# iwe rename stripping quotes from memory frontmatter

`iwe rename <old-key> <new-key>` on a memory note rewrote its frontmatter without quotes: `created: "2026-10-18 20:14"` became `created: 2026-10-18 20:14`, and `session` lost its quotes the same way, while every other note in `memory/` quotes both. It does the same to every note whose links it rewrites: on 2026-11-21 (iwe 0.28.0, in a sandbox copy of `memory/`) the two notes linking to a renamed one came back with both values unquoted, and `iwe schema validate` still passed, so only the store's uniform quoting is lost. `iwe update -k <key> --content -` writes the frontmatter exactly as given, so piping each touched note's quoted text back through `iwe update --strict --content -` restores it. The rename also left the `# ` heading as it was, so a retitle needs the heading edited separately. After a rename, put the quotes back, set the heading, and run `iwe internal claude session complete <session> --wrote <new key>` so the session log names the new key. Before renaming, `iwe rename --dry-run -f keys <old> <new>` lists the documents that link to the note.
