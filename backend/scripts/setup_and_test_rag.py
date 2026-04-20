"""Validate the live file-based RAG and run a few sample retrievals."""

from __future__ import annotations

import asyncio
import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from services.fast_rag_answer import answer_from_rag
from services.rag_service import reload_indexes, retrieve_chunks


async def main() -> None:
    rag_docs_dir = _BACKEND_DIR.parent / "rag_docs"
    if not rag_docs_dir.exists():
        raise SystemExit(f"rag_docs/ not found at {rag_docs_dir}")

    reload_indexes()
    print("[OK] Cleared cached indexes.")

    test_cases = [
        ("fitmax", "supplements and protein"),
        ("skinmax", "morning skincare routine"),
        ("bonemax", "what is mewing"),
    ]
    for maxx_id, query in test_cases:
        chunks = await retrieve_chunks(None, maxx_id=maxx_id, query=query, k=3)
        sim_info = f"top={chunks[0]['similarity']:.2f}" if chunks else "no chunks"
        print(f"[RETRIEVE] {maxx_id:8s} {query!r:32s} -> {len(chunks)} chunk(s) {sim_info}")

    answer, chunks = await answer_from_rag(
        message="what should i do for acne at night",
        maxx_hints=["skinmax"],
    )
    print("\n[ANSWER]")
    print(answer or "[no answer]")
    print(f"[chunks={len(chunks)}]")


if __name__ == "__main__":
    asyncio.run(main())
