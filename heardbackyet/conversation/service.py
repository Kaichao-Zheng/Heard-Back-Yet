"""Conversation-level coordination around a stateless query service."""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


MAX_QUERY_CHARS = 1_000
MAX_CONVERSATION_ID_CHARS = 128
CONVERSATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
LOGGER = logging.getLogger(__name__)


class FollowUpRewriteError(ValueError):
    """Raised when a model cannot produce a valid standalone follow-up."""


@dataclass(frozen=True)
class ConversationTurn:
    """One complete user/assistant exchange kept for later follow-ups."""

    user_query: str
    resolved_query: str
    response: dict[str, Any]


class StatelessQueryService(Protocol):
    def run(self, user_query: str, /) -> dict[str, Any]: ...


class ConversationStore(Protocol):
    def load(self, conversation_id: str) -> tuple[ConversationTurn, ...]: ...

    def append(self, conversation_id: str, turn: ConversationTurn) -> None: ...


class FollowUpRewriter(Protocol):
    def rewrite(
        self,
        user_query: str,
        turns: Sequence[ConversationTurn],
    ) -> str: ...


class ConversationService:
    """Coordinate optional session memory around a stateless query service."""

    def __init__(
        self,
        query_service: StatelessQueryService,
        store: ConversationStore,
        follow_up_rewriter: FollowUpRewriter,
        *,
        lock_stripes: int = 64,
    ) -> None:
        if lock_stripes < 1:
            raise ValueError("lock_stripes must be positive")
        self._query_service = query_service
        self._store = store
        self._follow_up_rewriter = follow_up_rewriter
        # Fixed stripes bound lock memory while serializing each session's transaction.
        self._locks = tuple(threading.Lock() for _ in range(lock_stripes))

    def run(
        self,
        user_query: str,
        /,
        *,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        if conversation_id is None:
            return self._query_service.run(user_query)
        if (
            not conversation_id
            or len(conversation_id) > MAX_CONVERSATION_ID_CHARS
            or CONVERSATION_ID_PATTERN.fullmatch(conversation_id) is None
        ):
            raise ValueError("conversation_id is invalid")
        if not user_query or len(user_query) > MAX_QUERY_CHARS:
            raise ValueError("user_query length is invalid")

        lock = self._locks[hash(conversation_id) % len(self._locks)]
        with lock:
            turns = self._store.load(conversation_id)
            try:
                resolved_query = self._follow_up_rewriter.rewrite(user_query, turns)
            except FollowUpRewriteError:
                # Context rewriting is best-effort; the core query path must remain
                # available when the model endpoint or its output is unreliable.
                LOGGER.warning(
                    "follow-up rewrite failed; using the original query",
                    exc_info=True,
                )
                resolved_query = user_query
            response = self._query_service.run(resolved_query)
            self._store.append(
                conversation_id,
                ConversationTurn(
                    user_query=user_query,
                    resolved_query=resolved_query,
                    response=response,
                ),
            )
            return response
