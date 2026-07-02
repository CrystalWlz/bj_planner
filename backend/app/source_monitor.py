from __future__ import annotations

import hashlib
import re

import httpx

from .database import insert_source_document, latest_source_hash


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def html_to_text(html: str) -> str:
    text = TAG_RE.sub(" ", html)
    text = SPACE_RE.sub(" ", text)
    return text.strip()


async def fetch_preview(url: str, name: str | None = None) -> dict:
    previous_hash = latest_source_hash(url)
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    text = html_to_text(response.text)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    summary = text[:800]
    changed = previous_hash is None or previous_hash != content_hash
    record = insert_source_document(
        name=name or url,
        url=url,
        content_hash=content_hash,
        status="pending_review",
        summary=summary,
    )
    record["changed_from_previous"] = changed
    return record

