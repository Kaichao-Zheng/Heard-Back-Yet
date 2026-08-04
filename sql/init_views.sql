-- Reference snapshot only; application view changes are managed by Alembic migrations.
-- This file is not read by runtime code and must not be used to upgrade a database.

CREATE OR REPLACE VIEW v_application_overview AS
SELECT
    -- Application identity
    a.application_id,
    a.company_id,
    a.position_id,
    c.company_name,
    p.position_name,

    -- Application-level status_email snapshot
    a.latest_status_email_id,       -- snapshot pointer
    a.latest_status_received_at,    -- snapshot
    a.latest_status,                -- snapshot
    e.subject AS latest_status_email_subject,
    e.application_link_method AS email_link_method,
    e.source_path AS eml_source_path,

    -- Application-level JD snapshot
    a.latest_jd_id,                 -- snapshot pointer
    jd.captured_at AS jd_captured_at,
    jd.location_raw AS jd_location_raw,
    jd.salary_raw AS jd_salary_raw,
    jd.source_path AS jd_source_path,
    jd.source_url AS jd_source_url
FROM application AS a
JOIN company AS c
    ON c.company_id = a.company_id
JOIN position AS p
    ON p.position_id = a.position_id
LEFT JOIN email AS e
    ON e.email_id = a.latest_status_email_id
    AND e.application_id = a.application_id
LEFT JOIN job_description AS jd
    ON jd.jd_id = a.latest_jd_id
    AND jd.application_id = a.application_id;

CREATE OR REPLACE VIEW v_application_timeline AS
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
JOIN company_alias AS ca
    ON ca.raw_name = e.company_raw
JOIN company AS c
    ON c.company_id = ca.company_id
LEFT JOIN application AS a
    ON a.application_id = e.application_id
    AND a.company_id = c.company_id
LEFT JOIN position AS p
    ON p.position_id = a.position_id
WHERE e.email_type IN (
    'applied',
    'assessment',
    'interview',
    'offer',
    'rejection'
);

CREATE OR REPLACE VIEW v_application_provenance AS
SELECT
    -- Application identity
    a.application_id,
    c.company_name,
    p.position_name,
    e.company_raw,
    e.position_raw,

    -- Provenance meaning
    e.application_link_method,
    a.latest_status AS inferred_value,
    'latest_status'::TEXT AS inferred_field,
    'latest_status_email'::TEXT AS provenance_kind,
    'email'::TEXT AS source_type,

    -- Provenance source
    e.email_id AS provenance_id,
    e.received_at AS provenance_timestamp,
    e.subject,
    e.source_path,
    NULL::TEXT AS source_url
FROM application AS a
JOIN company AS c
    ON c.company_id = a.company_id
JOIN position AS p
    ON p.position_id = a.position_id
JOIN email AS e
    ON e.email_id = a.latest_status_email_id
    AND e.application_id = a.application_id

UNION ALL

SELECT
    -- Application identity
    e.application_id,
    c.company_name,
    p.position_name,
    e.company_raw,
    e.position_raw,

    -- Provenance meaning
    e.application_link_method,
    e.email_type AS inferred_value,
    'application_link'::TEXT AS inferred_field,
    'linked_email'::TEXT AS provenance_kind,
    'email'::TEXT AS source_type,

    -- Provenance source
    e.email_id AS provenance_id,
    e.received_at AS provenance_timestamp,
    e.subject,
    e.source_path,
    NULL::TEXT AS source_url
FROM email AS e
JOIN application AS a
    ON a.application_id = e.application_id
JOIN company AS c
    ON c.company_id = a.company_id
JOIN position AS p
    ON p.position_id = a.position_id
WHERE e.application_id IS NOT NULL

UNION ALL

SELECT
    -- Application identity
    jd.application_id,
    c.company_name,
    p.position_name,
    jd.company_raw,
    jd.position_raw,

    -- Provenance meaning
    NULL::TEXT AS application_link_method,
    NULL::TEXT AS inferred_value,
    'application_link'::TEXT AS inferred_field,
    'linked_job_description'::TEXT AS provenance_kind,
    'job_description'::TEXT AS source_type,

    -- Provenance source
    jd.jd_id AS provenance_id,
    jd.captured_at::TIMESTAMPTZ AS provenance_timestamp,
    NULL::TEXT AS subject,
    jd.source_path,
    jd.source_url
FROM job_description AS jd
JOIN application AS a
    ON a.application_id = jd.application_id
JOIN company AS c
    ON c.company_id = a.company_id
JOIN position AS p
    ON p.position_id = a.position_id
WHERE jd.application_id IS NOT NULL;

CREATE OR REPLACE VIEW v_inconsistent_status_snapshot AS
SELECT
    a.application_id,
    c.company_name,
    p.position_name,
    CASE
        WHEN (
            a.latest_status IS NOT NULL
            AND a.latest_status_email_id IS NULL
        ) THEN 'missing_status_email_pointer'
        WHEN (
            a.latest_status_email_id IS NOT NULL
            AND e.email_id IS NULL
        ) THEN 'dangling_status_email_pointer'
        WHEN (
            e.email_id IS NOT NULL
            AND e.application_id IS DISTINCT FROM a.application_id
        ) THEN 'mismatched_status_email_application'
        WHEN (
            e.email_id IS NOT NULL
            AND a.latest_status IS DISTINCT FROM e.email_type
        ) THEN 'mismatched_status_value'
        WHEN (
            e.email_id IS NOT NULL
            AND a.latest_status_received_at IS DISTINCT FROM e.received_at
        ) THEN 'mismatched_status_timestamp'
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
JOIN company AS c
    ON c.company_id = a.company_id
JOIN position AS p
    ON p.position_id = a.position_id
LEFT JOIN email AS e
    ON e.email_id = a.latest_status_email_id
WHERE (
    a.latest_status IS NOT NULL
    AND a.latest_status_email_id IS NULL
)
OR (
    a.latest_status_email_id IS NOT NULL
    AND e.email_id IS NULL
)
OR (
    e.email_id IS NOT NULL
    AND e.application_id IS DISTINCT FROM a.application_id
)
OR (
    e.email_id IS NOT NULL
    AND a.latest_status IS DISTINCT FROM e.email_type
)
OR (
    e.email_id IS NOT NULL
    AND a.latest_status_received_at IS DISTINCT FROM e.received_at
);

CREATE OR REPLACE VIEW v_unlinked_status_email AS
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
AND e.application_id IS NULL;
