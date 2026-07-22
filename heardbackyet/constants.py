from __future__ import annotations


EMBEDDING_DIMENSION = 1024
EMAIL_BODY_CHAR_LIMIT = 2000
JD_SEMANTIC_CHAR_LIMIT = 2000

RETRIEVAL_SOURCE_TYPES = (
    "email",
    "job_description",
)

APPLICATION_EVIDENCE_KINDS = (
    "latest_status_email",
    "linked_email",
    "linked_job_description",
)

# Labels that can represent an application progress stage.
APPLICATION_PROGRESS_LABELS = (
    "applied",
    "assessment",
    "interview",
    "offer",
    "rejection",
)

SUPPLEMENTARY_INFO_LABELS = (
    "logistics",
    "profile-update",
)

# Email categories admitted to the vector-backed semantic index by retrieval policy.
SEMANTIC_INDEX_EMAIL_LABELS = (
    APPLICATION_PROGRESS_LABELS
    + SUPPLEMENTARY_INFO_LABELS
)

CATEGORY_LABEL_UNKNOWN = "unknown"

ALLOWED_CATEGORY_LABELS = (
    "auth",
    "delivery-failure",
    "logistics",
    "profile-update",
    "unrelated",
    CATEGORY_LABEL_UNKNOWN,
) + APPLICATION_PROGRESS_LABELS

CATEGORY_EVIDENCE = {
    "subject_sender": "subject_sender",
    "body_excerpt": "body_excerpt",
}

ENTITY_EVIDENCE = {
    "subject": "subject",
    "body_text": "body_text",
}

APPLICATION_LINK_METHODS = (
    "exact",
    "company_singleton",
    "manual",
)
