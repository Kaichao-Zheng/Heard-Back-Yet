from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from constants import ENTITY_EVIDENCE
from paths import EML_PARSED_DIR, ENV_PATH

load_dotenv(ENV_PATH)

ENTITY_EXTRACTION_MODEL = os.getenv("ENTITY_EXTRACTION_MODEL")
if not ENTITY_EXTRACTION_MODEL:
    raise RuntimeError(
        "ENTITY_EXTRACTION_MODEL is required. Configure it in the project .env file."
    )
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_RESPONSE_RETRIES = 1
MAX_BODY_CHARS = 2000
MIN_CANDIDATE_CONFIDENCE = 0.60
REVIEW_THRESHOLD = 0.80
TOP_CANDIDATE_MARGIN = 0.1
OLLAMA_TIMEOUT_SECONDS = 60

SYSTEM_PROMPT = "Extract job application entities. Return JSON only."

ENTITY_GUIDE = """
Extract employer companies and job positions from this email. Return all reliable candidates.

Rules:
- raw must appear in the email, with only whitespace cleanup.
- confidence should reflect how strongly the email supports the candidate; the highest-confidence candidate is selected.
- source must be "subject" or "body_text", generally "subject" >= "body_text".
- keep distinct aliases or brands as separate candidates.
- return candidates whose confidence is at least 0.75. If none exists, return an empty list.
- Ignore unrelated sections such as job recommendations, whose headings imply guess, recommendation, or similarity.

Entities:
- Company: employer, recruiting brand, company display name, or company domain brand. Generic words such as recruitment, hiring, zhaopin, noreply, mail, system, assessment, interview, or campus recruitment are not company names by themselves.
- Position: explicit job title only, such as engineer, scientist, analyst, intern, manager, designer. Preserve modifiers, levels, tracks, locations, and parenthesized qualifiers that are part of the original title. Do not treat campus recruitment, assessment, test, interview, event, program, or process names as positions.

""".strip()


def default_json_dir() -> Path:
    return EML_PARSED_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract company and position entities from parsed email JSON files."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract files that already have selected company or position raw values.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposed entity updates without writing JSON files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Extract entities from at most this many parsed email JSON files.",
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


