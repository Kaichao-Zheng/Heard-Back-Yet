"""Deterministic Canonical Response rendering for Weixin text messages."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse


def _is_public_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.hostname.lower() == "localhost":
        return False
    try:
        return ipaddress.ip_address(parsed.hostname).is_global
    except ValueError:
        return True


def _source_lines(sources: object) -> list[str]:
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
        return []

    lines: list[str] = []
    seen_urls: set[str] = set()
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        url = source.get("source_url") or source.get("jd_source_url")
        if not isinstance(url, str) or not _is_public_http_url(url):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = (
            source.get("title")
            or source.get("source_name")
            or source.get("company_name")
            or f"来源 {len(lines) + 1}"
        )
        lines.append(f"{len(lines) + 1}. {str(title).strip()}\n{url}")
    return lines


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split at paragraph boundaries, then hard-split pathological paragraphs."""
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        remaining = paragraph.strip()
        while len(remaining) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(remaining[:max_chars])
            remaining = remaining[max_chars:]
        if not remaining:
            continue
        candidate = remaining if not current else f"{current}\n\n{remaining}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = remaining
    if current:
        chunks.append(current)
    return chunks or [""]


def render_weixin_messages(
    response: Mapping[str, Any],
    *,
    max_chars: int = 3_500,
) -> tuple[str, ...]:
    """Render one public response without exposing local source paths."""
    answer = str(response.get("answer") or "暂时没有可返回的回答。").strip()
    source_lines = _source_lines(response.get("sources"))
    rendered = answer
    if source_lines:
        rendered = f"{rendered}\n\n来源\n" + "\n\n".join(source_lines)

    chunks = _split_text(rendered, max_chars - 16)
    if len(chunks) == 1:
        return (chunks[0],)
    total = len(chunks)
    return tuple(f"[{index}/{total}]\n{chunk}" for index, chunk in enumerate(chunks, start=1))
