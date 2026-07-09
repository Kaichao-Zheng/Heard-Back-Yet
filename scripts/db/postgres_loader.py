from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from constants import (
    APPLICATION_PROGRESS_LABELS,
    ALLOWED_CATEGORY_LABELS
)
from paths import (
    COMPANY_ALIASES_PATH,
    EML_PARSED_DIR,
    JD_PARSED_DIR,
    POSITION_ALIASES_PATH,
)
from db.postgres_models import (
    CompanyAlias,
    Company,
    PositionAlias,
    Position,
    Application,
    Email,
    JobDescription,
)


@dataclass
class LoadStats:
    company_alias_rows_loaded: int = 0
    company_alias_rows_skipped: int = 0
    position_alias_rows_loaded: int = 0
    position_alias_rows_skipped: int = 0
    eml_records: int = 0
    jd_records: int = 0
    companies_created: int = 0
    positions_created: int = 0
    company_aliases_created: int = 0
    company_aliases_updated: int = 0
    position_aliases_created: int = 0
    position_aliases_updated: int = 0
    applications_created: int = 0
    application_statuses_updated: int = 0
    email_exact_links: int = 0
    email_company_singleton_links: int = 0
    emails_inserted: int = 0
    emails_updated: int = 0
    job_descriptions_inserted: int = 0
    job_descriptions_updated: int = 0


@dataclass(frozen=True)
class AliasResolution:
    entity: Company | Position
    alias_created: bool
    alias_updated: bool
    entity_created: bool


