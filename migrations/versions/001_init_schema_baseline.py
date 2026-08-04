"""init schema baseline

Revision ID: 001
Revises:
Create Date: 2026-08-04 14:35:45.247474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # pgvector must exist before PostgreSQL can create the embedding column.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")

    op.create_table(
        "company",
        sa.Column("company_id", sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("company_id"),
        sa.UniqueConstraint("company_name", name="company_company_name_key"),
    )
    op.create_table(
        "position",
        sa.Column("position_id", sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column("position_name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("position_id"),
        sa.UniqueConstraint("position_name", name="position_position_name_key"),
    )
    op.create_table(
        "application",
        sa.Column(
            "application_id", sa.Integer(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("latest_status", sa.Text(), nullable=True),
        sa.Column("latest_status_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_status_email_id", sa.Integer(), nullable=True),
        sa.Column("latest_jd_id", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "latest_status IS NULL OR latest_status IN "
            "('applied', 'assessment', 'interview', 'offer', 'rejection')",
            name="application_latest_status_check",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["company.company_id"]),
        sa.ForeignKeyConstraint(["position_id"], ["position.position_id"]),
        sa.PrimaryKeyConstraint("application_id"),
        sa.UniqueConstraint(
            "company_id",
            "position_id",
            name="application_company_id_position_id_key",
        ),
    )
    op.create_table(
        "company_alias",
        sa.Column(
            "company_alias_id", sa.Integer(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.company_id"]),
        sa.PrimaryKeyConstraint("company_alias_id"),
        sa.UniqueConstraint("raw_name", name="company_alias_raw_name_key"),
    )
    op.create_table(
        "position_alias",
        sa.Column(
            "position_alias_id",
            sa.Integer(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["position_id"], ["position.position_id"]),
        sa.PrimaryKeyConstraint("position_alias_id"),
        sa.UniqueConstraint("raw_name", name="position_alias_raw_name_key"),
    )
    op.create_table(
        "email",
        sa.Column("email_id", sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recipient", sa.Text(), nullable=False),
        sa.Column("sender", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("email_type", sa.Text(), nullable=True),
        sa.Column("company_raw", sa.Text(), nullable=True),
        sa.Column("position_raw", sa.Text(), nullable=True),
        sa.Column("application_link_method", sa.Text(), nullable=True),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "application_link_method IS NULL OR application_link_method IN "
            "('exact', 'company_singleton', 'manual')",
            name="email_application_link_method_check",
        ),
        sa.CheckConstraint(
            "email_type IS NULL OR email_type IN "
            "('auth', 'delivery-failure', 'logistics', 'unrelated', 'unknown', "
            "'applied', 'profile-update', 'assessment', 'interview', 'offer', "
            "'rejection')",
            name="email_email_type_check",
        ),
        sa.ForeignKeyConstraint(["application_id"], ["application.application_id"]),
        sa.PrimaryKeyConstraint("email_id"),
        sa.UniqueConstraint("message_id", name="email_message_id_key"),
    )
    op.create_table(
        "job_description",
        sa.Column("jd_id", sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column("captured_at", sa.Date(), nullable=True),
        sa.Column("company_raw", sa.Text(), nullable=True),
        sa.Column("position_raw", sa.Text(), nullable=True),
        sa.Column("location_raw", sa.Text(), nullable=True),
        sa.Column("salary_raw", sa.Text(), nullable=True),
        sa.Column("responsibilities", sa.Text(), nullable=True),
        sa.Column("qualifications", sa.Text(), nullable=True),
        sa.Column("nice_to_have", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["application.application_id"]),
        sa.PrimaryKeyConstraint("jd_id"),
    )
    op.create_table(
        "retrieval_chunk",
        sa.Column("chunk_id", sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("position_id", sa.Integer(), nullable=True),
        sa.Column("email_type", sa.Text(), nullable=True),
        sa.Column("semantic_fields", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column(
            "embedded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(source_type = 'email' AND email_type IN "
            "('applied', 'assessment', 'interview', 'offer', 'rejection', "
            "'logistics', 'profile-update')) OR "
            "(source_type = 'job_description' AND email_type IS NULL)",
            name="retrieval_chunk_check",
        ),
        sa.CheckConstraint(
            "source_type IN ('email', 'job_description')",
            name="retrieval_chunk_source_type_check",
        ),
        sa.ForeignKeyConstraint(["application_id"], ["application.application_id"]),
        sa.ForeignKeyConstraint(["company_id"], ["company.company_id"]),
        sa.ForeignKeyConstraint(["position_id"], ["position.position_id"]),
        sa.PrimaryKeyConstraint("chunk_id"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            name="retrieval_chunk_source_type_source_id_key",
        ),
    )

    op.execute(APPLICATION_OVERVIEW_VIEW)
    op.execute(APPLICATION_TIMELINE_VIEW)
    op.execute(APPLICATION_PROVENANCE_VIEW)
    op.execute(INCONSISTENT_STATUS_SNAPSHOT_VIEW)
    op.execute(UNLINKED_STATUS_EMAIL_VIEW)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_unlinked_status_email")
    op.execute("DROP VIEW IF EXISTS v_inconsistent_status_snapshot")
    op.execute("DROP VIEW IF EXISTS v_application_provenance")
    op.execute("DROP VIEW IF EXISTS v_application_timeline")
    op.execute("DROP VIEW IF EXISTS v_application_overview")
    op.drop_table("retrieval_chunk")
    op.drop_table("job_description")
    op.drop_table("email")
    op.drop_table("position_alias")
    op.drop_table("company_alias")
    op.drop_table("application")
    op.drop_table("position")
    op.drop_table("company")
    op.execute("DROP EXTENSION IF EXISTS vector")


APPLICATION_OVERVIEW_VIEW = """
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


