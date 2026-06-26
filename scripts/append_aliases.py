from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


EML_JSON_DIR = "data/raw/eml/parsed"
JD_JSON_DIR = "data/raw/jd/parsed"
ALIAS_DIR = "data/raw/entity_aliases"
ALIAS_FILES = {
    "company": "company_aliases.csv",
    "position": "position_aliases.csv",
}
ALIAS_COLUMNS = ("normalized", "raw")


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append raw company and position aliases from parsed EML and JD JSON."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposed alias additions without writing CSV files.",
    )
    return parser.parse_args()


def load_record(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        record = json.load(file)

    if not isinstance(record, dict):
        raise ValueError(f"Top-level JSON value must be an object: {path}")
    return record


def clean_raw(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    raw = value.strip()
    return raw or None


def selected_raw(record: dict[str, Any], entity_name: str) -> str | None:
    entity = record.get(entity_name)
    if not isinstance(entity, dict):
        return None

    selected = entity.get("selected")
    if not isinstance(selected, dict):
        return None

    return clean_raw(selected.get("raw"))


def append_unique(values: list[str], seen: set[str], raw: str | None) -> None:
    if raw is None:
        return

    dedupe_key = raw.casefold()
    if dedupe_key in seen:
        return

    seen.add(dedupe_key)
    values.append(raw)


def collect_eml_raw_values(eml_json_dir: Path) -> dict[str, list[str]]:
    if not eml_json_dir.is_dir():
        raise FileNotFoundError(f"EML JSON directory does not exist: {eml_json_dir}")

    values: dict[str, list[str]] = {entity_name: [] for entity_name in ALIAS_FILES}
    seen: dict[str, set[str]] = {entity_name: set() for entity_name in ALIAS_FILES}

    for path in sorted(eml_json_dir.glob("*.json")):
        record = load_record(path)
        for entity_name in ALIAS_FILES:
            append_unique(
                values[entity_name],
                seen[entity_name],
                selected_raw(record, entity_name),
            )

    return values


def collect_jd_raw_values(jd_json_dir: Path) -> dict[str, list[str]]:
    if not jd_json_dir.is_dir():
        raise FileNotFoundError(f"JD JSON directory does not exist: {jd_json_dir}")

    values: dict[str, list[str]] = {entity_name: [] for entity_name in ALIAS_FILES}
    seen: dict[str, set[str]] = {entity_name: set() for entity_name in ALIAS_FILES}

    for path in sorted(jd_json_dir.glob("*.json")):
        record = load_record(path)
        append_unique(values["company"], seen["company"], clean_raw(record.get("Company")))
        append_unique(values["position"], seen["position"], clean_raw(record.get("Position")))

    return values


def collect_raw_values(root: Path) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {entity_name: [] for entity_name in ALIAS_FILES}
    seen: dict[str, set[str]] = {entity_name: set() for entity_name in ALIAS_FILES}

    # EML selected.raw values come first because they are grounded in application
    # emails; JD raw values fill in broader known company/position aliases.
    for source_values in (
        collect_eml_raw_values(root / EML_JSON_DIR),
        collect_jd_raw_values(root / JD_JSON_DIR),
    ):
        for entity_name, raw_values in source_values.items():
            for raw in raw_values:
                append_unique(values[entity_name], seen[entity_name], raw)

    return values


def read_alias_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != list(ALIAS_COLUMNS):
            raise ValueError(
                f"{path} must have exactly these columns: {', '.join(ALIAS_COLUMNS)}"
            )
        return [
            {
                "normalized": row.get("normalized", ""),
                "raw": row.get("raw", ""),
            }
            for row in reader
        ]


def write_alias_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ALIAS_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def alias_additions(
    rows: list[dict[str, str]],
    raw_values: list[str],
) -> list[dict[str, str]]:
    existing_raw = {
        row.get("raw", "").casefold()
        for row in rows
        if row.get("raw", "").strip()
    }
    return [
        {"normalized": "", "raw": raw}
        for raw in raw_values
        if raw.casefold() not in existing_raw
    ]


def append_aliases(dry_run: bool) -> int:
    root = project_root()
    raw_values = collect_raw_values(root)

    for entity_name, file_name in ALIAS_FILES.items():
        alias_path = root / ALIAS_DIR / file_name
        rows = read_alias_rows(alias_path)
        additions = alias_additions(rows, raw_values[entity_name])

        print(f"{entity_name}: {len(additions)} new alias row(s)")
        for row in additions:
            print(f"  {row['raw']}")

        if not dry_run and (additions or not alias_path.exists()):
            write_alias_rows(alias_path, rows + additions)

    return 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    try:
        raise SystemExit(append_aliases(args.dry_run))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
