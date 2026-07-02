SELECT 'company' AS table_name, COUNT(*) FROM company
UNION ALL
SELECT 'position', COUNT(*) FROM position
UNION ALL
SELECT 'company_alias', COUNT(*) FROM company_alias
UNION ALL
SELECT 'position_alias', COUNT(*) FROM position_alias
UNION ALL
SELECT 'application', COUNT(*) FROM application
UNION ALL
SELECT 'email', COUNT(*) FROM email
UNION ALL
SELECT 'job_description', COUNT(*) FROM job_description;