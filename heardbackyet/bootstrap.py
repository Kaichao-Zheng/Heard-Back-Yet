"""Application composition root for the FastAPI process."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from heardbackyet.db.config import load_postgres_config
from heardbackyet.retrieval.text_embedder import TextEmbedder, load_embedding_config
from heardbackyet.response.answer_query import AnswerQuery
from heardbackyet.response.response_generator import (
    MODEL as RESPONSE_MODEL,
    MODEL_API_CONFIG as RESPONSE_MODEL_API_CONFIG,
    OLLAMA_TIMEOUT_SECONDS as RESPONSE_TIMEOUT_SECONDS,
)
from heardbackyet.conversation import (
    ConversationService,
    InMemoryConversationStore,
    ModelFollowUpRewriter,
)
from heardbackyet.presentation.web.readiness import DependencyReadinessChecker


@dataclass
class ApiRuntime:
    """Process-level resources owned by one FastAPI lifespan."""

    query_service: ConversationService
    readiness_service: DependencyReadinessChecker
    engine: Engine

    def close(self) -> None:
        self.engine.dispose()


def build_api_runtime() -> ApiRuntime:
    """Build the API object graph while keeping database sessions request-local."""
    database_url = load_postgres_config().database_url()
    embedding_config = load_embedding_config()
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 1},
    )
    db_session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    answer_query = AnswerQuery(
        db_session_factory,
        TextEmbedder(embedding_config),
    )
    query_service = ConversationService(
        answer_query,
        InMemoryConversationStore(),
        ModelFollowUpRewriter(
            model=RESPONSE_MODEL,
            model_api_config=RESPONSE_MODEL_API_CONFIG,
            timeout_seconds=RESPONSE_TIMEOUT_SECONDS,
        ),
    )
    readiness_service = DependencyReadinessChecker(engine)
    return ApiRuntime(
        query_service=query_service,
        readiness_service=readiness_service,
        engine=engine,
    )
