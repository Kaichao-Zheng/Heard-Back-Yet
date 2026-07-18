from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from heardbackyet.db.config import load_postgres_config
from heardbackyet.db.postgres_loader import (
    LoadStats,
    PostgresLoader,
)


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
    print("- Load alias mappings")
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

    print("- Load job descriptions")
    print(
        f"loaded {stats.jd_records} records from parsed JD JSON;"
    )
    print(
        "table job_description inserted/updated "
        f"{stats.job_descriptions_inserted}/{stats.job_descriptions_updated};"
    )

    print("- Load emails")
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

    print("- Sync applications")
    print(f"table application created {stats.applications_created};")
    print(f"table application latest_status snapshot updated {stats.application_statuses_updated};")
    print(f"table application latest_jd_id snapshot pointer updated {stats.application_latest_jds_updated};")
    if dry_run:
        print("Dry run complete; transaction was rolled back.")
    else:
        print("PostgreSQL load committed successfully.")
