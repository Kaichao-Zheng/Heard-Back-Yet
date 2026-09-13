from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from heardbackyet.constants import EMBEDDING_DIMENSION
from heardbackyet.model_api import (
    ModelAPIConfig,
    ModelAPIResponseError,
    embedding_values,
    load_model_api_config,
)
from heardbackyet.paths import ENV_PATH

EMBEDDING_BATCH_SIZE = 10           # a safer batch size for alibaba model studio
EMBEDDING_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class EmbeddingConfig:
    api: ModelAPIConfig
    model: str


def load_embedding_config() -> EmbeddingConfig:
    load_dotenv(ENV_PATH)
    model = os.getenv("EMBEDDING_MODEL")
    if not model:
        raise RuntimeError(
            "EMBEDDING_MODEL is required. Configure it in the project .env file."
        )
    return EmbeddingConfig(
        api=load_model_api_config(),
        model=model,
    )


class TextEmbedder:
    def __init__(self, config: EmbeddingConfig) -> None:
        self.config = config

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def model_ref(self) -> str:
        return self.config.api.model_ref(self.model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[start : start + EMBEDDING_BATCH_SIZE]
            embeddings.extend(self._embed_batch(batch))
        return embeddings

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            raw_embeddings = embedding_values(
                self.config.api,
                model=self.config.model,
                texts=texts,
                dimensions=EMBEDDING_DIMENSION,
                timeout_seconds=EMBEDDING_TIMEOUT_SECONDS,
            )
        except ModelAPIResponseError as exc:
            raise ValueError(str(exc)) from exc
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
