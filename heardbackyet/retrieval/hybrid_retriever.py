from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Sequence

from sqlalchemy.orm import Session

from heardbackyet.retrieval.text_embedder import OllamaTextEmbedder
from heardbackyet.retrieval.search_contracts import (
    RetrievalSnapshot,
    SearchMetadata,
    SearchRequest,
)
from heardbackyet.retrieval.semantic_retriever import (
    SemanticSearchHit,
    search_semantic,
)
from heardbackyet.retrieval.lexical_retriever import (
    LexicalSearchHit,
    search_lexical,
)


DEFAULT_RRF_K = 60
MIN_RRF_CANDIDATES = 20
DEFAULT_SEMANTIC_WEIGHT = 1.0
DEFAULT_LEXICAL_WEIGHT = 1.0


@dataclass(frozen=True)
class HybridSearchRetrieval:
    """RRF score and the component ranks that produced one fused hit."""

    rank: int
    metric: str
    score: float
    rrf_k: int
    semantic_weight: float
    lexical_weight: float
    semantic_rank: int | None
    lexical_rank: int | None
    semantic_distance: float | None
    lexical_score: float | None
    embedding_model: str | None


@dataclass(frozen=True)
class HybridSearchHit:
    """Semantic and lexical rankings fused over the shared chunk identity."""

    retrieval: HybridSearchRetrieval
    metadata: SearchMetadata
    snapshot: RetrievalSnapshot


def search_hybrid(
    session: Session,
    embedder: OllamaTextEmbedder,
    request: SearchRequest,
    *,
    rrf_k: int = DEFAULT_RRF_K,
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
    lexical_weight: float = DEFAULT_LEXICAL_WEIGHT,
) -> list[HybridSearchHit]:
    """Return semantic and lexical results fused with reciprocal rank fusion."""
    _validate_rrf_parameters(rrf_k, semantic_weight, lexical_weight)

    # Keep each component pool deeper than the public result limit so RRF can
    # surface cross-list agreement before returning the final Top-N.
    candidate_request = replace(
        request,
        limit=max(request.limit, MIN_RRF_CANDIDATES),
    )
    semantic_hits = search_semantic(session, embedder, candidate_request)
    # Hybrid candidates must come from the same model-versioned corpus used by
    # semantic search; standalone lexical search can still span all rows.
    lexical_hits = search_lexical(
        session,
        candidate_request,
        embedding_model=embedder.model_ref,
    )
    return fuse_rrf(
        semantic_hits,
        lexical_hits,
        limit=request.limit,
        rrf_k=rrf_k,
        semantic_weight=semantic_weight,
        lexical_weight=lexical_weight,
    )


def fuse_rrf(
    semantic_hits: Sequence[SemanticSearchHit],
    lexical_hits: Sequence[LexicalSearchHit],
    *,
    limit: int,
    rrf_k: int = DEFAULT_RRF_K,
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
    lexical_weight: float = DEFAULT_LEXICAL_WEIGHT,
) -> list[HybridSearchHit]:
    """Fuse two ranked lists without comparing their incompatible raw scores."""
    if limit < 1:
        raise ValueError("limit must be a positive integer")
    _validate_rrf_parameters(rrf_k, semantic_weight, lexical_weight)

    semantic_by_chunk = {hit.metadata.chunk_id: hit for hit in semantic_hits}
    lexical_by_chunk = {hit.metadata.chunk_id: hit for hit in lexical_hits}
    chunk_ids = set(semantic_by_chunk) | set(lexical_by_chunk)

    def rrf_score(chunk_id: int) -> float:
        score = 0.0
        semantic_hit = semantic_by_chunk.get(chunk_id)
        lexical_hit = lexical_by_chunk.get(chunk_id)
        if semantic_hit is not None:
            score += semantic_weight / (rrf_k + semantic_hit.retrieval.rank)
        if lexical_hit is not None:
            score += lexical_weight / (rrf_k + lexical_hit.retrieval.rank)
        return score

    # Score is the only relevance signal. Best component rank and chunk ID make
    # otherwise equal one-list hits deterministic without mixing raw scores.
    ranked_chunk_ids = sorted(
        chunk_ids,
        key=lambda chunk_id: (
            -rrf_score(chunk_id),
            min(
                semantic_by_chunk[chunk_id].retrieval.rank
                if chunk_id in semantic_by_chunk
                else float("inf"),
                lexical_by_chunk[chunk_id].retrieval.rank
                if chunk_id in lexical_by_chunk
                else float("inf"),
            ),
            chunk_id,
        ),
    )

    hits: list[HybridSearchHit] = []
    for chunk_id in ranked_chunk_ids[:limit]:
        semantic_hit = semantic_by_chunk.get(chunk_id)
        lexical_hit = lexical_by_chunk.get(chunk_id)
        representative = semantic_hit or lexical_hit
        if representative is None:
            raise AssertionError("RRF candidate must exist in at least one ranked list")

        if (
            semantic_hit is not None
            and lexical_hit is not None
            and (
                semantic_hit.metadata != lexical_hit.metadata
                or semantic_hit.snapshot != lexical_hit.snapshot
            )
        ):
            raise ValueError(f"inconsistent chunk payload for chunk_id={chunk_id}")

        hits.append(
            HybridSearchHit(
                retrieval=HybridSearchRetrieval(
                    rank=len(hits) + 1,
                    metric="rrf",
                    score=rrf_score(chunk_id),
                    rrf_k=rrf_k,
                    semantic_weight=semantic_weight,
                    lexical_weight=lexical_weight,
                    semantic_rank=(
                        semantic_hit.retrieval.rank
                        if semantic_hit is not None
                        else None
                    ),
                    lexical_rank=(
                        lexical_hit.retrieval.rank
                        if lexical_hit is not None
                        else None
                    ),
                    semantic_distance=(
                        semantic_hit.retrieval.distance
                        if semantic_hit is not None
                        else None
                    ),
                    lexical_score=(
                        lexical_hit.retrieval.score
                        if lexical_hit is not None
                        else None
                    ),
                    embedding_model=(
                        semantic_hit.retrieval.embedding_model
                        if semantic_hit is not None
                        else None
                    ),
                ),
                metadata=representative.metadata,
                snapshot=representative.snapshot,
            )
        )
    return hits


def _validate_rrf_parameters(
    rrf_k: int,
    semantic_weight: float,
    lexical_weight: float,
) -> None:
    if rrf_k < 1:
        raise ValueError("rrf_k must be a positive integer")

    weights = {
        "semantic_weight": semantic_weight,
        "lexical_weight": lexical_weight,
    }
    for name, value in weights.items():
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite non-negative number")
    if semantic_weight == 0 and lexical_weight == 0:
        raise ValueError("semantic_weight and lexical_weight cannot both be zero")
