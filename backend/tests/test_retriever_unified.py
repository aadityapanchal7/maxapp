"""Unified BM25 retriever coverage — edge cases and stable IDs."""

from __future__ import annotations

import pytest

from services import rag_service
from services.rag_service import (
    VALID_MAXX_IDS,
    _chunk_id,
    _tokenize,
    reload_indexes,
    retrieve_chunks,
)


_FAKE_SKINMAX_DOCS = [
    (
        "routines",
        "# Skinmax Routines\n\n## PM routine\nAt night use a gentle cleanser, then adapalene, "
        "then a moisturizer. Acne-prone skin benefits from this order.\n\n"
        "## AM routine\nCleanser, niacinamide, moisturizer, spf.\n",
    ),
]


def _install_fake_docs(monkeypatch):
    async def _fake_fetch(_maxx: str):
        return list(_FAKE_SKINMAX_DOCS)

    monkeypatch.setattr(rag_service, "_fetch_docs_from_db", _fake_fetch)
    reload_indexes()


def test_tokenize_drops_stopwords_and_punct():
    tokens = _tokenize("What should I do for acne at night?")
    assert "what" not in tokens
    assert "should" not in tokens
    assert "acne" in tokens
    assert "night" in tokens


def test_chunk_id_is_stable_and_scoped_to_source():
    a = _chunk_id(source="rag_docs/skinmax/a.md", doc_title="a", section="PM", chunk_index=0)
    b = _chunk_id(source="rag_docs/skinmax/a.md", doc_title="a", section="PM", chunk_index=0)
    c = _chunk_id(source="rag_docs/skinmax/b.md", doc_title="b", section="PM", chunk_index=0)
    assert a == b
    assert a != c
    assert a.startswith("a:0:")


@pytest.mark.asyncio
async def test_retrieve_chunks_rejects_empty_query():
    reload_indexes()
    assert await retrieve_chunks(None, "skinmax", "", k=3) == []
    assert await retrieve_chunks(None, "skinmax", "   ", k=3) == []


@pytest.mark.asyncio
async def test_retrieve_chunks_rejects_unknown_maxx():
    reload_indexes()
    assert await retrieve_chunks(None, "unknownmax", "acne", k=3) == []


@pytest.mark.asyncio
async def test_retrieve_chunks_valid_modules_only():
    assert "skinmax" in VALID_MAXX_IDS
    assert "fitmax" in VALID_MAXX_IDS
    assert "hairmax" in VALID_MAXX_IDS
    assert "heightmax" in VALID_MAXX_IDS
    assert "bonemax" in VALID_MAXX_IDS


@pytest.mark.asyncio
async def test_retrieve_chunks_carries_metadata_source_and_section(monkeypatch):
    _install_fake_docs(monkeypatch)
    rows = await retrieve_chunks(None, "skinmax", "pm routine acne", k=2, min_similarity=0.0)
    assert rows
    for row in rows:
        meta = row.get("metadata") or {}
        assert meta.get("source"), "metadata.source required for audit trail"
        assert meta.get("section"), "metadata.section required for audit trail"
        assert isinstance(row["id"], str) and row["id"]


@pytest.mark.asyncio
async def test_retrieve_chunks_logs_telemetry(monkeypatch):
    calls: list[dict] = []

    def _capture(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(rag_service, "log_retrieval", _capture)
    _install_fake_docs(monkeypatch)
    await retrieve_chunks(None, "skinmax", "pm routine acne", k=2, min_similarity=0.0)
    assert calls
    latest = calls[-1]
    assert latest["maxx_id"] == "skinmax"
    assert latest["threshold"] == 0.0
    assert latest["query_tokens"] >= 1
    assert latest["hits"] >= 0
