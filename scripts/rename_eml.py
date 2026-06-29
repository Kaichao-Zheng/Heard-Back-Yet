from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
HASH_PREFIX_LENGTH = 8
WINDOWS_DEDUPE_SUFFIX_PATTERN = re.compile(r"\s*\(\s*\d+\s*\)\s*$")


@dataclass(frozen=True)
class RenameResult:
    status: str
    source: Path
    target: Path | None = None
    message_id_hash: str | None = None
    reason: str | None = None


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_source_dir() -> Path:
    return project_root() / "data" / "raw" / "eml" / "source"


def default_output_dir() -> Path:
    return project_root() / "data" / "raw" / "eml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy imported .eml files from data/raw/eml/source into data/raw/eml with stable names."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned file copies without changing files.",
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


def hash_message_id(message_id: str) -> str:
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
    eml_path: Path, output_dir: Path, timestamp: str, message_id_hash: str
) -> Path:
    hash_prefix = message_id_hash[:HASH_PREFIX_LENGTH]
    return output_dir / f"{timestamp}_{hash_prefix} - {normalized_source_name(eml_path)}"


def rename_eml_files(
    source_dir: Path, output_dir: Path, dry_run: bool = False
) -> list[RenameResult]:
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    results: list[RenameResult] = []
    for eml_path in sorted(source_dir.glob("*.eml")):
        if has_processed_prefix(eml_path):
            results.append(
                RenameResult(
                    status="skipped",
                    source=eml_path,
                    reason="already has stable naming prefix",
                )
            )
            continue

        try:
            timestamp = parse_email_timestamp(eml_path)
        except Exception:
            timestamp = fallback_timestamp(eml_path)

        try:
            message_id = parse_message_id(eml_path)
            message_id_hash = hash_message_id(message_id)
            target = build_target_path(
                eml_path, output_dir, timestamp, message_id_hash
            )
        except (OSError, ValueError) as error:
            results.append(
                RenameResult(status="failed", source=eml_path, reason=str(error))
            )
            continue

        if target.exists():
            try:
                target_message_id = parse_message_id(target)
                status = "duplicate" if target_message_id == message_id else "conflict"
                reason = (
                    "target already exists with same Message-ID"
                    if status == "duplicate"
                    else "target already exists with a different Message-ID"
                )
            except (OSError, ValueError) as error:
                status = "conflict"
                reason = f"target already exists and cannot be verified: {error}"

            results.append(
                RenameResult(
                    status=status,
                    source=eml_path,
                    target=target,
                    message_id_hash=message_id_hash,
                    reason=reason,
                )
            )
            continue

        if not dry_run:
            try:
                shutil.copy2(eml_path, target)
            except OSError as error:
                results.append(
                    RenameResult(
                        status="failed",
                        source=eml_path,
                        target=target,
                        message_id_hash=message_id_hash,
                        reason=str(error),
                    )
                )
                continue

        results.append(
            RenameResult(
                status="copied",
                source=eml_path,
                target=target,
                message_id_hash=message_id_hash,
            )
        )

    return results


def print_result(result: RenameResult, dry_run: bool) -> None:
    labels = {
        "copied": "Would create:" if dry_run else "Created:",
        "duplicate": "Skipped:",
        "conflict": "Skipped:",
        "failed": "Failed:",
        "skipped": "Skipped:",
    }
    print(labels.get(result.status, result.status))
    if result.target is not None:
        print(f"  {result.target}")
    print("From:")
    print(f"  {result.source}")
    if result.status in {"duplicate", "conflict"}:
        print("Status:")
        print(f"  {result.status}")
    if result.message_id_hash is not None:
        print("Message-ID SHA-256:")
        print(f"  {result.message_id_hash}")
    if result.reason:
        print("Reason:")
        print(f"  {result.reason}")


def print_summary(results: list[RenameResult]) -> None:
    counts = {
        "copied": 0,
        "duplicate": 0,
        "conflict": 0,
        "failed": 0,
        "skipped": 0,
    }
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    processed = counts["copied"]
    skipped = counts["duplicate"] + counts["conflict"] + counts["skipped"]
    print(f"Processed: {processed}; skipped: {skipped}; failed: {counts['failed']}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    results = rename_eml_files(
        default_source_dir(), default_output_dir(), dry_run=args.dry_run
    )

    if not results:
        print("No .eml files needed copying.")
        return

    for result in results:
        print_result(result, args.dry_run)
    print_summary(results)


if __name__ == "__main__":
    main()
