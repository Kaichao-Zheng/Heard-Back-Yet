from __future__ import annotations

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from heardbackyet.constants import EMBEDDING_DIMENSION


class Base(DeclarativeBase):
    pass


class CompanyAlias(Base):
    __tablename__ = "company_alias"

    company_alias_id: Mapped[int] = mapped_column(
        Identity(always=True), primary_key=True
    )
    raw_name: Mapped[str] = mapped_column(Text, unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.company_id"))
    company: Mapped[Company] = relationship()


class PositionAlias(Base):
    __tablename__ = "position_alias"

    position_alias_id: Mapped[int] = mapped_column(
        Identity(always=True), primary_key=True
    )
    raw_name: Mapped[str] = mapped_column(Text, unique=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("position.position_id"))
    position: Mapped[Position] = relationship()


class Company(Base):
    __tablename__ = "company"

    company_id: Mapped[int] = mapped_column(
        Identity(always=True), primary_key=True
    )
    company_name: Mapped[str] = mapped_column(Text, unique=True)


class Position(Base):
    __tablename__ = "position"

    position_id: Mapped[int] = mapped_column(
        Identity(always=True), primary_key=True
    )
    position_name: Mapped[str] = mapped_column(Text, unique=True)


class Application(Base):
    __tablename__ = "application"
    __table_args__ = (
        CheckConstraint(
            "latest_status IS NULL OR latest_status IN "
            "('applied', 'assessment', 'interview', 'offer', 'rejection')",
            name="application_latest_status_check",
        ),
        UniqueConstraint(
            "company_id",
            "position_id",
            name="application_company_id_position_id_key",
        ),
    )

    application_id: Mapped[int] = mapped_column(
        Identity(always=True), primary_key=True
    )
    latest_status: Mapped[str | None] = mapped_column(Text)
    latest_status_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    latest_status_email_id: Mapped[int | None]
    latest_jd_id: Mapped[int | None]
    company_id: Mapped[int] = mapped_column(ForeignKey("company.company_id"))
    position_id: Mapped[int] = mapped_column(ForeignKey("position.position_id"))


class Email(Base):
    __tablename__ = "email"
    __table_args__ = (
        CheckConstraint(
            "email_type IS NULL OR email_type IN "
            "('auth', 'delivery-failure', 'logistics', 'unrelated', 'unknown', "
            "'applied', 'profile-update', 'assessment', 'interview', 'offer', "
            "'rejection')",
            name="email_email_type_check",
        ),
        CheckConstraint(
            "application_link_method IS NULL OR application_link_method IN "
            "('exact', 'company_singleton', 'manual')",
            name="email_application_link_method_check",
        ),
    )

    email_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    message_id: Mapped[str] = mapped_column(Text, unique=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recipient: Mapped[str] = mapped_column(Text)
    sender: Mapped[str] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(Text)
    email_type: Mapped[str | None] = mapped_column(Text)
    company_raw: Mapped[str | None] = mapped_column(Text)
    position_raw: Mapped[str | None] = mapped_column(Text)
    application_link_method: Mapped[str | None] = mapped_column(Text)
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("application.application_id")
    )


class JobDescription(Base):
    __tablename__ = "job_description"

    jd_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    captured_at: Mapped[date | None]
    company_raw: Mapped[str | None] = mapped_column(Text)
    position_raw: Mapped[str | None] = mapped_column(Text)
    location_raw: Mapped[str | None] = mapped_column(Text)
    salary_raw: Mapped[str | None] = mapped_column(Text)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    qualifications: Mapped[str | None] = mapped_column(Text)
    nice_to_have: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(Text)
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("application.application_id")
    )


class RetrievalChunk(Base):
    __tablename__ = "retrieval_chunk"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('email', 'job_description')",
            name="retrieval_chunk_source_type_check",
        ),
        CheckConstraint(
            "(source_type = 'email' AND email_type IN "
            "('applied', 'assessment', 'interview', 'offer', 'rejection', "
            "'logistics', 'profile-update')) OR "
            "(source_type = 'job_description' AND email_type IS NULL)",
            name="retrieval_chunk_check",
        ),
        UniqueConstraint(
            "source_type",
            "source_id",
            name="retrieval_chunk_source_type_source_id_key",
        ),
    )

    chunk_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    source_type: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int]
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("application.application_id")
    )
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.company_id"))
    position_id: Mapped[int | None] = mapped_column(
        ForeignKey("position.position_id")
    )
    email_type: Mapped[str | None] = mapped_column(Text)
    semantic_fields: Mapped[list[str]] = mapped_column(ARRAY(Text))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION))
    embedding_model: Mapped[str] = mapped_column(Text)
    embedded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
