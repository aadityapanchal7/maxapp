"""Chunk audit trail: file-based refs stored on chat_history.retrieved_chunk_ids."""

from __future__ import annotations

from api import chat as chat_api


def test_chunk_audit_refs_prefer_stable_id():
    chunks = [
        {
            "id": "routines:0:abc123",
            "metadata": {"source": "rag_docs/skinmax/routines.md", "section": "PM routine"},
        }
    ]
    refs = chat_api._chunk_audit_refs(chunks)
    assert refs == ["routines:0:abc123"]


def test_chunk_audit_refs_fallback_to_source_section():
    chunks = [
        {
            "metadata": {"source": "rag_docs/skinmax/routines.md", "section": "PM routine"},
        }
    ]
    refs = chat_api._chunk_audit_refs(chunks)
    assert refs == ["rag_docs/skinmax/routines.md::PM routine"]


def test_chunk_audit_refs_fallback_to_doc_title_only():
    chunks = [
        {"doc_title": "routines"},
    ]
    refs = chat_api._chunk_audit_refs(chunks)
    assert refs == ["routines"]


def test_chunk_audit_refs_dedupes_and_preserves_order():
    chunks = [
        {"id": "a:0:111"},
        {"id": "b:0:222"},
        {"id": "a:0:111"},  # duplicate
    ]
    refs = chat_api._chunk_audit_refs(chunks)
    assert refs == ["a:0:111", "b:0:222"]


def test_chunk_audit_refs_returns_none_when_empty():
    assert chat_api._chunk_audit_refs([]) is None
    assert chat_api._chunk_audit_refs(None) is None


def test_chunk_audit_refs_skips_non_dicts():
    assert chat_api._chunk_audit_refs([None, "oops", 42]) is None


def test_chunk_audit_refs_supports_file_based_ids_with_numeric_index():
    chunks = [
        {"metadata": {"source": "rag_docs/bonemax/guide.md"}, "chunk_index": 3},
    ]
    refs = chat_api._chunk_audit_refs(chunks)
    assert refs == ["rag_docs/bonemax/guide.md::3"]
