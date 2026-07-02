from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

from paths import ENV_PATH

MAINTENANCE_DATABASE = "postgres"
POSTGRES_DRIVER = "postgresql+psycopg"


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    database: str
    user: str
    password: str | None

    def database_url(self, database: str | None = None) -> URL:
        return URL.create(
            drivername=POSTGRES_DRIVER,
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=database or self.database,
        )


def load_postgres_config(env_path: Path = ENV_PATH) -> PostgresConfig:
    load_dotenv(env_path)

    host = _required_env("POSTGRES_HOST")
    user = _required_env("POSTGRES_USER")
    database = _required_env("POSTGRES_DB")
    port_raw = _required_env("POSTGRES_PORT")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError("POSTGRES_PORT must be an integer.") from exc

    return PostgresConfig(
        host=host,
        port=port,
        database=database,
        user=user,
        password=_optional_env("POSTGRES_PASSWORD"),
    )


def _required_env(name: str) -> str:
    value = _optional_env(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip()
