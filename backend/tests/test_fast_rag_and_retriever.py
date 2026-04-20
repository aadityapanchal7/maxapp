from __future__ import annotations

import pytest

from services import fast_rag_answer as fast_rag
from services.rag_service import reload_indexes, retrieve_chunks


class _FakeResp:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    def bind(self, **_kwargs):
        return self

    async def ainvoke(self, _messages):
        return _FakeResp("Use sunscreen at night only if your docs say so. [source: skinmax/routines.md > PM routine]")


@pytest.mark.asyncio
async def test_retrieve_chunks_returns_stable_file_chunk_ids():
    reload_indexes()
    rows = await retrieve_chunks(None, "skinmax", "what should i do for acne at night", k=3, min_similarity=0.35)
    assert rows
    for row in rows:
        assert isinstance(row["id"], str)
        assert row["id"]
        assert row["metadata"]["source"]
        assert row["metadata"]["section"]


@pytest.mark.asyncio
async def test_retrieve_chunks_respects_threshold():
    reload_indexes()
    rows = await retrieve_chunks(None, "skinmax", "what should i do for acne at night", k=3, min_similarity=999.0)
    assert rows == []


@pytest.mark.asyncio
async def test_answer_from_chunks_preserves_clean_citations(monkeypatch):
    monkeypatch.setattr(fast_rag, "get_chat_llm_with_fallback", lambda **_kwargs: _FakeLLM())
    retrieved = await fast_rag.gather_rag_evidence(
        message="what should i do for acne at night",
        maxx_hints=["skinmax"],
    )
    assert retrieved
    answer = await fast_rag.answer_from_chunks(
        message="what should i do for acne at night",
        retrieved=retrieved,
    )
    assert "[source:" in answer
    assert "skinmax" in answer.lower()
