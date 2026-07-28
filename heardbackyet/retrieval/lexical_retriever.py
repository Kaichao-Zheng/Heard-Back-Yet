from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from heardbackyet.db.postgres_models import RetrievalChunk
from heardbackyet.retrieval.search_contracts import (
    RetrievalSnapshot,
    SearchMetadata,
    SearchRequest,
)


# Keep technical terminologies such as qwen3.5, node.js, c++, and c# intact.
# Chinese spans remain exact lexical tokens; language-aware segmentation is
# deferred until the small corpus demonstrates that it is necessary.
TOKEN_PATTERN = re.compile(
    r"[a-z0-9](?:[a-z0-9._+#/-]*[a-z0-9+#])?|[\u3400-\u4dbf\u4e00-\u9fff]+"
)


@dataclass(frozen=True)
class LexicalSearchRetrieval:
    """BM25 ranking details for one lexical hit."""

    rank: int
    metric: str
    score: float


@dataclass(frozen=True)
class LexicalSearchHit:
    """Ranked lexical hit over the existing retrieval corpus."""

    retrieval: LexicalSearchRetrieval
    metadata: SearchMetadata
    snapshot: RetrievalSnapshot


def search_lexical(
    session: Session,
    request: SearchRequest,
    *,
    embedding_model: str | None = None,
) -> list[LexicalSearchHit]:
    """Return BM25-ranked chunks after applying exact metadata filters."""
    query = request.query.strip()
    if not query:
        raise ValueError("query must not be empty")
    if request.limit < 1:
        raise ValueError("limit must be a positive integer")

    query_tokens = tuple(dict.fromkeys(tokenize_lexical_text(query)))
    if not query_tokens:
        raise ValueError("query must contain at least one lexical token")

    # Filter before ranking so an unfiltered Top-N cannot discard eligible
    # chunks that should compete inside the requested application/source scope.
    statement = select(RetrievalChunk)
    if embedding_model is not None:
        statement = statement.where(
            RetrievalChunk.embedding_model == embedding_model
        )
    filters = request.filters
    if filters.application_id is not None:
        statement = statement.where(
            RetrievalChunk.application_id == filters.application_id
        )
    if filters.company_id is not None:
        statement = statement.where(RetrievalChunk.company_id == filters.company_id)
    if filters.position_id is not None:
        statement = statement.where(
            RetrievalChunk.position_id == filters.position_id
        )
    if filters.source_types is not None:
        statement = statement.where(
            RetrievalChunk.source_type.in_(filters.source_types)
        )
    if filters.email_types is not None:
        statement = statement.where(
            RetrievalChunk.email_type.in_(filters.email_types)
        )
    if filters.linked_only is True:
        statement = statement.where(RetrievalChunk.application_id.is_not(None))
    elif filters.linked_only is False:
        statement = statement.where(RetrievalChunk.application_id.is_(None))
    statement = statement.order_by(RetrievalChunk.chunk_id.asc())
    chunks = list(session.scalars(statement))
    if not chunks:
        return []

    documents = [tokenize_lexical_text(chunk.content) for chunk in chunks]
    if not any(documents):
        return []
    scores = BM25Okapi(documents).get_scores(query_tokens)
    ranked = sorted(
        zip(chunks, documents, scores),
        key=lambda item: (-float(item[2]), item[0].chunk_id),
    )

    query_terms = set(query_tokens)
    hits: list[LexicalSearchHit] = []
    for chunk, document_tokens, score in ranked:
        # BM25Okapi can assign non-positive scores to very common terms. Test
        # token overlap directly so matches remain eligible while unrelated
        # zero-score rows are not returned merely to fill the result limit.
        if query_terms.isdisjoint(document_tokens):
            continue
        hits.append(
            LexicalSearchHit(
                retrieval=LexicalSearchRetrieval(
                    rank=len(hits) + 1,
                    metric="bm25",
                    score=float(score),
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
        if len(hits) >= request.limit:
            break
    return hits


def tokenize_lexical_text(value: str) -> tuple[str, ...]:
    """Normalize text and return conservative exact-match lexical tokens."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return tuple(TOKEN_PATTERN.findall(normalized))
