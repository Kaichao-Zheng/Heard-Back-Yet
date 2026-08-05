"""Build static assets with public browser configuration."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from heardbackyet.paths import ENV_PATH, PROJECT_ROOT, STATIC_DIR


def normalize_api_base_url(raw_value: str) -> str:
    value = raw_value.strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("FRONTEND_API_BASE_URL must be an absolute HTTP(S) URL.")
    if parsed.query or parsed.fragment:
        raise ValueError("FRONTEND_API_BASE_URL must not contain a query or fragment.")
    return value


def build_frontend(*, output_dir: Path, env_path: Path = ENV_PATH) -> Path:
    load_dotenv(env_path, override=False)
    api_base_url = normalize_api_base_url(
        os.getenv("FRONTEND_API_BASE_URL", "")
    )

    resolved_output = output_dir.resolve()
    if resolved_output == STATIC_DIR.resolve():
        raise ValueError("output_dir must not overwrite the source static directory.")

    static_output = resolved_output / "static"
    static_output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STATIC_DIR / "index.html", resolved_output / "index.html")
    for filename in ("app.js", "styles.css"):
        shutil.copy2(STATIC_DIR / filename, static_output / filename)

    config = {"apiBaseUrl": api_base_url}
    config_javascript = (
        "window.__HEARDBACKYET_CONFIG__ = Object.freeze("
        f"{json.dumps(config, ensure_ascii=False)});\n"
    )
    (static_output / "config.js").write_text(config_javascript, encoding="utf-8")
    return resolved_output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the static frontend.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "dist",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ENV_PATH,
    )
    args = parser.parse_args()
    output_dir = build_frontend(
        output_dir=args.output_dir,
        env_path=args.env_file,
    )
    print(f"Frontend build created: {output_dir}")


if __name__ == "__main__":
    main()
