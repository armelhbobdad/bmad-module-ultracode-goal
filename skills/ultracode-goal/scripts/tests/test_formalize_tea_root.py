"""formalize_check.py reads TEA's test-artifacts root as preflight resolves it.

The TEA-reader reads TEA's files under the root preflight injects as
ULTRACODE_TEST_ARTIFACTS: the TEA config's `test_artifacts:` scalar, else
`_bmad-output/test-artifacts`. The leak check exempts that root and a set
`trace_output:`, a key TEA 1.27.2 does not wire. formalize_check.py once read
the config with a copy of preflight_check.py's reader that never got the
inline-comment strip, and once took `trace_output` for the root TEA writes
under. These tests pin the reading to preflight's own.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS / "formalize_check.py"
DEFAULT = "_bmad-output/test-artifacts"


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


# (id, config text, the artifacts root relative to the project root, a set trace_output or None)
_VALUES = [
    ("plain", "test_artifacts: out/ta\n", "out/ta", None),
    ("commented", "test_artifacts: out/ta  # where TEA writes\n", "out/ta", None),
    ("trace-commented", "trace_output: out/tr  # where trace writes\n", DEFAULT, "out/tr"),
    ("double-quoted", 'test_artifacts: "out/ta" # where TEA writes\n', "out/ta", None),
    ("single-quoted", "test_artifacts: 'out/ta'  # where TEA writes\n", "out/ta", None),
    ("hash-in-value", "test_artifacts: out/a#b\n", "out/a#b", None),
    ("hash-in-quotes", 'test_artifacts: "out/a #b"  # note\n', "out/a #b", None),
    ("project-root", "trace_output: {project-root}/tr  # note\n", DEFAULT, "tr"),
    ("no-value-then-nested", "test_artifacts:\n  nested: x\n", DEFAULT, None),
    ("comment-only", "test_artifacts:  # set by TEA\n", DEFAULT, None),
    ("comment-only-trace", "trace_output:   # set once TEA traces\ntest_artifacts: out/ta\n", "out/ta", None),
    ("commented-out", "# test_artifacts: out/old\n", DEFAULT, None),
    ("installer", 'test_artifacts: "{project-root}/out/ta"\ntrace_output: out/ta/traceability\n',
     "out/ta", "out/ta/traceability"),
    ("trace-first", "trace_output: out/tr\ntest_artifacts: out/ta\n", "out/ta", "out/tr"),
    ("trace-last", "test_artifacts: out/ta\ntrace_output: out/tr\n", "out/ta", "out/tr"),
    ("empty-trace", 'trace_output: ""\ntest_artifacts: out/ta\n', "out/ta", None),
    ("same-folder", "test_artifacts: out/ta\ntrace_output: out/ta\n", "out/ta", None),
    ("neither-key", "test_framework: pytest\n", DEFAULT, None),
]


@pytest.mark.parametrize(("body", "artifacts", "trace"), [v[1:] for v in _VALUES], ids=[v[0] for v in _VALUES])
def test_the_roots_are_read_as_preflight_reads_the_values(tmp_path, body, artifacts, trace):
    roots = fc._tea_roots(_config(tmp_path, body), tmp_path)
    assert roots.artifacts == tmp_path / artifacts
    assert roots.exempt == (tmp_path / artifacts,) + ((tmp_path / trace,) if trace else ())


@pytest.mark.parametrize("body", [v[1] for v in _VALUES], ids=[v[0] for v in _VALUES])
def test_the_artifacts_root_is_preflights_own(tmp_path, body):
    config = _config(tmp_path, body)
    assert fc._tea_roots(config, tmp_path).artifacts == pc._tea_artifacts_root(
        tmp_path, pc._read_toml_or_yaml_flags(config)
    )


def test_a_toml_config_drops_its_comment(tmp_path):
    config = _config(tmp_path, 'test_artifacts = "out/ta"  # where TEA writes\n', "config.toml")
    assert fc._tea_roots(config, tmp_path).artifacts == tmp_path / "out/ta"


def test_an_absolute_value_is_read_where_it_is(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    config = _config(tmp_path / "project", f"test_artifacts: {elsewhere.as_posix()}  # note\n")
    assert fc._tea_roots(config, tmp_path / "project").artifacts == elsewhere


def test_a_missing_config_reads_the_default_root(tmp_path):
    for config in (tmp_path / "tea" / "config.yaml", tmp_path):
        roots = fc._tea_roots(config, tmp_path)
        assert roots.artifacts == tmp_path / DEFAULT
        assert roots.exempt == (tmp_path / DEFAULT,)


def test_an_unreadable_config_yields_no_root(tmp_path, monkeypatch):
    config = _config(tmp_path, "test_artifacts: out/ta\n")
    assert fc._tea_roots(config, tmp_path).artifacts == tmp_path / "out/ta"

    def unreadable(path, keys=()):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(sys.modules["preflight_check"], "_read_toml_or_yaml_flags", unreadable)
    assert fc._tea_roots(config, tmp_path) is None


def test_the_default_keys_still_read_teas_flags(tmp_path):
    config = _config(tmp_path, "trace_output: out/tr\ntest_framework: pytest  # note\n")
    assert pc._read_toml_or_yaml_flags(config) == {"test_framework": "pytest"}
    assert pc._read_toml_or_yaml_flags(config, fc._TEA_ROOT_KEYS) == {"trace_output": "out/tr"}


def test_the_root_is_preflights_own_reading_not_a_copy():
    source = SCRIPT.read_text(encoding="utf-8")
    # One reader: this script's copy lost the inline-comment strip.
    for name in ("def _read_toml_or_yaml_flags", "def _strip_inline_comment", "tomllib", "{key}\\s*:",
                 "def _tea_trace_output_root", "def _find_under", '"test-artifacts"'):
        assert name not in source, name
    assert "preflight_check._read_toml_or_yaml_flags(tea_config, _TEA_ROOT_KEYS)" in source
    assert "preflight_check._tea_artifacts_root(project_root, flags)" in source
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


def test_a_commented_test_artifacts_still_feeds_the_tea_reader(tmp_path):
    root = _project(tmp_path, "test_artifacts: {project-root}/ta  # where TEA writes\n", "ta")
    out = _verdict(root)
    # The Epic's test-design under the real root is read: its blank Score is a
    # gap. No NFR assessment is owed before the Epic is built.
    assert "blank_pxi_score" in _gap_kinds(out)
    assert "missing_nfr_assessment" not in _gap_kinds(out)


def test_trace_output_is_no_root_the_tea_reader_reads(tmp_path):
    # TEA 1.27.2 writes nothing under trace_output, so a test-design there is not read.
    root = _project(tmp_path, "trace_output: {project-root}/trace_out  # where trace writes\n", "trace_out")
    assert "blank_pxi_score" not in _gap_kinds(_verdict(root))


def test_a_commented_root_inside_impl_artifacts_is_no_leak(tmp_path):
    config = "test_artifacts: {project-root}/impl-artifacts/tea  # where TEA writes\n"
    out = _verdict(_project(tmp_path, config, "impl-artifacts/tea"))
    assert "leaked_tea_artifact" not in _gap_kinds(out), out["mechanical_gaps"]
    # Control: an uncommented config naming another root still sees the leak.
    other = _verdict(_project(tmp_path / "other", "test_artifacts: {project-root}/trace_out\n", "impl-artifacts/tea"))
    assert "leaked_tea_artifact" in _gap_kinds(other)
