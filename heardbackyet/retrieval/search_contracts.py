from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SearchFilters:
    """Exact metadata constraints applied before retrieval ranking."""

    application_id: int | None = None
    company_id: int | None = None
    position_id: int | None = None
    source_types: tuple[str, ...] | None = None
    email_types: tuple[str, ...] | None = None
    linked_only: bool | None = None


@dataclass(frozen=True)
class RetrievalSnapshot:
    """Context-enriched content snapshot used for retrieval ranking."""

    semantic_fields: tuple[str, ...]
    content: str


@dataclass(frozen=True)
class SearchMetadata:
    """Chunk identity and business links used for exact filtering."""

    chunk_id: int
    source_type: str
    source_id: int
    application_id: int | None
    company_id: int | None
    position_id: int | None
    email_type: str | None


@dataclass(frozen=True)
class SearchRequest:
    """Public search input: natural-language query plus exact filters."""

    query: str
    filters: SearchFilters = field(default_factory=SearchFilters)
    limit: int = 10
