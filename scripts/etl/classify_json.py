from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from constants import (
    ALLOWED_CATEGORY_LABELS,
    CATEGORY_EVIDENCE,
    CATEGORY_LABEL_UNKNOWN,
)
from paths import EML_PARSED_DIR


DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
MAX_BODY_CHARS = 1500
MODEL_RESPONSE_RETRIES = 1
REVIEW_THRESHOLD = 0.75
SUBJECT_SENDER_ACCEPT_THRESHOLD = 0.85
OLLAMA_TIMEOUT_SECONDS = 60

SYSTEM_PROMPT = (
    "You classify emails into a closed label set. "
    "You must return only valid JSON and no markdown."
)

LABEL_GUIDE = """
Use exactly one label:
- delivery-failure: bounce, undelivered, failed delivery, mail system error.
- offer: offer, acceptance, contract, compensation, formal hire decision.
- rejection: the application will not continue for this role, regardless of wording. Includes direct rejection, indirect rejection, role filled, another candidate selected, or no longer under consideration.
- interview: interview invitation, confirmation, scheduling, rescheduling, feedback related to an interview.
- assessment: online assessment, coding test, questionnaire, test invitation or reminder.
- applied: application submitted, received, under review, application confirmation.
- auth: login, verification code, account creation, password, MFA, identity verification.
- profile-update: candidate profile, resume/CV, candidate information, or personal information was updated or needs completion.
- logistics: recruiting process notices, arrangements, reminders, instructions, consent/privacy authorization, or next-step prerequisites that do not clearly change application status.
- unknown: job/recruiting related, but the category is unclear from available evidence.
- unrelated: not related to job applications, recruiting, hiring, or career platforms.

Priority when multiple signals appear:
delivery-failure > offer/rejection > interview > assessment > applied > auth > profile-update > logistics > unknown/unrelated.

Use profile-update only when the email is clearly about maintaining candidate profile, resume/CV, or personal information.
Use logistics for process notices or administrative recruiting information when it is not applied, assessment, interview, offer, rejection, auth, or profile-update.
Use unknown when the email appears recruitment-related but its type cannot be determined.

Confidence is your self-reported certainty, not an objective probability.
Return lower confidence for ambiguous or weak evidence.
""".strip()

def default_json_dir() -> Path:
    return EML_PARSED_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify parsed email JSON files with a local Ollama model."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reclassify files that already have category.label.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposed classifications without writing JSON files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Classify at most this many parsed email JSON files.",
    )
    return parser.parse_args()


def iter_json_files(limit: int | None) -> list[Path]:
    path = default_json_dir()
    if not path.is_dir():
        raise FileNotFoundError(f"JSON directory does not exist: {path}")

    paths = sorted(path.glob("*.json"))
    if limit is not None:
        if limit < 0:
            raise ValueError("--limit must be 0 or greater")
        return paths[:limit]
    return paths


