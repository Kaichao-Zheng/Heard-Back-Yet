from __future__ import annotations

import argparse
import sys
from pathlib import Path

from db_config import (
    ENV_PATH,
    MAINTENANCE_DATABASE,
    PROJECT_ROOT,
    PostgresConfig,
    load_postgres_config,
)


INIT_SCHEMA_PATH = PROJECT_ROOT / "sql" / "init_schema.sql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drop and recreate the local PostgreSQL database, then initialize schema."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read configuration and schema without connecting to PostgreSQL.",
    )
    return parser.parse_args()


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


def print_reset_context(config: PostgresConfig) -> None:
    schema_statement_count = len(read_sql_statements(INIT_SCHEMA_PATH))

    print(f"- Load connection settings from: {ENV_PATH}")
    print(f"- Recreate database: {config.database}")
    print(f"- Maintenance database: {MAINTENANCE_DATABASE}")
    print(f"- Create schema from: {INIT_SCHEMA_PATH}")
    print(f"- Schema statements: {schema_statement_count}")


def main() -> int:
    args = parse_args()

    try:
        config = load_postgres_config()
        print_reset_context(config)
        if args.dry_run:
            print("Dry run complete; database was not changed.")
            return 0

        recreate_database(config)
        create_tables(config)
    except Exception as exc:
        print(f"reset_db failed: {exc}", file=sys.stderr)
        return 1

    print(f"Database {config.database!r} reset successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
