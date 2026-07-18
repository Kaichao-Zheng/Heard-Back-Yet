from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


from heardbackyet.constants import RETRIEVAL_EMAIL_LABELS
from heardbackyet.db.config import load_postgres_config
from heardbackyet.retrieval.semantic_search import (
    RETRIEVAL_SOURCE_TYPES,
    SearchFilters,
    SearchRequest,
    search_retrieval,
)
from heardbackyet.retrieval.source_hydration import hydrate_search_hits
from heardbackyet.retrieval.text_embedder import (
    OllamaTextEmbedder,
    load_embedding_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search indexed email and JD content with exact cosine distance."
    )
    parser.add_argument("query", help="Natural-language semantic search query.")
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
        choices=RETRIEVAL_EMAIL_LABELS,
        help="Filter an eligible email label; repeat to select more than one.",
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
        default=10,
        help="Maximum filtered results to return (default: 10).",
    )
    parser.add_argument(
        "--hydrate",
        action="store_true",
        help="Attach authoritative Email/JD source fields to each search hit.",
    )
    return parser.parse_args()


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
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
        embedder = OllamaTextEmbedder(load_embedding_config())
        engine = create_engine(load_postgres_config().database_url())
        with Session(engine) as session:
            hits = search_retrieval(session, embedder, request)
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
