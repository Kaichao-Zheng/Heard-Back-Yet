from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


from heardbackyet.constants import RETRIEVAL_SOURCE_TYPES, SEMANTIC_INDEX_EMAIL_LABELS
from heardbackyet.db.config import load_postgres_config
from heardbackyet.retrieval.semantic_retriever import search_semantic
from heardbackyet.retrieval.lexical_retriever import search_lexical
from heardbackyet.retrieval.hybrid_retriever import search_hybrid
from heardbackyet.retrieval.search_contracts import (
    SearchFilters,
    SearchRequest,
)
from heardbackyet.retrieval.hit_hydration import hydrate_search_hits
from heardbackyet.retrieval.text_embedder import (
    OllamaTextEmbedder,
    load_embedding_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search indexed email and JD content with semantic, lexical, or RRF hybrid ranking."
    )
    parser.add_argument("query", help="Natural-language content search query.")
    parser.add_argument(
        "--mode",
        choices=("semantic", "lexical", "hybrid"),
        default="semantic",
        help="Ranking implementation to use (default: semantic).",
    )
    parser.add_argument(
        "--application-id",
        type=positive_int,
        help="Only search chunks linked to one application.",
    )
    parser.add_argument(
        "--company-id",
        type=positive_int,
        help="Only search chunks associated with one canonical company.",
    )
    parser.add_argument(
        "--position-id",
        type=positive_int,
        help="Only search chunks associated with one canonical position.",
    )
    parser.add_argument(
        "--source-type",
        action="append",
        choices=RETRIEVAL_SOURCE_TYPES,
        help="Filter a source type; repeat to select more than one.",
    )
    parser.add_argument(
        "--email-type",
        action="append",
        choices=SEMANTIC_INDEX_EMAIL_LABELS,
        help=(
            "Filter an email label included in the semantic index; "
            "repeat to select more than one."
        ),
    )
    link_scope = parser.add_mutually_exclusive_group()
    link_scope.add_argument(
        "--linked-only",
        action="store_true",
        help="Only return chunks linked to an application.",
    )
    link_scope.add_argument(
        "--unlinked-only",
        action="store_true",
        help="Only return chunks not linked to an application.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=5,
        help="Maximum filtered results to return (default: 5).",
    )
    parser.add_argument(
        "--semantic-weight",
        type=non_negative_float,
        default=1.0,
        help="Semantic contribution in hybrid mode (default: 1.0).",
    )
    parser.add_argument(
        "--lexical-weight",
        type=non_negative_float,
        default=1.0,
        help="Lexical contribution in hybrid mode (default: 1.0).",
    )
    parser.add_argument(
        "--hydrate",
        action="store_true",
        help="Attach authoritative Email/JD source fields to search hits.",
    )
    return parser.parse_args()


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError(
            "value must be a finite non-negative number"
        )
    return parsed


def linked_only_from_args(args: argparse.Namespace) -> bool | None:
    if args.linked_only:
        return True
    if args.unlinked_only:
        return False
    return None


def build_request(args: argparse.Namespace) -> SearchRequest:
    return SearchRequest(
        query=args.query,
        filters=SearchFilters(
            application_id=args.application_id,
            company_id=args.company_id,
            position_id=args.position_id,
            source_types=(tuple(args.source_type) if args.source_type else None),
            email_types=(tuple(args.email_type) if args.email_type else None),
            linked_only=linked_only_from_args(args),
        ),
        limit=args.limit,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    engine = None
    try:
        request = build_request(args)
        engine = create_engine(load_postgres_config().database_url())
        with Session(engine) as session:
            if args.mode == "lexical":
                hits = search_lexical(session, request)
            else:
                embedder = OllamaTextEmbedder(load_embedding_config())
                if args.mode == "hybrid":
                    hits = search_hybrid(
                        session,
                        embedder,
                        request,
                        semantic_weight=args.semantic_weight,
                        lexical_weight=args.lexical_weight,
                    )
                else:
                    hits = search_semantic(session, embedder, request)
            results = hydrate_search_hits(session, hits) if args.hydrate else hits
        print(
            json.dumps(
                [asdict(hit) for hit in results],
                ensure_ascii=False,
                indent=2,
                default=json_default,
            )
        )
    except Exception as exc:
        print(f"search_chunks failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    return 0


def json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
