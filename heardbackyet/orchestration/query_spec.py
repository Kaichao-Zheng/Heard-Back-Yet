from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class QueryIntent(StrEnum):
    """Public information need produced by the natural-language analyzer."""

    APPLICATION_OVERVIEW = "application_overview"
    APPLICATION_TIMELINE = "application_timeline"
    APPLICATION_EVIDENCE = "application_evidence"
    CONTENT_SEARCH = "content_search"
    INCONSISTENT_STATUS_SNAPSHOT = "inconsistent_status_snapshot"
    UNLINKED_STATUS_EMAIL = "unlinked_status_email"


@dataclass(frozen=True)
class QuerySpec:
    """Normalized query contract shared across analysis, scope, and planning."""

    intent: QueryIntent
    query: str = ""
    application_id: int | None = None
    company_id: int | None = None
    position_id: int | None = None
    company: str | None = None
    email_types: tuple[str, ...] | None = None
    source_types: tuple[str, ...] | None = None
    linked_only: bool | None = None
    since: datetime | None = None
    before: datetime | None = None
    evidence_kind: str | None = None
    limit: int | None = None
    hydrate: bool = True

    def __post_init__(self) -> None:
        for field_name in ("application_id", "company_id", "position_id"):
            value = getattr(self, field_name)
            if value is not None and value < 1:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.limit is not None and self.limit < 1:
            raise ValueError("limit must be a positive integer")
        if self.intent is QueryIntent.CONTENT_SEARCH and not self.query.strip():
            raise ValueError("content_search requires a non-empty query")
