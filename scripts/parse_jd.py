from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


RAW_JD_DIR = "data/raw/jd"
PARSED_JD_DIR = "data/raw/jd/parsed"
JD_EXTENSIONS = {".md", ".markdown"}
JD_FILENAME_PATTERN = re.compile(r"^\d{8}_.+")


@dataclass(frozen=True)
class ParseResult:
    status: str
    source: Path
    output: Path | None = None
    reason: str | None = None


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_raw_dir() -> Path:
    return project_root() / RAW_JD_DIR


def default_json_dir() -> Path:
    return project_root() / PARSED_JD_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert JD Markdown files into JSON keyed by level-one headings."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned JSON outputs without writing files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recreate JD JSON files that already exist.",
    )
    return parser.parse_args()


def iter_jd_markdown(raw_dir: Path) -> list[Path]:
    paths = [
        path
        for path in raw_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in JD_EXTENSIONS
        and JD_FILENAME_PATTERN.match(path.stem)
    ]
    return sorted(paths, key=lambda path: path.name.lower())


def clean_heading(raw_heading: str) -> str:
    return raw_heading.strip().rstrip("#").strip()


def parse_jd_markdown(markdown_text: str, source_path: Path) -> dict[str, str]:
    records: dict[str, list[str]] = {}
    current_heading: str | None = None
    heading_pattern = re.compile(r"^#(?!#)\s+(.+?)\s*$")

    for line in markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = heading_pattern.match(line)
        if match:
            current_heading = clean_heading(match.group(1))
            if not current_heading:
                raise ValueError(f"Empty level-one heading: {source_path}")
            if current_heading in records:
                raise ValueError(
                    f"Duplicate level-one heading '{current_heading}': {source_path}"
                )
            records[current_heading] = []
            continue

        if current_heading is not None:
            records[current_heading].append(line)

    if not records:
        raise ValueError(f"No level-one headings found: {source_path}")

    # Only convert H1 section boundaries into JSON keys; keep section text as-is.
    return {heading: "\n".join(lines).strip() for heading, lines in records.items()}


def parse_jd_file(jd_path: Path) -> dict[str, str]:
    markdown_text = jd_path.read_text(encoding="utf-8")
    return parse_jd_markdown(markdown_text, jd_path)


def output_path_for(jd_path: Path, json_dir: Path) -> Path:
    return json_dir / jd_path.with_suffix(".json").name


def write_record(jd_path: Path, record: dict[str, str], json_dir: Path) -> None:
    json_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_path_for(jd_path, json_dir)
    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(record, file, ensure_ascii=False, indent=2)
        file.write("\n")


def parse_raw_dir(
    raw_dir: Path = default_raw_dir(),
    json_dir: Path = default_json_dir(),
    dry_run: bool = False,
    force: bool = False,
) -> list[ParseResult]:
    if not raw_dir.exists():
        raise FileNotFoundError(f"JD directory does not exist: {raw_dir}")
    if not raw_dir.is_dir():
        raise NotADirectoryError(f"JD path is not a directory: {raw_dir}")

    results: list[ParseResult] = []
    for jd_path in iter_jd_markdown(raw_dir):
        output_path = output_path_for(jd_path, json_dir)
        output_exists = output_path.exists()
        if output_exists and not force:
            results.append(
                ParseResult(
                    status="skipped",
                    source=jd_path,
                    output=output_path,
                    reason="JD JSON already exists",
                )
            )
            continue

        record = parse_jd_file(jd_path)
        if not dry_run:
            write_record(jd_path, record, json_dir)

        results.append(
            ParseResult(
                status="recreated" if output_exists and force else "created",
                source=jd_path,
                output=output_path,
            )
        )

    return results


def print_result(result: ParseResult, dry_run: bool) -> None:
    if result.status == "created":
        print("Would create:" if dry_run else "Created:")
    elif result.status == "recreated":
        print("Would recreate:" if dry_run else "Recreated:")
    elif result.status == "skipped":
        print("Skipped:")
    else:
        print(result.status)

    if result.output is not None:
        print(f"  {result.output}")
    if result.status == "skipped":
        print("From:")
        print(f"  {result.source}")
    if result.reason:
        print("Reason:")
        print(f"  {result.reason}")


def print_summary(results: list[ParseResult]) -> None:
    processed = sum(
        1 for result in results if result.status in {"created", "recreated"}
    )
    skipped = sum(1 for result in results if result.status == "skipped")
    print(f"Processed: {processed}; skipped: {skipped}; failed: 0")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    results = parse_raw_dir(
        dry_run=args.dry_run,
        force=args.force,
    )
    if not results:
        print("No JD Markdown files found.")
        return

    for result in results:
        print_result(result, args.dry_run)
    print_summary(results)


if __name__ == "__main__":
    main()
