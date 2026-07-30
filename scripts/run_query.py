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
from heardbackyet.retrieval.text_embedder import (
    OllamaTextEmbedder,
    load_embedding_config,
)
from heardbackyet.orchestration.query_orchestrator import (
    QueryOrchestrationResult,
    QueryOrchestrator,
)
from heardbackyet.response.response_generator import (
    generate_baseline_response,
    generate_response,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify and execute one natural-language application query."
    )
    parser.add_argument("question", help="Natural-language question to execute.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--evidence-only",
        action="store_true",
        help="Run orchestration and show its evidence without generating an answer.",
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


def build_cli_payload(result: QueryOrchestrationResult) -> dict[str, Any]:
    """Expose orchestration output without leaking the internal retrieval plan."""
    serialized = asdict(result)
    classification = serialized["classification"]
    final_results = None
    if result.plan is not None:
        final_step_id = result.plan.steps[-1].step_id
        final_results = serialized["step_results"][final_step_id]

    return {
        "outcome": classification["outcome"],
        "reason_code": classification["reason_code"],
        "results": final_results,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    engine = None
    try:
        if args.llm_only:
            payload = {
                "mode": "llm_only",
                **generate_baseline_response(args.question),
            }
        else:
            engine = create_engine(load_postgres_config().database_url())
            embedder = OllamaTextEmbedder(load_embedding_config())
            with Session(engine) as session:
                result = QueryOrchestrator(
                    session,
                    embedder=embedder,
                ).orchestrate(args.question)
            if args.evidence_only:
                payload = {
                    "mode": "evidence_only",
                    **build_cli_payload(result),
                }
            else:
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
