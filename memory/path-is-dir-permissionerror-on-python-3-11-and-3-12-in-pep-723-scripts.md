---
created: "2026-11-17 19:42"
session: "60ac1f41-93ab-4fff-b3c7-bdf99f676ae8"
---

# Path.is_dir PermissionError on Python 3.11 and 3.12 in PEP 723 scripts

The skill scripts declare `requires-python >=3.11` in their PEP 723 header and `uv run` reuses whichever interpreter it cached the script with, and on Python 3.11 and 3.12 `pathlib.Path.is_dir()`, `.is_file()` and `.exists()` raise `PermissionError` (EACCES) for a path under a folder the process cannot search, where 3.14 returns False. The final adversarial pass on `skills/ultracode-goal/scripts/carry_build_cache.py` (PR #242) reproduced it with `uv run --python 3.11` and `3.12`: `out --worktree` under a `chmod 600` parent printed a traceback and exited 1 instead of the documented 2, and on 3.14 a `drop` of an unreachable stash read as success. The fix was `os.path.isdir()`, `os.path.isfile()` and `os.path.exists()` on every user-given path, plus an `lstat` of the stash that reports any error other than ENOENT under `failed`; nothing in the code says why, so keep that form when editing it. Run such scripts and their tests under `--python 3.11` too, not only the local default interpreter.
