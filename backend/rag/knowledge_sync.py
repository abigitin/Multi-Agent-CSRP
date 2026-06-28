from __future__ import annotations

import json
from datetime import datetime

from backend.core.config import get_settings
from backend.core.database import SessionLocal
from backend.core.models import KnowledgeDocument
from backend.integrations.atlassian import AtlassianClient, KnowledgePage
from backend.rag.pinecone_store import is_enabled as pinecone_enabled
from backend.rag.pinecone_store import upsert_pages


def sync_knowledge_base() -> dict[str, int]:
    settings = get_settings()
    client = AtlassianClient()
    pages = client.fetch_confluence_pages() + client.fetch_jira_issues()
    source = "atlassian" if client.is_configured() else "dev_mock_confluence"
    if not pages:
        if settings.is_production:
            raise RuntimeError("Atlassian knowledge sync returned no pages in production.")
        pages = _mock_pages()
    _persist_documents(pages)
    upserted = _upsert_documents(pages)
    return {
        "documents": len(pages),
        "upserted": upserted,
        "mode": "pinecone" if pinecone_enabled() else "local",
        "source": source,
    }


def _persist_documents(pages: list[KnowledgePage]) -> None:
    db = SessionLocal()
    try:
        for page in pages:
            existing = (
                db.query(KnowledgeDocument)
                .filter(KnowledgeDocument.source == page.source, KnowledgeDocument.source_id == page.id)
                .one_or_none()
            )
            payload = {
                "source": page.source,
                "source_id": page.id,
                "title": page.title,
                "url": page.url,
                "text": page.text,
                "metadata_json": json.dumps(page.metadata, default=str),
                "embedding_status": "pinecone" if pinecone_enabled() else "local",
                "updated_at": datetime.utcnow(),
            }
            if existing:
                for key, value in payload.items():
                    setattr(existing, key, value)
            else:
                db.add(KnowledgeDocument(**payload))
        db.commit()
    finally:
        db.close()


def _upsert_documents(pages: list[KnowledgePage]) -> int:
    return upsert_pages(pages)


def _mock_pages() -> list[KnowledgePage]:
    from backend.rag.confluence_loader import load_documents

    return [
        KnowledgePage(
            id=doc["source"],
            source="mock_confluence",
            title=doc["source"],
            url="",
            text=doc["text"],
            kind="page",
            updated_at=None,
            metadata={"mode": "mock"},
        )
        for doc in load_documents(get_settings().confluence_dir)
    ]
