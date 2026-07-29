from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from urllib.request import Request, urlopen


class OllamaChatResponseError(ValueError):
    """Raised when an Ollama chat response violates the expected envelope."""


def chat_content(
    ollama_url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> str:
    """POST one non-streaming chat payload and return message.content."""
    response_payload = _post_chat(ollama_url, payload, timeout_seconds)
    content = response_payload.get("message", {}).get("content")
    if not isinstance(content, str):
        raise OllamaChatResponseError(
            "Ollama response did not include message.content"
        )
    return content


def iter_chat_chunks(
    ollama_url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """POST one streaming chat payload and yield each raw and decoded chunk."""
    request = _build_request(ollama_url, payload)
    with urlopen(request, timeout=timeout_seconds) as response:
        for line in response:
            if not line.strip():
                continue
            raw = line.decode("utf-8", errors="replace")
            chunk = json.loads(raw)
            if not isinstance(chunk, dict):
                raise OllamaChatResponseError(
                    "Ollama stream chunk must be a JSON object"
                )
            yield raw, chunk


def _post_chat(
    ollama_url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    request = _build_request(ollama_url, payload)
    with urlopen(request, timeout=timeout_seconds) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(response_payload, dict):
        raise OllamaChatResponseError("Ollama response must be a JSON object")
    return response_payload


def _build_request(ollama_url: str, payload: dict[str, Any]) -> Request:
    return Request(
        ollama_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
