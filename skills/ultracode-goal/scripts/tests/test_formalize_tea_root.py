"""formalize_check.py reads the TEA trace_output root with preflight's reader.

The root comes from the TEA config's `trace_output:` scalar, else its
`test_artifacts:` one. formalize_check.py once read them with a copy of
preflight_check.py's reader that never got the inline-comment strip, so
`test_artifacts: <path>  # where TEA writes` named a folder that does not
exist. The TEA-reader then found no test-design under it, and a TEA artifact
under the real root, when that root sits inside the implementation artifacts,
read as leaked. These tests pin the reading to preflight's own.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS / "formalize_check.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fc = _load("formalize_check", SCRIPT)
pc = _load("preflight_check", SCRIPTS / "preflight_check.py")


def _config(root: Path, body: str, name: str = "config.yaml") -> Path:
    path = root / "tea" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# (id, config text, the root relative to the project root, or None for no root)
_VALUES = [
    ("plain", "test_artifacts: out/ta\n", "out/ta"),
    ("commented", "test_artifacts: out/ta  # where TEA writes\n", "out/ta"),
    ("trace-commented", "trace_output: out/tr  # where trace writes\n", "out/tr"),
    ("double-quoted", 'test_artifacts: "out/ta" # where TEA writes\n', "out/ta"),
    ("single-quoted", "test_artifacts: 'out/ta'  # where TEA writes\n", "out/ta"),
    ("hash-in-value", "test_artifacts: out/a#b\n", "out/a#b"),
    ("hash-in-quotes", 'test_artifacts: "out/a #b"  # note\n', "out/a #b"),
    ("project-root", "trace_output: {project-root}/tr  # note\n", "tr"),
    ("no-value-then-nested", "test_artifacts:\n  nested: x\n", None),
    ("comment-only", "test_artifacts:  # set by TEA\n", None),
    ("comment-only-trace-falls-back", "trace_output:   # set once TEA traces\ntest_artifacts: out/ta\n", "out/ta"),
    ("commented-out", "# test_artifacts: out/old\n", None),
    ("trace-first", "trace_output: out/tr\ntest_artifacts: out/ta\n", "out/tr"),
    ("trace-first-by-key", "test_artifacts: out/ta\ntrace_output: out/tr\n", "out/tr"),
    ("empty-trace-falls-back", 'trace_output: ""\ntest_artifacts: out/ta\n', "out/ta"),
    ("neither-key", "test_framework: pytest\n", None),
]


@pytest.mark.parametrize(("body", "expected"), [v[1:] for v in _VALUES], ids=[v[0] for v in _VALUES])
def test_the_root_is_read_as_preflight_reads_the_value(tmp_path, body, expected):
    config = _config(tmp_path, body)
    root = fc._tea_trace_output_root(config, tmp_path)
    assert root == (None if expected is None else tmp_path / expected)


_TEST_ARTIFACTS_ONLY = [v for v in _VALUES if v[2] is not None and "trace_output" not in v[1]]


@pytest.mark.parametrize("body", [v[1] for v in _TEST_ARTIFACTS_ONLY], ids=[v[0] for v in _TEST_ARTIFACTS_ONLY])
def test_a_test_artifacts_root_matches_preflights_own(tmp_path, body):
    config = _config(tmp_path, body)
    assert fc._tea_trace_output_root(config, tmp_path) == pc._tea_artifacts_root(
        tmp_path, pc._read_toml_or_yaml_flags(config)
    )


def test_a_toml_config_drops_its_comment(tmp_path):
    config = _config(tmp_path, 'test_artifacts = "out/ta"  # where TEA writes\n', "config.toml")
    assert fc._tea_trace_output_root(config, tmp_path) == tmp_path / "out/ta"


def test_an_absolute_value_is_read_where_it_is(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    config = _config(tmp_path / "project", f"trace_output: {elsewhere.as_posix()}  # note\n")
    assert fc._tea_trace_output_root(config, tmp_path / "project") == elsewhere


def test_a_missing_config_yields_no_root(tmp_path):
    assert fc._tea_trace_output_root(tmp_path / "tea" / "config.yaml", tmp_path) is None
    assert fc._tea_trace_output_root(tmp_path, tmp_path) is None


def test_an_unreadable_config_yields_no_root(tmp_path, monkeypatch):
    config = _config(tmp_path, "trace_output: out/tr\n")
    assert fc._tea_trace_output_root(config, tmp_path) == tmp_path / "out/tr"

    def unreadable(path, keys=()):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(sys.modules["preflight_check"], "_read_toml_or_yaml_flags", unreadable)
    assert fc._tea_trace_output_root(config, tmp_path) is None


def test_the_default_keys_still_read_teas_flags(tmp_path):
    config = _config(tmp_path, "trace_output: out/tr\ntest_framework: pytest  # note\n")
    assert pc._read_toml_or_yaml_flags(config) == {"test_framework": "pytest"}
    assert pc._read_toml_or_yaml_flags(config, fc._TEA_ROOT_KEYS) == {"trace_output": "out/tr"}


def test_the_root_is_preflights_own_reading_not_a_copy():
    source = SCRIPT.read_text(encoding="utf-8")
    # One reader: this script's copy lost the inline-comment strip.
    for name in ("def _read_toml_or_yaml_flags", "def _strip_inline_comment", "tomllib", "{key}\\s*:"):
        assert name not in source, name
    assert "preflight_check._read_toml_or_yaml_flags(tea_config, _TEA_ROOT_KEYS)" in source
    # Still stdlib-only, so `uv run` needs no environment for it.
    assert "# dependencies = []\n" in source
    # Imported lazily, inside the one function that reads the config.
    assert "\nimport preflight_check" not in source


# --- the verdict a commented config used to change ---------------------------

_RISK = "| Risk ID | Category | P | I | Score | Mitigation |\n|--|--|--|--|--|--|\n| TECH-1 | TECH | 3 | 2 |  | retry |\n"


def _project(root: Path, config: str, tea_dir: str) -> Path:
    for folder in ("planning-artifacts", "impl-artifacts"):
        (root / folder).mkdir(parents=True)
    _config(root, config)
    tea = root / tea_dir
    tea.mkdir(parents=True)
    (tea / "test-design-epic-40.md").write_text(_RISK, encoding="utf-8")
    (root / "planning-artifacts" / "prd-fixture.md").write_text("# PRD\n", encoding="utf-8")
    (root / "planning-artifacts" / "architecture-fixture.md").write_text("# Architecture\n", encoding="utf-8")
    (root / "impl-artifacts" / "sprint-status.yaml").write_text(
        "development_status:\n  epic-40: in-progress\n  40-1-x: backlog\n", encoding="utf-8"
    )
    return root


def _verdict(root: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--epic", "40", "--project-root", str(root),
         "--planning-artifacts", str(root / "planning-artifacts"),
         "--impl-artifacts", str(root / "impl-artifacts"),
         "--tea-config", str(root / "tea" / "config.yaml")],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _gap_kinds(out: dict) -> list[str]:
    return [str(g.get("kind")) for g in out["mechanical_gaps"]]


def test_a_commented_trace_output_still_feeds_the_tea_reader(tmp_path):
    root = _project(tmp_path, "trace_output: {project-root}/trace_out  # where trace writes\n", "trace_out")
    out = _verdict(root)
    # The test-design under the real root is read: its blank Score is a gap,
    # and the nfr-assessment it implies is owed.
    assert "blank_pxi_score" in _gap_kinds(out)
    assert "missing_nfr_assessment" in _gap_kinds(out)


def test_a_commented_root_inside_impl_artifacts_is_no_leak(tmp_path):
    config = "test_artifacts: {project-root}/impl-artifacts/tea  # where TEA writes\n"
    out = _verdict(_project(tmp_path, config, "impl-artifacts/tea"))
    assert "leaked_tea_artifact" not in _gap_kinds(out), out["mechanical_gaps"]
    # Control: an uncommented config naming another root still sees the leak.
    other = _verdict(_project(tmp_path / "other", "test_artifacts: {project-root}/trace_out\n", "impl-artifacts/tea"))
    assert "leaked_tea_artifact" in _gap_kinds(other)
