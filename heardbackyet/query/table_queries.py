from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


def query_company_matches(
    conn: Connection,
    *,
    company: str,
) -> list[dict[str, Any]]:
    """Return exact canonical company-name or alias matches without guessing."""
    normalized_company = company.strip()
    if not normalized_company:
        raise ValueError("company must not be blank")

    result = conn.execute(
        text(
            """
            SELECT DISTINCT
                c.company_id,
                c.company_name
            FROM company AS c
            LEFT JOIN company_alias AS ca
                ON ca.company_id = c.company_id
            WHERE
                LOWER(c.company_name) = LOWER(:company)
                OR LOWER(ca.raw_name) = LOWER(:company)
            ORDER BY c.company_id
            """
        ),
        {"company": normalized_company},
    )
    return [dict(row) for row in result.mappings()]
