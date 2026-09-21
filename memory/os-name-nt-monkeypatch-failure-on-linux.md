---
created: "2026-08-02 13:20"
session: "69c5ff6f-e98d-41a7-866b-444f3e6f1641"
---

# os.name nt monkeypatch failure on Linux

Faking Windows with `os.name = "nt"` on Linux before the stdlib or pytest is imported fails with `ModuleNotFoundError: No module named 'nt'`; `python3 -c "import os; os.name='nt'; import shutil"` reproduces it, because shutil does `import nt` at load whenever `os.name` says Windows and pytest's terminal writer imports shutil. So the suite's Windows-only branches cannot be exercised that way; what worked was temporarily flipping the guard in `skills/ultracode-goal/scripts/tests/test_drive_epic.py` from `if os.name != "nt":` to `if False:`, running the affected tests, and restoring it; the real check is the windows-latest CI job. `grep -n 'os.name' skills/ultracode-goal/scripts/tests/*.py` finds the platform gates; the suite runs via `npm run test:python` (`uv run --with pytest==9.1.1 --with pytest-xdist==3.8.0 pytest ... -n auto`) and plain `python3` has no pytest.
