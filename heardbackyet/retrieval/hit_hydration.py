from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from heardbackyet.db.postgres_models import Email, JobDescription
from heardbackyet.retrieval.semantic_retriever import SemanticSearchHit


@dataclass(frozen=True)
class EmailSourceFacts:
    """Authoritative email fields loaded after semantic ranking."""

    email_id: int
    message_id: str
    received_at: datetime
    recipient: str
    sender: str
    subject: str | None
    body_text: str | None
    source_path: str | None
    email_type: str | None
    company_raw: str | None
    position_raw: str | None
    application_link_method: str | None
    application_id: int | None


@dataclass(frozen=True)
class JobDescriptionSourceFacts:
    """Authoritative JD fields loaded after semantic ranking."""

    jd_id: int
    captured_at: date | None
    company_raw: str | None
    position_raw: str | None
    location_raw: str | None
    salary_raw: str | None
    responsibilities: str | None
    qualifications: str | None
    nice_to_have: str | None
    source_url: str | None
    source_path: str | None
    application_id: int | None


HydratedSource = EmailSourceFacts | JobDescriptionSourceFacts


@dataclass(frozen=True)
class HydratedSearchHit(SemanticSearchHit):
    """Search hit enriched with its current authoritative source row."""

    source: HydratedSource


def hydrate_search_hits(
    session: Session,
    hits: Sequence[SemanticSearchHit],
) -> list[HydratedSearchHit]:
    """Batch-load source facts for ranked hits without changing their order."""
    email_ids = {
        hit.metadata.source_id
        for hit in hits
        if hit.metadata.source_type == "email"
    }
    jd_ids = {
        hit.metadata.source_id
        for hit in hits
        if hit.metadata.source_type == "job_description"
    }

    email_rows: dict[int, Email] = {}
    if email_ids:
        emails = session.scalars(
            select(Email).where(Email.email_id.in_(email_ids))
        ).all()
        email_rows = {email.email_id: email for email in emails}

    jd_rows: dict[int, JobDescription] = {}
    if jd_ids:
        job_descriptions = session.scalars(
            select(JobDescription).where(JobDescription.jd_id.in_(jd_ids))
        ).all()
        jd_rows = {jd.jd_id: jd for jd in job_descriptions}

    hydrated_hits: list[HydratedSearchHit] = []
    for hit in hits:
        source_type = hit.metadata.source_type
        source_id = hit.metadata.source_id
        if source_type == "email":
            email = email_rows.get(source_id)
            if email is None:
                raise LookupError(f"email source not found: {source_id}")
            source: HydratedSource = _email_facts(email)
        elif source_type == "job_description":
            jd = jd_rows.get(source_id)
            if jd is None:
                raise LookupError(f"job_description source not found: {source_id}")
            source = _job_description_facts(jd)
        else:
            raise ValueError(f"unsupported retrieval source_type: {source_type}")

        hydrated_hits.append(
            HydratedSearchHit(
                retrieval=hit.retrieval,
                metadata=hit.metadata,
                snapshot=hit.snapshot,
                source=source,
            )
        )
    return hydrated_hits


def _email_facts(email: Email) -> EmailSourceFacts:
    return EmailSourceFacts(
        email_id=email.email_id,
        message_id=email.message_id,
        received_at=email.received_at,
        recipient=email.recipient,
        sender=email.sender,
        subject=email.subject,
        body_text=email.body_text,
        source_path=email.source_path,
        email_type=email.email_type,
        company_raw=email.company_raw,
        position_raw=email.position_raw,
        application_link_method=email.application_link_method,
        application_id=email.application_id,
    )


def _job_description_facts(jd: JobDescription) -> JobDescriptionSourceFacts:
    return JobDescriptionSourceFacts(
        jd_id=jd.jd_id,
        captured_at=jd.captured_at,
        company_raw=jd.company_raw,
        position_raw=jd.position_raw,
        location_raw=jd.location_raw,
        salary_raw=jd.salary_raw,
        responsibilities=jd.responsibilities,
        qualifications=jd.qualifications,
        nice_to_have=jd.nice_to_have,
        source_url=jd.source_url,
        source_path=jd.source_path,
        application_id=jd.application_id,
    )
