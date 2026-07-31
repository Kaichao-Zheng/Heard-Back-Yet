from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from heardbackyet.model_api import ChatRequest, chat_content, load_model_api_config
from heardbackyet.paths import ENV_PATH
from heardbackyet.retrieval.text_embedder import (
    EmbeddingConfig,
    TextEmbedder,
)


CHAT_MODEL_ENV_NAMES = (
    "TEXT_CLASSIFICATION_MODEL",
    "ENTITY_EXTRACTION_MODEL",
    "INTENT_CLASSIFICATION_MODEL",
    "RESPONSE_GENERATION_MODEL",
)
EMBEDDING_MODEL_ENV_NAME = "EMBEDDING_MODEL"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test configured Chat and Embedding model APIs."
    )
    return parser.parse_args()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required. Configure it in the project .env file.")
    return value


def main() -> int:
    parse_args()
    load_dotenv(ENV_PATH)
    try:
        config = load_model_api_config()
        roles_by_model: dict[str, list[str]] = {}
        for name in CHAT_MODEL_ENV_NAMES:
            roles_by_model.setdefault(required_env(name), []).append(name)

        chat_results = []
        for model, roles in roles_by_model.items():
            content = chat_content(
                config,
                ChatRequest(
                    model=model,
                    stream=False,
                    messages=[
                        {
                            "role": "user",
                            "content": "Reply with exactly: OK",
                        }
                    ],
                    temperature=0,
                    seed=0,
                    thinking=False,
                ),
                60,
            ).strip()
            chat_results.append(
                {
                    "model": model,
                    "roles": roles,
                    "response": content,
                }
            )

        embedding_model = required_env(EMBEDDING_MODEL_ENV_NAME)
        embedder = TextEmbedder(
            EmbeddingConfig(api=config, model=embedding_model)
        )
        embeddings = embedder.embed(["model API smoke test"])

        print(
            json.dumps(
                {
                    "provider": config.provider,
                    "chat": chat_results,
                    "embedding": {
                        "model": embedding_model,
                        "count": len(embeddings),
                        "dimension": len(embeddings[0]),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(f"model API smoke failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
