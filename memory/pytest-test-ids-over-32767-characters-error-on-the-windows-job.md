---
created: "2026-11-03 18:11"
session: "18a0e403-10ce-436e-a0f4-b2362871b122"
---

# pytest test ids over 32767 characters error on the Windows job

pytest copies each test's node id into the `PYTEST_CURRENT_TEST` environment variable, and Windows caps an environment variable at 32767 characters, so a parametrized test whose parameter holds a whole file's text errors at setup and teardown with `ValueError: the environment variable is longer than 32767 characters` on the windows-latest job only, while Linux passes. On PR #200, `test_a_touched_line_has_no_em_dash_left` in `skills/ultracode-goal/scripts/tests/test_story_evidence_folder_prose.py` took `gate.md`'s and `execute.md`'s text as its parameter, giving ids of about 106,000 characters. The job log stopped right after pytest's `ERRORS` header, and `gh run view --log` showed nothing more; the error itself was only in the raw job log, `gh api --allow-escape-sequences repos/<owner>/<repo>/actions/jobs/<id>/logs`. Key such a parameter by a short name and look the text up inside the test, and before pushing check the longest collected id: `pytest --collect-only -q` piped to `awk '{print length($0)}' | sort -rn | head -1`. Related: [[git-config-nosystem-in-tests-drops-windows-autocrlf]].
