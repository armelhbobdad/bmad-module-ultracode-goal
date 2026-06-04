#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for merge-help-csv.py.

Run: uv run --with pytest pytest scripts/tests/test_merge_help_csv.py -v

Covers fresh-target creation, the anti-zombie idempotency guarantee,
foreign-row preservation, positional header preservation when merging an
after/before source into a preceded-by/followed-by catalog, and the
no-data-rows validation error.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "merge-help-csv.py"

SOURCE_HEADER = (
    "module,skill,display-name,menu-code,description,action,args,phase,"
    "after,before,required,output-location,outputs"
)
CATALOG_HEADER = (
    "module,skill,display-name,menu-code,description,action,args,phase,"
    "preceded-by,followed-by,required,output-location,outputs"
)
UCG_MAIN = (
    'UltraCode Goal,ultracode-goal,Run Epic Autonomously,UG,"Run a BMAD Epic, autonomously.",,'
    ",4-implementation,bmad-sprint-planning,bmad-retrospective,false,implementation_artifacts,run-report.md"
)
# Second capability row: keeps multi-row merge mechanics covered (source CSVs
# never author _meta rows — those are assembler-owned, see --module-yaml).
UCG_EXTRA = (
    "UltraCode Goal,ultracode-goal,Epic Retrospective,UR,Review a completed Epic run.,retro,,"
    "4-implementation,,,false,implementation_artifacts,retrospective"
)
FOREIGN_ROW = (
    "BMad Builder,bmad-module-builder,Validate Module,VM,Check module structure.,validate-module,,"
    "anytime,,,false,bmad_builder_reports,validation report"
)


def write_source(tmp_path: Path, rows: list[str] | None = None) -> Path:
    # Lives in its own assets/ subdir so a target named module-help.csv in
    # tmp_path never collides with the source file.
    source_dir = tmp_path / "assets"
    source_dir.mkdir(exist_ok=True)
    source = source_dir / "module-help.csv"
    lines = [SOURCE_HEADER, *(rows if rows is not None else [UCG_MAIN, UCG_EXTRA])]
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return source


def run_merge(target: Path, source: Path, extra: list[str] | None = None):
    cmd = [sys.executable, str(SCRIPT), "--target", str(target), "--source", str(source)]
    if extra:
        cmd += extra
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def read_rows(target: Path) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(StringIO(target.read_text(encoding="utf-8"))))
    return rows[0], rows[1:]


def test_creates_missing_target_with_source_header(tmp_path):
    source = write_source(tmp_path)
    target = tmp_path / "_bmad" / "module-help.csv"

    proc = run_merge(target, source)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "success"
    assert result["target_existed"] is False
    assert result["rows_added"] == 2

    header, rows = read_rows(target)
    assert ",".join(header) == SOURCE_HEADER
    assert len(rows) == 2


def test_anti_zombie_rerun_is_idempotent(tmp_path):
    source = write_source(tmp_path)
    target = tmp_path / "module-help.csv"

    run_merge(target, source)
    proc = run_merge(target, source)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["rows_removed"] == 2
    assert result["rows_added"] == 2

    _, rows = read_rows(target)
    assert len(rows) == 2  # not 4 — stale rows replaced, never duplicated


def test_preserves_foreign_module_rows(tmp_path):
    source = write_source(tmp_path)
    target = tmp_path / "module-help.csv"
    target.write_text("\n".join([SOURCE_HEADER, FOREIGN_ROW]) + "\n", encoding="utf-8")

    proc = run_merge(target, source)
    assert proc.returncode == 0, proc.stderr

    _, rows = read_rows(target)
    modules = [row[0] for row in rows]
    assert "BMad Builder" in modules
    assert modules.count("UltraCode Goal") == 2


