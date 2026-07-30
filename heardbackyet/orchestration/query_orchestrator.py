from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from heardbackyet.orchestration.intent_classifier import (
    ClassificationOutcome,
    IntentClassification,
    IntentClassifier,
)
from heardbackyet.orchestration.retrieval_executor import execute_retrieval_plan
from heardbackyet.orchestration.retrieval_planner import (
    RetrievalPlan,
    RetrievalPlanner,
)
from heardbackyet.retrieval.text_embedder import TextEmbedder


@dataclass(frozen=True)
class QueryOrchestrationResult:
    """Classification plus any retrieval work completed for one question."""

    classification: IntentClassification
    plan: RetrievalPlan | None
    step_results: dict[str, tuple[Any, ...]] | None

    def __post_init__(self) -> None:
        is_resolved = self.classification.outcome is ClassificationOutcome.RESOLVED
        if is_resolved and (self.plan is None or self.step_results is None):
            raise ValueError("resolved orchestration requires a plan and step results")
        if not is_resolved and (self.plan is not None or self.step_results is not None):
            raise ValueError("non-resolved orchestration must not execute retrieval")


class QueryOrchestrator:
    """Coordinate intent classification, retrieval planning, and execution."""

    def __init__(
        self,
        session: Session,
        *,
        embedder: TextEmbedder | None = None,
        classifier: IntentClassifier | None = None,
        planner: RetrievalPlanner | None = None,
    ) -> None:
        self._session = session
        self._embedder = embedder
        self._classifier = classifier or IntentClassifier()
        self._planner = planner or RetrievalPlanner()

    def orchestrate(
        self,
        question: str,
        *,
        reference_time: datetime | None = None,
    ) -> QueryOrchestrationResult:
        classification = self._classifier.classify(
            question,
            reference_time=reference_time,
        )
        if classification.outcome is not ClassificationOutcome.RESOLVED:
            return QueryOrchestrationResult(
                classification=classification,
                plan=None,
                step_results=None,
            )

        if classification.spec is None:
            raise RuntimeError("resolved classification did not provide a QuerySpec")

        plan = self._planner.plan(classification.spec)
        step_results = execute_retrieval_plan(
            plan,
            self._session,
            self._embedder,
        )
        return QueryOrchestrationResult(
            classification=classification,
            plan=plan,
            step_results=step_results,
        )
