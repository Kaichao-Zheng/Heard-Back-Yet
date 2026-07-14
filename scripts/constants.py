from __future__ import annotations


EMBEDDING_DIMENSION = 1024
EMAIL_BODY_CHAR_LIMIT = 2000
JD_SEMANTIC_CHAR_LIMIT = 2000

CATEGORY_LABEL_UNKNOWN = "unknown"

# Labels that can represent an application progress stage.
APPLICATION_PROGRESS_LABELS = (
    "applied",
    "assessment",
    "interview",
    "offer",
    "rejection",
)

RETRIEVAL_EMAIL_LABELS = APPLICATION_PROGRESS_LABELS + (
    "logistics",
    "profile-update",
)

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
