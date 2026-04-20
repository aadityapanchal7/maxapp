from __future__ import annotations

import pytest

from services import fast_rag_answer as fast_rag
from services import rag_service
from services.rag_service import reload_indexes, retrieve_chunks


# Synthetic in-memory docs used to stand in for Supabase's rag_documents rows.
# Each test that hits retrieval monkeypatches `_fetch_docs_from_db` to return
# this fixture so the BM25 path runs without a real DB.
_FAKE_SKINMAX_DOCS: list[tuple[str, str]] = [
    (
        "routines",
        "# Skinmax Routines\n\n## PM routine\nAt night use a gentle cleanser, then adapalene, "
        "then a moisturizer. Acne-prone skin benefits from this order.\n\n"
        "## AM routine\nCleanser, niacinamide, moisturizer, spf. Skip exfoliants in the morning.\n",
    ),
    (
        "acne",
        "## Acne basics\nAdapalene at night for acne works best with consistent use. "
        "Avoid harsh scrubs — they irritate breakouts.\n",
    ),
]


def _install_fake_docs(monkeypatch, docs=None):
    docs = docs if docs is not None else _FAKE_SKINMAX_DOCS

    async def _fake_fetch(_maxx: str) -> list[tuple[str, str]]:
        return list(docs)

    monkeypatch.setattr(rag_service, "_fetch_docs_from_db", _fake_fetch)
    reload_indexes()


class _FakeResp:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    def bind(self, **_kwargs):
        return self

    async def ainvoke(self, _messages):
        return _FakeResp("Use sunscreen at night only if your docs say so. [source: skinmax/routines.md > PM routine]")


@pytest.mark.asyncio
async def test_retrieve_chunks_returns_stable_file_chunk_ids(monkeypatch):
    _install_fake_docs(monkeypatch)
    rows = await retrieve_chunks(None, "skinmax", "what should i do for acne at night", k=3, min_similarity=0.0)
    assert rows
    for row in rows:
        assert isinstance(row["id"], str)
        assert row["id"]
        assert row["metadata"]["source"]
        assert row["metadata"]["section"]


@pytest.mark.asyncio
async def test_retrieve_chunks_respects_threshold(monkeypatch):
    _install_fake_docs(monkeypatch)
    rows = await retrieve_chunks(None, "skinmax", "what should i do for acne at night", k=3, min_similarity=999.0)
    assert rows == []


@pytest.mark.asyncio
async def test_answer_from_chunks_preserves_clean_citations(monkeypatch):
    _install_fake_docs(monkeypatch)
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
