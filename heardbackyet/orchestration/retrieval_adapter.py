from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy.orm import Session

from heardbackyet.orchestration.retrieval_planner import (
    BoundId,
    RetrievalPlan,
    SemanticFilterPlan,
    SemanticRetrievalStep,
    StepOutputRef,
    StructuredOperation,
    StructuredRetrievalStep,
)
from heardbackyet.query.table_queries import query_company_matches
from heardbackyet.query.view_queries import (
    query_application_evidence,
    query_application_overview,
    query_application_timeline,
    query_inconsistent_status_snapshots,
    query_unlinked_status_emails,
)
from heardbackyet.retrieval.semantic_search import (
    SearchFilters,
    SearchRequest,
    search_retrieval,
)
from heardbackyet.retrieval.source_hydration import hydrate_search_hits
from heardbackyet.retrieval.text_embedder import OllamaTextEmbedder


class RetrievalScopeError(LookupError):
    """A hybrid filter could not be resolved to exactly one scalar value."""


def execute_retrieval_plan(
    plan: RetrievalPlan,
    session: Session,
    embedder: OllamaTextEmbedder | None = None,
) -> dict[str, tuple[Any, ...]]:
    """Adapt planned steps to the existing structured and semantic APIs."""
    results: dict[str, tuple[Any, ...]] = {}

    for step in plan.steps:
        if isinstance(step, StructuredRetrievalStep):
            records = _execute_structured_step(step, session)
        elif isinstance(step, SemanticRetrievalStep):
            records = _execute_semantic_step(step, session, embedder, results)
        else:
            raise TypeError(f"unsupported retrieval step: {type(step).__name__}")
        results[step.step_id] = tuple(records)

    return results


def _execute_structured_step(
    step: StructuredRetrievalStep,
    session: Session,
) -> list[dict[str, Any]]:
    conn = session.connection()
    parameters = step.parameters

    match step.operation:
        case StructuredOperation.RESOLVE_COMPANY:
            if not parameters.company:
                raise ValueError("resolve_company requires company")
            return query_company_matches(
                conn,
                company=parameters.company,
            )
        case StructuredOperation.APPLICATION_OVERVIEW:
            return query_application_overview(
                conn,
                company=parameters.company,
                limit=parameters.limit,
            )
        case StructuredOperation.APPLICATION_TIMELINE:
            return query_application_timeline(
                conn,
                application_id=parameters.application_id,
                company=parameters.company,
                email_type=parameters.email_type,
                since=parameters.since,
                before=parameters.before,
                limit=parameters.limit,
            )
        case StructuredOperation.APPLICATION_EVIDENCE:
            return query_application_evidence(
                conn,
                application_id=parameters.application_id,
                company=parameters.company,
                evidence_kind=parameters.evidence_kind,
                source_type=parameters.source_type,
                limit=parameters.limit,
            )
        case StructuredOperation.INCONSISTENT_STATUS_SNAPSHOT:
            return query_inconsistent_status_snapshots(
                conn,
                limit=parameters.limit,
            )
        case StructuredOperation.UNLINKED_STATUS_EMAIL:
            return query_unlinked_status_emails(
                conn,
                company=parameters.company,
                since=parameters.since,
                limit=parameters.limit,
            )

    raise ValueError(f"unsupported structured operation: {step.operation}")


def _execute_semantic_step(
    step: SemanticRetrievalStep,
    session: Session,
    embedder: OllamaTextEmbedder | None,
    results: Mapping[str, tuple[Any, ...]],
) -> list[Any]:
    if embedder is None:
        raise ValueError("semantic retrieval requires an embedder")

    request = SearchRequest(
        query=step.query,
        filters=_resolve_search_filters(step.filters, results),
        limit=step.limit,
    )
    hits = search_retrieval(session, embedder, request)
    if step.hydrate:
        return hydrate_search_hits(session, hits)
    return hits


def _resolve_search_filters(
    plan: SemanticFilterPlan,
    results: Mapping[str, tuple[Any, ...]],
) -> SearchFilters:
    return SearchFilters(
        application_id=_resolve_bound_id(plan.application_id, results),
        company_id=_resolve_bound_id(plan.company_id, results),
        position_id=_resolve_bound_id(plan.position_id, results),
        source_types=plan.source_types,
        email_types=plan.email_types,
        linked_only=plan.linked_only,
    )


def _resolve_bound_id(
    value: BoundId,
    results: Mapping[str, tuple[Any, ...]],
) -> int | None:
    if not isinstance(value, StepOutputRef):
        return value

    source_records = results.get(value.step_id)
    if source_records is None:
        raise RetrievalScopeError(
            f"step result not available for filter binding: {value.step_id}"
        )

    resolved_values: set[int] = set()
    for record in source_records:
        if isinstance(record, Mapping):
            candidate = record.get(value.field)
        else:
            candidate = getattr(record, value.field, None)
        if candidate is not None:
            resolved_values.add(candidate)

    if not resolved_values:
        raise RetrievalScopeError(
            f"step {value.step_id} produced no {value.field} value"
        )
    if len(resolved_values) > 1:
        values = ", ".join(str(item) for item in sorted(resolved_values))
        raise RetrievalScopeError(
            f"step {value.step_id} produced ambiguous {value.field} values: {values}"
        )
    return next(iter(resolved_values))
