from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db.config import load_postgres_config


MONTH_QUERY_TZ = timezone(timedelta(hours=8))


def query_application_overview(
    conn: Connection,
    *,
    company: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return current application snapshots from v_application_overview."""
    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if company:
        where_clauses.append("company_name ILIKE :company_pattern")
        params["company_pattern"] = f"%{company}%"

    sql = """
        SELECT
            application_id,
            company_id,
            position_id,
            company_name,
            position_name,
            latest_status_email_id,
            latest_status_received_at,
            latest_status,
            latest_status_email_subject,
            email_link_method,
            latest_jd_id,
            jd_captured_at,
            jd_location_raw,
            jd_salary_raw,
            jd_source_url
        FROM v_application_overview
    """
    return _fetch_view_rows(
        conn,
        sql,
        where_clauses,
        """
        ORDER BY latest_status_received_at DESC NULLS LAST, application_id DESC
        """,
        params,
        limit,
    )


def query_application_timeline(
    conn: Connection,
    *,
    application_id: int | None = None,
    company: str | None = None,
    email_type: str | None = None,
    since: datetime | None = None,
    before: datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return company-grain status timeline rows from v_application_timeline."""
    if application_id is None and not company and not _is_recent_submission_query(
        email_type,
        since,
    ):
        raise ValueError(
            "timeline queries must be scoped by application_id, company, "
            "or email_type='applied' with since"
        )

    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if application_id is not None:
        where_clauses.append("application_id = :application_id")
        params["application_id"] = application_id
    if company:
        where_clauses.append("company_name ILIKE :company_pattern")
        params["company_pattern"] = f"%{company}%"
    if email_type:
        where_clauses.append("email_type = :email_type")
        params["email_type"] = email_type
    if since is not None:
        where_clauses.append("received_at >= :since")
        params["since"] = since
    if before is not None:
        where_clauses.append("received_at < :before")
        params["before"] = before

    sql = """
        SELECT
            application_id,
            company_name,
            position_name,
            timeline_step,
            received_at,
            email_type,
            is_status_email,
            subject,
            sender,
            recipient,
            email_id,
            application_link_method,
            source_path
        FROM v_application_timeline
    """
    return _fetch_view_rows(
        conn,
        sql,
        where_clauses,
        """
        ORDER BY received_at ASC NULLS LAST, email_id ASC
        """,
        params,
        limit,
    )


def query_application_evidence(
    conn: Connection,
    *,
    application_id: int | None = None,
    company: str | None = None,
    evidence_kind: str | None = None,
    source_type: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return explainability evidence rows from v_application_evidence."""
    if application_id is None and not company:
        raise ValueError("evidence queries must be scoped by application_id or company")

    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if application_id is not None:
        where_clauses.append("application_id = :application_id")
        params["application_id"] = application_id
    if company:
        where_clauses.append("company_name ILIKE :company_pattern")
        params["company_pattern"] = f"%{company}%"
    if evidence_kind:
        where_clauses.append("evidence_kind = :evidence_kind")
        params["evidence_kind"] = evidence_kind
    if source_type:
        where_clauses.append("source_type = :source_type")
        params["source_type"] = source_type

    sql = """
        SELECT
            application_id,
            company_name,
            position_name,
            company_raw,
            position_raw,
            application_link_method,
            inferred_value,
            inferred_field,
            evidence_kind,
            source_type,
            evidence_id,
            evidence_timestamp,
            subject,
            source_path,
            source_url
        FROM v_application_evidence
    """
    return _fetch_view_rows(
        conn,
        sql,
        where_clauses,
        """
        ORDER BY evidence_timestamp ASC NULLS LAST, evidence_id ASC
        """,
        params,
        limit,
    )


def query_inconsistent_status_snapshots(
    conn: Connection,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return application status snapshot review rows."""
    sql = """
        SELECT
            application_id,
            company_name,
            position_name,
            inconsistency_kind,
            latest_status,
            latest_status_received_at,
            latest_status_email_id,
            pointed_email_id,
            pointed_email_application_id,
            pointed_email_type,
            pointed_email_received_at,
            pointed_email_subject
        FROM v_inconsistent_status_snapshot
    """
    return _fetch_view_rows(
        conn,
        sql,
        [],
        """
        ORDER BY application_id ASC
        """,
        {},
        limit,
    )


def query_unlinked_status_emails(
    conn: Connection,
    *,
    company: str | None = None,
    since: datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return status-driving emails that are not linked to an application."""
    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if company:
        where_clauses.append("company_raw ILIKE :company_pattern")
        params["company_pattern"] = f"%{company}%"
    if since is not None:
        where_clauses.append("received_at >= :since")
        params["since"] = since

    sql = """
        SELECT
            email_id,
            received_at,
            sender,
            recipient,
            subject,
            email_type,
            company_raw,
            position_raw,
            application_link_method,
            source_path
        FROM v_unlinked_status_email
    """
    return _fetch_view_rows(
        conn,
        sql,
        where_clauses,
        """
        ORDER BY received_at DESC NULLS LAST, email_id DESC
        """,
        params,
        limit,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query read-only PostgreSQL application tracking views."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    overview = subparsers.add_parser(
        "overview",
        help="List current application snapshots.",
    )
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
        "evidence",
        help="List evidence rows for one application or company.",
    )
    evidence.set_defaults(query_name="evidence")
    evidence.add_argument("--application-id", type=int, help="Filter one application.")
    evidence.add_argument("--company", help="Filter company_name with ILIKE.")
    evidence.add_argument("--evidence-kind", help="Filter by evidence_kind.")
    evidence.add_argument("--source-type", help="Filter by source_type.")
    add_limit_argument(evidence)

    inconsistent = subparsers.add_parser(
        "inconsistent-snapshot",
        help="List inconsistent latest status snapshots.",
    )
    inconsistent.set_defaults(query_name="inconsistent_status_snapshot")
    add_limit_argument(inconsistent)

    unlinked = subparsers.add_parser(
        "unlinked-email",
        help="List unlinked status-driving emails.",
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
        "--limit",
        type=positive_int,
        help="Maximum number of rows to return.",
    )


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    config = load_postgres_config()
    engine = create_engine(config.database_url())
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


def run_query_command(conn: Connection, args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.query_name == "overview":
        return query_application_overview(
            conn,
            company=args.company,
            limit=args.limit,
        )
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


def timeline_range_from_args(args: argparse.Namespace) -> tuple[datetime | None, datetime | None]:
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


def _is_recent_submission_query(email_type: str | None, since: datetime | None) -> bool:
    return email_type == "applied" and since is not None


def _fetch_view_rows(
    conn: Connection,
    base_sql: str,
    where_clauses: list[str],
    order_by_sql: str,
    params: dict[str, Any],
    limit: int | None,
) -> list[dict[str, Any]]:
    if limit is not None and limit < 1:
        raise ValueError("limit must be a positive integer")

    sql_parts = [base_sql]
    if where_clauses:
        sql_parts.append("WHERE " + " AND ".join(where_clauses))
    sql_parts.append(order_by_sql)
    if limit is not None:
        sql_parts.append("LIMIT :limit")
        params = {**params, "limit": limit}

    result = conn.execute(text("\n".join(sql_parts)), params)
    return [dict(row) for row in result.mappings()]


def json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
