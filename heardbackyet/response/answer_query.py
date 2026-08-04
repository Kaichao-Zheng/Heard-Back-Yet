"""Framework-neutral entry point for the user-query-to-response workflow."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from heardbackyet.orchestration.query_orchestrator import QueryOrchestrator
from heardbackyet.retrieval.text_embedder import TextEmbedder
from heardbackyet.response.response_generator import generate_response


class AnswerQuery:
    """Coordinate query orchestration and response generation."""

    def __init__(
        self,
        db_session_factory: sessionmaker[Session],
        embedder: TextEmbedder,
    ) -> None:
        self._db_session_factory = db_session_factory
        self._embedder = embedder

    def run(self, user_query: str) -> dict[str, Any]:
        """Run one stateless user query in a request-local database session."""
        with self._db_session_factory() as db_session:
            result = QueryOrchestrator(
                db_session,
                embedder=self._embedder,
            ).orchestrate(user_query)
        return generate_response(result)
