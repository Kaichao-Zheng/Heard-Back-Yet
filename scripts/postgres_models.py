from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CompanyAlias(Base):
    __tablename__ = "company_alias"

    company_alias_id: Mapped[int] = mapped_column(primary_key=True)
    raw_name: Mapped[str] = mapped_column(unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.company_id"))
    company: Mapped[Company] = relationship()


class PositionAlias(Base):
    __tablename__ = "position_alias"

    position_alias_id: Mapped[int] = mapped_column(primary_key=True)
    raw_name: Mapped[str] = mapped_column(unique=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("position.position_id"))
    position: Mapped[Position] = relationship()


class Company(Base):
    __tablename__ = "company"

    company_id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(unique=True)


class Position(Base):
    __tablename__ = "position"

    position_id: Mapped[int] = mapped_column(primary_key=True)
    position_name: Mapped[str] = mapped_column(unique=True)


class Application(Base):
    __tablename__ = "application"

    application_id: Mapped[int] = mapped_column(primary_key=True)
    latest_status: Mapped[str | None]
    latest_status_received_at: Mapped[datetime | None]
    latest_status_email_id: Mapped[int | None]
    company_id: Mapped[int] = mapped_column(ForeignKey("company.company_id"))
    position_id: Mapped[int] = mapped_column(ForeignKey("position.position_id"))


class Email(Base):
    __tablename__ = "email"

    email_id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(unique=True)
    received_at: Mapped[datetime]
    recipient: Mapped[str]
    sender: Mapped[str]
    subject: Mapped[str | None]
    body_text: Mapped[str | None]
    source_path: Mapped[str | None]
    email_type: Mapped[str | None]
    company_raw: Mapped[str | None]
    position_raw: Mapped[str | None]
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("application.application_id")
    )


class JobDescription(Base):
    __tablename__ = "job_description"

    jd_id: Mapped[int] = mapped_column(primary_key=True)
    company_raw: Mapped[str | None]
    position_raw: Mapped[str | None]
    location_raw: Mapped[str | None]
    salary_raw: Mapped[str | None]
    responsibilities: Mapped[str | None]
    qualifications: Mapped[str | None]
    nice_to_have: Mapped[str | None]
    source_url: Mapped[str | None]
    source_path: Mapped[str | None]
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("application.application_id")
    )
