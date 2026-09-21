---
created: "2026-08-04 22:37"
session: "aaa0183f-7e6f-4b48-9a53-6932565cebe1"
---

# Pytest fixed-depth dependency on repo-root STABILITY.md

The suite under `skills/ultracode-goal/scripts/tests` pins the repo root by parent depth (`_REPO_ROOT = Path(__file__).resolve().parents[4]` in test_budget_stop.py, test_no_harm.py, test_phase3_evidence_gate.py, test_ucg_awareness_fragments.py and test_health_check_fp.py) and reads docs/\_internal/STABILITY.md, CHANGELOG.md, docs/how-it-works.md and CONTRIBUTING.md unguarded. A scratch or mutation copy of only scripts/ or skills/ultracode-goal/ dies with `FileNotFoundError: [Errno 2] No such file or directory: '<copy>/docs/_internal/STABILITY.md'` from `_STABILITY.read_text(...)`, not with a test assertion. Copy the whole repo at full depth instead (`rsync -a --exclude .git --exclude node_modules --exclude .venv --exclude _bmad-output --exclude graphify-out --exclude _ucg-learn --exclude website --exclude build <repo>/ <copy>/`) and run it the way `test:python` does (`uv run --with pytest==9.1.1 --with pytest-xdist==3.8.0 pytest skills/ultracode-goal/scripts/tests/ -n auto`); pyproject.toml declares no dependencies, so a bare `uv run pytest` fails with "error: Failed to spawn: `pytest`".
