"""OpenAI embeddings wrapper.

Uses the OpenAI SDK (already a dependency) regardless of LLM_PROVIDER, because
Gemini embeddings live in a different dimensional space and we've committed to
1536-dim in the pgvector column. Keep embeddings on one provider.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Sequence

from config import settings

logger = logging.getLogger(__name__)


def _client():
    from openai import OpenAI

    key = (settings.openai_api_key or "").strip()
    if not key:
        raise ValueError(
            "OPENAI_API_KEY is not set — required for RAG embeddings even when "
            "LLM_PROVIDER=gemini. Set it in .env."
        )
    return OpenAI(api_key=key)


async def embed_texts(texts: Sequence[str]) -> List[List[float]]:
    """Embed a batch of strings. Returns one vector per input, preserving order."""
    if not texts:
        return []

    def _sync() -> List[List[float]]:
        client = _client()
        # OpenAI caps each request at ~300k tokens total; batches of 100 short chunks are safe.
        resp = client.embeddings.create(
            model=settings.embedding_model,
            input=list(texts),
        )
        return [d.embedding for d in resp.data]

    return await asyncio.to_thread(_sync)


async def embed_one(text: str) -> List[float]:
    vectors = await embed_texts([text])
    return vectors[0]
