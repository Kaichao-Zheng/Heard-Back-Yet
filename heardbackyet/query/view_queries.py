from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


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


def query_application_provenance(
    conn: Connection,
    *,
    application_id: int | None = None,
    company: str | None = None,
    provenance_kind: str | None = None,
    source_type: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return explainability rows from v_application_provenance."""
    if application_id is None and not company:
        raise ValueError(
            "provenance queries must be scoped by application_id or company"
        )

    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if application_id is not None:
        where_clauses.append("application_id = :application_id")
        params["application_id"] = application_id
    if company:
        where_clauses.append("company_name ILIKE :company_pattern")
        params["company_pattern"] = f"%{company}%"
    if provenance_kind:
        where_clauses.append("provenance_kind = :provenance_kind")
        params["provenance_kind"] = provenance_kind
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
            provenance_kind,
            source_type,
            provenance_id,
            provenance_timestamp,
            subject,
            source_path,
            source_url
        FROM v_application_provenance
    """
    return _fetch_view_rows(
        conn,
        sql,
        where_clauses,
        """
        ORDER BY provenance_timestamp ASC NULLS LAST, provenance_id ASC
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