def load_record(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Top-level JSON value must be an object: {path}")
    return data


def save_record(path: Path, record: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(record, file, ensure_ascii=False, indent=2)
        file.write("\n")


def build_prompt(record: dict[str, Any], include_body: bool, max_body_chars: int) -> str:
    email_payload = {
        "sender": record.get("sender"),
        "subject": record.get("subject"),
    }

    if include_body:
        body_text = str(record.get("body_text") or "")
        if len(body_text) > max_body_chars:
            body_text = body_text[:max_body_chars] + "\n[TRUNCATED]"
        email_payload[CATEGORY_EVIDENCE["body_excerpt"]] = body_text

    evidence_note = (
        "Use subject as the primary signal and sender as supporting context. Use body_excerpt only as additional evidence."
        if include_body
        else "Use only sender and subject. Return low confidence if they are not enough."
    )

    return (
        "Classify this parsed recruitment email.\n\n"
        f"{LABEL_GUIDE}\n\n"
        f"{evidence_note}\n\n"
        "Return strict JSON only, with this shape:\n"
        '{"label":"one allowed label","confidence":0.0}\n\n'
        "Email JSON:\n"
        f"{json.dumps(email_payload, ensure_ascii=False, indent=2)}"
    )


def call_ollama(ollama_url: str, model: str, prompt: str, timeout_seconds: int) -> str:
    endpoint = ollama_url.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "stream": False,
        "think": False,         # Keep thinking disabled. 
        "format": "json",       # With Qwen thinking mode and format=json, ambiguous emails can overthink until timeout.
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": 0,
        },
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        response_payload = json.loads(response.read().decode("utf-8"))

    content = response_payload.get("message", {}).get("content")
    if not isinstance(content, str):
        raise ValueError("Ollama response did not include message.content")
    return content


def parse_model_json(content: str) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        value = json.loads(content[start : end + 1])

    if not isinstance(value, dict):
        raise ValueError("Model response JSON must be an object")
    return value


def validate_classification(value: dict[str, Any]) -> dict[str, Any]:
    label = value.get("label")
    if label not in ALLOWED_CATEGORY_LABELS:
        raise ValueError(f"Invalid label from model: {label!r}")

    confidence = value.get("confidence")
    if isinstance(confidence, str):
        confidence = float(confidence)
    if not isinstance(confidence, (int, float)):
        raise ValueError("Confidence must be a number")

    confidence = float(confidence)
    if confidence < 0 or confidence > 1:
        raise ValueError(f"Confidence out of range: {confidence}")

    return {
        "label": label,
        "confidence": round(confidence, 3),
    }


def fallback_classification(error: Exception) -> dict[str, Any]:
    _message = str(error).strip()
    return {
        "label": CATEGORY_LABEL_UNKNOWN,
        "confidence": 0.0,
    }


def classify_record(
    record: dict[str, Any],
    ollama_url: str,
    model: str,
    max_body_chars: int,
    retries: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    subject_sender_result = classify_with_evidence(
        record=record,
        include_body=False,
        ollama_url=ollama_url,
        model=model,
        max_body_chars=max_body_chars,
        retries=retries,
        timeout_seconds=timeout_seconds,
    )

    if (
        subject_sender_result["label"] != CATEGORY_LABEL_UNKNOWN
        and subject_sender_result["confidence"] >= SUBJECT_SENDER_ACCEPT_THRESHOLD
    ):
        subject_sender_result["evidence"] = CATEGORY_EVIDENCE["subject_sender"]
        return subject_sender_result

    print("Escalating to body_excerpt:")
    print(
        "  "
        f"subject_sender label={subject_sender_result['label']} "
        f"confidence={subject_sender_result['confidence']:.3f}"
    )
    print("Evidence:")
    print(f"  {CATEGORY_EVIDENCE['body_excerpt']}")
    body_result = classify_with_evidence(
        record=record,
        include_body=True,
        ollama_url=ollama_url,
        model=model,
        max_body_chars=max_body_chars,
        retries=retries,
        timeout_seconds=timeout_seconds,
    )
    body_result["evidence"] = CATEGORY_EVIDENCE["body_excerpt"]
    return body_result


def classify_with_evidence(
    record: dict[str, Any],
    include_body: bool,
    ollama_url: str,
    model: str,
    max_body_chars: int,
    retries: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    prompt = build_prompt(record, include_body, max_body_chars)
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            content = call_ollama(ollama_url, model, prompt, timeout_seconds)
            return validate_classification(parse_model_json(content))
        except (ValueError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(1)

    if last_error is None:
        last_error = ValueError("classification failed for an unknown reason")
    return fallback_classification(last_error)


def should_skip(record: dict[str, Any], force: bool) -> bool:
    if force:
        return False
    category = record.get("category")
    return isinstance(category, dict) and bool(category.get("label"))


def update_category(
    record: dict[str, Any],
    classification: dict[str, Any],
    model: str,
    review_threshold: float,
) -> None:
    category = record.get("category")
    if not isinstance(category, dict):
        category = {}
        record["category"] = category

    confidence = float(classification["confidence"])
    label = str(classification["label"])

    category.update(
        {
            "label": label,
            "confidence": confidence,
            "source": f"ollama:{model}:{classification['evidence']}",
            "review_required": label == CATEGORY_LABEL_UNKNOWN
            or confidence < review_threshold,
        }
    )


def classify_files(args: argparse.Namespace) -> int:
    paths = iter_json_files(args.limit)
    if not paths:
        print("No .json files found.")
        return 0

    processed = 0
    skipped = 0
    failed = 0

    for path in paths:
        record = load_record(path)
        if should_skip(record, args.force):
            skipped += 1
            print("Skipped:")
            print(f"  {path}")
            continue

        try:
            classification = classify_record(
                record=record,
                ollama_url=DEFAULT_OLLAMA_URL,
                model=DEFAULT_MODEL,
                max_body_chars=MAX_BODY_CHARS,
                retries=MODEL_RESPONSE_RETRIES,
                timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
            )
        except (TimeoutError, socket.timeout, urllib.error.URLError) as error:
            failed += 1
            print("Failed:")
            print(f"  {path}")
            print("Reason:")
            print(f"  {error}")
            continue
        update_category(record, classification, DEFAULT_MODEL, REVIEW_THRESHOLD)

        category = record["category"]
        print(
            f"{'Would update' if args.dry_run else 'Updated'}: {path}\n"
            f"  -> {category['label']} ({category['confidence']:.3f}, "
            f"review_required={category['review_required']}, "
            f"source={category['source']})"
        )

        if not args.dry_run:
            save_record(path, record)
        processed += 1

    print(f"Processed: {processed}; skipped: {skipped}; failed: {failed}")
    return 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    try:
        raise SystemExit(classify_files(args))
    except (OSError, ValueError, urllib.error.URLError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