APPLICATION_TIMELINE_VIEW = """
CREATE VIEW v_application_timeline AS
SELECT
    a.application_id,
    c.company_name,
    p.position_name,
    ROW_NUMBER() OVER (
        PARTITION BY c.company_id
        ORDER BY e.received_at, e.email_id
    ) AS timeline_step,
    e.received_at,
    e.email_type,
    TRUE AS is_status_email,
    e.subject,
    e.sender,
    e.recipient,
    e.email_id,
    e.application_link_method,
    e.source_path
FROM email AS e
JOIN company_alias AS ca ON ca.raw_name = e.company_raw
JOIN company AS c ON c.company_id = ca.company_id
LEFT JOIN application AS a
    ON a.application_id = e.application_id
    AND a.company_id = c.company_id
LEFT JOIN position AS p ON p.position_id = a.position_id
WHERE e.email_type IN (
    'applied',
    'assessment',
    'interview',
    'offer',
    'rejection'
)
"""


APPLICATION_PROVENANCE_VIEW = """
CREATE VIEW v_application_provenance AS
SELECT
    a.application_id,
    c.company_name,
    p.position_name,
    e.company_raw,
    e.position_raw,
    e.application_link_method,
    a.latest_status AS inferred_value,
    'latest_status'::TEXT AS inferred_field,
    'latest_status_email'::TEXT AS provenance_kind,
    'email'::TEXT AS source_type,
    e.email_id AS provenance_id,
    e.received_at AS provenance_timestamp,
    e.subject,
    e.source_path,
    NULL::TEXT AS source_url
FROM application AS a
JOIN company AS c ON c.company_id = a.company_id
JOIN position AS p ON p.position_id = a.position_id
JOIN email AS e
    ON e.email_id = a.latest_status_email_id
    AND e.application_id = a.application_id

UNION ALL

SELECT
    e.application_id,
    c.company_name,
    p.position_name,
    e.company_raw,
    e.position_raw,
    e.application_link_method,
    e.email_type AS inferred_value,
    'application_link'::TEXT AS inferred_field,
    'linked_email'::TEXT AS provenance_kind,
    'email'::TEXT AS source_type,
    e.email_id AS provenance_id,
    e.received_at AS provenance_timestamp,
    e.subject,
    e.source_path,
    NULL::TEXT AS source_url
FROM email AS e
JOIN application AS a ON a.application_id = e.application_id
JOIN company AS c ON c.company_id = a.company_id
JOIN position AS p ON p.position_id = a.position_id
WHERE e.application_id IS NOT NULL

UNION ALL

SELECT
    jd.application_id,
    c.company_name,
    p.position_name,
    jd.company_raw,
    jd.position_raw,
    NULL::TEXT AS application_link_method,
    NULL::TEXT AS inferred_value,
    'application_link'::TEXT AS inferred_field,
    'linked_job_description'::TEXT AS provenance_kind,
    'job_description'::TEXT AS source_type,
    jd.jd_id AS provenance_id,
    jd.captured_at::TIMESTAMPTZ AS provenance_timestamp,
    NULL::TEXT AS subject,
    jd.source_path,
    jd.source_url
FROM job_description AS jd
JOIN application AS a ON a.application_id = jd.application_id
JOIN company AS c ON c.company_id = a.company_id
JOIN position AS p ON p.position_id = a.position_id
WHERE jd.application_id IS NOT NULL
"""


