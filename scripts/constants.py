from __future__ import annotations


CATEGORY_LABEL_UNKNOWN = "unknown"

# Labels that can represent an application progress stage.
APPLICATION_PROGRESS_LABELS = (
    "applied",
    "assessment",
    "interview",
    "offer",
    "rejection",
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
