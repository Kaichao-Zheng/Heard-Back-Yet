from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy.orm import Session

from heardbackyet.orchestration.retrieval_planner import (
    BoundId,
    RetrievalBackend,
    RetrievalPlan,
    SemanticFilterPlan,
    SemanticRetrievalStep,
    StepOutputRef,
    StructuredOperation,
    StructuredRetrievalStep,
)
from heardbackyet.retrieval.search_contracts import (
    SearchFilters,
    SearchRequest,
)
from heardbackyet.retrieval.structured_retriever import (
    retrieve_application_overview,
    retrieve_application_provenance,
    retrieve_application_timeline,
    retrieve_company_matches,
    retrieve_inconsistent_status_snapshots,
    retrieve_unlinked_status_emails,
)
from heardbackyet.retrieval.semantic_retriever import search_semantic
from heardbackyet.retrieval.lexical_retriever import search_lexical
from heardbackyet.retrieval.hybrid_retriever import search_hybrid
from heardbackyet.retrieval.hit_hydration import hydrate_search_hits
from heardbackyet.retrieval.text_embedder import TextEmbedder


class RetrievalScopeError(LookupError):
    """A late-bound filter could not be resolved to exactly one scalar value."""


def execute_retrieval_plan(
    plan: RetrievalPlan,
    session: Session,
    embedder: TextEmbedder | None = None,
) -> dict[str, tuple[Any, ...]]:
    """Execute planned steps through structured and semantic APIs."""
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
            return retrieve_company_matches(
                conn,
                company=parameters.company,
            )
        case StructuredOperation.APPLICATION_OVERVIEW:
            return retrieve_application_overview(
                conn,
                company=parameters.company,
                limit=parameters.limit,
            )
        case StructuredOperation.APPLICATION_TIMELINE:
            return retrieve_application_timeline(
                conn,
                application_id=parameters.application_id,
                company=parameters.company,
                email_type=parameters.email_type,
                since=parameters.since,
                before=parameters.before,
                limit=parameters.limit,
            )
        case StructuredOperation.APPLICATION_PROVENANCE:
            return retrieve_application_provenance(
                conn,
                application_id=parameters.application_id,
                company=parameters.company,
                provenance_kind=parameters.provenance_kind,
                source_type=parameters.source_type,
                limit=parameters.limit,
            )
        case StructuredOperation.INCONSISTENT_STATUS_SNAPSHOT:
            return retrieve_inconsistent_status_snapshots(
                conn,
                limit=parameters.limit,
            )
        case StructuredOperation.UNLINKED_STATUS_EMAIL:
            return retrieve_unlinked_status_emails(
                conn,
                company=parameters.company,
                since=parameters.since,
                limit=parameters.limit,
            )

    raise ValueError(f"unsupported structured operation: {step.operation}")


def _execute_semantic_step(
    step: SemanticRetrievalStep,
    session: Session,
    embedder: TextEmbedder | None,
    results: Mapping[str, tuple[Any, ...]],
) -> list[Any]:
    request = SearchRequest(
        query=step.query,
        filters=_resolve_search_filters(step.filters, results),
        limit=step.limit,
    )
    if step.backend is RetrievalBackend.SEMANTIC:
        if embedder is None:
            raise ValueError("semantic backend requires an embedder")
        hits = search_semantic(session, embedder, request)
    elif step.backend is RetrievalBackend.LEXICAL:
        hits = search_lexical(session, request)
    elif step.backend is RetrievalBackend.HYBRID:
        if embedder is None:
            raise ValueError("hybrid backend requires an embedder")
        hits = search_hybrid(session, embedder, request)
    else:
        raise ValueError(
            f"unsupported semantic retrieval backend: {step.backend}"
        )
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
