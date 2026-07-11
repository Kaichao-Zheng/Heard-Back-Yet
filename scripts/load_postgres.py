from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.config import load_postgres_config
from db.postgres_loader import (
    LoadStats,
    PostgresLoader,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load parsed EML, parsed JD, and alias mapping data into PostgreSQL."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load all sources in one transaction, then roll back instead of committing.",
    )
    return parser.parse_args()


def run_load(dry_run: bool) -> LoadStats:
    config = load_postgres_config()
    engine = create_engine(config.database_url())
    session = Session(engine)
    try:
        loader = PostgresLoader(session)
        stats = loader.load()
        if dry_run:
            session.rollback()
        else:
            session.commit()
        return stats
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def print_summary(stats: LoadStats, dry_run: bool) -> None:
    print("== load_alias_mappings ==")
    print(
        "loaded/skipped "
        f"{stats.company_alias_rows_loaded}/{stats.company_alias_rows_skipped} "
        "records from company_aliases.csv;"
    )
    print(
        "loaded/skipped "
        f"{stats.position_alias_rows_loaded}/{stats.position_alias_rows_skipped} "
        "records from position_aliases.csv;"
    )
    print(f"table company_alias created/updated {stats.company_aliases_created}/{stats.company_aliases_updated};")
    print(f"table company created {stats.companies_created};")
    print(f"table position_alias created/updated {stats.position_aliases_created}/{stats.position_aliases_updated};")
    print(f"table position created {stats.positions_created};")

    print("== load_job_descriptions ==")
    print(
        f"loaded {stats.jd_records} records from parsed JD JSON;"
    )
    print(
        "table job_description inserted/updated "
        f"{stats.job_descriptions_inserted}/{stats.job_descriptions_updated};"
    )

    print("== load_emails ==")
    print(
        f"loaded {stats.eml_records} records from parsed EML JSON;"
    )
    print(
        "table email inserted/updated "
        f"{stats.emails_inserted}/{stats.emails_updated};"
    )
    print(f"table email exact links {stats.email_exact_links};")
    print(
        "table email company_singleton links "
        f"{stats.email_company_singleton_links};"
    )

    print("== sync_applications ==")
    print(f"table application created {stats.applications_created};")
    print(f"table application latest_status snapshot updated {stats.application_statuses_updated};")
    print(f"table application latest_jd_id snapshot pointer updated {stats.application_latest_jds_updated};")
    if dry_run:
        print("Dry run complete; transaction was rolled back.")
    else:
        print("PostgreSQL load committed successfully.")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    try:
        stats = run_load(args.dry_run)
        print_summary(stats, args.dry_run)
    except Exception as exc:
        print(f"load_postgres failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
