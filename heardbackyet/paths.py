from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
SQL_SCHEMA_PATH = PROJECT_ROOT / "sql" / "init_schema.sql"
SQL_VIEWS_PATH = PROJECT_ROOT / "sql" / "init_views.sql"
ENV_PATH = PROJECT_ROOT / ".env"

STATIC_DIR = PACKAGE_ROOT / "static"
DATA_ROOT = PROJECT_ROOT / "data"

EML_IMPORT_DIR = DATA_ROOT / "eml"
EML_RENAMED_DIR = EML_IMPORT_DIR / "renamed"
EML_PARSED_DIR = EML_IMPORT_DIR / "parsed"

JD_DIR = DATA_ROOT / "jd"
JD_PARSED_DIR = JD_DIR / "parsed"

ENTITY_ALIASES_DIR = DATA_ROOT / "entity_aliases"
COMPANY_ALIASES_PATH = ENTITY_ALIASES_DIR / "company_aliases.csv"
POSITION_ALIASES_PATH = ENTITY_ALIASES_DIR / "position_aliases.csv"
