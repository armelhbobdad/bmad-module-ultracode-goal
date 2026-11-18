---
created: "2026-10-06 21:00"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# Boost output showing $HOME and $TMPDIR in place of absolute paths

The Boost shell hook compacts Bash output and displays the home directory as `$HOME` and `/tmp` as `$TMPDIR`, so printing `.claude/settings.local.json` makes UCG's armed hook commands, which hold absolute paths, look as if they held a literal `$HOME`. Before concluding a hook path is broken, or rewriting it, check the real bytes (for example a short Python read testing for the absolute prefix). On 2026-10-06 that check printed the absolute path, and `$HOME` was only Boost rewriting the display.
