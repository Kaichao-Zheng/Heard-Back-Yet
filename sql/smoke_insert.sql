INSERT INTO company (company_name)
VALUES ('Example Company')
ON CONFLICT (company_name) DO NOTHING;

INSERT INTO position (position_name)
VALUES ('Example Position')
ON CONFLICT (position_name) DO NOTHING;

INSERT INTO company_alias (raw_name, company_id)
SELECT 'Example Co', company_id
FROM company
WHERE company_name = 'Example Company'
ON CONFLICT (raw_name) DO NOTHING;

INSERT INTO position_alias (raw_name, position_id)
SELECT 'Example Position Alias', position_id
FROM position
WHERE position_name = 'Example Position'
ON CONFLICT (raw_name) DO NOTHING;

INSERT INTO application (company_id, position_id)
SELECT c.company_id, p.position_id
FROM company c
JOIN position p ON p.position_name = 'Example Position'
WHERE c.company_name = 'Example Company'
ON CONFLICT (company_id, position_id) DO NOTHING;

INSERT INTO email (
    message_id,
    received_at,
    recipient,
    sender,
    subject,
    body_text,
    source_path,
    email_type,
    company_raw,
    position_raw,
    application_link_method,
    application_id
)
SELECT
    'smoke-message-id',
    NOW(),
    'candidate@example.com',
    'recruiter@example.com',
    'Application received',
    'Smoke test email body',
    'smoke/eml/example.eml',
    'applied',
    'Example Co',
    'Example Position Alias',
    'exact',
    a.application_id
FROM application a
JOIN company c ON c.company_id = a.company_id
JOIN position p ON p.position_id = a.position_id
WHERE c.company_name = 'Example Company'
  AND p.position_name = 'Example Position'
ON CONFLICT (message_id) DO NOTHING;

UPDATE application a
SET
    latest_status = e.email_type,
    latest_status_received_at = e.received_at,
    latest_status_email_id = e.email_id
FROM email e, company c, position p
WHERE e.application_id = a.application_id
  AND c.company_id = a.company_id
  AND p.position_id = a.position_id
  AND e.message_id = 'smoke-message-id'
  AND c.company_name = 'Example Company'
  AND p.position_name = 'Example Position';

INSERT INTO job_description (
    company_raw,
    position_raw,
    location_raw,
    salary_raw,
    responsibilities,
    qualifications,
    nice_to_have,
    source_url,
    source_path,
    application_id
)
SELECT
    'Example Co',
    'Example Position Alias',
    'Example Location',
    'Example Salary',
    'Example Responsibilities',
    'Example Qualifications',
    'Example Nice To Have',
    'https://example.com/jobs/example-position',
    'smoke/jd/example-position.md',
    a.application_id
FROM application a
JOIN company c ON c.company_id = a.company_id
JOIN position p ON p.position_id = a.position_id
WHERE c.company_name = 'Example Company'
  AND p.position_name = 'Example Position'
  AND NOT EXISTS (
      SELECT 1
      FROM job_description jd
      WHERE jd.source_path = 'smoke/jd/example-position.md'
  );
