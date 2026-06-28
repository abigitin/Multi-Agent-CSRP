from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.core.config import get_settings
from backend.integrations.atlassian import KnowledgePage


@dataclass
class PineconeDocument:
    source: str
    title: str
    url: str | None
    text: str
    metadata: dict[str, Any]
    score: float
    updated_at: str


def is_enabled() -> bool:
    settings = get_settings()
    return bool(settings.pinecone_api_key)


def upsert_pages(pages: list[KnowledgePage]) -> int:
    settings = get_settings()
    if not pages:
        return 0
    if not settings.pinecone_api_key:
        if settings.is_production:
            raise RuntimeError("PINECONE_API_KEY is required for production knowledge sync.")
        return 0

    records: list[dict[str, Any]] = []
    for page in pages:
        for chunk_index, chunk in enumerate(chunk_text(page.text)):
            record_id = f"{page.source}:{page.id}:{chunk_index}"
            metadata = {
                key: value
                for key, value in page.metadata.items()
                if key
                not in {
                    "_id",
                    settings.pinecone_embed_field,
                    "source",
                    "record_id",
                    "title",
                    "url",
                    "kind",
                    "updated_at",
                }
            }
            records.append(
                {
                    "_id": record_id,
                    settings.pinecone_embed_field: chunk,
                    "source": page.source,
                    "record_id": page.id,
                    "title": page.title,
                    "url": page.url,
                    "kind": page.kind,
                    "updated_at": page.updated_at or "",
                    **metadata,
                }
            )

    if not records:
        return 0

    try:
        index = _index()
        if settings.pinecone_integrated_embedding:
            index.upsert_records(namespace=settings.pinecone_namespace, records=records)
        else:
            raise RuntimeError("Only integrated-embedding Pinecone indexes are supported for this store.")
    except Exception as exc:
        if settings.is_production:
            raise RuntimeError(f"Pinecone upsert failed: {_safe_error(exc)}") from exc
        return 0
    return len(records)


def search(query: str, limit: int = 4) -> list[PineconeDocument]:
    settings = get_settings()
    if not settings.pinecone_api_key:
        return []
    if not query.strip():
        return []

    try:
        result = _index().search(
            namespace=settings.pinecone_namespace,
            inputs={settings.pinecone_embed_field: query},
            top_k=limit,
            fields=[
                settings.pinecone_embed_field,
                "source",
                "record_id",
                "title",
                "url",
                "kind",
                "updated_at",
            ],
        )
    except Exception:
        if settings.is_production:
            raise
        return []

    return [_document_from_hit(hit) for hit in _hits(result) if _hit_text(hit)]


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def _index():
    settings = get_settings()
    from pinecone import Pinecone

    pc = Pinecone(api_key=settings.pinecone_api_key)
    if settings.pinecone_host:
        return pc.Index(host=settings.pinecone_host)
    return pc.Index(settings.pinecone_index)


def _hits(result: Any) -> list[Any]:
    if isinstance(result, dict):
        nested = result.get("result")
        if isinstance(nested, dict):
            return list(nested.get("hits", []) or nested.get("matches", []) or [])
        return list(result.get("hits", []) or result.get("matches", []) or [])
    nested = getattr(result, "result", None)
    if nested is not None:
        hits = getattr(nested, "hits", None)
        if hits is not None:
            return list(hits)
    hits = getattr(result, "hits", None)
    if hits is not None:
        return list(hits)
    matches = getattr(result, "matches", None)
    if matches is not None:
        return list(matches)
    return []


def _document_from_hit(hit: Any) -> PineconeDocument:
    fields = _hit_fields(hit)
    settings = get_settings()
    text = str(fields.get(settings.pinecone_embed_field) or fields.get("text") or "")
    source = str(fields.get("source") or "pinecone")
    return PineconeDocument(
        source=source,
        title=str(fields.get("title") or source or "Knowledge source"),
        url=fields.get("url"),
        text=text,
        metadata=dict(fields),
        score=float(_hit_score(hit) or 0.0),
        updated_at=str(fields.get("updated_at") or datetime.utcnow().isoformat()),
    )


def _hit_fields(hit: Any) -> dict[str, Any]:
    if isinstance(hit, dict):
        fields = hit.get("fields") or hit.get("metadata") or {}
        return fields if isinstance(fields, dict) else {}
    fields = getattr(hit, "fields", None) or getattr(hit, "metadata", None) or {}
    return fields if isinstance(fields, dict) else {}


def _hit_text(hit: Any) -> str:
    fields = _hit_fields(hit)
    settings = get_settings()
    return str(fields.get(settings.pinecone_embed_field) or fields.get("text") or "")


def _hit_score(hit: Any) -> float:
    if isinstance(hit, dict):
        return float(hit.get("_score") or hit.get("score") or 0.0)
    return float(getattr(hit, "_score", None) or getattr(hit, "score", None) or 0.0)


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    settings = get_settings()
    for secret in (settings.pinecone_api_key,):
        if secret:
            message = message.replace(secret, "[redacted]")
    return message