class PostgresLoader:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.stats = LoadStats()
        self.company_cache: dict[str, Company] = {}
        self.position_cache: dict[str, Position] = {}
        self.company_alias_cache: dict[str, CompanyAlias] = {}
        self.position_alias_cache: dict[str, PositionAlias] = {}
        self.application_cache: dict[tuple[int, int], Application] = {}
        self.touched_email_application_ids: set[int] = set()

    def load(self) -> LoadStats:
        self.load_alias_csv()
        self.load_jd_json()
        self.load_email_json()
        self.refresh_latest_statuses()
        return self.stats

    def load_alias_csv(self) -> None:
        for row in read_alias_rows(COMPANY_ALIASES_PATH):
            raw = clean_text(row.get("raw"))
            canonical = clean_text(row.get("normalized"))
            if raw is None or canonical is None:
                self.stats.company_alias_rows_skipped += 1
                continue
            result = self.ensure_company_alias(raw, canonical)
            self.record_company_alias_result(result)
            self.stats.company_alias_rows_loaded += 1

        for row in read_alias_rows(POSITION_ALIASES_PATH):
            raw = clean_text(row.get("raw"))
            canonical = clean_text(row.get("normalized"))
            if raw is None or canonical is None:
                self.stats.position_alias_rows_skipped += 1
                continue
            result = self.ensure_position_alias(raw, canonical)
            self.record_position_alias_result(result)
            self.stats.position_alias_rows_loaded += 1

    def load_email_json(self) -> None:
        records = [load_json(path) for path in iter_json_files(EML_PARSED_DIR)]
        records.sort(key=email_sort_key)

        for record in records:
            self.stats.eml_records += 1
            company_raw = selected_entity_raw(record, "company")
            position_raw = selected_entity_raw(record, "position")
            company = self.company_for_raw(company_raw)
            position = self.position_for_raw(position_raw)
            email_type = category_label(record)
            application, application_link_method = self.application_for_email(
                company,
                position,
                email_type,
            )

            values = {
                "message_id": required_text(record.get("message_id"), "message_id"),
                "received_at": parse_datetime(
                    required_text(record.get("received_at"), "received_at")
                ),
                "recipient": required_text(record.get("recipient"), "recipient"),
                "sender": required_text(record.get("sender"), "sender"),
                "subject": clean_text(record.get("subject")),
                "body_text": clean_text(record.get("body_text")),
                "source_path": clean_text(record.get("source_path")),
                "email_type": email_type,
                "company_raw": company_raw,
                "position_raw": position_raw,
                "application_link_method": application_link_method,
                "application_id": application.application_id if application else None,
            }
            existing = self.scalar(
                select(Email).where(Email.message_id == values["message_id"])
            )
            if existing is None:
                self.session.add(Email(**values))
                self.stats.emails_inserted += 1
            else:
                if existing.application_id is not None:
                    self.touched_email_application_ids.add(existing.application_id)
                for key, value in values.items():
                    setattr(existing, key, value)
                self.stats.emails_updated += 1
            if values["application_id"] is not None:
                self.touched_email_application_ids.add(values["application_id"])
                if application_link_method == "exact":
                    self.stats.email_exact_links += 1
                elif application_link_method == "company_singleton":
                    self.stats.email_company_singleton_links += 1

    def load_jd_json(self) -> None:
        for path in iter_json_files(JD_PARSED_DIR):
            record = load_json(path)
            self.stats.jd_records += 1
            company_raw = clean_text(record.get("Company"))
            position_raw = clean_text(record.get("Position"))
            company = self.company_for_raw(company_raw)
            position = self.position_for_raw(position_raw)
            application = self.application_for(company, position)

            values = {
                "captured_at": parse_date(clean_text(record.get("Captured At"))),
                "company_raw": company_raw,
                "position_raw": position_raw,
                "location_raw": clean_text(record.get("Location")),
                "salary_raw": clean_text(record.get("Salary")),
                "responsibilities": clean_text(record.get("Responsibilities")),
                "qualifications": clean_text(record.get("Qualifications")),
                "nice_to_have": clean_text(record.get("Nice to Have")),
                "source_url": clean_text(record.get("Source URL")),
                "source_path": clean_text(record.get("source_path")),
                "application_id": application.application_id if application else None,
            }
            existing = None
            if values["source_path"] is not None:
                existing = self.scalar(
                    select(JobDescription).where(
                        JobDescription.source_path == values["source_path"]
                    )
                )
            if existing is None:
                self.session.add(JobDescription(**values))
                self.stats.job_descriptions_inserted += 1
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
                self.stats.job_descriptions_updated += 1

    def company_for_raw(self, raw: str | None) -> Company | None:
        if raw is None:
            return None
        alias = self.company_alias_cache.get(raw)
        if alias is None:
            alias = self.scalar(select(CompanyAlias).where(CompanyAlias.raw_name == raw))
            if alias is not None:
                self.company_alias_cache[raw] = alias
        return alias.company if alias is not None else None

    def position_for_raw(self, raw: str | None) -> Position | None:
        if raw is None:
            return None
        alias = self.position_alias_cache.get(raw)
        if alias is None:
            alias = self.scalar(
                select(PositionAlias).where(PositionAlias.raw_name == raw)
            )
            if alias is not None:
                self.position_alias_cache[raw] = alias
        return alias.position if alias is not None else None

    def ensure_company_alias(self, raw_name: str, company_name: str) -> AliasResolution:
        alias = self.company_alias_cache.get(raw_name)
        if alias is None:
            alias = self.scalar(select(CompanyAlias).where(CompanyAlias.raw_name == raw_name))
            if alias is not None:
                self.company_alias_cache[raw_name] = alias
        if alias is not None:
            company, company_created = self.ensure_company(company_name)
            if alias.company_id != company.company_id:
                alias.company = company
                self.session.flush()
                return AliasResolution(company, False, True, company_created)
            return AliasResolution(alias.company, False, False, company_created)

        company, company_created = self.ensure_company(company_name)
        alias = CompanyAlias(raw_name=raw_name, company=company)
        self.session.add(alias)
        self.session.flush()
        self.company_alias_cache[raw_name] = alias
        return AliasResolution(company, True, False, company_created)

    def ensure_position_alias(self, raw_name: str, position_name: str) -> AliasResolution:
        alias = self.position_alias_cache.get(raw_name)
        if alias is None:
            alias = self.scalar(
                select(PositionAlias).where(PositionAlias.raw_name == raw_name)
            )
            if alias is not None:
                self.position_alias_cache[raw_name] = alias
        if alias is not None:
            position, position_created = self.ensure_position(position_name)
            if alias.position_id != position.position_id:
                alias.position = position
                self.session.flush()
                return AliasResolution(position, False, True, position_created)
            return AliasResolution(alias.position, False, False, position_created)

        position, position_created = self.ensure_position(position_name)
        alias = PositionAlias(raw_name=raw_name, position=position)
        self.session.add(alias)
        self.session.flush()
        self.position_alias_cache[raw_name] = alias
        return AliasResolution(position, True, False, position_created)

    def ensure_company(self, company_name: str) -> tuple[Company, bool]:
        company = self.company_cache.get(company_name)
        if company is not None:
            return company, False

        company = self.scalar(select(Company).where(Company.company_name == company_name))
        if company is not None:
            self.company_cache[company_name] = company
            return company, False

        company = Company(company_name=company_name)
        self.session.add(company)
        self.session.flush()
        self.company_cache[company_name] = company
        return company, True

    def ensure_position(self, position_name: str) -> tuple[Position, bool]:
        position = self.position_cache.get(position_name)
        if position is not None:
            return position, False

        position = self.scalar(
            select(Position).where(Position.position_name == position_name)
        )
        if position is not None:
            self.position_cache[position_name] = position
            return position, False

        position = Position(position_name=position_name)
        self.session.add(position)
        self.session.flush()
        self.position_cache[position_name] = position
        return position, True

    def application_for(
        self,
        company: Company | None,
        position: Position | None,
    ) -> Application | None:
        if company is None or position is None:
            return None

        key = (company.company_id, position.position_id)
        application = self.application_cache.get(key)
        if application is None:
            application = self.scalar(
                select(Application).where(
                    Application.company_id == company.company_id,
                    Application.position_id == position.position_id,
                )
            )
            if application is None:
                application = Application(
                    company_id=company.company_id,
                    position_id=position.position_id,
                    latest_status=None,
                    latest_status_received_at=None,
                    latest_status_email_id=None,
                )
                self.session.add(application)
                self.session.flush()
                self.stats.applications_created += 1
            self.application_cache[key] = application

        return application

    def application_for_email(
        self,
        company: Company | None,
        position: Position | None,
        email_type: str | None,
    ) -> tuple[Application | None, str | None]:
        if company is None:
            return None, None
        if position is not None:
            return (
                self.application_for(company, position),
                "exact",
            )
        if email_type not in APPLICATION_PROGRESS_LABELS:
            return None, None

        application = self.singleton_application_for_company(company)
        if application is None:
            return None, None
        return application, "company_singleton"

    def singleton_application_for_company(self, company: Company) -> Application | None:
        self.session.flush()
        applications = list(
            self.session.execute(
                select(Application)
                .where(Application.company_id == company.company_id)
                .order_by(Application.application_id)
                .limit(2)
            ).scalars()
        )
        if len(applications) != 1:
            return None

        application = applications[0]
        key = (application.company_id, application.position_id)
        self.application_cache[key] = application
        return application

    def refresh_latest_statuses(self) -> None:
        self.session.flush()
        for application_id in sorted(self.touched_email_application_ids):
            application = self.session.get(Application, application_id)
            if application is None:
                continue

            latest_email = self.scalar(
                select(Email)
                .where(
                    Email.application_id == application_id,
                    Email.email_type.in_(APPLICATION_PROGRESS_LABELS),
                )
                .order_by(Email.received_at.desc(), Email.email_id.desc())
                .limit(1)
            )
            latest_status = latest_email.email_type if latest_email else None
            latest_status_received_at = latest_email.received_at if latest_email else None
            latest_status_email_id = latest_email.email_id if latest_email else None

            if (
                application.latest_status != latest_status
                or application.latest_status_received_at != latest_status_received_at
                or application.latest_status_email_id != latest_status_email_id
            ):
                application.latest_status = latest_status
                application.latest_status_received_at = latest_status_received_at
                application.latest_status_email_id = latest_status_email_id
                self.stats.application_statuses_updated += 1

    def record_company_alias_result(self, result: AliasResolution) -> None:
        if result.entity_created:
            self.stats.companies_created += 1
        if result.alias_created:
            self.stats.company_aliases_created += 1
        if result.alias_updated:
            self.stats.company_aliases_updated += 1

    def record_position_alias_result(self, result: AliasResolution) -> None:
        if result.entity_created:
            self.stats.positions_created += 1
        if result.alias_created:
            self.stats.position_aliases_created += 1
        if result.alias_updated:
            self.stats.position_aliases_updated += 1

    def scalar(self, statement: Select[Any]) -> Any:
        return self.session.execute(statement).scalar_one_or_none()


def iter_json_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(path.glob("*.json"), key=lambda item: item.name.lower())


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"Top-level JSON value must be an object: {path}")
    return value


def read_alias_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


def clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def required_text(value: Any, field_name: str) -> str:
    text = clean_text(value)
    if text is None:
        raise ValueError(f"Missing required field: {field_name}")
    return text


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def selected_entity_raw(record: dict[str, Any], entity_name: str) -> str | None:
    entity = record.get(entity_name)
    if not isinstance(entity, dict):
        return None
    selected = entity.get("selected")
    if not isinstance(selected, dict):
        return None
    return clean_text(selected.get("raw"))


def category_label(record: dict[str, Any]) -> str | None:
    category = record.get("category")
    if not isinstance(category, dict):
        return None
    label = clean_text(category.get("label"))
    if label is None:
        return None
    if label not in ALLOWED_CATEGORY_LABELS:
        raise ValueError(f"Invalid email category label: {label}")
    return label


def email_sort_key(record: dict[str, Any]) -> tuple[datetime, str]:
    received_at = clean_text(record.get("received_at"))
    message_id = clean_text(record.get("message_id")) or ""
    if received_at is None:
        return datetime.min, message_id
    return parse_datetime(received_at), message_id
