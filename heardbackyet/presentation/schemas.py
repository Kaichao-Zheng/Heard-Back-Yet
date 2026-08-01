"""Public HTTP request and response contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class UserQueryRequest(BaseModel):
    """Public input for one stateless application user query."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_query: str = Field(min_length=1, max_length=4000)


class UserQueryResponse(BaseModel):
    """Public response to one user query without internal plan details."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal[
        "resolved",
        "direct_answer",
        "needs_clarification",
        "requires_decomposition",
        "unsupported",
    ]
    reason_code: Literal[
        "ambiguous_reference",
        "missing_scope",
        "compound_query",
        "out_of_domain",
        "unsupported_capability",
        "restricted_request",
    ] | None
    answer: str
    sources: list[dict[str, Any]]


class ErrorResponse(BaseModel):
    """Non-sensitive public error envelope."""

    code: str
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
