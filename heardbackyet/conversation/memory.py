"""Bounded process-local storage for temporary conversations."""

from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from heardbackyet.conversation.service import ConversationTurn


CONVERSATION_TTL_SECONDS = 60 * 30   # 30-minute TTL
MAX_CONVERSATIONS = 99
MAX_TURNS = 3


@dataclass
class _StoredConversation:
    turns: tuple[ConversationTurn, ...]
    expires_at: float


class InMemoryConversationStore:
    """Keep a small LRU set of conversations with sliding expiration."""

    def __init__(
        self,
        *,
        max_turns: int = MAX_TURNS,
        ttl_seconds: float = CONVERSATION_TTL_SECONDS,
        max_conversations: int = MAX_CONVERSATIONS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_turns < 1 or ttl_seconds <= 0 or max_conversations < 1:
            raise ValueError("conversation store limits must be positive")
        self._max_turns = max_turns
        self._ttl_seconds = ttl_seconds
        self._max_conversations = max_conversations
        self._clock = clock
        self._entries: OrderedDict[str, _StoredConversation] = OrderedDict()
        self._lock = threading.RLock()

    def load(self, conversation_id: str) -> tuple[ConversationTurn, ...]:
        with self._lock:
            now = self._clock()
            self._prune_expired(now)
            entry = self._entries.get(conversation_id)
            if entry is None:
                return ()
            entry.expires_at = now + self._ttl_seconds
            self._entries.move_to_end(conversation_id)
            return copy.deepcopy(entry.turns)

    def append(self, conversation_id: str, turn: ConversationTurn) -> None:
        with self._lock:
            now = self._clock()
            self._prune_expired(now)
            existing = self._entries.get(conversation_id)
            turns = existing.turns if existing is not None else ()
            turns = (*turns, copy.deepcopy(turn))[-self._max_turns :]
            self._entries[conversation_id] = _StoredConversation(
                turns=turns,
                expires_at=now + self._ttl_seconds,
            )
            self._entries.move_to_end(conversation_id)
            while len(self._entries) > self._max_conversations:
                self._entries.popitem(last=False)

    def _prune_expired(self, now: float) -> None:
        expired = [
            conversation_id
            for conversation_id, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for conversation_id in expired:
            del self._entries[conversation_id]
