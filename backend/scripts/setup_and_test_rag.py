"""
RAG setup and test script.

Run this after enabling pgvector in the Supabase dashboard.

Usage (from backend/ directory):
    python scripts/setup_and_test_rag.py

Steps:
  1. Verifies pgvector extension is active
  2. Creates rag_documents table
  3. Tests embedding (OpenAI API)
  4. Ingests the placeholder docs from rag_docs/
  5. Tests retrieval with a sample query
"""

from __future__ import annotations
import asyncio
import os
import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR / ".env")

STEP = 0
def step(msg: str):
    global STEP
    STEP += 1
    print(f"\n[{STEP}] {msg}")

def ok(msg: str = ""):
    print(f"    ✓  {msg}" if msg else "    ✓")

def fail(msg: str):
    print(f"    ✗  {msg}")
    sys.exit(1)


async def main():
    # ------------------------------------------------------------------
    step("Checking OPENAI_API_KEY")
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or key.startswith("your-"):
        fail("OPENAI_API_KEY not set in .env")
    ok(f"key ends with …{key[-6:]}")

    # ------------------------------------------------------------------
    step("Connecting to Supabase")
    from db.sqlalchemy import engine
    from sqlalchemy import text
    try:
        async with engine.connect() as conn:
            r = await conn.execute(text("SELECT 1"))
            r.fetchone()
        ok("connected")
    except Exception as e:
        fail(f"Cannot connect to Supabase: {e}")

    # ------------------------------------------------------------------
    step("Checking pgvector extension")
    async with engine.connect() as conn:
        r = await conn.execute(text(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ))
        row = r.fetchone()
    if not row:
        fail(
            "pgvector extension is NOT enabled.\n\n"
            "    → Go to: https://supabase.com/dashboard/project/nlzsqnlkixcfkncpoqku/database/extensions\n"
            "    → Search for 'vector' and click Enable\n"
            "    → Then re-run this script"
        )
    ok(f"pgvector v{row[0]} active")

    # ------------------------------------------------------------------
    step("Creating rag_documents table")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS rag_documents (
                    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    maxx_id     VARCHAR(50)  NOT NULL,
                    doc_title   VARCHAR(255) NOT NULL,
                    chunk_index INTEGER      NOT NULL DEFAULT 0,
                    content     TEXT         NOT NULL,
                    embedding   VECTOR(1536) NOT NULL,
                    metadata    JSONB        NOT NULL DEFAULT '{}',
                    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
                    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_rag_docs_maxx_id ON rag_documents (maxx_id)"
            ))
        ok("rag_documents table ready")
    except Exception as e:
        fail(f"Table creation failed: {e}")

    # ------------------------------------------------------------------
    step("Testing OpenAI embeddings")
    try:
        from langchain_openai import OpenAIEmbeddings
        embedder = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=key)
        vec = await asyncio.to_thread(embedder.embed_query, "test query")
        assert len(vec) == 1536, f"expected 1536 dims, got {len(vec)}"
        ok(f"embedding works — 1536 dimensions")
    except Exception as e:
        fail(f"Embedding failed: {e}")

    # ------------------------------------------------------------------
    step("Ingesting docs from rag_docs/")
    rag_docs_dir = _BACKEND_DIR.parent / "rag_docs"
    if not rag_docs_dir.exists():
        fail(f"rag_docs/ not found at {rag_docs_dir}")

    from db.sqlalchemy import AsyncSessionLocal
    from services.rag_ingest import ingest_doc

    total = 0
    errors = []
    VALID = {"skinmax", "fitmax", "hairmax", "heightmax", "bonemax"}

    async with AsyncSessionLocal() as db:
        for maxx_dir in sorted(rag_docs_dir.iterdir()):
            if not maxx_dir.is_dir() or maxx_dir.name not in VALID:
                continue
            for doc_file in sorted(maxx_dir.glob("*")):
                if doc_file.suffix.lower() not in {".md", ".txt", ".docx"}:
                    continue
                try:
                    if doc_file.suffix.lower() == ".docx":
                        from docx import Document
                        doc = Document(str(doc_file))
                        content = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
                    else:
                        content = doc_file.read_text(encoding="utf-8")

                    doc_title = doc_file.stem.replace("-", " ").replace("_", " ").title()
                    n = await ingest_doc(db, content, maxx_dir.name, doc_title, str(doc_file))
                    total += n
                    print(f"    ✓  {maxx_dir.name}/{doc_file.name}  →  {n} chunks")
                except Exception as e:
                    msg = f"{maxx_dir.name}/{doc_file.name}: {e}"
                    errors.append(msg)
                    print(f"    ✗  {msg}")

    if errors:
        print(f"\n    {len(errors)} error(s) during ingestion")
    ok(f"{total} total chunks ingested")

    # ------------------------------------------------------------------
    step("Testing retrieval")
    from db.sqlalchemy import AsyncSessionLocal
    from services.rag_service import retrieve_chunks

    test_cases = [
        ("fitmax",    "supplements and protein",        0.0),
        ("fitmax",    "hi",                             0.0),   # should return [] or low-sim chunks filtered
        ("skinmax",   "morning skincare routine",       0.0),
    ]

    async with AsyncSessionLocal() as db:
        for maxx_id, query, _ in test_cases:
            chunks = await retrieve_chunks(db, maxx_id=maxx_id, query=query, k=3)
            sim_info = f"top similarity={chunks[0]['similarity']:.2f}" if chunks else "no chunks (below threshold)"
            print(f"    query={query!r:40s}  [{maxx_id}]  →  {len(chunks)} chunk(s)  {sim_info}")

    print("\n" + "="*60)
    print("RAG pipeline is ready!")
    print("="*60)
    print("\nNext steps:")
    print("  1. Replace placeholder .md files in rag_docs/ with your real content")
    print("  2. Re-run the ingest script:  python scripts/ingest_rag_docs.py")
    print("  3. Start the backend and test a chat message")


if __name__ == "__main__":
    asyncio.run(main())
