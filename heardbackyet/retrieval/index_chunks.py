from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from heardbackyet.constants import RETRIEVAL_EMAIL_LABELS
from heardbackyet.db.config import load_postgres_config
from heardbackyet.db.postgres_models import (
    Application,
    Company,
    Email,
    JobDescription,
    Position,
    RetrievalChunk,
)
from heardbackyet.retrieval.content_renderer import (
    render_email_content,
    render_jd_content,
)
from heardbackyet.retrieval.text_embedder import (
    OllamaTextEmbedder,
    load_embedding_config,
)


@dataclass(frozen=True)
class ChunkMetadata:
    source_type: str
    source_id: int
    application_id: int | None
    company_id: int | None
    position_id: int | None
    email_type: str | None
    semantic_fields: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalDocument:
    metadata: ChunkMetadata
    content: str
    embedding: list[float] | None = None


@dataclass(frozen=True)
class IndexStats:
    eligible_emails: int
    job_descriptions: int
    rendered_emails: int
    rendered_job_descriptions: int
    indexed_chunks: int


def collect_candidates(
    session: Session,
    limit: int | None = None,
    source: str | None = None,
) -> tuple[list[RetrievalDocument], IndexStats]:
    candidates: list[RetrievalDocument] = []
    eligible_emails = 0
    job_descriptions = 0

    if source in (None, "email"):
        email_query = (
            select(Email, Application, Company, Position)
            .select_from(Email)
            .outerjoin(Application, Email.application_id == Application.application_id)
            .outerjoin(Company, Application.company_id == Company.company_id)
            .outerjoin(Position, Application.position_id == Position.position_id)
            .where(Email.email_type.in_(RETRIEVAL_EMAIL_LABELS))
            .order_by(Email.email_id)
        )
        for email, application, company, position in session.execute(email_query):
            eligible_emails += 1
            rendered = render_email_content(
                email,
                company.company_name if company else None,
                position.position_name if position else None,
            )
            if rendered is not None:
                candidates.append(
                    RetrievalDocument(
                        metadata=ChunkMetadata(
                            source_type="email",
                            source_id=email.email_id,
                            application_id=email.application_id,
                            company_id=application.company_id if application else None,
                            position_id=application.position_id if application else None,
                            email_type=email.email_type,
                            semantic_fields=rendered.semantic_fields,
                        ),
                        content=rendered.content,
                    )
                )
                if limit is not None and len(candidates) >= limit:
                    break

    rendered_emails = len(candidates)
    if source in (None, "jd") and (limit is None or len(candidates) < limit):
        jd_query = (
            select(JobDescription, Application, Company, Position)
            .select_from(JobDescription)
            .outerjoin(
                Application,
                JobDescription.application_id == Application.application_id,
            )
            .outerjoin(Company, Application.company_id == Company.company_id)
            .outerjoin(Position, Application.position_id == Position.position_id)
            .order_by(JobDescription.jd_id)
        )
        for jd, application, company, position in session.execute(jd_query):
            job_descriptions += 1
            rendered = render_jd_content(
                jd,
                company.company_name if company else None,
                position.position_name if position else None,
            )
            if rendered is not None:
                candidates.append(
                    RetrievalDocument(
                        metadata=ChunkMetadata(
                            source_type="job_description",
                            source_id=jd.jd_id,
                            application_id=jd.application_id,
                            company_id=application.company_id if application else None,
                            position_id=application.position_id if application else None,
                            email_type=None,
                            semantic_fields=rendered.semantic_fields,
                        ),
                        content=rendered.content,
                    )
                )
                if limit is not None and len(candidates) >= limit:
                    break

    return candidates, IndexStats(
        eligible_emails=eligible_emails,
        job_descriptions=job_descriptions,
        rendered_emails=rendered_emails,
        rendered_job_descriptions=len(candidates) - rendered_emails,
        indexed_chunks=0,
    )


def rebuild_index(
    session: Session,
    limit: int | None = None,
    source: str | None = None,
) -> IndexStats:
    candidates, stats = collect_candidates(session, limit, source)
    embedder = OllamaTextEmbedder(load_embedding_config())
    embeddings = embedder.embed([candidate.content for candidate in candidates])
    if len(embeddings) != len(candidates):
        raise ValueError("Embedding count does not match rendered chunk count.")

    # Finish every provider call before replacing rows so failures can roll back
    # without leaving a partially rebuilt retrieval corpus.
    embedded_at = datetime.now(timezone.utc)
    documents = [
        replace(candidate, embedding=embedding)
        for candidate, embedding in zip(candidates, embeddings)
    ]

    session.execute(delete(RetrievalChunk))
    for document in documents:
        metadata = document.metadata
        session.add(
            RetrievalChunk(
                source_type=metadata.source_type,
                source_id=metadata.source_id,
                application_id=metadata.application_id,
                company_id=metadata.company_id,
                position_id=metadata.position_id,
                email_type=metadata.email_type,
                semantic_fields=list(metadata.semantic_fields),
                content=document.content,
                embedding=document.embedding,
                embedding_model=embedder.model_ref,
                embedded_at=embedded_at,
            )
        )
    session.flush()
    return IndexStats(
        eligible_emails=stats.eligible_emails,
        job_descriptions=stats.job_descriptions,
        rendered_emails=stats.rendered_emails,
        rendered_job_descriptions=stats.rendered_job_descriptions,
        indexed_chunks=len(candidates),
    )


def run(
    preview: bool,
    dry_run: bool,
    limit: int | None = None,
    source: str | None = None,
) -> tuple[IndexStats, list[RetrievalDocument]]:
    if (limit is not None or source is not None) and not (preview or dry_run):
        raise ValueError("--limit and source selection require --preview or --dry-run")
    engine = create_engine(load_postgres_config().database_url())
    session = Session(engine)
    try:
        if preview:
            candidates, stats = collect_candidates(session, limit, source)
            return stats, candidates
        stats = rebuild_index(session, limit, source)
        if dry_run:
            session.rollback()
        else:
            session.commit()
        return stats, []
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()
