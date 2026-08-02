from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from heardbackyet.db.config import load_postgres_config
from heardbackyet.orchestration.intent_classifier import (
    IntentClassification,
    IntentClassifier,
)
from heardbackyet.orchestration.query_orchestrator import (
    QueryOrchestrationResult,
    QueryOrchestrator,
)
from heardbackyet.orchestration.query_spec import QueryIntent
from heardbackyet.retrieval.text_embedder import (
    TextEmbedder,
    load_embedding_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify and execute one natural-language application query."
    )
    parser.add_argument("question", help="Natural-language question to execute.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--evidence",
        action="store_true",
        help=(
            "Show classification and, for content_search, append retriever "
            "evidence without generating an answer."
        ),
    )
    modes.add_argument(
        "--query-spec",
        action="store_true",
        help=(
            "Show the validated QuerySpec produced before retrieval planning, "
            "then stop."
        ),
    )
    modes.add_argument(
        "--llm-only",
        action="store_true",
        help="Skip orchestration and let the response model answer directly.",
    )
    return parser.parse_args()


def json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def build_cli_payload(
    classification: IntentClassification,
    result: QueryOrchestrationResult | None = None,
) -> dict[str, Any]:
    """Expose classification plus optional content-search evidence."""
    reason = classification.reason_code
    spec = classification.spec
    payload: dict[str, Any] = {
        "outcome": classification.outcome.value,
        "reason_code": reason.value if reason is not None else None,
        "intent": spec.intent.value if spec is not None else None,
    }
    if result is not None:
        if result.plan is None or result.step_results is None:
            raise ValueError("retrieval evidence requires completed orchestration")
        final_step_id = result.plan.steps[-1].step_id
        records = asdict(result)["step_results"][final_step_id]
        projected_records = []
        for record in records:
            retrieval = record.get("retrieval")
            if not isinstance(retrieval, dict):
                raise ValueError("content evidence record is missing retrieval metadata")
            metric = retrieval.get("metric")
            metric_fields = {
                "cosine_distance": ("rank", "metric", "distance"),
                "bm25": ("rank", "metric", "score"),
                "rrf": ("rank", "metric", "score"),
            }.get(metric)
            if metric_fields is None:
                raise ValueError(f"unsupported retrieval metric: {metric}")
            projected_records.append(
                {
                    **record,
                    "retrieval": {
                        field_name: retrieval[field_name]
                        for field_name in metric_fields
                    },
                }
            )
        payload["results"] = projected_records
    return payload


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    engine = None
    try:
        if args.llm_only:
            from heardbackyet.response.response_generator import (
                generate_baseline_response,
            )

            payload = {
                "mode": "llm_only",
                **generate_baseline_response(args.question),
            }
        elif args.query_spec:
            classification = IntentClassifier().classify(args.question)
            reason = classification.reason_code
            payload = {
                "mode": "query_spec",
                "outcome": classification.outcome.value,
                "reason_code": reason.value if reason is not None else None,
                "query_spec": (
                    asdict(classification.spec)
                    if classification.spec is not None
                    else None
                ),
            }
        elif args.evidence:
            classification = IntentClassifier().classify(args.question)
            spec = classification.spec
            result = None
            if (
                spec is not None
                and spec.intent is QueryIntent.CONTENT_SEARCH
            ):
                engine = create_engine(load_postgres_config().database_url())
                embedder = TextEmbedder(load_embedding_config())
                with Session(engine) as session:
                    result = QueryOrchestrator(
                        session,
                        embedder=embedder,
                    ).orchestrate_classified_query(classification)
            payload = {
                "mode": "evidence",
                **build_cli_payload(classification, result),
            }
        else:
            engine = create_engine(load_postgres_config().database_url())
            embedder = TextEmbedder(load_embedding_config())
            with Session(engine) as session:
                result = QueryOrchestrator(
                    session,
                    embedder=embedder,
                ).orchestrate(args.question)
            from heardbackyet.response.response_generator import generate_response

            payload = {
                "mode": "full",
                **generate_response(result),
            }
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                default=json_default,
            )
        )
    except Exception as exc:
        print(f"query failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
