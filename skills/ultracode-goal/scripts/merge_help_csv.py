#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Merge this module's help entries into a shared BMad help CSV.

Reads ./assets/module-help.csv and merges its rows into a target CSV —
{project-root}/_bmad/module-help.csv (the standalone self-registration
convention) and/or {project-root}/_bmad/_config/bmad-help.csv (the assembled
catalog the installed bmad-help skill loads). Uses an anti-zombie pattern:
all existing rows matching this module's code (column 1) are removed before
appending fresh rows, so re-running is idempotent and stale entries never
persist.

The merge is positional: when the target already exists, its header line is
kept as-is. The source header spells columns 9-10 `preceded-by`/`followed-by`
— the BMad-canonical names, matching every live module-help.csv, the assembled
bmad-help.csv, and the standalone-module validator. Because the merge maps by
position (the target header is authoritative), even a legacy source that still
spelled those columns `after`/`before` would transfer verbatim either way.

With --module-yaml, a `_meta` docs row is synthesized from module.yaml's
`name` and `docs_llms` and merged ahead of the source rows — the same row the
npx installer assembles, so both registration paths produce identical catalog
state. Source CSVs never author `_meta` rows themselves (the standalone-module
validator treats `_meta` as an orphan skill reference).

Exit codes: 0=success, 1=validation error, 2=runtime error
"""

import argparse
import csv
import json
import sys
from io import StringIO
from pathlib import Path

# Fallback header, used only when neither the target nor the source carries
# one. Matches the BMad-canonical convention (preceded-by/followed-by) shared by
# every live module-help.csv and the assembled catalog.
HEADER = [
    "module",
    "skill",
    "display-name",
    "menu-code",
    "description",
    "action",
    "args",
    "phase",
    "preceded-by",
    "followed-by",
    "required",
    "output-location",
    "outputs",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Merge module help entries into a shared BMad help CSV with an anti-zombie pattern."
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Path to the target help CSV (e.g. _bmad/module-help.csv or _bmad/_config/bmad-help.csv)",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the source module-help.csv with entries to merge",
    )
    parser.add_argument(
        "--module-yaml",
        help="Path to assets/module.yaml; synthesizes the module's _meta docs row from its name and docs_llms fields.",
    )
    parser.add_argument(
        "--legacy-dir",
        help="Path to _bmad/ directory to check for legacy per-module CSV files.",
    )
    parser.add_argument(
        "--module-code",
        help="Module code (required with --legacy-dir for scoping cleanup).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress to stderr",
    )
    return parser.parse_args()


def read_csv_rows(path: str) -> tuple[list[str], list[list[str]]]:
    """Read CSV file returning (header, data_rows).

    Returns empty header and rows if file doesn't exist.
    """
    file_path = Path(path)
    if not file_path.exists():
        return [], []

    with open(file_path, "r", encoding="utf-8", newline="") as f:
        content = f.read()

    reader = csv.reader(StringIO(content))
    rows = list(reader)

    if not rows:
        return [], []

    return rows[0], rows[1:]


def parse_module_scalars(path: str) -> dict[str, str]:
    """Read top-level single-line scalar values from a module.yaml.

    Deliberately minimal (stdlib-only): comments, indented/nested keys, and
    block scalars (`>`/`|`) are skipped. Sufficient for `name` and
    `docs_llms`, which are plain quoted scalars.
    """
    result: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line or line[0] in (" ", "\t", "#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.strip().strip('"').strip("'")
        if value and value not in (">", "|"):
            result[key.strip()] = value
    return result


def build_meta_row(module_yaml_path: str, column_count: int) -> list[str] | None:
    """Synthesize the `_meta` docs row the assembled catalog convention uses.

    Returns None when module.yaml lacks `name` or `docs_llms`.
    """
    scalars = parse_module_scalars(module_yaml_path)
    name = scalars.get("name", "")
    docs_llms = scalars.get("docs_llms", "")
    if not name or not docs_llms:
        return None
    row = [""] * column_count
    row[0] = name
    row[1] = "_meta"
    row[10] = "false"  # required
    row[11] = docs_llms  # output-location carries the docs URL
    return row


def extract_module_codes(rows: list[list[str]]) -> set[str]:
    """Extract unique module codes from data rows."""
    codes = set()
    for row in rows:
        if row and row[0].strip():
            codes.add(row[0].strip())
    return codes


def filter_rows(rows: list[list[str]], module_code: str) -> list[list[str]]:
    """Remove all rows matching the given module code."""
    return [row for row in rows if not row or row[0].strip() != module_code]


def write_csv(path: str, header: list[str], rows: list[list[str]], verbose: bool = False) -> None:
    """Write header + rows to CSV file, creating parent dirs as needed."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"Writing {len(rows)} data rows to {path}", file=sys.stderr)

    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def cleanup_legacy_csvs(legacy_dir: str, module_code: str, verbose: bool = False) -> list:
    """Delete legacy per-module module-help.csv files for this module and core only.

    Returns list of deleted file paths.
    """
    deleted = []
    for subdir in (module_code, "core"):
        legacy_path = Path(legacy_dir) / subdir / "module-help.csv"
        if legacy_path.exists():
            if verbose:
                print(f"Deleting legacy CSV: {legacy_path}", file=sys.stderr)
            legacy_path.unlink()
            deleted.append(str(legacy_path))
    return deleted


