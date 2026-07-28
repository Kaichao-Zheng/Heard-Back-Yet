from __future__ import annotations

from dataclasses import dataclass

from heardbackyet.constants import (
    EMAIL_BODY_CHAR_LIMIT,
    JD_SEMANTIC_CHAR_LIMIT,
    SEMANTIC_INDEX_EMAIL_LABELS,
)
from heardbackyet.db.postgres_models import Email, JobDescription

TRUNCATION_MARKER = "[TRUNCATED]"
MISSING_SENTINELS = frozenset(
    {"-", "—", "n/a", "na", "none", "not applicable", "not available", "null"}
)


@dataclass(frozen=True)
class RenderedContent:
    content: str
    semantic_fields: tuple[str, ...]


def render_email_content(
    email: Email,
    canonical_company: str | None = None,
    canonical_position: str | None = None,
) -> RenderedContent | None:
    if email.email_type not in SEMANTIC_INDEX_EMAIL_LABELS:
        return None

    lines = _identity_lines(
        canonical_company,
        canonical_position,
        email.company_raw,
        email.position_raw,
    )
    semantic_fields: list[str] = []

    subject = _clean_structured_text(email.subject)
    if subject is not None:
        lines.append(f"Subject: {subject}")
        semantic_fields.append("subject")

    body = _clean_free_text(email.body_text)
    if body is not None:
        if len(body) > EMAIL_BODY_CHAR_LIMIT:
            body = body[:EMAIL_BODY_CHAR_LIMIT] + TRUNCATION_MARKER
        lines.append(f"Body:\n{body}")
        semantic_fields.append("body_text")

    if not lines:
        return None
    return RenderedContent("\n".join(lines), tuple(semantic_fields))


def render_jd_content(
    jd: JobDescription,
    canonical_company: str | None = None,
    canonical_position: str | None = None,
) -> RenderedContent | None:
    fields = (
        ("location", "Location", _clean_structured_text(jd.location_raw)),
        ("salary", "Salary", _clean_structured_text(jd.salary_raw)),
        (
            "responsibilities",
            "Responsibilities",
            _clean_structured_text(jd.responsibilities),
        ),
        (
            "qualifications",
            "Qualifications",
            _clean_structured_text(jd.qualifications),
        ),
        (
            "nice_to_have",
            "Nice to have",
            _clean_structured_text(jd.nice_to_have),
        ),
    )
    if not any(value is not None for _, _, value in fields):
        return None

    lines = _identity_lines(
        canonical_company,
        canonical_position,
        jd.company_raw,
        jd.position_raw,
    )
    semantic_fields: list[str] = []
    remaining = JD_SEMANTIC_CHAR_LIMIT
    for field_name, label, value in fields:
        if value is None or remaining <= 0:
            continue
        rendered_value = _truncate_within_budget(value, remaining)
        lines.append(f"{label}: {rendered_value}")
        semantic_fields.append(field_name)
        remaining -= len(rendered_value)

    return RenderedContent("\n".join(lines), tuple(semantic_fields))


def _identity_lines(
    canonical_company: str | None,
    canonical_position: str | None,
    extracted_company: str | None,
    extracted_position: str | None,
) -> list[str]:
    canonical_company = _clean_structured_text(canonical_company)
    canonical_position = _clean_structured_text(canonical_position)
    extracted_company = _clean_structured_text(extracted_company)
    extracted_position = _clean_structured_text(extracted_position)
    lines: list[str] = []

    if canonical_company is not None:
        lines.append(f"Company: {canonical_company}")
    if canonical_position is not None:
        lines.append(f"Position: {canonical_position}")
    if extracted_company is not None and extracted_company != canonical_company:
        lines.append(f"Company alias: {extracted_company}")
    if extracted_position is not None and extracted_position != canonical_position:
        lines.append(f"Position alias: {extracted_position}")
    return lines


def _clean_structured_text(value: str | None) -> str | None:
    text = _clean_free_text(value)
    if text is None or text.casefold() in MISSING_SENTINELS:
        return None
    return text


def _clean_free_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _truncate_within_budget(value: str, budget: int) -> str:
    if len(value) <= budget:
        return value
    if budget <= len(TRUNCATION_MARKER):
        return value[:budget]
    return value[: budget - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER
