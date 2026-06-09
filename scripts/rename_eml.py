from __future__ import annotations

import argparse
import hashlib
import re
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
HASH_PREFIX_LENGTH = 8
WINDOWS_DEDUPE_SUFFIX_PATTERN = re.compile(r"\s*\(\s*\d+\s*\)\s*$")


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_temp_dir() -> Path:
    return project_root() / "data" / "temp"


def default_output_dir() -> Path:
    return project_root() / "data" / "raw" / "eml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move imported .eml files into data/raw/eml with stable names."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned file moves without changing files.",
    )
    return parser.parse_args()


def parse_email_timestamp(eml_path: Path) -> str:
    with eml_path.open("rb") as file:
        message = BytesParser(policy=policy.default).parse(file, headersonly=True)

    date_header = message.get("Date")
    if date_header:
        parsed_date = parsedate_to_datetime(date_header)
        if parsed_date.tzinfo is not None:
            parsed_date = parsed_date.astimezone()
        return parsed_date.strftime(TIMESTAMP_FORMAT)

    # Some exported emails may be missing a Date header. The file timestamp is
    # only a fallback for naming; the raw .eml content is never changed.
    return fallback_timestamp(eml_path)


def fallback_timestamp(eml_path: Path) -> str:
    return datetime.fromtimestamp(eml_path.stat().st_mtime).strftime(TIMESTAMP_FORMAT)


def parse_message_id(eml_path: Path) -> str:
    with eml_path.open("rb") as file:
        message = BytesParser(policy=policy.default).parse(file, headersonly=True)

    message_id = message.get("Message-ID")
    if not message_id:
        raise ValueError(f"Missing Message-ID header: {eml_path}")

    return str(message_id).strip()


def calculate_message_id_hash(message_id: str) -> str:
    return hashlib.sha256(message_id.encode("utf-8")).hexdigest()


def normalized_source_name(eml_path: Path) -> str:
    cleaned_stem = WINDOWS_DEDUPE_SUFFIX_PATTERN.sub("", eml_path.stem).rstrip()
    if not cleaned_stem:
        return eml_path.name

    return f"{cleaned_stem}{eml_path.suffix}"


def has_processed_prefix(eml_path: Path) -> bool:
    stem = eml_path.stem
    separator_start = 16 + HASH_PREFIX_LENGTH
    return (
        len(stem) > separator_start + len(" - ")
        and stem[0:8].isdigit()
        and stem[8] == "_"
        and stem[9:15].isdigit()
        and stem[15] == "_"
        and all(char in "0123456789abcdef" for char in stem[16 : 16 + HASH_PREFIX_LENGTH])
        and stem[separator_start : separator_start + len(" - ")] == " - "
    )


def build_target_path(
    eml_path: Path, output_dir: Path, timestamp: str, email_hash: str
) -> Path:
    hash_prefix = email_hash[:HASH_PREFIX_LENGTH]
    return output_dir / f"{timestamp}_{hash_prefix} - {normalized_source_name(eml_path)}"


def rename_eml_files(
    temp_dir: Path, output_dir: Path, dry_run: bool = False
) -> list[tuple[Path, Path, str]]:
    if not temp_dir.exists():
        raise FileNotFoundError(f"Temp directory does not exist: {temp_dir}")

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    renamed: list[tuple[Path, Path, str]] = []
    for eml_path in sorted(temp_dir.glob("*.eml")):
        if has_processed_prefix(eml_path):
            continue

        try:
            timestamp = parse_email_timestamp(eml_path)
        except Exception:
            timestamp = fallback_timestamp(eml_path)

        message_id = parse_message_id(eml_path)
        email_hash = calculate_message_id_hash(message_id)
        target = build_target_path(eml_path, output_dir, timestamp, email_hash)
        renamed.append((eml_path, target, email_hash))

        if not dry_run:
            eml_path.rename(target)

    return renamed


def main() -> None:
    args = parse_args()
    renamed = rename_eml_files(
        default_temp_dir(), default_output_dir(), dry_run=args.dry_run
    )

    if not renamed:
        print("No .eml files needed moving.")
        return

    for source, target, email_hash in renamed:
        print("Would create:" if args.dry_run else "Created:")
        print(f"  {target}")
        if args.dry_run:
            print("From:")
            print(f"  {source}")
        print(f"Message-ID SHA-256:")
        print(f"  {email_hash}")


if __name__ == "__main__":
    main()
