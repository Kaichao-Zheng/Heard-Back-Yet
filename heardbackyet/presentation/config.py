from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from heardbackyet.paths import ENV_PATH


def load_api_allowed_frontend_origins(
    env_path: Path = ENV_PATH,
) -> tuple[str, ...]:
    """Load exact frontend origins allowed to call the browser API."""
    load_dotenv(env_path)
    raw_value = os.getenv("API_ALLOWED_FRONTEND_ORIGINS", "")
    origins = tuple(
        origin.strip().rstrip("/")
        for origin in raw_value.split(",")
        if origin.strip()
    )
    for origin in origins:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                "API_ALLOWED_FRONTEND_ORIGINS entries must be absolute "
                "HTTP(S) origins."
            )
        if parsed.path or parsed.query or parsed.fragment:
            raise ValueError(
                "API_ALLOWED_FRONTEND_ORIGINS entries must not contain a path, "
                "query, or fragment."
            )
    return origins