def build_prompt(record: dict[str, Any]) -> str:
    body_text = str(record.get("body_text") or "")
    if len(body_text) > MAX_BODY_CHARS:
        body_text = body_text[:MAX_BODY_CHARS] + "\n[TRUNCATED]"

    email_payload = {
        "subject": record.get("subject"),
        "body_text": body_text,
    }

    return (
        "Extract employer company and job position mentions from this parsed recruitment email.\n\n"
        f"{ENTITY_GUIDE}\n\n"
        "Return strict JSON only, with this shape:\n"
        "{"
        '"company_candidates":[{"raw":"company text","confidence":0.0,"source":"subject|body_text"}],'
        '"position_candidates":[{"raw":"position text","confidence":0.0,"source":"subject|body_text"}]'
        "}\n\n"
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


def clean_raw(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    text = re.sub(r"\s+", " ", value).strip()
    text = text.strip(" \t\r\n\"'`[]{}<>:;,.")
    return text or None


def parse_confidence(value: Any) -> float:
    if isinstance(value, str):
        value = float(value)
    if not isinstance(value, (int, float)):
        raise ValueError("Candidate confidence must be a number")

    confidence = float(value)
    if confidence < 0 or confidence > 1:
        raise ValueError(f"Candidate confidence out of range: {confidence}")
    return round(confidence, 3)


def parse_source(value: Any, model: str) -> str:
    if value not in ENTITY_EVIDENCE.values():
        raise ValueError(f"Candidate source must be one of {sorted(ENTITY_EVIDENCE.values())}")
    return f"ollama:{model}:{value}"


def evidence_from_source(source: str) -> str:
    return source.rsplit(":", 1)[-1]


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).casefold()


def raw_supported_by_source(raw: str, source: str, record: dict[str, Any]) -> bool:
    evidence = evidence_from_source(source)
    return normalized_text(raw) in normalized_text(record.get(evidence))


def validate_candidates(
    value: Any,
    model: str,
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("Candidate field must be a list")

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each candidate must be an object")

        raw = clean_raw(item.get("raw"))
        if raw is None:
            continue

        source = parse_source(item.get("source"), model)
        if not raw_supported_by_source(raw, source, record):
            continue

        confidence = parse_confidence(item.get("confidence"))
        if confidence < MIN_CANDIDATE_CONFIDENCE:
            continue

        dedupe_key = raw.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        candidates.append(
            {
                "raw": raw,
                "confidence": confidence,
                "source": source,
            }
        )

    candidates.sort(key=lambda candidate: candidate["confidence"], reverse=True)
    return candidates


def validate_extraction(
    value: dict[str, Any],
    model: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "company_candidates": validate_candidates(
            value.get("company_candidates", []), model, record
        ),
        "position_candidates": validate_candidates(
            value.get("position_candidates", []), model, record
        ),
    }


def fallback_extraction(_error: Exception) -> dict[str, Any]:
    return {
        "company_candidates": [],
        "position_candidates": [],
    }


def extract_record(
    record: dict[str, Any],
    ollama_url: str,
    model: str,
    retries: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    prompt = build_prompt(record)
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            content = call_ollama(ollama_url, model, prompt, timeout_seconds)
            return validate_extraction(parse_model_json(content), model, record)
        except (ValueError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(1)

    if last_error is None:
        last_error = ValueError("entity extraction failed for an unknown reason")
    return fallback_extraction(last_error)


def ensure_entity_slot(record: dict[str, Any], entity_name: str) -> dict[str, Any]:
    entity = record.get(entity_name)
    if not isinstance(entity, dict):
        entity = {}
        record[entity_name] = entity

    selected = entity.get("selected")
    if not isinstance(selected, dict):
        selected = {}
        entity["selected"] = selected

    entity.setdefault("candidates", [])
    return entity


def selected_from_candidates(
    candidates: list[dict[str, Any]],
    review_threshold: float,
) -> dict[str, Any]:
    if not candidates:
        return {
            "raw": None,
            "confidence": None,
            "source": None,
            "review_required": True,
        }

    top = candidates[0]
    runner_up = candidates[1] if len(candidates) > 1 else None
    confidence = float(top["confidence"])
    close_second = (
        runner_up is not None
        and round(confidence - float(runner_up["confidence"]), 3) < TOP_CANDIDATE_MARGIN
    )

    return {
        "raw": top["raw"],
        "confidence": confidence,
        "source": top["source"],
        "review_required": confidence < review_threshold or close_second,
    }


def update_entity(
    record: dict[str, Any],
    entity_name: str,
    candidates: list[dict[str, Any]],
    review_threshold: float,
) -> None:
    entity = ensure_entity_slot(record, entity_name)
    entity["selected"] = selected_from_candidates(candidates, review_threshold)
    selected_raw_value = entity["selected"].get("raw")
    if selected_raw_value is None:
        entity["candidates"] = []
        return

    selected_key = selected_raw_value.casefold()
    entity["candidates"] = [
        candidate
        for candidate in candidates
        if str(candidate.get("raw", "")).casefold() != selected_key
    ]


def selected_raw(record: dict[str, Any], entity_name: str) -> str | None:
    entity = record.get(entity_name)
    if not isinstance(entity, dict):
        return None
    selected = entity.get("selected")
    if not isinstance(selected, dict):
        return None
    raw = selected.get("raw")
    return raw if isinstance(raw, str) and raw.strip() else None


def should_skip(record: dict[str, Any], force: bool) -> bool:
    if force:
        return False
    return selected_raw(record, "company") is not None or selected_raw(record, "position") is not None


def extract_files(args: argparse.Namespace) -> int:
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
            extraction = extract_record(
                record=record,
                ollama_url=DEFAULT_OLLAMA_URL,
                model=ENTITY_EXTRACTION_MODEL,
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

        update_entity(
            record,
            "company",
            extraction["company_candidates"],
            REVIEW_THRESHOLD,
        )
        update_entity(
            record,
            "position",
            extraction["position_candidates"],
            REVIEW_THRESHOLD,
        )

        company = record["company"]["selected"]
        position = record["position"]["selected"]
        print(
            f"{'Would update' if args.dry_run else 'Updated'}: {path}\n"
            f"  company -> {company['raw']!r} "
            f"({company['confidence']}, review_required={company['review_required']})\n"
            f"  position -> {position['raw']!r} "
            f"({position['confidence']}, review_required={position['review_required']})"
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
        raise SystemExit(extract_files(args))
    except (OSError, ValueError, urllib.error.URLError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