INCONSISTENT_STATUS_SNAPSHOT_VIEW = """
CREATE VIEW v_inconsistent_status_snapshot AS
SELECT
    a.application_id,
    c.company_name,
    p.position_name,
    CASE
        WHEN a.latest_status IS NOT NULL
            AND a.latest_status_email_id IS NULL
            THEN 'missing_status_email_pointer'
        WHEN a.latest_status_email_id IS NOT NULL
            AND e.email_id IS NULL
            THEN 'dangling_status_email_pointer'
        WHEN e.email_id IS NOT NULL
            AND e.application_id IS DISTINCT FROM a.application_id
            THEN 'mismatched_status_email_application'
        WHEN e.email_id IS NOT NULL
            AND a.latest_status IS DISTINCT FROM e.email_type
            THEN 'mismatched_status_value'
        WHEN e.email_id IS NOT NULL
            AND a.latest_status_received_at IS DISTINCT FROM e.received_at
            THEN 'mismatched_status_timestamp'
    END AS inconsistency_kind,
    a.latest_status,
    a.latest_status_received_at,
    a.latest_status_email_id,
    e.email_id AS pointed_email_id,
    e.application_id AS pointed_email_application_id,
    e.email_type AS pointed_email_type,
    e.received_at AS pointed_email_received_at,
    e.subject AS pointed_email_subject
FROM application AS a
JOIN company AS c ON c.company_id = a.company_id
JOIN position AS p ON p.position_id = a.position_id
LEFT JOIN email AS e ON e.email_id = a.latest_status_email_id
WHERE (a.latest_status IS NOT NULL AND a.latest_status_email_id IS NULL)
OR (a.latest_status_email_id IS NOT NULL AND e.email_id IS NULL)
OR (e.email_id IS NOT NULL AND e.application_id IS DISTINCT FROM a.application_id)
OR (e.email_id IS NOT NULL AND a.latest_status IS DISTINCT FROM e.email_type)
OR (
    e.email_id IS NOT NULL
    AND a.latest_status_received_at IS DISTINCT FROM e.received_at
)
"""


UNLINKED_STATUS_EMAIL_VIEW = """
CREATE VIEW v_unlinked_status_email AS
SELECT
    e.email_id,
    e.received_at,
    e.sender,
    e.recipient,
    e.subject,
    e.email_type,
    e.company_raw,
    e.position_raw,
    e.application_link_method,
    e.source_path
FROM email AS e
WHERE e.email_type IN (
    'applied',
    'assessment',
    'interview',
    'offer',
    'rejection'
)
AND e.application_id IS NULL
"""
