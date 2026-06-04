#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for merge-config.py.

Run: uv run --with pytest pytest scripts/tests/test_merge_config.py -v

merge-config.py declares a pyyaml PEP 723 dependency, so it is exercised via
`uv run` (which resolves it) rather than the bare test interpreter. Covers
the fresh module-section write with the core/user split, and the anti-zombie
section replacement on re-registration.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "merge-config.py"
MODULE_YAML = Path(__file__).resolve().parents[2] / "assets" / "module.yaml"

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")


def run_merge(tmp_path: Path, answers: dict):
    answers_file = tmp_path / "answers.json"
    answers_file.write_text(json.dumps(answers), encoding="utf-8")
    cmd = [
        "uv",
        "run",
        str(SCRIPT),
        "--config-path",
        str(tmp_path / "_bmad" / "config.yaml"),
        "--user-config-path",
        str(tmp_path / "_bmad" / "config.user.yaml"),
        "--module-yaml",
        str(MODULE_YAML),
        "--answers",
        str(answers_file),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def test_fresh_registration_splits_core_and_user_settings(tmp_path):
    proc = run_merge(
        tmp_path,
        {
            "core": {
                "user_name": "Armel",
                "communication_language": "English",
                "document_output_language": "English",
                "output_folder": "{project-root}/_bmad-output",
            },
            "module": {},
        },
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "success"
    assert result["module_code"] == "ultracode-goal"
    assert sorted(result["user_keys"]) == ["communication_language", "user_name"]

    config_text = (tmp_path / "_bmad" / "config.yaml").read_text(encoding="utf-8")
    assert "ultracode-goal:" in config_text  # module section registered
    assert "user_name" not in config_text  # user-only keys never land here
    user_text = (tmp_path / "_bmad" / "config.user.yaml").read_text(encoding="utf-8")
    assert "user_name: Armel" in user_text


def test_rerun_replaces_module_section_anti_zombie(tmp_path):
    run_merge(tmp_path, {"core": {"output_folder": "{project-root}/_bmad-output"}, "module": {}})
    proc = run_merge(tmp_path, {"module": {}})
    assert proc.returncode == 0, proc.stderr

    config_text = (tmp_path / "_bmad" / "config.yaml").read_text(encoding="utf-8")
    assert config_text.count("ultracode-goal:") == 1  # replaced, not duplicated
    assert "output_folder: '{project-root}/_bmad-output'" in config_text or "output_folder: {project-root}/_bmad-output" in config_text
