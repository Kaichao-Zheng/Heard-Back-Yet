"""add source paths to application overview

Revision ID: 002
Revises: 001
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Expose the status-email and JD source files on the overview view."""
    # CREATE OR REPLACE cannot insert eml_source_path before the existing JD columns.
    op.execute("DROP VIEW v_application_overview")
    op.execute(APPLICATION_OVERVIEW_VIEW_WITH_SOURCE_PATHS)


def downgrade() -> None:
    """Restore the overview view contract from revision 001."""
    # PostgreSQL cannot remove view columns with CREATE OR REPLACE VIEW.
    op.execute("DROP VIEW v_application_overview")
    op.execute(APPLICATION_OVERVIEW_VIEW_WITHOUT_SOURCE_PATHS)


APPLICATION_OVERVIEW_VIEW_WITH_SOURCE_PATHS = """
CREATE VIEW v_application_overview AS
SELECT
    a.application_id,
    a.company_id,
    a.position_id,
    c.company_name,
    p.position_name,
    a.latest_status_email_id,
    a.latest_status_received_at,
    a.latest_status,
    e.subject AS latest_status_email_subject,
    e.application_link_method AS email_link_method,
    e.source_path AS eml_source_path,
    a.latest_jd_id,
    jd.captured_at AS jd_captured_at,
    jd.location_raw AS jd_location_raw,
    jd.salary_raw AS jd_salary_raw,
    jd.source_path AS jd_source_path,
    jd.source_url AS jd_source_url
FROM application AS a
JOIN company AS c ON c.company_id = a.company_id
JOIN position AS p ON p.position_id = a.position_id
LEFT JOIN email AS e
    ON e.email_id = a.latest_status_email_id
    AND e.application_id = a.application_id
LEFT JOIN job_description AS jd
    ON jd.jd_id = a.latest_jd_id
    AND jd.application_id = a.application_id
"""


APPLICATION_OVERVIEW_VIEW_WITHOUT_SOURCE_PATHS = """
CREATE VIEW v_application_overview AS
SELECT
    a.application_id,
    a.company_id,
    a.position_id,
    c.company_name,
    p.position_name,
    a.latest_status_email_id,
    a.latest_status_received_at,
    a.latest_status,
    e.subject AS latest_status_email_subject,
    e.application_link_method AS email_link_method,
    a.latest_jd_id,
    jd.captured_at AS jd_captured_at,
    jd.location_raw AS jd_location_raw,
    jd.salary_raw AS jd_salary_raw,
    jd.source_url AS jd_source_url
FROM application AS a
JOIN company AS c ON c.company_id = a.company_id
JOIN position AS p ON p.position_id = a.position_id
LEFT JOIN email AS e
    ON e.email_id = a.latest_status_email_id
    AND e.application_id = a.application_id
LEFT JOIN job_description AS jd
    ON jd.jd_id = a.latest_jd_id
    AND jd.application_id = a.application_id
"""