def main():
    args = parse_args()

    # Read source entries
    source_header, source_rows = read_csv_rows(args.source)
    if not source_rows:
        print(f"Error: No data rows found in source {args.source}", file=sys.stderr)
        sys.exit(1)

    # Synthesize the _meta docs row (assembler-owned, never source-authored)
    if args.module_yaml:
        if not Path(args.module_yaml).exists():
            print(f"Error: module.yaml not found at {args.module_yaml}", file=sys.stderr)
            sys.exit(1)
        meta_row = build_meta_row(args.module_yaml, len(source_header) if source_header else len(HEADER))
        if meta_row:
            source_rows = [meta_row, *source_rows]

    # Determine module codes being merged
    source_codes = extract_module_codes(source_rows)
    if not source_codes:
        print("Error: Could not determine module code from source rows", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Source module codes: {source_codes}", file=sys.stderr)
        print(f"Source rows: {len(source_rows)}", file=sys.stderr)

    # Read existing target (may not exist)
    target_header, target_rows = read_csv_rows(args.target)
    target_existed = Path(args.target).exists()

    if args.verbose:
        print(f"Target exists: {target_existed}", file=sys.stderr)
        if target_existed:
            print(f"Existing target rows: {len(target_rows)}", file=sys.stderr)

    # Use target header when present (positional merge keeps the catalog's
    # own column names authoritative), else the source's, else the fallback.
    header = target_header if target_header else (source_header if source_header else HEADER)

    # Anti-zombie: remove all rows for each source module code
    filtered_rows = target_rows
    removed_count = 0
    for code in source_codes:
        before_count = len(filtered_rows)
        filtered_rows = filter_rows(filtered_rows, code)
        removed_count += before_count - len(filtered_rows)

    if args.verbose and removed_count > 0:
        print(f"Removed {removed_count} existing rows (anti-zombie)", file=sys.stderr)

    # Append source rows
    merged_rows = filtered_rows + source_rows

    # Write result
    write_csv(args.target, header, merged_rows, args.verbose)

    # Legacy cleanup: delete old per-module CSV files
    legacy_deleted = []
    if args.legacy_dir:
        if not args.module_code:
            print(
                "Error: --module-code is required when --legacy-dir is provided",
                file=sys.stderr,
            )
            sys.exit(1)
        legacy_deleted = cleanup_legacy_csvs(args.legacy_dir, args.module_code, args.verbose)

    # Output result summary as JSON
    result = {
        "status": "success",
        "target_path": str(Path(args.target).resolve()),
        "target_existed": target_existed,
        "module_codes": sorted(source_codes),
        "rows_removed": removed_count,
        "rows_added": len(source_rows),
        "total_rows": len(merged_rows),
        "legacy_csvs_deleted": legacy_deleted,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
