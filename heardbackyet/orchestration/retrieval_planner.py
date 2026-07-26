from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from heardbackyet.orchestration.query_spec import QueryIntent, QuerySpec


class RetrievalMode(StrEnum):
    STRUCTURED = "structured"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class StructuredOperation(StrEnum):
    RESOLVE_COMPANY = "resolve_company"
    APPLICATION_OVERVIEW = "application_overview"
    APPLICATION_TIMELINE = "application_timeline"
    APPLICATION_PROVENANCE = "application_provenance"
    INCONSISTENT_STATUS_SNAPSHOT = "inconsistent_status_snapshot"
    UNLINKED_STATUS_EMAIL = "unlinked_status_email"


@dataclass(frozen=True)
class RouteDecision:
    """Internal routing-policy result retained for plan explainability."""

    mode: RetrievalMode
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("route reason must not be empty")


@dataclass(frozen=True)
class StructuredQueryParameters:
    application_id: int | None = None
    company: str | None = None
    email_type: str | None = None
    since: datetime | None = None
    before: datetime | None = None
    provenance_kind: str | None = None
    source_type: str | None = None
    limit: int | None = None


@dataclass(frozen=True)
class StepOutputRef:
    """Late-bound scalar read from an earlier retrieval step's records."""

    step_id: str
    field: str


BoundId = int | StepOutputRef | None


@dataclass(frozen=True)
class SemanticFilterPlan:
    """Search filters that may contain values resolved during execution."""

    application_id: BoundId = None
    company_id: BoundId = None
    position_id: BoundId = None
    source_types: tuple[str, ...] | None = None
    email_types: tuple[str, ...] | None = None
    linked_only: bool | None = None


@dataclass(frozen=True)
class StructuredRetrievalStep:
    step_id: str
    operation: StructuredOperation
    parameters: StructuredQueryParameters
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticRetrievalStep:
    step_id: str
    query: str
    filters: SemanticFilterPlan = field(default_factory=SemanticFilterPlan)
    limit: int = 10
    hydrate: bool = True
    depends_on: tuple[str, ...] = ()


RetrievalStep = StructuredRetrievalStep | SemanticRetrievalStep