def test_positional_merge_keeps_target_catalog_header(tmp_path):
    # The assembled catalog spells columns 9-10 preceded-by/followed-by; an
    # after/before source must merge positionally without renaming them.
    source = write_source(tmp_path)
    target = tmp_path / "bmad-help.csv"
    target.write_text("\n".join([CATALOG_HEADER, FOREIGN_ROW]) + "\n", encoding="utf-8")

    proc = run_merge(target, source)
    assert proc.returncode == 0, proc.stderr

    header, rows = read_rows(target)
    assert ",".join(header) == CATALOG_HEADER  # target header authoritative
    ucg_main = next(row for row in rows if row[1] == "ultracode-goal")
    assert ucg_main[8] == "bmad-sprint-planning"  # after → preceded-by slot
    assert ucg_main[9] == "bmad-retrospective"  # before → followed-by slot


def test_quoted_description_with_commas_survives_round_trip(tmp_path):
    source = write_source(tmp_path)
    target = tmp_path / "module-help.csv"

    run_merge(target, source)
    _, rows = read_rows(target)
    ucg_main = next(row for row in rows if row[1] == "ultracode-goal")
    assert ucg_main[4] == "Run a BMAD Epic, autonomously."


def test_source_without_data_rows_is_a_validation_error(tmp_path):
    source = write_source(tmp_path, rows=[])
    target = tmp_path / "module-help.csv"

    proc = run_merge(target, source)
    assert proc.returncode == 1
    assert "No data rows" in proc.stderr
    assert not target.exists()


def test_legacy_dir_requires_module_code(tmp_path):
    source = write_source(tmp_path)
    target = tmp_path / "module-help.csv"

    proc = run_merge(target, source, extra=["--legacy-dir", str(tmp_path)])
    assert proc.returncode == 1
    assert "--module-code is required" in proc.stderr


def test_module_yaml_synthesizes_meta_row(tmp_path):
    # --module-yaml produces the same _meta docs row the npx installer
    # assembles, so both registration paths converge on identical state.
    source = write_source(tmp_path)
    module_yaml = tmp_path / "module.yaml"
    module_yaml.write_text(
        'code: ultracode-goal\nname: "UltraCode Goal"\n'
        'docs_llms: "https://example.test/llms.txt"\nmodule_greeting: >\n  Hi there.\n',
        encoding="utf-8",
    )
    target = tmp_path / "bmad-help.csv"

    proc = run_merge(target, source, extra=["--module-yaml", str(module_yaml)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["rows_added"] == 3  # _meta + the 2 source rows

    _, rows = read_rows(target)
    meta = next(row for row in rows if row[1] == "_meta")
    assert meta[0] == "UltraCode Goal"
    assert meta[10] == "false"
    assert meta[11] == "https://example.test/llms.txt"
    assert len(meta) == 13


def test_module_yaml_without_docs_llms_skips_meta_row(tmp_path):
    source = write_source(tmp_path)
    module_yaml = tmp_path / "module.yaml"
    module_yaml.write_text('code: ultracode-goal\nname: "UltraCode Goal"\n', encoding="utf-8")
    target = tmp_path / "bmad-help.csv"

    proc = run_merge(target, source, extra=["--module-yaml", str(module_yaml)])
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["rows_added"] == 2  # source rows only

    _, rows = read_rows(target)
    assert not any(row[1] == "_meta" for row in rows)


def test_missing_module_yaml_is_a_validation_error(tmp_path):
    source = write_source(tmp_path)
    target = tmp_path / "bmad-help.csv"

    proc = run_merge(target, source, extra=["--module-yaml", str(tmp_path / "nope.yaml")])
    assert proc.returncode == 1
    assert "module.yaml not found" in proc.stderr


def test_legacy_cleanup_removes_per_module_csvs(tmp_path):
    source = write_source(tmp_path)
    target = tmp_path / "module-help.csv"
    legacy = tmp_path / "_bmad"
    for subdir in ("ultracode-goal", "core", "other-module"):
        (legacy / subdir).mkdir(parents=True)
        (legacy / subdir / "module-help.csv").write_text(SOURCE_HEADER + "\n", encoding="utf-8")

    proc = run_merge(target, source, extra=["--legacy-dir", str(legacy), "--module-code", "ultracode-goal"])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert len(result["legacy_csvs_deleted"]) == 2
    assert not (legacy / "ultracode-goal" / "module-help.csv").exists()
    assert not (legacy / "core" / "module-help.csv").exists()
    assert (legacy / "other-module" / "module-help.csv").exists()  # untouched
