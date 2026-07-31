from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from heardbackyet.paths import ENV_PATH


class ModelAPIResponseError(ValueError):
    """Raised when a model API response violates the expected envelope."""


@dataclass(frozen=True)
class ModelAPIConfig:
    provider: str
    base_url: str
    api_key: str | None

    def model_ref(self, model: str) -> str:
        return f"{self.provider}:{model}"


@dataclass(frozen=True)
class ChatRequest:
    """Provider-neutral configuration for one non-streaming chat request."""

    model: str
    messages: list[dict[str, str]]
    stream: bool = False
    json_output: bool = False
    json_schema: dict[str, Any] | None = None
    temperature: float = 0
    seed: int = 0
    thinking: bool | None = None


def load_model_api_config() -> ModelAPIConfig:
    """Load one backend used by every model task in the current process."""
    load_dotenv(ENV_PATH)
    provider = _required_env("MODEL_PROVIDER")
    if provider == "ollama":
        return ModelAPIConfig(
            provider=provider,
            base_url=_required_env("OLLAMA_URL").rstrip("/"),
            api_key=None,
        )
    if provider == "alibaba_model_studio":
        return ModelAPIConfig(
            provider=provider,
            base_url=_required_env("MODEL_BASE_URL").rstrip("/"),
            api_key=_required_env("MODEL_API_KEY"),
        )
    raise RuntimeError(
        f"Unsupported MODEL_PROVIDER {provider!r}; "
        "expected 'ollama' or 'alibaba_model_studio'."
    )


def chat_content(
    config: ModelAPIConfig,
    request: ChatRequest,
    timeout_seconds: int,
) -> str:
    """POST one non-streaming chat request and return its text content."""
    if config.provider == "ollama":
        endpoint = config.base_url + "/api/chat"
        request_payload = _ollama_chat_payload(request)
    else:
        endpoint = config.base_url + "/chat/completions"
        request_payload = _alibaba_model_studio_chat_payload(request)

    response_payload = _post_json(
        endpoint,
        request_payload,
        timeout_seconds,
        api_key=config.api_key,
    )
    if config.provider == "ollama":
        content = response_payload.get("message", {}).get("content")
    else:
        choices = response_payload.get("choices")
        content = (
            choices[0].get("message", {}).get("content")
            if isinstance(choices, list)
            and choices
            and isinstance(choices[0], dict)
            else None
        )
    if not isinstance(content, str):
        raise ModelAPIResponseError(
            f"{config.provider} chat response did not include text content"
        )
    return content


def iter_chat_chunks(
    ollama_url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """POST one Ollama streaming chat payload and yield decoded chunks."""
    request = Request(
        ollama_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        for line in response:
            if not line.strip():
                continue
            raw = line.decode("utf-8", errors="replace")
            chunk = json.loads(raw)
            if not isinstance(chunk, dict):
                raise ModelAPIResponseError(
                    "Ollama stream chunk must be a JSON object"
                )
            yield raw, chunk


def embedding_values(
    config: ModelAPIConfig,
    *,
    model: str,
    texts: list[str],
    dimensions: int,
    timeout_seconds: int,
) -> list[Any]:
    """POST one embedding batch and return the unvalidated vector values."""
    if config.provider == "ollama":
        endpoint = config.base_url + "/api/embed"
        request_payload = {
            "model": model,
            "input": texts,
            "truncate": False,
            "dimensions": dimensions,
        }
    else:
        endpoint = config.base_url + "/embeddings"
        request_payload = {
            "model": model,
            "input": texts,
            "dimensions": dimensions,
            "encoding_format": "float",
        }

    response_payload = _post_json(
        endpoint,
        request_payload,
        timeout_seconds,
        api_key=config.api_key,
    )
    if config.provider == "ollama":
        values = response_payload.get("embeddings")
    else:
        data = response_payload.get("data")
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            # OpenAI-compatible APIs identify each input position explicitly.
            ordered = sorted(data, key=lambda item: item.get("index", 0))
            values = [item.get("embedding") for item in ordered]
        else:
            values = None
    if not isinstance(values, list) or len(values) != len(texts):
        raise ModelAPIResponseError(
            f"{config.provider} returned an unexpected embedding count"
        )
    return values


def _ollama_chat_payload(request: ChatRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": request.model,
        "stream": request.stream,
    }
    if request.thinking is not None:
        payload["think"] = request.thinking
    if request.json_schema is not None:
        payload["format"] = request.json_schema
    elif request.json_output:
        payload["format"] = "json"
    payload["messages"] = request.messages
    payload["options"] = {
        "temperature": request.temperature,
        "seed": request.seed,
    }
    return payload


def _alibaba_model_studio_chat_payload(request: ChatRequest) -> dict[str, Any]:
    """Translate the internal request into Alibaba Model Studio chat fields."""
    payload: dict[str, Any] = {
        "model": request.model,
        "stream": request.stream,
    }
    if request.thinking is not None:
        # Alibaba Model Studio uses this non-standard extension for Qwen.
        payload["enable_thinking"] = request.thinking
    if request.json_output or request.json_schema is not None:
        payload["response_format"] = {"type": "json_object"}
    payload["messages"] = request.messages
    payload["temperature"] = request.temperature
    payload["seed"] = request.seed
    return payload


def _post_json(
    endpoint: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    *,
    api_key: str | None,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(response_payload, dict):
        raise ModelAPIResponseError("Model API response must be a JSON object")
    return response_payload


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required. Configure it in the project .env file.")
    return value