@dataclass(frozen=True)
class RetrievalPlan:
    mode: RetrievalMode
    routing_reason: str
    steps: tuple[RetrievalStep, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("retrieval plan must contain at least one step")

        # Plans execute in tuple order, so every dependency must be declared by
        # an earlier step. This catches cycles and misspelled references early.
        completed_ids: set[str] = set()
        for step in self.steps:
            if not step.step_id:
                raise ValueError("step_id must not be empty")
            if step.step_id in completed_ids:
                raise ValueError(f"duplicate step_id: {step.step_id}")
            missing = set(step.depends_on) - completed_ids
            if missing:
                names = ", ".join(sorted(missing))
                raise ValueError(
                    f"step {step.step_id} depends on unavailable steps: {names}"
                )
            completed_ids.add(step.step_id)


INTENT_OPERATIONS = {
    QueryIntent.APPLICATION_OVERVIEW: StructuredOperation.APPLICATION_OVERVIEW,
    QueryIntent.APPLICATION_TIMELINE: StructuredOperation.APPLICATION_TIMELINE,
    QueryIntent.APPLICATION_PROVENANCE: StructuredOperation.APPLICATION_PROVENANCE,
    QueryIntent.INCONSISTENT_STATUS_SNAPSHOT: (
        StructuredOperation.INCONSISTENT_STATUS_SNAPSHOT
    ),
    QueryIntent.UNLINKED_STATUS_EMAIL: StructuredOperation.UNLINKED_STATUS_EMAIL,
}


# Routing policy: choose structured, semantic, or hybrid retrieval from the
# normalized QuerySpec. Step construction remains the planner's responsibility.
def _decide_retrieval_route(spec: QuerySpec) -> RouteDecision:
    """Select the retrieval mode from normalized, analyzer-owned constraints."""
    if spec.intent is not QueryIntent.CONTENT_SEARCH:
        return RouteDecision(
            mode=RetrievalMode.STRUCTURED,
            reason=f"{spec.intent.value} is served by a structured query",
        )

    has_resolved_scope = any(
        (spec.application_id, spec.company_id, spec.position_id)
    )
    if spec.company and not has_resolved_scope:
        return RouteDecision(
            mode=RetrievalMode.HYBRID,
            reason="company text requires structured application scope resolution",
        )

    return RouteDecision(
        mode=RetrievalMode.SEMANTIC,
        reason="content search uses semantic retrieval with metadata filters",
    )


class RetrievalPlanner:
    """Route an analyzed query and compile it into retrieval steps."""

    def plan(self, spec: QuerySpec) -> RetrievalPlan:
        route = _decide_retrieval_route(spec)
        builders = {
            RetrievalMode.STRUCTURED: self._plan_structured,
            RetrievalMode.SEMANTIC: self._plan_semantic,
            RetrievalMode.HYBRID: self._plan_hybrid,
        }
        steps = builders[route.mode](spec)
        return RetrievalPlan(
            mode=route.mode,
            routing_reason=route.reason,
            steps=steps,
        )

    def _plan_structured(
        self,
        spec: QuerySpec,
    ) -> tuple[StructuredRetrievalStep, ...]:
        operation = INTENT_OPERATIONS.get(spec.intent)
        if operation is None:
            raise ValueError(f"intent {spec.intent} has no structured operation")

        email_type = self._single_value("email_types", spec.email_types)
        source_type = self._single_value("source_types", spec.source_types)
        parameters = StructuredQueryParameters(
            application_id=spec.application_id,
            company=spec.company,
            email_type=email_type,
            since=spec.since,
            before=spec.before,
            provenance_kind=spec.provenance_kind,
            source_type=source_type,
            limit=spec.limit,
        )
        self._validate_structured_scope(operation, parameters)
        return (
            StructuredRetrievalStep(
                step_id="structured_query",
                operation=operation,
                parameters=parameters,
            ),
        )

    def _plan_semantic(self, spec: QuerySpec) -> tuple[SemanticRetrievalStep, ...]:
        self._validate_content_search(spec)
        if spec.company and not any(
            (spec.application_id, spec.company_id, spec.position_id)
        ):
            raise ValueError(
                "company text requires hybrid scope resolution before semantic search"
            )

        return (
            self._semantic_step(
                spec,
                filters=SemanticFilterPlan(
                    application_id=spec.application_id,
                    company_id=spec.company_id,
                    position_id=spec.position_id,
                    source_types=spec.source_types,
                    email_types=spec.email_types,
                    linked_only=spec.linked_only,
                ),
            ),
        )

    def _plan_hybrid(
        self,
        spec: QuerySpec,
    ) -> tuple[StructuredRetrievalStep, SemanticRetrievalStep]:
        self._validate_content_search(spec)
        if not spec.company:
            raise ValueError("hybrid planning currently requires a company scope")
        if any((spec.application_id, spec.company_id, spec.position_id)):
            raise ValueError(
                "resolved ID filters should use semantic mode without scope resolution"
            )
        if spec.linked_only is False:
            raise ValueError("hybrid application scope conflicts with linked_only=False")

        resolve_company = StructuredRetrievalStep(
            step_id="resolve_company",
            operation=StructuredOperation.RESOLVE_COMPANY,
            # Exact canonical/alias matching may still expose conflicting data.
            # Keep every match so the adapter rejects an ambiguous hard filter.
            parameters=StructuredQueryParameters(company=spec.company),
        )
        search_content = self._semantic_step(
            spec,
            filters=SemanticFilterPlan(
                company_id=StepOutputRef(
                    step_id=resolve_company.step_id,
                    field="company_id",
                ),
                source_types=spec.source_types,
                email_types=spec.email_types,
                linked_only=True,
            ),
            depends_on=(resolve_company.step_id,),
        )
        return resolve_company, search_content

    @staticmethod
    def _semantic_step(
        spec: QuerySpec,
        *,
        filters: SemanticFilterPlan,
        depends_on: tuple[str, ...] = (),
    ) -> SemanticRetrievalStep:
        return SemanticRetrievalStep(
            step_id="semantic_search",
            query=spec.query.strip(),
            filters=filters,
            limit=spec.limit or 10,
            hydrate=spec.hydrate,
            depends_on=depends_on,
        )

    @staticmethod
    def _validate_content_search(spec: QuerySpec) -> None:
        if spec.intent is not QueryIntent.CONTENT_SEARCH:
            raise ValueError(
                f"{spec.intent} cannot be planned as semantic content search"
            )

    @staticmethod
    def _single_value(
        field_name: str,
        values: tuple[str, ...] | None,
    ) -> str | None:
        if values is None:
            return None
        if len(values) != 1:
            raise ValueError(f"structured {field_name} requires exactly one value")
        return values[0]

    @staticmethod
    def _validate_structured_scope(
        operation: StructuredOperation,
        parameters: StructuredQueryParameters,
    ) -> None:
        if operation is StructuredOperation.APPLICATION_TIMELINE:
            recent_submission = (
                parameters.email_type == "applied" and parameters.since is not None
            )
            if (
                parameters.application_id is None
                and not parameters.company
                and not recent_submission
            ):
                raise ValueError(
                    "timeline planning requires application_id, company, or "
                    "email_type='applied' with since"
                )
        elif operation is StructuredOperation.APPLICATION_PROVENANCE:
            if parameters.application_id is None and not parameters.company:
                raise ValueError(
                    "provenance planning requires application_id or company"
                )
