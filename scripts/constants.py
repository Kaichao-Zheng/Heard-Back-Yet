from __future__ import annotations


CATEGORY_LABEL_UNKNOWN = "unknown"

ALLOWED_CATEGORY_LABELS = (
    "applied",
    "assessment",
    "auth",
    "delivery-failure",
    "interview",
    "logistics",
    "offer",
    "profile-update",
    "rejection",
    "unrelated",
    CATEGORY_LABEL_UNKNOWN,
)

CATEGORY_EVIDENCE = {
    "subject_sender": "subject_sender",
    "body_excerpt": "body_excerpt",
}

ENTITY_EVIDENCE = {
    "sender": "sender",
    "subject": "subject",
    "body_text": "body_text",
}
