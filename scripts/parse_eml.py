from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from email import policy
from email.headerregistry import AddressHeader
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any


RAW_EMAIL_DIR = "data/raw/eml"
PARSED_JSON_DIR = "data/raw/json"
CURRENT_USER_ID = "001"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_raw_dir() -> Path:
    return project_root() / RAW_EMAIL_DIR


def default_json_dir() -> Path:
    return project_root() / PARSED_JSON_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse raw .eml files into structured JSON files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned JSON outputs without writing files.",
    )
    return parser.parse_args()


def calculate_email_id(message_id: str) -> str:
    return hashlib.sha256(message_id.encode("utf-8")).hexdigest()


def parse_message(eml_path: Path) -> EmailMessage | Message:
    with eml_path.open("rb") as file:
        return BytesParser(policy=policy.default).parse(file)


def required_header(message: EmailMessage | Message, header_name: str, eml_path: Path) -> str:
    value = message.get(header_name)
    if value is None:
        raise ValueError(f"Missing {header_name} header: {eml_path}")

    text = str(value).strip()
    if not text:
        raise ValueError(f"Empty {header_name} header: {eml_path}")

    return text


def parse_received_at(message: EmailMessage | Message, eml_path: Path) -> str:
    raw_date = required_header(message, "Date", eml_path)
    parsed_date = parsedate_to_datetime(raw_date)
    if parsed_date.tzinfo is None:
        raise ValueError(f"Date header is missing timezone: {eml_path}")

    return parsed_date.isoformat()


def format_address_header(message: EmailMessage | Message, header_name: str) -> str:
    value = message.get(header_name)
    if value is None:
        return ""

    if isinstance(value, AddressHeader):
        return ", ".join(str(address) for address in value.addresses)

    addresses = getaddresses([str(value)])
    formatted = [
        f"{name} <{address}>".strip() if name else address
        for name, address in addresses
        if name or address
    ]
    return ", ".join(formatted) if formatted else str(value).strip()


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_text(source: str) -> str:
    source = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", source)
    source = re.sub(r"(?i)<br\s*/?>", "\n", source)
    source = re.sub(r"(?i)</p\s*>", "\n", source)
    source = re.sub(r"(?i)</div\s*>", "\n", source)
    source = re.sub(r"<[^>]+>", " ", source)
    return normalize_text(html.unescape(source))


def part_text(part: EmailMessage | Message) -> str:
    try:
        content = part.get_content()
    except LookupError:
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        content = payload.decode(charset, errors="replace")

    if isinstance(content, bytes):
        charset = part.get_content_charset() or "utf-8"
        return content.decode(charset, errors="replace")

    return str(content)


def extract_body_text(message: EmailMessage | Message) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    for part in message.walk():
        if part.is_multipart():
            continue

        disposition = part.get_content_disposition()
        if disposition == "attachment":
            continue

        content_type = part.get_content_type()
        if content_type == "text/plain":
            text = normalize_text(part_text(part))
            if text:
                plain_parts.append(text)
        elif content_type == "text/html":
            text = html_to_text(part_text(part))
            if text:
                html_parts.append(text)

    # Prefer explicit plain text because HTML fallback can lose layout and links.
    if plain_parts:
        return normalize_text("\n\n".join(plain_parts))

    return normalize_text("\n\n".join(html_parts))


def parse_eml(eml_path: Path, user_id: str) -> dict[str, Any]:
    message = parse_message(eml_path)
    message_id = required_header(message, "Message-ID", eml_path)

    return {
        "email_id": calculate_email_id(message_id),
        "message_id": message_id,
        "user_id": user_id,
        "sender": format_address_header(message, "From"),
        "recipient": format_address_header(message, "To"),
        "received_at": parse_received_at(message, eml_path),
        "subject": str(message.get("Subject", "")).strip(),
        "body_text": extract_body_text(message),
        "source_path": eml_path.relative_to(project_root()).as_posix(),
        "category": {
            "label": None,
            "confidence": None,
            "source": None,
            "review_required": None,
        },
        "company": {
            "selected": {
                "normalized": None,
                "raw": None,
                "confidence": None,
                "source": None,
                "review_required": None,
            },
            "candidates": [],
        },
        "position": {
            "selected": {
                "normalized": None,
                "raw": None,
                "confidence": None,
                "source": None,
                "review_required": None,
            },
            "candidates": [],
        },
    }


def validate_unique(records: list[tuple[Path, dict[str, Any]]]) -> None:
    message_ids: dict[str, Path] = {}
    email_ids: dict[str, tuple[str, Path]] = {}

    for eml_path, record in records:
        message_id = str(record["message_id"])
        email_id = str(record["email_id"])

        existing_message_path = message_ids.get(message_id)
        if existing_message_path is not None:
            raise ValueError(
                "Duplicate Message-ID: "
                f"{message_id} in {existing_message_path} and {eml_path}"
            )
        message_ids[message_id] = eml_path

        existing_email = email_ids.get(email_id)
        if existing_email is not None and existing_email[0] != message_id:
            raise ValueError(
                "Email ID hash collision: "
                f"{email_id} maps to {existing_email[0]} in {existing_email[1]} "
                f"and {message_id} in {eml_path}"
            )
        email_ids[email_id] = (message_id, eml_path)


def output_path_for(eml_path: Path, json_dir: Path) -> Path:
    return json_dir / eml_path.with_suffix(".json").name


def write_records(records: list[tuple[Path, dict[str, Any]]], json_dir: Path) -> None:
    json_dir.mkdir(parents=True, exist_ok=True)
    for eml_path, record in records:
        output_path = output_path_for(eml_path, json_dir)
        with output_path.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(record, file, ensure_ascii=False, indent=2)
            file.write("\n")


def parse_raw_dir(
    raw_dir: Path,
    json_dir: Path = default_json_dir(),
    user_id: str = CURRENT_USER_ID,
    dry_run: bool = False,
) -> list[Path]:
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw directory does not exist: {raw_dir}")

    records = [
        (eml_path, parse_eml(eml_path, user_id))
        for eml_path in sorted(raw_dir.glob("*.eml"))
    ]
    validate_unique(records)
    if not dry_run:
        write_records(records, json_dir)
    return [output_path_for(eml_path, json_dir) for eml_path, _record in records]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    outputs = parse_raw_dir(default_raw_dir(), dry_run=args.dry_run)
    if not outputs:
        print("No .eml files found.")
        return

    for output_path in outputs:
        print("Would create:" if args.dry_run else "Created:")
        print(f"  {output_path}")


if __name__ == "__main__":
    main()
