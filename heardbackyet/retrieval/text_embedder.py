from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from heardbackyet.constants import EMBEDDING_DIMENSION
from heardbackyet.paths import ENV_PATH

EMBEDDING_BATCH_SIZE = 32
EMBEDDING_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class EmbeddingConfig:
    endpoint: str
    model: str


def load_embedding_config() -> EmbeddingConfig:
    load_dotenv(ENV_PATH)
    model = os.getenv("EMBEDDING_MODEL")
    if not model:
        raise RuntimeError(
            "EMBEDDING_MODEL is required. Configure it in the project .env file."
        )
    return EmbeddingConfig(
        endpoint=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        model=model,
    )


class OllamaTextEmbedder:
    def __init__(self, config: EmbeddingConfig) -> None:
        self.config = config

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def model_ref(self) -> str:
        return f"ollama:{self.model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[start : start + EMBEDDING_BATCH_SIZE]
            embeddings.extend(self._embed_batch(batch))
        return embeddings

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        request = Request(
            self.config.endpoint + "/api/embed",
            data=json.dumps(
                {
                    "model": self.config.model,
                    "input": texts,
                    "truncate": False,
                    "dimensions": EMBEDDING_DIMENSION,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=EMBEDDING_TIMEOUT_SECONDS) as response:
                result = json.load(response)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama embedding request failed with HTTP {exc.code}: {detail}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"Cannot reach Ollama embedding endpoint at {request.full_url}: {exc}"
            ) from exc

        raw_embeddings = result.get("embeddings") if isinstance(result, dict) else None
        if not isinstance(raw_embeddings, list) or len(raw_embeddings) != len(texts):
            raise ValueError("Ollama returned an unexpected embedding count.")
        return [self._validate_embedding(value) for value in raw_embeddings]

    @staticmethod
    def _validate_embedding(value: Any) -> list[float]:
        if not isinstance(value, list) or len(value) != EMBEDDING_DIMENSION:
            actual = len(value) if isinstance(value, list) else "non-list"
            raise ValueError(
                f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSION}, got {actual}."
            )
        embedding = [float(component) for component in value]
        if not all(math.isfinite(component) for component in embedding):
            raise ValueError("Embedding contains a non-finite component.")
        return embedding
