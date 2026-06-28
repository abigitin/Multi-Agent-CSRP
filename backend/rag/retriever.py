from __future__ import annotations

import re
from dataclasses import dataclass

from backend.core.config import get_settings
from backend.rag.embeddings import embed_text
from backend.rag.confluence_loader import load_documents
from backend.rag.pinecone_store import search as pinecone_search


@dataclass
class ContextChunk:
    source: str
    text: str
    score: float


class SupportRetriever:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.documents = load_documents(self.settings.confluence_dir)

    def retrieve(self, query: str, limit: int = 3) -> list[str]:
        pinecone_hits = self._pinecone_retrieve(query, limit)
        if pinecone_hits or (self.settings.pinecone_api_key and self.settings.is_production):
            chunks = pinecone_hits
        else:
            chunks = self._local_retrieve(query, limit)
        return [f"[{chunk.source}] {chunk.text.strip()}" for chunk in chunks]

    def _local_retrieve(self, query: str, limit: int) -> list[ContextChunk]:
        query_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        query_vector = embed_text(query)
        ranked: list[ContextChunk] = []
        for doc in self.documents:
            text = doc["text"]
            doc_terms = set(re.findall(r"[a-z0-9]+", text.lower()))
            lexical_score = len(query_tokens & doc_terms) / max(len(query_tokens), 1)
            doc_vector = embed_text(text)
            semantic_score = _cosine_similarity(query_vector, doc_vector)
            score = (lexical_score * 0.35) + (semantic_score * 0.65)
            if score:
                ranked.append(ContextChunk(doc["source"], text, score))
        return sorted(ranked, key=lambda chunk: chunk.score, reverse=True)[:limit]

    def _pinecone_retrieve(self, query: str, limit: int) -> list[ContextChunk]:
        if not self.settings.pinecone_api_key:
            return []
        try:
            return [
                ContextChunk(doc.source, doc.text, doc.score)
                for doc in pinecone_search(query, limit)
                if doc.text
            ]
        except Exception:
            if self.settings.is_production:
                raise
            return []


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(y * y for y in b) ** 0.5
    if not mag_a or not mag_b:
        return 0.0
    return dot / (mag_a * mag_b)
