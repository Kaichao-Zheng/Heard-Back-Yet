from __future__ import annotations

from pathlib import Path

from heardbackyet.db.config import (
    MAINTENANCE_DATABASE,
    PostgresConfig,
    load_postgres_config,
)
from heardbackyet.paths import ENV_PATH, SQL_SCHEMA_PATH, SQL_VIEWS_PATH


INIT_SCHEMA_PATH = SQL_SCHEMA_PATH
INIT_VIEWS_PATH = SQL_VIEWS_PATH


def quote_identifier(identifier: str) -> str:
    # Database names cannot be bound as SQL parameters, so quote the identifier.
    return '"' + identifier.replace('"', '""') + '"'


def recreate_database(config: PostgresConfig) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(
        config.database_url(MAINTENANCE_DATABASE),
        isolation_level="AUTOCOMMIT",
    )
    db_name = quote_identifier(config.database)

    with engine.connect() as conn:
        conn.execute(
            text(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = :database
                  AND pid <> pg_backend_pid()
                """
            ),
            {"database": config.database},
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
        conn.execute(text(f"CREATE DATABASE {db_name}"))

    engine.dispose()


def read_sql_statements(path: Path) -> list[str]:
    raw_sql = path.read_text(encoding="utf-8")
    statements = []

    for statement in raw_sql.split(";"):
        stripped = statement.strip()
        if stripped:
            statements.append(stripped)

    if not statements:
        raise RuntimeError(f"No SQL statements found in {path}")
    return statements


def create_tables(config: PostgresConfig) -> None:
    from sqlalchemy import create_engine

    engine = create_engine(config.database_url())
    try:
        # Run the schema file in one transaction so partial table creation rolls back.
        with engine.begin() as conn:
            for statement in read_sql_statements(INIT_SCHEMA_PATH):
                conn.exec_driver_sql(statement)
    finally:
        engine.dispose()


def create_views(config: PostgresConfig) -> None:
    from sqlalchemy import create_engine

    engine = create_engine(config.database_url())
    try:
        with engine.begin() as conn:
            for statement in read_sql_statements(INIT_VIEWS_PATH):
                conn.exec_driver_sql(statement)
    finally:
        engine.dispose()


def reset_database(config: PostgresConfig | None = None) -> PostgresConfig:
    """Recreate the configured database, schema, and read-only views."""
    resolved_config = config or load_postgres_config()
    recreate_database(resolved_config)
    create_tables(resolved_config)
    create_views(resolved_config)
    return resolved_config


def print_reset_context(config: PostgresConfig) -> None:
    schema_statement_count = len(read_sql_statements(INIT_SCHEMA_PATH))
    view_statement_count = len(read_sql_statements(INIT_VIEWS_PATH))

    print(f"- Load connection settings from: {ENV_PATH}")
    print(f"- Recreate database: {config.database}")
    print(f"- Maintenance database: {MAINTENANCE_DATABASE}")
    print(f"- Create schema from: {INIT_SCHEMA_PATH}")
    print(f"- Schema statements: {schema_statement_count}")
    print(f"- Create views from: {INIT_VIEWS_PATH}")
    print(f"- View statements: {view_statement_count}")
