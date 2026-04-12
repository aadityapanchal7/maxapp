"""
RAG document ingestion script — syncs local rag_docs/ folder into Supabase pgvector.

Scans: <repo_root>/rag_docs/{maxx_id}/*  (supports .md, .txt, .docx)
Each subfolder name becomes the maxx_id namespace.
Each filename (without extension) becomes the doc_title.

Usage (from the backend/ directory):
    python scripts/ingest_rag_docs.py

Options:
    --maxx_id fitmax     Only ingest docs for a specific module
    --dry-run            Print what would be ingested without writing to DB
    --chunk-size 800     Override chunk size (default: 800 characters)
    --chunk-overlap 100  Override chunk overlap (default: 100 characters)

Requirements:
    - .env file in backend/ (or parent directory) with SUPABASE_DB_* and OPENAI_API_KEY
    - rag_docs/ folder at the repo root (sibling to backend/)
    - pgvector enabled on Supabase (CREATE EXTENSION IF NOT EXISTS vector)
    - python-docx installed for .docx support (already in requirements.txt)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys

# Allow importing backend modules when running from the backend/ directory
_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR / ".env")
load_dotenv(_BACKEND_DIR.parent / ".env", override=False)  # repo-root fallback

# rag_docs/ lives one level above backend/
RAG_DOCS_DIR = _BACKEND_DIR.parent / "rag_docs"

SUPPORTED_EXTENSIONS = {".md", ".txt", ".docx"}
VALID_MAXX_IDS = {"skinmax", "fitmax", "hairmax", "heightmax", "bonemax"}


def read_file_content(path: pathlib.Path) -> str:
    """Read a document file and return its plain text content."""
    ext = path.suffix.lower()
    if ext == ".docx":
        try:
            from docx import Document
        except ImportError:
            raise ImportError(
                "python-docx is required for .docx files. "
                "Run: pip install python-docx"
            )
        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    else:
        return path.read_text(encoding="utf-8")


async def run(
    filter_maxx: str | None = None,
    dry_run: bool = False,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> None:
    if not RAG_DOCS_DIR.exists():
        print(f"[ERROR] rag_docs/ not found at: {RAG_DOCS_DIR}")
        print("  Create the folder and add your docs:")
        print("    rag_docs/fitmax/supplements.md")
        print("    rag_docs/skinmax/routines.md")
        print("    ...")
        sys.exit(1)

    # Collect files to ingest
    jobs: list[tuple[str, str, pathlib.Path]] = []  # (maxx_id, doc_title, path)
    for maxx_dir in sorted(RAG_DOCS_DIR.iterdir()):
        if not maxx_dir.is_dir():
            continue
        maxx_id = maxx_dir.name.lower()
        if maxx_id not in VALID_MAXX_IDS:
            print(f"[SKIP] Unknown folder '{maxx_id}' — not a valid maxx_id")
            continue
        if filter_maxx and maxx_id != filter_maxx:
            continue
        for doc_file in sorted(maxx_dir.iterdir()):
            if doc_file.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            doc_title = doc_file.stem.replace("-", " ").replace("_", " ").title()
            jobs.append((maxx_id, doc_title, doc_file))

    if not jobs:
        print("[INFO] No documents found to ingest.")
        return

    print(f"Found {len(jobs)} document(s) to ingest:")
    for maxx_id, doc_title, path in jobs:
        print(f"  [{maxx_id}] {path.name}  →  \"{doc_title}\"")

    if dry_run:
        print("\n[DRY RUN] No changes written.")
        return

    # Import DB + ingest service after env is loaded
    from db.sqlalchemy import AsyncSessionLocal, init_db
    from services.rag_ingest import ingest_doc

    print("\nInitialising database (running migrations if needed)…")
    await init_db()

    total_chunks = 0
    errors: list[str] = []

    async with AsyncSessionLocal() as db:
        for maxx_id, doc_title, doc_file in jobs:
            try:
                content = read_file_content(doc_file)
                n = await ingest_doc(
                    db=db,
                    content=content,
                    maxx_id=maxx_id,
                    doc_title=doc_title,
                    source_file=str(doc_file),
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
                total_chunks += n
                print(f"  [OK] {maxx_id}/{doc_file.name}  →  {n} chunks")
            except Exception as e:
                msg = f"  [ERROR] {maxx_id}/{doc_file.name}: {e}"
                print(msg)
                errors.append(msg)

    print(f"\nDone. {total_chunks} total chunks ingested across {len(jobs) - len(errors)} doc(s).")
    if errors:
        print(f"{len(errors)} error(s):")
        for err in errors:
            print(err)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest rag_docs/ into Supabase pgvector")
    parser.add_argument("--maxx_id", default=None, help="Only ingest a specific module (e.g. fitmax)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be ingested without writing")
    parser.add_argument("--chunk-size", type=int, default=800, help="Chunk size in characters (default: 800)")
    parser.add_argument("--chunk-overlap", type=int, default=100, help="Chunk overlap in characters (default: 100)")
    args = parser.parse_args()

    asyncio.run(run(
        filter_maxx=args.maxx_id,
        dry_run=args.dry_run,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    ))


if __name__ == "__main__":
    main()
