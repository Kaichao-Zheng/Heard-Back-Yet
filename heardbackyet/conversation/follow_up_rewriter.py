"""Resolve contextual follow-ups into standalone retrieval questions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from heardbackyet.conversation.service import (
    MAX_QUERY_CHARS,
    ConversationTurn,
    FollowUpRewriteError,
)
from heardbackyet.model_api import (
    ChatRequest,
    ModelAPIConfig,
    ModelAPIResponseError,
    chat_content,
)


class ModelFollowUpRewriter:
    """Rewrite a contextual follow-up into one standalone retrieval question."""

    _RESPONSE_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["resolved_query"],
        "properties": {
            "resolved_query": {"type": "string", "minLength": 1},
        },
    }

    def __init__(
        self,
        *,
        model: str,
        model_api_config: ModelAPIConfig,
        timeout_seconds: int,
    ) -> None:
        self._model = model
        self._model_api_config = model_api_config
        self._timeout_seconds = timeout_seconds

    def rewrite(
        self,
        user_query: str,
        turns: Sequence[ConversationTurn],
    ) -> str:
        if not turns:
            return user_query

        history = [
            {
                "user_query": turn.user_query,
                "resolved_query": turn.resolved_query,
                "answer": str(turn.response.get("answer", ""))[:4_000],
                "sources": self._compact_sources(turn.response.get("sources")),
            }
            for turn in turns
        ]
        prompt = json.dumps(
            {"history": history, "current_query": user_query},
            ensure_ascii=False,
            default=str,
        )
        request = ChatRequest(
            model=self._model,
            stream=False,
            thinking=False,
            json_schema=self._RESPONSE_SCHEMA,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Rewrite the current job-application follow-up as one standalone "
                        "question using only the supplied history. Preserve the user's "
                        "language and intent. Do not answer the question. If history is "
                        "not needed or cannot resolve the reference, return the current "
                        "query unchanged. Return exactly one JSON object with no other "
                        'fields or text: {"resolved_query":"the standalone question"}.'
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            seed=0,
        )
        try:
            raw_response = chat_content(
                self._model_api_config,
                request,
                self._timeout_seconds,
            )
            payload = json.loads(raw_response)
        except (json.JSONDecodeError, ModelAPIResponseError, OSError) as error:
            raise FollowUpRewriteError(
                "follow-up rewriter returned an invalid response"
            ) from error

        if not isinstance(payload, dict):
            raise FollowUpRewriteError("follow-up rewriter response must be an object")
        if set(payload) == {"resolved_query"}:
            resolved_query = payload["resolved_query"]
        elif set(payload) == {"rewritten_query"}:
            # Some JSON-object-only providers choose this semantically equivalent
            # field name because they cannot enforce the supplied JSON Schema.
            resolved_query = payload["rewritten_query"]
        else:
            raise FollowUpRewriteError(
                "follow-up rewriter response has unexpected fields"
            )
        if not isinstance(resolved_query, str):
            raise FollowUpRewriteError("resolved_query must be a string")
        resolved_query = resolved_query.strip()
        if not resolved_query or len(resolved_query) > MAX_QUERY_CHARS:
            raise FollowUpRewriteError("resolved_query length is invalid")
        return resolved_query

    @staticmethod
    def _compact_sources(value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        compact: list[dict[str, str]] = []
        for source in value[:5]:
            if not isinstance(source, Mapping):
                continue
            compact.append(
                {
                    str(key): str(item)[:500]
                    for key, item in source.items()
                    if item is not None
                }
            )
        return compact
