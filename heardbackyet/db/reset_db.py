from __future__ import annotations

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from heardbackyet.db.config import (
    MAINTENANCE_DATABASE,
    PostgresConfig,
    load_postgres_config,
)
from heardbackyet.paths import ALEMBIC_CONFIG_PATH, ENV_PATH


MIGRATION_TARGET = "head"


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


def build_alembic_config(config: PostgresConfig) -> Config:
    """Build Alembic configuration for the explicitly selected database."""
    alembic_config = Config(str(ALEMBIC_CONFIG_PATH))
    alembic_config.attributes["database_url"] = config.database_url().render_as_string(
        hide_password=False
    )
    return alembic_config


def migration_head(config: PostgresConfig) -> str:
    """Return the single migration head, failing before a destructive reset."""
    script = ScriptDirectory.from_config(build_alembic_config(config))
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected exactly one Alembic head; found: {heads}")
    return heads[0]


def upgrade_schema(config: PostgresConfig) -> None:
    """Upgrade the configured database to the latest schema revision."""
    migration_head(config)
    command.upgrade(build_alembic_config(config), MIGRATION_TARGET)


def reset_database(config: PostgresConfig | None = None) -> PostgresConfig:
    """Recreate the configured database and upgrade its schema to Alembic head."""
    resolved_config = config or load_postgres_config()
    recreate_database(resolved_config)
    upgrade_schema(resolved_config)
    return resolved_config


def print_reset_context(config: PostgresConfig) -> None:
    head = migration_head(config)

    print(f"- Load connection settings from: {ENV_PATH}")
    print(f"- Recreate database: {config.database}")
    print(f"- Maintenance database: {MAINTENANCE_DATABASE}")
    print(f"- Alembic config: {ALEMBIC_CONFIG_PATH}")
    print(f"- Upgrade schema to: {MIGRATION_TARGET} ({head})")
