"""Fast dependency checks used before starting an interactive query."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

LOGGER = logging.getLogger(__name__)


class DependencyReadinessChecker:
    """Check that the PostgreSQL dependency supplied by Docker is reachable."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def first_unavailable_dependency(self) -> str | None:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as error:
            LOGGER.warning("readiness check failed for database: %s", error)
            return "database"
        return None
