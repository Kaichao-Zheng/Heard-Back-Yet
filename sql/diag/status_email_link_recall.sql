SELECT
    COUNT(*) AS total_emails,
    COUNT(*) FILTER (
        WHERE email_type IN (
            'applied',
            'assessment',
            'interview',
            'offer',
            'rejection'
        )
    ) AS status_emails,
    ROUND(
        1.0 * COUNT(*) FILTER (
            WHERE email_type IN ('applied', 'assessment', 'interview', 'offer', 'rejection')
        )
        / NULLIF(COUNT(*), 0),
        4
    ) AS status_email_ratio,
    COUNT(*) FILTER (
        WHERE email_type IN (
            'applied',
            'assessment',
            'interview',
            'offer',
            'rejection'
        )
        AND application_id IS NOT NULL
    ) AS linked_status_emails,
    ROUND(
        1.0 * COUNT(*) FILTER (
            WHERE email_type IN ('applied', 'assessment', 'interview', 'offer', 'rejection')
            AND application_id IS NOT NULL
        )
        / NULLIF(COUNT(*) FILTER (
            WHERE email_type IN ('applied', 'assessment', 'interview', 'offer', 'rejection')
        ), 0),
        4
    ) AS status_link_recall
FROM email;