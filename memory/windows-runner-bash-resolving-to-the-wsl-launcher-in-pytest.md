---
created: "2026-11-05 23:11"
session: "18a0e403-10ce-436e-a0f4-b2362871b122"
---

# Windows runner bash resolving to the WSL launcher in pytest

On the windows-latest GitHub runner, `bash` (what `shutil.which("bash")` finds) can be the WSL launcher, which cannot read a `C:/...` path. So a pytest that runs `subprocess.run(["bash", "-c", ...])` on a tmp_path project failed only in the `python (windows-latest)` job with `subprocess.CalledProcessError: Command '['bash', '-c', 'cat "C:/Users/runneradmin/AppData/Local/Temp/pytest-of-runneradmin/...` (PR #214, eight parametrized cases of `test_the_cat_command_clears_the_guard_and_appends` in `test_decision_log_slice_prose.py`). A `shutil.which("bash")` skip alone does not catch it. Split the bash step into its own test marked `@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="needs a POSIX bash that reads the project's own paths")` and keep the platform-neutral half running everywhere (fix commit 8b8db29).
