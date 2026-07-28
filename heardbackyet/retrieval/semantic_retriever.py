from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from heardbackyet.constants import RETRIEVAL_SOURCE_TYPES, SEMANTIC_INDEX_EMAIL_LABELS
from heardbackyet.db.postgres_models import RetrievalChunk
from heardbackyet.retrieval.search_contracts import (
    RetrievalSnapshot,
    SearchFilters,
    SearchMetadata,
    SearchRequest,
)
from heardbackyet.retrieval.text_embedder import OllamaTextEmbedder


@dataclass(frozen=True)
class SemanticSearchRetrieval:
    """Similarity calculation details for one ranked hit."""

    rank: int
    metric: str
    distance: float
    embedding_model: str


@dataclass(frozen=True)
class SemanticSearchHit:
    """Ranked search contract; raw embedding vectors remain internal."""

    retrieval: SemanticSearchRetrieval
    metadata: SearchMetadata
    snapshot: RetrievalSnapshot


def search_semantic(
    session: Session,
    embedder: OllamaTextEmbedder,
    request: SearchRequest,
) -> list[SemanticSearchHit]:
    """Embed one query and return exact cosine-search results."""
    query = request.query.strip()
    _validate_request(request, query)

    embeddings = embedder.embed([query])
    if len(embeddings) != 1:
        raise ValueError("Expected exactly one query embedding.")
    query_embedding = embeddings[0]

    # Build one SQL query: metadata predicates become WHERE clauses before
    # cosine-distance ordering and LIMIT select the final top-K results.
    distance = RetrievalChunk.embedding.cosine_distance(query_embedding).label(
        "distance"
    )
    statement = select(RetrievalChunk, distance)
    statement = _apply_filters(statement, request.filters, embedder.model_ref)
    statement = statement.order_by(distance.asc(), RetrievalChunk.chunk_id.asc())
    statement = statement.limit(request.limit)

    rows = session.execute(statement).all()
    hits: list[SemanticSearchHit] = []
    for rank, (chunk, distance_value) in enumerate(rows, start=1):
        hits.append(
            SemanticSearchHit(
                retrieval=SemanticSearchRetrieval(
                    rank=rank,
                    metric="cosine_distance",
                    distance=float(distance_value),
                    embedding_model=embedder.model_ref,
                ),
                metadata=SearchMetadata(
                    chunk_id=chunk.chunk_id,
                    source_type=chunk.source_type,
                    source_id=chunk.source_id,
                    application_id=chunk.application_id,
                    company_id=chunk.company_id,
                    position_id=chunk.position_id,
                    email_type=chunk.email_type,
                ),
                snapshot=RetrievalSnapshot(
                    content=chunk.content,
                    semantic_fields=tuple(chunk.semantic_fields),
                ),
            )
        )
    return hits


def _apply_filters(
    statement: Select[tuple[RetrievalChunk, float]],
    filters: SearchFilters,
    embedding_model: str,
) -> Select[tuple[RetrievalChunk, float]]:
    """Append metadata WHERE predicates before vector ranking."""
    # Only compare vectors produced by the same provider/model contract.
    statement = statement.where(RetrievalChunk.embedding_model == embedding_model)

    if filters.application_id is not None:
        statement = statement.where(
            RetrievalChunk.application_id == filters.application_id
        )
    if filters.company_id is not None:
        statement = statement.where(RetrievalChunk.company_id == filters.company_id)
    if filters.position_id is not None:
        statement = statement.where(RetrievalChunk.position_id == filters.position_id)
    if filters.source_types is not None:
        statement = statement.where(
            RetrievalChunk.source_type.in_(filters.source_types)
        )
    if filters.email_types is not None:
        statement = statement.where(RetrievalChunk.email_type.in_(filters.email_types))
    if filters.linked_only is True:
        statement = statement.where(RetrievalChunk.application_id.is_not(None))
    elif filters.linked_only is False:
        statement = statement.where(RetrievalChunk.application_id.is_(None))

    return statement


def _validate_request(request: SearchRequest, normalized_query: str) -> None:
    if not normalized_query:
        raise ValueError("query must not be empty")
    if request.limit < 1:
        raise ValueError("limit must be a positive integer")

    filters = request.filters
    for field_name in ("application_id", "company_id", "position_id"):
        value = getattr(filters, field_name)
        if value is not None and value < 1:
            raise ValueError(f"{field_name} must be a positive integer")

    _validate_choices("source_types", filters.source_types, RETRIEVAL_SOURCE_TYPES)
    _validate_choices("email_types", filters.email_types, SEMANTIC_INDEX_EMAIL_LABELS)

    if filters.application_id is not None and filters.linked_only is False:
        raise ValueError("application_id cannot be combined with linked_only=False")
    if (
        filters.email_types is not None
        and filters.source_types is not None
        and "email" not in filters.source_types
    ):
        raise ValueError("email_types requires source_types to include email")


def _validate_choices(
    field_name: str,
    values: tuple[str, ...] | None,
    allowed_values: tuple[str, ...],
) -> None:
    if values is None:
        return
    if not values:
        raise ValueError(f"{field_name} must not be empty when provided")

    invalid_values = sorted(set(values) - set(allowed_values))
    if invalid_values:
        invalid = ", ".join(invalid_values)
        allowed = ", ".join(allowed_values)
        raise ValueError(f"invalid {field_name}: {invalid}; allowed values: {allowed}")
