"""Framework-neutral entry point for the user-query-to-response workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from heardbackyet.db.config import load_postgres_config
from heardbackyet.orchestration.query_orchestrator import QueryOrchestrator
from heardbackyet.retrieval.text_embedder import TextEmbedder, load_embedding_config
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


@dataclass
class AnswerQueryRuntime:
    """Long-lived dependencies owned by one API lifespan."""

    runner: AnswerQuery
    engine: Engine

    def close(self) -> None:
        self.engine.dispose()


def build_answer_query_runtime() -> AnswerQueryRuntime:
    """Build shared dependencies while keeping database sessions request-local."""
    database_url = load_postgres_config().database_url()
    embedding_config = load_embedding_config()
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )
    db_session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    runner = AnswerQuery(
        db_session_factory,
        TextEmbedder(embedding_config),
    )
    return AnswerQueryRuntime(runner=runner, engine=engine)
