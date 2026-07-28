from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


from heardbackyet.etl.classify_json import (
    MODEL,
    MODEL_ENDPOINT,
    MAX_BODY_CHARS,
    OLLAMA_TIMEOUT_SECONDS,
    SYSTEM_PROMPT,
    build_prompt,
    load_record,
    parse_model_json,
    validate_classification,
)
from heardbackyet.paths import EML_PARSED_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug one classification Ollama call and show thinking/content chunks."
    )
    parser.add_argument(
        "json_path",
        nargs="?",
        type=Path,
        help="Parsed email JSON path. Defaults to the first parsed EML JSON file.",
    )
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--ollama-url", default=MODEL_ENDPOINT)
    parser.add_argument(
        "--timeout",
        type=int,
        default=OLLAMA_TIMEOUT_SECONDS,
        help="HTTP read timeout in seconds.",
    )
    parser.add_argument(
        "--num-predict",
        type=int,
        default=None,
        help="Optional Ollama num_predict value.",
    )
    parser.add_argument(
        "--include-body",
        action="store_true",
        help="Use classifier body_excerpt prompt instead of sender+subject only.",
    )
    parser.add_argument(
        "--no-format-json",
        action="store_true",
        help="Do not send format=json.",
    )
    parser.add_argument(
        "--no-think",
        action="store_true",
        help="Send think=false.",
    )
    parser.add_argument(
        "--raw-chunks",
        action="store_true",
        help="Print each raw streamed JSON chunk.",
    )
    parser.add_argument(
        "--no-live-text",
        dest="live_text",
        action="store_false",
        help="Do not print streamed thinking/content text as it arrives.",
    )
    parser.set_defaults(live_text=True)
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Print the exact prompt sent to the model.",
    )
    return parser.parse_args()


def default_json_path() -> Path:
    paths = sorted(EML_PARSED_DIR.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"No parsed email JSON files found in {EML_PARSED_DIR}")
    return paths[0]


def resolve_json_path(path: Path | None) -> Path:
    if path is None:
        return default_json_path()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def build_payload(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": args.model,
        "stream": True,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0},
    }
    if not args.no_format_json:
        payload["format"] = "json"
    if args.no_think:
        payload["think"] = False
    if args.num_predict is not None:
        payload["options"]["num_predict"] = args.num_predict
    return payload


def stream_ollama(args: argparse.Namespace, prompt: str) -> tuple[str, str, int, float]:
    endpoint = args.ollama_url.rstrip("/") + "/api/chat"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(build_payload(args, prompt)).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    thinking_parts: list[str] = []
    content_parts: list[str] = []
    chunks = 0
    started = time.monotonic()

    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        for line in response:
            if not line.strip():
                continue
            chunks += 1
            raw = line.decode("utf-8", errors="replace")
            if args.raw_chunks:
                print(raw.rstrip())

            chunk = json.loads(raw)
            message = chunk.get("message", {})
            thinking = message.get("thinking")
            content = message.get("content")
            if isinstance(thinking, str) and thinking:
                thinking_parts.append(thinking)
                if args.live_text:
                    print(thinking, end="", flush=True)
            if isinstance(content, str) and content:
                content_parts.append(content)
                if args.live_text:
                    print(content, end="", flush=True)
            if chunk.get("done"):
                break

    if args.live_text:
        print()

    return (
        "".join(thinking_parts),
        "".join(content_parts),
        chunks,
        time.monotonic() - started,
    )


def print_section(title: str, value: str) -> None:
    print(f"--- {title} ---")
    if value:
        print(value)
    else:
        print("<empty>")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    json_path = resolve_json_path(args.json_path)
    record = load_record(json_path)
    prompt = build_prompt(
        record,
        include_body=args.include_body,
        max_body_chars=MAX_BODY_CHARS,
    )

    print(f"path={json_path}")
    print("task=classification")
    print(f"prompt=classify_json.build_prompt(include_body={args.include_body})")
    print(f"model={args.model}")
    print(f"think={not args.no_think}")
    print(f"format_json={not args.no_format_json}")
    print(f"timeout={args.timeout}")
    print(f"num_predict={args.num_predict}")
    if args.show_prompt:
        print_section("PROMPT", prompt)
    sys.stdout.flush()

    thinking, content, chunks, elapsed = stream_ollama(args, prompt)

    print(
        f"--- SUMMARY --- chunks={chunks} elapsed_seconds={elapsed:.3f} "
        f"thinking_chars={len(thinking)} content_chars={len(content)}"
    )
    print(f"content_repr={content!r}")
    print_section("THINKING", thinking)
    print_section("CONTENT", content)

    try:
        parsed = parse_model_json(content)
        validated = validate_classification(parsed)
    except Exception as error:  # noqa: BLE001 - diagnostic script should show exact failure.
        print("--- PARSE/VALIDATION ERROR ---")
        print(f"{type(error).__name__}: {error}")
    else:
        print("--- VALIDATED CLASSIFICATION ---")
        print(json.dumps(validated, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
