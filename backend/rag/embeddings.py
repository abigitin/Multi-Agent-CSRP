from __future__ import annotations

from functools import lru_cache
import hashlib
import re

from backend.core.config import get_settings


@lru_cache
def _model():
    settings = get_settings()
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None

    try:
        return SentenceTransformer(settings.embedding_model)
    except Exception:
        return None


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _model()
    if model is None:
        return [_fallback_embedding(text) for text in texts]
    try:
        vectors = model.encode(texts, normalize_embeddings=True).tolist()
    except Exception:
        return [_fallback_embedding(text) for text in texts]
    return [[float(value) for value in vector] for vector in vectors]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def _fallback_embedding(text: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    magnitude = sum(value * value for value in vector) ** 0.5
    if not magnitude:
        return vector
    return [value / magnitude for value in vector]
