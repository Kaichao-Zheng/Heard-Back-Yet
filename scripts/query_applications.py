from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from heardbackyet.constants import RETRIEVAL_SOURCE_TYPES, APPLICATION_EVIDENCE_KINDS
from heardbackyet.db.config import load_postgres_config
from heardbackyet.query.view_queries import (
    query_application_evidence,
    query_application_overview,
    query_application_timeline,
    query_inconsistent_status_snapshots,
    query_unlinked_status_emails,
)


MONTH_QUERY_TZ = timezone(timedelta(hours=8))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query read-only PostgreSQL application tracking views."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    overview = subparsers.add_parser("overview", help="List current application snapshots.")
    overview.set_defaults(query_name="overview")
    overview.add_argument("--company", help="Filter company_name with ILIKE.")
    add_limit_argument(overview)

    timeline = subparsers.add_parser(
        "timeline",
        help="List company-grain status timeline rows, optionally scoped to one application.",
    )
    timeline.set_defaults(query_name="timeline")
    timeline.add_argument("--application-id", type=int, help="Filter one application.")
    timeline.add_argument("--company", help="Filter company_name with ILIKE.")
    timeline.add_argument("--email-type", help="Filter by email_type.")
    timeline_range = timeline.add_mutually_exclusive_group()
    timeline_range.add_argument(
        "--last-days",
        type=positive_int,
        help="Only include emails received in the last N days.",
    )
    timeline_range.add_argument(
        "--month",
        type=parse_month,
        metavar="YYYY-MM",
        help="Only include emails received in one calendar month.",
    )
    add_limit_argument(timeline)

    evidence = subparsers.add_parser(
        "evidence", help="List evidence rows for one application or company."
    )
    evidence.set_defaults(query_name="evidence")
    evidence.add_argument("--application-id", type=int, help="Filter one application.")
    evidence.add_argument("--company", help="Filter company_name with ILIKE.")
    evidence.add_argument(
        "--evidence-kind",
        choices=APPLICATION_EVIDENCE_KINDS,
        help="Filter by evidence_kind.",
    )
    evidence.add_argument(
        "--source-type",
        choices=RETRIEVAL_SOURCE_TYPES,
        help="Filter by source_type.",
    )
    add_limit_argument(evidence)

    inconsistent = subparsers.add_parser(
        "inconsistent-snapshot", help="List inconsistent latest status snapshots."
    )
    inconsistent.set_defaults(query_name="inconsistent_status_snapshot")
    add_limit_argument(inconsistent)

    unlinked = subparsers.add_parser(
        "unlinked-email", help="List unlinked status-driving emails."
    )
    unlinked.set_defaults(query_name="unlinked_status_email")
    unlinked.add_argument("--company", help="Filter company_raw with ILIKE.")
    unlinked.add_argument(
        "--last-days",
        type=positive_int,
        help="Only include emails received in the last N days.",
    )
    add_limit_argument(unlinked)
    return parser.parse_args()


def add_limit_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--limit", type=positive_int, help="Maximum number of rows to return."
    )


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def run_query_command(conn: Connection, args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.query_name == "overview":
        return query_application_overview(conn, company=args.company, limit=args.limit)
    if args.query_name == "timeline":
        since, before = timeline_range_from_args(args)
        return query_application_timeline(
            conn,
            application_id=args.application_id,
            company=args.company,
            email_type=args.email_type,
            since=since,
            before=before,
            limit=args.limit,
        )
    if args.query_name == "evidence":
        return query_application_evidence(
            conn,
            application_id=args.application_id,
            company=args.company,
            evidence_kind=args.evidence_kind,
            source_type=args.source_type,
            limit=args.limit,
        )
    if args.query_name == "inconsistent_status_snapshot":
        return query_inconsistent_status_snapshots(conn, limit=args.limit)
    if args.query_name == "unlinked_status_email":
        return query_unlinked_status_emails(
            conn,
            company=args.company,
            since=since_from_last_days(args.last_days),
            limit=args.limit,
        )
    raise ValueError(f"Unsupported command: {args.command}")


def since_from_last_days(last_days: int | None) -> datetime | None:
    if last_days is None:
        return None
    return datetime.now(UTC) - timedelta(days=last_days)


def timeline_range_from_args(
    args: argparse.Namespace,
) -> tuple[datetime | None, datetime | None]:
    if args.month is not None:
        return args.month
    return since_from_last_days(args.last_days), None


def parse_month(value: str) -> tuple[datetime, datetime]:
    try:
        year_raw, month_raw = value.split("-", maxsplit=1)
        year = int(year_raw)
        month = int(month_raw)
        start = datetime(year, month, 1, tzinfo=MONTH_QUERY_TZ)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("month must use YYYY-MM format") from exc

    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=MONTH_QUERY_TZ)
    else:
        end = datetime(year, month + 1, 1, tzinfo=MONTH_QUERY_TZ)
    return start, end


def json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    engine = create_engine(load_postgres_config().database_url())
    try:
        with engine.connect() as conn:
            rows = run_query_command(conn, args)
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=json_default))
    except Exception as exc:
        print(f"query_applications failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
